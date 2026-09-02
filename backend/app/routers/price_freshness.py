"""Настройка сроков актуальности цены по категориям — владелец, 2026-08-29.

Владелец: «Срок актуальности РАЗНЫЙ для разных видов товаров: бытовые — до
2 месяцев, продукты питания — около 2 недель. Значит нужны настраиваемые
правила по категориям». GET доступен любому авторизованному (нужно, чтобы
фронт мог показать актуальные TTL в подсказках), PUT — только
администраторам организации (ADMIN_ROLES уже включает org_admin — см.
app/auth/jwt.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, ADMIN_ROLES
from app.database import get_db
from app.models.price_freshness_rule import PriceFreshnessRule
from app.models.user import User
from app.services.price_freshness import DEFAULT_TTL_DAYS

router = APIRouter(prefix="/api/price-freshness", tags=["price-freshness"])


class PriceFreshnessRuleOut(BaseModel):
    id: int
    org_id: Optional[int] = None
    scope_kind: str
    scope_key: str
    ttl_days: int
    model_config = {"from_attributes": True}


class PriceFreshnessRuleIn(BaseModel):
    scope_kind: str  # 'default' | 'category' | 'product_type' | 'item_kind'
    scope_key: str
    ttl_days: int


class PriceFreshnessRulesOut(BaseModel):
    rules: List[PriceFreshnessRuleOut]
    effective_default_ttl_days: int


_VALID_SCOPE_KINDS = ("default", "category", "product_type", "item_kind")


@router.get("/rules", response_model=PriceFreshnessRulesOut)
async def get_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Правила текущей организации (org_id пользователя) + глобальные
    (org_id IS NULL), плюс эффективный дефолт."""
    org_id = current_user.org_id
    q = select(PriceFreshnessRule)
    if org_id is not None:
        q = q.where(
            (PriceFreshnessRule.org_id.is_(None)) | (PriceFreshnessRule.org_id == org_id)
        )
    else:
        q = q.where(PriceFreshnessRule.org_id.is_(None))
    rows = (await db.execute(q)).scalars().all()

    effective_default = DEFAULT_TTL_DAYS
    for r in rows:
        if r.scope_kind == "default" and r.scope_key == "*":
            effective_default = r.ttl_days
            if r.org_id == org_id and org_id is not None:
                break  # org-override побеждает global — но продолжаем сканировать на случай порядка

    return PriceFreshnessRulesOut(
        rules=[PriceFreshnessRuleOut.model_validate(r) for r in rows],
        effective_default_ttl_days=effective_default,
    )


@router.put("/rules", response_model=PriceFreshnessRulesOut)
async def update_rules(
    items: List[PriceFreshnessRuleIn],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Заменить набор правил ТЕКУЩЕЙ организации (org_id пользователя).
    Глобальные правила (org_id IS NULL) этим эндпоинтом не трогаются —
    только superadmin через прямой доступ к БД может менять дефолты для
    всех организаций (сознательно не даём этого через API, чтобы одна
    организация не смогла подменить дефолт другим)."""
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Недостаточно прав для изменения сроков актуальности цены")
    org_id = current_user.org_id
    if not org_id:
        raise HTTPException(400, "Пользователь без организации не может настраивать сроки актуальности")

    for item in items:
        if item.scope_kind not in _VALID_SCOPE_KINDS:
            raise HTTPException(422, {
                "code": "invalid_scope_kind",
                "message": f"Недопустимый scope_kind: {item.scope_kind}. Допустимо: {', '.join(_VALID_SCOPE_KINDS)}",
            })
        if item.ttl_days <= 0:
            raise HTTPException(422, {
                "code": "invalid_ttl_days",
                "message": "Срок актуальности должен быть положительным числом дней",
            })

    await db.execute(delete(PriceFreshnessRule).where(PriceFreshnessRule.org_id == org_id))
    for item in items:
        db.add(PriceFreshnessRule(
            org_id=org_id,
            scope_kind=item.scope_kind,
            scope_key=item.scope_key,
            ttl_days=item.ttl_days,
        ))
    await db.commit()

    return await get_rules(db=db, current_user=current_user)
