"""CLI-отчёт: проверка app.services.product_type_keys на двух реальных
выгрузках пожарной безопасности (владелец, 27.10.2026) — k_spasatel_rescue_
nomenclature.json (Спасатель) и fire_equipment_nomenclature.json (Магазин
01), формат GALA (см. app.services.catalog_gala.format) — те же поля name/
characteristics/manufacturer/category_path, что отдаёт
catalog_gala.from_store_nomenclature.convert().

Запуск (из backend/, без БД — скрипт её не трогает):
    python -m scripts.eval_type_keys
    python -m scripts.eval_type_keys --dir "C:\\Users\\1\\Downloads\\Товары и ТЗ"

Своей логики сравнения ключей НЕ пишет (ПРАВИЛО №6) — вызывает ТОЛЬКО
product_type_keys.type_key() и product_type_keys.keys_match_unique()
(которая внутри зовёт keys_match()); если в будущем появится реальное
автосведение каталога, оно обязано вызывать те же функции, а не копировать
их — ОСОБЕННО keys_match_unique: правило однозначности (1-к-1 в каждом
магазине под одним ключом) должно применяться там же, где загрузка
сверяет кандидата с уже загруженными карточками (владелец, 27.10.2026,
правка после обзора 40 пар)."""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.product_type_keys import type_key, keys_match, keys_match_unique  # noqa: E402

DEFAULT_DIR = r"C:\Users\1\Downloads\Товары и ТЗ"
SPASATEL_FILE = "k_spasatel_rescue_nomenclature.json"
MAGAZIN01_FILE = "fire_equipment_nomenclature.json"

CONFIDENT_EXAMPLES = 8
CHECK_EXAMPLES = 5

_SCRATCHPAD = (
    r"C:\Users\1\AppData\Local\Temp\claude\c--Users-1-Desktop-Cursor-VSKS-CRM"
    r"\4f85c333-7946-400c-aef0-3ff425d8e435\scratchpad"
)
# Куда выгружать ВСЕ пары "уверенно" (огнетушители+рукава) — владелец,
# 27.10.2026. Один файл, по строке на пару.
CONFIDENT_PAIRS_DUMP = _SCRATCHPAD + r"\type_key_confident_pairs.txt"
# 15 примеров "проверить" с причиной — владелец, 27.10.2026, правка после
# обзора 40 пар.
CHECK_PAIRS_DUMP = _SCRATCHPAD + r"\type_key_check_pairs.txt"
CHECK_PAIRS_DUMP_LIMIT = 15
DUMP_KINDS = ("огнетушитель", "рукав")


def load_items(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["items"] if isinstance(data, dict) else data


def classify(items: list) -> dict:
    """kind -> list of (item, TypeKeyResult)."""
    by_kind = defaultdict(list)
    for item in items:
        result = type_key(
            item.get("name"),
            item.get("characteristics"),
            item.get("manufacturer"),
            item.get("category_path"),
        )
        if result is not None:
            by_kind[result.kind].append((item, result))
    return by_kind


def _ambiguity_reason(result_a, result_b, results_a, results_b) -> str:
    """Причина для пары, у которой буквенный key совпал (keys_match ==
    "уверенно"), но keys_match_unique понизил до "проверить" — сколько
    карточек с этим же ключом у каждой стороны (правило однозначности,
    владелец, 27.10.2026)."""
    count_a = sum(1 for r in results_a if r is not None and r.kind == result_a.kind and r.key == result_a.key)
    count_b = sum(1 for r in results_b if r is not None and r.kind == result_b.kind and r.key == result_b.key)
    return f"неоднозначно: ключ совпал, но у Спасателя {count_a} карточек, у Магазин01 {count_b} карточек с этим ключом"


def _diff_reason(a_result, b_result) -> str:
    """Человекочитаемая причина, почему пара НЕ "уверенно"/"проверить" —
    какой конкретно признак разошёлся или не извлёкся, для отчёта."""
    if a_result.key is not None and b_result.key is not None:
        for field_a, field_b in zip(a_result.key, b_result.key):
            if field_a != field_b:
                return f"key: {field_a!r} != {field_b!r}"
    missing = set(a_result.missing) | set(b_result.missing)
    if missing:
        return "не извлеклось: " + ", ".join(sorted(missing))
    return "?"


def compare_kind(kind: str, spas_list: list, m01_list: list) -> dict:
    """Возвращает confident/check-пары с ПРИЧИНОЙ у каждой check-пары —
    либо "неоднозначно" (ключ совпал, но не 1-к-1, см. keys_match_unique),
    либо обычное расхождение признака/отсутствие (_diff_reason)."""
    confident_pairs = []
    check_pairs = []
    results_a = [r for _, r in spas_list]
    results_b = [r for _, r in m01_list]
    for item_a, result_a in spas_list:
        for item_b, result_b in m01_list:
            base_verdict = keys_match(result_a, result_b)
            if base_verdict is None:
                continue
            final_verdict = keys_match_unique(result_a, result_b, results_a, results_b)
            if final_verdict == "уверенно":
                confident_pairs.append((item_a, item_b, result_a, result_b))
            elif base_verdict == "уверенно":
                # Ключ совпал побуквенно, но не прошёл правило однозначности.
                reason = _ambiguity_reason(result_a, result_b, results_a, results_b)
                check_pairs.append((item_a, item_b, result_a, result_b, reason))
            else:
                reason = _diff_reason(result_a, result_b)
                check_pairs.append((item_a, item_b, result_a, result_b, reason))
    return {"confident": confident_pairs, "check": check_pairs}


def print_report(spas_by_kind: dict, m01_by_kind: dict) -> dict:
    """Печатает отчёт по всем видам, возвращает {kind: compare_kind(...)}
    для последующей выгрузки в файлы (без пересчёта сравнения второй раз —
    ПРАВИЛО №6)."""
    all_kinds = sorted(set(spas_by_kind) | set(m01_by_kind))
    comparisons = {}
    for kind in all_kinds:
        spas_list = spas_by_kind.get(kind, [])
        m01_list = m01_by_kind.get(kind, [])
        print(f"\n=== {kind} ===")
        print(f"Распознано: Спасатель={len(spas_list)}, Магазин01={len(m01_list)}")

        comparison = compare_kind(kind, spas_list, m01_list)
        comparisons[kind] = comparison
        confident = comparison["confident"]
        check = comparison["check"]
        print(f"Уверенно (полный ключ совпал, 1-к-1 в каждом магазине): {len(confident)}")
        print(f"Проверить (ключ совпал неоднозначно, или только бренд+модель/код, или что-то разошлось/не извлеклось): {len(check)}")

        print(f"-- Примеры «уверенно» (до {CONFIDENT_EXAMPLES}):")
        for item_a, item_b, result_a, result_b in confident[:CONFIDENT_EXAMPLES]:
            print(f"   Спасатель: {item_a.get('name')!r}")
            print(f"   Магазин01: {item_b.get('name')!r}")
            print(f"   key: {result_a.key}")
            print()

        print(f"-- Примеры «проверить» (до {CHECK_EXAMPLES}), с причиной расхождения:")
        for item_a, item_b, result_a, result_b, reason in check[:CHECK_EXAMPLES]:
            print(f"   Спасатель: {item_a.get('name')!r}")
            print(f"   Магазин01: {item_b.get('name')!r}")
            print(f"   расходится: {reason}")
            print()
    return comparisons


def dump_confident_pairs(comparisons: dict, out_path: str) -> int:
    """Выгружает ВСЕ пары "уверенно" для DUMP_KINDS в один файл, строка на
    пару: вид | ключ | Спасатель: название | Магазин 01: название
    (владелец, 27.10.2026)."""
    lines = []
    for kind in DUMP_KINDS:
        for item_a, item_b, result_a, result_b in comparisons.get(kind, {}).get("confident", []):
            lines.append(
                f"{kind} | {result_a.key} | "
                f"Спасатель: {item_a.get('name')} | "
                f"Магазин 01: {item_b.get('name')}"
            )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def dump_check_pairs(comparisons: dict, out_path: str, limit: int) -> int:
    """Выгружает до `limit` примеров "проверить" (суммарно по DUMP_KINDS,
    в порядке видов) с причиной, строка на пару: вид | Спасатель: название
    | Магазин 01: название | причина: ... (владелец, 27.10.2026)."""
    lines = []
    for kind in DUMP_KINDS:
        for item_a, item_b, result_a, result_b, reason in comparisons.get(kind, {}).get("check", []):
            if len(lines) >= limit:
                break
            lines.append(
                f"{kind} | "
                f"Спасатель: {item_a.get('name')} | "
                f"Магазин 01: {item_b.get('name')} | "
                f"причина: {reason}"
            )
        if len(lines) >= limit:
            break
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=DEFAULT_DIR, help="папка с двумя файлами выгрузки")
    args = parser.parse_args()

    base = Path(args.dir)
    spas_items = load_items(base / SPASATEL_FILE)
    m01_items = load_items(base / MAGAZIN01_FILE)
    print(f"Спасатель: {len(spas_items)} позиций, Магазин01: {len(m01_items)} позиций")

    spas_by_kind = classify(spas_items)
    m01_by_kind = classify(m01_items)

    comparisons = print_report(spas_by_kind, m01_by_kind)

    dumped_confident = dump_confident_pairs(comparisons, CONFIDENT_PAIRS_DUMP)
    print(f"\nВыгружено пар «уверенно» ({'/'.join(DUMP_KINDS)}) в {CONFIDENT_PAIRS_DUMP}: {dumped_confident}")

    dumped_check = dump_check_pairs(comparisons, CHECK_PAIRS_DUMP, CHECK_PAIRS_DUMP_LIMIT)
    print(f"Выгружено примеров «проверить» в {CHECK_PAIRS_DUMP}: {dumped_check}")


if __name__ == "__main__":
    main()
