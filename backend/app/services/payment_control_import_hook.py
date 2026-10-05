"""Автосопоставление после импорта выписки — план
.planning/quick/2026-10-06-statement-control/PLAN.md, п.5.

После КАЖДОЙ загрузки выписки (app/routers/bank_statements.py, ПОСЛЕ коммита
прогона) — по субсидиям, затронутым вставленными/обновлёнными строками,
запускается ТО ЖЕ штатное сопоставление, что и ручной POST
/api/purchases/match-payments?dry_run=false (см.
app/services/payment_matching_run.py::run_match_payments, ПРАВИЛО №6 — вторая
логика сопоставления здесь не заводится, только вызов).

Ошибка сопоставления одной субсидии не должна ронять импорт — логируется и
попадает в errors, остальные субсидии прогона это не останавливает.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.subsidy import Subsidy
from app.services.bank_payment_subsidy_scope import bank_payment_matches_subsidy

logger = logging.getLogger(__name__)


async def _affected_subsidy_ids(db: AsyncSession, bank_payments: list[BankPayment]) -> set[int]:
    """Субсидии, которым видна хотя бы одна из затронутых строк — по тому же
    правилу, что и везде (bank_payment_matches_subsidy, ПРАВИЛО №6)."""
    direct_ids = {bp.subsidy_id for bp in bank_payments if bp.subsidy_id}

    subsidy_rows = (await db.execute(
        select(Subsidy).where(Subsidy.agreement_number.isnot(None))
    )).scalars().all()
    for s in subsidy_rows:
        if s.id in direct_ids:
            continue
        if any(bank_payment_matches_subsidy(bp, s) for bp in bank_payments):
            direct_ids.add(s.id)
    return direct_ids


async def auto_match_after_import(db: AsyncSession, touched_bank_payments: list[BankPayment]) -> dict:
    """{"auto_matched": {subsidy_id: {attached_groups}}, "errors": [...]}"""
    from app.services.payment_matching_run import run_match_payments

    result: dict = {"auto_matched": {}, "errors": []}
    if not touched_bank_payments:
        return result

    try:
        subsidy_ids = await _affected_subsidy_ids(db, touched_bank_payments)
    except Exception:
        logger.warning("auto-match after import: не удалось определить затронутые субсидии", exc_info=True)
        return result

    for sid in subsidy_ids:
        try:
            report = await run_match_payments(db, sid, dry_run=False)
            result["auto_matched"][str(sid)] = {
                "attached_groups": len(report.get("attached", [])),
            }
        except Exception as exc:
            logger.warning("auto-match after import failed for subsidy %s", sid, exc_info=True)
            result["errors"].append({"subsidy_id": sid, "error": str(exc)})

    return result
