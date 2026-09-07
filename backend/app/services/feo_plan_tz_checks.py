"""feo_plan_tz_checks.py — контроль «ТЗ не выше привязанной плановой позиции».

Вынесено из feo_plan.py (рефакторинг без изменения поведения, сессия
2026-09-08, см. ПРАВИЛО №5). assert_tz_not_over_plan читает план узла
'manual_sum' через общий feo_plan_common._leaf_plan_manual — та же формула,
что и compute_feo_plan_tree/find_excess_culprit (ПРАВИЛО №6).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.services.feo_plan_common import _leaf_plan_manual


def _fmt_qty(d: Decimal) -> str:
    """Количество без хвостовых нулей (2, не 2.0000; 2.5, не 2.5000)."""
    s = f"{d:,.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _fmt_money(d: Decimal) -> str:
    return f"{d:,.2f} ₽"


async def assert_tz_not_over_plan(
    db: AsyncSession,
    *,
    feo_planned_item_id: Optional[int],
    feo_category_id: Optional[int],
    quantity,
    unit_price,
    total_price,
    item_name: str = "",
    sibling_quantity=0,
    sibling_total=0,
) -> None:
    """Бросает HTTPException 409, если ТЗ позиции (кол-во / цена за единицу / сумма)
    превышает привязанную плановую позицию — владелец (2026-08-07, план
    zany-fluttering-mountain.md, шаг 5): «ТЗ может быть НИЖЕ плана, но НЕ ВЫШЕ —
    ни по количеству, ни по цене за единицу, ни по сумме».

    Источник плана — РОВНО один из двух (не смешиваются между собой):
      1. feo_planned_item_id задан → FeoPlannedItem.quantity / .amount / .unit_price.
         Владелец (2026-09-02, «Логистические услуги»): unit_price — ОТДЕЛЬНОЕ
         поле цены за единицу (см. докстринг модели и миграцию
         z1a2b3c4d5e6_feo_planned_item_unit_price.py), а не производная от
         amount/quantity:
           - unit_price задана → план полноценный, amount = ИТОГОВАЯ сумма
             (используется как есть, либо quantity × unit_price, если amount
             почему-то пуст); количество/цена за единицу/сумма проверяются
             все три, как раньше.
           - unit_price NULL (в т.ч. ВСЕ позиции, заведённые до появления
             этого поля, — осознанное послабление, не регресс) → amount сама
             по себе ИТОГОВАЯ сумма, quantity — ОРИЕНТИРОВОЧНОЕ количество:
             деление amount/quantity НЕ выполняется, planned_unit_price
             остаётся None (цена за единицу не ограничивается), planned_qty
             тоже остаётся None (количество не ограничивается) — единственное
             ограничение ниже — сумма (planned_total = amount). Раньше здесь
             ВСЕГДА делили amount на quantity, из-за чего сценарий «сумма
             200 000, услуг примерно 20» неявно превращался в потолок цены
             10 000/услуга и блокировал закупку 21-й услуги в пределах той же
             суммы — ровно то, что владелец просил прекратить.
      2. Иначе, если задан feo_category_id → FeoCategory.planned_quantity /
         .planned_amount листа (planned_amount там УЖЕ цена за единицу, см.
         модель); плановая сумма = planned_quantity × planned_amount.
         Фолбэк (план переехал в записи внутри категории): если ОБА поля
         категории пусты (NULL) — берём активные FeoPlannedItem этой категории:
         plan_total = Σ amount (только положительные суммы), plan_qty =
         Σ quantity (если сумма количеств > 0), plan_unit_price = plan_total /
         plan_qty при plan_qty > 0. Без этого фолбэка гейт «ТЗ не дороже и не
         больше плана» тихо отключается для мигрированных категорий-листьев —
         см. compute_feo_plan_tree (тот же приём, та же семантика).

    Количество проверяется ОТДЕЛЬНО и обязательно от суммы — сценарий владельца
    «план 2 самолёта за 30 млн» не разрешает купить 3 штуки даже за те же 30 млн
    (3 шт по более низкой цене может пройти по сумме, но не по количеству).

    Никакого допуска: сравнение строго `>` в Decimal, без эпсилона («баланс
    копейка в копейку» — владелец). Входные quantity/unit_price/total_price
    приводятся к Decimal(str(...)) на входе (вызывающий код может передать
    float/None).

    Нет плановых данных (ни по FeoPlannedItem, ни по FeoCategory) → no-op —
    позиции без плана этим правилом не ограничиваются.

    Сообщение 409 перечисляет ВСЕ нарушенные величины разом (позиция может
    одновременно превышать и количество, и сумму — напр. «3 шт × 4 000 000»
    при плане «2 шт × 4 000 000»), с планом/фактом/разницей по каждой и общей
    подсказкой «что делать».

    sibling_quantity/sibling_total (владелец, задача от 2026-08-17, прод-инцидент
    закупка РЕЕ-2026-00887, +5 761 ₽): эта функция изначально проверяла КАЖДУЮ
    строку ТЗ по отдельности против ПОЛНОГО плана её плановой позиции — если в
    одной операции ДВЕ строки ссылались на ОДНУ и ту же плановую позицию, каждая
    проходила поодиночке, а суммарно план превышался. Параметры добавляют к
    проверяемым количеству и сумме остальные строки ТОЙ ЖЕ операции (закупки/
    заявки), уже привязанные к той же плановой позиции — накопление в пределах
    ОДНОЙ операции, межзакупочный расход сознательно НЕ учитывается (на проде
    таких случаев не было, а проверка через операции несёт риск ложных отказов).
    К цене за единицу (unit_price/price_d) siblings НЕ прибавляются — цена за
    единицу не накапливается, это свойство конкретной строки, а не объёма.
    Дефолт 0 — поведение без siblings не меняется. См. также обёртку
    assert_tz_batch_not_over_plan ниже, которая считает siblings по списку строк.
    """
    from fastapi import HTTPException
    from app.models.feo_planned_item import FeoPlannedItem

    planned_qty: Optional[Decimal] = None
    planned_unit_price: Optional[Decimal] = None
    planned_total: Optional[Decimal] = None

    if feo_planned_item_id:
        fpi = await db.get(FeoPlannedItem, feo_planned_item_id)
        if fpi is not None:
            if fpi.unit_price is not None:
                # Цена за единицу задана явно — план полноценный (см. докстринг
                # выше): количество, цена за единицу И сумма проверяются все.
                planned_unit_price = Decimal(str(fpi.unit_price))
                if fpi.quantity is not None:
                    planned_qty = Decimal(str(fpi.quantity))
                if fpi.amount is not None:
                    planned_total = Decimal(str(fpi.amount))
                elif planned_qty is not None:
                    planned_total = planned_qty * planned_unit_price
            else:
                # unit_price НЕ задана (владелец, 2026-09-02) — amount является
                # ИТОГОВОЙ суммой сама по себе, quantity ОРИЕНТИРОВОЧНОЕ.
                # planned_qty/planned_unit_price сознательно остаются None —
                # НЕ делим amount на quantity и НЕ ограничиваем ни количество,
                # ни цену за единицу. Единственное ограничение — сумма.
                # Затрагивает и ВСЕ позиции, заведённые до появления unit_price
                # (у них он тоже NULL) — осознанное послабление, см. докстринг.
                if fpi.amount is not None:
                    planned_total = Decimal(str(fpi.amount))
    elif feo_category_id:
        cat = await db.get(FeoCategory, feo_category_id)
        if cat is not None and (cat.plan_source or "planned_items") == "manual_sum":
            # Задача 6 (владелец, сессия 2026-09-03, отчёт): ДО этой правки здесь
            # безусловно брали planned_quantity×planned_amount, не глядя на
            # plan_source/manual_plan_amount — расходится с compute_feo_plan_tree/
            # find_excess_culprit, которые читают план узла через _leaf_plan_manual
            # (переключатель FeoCategory.plan_source). Для категорий в режиме
            # 'manual_sum' план теперь читается ТОЙ ЖЕ точкой.
            #
            # Проверено на живых данных (сессия 2026-09-03): у ВСЕХ 214 категорий
            # с plan_source='manual_sum' manual_plan_amount ЧИСЛЕННО совпадает со
            # старым planned_quantity×planned_amount, и активных FeoPlannedItem
            # под ними сейчас 0 — то есть СЕГОДНЯ эта ветка не меняет НИ ОДНОЙ
            # цифры ни у одной живой категории. Меняется только поведение ПОСЛЕ
            # согласования превышения плана (excess_plan_over_manual approved) —
            # раньше assert_tz_not_over_plan держал потолок на старом ручном числе
            # НАВСЕГДА, полностью игнорируя факт согласования; теперь видит
            # выросший items_total, как и дерево плана/find_excess_culprit.
            #
            # planned_qty/planned_unit_price (количество/цена за единицу)
            # СОЗНАТЕЛЬНО остаются от старых полей категории, НЕ пересчитываются
            # через _leaf_plan_manual — у 'manual_sum' нет отдельного понятия
            # «количество» (только суммарная цифра), а замена этих двух лимитов
            # не запрошена владельцем и несёт свой отдельный риск регрессии.
            if cat.planned_quantity is not None:
                planned_qty = Decimal(str(cat.planned_quantity))
            if cat.planned_amount is not None:
                planned_unit_price = Decimal(str(cat.planned_amount))

            _fpi_amt_q = (
                select(func.coalesce(
                    func.sum(case((FeoPlannedItem.amount > 0, FeoPlannedItem.amount), else_=0)), 0,
                ))
                .where(FeoPlannedItem.feo_category_id == feo_category_id)
                .where(FeoPlannedItem.is_active.is_(True))
            )
            _items_total = float((await db.execute(_fpi_amt_q)).scalar() or 0)

            from app.models.plan_excess_approval import PlanExcessApproval as _PEA
            _latest_status = (await db.execute(
                select(_PEA.status)
                .where(_PEA.feo_category_id == feo_category_id)
                .order_by(_PEA.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            _excess_approved = (_latest_status == "approved")

            _, _plan_manual, _ = _leaf_plan_manual(
                cat.plan_source, cat.manual_plan_amount, _items_total, _excess_approved,
            )
            planned_total = Decimal(str(_plan_manual))
        elif cat is not None:
            # plan_source='planned_items' (умолчание) — формулу СОЗНАТЕЛЬНО НЕ
            # трогаем (см. анализ задачи 6, отчёт сессии 2026-09-03): на живых
            # данных нашлось 53 категории с plan_source='planned_items', но
            # НЕНУЛЕВЫМИ planned_quantity/planned_amount при 0 активных
            # FeoPlannedItem — перевод их на Σ FeoPlannedItem (=0) обрушил бы
            # допустимый план этих категорий (местами многомиллионный) до нуля и
            # заблокировал бы ЛЮБУЮ позицию ТЗ по ним, чего никто не просил.
            # Раз compute_feo_plan_tree (после f8d68bc) уже игнорирует эти поля
            # для 'planned_items' — расхождение между ним и этой функцией у ЭТИХ
            # 53 категорий было и остаётся; чинить его — отдельная задача владельца
            # (например, домигрировать их в 'manual_sum', как остальные 214), не
            # эта.
            if cat.planned_quantity is not None:
                planned_qty = Decimal(str(cat.planned_quantity))
            if cat.planned_amount is not None:
                planned_unit_price = Decimal(str(cat.planned_amount))
            if planned_qty is not None and planned_unit_price is not None:
                planned_total = planned_qty * planned_unit_price
            elif planned_qty is None and planned_unit_price is None:
                # План переехал в записи внутри категории (FeoPlannedItem) — у
                # мигрированных категорий-листьев planned_quantity/planned_amount
                # самой категории — NULL, план лежит в активных FeoPlannedItem.
                # Без этого фолбэка planned_qty/planned_unit_price/planned_total
                # остаются None, ниже срабатывает no-op, и позиция закупки,
                # привязанная к КАТЕГОРИИ напрямую (без конкретной плановой
                # позиции), перестаёт ограничиваться вообще — 409 не сработает
                # никогда. Один запрос с агрегатами, без загрузки всех строк —
                # см. образец в compute_feo_plan_tree (feo_plan.py).
                fpi_agg_q = (
                    select(
                        func.coalesce(
                            func.sum(case((FeoPlannedItem.amount > 0, FeoPlannedItem.amount), else_=0)),
                            0,
                        ).label("amt"),
                        func.coalesce(func.sum(FeoPlannedItem.quantity), 0).label("qty"),
                    )
                    .where(FeoPlannedItem.feo_category_id == feo_category_id)
                    .where(FeoPlannedItem.is_active.is_(True))
                )
                agg_row = (await db.execute(fpi_agg_q)).one()
                fb_amt = Decimal(str(agg_row.amt or 0))
                fb_qty = Decimal(str(agg_row.qty or 0))
                if fb_amt > 0:
                    planned_total = fb_amt
                if fb_qty > 0:
                    planned_qty = fb_qty
                if planned_qty is not None and planned_qty > 0 and planned_total is not None:
                    planned_unit_price = planned_total / planned_qty

    if planned_qty is None and planned_unit_price is None and planned_total is None:
        return  # плановые данные не заданы — правило не применяется

    own_qty_d = Decimal(str(quantity)) if quantity is not None else Decimal("0")
    price_d = Decimal(str(unit_price)) if unit_price is not None else Decimal("0")
    own_total_d = Decimal(str(total_price)) if total_price is not None else (own_qty_d * price_d)

    sib_qty_d = Decimal(str(sibling_quantity)) if sibling_quantity is not None else Decimal("0")
    sib_total_d = Decimal(str(sibling_total)) if sibling_total is not None else Decimal("0")

    qty_d = own_qty_d + sib_qty_d
    total_d = own_total_d + sib_total_d
    has_siblings = sib_qty_d != 0 or sib_total_d != 0

    violations: list[str] = []
    if planned_qty is not None and qty_d > planned_qty:
        diff = qty_d - planned_qty
        violations.append(
            f"количество: план {_fmt_qty(planned_qty)}, в ТЗ {_fmt_qty(qty_d)} "
            f"(больше на {_fmt_qty(diff)})"
        )
    if planned_unit_price is not None and price_d > planned_unit_price:
        diff = price_d - planned_unit_price
        violations.append(
            f"цена за единицу: план {_fmt_money(planned_unit_price)}, в ТЗ {_fmt_money(price_d)} "
            f"(больше на {_fmt_money(diff)})"
        )
    if planned_total is not None and total_d > planned_total:
        diff = total_d - planned_total
        violations.append(
            f"сумма: план {_fmt_money(planned_total)}, в ТЗ {_fmt_money(total_d)} "
            f"(больше на {_fmt_money(diff)})"
        )

    if not violations:
        return

    name = item_name.strip() if item_name else "позиция"
    siblings_note = (
        " (учтены все строки этой операции, привязанные к той же плановой позиции)"
        if has_siblings else ""
    )
    raise HTTPException(
        409,
        f"ТЗ позиции «{name}»{siblings_note} превышает план: " + "; ".join(violations) + ". "
        "Измените плановую позицию в Плане закупок (потребует согласования, если "
        "выходит за ФЭО) или уменьшите ТЗ."
    )


async def assert_tz_batch_not_over_plan(
    db: AsyncSession,
    rows: list,
    *,
    fallback_category_id: Optional[int] = None,
) -> None:
    """Гейт «ТЗ не выше плана» (assert_tz_not_over_plan) для СПИСКА строк одной
    операции (закупка/заявка) целиком — владелец, 2026-08-17, прод-инцидент
    закупка РЕЕ-2026-00887 (+5 761 ₽): assert_tz_not_over_plan проверяла КАЖДУЮ
    строку по отдельности против ПОЛНОГО плана её плановой позиции — если в
    одной операции ДВЕ строки ссылались на ОДНУ и ту же плановую позицию, каждая
    поодиночке проходила (например «план 21 шт / 15 750 ₽»: строка А = 21 шт /
    15 750 ₽ — ровно план, строка Б = 4 шт / 3 000 ₽ — тоже ≤ плана), а вместе
    план превышали (25 шт / 18 750 ₽ против 21 шт / 15 750 ₽). Эта обёртка
    группирует строки по feo_planned_item_id и проверяет план ОДИН раз на
    группу, передавая сумму количества/суммы группы.

    Граница области (важно, НЕ расширять): накопление применяется ТОЛЬКО к
    строкам с заполненным feo_planned_item_id. Строки с feo_planned_item_id
    пустым проверяются против плана КАТЕГОРИИ по отдельности, как раньше —
    накопление там дублировало бы assert_no_unapproved_excess (у которого есть
    свой путь согласования). Межзакупочный расход (та же плановая позиция в
    ДРУГОЙ операции) сознательно НЕ учитывается — на проде таких случаев ноль,
    а проверка через операции несёт риск ложных отказов.

    Строки с over_plan=True пропускаются полностью — не проверяются и не
    учитываются в сумме группы (та же семантика, что и в поштучных вызовах
    во всех местах, откуда раньше вызывалась assert_tz_not_over_plan напрямую).

    unit_price группы = МАКСИМАЛЬНАЯ цена за единицу среди строк группы —
    правило «цена за единицу не выше плановой» обязано сработать на самой
    дорогой строке; для группы из одной строки это её собственная цена, т.е.
    поведение идентично прежнему поштучному вызову.

    Порядок обхода — сначала строки без плановой позиции (в порядке появления
    в rows), затем группы (в порядке первого появления feo_planned_item_id в
    rows) — детерминированный при одинаковом входе, чтобы сообщение об ошибке
    не «прыгало» между одинаковыми запросами. Полное совпадение с исходным
    построчным порядком невозможно в принципе: сумму группы нельзя посчитать,
    не увидев все её строки, поэтому группы проверяются отдельным проходом
    после сборки.

    Разложение суммы группы на «свою»/«братьев» (2026-08-17, фикс текста
    ошибки): ДО этого вызов передавал в assert_tz_not_over_plan уже готовую
    сумму группы целиком через quantity/total_price, БЕЗ sibling_quantity/
    sibling_total — из-за этого внутри has_siblings всегда получался False
    (siblings были нулевыми), и пояснение «учтены все строки...» в тексте 409
    никогда не появлялось, хотя число уже было накоплено по группе — владелец
    видел «в ТЗ 26 шт» и не понимал, откуда взялась цифра, если в его строке
    было только 21. Теперь количество/сумма ПЕРВОЙ строки группы передаются
    как «свои» (quantity/total_price), а Σ остальных строк группы — как
    sibling_quantity/sibling_total. Итоговые проверяемые величины (qty_d =
    own + sib, total_d = own + sib внутри assert_tz_not_over_plan) численно
    ИДЕНТИЧНЫ прежним — меняется только то, что has_siblings становится True
    для групп из 2+ строк и в сообщение попадает пояснение. Для группы из
    ОДНОЙ строки siblings = 0 — поведение полностью совпадает с прежним.
    """
    groups: dict[int, list] = {}
    individuals: list = []
    for row in rows:
        if getattr(row, "over_plan", False):
            continue
        fpi_id = getattr(row, "feo_planned_item_id", None)
        if fpi_id:
            groups.setdefault(fpi_id, []).append(row)
        else:
            individuals.append(row)

    for row in individuals:
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=None,
            feo_category_id=getattr(row, "feo_category_id", None) or fallback_category_id,
            quantity=row.quantity,
            unit_price=row.unit_price,
            total_price=row.total_price,
            item_name=row.item_name,
        )

    for fpi_id, group_rows in groups.items():
        first = group_rows[0]
        siblings = group_rows[1:]

        max_price = Decimal("0")
        for r in group_rows:
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            if r_price > max_price:
                max_price = r_price

        own_qty = Decimal(str(first.quantity)) if first.quantity is not None else Decimal("0")
        own_price = Decimal(str(first.unit_price)) if first.unit_price is not None else Decimal("0")
        own_total = Decimal(str(first.total_price)) if first.total_price is not None else (own_qty * own_price)

        sib_qty = Decimal("0")
        sib_total = Decimal("0")
        for r in siblings:
            r_qty = Decimal(str(r.quantity)) if r.quantity is not None else Decimal("0")
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            r_total = Decimal(str(r.total_price)) if r.total_price is not None else (r_qty * r_price)
            sib_qty += r_qty
            sib_total += r_total

        name = (first.item_name or "").strip() or "позиция"
        if len(group_rows) > 1:
            name = f"{name} и ещё {len(group_rows) - 1} поз."
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=fpi_id,
            feo_category_id=(getattr(first, "feo_category_id", None) or fallback_category_id),
            quantity=own_qty,
            unit_price=max_price,
            total_price=own_total,
            item_name=name,
            sibling_quantity=sib_qty,
            sibling_total=sib_total,
        )



