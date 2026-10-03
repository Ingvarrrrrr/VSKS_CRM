"""Удаление копии субсидии (песочницы) целиком — часть «Копия субсидии для
экспериментов» (план breezy-mixing-lovelace.md, Часть Б, ПРАВИЛО №5).

Порядок — тот же принцип, что у отката импорта факта (ПРАВИЛО №6,
app/services/historical_fact_import/rollback.py:85): платежи → закупки
(cascade удаляет их позиции/файлы/позиции договора) → договоры копии →
дерево ФЭО → сама субсидия (CASCADE в БД добирает согласующих/участников/
доступы/ответственных/events/аллокации/соглашения — см. models/subsidy.py).

Только для is_sandbox=true — caller (router) это уже проверил.
"""
from __future__ import annotations

import os
import shutil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy
from app.models.purchase import Purchase
from app.models.payment import Payment
from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.routers.subsidy_approvers import SUBSIDY_TEMPLATES_DIR


async def dry_run_delete(db: AsyncSession, subsidy_id: int) -> dict:
    """Сколько закупок/договоров/платежей уйдёт — для диалога подтверждения."""
    purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.subsidy_id == subsidy_id)
    )).scalars().all()
    contracts_n = (await db.execute(
        select(Contract.id).where(Contract.subsidy_id == subsidy_id)
    )).scalars().all()
    payments_n = 0
    if purchase_ids:
        payments_n = len((await db.execute(
            select(Payment.id).where(Payment.purchase_id.in_(purchase_ids))
        )).scalars().all())
    return {
        "purchases": len(purchase_ids),
        "contracts": len(contracts_n),
        "payments": payments_n,
    }


async def delete_sandbox_copy(db: AsyncSession, subsidy: Subsidy) -> dict:
    counts = await dry_run_delete(db, subsidy.id)

    purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()

    if purchase_ids:
        payments = (await db.execute(
            select(Payment).where(Payment.purchase_id.in_(purchase_ids))
        )).scalars().all()
        for pay in payments:
            await db.delete(pay)
        await db.flush()

        purchases = (await db.execute(
            select(Purchase).where(Purchase.id.in_(purchase_ids))
        )).scalars().all()
        for p in purchases:
            await db.delete(p)
        await db.flush()

    contracts = (await db.execute(
        select(Contract).where(Contract.subsidy_id == subsidy.id)
    )).scalars().all()
    for c in contracts:
        await db.delete(c)
    await db.flush()

    categories = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalars().all()
    for cat in categories:
        await db.delete(cat)
    await db.flush()

    await db.delete(subsidy)
    await db.flush()

    templates_dir = os.path.join(SUBSIDY_TEMPLATES_DIR, str(subsidy.id))
    if os.path.isdir(templates_dir):
        shutil.rmtree(templates_dir, ignore_errors=True)

    return counts
