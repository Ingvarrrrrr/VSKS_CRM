"""metric_drill_rows.py — построчные данные для GET /api/dashboard/metric-drill
(app/routers/dashboard_metric_drill.py, план abstract-noodling-pelican.md,
п.4 техчасти, 15.10.2026): по клику на строку карточки субсидии — список, из
которого сложилось число.

ПРАВИЛО №6 — ни одна функция здесь не считает сумму заново: каждая метрика —
тонкая обёртка вокруг уже существующего источника (см. докстринг у вызова),
`card_total` — ТОТ ЖЕ агрегат, что показывает карточка SubsidyMoneyCards.vue/
SubsidyKpiCards.vue. Σ rows["amount"] ОБЯЗАНА совпасть с card_total до копейки
(test_metric_drill.py) — если агрегат раньше считался SQL-ем напрямую, здесь
агрегат ПЕРЕВЕДЁН на построчную функцию (см. feo_plan_payments.
paid_consumption_rows, subsidy_paid_breakdown.paid_breakdown_rows), вторая
формула не вводится.

Метрики (см. METRICS):
  monthly_future                — дерево «договор → месяцы» карточки
                                   «Заключено» (monthly_future_payments.py).
  monthly_future_not_started    — строка 4 карточки «Можно перераспределить»
                                   («ещё уйдёт помесячно, не начато»).
  not_committed_nice/_likely    — «хотелось бы»/«скорее всего» без договора.
  paid_declared/paid_confirmed  — карточка «Оплачено».
  balance_marked/balance_confirmed — «Остаток субсидии»: Бюджет ФЭО минус
                                   оплаченные закупки (тот же источник, что
                                   корни дерева ФЭО).
  economy                       — «Экономия по закупкам».
"""
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.feo_plan_payments import paid_consumption_rows
from app.services.monthly_future_payments import (
    framework_order_month_rows,
    monthly_future_rows as _monthly_future_rows,
    monthly_future_totals_by_subsidy,
)
from app.services.plan_need_level import is_reserve_need_level
from app.services.purchase_drill_text import purchase_drill_texts
from app.services.purchase_economy import purchase_economy_bulk
from app.services.redistributable_raw import not_committed_raw_rows
from app.services.subsidy_money_summary import subsidy_money_summary
from app.services.subsidy_paid_breakdown import paid_breakdown_by_subsidy, paid_breakdown_rows

METRICS: tuple = (
    "monthly_future", "monthly_future_not_started",
    "not_committed_nice", "not_committed_likely",
    "paid_declared", "paid_confirmed",
    "balance_marked", "balance_confirmed",
    "economy",
)


# ---------------------------------------------------------------------------
# Общие мелочи (без побочных эффектов — Правило №5 не требует отдельного
# модуля ради нескольких строк батч-подгрузки, используются только здесь).
# ---------------------------------------------------------------------------

async def _purchases_map(db: AsyncSession, purchase_ids) -> dict[int, Purchase]:
    ids = {pid for pid in purchase_ids if pid is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Purchase).where(Purchase.id.in_(ids)))).scalars().all()
    return {p.id: p for p in rows}


async def _contractor_names(db: AsyncSession, contractor_ids) -> dict[int, str]:
    ids = {cid for cid in contractor_ids if cid is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Contractor.id, Contractor.name).where(Contractor.id.in_(ids)))).all()
    return {r.id: r.name for r in rows}


async def _subsidy_names(db: AsyncSession, subsidy_ids) -> dict[int, str]:
    if not subsidy_ids:
        return {}
    rows = (await db.execute(select(Subsidy.id, Subsidy.name).where(Subsidy.id.in_(subsidy_ids)))).all()
    return {r.id: r.name for r in rows}


def _category_path_str(cat_id: Optional[int], cats: dict[int, dict]) -> str:
    """'Направление › Тип расходов › Позиция' — путь от корня до cat_id
    включительно, по parent_id. Та же схема построения пути, что и в
    redistributable_raw._category_path/feo_card_drill._category_path
    (ПРАВИЛО №5/№6: путь строится по дереву категорий данной субсидии, не
    вторая формула категории — только локальный обход уже загруженного
    словаря cats)."""
    if cat_id is None or cat_id not in cats:
        return ""
    names: list[str] = []
    seen: set = set()
    cur = cat_id
    while cur is not None and cur in cats and cur not in seen:
        seen.add(cur)
        names.append(cats[cur]["name"] or "")
        cur = cats[cur]["parent_id"]
    return " › ".join(reversed(names))


async def _purchase_category_paths(db: AsyncSession, purchase_ids) -> dict[int, str]:
    """{purchase_id: "Направление › ... › Статья"} — дефект MetricDrillDialog.vue
    (план owner 21.10.2026, часть 0б): колонка «Направление ФЭО» была пустой
    для закупок, у которых статья указана на САМОЙ закупке (Purchase.
    feo_category_id), а не у позиции — так у закупок ФОТ ХРО_2026 (ЗП/
    Отчисления/Командировочные, item_type=NULL, своей feo_category_id у
    позиции нет). Фолбэк для эффективной категории закупки: статья первой
    позиции с заполненной feo_category_id → статья плановой позиции этой
    строки → статья самой закупки (Purchase.feo_category_id)."""
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    purchase_ids = [pid for pid in dict.fromkeys(purchase_ids) if pid is not None]
    if not purchase_ids:
        return {}

    purchases = (await db.execute(
        select(Purchase.id, Purchase.subsidy_id, Purchase.feo_category_id)
        .where(Purchase.id.in_(purchase_ids))
    )).all()
    subsidy_of = {r.id: r.subsidy_id for r in purchases}
    purchase_cat = {r.id: r.feo_category_id for r in purchases}

    item_rows = (await db.execute(
        select(
            PurchaseItem.purchase_id, PurchaseItem.id, PurchaseItem.feo_category_id,
            FeoPlannedItem.feo_category_id.label("plan_category_id"),
        )
        .outerjoin(FeoPlannedItem, PurchaseItem.feo_planned_item_id == FeoPlannedItem.id)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .order_by(PurchaseItem.id)
    )).all()

    effective_cat: dict[int, int] = {}
    for r in item_rows:
        if r.purchase_id in effective_cat:
            continue
        cid = r.feo_category_id or r.plan_category_id
        if cid is not None:
            effective_cat[r.purchase_id] = cid
    for pid in purchase_ids:
        if pid not in effective_cat and purchase_cat.get(pid) is not None:
            effective_cat[pid] = purchase_cat[pid]

    subsidy_ids = {sid for sid in subsidy_of.values() if sid is not None}
    cats: dict[int, dict] = {}
    if subsidy_ids:
        cat_rows = (await db.execute(
            select(FeoCategory.id, FeoCategory.parent_id, FeoCategory.name)
            .where(FeoCategory.subsidy_id.in_(subsidy_ids))
        )).all()
        cats = {r.id: {"parent_id": r.parent_id, "name": r.name} for r in cat_rows}

    return {pid: _category_path_str(effective_cat.get(pid), cats) for pid in purchase_ids}


def _reconcile_rows(raw: list[Decimal], target: Decimal) -> list[Decimal]:
    """Округление списка сумм построчно с подгонкой по модулю наибольшей
    строки к `target` — тот же приём, что dashboard_type_split.reconcile_split,
    применённый к произвольному числу строк (не фиксированным 3 товар/услуга/
    без типа) — используется, когда строки режутся по kind (paid_declared/
    paid_confirmed), чтобы Σ строк осталась РОВНО card_total после округления
    копеек каждой строки."""
    if not raw:
        return []
    cents = Decimal("0.01")
    rounded = [r.quantize(cents) for r in raw]
    diff = target.quantize(cents) - sum(rounded)
    if diff != 0:
        idx = max(range(len(raw)), key=lambda i: abs(raw[i]))
        rounded[idx] += diff
    return rounded


async def _purchase_row(db_texts: dict, purchases: dict, contractor_names: dict,
                         subsidy_names: dict, purchase_id: int, amount: float,
                         category_paths: Optional[dict] = None) -> dict:
    p = purchases.get(purchase_id)
    text = db_texts.get(purchase_id, {})
    # Фолбэк «Предмет» (владелец 21.10.2026, ХРО_2026: закупки импорта факта
    # ФОТ — Purchase.subject/item_name пустые, но у позиции есть название —
    # «ЗП»/«Отчисления»/«Командировочные») — items_text уже собирает
    # PurchaseItem.item_name (purchase_drill_text.purchase_drill_texts,
    # ПРАВИЛО №6, не вторая сборка названий позиций).
    _subject = (p.subject or p.item_name) if p else None
    if not _subject:
        _subject = text.get("items_text") or None
    return {
        "row_type": "purchase",
        "purchase_id": purchase_id,
        "purchase_number": (p.purchase_number if p and p.purchase_number is not None else purchase_id),
        "subject": _subject,
        "supplier": text.get("supplier") or (contractor_names.get(p.contractor_id) if p and p.contractor_id else None),
        "items_text": text.get("items_text", ""),
        "status": p.status if p else None,
        "subsidy_id": p.subsidy_id if p else None,
        "subsidy_name": subsidy_names.get(p.subsidy_id) if p else None,
        "category_path": (category_paths or {}).get(purchase_id, ""),
        "amount": amount,
    }


# ---------------------------------------------------------------------------
# monthly_future — дерево «договор → месяцы» (карточка «Заключено»).
# ---------------------------------------------------------------------------

async def monthly_future_drill(db: AsyncSession, subsidy_ids: list[int], today: Optional[_date] = None) -> dict:
    rows = await _monthly_future_rows(db, subsidy_ids, today=today)
    totals = await monthly_future_totals_by_subsidy(db, subsidy_ids, today=today)
    card_total = sum(d["total"] for d in totals.values())

    purchase_ids = {r["purchase_id"] for r in rows if r.get("purchase_id") is not None}
    purchase_ids |= {r["parent_purchase_id"] for r in rows if r.get("parent_purchase_id") is not None}
    purchases = await _purchases_map(db, purchase_ids)
    contractor_names = await _contractor_names(db, (p.contractor_id for p in purchases.values()))
    subsidy_names = await _subsidy_names(db, subsidy_ids)

    rows_out = []
    for r in rows:
        contract = purchases.get(r.get("parent_purchase_id")) if r.get("parent_purchase_id") else None
        purchase = purchases.get(r["purchase_id"])
        contractor = None
        if contract and contract.contractor_id:
            contractor = contractor_names.get(contract.contractor_id)
        elif purchase and purchase.contractor_id:
            contractor = contractor_names.get(purchase.contractor_id)
        sid = r.get("subsidy_id") or (purchase.subsidy_id if purchase else None)
        rows_out.append({
            "row_type": "month",
            "contract_id": r.get("contract_id"),
            "contract_number": contract.purchase_number if contract else None,
            "contractor": contractor,
            "parent_purchase_id": r.get("parent_purchase_id"),
            "parent_subject": (contract.subject or contract.item_name) if contract else None,
            "purchase_id": r["purchase_id"],
            "purchase_number": purchase.purchase_number if purchase else None,
            "month": r["month"].isoformat() if r.get("month") else None,
            "amount": r["amount"],
            "source": r["source"],
            "subsidy_id": sid,
            "subsidy_name": subsidy_names.get(sid),
        })
    total = sum(r["amount"] for r in rows_out)
    return {"metric": "monthly_future", "total": total, "card_total": card_total, "rows": rows_out}


# ---------------------------------------------------------------------------
# monthly_future_not_started — строка 4 карточки «Можно перераспределить».
# ---------------------------------------------------------------------------

async def monthly_future_not_started_drill(db: AsyncSession, subsidy_ids: list[int],
                                            today: Optional[_date] = None) -> dict:
    raw_rows_map = await not_committed_raw_rows(db, subsidy_ids, today=today)
    flagged = [
        {**row, "subsidy_id": sid}
        for sid, item_rows in raw_rows_map.items() for row in item_rows
        if row["monthly_future_not_started"]
    ]
    summary = await subsidy_money_summary(db, subsidy_ids)
    card_total = sum(float(summary.get(sid, {}).get("monthly_future_not_started", 0.0) or 0.0) for sid in subsidy_ids)

    # Будущие заказы рамочных договоров — тот же источник, которым
    # not_committed_raw_rows уже проставила флаг monthly_future_not_started
    # (см. её докстринг) — здесь только собираем контекст (договор/месяц/
    # сумма заказа) для отображения, не вторая формула флага.
    _today = today or _date.today()
    _cur_month = _date(_today.year, _today.month, 1)
    fw_rows = await framework_order_month_rows(db, subsidy_ids)
    future_fw = [r for r in fw_rows if r.get("month") is not None and r["month"] > _cur_month]
    future_purchase_ids = {r["purchase_id"] for r in future_fw}

    item_ids = [r["planned_item_id"] for r in flagged]
    purchases_by_item: dict[int, set] = {}
    if item_ids and future_purchase_ids:
        link_rows = (await db.execute(
            select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
            .where(PurchaseItem.purchase_id.in_(future_purchase_ids))
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        )).all()
        for lr in link_rows:
            purchases_by_item.setdefault(lr.feo_planned_item_id, set()).add(lr.purchase_id)

    fw_by_purchase: dict[int, list] = {}
    for r in future_fw:
        fw_by_purchase.setdefault(r["purchase_id"], []).append(r)

    purchase_ids_needed = {pid for pids in purchases_by_item.values() for pid in pids}
    purchase_ids_needed |= {
        r.get("parent_purchase_id") for lst in fw_by_purchase.values() for r in lst
        if r.get("parent_purchase_id") is not None
    }
    purchases = await _purchases_map(db, purchase_ids_needed)
    contractor_names = await _contractor_names(db, (p.contractor_id for p in purchases.values()))
    subsidy_names = await _subsidy_names(db, subsidy_ids)

    rows_out = []
    for row in flagged:
        pids = sorted(purchases_by_item.get(row["planned_item_id"], []))
        orders = []
        for pid in pids:
            purchase = purchases.get(pid)
            for fwr in fw_by_purchase.get(pid, []):
                contract = purchases.get(fwr.get("parent_purchase_id"))
                orders.append({
                    "purchase_id": pid,
                    "purchase_number": purchase.purchase_number if purchase else None,
                    "contract_id": fwr.get("parent_purchase_id"),
                    "contract_number": contract.purchase_number if contract else None,
                    "contractor": contractor_names.get(contract.contractor_id) if contract and contract.contractor_id else None,
                    "month": fwr["month"].isoformat() if fwr.get("month") else None,
                    "order_amount": fwr["amount"],
                })
        orders.sort(key=lambda o: o["month"] or "")
        first = orders[0] if orders else {}
        rows_out.append({
            "row_type": "planned_item",
            "planned_item_id": row["planned_item_id"],
            "name": row["name"],
            "category_path": row["category_path"],
            "feo_category_id": row.get("feo_category_id"),
            "subsidy_id": row["subsidy_id"],
            "subsidy_name": subsidy_names.get(row["subsidy_id"]),
            "amount": row["raw"],
            "contract_id": first.get("contract_id"),
            "contract_number": first.get("contract_number"),
            "contractor": first.get("contractor"),
            "parent_subject": None,
            "month": first.get("month"),
            "order_amount": first.get("order_amount"),
            "orders": orders,
        })
    total = sum(r["amount"] for r in rows_out)
    return {"metric": "monthly_future_not_started", "total": total, "card_total": card_total, "rows": rows_out}


# ---------------------------------------------------------------------------
# not_committed_nice / not_committed_likely — «хотелось бы»/«скорее всего».
# ---------------------------------------------------------------------------

async def not_committed_level_drill(db: AsyncSession, subsidy_ids: list[int], metric: str,
                                     today: Optional[_date] = None) -> dict:
    is_nice_metric = metric == "not_committed_nice"
    raw_rows_map = await not_committed_raw_rows(db, subsidy_ids, today=today)
    # 🟡 "not_committed_nice" собирает И 'nice_to_have', И 'unforeseen' (тот
    # же резервный бакет — is_reserve_need_level, ПРАВИЛО №6); "not_committed_likely" —
    # всё остальное (включая отсутствие валидной привязки, see docstring выше).
    rows = [
        {**row, "subsidy_id": sid}
        for sid, item_rows in raw_rows_map.items() for row in item_rows
        if not row["monthly_future_not_started"]
        and (is_reserve_need_level(row["need_level"]) if is_nice_metric else not is_reserve_need_level(row["need_level"]))
    ]
    summary = await subsidy_money_summary(db, subsidy_ids)
    field = "not_committed_nice" if metric == "not_committed_nice" else "not_committed_likely"
    card_total = sum(float(summary.get(sid, {}).get(field, 0.0) or 0.0) for sid in subsidy_ids)
    subsidy_names = await _subsidy_names(db, subsidy_ids)

    rows_out = [{
        "row_type": "planned_item",
        "planned_item_id": r["planned_item_id"],
        "name": r["name"],
        "category_path": r["category_path"],
        "feo_category_id": r.get("feo_category_id"),
        "subsidy_id": r["subsidy_id"],
        "subsidy_name": subsidy_names.get(r["subsidy_id"]),
        "contribution": r["contribution"],
        "committed": r["committed"],
        "amount": r["raw"],
    } for r in rows]
    total = sum(r["amount"] for r in rows_out)
    return {"metric": metric, "total": total, "card_total": card_total, "rows": rows_out}


# ---------------------------------------------------------------------------
# paid_declared / paid_confirmed — карточка «Оплачено».
# ---------------------------------------------------------------------------

async def paid_drill(db: AsyncSession, subsidy_ids: list[int], metric: str, kind: Optional[str] = None) -> dict:
    field = "declared" if metric == "paid_declared" else "confirmed"
    rows = await paid_breakdown_rows(db, subsidy_ids)
    breakdown = await paid_breakdown_by_subsidy(db, subsidy_ids)
    by_kind_field = "declared_by_kind" if metric == "paid_declared" else "confirmed_by_kind"

    purchases = await _purchases_map(db, (r["purchase_id"] for r in rows))
    contractor_names = await _contractor_names(db, (p.contractor_id for p in purchases.values()))
    subsidy_names = await _subsidy_names(db, subsidy_ids)
    texts = await purchase_drill_texts(db, (r["purchase_id"] for r in rows))
    category_paths = await _purchase_category_paths(db, (r["purchase_id"] for r in rows))

    if kind is None:
        card_total = sum(float(breakdown.get(sid, {}).get(field, 0.0) or 0.0) for sid in subsidy_ids)
        rows_out = [
            await _purchase_row(texts, purchases, contractor_names, subsidy_names, r["purchase_id"], float(r[field]), category_paths)
            for r in rows
        ]
    else:
        from app.services.item_type_split import KIND_PAYROLL, purchase_type_shares
        card_total = sum(float((breakdown.get(sid, {}).get(by_kind_field) or {}).get(kind, 0.0)) for sid in subsidy_ids)
        # Группируем «сырые» (нераскруглённые) суммы по субсидии, затем
        # подгоняем построчно к card_total той же субсидии (см. _reconcile_rows)
        # — так Σ строк остаётся РОВНО card_total, как и у реконсиляции по типу
        # на самой карточке (dashboard_type_split.reconcile_split). ФОТ (задача
        # владельца 21.10.2026, ХРО_2026) — закупка с r["is_payroll"]=True несёт
        # ВСЮ свою сумму в payroll (share=1), ноль в goods/services/unspecified
        # (тот же collapse, что и у карточки — см. subsidy_paid_breakdown.py).
        by_subsidy: dict[int, list[tuple[dict, Decimal]]] = {}
        for r in rows:
            if r.get("is_payroll"):
                share = Decimal(1) if kind == KIND_PAYROLL else Decimal(0)
            else:
                shares = purchase_type_shares(r["items"])
                share = {"goods": shares.goods, "services": shares.services, "unspecified": shares.unspecified}.get(kind)
            if share is None or share == 0:
                continue
            by_subsidy.setdefault(r["subsidy_id"], []).append((r, r[field] * share))
        rows_out = []
        for sid, entries in by_subsidy.items():
            target = Decimal(str((breakdown.get(sid, {}).get(by_kind_field) or {}).get(kind, 0.0)))
            rounded = _reconcile_rows([amt for _r, amt in entries], target)
            for (r, _amt), amt_rounded in zip(entries, rounded):
                if amt_rounded == 0:
                    continue
                rows_out.append(await _purchase_row(
                    texts, purchases, contractor_names, subsidy_names, r["purchase_id"], float(amt_rounded),
                    category_paths,
                ))
    total = sum(r["amount"] for r in rows_out)
    return {"metric": metric, "total": total, "card_total": card_total, "rows": rows_out}


# ---------------------------------------------------------------------------
# balance_marked / balance_confirmed — «Остаток субсидии».
# ---------------------------------------------------------------------------

async def balance_drill(db: AsyncSession, subsidy_ids: list[int], metric: str) -> dict:
    field = "paid_marked" if metric == "balance_marked" else "paid_confirmed"
    card_field = "balance_by_marks" if metric == "balance_marked" else "balance_by_statement"

    summary = await subsidy_money_summary(db, subsidy_ids)
    # Только субсидии с введённым ФЭО (budget_basis задан) — иначе card_field=None,
    # строки такой субсидии не держат инвариант Σ==card_total ни с чем (см.
    # докстринг subsidy_money_summary.feo_entered).
    entered_ids = [sid for sid in subsidy_ids if summary.get(sid, {}).get(card_field) is not None]
    card_total = sum(float(summary.get(sid, {}).get(card_field, 0.0) or 0.0) for sid in entered_ids)

    pay_rows = await paid_consumption_rows(db, entered_ids, exclude_planned_item_linked=False)
    by_purchase: dict[int, float] = {}
    purchase_subsidy: dict[int, int] = {}
    for r in pay_rows:
        by_purchase[r["purchase_id"]] = by_purchase.get(r["purchase_id"], 0.0) + r[field]
        purchase_subsidy[r["purchase_id"]] = r["subsidy_id"]

    purchases = await _purchases_map(db, by_purchase.keys())
    contractor_names = await _contractor_names(db, (p.contractor_id for p in purchases.values()))
    subsidy_names = await _subsidy_names(db, entered_ids)
    texts = await purchase_drill_texts(db, by_purchase.keys())
    category_paths = await _purchase_category_paths(db, by_purchase.keys())

    rows_out = []
    for sid in entered_ids:
        budget_basis = summary.get(sid, {}).get("budget_basis")
        if budget_basis is None:
            continue
        rows_out.append({
            "row_type": "budget",
            "purchase_id": None,
            "subject": "Бюджет ФЭО",
            "subsidy_id": sid,
            "subsidy_name": subsidy_names.get(sid),
            "amount": float(budget_basis),
        })
    for pid, amount in by_purchase.items():
        if abs(amount) < 0.005:
            continue
        sid = purchase_subsidy.get(pid)
        row = await _purchase_row(texts, purchases, contractor_names, subsidy_names, pid, -amount, category_paths)
        row["subsidy_id"] = sid
        row["subsidy_name"] = subsidy_names.get(sid)
        rows_out.append(row)

    total = sum(r["amount"] for r in rows_out)
    return {"metric": metric, "total": total, "card_total": card_total, "rows": rows_out}


# ---------------------------------------------------------------------------
# economy — «Экономия по закупкам».
# ---------------------------------------------------------------------------

async def economy_drill(db: AsyncSession, subsidy_ids: list[int]) -> dict:
    from app.services.purchase_economy import purchase_economy_by_subsidy

    p_rows = (await db.execute(
        select(Purchase.id, Purchase.subsidy_id).where(Purchase.subsidy_id.in_(subsidy_ids))
    )).all()
    sid_by_purchase = {r.id: r.subsidy_id for r in p_rows}

    econ_by_subsidy = await purchase_economy_by_subsidy(db, subsidy_ids)
    card_total = sum(float(d.get("economy_total") or 0.0) for d in econ_by_subsidy.values())

    econ = await purchase_economy_bulk(db, list(sid_by_purchase.keys())) if sid_by_purchase else {}
    purchases = await _purchases_map(db, sid_by_purchase.keys())
    contractor_names = await _contractor_names(db, (p.contractor_id for p in purchases.values()))
    subsidy_names = await _subsidy_names(db, subsidy_ids)
    measured_ids = [pid for pid, bucket in econ.items() if bucket.get("economy") is not None]
    texts = await purchase_drill_texts(db, measured_ids)
    category_paths = await _purchase_category_paths(db, measured_ids)

    rows_out = []
    for pid in measured_ids:
        bucket = econ[pid]
        row = await _purchase_row(texts, purchases, contractor_names, subsidy_names, pid, float(bucket["economy"]), category_paths)
        row["plan_amount"] = float(bucket["planned_sum"])
        row["contract_amount"] = float(bucket["fact_sum"])
        rows_out.append(row)

    total = sum(r["amount"] for r in rows_out)
    return {"metric": "economy", "total": total, "card_total": card_total, "rows": rows_out}
