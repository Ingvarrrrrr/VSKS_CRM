"""Ежедневные напоминания о дедлайнах задач/закупок/платежей/согласований.

Перенесено 1:1 из app/__init__.py._deadline_reminder_loop при разрезании
монолитного файла на модули (Правило №5). Логика не менялась.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.database import async_session


async def _deadline_reminder_loop():
    """Ежедневно в 09:00 UTC шлёт напоминания о задачах и закупках."""
    from sqlalchemy import select
    from app.models.task import Task, TaskAssignee, TaskStatus
    from app.models.user import User
    from app.models.purchase import Purchase
    from app.models.purchase_event import PurchaseMember
    from app.models.purchase_approval import PurchaseApproval
    from app.notifications import notify_deadline_soon, notify_purchase_deadline

    log = logging.getLogger(__name__)
    while True:
        try:
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= next_run:
                from datetime import timedelta
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())

            async with async_session() as db:
                today = datetime.now(timezone.utc).date()

                # ── 1. Task deadlines (0, 1, 3 дня) ──
                result = await db.execute(
                    select(Task).where(
                        Task.status.in_([TaskStatus.todo, TaskStatus.in_progress]),
                        Task.due_date.isnot(None),
                    )
                )
                for task in result.scalars().all():
                    due_date = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
                    days_left = (due_date - today).days
                    if days_left not in (0, 1, 3):
                        continue
                    assignees_result = await db.execute(
                        select(TaskAssignee).where(
                            TaskAssignee.task_id == task.id,
                            TaskAssignee.consent_pending == False,  # noqa: E712
                        )
                    )
                    for ta in assignees_result.scalars().all():
                        user = await db.get(User, ta.user_id)
                        if user:
                            await notify_deadline_soon(task, user, days_left)

                # ── 2. Purchase execution_term deadlines (0, 1, 3 дня) ──
                active_statuses = ("work_in_progress", "contracted")
                purch_result = await db.execute(
                    select(Purchase).where(
                        Purchase.status.in_(active_statuses),
                        Purchase.execution_term.isnot(None),
                    )
                )
                for p in purch_result.scalars().all():
                    days_left = (p.execution_term - today).days
                    if days_left not in (0, 1, 3, -1, -3):
                        continue
                    # Notify assigned user + members
                    notified = set()
                    if p.assigned_user_id:
                        u = await db.get(User, p.assigned_user_id)
                        if u:
                            await notify_purchase_deadline(p, u, days_left, "execution_term")
                            notified.add(p.assigned_user_id)
                    members = (await db.execute(
                        select(PurchaseMember).where(PurchaseMember.purchase_id == p.id)
                    )).scalars().all()
                    for m in members:
                        if m.user_id not in notified:
                            u = await db.get(User, m.user_id)
                            if u:
                                await notify_purchase_deadline(p, u, days_left, "execution_term")

                # ── 3. Payment overdue: delivered >5 days ago, not paid ──
                delivered_result = await db.execute(
                    select(Purchase).where(
                        Purchase.status == "delivered",
                        Purchase.delivery_date.isnot(None),
                    )
                )
                for p in delivered_result.scalars().all():
                    days_since = (today - p.delivery_date).days
                    if days_since < 5 or days_since % 5 != 0:  # remind every 5 days
                        continue
                    notified = set()
                    if p.assigned_user_id:
                        u = await db.get(User, p.assigned_user_id)
                        if u:
                            await notify_purchase_deadline(p, u, days_since, "payment_overdue")
                            notified.add(p.assigned_user_id)
                    members = (await db.execute(
                        select(PurchaseMember).where(PurchaseMember.purchase_id == p.id)
                    )).scalars().all()
                    for m in members:
                        if m.user_id not in notified:
                            u = await db.get(User, m.user_id)
                            if u:
                                await notify_purchase_deadline(p, u, days_since, "payment_overdue")

                # ── 4. Approval deadline overdue ──
                overdue_approvals = (await db.execute(
                    select(PurchaseApproval).where(
                        PurchaseApproval.status == "pending",
                        PurchaseApproval.approval_deadline.isnot(None),
                        PurchaseApproval.approval_deadline < today,
                    )
                )).scalars().all()
                for appr in overdue_approvals:
                    days_overdue = (today - appr.approval_deadline).days
                    if days_overdue not in (1, 3, 7):  # remind at 1, 3, 7 days overdue
                        continue
                    if appr.user_id:
                        u = await db.get(User, appr.user_id)
                        p = await db.get(Purchase, appr.purchase_id)
                        if u and p:
                            await notify_purchase_deadline(p, u, days_overdue, "approval_overdue")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).warning(f"Deadline reminder error: {e}")
            await asyncio.sleep(3600)
