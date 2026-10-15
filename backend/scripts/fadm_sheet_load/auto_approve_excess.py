"""Автосогласование превышения по субсидии после переноса закупок
(владелец 15.10.2026: «все перенесённые и сопоставленные — автоматически
считаются согласованными на превышение», от его имени).

Какие превышения есть у узла и согласованы ли они — читает compute_feo_plan_tree
(ПРАВИЛО №6: те же поля, что видит интерфейс). На каждый несогласованный вид
заводится PlanExcessApproval в статусе approved с одним шагом, решённым
владельцем, — то же, что оставляет штатное «Согласовать»
(app.routers.plan_excess.decide_plan_excess_step).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory

from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
from app.models.user import User
from app.services import plan_excess_kinds as k
from app.services.feo_plan_tree import compute_feo_plan_tree

# (вид, поле суммы узла, поле «уже согласовано»)
KIND_FIELDS = (
    (k.OVER_FEO, "excess_over_feo", "excess_approved"),
    (k.FACT_OVER_PLAN, "excess_fact_over_plan", "excess_fact_approved"),
    (k.PLAN_OVER_MANUAL, "excess_plan_over_manual", "excess_plan_approved"),
    (k.PLAN_OVER_FEO_GOODS, "excess_plan_over_feo_goods", "excess_plan_over_feo_goods_approved"),
    (k.PLAN_OVER_FEO_SERVICES, "excess_plan_over_feo_services", "excess_plan_over_feo_services_approved"),
    (k.FACT_OVER_PLAN_GOODS, "excess_fact_over_plan_goods", "excess_fact_over_plan_goods_approved"),
    (k.FACT_OVER_PLAN_SERVICES, "excess_fact_over_plan_services", "excess_fact_over_plan_services_approved"),
)


@dataclass
class AutoApproval:
    category_id: int
    category_name: str
    kind: str
    amount: Decimal


async def auto_approve_subsidy_excess(
    db: AsyncSession, subsidy_id: int, *, requester_id: int, approver_id: int, comment: str,
) -> list[AutoApproval]:
    tree = await compute_feo_plan_tree(db, [subsidy_id])  # {feo_category_id: узел}
    names = dict((await db.execute(
        select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(list(tree.keys())))
    )).all()) if tree else {}
    approver = await db.get(User, approver_id)
    now = datetime.now(timezone.utc)
    out: list[AutoApproval] = []
    for cat_id, node in tree.items():
        for kind, amount_key, approved_key in KIND_FIELDS:
            amount = Decimal(str(node.get(amount_key) or 0)).quantize(Decimal("0.01"))
            if amount <= 0 or node.get(approved_key):
                continue
            approval = PlanExcessApproval(
                feo_category_id=cat_id, subsidy_id=subsidy_id, kind=kind,
                excess_amount=amount,
                plan_amount=Decimal(str(node.get("plan") or 0)),
                budget_amount=Decimal(str(node["budget"])) if node.get("budget") is not None else None,
                status="approved", mode="sequential", requested_by_id=requester_id,
                resolved_at=now, comment=comment,
            )
            approval.steps.append(PlanExcessApprovalStep(
                user_id=approver_id, order_num=0, status="approved", comment=comment,
                approver_full_name=approver.full_name if approver else None,
                decided_at=now, decided_by_user_id=approver_id,
            ))
            db.add(approval)
            out.append(AutoApproval(cat_id, names.get(cat_id, str(cat_id)), kind, amount))
    await db.flush()
    return out
