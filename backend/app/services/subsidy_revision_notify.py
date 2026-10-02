"""Уведомления по корректировке утверждённой субсидии — тонкая обвязка над
app.notifications (ПРАВИЛО №6: сам текст/отправка живёт там, по образцу
_notify_pending_plan_excess_approvers/_notify_plan_excess_decision в
app.routers.plan_excess, здесь — только сбор адресатов для ЭТОЙ сущности).
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_revision import SubsidyRevision
from app.models.subsidy import Subsidy
from app.models.user import User

logger = logging.getLogger(__name__)


async def notify_submitted(db: AsyncSession, revision: SubsidyRevision) -> None:
    """Корректировка отправлена на проверку — уведомить обладателей
    subsidy.edit по субсидии (кандидаты — тот же источник, что и у
    plan_excess.decide/wish-согласования, ПРАВИЛО №6)."""
    try:
        from app.notifications import notify_subsidy_revision_submitted
        from app.services.authorized_approvers import list_users_with_org_key

        subsidy = await db.get(Subsidy, revision.subsidy_id)
        if subsidy is None or not subsidy.org_id:
            return
        author = await db.get(User, revision.author_id) if revision.author_id else None
        author_name = (author.full_name or author.username) if author else "—"
        approvers = await list_users_with_org_key(
            db, subsidy.org_id, "subsidy.edit",
            subsidy_id=revision.subsidy_id, exclude_user_id=revision.author_id,
        )
        for u in approvers:
            await notify_subsidy_revision_submitted(revision, subsidy, u, author_name)
    except Exception as e:
        logger.warning("notify subsidy-revision submitted failed: %s", e)


async def notify_revision_decided(db: AsyncSession, revision: SubsidyRevision) -> None:
    """Решение проверяющего (целиком или частично) — уведомить автора."""
    try:
        from app.notifications import notify_subsidy_revision_decided

        if not revision.author_id:
            return
        author = await db.get(User, revision.author_id)
        if author is None:
            return
        subsidy = await db.get(Subsidy, revision.subsidy_id)
        decided_by = await db.get(User, revision.decided_by_id) if revision.decided_by_id else None
        decided_by_name = (decided_by.full_name or decided_by.username) if decided_by else "—"
        await notify_subsidy_revision_decided(revision, subsidy, author, decided_by_name)
    except Exception as e:
        logger.warning("notify subsidy-revision decided failed: %s", e)
