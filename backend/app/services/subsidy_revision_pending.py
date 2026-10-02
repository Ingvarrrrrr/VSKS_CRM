"""«Мои задачи» — корректировки субсидии, ждущие решения ТЕКУЩЕГО пользователя.
Подключается ОДНОЙ веткой в app.routers.purchase_approvals._collect_my_pending
(ПРАВИЛО №6 — список/счётчик там уже существует, второй список не заводим)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_revision import SubsidyRevision
from app.models.subsidy import Subsidy
from app.models.user import User


async def collect_my_pending_subsidy_revisions(db: AsyncSession, current_user: User) -> list[dict]:
    """Элементы в ТОМ ЖЕ формате, что и остальные виды _collect_my_pending
    (kind/title/subtitle/amount/requested_at/link) — субсидии, где
    current_user может решать (has_org_key 'subsidy.edit'), и есть
    корректировка в статусе submitted/partially_decided."""
    from app.auth.permissions import has_org_key
    from app.services.subsidy_revision_guard import revision_enabled

    if not revision_enabled():
        return []

    rows = (await db.execute(
        select(SubsidyRevision, Subsidy)
        .join(Subsidy, SubsidyRevision.subsidy_id == Subsidy.id)
        .where(SubsidyRevision.status.in_(("submitted", "partially_decided")))
        .order_by(SubsidyRevision.submitted_at)
    )).all()

    out: list[dict] = []
    for revision, subsidy in rows:
        if revision.author_id == current_user.id:
            continue  # самосогласование — как и у plan_excess/wish
        if current_user.role != "superadmin" and not await has_org_key(
            current_user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy.id,
        ):
            continue
        author = await db.get(User, revision.author_id) if revision.author_id else None
        out.append({
            "kind": "subsidy_revision",
            "approval_id": revision.id,
            "title": f"Корректировка №{revision.number}: {subsidy.name}",
            "subtitle": f"Автор: {(author.full_name or author.username) if author else '—'}",
            "amount": None,
            "requested_at": revision.submitted_at.isoformat() if revision.submitted_at else None,
            "link": f"/subsidies/{subsidy.id}/revisions/{revision.id}",
        })
    return out
