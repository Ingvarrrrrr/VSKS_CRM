"""Сборка данных для живого (текущего) экспорта плана-графика субсидии.

Вынесено из app/routers/subsidy_plan_graph_export.py::export_plan_graph_excel
(Правило №5, рефакторинг 2026-09-08). Только запросы к БД и агрегация — без
какого-либо построения книги Excel (это app.services.plan_graph_export_xlsx).

ПРАВИЛО №6: эффективная сумма закупки без позиций (секция «без категории ФЭО»/
«itemless») читается ТОЛЬКО через app.services.purchase_amounts.load_purchase_amounts
— единая цепочка-по-стадии, используемая везде в проекте.
"""
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.services.purchase_amounts import load_purchase_amounts

# статусы: plan_schedule, work_in_progress → «Запланировано»;
#          contracted → «Договор»; ordered → «Заказано»;
#          delivered → «Поставлено»; paid → «Оплачено»
_STATUS_HUMAN = {
    "wishes": "Запланировано", "plan_schedule": "Запланировано",
    "work_in_progress": "Запланировано",
    "contracted": "Договор", "ordered": "Заказано",
    "delivered": "Поставлено", "paid": "Оплачено",
}
_PLANNED_STATUSES = ("wishes", "plan_schedule", "work_in_progress", "contracted", "ordered")


def _act_number(acc_number, acc_docs) -> str:
    if acc_number:
        return str(acc_number)
    if isinstance(acc_docs, list) and acc_docs:
        first = acc_docs[0]
        if isinstance(first, dict) and first.get("number"):
            return str(first["number"])
    return ""


def _empty_summary_buckets() -> dict:
    return {"paid": 0.0, "delivered": 0.0, "accepted_unpaid": 0.0,
            "planned": 0.0, "monthly": 0.0, "likely": 0.0, "total": 0.0}


async def gather_live_plan_graph_data(db: AsyncSession, subsidy_id: int) -> dict:
    """Собирает все данные, нужные для построения живой книги плана-графика.

    Возвращает dict:
      cats, item_ids, cat_ids, items_by_cat, used_map, contractor_map,
      purchased_by_item, cat_status_map, cat_monthly_map, cat_contractor_map,
      purchased_by_cat, unlinked_purchases, summary.
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
    used_map: dict[int, float] = {}
    if item_ids:
        used_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                func.coalesce(func.sum(_PI.total_price), 0).label("used"),
            )
            .where(_PI.feo_planned_item_id.in_(item_ids))
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
            # Детализацию по категории показываем только для позиций БЕЗ привязки к
            # плановой статье — иначе задвоится со строками под плановой позицией.
            if r.feo_planned_item_id is None:
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
                })

    # ── Закупки БЕЗ позиций: факт живёт на самой закупке (item_name/суммы) ──
    # Иначе такие закупки полностью выпадают из выгрузки.
    itemless_extra: list[dict] = []      # для «Сводной»
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
        }
        itemless_extra.append(d)
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
        })

    items_by_cat: dict[int, list] = {}
    for item in feo_items:
        items_by_cat.setdefault(item.feo_category_id, []).append(item)

    # Дерево (для будущего/альтернативного рендера через render_plan_graph_workbook)
    # — исторически строилось здесь и в текущем «живом» экспорте не используется
    # (см. app.services.plan_graph_export_xlsx, у него собственный traverse по
    # cats/cats_by_parent). Оставлено ради 1:1 сохранения побочных эффектов при
    # рефакторинге (Правило №5 2026-09-08) — не потребитель, вычисление без
    # побочных эффектов на БД, безопасно держать как есть.
    def _build_live_tree(all_cats, parent_id=None):
        nodes = []
        for c in all_cats:
            if c.parent_id == parent_id:
                cat_items = items_by_cat.get(c.id, [])
                children = _build_live_tree(all_cats, parent_id=c.id)
                node = {
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "children": children,
                    "_live_items": cat_items,
                    "_used_map": used_map,
                    "_contractor_map": contractor_map,
                }
                nodes.append(node)
        return nodes

    _build_live_tree(list(cats))  # см. комментарий выше — результат намеренно не используется

    # ── Лист «Сводная»: деньги по Товары/Услуги × корзины обязательств ────────
    summary = {"услуга": _empty_summary_buckets(), "товар": _empty_summary_buckets()}
    sum_rows = (await db.execute(
        select(
            func.coalesce(_PI.item_type, _P.item_type).label("item_type"),
            _PI.total_price,
            _P.status,
            _P.acceptance_doc_number,
            _P.acceptance_docs,
            _P.is_monthly_payment,
            _P.is_likely_needed,
        )
        .join(_P, _PI.purchase_id == _P.id)
        .where(or_(
            func.coalesce(_PI.feo_category_id, _P.feo_category_id).in_(cat_ids or [-1]),
            _PI.feo_planned_item_id.in_(item_ids or [-1]),
            _P.subsidy_id == subsidy_id,
        ))
    )).all()
    for r in sum_rows:
        key = "услуга" if (r.item_type or "").strip().lower() == "услуга" else "товар"
        b = summary[key]
        amt = float(r.total_price or 0)
        st = r.status or ""
        b["total"] += amt
        if st == "paid":
            b["paid"] += amt
        if st == "delivered":
            b["delivered"] += amt
        has_act = bool(r.acceptance_doc_number) or bool(
            isinstance(r.acceptance_docs, list) and r.acceptance_docs)
        if has_act and st != "paid":
            b["accepted_unpaid"] += amt
        if st in _PLANNED_STATUSES:
            b["planned"] += amt
        if r.is_monthly_payment:
            b["monthly"] += amt
        if r.is_likely_needed:
            b["likely"] += amt

    # Закупки без позиций — их суммы живут на самой закупке
    for d in itemless_extra:
        key = "услуга" if d["item_type"] == "услуга" else "товар"
        b = summary[key]
        amt = d["total"]
        st = d["raw_status"]
        b["total"] += amt
        if st == "paid":
            b["paid"] += amt
        if st == "delivered":
            b["delivered"] += amt
        if d["has_act"] and st != "paid":
            b["accepted_unpaid"] += amt
        if st in _PLANNED_STATUSES:
            b["planned"] += amt
        if d["is_monthly"]:
            b["monthly"] += amt
        if d["is_likely_needed"]:
            b["likely"] += amt

    return {
        "cats": list(cats),
        "item_ids": item_ids,
        "cat_ids": cat_ids,
        "items_by_cat": items_by_cat,
        "used_map": used_map,
        "contractor_map": contractor_map,
        "status_sums_map": status_sums_map,
        "purchased_by_item": purchased_by_item,
        "cat_status_map": cat_status_map,
        "cat_monthly_map": cat_monthly_map,
        "cat_contractor_map": cat_contractor_map,
        "purchased_by_cat": purchased_by_cat,
        "unlinked_purchases": unlinked_purchases,
        "summary": summary,
    }
