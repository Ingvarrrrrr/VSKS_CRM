"""Автотесты решения владельца (2026-09-15, опрос): одна КАТЕГОРИЯ
(строка-заголовок без «Плановой позиции») объявлена в файле НЕСКОЛЬКИМИ
строками с РАЗНЫМИ «Суммами по ФЭО» — пример владельца дословно:

    «Пожарное оборудование»: строка 10 = 1 400 000, строка 50 = 1 500 000 —
    импорт не должен молча брать последнюю. Нужно спрашивать человека по
    каждой такой категории отдельно, как уже сделано для одинаковых позиций
    (feo_import_duplicates.py) — варианты «взять первую», «взять последнюю»,
    «сложить».

Механизм — `app/services/feo_import_budget_conflicts.py`, подключён в
`feo_import_apply.py` (`register_budget_write` заменяет прямые
`budget_writes.setdefault(...).append(...)`, `apply_budget_conflict_
resolutions` вызывается после основного цикла по строкам вместо прежнего
безусловного warning) и `feo_import_core.py` (`budget_conflict_groups` в
ответе, парсинг `duplicate_resolutions` для ключей `budget::*`).

Тот же канал решений `duplicate_resolutions`, что и у дублей имени Ур.5
(Правило №6, один канал на весь импорт) — ключи различаются префиксом
`budget::` (feo_import_budget_conflicts.KEY_PREFIX).

Использует макет строки/фикстуры из test_feo_import_tree.py и тот же приём
локальной `_import` с `dry_run`/`duplicate_resolutions`, что и
test_feo_import_duplicate_names.py (Правило №6 — не дублировать
`mk_row`/`_make_subsidy`/`_cleanup_subsidy` второй раз).

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному:
`python -m pytest tests/test_feo_import_budget_conflicts.py::<имя> -x -q`.
"""
import json
from decimal import Decimal

import pytest

from app.routers.feo_categories import _do_feo_import
from tests.test_feo_import_tree import (
    _IDX,
    _cleanup_subsidy,
    _get_categories,
    _make_subsidy,
    mk_row,
)


async def _import(db_session, subsidy_id, rows, dry_run=False, duplicate_resolutions=None):
    """Как `_import` в test_feo_import_tree.py, но с `dry_run`/
    `duplicate_resolutions` — нужны для сценария «предпросмотр → выбор
    человека → боевой импорт» (тот же приём, что и в
    test_feo_import_duplicate_names.py)."""
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


# --- а. Две строки-заголовка с РАЗНЫМИ суммами -> одна группа, 3 варианта ---

@pytest.mark.asyncio
async def test_two_different_sums_create_one_conflict_group(db_session):
    """Пример владельца: «Пожарное оборудование» задана дважды — строка 2
    (1 400 000) и строка 3 (1 500 000). Без явного решения человека —
    поведение не меняется, побеждает последняя строка (backward-compat)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Пожарное оборудование", feo_sum="1400000"),
            mk_row(lvl2="Пожарное оборудование", feo_sum="1500000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        groups = result["budget_conflict_groups"]
        assert len(groups) == 1
        g = groups[0]
        assert g["name"] == "Пожарное оборудование"
        assert [r["row"] for r in g["rows"]] == [2, 3]
        assert [r["amount"] for r in g["rows"]] == [1400000.0, 1500000.0]
        assert g["options"]["first"] == {"row": 2, "amount": 1400000.0}
        assert g["options"]["last"] == {"row": 3, "amount": 1500000.0}
        assert g["options"]["sum"] == {"amount": 2900000.0}
        assert g["resolution"] == "last", "без выбора человека — прежнее поведение"

        overwritten = [w for w in result["warnings"] if w["kind"] == "budget_overwritten_by_row"]
        assert len(overwritten) == 1
        assert "учтена последняя (строка 3)" in overwritten[0]["message"]

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Пожарное оборудование")
        assert leaf.budget == Decimal("1500000"), "по умолчанию — последняя строка, поведение не меняем"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- б. resolution=first -----------------------------------------------------

@pytest.mark.asyncio
async def test_resolution_first_takes_first_row(db_session):
    """Явный выбор «взять первую» — бюджет категории равен сумме ПЕРВОЙ по
    порядку строки файла, не последней."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Пожарное оборудование", feo_sum="1400000"),
            mk_row(lvl2="Пожарное оборудование", feo_sum="1500000"),
        ]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert preview["errors"] == []
        key = preview["budget_conflict_groups"][0]["key"]
        assert key.startswith("budget::"), "ключ группы бюджетного конфликта обязан быть в своём пространстве имён"

        result = await _import(db_session, subsidy_id, rows, duplicate_resolutions={key: "first"})
        assert result["errors"] == []
        assert result["budget_conflict_groups"][0]["resolution"] == "first"

        overwritten = [w for w in result["warnings"] if w["kind"] == "budget_overwritten_by_row"]
        assert len(overwritten) == 1
        assert "по вашему выбору взята первая (строка 2" in overwritten[0]["message"]

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Пожарное оборудование")
        assert leaf.budget == Decimal("1400000")
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


# --- в. resolution=sum -------------------------------------------------------

@pytest.mark.asyncio
async def test_resolution_sum_adds_values(db_session):
    """Явный выбор «сложить» — бюджет категории равен сумме ВСЕХ
    строк-кандидатов, деньги не пропадают и не задваиваются."""
    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Пожарное оборудование", feo_sum="1400000"),
            mk_row(lvl2="Пожарное оборудование", feo_sum="1500000"),
        ]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        key = preview["budget_conflict_groups"][0]["key"]

        result = await _import(db_session, subsidy_id, rows, duplicate_resolutions={key: "sum"})
        assert result["errors"] == []
        assert result["budget_conflict_groups"][0]["resolution"] == "sum"

        overwritten = [w for w in result["warnings"] if w["kind"] == "budget_overwritten_by_row"]
        assert "по вашему выбору сложены: 2 900 000.00" in overwritten[0]["message"]

        cats = await _get_categories(db_session, subsidy_id)
        leaf = next(c for c in cats if c.name == "Пожарное оборудование")
        assert leaf.budget == Decimal("2900000")
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)


# --- г. Одинаковые суммы -> группы нет, конфликта нет -----------------------

@pytest.mark.asyncio
async def test_identical_sums_are_not_a_conflict(db_session):
    """Несколько строк задают ОДНО И ТО ЖЕ число (обычное дело для
    «строк-подытогов» без Уровня 3) — это НЕ конфликт: без группы, без
    предупреждения, а не «требует выбора» на пустом месте."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [
            mk_row(lvl2="Экипировка", feo_sum="500000"),
            mk_row(lvl2="Экипировка", feo_sum="500000"),
        ]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert result["budget_conflict_groups"] == []
        assert not any(w["kind"] == "budget_overwritten_by_row" for w in result["warnings"])

        cats = await _get_categories(db_session, subsidy.id)
        leaf = next(c for c in cats if c.name == "Экипировка")
        assert leaf.budget == Decimal("500000")
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- д. Неверное значение resolution -> 400 ----------------------------------

@pytest.mark.asyncio
async def test_invalid_budget_resolution_value_is_400(db_session):
    """`duplicate_resolutions` для ключа `budget::*` принимает только
    'first'/'last'/'sum' — чужое значение (например, 'merge', допустимое
    только для групп дублей Ур.5) обязано быть отклонено 400, как и для
    любого другого неверного значения в этом канале."""
    from fastapi import HTTPException

    subsidy = await _make_subsidy(db_session)
    subsidy_id = subsidy.id
    try:
        rows = [
            mk_row(lvl2="Пожарное оборудование", feo_sum="1400000"),
            mk_row(lvl2="Пожарное оборудование", feo_sum="1500000"),
        ]
        preview = await _import(db_session, subsidy_id, rows, dry_run=True)
        key = preview["budget_conflict_groups"][0]["key"]

        with pytest.raises(HTTPException) as exc_info:
            await _import(db_session, subsidy_id, rows, duplicate_resolutions={key: "merge"})
        assert exc_info.value.status_code == 400
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
