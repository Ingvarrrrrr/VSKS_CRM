"""POST /api/purchase-transfer/* — копирование закупок в другую субсидию
(превью сопоставления + применение) и GET .../links/{id} (связи копия↔оригинал).

Права: 'purchase.copy_to_subsidy' (app/startup/permission_seeds.py,
app/auth/permissions.py::SUBSIDY_GRANT_NON_GLOBAL) на ЦЕЛЕВУЮ субсидию —
app.auth.permissions.has_org_key, точечная проверка по subsidy_id (ПРАВИЛО
№6, та же функция, что и остальные орг-осознанные write-проверки). Обе
стороны (источник и цель) должны быть видимы пользователю —
app.auth.visibility.get_visible_subsidy_ids. Целевая субсидия должна быть
утверждена — app.services.subsidy_draft_guard.assert_subsidy_approved_for_binding
(та же проверка, что PATCH /purchases/{id}).

Логика переноса — app/services/purchase_transfer/ (match.py/copy_one.py/
merge_into.py), не повторяется здесь (ПРАВИЛО №6).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_transfer.copy_one import copy_to_subsidy
from app.services.purchase_transfer.match import build_purchase_key, classify
from app.services.purchase_transfer.merge_into import merge_into
from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding

router = APIRouter(prefix="/api/purchase-transfer", tags=["purchase-transfer"])

# Закупки, которые не участвуют в переносе («действующие» — тот же набор
# статусов, что scripts/fadm_sheet_load/pair_old_to_target.py::_active).
_INACTIVE_STATUSES = ("cancelled", "draft")


class PreviewRequest(BaseModel):
    source_subsidy_id: int
    target_subsidy_id: int
    purchase_ids: Optional[list[int]] = None


class ApplyItem(BaseModel):
    source_purchase_id: int
    action: str  # 'copy' | 'merge' | 'skip'
    target_purchase_id: Optional[int] = None


class ApplyRequest(BaseModel):
    target_subsidy_id: int
    items: list[ApplyItem]


async def _active_purchases(db: AsyncSession, subsidy_id: int, purchase_ids: Optional[list[int]] = None) -> list[Purchase]:
    conditions = [
        Purchase.subsidy_id == subsidy_id,
        Purchase.stopped_at.is_(None),
        Purchase.status.notin_(_INACTIVE_STATUSES),
    ]
    if purchase_ids is not None:
        conditions.append(Purchase.id.in_(purchase_ids))
    return list((await db.execute(
        select(Purchase).where(*conditions).order_by(Purchase.id)
    )).scalars().all())


async def _check_access(db: AsyncSession, user: User, source_subsidy_id: int, target_subsidy_id: int) -> tuple[Subsidy, Subsidy]:
    source = await db.get(Subsidy, source_subsidy_id)
    target = await db.get(Subsidy, target_subsidy_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND", "message": "Субсидия-источник не найдена"})
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "TARGET_NOT_FOUND", "message": "Целевая субсидия не найдена"})

    visible_ids = await get_visible_subsidy_ids(user, db, "subsidies")
    if visible_ids is not None:
        if source.id not in visible_ids:
            raise HTTPException(status_code=403, detail={"code": "SOURCE_NOT_VISIBLE", "message": "Субсидия-источник недоступна"})
        if target.id not in visible_ids:
            raise HTTPException(status_code=403, detail={"code": "TARGET_NOT_VISIBLE", "message": "Целевая субсидия недоступна"})

    if not await has_org_key(user, db, target.org_id, "purchase.copy_to_subsidy", subsidy_id=target.id):
        raise HTTPException(
            status_code=403,
            detail={"code": "NO_COPY_PERMISSION", "message": "Нет права копировать закупки в эту субсидию"},
        )
    await assert_subsidy_approved_for_binding(db, target.id)
    return source, target


async def _brief_map(db: AsyncSession, purchases: list[Purchase]) -> dict[int, dict]:
    """Brief для каждой закупки — батч-загрузка (без N+1): суммы/контрагенты/
    категории/карта «копия → оригинал» одним запросом каждая."""
    ids = [p.id for p in purchases]
    if not ids:
        return {}
    amounts = await load_purchase_amounts(db, ids)

    contractor_ids = {p.contractor_id for p in purchases if p.contractor_id}
    contractors: dict[int, Contractor] = {}
    if contractor_ids:
        rows = (await db.execute(select(Contractor).where(Contractor.id.in_(contractor_ids)))).scalars().all()
        contractors = {c.id: c for c in rows}

    user_ids = {p.assigned_user_id for p in purchases if p.assigned_user_id} | \
        {p.reimbursement_user_id for p in purchases if p.reimbursement_user_id}
    users: dict[int, User] = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u for u in rows}

    cat_ids = {p.feo_category_id for p in purchases if p.feo_category_id}
    cats: dict[int, str] = {}
    if cat_ids:
        rows = (await db.execute(select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids)))).all()
        cats = dict(rows)

    orig_ids = {p.copied_from_purchase_id for p in purchases if p.copied_from_purchase_id}
    orig_regs: dict[int, str] = {}
    if orig_ids:
        rows = (await db.execute(select(Purchase.id, Purchase.registry_number).where(Purchase.id.in_(orig_ids)))).all()
        orig_regs = dict(rows)

    briefs: dict[int, dict] = {}
    for p in purchases:
        contractor = contractors.get(p.contractor_id) if p.contractor_id else None
        employee = None
        who = p.reimbursement_user_id or p.assigned_user_id
        if who and who in users:
            employee = users[who].full_name
        amount = amounts[p.id].effective if p.id in amounts and amounts[p.id].effective is not None else None
        briefs[p.id] = {
            "id": p.id,
            "registry_number": p.registry_number,
            "subject": p.subject,
            "contractor_name": contractor.name if contractor else None,
            "contractor_inn": contractor.inn if contractor else None,
            "employee_name": employee,
            "purchase_method": p.purchase_method,
            "status": p.status,
            "amount": float(amount) if amount is not None else None,
            "feo_category_name": cats.get(p.feo_category_id) if p.feo_category_id else None,
            "copied_from_registry_number": orig_regs.get(p.copied_from_purchase_id) if p.copied_from_purchase_id else None,
        }
    return briefs


@router.post("/preview")
async def preview(
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source, target = await _check_access(db, current_user, body.source_subsidy_id, body.target_subsidy_id)

    source_purchases = await _active_purchases(db, source.id, body.purchase_ids)
    target_purchases = await _active_purchases(db, target.id)

    contractor_ids = {p.contractor_id for p in source_purchases + target_purchases if p.contractor_id}
    inns: dict[int, str] = {}
    if contractor_ids:
        rows = (await db.execute(select(Contractor.id, Contractor.inn).where(Contractor.id.in_(contractor_ids)))).all()
        inns = dict(rows)
    amounts = await load_purchase_amounts(db, [p.id for p in source_purchases + target_purchases])

    def _key(p: Purchase):
        amt = amounts[p.id].effective if p.id in amounts else None
        return build_purchase_key(p, contractor_inn=inns.get(p.contractor_id), effective_amount=amt)

    source_keys = [_key(p) for p in source_purchases]
    target_keys = [_key(p) for p in target_purchases]
    classification = classify(source_keys, target_keys)

    source_brief = await _brief_map(db, source_purchases)
    target_brief = await _brief_map(db, target_purchases)
    target_brief_by_id = target_brief

    rows = []
    for p in source_purchases:
        cls = classification.get(p.id)
        state = cls.state if cls else "none"
        match_brief = target_brief_by_id.get(cls.match_purchase_id) if cls and cls.match_purchase_id else None
        default_action = {"same": "skip", "amount_only": None, "none": "copy"}[state]
        rows.append({
            "source": source_brief[p.id],
            "state": state,
            "match": match_brief,
            "default_action": default_action,
        })

    return {
        "source_subsidy": {"id": source.id, "name": source.name},
        "target_subsidy": {"id": target.id, "name": target.name},
        "rows": rows,
        "target_purchases": [target_brief_by_id[p.id] for p in target_purchases],
    }


@router.post("/apply")
async def apply(
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await db.get(Subsidy, body.target_subsidy_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "TARGET_NOT_FOUND", "message": "Целевая субсидия не найдена"})

    visible_ids = await get_visible_subsidy_ids(current_user, db, "subsidies")
    if visible_ids is not None and target.id not in visible_ids:
        raise HTTPException(status_code=403, detail={"code": "TARGET_NOT_VISIBLE", "message": "Целевая субсидия недоступна"})
    if not await has_org_key(current_user, db, target.org_id, "purchase.copy_to_subsidy", subsidy_id=target.id):
        raise HTTPException(
            status_code=403,
            detail={"code": "NO_COPY_PERMISSION", "message": "Нет права копировать закупки в эту субсидию"},
        )
    await assert_subsidy_approved_for_binding(db, target.id)

    source_ids = {it.source_purchase_id for it in body.items}
    source_purchases = {p.id: p for p in (await db.execute(
        select(Purchase).where(Purchase.id.in_(source_ids))
    )).scalars().all()}

    copy_ids: list[int] = []
    merge_items: list[ApplyItem] = []
    skipped = 0
    for item in body.items:
        src = source_purchases.get(item.source_purchase_id)
        if src is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "SOURCE_PURCHASE_NOT_FOUND", "message": f"Закупка-источник id={item.source_purchase_id} не найдена"},
            )
        if visible_ids is not None and src.subsidy_id not in visible_ids:
            raise HTTPException(
                status_code=403,
                detail={"code": "SOURCE_NOT_VISIBLE", "message": f"Субсидия закупки id={src.id} недоступна"},
            )
        if item.action == "skip":
            skipped += 1
        elif item.action == "copy":
            copy_ids.append(item.source_purchase_id)
        elif item.action == "merge":
            if item.target_purchase_id is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "MERGE_NEEDS_TARGET", "message": "Чтобы дополнить закупку, выберите её пару в целевой субсидии"},
                )
            merge_items.append(item)
        else:
            raise HTTPException(status_code=422, detail={"code": "BAD_ACTION", "message": f"Неизвестное действие «{item.action}»"})

    copied = []
    warnings: list[str] = []
    outcomes = await copy_to_subsidy(db, copy_ids, target.id, current_user, warnings_out=warnings) if copy_ids else []
    for o in outcomes:
        copied.append({
            "source_id": o.source_id, "source_registry_number": o.source_registry_number,
            "new_id": o.new_id, "new_registry_number": o.new_registry_number,
        })

    merged = []
    for item in merge_items:
        src = source_purchases[item.source_purchase_id]
        tgt = await db.get(Purchase, item.target_purchase_id)
        if tgt is None or tgt.subsidy_id != target.id:
            raise HTTPException(
                status_code=422,
                detail={"code": "MERGE_TARGET_NOT_IN_SUBSIDY", "message": "Выбранная пара не найдена в целевой субсидии"},
            )
        result = await merge_into(db, src, tgt, current_user)
        merged.append({
            "source_id": result.source_id, "target_id": result.target_id,
            "target_registry_number": result.target_registry_number,
        })

    await db.commit()
    return {"copied": copied, "merged": merged, "skipped": skipped, "warnings": warnings}


@router.get("/links/{purchase_id}")
async def links(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = await db.get(Purchase, purchase_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "PURCHASE_NOT_FOUND", "message": "Закупка не найдена"})

    copied_from = None
    if p.copied_from_purchase_id:
        orig = await db.get(Purchase, p.copied_from_purchase_id)
        if orig is not None:
            subsidy = await db.get(Subsidy, orig.subsidy_id) if orig.subsidy_id else None
            copied_from = {
                "id": orig.id, "registry_number": orig.registry_number,
                "subsidy_id": orig.subsidy_id, "subsidy_name": subsidy.name if subsidy else None,
            }

    copy_rows = (await db.execute(
        select(Purchase).where(Purchase.copied_from_purchase_id == purchase_id)
    )).scalars().all()
    subsidy_ids = {c.subsidy_id for c in copy_rows if c.subsidy_id}
    subsidy_names: dict[int, str] = {}
    if subsidy_ids:
        rows = (await db.execute(select(Subsidy.id, Subsidy.name).where(Subsidy.id.in_(subsidy_ids)))).all()
        subsidy_names = dict(rows)

    copies = [
        {
            "id": c.id, "registry_number": c.registry_number,
            "subsidy_id": c.subsidy_id, "subsidy_name": subsidy_names.get(c.subsidy_id) if c.subsidy_id else None,
        }
        for c in copy_rows
    ]
    return {"copied_from": copied_from, "copies": copies}
