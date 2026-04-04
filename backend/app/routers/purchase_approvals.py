from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_event import PurchaseEvent
from app.models.subsidy_approver import SubsidyApprover
from app.schemas.schemas import PurchaseApprovalOut, ApprovalDecisionRequest
from app.auth.jwt import get_current_user, ADMIN_ROLES, MANAGER_ROLES
from app.models.user import User
from typing import List
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["approvals"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _to_out(a: PurchaseApproval) -> dict:
    return {
        "id": a.id,
        "purchase_id": a.purchase_id,
        "subsidy_approver_id": a.subsidy_approver_id,
        "order_num": a.order_num,
        "role_name": a.role_name,
        "approver_full_name": a.approver_full_name,
        "user_id": a.user_id,
        "status": a.status,
        "comment": a.comment,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "decided_by_user_id": a.decided_by_user_id,
        "decided_by_username": a.decided_by_username,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "has_signature": bool(a.signature_data),
        "signature_algorithm": a.signature_algorithm,
    }


# ── 1. Start approval chain ─────────────────────────────────────────────────

@router.post("/purchases/{pid}/approvals/start", response_model=List[PurchaseApprovalOut])
async def start_approval(
    pid: int,
    body: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in MANAGER_ROLES:
        raise HTTPException(403, "Недостаточно прав")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not p.subsidy_id:
        raise HTTPException(422, "У закупки не указана субсидия")

    # Check purchase status — at least confirmed
    ALLOWED = ("confirmed", "work_in_progress")
    if p.status not in ALLOWED:
        raise HTTPException(422, f"Согласование можно запустить только в статусах: {', '.join(ALLOWED)}")

    # Check no active chain already
    if p.approval_status == "in_progress":
        raise HTTPException(422, "Согласование уже запущено")

    # Approval mode: sequential (default) or parallel
    approval_mode = body.get("approval_mode", "sequential")
    if approval_mode not in ("sequential", "parallel"):
        approval_mode = "sequential"
    # Sign type: electronic (default) or paper
    approval_sign_type = body.get("approval_sign_type", "electronic")
    if approval_sign_type not in ("electronic", "paper"):
        approval_sign_type = "electronic"
    # Optional deadline
    from datetime import date as _date
    approval_deadline_str = body.get("approval_deadline")
    approval_deadline = None
    if approval_deadline_str:
        try:
            approval_deadline = _date.fromisoformat(str(approval_deadline_str))
        except (ValueError, TypeError):
            pass

    # Clear old approvals if re-starting after rejection
    old = await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == pid)
    )
    for row in old.scalars().all():
        await db.delete(row)

    # Load subsidy approvers
    result = await db.execute(
        select(SubsidyApprover)
        .where(SubsidyApprover.subsidy_id == p.subsidy_id, SubsidyApprover.is_default == True)
        .order_by(SubsidyApprover.order_num)
    )
    approvers = result.scalars().all()
    if not approvers:
        raise HTTPException(422, "У субсидии нет согласующих (approvers). Добавьте их во вкладке «Субсидии».")

    # Create PurchaseApproval records
    created = []
    for sa in approvers:
        pa = PurchaseApproval(
            purchase_id=pid,
            subsidy_approver_id=sa.id,
            order_num=sa.order_num,
            role_name=sa.role_name,
            approver_full_name=sa.full_name,
            user_id=sa.user_id,
            status="pending",
            approval_deadline=approval_deadline,
        )
        db.add(pa)
        created.append(pa)

    p.approval_status = "in_progress"
    p.approval_mode = approval_mode
    p.approval_sign_type = approval_sign_type

    # Event
    db.add(PurchaseEvent(
        purchase_id=pid,
        user_id=current_user.id,
        event_type="approval_started",
        data={"approver_count": len(created), "mode": approval_mode, "sign_type": approval_sign_type},
    ))

    await db.commit()
    for pa in created:
        await db.refresh(pa)

    # Notify approvers
    try:
        from app.notifications import notify_approval_started, notify_approval_your_turn
        approver_users = []
        for pa in created:
            if pa.user_id:
                u = await db.get(User, pa.user_id)
                if u:
                    approver_users.append(u)
        await notify_approval_started(p, approver_users)
        # In sequential mode, notify first approver it's their turn
        if approval_mode != "parallel" and created:
            first = created[0]
            if first.user_id:
                first_user = await db.get(User, first.user_id)
                if first_user:
                    await notify_approval_your_turn(p, first_user)
    except Exception:
        pass  # notifications are best-effort

    return [_to_out(pa) for pa in created]


# ── 2. List approvals ───────────────────────────────────────────────────────

@router.get("/purchases/{pid}/approvals", response_model=List[PurchaseApprovalOut])
async def list_approvals(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PurchaseApproval)
        .where(PurchaseApproval.purchase_id == pid)
        .order_by(PurchaseApproval.order_num)
    )
    return [_to_out(a) for a in result.scalars().all()]


# ── 3. Decide (approve / reject) ────────────────────────────────────────────

@router.post("/purchases/{pid}/approvals/{aid}/decide", response_model=PurchaseApprovalOut)
async def decide_approval(
    pid: int,
    aid: int,
    body: ApprovalDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(422, "action must be 'approve' or 'reject'")

    if body.action == "reject" and not body.comment:
        raise HTTPException(422, "При отклонении необходимо указать комментарий")

    # Load approval
    approval = await db.get(PurchaseApproval, aid)
    if not approval or approval.purchase_id != pid:
        raise HTTPException(404, "Согласование не найдено")
    if approval.status != "pending":
        raise HTTPException(422, f"Это согласование уже обработано (статус: {approval.status})")

    # Check sequential order (only in sequential mode)
    purchase_for_mode = await db.get(Purchase, pid)
    if purchase_for_mode and purchase_for_mode.approval_mode != "parallel":
        result = await db.execute(
            select(PurchaseApproval)
            .where(PurchaseApproval.purchase_id == pid, PurchaseApproval.order_num < approval.order_num)
        )
        prior = result.scalars().all()
        for p in prior:
            if p.status not in ("approved", "skipped"):
                raise HTTPException(422, "Предыдущие согласующие ещё не приняли решение")

    # Authorization check
    is_admin = current_user.role in ADMIN_ROLES
    if approval.user_id:
        if approval.user_id != current_user.id and not is_admin:
            raise HTTPException(403, "Вы не являетесь назначенным согласующим")
    else:
        if not is_admin and current_user.role not in MANAGER_ROLES:
            raise HTTPException(403, "Согласующий не привязан к пользователю. Действие доступно менеджеру/админу.")

    # Электронная подпись
    if body.action == "approve" and body.sign_electronically:
        if not current_user.signature_image:
            raise HTTPException(422, "Электронная подпись не создана. Сначала нарисуйте подпись в профиле.")
        approval.signature_data = current_user.signature_image
        approval.signature_algorithm = "visual"

    # Record decision
    approval.status = body.action + ("d" if body.action == "approve" else "ed")  # approved / rejected
    approval.comment = body.comment
    approval.decided_at = datetime.now(timezone.utc)
    approval.decided_by_user_id = current_user.id
    approval.decided_by_username = current_user.username
    approval.decided_by_ip = _client_ip(request)

    # Load purchase
    purchase = await db.get(Purchase, pid)

    if body.action == "reject":
        purchase.approval_status = "rejected"
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="approval_rejected",
            data={
                "approver": approval.approver_full_name,
                "role": approval.role_name,
                "comment": body.comment,
            },
        ))
    else:
        # Check if all approved
        all_approvals = await db.execute(
            select(PurchaseApproval).where(PurchaseApproval.purchase_id == pid)
        )
        all_list = all_approvals.scalars().all()
        all_done = all(
            a.status in ("approved", "skipped") or a.id == aid
            for a in all_list
        )
        if all_done:
            purchase.approval_status = "approved"
            db.add(PurchaseEvent(
                purchase_id=pid,
                user_id=current_user.id,
                event_type="approval_completed",
                data={"total_approvers": len(all_list)},
            ))
        else:
            # Find next approver
            pending = [a for a in all_list if a.status == "pending" and a.id != aid]
            pending.sort(key=lambda x: x.order_num)
            next_approver = pending[0].approver_full_name if pending else None
            db.add(PurchaseEvent(
                purchase_id=pid,
                user_id=current_user.id,
                event_type="approval_step_completed",
                data={
                    "approver": approval.approver_full_name,
                    "next_approver": next_approver,
                },
            ))

    await db.commit()
    await db.refresh(approval)

    # Notifications
    try:
        from app.notifications import notify_approval_decided, notify_approval_your_turn, notify_approval_completed
        approver_name = approval.approver_full_name or current_user.full_name

        # Collect purchase members/creator to notify
        notify_users = []
        if purchase.created_by_id:
            creator = await db.get(User, purchase.created_by_id)
            if creator:
                notify_users.append(creator)

        await notify_approval_decided(
            purchase, approver_name, approval.status,
            comment=body.comment or "", notify_users=notify_users
        )

        if approval.status == "approved":
            # If all done — notify completion
            if purchase.approval_status == "approved":
                await notify_approval_completed(purchase, notify_users)
            else:
                # Notify next approver in sequential mode
                if purchase.approval_mode != "parallel":
                    all_res = await db.execute(
                        select(PurchaseApproval)
                        .where(PurchaseApproval.purchase_id == pid, PurchaseApproval.status == "pending")
                        .order_by(PurchaseApproval.order_num)
                    )
                    next_pa = all_res.scalars().first()
                    if next_pa and next_pa.user_id:
                        next_user = await db.get(User, next_pa.user_id)
                        if next_user:
                            await notify_approval_your_turn(purchase, next_user)
    except Exception:
        pass  # best-effort

    return _to_out(approval)


# ── 4. Reset approvals ──────────────────────────────────────────────────────

@router.post("/purchases/{pid}/approvals/reset")
async def reset_approvals(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Сброс согласования доступен только администратору")

    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    # Delete all approval records
    result = await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == pid)
    )
    for a in result.scalars().all():
        await db.delete(a)

    purchase.approval_status = None

    db.add(PurchaseEvent(
        purchase_id=pid,
        user_id=current_user.id,
        event_type="approval_reset",
        data={},
    ))

    await db.commit()
    return {"ok": True}


# ── 5. My pending approvals ─────────────────────────────────────────────────

@router.get("/approvals/my-pending")
async def my_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find all approvals assigned to current user with status=pending
    result = await db.execute(
        select(PurchaseApproval)
        .where(
            PurchaseApproval.user_id == current_user.id,
            PurchaseApproval.status == "pending",
        )
        .order_by(PurchaseApproval.created_at)
    )
    my_approvals = result.scalars().all()

    out = []
    for ap in my_approvals:
        # Load purchase info
        purchase = await db.get(Purchase, ap.purchase_id)
        if not purchase or purchase.approval_status != "in_progress":
            continue

        # Check if it's actually this user's turn (sequential mode only)
        if purchase.approval_mode != "parallel":
            prior_result = await db.execute(
                select(PurchaseApproval)
                .where(
                    PurchaseApproval.purchase_id == ap.purchase_id,
                    PurchaseApproval.order_num < ap.order_num,
                )
            )
            prior = prior_result.scalars().all()
            if any(p.status not in ("approved", "skipped") for p in prior):
                continue  # Not this user's turn yet

        out.append({
            "approval": _to_out(ap),
            "purchase": {
                "id": purchase.id,
                "purchase_number": purchase.purchase_number,
                "item_name": purchase.item_name,
                "subject": purchase.subject,
                "status": purchase.status,
                "subsidy_id": purchase.subsidy_id,
                "contract_price": float(purchase.contract_price) if purchase.contract_price else None,
            },
        })

    return out


# ── 6. Add approver to purchase (all roles) ─────────────────────────────────

@router.post("/purchases/{pid}/approvals/add")
async def add_approver(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an approver to the purchase approval chain. Available to all roles."""
    purchase = await db.get(Purchase, pid)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    role_name = (body.get("role_name") or "").strip()
    full_name = (body.get("full_name") or "").strip()
    user_id = body.get("user_id")

    if not role_name or not full_name:
        raise HTTPException(422, "Укажите должность и ФИО согласующего")

    # Determine order_num — append after current max
    existing = (await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == pid)
    )).scalars().all()
    max_order = max((a.order_num for a in existing), default=0)

    new_approval = PurchaseApproval(
        purchase_id=pid,
        order_num=max_order + 1,
        role_name=role_name,
        approver_full_name=full_name,
        user_id=user_id,
        status="pending",
    )
    db.add(new_approval)

    db.add(PurchaseEvent(
        purchase_id=pid,
        user_id=current_user.id,
        event_type="member_added",
        data={"role_name": role_name, "full_name": full_name},
    ))

    await db.commit()
    await db.refresh(new_approval)
    return _to_out(new_approval)
