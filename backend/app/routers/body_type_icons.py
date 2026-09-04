"""
Редактор значков кузова ТС (владелец, 2026-09) — Автоблок.

Endpoints:
  GET    /api/body-type-icons              — переопределения организации + can_manage
  PUT    /api/body-type-icons/{body_type}  — задать/изменить значок для кузова
  DELETE /api/body-type-icons/{body_type}  — вернуть кузов к значку по умолчанию
  DELETE /api/body-type-icons              — вернуть ВСЕ кузова организации к умолчанию

Право на изменение — vehicle.fields.manage (тот же класс настроек, что и состав
полей карточки ТС — см. app/routers/vehicle_fields.py, новых прав не заводим).
GET доступен любому с доступом к вкладке 'vehicles' — карточка ТС должна
уметь отрисовать переопределённый значок независимо от прав на его смену.
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab, require_action, _has_key_in_any_org
from app.database import get_db
from app.models.user import User
from app.services.body_type_icons import (
    InvalidBodyTypeIcon,
    delete_all_overrides,
    delete_override,
    get_overrides,
    upsert_override,
)

router = APIRouter(prefix="/api/body-type-icons", tags=["body-type-icons"])


class BodyTypeIconBody(BaseModel):
    icon_kind: str
    icon_value: str


def _require_org_id(current_user: User) -> int:
    org_id = current_user.org_id
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Выберите организацию, чтобы менять значки кузова карточки ТС",
        )
    return org_id


@router.get("")
async def get_body_type_icons(
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.org_id
    overrides = await get_overrides(db, org_id) if org_id else {}

    can_manage = (
        current_user.role == "superadmin"
        or await _has_key_in_any_org(current_user, db, "vehicle.fields.manage")
    )

    return {"can_manage": can_manage, "overrides": overrides}


@router.put("/{body_type}")
async def set_body_type_icon(
    body: BodyTypeIconBody,
    body_type: str = Path(...),
    current_user: User = Depends(require_action("vehicle.fields.manage")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org_id(current_user)
    try:
        await upsert_override(db, org_id, body_type, body.icon_kind, body.icon_value)
    except InvalidBodyTypeIcon as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/{body_type}")
async def reset_body_type_icon(
    body_type: str = Path(...),
    current_user: User = Depends(require_action("vehicle.fields.manage")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org_id(current_user)
    await delete_override(db, org_id, body_type)
    return {"ok": True}


@router.delete("")
async def reset_all_body_type_icons(
    current_user: User = Depends(require_action("vehicle.fields.manage")),
    db: AsyncSession = Depends(get_db),
):
    org_id = _require_org_id(current_user)
    await delete_all_overrides(db, org_id)
    return {"ok": True}
