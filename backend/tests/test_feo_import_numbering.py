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
from app.routers.feo_import import detect_numbering_columns
from app.services.feo_import_numbering import parse_row_path
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


# --- 0. Разбор пути строки и детект колонок — боевой файл ДНР_2026, ------
# смешанные целые/склеенные-точками значения в одной и той же колонке
# (владелец, 22.09): A=1..2 целое, но B/C/D иногда несут "2.2"/"2.2.1"/"2.3"
# вместо отдельных целых по колонкам — раскладка условий ниже дословно
# повторяет 8 примеров строк реального файла.

@pytest.mark.parametrize("kwargs,expected", [
    # r2: A=1,D=1 (B/C пусты) — D оторванный хвост, не читается вовсе
    (dict(num1=1, num4=1), (1,)),
    # r7: A=2,D=2 (B/C пусты) — тот же оторванный хвост
    (dict(num1=2, num4=2), (2,)),
    # r16: A=2,B=1,C=2 — обычные целые по колонкам
    (dict(num1=2, num2=1, num3=2), (2, 1, 2)),
    # r17: A=2,B=1,C=2,D=1 — лист под узлом r16
    (dict(num1=2, num2=1, num3=2, num4=1), (2, 1, 2, 1)),
    # r21: A=2,B=2,D="2.2" (C пусто) — D недостижим (обрыв раньше на пустой C)
    (dict(num1=2, num2=2, num4="2.2"), (2, 2)),
    # r22: A=2,B=2,C="2.2.1" — склеенная ячейка задаёт путь целиком (3 сегмента)
    (dict(num1=2, num2=2, num3="2.2.1"), (2, 2, 1)),
    # r23: A=2,B=3,D="2.3" (C пусто) — D недостижим
    (dict(num1=2, num2=3, num4="2.3"), (2, 3)),
    # r24: A=2,B=3,C=1 — обычные целые
    (dict(num1=2, num2=3, num3=1), (2, 3, 1)),
])
def test_parse_row_path_handles_dotted_cells_and_orphan_tail(kwargs, expected):
    row = mk_row(**kwargs)
    assert parse_row_path(
        row, _IDX["num1"], _IDX["num2"], _IDX["num3"], _IDX["num4"],
    ) == expected


def test_detect_numbering_columns_accepts_dotted_cells():
    """Боевой файл ДНР_2026: колонка C содержит "2.2.1" (не целое), колонка D
    содержит то целое (1,2), то склеенное "2.2"/"2.3" — раньше detect_
    numbering_columns требовал ИСКЛЮЧИТЕЛЬНО целых и обрывался на первой же
    такой ячейке, урезая число обнаруженных колонок нумерации (2 вместо 4) и
    роняя файл в старую построчную логику. Все 4 колонки обязаны пройти
    детект."""
    rows = [
        mk_row(num1=1, num4=1),
        mk_row(num1=2, num4=2),
        mk_row(num1=2, num2=1, num3=2),
        mk_row(num1=2, num2=1, num3=2, num4=1),
        mk_row(num1=2, num2=2, num4="2.2"),
        mk_row(num1=2, num2=2, num3="2.2.1"),
        mk_row(num1=2, num2=3, num4="2.3"),
        mk_row(num1=2, num2=3, num3=1),
    ]
    cols = detect_numbering_columns(rows, boundary_col=4)
    assert cols == [_IDX["num1"], _IDX["num2"], _IDX["num3"], _IDX["num4"]]


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


# --- 2b. Старый путь без нумерации: строка-сирота без уровней читает свои --
# qty/unit/price (не только сумму), и group_total_row отменяет её ДО того,
# как она попадёт в окно дублей вместе с составляющими той же суммы
# (владелец, скриншоты: F/G/H пусты, AE/AF/AG/AH/AI = Плановая позиция/ед./
# кол-во/цена/сумма плана; боевые строки 9 и 16).

@pytest.mark.asyncio
async def test_no_numbering_orphan_group_total_before_dedup_and_qty_read(db_session):
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
        result = await _import(db_session, subsidy.id, rows, numbered=False)
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


# --- 3. Количество не выдумывается для листа по нумерации (та же ошибка, ---
# что владелец поймал в К4, feo_import_duplicates._sum_qty) ----------------

@pytest.mark.asyncio
async def test_numbering_leaf_qty_not_invented(db_session):
    rows = [
        mk_row(num1=9, lvl2="Тест количество"),  # узел (9,) — 2 листа-ребёнка
        # Кол-во не задано, но задана Сумма плана напрямую — amount = сумма
        # плана как есть, quantity остаётся None (не 1).
        mk_row(num1=9, num2=1, item_name="Позиция без кол-ва с суммой плана", plan_sum=Decimal("5000")),
        # Кол-во не задано, задана только цена (без Суммы плана) — цена БЕЗ
        # количества сама по себе не сумма (цена × выдуманная 1 — ошибка);
        # amount падает на фолбэк «Сумма по ФЭО».
        mk_row(num1=9, num2=2, item_name="Позиция без кол-ва с ценой", price=Decimal("100"), feo_sum=Decimal("300")),
    ]
    subsidy = await _make_subsidy(db_session)
    try:
        result = await _import(db_session, subsidy.id, rows, numbered=True)
        assert result["errors"] == []

        cats = await _get_categories(db_session, subsidy.id)
        by_name = {c.name: c for c in cats}
        node = by_name["Тест количество"]
        items = await _get_items(db_session, node.id)
        by_item = {it.name: it for it in items}
        assert len(items) == 2

        with_plan_sum = by_item["Позиция без кол-ва с суммой плана"]
        assert with_plan_sum.quantity is None, "количество не задано в файле — не должно стать 1"
        assert with_plan_sum.amount == Decimal("5000")

        with_price = by_item["Позиция без кол-ва с ценой"]
        assert with_price.quantity is None, "количество не задано в файле — не должно стать 1"
        assert with_price.amount == Decimal("300"), (
            "цена без количества — не сумма (100×1 не должно быть посчитано); "
            "взята Сумма по ФЭО"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)


# --- 4. Тот же результат, что и тест 1, при боевой раскладке нумерации -----
# ДНР_2026 (22.09): "оторванные хвосты" (D заполнена при пустых B/C) и
# склеенные точками ячейки ("2.2.1") вместо отдельных целых по колонкам.

@pytest.mark.asyncio
async def test_numbering_builds_same_tree_with_battle_file_dotted_layout(db_session):
    rows = [
        # ФОТ — узел (1,); num4=1 — оторванный хвост при пустых num2/num3 (r2)
        mk_row(num1=1, num4=1, lvl2="ФОТ и иные выплаты персоналу", plan_sum=Decimal("33881012.80")),
        mk_row(num1=1, num2=1, item_name="ФОТ ДНР", plan_sum=Decimal("27141912")),
        mk_row(num1=1, num2=2, item_name="НДФЛ 13%", plan_sum=Decimal("4055688")),
        mk_row(num1=1, num2=3, item_name="Страховой взнос 7.8%", plan_sum=Decimal("2433412.80")),
        mk_row(num1=1, num2=4, item_name="Командировочные расходы", plan_sum=Decimal("250000")),
        # Прочие расходы — узел (2,); num4=2 — оторванный хвост (r7)
        mk_row(num1=2, num4=2, lvl2="Прочие расходы", feo_sum=Decimal("3721209.09")),
        # Коммунальные расходы — узел (2,1,2) вместо (2,1) в основном тесте
        # (r16: A=2,B=1,C=2, обычные целые по колонкам) — ancestor всё равно
        # ближайший УЖЕ созданный узел (root «Прочие расходы»), т.к. узла
        # (2,1) отдельно нет ни там, ни здесь — дерево получается тем же.
        mk_row(num1=2, num2=1, num3=2, item_name="Коммунальные расходы", plan_sum=Decimal("760000")),
        mk_row(num1=2, num2=1, num3=2, num4=1, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 1", qty=8, price=75000, plan_sum=Decimal("600000")),
        mk_row(num1=2, num2=1, num3=2, num4=2, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 2", qty=4, price=20000, plan_sum=Decimal("80000")),
        mk_row(num1=2, num2=1, num3=2, num4=3, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 3", qty=1, price=20000, plan_sum=Decimal("20000")),
        mk_row(num1=2, num2=1, num3=2, num4=4, lvl2="Прочие расходы",
               lvl3="Расходы на арендную плату за пользование помещением",
               item_name="Арендный платёж 4", qty=1, price=60000, plan_sum=Decimal("60000")),
        # Расходы на техобслуживание — узел (2,2); num4="2.2" — оторванный
        # хвост, недостижим (обрыв раньше на пустой C, r21)
        mk_row(num1=2, num2=2, num4="2.2", item_name="Расходы на техническое обслуживание оргтехники", feo_sum=Decimal("100000")),
        # Лист (2,2,1) — задан СКЛЕЕННОЙ ячейкой "2.2.1" в одной колонке (C)
        # вместо отдельных целых B=2,C=1 (r22) — путь совпадает с накопленным
        # слева (A=2,B=2) и задаёт его целиком.
        mk_row(num1=2, num2=2, num3="2.2.1", item_name="Расходы на техническое обслуживание оргтехники", plan_sum=Decimal("100000")),
        # Расходы на содержание и ремонт ТС — узел (2,3); num4="2.3" —
        # оторванный хвост, недостижим (r23)
        mk_row(num1=2, num2=3, num4="2.3", item_name="Расходы на содержание и ремонт транспортных средств", feo_sum=Decimal("863979.59")),
        mk_row(num1=2, num2=3, num3=1, item_name="Ремонт ТС", plan_sum=Decimal("863979.59")),
        # Расходы закупка товаров... — узел (2,4), 3 дочерних позиции
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
            "должно быть РОВНО 2 корня, как и в основном тесте — оторванные "
            "хвосты (D при пустых B/C) не должны стать отдельными узлами"
        )

        fot = by_name["ФОТ и иные выплаты персоналу"]
        fot_items = await _get_items(db_session, fot.id)
        assert len(fot_items) == 4
        assert sum((it.amount for it in fot_items), Decimal("0")) == Decimal("33881012.80")

        kom = by_name["Коммунальные расходы"]
        assert kom.parent_id == by_name["Прочие расходы"].id, "«Коммунальные расходы» — узел под «Прочие расходы», не корень"
        kom_items = await _get_items(db_session, kom.id)
        assert len(kom_items) == 4, "4 позиции — те же 4 «Арендных платежа»"
        assert sum((it.amount for it in kom_items), Decimal("0")) == Decimal("760000")

        teh = by_name["Расходы на техническое обслуживание оргтехники"]
        assert teh.parent_id == by_name["Прочие расходы"].id
        teh_items = await _get_items(db_session, teh.id)
        assert len(teh_items) == 1
        assert teh_items[0].amount == Decimal("100000"), "позиция задана склеенной ячейкой «2.2.1»"

        remont = by_name["Расходы на содержание и ремонт транспортных средств"]
        assert remont.parent_id == by_name["Прочие расходы"].id

        zakupka = by_name["Расходы закупка товаров, услуг, в том числе проезд, проживание и питание"]
        assert zakupka.parent_id == by_name["Прочие расходы"].id
        zak_items = await _get_items(db_session, zakupka.id)
        assert len(zak_items) == 3
        assert sum((it.amount for it in zak_items), Decimal("0")) == Decimal("1997229.50")

        total_plan = Decimal("0")
        for c in cats:
            for it in await _get_items(db_session, c.id):
                total_plan += it.amount or Decimal("0")
        assert total_plan == Decimal("3721209.09") + Decimal("33881012.80"), (
            "то же итого, что и в основном тесте — дерево эквивалентно"
        )
    finally:
        await _cleanup_subsidy(db_session, subsidy.id)
