"""plan_graph_export_contracts_data.py — сбор данных для листа «Реестр
договоров» (вынесено из plan_graph_export_contracts_sheet.py 09.10.2026,
ПРАВИЛО №5 — файл-рендерер разросся до 606 строк, сбор данных и запись листа
теперь живут раздельно; plan_graph_export_contracts_sheet.py импортирует
`gather_contracts_sheet_data` отсюда и реэкспортирует под тем же именем —
роутер (app.routers.subsidy_plan_graph_export) и существующие тесты
(test_plan_graph_export_framework_head_excluded.py) продолжают импортировать
её из старого модуля без изменений).

ПРАВИЛО №6 — ни одна сумма/подпись здесь не считается второй формулой:
  - значения полей закупки (предмет, реестровый №, контрагент/ИНН, статус,
    № и дата платёжки) — app.services.purchase_export_cells.get_cell_value;
  - эффективная сумма закупки — app.services.purchase_amounts.
    load_purchase_amounts (effective);
  - каскад по стадиям (Поставлено/Оплачено заявки/позиции, и Σ по заявкам —
    Поставлено/Оплачено по договору) — app.services.plan_graph_export_rows.
    cascade_by_stage;
  - сумма/заказано/остаток договора, И вид договора по товар/услуга/ФОТ
    («kind») — app.services.contract_balances.contract_balances (та же
    запись несёт оба);
  - признак рамочного договора — Purchase.purchase_contract_type/
    parent_purchase_id (тот же критерий, что app.services.committed_amounts
    .is_framework_purchase_expr);
  - «Статья ФЭО» — тот же coalesce PurchaseItem→Purchase→FeoPlannedItem, что
    app.services.plan_graph_export_data.gather_live_plan_graph_data;
  - состав позиций (Ед./Кол-во/Цена за ед./Сумма позиции) — сырые поля
    PurchaseItem, тот же набор полей, что app.services.plan_graph_export_rows
    ._composition_values («Состав закупки»/«Цена за ед.» листа «План
    закупок»);
  - классификатор товар/услуга/ФОТ (kind_of/kind_of_by_category_id) —
    app.services.item_type_split — единственный источник, здесь только
    подпись столбца «Тип договора» и агрегация по сумме (fallback «по
    большинству»), второй классификатор не заводится.

ДОБАВЛЕНО (владелец 09.10.2026, 4-й заход):
  - «Вид договора» (Рамочный / Рамочный накопительный / Разовый) — по
    Purchase.purchase_contract_type ГОЛОВЫ/разовой закупки. Эти подписи
    СОЗНАТЕЛЬНО отличаются от app.services.dictionaries.CONTRACT_TYPE_LABELS
    («Рамочный (нарастающий итог)» и т.п. — подписи для форм договора) — тут
    короткие подписи именно для фильтра реестра, владелец задал их явно;
  - «Тип договора» (Поставка товаров / Оказание услуг / ФОТ) — primary: тот
    же kind, что уже лежит в contract_balances() (Purchase.item_type головы/
    разовой закупки, kind_of_by_category_id, НЕ второй расчёт); fallback,
    если primary == unspecified — большинство по сумме среди «позиций»
    группы (заявки рамочного — их Purchase.item_type; состав разовой —
    PurchaseItem.item_type), тот же kind_of, не второй классификатор;
  - для РАЗОВОГО договора с составом (PurchaseItem) — «Сумма заявки»/
    «Поставлено»/«Оплачено» теперь считаются НЕ на закупке целиком, а ПО
    КАЖДОЙ позиции (сумма позиции; каскад тем же cascade_by_stage от суммы
    позиции) — владелец: «для разовых суммы должны показываться у позиций».
    У закупки без позиций (itemless) эти три величины остаются на уровне
    закупки (иначе потерялись бы — им негде быть)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.contract_balances import contract_balances, contract_scope_predicate
from app.services.feo_payroll import payroll_category_ids
from app.services.item_type_split import KIND_GOODS, KIND_PAYROLL, KIND_SERVICES, kind_of
from app.services.plan_graph_export_data import item_kind_label
from app.services.plan_graph_export_rows import cascade_by_stage, category_full_path
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_export_cells import build_purchase_export_ctx, get_cell_value

# «Вид договора» (владелец 09.10.2026, замечание 3) — подписи короче и ИНЫЕ,
# чем app.services.dictionaries.CONTRACT_TYPE_LABELS (формы договора);
# заданы владельцем явно для этого столбца реестра, не переиспользуем тот
# словарь (разный смысл подписи для разных мест UI/экспорта).
_CONTRACT_VIEW_LABELS = {
    "framework_with_amount": "Рамочный",
    "framework_cumulative": "Рамочный накопительный",
}
_CONTRACT_VIEW_SINGLE = "Разовый"

# «Тип договора» (владелец 09.10.2026, замечание 4) — ТОЛЬКО 3 товарных
# корзины показываем в этом столбце (unspecified — пустая строка, не
# придумываем четвёртую подпись).
_CONTRACT_KIND_LABELS = {
    KIND_GOODS: "Поставка товаров",
    KIND_SERVICES: "Оказание услуг",
    KIND_PAYROLL: "ФОТ",
}


def contract_view_label(purchase_contract_type) -> str:
    """«Рамочный» / «Рамочный накопительный» / «Разовый» — по
    Purchase.purchase_contract_type головы рамочного договора/разовой
    закупки (владелец 09.10.2026, замечание 3)."""
    return _CONTRACT_VIEW_LABELS.get(purchase_contract_type or "", _CONTRACT_VIEW_SINGLE)


def contract_kind_label(primary_kind: str, fallback_pairs: list) -> str:
    """«Поставка товаров» / «Оказание услуг» / «ФОТ» — `primary_kind` уже
    посчитан вызывающим кодом через contract_balances()["kind"] (ПРАВИЛО №6).
    Если primary неопределён (unspecified/нет записи) — большинство по Σ
    среди `fallback_pairs` [(kind, amount), ...] (владелец: «по большинству
    суммы позиций»); нет ни одной типизированной суммы — "" (не придумываем
    подпись из воздуха)."""
    label = _CONTRACT_KIND_LABELS.get(primary_kind)
    if label:
        return label
    sums: dict = {}
    for k, amount in fallback_pairs:
        lbl = _CONTRACT_KIND_LABELS.get(k)
        if lbl:
            sums[lbl] = sums.get(lbl, 0.0) + (amount or 0.0)
    if not sums:
        return ""
    return max(sums, key=lambda lbl: sums[lbl])


def _is_framework(p: Purchase) -> bool:
    return bool(p.purchase_contract_type) and p.purchase_contract_type.startswith("framework")


def _order_sort_key(o: Purchase):
    try:
        n = float(o.order_number) if o.order_number not in (None, "") else float("inf")
    except (TypeError, ValueError):
        n = float("inf")
    return (n, o.purchase_number if o.purchase_number is not None else 10 ** 9)


async def _effective_category_ids(db: AsyncSession, purchase_ids: list) -> dict:
    """{purchase_id: feo_category_id} — тот же coalesce PurchaseItem.
    feo_category_id → Purchase.feo_category_id → FeoPlannedItem.
    feo_category_id, что в app.services.plan_graph_export_data.
    gather_live_plan_graph_data (не второй признак категории закупки)."""
    if not purchase_ids:
        return {}
    cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id, FeoPlannedItem.feo_category_id)
    rows = (await db.execute(
        select(Purchase.id, cat_col.label("cat"))
        .outerjoin(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
        .outerjoin(FeoPlannedItem, FeoPlannedItem.id == PurchaseItem.feo_planned_item_id)
        .where(Purchase.id.in_(purchase_ids))
    )).all()
    result: dict = {}
    for pid, cat in rows:
        if cat is not None and pid not in result:
            result[pid] = cat
    return result


async def _items_by_purchase(db: AsyncSession, purchase_ids: list) -> dict:
    """{purchase_id: [{"name","unit","qty","unit_price","total","item_type"}]}
    — состав закупки (владелец 09.10.2026, часть 3 — «внутри разового
    договора может быть несколько позиций»). Сырые поля PurchaseItem
    (quantity/unit/unit_price/total_price/item_type), та же пара сумм, что
    читает app.services.plan_graph_export_rows._composition_values («Состав
    закупки»/«Цена за ед.» листа «План закупок»), не вторая формула.
    "total" — total_price, если задан, иначе qty*unit_price, иначе 0.0
    (закупка без позиций просто не попадает в словарь)."""
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(PurchaseItem)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
        .order_by(PurchaseItem.purchase_id, PurchaseItem.id)
    )).scalars().all()
    result: dict = {}
    for it in rows:
        qty = float(it.quantity) if it.quantity is not None else None
        unit_price = float(it.unit_price) if it.unit_price is not None else None
        if it.total_price is not None:
            total = float(it.total_price)
        elif qty is not None and unit_price is not None:
            total = qty * unit_price
        else:
            total = 0.0
        result.setdefault(it.purchase_id, []).append({
            "name": it.item_name or "",
            "unit": it.unit or "",
            "qty": round(qty, 3) if qty is not None else "",
            "unit_price": round(unit_price, 2) if unit_price is not None else "",
            "total": round(total, 2),
            "item_type": it.item_type,
        })
    return result


async def gather_contracts_sheet_data(db: AsyncSession, subsidy_id: int) -> list:
    """[{head: {...}, orders: [{...}, ...]}, ...] — отсортировано по № закупки
    головы/разовой закупки по возрастанию (владелец: «по номеру закупки»).
    head/orders несут "items" — список позиций (PurchaseItem) этой строки,
    [] если позиций нет. У РАЗОВОЙ закупки с позициями каждая позиция несёт
    СВОИ "order_sum"/"order_delivered"/"order_paid" (владелец, замечание 2) —
    рендерер пишет их в столбцы уровня ЗАЯВКИ строки «Позиция», а не в
    строку договора."""
    # ПРАВИЛО №6: предикат «входит в реестр договоров» — ОДИН, из
    # contract_balances.contract_scope_predicate.
    rows = (await db.execute(
        select(Purchase)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status != "cancelled")
        .where(contract_scope_predicate(Purchase))
    )).scalars().all()
    if not rows:
        return []

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    ctx = await build_purchase_export_ctx(db, rows)
    amounts_by_id = await load_purchase_amounts(db, [p.id for p in rows])
    eff_cat_ids = await _effective_category_ids(db, [p.id for p in rows])
    items_by_purchase = await _items_by_purchase(db, [p.id for p in rows])
    payroll_ids = await payroll_category_ids(db, [subsidy_id])
    # ПРАВИЛО №6 — сумма/заказано/остаток договора И «kind» (товар/услуга/
    # ФОТ) ЧИТАЮТСЯ отсюда, второй расчёт этих величин здесь не заводится.
    balances = (await contract_balances(db, subsidy_id))["by_purchase"]

    def _cell(key: str, p: Purchase):
        return get_cell_value(key, p, ctx)

    def _kind_label(p: Purchase) -> str:
        """«Товар / услуга» закупки `p» — item_kind_label листов «План
        закупок» (ПРАВИЛО №6)."""
        return item_kind_label(p.item_type, eff_cat_ids.get(p.id), payroll_ids)

    def _eff(p: Purchase) -> float:
        a = amounts_by_id.get(p.id)
        return float(a.effective) if a and a.effective is not None else 0.0

    def _stage(p: Purchase) -> tuple:
        _planned, _contract, _ordered, delivered, paid = cascade_by_stage(p.status, _eff(p))
        return delivered, paid

    def _items_with_stage(p: Purchase) -> list:
        """Состав закупки `p`, КАЖДАЯ позиция несёт свои order_sum/
        order_delivered/order_paid (каскад от суммы САМОЙ позиции, тот же
        cascade_by_stage, что строки заявок — владелец, замечание 2)."""
        result = []
        for it in items_by_purchase.get(p.id, []):
            _planned, _contract, _ordered, d, pa = cascade_by_stage(p.status, it["total"])
            result.append({**it, "order_sum": it["total"], "order_delivered": round(d, 2), "order_paid": round(pa, 2)})
        return result

    contract_ids = {p.contract_id for p in rows if p.contract_id}
    contracts_by_id: dict = {}
    if contract_ids:
        contracts_by_id = {
            c.id: c for c in (await db.execute(
                select(Contract).where(Contract.id.in_(contract_ids))
            )).scalars().all()
        }

    heads = [p for p in rows if _is_framework(p) and p.parent_purchase_id is None]
    head_ids = {p.id for p in heads}
    orders_by_head: dict = {}
    singles: list = []
    for p in rows:
        if p.id in head_ids:
            continue
        if p.parent_purchase_id in head_ids:
            orders_by_head.setdefault(p.parent_purchase_id, []).append(p)
        else:
            singles.append(p)

    # Владелец 09.10.2026, прод ФАДМ 2026_2, 3-й заход: формальная голова без
    # заявок — не голова по смыслу, выводить как разовый договор (ПРАВИЛО
    # №6 — тот же приём, что contract_balances.contract_balances).
    heads_without_orders = [h for h in heads if not orders_by_head.get(h.id)]
    heads = [h for h in heads if orders_by_head.get(h.id)]
    singles.extend(heads_without_orders)

    groups: list = []
    for head in heads:
        orders = sorted(orders_by_head.get(head.id, []), key=_order_sort_key)
        bal = balances.get(head.id) or {"contract_sum": 0.0, "ordered": 0.0, "remaining": 0.0, "kind": "unspecified"}

        order_rows = []
        order_cat_paths: set = set()
        for o in orders:
            odelivered, opaid = _stage(o)
            o_cat_path = category_full_path(cats, eff_cat_ids.get(o.id))
            order_cat_paths.add(o_cat_path)
            order_rows.append({
                "order_number": o.order_number or "", "purchase_number": o.purchase_number or "",
                "registry_number": _cell("registry_number", o),
                "subject": _cell("subject", o) or o.item_name or "",
                "sum": round(_eff(o), 2), "delivered": round(odelivered, 2), "paid": round(opaid, 2),
                "status": _cell("status", o),
                "pp_number": _cell("payment_doc_number", o), "pp_date": _cell("payment_doc_date", o),
                "pp_amount": _cell("payment_amount", o),
                "category_path": o_cat_path,
                "purchase_id": o.id,
                "items": _items_with_stage(o),
                "item_kind": _kind_label(o),
                "planned_payment_month": _cell("planned_payment_month", o),
                "payment_month": _cell("payment_month", o),
            })

        if len(order_cat_paths) == 1:
            head_cat_path = next(iter(order_cat_paths))
        elif order_cat_paths:
            head_cat_path = "Разные"
        else:
            head_cat_path = category_full_path(cats, eff_cat_ids.get(head.id))

        # «Поставлено/Оплачено по договору» — Σ по строкам заявок ЭТОГО
        # договора (тем же cascade_by_stage, что и сами строки заявок).
        delivered_total = round(sum(o["delivered"] for o in order_rows), 2)
        paid_total = round(sum(o["paid"] for o in order_rows), 2)

        contract_type_view = contract_view_label(head.purchase_contract_type)
        contract_kind = contract_kind_label(
            bal.get("kind", "unspecified"),
            [(kind_of(o.item_type), _eff(o)) for o in orders],
        )

        groups.append({
            "head": {
                "purchase_number": head.purchase_number or "",
                "registry_number": _cell("registry_number", head),
                "contract_number": (
                    contracts_by_id.get(head.contract_id).number if head.contract_id in contracts_by_id else None
                ) or head.contract_number or "",
                "contract_date": (
                    str(contracts_by_id[head.contract_id].date)
                    if head.contract_id in contracts_by_id and contracts_by_id[head.contract_id].date
                    else (str(head.contract_date) if head.contract_date else "")
                ),
                "contractor": _cell("contractor", head), "contractor_inn": _cell("contractor_inn", head),
                "subject": _cell("subject", head) or head.item_name or "",
                "contract_sum": round(bal["contract_sum"], 2), "ordered": round(bal["ordered"], 2),
                "remaining": round(bal["remaining"], 2),
                "delivered_total": delivered_total, "paid_total": paid_total,
                "is_framework": True,
                "status": _cell("status", head),
                "category_path": head_cat_path,
                "purchase_id": head.id,
                "items": [],  # владелец: у организационной "головы" своих позиций нет
                "contract_type_view": contract_type_view,
                "contract_kind": contract_kind,
            },
            "orders": order_rows,
            "sort_key": head.purchase_number if head.purchase_number is not None else 10 ** 9,
        })

    for p in singles:
        delivered, paid = _stage(p)
        bal = balances.get(p.id) or {"contract_sum": 0.0, "ordered": 0.0, "remaining": 0.0, "kind": "unspecified"}
        eff = round(_eff(p), 2)
        items = _items_with_stage(p)
        contract_type_view = contract_view_label(p.purchase_contract_type)
        contract_kind = contract_kind_label(
            bal.get("kind", "unspecified"),
            [(kind_of(it.get("item_type")), it["total"]) for it in items],
        )
        groups.append({
            "head": {
                "purchase_number": p.purchase_number or "",
                "registry_number": _cell("registry_number", p),
                "contract_number": _cell("contract_number", p),
                "contract_date": _cell("contract_date", p),
                "contractor": _cell("contractor", p), "contractor_inn": _cell("contractor_inn", p),
                "subject": _cell("subject", p) or p.item_name or "",
                "contract_sum": round(bal["contract_sum"], 2), "ordered": round(bal["ordered"], 2),
                "remaining": round(bal["remaining"], 2),
                "delivered_total": round(delivered, 2), "paid_total": round(paid, 2),
                "is_framework": False,
                "status": _cell("status", p),
                "category_path": category_full_path(cats, eff_cat_ids.get(p.id)),
                "purchase_id": p.id,
                # Разовая закупка — сама себе единственная «заявка» (владелец,
                # часть A): «Сумма заявки»/«Поставлено»/«Оплачено» заполнены В
                # СТРОКЕ ДОГОВОРА только если у закупки НЕТ позиций (itemless
                # — владелец, замечание 2); с позициями — эти три величины
                # распределены ПО ПОЗИЦИЯМ (см. items[*]["order_sum"]).
                "single_sum": eff, "single_delivered": round(delivered, 2), "single_paid": round(paid, 2),
                "single_status": _cell("status", p),
                "items": items,
                "item_kind": _kind_label(p),
                "planned_payment_month": _cell("planned_payment_month", p),
                "payment_month": _cell("payment_month", p),
                "contract_type_view": contract_type_view,
                "contract_kind": contract_kind,
            },
            "orders": [],
            "sort_key": p.purchase_number if p.purchase_number is not None else 10 ** 9,
        })

    groups.sort(key=lambda g: g["sort_key"])
    return groups
