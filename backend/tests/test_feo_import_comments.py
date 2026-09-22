"""Владелец, 22.09: колонка «Комментарий» шаблона импорта ФЭО уходит в ЛЕНТУ
комментариев (feo_comments — app/models/feo_comment.py), НЕ в notes. См.
app/services/feo_import_comments.py (сбор намерений + запись), задействован
через `_do_feo_import` (app/routers/feo_categories.py — реальное тело в
app/services/feo_import_core.py) параметром `c_comment`.

Проверяем ровно то, что просил владелец в задании:
  1. строка файла с заполненной «Плановой позицией» и «Комментарием» создаёт
     РОВНО ОДИН FeoComment у созданной FeoPlannedItem;
  2. повторный прогон ТОГО ЖЕ файла второй комментарий с тем же текстом НЕ
     создаёт (идемпотентность повторного импорта).

Как и test_feo_import_tree.py (тот же файл-сосед, тот же приём): `_do_feo_import`
вызывается напрямую списком строк, без HTTP/xlsx. Флейк pytest-asyncio
«different loop» — гонять тесты этого файла ПО ОДНОМУ:
`python -m pytest tests/test_feo_import_comments.py::<имя> -x -q`.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.routers.feo_categories import _do_feo_import
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_comment import FeoComment


# --- Макет тестовой строки: lvl2, lvl3, item_name, plan_sum, comment -------
ROW_FIELDS = ["lvl2", "lvl3", "item_name", "plan_qty", "plan_sum", "comment"]
_IDX = {name: i for i, name in enumerate(ROW_FIELDS)}


def mk_row(**kwargs):
    unknown = set(kwargs) - set(ROW_FIELDS)
    assert not unknown, f"неизвестные поля строки: {unknown}"
    row = [None] * len(ROW_FIELDS)
    for k, v in kwargs.items():
        row[_IDX[k]] = v
    return row


async def _make_subsidy(db_session):
    s = Subsidy(
        name=f"TestFeoImportComments-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=0,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _cleanup_subsidy(db_session, subsidy_id):
    await db_session.execute(text(
        "DELETE FROM feo_comments WHERE feo_planned_item_id IN "
        "(SELECT id FROM feo_planned_items WHERE feo_category_id IN "
        "(SELECT id FROM feo_categories WHERE subsidy_id = :sid))"
        " OR feo_category_id IN (SELECT id FROM feo_categories WHERE subsidy_id = :sid)"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM feo_planned_items WHERE feo_category_id IN "
        "(SELECT id FROM feo_categories WHERE subsidy_id = :sid)"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM feo_categories WHERE subsidy_id = :sid"
    ), {"sid": subsidy_id})
    await db_session.execute(text(
        "DELETE FROM subsidies WHERE id = :sid"
    ), {"sid": subsidy_id})
    await db_session.commit()


async def _import(db_session, subsidy_id, rows, dry_run=False):
    return await _do_feo_import(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=None, c_lvl5=_IDX["item_name"],
        c_qty=None, c_unit=None, c_item_amt=None,
        c_code=None, c_appendix=None, c_budget=None, c_active=None,
        c_row_plan_qty=_IDX["plan_qty"], c_row_plan_sum=_IDX["plan_sum"],
        c_comment=_IDX["comment"],
        default_subsidy_id=subsidy_id,
        dry_run=dry_run,
        db=db_session,
    )


async def _get_categories(db_session, subsidy_id):
    res = await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    return res.scalars().all()


async def _get_items(db_session, feo_category_id):
    res = await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == feo_category_id)
    )
    return res.scalars().all()


async def _get_item_comments(db_session, feo_planned_item_id):
    res = await db_session.execute(
        select(FeoComment).where(FeoComment.feo_planned_item_id == feo_planned_item_id)
    )
    return res.scalars().all()


@pytest.mark.asyncio
async def test_row_comment_creates_one_item_comment_and_reimport_does_not_duplicate(db_session):
    """Строка с «Плановой позицией» + «Комментарием» → ровно один FeoComment у
    созданной FeoPlannedItem. Повторный импорт ТОГО ЖЕ файла — второй
    комментарий с тем же текстом не создаётся (Правило владельца:
    идемпотентность повторного импорта)."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Прочие расходы", lvl3="Расходы на ремонт ТС",
            item_name="УАЗ Патриот У914ВН 180",
            plan_qty="1", plan_sum="178779.59",
            comment="Согласовано с бухгалтерией 22.09",
        )]

        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert result["comments_created"] == 1

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        leaf = by_name["Расходы на ремонт ТС"]
        items = await _get_items(db_session, leaf.id)
        assert len(items) == 1
        item = items[0]
        assert item.name == "УАЗ Патриот У914ВН 180"

        comments = await _get_item_comments(db_session, item.id)
        assert len(comments) == 1
        assert comments[0].text == "Согласовано с бухгалтерией 22.09"
        assert comments[0].feo_category_id is None

        # Повторный прогон ТОГО ЖЕ файла — тот же товар (найден по имени,
        # см. _matching_items в feo_import_duplicates.py) не получает второй
        # комментарий с тем же текстом.
        result2 = await _import(db_session, subsidy.id, rows)
        assert result2["errors"] == []
        assert result2["comments_created"] == 0

        items_after = await _get_items(db_session, leaf.id)
        assert len(items_after) == 1
        comments_after = await _get_item_comments(db_session, items_after[0].id)
        assert len(comments_after) == 1, "повторный импорт не должен плодить дубли комментария"
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_row_without_item_attaches_comment_to_category(db_session):
    """Строка БЕЗ «Плановой позиции» (только уровни) + «Комментарий» →
    комментарий уходит к КАТЕГОРИИ этой строки (самый глубокий уровень), а не
    теряется и не пишется в notes."""
    subsidy = await _make_subsidy(db_session)
    try:
        rows = [mk_row(
            lvl2="Прочие расходы", lvl3="Расходы на ремонт ТС",
            comment="Требует уточнения по смете",
        )]
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []
        assert result["comments_created"] == 1

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        leaf = by_name["Расходы на ремонт ТС"]

        res = await db_session.execute(
            select(FeoComment).where(FeoComment.feo_category_id == leaf.id)
        )
        comments = res.scalars().all()
        assert len(comments) == 1
        assert comments[0].text == "Требует уточнения по смете"
        assert comments[0].feo_planned_item_id is None
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


@pytest.mark.asyncio
async def test_dry_run_does_not_write_comment_but_counts_it(db_session):
    """dry_run=True: комментарий НЕ пишется в БД (транзакция откатывается), но
    comments_created в ответе считает, сколько было бы создано — предпросмотр
    мастера должен это показать."""
    subsidy = await _make_subsidy(db_session)
    # Правило (см. test_feo_import_budget_conflicts.py): захватываем id ДО
    # dry_run — rollback внутри _do_feo_import(dry_run=True) экспайрит ORM-
    # объект `subsidy`, и обращение к `subsidy.id` ПОСЛЕ dry_run триггерит
    # его перезагрузку внутри savepoint тестовой транзакции — конфликт.
    subsidy_id = subsidy.id
    try:
        rows = [mk_row(
            lvl2="Прочие расходы", lvl3="Расходы на ремонт ТС",
            item_name="УАЗ Патриот У914ВН 180",
            plan_qty="1", plan_sum="178779.59",
            comment="Комментарий предпросмотра",
        )]
        result = await _import(db_session, subsidy_id, rows, dry_run=True)
        assert result["errors"] == []
        assert result["comments_created"] == 1

        cats = await _get_categories(db_session, subsidy_id)
        assert cats == [], "dry_run не должен ничего писать в БД"
    finally:
        await _cleanup_subsidy(db_session, subsidy_id)
