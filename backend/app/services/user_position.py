"""Единственный источник резолюции и записи должности сотрудника (Правило №6).

Источник истины — ``user_organizations.position`` (должность по конкретной
организации). ``users.position`` — deprecated legacy-поле, читается/пишется
ТОЛЬКО как последний fallback, когда у пользователя нет ни одного членства
(``UserOrganization``) вообще. Как только у человека появляется хотя бы одно
членство, ``users.position`` перестаёт участвовать в резолюции для этого
пользователя (Правило: «один показатель — один источник истины»).

До этого модуля резолюция дублировалась (documents/contexts.py._resolve_user_position
и routers/hierarchy.py считали её каждый по-своему) и запись дублировалась
(routers/users.py копировал user.position → UO, routers/departments.py и
services/dept_role_sync.py писали UO напрямую). Теперь один читатель и один
писатель, остальной код обязан вызывать их, а не считать/писать position сам.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_organization import UserOrganization

__all__ = [
    "POSITION_UNSET",
    "UserPositionError",
    "UserPositionAmbiguousOrgError",
    "UserPositionNoMembershipError",
    "resolve_user_position",
    "bulk_load_memberships",
    "set_user_position",
]


# Сентинел «значение не передавали вообще» — отличает «position не менялась в
# этом запросе» (не трогать существующую запись) от «position явно очищена в
# null/пустую строку».
POSITION_UNSET = object()


class UserPositionError(Exception):
    """Базовая ошибка записи должности. .user_message — текст для HTTPException."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class UserPositionAmbiguousOrgError(UserPositionError):
    """org_id не передан, а членств несколько — писать некуда без уточнения."""

    def __init__(self):
        super().__init__("Укажите организацию: должность задаётся по организации")


class UserPositionNoMembershipError(UserPositionError):
    """org_id передан, но пользователь не состоит в этой организации."""

    def __init__(self):
        super().__init__(
            "Пользователь не состоит в указанной организации — сначала добавьте членство"
        )


def _ordered(memberships: Optional[Sequence[UserOrganization]]) -> list[UserOrganization]:
    return sorted(memberships or [], key=lambda m: m.id)


def resolve_user_position(
    user,
    org_id: Optional[int] = None,
    memberships: Optional[Sequence[UserOrganization]] = None,
) -> Optional[str]:
    """Возвращает должность пользователя, не выполняя запросов к БД.

    ``memberships`` — предзагруженный список ``UserOrganization`` этого
    пользователя (используйте :func:`bulk_load_memberships` для списков без
    N+1, либо один запрос на пользователя в единичных сценариях).

    Приоритет:
      1. Среди memberships есть строка с ``org_id == org_id`` (если org_id
         задан) → её position (может быть None — тогда результат None, мы НЕ
         подменяем должностью из чужой организации).
      2. org_id не задан (или под него нет ни одной строки — см. п.1, тогда
         результат уже вернулся): ровно одно членство → его position;
         несколько членств → первое по id (правило, ранее жившее только в
         routers/hierarchy.py — сохранено здесь).
      3. Ни одного членства вообще → ``users.position`` (legacy fallback).
    """
    ordered = _ordered(memberships)

    if not ordered:
        return (getattr(user, "position", None) or None) if user is not None else None

    if org_id is not None:
        match = next((m for m in ordered if m.org_id == org_id), None)
        if match is not None:
            return match.position or None
        # Членство есть, но не в этой организации — не путаем чужую должность
        # с должностью в запрошенной организации.
        return None

    if len(ordered) == 1:
        return ordered[0].position or None

    return next((m.position for m in ordered if m.position), None)


async def bulk_load_memberships(
    db: AsyncSession, user_ids: Iterable[int]
) -> dict[int, list[UserOrganization]]:
    """Одним запросом грузит все членства для набора пользователей.

    Возвращает user_id -> [UserOrganization, ...] (по возрастанию id).
    Используйте вместе с :func:`resolve_user_position` при построении списков
    сотрудников, чтобы не резолвить должность запросом на каждого.
    """
    ids = [uid for uid in {u for u in user_ids if u is not None}]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(UserOrganization)
            .where(UserOrganization.user_id.in_(ids))
            .order_by(UserOrganization.id)
        )
    ).scalars().all()
    out: dict[int, list[UserOrganization]] = {}
    for r in rows:
        out.setdefault(r.user_id, []).append(r)
    return out


async def set_user_position(
    db: AsyncSession,
    position: Optional[str],
    *,
    user=None,
    org_id: Optional[int] = None,
    dept_id: Optional[int] = None,
    membership: Optional[UserOrganization] = None,
) -> object:
    """Единственная точка записи должности сотрудника (существующая запись).

    Создание membership-строки НЕ входит в ответственность этой функции —
    вызывающий код обязан использовать существующий upsert членства (см.
    routers/users.py:_sync_user_department, routers/departments.py add_member,
    routers/departments.py import) и передать сюда уже найденную/только что
    созданную строку. Здесь только МЕНЯЕТСЯ поле position, commit делает
    вызывающий код (как и остальные функции этого домена — dept_role_sync).

    Режимы вызова:
      ``membership=<row>`` — строка уже однозначно найдена вызывающим кодом
        (например, по конкретному dept_id в departments.py) — пишем прямо в
        неё, org_id/dept_id игнорируются.
      ``org_id`` задан (без membership) — ищем среди членств пользователя
        первую по id строку с этим org_id. Нет ни одной → UserPositionNoMembershipError.
        Если у пользователя несколько строк в этой же организации (мульти-отдел)
        и важен конкретный отдел — передавайте dept_id или найденный membership
        напрямую, здесь это просто дополнительный фильтр.
      ``org_id`` не задан — ровно одно членство → пишем в него; несколько →
        UserPositionAmbiguousOrgError; ни одного → пишем в users.position
        (единственный случай, когда функция трогает legacy-поле User.position).
    """
    if membership is not None:
        membership.position = position
        return membership

    if user is None:
        raise ValueError("set_user_position: укажите membership= или user=")

    rows = (
        await db.execute(
            select(UserOrganization)
            .where(UserOrganization.user_id == user.id)
            .order_by(UserOrganization.id)
        )
    ).scalars().all()

    if org_id is not None:
        candidates = [m for m in rows if m.org_id == org_id]
        if dept_id is not None:
            narrowed = [m for m in candidates if m.dept_id == dept_id]
            if narrowed:
                candidates = narrowed
        if not candidates:
            raise UserPositionNoMembershipError()
        candidates[0].position = position
        return candidates[0]

    if not rows:
        user.position = position
        return user
    if len(rows) == 1:
        rows[0].position = position
        return rows[0]
    raise UserPositionAmbiguousOrgError()
