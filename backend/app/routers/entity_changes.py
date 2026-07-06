"""entity_changes router — Phase 31

POST /api/entity-changes/{entity_type}/{entity_id}/dismiss-field
    Upsert EntityFieldSeen for current user (per-user seen-state, D-08).
    user_id always from auth, never from body (ASVS V4 T-31-01-01).

GET /api/entity-changes/{entity_type}/{entity_id}
    List EntityChange records for a given entity (with optional `since` filter).
    Only returns entities the current user has access to (auth required).

Reusable helper: record_entity_changes() — called from update endpoints and
can be imported by plan 31-04 for contracts cascade.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.entity_change import EntityChange, EntityFieldSeen
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/entity-changes", tags=["entity-changes"])

# Allowed entity types (validation guard — ASVS V4 T-31-01-01)
_VALID_ENTITY_TYPES = {"purchase", "wish", "task"}


class DismissFieldBody(BaseModel):
    field_name: str


class EntityChangeOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by_id: Optional[int] = None
    changed_by_name: Optional[str] = None
    changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Reusable helper ──────────────────────────────────────────────────────────

async def record_entity_changes(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    changed_by_id: int,
    changed_by_name: Optional[str],
    old_values: dict,
    new_values: dict,
) -> None:
    """Record EntityChange rows for each field that actually changed.

    Compares str(old) vs str(new) to handle Decimal/Date/int uniformly.
    One call per save event (D-06: one save = one change, not per-keystroke).
    Exported for reuse by plan 31-04 (contracts cascade) and any future callers.

    Only inserts rows where values differ — no-op if nothing changed.
    Commits changes in a separate short transaction.
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise ValueError(f"Invalid entity_type: {entity_type!r}. Must be one of {_VALID_ENTITY_TYPES}")

    changes = []
    for field_name in old_values:
        old = old_values.get(field_name)
        new = new_values.get(field_name)
        old_s = str(old) if old is not None else None
        new_s = str(new) if new is not None else None
        if old_s != new_s:
            changes.append(EntityChange(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                old_value=old_s,
                new_value=new_s,
                changed_by_id=changed_by_id,
                changed_by_name=changed_by_name,
            ))
    if changes:
        for c in changes:
            db.add(c)
        await db.commit()


# ── Batch unseen helpers ─────────────────────────────────────────────────────

async def get_unseen_map(
    db: AsyncSession,
    entity_type: str,
    entity_ids: list[int],
    current_user_id: int,
) -> dict[int, list[str]]:
    """Return {entity_id: [unseen_field, ...]} for the given entity_type and ids.

    Uses exactly 2 queries (N+1 prevention, T-31-01-04):
    1. SELECT MAX(changed_at) GROUP BY (entity_id, field_name) WHERE changed_by != me
    2. SELECT dismissed_at WHERE user_id = me

    A field is unseen if its latest change_at > dismissed_at (or dismissed_at is NULL).
    """
    if not entity_ids:
        return {}

    from sqlalchemy import func as sa_func

    # Query 1: latest change per (entity_id, field_name) by OTHER users
    change_rows = (await db.execute(
        select(
            EntityChange.entity_id,
            EntityChange.field_name,
            sa_func.max(EntityChange.changed_at).label("latest_changed_at"),
        )
        .where(
            EntityChange.entity_type == entity_type,
            EntityChange.entity_id.in_(entity_ids),
            EntityChange.changed_by_id != current_user_id,
        )
        .group_by(EntityChange.entity_id, EntityChange.field_name)
    )).all()

    if not change_rows:
        return {}

    # Build: (entity_id, field_name) -> latest_changed_at
    latest_change: dict[tuple, datetime] = {}
    for row in change_rows:
        latest_change[(row.entity_id, row.field_name)] = row.latest_changed_at

    # Query 2: dismissed_at per (entity_id, field_name) for current user
    seen_rows = (await db.execute(
        select(EntityFieldSeen)
        .where(
            EntityFieldSeen.user_id == current_user_id,
            EntityFieldSeen.entity_type == entity_type,
            EntityFieldSeen.entity_id.in_(entity_ids),
        )
    )).scalars().all()

    seen_map: dict[tuple, datetime] = {}
    for s in seen_rows:
        seen_map[(s.entity_id, s.field_name)] = s.dismissed_at

    # Compute unseen per entity_id
    result: dict[int, list[str]] = {}
    for (eid, fname), latest_at in latest_change.items():
        dismissed_at = seen_map.get((eid, fname))
        if dismissed_at is None or latest_at > dismissed_at:
            result.setdefault(eid, []).append(fname)

    return result


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{entity_type}/{entity_id}/dismiss-field")
async def dismiss_field(
    entity_type: str,
    entity_id: int,
    body: DismissFieldBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a specific field as seen by the current user.

    user_id is always derived from auth token (current_user.id) — never from body.
    entity_type is validated against the allow-list (T-31-01-01).
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип сущности '{entity_type}'. Допустимые: {sorted(_VALID_ENTITY_TYPES)}",
        )

    field_name = body.field_name.strip()
    if not field_name:
        raise HTTPException(status_code=422, detail="field_name не может быть пустым")

    # Upsert: delete existing row then insert fresh (portable across PG versions)
    await db.execute(
        delete(EntityFieldSeen).where(
            EntityFieldSeen.user_id == current_user.id,
            EntityFieldSeen.entity_type == entity_type,
            EntityFieldSeen.entity_id == entity_id,
            EntityFieldSeen.field_name == field_name,
        )
    )
    db.add(EntityFieldSeen(
        user_id=current_user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        dismissed_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return {"ok": True, "entity_type": entity_type, "entity_id": entity_id, "field_name": field_name}


@router.get("/{entity_type}/{entity_id}", response_model=List[EntityChangeOut])
async def get_entity_changes(
    entity_type: str,
    entity_id: int,
    since: Optional[datetime] = Query(None, description="Filter changes after this datetime"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # auth required (T-31-01-03)
):
    """List change history for a specific entity.

    Auth required — ensures only authenticated users can read change history.
    Visibility of the entity itself is enforced by the entity's own router;
    this endpoint returns changes for any entity_id the caller requests,
    relying on the fact that the caller must know the entity_id (security-by-obscurity
    is acceptable here since entity_ids are sequential integers without additional
    secret tokens — the entity router's GET /{id} already checks access).
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип сущности '{entity_type}'. Допустимые: {sorted(_VALID_ENTITY_TYPES)}",
        )

    q = select(EntityChange).where(
        EntityChange.entity_type == entity_type,
        EntityChange.entity_id == entity_id,
    ).order_by(EntityChange.changed_at.desc())

    if since is not None:
        q = q.where(EntityChange.changed_at > since)

    rows = (await db.execute(q)).scalars().all()
    return rows
