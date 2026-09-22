"""Построчный импорт ФЭО БЕЗ нумерации A–D (app/services/feo_import_apply.py:
item_attached_to_previous_node/group_total_row/item_name_equals_category).

Решение владельца (22.09, дословно): «Категории в названии колонок. Нет у
колонки названия — она не нужна ни мне, ни программе». Путь импорта «по
нумерации» (безымянные ведущие колонки A–D как источник иерархии,
app/services/feo_import_numbering.py + detect_numbering_columns/c_num*/
col_num*) удалён целиком — единственный источник дерева теперь маппинг по
заголовку (`find_col`) и явный column-mapping мастера (`/import-mapped`),
безымянные колонки слева от «Субсидия» просто игнорируются, как и любые
другие неопознанные колонки.

Тот же стиль вызова, что и в test_feo_import_tree.py: `_do_feo_import`
напрямую списком строк (xlsx не нужен), колонки — индексы через `c_*`.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.routers.feo_categories import _do_feo_import
from app.routers.feo_import import import_feo_from_excel
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from tests.test_feo_import_item_type_column import _mk_xlsx_upload

ROW_FIELDS = [
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
    s = Subsidy(name=f"TestFeoOrphan-{uuid.uuid4().hex[:8]}", year=2026, budget=0, require_planned_dates=False)
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


async def _import(db_session, subsidy_id, rows):
    return await _do_feo_import(
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


# --- 1. Пустой Уровень 2 не рождает корень, group_total_row отменяет ------
# строку-сироту (сумма = сумме следующих строк того же узла).

@pytest.mark.asyncio
async def test_orphan_row_attaches_to_previous_node_and_group_total_suppressed(db_session):
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
        result = await _import(db_session, subsidy.id, rows)
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


# --- 2. Строка-сирота без уровней читает свои qty/unit/price (не только ----
# сумму), и group_total_row отменяет её ДО того, как она попадёт в окно
# дублей вместе с составляющими той же суммы (владелец, скриншоты: F/G/H
# пусты, AE/AF/AG/AH/AI = Плановая позиция/ед./кол-во/цена/сумма плана;
# боевые строки 9 и 16).

@pytest.mark.asyncio
async def test_orphan_group_total_before_dedup_and_qty_read(db_session):
    rows = [
        mk_row(lvl2="Прочие расходы"),  # якорь — устанавливает узел-предка
        # Строка 9: итог группы (AG=1, AI=450 000) = сумме 6 следующих строк
        # (по 75 000) — не должна стать отдельной позицией.
        mk_row(item_name="Аренда помещения/страхование", qty=1, plan_sum=Decimal("450000")),
        mk_row(item_name="Аренда — офис 1", plan_sum=Decimal("75000")),
        mk_row(item_name="Аренда — офис 2", plan_sum=Decimal("75000")),
        mk_row(item_name="Аренда — офис 3", plan_sum=Decimal("75000")),
        mk_row(item_name="Аренда — офис 4", plan_sum=Decimal("75000")),
        mk_row(item_name="Аренда — офис 5", plan_sum=Decimal("75000")),
        mk_row(item_name="Аренда — офис 6", plan_sum=Decimal("75000")),
        # Строка 16: итог группы (AG=12, AH=50 000, AI=760 000) = сумме
        # 17–20 (600 000+80 000+20 000+60 000); AE («Плановая позиция»)
        # совпадает у всех пяти строк («Коммунальные расходы») — тот же
        # ключ группы дублей, что и у строк-составляющих.
        mk_row(item_name="Коммунальные расходы", qty=12, price=Decimal("50000"), plan_sum=Decimal("760000")),
        mk_row(item_name="Коммунальные расходы", plan_sum=Decimal("600000")),
        mk_row(item_name="Коммунальные расходы", plan_sum=Decimal("20000")),
        mk_row(item_name="Коммунальные расходы", plan_sum=Decimal("60000")),
        mk_row(item_name="Коммунальные расходы", plan_sum=Decimal("80000")),
        # Контрольная строка: сирота с реальным количеством, НЕ итог группы
        # (ни с чем не совпадает) — количество обязано остаться 12, а не
        # превратиться в выдуманную 1.
        mk_row(item_name="Тест количество без итога", qty=12, plan_sum=Decimal("999999")),
    ]
    subsidy = await _make_subsidy(db_session)
    try:
        result = await _import(db_session, subsidy.id, rows)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        prochie = next(c for c in cats if c.name == "Прочие расходы")
        items = await _get_items(db_session, prochie.id)
        by_name: dict[str, list] = {}
        for it in items:
            by_name.setdefault(it.name, []).append(it)

        assert "Аренда помещения/страхование" not in by_name, (
            "строка-итог (450 000 = 6×75 000) не должна стать отдельной позицией"
        )
        assert sum(len(v) for k, v in by_name.items() if k.startswith("Аренда — офис")) == 6

        kom_items = by_name.get("Коммунальные расходы", [])
        assert len(kom_items) == 4, "только 4 составляющих строки 17–20; итоговая строка 16 отменена"
        assert sum((it.amount for it in kom_items), Decimal("0")) == Decimal("760000")

        control = by_name["Тест количество без итога"]
        assert len(control) == 1
        assert control[0].quantity == Decimal("12"), (
            "реальное количество из файла обязано сохраниться, не выдуманная 1"
        )

        warn_by_kind_name = {(w["kind"], w.get("name")) for w in result["warnings"]}
        assert ("group_total_row", "Аренда помещения/страхование") in warn_by_kind_name
        assert ("group_total_row", "Коммунальные расходы") in warn_by_kind_name
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 3. Строка item_name_equals_category без детей, равная сумме следующих -
# строк того же уровня (пример «Расходы закупка товаров…» 1 997 229,50 =
# 700 000 + 580 659,50 + 716 570) → позиция не создаётся, предупреждение
# подменяется на group_total_row (feo_import_apply.py::_self_declared_regs,
# тот же пост-проход и то же имя предупреждения, что и у строки-сироты выше
# — Правило №6, одна логика строки-итога на оба случая).

@pytest.mark.asyncio
async def test_item_name_equals_category_group_total_suppressed(db_session):
    _name = "Расходы закупка товаров, услуг, в том числе проезд, проживание и питание"
    rows = [
        # Строка называет себя и подразделом (Уровень 2), и позицией
        # (Плановая позиция) — item_name_equals_category; её сумма совпадает
        # с суммой трёх следующих строк того же уровня.
        mk_row(lvl2=_name, item_name=_name, feo_sum=Decimal("1997229.50")),
        mk_row(lvl2="Проезд, проживание, питание", feo_sum=Decimal("700000")),
        mk_row(lvl2="МТО для организации участия в ГМ, ЧС и тд", feo_sum=Decimal("580659.50")),
        mk_row(lvl2="Доп комплектация", feo_sum=Decimal("716570")),
    ]
    subsidy = await _make_subsidy(db_session)
    try:
        result = await _do_feo_import(
            rows=rows,
            c_subsidy=None,
            c_lvl2=_IDX["lvl2"], c_lvl3=None, c_lvl4=None, c_lvl5=_IDX["item_name"],
            c_qty=_IDX["qty"], c_unit=_IDX["unit"], c_item_amt=None,
            c_code=None, c_appendix=None, c_budget=None, c_active=None,
            c_item_price=_IDX["price"],
            c_row_feo_sum=_IDX["feo_sum"], c_row_plan_sum=_IDX["plan_sum"],
            default_subsidy_id=subsidy.id,
            db=db_session,
        )
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        leaf = by_name[_name]
        assert leaf.budget == Decimal("1997229.50")

        items = await _get_items(db_session, leaf.id)
        assert items == [], "строка-итог группы не должна стать отдельной позицией"

        warn_kinds = {(w["kind"], w.get("name")) for w in result["warnings"]}
        assert ("group_total_row", _name) in warn_kinds
        assert ("item_name_equals_category", _name) not in warn_kinds, (
            "предупреждение обязано быть ЗАМЕНЕНО на group_total_row, а не дублироваться"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 4. Безымянные колонки слева от «Субсидия» (бывшие кандидаты в ---------
# нумерацию A–D, удалённую 22.09) просто ИГНОРИРУЮТСЯ — маппинг только по
# заголовку (find_col), результат импорта идентичен файлу без них.

@pytest.mark.asyncio
async def test_unnamed_leading_columns_before_subsidy_are_ignored(db_session, superadmin_user):
    async def _run(with_garbage: bool):
        subsidy = await _make_subsidy(db_session)
        try:
            if with_garbage:
                headers = [
                    "", "", "", "",
                    "Субсидия", "Уровень 2", "Плановая позиция", "Сумма по ФЭО",
                ]
                row = [
                    "7", "2.2.1", "abc", "3",
                    subsidy.name, "Направление", "Позиция", "500000",
                ]
            else:
                headers = ["Субсидия", "Уровень 2", "Плановая позиция", "Сумма по ФЭО"]
                row = [subsidy.name, "Направление", "Позиция", "500000"]
            upload = _mk_xlsx_upload(headers, row)
            result = await import_feo_from_excel(
                file=upload, dry_run=False, remap="", apply_remap=False,
                duplicate_resolutions="", item_type_decisions="",
                db=db_session, current_user=superadmin_user,
            )
            assert result["errors"] == []
            cats = await _get_categories(db_session, subsidy.id)
            cat = next(c for c in cats if c.name == "Направление")
            items = await _get_items(db_session, cat.id)
            return cat.budget, sorted((it.name, it.amount) for it in items)
        finally:
            await _cleanup_subsidy(db_session, subsidy.id)

    baseline = await _run(False)
    with_garbage = await _run(True)
    assert with_garbage == baseline, (
        "безымянные колонки слева от «Субсидия» обязаны игнорироваться целиком — "
        "результат не должен отличаться от файла без них"
    )
