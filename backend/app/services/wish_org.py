# -*- coding: utf-8 -*-
"""Организация заявки (Wish.org_id) — ЕДИНСТВЕННЫЙ источник правила (ПРАВИЛО №6).

Баг с прода (заявка №209, 22.10.2026): Лягин создал заявку кнопкой «на основе
плана» в карточке субсидии «ХРО_2026» (subsidies.org_id=28, «ХРО ВСКС»), а
wishes.org_id записался = 1 («ВСКС»). Причина — старый код считал org_id как
`org_ids[0]` из get_org_filter (list(set(...)) — порядок произвольный, по
факту брал организацию с наименьшим id) и полностью игнорировал организацию
выбранной субсидии. Последствие: согласующие заявки считались по чужой
организации (wish_approvals.py::list_users_with_org_key(db, wish.org_id, ...)),
видимость заявки — тоже не та. На проде нашлось 17 заявок с
wishes.org_id != subsidies.org_id.

Решение владельца: если у заявки есть субсидия — org_id заявки берётся из
subsidies.org_id. Без субсидии — активная организация пользователя (прежний
фолбэк).

Эта функция — единственное место, где считается org_id заявки; все роутеры/
сервисы, создающие или перепривязывающие Wish к субсидии, обязаны звать её, а
не повторять формулу (create_wish/update_wish/patch_wish_execution/copy_wish —
см. вызовы в routers/wishes.py и routers/wish_transitions.py).
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_org_filter, get_single_org_id
from app.models.user import User


def _fallback_org_id(current_user: User) -> Optional[int]:
    """Активная организация пользователя — прежнее поведение (без субсидии).

    get_single_org_id уже учитывает активную выборку (_active_org_id/
    _active_org_ids для superadmin); если он не смог определить одну
    организацию — старый фолбэк на первый элемент get_org_filter, затем
    current_user.org_id (ровно то, что было в коде до этого фикса)."""
    org_id = get_single_org_id(current_user)
    if org_id is not None:
        return org_id
    org_ids = get_org_filter(current_user)
    return org_ids[0] if org_ids else current_user.org_id


async def resolve_wish_org_id(
    db: AsyncSession,
    current_user: User,
    subsidy_id: Optional[int],
) -> Optional[int]:
    """Org_id для заявки, которую СОЗДАЁТ или ПРАВИТ пользователь (subsidy_id
    приходит из тела запроса — требует проверки видимости ДО использования её
    org_id, иначе можно создать/перепривязать заявку в чужой организации,
    ПРАВИЛО №8 п.2).

    subsidy_id задан → ensure_subsidy_visible (app/auth/object_visibility.py,
    уже единственный источник «видна ли субсидия пользователю», 404 на
    невидимую — переиспользуем, второй проверки не пишем); если у субсидии
    задан org_id — он и есть org_id заявки. Субсидия без org_id (общая/
    NULL) или subsidy_id не передан → _fallback_org_id (прежнее поведение)."""
    if subsidy_id is not None:
        from app.auth.object_visibility import ensure_subsidy_visible

        subsidy = await ensure_subsidy_visible(current_user, subsidy_id, db)
        if subsidy.org_id is not None:
            return subsidy.org_id

    return _fallback_org_id(current_user)


async def wish_org_id_for_subsidy_or_fallback(
    db: AsyncSession,
    subsidy_id: Optional[int],
    fallback_org_id: Optional[int],
) -> Optional[int]:
    """Та же формула «org субсидии, иначе фолбэк», но БЕЗ проверки видимости —
    для мест, где subsidy_id не пришёл от пользователя заново, а уже взят с
    существующего, ранее проверенного объекта (закупка авансового отчёта,
    app/services/advance_companion_wish.py): закупка уже создана, её
    subsidy_id — не вход от пользователя, который нужно было бы валидировать
    повторно (ПРАВИЛО №8 п.2 касается входа от пользователя, не чтения уже
    существующей записи). Второй механизм расчёта org_id не заводим —
    resolve_wish_org_id выше вызывает ту же логику «субсидия → её org_id»
    после отдельной проверки видимости, эта функция — её часть без гейта."""
    if subsidy_id is not None:
        from app.models.subsidy import Subsidy

        subsidy = await db.get(Subsidy, subsidy_id)
        if subsidy is not None and subsidy.org_id is not None:
            return subsidy.org_id

    return fallback_org_id
