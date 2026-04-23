from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import require_role, ADMIN_ROLES
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.system_incident import SystemIncident

router = APIRouter(prefix="/api/system-incidents", tags=["system-incidents"])


@router.get("/")
async def list_incidents(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('system_incidents')),
):
    q = select(SystemIncident).order_by(desc(SystemIncident.created_at))
    if search:
        like = f"%{search}%"
        q = q.where(
            SystemIncident.message.ilike(like) |
            SystemIncident.path.ilike(like) |
            SystemIncident.correlation_id.ilike(like)
        )
    total_q = select(SystemIncident)
    if search:
        like = f"%{search}%"
        total_q = total_q.where(
            SystemIncident.message.ilike(like) |
            SystemIncident.path.ilike(like) |
            SystemIncident.correlation_id.ilike(like)
        )
    rows = (await db.execute(q.offset(offset).limit(limit))).scalars().all()
    return [
        {
            "id": r.id,
            "message": r.message,
            "details": r.details,
            "code": r.code,
            "correlation_id": r.correlation_id,
            "path": r.path,
            "method": r.method,
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('system_incidents')),
):
    r = (await db.execute(select(SystemIncident).where(SystemIncident.id == incident_id))).scalar_one_or_none()
    if r:
        await db.delete(r)
        await db.commit()


@router.delete("/", status_code=204)
async def clear_incidents(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('system_incidents')),
):
    rows = (await db.execute(select(SystemIncident))).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.commit()
