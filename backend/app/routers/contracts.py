from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.contract import Contract
from app.models.contract_subsidy import ContractSubsidy
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.schemas.schemas import ContractCreate, ContractOut, ContractSubsidyOut, ContractUpdateResponse, ContractSyncWarnings
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.auth.permissions import require_tab, require_action
from app.auth.visibility import build_visibility_clause, get_visible_subsidy_ids
from app.models.subsidy import Subsidy
from typing import List, Optional
from decimal import Decimal
from app.routers.purchase_budget import FRAMEWORK_TYPES

# Резка волны 2026-09-08 (Правило №5, contracts.py 1323 → core): вынесены
# contracts_approval.py (_build_approval_purchase_fields +
# get_or_create_approval_purchase), contracts_admin.py (merge_contracts,
# migrate_contracts_from_purchases, bulk_enrich_contracts_from_purchases,
# backfill_from_receipts_legacy), contracts_import.py (парсинг xlsx/xls/docx/
# pdf/OCR + contracts_import_preview/mapped), contracts_stages.py
# (generate_monthly_stages). Реэкспорт ниже сохраняет существующие импорты
# рабочими: tests/test_contract_approval_purchase.py делает `from
# app.routers.contracts import _build_approval_purchase_fields`;
# purchases.py и purchase_transitions.py делают `from app.routers.contracts
# import ensure_contract_linked` на уровне модуля.
from app.routers.contracts_approval import _build_approval_purchase_fields  # noqa: F401
from app.services.contracts_linking import ensure_contract_linked  # noqa: F401

async def _enrich_contract_from_purchases(c: Contract, db: AsyncSession) -> int:
    """Auto-fill ПУСТЫЕ optional fields на Contract из любой связанной Purchase.

    Returns: count of fields filled (для diag). 0 если нечего обогащать.

    Заполняет только NULL поля — не перезаписывает то что user явно ввёл.
    Полей: subject, max_amount, start_date, end_date, purchase_method, item_type, contractor_id.
    """
    from app.models.purchase import Purchase as _P

    # Phase 27.1.12: добавлен contractor_id в проверку all-filled
    # Если все поля заполнены — выйти
    if all([
        c.subject, c.max_amount is not None,
        c.start_date, c.end_date,
        c.purchase_method, c.item_type,
        c.contractor_id is not None,  # NEW
    ]):
        return 0

    p = (await db.execute(
        select(_P).where(_P.contract_id == c.id).limit(1)
    )).scalar_one_or_none()
    if not p:
        return 0

    filled = 0
    # Phase 27.1.12: заполнить contractor_id из Purchase (только если NULL)
    if c.contractor_id is None and p.contractor_id is not None:
        c.contractor_id = p.contractor_id
        filled += 1

    if not c.subject:
        v = p.subject or str(p.purchase_number or '')
        if v:
            c.subject = v
            filled += 1
    # 27.4-19: framework_cumulative (накопительный) НЕ имеет max_amount —
    # пропускаем enrich этого поля чтобы не воскрешать «Превышен лимит» после 27.4-17.
    if c.max_amount is None and c.contract_type != 'framework_cumulative':
        # ПРАВИЛО №6 (2026-09-07, волна 4b-2c): раньше `total_nmck or contract_price
        # or planned_total_price` — truthy-баг (0 в любом из полей молча проваливался
        # дальше по цепочке). Единый источник: contract_amount() (цена договора ??
        # Σ ContractItem.total ПО ЭТОЙ закупке), с фолбэком на purchase_amounts().plan,
        # если по договору вообще ничего нет. НМЦК сюда сознательно не входит —
        # contract_amount() не читает total_nmck (см. её докстринг в purchase_amounts.py).
        from app.models.contract_item import ContractItem as _CI
        from app.services.purchase_amounts import contract_amount, purchase_amounts
        ci_total = (await db.execute(
            select(func.sum(_CI.total)).where(_CI.purchase_id == p.id)
        )).scalar_one_or_none()
        v = contract_amount(p, contract_items_total=ci_total)
        if v is None:
            v = purchase_amounts(p).plan
        if v is not None:
            c.max_amount = v
            filled += 1
    if not c.start_date and p.contract_date:
        c.start_date = p.contract_date
        filled += 1
    if not c.end_date and p.execution_term:
        c.end_date = p.execution_term
        filled += 1
    if not c.purchase_method:
        c.purchase_method = p.purchase_method if p.purchase_method in ('single', 'competitive') else 'single'
        filled += 1
    if not c.item_type:
        c.item_type = p.item_type or 'товар'
        filled += 1
    return filled


def _framework_approval_state(approval_status: Optional[str]) -> Optional[str]:
    """Purchase.approval_status рамочной ГОЛОВЫ → упрощённое состояние для
    реестра договоров (ContractOut.approval_state), которым фронт решает,
    затемнять ли строку. approved — согласовано; pending — в работе или
    отклонено (ждёт повторного согласования); None — головы ещё нет или
    цепочка не строилась (нет руководителя организации, см.
    purchases.py::_build_framework_chain_approvals) — тогда фронт не затемняет."""
    if approval_status == "approved":
        return "approved"
    if approval_status in ("in_progress", "rejected"):
        return "pending"
    return None


router = APIRouter(prefix="/api/contracts", tags=["contracts"])

@router.get("/", response_model=List[ContractOut])
async def list_contracts(
    subsidy_id: Optional[int] = Query(None),
    contract_type: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contractor_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Contract).options(
        selectinload(Contract.contractor),
        selectinload(Contract.subsidy),
        selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy),
    ).order_by(Contract.id.desc())
    if subsidy_id is not None:
        q = q.where(Contract.subsidy_id == subsidy_id)
    if contract_type is not None:
        q = q.where(Contract.contract_type == contract_type)
    if purchase_method is not None:
        q = q.where(Contract.purchase_method == purchase_method)
    if status is not None:
        q = q.where(Contract.status == status)
    if contractor_id is not None:
        q = q.where(Contract.contractor_id == contractor_id)
    vis = await get_visible_subsidy_ids(current_user, db, "contracts")
    if vis is not None:
        q = q.where(Contract.subsidy_id.in_(vis))
    # Phase 28 Bundle 3: user-level visibility filter (was missing — data leak fix).
    clause = await build_visibility_clause(current_user, db, 'contract')
    if clause is not None:
        q = q.where(clause)
    result = await db.execute(q)
    contracts = result.scalars().all()
    out = []
    for c in contracts:
        # phase26-l-2: COALESCE chain contract_price → planned_total_price → total_nmck
        # чтобы legacy-закупки с NULL contract_price тоже учитывались в total_ordered.
        ordered_result = await db.execute(
            select(func.coalesce(
                func.sum(func.coalesce(Purchase.contract_price, Purchase.planned_total_price, Purchase.total_nmck, 0)),
                0
            ))
            .where(Purchase.contract_id == c.id)
        )
        total_ordered = ordered_result.scalar() or Decimal("0")
        # 27.4-18: total_delivered — приоритет JSONB acceptance_docs[].amount
        # (после Phase 26-H legacy delivery_payment_amount/acceptance_doc_amount = NULL
        # для всех новых закупок, агрегат показывал 0 при реально поставленных).
        delivered_rows = (await db.execute(
            select(Purchase.delivery_payment_amount, Purchase.acceptance_docs)
            .where(Purchase.contract_id == c.id)
        )).all()
        total_delivered = Decimal("0")
        for dpa, docs in delivered_rows:
            if dpa is not None:
                total_delivered += Decimal(str(dpa))
                continue
            if docs:
                try:
                    docs_list = docs if isinstance(docs, list) else []
                    for doc_entry in docs_list:
                        if isinstance(doc_entry, dict) and doc_entry.get('amount') is not None:
                            total_delivered += Decimal(str(doc_entry['amount']))
                except Exception:
                    pass
        # SUM(payment_amount) — total paid (only for paid-status purchases)
        paid_result = await db.execute(
            select(func.coalesce(func.sum(Purchase.payment_amount), 0))
            .where(Purchase.contract_id == c.id, Purchase.status == "paid")
        )
        total_paid = paid_result.scalar() or Decimal("0")

        d = ContractOut.model_validate(c)
        d.total_ordered = total_ordered
        d.total_delivered = total_delivered
        d.total_paid = total_paid
        d.total_payment = total_delivered  # legacy compat
        # framework_cumulative — без предельной суммы: остаток не считается (нет лимита)
        if c.contract_type == 'framework_cumulative' and not c.max_amount:
            d.remaining_ordered = None   # нет лимита — нет отрицательного остатка
            d.remaining = None
        else:
            max_amt = c.max_amount or Decimal("0")
            d.remaining_ordered = max_amt - total_ordered              # сколько ещё можно заказать
            d.remaining = d.remaining_ordered  # legacy: now shows ordered remaining
        d.remaining_delivered = total_ordered - total_delivered         # заказано, но не поставлено
        d.remaining_paid = total_delivered - total_paid                 # поставлено, но не оплачено
        if c.contractor:
            d.contractor_name = c.contractor.name
            d.contractor_inn = c.contractor.inn
        elif not d.contractor_name:
            # Phase 27.1.4: fallback — pull contractor from linked purchases
            # (advance imports без явного Contract.contractor_id)
            from app.models.purchase import Purchase as _P
            from app.models.contractor import Contractor as _C
            row = (await db.execute(
                select(_C.name, _C.inn).select_from(_P).join(_C, _C.id == _P.contractor_id)
                .where(_P.contract_id == c.id, _P.contractor_id.isnot(None))
                .limit(1)
            )).first()
            if row:
                d.contractor_name, d.contractor_inn = row
        if c.subsidy:
            d.subsidy_name = c.subsidy.name
        d.extra_subsidies = [
            ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
            for es in (c.extra_subsidies or [])
        ]
        # Владелец (2026-09-02): «рамочный договор без закупок внутри должен быть
        # визуально помечен, пока не согласован» — approval_state вычисляется из
        # Purchase.approval_status привязанной рамочной ГОЛОВЫ (is_framework_head,
        # см. purchases.py), отдельной колонки на Contract не заводим.
        if c.contract_type in FRAMEWORK_TYPES:
            head_status = (await db.execute(
                select(Purchase.approval_status).where(
                    Purchase.contract_id == c.id,
                    Purchase.parent_purchase_id.is_(None),
                    Purchase.purchase_contract_type.in_(FRAMEWORK_TYPES),
                ).limit(1)
            )).scalar_one_or_none()
            d.approval_state = _framework_approval_state(head_status)
        out.append(d)
    return out

@router.post("/", response_model=ContractOut)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('contracts')),
):
    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, data.subsidy_id)
    for _sid in (data.extra_subsidy_ids or []):
        await assert_subsidy_approved_for_binding(db, _sid)

    # Duplicate check: same number + contractor + subsidy (org) + date
    if data.contractor_id and data.number:
        dup_q = select(Contract).where(
            Contract.number == data.number,
            Contract.contractor_id == data.contractor_id,
        )
        # Same org (subsidy) — different orgs can have same contract number
        if data.subsidy_id:
            dup_q = dup_q.where(Contract.subsidy_id == data.subsidy_id)
        if data.date:
            dup_q = dup_q.where(Contract.date == data.date)
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            raise HTTPException(
                409,
                f"Договор с таким номером, контрагентом и датой уже существует (ID {dup.id})"
            )
    extra_ids = data.extra_subsidy_ids or []
    dump = data.model_dump(exclude={"extra_subsidy_ids"})
    c = Contract(**dump)
    # 27.4-17: framework_cumulative (накопительный) НЕ имеет предельной суммы —
    # обнуляем max_amount чтобы не получался ложный «Превышен лимит».
    if c.contract_type == 'framework_cumulative':
        c.max_amount = None
    db.add(c)
    await db.flush()

    # Phase 27.1.6: auto-fill empty fields from linked purchases (если уже привязаны)
    await _enrich_contract_from_purchases(c, db)

    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=c.id, subsidy_id=sid))
    await db.commit()
    await db.refresh(c)
    result = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == c.id)
    )
    c = result.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return d

@router.put("/{cid}", response_model=ContractUpdateResponse)
async def update_contract(cid: int, data: ContractCreate, db: AsyncSession = Depends(get_db), current_user=Depends(require_tab('contracts'))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")

    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, data.subsidy_id)
    for _sid in (data.extra_subsidy_ids or []):
        await assert_subsidy_approved_for_binding(db, _sid)

    old_number = c.number
    old_date = c.date
    old_contractor_id = c.contractor_id
    # Duplicate check on update (exclude self, same org)
    if data.contractor_id and data.number:
        dup_q = select(Contract).where(
            Contract.number == data.number,
            Contract.contractor_id == data.contractor_id,
            Contract.id != cid,
        )
        if data.subsidy_id:
            dup_q = dup_q.where(Contract.subsidy_id == data.subsidy_id)
        if data.date:
            dup_q = dup_q.where(Contract.date == data.date)
        dup = (await db.execute(dup_q)).scalar_one_or_none()
        if dup:
            raise HTTPException(409, f"Договор с таким номером и контрагентом уже существует (ID {dup.id})")
    extra_ids = data.extra_subsidy_ids or []
    for k, v in data.model_dump(exclude={"extra_subsidy_ids"}).items():
        setattr(c, k, v)
    # 27.4-17: framework_cumulative (накопительный) НЕ имеет предельной суммы.
    # Обнуляем max_amount даже если пользователь его прислал — иначе ложный «Превышен лимит».
    if c.contract_type == 'framework_cumulative':
        c.max_amount = None

    # Phase 31-04: cascade sync to linked purchases using model_fields_set
    # (distinguishes «not sent» from «explicitly set to None» — pitfall 6)
    set_fields = data.model_fields_set
    cascade_number = 'number' in set_fields
    cascade_date = 'date' in set_fields
    cascade_contractor = 'contractor_id' in set_fields

    n_updated_purchases = 0
    warnings = ContractSyncWarnings()

    if cascade_number or cascade_date or cascade_contractor:
        linked_result = await db.execute(select(Purchase).where(Purchase.contract_id == cid))
        linked_purchases = linked_result.scalars().all()
        n_updated_purchases = len(linked_purchases)

        # Import helper from plan 31-01 (entity change tracking, T-31-04-02)
        from app.routers.entity_changes import record_entity_changes as _rec_changes
        # ПРАВИЛО №6 (2026-09-07, группа D7): единственный писатель кэша
        # number/date/type/contractor_id на Purchase — _sync_purchase_from_contract
        # (app.routers.purchases). Раньше здесь были параллельные setattr —
        # своя копия той же логики (расхождение с сервисом, которое
        # backfill-фазы 26-j-1/26-k-2/26-lll/26-mmm потом чинили). Локальный
        # импорт — purchases.py импортирует ИЗ этого модуля на уровне модуля
        # (ensure_contract_linked), обратный импорт сверху дал бы цикл.
        from app.routers.purchases import _sync_purchase_from_contract
        _sync_fields = ("contract_number", "contract_date", "purchase_contract_type", "contractor_id")

        for p in linked_purchases:
            before = {f: getattr(p, f) for f in _sync_fields}
            await _sync_purchase_from_contract(p, db)
            old_vals = {f: before[f] for f in _sync_fields if before[f] != getattr(p, f)}
            new_vals = {f: getattr(p, f) for f in old_vals}

            # Record entity changes for audit trail (batch, committed after main commit)
            if old_vals:
                await _rec_changes(
                    db=db,
                    entity_type='purchase',
                    entity_id=p.id,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or getattr(current_user, 'username', None),
                    old_values=old_vals,
                    new_values=new_vals,
                )

        # Warnings: amount_over_max
        if c.max_amount is not None and c.max_amount > 0:
            total_purchases = sum(p.planned_total_price or 0 for p in linked_purchases)
            if total_purchases > c.max_amount:
                warnings.amount_over_max = True

        # Warnings: date_out_of_validity (purchases with execution_term outside contract range)
        out_of_validity: list[int] = []
        for p in linked_purchases:
            if p.execution_term:
                if c.start_date and p.execution_term < c.start_date:
                    out_of_validity.append(p.id)
                elif c.end_date and p.execution_term > c.end_date:
                    out_of_validity.append(p.id)
        warnings.date_out_of_validity = out_of_validity

    # Replace extra subsidies
    old_extras = await db.execute(select(ContractSubsidy).where(ContractSubsidy.contract_id == cid))
    for es in old_extras.scalars().all():
        await db.delete(es)
    for sid in extra_ids:
        db.add(ContractSubsidy(contract_id=cid, subsidy_id=sid))

    # Phase 27.1.6: auto-fill пустые fields из связанных Purchase
    await _enrich_contract_from_purchases(c, db)

    await db.commit()
    result2 = await db.execute(
        select(Contract).options(
            selectinload(Contract.extra_subsidies).selectinload(ContractSubsidy.subsidy)
        ).where(Contract.id == cid)
    )
    c = result2.scalar_one()
    d = ContractOut.model_validate(c)
    d.extra_subsidies = [
        ContractSubsidyOut(id=es.id, subsidy_id=es.subsidy_id, subsidy_name=es.subsidy.name if es.subsidy else None)
        for es in c.extra_subsidies
    ]
    return ContractUpdateResponse(
        contract=d,
        n_updated_purchases=n_updated_purchases,
        warnings=warnings,
    )

@router.delete("/{cid}")
async def delete_contract(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_action('contract.delete'))):
    result = await db.execute(select(Contract).where(Contract.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Not found")
    await db.delete(c)
    await db.commit()
    return {"ok": True}
