"""Построение восходящей цепочки согласующих для заявки (wish).

Источник иерархии — ЯВНЫЕ настраиваемые поля, НЕ UserHierarchy.manager_id:
  • Department.deputy_head_user_id / head_user_id / curator_user_id / parent_id
  • Organization.head_user_id
  • User.superior_user_id (ручной override реального подчинения)

Цепочка строится СНИЗУ ВВЕРХ от отдела автора заявки и обрезается на явно
выбранном верхнем согласующем (top_user_id) — всё, что выше него, отбрасывается.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization

_MAX_DEPTH = 30


async def _author_department(db: AsyncSession, author_id: int, org_id: int) -> Department | None:
    """Отдел автора в рамках org_id (первый с непустым dept_id)."""
    dept_id = (await db.execute(
        select(UserOrganization.dept_id).where(
            UserOrganization.user_id == author_id,
            UserOrganization.org_id == org_id,
            UserOrganization.dept_id.isnot(None),
        ).limit(1)
    )).scalar_one_or_none()
    if not dept_id:
        return None
    return await db.get(Department, dept_id)


async def _walk_superiors(db: AsyncSession, start_id: int) -> list[tuple[int, str]]:
    """Проход вверх по User.superior_user_id от start_id (не включая start_id)."""
    out: list[tuple[int, str]] = []
    seen = {start_id}
    cur = await db.get(User, start_id)
    depth = 0
    while cur is not None and cur.superior_user_id and depth < _MAX_DEPTH:
        sup_id = cur.superior_user_id
        if sup_id in seen:
            break
        seen.add(sup_id)
        out.append((sup_id, "Вышестоящий начальник"))
        cur = await db.get(User, sup_id)
        depth += 1
    return out


async def build_ascending_chain(
    db: AsyncSession, author_id: int, top_user_id: int, org_id: int
) -> list[dict]:
    """Вернуть [{user_id, role_name, full_name, order_num}] снизу вверх до top_user_id."""
    ordered: list[tuple[int, str]] = []
    seen: set[int] = {author_id}

    def add(uid, role):
        if uid and uid not in seen:
            seen.add(uid)
            ordered.append((uid, role))

    # 1. Дерево отделов автора: свой отдел (зам→начальник), затем вверх по parent_id
    dept = await _author_department(db, author_id, org_id)
    cur = dept
    depth = 0
    while cur is not None and depth < _MAX_DEPTH:
        if depth == 0:
            add(cur.deputy_head_user_id, "Зам.начальника отдела")
            add(cur.head_user_id, "Начальник отдела")
        else:
            add(cur.curator_user_id, "Курирующий зам")
            add(cur.deputy_head_user_id, "Зам.начальника подразделения")
            add(cur.head_user_id, "Начальник подразделения")
        cur = await db.get(Department, cur.parent_id) if cur.parent_id else None
        depth += 1

    # 2. Руководитель организации
    org = await db.get(Organization, org_id)
    if org is not None:
        add(org.head_user_id, "Руководитель организации")

    # 3. Override: явный вышестоящий начальник автора имеет приоритет —
    #    ставим его цепочку в начало (реальное подчинение перебивает оргструктуру).
    sup_chain = await _walk_superiors(db, author_id)
    if sup_chain:
        sup_ids = {u for u, _ in sup_chain}
        ordered = sup_chain + [(u, r) for (u, r) in ordered if u not in sup_ids]

    # 4. Обрезать на top_user_id (включительно). Если его нет в цепочке — добавить в конец.
    result_ids: list[tuple[int, str]] = []
    found = False
    for uid, role in ordered:
        result_ids.append((uid, role))
        if uid == top_user_id:
            found = True
            break
    if not found:
        result_ids.append((top_user_id, "Согласующий"))

    # 5. Обогатить именами + order_num
    uids = [u for u, _ in result_ids]
    users_map: dict[int, User] = {}
    if uids:
        for u in (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all():
            users_map[u.id] = u
    chain: list[dict] = []
    for i, (uid, role) in enumerate(result_ids):
        u = users_map.get(uid)
        chain.append({
            "user_id": uid,
            "role_name": role,
            "full_name": (u.full_name or u.username) if u else None,
            "order_num": i,
        })
    return chain
