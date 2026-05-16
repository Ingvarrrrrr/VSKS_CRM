from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.permissions import require_tab

router = APIRouter(prefix="/api/staff-directory", tags=["staff-directory"])


@router.get("/", dependencies=[Depends(require_tab("staff_directory"))])
async def list_directory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only список сотрудников видимых current_user через org_filter.

    Скрыто: superadmin (если current_user не superadmin) + exclude_from_directory=true.
    """
    org_ids = get_org_filter(current_user)

    # Базовый запрос
    q = select(User).where(
        User.exclude_from_directory == False,  # noqa: E712
    )

    # Фильтр по организациям
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))

    # D-09: superadmin виден только другим superadmin
    if current_user.role != "superadmin":
        q = q.where(User.role != "superadmin")

    q = q.distinct()
    result = await db.execute(q)
    users = result.scalars().all()

    # Подгрузить org names
    org_id_to_name: dict = {}
    if users:
        org_ids_in_use = {u.org_id for u in users if u.org_id}
        if org_ids_in_use:
            org_q = select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids_in_use)
            )
            org_rows = await db.execute(org_q)
            org_id_to_name = {r[0]: r[1] for r in org_rows.all()}

    out = []
    for u in users:
        out.append({
            "id": u.id,
            "full_name": u.full_name or u.username,
            "position": u.position,
            "department": u.department,
            "phone": u.phone,
            "work_phone": u.work_phone,
            "email": u.email,
            "photo_url": u.profile_photo,
            "org_id": u.org_id,
            "org_name": org_id_to_name.get(u.org_id) if u.org_id else None,
        })

    # Сортировка: ФИО алфавит
    out.sort(key=lambda r: (r.get("full_name") or "").lower())
    return out
