"""Единый гейт «закупка видна и у пользователя есть право денежной операции
в её организации/субсидии» (аудит безопасности 20.10.2026, ПРАВИЛО №6/№8).

Повод: payments.py и bank_statements_registry.py проверяли только ПРАВО
(require_action/has_org_key — "есть ли ключ в ЛЮБОЙ своей орге"), но не
принадлежность самого объекта (Purchase/BankPayment) пользователю — закупка
или банковский платёж чужой организации были доступны по id. Этот файл не
вводит вторую проверку видимости — он переиспользует:

  - ensure_purchase_visible (app.auth.object_visibility) — тот же гейт
    видимости закупки по id, что и GET /api/purchases/{id}.
  - has_org_key (app.auth.permissions) — ту же орг-осознанную проверку
    права, что и везде в проекте, с учётом точечного грант на субсидию.

Вызывается из routers/payments.py (создание/удаление Payment) и
routers/bank_statements_registry.py (confirm/match строки выписки на
закупку/договор) — второй копии проверки нигде не писать (Правило №6)."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User


async def get_purchase_org_id(db: AsyncSession, purchase: Purchase) -> Optional[int]:
    """Орг, в которой лежит закупка — через её субсидию (у Purchase своей
    колонки org_id нет). None — закупка без субсидии; has_org_key в этом
    случае проверяет только общий (не орг-специфичный) эффективный набор."""
    if purchase.subsidy_id is None:
        return None
    subsidy = await db.get(Subsidy, purchase.subsidy_id)
    return subsidy.org_id if subsidy else None


async def ensure_purchase_payment_access(
    user: User, db: AsyncSession, purchase_id: int, action_key: str,
) -> Purchase:
    """Закупка видна пользователю (иначе 404 — тот же гейт, что у
    /api/purchases/{id}) И у него есть action_key именно в её орге/субсидии
    (иначе 403). Используется для любой денежной операции над оплатами
    закупки: создание/удаление Payment, подтверждение/матчинг строки
    банковской выписки на эту закупку."""
    from app.auth.object_visibility import ensure_purchase_visible
    from app.auth.permissions import has_org_key

    purchase = await ensure_purchase_visible(user, purchase_id, db)

    org_id = await get_purchase_org_id(db, purchase)
    if not await has_org_key(user, db, org_id, action_key, subsidy_id=purchase.subsidy_id):
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав на операции с оплатами этой закупки",
        )
    return purchase


async def ensure_purchase_matches_bank_payment_org(
    purchase: Purchase, db: AsyncSession, bp_org_id: Optional[int],
) -> None:
    """Закупка принадлежит той же организации, что и банковский платёж
    (BankPayment.org_id) — нельзя разнести строку выписки одной орги на
    закупку другой. bp_org_id=None (соглашение в выписке не опознано) —
    проверку пропускаем, доступ к самому BankPayment уже отфильтрован
    _row_visible/require_action в вызывающем роуте."""
    if bp_org_id is None:
        return
    purchase_org_id = await get_purchase_org_id(db, purchase)
    if purchase_org_id is not None and purchase_org_id != bp_org_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Закупка №{purchase.id} относится к другой организации — "
                "её нельзя разнести на этот банковский платёж"
            ),
        )
