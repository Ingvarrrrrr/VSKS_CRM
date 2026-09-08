"""Фото и скан водительского удостоверения КОНКРЕТНОГО пользователя (не «я»,
см. users_me.py), + синхронизация карточки сотрудника в контрагента.

ПЕРЕНЕСЕНО (не изменено) из app/routers/users.py при разрезании монолитного
роутера (Правило №5, сессия 2026-09-08). Тот же префикс /api/users. Пути
здесь двухсегментные (/{user_id}/photo, /{user_id}/license-scan,
/{user_id}/sync-contractor) — конфликта по форме с GET /{user_id} core-роутера
нет (сегментов больше), порядок регистрации относительно него не важен.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.jwt import get_current_user
from app.auth.permissions import require_action, require_tab

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user_id}/photo")
async def get_user_photo(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return {"photo_url": user.profile_photo}


@router.put("/{user_id}/photo")
async def set_user_photo(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    photo_url = body.get("photo_url")
    if not photo_url or not isinstance(photo_url, str):
        raise HTTPException(422, "photo_url required")
    user.profile_photo = photo_url
    await db.commit()
    return {"ok": True}


@router.delete("/{user_id}/photo")
async def delete_user_photo(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.profile_photo = None
    await db.commit()
    return {"ok": True}


@router.get("/{user_id}/license-scan")
async def get_user_license_scan(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return {"license_scan": user.license_scan}


@router.put("/{user_id}/license-scan")
async def set_user_license_scan(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    scan = body.get("license_scan")
    if not scan or not isinstance(scan, str) or not scan.startswith("data:image/"):
        raise HTTPException(422, "Скан должен быть data:image/...;base64,...")
    if len(scan) > 3_000_000:
        raise HTTPException(422, "Скан слишком большой (макс 3 МБ)")
    user.license_scan = scan
    await db.commit()
    return {"ok": True}


@router.delete("/{user_id}/license-scan")
async def delete_user_license_scan(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.license_scan = None
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sync user to contractors
# ---------------------------------------------------------------------------

@router.post("/{user_id}/sync-contractor")
async def sync_user_to_contractor(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_action('user.manage')),
):
    """Create or update a Contractor record from user data (same org, filtered accordingly)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if not user.full_name and not user.inn:
        raise HTTPException(400, "У сотрудника нет ни ФИО, ни ИНН — нечего записывать")

    from app.models.contractor import Contractor

    # Try to find existing contractor by INN or by name within same org
    contractor = None
    if user.inn:
        contractor = (await db.execute(
            select(Contractor).where(
                Contractor.inn == user.inn,
                Contractor.org_id == user.org_id,
            )
        )).scalar_one_or_none()
    if not contractor and user.full_name:
        contractor = (await db.execute(
            select(Contractor).where(
                Contractor.name == user.full_name,
                Contractor.org_id == user.org_id,
            )
        )).scalar_one_or_none()

    if contractor:
        if user.full_name: contractor.name = user.full_name
        if user.inn: contractor.inn = user.inn
        if user.phone: contractor.phone = user.phone
        if user.email: contractor.email = user.email
        contractor.contact_person = user.full_name
        await db.commit()
        return {"ok": True, "action": "updated", "contractor_id": contractor.id}
    else:
        c = Contractor(
            name=user.full_name or user.username,
            inn=user.inn,
            phone=user.phone,
            email=user.email,
            contact_person=user.full_name,
            org_type="Физ.лицо",
            org_id=user.org_id,
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return {"ok": True, "action": "created", "contractor_id": c.id}
