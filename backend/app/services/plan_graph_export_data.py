"""Сборка данных для живого (текущего) экспорта плана-графика субсидии.

Вынесено из app/routers/subsidy_plan_graph_export.py::export_plan_graph_excel
(Правило №5, рефакторинг 2026-09-08). Только запросы к БД и агрегация — без
какого-либо построения книги Excel (это app.services.plan_graph_export_xlsx).

ПРАВИЛО №6: эффективная сумма закупки без позиций (секция «без категории ФЭО»/
«itemless») читается ТОЛЬКО через app.services.purchase_amounts.load_purchase_amounts
— единая цепочка-по-стадии, используемая везде в проекте.

ИЗМЕНЕНО (Задача А, владелец 07.10.2026, план .planning/quick/2026-10-07-
plan-graph-export/PLAN.md): лист «Сводная» больше НЕ считает собственные
корзины здесь (старое поле `summary`/`_empty_summary_buckets` и блок сборки
по Товары/Услуги — удалены, это был второй расчёт мимо экрана субсидии,
ПРАВИЛО №6). Числа для «Сводной» теперь читает
app.services.subsidy_summary_by_kind.subsidy_summary_by_kind — отдельными
вызовами уже существующих функций экрана субсидии, роутер вызывает её сам.

ИЗМЕНЕНО (Задача B, владелец 07.10.2026): used_map (Σ PurchaseItem.total_price
плановой позиции — «Фактически (итого)» строки позиции) теперь ИСКЛЮЧАЕТ
отменённые закупки (status='cancelled') — раньше запрос не join'ился с
Purchase и не фильтровал статус вовсе, отменённая закупка молча входила в
факт/остаток/% исполнения.

ДОБАВЛЕНО (владелец 07.10.2026, группа «Договор и оплата»): к каждому
purchase_id, встреченному в под-строках фактических позиций (purchased_by_item/
purchased_by_cat/unlinked_purchases), подгружается сама Purchase ОДНИМ
запросом (purchase_rows_by_id) + общий ctx (purchase_export_ctx) из
app.services.purchase_export_cells — те же справочники, что у экспорта
закупок (ПРАВИЛО №6: не второй механизм чтения полей закупки, а
переиспользование get_cell_value)."""
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.services.committed_amounts import planned_item_contributions
from app.services.contract_balances import contract_balances
from app.services.feo_payroll import payroll_category_ids
from app.services.item_type_split import (
    KIND_GOODS, KIND_PAYROLL, KIND_SERVICES, KIND_UNSPECIFIED,
    kind_of_by_category_id,
)
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_export_cells import build_purchase_export_ctx


def item_planned_month(item) -> str:
    """«План. месяц платежа» ПОЗИЦИИ (не закупки) — владелец 09.10.2026,
    сверка на проде: grep plan_cashflow.py показал, что единственное
    существующее понятие «когда позиция должна быть оплачена по плану»
    (без закупки) — её СОБСТВЕННЫЕ FeoPlannedItem.planned_date (one_time) /
    monthly_start_date (monthly), те же поля, что app.services.plan_cashflow
    .expand_planned_item использует для прогноза cash-flow (ПРАВИЛО №6 — не
    второй резолвер, те же два поля по тому же payment_mode). Отдельного
    резолвера «закупка → позиция → график» в проекте НЕТ (Purchase.
    planned_payment_month и FeoPlannedItem.planned_date/monthly_start_date
    живут в разных, не связанных друг с другом местах) — для строк закупок
    столбец продолжает читаться через get_cell_value (Purchase.
    planned_payment_month), для строк позиций БЕЗ закупок — отсюда."""
    d = item.monthly_start_date if (item.payment_mode or "one_time") == "monthly" else item.planned_date
    return str(d) if d else ""

# «Товар / услуга» (владелец 08.10.2026, замечание 1 экспорта плана-графика)
# — подписи ОДНОЙ позиции/закупки, единственное число. Отличаются от подписей
# множественного числа агрегатных строк по виду («Товары»/«Услуги» на листе
# «Сводная» — plan_graph_export_summary_sheet._KIND_LABELS, и в карточках ФЭО
# — feo_card_drill._KIND_LABELS): те подписывают СУММУ по виду, не одну
# позицию — разный текст для разного места вывода, не вторая копия одной и
# той же подписи (ПРАВИЛО №6).
_ITEM_KIND_LABELS = {
    KIND_GOODS: "Товар", KIND_SERVICES: "Услуга",
    KIND_PAYROLL: "ФОТ", KIND_UNSPECIFIED: "Без типа",
}


def item_kind_label(item_type, feo_category_id, payroll_ids) -> str:
    """Подпись столбца «Товар / услуга» экспорта плана-графика (владелец
    08.10.2026) — ЕДИНСТВЕННАЯ точка вызова kind_of_by_category_id для этого
    столбца (app.services.item_type_split, ПРАВИЛО №6 — классификатор там,
    здесь только подпись). `payroll_ids` — любой контейнер с `in`
    (см. app.services.feo_payroll.payroll_category_ids)."""
    return _ITEM_KIND_LABELS[kind_of_by_category_id(item_type, feo_category_id, payroll_ids)]

# статусы: plan_schedule, work_in_progress → «Запланировано»;
#          contracted → «Договор»; ordered → «Заказано»;
#          delivered → «Поставлено»; paid → «Оплачено»
_STATUS_HUMAN = {
    "wishes": "Запланировано", "plan_schedule": "Запланировано",
    "work_in_progress": "Запланировано",
    "contracted": "Договор", "ordered": "Заказано",
    "delivered": "Поставлено", "paid": "Оплачено",
}


def _act_number(acc_number, acc_docs) -> str:
    if acc_number:
        return str(acc_number)
    if isinstance(acc_docs, list) and acc_docs:
        first = acc_docs[0]
        if isinstance(first, dict) and first.get("number"):
            return str(first["number"])
    return ""


async def gather_live_plan_graph_data(db: AsyncSession, subsidy_id: int) -> dict:
    """Собирает все данные, нужные для построения живой книги плана-графика.

    Возвращает dict:
      cats, item_ids, cat_ids, items_by_cat, used_map, contractor_map,
      purchased_by_item, cat_status_map, cat_monthly_map, cat_contractor_map,
      purchased_by_cat, unlinked_purchases.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase import Purchase as _P
    from app.models.contractor import Contractor as _C

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
        .order_by(FeoCategory.level, FeoCategory.id)
    )).scalars().all()

    feo_items = (await db.execute(
        select(_FPI)
        .join(FeoCategory, _FPI.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(_FPI.is_active == True)
        .order_by(_FPI.id)
    )).scalars().all()

    item_ids = [i.id for i in feo_items]
    # «Товар / услуга» (владелец 08.10.2026, замечание 1) — payroll-категории
    # субсидии (ПРАВИЛО №6: единственный резолвер — app.services.feo_payroll
    # .payroll_category_ids) и {item_id: feo_category_id} плановых позиций,
    # нужны ниже для item_kind_label (и покупок, привязанных к позиции, и
    # самих позиций).
    payroll_ids = await payroll_category_ids(db, [subsidy_id])
    item_cat_map = {i.id: i.feo_category_id for i in feo_items}
    item_kind_map = {
        i.id: item_kind_label(i.item_type, i.feo_category_id, payroll_ids)
        for i in feo_items
    }
    # «План (плановые позиции)» (владелец 09.10.2026, сверка на проде ФАДМ
    # 2026_2 id 89 — Σ «План» в выгрузке 15 883 686,50 против 15 880 300,00 у
    # дерева/subsidy_type_totals): дерево (feo_plan_tree._manual_plan_for) для
    # категории с plan_source='planned_items' (умолчание) считает план УЗЛА
    # как Σ КОНТРИБЬЮЦИЙ позиций (committed_amounts.planned_item_contributions
    # — замещение savings законтрактованной суммой, если количество набрано
    # полностью), а НЕ голую Σ FeoPlannedItem.amount; для 'manual_sum' —
    # дерево читает СЫРУЮ Σ amount (контрибьюция туда не подставляется,
    # владелец явно просил не трогать этот режим). Экспорт раньше всегда брал
    # item.amount — расходился с деревом ровно на величину замещённых savings.
    # ПРАВИЛО №6 — тот же резолвер, что дерево, не второй расчёт.
    _cat_plan_source = {c.id: (c.plan_source or "planned_items") for c in cats}
    _contributions = await planned_item_contributions(db, [c.id for c in cats])
    item_plan_map: dict[int, float] = {}
    item_plan_month_map: dict[int, str] = {}
    for i in feo_items:
        if _cat_plan_source.get(i.feo_category_id) == "manual_sum":
            item_plan_map[i.id] = float(i.amount or 0)
        else:
            _c = _contributions.get(i.id)
            item_plan_map[i.id] = _c["amount"] if _c is not None else float(i.amount or 0)
        item_plan_month_map[i.id] = item_planned_month(i)
    used_map: dict[int, float] = {}
    if item_ids:
        # Задача B (07.10.2026): join на Purchase + исключение 'cancelled' —
        # отменённая закупка не входит в факт/остаток/% исполнения позиции.
        used_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                func.coalesce(func.sum(_PI.total_price), 0).label("used"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .where(_P.status != "cancelled")
            .group_by(_PI.feo_planned_item_id)
        )).all()
        used_map = {r.feo_planned_item_id: float(r.used) for r in used_rows}

    # Status breakdown: sum(PurchaseItem.total_price) per (feo_planned_item_id, Purchase.status)
    status_sums_map: dict[int, dict[str, float]] = {}
    if item_ids:
        st_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                _P.status,
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .group_by(_PI.feo_planned_item_id, _P.status)
        )).all()
        for r in st_rows:
            status_sums_map.setdefault(r.feo_planned_item_id, {})[r.status] = float(r.s)

    contractor_map: dict[int, str] = {}
    if item_ids:
        c_rows = (await db.execute(
            select(_PI.feo_planned_item_id, _C.name.label("cname"))
            .join(_P, _PI.purchase_id == _P.id)
            .join(_C, _P.contractor_id == _C.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .distinct()
        )).all()
        for r in c_rows:
            if r.feo_planned_item_id not in contractor_map:
                contractor_map[r.feo_planned_item_id] = r.cname

    # Фактически закупленные позиции (PurchaseItem) по каждой плановой статье —
    # чтобы в выгрузке было видно ЧТО куплено и ПО КАКОЙ ЦЕНЕ, а не только сумма.
    purchased_by_item: dict[int, list] = {}
    if item_ids:
        pi_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                _PI.item_name,
                _PI.unit,
                _PI.quantity,
                _PI.unit_price,
                _PI.total_price,
                _PI.contractor_name,
                _P.id.label("purchase_id"),
                _P.status,
                _P.acceptance_doc_number,
                _P.acceptance_docs,
                # «Товар / услуга» (владелец 08.10.2026, замечание 1) —
                # ТОЛЬКО Purchase.item_type (товар/услуга/работа); НЕ
                # PurchaseItem.item_type — то поле хранит свободный «вид
                # товара» («Клей-карандаш…», см. app/models/purchase_item.py),
                # не классификатор товар/услуга (не второй механизм — тот же
                # источник, что у остальных строк этого модуля).
                _P.item_type,
            )
            .join(_P, _PI.purchase_id == _P.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .order_by(_PI.feo_planned_item_id, _PI.id)
        )).all()
        for r in pi_rows:
            purchased_by_item.setdefault(r.feo_planned_item_id, []).append({
                "name": r.item_name or "",
                "unit": r.unit or "",
                "qty": float(r.quantity or 0),
                "unit_price": float(r.unit_price or 0),
                "total": float(r.total_price or 0),
                "contractor": r.contractor_name or "",
                "raw_status": r.status or "",
                "status": _STATUS_HUMAN.get(r.status, r.status or ""),
                "purchase_id": r.purchase_id,
                "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
                "item_kind": item_kind_label(
                    r.item_type, item_cat_map.get(r.feo_planned_item_id), payroll_ids,
                ),
            })

    # FCAT: закупки часто привязаны к КАТЕГОРИИ (feo_category_id), а не к плановой
    # позиции. Агрегируем факт по категории — иначе колонки факта пустые.
    cat_ids = [c.id for c in cats]
    cat_status_map: dict[int, dict[str, float]] = {}
    cat_contractor_map: dict[int, str] = {}
    cat_monthly_map: dict[int, float] = {}  # факт по закупкам-регулярным (ежемес.) платежам
    purchased_by_cat: dict[int, list] = {}
    # Привязка к категории живёт на ТРЁХ уровнях: PurchaseItem.feo_category_id,
    # Purchase.feo_category_id (так работает вкладка «план vs факт») и через
    # плановую статью (feo_planned_item_id → её категория). Берём coalesce,
    # иначе часть факта выпадает из роллапа.
    _ecat = func.coalesce(_PI.feo_category_id, _P.feo_category_id, _FPI.feo_category_id)
    if cat_ids:
        cst_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                _P.status,
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .group_by(_ecat, _P.status)
        )).all()
        for r in cst_rows:
            cat_status_map.setdefault(r.ecat, {})[r.status] = float(r.s)

        mth_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                func.coalesce(func.sum(_PI.total_price), 0).label("s"),
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .where(_P.is_monthly_payment.is_(True))
            .group_by(_ecat)
        )).all()
        for r in mth_rows:
            cat_monthly_map[r.ecat] = float(r.s)

        cpi_rows = (await db.execute(
            select(
                _ecat.label("ecat"),
                _PI.feo_planned_item_id,
                _PI.item_name,
                _PI.unit,
                _PI.quantity,
                _PI.unit_price,
                _PI.total_price,
                func.coalesce(_PI.contractor_name, _C.name).label("contractor_name"),
                _P.id.label("purchase_id"),
                _P.status,
                _P.is_monthly_payment,
                _P.monthly_payment_count,
                _P.monthly_payment_amount,
                _P.acceptance_doc_number,
                _P.acceptance_docs,
                # Валидность привязки к плановой позиции (владелец 09.10.2026,
                # прод ФАДМ 2026_2 — закупки 909/975/2044/3218 пропадали):
                # feo_planned_item_id указывает на НЕАКТИВНУЮ/чужой-категории
                # позицию — такая ссылка не "валидна", строка не попадает в
                # purchased_by_item (там фильтр по активным item_ids) и раньше
                # молча выпадала и из purchased_by_cat (фильтр был только
                # "feo_planned_item_id IS NULL"). Та же проверка валидности
                # ссылки, что в app.services.committed_amounts (_valid_link).
                _FPI.id.label("fpi_id"),
                _FPI.is_active.label("fpi_is_active"),
                _FPI.feo_category_id.label("fpi_cat_id"),
                # «Товар / услуга» (владелец 08.10.2026, замечание 1) — та же
                # оговорка, что у pi_rows выше: Purchase.item_type, не
                # PurchaseItem.item_type.
                _P.item_type,
            )
            .join(_P, _PI.purchase_id == _P.id)
            .outerjoin(_C, _P.contractor_id == _C.id)
            .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
            .where(_ecat.in_(cat_ids))
            .order_by(_ecat, _PI.id)
        )).all()
        for r in cpi_rows:
            if r.contractor_name and r.ecat not in cat_contractor_map:
                cat_contractor_map[r.ecat] = r.contractor_name
            _valid_link = (
                r.feo_planned_item_id is not None
                and r.fpi_id is not None
                and bool(r.fpi_is_active)
                and r.fpi_cat_id == r.ecat
            )
            # Детализацию по категории показываем для позиций БЕЗ ВАЛИДНОЙ
            # привязки к плановой статье (нет ссылки ВООБЩЕ, ИЛИ ссылка на
            # неактивную/чужую-категории позицию) — иначе такая позиция не
            # попадёт никуда (не покрыта и purchased_by_item).
            if not _valid_link:
                purchased_by_cat.setdefault(r.ecat, []).append({
                    "name": r.item_name or "",
                    "unit": r.unit or "",
                    "qty": float(r.quantity or 0),
                    "unit_price": float(r.unit_price or 0),
                    "total": float(r.total_price or 0),
                    "contractor": r.contractor_name or "",
                    "raw_status": r.status or "",
                    "status": _STATUS_HUMAN.get(r.status, r.status or ""),
                    "purchase_id": r.purchase_id,
                    "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
                    "is_monthly": bool(r.is_monthly_payment),
                    "monthly_count": r.monthly_payment_count,
                    "monthly_amount": float(r.monthly_payment_amount or 0),
                    "item_kind": item_kind_label(r.item_type, r.ecat, payroll_ids),
                })

    # ── Закупки БЕЗ позиций: факт живёт на самой закупке (item_name/суммы) ──
    # Иначе такие закупки полностью выпадают из выгрузки.
    #
    # ИСКЛЮЧЕНИЕ (владелец 08.10.2026, прод ФАДМ 2026_2): ГОЛОВА рамочного
    # договора (purchase_contract_type начинается с 'framework', parent_
    # purchase_id IS NULL) — сама договор, а не закупка-товар; у неё нет
    # PurchaseItem, поэтому без этого фильтра она попадала в «план закупок»
    # строкой с нулями («ПАО РОСТЕЛЕКОМ — рамочный договор (закупка 1)» и
    # т.п.). Реальные деньги несут её заказы (parent_purchase_id = голова,
    # есть собственные позиции/факт) — они продолжают попадать в выгрузку как
    # обычно. Тот же критерий рамочности, что в «Реестре договоров»
    # (plan_graph_export_contracts_sheet.py) и в app.services.committed_amounts
    # .is_framework_purchase_expr — не второй признак.
    from app.services.committed_amounts import is_framework_purchase_expr as _is_fw_expr
    from sqlalchemy import and_ as _sqland, not_ as _sqlnot

    unlinked_purchases: list[dict] = []  # секция «без категории ФЭО»
    pl_rows = (await db.execute(
        select(
            _P.id.label("purchase_id"), _P.feo_category_id, _P.item_name,
            _P.subject, _P.status,
            _P.planned_quantity, _P.unit, _P.planned_unit_price,
            _P.planned_total_price, _P.final_total_amount,
            _P.acceptance_doc_number, _P.acceptance_docs,
            _P.is_monthly_payment, _P.monthly_payment_count, _P.monthly_payment_amount,
            _P.item_type, _P.is_likely_needed,
            _C.name.label("contractor_name"),
        )
        .outerjoin(_C, _P.contractor_id == _C.id)
        .where(or_(
            _P.feo_category_id.in_(cat_ids or [-1]),
            _P.subsidy_id == subsidy_id,
        ))
        .where(~select(_PI.id).where(_PI.purchase_id == _P.id).exists())
        .where(_sqlnot(_sqland(_is_fw_expr(_P), _P.parent_purchase_id.is_(None))))
        .order_by(_P.id)
    )).all()
    _cat_id_set = set(cat_ids)
    # ПРАВИЛО №6 (2026-09-07, волна 4b-2c): раньше `final_total_amount or
    # planned_total_price or 0` — truthy-баг (0 в final_total_amount проваливался
    # в план) плюс final_total_amount — легаси-скаляр мимо единого источника
    # (не участвует в цепочке purchase_amounts вообще). Заменено на bulk
    # load_purchase_amounts().effective — та же цепочка-по-стадии, что и везде:
    # поставлено/оплачено берёт факт (JSONB acceptance_docs), до договора — план.
    _amounts_by_pid = await load_purchase_amounts(db, [r.purchase_id for r in pl_rows])
    for r in pl_rows:
        _pa = _amounts_by_pid.get(r.purchase_id)
        amount = float(_pa.effective) if _pa and _pa.effective is not None else 0.0
        qty = float(r.planned_quantity or 0)
        d = {
            "name": (r.item_name or r.subject or f"Закупка №{r.purchase_id}"),
            "unit": r.unit or "",
            "qty": qty,
            "unit_price": float(r.planned_unit_price or 0) or (amount / qty if qty else amount),
            "total": amount,
            "contractor": r.contractor_name or "",
            "raw_status": r.status or "",
            "status": _STATUS_HUMAN.get(r.status, r.status or ""),
            "purchase_id": r.purchase_id,
            "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
            "has_act": bool(r.acceptance_doc_number) or bool(
                isinstance(r.acceptance_docs, list) and r.acceptance_docs),
            "is_monthly": bool(r.is_monthly_payment),
            "monthly_count": r.monthly_payment_count,
            "monthly_amount": float(r.monthly_payment_amount or 0),
            "item_type": (r.item_type or "").strip().lower(),
            "is_likely_needed": bool(r.is_likely_needed),
            "item_kind": item_kind_label(r.item_type, r.feo_category_id, payroll_ids),
        }
        if r.feo_category_id in _cat_id_set:
            purchased_by_cat.setdefault(r.feo_category_id, []).append(d)
            if amount:
                m = cat_status_map.setdefault(r.feo_category_id, {})
                st_key = r.status or ""
                m[st_key] = m.get(st_key, 0.0) + amount
                if r.is_monthly_payment:
                    cat_monthly_map[r.feo_category_id] = \
                        cat_monthly_map.get(r.feo_category_id, 0.0) + amount
        else:
            unlinked_purchases.append(d)

    # ── Позиции закупок, привязанных к субсидии ТОЛЬКО через subsidy_id ──────
    # (ни у закупки, ни у позиций нет категории/плановой статьи)
    _ecat_u = func.coalesce(_PI.feo_category_id, _P.feo_category_id, _FPI.feo_category_id)
    upi_rows = (await db.execute(
        select(
            _PI.item_name, _PI.unit, _PI.quantity, _PI.unit_price, _PI.total_price,
            func.coalesce(_PI.contractor_name, _C.name).label("contractor_name"),
            func.coalesce(_PI.item_type, _P.item_type).label("item_type"),
            # «Товар / услуга» (владелец 08.10.2026, замечание 1) — отдельно
            # от "item_type" выше: тот коалесс исторически предпочитает
            # PurchaseItem.item_type (свободный «вид товара», не классификатор
            # товар/услуга, см. pi_rows выше) — для item_kind нужен ТОЛЬКО
            # Purchase.item_type.
            _P.item_type.label("p_item_type"),
            _P.id.label("purchase_id"), _P.status,
            _P.is_monthly_payment, _P.monthly_payment_count, _P.monthly_payment_amount,
            _P.acceptance_doc_number, _P.acceptance_docs, _P.is_likely_needed,
        )
        .join(_P, _PI.purchase_id == _P.id)
        .outerjoin(_C, _P.contractor_id == _C.id)
        .outerjoin(_FPI, _PI.feo_planned_item_id == _FPI.id)
        .where(_P.subsidy_id == subsidy_id)
        .where(_ecat_u.is_(None))
        .order_by(_P.id, _PI.id)
    )).all()
    for r in upi_rows:
        unlinked_purchases.append({
            "name": r.item_name or "",
            "unit": r.unit or "",
            "qty": float(r.quantity or 0),
            "unit_price": float(r.unit_price or 0),
            "total": float(r.total_price or 0),
            "contractor": r.contractor_name or "",
            "raw_status": r.status or "",
            "status": _STATUS_HUMAN.get(r.status, r.status or ""),
            "purchase_id": r.purchase_id,
            "act_number": _act_number(r.acceptance_doc_number, r.acceptance_docs),
            "is_monthly": bool(r.is_monthly_payment),
            "monthly_count": r.monthly_payment_count,
            "monthly_amount": float(r.monthly_payment_amount or 0),
            # Нет категории ФЭО вовсе (секция «без категории») — payroll
            # неприменим, item_kind_label(None, ...) корректно деградирует к
            # kind_of(p_item_type).
            "item_kind": item_kind_label(r.p_item_type, None, payroll_ids),
        })

    items_by_cat: dict[int, list] = {}
    for item in feo_items:
        items_by_cat.setdefault(item.feo_category_id, []).append(item)

    # ── Группа «Договор и оплата» (владелец 07.10.2026) ──────────────────────
    # Все purchase_id, встреченные в под-строках фактических позиций — ОДИН
    # запрос Purchase по всем сразу (без N+1), + общий ctx экспорта закупок
    # (purchase_export_ctx), чтобы значения новых столбцов читались через
    # get_cell_value (ПРАВИЛО №6), а не вторым механизмом.
    _sub_row_purchase_ids: set = set()
    for _lst in purchased_by_item.values():
        _sub_row_purchase_ids.update(d["purchase_id"] for d in _lst if d.get("purchase_id"))
    for _lst in purchased_by_cat.values():
        _sub_row_purchase_ids.update(d["purchase_id"] for d in _lst if d.get("purchase_id"))
    _sub_row_purchase_ids.update(d["purchase_id"] for d in unlinked_purchases if d.get("purchase_id"))

    purchase_rows_by_id: dict[int, Purchase] = {}
    if _sub_row_purchase_ids:
        _p_rows = (await db.execute(
            select(Purchase).where(Purchase.id.in_(_sub_row_purchase_ids))
        )).scalars().all()
        purchase_rows_by_id = {p.id: p for p in _p_rows}
    purchase_export_ctx = await build_purchase_export_ctx(db, list(purchase_rows_by_id.values()))
    # «Остаток по договору» (владелец 08.10.2026, часть C) — ЕДИНЫЙ источник,
    # не второй расчёт (ПРАВИЛО №6): plan_graph_export_rows.collect_plan_graph_rows
    # читает contract_balances_by_purchase, сама его не считает.
    _cb = await contract_balances(db, subsidy_id)
    contract_balances_by_purchase = _cb["by_purchase"]
    contract_balance_groups = _cb["groups"]

    return {
        "cats": list(cats),
        "item_ids": item_ids,
        "cat_ids": cat_ids,
        "items_by_cat": items_by_cat,
        "used_map": used_map,
        "contractor_map": contractor_map,
        "status_sums_map": status_sums_map,
        # «Товар / услуга» плановых позиций (владелец 08.10.2026, замечание 1)
        # — {feo_planned_item_id: "Товар"/"Услуга"/"ФОТ"/"Без типа"},
        # прочитано xlsx/flat_sheet builder'ами (ПРАВИЛО №6, один расчёт).
        "item_kind_map": item_kind_map,
        # «План (плановые позиции)» (владелец 09.10.2026) — {item_id: её
        # вклад в план, см. комментарий выше — ТО ЖЕ число, что суммирует
        # дерево в своём "plan_manual"/items_total для этого узла}.
        "item_plan_map": item_plan_map,
        # «План. месяц платежа» позиций БЕЗ закупок (владелец 09.10.2026,
        # п.2) — {item_id: "YYYY-MM-DD" | ""}, см. item_planned_month().
        "item_plan_month_map": item_plan_month_map,
        "purchased_by_item": purchased_by_item,
        "cat_status_map": cat_status_map,
        "cat_monthly_map": cat_monthly_map,
        "cat_contractor_map": cat_contractor_map,
        "purchased_by_cat": purchased_by_cat,
        "unlinked_purchases": unlinked_purchases,
        "purchase_rows_by_id": purchase_rows_by_id,
        "contract_balances_by_purchase": contract_balances_by_purchase,
        "contract_balance_groups": contract_balance_groups,
        "purchase_export_ctx": purchase_export_ctx,
    }
