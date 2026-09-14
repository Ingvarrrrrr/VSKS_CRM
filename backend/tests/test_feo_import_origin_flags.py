"""Автотесты на происхождение плановой позиции (`FeoPlannedItem.is_feo_breakdown`/
`is_internal_plan`) — задача владельца 2026-09-1x: «по ФЭО» должно стоять
только у строк, у которых реально есть деньги в разделе ФЭО файла; если
деньги только в плановом разделе — это «Внутренний план» (обе галочки могут
быть True одновременно, обе False — никогда).

Единственный источник решения — `resolve_origin_flags` в
`app/services/feo_import_common.py` (Правило №6); эти тесты проверяют её
эффект end-to-end через `_do_feo_import`, а не саму функцию изолированно —
баг был именно в том, что три места установки признака игнорировали её.

Переиспользует фикстуры `test_feo_import_tree.py` (`mk_row`, `_make_subsidy`,
`_cleanup_subsidy`, `_get_categories`, `_get_items`, набор полей
`ROW_FIELDS`/`_IDX`) и хелпер запуска импорта `_import17` из
`test_feo_import_promote_level.py`.

`_import17` (не `_import`) выбран намеренно: `_import` объявляет колонку
«Уровень 4» присутствующей, но пустой в наших строках — тогда срабатывает
продвижение «Плановой позиции» в свободный Уровень 4 (см. feo_import_apply.py,
блок «Продвижение „Плановой позиции“ в уровень», это отдельная от
происхождения логика, есть в файле ДО этой задачи) вместо создания
FeoPlannedItem — ровно то, что тесты этого файла не проверяют и чем мешают
себе. `_import17` не объявляет колонку «Уровень 4» вовсе — воспроизводит
17-колоночный шаблон, где строка «Ур.2 + Ур.3 + Плановая позиция» остаётся
настоящей позицией листа.

ВАЖНО (известная особенность проекта): async-тесты в этом файле падают с
«different loop», если запускать 2+ штук в одном вызове pytest. Гонять по
одному: `python -m pytest tests/test_feo_import_origin_flags.py::<имя> -x -q`.
"""
import pytest

from tests.test_feo_import_promote_level import _import17
from tests.test_feo_import_tree import (
    _cleanup_subsidy, _get_categories, _get_items, _make_subsidy, mk_row,
)


async def _single_item(db_session, subsidy_id, leaf_name):
    """Ходовой хелпер тестов этого файла: единственная категория с именем
    `leaf_name` и единственная плановая позиция внутри неё."""
    cats = await _get_categories(db_session, subsidy_id)
    leaf = next(c for c in cats if c.name == leaf_name)
    items = await _get_items(db_session, leaf.id)
    assert len(items) == 1, f"ожидалась ровно одна позиция в «{leaf_name}», получено {len(items)}"
    return items[0]


@pytest.mark.asyncio
async def test_row_with_feo_money_only_is_feo_breakdown(db_session):
    """Строка с деньгами ТОЛЬКО в колонках ФЭО → is_feo_breakdown=True,
    is_internal_plan=False (плановых колонок в файле вообще нет)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление ФЭО", lvl3="Категория ФЭО",
            item_name="Позиция только ФЭО",
            feo_qty="10", feo_unit="шт", feo_price="100", feo_sum="1000",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        item = await _single_item(db_session, subsidy.id, "Категория ФЭО")
        assert item.name == "Позиция только ФЭО"
        assert item.is_feo_breakdown is True
        assert item.is_internal_plan is False
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_row_with_plan_money_only_is_internal_plan(db_session):
    """Строка с деньгами ТОЛЬКО в плановых колонках → is_internal_plan=True,
    is_feo_breakdown=False (боевой случай владельца — «Питание...»)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Питание", lvl3="Закупка продуктов",
            item_name="Позиция только план",
            plan_qty="1", plan_unit="усл", plan_price="500", plan_sum="500",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        item = await _single_item(db_session, subsidy.id, "Закупка продуктов")
        assert item.name == "Позиция только план"
        assert item.is_internal_plan is True
        assert item.is_feo_breakdown is False
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_row_with_both_feo_and_plan_money_sets_both_flags(db_session):
    """Строка с деньгами и в ФЭО, и в плане → обе галочки True одновременно
    (владелец явно допускает это сочетание)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление Обе", lvl3="Категория Обе",
            item_name="Позиция обе суммы",
            feo_sum="1000", plan_sum="500",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        item = await _single_item(db_session, subsidy.id, "Категория Обе")
        assert item.is_feo_breakdown is True
        assert item.is_internal_plan is True
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_row_with_no_money_defaults_to_internal_plan(db_session):
    """Строка совсем без денег (позиция заведена вручную, ни ФЭО, ни план не
    заполнены) → is_internal_plan=True, is_feo_breakdown=False — «обе False»
    запрещено."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Направление Пусто", lvl3="Категория Пусто",
            item_name="Позиция без денег",
        )]
        result = await _import17(db_session, subsidy.id, rows)
        assert result["errors"] == []

        item = await _single_item(db_session, subsidy.id, "Категория Пусто")
        assert item.is_internal_plan is True
        assert item.is_feo_breakdown is False
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
