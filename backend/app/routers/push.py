from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from pydantic import BaseModel
from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.user import User
import os

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscribeBody(BaseModel):
    endpoint: str
    keys: dict  # {p256dh: str, auth: str}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Upsert: delete old sub for same endpoint, insert new
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == body.endpoint,
        )
    )
    sub = PushSubscription(
        user_id=current_user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.get("p256dh", ""),
        auth=body.keys.get("auth", ""),
    )
    db.add(sub)
    await db.commit()
    return {"ok": True}


@router.get("/vapid-key")
async def get_vapid_key():
    return {"key": os.environ.get("VAPID_PUBLIC_KEY", "")}


@router.get("/diagnostics")
async def push_diagnostics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 26-CC: диагностика push для отладки PWA badge на iOS/Android.

    Возвращает:
      - vapid_configured: backend готов слать push (есть VAPID_PRIVATE_KEY)
      - vapid_public_present: есть VAPID_PUBLIC_KEY (фронт может subscribe)
      - my_subscriptions: число подписок текущего user'а
      - total_subscriptions: всего подписок в БД
      - pywebpush_available: модуль установлен
    """
    from sqlalchemy import select, func

    has_private = bool(os.environ.get("VAPID_PRIVATE_KEY"))
    has_public = bool(os.environ.get("VAPID_PUBLIC_KEY"))

    try:
        import pywebpush  # noqa: F401
        pywebpush_ok = True
    except ImportError:
        pywebpush_ok = False

    my_subs = (await db.execute(
        select(func.count(PushSubscription.id))
        .where(PushSubscription.user_id == current_user.id)
    )).scalar() or 0

    total_subs = (await db.execute(
        select(func.count(PushSubscription.id))
    )).scalar() or 0

    return {
        "vapid_configured": has_private and has_public,
        "vapid_public_present": has_public,
        "vapid_private_present": has_private,
        "pywebpush_available": pywebpush_ok,
        "my_subscriptions": my_subs,
        "total_subscriptions": total_subs,
        "user_id": current_user.id,
    }


@router.post("/test")
async def push_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 26-CC: отправить тестовый push текущему user'у для отладки бейджа."""
    import asyncio
    from app.routers.chat import _send_push_notifications
    asyncio.create_task(_send_push_notifications(
        participant_ids=[current_user.id],
        title="Тест push",
        body="Если видишь — push работает. Если на иконке появилась цифра — badge тоже работает.",
        db=db,
    ))
    return {"ok": True, "user_id": current_user.id}
