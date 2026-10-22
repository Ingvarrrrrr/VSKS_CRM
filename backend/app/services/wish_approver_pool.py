# -*- coding: utf-8 -*-
"""Пул кандидатов в согласующие заявки (Wish) — единственное место, где
считается «кого вообще можно поставить согласующим заявки» (ПРАВИЛО №6).

Владелец (22.10.2026): «В согласование необходимости закупки можно вообще
кого угодно включить» — согласующим заявки (и верхним, и любым другим в
цепочке) может быть ЛЮБОЙ пользователь аккаунта, без проверки конкретных
прав (wish.approve/subsidy.edit и т.п. — это про деньги, не про согласование
необходимости закупки, см. правило №3 решений владельца). Единственное
серверное ограничение — пользователь должен быть из того же аккаунта
(контура), что и организация заявки, иначе согласующим можно было бы
подставить постороннего (дыра: POST /approvers не проверял user_id вовсе).

Контур — app.auth.visibility.compute_account_contour_org_ids (канонический
расчёт, единственный, см. её докстринг). «Пользователь организации» внутри
контура — тот же расчёт «штата», что и везде (ПРАВИЛО №6, не второй
расчёт): app.services.service_note_initiators._staff_conditions (primary
User.org_id ИЛИ членство user_organizations) ОБЪЕДИНЁННЫЙ с
_org_access_conditions (персональный доступ user_org_access) — точно тот
же союз формул, что использует app/routers/users.py::list_users в режиме
explicit_assign_mode для «кого можно назначить».
"""
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException


async def approver_pool_user_ids(db: AsyncSession, org_id: int) -> set[int]:
    """Все пользователи контура аккаунта организации org_id — пул кандидатов
    в согласующие заявки этой организации. Пустой org_id → пустой пул (заявка
    без организации не ожидается, но на всякий случай не отдаём всех)."""
    if not org_id:
        return set()

    from app.auth.visibility import compute_account_contour_org_ids
    from app.services.service_note_initiators import (
        _staff_conditions,
        _org_access_conditions,
    )
    from app.models.user import User

    contour_org_ids = await compute_account_contour_org_ids(db, org_id)
    ids = contour_org_ids | {int(org_id)}
    if not ids:
        return set()

    conds = _staff_conditions(list(ids)) + _org_access_conditions(list(ids))
    rows = (await db.execute(select(User.id).where(or_(*conds)))).scalars().all()
    return {int(x) for x in rows}


async def assert_approver_in_pool(db: AsyncSession, org_id: int, user_id: int) -> None:
    """400, если user_id не входит в пул кандидатов организации org_id (см.
    approver_pool_user_ids) — единственная серверная проверка для
    согласующего заявки (ни верхнего, ни любого добавленного вручную: права
    на согласование необходимости закупки владелец сознательно НЕ ограничивает,
    22.10.2026)."""
    pool = await approver_pool_user_ids(db, org_id)
    if user_id not in pool:
        raise HTTPException(
            400, "Согласующим можно выбрать только сотрудника вашего аккаунта",
        )
