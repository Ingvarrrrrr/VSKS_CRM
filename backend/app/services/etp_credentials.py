"""Сервис разрешения учётных данных электронных торговых площадок (ЭТП).

Правило №6 и План 2026-10-30:
Ключи берутся из Organization субсидии закупки (purchase.subsidy.org_id).
Общий ключ сервера из .env разрешён ТОЛЬКО если ИНН организации субсидии = ВСКС (7731178803).
ИНН организатора на площадке сверяется с ИНН организации субсидии.
"""
import base64
import json
import logging
import os
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organization import Organization
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.cred_crypto import decrypt_password

logger = logging.getLogger(__name__)

VSKS_INN = "7731178803"


def extract_organizer_inn_from_jwt(jwt_token: str) -> Optional[str]:
    """Извлекает ИНН организации из payload JWT-токена Росэлторга (если присутствует)."""
    if not jwt_token or "." not in jwt_token:
        return None
    try:
        parts = jwt_token.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
            inn = (
                claims.get("inn")
                or claims.get("company_inn")
                or claims.get("companyInn")
                or claims.get("customer_inn")
                or (claims.get("company") or {}).get("inn")
                or (claims.get("user") or {}).get("inn")
            )
            return str(inn).strip() if inn else None
    except Exception as e:
        logger.debug("Failed to decode JWT claims for organizer INN: %s", e)
    return None


def verify_organizer_inn(organizer_inn: Optional[str], org_inn: Optional[str], org_name: str) -> None:
    """Сверяет ИНН организатора площадки с ИНН организации субсидии."""
    if organizer_inn and org_inn:
        clean_org_inn = org_inn.strip()
        clean_plat_inn = organizer_inn.strip()
        if clean_plat_inn and clean_org_inn and clean_plat_inn != clean_org_inn:
            raise HTTPException(
                422,
                f"ИНН ключа площадки ({clean_plat_inn}) не совпадает с ИНН организации субсидии «{org_name}» ({clean_org_inn})",
            )


async def resolve_purchase_etp_credentials(
    db: AsyncSession,
    purchase_id: int,
    platform: str,
) -> dict:
    """Разрешает учётные данные площадки для конкретной закупки.

    Возвращает dict:
      - ok: bool
      - error: Optional[str]
      - org_id: Optional[int]
      - org_name: str
      - org_inn: str
      - token: str (для roseltorg_rb)
      - login: str (для fabrikant)
      - password: str (для fabrikant)
    """
    res = await db.execute(select(Purchase).where(Purchase.id == purchase_id))
    p = res.scalar_one_or_none()
    if not p:
        return {"ok": False, "error": "Закупка не найдена", "org_name": "", "org_inn": ""}

    org: Optional[Organization] = None
    if p.subsidy_id:
        sub_res = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
        subsidy = sub_res.scalar_one_or_none()
        if subsidy and subsidy.org_id:
            org_res = await db.execute(
                select(Organization)
                .options(selectinload(Organization.contractor))
                .where(Organization.id == subsidy.org_id)
            )
            org = org_res.scalar_one_or_none()

    if org:
        org_name = org.name or (org.contractor.name if org.contractor else None) or f"Организация #{org.id}"
        org_inn = (org.inn or (org.contractor.inn if org.contractor else None) or "").strip()
        org_id = org.id
    else:
        org_name = "ВСКС"
        org_inn = VSKS_INN
        org_id = None

    if platform == "roseltorg_rb":
        token: Optional[str] = None
        if org and org.roseltorg_token_encrypted:
            try:
                token = decrypt_password(org.roseltorg_token_encrypted)
            except Exception as e:
                logger.error("Failed to decrypt roseltorg token for org %s: %s", org.id, e)
                token = None

        if not token:
            # Общий ключ сервера из .env разрешён ТОЛЬКО если ИНН организации = ВСКС
            if org_inn == VSKS_INN or org_id is None:
                token = os.getenv("ROSELTORG_TOKEN", "").strip() or None

        if not token:
            return {
                "ok": False,
                "error": f"У организации «{org_name}» нет ключа Росэлторга — добавьте в карточке организации",
                "org_id": org_id,
                "org_name": org_name,
                "org_inn": org_inn,
            }

        return {
            "ok": True,
            "platform": "roseltorg_rb",
            "token": token,
            "org_id": org_id,
            "org_name": org_name,
            "org_inn": org_inn,
        }

    elif platform == "fabrikant":
        login: Optional[str] = None
        password: Optional[str] = None
        if org and org.fabrikant_login and org.fabrikant_password_encrypted:
            login = org.fabrikant_login.strip() or None
            try:
                password = decrypt_password(org.fabrikant_password_encrypted)
            except Exception as e:
                logger.error("Failed to decrypt fabrikant password for org %s: %s", org.id, e)
                password = None

        if not login or not password:
            if org_inn == VSKS_INN or org_id is None:
                login = os.getenv("FABRIKANT_LOGIN", "").strip() or None
                password = os.getenv("FABRIKANT_PASSWORD", "").strip() or None

        if not login or not password:
            return {
                "ok": False,
                "error": f"У организации «{org_name}» нет учётных данных Фабриканта — добавьте в карточке организации",
                "org_id": org_id,
                "org_name": org_name,
                "org_inn": org_inn,
            }

        return {
            "ok": True,
            "platform": "fabrikant",
            "login": login,
            "password": password,
            "org_id": org_id,
            "org_name": org_name,
            "org_inn": org_inn,
        }

    return {
        "ok": False,
        "error": f"Неподдерживаемая площадка: {platform}",
        "org_id": org_id,
        "org_name": org_name,
        "org_inn": org_inn,
    }
