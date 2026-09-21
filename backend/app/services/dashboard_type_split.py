"""План B (ancient-prancing-music.md, раздел B/1) — товары/услуги/без типа по
каждому накопительному этапу дашборда (plan_schedule/work/ordered/contracts/
delivered/delivered_unpaid/paid), и глобально, и per-subsidy.

Извлечено рядом с dashboard_charts.py (Правило №5 — не раздувать роутер) по
образцу app.services.dashboard_monthly_accrual: чистый агрегат, видимость
приходит СНАРУЖИ колбэком/параметрами, здесь своей логики видимости нет.

НЕ второй набор корзин (Правило №6): суммы по этапу — ровно те же значения,
что basket_q/subsidy_q/contract_*_q в dashboard_charts.py (effective_amount_expr/
planned_total_price, тот же набор статусов) — здесь они лишь РАСКЛАДЫВАЮТСЯ по
типу через app.services.item_type_split (purchase_type_shares/kind_of,
единственный источник правила типа/долей).

Метод: для каждой закупки в скоупе — доля товары/услуги/без типа по ЕЁ
собственным PurchaseItem (purchase_type_shares), помноженная на сумму, которой
закупка засчитывается в тот или иной этап (та же сумма, что и в существующих
корзинах). Раскладка НАКАПЛИВАЕТСЯ «сырыми» (нераскруглёнными) Decimal —
округление до копейки происходит РОВНО ОДИН РАЗ, в reconcile_split(), против
уже посчитанного (существующего) значения этапа — так сумма трёх частей
конструктивно совпадает с прежним числом, а не проверяется постфактум.

«Заключено договоров» — то же самое для framework_cumulative (доля по
позициям привязанных закупок) и для single/framework_with_amount (доля по
ПУЛУ позиций ВСЕХ закупок, привязанных к договору через Purchase.contract_id —
сам договор своих позиций не имеет). Договор без единой привязанной закупки
(или без единой позиции в привязанных закупках) — целиком «без типа»
(см. reconcile_split: raw_total == 0 → всё в unspecified).

Помесячное начисление (dashboard_monthly_accrual.py) НЕ входит в раскладку
здесь — оно не привязано к позициям конкретной закупки (агрегат по графику
платежей); вызывающая сторона (dashboard_charts.py) добавляет его к
«ordered» ЦЕЛИКОМ как «без типа» (решение владельца, план раздел B/1).
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.item_type_split import TypeShares, purchase_type_shares, split_amount_by_shares
from app.services.purchase_amounts import effective_amount_expr

STAGE_KEYS: tuple = (
    "plan_schedule", "work", "ordered", "contracts", "delivered", "delivered_unpaid", "paid",
)


def _zero3() -> List[Decimal]:
    return [Decimal(0), Decimal(0), Decimal(0)]


def _add3(acc: List[Decimal], amt: Decimal, shares: TypeShares) -> None:
    acc[0] += amt * shares.goods
    acc[1] += amt * shares.services
    acc[2] += amt * shares.unspecified


def reconcile_split(raw: List[Decimal], target) -> Dict[str, float]:
    """raw = [raw_goods, raw_services, raw_unspecified] (Decimal, нераскруглённые).
    target — уже посчитанное (существующее) значение этапа (float/Decimal/None).
    Возвращает {"goods","services","unspecified"} (float), сумма которых РОВНО
    target (до копейки) — через split_amount_by_shares (item_type_split.py,
    единственная формула округления с сохранением суммы)."""
    target_dec = Decimal(str(target)) if target is not None else Decimal(0)
    raw_total = raw[0] + raw[1] + raw[2]
    if raw_total == 0:
        # Ни одна закупка/договор этапа не дала распознаваемой доли по типу
        # (нет позиций/нет данных) — вся сумма «без типа» (purchase_type_shares).
        return {"goods": 0.0, "services": 0.0, "unspecified": float(target_dec)}
    goods_share = raw[0] / raw_total
    services_share = raw[1] / raw_total
    shares = TypeShares(
        goods=goods_share,
        services=services_share,
        unspecified=Decimal(1) - goods_share - services_share,
    )
    g, s, u = split_amount_by_shares(target_dec, shares)
    return {"goods": float(g), "services": float(s), "unspecified": float(u)}


async def _items_by_purchase(db: AsyncSession, purchase_ids: List[int]) -> Dict[int, list]:
    if not purchase_ids:
        return {}
    rows = (await db.execute(
        select(PurchaseItem.purchase_id, PurchaseItem.item_type, PurchaseItem.total_price)
        .where(PurchaseItem.purchase_id.in_(purchase_ids))
    )).all()
    out: Dict[int, list] = {}
    for pid, itype, tprice in rows:
        out.setdefault(pid, []).append(SimpleNamespace(item_type=itype, total_price=tprice))
    return out


async def compute_type_split_raw(
    db: AsyncSession,
    *,
    apply_filter: Callable,
    use_sids: bool,
    visible_subsidy_ids: Optional[set],
    org_ids: Optional[list],
) -> dict:
    """Возвращает {"global": {stage: [g,s,u]}, "per_subsidy": {sid: {stage: [g,s,u]}}}
    — Decimal-триплеты, НЕраскруглённые. Вызывающий код обязан прогнать каждую
    через reconcile_split() против уже посчитанного значения этапа.

    apply_filter — тот же колбэк-фильтр видимости покупок, что и
    compute_monthly_ordered_map (_apply_purchase_org_filter, применённый
    вызывающей стороной с нужными current_user/org_ids/visible_subsidy_ids).
    use_sids/visible_subsidy_ids/org_ids — те же переменные, что
    dashboard_charts.py использует для contract_single_q/contract_fc_q (эти два
    запроса фильтруются НЕ через apply_filter, а напрямую по Contract/Purchase —
    та же логика видимости, продублированная и в самом dashboard_charts.py
    для каждого из shared-запросов)."""
    global_split: Dict[str, List[Decimal]] = {stage: _zero3() for stage in STAGE_KEYS}
    per_subsidy_split: Dict[int, Dict[str, List[Decimal]]] = {}

    def _sid_bucket(sid) -> Optional[Dict[str, List[Decimal]]]:
        if sid is None:
            return None
        if sid not in per_subsidy_split:
            per_subsidy_split[sid] = {stage: _zero3() for stage in STAGE_KEYS}
        return per_subsidy_split[sid]

    # ── Покупки, попадающие хотя бы в одну корзину (те же 6, что basket_q) ──
    base_q = (
        select(
            Purchase.id, Purchase.status, Purchase.subsidy_id,
            Purchase.planned_total_price, effective_amount_expr().label("effective"),
        )
        .where(Purchase.status.notin_(["cancelled", "wishes"]))
    )
    base_q = apply_filter(base_q)
    purchase_rows = (await db.execute(base_q)).all()

    # ── «Заключено договоров», framework_cumulative — те же покупки, что
    # contract_fc_q, доля по СВОИМ позициям (могут пересекаться с base_q —
    # статусы contracted/ordered/delivered/paid уже входят в base_q). ──
    fc_q = (
        select(Purchase.id, Purchase.subsidy_id, effective_amount_expr().label("effective"))
        .join(Contract, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Purchase.status.in_(["contracted", "ordered", "delivered", "paid"]))
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            fc_q = fc_q.where(Purchase.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        fc_q = fc_q.where(Purchase.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    fc_rows = (await db.execute(fc_q)).all()

    # ── «Заключено договоров», single/framework_with_amount — сумма (max_amount)
    # не привязана к конкретной закупке; доля берётся по ПУЛУ позиций ВСЕХ
    # закупок, привязанных к договору (Purchase.contract_id). ──
    contract_q = (
        select(Contract.id, Contract.subsidy_id, Contract.max_amount, Contract.contract_type)
        .where(Contract.status == "active")
    )
    if use_sids:
        if visible_subsidy_ids is not None:
            contract_q = contract_q.where(Contract.subsidy_id.in_(visible_subsidy_ids))
    elif org_ids is not None:
        contract_q = contract_q.where(Contract.subsidy_id.in_(
            select(Subsidy.id).where(Subsidy.org_id.in_(org_ids))
        ))
    all_contracts = (await db.execute(contract_q)).all()
    # 'single' требует хотя бы одну реально привязанную закупку в нужных статусах
    # (см. _contracted_purchase_exists в dashboard_charts.py::contract_single_q);
    # 'framework_with_amount' входит безусловно. Один запрос на ВСЕ single-контракты
    # сразу — не по одному (избегаем N+1/await внутри comprehension).
    _single_ids = [c.id for c in all_contracts if c.contract_type == "single"]
    _existing_purchase_contract_ids: set = set()
    if _single_ids:
        _rows = (await db.execute(
            select(Purchase.contract_id)
            .where(Purchase.contract_id.in_(_single_ids))
            .where(Purchase.status.in_(["contracted", "ordered", "delivered", "paid"]))
            .distinct()
        )).all()
        _existing_purchase_contract_ids = {r[0] for r in _rows}
    single_contracts = [
        c for c in all_contracts
        if c.contract_type == "framework_with_amount"
        or (c.contract_type == "single" and c.id in _existing_purchase_contract_ids)
    ]
    contract_ids = [c.id for c in single_contracts]
    linked_purchase_rows: list = []
    if contract_ids:
        linked_purchase_rows = (await db.execute(
            select(Purchase.id, Purchase.contract_id).where(Purchase.contract_id.in_(contract_ids))
        )).all()
    linked_purchase_ids_by_contract: Dict[int, list] = {}
    for pid, cid in linked_purchase_rows:
        linked_purchase_ids_by_contract.setdefault(cid, []).append(pid)

    # ── Один общий запрос позиций закупок на объединение всех участвующих id ──
    all_purchase_ids = list({
        *[r.id for r in purchase_rows],
        *[r.id for r in fc_rows],
        *[pid for pid, _ in linked_purchase_rows],
    })
    items_by_purchase = await _items_by_purchase(db, all_purchase_ids)

    # ── 6-корзинная раскладка (см. widgets в dashboard_charts.py) ──
    for r in purchase_rows:
        shares = purchase_type_shares(items_by_purchase.get(r.id, ()))
        sid_bucket = _sid_bucket(r.subsidy_id)
        plan_amt = Decimal(str(r.planned_total_price)) if r.planned_total_price is not None else Decimal(0)
        eff_amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)

        def _accrue(stage: str, amt: Decimal) -> None:
            _add3(global_split[stage], amt, shares)
            if sid_bucket is not None:
                _add3(sid_bucket[stage], amt, shares)

        if r.status == "plan_schedule":
            _accrue("plan_schedule", plan_amt)
        elif r.status == "work_in_progress":
            _accrue("plan_schedule", plan_amt)
            _accrue("work", plan_amt)
        elif r.status in ("contracted", "ordered"):
            _accrue("plan_schedule", eff_amt)
            _accrue("work", eff_amt)
            if r.status == "ordered":
                _accrue("ordered", eff_amt)
        elif r.status == "delivered":
            _accrue("plan_schedule", eff_amt)
            _accrue("work", eff_amt)
            _accrue("ordered", eff_amt)
            _accrue("delivered", eff_amt)
            _accrue("delivered_unpaid", eff_amt)
        elif r.status == "paid":
            _accrue("plan_schedule", eff_amt)
            _accrue("work", eff_amt)
            _accrue("ordered", eff_amt)
            _accrue("delivered", eff_amt)
            _accrue("paid", eff_amt)

    # ── «Заключено договоров»: framework_cumulative ──
    for r in fc_rows:
        shares = purchase_type_shares(items_by_purchase.get(r.id, ()))
        amt = Decimal(str(r.effective)) if r.effective is not None else Decimal(0)
        _add3(global_split["contracts"], amt, shares)
        sid_bucket = _sid_bucket(r.subsidy_id)
        if sid_bucket is not None:
            _add3(sid_bucket["contracts"], amt, shares)

    # ── «Заключено договоров»: single/framework_with_amount ──
    for c in single_contracts:
        linked_ids = linked_purchase_ids_by_contract.get(c.id, [])
        pooled_items: list = []
        for pid in linked_ids:
            pooled_items.extend(items_by_purchase.get(pid, ()))
        shares = purchase_type_shares(pooled_items)
        amt = Decimal(str(c.max_amount)) if c.max_amount is not None else Decimal(0)
        _add3(global_split["contracts"], amt, shares)
        sid_bucket = _sid_bucket(c.subsidy_id)
        if sid_bucket is not None:
            _add3(sid_bucket["contracts"], amt, shares)

    return {
        "global": global_split,
        "per_subsidy": per_subsidy_split,
    }
