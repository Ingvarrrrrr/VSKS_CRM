"""POST /api/purchases/{pid}/correction, GET /api/purchases/{pid}/corrections
и POST /api/purchases/{pid}/return-to-draft-wish.

Под-роутер purchases.py (Правило №5), подключается `router.include_router
(purchase_correction_router)` БЕЗ своего prefix — routes.py не трогается.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.object_visibility import ensure_purchase_visible
from app.database import get_db
from app.models.event import Event
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_item import PurchaseItem
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.feo_effective_category import effective_item_feo_category_id
from app.services.feo_plan import build_category_path
from app.services.payroll_category_guard import assert_no_goods_in_payroll
from app.services.plan_autoassign import auto_assign_planned_items, deactivate_if_orphaned
from app.services.purchase_correction_service import (
    check_correction_excess,
    ensure_can_correct,
    return_purchase_to_draft_wish_core,
)
from app.services.purchase_feo_checks import _category_within

router = APIRouter(tags=["purchase-correction"])


class PurchaseItemCorrectionIn(BaseModel):
    id: int
    feo_category_id: Optional[int] = None
    feo_planned_item_id: Optional[int] = None


class PurchaseCorrectionIn(BaseModel):
    feo_category_id: Optional[int] = None
    feo_per_item: Optional[bool] = None
    event_id: Optional[int] = None
    items: Optional[list[PurchaseItemCorrectionIn]] = None
    comment: Optional[str] = None
    allow_excess: bool = False


class ReturnToDraftWishIn(BaseModel):
    comment: Optional[str] = None


async def _build_cat_path_map(
    db: AsyncSession, cat_ids: set[int], subsidy_id: Optional[int],
) -> dict[int, str]:
    cats: list[FeoCategory] = []
    if subsidy_id:
        cats.extend((await db.execute(
            select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
        )).scalars().all())
    cat_by_id = {c.id: c for c in cats}
    missing = {cid for cid in cat_ids if cid is not None and cid not in cat_by_id}
    if missing:
        extra_cats = (await db.execute(
            select(FeoCategory).where(FeoCategory.id.in_(missing))
        )).scalars().all()
        for c in extra_cats:
            cat_by_id[c.id] = c
    return {cid: build_category_path(cat_by_id[cid], cat_by_id) for cid in cat_by_id}


async def _build_corrections_summary(p: Purchase, db: AsyncSession) -> dict:
    events = (await db.execute(
        select(PurchaseEvent)
        .where(
            PurchaseEvent.purchase_id == p.id,
            PurchaseEvent.event_type == "purchase_correction",
        )
        .order_by(PurchaseEvent.created_at.asc(), PurchaseEvent.id.asc())
    )).scalars().all()

    user_ids = {ev.user_id for ev in events if ev.user_id is not None}
    user_names: dict[int, str] = {}
    if user_ids:
        u_rows = (await db.execute(
            select(User.id, User.full_name, User.username).where(User.id.in_(user_ids))
        )).all()
        user_names = {uid: (full_name or username) for uid, full_name, username in u_rows}

    cat_paths = await _build_cat_path_map(
        db,
        {p.feo_category_id} if p.feo_category_id is not None else set(),
        p.subsidy_id,
    )
    current_event_name: Optional[str] = None
    if p.event_id:
        ev_obj = await db.get(Event, p.event_id)
        if ev_obj is not None:
            current_event_name = ev_obj.name

    current_feo_category_name: Optional[str] = (
        "Разные категории для каждого товара"
        if bool(getattr(p, "feo_per_item", False))
        else (cat_paths.get(p.feo_category_id) if p.feo_category_id else None)
    )

    category_corrected = False
    event_corrected = False
    planned_corrected = False
    initial_feo_category_name: Optional[str] = None
    initial_event_name: Optional[str] = None
    history: list[dict] = []

    for ev in events:
        d = ev.data or {}
        cat_changed = bool(d.get("category_changed"))
        ev_changed = bool(d.get("event_changed"))
        items_changes = list(d.get("items_changes") or [])
        has_cat_or_item_cat = cat_changed or any(
            ch.get("old_feo_category_id") != ch.get("new_feo_category_id")
            for ch in items_changes
        )
        if has_cat_or_item_cat:
            category_corrected = True
            if initial_feo_category_name is None:
                if d.get("old_feo_per_item"):
                    initial_feo_category_name = "Разные категории для каждого товара"
                else:
                    initial_feo_category_name = d.get("old_feo_category_name")
        if items_changes:
            planned_corrected = True
        if ev_changed:
            event_corrected = True
            if initial_event_name is None and "old_event_name" in d:
                initial_event_name = d.get("old_event_name")

        history.append({
            "id": ev.id,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "user_id": ev.user_id,
            "user_name": user_names.get(ev.user_id, "Пользователь") if ev.user_id else "Система",
            "comment": d.get("comment"),
            "category_changed": cat_changed,
            "old_feo_category_id": d.get("old_feo_category_id"),
            "new_feo_category_id": d.get("new_feo_category_id"),
            "old_feo_category_name": d.get("old_feo_category_name"),
            "new_feo_category_name": d.get("new_feo_category_name"),
            "old_feo_per_item": bool(d.get("old_feo_per_item", False)),
            "new_feo_per_item": bool(d.get("new_feo_per_item", False)),
            "items_changes": items_changes,
            "event_changed": ev_changed,
            "old_event_id": d.get("old_event_id"),
            "new_event_id": d.get("new_event_id"),
            "old_event_name": d.get("old_event_name"),
            "new_event_name": d.get("new_event_name"),
        })

    history.reverse()
    return {
        "category_corrected": category_corrected,
        "event_corrected": event_corrected,
        "planned_corrected": planned_corrected,
        "initial_feo_category_name": initial_feo_category_name,
        "current_feo_category_name": current_feo_category_name,
        "initial_event_name": initial_event_name,
        "current_event_name": current_event_name,
        "history": history,
    }


@router.get("/{pid}/corrections")
async def get_purchase_corrections(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ensure_purchase_visible(current_user, pid, db)
    p = await db.get(Purchase, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Закупка не найдена")
    return await _build_corrections_summary(p, db)


@router.post("/{pid}/return-to-draft-wish")
async def return_purchase_to_draft_wish(
    pid: int,
    body: ReturnToDraftWishIn = ReturnToDraftWishIn(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = await db.get(Purchase, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Закупка не найдена")
    await ensure_can_correct(p, current_user, db)
    return await return_purchase_to_draft_wish_core(p, body.comment, db, current_user)


@router.post("/{pid}/correction")
async def apply_purchase_correction(
    pid: int,
    body: PurchaseCorrectionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = await db.get(Purchase, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="Закупка не найдена")
    await ensure_can_correct(p, current_user, db)

    p_items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id).order_by(PurchaseItem.id)
    )).scalars().all()
    p_items_by_id = {it.id: it for it in p_items}

    items_in_by_id: dict[int, PurchaseItemCorrectionIn] = {}
    if body.items is not None:
        for item_in in body.items:
            if item_in.id not in p_items_by_id:
                raise HTTPException(status_code=400, detail=f"Позиция #{item_in.id} не принадлежит закупке #{p.id}")
            items_in_by_id[item_in.id] = item_in

    old_header_cat_id = p.feo_category_id
    old_per_item = bool(getattr(p, "feo_per_item", False))
    old_event_id = p.event_id
    old_items_snap = {
        it.id: {
            "feo_category_id": effective_item_feo_category_id(old_per_item, old_header_cat_id, it.feo_category_id),
            "feo_planned_item_id": it.feo_planned_item_id,
            "name": it.item_name,
        }
        for it in p_items
    }

    if "event_id" in body.model_fields_set:
        if body.event_id is not None:
            ev = await db.get(Event, body.event_id)
            if ev is None:
                raise HTTPException(status_code=404, detail="Мероприятие не найдено")
            if p.subsidy_id and ev.subsidy_id != p.subsidy_id:
                raise HTTPException(status_code=400, detail="Мероприятие относится к другой субсидии")
        p.event_id = body.event_id

    if "feo_per_item" in body.model_fields_set and body.feo_per_item is not None:
        p.feo_per_item = bool(body.feo_per_item)
    per_item_mode = bool(getattr(p, "feo_per_item", False))

    if "feo_category_id" in body.model_fields_set:
        if body.feo_category_id is not None:
            cat_obj = await db.get(FeoCategory, body.feo_category_id)
            if cat_obj is None:
                raise HTTPException(status_code=404, detail="Категория ФЭО не найдена")
            if p.subsidy_id and cat_obj.subsidy_id != p.subsidy_id:
                raise HTTPException(status_code=400, detail="Категория ФЭО относится к другой субсидии")
        p.feo_category_id = body.feo_category_id

    if not per_item_mode:
        if p.feo_category_id is None and body.feo_per_item is False:
            raise HTTPException(status_code=422, detail="Выберите общую категорию ФЭО для закупки")
        if p.feo_category_id is not None:
            for pi in p_items:
                pi.feo_category_id = p.feo_category_id
    else:
        for pi in p_items:
            item_in = items_in_by_id.get(pi.id)
            if item_in is not None and "feo_category_id" in item_in.model_fields_set:
                if item_in.feo_category_id is not None:
                    c_obj = await db.get(FeoCategory, item_in.feo_category_id)
                    if c_obj is None:
                        raise HTTPException(status_code=404, detail=f"Категория ФЭО #{item_in.feo_category_id} не найдена")
                    if p.subsidy_id and c_obj.subsidy_id != p.subsidy_id:
                        raise HTTPException(status_code=400, detail="Категория ФЭО позиции относится к другой субсидии")
                pi.feo_category_id = item_in.feo_category_id
            elif pi.feo_category_id is None and old_header_cat_id is not None:
                pi.feo_category_id = old_header_cat_id
        distinct_cats = {pi.feo_category_id for pi in p_items if pi.feo_category_id is not None}
        p.feo_category_id = next(iter(distinct_cats)) if len(distinct_cats) == 1 else None

    for pi in p_items:
        eff_cid = effective_item_feo_category_id(per_item_mode, p.feo_category_id, pi.feo_category_id)
        if eff_cid is not None:
            await assert_no_goods_in_payroll(db, eff_cid, [pi])

    old_fpis_to_check: dict[int, FeoPlannedItem] = {}
    for pi in p_items:
        eff_cid = effective_item_feo_category_id(per_item_mode, p.feo_category_id, pi.feo_category_id)
        item_in = items_in_by_id.get(pi.id)
        old_fpi_id = old_items_snap[pi.id]["feo_planned_item_id"]
        fpi_explicit = item_in is not None and ("feo_planned_item_id" in item_in.model_fields_set)

        if fpi_explicit:
            new_fpi_id = item_in.feo_planned_item_id
            if new_fpi_id is not None:
                target_fpi = await db.get(FeoPlannedItem, new_fpi_id)
                if target_fpi is None:
                    raise HTTPException(status_code=404, detail="Выбранная плановая позиция не найдена")
                if not target_fpi.is_active:
                    raise HTTPException(status_code=409, detail=f"Плановая позиция «{target_fpi.name}» неактивна")
                if eff_cid is not None and not await _category_within(db, target_fpi.feo_category_id, eff_cid):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Плановая позиция «{target_fpi.name}» относится к другой категории ФЭО",
                    )
                pi.feo_planned_item_id = target_fpi.id
                pi.over_plan = False
                pi.from_plan = not bool(target_fpi.auto_created)
            else:
                pi.feo_planned_item_id = None
                pi.over_plan = False
                pi.from_plan = False
            if old_fpi_id is not None and old_fpi_id != pi.feo_planned_item_id:
                old_fpi = await db.get(FeoPlannedItem, old_fpi_id)
                if old_fpi is not None:
                    old_fpis_to_check[old_fpi.id] = old_fpi
        elif old_fpi_id is not None:
            cur_fpi = await db.get(FeoPlannedItem, old_fpi_id)
            if cur_fpi is not None and eff_cid is not None and not await _category_within(
                db, cur_fpi.feo_category_id, eff_cid
            ):
                pi.feo_planned_item_id = None
                pi.over_plan = False
                pi.from_plan = False
                old_fpis_to_check[cur_fpi.id] = cur_fpi

    linked_wis: dict[int, WishItem] = {}
    if p.wish_id:
        wish = await db.get(Wish, p.wish_id)
        if wish is not None:
            wish.feo_category_id = p.feo_category_id
            wish.feo_per_item = per_item_mode
            wish.event_id = p.event_id
        wi_ids = {pi.wish_item_id for pi in p_items if pi.wish_item_id is not None}
        if wi_ids:
            wi_rows = (await db.execute(select(WishItem).where(WishItem.id.in_(wi_ids)))).scalars().all()
            linked_wis = {wi.id: wi for wi in wi_rows}
            for pi in p_items:
                if pi.wish_item_id in linked_wis:
                    wi = linked_wis[pi.wish_item_id]
                    wi.feo_category_id = pi.feo_category_id
                    wi.feo_planned_item_id = pi.feo_planned_item_id
                    wi.from_plan = pi.from_plan
                    wi.over_plan = pi.over_plan

    await db.flush()
    for old_fpi in old_fpis_to_check.values():
        await deactivate_if_orphaned(db, old_fpi)

    await auto_assign_planned_items(
        p_items,
        p.feo_category_id,
        db,
        note=f"корректировкой закупки {p.registry_number or f'№{p.id}'}",
        per_item_mode=per_item_mode,
    )

    if linked_wis:
        for pi in p_items:
            if pi.wish_item_id in linked_wis:
                wi = linked_wis[pi.wish_item_id]
                wi.feo_category_id = pi.feo_category_id
                wi.feo_planned_item_id = pi.feo_planned_item_id
                wi.over_plan = pi.over_plan

    await db.flush()

    # Сбор изменений и контроль сумм при смене категории ФЭО / плановой позиции
    all_cat_ids = {old_header_cat_id, p.feo_category_id}
    all_fpi_ids: set[int] = set()
    touched_cat_ids: set[int] = set()
    for pi in p_items:
        snap = old_items_snap[pi.id]
        old_eff_cid = snap["feo_category_id"]
        new_eff_cid = effective_item_feo_category_id(per_item_mode, p.feo_category_id, pi.feo_category_id)
        all_cat_ids.update((old_eff_cid, new_eff_cid))
        if snap["feo_planned_item_id"] is not None:
            all_fpi_ids.add(snap["feo_planned_item_id"])
        if pi.feo_planned_item_id is not None:
            all_fpi_ids.add(pi.feo_planned_item_id)
        if new_eff_cid is not None and (
            old_eff_cid != new_eff_cid or snap["feo_planned_item_id"] != pi.feo_planned_item_id
        ):
            touched_cat_ids.add(new_eff_cid)

    if touched_cat_ids:
        await check_correction_excess(
            db, p, p_items, touched_cat_ids, bool(body.allow_excess), current_user,
        )

    cat_paths = await _build_cat_path_map(db, {c for c in all_cat_ids if c is not None}, p.subsidy_id)
    fpi_names: dict[int, str] = {}
    if all_fpi_ids:
        fpi_rows = (await db.execute(
            select(FeoPlannedItem.id, FeoPlannedItem.name).where(FeoPlannedItem.id.in_(all_fpi_ids))
        )).all()
        fpi_names = {fid: name for fid, name in fpi_rows}

    items_changes: list[dict] = []
    for pi in p_items:
        snap = old_items_snap[pi.id]
        old_eff_cid = snap["feo_category_id"]
        new_eff_cid = effective_item_feo_category_id(per_item_mode, p.feo_category_id, pi.feo_category_id)
        old_fpi_id = snap["feo_planned_item_id"]
        new_fpi_id = pi.feo_planned_item_id
        if old_eff_cid != new_eff_cid or old_fpi_id != new_fpi_id:
            items_changes.append({
                "item_id": pi.id,
                "item_name": pi.item_name,
                "old_feo_category_id": old_eff_cid,
                "old_feo_category_name": cat_paths.get(old_eff_cid) if old_eff_cid else None,
                "new_feo_category_id": new_eff_cid,
                "new_feo_category_name": cat_paths.get(new_eff_cid) if new_eff_cid else None,
                "old_planned_item_id": old_fpi_id,
                "old_planned_item_name": fpi_names.get(old_fpi_id) if old_fpi_id else None,
                "new_planned_item_id": new_fpi_id,
                "new_planned_item_name": fpi_names.get(new_fpi_id) if new_fpi_id else None,
            })

    category_changed = (
        old_header_cat_id != p.feo_category_id
        or old_per_item != per_item_mode
        or any(ch["old_feo_category_id"] != ch["new_feo_category_id"] for ch in items_changes)
    )
    event_changed = old_event_id != p.event_id

    if category_changed or event_changed or items_changes:
        old_ev_name = None
        new_ev_name = None
        if event_changed:
            if old_event_id:
                oe = await db.get(Event, old_event_id)
                old_ev_name = oe.name if oe else f"#{old_event_id}"
            if p.event_id:
                ne = await db.get(Event, p.event_id)
                new_ev_name = ne.name if ne else f"#{p.event_id}"

        db.add(PurchaseEvent(
            purchase_id=p.id,
            user_id=current_user.id,
            event_type="purchase_correction",
            data={
                "comment": (body.comment or "").strip() or None,
                "category_changed": category_changed,
                "old_feo_category_id": old_header_cat_id,
                "new_feo_category_id": p.feo_category_id,
                "old_feo_category_name": (
                    "Разные категории для каждого товара"
                    if old_per_item else (cat_paths.get(old_header_cat_id) if old_header_cat_id else None)
                ),
                "new_feo_category_name": (
                    "Разные категории для каждого товара"
                    if per_item_mode else (cat_paths.get(p.feo_category_id) if p.feo_category_id else None)
                ),
                "old_feo_per_item": old_per_item,
                "new_feo_per_item": per_item_mode,
                "items_changes": items_changes,
                "event_changed": event_changed,
                "old_event_id": old_event_id,
                "new_event_id": p.event_id,
                "old_event_name": old_ev_name,
                "new_event_name": new_ev_name,
            },
        ))

    await db.commit()
    return await _build_corrections_summary(p, db)
