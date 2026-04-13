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
