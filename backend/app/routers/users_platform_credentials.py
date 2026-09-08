"""Учётные данные площадок (Fabrikant/Roseltorg) для публикации от имени
конкретного сотрудника.

ПЕРЕНЕСЕНО (не изменено) из app/routers/users.py при разрезании монолитного
роутера (Правило №5, сессия 2026-09-08). Тот же префикс /api/users. Пути
здесь трёх/двухсегментные (/{user_id}/platform-credentials[/{platform}]) —
конфликта по форме с GET /{user_id} core-роутера нет, порядок регистрации
относительно него не важен.

_assert_platform_access определена (перенесена как есть), но, как и в
исходном users.py, ни один эндпоинт её не вызывает — каждый делает свою
инлайн-проверку прав (см. дефект в отчёте о разрезании).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.jwt import get_current_user
from app.schemas.schemas import PlatformCredentialOut, PlatformCredentialUpsert
from typing import List

router = APIRouter(prefix="/api/users", tags=["users"])

ALLOWED_PLATFORMS = {"fabrikant", "roseltorg"}


def _assert_platform_access(current_user, user_id: int, db=None):
    """Проверяет, может ли current_user читать/менять креды user_id.
    Разрешено: сам пользователь ИЛИ имеет доступ к вкладке 'staff'.
    Возбуждает HTTPException 403 с понятной причиной по-русски.
    """
    if current_user.id == user_id:
        return  # сам себе — всегда можно
    # Не сам — требуется доступ к вкладке staff (выполнится в роутере через require_tab)
    # Здесь мы уже внутри роутеров с manual check, поэтому просто сообщаем причину.
    raise HTTPException(
        status_code=403,
        detail="Просмотр и изменение учётных данных площадок другого пользователя "
               "доступно только сотрудникам с доступом к разделу «Персонал».",
    )


@router.get("/{user_id}/platform-credentials", response_model=List[PlatformCredentialOut])
async def list_platform_credentials(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Возвращает список учётных данных площадок для пользователя.
    Пароль НИКОГДА не возвращается — только has_password: true.
    Доступ: сам пользователь ИЛИ вкладка 'staff'.
    """
    from app.auth.permissions import get_effective_tabs, _active_org
    # Проверяем права вручную
    if current_user.id != user_id:
        active_org = _active_org(current_user)
        effective = await get_effective_tabs(current_user, db, active_org)
        if "staff" not in effective:
            raise HTTPException(
                status_code=403,
                detail="Просмотр учётных данных площадок другого пользователя "
                       "доступно только сотрудникам с доступом к разделу «Персонал».",
            )

    from app.models.user_platform_credential import UserPlatformCredential
    rows = (await db.execute(
        select(UserPlatformCredential).where(UserPlatformCredential.user_id == user_id)
    )).scalars().all()
    return [
        PlatformCredentialOut(platform=r.platform, login=r.login, has_password=True)
        for r in rows
    ]


@router.put("/{user_id}/platform-credentials/{platform}", response_model=PlatformCredentialOut)
async def upsert_platform_credential(
    user_id: int,
    platform: str,
    body: PlatformCredentialUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert учётных данных площадки для пользователя.
    Если password пуст/None — обновляет только login.
    Доступ: сам пользователь ИЛИ вкладка 'staff'.
    """
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(400, f"Неизвестная площадка: {platform}. Допустимые: {', '.join(sorted(ALLOWED_PLATFORMS))}")

    from app.auth.permissions import get_effective_tabs, _active_org
    if current_user.id != user_id:
        active_org = _active_org(current_user)
        effective = await get_effective_tabs(current_user, db, active_org)
        if "staff" not in effective:
            raise HTTPException(
                status_code=403,
                detail="Изменение учётных данных площадок другого пользователя "
                       "доступно только сотрудникам с доступом к разделу «Персонал».",
            )

    from app.models.user_platform_credential import UserPlatformCredential
    from app.services.cred_crypto import encrypt_password

    row = (await db.execute(
        select(UserPlatformCredential).where(
            UserPlatformCredential.user_id == user_id,
            UserPlatformCredential.platform == platform,
        )
    )).scalar_one_or_none()

    if row is None:
        # Новая запись: пароль обязателен
        if not body.password:
            raise HTTPException(400, "Пароль обязателен при создании учётных данных площадки.")
        row = UserPlatformCredential(
            user_id=user_id,
            platform=platform,
            login=body.login,
            encrypted_password=encrypt_password(body.password),
        )
        db.add(row)
    else:
        row.login = body.login
        if body.password:
            row.encrypted_password = encrypt_password(body.password)

    await db.commit()
    return PlatformCredentialOut(platform=platform, login=row.login, has_password=True)


@router.delete("/{user_id}/platform-credentials/{platform}")
async def delete_platform_credential(
    user_id: int,
    platform: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет учётные данные площадки для пользователя.
    Доступ: сам пользователь ИЛИ вкладка 'staff'.
    """
    from app.auth.permissions import get_effective_tabs, _active_org
    if current_user.id != user_id:
        active_org = _active_org(current_user)
        effective = await get_effective_tabs(current_user, db, active_org)
        if "staff" not in effective:
            raise HTTPException(
                status_code=403,
                detail="Удаление учётных данных площадок другого пользователя "
                       "доступно только сотрудникам с доступом к разделу «Персонал».",
            )

    from app.models.user_platform_credential import UserPlatformCredential
    row = (await db.execute(
        select(UserPlatformCredential).where(
            UserPlatformCredential.user_id == user_id,
            UserPlatformCredential.platform == platform,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Учётные данные для указанной площадки не найдены.")
    await db.delete(row)
    await db.commit()
    return {"ok": True}
