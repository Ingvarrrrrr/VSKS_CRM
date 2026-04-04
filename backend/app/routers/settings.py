import smtplib
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import require_role, ADMIN_ROLES
from app.database import get_db
from app.models.system_setting import SystemSetting

router = APIRouter(prefix="/api/settings", tags=["settings"])

SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_from_name", "smtp_ssl"]


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def set_setting(db: AsyncSession, key: str, value: str):
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


class SmtpSettingsIn(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: Optional[str] = None  # None = don't change
    smtp_from: str
    smtp_from_name: Optional[str] = None
    smtp_ssl: bool = False


class SmtpSettingsOut(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_from: str = ""
    smtp_from_name: str = ""
    smtp_ssl: bool = False
    is_configured: bool = False


@router.get("/smtp", response_model=SmtpSettingsOut)
async def get_smtp_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    host = await get_setting(db, "smtp_host") or ""
    port = int(await get_setting(db, "smtp_port") or 587)
    user = await get_setting(db, "smtp_user") or ""
    frm = await get_setting(db, "smtp_from") or ""
    frm_name = await get_setting(db, "smtp_from_name") or ""
    ssl = (await get_setting(db, "smtp_ssl") or "false") == "true"
    return SmtpSettingsOut(
        smtp_host=host, smtp_port=port, smtp_user=user,
        smtp_from=frm, smtp_from_name=frm_name, smtp_ssl=ssl,
        is_configured=bool(host and user),
    )


@router.put("/smtp", response_model=SmtpSettingsOut)
async def update_smtp_settings(
    data: SmtpSettingsIn,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    await set_setting(db, "smtp_host", data.smtp_host)
    await set_setting(db, "smtp_port", str(data.smtp_port))
    await set_setting(db, "smtp_user", data.smtp_user)
    await set_setting(db, "smtp_from", data.smtp_from)
    await set_setting(db, "smtp_from_name", data.smtp_from_name or "")
    await set_setting(db, "smtp_ssl", "true" if data.smtp_ssl else "false")
    if data.smtp_password is not None:
        await set_setting(db, "smtp_password", data.smtp_password)
    await db.commit()
    return await get_smtp_settings(db=db)


@router.post("/smtp/test")
async def test_smtp(
    to_email: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(*ADMIN_ROLES)),
):
    host = await get_setting(db, "smtp_host") or ""
    port = int(await get_setting(db, "smtp_port") or 587)
    user = await get_setting(db, "smtp_user") or ""
    password = await get_setting(db, "smtp_password") or ""
    frm = await get_setting(db, "smtp_from") or user
    ssl = (await get_setting(db, "smtp_ssl") or "false") == "true"

    if not host or not user:
        raise HTTPException(400, "SMTP не настроен")

    try:
        msg = MIMEText("Тестовое письмо из VSKS CRM. SMTP работает корректно.", "plain", "utf-8")
        msg["Subject"] = "Тест SMTP — VSKS CRM"
        msg["From"] = frm
        msg["To"] = to_email
        if ssl:
            import smtplib as _smtp
            server = _smtp.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
            server.starttls()
        server.login(user, password)
        server.sendmail(frm, to_email, msg.as_string())
        server.quit()
        return {"ok": True, "message": f"Письмо отправлено на {to_email}"}
    except Exception as e:
        raise HTTPException(400, f"Ошибка SMTP: {str(e)}")
