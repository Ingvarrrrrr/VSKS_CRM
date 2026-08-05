"""plan_excess.py — согласование превышения плана ФЭО над финансированием узла.

Требование владельца (2026-08-05): «Если где-то превысил план ФЭО, значит
где-то надо снимать. Должны быть заблокированы действия, пока план закупок не
загонять обратно в размеры ФЭО. Согласование превышения должно быть цепочкой,
организации бывают разные, к директору не всегда простой сотрудник может
попасть» — цепочка строится тем же механизмом, что и у заявок (wishes), см.
app.services.approval_chain.build_ascending_chain.

Endpoints:
  GET  /api/plan-excess?subsidy_id=            — список запросов по субсидии
  POST /api/plan-excess                        — запросить согласование превышения по узлу
  POST /api/plan-excess/{id}/decide             — решение шага (approve/reject)

Влияние на app.services.feo_plan.compute_feo_plan_tree — см. её docstring и
assert_no_unapproved_excess (вызывается перед действиями, увеличивающими план,
в purchases.py/wishes.py).
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth.jwt import get_current_user, get_single_org_id, MANAGER_ROLES, OWNER_ROLES
from app.auth.permissions import require_tab
from app.models.user import User
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.models.organization import Organization
from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
from app.services.approval_chain import build_ascending_chain
from app.services.feo_plan import compute_feo_plan_tree

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plan-excess", tags=["plan-excess"])


def _is_saas(user: User) -> bool:
    return user.role in OWNER_ROLES


def _step_dict(s: PlanExcessApprovalStep) -> dict:
    return {
        "id": s.id,
        "approval_id": s.approval_id,
        "user_id": s.user_id,
        "order_num": s.order_num,
        "role_name": s.role_name,
        "full_name": s.approver_full_name,
        "status": s.status,
        "comment": s.comment,
        "decided_at": s.decided_at.isoformat() if s.decided_at else None,
        "decided_by_user_id": s.decided_by_user_id,
    }


def _approval_dict(a: PlanExcessApproval) -> dict:
    return {
        "id": a.id,
        "feo_category_id": a.feo_category_id,
        "subsidy_id": a.subsidy_id,
        "excess_amount": float(a.excess_amount) if a.excess_amount is not None else 0.0,
        "plan_amount": float(a.plan_amount) if a.plan_amount is not None else None,
        "budget_amount": float(a.budget_amount) if a.budget_amount is not None else None,
        "status": a.status,
        "mode": a.mode,
        "requested_by_id": a.requested_by_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "comment": a.comment,
        "steps": [_step_dict(s) for s in sorted(a.steps, key=lambda s: s.order_num)],
    }


async def _load_approval(approval_id: int, db: AsyncSession) -> PlanExcessApproval:
    a = (await db.execute(
        select(PlanExcessApproval)
        .options(selectinload(PlanExcessApproval.steps))
        .where(PlanExcessApproval.id == approval_id)
    )).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Запрос на согласование превышения не найден")
    return a


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_plan_excess_approvals(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("feo_categories")),
):
    rows = (await db.execute(
        select(PlanExcessApproval)
        .options(selectinload(PlanExcessApproval.steps))
        .where(PlanExcessApproval.subsidy_id == subsidy_id)
        .order_by(PlanExcessApproval.created_at.desc())
    )).scalars().all()
    return [_approval_dict(a) for a in rows]


async def _notify_pending_plan_excess_approvers(
    approval: PlanExcessApproval, db: AsyncSession, requester_name: str, cat_name: str,
) -> None:
    """Уведомляет согласующих из цепочки о необходимости решения по превышению плана ФЭО.

    По образцу app.routers.wishes._notify_pending_approvers:
    sequential → уведомить только первого (по order_num) pending-согласующего;
    parallel → уведомить всех pending сразу.
    """
    try:
        from app.notifications import notify_plan_excess_approval_step
        pending = sorted(
            (s for s in approval.steps if s.status == "pending"),
            key=lambda s: s.order_num,
        )
        if not pending:
            return
        targets = pending[:1] if approval.mode != "parallel" else pending
        for step in targets:
            if step.user_id and step.user_id != approval.requested_by_id:
                approver_user = await db.get(User, step.user_id)
                if approver_user:
                    await notify_plan_excess_approval_step(approval, approver_user, requester_name, cat_name)
    except Exception as e:
        logger.warning("notify plan-excess approvers failed: %s", e)


async def _notify_plan_excess_decision(
    approval: PlanExcessApproval, decided_step: PlanExcessApprovalStep,
    db: AsyncSession, decided_by_name: str, cat_name: str,
) -> None:
    """Уведомляет автора запроса о финальном решении и, для последовательного
    режима, следующего согласующего в очереди (если запрос ещё pending)."""
    try:
        from app.notifications import notify_plan_excess_decided, notify_plan_excess_approval_step
        if approval.status in ("approved", "rejected"):
            if approval.requested_by_id and approval.requested_by_id != decided_step.decided_by_user_id:
                requester = await db.get(User, approval.requested_by_id)
                if requester:
                    await notify_plan_excess_decided(
                        approval, requester, approval.status, decided_by_name,
                        decided_step.comment, cat_name,
                    )
        elif approval.status == "pending" and approval.mode != "parallel":
            nxt = next(
                (s for s in sorted(approval.steps, key=lambda s: s.order_num) if s.status == "pending"),
                None,
            )
            if nxt and nxt.user_id and nxt.user_id != approval.requested_by_id:
                nxt_user = await db.get(User, nxt.user_id)
                if nxt_user:
                    requester = await db.get(User, approval.requested_by_id) if approval.requested_by_id else None
                    requester_name = (requester.full_name or requester.username) if requester else "—"
                    await notify_plan_excess_approval_step(approval, nxt_user, requester_name, cat_name)
    except Exception as e:
        logger.warning("notify plan-excess decision failed: %s", e)


# ── POST request ──────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def request_plan_excess_approval(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("feo_categories")),
):
    """Запросить согласование превышения плана по узлу ФЭО. body:
    {feo_category_id, top_user_id?, mode?}. top_user_id — как в заявках,
    если не передан — берётся руководитель организации субсидии."""
    feo_category_id = int(body.get("feo_category_id", 0))
    if not feo_category_id:
        raise HTTPException(422, "feo_category_id обязателен")

    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")

    subsidy = await db.get(Subsidy, cat.subsidy_id)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    node = tree.get(feo_category_id)
    if node is None:
        raise HTTPException(404, "Узел ФЭО не найден в дереве плана")

    excess_amount = node.get("excess_amount") or 0.0
    if excess_amount <= 0.005:
        raise HTTPException(400, f"По категории «{cat.name}» нет превышения плана над финансированием ФЭО")

    existing_pending = (await db.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.feo_category_id == feo_category_id,
            PlanExcessApproval.status == "pending",
        ).order_by(PlanExcessApproval.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing_pending:
        full = await _load_approval(existing_pending.id, db)
        return _approval_dict(full)

    mode = body.get("mode", "sequential")
    if mode not in ("sequential", "parallel"):
        mode = "sequential"

    top_user_id = body.get("top_user_id")
    top_user_id = int(top_user_id) if top_user_id else None
    org_id = subsidy.org_id or get_single_org_id(current_user)
    if not top_user_id and org_id:
        org = await db.get(Organization, org_id)
        top_user_id = org.head_user_id if org else None
    if not top_user_id:
        top_user_id = current_user.id  # fallback: некому эскалировать — согласующий сам себе

    chain: list[dict] = []
    chain_warning: str | None = None
    if org_id:
        chain, chain_warning = await build_ascending_chain(db, current_user.id, top_user_id, org_id)
    if not chain:
        top_user = await db.get(User, top_user_id)
        chain = [{
            "user_id": top_user_id,
            "role_name": "Согласующий",
            "full_name": (top_user.full_name or top_user.username) if top_user else None,
            "order_num": 0,
        }]

    # Задача 2 (2026-08-05): цепочка не должна вырождаться молча.
    #   - цепочка полностью пуста (нет ни одного user_id) — некому направить запрос,
    #     не создаём «висящий» запрос, а объясняем, что нужно настроить.
    #   - цепочка состоит РОВНО из самого автора — формально запрос создаётся
    #     (иначе превышение никогда не согласовать), но фронт обязан явно
    #     показать пользователю, что согласовывать будет он сам.
    chain = [s for s in chain if s.get("user_id")]
    if not chain:
        raise HTTPException(
            409,
            "Не удалось определить, кому направить запрос на согласование превышения: "
            "у вас не назначен руководитель отдела, не задан руководитель организации "
            "(Organization.head_user_id) и не указан вышестоящий начальник (User.superior_user_id). "
            "Попросите администратора настроить одного из них.",
        )
    self_approval = all(s["user_id"] == current_user.id for s in chain)
    if self_approval:
        chain_warning = "Над вами нет вышестоящих согласующих — превышение будет согласовано вами лично."

    full_plan = node["plan"] + node["over"]  # текущая плановая сумма (до сжатия по бюджету)
    approval = PlanExcessApproval(
        feo_category_id=feo_category_id,
        subsidy_id=cat.subsidy_id,
        excess_amount=Decimal(str(excess_amount)),
        plan_amount=Decimal(str(full_plan)),
        budget_amount=Decimal(str(node.get("budget") or 0)),
        status="pending",
        mode=mode,
        requested_by_id=current_user.id,
    )
    db.add(approval)
    await db.flush()

    for step in chain:
        db.add(PlanExcessApprovalStep(
            approval_id=approval.id,
            user_id=step["user_id"],
            order_num=step["order_num"],
            role_name=step.get("role_name"),
            approver_full_name=step.get("full_name"),
            status="pending",
        ))
    await db.commit()

    full = await _load_approval(approval.id, db)
    requester_name = current_user.full_name or current_user.username
    await _notify_pending_plan_excess_approvers(full, db, requester_name, cat.name)

    resp = _approval_dict(full)
    resp["warning"] = chain_warning
    resp["self_approval"] = self_approval
    return resp


# ── POST decide ───────────────────────────────────────────────────────────────

@router.post("/{approval_id}/decide")
async def decide_plan_excess_step(
    approval_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("feo_categories")),
):
    approval = await _load_approval(approval_id, db)

    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision должен быть 'approved' или 'rejected'")

    step_id = body.get("step_id")
    step: PlanExcessApprovalStep | None = None
    if step_id:
        step = next((s for s in approval.steps if s.id == int(step_id)), None)
    else:
        # Без явного step_id — первый pending-шаг, назначенный текущему пользователю
        step = next(
            (s for s in approval.steps if s.status == "pending" and s.user_id == current_user.id),
            None,
        )
    if step is None:
        raise HTTPException(404, "Шаг согласования не найден")

    if step.status != "pending":
        raise HTTPException(400, f"По этому шагу уже принято решение: {step.status}")

    if not _is_saas(current_user) and current_user.role not in MANAGER_ROLES and step.user_id != current_user.id:
        raise HTTPException(403, "Решение может принять только назначенный согласующий или менеджер+")

    if approval.status != "pending":
        raise HTTPException(400, f"По этому запросу уже принято решение: {approval.status}")

    # Sequential: нельзя согласовать, пока нижестоящие (меньший order_num) ещё pending
    if approval.mode == "sequential":
        lower_pending = any(
            s.order_num < step.order_num and s.status == "pending" for s in approval.steps
        )
        if lower_pending:
            raise HTTPException(
                400,
                "Последовательное согласование: сначала должны согласовать нижестоящие в цепочке.",
            )

    step.status = decision
    step.comment = body.get("comment")
    step.decided_at = datetime.now(timezone.utc)
    step.decided_by_user_id = current_user.id
    await db.flush()

    if decision == "rejected":
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        approval.comment = body.get("comment")
    else:
        remaining = any(s.status == "pending" for s in approval.steps)
        if not remaining:
            approval.status = "approved"
            approval.resolved_at = datetime.now(timezone.utc)

    step_id_decided = step.id
    decided_by_name = current_user.full_name or current_user.username
    await db.commit()
    full = await _load_approval(approval_id, db)

    cat = await db.get(FeoCategory, full.feo_category_id)
    cat_name = cat.name if cat else f"категория №{full.feo_category_id}"
    decided_step = next((s for s in full.steps if s.id == step_id_decided), None)
    if decided_step is not None:
        await _notify_plan_excess_decision(full, decided_step, db, decided_by_name, cat_name)

    return _approval_dict(full)
