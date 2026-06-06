"""Wish members router — participant consent flow (mirror of purchase_members).

Endpoints:
  GET    /api/wishes/{wid}/members               — list participants
  POST   /api/wishes/{wid}/members               — add participant (with consent flow)
  DELETE /api/wishes/{wid}/members/{user_id}     — remove participant
  POST   /api/wishes/{wid}/members/consent       — accept/decline own consent
  GET    /api/wishes/members/pending-consent     — list wishes where current user has pending consent
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_member import WishMember
from app.services.consent import compute_consent_needed

logger = logging.getLogger(__name__)

# NOTE: prefix matches wishes.router so FastAPI resolves all /api/wishes/* paths together.
# Static path /members/pending-consent is registered in a router with prefix /api/wishes/members
# to avoid collision with /{wid:int} catch-all in wishes.router.
router = APIRouter(prefix="/api/wishes", tags=["wish-members"])
# Separate prefix for the static pending-consent endpoint
pending_router = APIRouter(prefix="/api/wishes/members", tags=["wish-members"])


def _member_dict(m: WishMember) -> dict:
    return {
        "id": m.id,
        "wish_id": m.wish_id,
        "user_id": m.user_id,
        "role": m.role,
        "added_by_id": m.added_by_id,
        "consent_pending": m.consent_pending,
        "username": (m.user.username if m.user else None),
        "full_name": (m.user.full_name if m.user else None),
        "added_by_name": (
            (m.added_by.full_name or m.added_by.username) if m.added_by else None
        ),
    }


async def _get_wish_or_403(wid: int, current_user: User, db: AsyncSession) -> Wish:
    """Load wish and check org access."""
    wish = await db.get(Wish, wid)
    if wish is None:
        raise HTTPException(404, "Заявка не найдена")
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к этой заявке")
    return wish


# ---------------------------------------------------------------------------
# GET /api/wishes/{wid}/members
# ---------------------------------------------------------------------------

@router.get("/{wid}/members")
async def list_wish_members(
    wid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_wish_or_403(wid, current_user, db)
    result = await db.execute(
        select(WishMember).where(WishMember.wish_id == wid)
    )
    return [_member_dict(m) for m in result.scalars().all()]


# ---------------------------------------------------------------------------
# POST /api/wishes/{wid}/members
# ---------------------------------------------------------------------------

@router.post("/{wid}/members", status_code=201)
async def add_wish_member(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    user_id = int(body.get("user_id", 0))
    role = body.get("role", "participant")

    if not user_id:
        raise HTTPException(422, "user_id обязателен")

    # Check target user exists
    target_user = await db.get(User, user_id)
    if target_user is None:
        raise HTTPException(404, "Пользователь не найден")

    # Upsert
    existing = await db.execute(
        select(WishMember).where(
            WishMember.wish_id == wid,
            WishMember.user_id == user_id,
        )
    )
    m = existing.scalar_one_or_none()
    is_new = m is None

    if m:
        # Already exists — update role, return 200 (not 409, mirrors purchase pattern)
        m.role = role
    else:
        # Compute consent
        consent_ids = await compute_consent_needed(current_user, [user_id], db)
        consent_pending = user_id in consent_ids

        m = WishMember(
            wish_id=wid,
            user_id=user_id,
            role=role,
            added_by_id=current_user.id,
            consent_pending=consent_pending,
        )
        db.add(m)

    await db.flush()
    await db.commit()
    await db.refresh(m)

    # Notifications (only for new entries, only if target != adder)
    if is_new and target_user.id != current_user.id:
        try:
            if m.consent_pending:
                from app.notifications import notify_wish_consent_required
                await notify_wish_consent_required(
                    wish, target_user, current_user.full_name or current_user.username
                )
            else:
                from app.notifications import notify_wish_member_added
                await notify_wish_member_added(
                    wish, target_user, current_user.full_name or current_user.username
                )
        except Exception as e:
            logger.warning("Wish member notify failed: %s", e)

    return _member_dict(m)


# ---------------------------------------------------------------------------
# DELETE /api/wishes/{wid}/members/{user_id}
# ---------------------------------------------------------------------------

@router.delete("/{wid}/members/{user_id}")
async def remove_wish_member(
    wid: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_wish_or_403(wid, current_user, db)
    result = await db.execute(
        select(WishMember).where(
            WishMember.wish_id == wid,
            WishMember.user_id == user_id,
        )
    )
    m = result.scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /api/wishes/{wid}/members/consent?accept=bool
# ---------------------------------------------------------------------------

@router.post("/{wid}/members/consent")
async def wish_member_consent(
    wid: int,
    accept: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current user accepts or declines their pending consent to participate in a wish."""
    await _get_wish_or_403(wid, current_user, db)

    member_res = await db.execute(
        select(WishMember).where(
            WishMember.wish_id == wid,
            WishMember.user_id == current_user.id,
            WishMember.consent_pending == True,  # noqa: E712
        )
    )
    m = member_res.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Нет ожидающего запроса согласия")

    if accept:
        m.consent_pending = False
        await db.commit()
        # Notify adder
        if m.added_by_id and m.added_by_id != current_user.id:
            try:
                adder = await db.get(User, m.added_by_id)
                if adder:
                    from app.notifications import notify_user, _esc
                    wish = await db.get(Wish, wid)
                    title = _esc(getattr(wish, 'title', None) or f"Заявка #{wid}")
                    await notify_user(
                        adder,
                        f"✅ <b>{_esc(current_user.full_name or current_user.username)}</b> принял участие в заявке «{title}»"
                    )
            except Exception as e:
                logger.warning("Wish consent accept notify failed: %s", e)
        return {"status": "accepted", "wish_id": wid}
    else:
        added_by_id = m.added_by_id
        await db.delete(m)
        await db.commit()
        # Notify adder
        if added_by_id and added_by_id != current_user.id:
            try:
                adder = await db.get(User, added_by_id)
                if adder:
                    from app.notifications import notify_user, _esc
                    wish = await db.get(Wish, wid)
                    title = _esc(getattr(wish, 'title', None) or f"Заявка #{wid}")
                    await notify_user(
                        adder,
                        f"❌ <b>{_esc(current_user.full_name or current_user.username)}</b> отклонил участие в заявке «{title}»"
                    )
            except Exception as e:
                logger.warning("Wish consent decline notify failed: %s", e)
        return {"status": "declined", "wish_id": wid}


# ---------------------------------------------------------------------------
# GET /api/wishes/members/pending-consent
# Static path — registered via pending_router (prefix /api/wishes/members)
# to avoid collision with /{wid:int} in wishes.router.
# Final URL: GET /api/wishes/members/pending-consent
# ---------------------------------------------------------------------------

@pending_router.get("/pending-consent")
async def wish_pending_consent(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List wishes where current user has a pending consent invitation."""
    result = await db.execute(
        select(WishMember).where(
            WishMember.user_id == current_user.id,
            WishMember.consent_pending == True,  # noqa: E712
        )
    )
    members = result.scalars().all()

    if not members:
        return []

    wish_ids = [m.wish_id for m in members]
    wishes_res = await db.execute(
        select(Wish).where(Wish.id.in_(wish_ids))
    )
    wish_map = {w.id: w for w in wishes_res.scalars().all()}

    out = []
    for m in members:
        w = wish_map.get(m.wish_id)
        if w is None:
            continue
        out.append({
            "wish_id": m.wish_id,
            "wish_member_id": m.id,
            "title": getattr(w, 'title', None) or f"Заявка #{m.wish_id}",
            "org_id": w.org_id,
            "status": w.status,
            "added_by_name": (
                (m.added_by.full_name or m.added_by.username) if m.added_by else None
            ),
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return out
