"""Двусторонняя синхронизация «должность члена отдела ↔ начальник/зам отдела».

Проблема: у отдела есть явные поля head_user_id / deputy_head_user_id (карточка
отдела), а у члена отдела — position в user_organizations («Начальник отдела»,
«Заместитель начальника отдела»). Раньше эти два механизма жили отдельно.

Здесь они сшиваются в обе стороны, СТРОГО на уровне конкретного членства
(user, org, dept): человек в разных отделах может занимать разные должности.

Функции только МУТИРУЮТ объекты в текущей сессии — commit делает вызывающий код.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user_organization import UserOrganization

POSITION_HEAD = "Начальник отдела"
POSITION_DEPUTY = "Заместитель начальника отдела"


async def _membership(db: AsyncSession, dept: Department, user_id: int) -> UserOrganization | None:
    return (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user_id,
            UserOrganization.org_id == dept.org_id,
            UserOrganization.dept_id == dept.id,
        )
    )).scalar_one_or_none()


async def _set_member_position(db, dept, user_id, position):
    m = await _membership(db, dept, user_id)
    if m is not None:
        m.position = position


async def _clear_member_position(db, dept, user_id, expected):
    """Снять должность у члена, только если она совпадает с ожидаемой (не трогаем
    произвольные должности)."""
    m = await _membership(db, dept, user_id)
    if m is not None and m.position == expected:
        m.position = None


async def sync_head_from_position(db: AsyncSession, dept: Department, user_id: int, position: str | None):
    """Должность члена изменилась → отразить в head_user_id / deputy_head_user_id отдела."""
    if position == POSITION_HEAD:
        if dept.head_user_id and dept.head_user_id != user_id:
            await _clear_member_position(db, dept, dept.head_user_id, POSITION_HEAD)
        dept.head_user_id = user_id
        # человек не может быть одновременно и начальником, и замом
        if dept.deputy_head_user_id == user_id:
            dept.deputy_head_user_id = None
    elif position == POSITION_DEPUTY:
        if dept.deputy_head_user_id and dept.deputy_head_user_id != user_id:
            await _clear_member_position(db, dept, dept.deputy_head_user_id, POSITION_DEPUTY)
        dept.deputy_head_user_id = user_id
        if dept.head_user_id == user_id:
            dept.head_user_id = None
    else:
        # Должность стала не-начальнической → снять человека с роли, если он её занимал.
        if dept.head_user_id == user_id:
            dept.head_user_id = None
        if dept.deputy_head_user_id == user_id:
            dept.deputy_head_user_id = None


async def sync_position_from_head(
    db: AsyncSession, dept: Department,
    old_head: int | None = None, old_deputy: int | None = None,
):
    """head_user_id / deputy_head_user_id отдела изменились → проставить должности членам."""
    if old_head and old_head != dept.head_user_id:
        await _clear_member_position(db, dept, old_head, POSITION_HEAD)
    if dept.head_user_id:
        await _set_member_position(db, dept, dept.head_user_id, POSITION_HEAD)

    if old_deputy and old_deputy != dept.deputy_head_user_id:
        await _clear_member_position(db, dept, old_deputy, POSITION_DEPUTY)
    if dept.deputy_head_user_id:
        await _set_member_position(db, dept, dept.deputy_head_user_id, POSITION_DEPUTY)


async def clear_role_on_removal(db: AsyncSession, dept: Department, user_id: int):
    """Человек выведен из отдела → снять с него роль начальника/зама этого отдела."""
    if dept.head_user_id == user_id:
        dept.head_user_id = None
    if dept.deputy_head_user_id == user_id:
        dept.deputy_head_user_id = None
