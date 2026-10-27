"""Оценка правила «тот же товар» (app.services.product_name_signature) на
реальных выгрузках C:\\Users\\1\\Downloads\\Товары и ТЗ\\ (владелец,
27.10.2026). Разовый offline-скрипт — ничего не пишет в БД.

Переиспользует (ПРАВИЛО №6, не копирует):
  - app.services.product_name_signature.{build_signature, match} — сама
    проверка;
  - tools.catalog_enrich.brand_dictionary.BrandDictionary — словарь брендов
    (та же структура, что у обогащения Кувалды), здесь просто засеян
    manufacturer-полями всех оцениваемых выгрузок (не кувалда-специфичным
    build_kuvalda_brand_dictionary — тот тянет кэш страниц, здесь не нужен);
  - tools.catalog_enrich.gala_quality_loader.load_catalog_gala() — тот же
    способ импортировать app.services.catalog_gala.* офлайн, без поднятия
    БД (единственное отличие от прямого `python -m scripts.…`: этот файл
    запускается и из backend/, и как отдельный offline-скрипт, поэтому
    sys.path настраивается тем же загрузчиком, не второй копией).

Эффективность (владелец, уточнение: "не O(N×M) по 150 тыс"): кандидаты
ищутся через индекс store→{digit_tokens: [сигнатуры]} — пары сравниваются
ТОЛЬКО внутри одного ключа digit_tokens (товары без цифр в названии в
индекс не попадают вовсе — слишком неспецифичны, см. REPORT в конце файла).

Запуск:
    cd backend && SECRET_KEY=x python scripts/eval_name_signature.py
"""
import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "eval_name_signature_offline_not_real")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_PROJECT_ROOT / "tools" / "catalog_enrich"))

from app.services.product_name_signature import build_signature, match  # noqa: E402

from brand_dictionary import BrandDictionary  # noqa: E402
from gala_quality_loader import load_catalog_gala  # noqa: E402

DATA_DIR = Path(r"C:\Users\1\Downloads\Товары и ТЗ")
SCRATCH_DIR = Path(
    r"C:\Users\1\AppData\Local\Temp\claude\c--Users-1-Desktop-Cursor-VSKS-CRM"
    r"\4f85c333-7946-400c-aef0-3ff425d8e435\scratchpad"
)

STORE_FILES = {
    "k_spasatel": "k_spasatel_rescue_nomenclature.json",
    "fire_equipment": "fire_equipment_nomenclature.enriched.json",
    "kns": "kns_computers_office_equipment.json",
    "regard": "regard_computers_office_equipment.enriched.json",
    "kuvalda": "kuvalda_tools_hardware_equipment.enriched.json",
    "baucenter_tools_hardware": "baucenter_tools_hardware.json",
    "baucenter_electro_lighting": "baucenter_electro_lighting.json",
    "baucenter_construction_all": "baucenter_construction_all.json",
    "sima_land": "sima_land_catalog_all.json",
}

PAIRS = [
    ("k_spasatel", "fire_equipment"),
    ("kns", "regard"),
    ("kuvalda", "baucenter_tools_hardware"),
    ("kuvalda", "baucenter_electro_lighting"),
    ("kuvalda", "baucenter_construction_all"),
    ("kuvalda", "kns"),
    ("sima_land_branded", "baucenter_branded"),  # особый случай, см. ниже
]


def _load_items(name: str) -> list:
    path = DATA_DIR / STORE_FILES[name]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items") if isinstance(data, dict) else data


def _build_brand_dictionary(quality, item_lists: list) -> BrandDictionary:
    d = BrandDictionary(quality)
    for items in item_lists:
        for it in items:
            manufacturer = it.get("manufacturer")
            if not manufacturer:
                continue
            if quality.is_bogus_manufacturer(manufacturer, it.get("name")):
                continue
            d.add(manufacturer)
    d.finalize()
    return d


def _specific_tokens(digit_tokens: frozenset) -> frozenset:
    """Для КЛЮЧА индекса (не для самой проверки — match() по-прежнему
    сравнивает ПОЛНЫЙ digit_tokens точно) выбрасываем "голые" числа длиной
    1-2 без букв ("2", "10", "100"...) — проверено на sima_land_catalog_all
    (152 652 товара): 132 таких ключа собирают >100 товаров каждый,
    "10" — 1584 товара, "5" — 1413, "2" — 1316 и т.д. (количество/артикул-
    остаток, не код модели). Без этого фильтра одна пара магазинов
    (sima_land×baucenter) даёт 2 676 589 "no"-пар на 959 ключах — техническая
    корректность не страдает (match() ниже всё равно жёстко проверяет полный
    набор чисел), но для ЭФФЕКТИВНОСТИ (владелец: "не O(N×M) по 150 тыс")
    такие ключи как якорь кандидатов бесполезны и только раздувают перебор."""
    return frozenset(t for t in digit_tokens if not (t.isdigit() and len(t) <= 2))


def _index_by_digits(sigs: list) -> dict:
    """store -> {specific_tokens: [сигнатуры]}. Товары без цифр ИЛИ только
    с "голыми" короткими числами в названии НЕ индексируются (слишком
    неспецифичны для безопасного авто-сведения — см. _specific_tokens)."""
    idx = defaultdict(list)
    for s in sigs:
        key = _specific_tokens(s.digit_tokens)
        if key:
            idx[key].append(s)
    return idx


def _reason_bucket(reason: str) -> str:
    """Грубая классификация причины match() для распределения в отчёте
    (владелец, 27.10.2026: "посчитай распределение причин")."""
    if reason.startswith("бренд"):
        return "бренд разный"
    if reason.startswith("вид товара"):
        return "вид товара разный"
    if reason.startswith("числа/индекс"):
        return "цифровые токены разные"
    if reason.startswith("цвет"):
        return "цвет"
    if reason.startswith("масса"):
        return "масса"
    if reason.startswith("страна"):
        return "страна"
    if "слабо похожи" in reason:
        return "название мало похоже"
    if reason.startswith("«"):
        return "характеристика (JSON)"
    return "другое/свойство из названия"


def _eval_pair(name_a, sigs_a, name_b, sigs_b, out_dir: Path, sample_no: bool = False) -> dict:
    idx_a = _index_by_digits(sigs_a)
    idx_b = _index_by_digits(sigs_b)
    common_keys = set(idx_a) & set(idx_b)

    auto_rows, check_rows, no_rows = [], [], []
    reason_counts = defaultdict(int)
    counted = {"auto": 0, "check": 0, "no": 0}
    for key in common_keys:
        group_a, group_b = idx_a[key], idx_b[key]
        for a in group_a:
            peers_a = tuple(x for x in group_a if x is not a)
            for b in group_b:
                peers_b = tuple(x for x in group_b if x is not b)
                res = match(a, b, peers_a=peers_a, peers_b=peers_b)
                counted[res["decision"]] += 1
                if res["decision"] == "auto":
                    auto_rows.append((a, b, res))
                elif res["decision"] == "check":
                    check_rows.append((a, b, res))
                elif sample_no:
                    reason_counts[_reason_bucket(res["reason"])] += 1
                    no_rows.append((a, b, res))

    pair_tag = f"{name_a}_{name_b}"
    auto_path = out_dir / f"sig_auto_{pair_tag}.txt"
    with auto_path.open("w", encoding="utf-8") as f:
        for a, b, res in auto_rows:
            f.write(f"{a.brand or ''} | {sorted(a.digit_tokens)} | "
                    f"{name_a}: {a.name} | {name_b}: {b.name}\n")

    check_sample = random.Random(42).sample(check_rows, min(30, len(check_rows)))
    check_path = out_dir / f"sig_check_{pair_tag}.txt"
    with check_path.open("w", encoding="utf-8") as f:
        for a, b, res in check_sample:
            f.write(f"{a.brand or ''} | {sorted(a.digit_tokens)} | "
                    f"{name_a}: {a.name} | {name_b}: {b.name} | {res['reason']}\n")

    result = {
        "pair": pair_tag,
        "items_a": len(sigs_a), "items_b": len(sigs_b),
        "common_digit_keys": len(common_keys),
        "auto": counted["auto"], "check": counted["check"], "no": counted["no"],
        "auto_file": str(auto_path), "check_file": str(check_path),
    }

    if sample_no and no_rows:
        no_sample = random.Random(42).sample(no_rows, min(40, len(no_rows)))
        # владелец назвал файл конкретно так, см. задание 27.10.2026.
        no_file_tag = "kuvalda_baucenter_tools" if pair_tag == "kuvalda_baucenter_tools_hardware" else pair_tag
        no_path = out_dir / f"sig_no_{no_file_tag}.txt"
        with no_path.open("w", encoding="utf-8") as f:
            for a, b, res in no_sample:
                f.write(f"{a.brand or ''} | {sorted(a.digit_tokens)} | "
                        f"{name_a}: {a.name} | {name_b}: {b.name} | {res['reason']}\n")
        result["no_file"] = str(no_path)
        result["no_reason_distribution"] = dict(
            sorted(reason_counts.items(), key=lambda kv: -kv[1])
        )

    return result


def main():
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    quality = load_catalog_gala()

    print("Загрузка файлов…")
    raw_items = {}
    for name in STORE_FILES:  # все файлы нужны хотя бы одной паре
        raw_items[name] = _load_items(name)
        print(f"  {name}: {len(raw_items[name])} строк")

    print("Сборка словаря брендов…")
    brand_dict = _build_brand_dictionary(quality, raw_items.values())
    print(f"  brand_dictionary: {len(brand_dict)} брендов")

    print("Построение сигнатур…")
    sigs = {name: [build_signature(it, brand_dictionary=brand_dict) for it in items]
            for name, items in raw_items.items()}

    # sima_land <-> baucenter* — только товары, где бренд найден (owner,
    # "только товары, где бренд найден"), baucenter — объединение трёх файлов.
    baucenter_all = (sigs["baucenter_tools_hardware"] + sigs["baucenter_electro_lighting"]
                      + sigs["baucenter_construction_all"])
    sigs["sima_land_branded"] = [s for s in sigs["sima_land"] if s.brand]
    sigs["baucenter_branded"] = [s for s in baucenter_all if s.brand]

    results = []
    for a, b in PAIRS:
        print(f"Пара {a} <-> {b}…")
        sample_no = (a, b) == ("kuvalda", "baucenter_tools_hardware")
        res = _eval_pair(a, sigs[a], b, sigs[b], SCRATCH_DIR, sample_no=sample_no)
        results.append(res)
        print(f"  items A={res['items_a']} B={res['items_b']} "
              f"общих ключей={res['common_digit_keys']} "
              f"auto={res['auto']} check={res['check']} no={res['no']}")

    report_path = SCRATCH_DIR / "sig_eval_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОтчёт: {report_path}")


if __name__ == "__main__":
    main()
