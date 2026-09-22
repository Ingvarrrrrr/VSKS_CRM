"""Автотесты на нумерацию строк A–D (22.09, боевой случай субсидия ДНР_2026,
см. app/services/feo_import_numbering.py) + связанные точечные правки
построчного импорта БЕЗ нумерации (app/services/feo_import_apply.py:
item_attached_to_previous_node/group_total_row).

Тот же стиль вызова, что и в test_feo_import_tree.py: `_do_feo_import`
напрямую списком строк (xlsx не нужен), колонки — индексы через `c_*`.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.routers.feo_categories import _do_feo_import
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem

ROW_FIELDS = [
    "num1", "num2", "num3", "num4",
    "lvl2", "lvl3", "lvl4", "item_name",
    "qty", "unit", "price", "feo_sum", "plan_sum",
]
_IDX = {name: i for i, name in enumerate(ROW_FIELDS)}


def mk_row(**kwargs):
    unknown = set(kwargs) - set(ROW_FIELDS)
    assert not unknown, f"неизвестные поля строки: {unknown}"
    row = [None] * len(ROW_FIELDS)
    for k, v in kwargs.items():
        row[_IDX[k]] = v
    return row


async def _make_subsidy(db_session):
    s = Subsidy(name=f"TestFeoNumbering-{uuid.uuid4().hex[:8]}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _cleanup_subsidy(db_session, subsidy_id):
    await db_session.execute(text(
        "DELETE FROM feo_planned_items WHERE feo_category_id IN "
        "(SELECT id FROM feo_categories WHERE subsidy_id = :sid)"
    ), {"sid": subsidy_id})
    await db_session.execute(text("DELETE FROM feo_categories WHERE subsidy_id = :sid"), {"sid": subsidy_id})
    await db_session.execute(text("DELETE FROM subsidies WHERE id = :sid"), {"sid": subsidy_id})
    await db_session.commit()


async def _get_categories(db_session, subsidy_id):
    res = await db_session.execute(select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id))
    return res.scalars().all()


async def _get_items(db_session, feo_category_id):
    res = await db_session.execute(select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == feo_category_id))
    return res.scalars().all()


async def _import(db_session, subsidy_id, rows, numbered: bool):
    kwargs = dict(
        rows=rows,
        c_subsidy=None,
        c_lvl2=_IDX["lvl2"], c_lvl3=_IDX["lvl3"], c_lvl4=_IDX["lvl4"], c_lvl5=_IDX["item_name"],
        c_qty=_IDX["qty"], c_unit=_IDX["unit"], c_item_amt=None,
        c_code=None, c_appendix=None, c_budget=None, c_active=None,
        c_item_price=_IDX["price"],
        c_row_feo_sum=_IDX["feo_sum"], c_row_plan_sum=_IDX["plan_sum"],
        default_subsidy_id=subsidy_id,
        db=db_session,
    )
    if numbered:
        kwargs.update(c_num1=_IDX["num1"], c_num2=_IDX["num2"], c_num3=_IDX["num3"], c_num4=_IDX["num4"])
    return await _do_feo_import(**kwargs)


# --- 1. Нумерация A-D — источник иерархии (боевой случай ДНР_2026) ---------

@pytest.mark.asyncio
async def test_numbering_builds_correct_tree_and_no_duplicate_totals(db_session):
    rows = [
        # ФОТ — узел (1,), N пусто -> бюджет из AI (group_total_row)
        mk_row(num1=1, lvl2="ФОТ и иные выплаты персоналу", plan_sum=Decimal("33881012.80")),
        mk_row(num1=1, num2=1, item_name="ФОТ ДНР", plan_sum=Decimal("27141912")),
        mk_row(num1=1, num2=2, item_name="НДФЛ 13%", plan_sum=Decimal("4055688")),
        mk_row(num1=1, num2=3, item_name="Страховой взнос 7.8%", plan_sum=Decimal("2433412.80")),
        mk_row(num1=1, num2=4, item_name="Командировочные расходы", plan_sum=Decimal("250000")),
        # Прочие расходы — узел (2,), N задано напрямую
        mk_row(num1=2, lvl2="Прочие расходы", feo_sum=Decimal("3721209.09")),
        # Коммунальные расходы — узел (2,1) БЕЗ имени уровня (F/G/H пусты) —
        # имя из «Плановой позиции»; N пусто -> group_total_row
        mk_row(num1=2, num2=1, item_name="Коммунальные расходы", plan_sum=Decimal("760000")),
        mk_row(num1=2, num2=1, num3=1, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 1", qty=8, price=75000, plan_sum=Decimal("600000")),
        mk_row(num1=2, num2=1, num3=2, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 2", qty=4, price=20000, plan_sum=Decimal("80000")),
        mk_row(num1=2, num2=1, num3=3, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 3", qty=1, price=20000, plan_sum=Decimal("20000")),
        mk_row(num1=2, num2=1, num3=4, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 4", qty=1, price=60000, plan_sum=Decimal("60000")),
        # Расходы на техобслуживание — узел (2,2), N задано напрямую
        mk_row(num1=2, num2=2, item_name="Расходы на техническое обслуживание оргтехники", feo_sum=Decimal("100000")),
        mk_row(num1=2, num2=2, num3=1, item_name="Расходы на техническое обслуживание оргтехники", plan_sum=Decimal("100000")),
        # Расходы на содержание и ремонт ТС — узел (2,3)
        mk_row(num1=2, num2=3, item_name="Расходы на содержание и ремонт транспортных средств", feo_sum=Decimal("863979.59")),
        mk_row(num1=2, num2=3, num3=1, item_name="Ремонт ТС", plan_sum=Decimal("863979.59")),
        # Расходы закупка товаров... — узел (2,4), 3 дочерних позиции, БЕЗ дублирующей позиции 1 997 229,50
        mk_row(num1=2, num2=4, item_name="Расходы закупка товаров, услуг, в том числе проезд, проживание и питание", feo_sum=Decimal("1997229.50")),
        mk_row(num1=2, num2=4, num3=1, item_name="Проезд, проживание, питание", plan_sum=Decimal("700000")),
        mk_row(num1=2, num2=4, num3=2, item_name="МТО для организации участия в ГМ, ЧС и тд", plan_sum=Decimal("580659.50")),
        mk_row(num1=2, num2=4, num3=3, item_name="Доп комплектация", plan_sum=Decimal("716570")),
    ]
    subsidy = await _make_subsidy(db_session)
    try:
        result = await _import(db_session, subsidy.id, rows, numbered=True)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}

        roots = [c for c in cats if c.parent_id is None]
        assert {c.name for c in roots} == {"ФОТ и иные выплаты персоналу", "Прочие расходы"}, (
            "должно быть РОВНО 2 корня — ни «Коммунальные расходы», ни «Аренда...» корнями быть не должны"
        )

        fot = by_name["ФОТ и иные выплаты персоналу"]
        fot_items = await _get_items(db_session, fot.id)
        assert len(fot_items) == 4
        assert sum((it.amount for it in fot_items), Decimal("0")) == Decimal("33881012.80")

        kom = by_name["Коммунальные расходы"]
        assert kom.parent_id == by_name["Прочие расходы"].id, "«Коммунальные расходы» — узел под «Прочие расходы», не корень"
        kom_items = await _get_items(db_session, kom.id)
        assert len(kom_items) == 4, "4 позиции — r17..r20"
        assert sum((it.amount for it in kom_items), Decimal("0")) == Decimal("760000")
        assert not any(it.name == "Коммунальные расходы" for it in kom_items), (
            "своей дублирующей позиции «Коммунальные расходы» быть не должно"
        )
        assert "Расходы на арендную плату за пользование помещением" not in by_name, (
            "имя уровня строки-листа не должно порождать отдельную категорию — нумерация побеждает"
        )

        zakupka = by_name["Расходы закупка товаров, услуг, в том числе проезд, проживание и питание"]
        assert zakupka.parent_id == by_name["Прочие расходы"].id
        zak_items = await _get_items(db_session, zakupka.id)
        assert len(zak_items) == 3
        assert sum((it.amount for it in zak_items), Decimal("0")) == Decimal("1997229.50")
        assert not any(it.name == zakupka.name for it in zak_items), (
            "дублирующей позиции 1 997 229,50 у «Расходы закупка товаров…» быть не должно"
        )

        # Σ плана субсидии = Прочие(3 721 209.09) + ФОТ(33 881 012.80)
        all_items = []
        for c in cats:
            all_items.extend(await _get_items(db_session, c.id))
        total_plan = sum((it.amount or Decimal("0") for it in all_items), Decimal("0"))
        assert total_plan == Decimal("3721209.09") + Decimal("33881012.80")

        kinds = {w["kind"] for w in result["warnings"]}
        assert "group_total_row" in kinds
        assert "numbering_vs_levels" in kinds
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 2. Без нумерации: пустой Уровень 2 не рождает корень, group_total_row -

@pytest.mark.asyncio
async def test_no_numbering_orphan_row_attaches_and_group_total_suppressed(db_session):
    rows = [
        mk_row(lvl2="Прочие расходы"),
        # «Сирота» — без единого уровня, сумма = сумме следующих 4 строк того
        # же узла -> НЕ должна стать корнем и НЕ должна создать свою позицию
        mk_row(item_name="Коммунальные расходы", plan_sum=Decimal("760000")),
        mk_row(lvl2="Прочие расходы", item_name="Арендный платёж 1", qty=8, price=75000, plan_sum=Decimal("600000")),
        mk_row(lvl2="Прочие расходы", item_name="Арендный платёж 2", qty=4, price=20000, plan_sum=Decimal("80000")),
        mk_row(lvl2="Прочие расходы", item_name="Арендный платёж 3", qty=1, price=20000, plan_sum=Decimal("20000")),
        mk_row(lvl2="Прочие расходы", item_name="Арендный платёж 4", qty=1, price=60000, plan_sum=Decimal("60000")),
    ]
    subsidy = await _make_subsidy(db_session)
    try:
        result = await _import(db_session, subsidy.id, rows, numbered=False)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        assert "Коммунальные расходы" not in by_name, "пустой Уровень 2 не должен рождать новый корень"
        assert set(by_name) == {"Прочие расходы"}

        prochie = by_name["Прочие расходы"]
        assert prochie.parent_id is None
        items = await _get_items(db_session, prochie.id)
        assert len(items) == 4, "позиция-сирота (r16) не создана — только 4 «Арендных платежа»"
        assert not any(it.name == "Коммунальные расходы" for it in items)
        total = sum((it.amount for it in items), Decimal("0"))
        assert total == Decimal("760000"), "план не задвоен (760 000, а не 1 520 000)"

        kinds = {w["kind"] for w in result["warnings"]}
        assert "group_total_row" in kinds
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
