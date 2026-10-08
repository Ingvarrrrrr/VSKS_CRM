"""contract_balances.py — «остаток денег на договоре» (владелец 08.10.2026,
прод ФАДМ 2026_2): ЕДИНАЯ точка расчёта, используется и «Реестром договоров»
(plan_graph_export_contracts_sheet.py — читает отсюда, не считает сама), и
новым столбцом «Остаток по договору, ₽» листов плана-графика
(plan_graph_export_xlsx.py/plan_graph_export_flat_sheet.py), и «Сводной»
(plan_graph_export_summary_sheet.py, столбец «Остаток на договорах, ₽» по
видам). ПРАВИЛО №6 — второй формулы «сумма договора минус заказано» в
проекте не заводить, читать отсюда.

Группировка — та же, что реестр договоров:
  рамочная ГОЛОВА (Purchase.purchase_contract_type начинается с 'framework',
  parent_purchase_id IS NULL) + её заказы (parent_purchase_id = голова);
  разовая закупка с договором (contract_id/contract_number, или статус от
  «Договор» и выше) — сама себе группа из одной закупки.

  Сумма договора — Contract.max_amount (если задан у рамочной головы);
    иначе — Σ effective её заказов (рамочный без явно введённой предельной
    суммы); у разовой — её effective (app.services.purchase_amounts).
  Заказано — Σ effective заказов (БЕЗ отменённых — они не попадают даже в
    исходную выборку, см. ниже); у разовой — её же effective (Заказано ==
    Сумма договора по построению).
  Остаток — Сумма договора − Заказано.

kind — вид группы (товар/услуга/ФОТ/без типа, app.services.item_type_split)
по item_type/категории ГОЛОВЫ (организационной записи рамочного договора,
либо самой разовой закупки) — используется «Сводной» для разбивки остатка по
видам."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.purchase import Purchase
from app.services.feo_payroll import payroll_category_ids as _payroll_category_ids
from app.services.item_type_split import kind_of_by_category_id
from app.services.purchase_amounts import load_purchase_amounts

_CONTRACT_STATUS_FLOOR = ("contracted", "ordered", "delivered", "paid")


def _is_framework(p: Purchase) -> bool:
    return bool(p.purchase_contract_type) and p.purchase_contract_type.startswith("framework")


def contract_scope_predicate(purchase=Purchase):
    """SQL-предикат «закупка входит в реестр договоров/остаток на договоре»
    — ЕДИНСТВЕННОЕ место правила (владелец 09.10.2026, прод ФАДМ 2026_2,
    2-й заход): статус от «Договор» и выше (contracted/ordered/delivered/
    paid) — РОВНО ОДНО условие, одинаковое для ГОЛОВЫ рамочного договора и
    любой другой закупки. Голова в статусе wishes/plan_schedule/
    work_in_progress (договор ещё не заключён) — НЕ входит, даже с заданным
    max_amount/contract_id (прод ФАДМ: РЕЕ-2026-03218, ООО «АДС-АВТО»,
    600 000, статус 'wishes' — договор не заключён, ложно попадала и в
    реестр, и в «Остаток на договорах»; 1-й заход этого фикса отличал голову
    от остальных закупок — оказалось, различать не нужно, правило теперь
    ОДНО для всех). contract_balances() и app.services.
    plan_graph_export_contracts_sheet.gather_contracts_sheet_data читают
    ОТСЮДА (ПРАВИЛО №6 — не второй предикат)."""
    return purchase.status.in_(_CONTRACT_STATUS_FLOOR)


async def contract_balances(db: AsyncSession, subsidy_id: int) -> dict:
    """{"by_purchase": {purchase_id: {"remaining","contract_sum","ordered",
    "group_head_id","kind"}}, "groups": [{"head_id","contract_sum","ordered",
    "remaining","kind","purchase_ids":[...]}, ...]}.

    `by_purchase` содержит запись на КАЖДУЮ закупку группы (голову и все её
    заказы — с ОДНИМ И ТЕМ ЖЕ remaining/contract_sum/ordered группы; разовую
    закупку — на себя) — вызывающему коду (строка листа плана, где известен
    только purchase_id конкретной закупки) не нужно знать, голова она или
    заказ."""
    rows = (await db.execute(
        select(Purchase)
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.status != "cancelled")
        .where(contract_scope_predicate(Purchase))
    )).scalars().all()
    if not rows:
        return {"by_purchase": {}, "groups": []}

    amounts_by_id = await load_purchase_amounts(db, [p.id for p in rows])

    def _eff(p: Purchase) -> float:
        a = amounts_by_id.get(p.id)
        return float(a.effective) if a and a.effective is not None else 0.0

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

    # Владелец 09.10.2026, прод ФАДМ 2026_2, 3-й заход: РЕЕ-2026-03110 —
    # purchase_contract_type='framework_cumulative', parent_purchase_id NULL,
    # но заявок под НЕЙ нет (у того же contract_id реальная голова —
    # РЕЕ-2026-03095). Формальный признак головы (рамочный тип + без
    # родителя) без хотя бы одной заявки — НЕ голова по смыслу (деньги
    # заняла САМА эта закупка, не организационная запись): считать её как
    # разовую закупку (своя Сумма заявки/Поставлено/Оплачено), а не
    # оставлять строкой-головой с пустым фактом.
    heads_without_orders = [h for h in heads if not orders_by_head.get(h.id)]
    heads = [h for h in heads if orders_by_head.get(h.id)]
    singles.extend(heads_without_orders)

    payroll_ids = await _payroll_category_ids(db, [subsidy_id])

    by_purchase: dict = {}
    groups: list = []

    for head in heads:
        orders = orders_by_head.get(head.id, [])
        ordered = sum(_eff(o) for o in orders)
        contract = contracts_by_id.get(head.contract_id)
        contract_sum = float(contract.max_amount) if (contract and contract.max_amount is not None) else ordered
        remaining = contract_sum - ordered
        kind = kind_of_by_category_id(head.item_type, head.feo_category_id, payroll_ids)
        purchase_ids = [head.id] + [o.id for o in orders]
        entry = {
            "remaining": remaining, "contract_sum": contract_sum, "ordered": ordered,
            "group_head_id": head.id, "kind": kind,
        }
        for pid in purchase_ids:
            by_purchase[pid] = entry
        groups.append({
            "head_id": head.id, "contract_sum": contract_sum, "ordered": ordered,
            "remaining": remaining, "kind": kind, "purchase_ids": purchase_ids,
        })

    for p in singles:
        eff = _eff(p)
        kind = kind_of_by_category_id(p.item_type, p.feo_category_id, payroll_ids)
        entry = {
            "remaining": 0.0, "contract_sum": eff, "ordered": eff,
            "group_head_id": p.id, "kind": kind,
        }
        by_purchase[p.id] = entry
        groups.append({
            "head_id": p.id, "contract_sum": eff, "ordered": eff,
            "remaining": 0.0, "kind": kind, "purchase_ids": [p.id],
        })

    return {"by_purchase": by_purchase, "groups": groups}
