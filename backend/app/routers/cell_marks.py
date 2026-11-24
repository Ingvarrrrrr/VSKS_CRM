"""cell_marks router — cell & row highlights and attached comments.

Endpoints:
- GET /api/cell-marks
- POST /api/cell-marks/batch
- POST /api/cell-marks/clear-color
- POST /api/cell-marks/{group_id}/resolve
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import owner_scope_org_ids
from app.models.cell_mark import CellMark
from app.models.user import User

router = APIRouter(prefix="/api/cell-marks", tags=["cell-marks"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CellMarkTarget(BaseModel):
    entity_type: str
    entity_id: int
    field_name: str = "*"
    org_id: Optional[int] = None
    subsidy_id: Optional[int] = None


class CellMarkBatchIn(BaseModel):
    targets: List[CellMarkTarget]
    color: Optional[str] = None
    comment: Optional[str] = None
    visibility: Literal["shared", "private"] = "shared"
    subsidy_id: Optional[int] = None
    org_id: Optional[int] = None


class ClearColorTarget(BaseModel):
    entity_type: str
    entity_id: int
    field_name: Optional[str] = None


class ClearColorIn(BaseModel):
    targets: List[ClearColorTarget]


class CellMarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: str
    entity_type: str
    entity_id: int
    field_name: str
    org_id: Optional[int] = None
    subsidy_id: Optional[int] = None
    color: Optional[str] = None
    comment: Optional[str] = None
    visibility: str
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[int] = None
    resolved_by_name: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BatchResultOut(BaseModel):
    group_id: str
    items: List[CellMarkOut]


class ClearColorResultOut(BaseModel):
    cleared: int


class ResolveResultOut(BaseModel):
    resolved: int
    group_id: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[CellMarkOut])
async def list_cell_marks(
    entity_type: str = Query(..., description="Target entity type"),
    entity_ids: Optional[str] = Query(None, description="Comma-separated entity IDs"),
    subsidy_id: Optional[int] = Query(None, description="Subsidy filter"),
    include_resolved: bool = Query(False, description="Include resolved comments/marks"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List cell and row marks matching filters within user's access scope."""
    q = select(CellMark).where(CellMark.entity_type == entity_type)

    if entity_ids:
        raw_ids = [x.strip() for x in entity_ids.split(",") if x.strip()]
        parsed_ids = [int(x) for x in raw_ids if x.isdigit()]
        if parsed_ids:
            q = q.where(CellMark.entity_id.in_(parsed_ids))
        else:
            return []

    if subsidy_id is not None:
        q = q.where(CellMark.subsidy_id == subsidy_id)

    if not include_resolved:
        q = q.where(CellMark.is_resolved.is_(False))

    # Visibility: shared (for everyone in org contour) or private (only author)
    q = q.where(
        or_(
            CellMark.visibility == "shared",
            CellMark.created_by_id == current_user.id,
        )
    )

    # Org access contour
    scope = await owner_scope_org_ids(current_user, db)
    if scope is not None:
        allowed_orgs = set(get_org_filter(current_user) or []) | scope
        q = q.where(
            or_(
                CellMark.org_id.is_(None),
                CellMark.org_id.in_(allowed_orgs),
                CellMark.created_by_id == current_user.id,
            )
        )

    q = q.order_by(CellMark.id.asc())
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/batch", response_model=BatchResultOut)
async def batch_upsert_cell_marks(
    body: CellMarkBatchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch apply color highlight and/or attached comment to cells and rows."""
    if not body.targets:
        raise HTTPException(status_code=422, detail="targets не может быть пустым")

    batch_group_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None)

    # Check caller org contour
    scope = await owner_scope_org_ids(current_user, db)
    allowed_orgs = set(get_org_filter(current_user) or [])
    if scope is not None:
        allowed_orgs = allowed_orgs | scope

    result_items: List[CellMark] = []

    for target in body.targets:
        field_name = (target.field_name or "*").strip() or "*"
        target_org_id = target.org_id or body.org_id or getattr(current_user, "org_id", None)
        target_subsidy_id = target.subsidy_id or body.subsidy_id

        # Search existing active mark
        cond = [
            CellMark.entity_type == target.entity_type,
            CellMark.entity_id == target.entity_id,
            CellMark.field_name == field_name,
            CellMark.is_resolved.is_(False),
        ]

        if body.visibility == "private":
            cond.append(CellMark.visibility == "private")
            cond.append(CellMark.created_by_id == current_user.id)
        else:
            cond.append(CellMark.visibility == "shared")
            if target_org_id:
                cond.append(
                    or_(
                        CellMark.org_id == target_org_id,
                        CellMark.org_id.is_(None),
                        CellMark.created_by_id == current_user.id,
                    )
                )

        existing = (await db.execute(select(CellMark).where(and_(*cond)))).scalars().first()

        if existing:
            existing.group_id = batch_group_id
            if "color" in body.model_fields_set and body.color is not None:
                existing.color = body.color
            if "comment" in body.model_fields_set:
                existing.comment = body.comment
                existing.visibility = body.visibility
            if target_org_id and not existing.org_id:
                existing.org_id = target_org_id
            if target_subsidy_id and not existing.subsidy_id:
                existing.subsidy_id = target_subsidy_id
            existing.updated_at = now
            result_items.append(existing)
        else:
            new_mark = CellMark(
                group_id=batch_group_id,
                entity_type=target.entity_type,
                entity_id=target.entity_id,
                field_name=field_name,
                org_id=target_org_id,
                subsidy_id=target_subsidy_id,
                color=body.color,
                comment=body.comment,
                visibility=body.visibility,
                is_resolved=False,
                created_by_id=current_user.id,
                created_by_name=user_name,
                created_at=now,
                updated_at=now,
            )
            db.add(new_mark)
            result_items.append(new_mark)

    await db.commit()
    for item in result_items:
        await db.refresh(item)

    return BatchResultOut(
        group_id=batch_group_id,
        items=[CellMarkOut.model_validate(x) for x in result_items],
    )


@router.post("/clear-color", response_model=ClearColorResultOut)
async def clear_cell_mark_color(
    body: ClearColorIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear color highlights from specified cells or entire entities."""
    if not body.targets:
        return ClearColorResultOut(cleared=0)

    now = datetime.now(timezone.utc)
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None)
    cleared_count = 0

    for target in body.targets:
        cond = [
            CellMark.entity_type == target.entity_type,
            CellMark.entity_id == target.entity_id,
            CellMark.is_resolved.is_(False),
            or_(
                CellMark.visibility == "shared",
                CellMark.created_by_id == current_user.id,
            ),
        ]

        if target.field_name is not None and target.field_name.strip() != "":
            target_field = target.field_name.strip()
            cond.append(CellMark.field_name == target_field)

        marks = (await db.execute(select(CellMark).where(and_(*cond)))).scalars().all()

        for m in marks:
            if m.comment and m.comment.strip():
                # Preserve attached comment, remove only color
                m.color = None
                m.updated_at = now
                cleared_count += 1
            else:
                # No comment: mark as resolved/cleared
                m.is_resolved = True
                m.resolved_at = now
                m.resolved_by_id = current_user.id
                m.resolved_by_name = user_name
                m.updated_at = now
                cleared_count += 1

    await db.commit()
    return ClearColorResultOut(cleared=cleared_count)


@router.post("/{group_id}/resolve", response_model=ResolveResultOut)
async def resolve_cell_marks_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all cell marks in a group as resolved ('Вопрос решён').

    Preserves color and comment in DB for historical audits (include_resolved=True),
    while immediately removing them from active selection (include_resolved=False).
    """
    q = select(CellMark).where(
        CellMark.group_id == group_id,
        CellMark.is_resolved.is_(False),
        or_(
            CellMark.visibility == "shared",
            CellMark.created_by_id == current_user.id,
        ),
    )

    scope = await owner_scope_org_ids(current_user, db)
    if scope is not None:
        allowed_orgs = set(get_org_filter(current_user) or []) | scope
        q = q.where(
            or_(
                CellMark.org_id.is_(None),
                CellMark.org_id.in_(allowed_orgs),
                CellMark.created_by_id == current_user.id,
            )
        )

    marks = (await db.execute(q)).scalars().all()
    now = datetime.now(timezone.utc)
    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None)

    for m in marks:
        m.is_resolved = True
        m.resolved_at = now
        m.resolved_by_id = current_user.id
        m.resolved_by_name = user_name
        m.updated_at = now

    await db.commit()
    return ResolveResultOut(resolved=len(marks), group_id=group_id)
