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

ИСПРАВЛЕНО 15.10.2026 (владелец, прод — «общие» договоры между копиями
субсидии «ФАДМ 2026_2»/id=89 и «ФАДМ 2026_3»/id=100: загрузчик нашёл
существующие договоры по номеру/дате/контрагенту, Contract.subsidy_id указывает
на ОДНУ "домашнюю" субсидию, а Purchase ОБЕИХ субсидий ссылаются на тот же
Contract.id): single/framework_with_amount строки раньше строились ОДНА НА
ДОГОВОР (Contract.id), атрибуция — Contract.subsidy_id, а Σ actual считалась
по ВСЕМ привязанным закупкам независимо от их Purchase.subsidy_id — у 89
список включал закупки 100-й. Теперь строка — на (contract_id, subsidy_id) из
app.services.stage_cumulative.single_fwa_rows_by_contract_subsidy() (ПРАВИЛО
№6 — та же атрибуция, что и у карточки/дерева ФЭО, не вторая формула);
framework_cumulative (cfc_stmt) уже и раньше группировался по Purchase.
subsidy_id, не трогали.
"""
from typing import Optional

from sqlalchemy import func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.services.committed_amounts import FRAMEWORK_COMMITTED_STATUSES, committed_status_predicate
from app.services.purchase_amounts import effective_amount_expr
from app.services.stage_cumulative import (
    committed_uncounted_expr,
    reserved_child_predicate,
    single_fwa_rows_by_contract_subsidy,
)

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

    # ── single / framework_with_amount ───────────────────────────────────────
    # ЕДИНСТВЕННЫЙ источник атрибуции «чей общий договор» — ПРАВИЛО №6,
    # app.services.stage_cumulative.single_fwa_rows_by_contract_subsidy()
    # (владелец, 15.10.2026 — договоры, общие между копиями субсидии: строка
    # теперь на (contract_id, subsidy_id), а не на Contract.id с атрибуцией по
    # Contract.subsidy_id — та же функция, что строит карточку/дерево ФЭО).
    single_fwa_rows = await single_fwa_rows_by_contract_subsidy(db, subsidy_ids=subsidy_ids)
    contract_ids = {cid for (cid, _sid) in single_fwa_rows}
    contract_meta: dict[int, object] = {}
    if contract_ids:
        meta_stmt = select(
            Contract.id, Contract.number, Contract.subject, Contract.contract_type, Contract.contractor_id,
        ).where(Contract.id.in_(contract_ids))
        contract_meta = {r.id: r for r in (await db.execute(meta_stmt)).all()}

    contractor_ids = {m.contractor_id for m in contract_meta.values() if m.contractor_id}

    for (contract_id, sid), b in single_fwa_rows.items():
        contract_amount = b["amount"]
        if contract_amount <= 0:
            continue
        ordered_amount = b["actual"]
        meta = contract_meta.get(contract_id)
        rows.append({
            "contract_id": contract_id,
            "number": meta.number if meta is not None else None,
            "subject": meta.subject if meta is not None else None,
            "contract_type": b["contract_type"],
            "contract_type_label": _label(b["contract_type"]),
            "contractor_id": meta.contractor_id if meta is not None else None,
            "subsidy_id": sid,
            "contract_amount": contract_amount,
            "ordered_amount": ordered_amount,
            "remaining": max(0.0, contract_amount - ordered_amount),
        })

    # ── framework_cumulative — Σ закупок, привязанных к договору ─────────────
    # Группировка ПО Purchase.subsidy_id, не Contract.subsidy_id (владелец,
    # 15.10.2026 — тот же «общий договор между копиями субсидии» дефект: эта
    # ветка суммировала ВСЕ закупки договора независимо от их субсидии и
    # относила их на домашний Contract.subsidy_id — ровно как cfc_cat_stmt в
    # stage_cumulative.contracted_rows_by_category уже делает ПРАВИЛЬНО, та
    # же пара статусов — FRAMEWORK_COMMITTED_STATUSES ИЛИ reserved_child_
    # predicate (заказ накопительного рамочного в статусе 'contracted' —
    # договор на партию уже заключён; раньше здесь не было reserved — часть
    # источника расхождения карточка/список, прод-находка 09.10.2026).
    cfc_stmt = (
        select(
            Contract.id, Contract.number, Contract.subject, Contract.contractor_id,
            Purchase.subsidy_id,
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .join(Purchase, Purchase.contract_id == Contract.id)
        .where(Contract.status == "active")
        .where(Contract.contract_type == "framework_cumulative")
        .where(Purchase.subsidy_id.in_(subsidy_ids))
        .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        .group_by(Contract.id, Contract.number, Contract.subject, Contract.contractor_id, Purchase.subsidy_id)
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
