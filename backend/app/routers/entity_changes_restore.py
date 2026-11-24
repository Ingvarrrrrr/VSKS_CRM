"""entity_changes_restore router — endpoint to restore a field value from history.

POST /api/entity-changes/{entity_type}/{entity_id}/restore
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import owner_scope_org_ids
from app.models.user import User
from app.models.feo_planned_item import FeoPlannedItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.wish import Wish
from app.models.task import Task, TaskPriority
from app.routers.entity_changes import record_entity_changes, _check_feo_history_read_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/entity-changes", tags=["entity-changes"])

_EDITABLE_FIELDS = {
    "feo_item": {"name", "quantity", "unit", "unit_price", "amount"},
    "feo_category": {"name", "code", "budget"},
    "purchase": {"subject", "item_name", "delivery_address", "notes"},
    "wish": {"title", "description", "justification"},
    "task": {"title", "description", "priority", "category"},
}


class RestoreFieldBody(BaseModel):
    field_name: str
    value: Optional[str] = None


def _parse_decimal(val: Optional[str]) -> Optional[Decimal]:
    if val is None or not str(val).strip():
        return None
    cleaned = str(val).strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail=f"Недопустимое числовое значение: {val!r}")


@router.post("/{entity_type}/{entity_id}/restore")
async def restore_entity_field(
    entity_type: str,
    entity_id: int,
    body: RestoreFieldBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Safely restore a scalar field on an entity to a previous value and record history."""
    if entity_type not in _EDITABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Откат изменений для типа '{entity_type}' не поддерживается",
        )

    field_name = body.field_name.strip()
    if field_name not in _EDITABLE_FIELDS[entity_type]:
        raise HTTPException(
            status_code=400,
            detail=f"Поле '{field_name}' недоступно для отката сущности '{entity_type}'",
        )

    scope = await owner_scope_org_ids(current_user, db)
    allowed_orgs = set(get_org_filter(current_user) or [])
    if scope is not None:
        allowed_orgs = allowed_orgs | scope

    user_name = getattr(current_user, "full_name", None) or getattr(current_user, "email", None)

    target_obj: Any = None
    target_attr: str = field_name
    converted_val: Any = None

    if entity_type == "feo_item":
        await _check_feo_history_read_access("feo_item", entity_id, current_user, db)
        target_obj = (await db.execute(
            select(FeoPlannedItem).where(FeoPlannedItem.id == entity_id)
        )).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail="Позиция ФЭО не найдена")

        if field_name in ("quantity", "unit_price", "amount"):
            converted_val = _parse_decimal(body.value)
        else:
            converted_val = body.value.strip() if body.value is not None else None

    elif entity_type == "feo_category":
        await _check_feo_history_read_access("feo_category", entity_id, current_user, db)
        target_obj = (await db.execute(
            select(FeoCategory).where(FeoCategory.id == entity_id)
        )).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail="Категория ФЭО не найдена")

        if field_name == "budget":
            converted_val = _parse_decimal(body.value)
        else:
            converted_val = body.value.strip() if body.value is not None else None

    elif entity_type == "purchase":
        target_obj = (await db.execute(
            select(Purchase).where(Purchase.id == entity_id)
        )).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail="Закупка не найдена")

        if field_name == "notes":
            if hasattr(target_obj, "notes"):
                target_attr = "notes"
            elif hasattr(target_obj, "task_comment"):
                target_attr = "task_comment"
            elif hasattr(target_obj, "service_note_text"):
                target_attr = "service_note_text"
            else:
                target_attr = "notes"

        converted_val = body.value.strip() if body.value is not None else None

    elif entity_type == "wish":
        target_obj = (await db.execute(
            select(Wish).where(Wish.id == entity_id)
        )).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        if scope is not None and getattr(target_obj, "org_id", None) not in allowed_orgs:
            raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

        converted_val = body.value.strip() if body.value is not None else None

    elif entity_type == "task":
        target_obj = (await db.execute(
            select(Task).where(Task.id == entity_id)
        )).scalar_one_or_none()
        if not target_obj:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        task_org = getattr(target_obj, "org_id", None)
        if (
            scope is not None
            and task_org is not None
            and task_org not in allowed_orgs
            and target_obj.assigned_user_id != current_user.id
            and target_obj.created_by_id != current_user.id
        ):
            raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")

        if field_name == "priority":
            if body.value:
                try:
                    converted_val = TaskPriority(body.value.strip())
                except ValueError:
                    converted_val = TaskPriority.medium
            else:
                converted_val = TaskPriority.medium
        else:
            converted_val = body.value.strip() if body.value is not None else None

    # Get old value for audit logging
    old_raw = getattr(target_obj, target_attr, None)
    old_str = str(old_raw) if old_raw is not None else None
    new_str = str(converted_val) if converted_val is not None else None

    # Apply change
    setattr(target_obj, target_attr, converted_val)

    # Record in entity_changes
    await record_entity_changes(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        changed_by_id=current_user.id,
        changed_by_name=user_name,
        old_values={field_name: old_str},
        new_values={field_name: new_str},
        source="manual",
        commit=False,
    )

    await db.commit()
    await db.refresh(target_obj)

    return {
        "ok": True,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field_name": field_name,
        "restored_value": new_str,
    }
