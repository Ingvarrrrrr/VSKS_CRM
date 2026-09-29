"""Карточка руководителя организации (по ЕГРЮЛ) — отдельная от подписанта.

Единственный источник данных — app.services.org_head (director_* на
Organization, resolve_org_head_user_id/refresh_director_from_egrul). Этот
роутер только читает/дёргает тот сервис и не заводит второго похода в
ЕГРЮЛ и второй логики сопоставления с сотрудником (Правило №6).

Права:
  • GET  — кто видит организацию (тот же гейт, что и GET /api/organizations/{id}
    в app.routers.organizations.get_organization, переиспользован импортом
    get_org_filter — копию гейта здесь не заводим).
  • POST /refresh — кто может редактировать организацию: те же роли, что и
    PUT /api/organizations/{id} (require_role('superadmin','admin','account_owner')
    в app.routers.organizations.update_organization).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter, require_role
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.services.documents.formatting import _format_initials_safe
from app.services.fio import compose_fio
from app.services.org_head import (
    _normalize_fio,
    get_org_director_full_name,
    refresh_director_from_egrul,
)
from app.services.org_requisites import org_requisites

router = APIRouter(tags=["organization-director"])


async def _check_view_access(db: AsyncSession, current_user: User, org_id: int) -> None:
    """Тот же гейт видимости, что у GET /api/organizations/{id}."""
    if current_user.role not in ('superadmin', 'account_owner'):
        visible = get_org_filter(current_user)
        if visible is not None and org_id not in visible:
            raise HTTPException(403, "Нет доступа к этой организации")


async def _load_org(db: AsyncSession, org_id: int) -> Organization:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    return org


async def _find_matching_employee(db: AsyncSession, org: Organization) -> dict | None:
    target_fio = _normalize_fio(org.director_last_name, org.director_first_name, org.director_middle_name)
    if not target_fio:
        return None
    rows = (await db.execute(
        select(User.id, User.last_name, User.first_name, User.middle_name)
        .distinct()
        .outerjoin(UserOrganization, UserOrganization.user_id == User.id)
        .where((User.org_id == org.id) | (UserOrganization.org_id == org.id))
    )).all()
    for uid, u_last, u_first, u_middle in rows:
        if _normalize_fio(u_last, u_first, u_middle) == target_fio:
            return {"id": uid, "full_name": compose_fio(u_last, u_first, u_middle)}
    return None


def _build_response(org: Organization, inn: str | None, employee: dict | None) -> dict:
    full = get_org_director_full_name(org)
    return {
        "last_name": org.director_last_name,
        "first_name": org.director_first_name,
        "middle_name": org.director_middle_name,
        "position": org.director_position,
        "fio_short": _format_initials_safe(full) if full else None,
        "employee": employee,
        "source": "egrul",
        "inn": inn,
    }


@router.get("/api/organizations/{org_id}/director")
async def get_organization_director(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_view_access(db, current_user, org_id)
    org = await _load_org(db, org_id)
    contractor = None
    if org.contractor_id:
        from app.models.contractor import Contractor
        contractor = await db.get(Contractor, org.contractor_id)
    inn = (org_requisites(org, contractor).get("inn") or None)
    employee = await _find_matching_employee(db, org)
    return _build_response(org, inn, employee)


@router.post("/api/organizations/{org_id}/director/refresh")
async def refresh_organization_director(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role('superadmin', 'admin', 'account_owner')),
):
    org = await _load_org(db, org_id)
    await refresh_director_from_egrul(db, org, force=True)
    await db.commit()
    await db.refresh(org)
    contractor = None
    if org.contractor_id:
        from app.models.contractor import Contractor
        contractor = await db.get(Contractor, org.contractor_id)
    inn = (org_requisites(org, contractor).get("inn") or None)
    employee = await _find_matching_employee(db, org)
    return _build_response(org, inn, employee)
