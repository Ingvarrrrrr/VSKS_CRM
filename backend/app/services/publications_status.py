"""Хелперы обновления статуса PlatformPublication (волна резки publications.py)."""
import json
import ssl
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models.platform_publication import PlatformPublication


def _make_ssl_ctx() -> ssl.SSLContext:
    """SSL context compatible with Росэлторг / Фабрикант (TLS 1.2, specific cipher)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256:DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


# ── статус публикации ─────────────────────────────────────────────────────

async def _set_pub_success(
    pub_id: int,
    external_id: str = None,
    external_url: str = None,
    status: str = "published",
    platform_number: str = None,
    platform_state: str = None,
):
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.status = status
            pub.external_id = external_id
            pub.external_url = external_url
            pub.platform_number = platform_number
            pub.platform_state = platform_state
            if status == "published":
                pub.published_at = datetime.now(timezone.utc)
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_platform_number(pub_id: int, number: str):
    """Проставляет platform_number ДО рендера/прикрепления документов, чтобы
    печатная форма извещения показывала номер площадки, а не наш internal
    requestId (external_id). _set_pub_success ниже по потоку перезапишет тем
    же либо уточнённым номером."""
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.platform_number = number
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_error(pub_id: int, error_text: str):
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.status = "error"
            pub.error_text = error_text[:500]
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()


async def _set_pub_attachments_result(pub_id: int, results: list):
    """Сохраняет результат прикрепления документов в PlatformPublication.attachments_result."""
    async with async_session() as db:
        res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
        pub = res.scalar_one_or_none()
        if pub:
            pub.attachments_result = json.dumps(results, ensure_ascii=False)
            pub.updated_at = datetime.now(timezone.utc)
            await db.commit()

