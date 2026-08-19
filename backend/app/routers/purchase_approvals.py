from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_event import PurchaseEvent
from app.models.subsidy_approver import SubsidyApprover
from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
from app.models.feo_category import FeoCategory
from app.schemas.schemas import PurchaseApprovalOut, ApprovalDecisionRequest
from app.auth.jwt import get_current_user, ADMIN_ROLES, MANAGER_ROLES
from app.models.user import User
from app.models.task import Task, TaskAssignee, TaskStatus, TaskPriority
from app.models.chat_message import ChatMessage
from app.routers.purchase_members import _create_assignment_chat_room
from app.services.responsible_role import is_responsible_role, RESPONSIBLE_PLACEHOLDER
from typing import List
from datetime import datetime, timezone, time

router = APIRouter(prefix="/api", tags=["approvals"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _resolve_purchase_org_id(db: AsyncSession, purchase: Purchase, current_user: User) -> int | None:
    """Purchase не хранит свою org_id (такой колонки нет ни в модели, ни в таблице
    purchases) — организация закупки определяется через субсидию, как и в
    purchases.py (`Purchase.subsidy_id == Subsidy.id` → `Subsidy.org_id`) и
    events.py/subsidy_approvers.py. Фолбэк на org_id текущего пользователя,
    если у закупки нет субсидии (см. исходный `p.org_id or current_user.org_id`)."""
    if purchase.subsidy_id:
        from app.models.subsidy import Subsidy
        subsidy = await db.get(Subsidy, purchase.subsidy_id)
        if subsidy is not None:
            return subsidy.org_id
    return current_user.org_id


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

    # Check purchase status — at least work_in_progress
    ALLOWED = ("work_in_progress",)
    if p.status not in ALLOWED:
        raise HTTPException(422, f"Согласование можно запустить только в статусе: {', '.join(ALLOWED)}")

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

    # Create PurchaseApproval records.
    # «Ответственный исполнитель» — роль-слот в subsidy_approvers (см.
    # app/services/responsible_role.py): ФИО там ВСЕГДА плейсхолдер, реальный
    # исполнитель определяется по КАЖДОЙ закупке отдельно, а не берётся
    # фиксированным из настроек субсидии — иначе он утекает во все закупки.
    created = []
    for sa in approvers:
        if is_responsible_role(sa.role_name):
            resolved_uid = p.assigned_user_id or p.service_note_by
            resolved_name = ""
            if resolved_uid:
                resolved_user = await db.get(User, resolved_uid)
                resolved_name = (getattr(resolved_user, "full_name", None) or "").strip() if resolved_user else ""
            if not resolved_name:
                resolved_name = (p.responsible_person or "").strip()
            if not resolved_name:
                resolved_name = RESPONSIBLE_PLACEHOLDER
            pa = PurchaseApproval(
                purchase_id=pid,
                subsidy_approver_id=sa.id,
                order_num=sa.order_num,
                role_name=sa.role_name,
                approver_full_name=resolved_name,
                user_id=resolved_uid,
                status="pending",
                approval_deadline=approval_deadline,
            )
        else:
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

    # Create Task + ChatRoom for each approver with user_id (best-effort, same transaction)
    purchase_label = f"Согласование закупки № {p.purchase_number or p.id}"
    org_id = await _resolve_purchase_org_id(db, p, current_user)
    for pa in created:
        if not pa.user_id:
            continue
        try:
            # Convert deadline date → datetime if needed
            task_due: datetime | None = None
            if approval_deadline is not None:
                task_due = datetime.combine(approval_deadline, time(23, 59, 59), tzinfo=timezone.utc)
            task = Task(
                title=purchase_label,
                description=f"Роль: {pa.role_name}. Принять решение по закупке.",
                status=TaskStatus.todo,
                priority=TaskPriority.medium,
                due_date=task_due,
                assigned_user_id=pa.user_id,
                created_by_id=current_user.id,
                org_id=org_id,
                purchase_id=p.id,
                category="Согласование",
            )
            db.add(task)
            await db.flush()
            db.add(TaskAssignee(task_id=task.id, user_id=pa.user_id, consent_pending=False))
            await db.flush()
            # ChatRoom (skip if approver is current user)
            if pa.user_id != current_user.id:
                room_id = await _create_assignment_chat_room(
                    db, current_user.id, pa.user_id, org_id, purchase_label,
                )
                db.add(ChatMessage(
                    room_id=room_id,
                    sender_id=current_user.id,
                    content=f"📋 Запущено согласование: {p.subject or ''}\nВаша роль: {pa.role_name}",
                ))
                await db.flush()
        except Exception:
            pass  # best-effort: not breaking the approval start

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
    approvals = result.scalars().all()

    # Исторические записи хранят логин — подменяем на ФИО решившего пользователя
    decider_ids = {a.decided_by_user_id for a in approvals if a.decided_by_user_id}
    names: dict[int, str] = {}
    if decider_ids:
        u_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(decider_ids))
        )).all()
        names = {uid: fn for uid, fn in u_rows if fn}

    out = []
    for a in approvals:
        d = _to_out(a)
        if a.decided_by_user_id and a.decided_by_user_id in names:
            d["decided_by_username"] = names[a.decided_by_user_id]
        out.append(d)
    return out


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
    approval.decided_by_username = current_user.full_name or current_user.username
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

    # Close Task for this approver (best-effort)
    if body.action in ("approve", "reject") and approval.user_id:
        try:
            task_res = await db.execute(
                select(Task).where(
                    Task.purchase_id == pid,
                    Task.assigned_user_id == approval.user_id,
                    Task.category == "Согласование",
                    Task.status == TaskStatus.todo,
                )
            )
            task_to_close = task_res.scalars().first()
            if task_to_close:
                task_to_close.status = TaskStatus.done if body.action == "approve" else TaskStatus.cancelled
        except Exception:
            pass  # best-effort

    await db.commit()
    await db.refresh(approval)

    # Notifications
    try:
        from app.notifications import notify_approval_decided, notify_approval_your_turn, notify_approval_completed
        approver_name = approval.approver_full_name or current_user.full_name

        # Collect purchase members/creator to notify.
        # Purchase has no created_by_id column (that's a Task field — same mine
        # as p.org_id above); reuse the "responsible person" resolution already
        # established for this purchase in start_approval() above.
        notify_users = []
        responsible_uid = purchase.assigned_user_id or purchase.service_note_by
        if responsible_uid:
            creator = await db.get(User, responsible_uid)
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

    # Cancel all pending approval Tasks for this purchase (best-effort)
    try:
        tasks_res = await db.execute(
            select(Task).where(
                Task.purchase_id == pid,
                Task.category == "Согласование",
                Task.status == TaskStatus.todo,
            )
        )
        for t in tasks_res.scalars().all():
            t.status = TaskStatus.cancelled
    except Exception:
        pass  # best-effort

    await db.commit()
    return {"ok": True}


# ── 5. My pending approvals (закупки + заявки + превышения плана ФЭО) ──────
#
# Владелец: «Все согласования должны быть в разделе про согласование. Человек,
# которому пришли согласования, должен узнавать об этом, и счётчик должен
# быть». Раньше эндпоинт отдавал только закупки (PurchaseApproval) — теперь
# аддитивно (kind + унифицированные поля title/subtitle/amount/link поверх
# старой формы записи) собираем все три вида согласований одним helper'ом,
# чтобы список (/my-pending) и счётчик (/my-pending/count) не могли разойтись.

async def _collect_my_pending(db: AsyncSession, current_user: User) -> list[dict]:
    """Единый список согласований, ожидающих решения current_user.

    Правила отбора для каждого вида повторяют логику очереди последовательного
    согласования, уже реализованную в «родном» роутере каждой сущности
    (purchase_approvals.decide_approval / wish_approvals.decide_wish_approval /
    plan_excess.decide_plan_excess_step) — здесь она не переизобретается,
    а повторяется один в один, чтобы отбор в списке совпадал с тем, что
    реально позволяет решить соответствующий /decide.
    """
    out: list[dict] = []

    # ── закупки (PurchaseApproval) ──
    result = await db.execute(
        select(PurchaseApproval)
        .where(
            PurchaseApproval.user_id == current_user.id,
            PurchaseApproval.status == "pending",
        )
        .order_by(PurchaseApproval.created_at)
    )
    my_approvals = result.scalars().all()
    for ap in my_approvals:
        purchase = await db.get(Purchase, ap.purchase_id)
        if not purchase or purchase.approval_status != "in_progress":
            continue

        # Очередь последовательного согласования — не наступила ли она ещё
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
                continue  # ещё не очередь этого согласующего

        out.append({
            "kind": "purchase",
            "approval_id": ap.id,
            "title": f"Закупка № {purchase.purchase_number or purchase.id}",
            "subtitle": f"{ap.role_name}: {ap.approver_full_name}",
            "amount": float(purchase.contract_price) if purchase.contract_price else None,
            "requested_at": ap.created_at.isoformat() if ap.created_at else None,
            "link": f"/orders/{purchase.id}/edit",
            # Старая форма записи — контракт с MyTasksView.vue не ломаем
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

    # ── заявки (WishApproval) — см. wish_approvals.decide_wish_approval ──
    wish_result = await db.execute(
        select(WishApproval)
        .where(
            WishApproval.user_id == current_user.id,
            WishApproval.status == "pending",
        )
        .order_by(WishApproval.created_at)
    )
    my_wish_approvals = wish_result.scalars().all()
    for wa in my_wish_approvals:
        wish = await db.get(Wish, wa.wish_id)
        if not wish or wish.status != "submitted":
            continue

        if wish.approval_mode == "sequential":
            lower_pending = (await db.execute(
                select(func.count()).select_from(WishApproval).where(
                    WishApproval.wish_id == wa.wish_id,
                    WishApproval.order_num < wa.order_num,
                    WishApproval.status == "pending",
                )
            )).scalar() or 0
            if lower_pending > 0:
                continue  # ещё не очередь этого согласующего

        amount = None
        if wish.estimated_price is not None:
            qty = float(wish.quantity) if wish.quantity is not None else 1.0
            amount = float(wish.estimated_price) * qty

        out.append({
            "kind": "wish",
            "approval_id": wa.id,
            "title": f"Заявка №{wish.id}: {wish.title or 'без названия'}",
            "subtitle": f"{wa.role_name}: {wa.approver_full_name}" if wa.role_name else "",
            "amount": amount,
            "requested_at": wa.created_at.isoformat() if wa.created_at else None,
            "link": f"/wishes?open={wish.id}",
        })

    # ── превышения плана ФЭО (PlanExcessApprovalStep) — см. plan_excess.decide_plan_excess_step ──
    step_result = await db.execute(
        select(PlanExcessApprovalStep)
        .where(
            PlanExcessApprovalStep.user_id == current_user.id,
            PlanExcessApprovalStep.status == "pending",
        )
        .order_by(PlanExcessApprovalStep.created_at)
    )
    my_excess_steps = step_result.scalars().all()
    for step in my_excess_steps:
        approval = await db.get(PlanExcessApproval, step.approval_id)
        if not approval or approval.status != "pending":
            continue

        all_steps_result = await db.execute(
            select(PlanExcessApprovalStep).where(PlanExcessApprovalStep.approval_id == approval.id)
        )
        all_steps = all_steps_result.scalars().all()
        if approval.mode != "parallel":
            lower_pending = any(
                s.order_num < step.order_num and s.status == "pending" for s in all_steps
            )
            if lower_pending:
                continue  # ещё не очередь этого согласующего

        cat = await db.get(FeoCategory, approval.feo_category_id)
        cat_name = cat.name if cat else f"категория №{approval.feo_category_id}"

        out.append({
            "kind": "plan_excess",
            "approval_id": step.id,
            "title": f"Превышение плана ФЭО: {cat_name}",
            "subtitle": f"Превышение над бюджетом: {float(approval.excess_amount):,.2f} ₽".replace(",", " "),
            "amount": float(approval.excess_amount) if approval.excess_amount is not None else None,
            "requested_at": step.created_at.isoformat() if step.created_at else None,
            "link": f"/subsidies?sid={approval.subsidy_id}",
        })

    return out


@router.get("/approvals/my-pending")
async def my_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _collect_my_pending(db, current_user)


@router.get("/approvals/my-pending/count")
async def my_pending_approvals_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Лёгкий счётчик для бейджа в сайдбаре — использует тот же helper, что и
    список выше, поэтому число всегда совпадает с длиной /my-pending."""
    items = await _collect_my_pending(db, current_user)
    counts = {"purchase": 0, "wish": 0, "plan_excess": 0}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {"total": len(items), **counts}


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

    if user_id is not None:
        target_user = await db.get(User, user_id)
        if target_user and target_user.role == "superadmin":
            raise HTTPException(400, "Суперадмина нельзя назначить согласующим")

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
