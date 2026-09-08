"""Справочники отделов и должностей для автокомплита в карточке сотрудника.

ПЕРЕНЕСЕНО (не изменено) из app/routers/users.py при разрезании монолитного
роутера (Правило №5, сессия 2026-09-08). Тот же префикс /api/users. Пути
здесь двухсегментные (/dictionaries/departments, /dictionaries/positions) —
конфликта по форме с GET /{user_id} core-роутера нет, порядок регистрации
относительно него не важен.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter
from typing import Optional

router = APIRouter(prefix="/api/users", tags=["users"])

DEFAULT_DEPARTMENTS = [
    "Отдел закупок", "Бухгалтерия", "Юридический отдел", "Склад",
    "Отдел кадров", "ИТ-отдел", "Отдел продаж", "Административный отдел",
    "Финансовый отдел", "Отдел логистики", "Отдел маркетинга",
    "Производственный отдел", "Служба безопасности", "Канцелярия",
]

DEFAULT_POSITIONS = [
    "Начальник отдела", "Заместитель начальника отдела", "Ведущий специалист",
    "Главный специалист", "Специалист", "Менеджер", "Старший менеджер",
    "Бухгалтер", "Главный бухгалтер", "Юрист", "Кладовщик",
    "Администратор", "Секретарь", "Инженер", "Аналитик",
    "Руководитель направления", "Директор", "Заместитель директора",
]


@router.get("/dictionaries/departments")
async def get_department_names(
    org_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Default + custom departments used in this org (optionally filtered by ?org_id=N)."""
    from app.models.department import Department
    if org_id is not None:
        # Только primary org: у мульти-орг (UOA) юзеров User.department — строка
        # родной орги, через UOA-join чужие отделы утекали в список другой орги.
        q = (
            select(User.department)
            .where(
                User.department.isnot(None),
                User.department != "",
                User.org_id == org_id,
            )
            .distinct()
        )
        dq = select(Department.name).where(Department.org_id == org_id, Department.name.isnot(None))
    else:
        org_ids = get_org_filter(current_user)
        q = select(User.department).where(User.department.isnot(None), User.department != "").distinct()
        dq = select(Department.name).where(Department.name.isnot(None))
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
            dq = dq.where(Department.org_id.in_(org_ids))
    result = await db.execute(q)
    custom = {r[0] for r in result.all() if r[0]}
    dept_table = {r[0] for r in (await db.execute(dq)).all() if r[0]}
    if org_id is not None:
        # Конкретная орга → только её реальные отделы, без generic-шаблонов:
        # тестировщики принимали DEFAULT_DEPARTMENTS за «отделы всех организаций».
        return sorted(custom | dept_table)
    all_depts = sorted(set(DEFAULT_DEPARTMENTS) | custom | dept_table)
    return all_depts


@router.get("/dictionaries/positions")
async def get_position_names(
    org_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Default + custom positions used in this org (optionally filtered by ?org_id=N).

    Rule #6: должность сотрудника теперь в основном живёт в user_organizations,
    а не в users.position (legacy, актуален только для людей без единого
    членства) — поэтому автокомплит собирает варианты из ОБОИХ источников,
    иначе после перехода на UO новые должности переставали бы предлагаться.
    """
    from app.models.user_org_access import UserOrgAccess
    from app.models.user_organization import UserOrganization
    custom: set[str] = set()
    if org_id is not None:
        # Users whose primary org is org_id OR who have access via user_org_access
        q = (
            select(User.position)
            .outerjoin(UserOrgAccess, UserOrgAccess.user_id == User.id)
            .where(
                User.position.isnot(None),
                User.position != "",
                (User.org_id == org_id) | (UserOrgAccess.org_id == org_id),
            )
            .distinct()
        )
        uo_q = select(UserOrganization.position).where(
            UserOrganization.org_id == org_id,
            UserOrganization.position.isnot(None),
            UserOrganization.position != "",
        ).distinct()
    else:
        org_ids = get_org_filter(current_user)
        q = select(User.position).where(User.position.isnot(None), User.position != "").distinct()
        uo_q = select(UserOrganization.position).where(
            UserOrganization.position.isnot(None), UserOrganization.position != ""
        ).distinct()
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
            uo_q = uo_q.where(UserOrganization.org_id.in_(org_ids))
    result = await db.execute(q)
    custom.update(r[0] for r in result.all())
    uo_result = await db.execute(uo_q)
    custom.update(r[0] for r in uo_result.all())
    all_positions = sorted(set(DEFAULT_POSITIONS) | custom)
    return all_positions
