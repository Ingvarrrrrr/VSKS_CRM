"""dashboard_contracts_drill.py — построчная расшифровка карточки «Заключено
договоров» (владелец, 06.10.2026, план sleepy-fluttering-walrus.md, п.2):
список договоров субсидии с суммой, заказано, остаток — по образцу
dashboard_type_drill.py, но единица строки — ДОГОВОР, а не позиция закупки.

ПРАВИЛО №6 — Σ amount всех строк ОБЯЗАНА равняться карточке «Заключено
договоров» (app.services.stage_cumulative.contracted_total_by_subsidy), иначе
опять «на эту цифру не выйти фильтрами» (ровно жалоба владельца про
redistributable-подстроки). Не вызываем contracted_total_by_subsidy() напрямую
(она агрегирует СРАЗУ по субсидии — нет начала строки «один договор»), но
строим amount КАЖДОЙ строки ТЕМИ ЖЕ выражениями/предикатами:
  - single/framework_with_amount — effective_amount_expr() Σ по закупкам,
    committed_status_predicate()/FRAMEWORK_COMMITTED_STATUSES ∪ reserved_child_
    predicate() (committed_amounts.py/stage_cumulative.py — «заказано+
    зарезервировано», та же пара, что fwa_children_cat_stmt/cfc_cat_stmt в
    contracted_rows_by_category), greatest(max_amount, Σ факт) — тот же приём,
    что _fwa_children_sum в contracted_total_by_subsidy (framework_with_amount)
    и single_contract_topup_by_subsidy (single: «лимит или факт, что больше» —
    то же greatest(), просто показан как ОДНО число строки, а не отдельная
    добавка). framework_with_amount НЕ гейтится статусом закупки-шапки —
    решение владельца 09.10.2026 (прод-пример «АДС-АВТО», договор «1», закупка
    №1253): действующий (status='active') framework_with_amount-договор сам
    по себе увеличивает «законтрактовано», даже если заказов по нему не было
    и сама шапка ещё не дошла до стадии «Договор» — «увеличивает
    законтрактованное, но не запланированное». Гейт по шапке (функция
    framework_with_amount_head_committed_expr) был введён и тем же днём
    отменён владельцем — см. git-историю, в committed_amounts.py не осталось.
  - framework_cumulative — Σ effective_amount_expr() по закупкам, привязанным
    к договору (FRAMEWORK_COMMITTED_STATUSES ∪ reserved_child_predicate(), та
    же пара, что и выше), group by Contract.id вместо Purchase.subsidy_id у
    cfc_q.
  - committed-закупки БЕЗ активного контракта признанного типа
    (committed_uncounted_expr(), stage_cumulative.py) — каждая такая закупка
    своей строкой («без закупки» в dashboard_type_drill.py — здесь наоборот,
    закупка есть, договора нет).

Σ amount всех строк == contracted_total_by_subsidy(...)[subsidy_id]['amount']
— проверено test_dashboard_contracts_drill.py на синтетических данных (один
разовый, один framework_with_amount с остатком, один framework_cumulative) И
test_contracted_total_stage_rules.py (framework_with_amount независимо от
статуса шапки + смешанные данные, включая договор с subsidy_id=NULL).

ИСПРАВЛЕНО 09.10.2026 (прод-находка, ФАДМ 2026_2, карточка 13 634 734,35 vs
список 13 599 122,55 — разница 35 611,80): _fwa_children_sum/cfc_stmt раньше
считали ТОЛЬКО FRAMEWORK_COMMITTED_STATUSES (ordered/delivered/paid), а
карточка (contracted_rows_by_category) уже включала reserved_child_predicate()
(заказ рамочного в статусе 'contracted' — договор на партию уже заключён) —
список «терял» зарезервированные-но-не-оформленные-как-заказ деньги, которые
карточка считала. Теперь оба места — ОДНО и то же выражение (ПРАВИЛО №6).
"""
from typing import Optional

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.services.committed_amounts import (
    FRAMEWORK_COMMITTED_STATUSES,
    SINGLE_COMMITTED_STATUSES,
    committed_status_predicate,
)
from app.services.purchase_amounts import effective_amount_expr
from app.services.stage_cumulative import committed_uncounted_expr, reserved_child_predicate

CONTRACT_TYPE_LABELS = {
    "single": "Разовый",
    "framework_with_amount": "Рамочный с суммой",
    "framework_cumulative": "Рамочный накопительный",
}


def _label(contract_type: Optional[str]) -> str:
    return CONTRACT_TYPE_LABELS.get(contract_type, contract_type or "—")


async def contracts_drill_rows(db: AsyncSession, *, subsidy_ids: list[int]) -> list[dict]:
    """Список договоров (+ «закупки без договора») субсидий subsidy_ids с
    contract_amount/ordered_amount/remaining — см. докстринг модуля за
    формулой каждого типа. `subsidy_ids` уже отфильтрованы по видимости/org/
    sandbox вызывающим кодом (эта функция сама не фильтрует видимость, тот же
    контракт, что и contracted_total_by_subsidy)."""
    rows: list[dict] = []
    if not subsidy_ids:
        return rows

    # ── single / framework_with_amount — активные контракты этих типов ──────
    # Те же предикаты, что и contracted_rows_by_category (карточка) — ОБЕ
    # группы статусов (FRAMEWORK_COMMITTED_STATUSES И reserved_child_predicate,
    # т.е. «ordered+reserved», ПРАВИЛО №6): раньше здесь был только
    # FRAMEWORK_COMMITTED_STATUSES, из-за чего список на 35 611,80 расходился
    # с карточкой на «зарезервированных» (status='contracted', заказ рамочного
    # договора) детях (прод-находка 09.10.2026).
    _fwa_children_sum = (
        select(func.coalesce(func.sum(effective_amount_expr()), 0))
        .where(Purchase.contract_id == Contract.id)
        .where(Purchase.parent_purchase_id.isnot(None))
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        .correlate(Contract)
        .scalar_subquery()
    )
    _single_children_sum = (
        select(func.coalesce(func.sum(effective_amount_expr()), 0))
        .where(Purchase.contract_id == Contract.id)
        .where(Purchase.status.in_(list(SINGLE_COMMITTED_STATUSES)))
        .correlate(Contract)
        .scalar_subquery()
    )

    cs_stmt = (
        select(
            Contract.id, Contract.number, Contract.subject, Contract.contract_type,
            Contract.max_amount, Contract.contractor_id, Contract.subsidy_id,
            _fwa_children_sum.label("fwa_actual"),
            _single_children_sum.label("single_actual"),
        )
        .where(Contract.status == "active")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        .where(Contract.contract_type.in_(("single", "framework_with_amount")))
    )
    cs_rows = (await db.execute(cs_stmt)).all()

    contractor_ids = {r.contractor_id for r in cs_rows if r.contractor_id}

    for r in cs_rows:
        recorded = float(r.max_amount) if r.max_amount is not None else 0.0
        if r.contract_type == "framework_with_amount":
            ordered_amount = float(r.fwa_actual or 0)
            if ordered_amount <= 0 and recorded <= 0:
                continue  # ни лимита, ни заказов — договор не участвует в карточке
        else:
            # single — та же проверка "существует привязанная committed-закупка",
            # что _contracted_purchase_exists в contracted_total_by_subsidy:
            # контракт БЕЗ фактической закупки не входит в карточку, даже если
            # у него записан max_amount (Правило №6 — не второй критерий отбора).
            ordered_amount = float(r.single_actual or 0)
            if ordered_amount <= 0:
                continue
        contract_amount = max(recorded, ordered_amount)
        rows.append({
            "contract_id": r.id,
            "number": r.number,
            "subject": r.subject,
            "contract_type": r.contract_type,
            "contract_type_label": _label(r.contract_type),
            "contractor_id": r.contractor_id,
            "subsidy_id": r.subsidy_id,
            "contract_amount": contract_amount,
            "ordered_amount": ordered_amount,
            "remaining": max(0.0, contract_amount - ordered_amount),
        })

    # ── framework_cumulative — Σ закупок, привязанных к договору ─────────────
    cfc_stmt = (
        select(
            Contract.id, Contract.number, Contract.subject, Contract.contractor_id, Contract.subsidy_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Contract.subsidy_id.in_(subsidy_ids))
        # Та же пара статусов, что и cfc_cat_stmt в contracted_rows_by_category
        # (карточка) — FRAMEWORK_COMMITTED_STATUSES ИЛИ reserved_child_predicate
        # (заказ накопительного рамочного в статусе 'contracted' — договор на
        # партию уже заключён). Раньше здесь не было reserved — часть источника
        # расхождения карточка/список (прод-находка 09.10.2026).
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        .group_by(Contract.id, Contract.number, Contract.subject, Contract.contractor_id, Contract.subsidy_id)
    )
    cfc_rows = (await db.execute(cfc_stmt)).all()
    for r in cfc_rows:
        amt = float(r.amt or 0)
        if amt <= 0:
            continue
        contractor_ids.add(r.contractor_id) if r.contractor_id else None
        rows.append({
            "contract_id": r.id,
            "number": r.number,
            "subject": r.subject,
            "contract_type": "framework_cumulative",
            "contract_type_label": _label("framework_cumulative"),
            "contractor_id": r.contractor_id,
            "subsidy_id": r.subsidy_id,
            "contract_amount": amt,
            "ordered_amount": amt,
            "remaining": 0.0,
        })

    # ── committed-закупки без активного контракта признанного типа ──────────
    uncounted_stmt = (
        select(
            Purchase.id, Purchase.purchase_number, Purchase.subject, Purchase.contractor_id, Purchase.subsidy_id,
            effective_amount_expr().label("amt"),
        )
        .outerjoin(Contract, Purchase.contract_id == Contract.id)
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(Purchase.stopped_at.is_(None))
        .where(committed_status_predicate(Purchase))
        .where(committed_uncounted_expr())
    )
    uncounted_rows = (await db.execute(uncounted_stmt)).all()
    for r in uncounted_rows:
        amt = float(r.amt or 0)
        if amt <= 0:
            continue
        if r.contractor_id:
            contractor_ids.add(r.contractor_id)
        rows.append({
            "contract_id": None,
            "number": None,
            "subject": r.subject or f"Закупка {r.purchase_number or r.id}",
            "contract_type": None,
            "contract_type_label": "Без договора",
            "contractor_id": r.contractor_id,
            "subsidy_id": r.subsidy_id,
            "contract_amount": amt,
            "ordered_amount": amt,
            "remaining": 0.0,
        })

    contractor_names: dict[int, str] = {}
    if contractor_ids:
        crows = (await db.execute(
            select(Contractor.id, Contractor.name).where(Contractor.id.in_(contractor_ids))
        )).all()
        contractor_names = {c.id: c.name for c in crows}
    for row in rows:
        row["contractor_name"] = contractor_names.get(row["contractor_id"]) if row["contractor_id"] else None

    rows.sort(key=lambda r: (r["subsidy_id"] or 0, r["number"] or ""))
    return rows
