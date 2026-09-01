"""Единая точка правды: какой аккаунт (root_org_id) получает НОВАЯ организация.

Организация не может остаться «ничейной» вне контура ни одного аккаунта —
единственное законное исключение: POST /api/register создаёт корень НОВОГО
аккаунта и намеренно НЕ вызывает этот хелпер (org.root_org_id там пуст, потому
что эта org и есть корень).

Баг, который этот модуль закрывает (2026-09-01): при создании организации
суперадмином (organizations.py, ветка «standalone org») root_org_id вообще не
проставлялся — так региональные отделения ВСКС (ХРО, Донецкое РО, ЛУГРО)
стали организациями без аккаунта. Правило теперь одно и применяется во всех
путях создания Organization кроме /register:
  1) явный запрошенный аккаунт (доступно только superadmin через выбор в
     форме) — резолвим к истинному корню на случай, если выбрали дочернюю
     организацию, а не головную;
  2) иначе — аккаунт вызывающего контекста (`fallback_org_id`, обычно
     current_user.org_id), тоже резолвим к корню;
  3) если ни того ни другого нет — явная ошибка, а не молчаливый NULL.

Принимает голый org_id (а не объект User), чтобы одинаково работать и в HTTP
эндпоинтах (fallback_org_id=current_user.org_id), и в фоновых задачах без
current_user — напр. стартовый бэкафилл в app/__init__.py, где источник
аккаунта — org_id уже существующей субсидии, а не залогиненный пользователь.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


async def resolve_new_org_root_id(
    db: AsyncSession,
    fallback_org_id: Optional[int],
    requested_root_org_id: Optional[int] = None,
) -> int:
    """Вернуть root_org_id для новой Organization (никогда не None).

    `requested_root_org_id` должен передаваться вызывающим ТОЛЬКО когда это
    явный осознанный выбор пользователя (сейчас — superadmin в форме
    создания организации). Для остальных ролей/контекстов вызывающий обязан
    передавать None, чтобы нельзя было привязать организацию к чужому
    аккаунту.

    `fallback_org_id` — org_id аккаунта по умолчанию, когда явного выбора нет
    (обычно current_user.org_id; для фоновых задач — org_id уже существующей
    связанной записи).
    """
    target_org_id = requested_root_org_id or fallback_org_id

    if not target_org_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Не указан аккаунт (головная организация) для новой организации — "
                "выберите его явно."
            ),
        )

    org = await db.get(Organization, target_org_id)
    if not org:
        raise HTTPException(
            status_code=400,
            detail=f"Организация-аккаунт с id={target_org_id} не найдена.",
        )

    # Истинный корень: если выбрали/унаследовали дочернюю org, поднимаемся к
    # её root_org_id; если это уже корень (root_org_id IS NULL) — берём её id.
    return int(org.root_org_id or org.id)
