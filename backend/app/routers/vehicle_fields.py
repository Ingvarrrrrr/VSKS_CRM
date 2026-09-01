"""
Vehicle fields catalog + hide/show management — Автоблок §4.

Endpoints:
  GET /api/vehicle-fields — каталог полей карточки ТС (группы, hidden, can_manage)
  PUT /api/vehicle-fields — изменить состав скрытых полей организации

Право на изменение — vehicle.fields.manage (см. сид в app/__init__.py, блок Phase 29).
Хранение конфигурации скрытия переиспользует org_section_config (без новой таблицы,
без нового права на чтение — GET доступен всем с доступом к вкладке 'vehicles').
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab, require_action, _has_key_in_any_org
from app.database import get_db
from app.models.org_section_config import OrgSectionConfig
from app.models.user import User
from app.services.vehicle_fields import (
    CONFIG_KEY_PREFIX,
    build_catalog,
    get_all_field_keys,
    get_field_label,
    get_hidden_field_keys,
    is_lockable,
)

router = APIRouter(prefix="/api/vehicle-fields", tags=["vehicle-fields"])


class FieldConfigItem(BaseModel):
    field_key: str
    is_hidden: bool


class FieldConfigBody(BaseModel):
    items: List[FieldConfigItem]


@router.get("")
async def get_vehicle_fields(
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """GET /api/vehicle-fields — каталог с учётом конфигурации организации пользователя."""
    hidden_keys = await get_hidden_field_keys(db, current_user.org_id)

    can_manage = (
        current_user.role == "superadmin"
        or await _has_key_in_any_org(current_user, db, "vehicle.fields.manage")
    )

    return {
        "can_manage": can_manage,
        "groups": build_catalog(hidden_keys),
        "hidden_keys": sorted(hidden_keys),
    }


@router.put("")
async def update_vehicle_fields(
    body: FieldConfigBody,
    current_user: User = Depends(require_action("vehicle.fields.manage")),
    db: AsyncSession = Depends(get_db),
):
    """PUT /api/vehicle-fields — полная перезапись набора скрытых полей ТС организации."""
    org_id = current_user.org_id
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Выберите организацию, чтобы менять состав полей карточки ТС",
        )

    # Валидация ДО любых мутаций БД: попытка скрыть незакрываемое поле → 400 с внятным текстом.
    for item in body.items:
        if item.is_hidden and not is_lockable(item.field_key):
            label = get_field_label(item.field_key) or item.field_key
            raise HTTPException(
                status_code=400,
                detail=f"Поле «{label}» нельзя скрыть — без него карточка ТС не работает.",
            )

    valid_keys = get_all_field_keys()

    await db.execute(
        delete(OrgSectionConfig).where(
            OrgSectionConfig.org_id == org_id,
            OrgSectionConfig.section_key.like(f"{CONFIG_KEY_PREFIX}%"),
        )
    )
    for item in body.items:
        if item.is_hidden and item.field_key in valid_keys and is_lockable(item.field_key):
            db.add(OrgSectionConfig(
                org_id=org_id,
                section_key=f"{CONFIG_KEY_PREFIX}{item.field_key}",
                is_hidden=True,
            ))
    await db.commit()
    return {"ok": True}
