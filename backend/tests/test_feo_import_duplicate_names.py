"""Автотесты волны 4, п.23 (слова владельца дословно): «При импорте плана из
экселя, если в разных строках одинаковые названия, то надо предложить
объединить, а не делать это самовольно и не брать только последнее значение
[...] Должно быть предложение оставить как есть — это N строк «чайник»,
каждая со своей ценой, или объединить со средней ценой [...] Совпадение
должно быть полным.»

Механизм — `app/services/feo_import_duplicates.py`, подключён в
`feo_import_apply.py` (сбор `state.pending_lvl5_items` во время основного
цикла по строкам) и `feo_import_core.py` (`finalize_lvl5_items`, вызывается
после `apply_rows`, парсинг параметра `duplicate_resolutions`).

Старый механизм — warning `duplicate_row_in_file` («учтена последняя
строка») — убран целиком (Правило №6, один механизм на «полное совпадение
имени в файле»): регрессия на его отсутствие — в
test_feo_import_target_subsidy.py::test_duplicate_rows_in_file_kept_separate_by_default
и test_feo_import_warnings_rows.py::test_duplicate_group_reported_with_row_numbers.

Использует макет строки/фикстуры из test_feo_import_tree.py (Правило №6 —
не дублировать `mk_row`/`_make_subsidy`/`_cleanup_subsidy` второй раз), и тот
же приём, что у `_import17` в test_feo_import_promote_level.py: локальная
копия `_import`, здесь — с доп. параметрами `dry_run`/`duplicate_resolutions`
(`_do_feo_import` поддерживает оба, `_import` из test_feo_import_tree.py —
нет ни одного из них).

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному:
`python -m pytest tests/test_feo_import_duplicate_names.py::<имя> -x -q`.
"""
import json
from decimal import Decimal

import pytest

from app.routers.feo_categories import _do_feo_import
from tests.test_feo_import_tree import (
    _IDX,
    _cleanup_subsidy,
    _get_categories,
    _get_items,
    _make_subsidy,
    mk_row,
)


async def _import(db_session, subsidy_id, rows, dry_run=False, duplicate_resolutions=None):
    """Как `_import` в test_feo_import_tree.py, но с `dry_run`/
    `duplicate_resolutions` — нужны здесь для сценария «предпросмотр → выбор
    человека → боевой импорт», которого нет у остальных тестов ФЭО-импорта."""
    return await _do_feo_import(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=_IDX["lvl4"], c_lvl5=_IDX["item_name"],
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=_IDX["code"], c_appendix=_IDX["appendix"], c_budget=_IDX["budget"], c_active=_IDX["active"],
        c_amt_lvl2=_IDX["amt_lvl2"],
        c_row_feo_qty=_IDX["feo_qty"], c_row_feo_unit=_IDX["feo_unit"],
        c_row_feo_price=_IDX["feo_price"], c_row_feo_sum=_IDX["feo_sum"],
        c_row_plan_qty=_IDX["plan_qty"], c_row_plan_unit=_IDX["plan_unit"],
        c_row_plan_price=_IDX["plan_price"], c_row_plan_sum=_IDX["plan_sum"],
        c_item_type=_IDX["item_type"],
        default_subsidy_id=subsidy_id,
        dry_run=dry_run,
        duplicate_resolutions=json.dumps(duplicate_resolutions) if duplicate_resolutions else "",
        db=db_session,
    )


# --- 1. По умолчанию («оставить как есть») — три отдельные позиции ---------

@pytest.mark.asyncio
async def test_default_resolution_keeps_rows_separate(db_session):
    """Владелец: пять «чайников» могли быть заведены НАМЕРЕННО (пять разных
    закупок) — без явного выбора человека объединение НЕ должно происходить,
    даже если групп много. Три строки «Чайник» с ценами 4000/5000/6000 →
    ТРИ плановые позиции, сумма равна сумме трёх строк."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="4000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="5000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="6000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        groups = result["duplicate_groups"]
        assert len(groups) == 1
        g = groups[0]
        assert g["name"] == "Чайник"
        assert g["count"] == 3
        assert g["resolution"] == "keep", "по умолчанию — без автоматического объединения"
        assert [r["row"] for r in g["rows"]] == [2, 3, 4]
        assert sorted(r["amount"] for r in g["rows"]) == [4000.0, 5000.0, 6000.0]

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Кухня")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 3, "каждая строка — своя позиция, как и написал владелец"
        assert sorted(it.amount for it in items) == [Decimal("4000"), Decimal("5000"), Decimal("6000")]
        assert sum(it.amount for it in items) == Decimal("15000"), "сумма трёх строк не должна пострадать"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 2. Явный выбор «объединить» — одна позиция со средней ценой -----------

@pytest.mark.asyncio
async def test_merge_resolution_combines_sum_and_quantity(db_session):
    """Владелец: «объединить со средней ценой, тогда получилась бы одна
    строчка «Чайник» с ценой средней 5000, которая получилась из
    (4000+5000+6000)/3» — суммы и количества СКЛАДЫВАЮТСЯ (владелец,
    уточнение №2: деньги не должны измениться ни на рубль), цена выводится
    делением. Три строки без явного количества (qty неявно = 1 каждая) →
    объединённое количество = 3, сумма = 15000, цена = 5000."""
    subsidy = await _make_subsidy(db_session)
    # `subsidy.id` захвачен здесь ЯВНО, обычным int'ом — dry_run ниже делает
    # `db.rollback()`, который истекает (expire) все ORM-объекты сессии, а
    # повторное обращение к `subsidy.id` после rollback в async-сессии требует
    # await (иначе SQLAlchemy падает MissingGreenlet) — используем сохранённое
    # значение везде дальше вместо повторного чтения атрибута объекта.
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="4000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="5000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="6000"),
        ]

        # Предпросмотр (dry-run, как и в мастере) — узнаём ключ группы, чтобы
        # передать решение человека в боевой вызов; ничего не пишется в БД.
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        group_key = preview["duplicate_groups"][0]["key"]
        assert preview["duplicate_groups"][0]["merged_preview"] == {
            "qty": 3.0, "unit": None, "price": 5000.0, "amount": 15000.0,
        }
        cats_after_dry_run = await _get_categories(db_session, subsidy_id)
        assert cats_after_dry_run == [], "dry_run обязан откатывать транзакцию"

        result = await _import(db_session, subsidy_id, rows, duplicate_resolutions={group_key: "merge"})
        assert result["errors"] == []
        assert result["duplicate_groups"][0]["resolution"] == "merge"

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Кухня")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1, "объединение — ОДНА позиция"
        item = items[0]
        assert item.name == "Чайник"
        assert item.amount == Decimal("15000"), "сумма не должна измениться ни на рубль"
        assert item.quantity == Decimal("3"), "количество — сумма количеств (по умолчанию 1 на строку)"

        merge_warn = [w for w in result["warnings"] if w["kind"] == "duplicate_group_merged"]
        assert len(merge_warn) == 1
        assert "15 000" in merge_warn[0]["message"], merge_warn[0]["message"]
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


# --- 3. Регистр/пробелы — считаются одним и тем же именем -------------------

@pytest.mark.asyncio
async def test_case_and_whitespace_variants_are_one_group(db_session):
    """«Чайник» / «чайник» / «  ЧАЙНИК  » — разные строки байт-в-байт, но
    ОДНО и то же имя после нормализации (та же normalize_feo_name, что и
    везде в проекте) — обязаны попасть в ОДНУ группу дублей, не в три
    независимые позиции без предупреждения."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="1000"),
            mk_row(lvl2="Кухня", item_name="чайник", plan_sum="2000"),
            mk_row(lvl2="Кухня", item_name="  ЧАЙНИК  ", plan_sum="3000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        groups = result["duplicate_groups"]
        assert len(groups) == 1, "регистр/пробелы не создают отдельных групп"
        assert groups[0]["count"] == 3
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 4. Разные по существу названия — НЕ группируются (fuzzy запрещён) -----

@pytest.mark.asyncio
async def test_materially_different_names_are_not_grouped(db_session):
    """Владелец: «совпадение должно быть полным» — «Чайник» и «Чайник
    электрический» (или любое другое различающееся по существу имя) НЕ
    считаются одной группой, даже если очень похожи (в этом проекте fuzzy
    matching уже один раз слепил разные товары — см. Lessons.md)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="1000"),
            mk_row(lvl2="Кухня", item_name="Чайник электрический", plan_sum="2000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert result["duplicate_groups"] == [], "разные по существу имена не группируются"

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Кухня")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 2
        assert {it.name for it in items} == {"Чайник", "Чайник электрический"}
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 5. Идемпотентность «оставить как есть» при повторном импорте ----------

@pytest.mark.asyncio
async def test_keep_separate_reimport_is_idempotent(db_session):
    """Повторный импорт ТОГО ЖЕ файла с тем же (умалчиваемым) решением
    «оставить как есть» не должен плодить новые позиции — порядковое
    сопоставление по номеру строки/id (см. _upsert_keep_separate) обязано
    найти уже существующие три позиции и не создать новых."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="4000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="5000"),
            mk_row(lvl2="Кухня", item_name="Чайник", plan_sum="6000"),
        ]
        result1 = await _import(db_session, subsidy.id, rows)
        assert result1["errors"] == []

        result2 = await _import(db_session, subsidy.id, rows)
        assert result2["errors"] == []
        assert result2["created"] == 0, "повторный импорт не должен создавать новые позиции"

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Кухня")
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 3, "дублей позиций быть не должно"
        assert sorted(it.amount for it in items) == [Decimal("4000"), Decimal("5000"), Decimal("6000")]
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
