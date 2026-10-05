"""Дедуп повторной загрузки той же казначейской выписки — защита от
задвоения LEGACY-строк (загруженных ДО появления колонки «Идентификатор
документа», external_doc_id IS NULL) при перезаливке файла, который теперь
несёт external_doc_id.

Находка 05.10.2026 (живая проверка payment-control): прод имеет минимум 72
строки bank_payments, загруженные 07.05.2026 БЕЗ external_doc_id (колонки/
значения тогда не было). Следующая свежая выгрузка задвоила бы их — прежний
импорт (app/routers/bank_statements.py) при совпадении external_doc_id
пропускал строку ЦЕЛИКОМ, а для строк без id вообще не искал пару, так что
статус старой строки («на исполнении») никогда не обновлялся до «Исполнен».

Три исхода для входящей строки с external_doc_id:
  1. EXACT_UPDATE — в БД уже есть строка с ТЕМ ЖЕ external_doc_id: это та же
     платёжка, сверенная раньше. Не вставляем — обновляем MUTABLE_FIELDS.
  2. MERGE_LEGACY — external_doc_id в БД нет, но есть РОВНО ОДНА строка БЕЗ
     external_doc_id с тем же payment_number (нормализованным) + payment_date
     + amount + payee_inn (+ payer_account, если есть у обеих, — сужает при
     неоднозначности): та же платёжка, загруженная до появления колонки.
     Проставляем ей external_doc_id и обновляем поля.
  3. AMBIGUOUS — больше одного такого legacy-кандидата: не склеиваем (риск
     перепутать платёж), строка вставляется как НОВАЯ, помечается в счётчиках
     прогона — спорный случай отдаётся человеку.

Строки без external_doc_id (источник вообще не даёт колонку) этим дедупом не
занимаются — для них действует прежний запасной ключ, source_row_hash
(уникальный индекс на уровне БД, ловит только побайтовые повторы).

ПРАВИЛО №6: связи платежа (Payment.bank_payment_id, matched_*) этот модуль
НИКОГДА не трогает — то, что сопоставлено позже, принадлежит привязке
(app/services/payment_lookup.py), а не парсеру выписки.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.payment_basis import normalize_doc_number

# Поля, которые казначейство может изменить ПОСЛЕ первой загрузки строки —
# единственная точка (ПРАВИЛО №6), что считается «обновляемым» при повторной
# загрузке/склейке legacy-строки. Идентичность платежа (payment_number/date/
# amount/payee_*) и связи (matched_*, Payment.bank_payment_id) сюда НЕ входят.
MUTABLE_FIELDS = (
    "status",
    "execution_datetime",
    "purpose_text",
    "parsed_contract_number",
    "parsed_contract_date",
    "parsed_kbk",
    "parsed_documents",
    "basis_doc_text",
    "basis_doc_number",
    "basis_doc_date",
    "subsidy_code",
    "expense_code",
    "raw_json",
    "source_row_hash",
)


class DedupAction(str, Enum):
    EXACT_UPDATE = "exact_update"
    MERGE_LEGACY = "merge_legacy"
    AMBIGUOUS = "ambiguous"
    NEW = "new"


@dataclass
class DedupResult:
    action: DedupAction
    existing: Optional[BankPayment] = None


async def find_dedup_target(
    db: AsyncSession, pr, existing_by_ext_id: dict,
) -> DedupResult:
    """pr — ParsedRow (bank_statement_parser_rows.py). existing_by_ext_id —
    предзагруженный словарь external_doc_id -> существующая BankPayment из БД
    (НЕ из этого файла) — один SELECT на весь импорт, не per-row."""
    if not pr.external_doc_id:
        return DedupResult(DedupAction.NEW)

    existing = existing_by_ext_id.get(pr.external_doc_id)
    if existing is not None:
        return DedupResult(DedupAction.EXACT_UPDATE, existing)

    if not pr.payment_number or not pr.payment_date or pr.amount is None or not pr.payee_inn:
        return DedupResult(DedupAction.NEW)  # ключа недостаточно для безопасной склейки

    norm_number = normalize_doc_number(str(pr.payment_number))
    candidates = (await db.execute(
        select(BankPayment).where(
            BankPayment.external_doc_id.is_(None),
            BankPayment.payment_date == pr.payment_date,
            BankPayment.amount == Decimal(str(pr.amount)),
            BankPayment.payee_inn == pr.payee_inn,
        )
    )).scalars().all()
    matches = [c for c in candidates if normalize_doc_number(str(c.payment_number or "")) == norm_number]
    if not matches:
        return DedupResult(DedupAction.NEW)
    if len(matches) > 1 and pr.payer_account:
        narrowed = [c for c in matches if c.payer_account and c.payer_account == pr.payer_account]
        if len(narrowed) == 1:
            matches = narrowed
    if len(matches) == 1:
        return DedupResult(DedupAction.MERGE_LEGACY, matches[0])
    return DedupResult(DedupAction.AMBIGUOUS)


def apply_mutable_fields(existing: BankPayment, pr) -> bool:
    """Переносит изменяемые поля pr → existing. Возвращает True, если хоть
    одно значение реально изменилось (счётчик updated/unchanged)."""
    changed = False
    for field_name in MUTABLE_FIELDS:
        new_value = getattr(pr, field_name, None)
        if new_value is None:
            continue  # пустое значение в новой строке не затирает старое
        old_value = getattr(existing, field_name, None)
        if new_value != old_value:
            setattr(existing, field_name, new_value)
            changed = True
    return changed


async def recompute_if_now_executed(db: AsyncSession, existing: BankPayment, was_executed: bool) -> None:
    """Строка ТОЛЬКО ЧТО стала исполненной (не была раньше) и к ней уже
    привязаны Payment закупок → пересчитать оплату штатно
    (app/services/purchase_payments.py::recompute_purchase_payments), чтобы
    сработал запрос «Оплачено» согласующим (ПРАВИЛО №6 — не вторая копия
    порога/уведомления)."""
    now_executed = (existing.status or "").upper().strip() in EXECUTED_STATUSES
    if was_executed or not now_executed:
        return
    from app.models.payment import Payment
    from app.services.purchase_payments import recompute_purchase_payments

    purchase_ids = (await db.execute(
        select(Payment.purchase_id).where(
            Payment.bank_payment_id == existing.id, Payment.purchase_id.isnot(None),
        )
    )).scalars().all()
    for pid in {p for p in purchase_ids if p is not None}:
        await recompute_purchase_payments(db, pid)
