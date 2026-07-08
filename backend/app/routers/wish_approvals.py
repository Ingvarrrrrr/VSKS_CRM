"""Wish approvers router — многоуровневое согласование заявок с авто-каскадом.

Endpoints:
  GET    /api/wishes/{wid}/approvers                        — список согласующих
  POST   /api/wishes/{wid}/approvers/cascade                — построить восходящую цепочку
  POST   /api/wishes/{wid}/approvers                        — добавить согласующего вручную
  DELETE /api/wishes/{wid}/approvers/{approval_id}          — удалить согласующего (pending)
  POST   /api/wishes/{wid}/approvers/{approval_id}/decide   — согласовать/отклонить
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, MANAGER_ROLES, OWNER_ROLES
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.services.approval_chain import build_ascending_chain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wishes", tags=["wish-approvals"])


def _approval_dict(a: WishApproval) -> dict:
    return {
        "id": a.id,
        "wish_id": a.wish_id,
        "user_id": a.user_id,
        "order_num": a.order_num,
        "role_name": a.role_name,
        "full_name": a.approver_full_name,
        "is_auto": a.is_auto,
        "status": a.status,
        "comment": a.comment,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "decided_by_user_id": a.decided_by_user_id,
    }


async def _get_wish_or_403(wid: int, current_user: User, db: AsyncSession) -> Wish:
    wish = await db.get(Wish, wid)
    if wish is None:
        raise HTTPException(404, "Заявка не найдена")
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к этой заявке")
    return wish


def _is_saas(user: User) -> bool:
    return user.role in OWNER_ROLES


async def _load_approvals(wid: int, db: AsyncSession) -> list[WishApproval]:
    return (await db.execute(
        select(WishApproval).where(WishApproval.wish_id == wid).order_by(WishApproval.order_num)
    )).scalars().all()


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("/{wid}/approvers")
async def list_wish_approvers(
    wid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_wish_or_403(wid, current_user, db)
    rows = await _load_approvals(wid, db)
    return [_approval_dict(a) for a in rows]


# ── POST cascade ──────────────────────────────────────────────────────────────

@router.post("/{wid}/approvers/cascade")
async def cascade_wish_approvers(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Построить восходящую цепочку согласующих от отдела автора до top_user_id."""
    wish = await _get_wish_or_403(wid, current_user, db)
    top_user_id = int(body.get("top_user_id", 0))
    mode = body.get("mode", "sequential")
    if mode not in ("sequential", "parallel"):
        mode = "sequential"
    if not top_user_id:
        raise HTTPException(422, "top_user_id обязателен")

    author_id = wish.created_by or current_user.id
    chain = await build_ascending_chain(db, author_id, top_user_id, wish.org_id)
    if not chain:
        raise HTTPException(400, "Не удалось построить цепочку согласующих — проверьте иерархию отдела")

    # Replace existing auto rows (keep manual ones? — cascade пересобирает всю цепочку)
    for a in await _load_approvals(wid, db):
        await db.delete(a)
    await db.flush()

    created: list[WishApproval] = []
    for step in chain:
        a = WishApproval(
            wish_id=wid,
            user_id=step["user_id"],
            order_num=step["order_num"],
            role_name=step["role_name"],
            approver_full_name=step["full_name"],
            is_auto=True,
            status="pending",
        )
        db.add(a)
        created.append(a)

    wish.approval_mode = mode
    wish.status = "submitted"
    await db.commit()

    rows = await _load_approvals(wid, db)
    return {"approval_mode": mode, "approvers": [_approval_dict(a) for a in rows]}


# ── POST add manual ───────────────────────────────────────────────────────────

@router.post("/{wid}/approvers", status_code=201)
async def add_wish_approver(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    user_id = int(body.get("user_id", 0))
    if not user_id:
        raise HTTPException(422, "user_id обязателен")
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Пользователь не найден")

    existing = (await db.execute(
        select(WishApproval).where(
            WishApproval.wish_id == wid,
            WishApproval.user_id == user_id,
        )
    )).scalar_one_or_none()
    if existing:
        return _approval_dict(existing)

    max_order = (await db.execute(
        select(func.max(WishApproval.order_num)).where(WishApproval.wish_id == wid)
    )).scalar()
    next_order = (max_order + 1) if max_order is not None else 0

    a = WishApproval(
        wish_id=wid,
        user_id=user_id,
        order_num=next_order,
        role_name=body.get("role_name") or "Согласующий",
        approver_full_name=target.full_name or target.username,
        is_auto=False,
        status="pending",
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _approval_dict(a)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete("/{wid}/approvers/{approval_id}")
async def remove_wish_approver(
    wid: int,
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_wish_or_403(wid, current_user, db)
    a = await db.get(WishApproval, approval_id)
    if a and a.wish_id == wid:
        if a.status != "pending":
            raise HTTPException(400, "Нельзя удалить согласующего, который уже принял решение")
        await db.delete(a)
        await db.commit()
    return {"ok": True}


# ── POST decide ───────────────────────────────────────────────────────────────

@router.post("/{wid}/approvers/{approval_id}/decide")
async def decide_wish_approval(
    wid: int,
    approval_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    a = await db.get(WishApproval, approval_id)
    if a is None or a.wish_id != wid:
        raise HTTPException(404, "Согласующий не найден")

    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision должен быть 'approved' или 'rejected'")

    # Права: решать может сам назначенный согласующий или менеджер+/SaaS
    if not _is_saas(current_user) and current_user.role not in MANAGER_ROLES and a.user_id != current_user.id:
        raise HTTPException(403, "Решение может принять только назначенный согласующий или менеджер+")

    if a.status != "pending":
        raise HTTPException(400, f"По этому согласующему уже принято решение: {a.status}")

    # Sequential: нельзя согласовать, пока нижестоящие (меньший order_num) ещё pending
    if wish.approval_mode == "sequential":
        lower_pending = (await db.execute(
            select(func.count()).select_from(WishApproval).where(
                WishApproval.wish_id == wid,
                WishApproval.order_num < a.order_num,
                WishApproval.status == "pending",
            )
        )).scalar() or 0
        if lower_pending > 0:
            raise HTTPException(
                400,
                "Последовательное согласование: сначала должны согласовать нижестоящие в цепочке.",
            )

    a.status = decision
    a.comment = body.get("comment")
    a.decided_at = datetime.now(timezone.utc)
    a.decided_by_user_id = current_user.id
    await db.flush()

    creator = await db.get(User, wish.created_by) if wish.created_by else None
    decided_name = current_user.full_name or current_user.username

    if decision == "rejected":
        wish.status = "rejected"
        wish.rejection_reason = body.get("comment")
        await db.commit()
        if creator and creator.id != current_user.id:
            try:
                from app.notifications import notify_wish_rejected
                await notify_wish_rejected(wish, creator, decided_name, body.get("comment"))
            except Exception as e:
                logger.warning("notify_wish_rejected failed: %s", e)
    else:
        # approved — если все approved → заявка согласована
        remaining = (await db.execute(
            select(func.count()).select_from(WishApproval).where(
                WishApproval.wish_id == wid,
                WishApproval.status == "pending",
            )
        )).scalar() or 0
        if remaining == 0:
            wish.status = "approved"
            wish.approved_by = current_user.id
            await db.commit()
            if creator:
                try:
                    from app.notifications import notify_wish_approved
                    await notify_wish_approved(wish, creator)
                except Exception as e:
                    logger.warning("notify_wish_approved failed: %s", e)
        else:
            await db.commit()
            # sequential — уведомить следующего согласующего
            if wish.approval_mode == "sequential":
                nxt = (await db.execute(
                    select(WishApproval).where(
                        WishApproval.wish_id == wid,
                        WishApproval.status == "pending",
                    ).order_by(WishApproval.order_num).limit(1)
                )).scalar_one_or_none()
                if nxt and nxt.user_id:
                    try:
                        nxt_user = await db.get(User, nxt.user_id)
                        if nxt_user:
                            from app.notifications import notify_wish_approval_step
                            await notify_wish_approval_step(wish, nxt_user, decided_name)
                    except Exception as e:
                        logger.warning("notify_wish_approval_step failed: %s", e)

    rows = await _load_approvals(wid, db)
    return {"status": wish.status, "approvers": [_approval_dict(a) for a in rows]}
