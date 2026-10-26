"""CLI: пересчёт описания уже загруженных товаров каталога из исходного
JSON-файла поставщика (владелец, 26.10.2026, финальное решение дня — см.
docstring `app.services.products_import_apply.apply_products_import`:
«данные из JSON должны быть лучше того, что было вписано до этого»).

Назначение: товар уже в БД (создан прошлым импортом, import_note вида
«Импорт каталога из файла «X»», example.gala.json/load_gala_catalog.py или
rebuild самого прода) — пересобрать его описание из исходного файла X тем же
конвертером (app/services/catalog_gala/from_*.py) + ЕДИНСТВЕННОЙ сборкой
build_tech_description (app/services/product_tech_description.py, ПРАВИЛО
№6) и заменить описание в БД безусловно, если файл даёт хоть что-то; иначе —
не трогать (единственная защита, см. docstring apply_products_import).

Запуск (из backend/, с активным venv или внутри backend_a):
    python -m scripts.rebuild_descriptions_from_sources --dry-run
    python -m scripts.rebuild_descriptions_from_sources --dry-run \
        --db-source csv --csv-path <путь к выгрузке прода>.csv
    python -m scripts.rebuild_descriptions_from_sources --apply \
        --db-source local --user-email <email>

Своей логики сопоставления строки с товаром и сборки текста этот скрипт НЕ
пишет (ПРАВИЛО №6) — переиспользует:
  - конвертеры из scripts/catalog_to_gala.py (_CONVERTERS, _detect_source) —
    тот же автоматический выбор, что и у ручной конвертации файла;
  - build_tech_description (app/services/product_tech_description.py) —
    единственная сборка текста описания из base_text+характеристик;
  - products_import_match.norm_key/ProductMatchIndex — единственный
    механизм сопоставления строки файла с товаром каталога (конструктор
    принимает любой duck-typed объект с .id/.name/.description, не только
    ORM Product — этим пользуется --db-source csv, см. _load_csv_match_index);
  - product_description_history.set_product_description — единственный
    писатель истории описаний, source="import".

--db-source csv работает ПОЛНОСТЬЮ В ПАМЯТИ по уже готовой CSV-выгрузке
прода (её сделал владелец заранее через ssh+psql \\copy, read-only) — этот
скрипт НЕ подключается к проду и никогда не пишет в этом режиме (--apply с
--db-source csv запрещён явной проверкой, см. main()).
"""
import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from app.services.catalog_gala import (  # noqa: E402
    from_electro_mpo, from_vkusvill, from_gala_sheet, from_baucenter, from_store_nomenclature,
)
from app.services.product_description_merge import (  # noqa: E402
    is_new_description_shorter, merge_missing_lines,
)
from app.services.product_tech_description import build_tech_description  # noqa: E402
from app.services.products_import_match import ProductMatchIndex, norm_key  # noqa: E402

# Единый словарь конвертеров (ПРАВИЛО №6) — тот же, что у
# scripts/catalog_to_gala.py, вторую карту источников не завести.
_CONVERTERS = {
    "electro_mpo": from_electro_mpo.convert,
    "vkusvill": from_vkusvill.convert,
    "gala_sheet": from_gala_sheet.convert,
    "baucenter": from_baucenter.convert,
    "store_nomenclature": from_store_nomenclature.convert,
}

# Файлы по умолчанию (владелец, 26.10.2026) — ВСЕ выгрузки поставщиков,
# кроме catalog_goods_1010.json (не формат catalog_gala — уже плоский формат
# обычного импорта, без specifications/raw-структуры, см. отчёт --dry-run).
DEFAULT_FILES = [
    r"C:\Users\1\Downloads\Товары и ТЗ\fire_equipment_nomenclature.json",
    r"C:\Users\1\Downloads\Товары и ТЗ\k_spasatel_rescue_nomenclature.json",
    r"C:\Users\1\Downloads\Товары и ТЗ\promalp_height_safety_nomenclature.json",
    r"C:\Users\1\Downloads\Товары и ТЗ\rescue_medical_nomenclature.json",
    r"C:\Users\1\Downloads\Товары и ТЗ\sima_land_catalog_all.json",
    r"C:\Users\1\Downloads\baucenter_construction_all.json",
    r"C:\Users\1\Downloads\baucenter_electro_lighting.json",
    r"C:\Users\1\Downloads\baucenter_tools_hardware.json",
    r"C:\Users\1\Downloads\electro_mpo_breakers_all.json",
    r"C:\Users\1\Downloads\electro_mpo_cables_all.json",
    r"C:\Users\1\Downloads\electro_mpo_nomenclature_1000.json",
    r"C:\Users\1\Downloads\electro_mpo_nomenclature_massive.json",
    r"C:\Users\1\Downloads\vkusvill_grocery_nomenclature.json",
    r"C:\Users\1\Downloads\vkusvill_grocery_nomenclature_1000.json",
]

DEFAULT_CSV_PATH = (
    r"C:\Users\1\AppData\Local\Temp\claude\c--Users-1-Desktop-Cursor-VSKS-CRM"
    r"\b0e6cde9-201f-46ad-b357-6038ab045488\scratchpad\prod_products_export.csv"
)

LASTIK_PRODUCT_ID = 152085
LASTIK_NAME_HINT = "ластик фигурный"


# --- выбор конвертера (переиспользует scripts/catalog_to_gala.py) ---------

_BASENAME_PREFIX_MAP = (
    ("baucenter_", "baucenter"),
    ("electro_mpo_", "electro_mpo"),
    ("vkusvill_", "vkusvill"),
)


def _detect_source_like_catalog_to_gala(raw) -> Optional[str]:
    """Тот же автоопределение, что scripts/catalog_to_gala.py::_detect_source
    (price_rub+source_store у первого элемента → store_nomenclature) — не
    импортируем сам catalog_to_gala.py, т.к. это CLI-модуль с main()/argparse
    верхнего уровня, а не библиотека; логика однострочная, держим рядом."""
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        if "price_rub" in raw[0] and "source_store" in raw[0]:
            return "store_nomenclature"
    return None


def _pick_converter(path: str, raw: list) -> Optional[str]:
    """Возвращает ключ _CONVERTERS для файла. Порядок важен: сначала
    сигнатура store_nomenclature (price_rub+source_store) — она встречается
    и у файлов с именем "baucenter_*" (electro_lighting/tools_hardware
    используют store_nomenclature-формат, а не baucenter-формат, который
    требует id/price/url без price_rub/source_store, проверено на реальных
    файлах 26.10.2026); только если сигнатура не совпала — префикс basename.
    None — конвертер не распознан."""
    detected = _detect_source_like_catalog_to_gala(raw)
    if detected:
        return detected
    basename = os.path.basename(path).lower()
    for prefix, source in _BASENAME_PREFIX_MAP:
        if basename.startswith(prefix):
            return source
    return None


def _load_raw(path: str) -> list:
    """json.load() всего файла — проверено 26.10.2026 на реальном
    sima_land_catalog_all.json (150 МБ, 152 652 позиции): загружается целиком
    за ~2 секунды без MemoryError на обычной машине разработчика. Выделенный
    потоковый парсер (ijson) не потребовался — не добавляем зависимость,
    которая не нужна на практике (ПРАВИЛО №6 — не плодить вторую реализацию
    загрузки JSON без причины)."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- сопоставление с БД -----------------------------------------------------

def _load_csv_match_index(csv_path: str) -> ProductMatchIndex:
    """Один общий ProductMatchIndex на ВСЕ файлы (--db-source csv) — строится
    ОДИН раз, не пересоздаётся на каждый обрабатываемый файл (CSV ~200 МБ,
    ~149 тыс. строк). Потоковое чтение csv.DictReader — файл не грузится в
    память целиком, только построенный индекс (SimpleNamespace на строку).
    country_origin/manufacturer/article читаются из CSV (Задача 2б,
    26.10.2026, см. prod_products_export_v2.csv — v1 не содержал
    country_origin) — нужны как "старое значение" для статистики по Задаче
    2/3; старый CSV без этих колонок не ломается — .get(...) даёт пустую
    строку, как и раньше у name/description."""
    index = ProductMatchIndex()
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pid = int(row["id"])
            except (KeyError, ValueError, TypeError):
                continue
            index.add(SimpleNamespace(
                id=pid,
                name=row.get("name") or "",
                description=row.get("description") or "",
                country_origin=row.get("country_origin") or "",
                manufacturer=row.get("manufacturer") or "",
                article=row.get("article") or "",
            ))
    return index


async def _load_db_match_index(db, file_names) -> ProductMatchIndex:
    """--db-source local: кандидаты из реальной БД сужены по именам ЭТОГО
    файла — переиспользует load_candidate_products (products_import_match.py,
    ПРАВИЛО №6), не второй SQL-запрос."""
    from app.services.products_import_match import load_candidate_products
    candidates = await load_candidate_products(db, file_names)
    return ProductMatchIndex(candidates)


# --- отчёт по одному файлу --------------------------------------------------

@dataclass
class FileReport:
    path: str
    total_items: int = 0
    matched: int = 0
    unmatched: int = 0
    no_data_in_file: int = 0
    unchanged: int = 0
    changed: int = 0
    was_empty_now_filled: int = 0
    # Задача 1 (26.10.2026, ПРАВИЛО №6): раньше "короче старого" была чисто
    # информационной меткой, а запись всё равно безусловно заменяла описание
    # файловым. Теперь это критерий объединения — merged_count считает
    # реально объединённые описания (replaced_count — обычная замена).
    # shorter_count остаётся как ПРОВЕРОЧНАЯ метрика: после объединения
    # результат по построению не короче старого, поэтому "короче старого" в
    # финале должно быть 0 (см. _write_samples_md/_print_report).
    merged_count: int = 0
    replaced_count: int = 0
    shorter_count: int = 0
    shorter_after_merge_count: int = 0  # проверка: должно остаться 0
    # Задача 2/3 (26.10.2026): country_origin/manufacturer/article — файл
    # заменяет значение в БД безусловно, если он его даёт; иначе поле не
    # трогаем. Счётчики ниже считают, у скольких товаров значение В БД
    # РЕАЛЬНО изменится (отличается от текущего после _norm_simple), не
    # просто "в файле что-то есть".
    country_will_change: int = 0  # country_origin заменится новым значением
    country_to_non_rf: int = 0  # из них — новое значение НЕ "РФ"/"Россия"
    manufacturer_will_change: int = 0
    article_will_change: int = 0
    shorter_samples: list = field(default_factory=list)  # [{"name","old","new"}]
    merged_samples: list = field(default_factory=list)  # [{"name","old","new","merged"}], до 10 на файл (Задача 1/3)
    change_samples: list = field(default_factory=list)  # [{"name","old","new"}], первые 3 изменённых файла (Задача 3)
    lastik_sample: Optional[dict] = None
    lastik_is_exact: bool = False
    error: Optional[str] = None


def _norm_simple(s) -> str:
    """Нормализация для сравнения country_origin/manufacturer/article —
    регистр и края пробелов не должны считаться "изменением" (Задача 2/3,
    26.10.2026). Не тот же norm_key() из products_import_match (та чистит
    name/description, \\r\\n и ё/е — для коротких атрибутов это избыточно),
    но намеренно простая и единственная для ЭТИХ трёх полей в этом скрипте."""
    return (s or "").strip().lower()


_RF_COUNTRY_VALUES = {"рф", "россия", "российская федерация"}


# Алиас — переносит имя прежней локальной функции на общую реализацию
# (ПРАВИЛО №6, задача 1, 2026-10-26): логика "короче" теперь живёт ТОЛЬКО в
# app.services.product_description_merge, второй такой функции здесь нет.
_is_shorter = is_new_description_shorter


def _looks_like_lastik(product_id: Optional[int], name: str) -> bool:
    if product_id == LASTIK_PRODUCT_ID:
        return True
    return LASTIK_NAME_HINT in (name or "").lower()


async def _process_file(
    path: str,
    match_index: ProductMatchIndex,
    *,
    apply: bool,
    db=None,
    current_user=None,
) -> FileReport:
    """Обрабатывает один исходный файл: конвертирует, сопоставляет каждую
    позицию с товаром БД через match_index, пересобирает описание и либо
    считает изменение (dry-run), либо применяет его (--apply, через
    set_product_description — ЕДИНСТВЕННЫЙ писатель истории описаний)."""
    report = FileReport(path=path)
    try:
        raw = _load_raw(path)
    except Exception as e:
        report.error = f"не удалось прочитать файл: {e}"
        return report

    source = _pick_converter(path, raw)
    if source is None:
        report.error = "конвертер не распознан (ни по сигнатуре, ни по имени файла)"
        return report

    converter = _CONVERTERS[source]
    converted = converter(raw, os.path.basename(path))
    items = converted.get("items", [])
    report.total_items = len(items)

    for item in items:
        name = item.get("name")
        if not name:
            continue
        new_desc = build_tech_description(item.get("characteristics"), item.get("description"))

        match = match_index.find(name, item.get("description"))
        product = match["product"]
        if product is None:
            report.unmatched += 1
            continue
        report.matched += 1

        # --- country_origin/manufacturer/article (Задача 2, 26.10.2026) ---
        # Правило владельца: файл даёт значение → заменяет БД безусловно
        # (даже если там уже что-то было); файл не даёт значение → поле не
        # трогаем (независимо от того, что сейчас в БД, включая дефолт "РФ").
        # country_origin/manufacturer/article уже есть в item — convert()
        # разбирает specifications один раз (ПРАВИЛО №6), второй разбор
        # specifications здесь не пишем.
        item_country = (item.get("country_origin") or "").strip() or None
        item_manufacturer = (item.get("manufacturer") or "").strip() or None
        item_article = (item.get("article") or "").strip() or None

        old_country = getattr(product, "country_origin", None) or ""
        old_manufacturer = getattr(product, "manufacturer", None) or ""
        old_article = getattr(product, "article", None) or ""

        country_changes = item_country is not None and _norm_simple(item_country) != _norm_simple(old_country)
        manufacturer_changes = item_manufacturer is not None and _norm_simple(item_manufacturer) != _norm_simple(old_manufacturer)
        article_changes = item_article is not None and _norm_simple(item_article) != _norm_simple(old_article)

        if country_changes:
            report.country_will_change += 1
            if _norm_simple(item_country) not in _RF_COUNTRY_VALUES:
                report.country_to_non_rf += 1
        if manufacturer_changes:
            report.manufacturer_will_change += 1
        if article_changes:
            report.article_will_change += 1

        if apply:
            # "Безусловно" — пишем, если файл дал значение, не только когда
            # оно отличается от старого (отличие и так гарантирует запись
            # нового значения; при равенстве после нормализации — не заводим
            # отдельную ветку, просто переприсваиваем то же самое). Обычные
            # атрибуты ORM — у этих полей нет истории (в отличие от
            # description/set_product_description).
            if item_country is not None:
                product.country_origin = item_country
            if item_manufacturer is not None:
                product.manufacturer = item_manufacturer
            if item_article is not None:
                product.article = item_article

        if not new_desc:
            report.no_data_in_file += 1
            continue

        old_desc = getattr(product, "description", None) or ""
        if norm_key(old_desc) == norm_key(new_desc):
            report.unchanged += 1
            continue

        report.changed += 1
        if not old_desc.strip():
            report.was_empty_now_filled += 1

        # Задача 1 (26.10.2026, ПРАВИЛО №6): новое заметно короче старого →
        # не заменяем, а объединяем (старое целиком + недостающие строки
        # нового в конец) через app.services.product_description_merge —
        # тот же критерий и та же сборка, что в products_import_apply.py.
        if _is_shorter(old_desc, new_desc):
            report.shorter_count += 1
            final_desc = merge_missing_lines(old_desc, new_desc)
            report.merged_count += 1
            if len(report.shorter_samples) < 10:
                report.shorter_samples.append({"name": name, "old": old_desc, "new": new_desc})
            if len(report.merged_samples) < 10:
                report.merged_samples.append({"name": name, "old": old_desc, "new": new_desc, "merged": final_desc})
            # Проверка (должна остаться 0 во всех прогонах): результат
            # объединения по построению не короче старого.
            if is_new_description_shorter(old_desc, final_desc):
                report.shorter_after_merge_count += 1
        else:
            final_desc = new_desc
            report.replaced_count += 1

        if len(report.change_samples) < 3:
            report.change_samples.append({"name": name, "old": old_desc, "new": final_desc})

        product_id = getattr(product, "id", None)
        if _looks_like_lastik(product_id, name) and not report.lastik_is_exact:
            # Точное совпадение id=152085 (владелец, задание) ВСЕГДА выигрывает
            # у совпадений просто по подстроке названия ("ластик фигурный" —
            # таких товаров в каталоге несколько) и больше не перезаписывается.
            report.lastik_sample = {"name": name, "old": old_desc, "new": final_desc, "id": product_id}
            if product_id == LASTIK_PRODUCT_ID:
                report.lastik_is_exact = True

        if apply:
            from app.services.product_description_history import set_product_description
            await set_product_description(db, product, "description", final_desc, current_user, source="import")

    return report


def _pick_lastik_sample(reports: list) -> Optional[dict]:
    """Среди всех обработанных файлов — сэмпл с точным id=152085, если он
    где-то найден; иначе первый найденный по подстроке названия (fallback)."""
    exact = next((r.lastik_sample for r in reports if r.lastik_is_exact), None)
    if exact:
        return exact
    return next((r.lastik_sample for r in reports if r.lastik_sample), None)


# --- вывод -------------------------------------------------------------------

def _print_report(reports: list) -> None:
    print("\n=== ОТЧЁТ ПО ФАЙЛАМ ===")
    total = FileReport(path="ИТОГО")
    for r in reports:
        if r.error:
            print(f"\n--- {r.path} ---\n  ОШИБКА: {r.error}")
            continue
        print(
            f"\n--- {r.path} ---\n"
            f"  позиций в файле: {r.total_items}\n"
            f"  сопоставлено с товаром БД: {r.matched} (не сопоставлено: {r.unmatched})\n"
            f"  в файле нет данных для описания: {r.no_data_in_file}\n"
            f"  без изменений: {r.unchanged}\n"
            f"  описание ИЗМЕНИТСЯ/изменено: {r.changed}\n"
            f"    из них было пусто -> станет заполнено: {r.was_empty_now_filled}\n"
            f"    заменено целиком: {r.replaced_count}, объединено (новое было короче): {r.merged_count}\n"
            f"    ПРОВЕРКА — короче старого ПОСЛЕ объединения (должно быть 0): {r.shorter_after_merge_count}\n"
            # Задача 3 (26.10.2026): country_origin — сколько товаров получат
            # НЕ-РФ страну (значение из файла непустое, отличается от
            # текущего в БД после нормализации регистра/пробелов, и это не
            # "РФ"/"Россия"/"Российская Федерация"); отдельно — сколько всего
            # значений country_origin реально изменится (включая смену на
            # другое РФ-подобное значение).
            f"  country_origin: станет НЕ-РФ: {r.country_to_non_rf} "
            f"(всего изменится значение country_origin: {r.country_will_change})\n"
            # manufacturer и article считаются РАЗДЕЛЬНО (не одной суммой) —
            # каждое число: сколько товаров получат другое значение этого
            # поля (файл дал непустое значение, отличается от текущего в БД
            # после нормализации).
            f"  manufacturer изменится: {r.manufacturer_will_change}, "
            f"article изменится: {r.article_will_change}"
        )
        total.total_items += r.total_items
        total.matched += r.matched
        total.unmatched += r.unmatched
        total.no_data_in_file += r.no_data_in_file
        total.unchanged += r.unchanged
        total.changed += r.changed
        total.was_empty_now_filled += r.was_empty_now_filled
        total.shorter_count += r.shorter_count
        total.merged_count += r.merged_count
        total.replaced_count += r.replaced_count
        total.shorter_after_merge_count += r.shorter_after_merge_count
        total.country_will_change += r.country_will_change
        total.country_to_non_rf += r.country_to_non_rf
        total.manufacturer_will_change += r.manufacturer_will_change
        total.article_will_change += r.article_will_change

    print(
        f"\n=== ИТОГО (все файлы) ===\n"
        f"  позиций: {total.total_items}, сопоставлено: {total.matched}, "
        f"не сопоставлено: {total.unmatched}\n"
        f"  без данных в файле: {total.no_data_in_file}, без изменений: {total.unchanged}\n"
        f"  изменится/изменено: {total.changed} "
        f"(было пусто->заполнено: {total.was_empty_now_filled}, "
        f"заменено: {total.replaced_count}, объединено: {total.merged_count})\n"
        f"  ПРОВЕРКА — короче старого ПОСЛЕ объединения (должно быть 0): {total.shorter_after_merge_count}\n"
        f"  country_origin станет НЕ-РФ: {total.country_to_non_rf} "
        f"(всего изменится country_origin: {total.country_will_change})\n"
        f"  manufacturer изменится: {total.manufacturer_will_change}, "
        f"article изменится: {total.article_will_change}"
    )

    sima = next((r for r in reports if "sima_land" in r.path.lower()), None)
    if sima and not sima.error:
        print(
            f"\n=== Отдельно Сима-ленд ({sima.path}) ===\n"
            f"  позиций: {sima.total_items}, сопоставлено: {sima.matched}\n"
            f"  изменится/изменено: {sima.changed} "
            f"(было пусто->заполнено: {sima.was_empty_now_filled}, "
            f"заменено: {sima.replaced_count}, объединено: {sima.merged_count})"
        )

    lastik = _pick_lastik_sample(reports)
    if lastik:
        print(
            f"\n=== Ластик (id={lastik['id']}, «{lastik['name']}») ===\n"
            f"  БЫЛО: {lastik['old']!r}\n"
            f"  СТАНЕТ: {lastik['new']!r}"
        )
    else:
        print("\n=== Ластик 152085 — не найден среди обработанных файлов/сопоставлений ===")


def _write_samples_md(reports: list, out_path: str) -> None:
    """Задача 3 (26.10.2026, владелец): по каждому файлу — РОВНО 3 примера
    «было/станет» (первые 3 товара, у которых описание реально изменится —
    «станет» здесь уже финальный результат, то есть после объединения, если
    оно случилось; меньше изменений в файле — все, что есть); отдельный
    раздел «Объединено» (задача 1) — до 10 примеров по ВСЕМ файлам вместе,
    видно старое целиком + файловое + что дописалось; отдельный раздел
    «Ластик 152085»."""
    lines = ["# Примеры «было/станет» (rebuild_descriptions_from_sources.py)\n"]
    for r in reports:
        if r.error:
            continue
        lines.append(f"\n## {r.path}\n")
        if not r.change_samples:
            lines.append("Изменений описания в этом файле нет.\n")
        else:
            for s in r.change_samples:
                lines.append(f"\n### {s['name']}\n\n**Было:**\n\n```\n{s['old']}\n```\n\n**Станет:**\n\n```\n{s['new']}\n```\n")

    lines.append(
        "\n## Объединено (новое из файла было заметно короче старого — "
        "задача 1, 26.10.2026)\n"
    )
    merged_samples = []
    for r in reports:
        if r.error:
            continue
        merged_samples.extend(r.merged_samples)
    merged_samples = merged_samples[:10]
    if not merged_samples:
        lines.append("\nТаких нет (новых описаний заметно короче старых не найдено).\n")
    else:
        for s in merged_samples:
            lines.append(
                f"\n### {s['name']}\n\n"
                f"**Было (в БД):**\n\n```\n{s['old']}\n```\n\n"
                f"**Новое из файла (короче, не записывается само по себе):**\n\n```\n{s['new']}\n```\n\n"
                f"**Станет (объединено, записывается):**\n\n```\n{s['merged']}\n```\n"
            )

    lines.append("\n## Ластик 152085\n")
    lastik = _pick_lastik_sample(reports)
    if lastik:
        lines.append(
            f"\n**id:** {lastik['id']}, **название:** {lastik['name']}\n\n"
            f"**Было:**\n\n```\n{lastik['old']}\n```\n\n**Станет:**\n\n```\n{lastik['new']}\n```\n"
        )
    else:
        lines.append("\nНе найден среди обработанных файлов/сопоставлений.\n")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


# --- main --------------------------------------------------------------------

async def _run_csv(files: list, csv_path: str) -> list:
    print(f"Строю индекс сопоставления из CSV: {csv_path} ...", file=sys.stderr)
    match_index = _load_csv_match_index(csv_path)
    print("Индекс построен.", file=sys.stderr)
    reports = []
    for path in files:
        reports.append(await _process_file(path, match_index, apply=False))
    return reports


async def _run_local(files: list, user_email: Optional[str], apply: bool) -> list:
    from app.database import async_session
    from app.models.user import User
    from sqlalchemy import select

    current_user = None
    async with async_session() as db:
        if apply:
            if not user_email:
                print("--apply требует --user-email", file=sys.stderr)
                sys.exit(2)
            current_user = (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none()
            if current_user is None:
                print(f"Пользователь с email {user_email!r} не найден.", file=sys.stderr)
                sys.exit(1)

        reports = []
        for path in files:
            try:
                raw = _load_raw(path)
            except Exception as e:
                reports.append(FileReport(path=path, error=f"не удалось прочитать файл: {e}"))
                continue
            source = _pick_converter(path, raw)
            if source is None:
                reports.append(FileReport(path=path, error="конвертер не распознан"))
                continue
            converted = _CONVERTERS[source](raw, os.path.basename(path))
            file_names = {item.get("name") for item in converted.get("items", [])}
            file_names.discard(None)
            match_index = await _load_db_match_index(db, file_names)
            report = await _process_file(path, match_index, apply=apply, db=db, current_user=current_user)
            reports.append(report)
            if apply:
                await db.commit()
        return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", default=None, help="пути к исходным JSON поставщиков (по умолчанию — весь список DEFAULT_FILES)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="только посчитать, что изменится (по умолчанию)")
    mode.add_argument("--apply", action="store_true", help="реально заменить описания в БД")
    parser.add_argument("--db-source", choices=["local", "csv"], default="local")
    parser.add_argument("--csv-path", default=DEFAULT_CSV_PATH)
    parser.add_argument("--user-email", default=None, help="email пользователя для --apply (source='import')")
    parser.add_argument("--samples-out", default=None, help="путь к markdown-файлу с примерами «было/станет»")
    args = parser.parse_args()

    apply = bool(args.apply) and not args.dry_run
    if args.apply and args.db_source == "csv":
        print("--apply запрещён с --db-source csv: прод только читаем, этот режим не подключается к БД и не пишет.", file=sys.stderr)
        sys.exit(2)

    files = args.files or DEFAULT_FILES

    import asyncio
    if args.db_source == "csv":
        reports = asyncio.run(_run_csv(files, args.csv_path))
    else:
        reports = asyncio.run(_run_local(files, args.user_email, apply))

    _print_report(reports)
    if args.samples_out:
        _write_samples_md(reports, args.samples_out)
        print(f"\nПримеры сохранены в {args.samples_out}")


if __name__ == "__main__":
    main()
