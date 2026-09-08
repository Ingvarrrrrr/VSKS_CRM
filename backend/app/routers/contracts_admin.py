"""Административные/миграционные операции над договорами.

Вынесено из app/routers/contracts.py (Правило №5, резка волны 2026-09-08):
merge_contracts, migrate_contracts_from_purchases, bulk_enrich_contracts_from_purchases
и его deprecated-алиас backfill_from_receipts_legacy — все требуют либо
require_tab('contracts'), либо require_role('admin'), и не относятся к
основному CRUD-циклу договора. Тот же префикс /api/contracts; ни один путь
здесь не совпадает по форме+методу с PUT/DELETE "/{cid}" ядра — порядок
регистрации относительно contracts.router не важен (см. комментарий в
routes.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import require_role
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contract import Contract
from app.models.purchase import Purchase

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.post("/{cid}/merge/{target_id}")
async def merge_contracts(cid: int, target_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_tab('contracts'))):
    """Merge contract cid INTO target_id: move all purchases, then delete cid."""
    if cid == target_id:
        raise HTTPException(400, "Нельзя объединить договор сам с собой")
    source = (await db.execute(select(Contract).where(Contract.id == cid))).scalar_one_or_none()
    target = (await db.execute(select(Contract).where(Contract.id == target_id))).scalar_one_or_none()
    if not source or not target:
        raise HTTPException(404, "Договор не найден")
    # Move purchases from source to target
    linked = (await db.execute(select(Purchase).where(Purchase.contract_id == cid))).scalars().all()
    for p in linked:
        p.contract_id = target_id
        if target.number:
            p.contract_number = target.number
    await db.delete(source)
    await db.commit()
    return {"ok": True, "moved_purchases": len(linked)}


@router.post("/migrate-from-purchases")
async def migrate_contracts_from_purchases(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('contracts')),
):
    """Create Contract records from purchases.contract_number strings (skip existing)."""
    # Get all purchases with a contract_number set but no contract_id
    q = select(Purchase).where(
        Purchase.contract_number.isnot(None),
        Purchase.contract_number != "",
    )
    result = await db.execute(q)
    purchases = result.scalars().all()

    # Existing contract numbers
    existing_result = await db.execute(select(Contract.number))
    existing_numbers = {row[0] for row in existing_result.all() if row[0]}

    created = 0
    skipped = 0
    # Map: contract_number -> new Contract (for purchases to link to)
    new_contracts: dict[str, Contract] = {}

    for p in purchases:
        num = (p.contract_number or "").strip()
        if not num:
            continue
        if num in existing_numbers or num in new_contracts:
            skipped += 1
            continue
        c = Contract(
            number=num,
            date=p.contract_date if hasattr(p, "contract_date") else None,
            contract_type="single",
            subsidy_id=p.subsidy_id,
            status="active",
        )
        db.add(c)
        new_contracts[num] = c
        created += 1

    if new_contracts:
        await db.flush()
        # Link purchases to their new contracts
        for p in purchases:
            num = (p.contract_number or "").strip()
            if num in new_contracts and p.contract_id is None:
                p.contract_id = new_contracts[num].id

    await db.commit()
    return {"created": created, "skipped": skipped}


@router.post("/bulk-enrich-from-purchases", dependencies=[Depends(require_role('admin'))])
async def bulk_enrich_contracts_from_purchases(db: AsyncSession = Depends(get_db)):
    """
    Two-phase batch operation для legacy:

    Phase 1 — create Contract для Purchase'ов с receipts (но без contract_id).
              Это покрывает авансовые импорты из Phase 27.1.4 эпохи.

    Phase 2 — enrich existing Contract'ы где ХОТЯ БЫ ОДНО optional поле NULL.
              Покрывает любые legacy договоры (созданные вручную или через миграцию).
    """
    # Phase 27.1.9: re-link Purchase.contract_id для Purchase'ов где contract_number
    # совпадает с Contract.number но contract_id NULL ИЛИ указывает на другой Contract.
    # Это закрывает gap когда auto-create Contract (Phase 27.1.4) и Purchase
    # разъехались (recompute / manual edit / прочее).
    from app.models.purchase import Purchase as _P2
    from app.models.contract import Contract as _C2
    from sqlalchemy import select as _s2

    purchases_with_num = (await db.execute(
        _s2(_P2).where(_P2.contract_number.isnot(None), _P2.contract_number != '')
    )).scalars().all()

    all_contracts_for_link = (await db.execute(_s2(_C2))).scalars().all()
    contract_by_number: dict = {}
    for c_iter in all_contracts_for_link:
        if c_iter.number:
            contract_by_number.setdefault(c_iter.number.strip(), []).append(c_iter)

    purchases_linked = 0
    for p_iter in purchases_with_num:
        num = (p_iter.contract_number or '').strip()
        if not num:
            continue
        candidates = contract_by_number.get(num, [])
        if not candidates:
            continue
        best = None
        if p_iter.contractor_id:
            best = next((c_c for c_c in candidates if c_c.contractor_id == p_iter.contractor_id), None)
        if not best:
            best = candidates[0]
        if p_iter.contract_id != best.id:
            p_iter.contract_id = best.id
            purchases_linked += 1

    from app.models.purchase_receipt import PurchaseReceipt as _PR
    rows_result = await db.execute(
        select(Purchase).join(_PR, _PR.purchase_id == Purchase.id)
        .where(Purchase.contract_id.is_(None), Purchase.contractor_id.isnot(None))
        .distinct()
    )
    rows = rows_result.scalars().all()

    created = 0
    for p in rows:
        # Idempotency guard: если уже есть Contract с таким же contractor_id + subsidy_id
        # и number = ожидаемому значению — пропустить
        expected_number = str(p.purchase_number) if p.purchase_number else f"AVANS-{p.id}"
        existing_q = await db.execute(
            select(Contract).where(
                Contract.number == expected_number,
                Contract.contractor_id == p.contractor_id,
            ).limit(1)
        )
        if existing_q.scalar_one_or_none():
            continue
        # ПРАВИЛО №6 (2026-09-07, волна 4b-2c): та же замена truthy-цепочки, что и
        # в _enrich_contract_from_purchases выше — contract_amount() с фолбэком на
        # purchase_amounts().plan, а не `total_nmck or contract_price or planned_total_price`.
        from app.models.contract_item import ContractItem as _CI3
        from app.services.purchase_amounts import contract_amount as _contract_amount3, purchase_amounts as _purchase_amounts3
        _ci_total3 = (await db.execute(
            select(func.sum(_CI3.total)).where(_CI3.purchase_id == p.id)
        )).scalar_one_or_none()
        _max_amount3 = _contract_amount3(p, contract_items_total=_ci_total3)
        if _max_amount3 is None:
            _max_amount3 = _purchase_amounts3(p).plan
        new_contract = Contract(
            contractor_id=p.contractor_id,
            subsidy_id=p.subsidy_id,
            contract_type='single',
            number=expected_number,
            date=p.created_at.date() if getattr(p, 'created_at', None) else None,
            status='active',
            # Phase 27.1.5: заполнить ВСЕ доступные поля из Purchase
            subject=p.subject or str(p.purchase_number or ''),
            max_amount=_max_amount3,
            start_date=p.contract_date,
            end_date=p.execution_term,
            purchase_method=p.purchase_method if p.purchase_method in ('single', 'competitive') else 'single',
            item_type=p.item_type or 'товар',
        )
        db.add(new_contract)
        await db.flush()
        p.contract_id = new_contract.id
        created += 1
    # Phase 27.1.6: enrich existing Contracts где ХОТЯ БЫ ОДНО optional поле NULL
    from sqlalchemy import or_
    from app.models.contract import Contract as _C
    from app.routers.contracts import _enrich_contract_from_purchases
    contracts_to_enrich = (await db.execute(
        select(_C).where(
            or_(
                _C.subject.is_(None),
                _C.max_amount.is_(None),
                _C.start_date.is_(None),
                _C.end_date.is_(None),
                _C.purchase_method.is_(None),
                _C.item_type.is_(None),
            )
        )
    )).scalars().all()
    enriched = 0
    for c in contracts_to_enrich:
        filled_count = await _enrich_contract_from_purchases(c, db)
        if filled_count > 0:
            enriched += 1
    # Phase 27.1.8: расширенный relink orphan ContractItem.source_item_id с fallback'ами
    from app.models.contract_item import ContractItem as _CI
    from app.models.purchase_item import PurchaseItem as _PI
    from sqlalchemy import select as _select, func as _func

    orphans_q = await db.execute(_select(_CI).where(_CI.source_item_id.isnot(None)))
    orphans_all = orphans_q.scalars().all()
    existing_pi_ids = set((await db.execute(_select(_PI.id))).scalars().all())
    orphans = [ci for ci in orphans_all if ci.source_item_id not in existing_pi_ids]

    relinked = 0
    for ci in orphans:
        if not ci.purchase_id:
            continue

        candidate = None

        # Pass 1: exact name match (был в 27.1.7)
        if ci.name:
            candidate = (await db.execute(
                _select(_PI).where(
                    _PI.purchase_id == ci.purchase_id,
                    _PI.item_name == ci.name,
                ).limit(1)
            )).scalar_one_or_none()

        # Pass 2: case-insensitive trimmed match
        if not candidate and ci.name:
            normalized_ci_name = ci.name.strip().lower()
            candidate = (await db.execute(
                _select(_PI).where(
                    _PI.purchase_id == ci.purchase_id,
                    _func.lower(_func.trim(_PI.item_name)) == normalized_ci_name,
                ).limit(1)
            )).scalar_one_or_none()

        # Pass 3: 1-to-1 fallback — если у Purchase ровно один PI и один orphan CI с тем же purchase_id, безусловно связать
        if not candidate:
            all_pi_in_purchase = (await db.execute(
                _select(_PI).where(_PI.purchase_id == ci.purchase_id)
            )).scalars().all()
            all_ci_in_purchase_orphan = [
                o for o in orphans
                if o.purchase_id == ci.purchase_id
            ]
            if len(all_pi_in_purchase) == 1 and len(all_ci_in_purchase_orphan) == 1:
                candidate = all_pi_in_purchase[0]

        # Pass 4: match по qty + unit_price (если совпадают точно)
        if not candidate and ci.quantity is not None and ci.unit_price is not None:
            candidate = (await db.execute(
                _select(_PI).where(
                    _PI.purchase_id == ci.purchase_id,
                    _PI.quantity == ci.quantity,
                    _PI.unit_price == ci.unit_price,
                ).limit(1)
            )).scalar_one_or_none()

        if candidate:
            ci.source_item_id = candidate.id
            relinked += 1

    # Phase 27.1.17: enrich ContractItem.vat_rate из связанной PurchaseItem (для legacy без vat_rate)
    from app.models.contract_item import ContractItem as _CI_vat
    from app.models.purchase_item import PurchaseItem as _PI_vat
    ci_no_vat = (await db.execute(
        _select(_CI_vat).where(_CI_vat.vat_rate.is_(None), _CI_vat.source_item_id.isnot(None))
    )).scalars().all()
    vat_filled = 0
    for ci in ci_no_vat:
        pi = await db.get(_PI_vat, ci.source_item_id)
        if pi and pi.vat_rate:
            ci.vat_rate = pi.vat_rate
            vat_filled += 1

    await db.commit()
    return {
        "created": created,
        "scanned_purchases": len(rows),
        "enriched_existing": enriched,
        "scanned_contracts": len(contracts_to_enrich),
        "relinked_orphans": relinked,
        "purchases_linked": purchases_linked,
        "vat_filled": vat_filled,
    }


@router.post("/backfill-from-receipts", deprecated=True, dependencies=[Depends(require_role('admin'))])
async def backfill_from_receipts_legacy(db: AsyncSession = Depends(get_db)):
    """Deprecated alias. Use /bulk-enrich-from-purchases."""
    return await bulk_enrich_contracts_from_purchases(db)
