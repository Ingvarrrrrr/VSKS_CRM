"""--relink, шаг 3: документы двойника → новая закупка.

Переиспользует clone_row (app.services.subsidy_copy._clone — ПРАВИЛО №6,
тот же хелпер, которым пользуется copy_purchases.py) и тот же приём с чеками
(fiscal-тройка обнуляется — uq_receipt_fiscal глобальна на всю таблицу,
оригинал в старой субсидии остаётся, копия с той же тройкой ловила бы
UniqueViolationError, см. docstring copy_purchases.py).

Что копируется — ВСЁ из purchase_files (файл договора, акты, служебные
записки, сгенерированные ТЗ — это все ОДНА таблица purchase_files с полем
file_type, см. app/routers/purchase_files.py::FILE_TYPES; отдельных таблиц
под «документы договора»/«служебки» в проекте нет) + purchase_receipts (чеки).
Объект в хранилище (S3/minio) НЕ копируется — новая строка PurchaseFile
ссылается на ТОТ ЖЕ filepath/ключ, что и у двойника (решение по умолчанию:
удаление файла в старой субсидии сломает ссылку и в новой — ПОМЕЧЕНО в отчёте
__main__.py как решение, требующее подтверждения владельца, если он захочет
независимость копий).

НЕ копируются: Payment (деньги, не документ — копия задвоила бы кассовые
операции сразу в двух субсидиях), Contract и сам Contract.id (задание прямым
текстом: «САМ Contract старой закупки к новой НЕ привязывать» — общий договор
задвоил бы суммы между субсидиями; ссылка purchase.contract_id у новой
закупки остаётся её СОБСТВЕННОЙ, из generate_temp_contract_number/
ensure_contract_linked в build.py).

Идемпотентность (повторный --relink не плодит дубли):
  - PurchaseFile: по (content_hash, original_name, size) — content_hash уже
    есть в модели (app/models/purchase_file.py); если у файла он NULL
    (старые записи до появления хеша) — фолбэк на (original_name, size).
  - PurchaseReceipt: по (seller_inn, total_sum, receipt_datetime) — фискальная
    тройка самого чека обнулена (см. выше), по ней сравнивать нельзя."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_file import PurchaseFile
from app.models.purchase_receipt import PurchaseReceipt
from app.services.subsidy_copy._clone import clone_row


@dataclass
class DocCopyCounters:
    files_copied: int = 0
    files_skipped_existing: int = 0
    receipts_copied: int = 0
    receipts_skipped_existing: int = 0
    by_file_type: dict = field(default_factory=dict)  # file_type -> count copied
    pairs_with_docs: int = 0


def _file_key(f: PurchaseFile) -> tuple:
    if f.content_hash:
        return ("hash", f.content_hash, f.original_name, f.size)
    return ("name_size", f.original_name, f.size)


def _receipt_key(r: PurchaseReceipt) -> tuple:
    return (r.seller_inn, str(r.total_sum), str(r.receipt_datetime))


async def copy_purchase_documents(
    db: AsyncSession, old_purchase_id: int, new_purchase_id: int, counters: DocCopyCounters,
) -> None:
    old_files = (await db.execute(
        select(PurchaseFile).where(PurchaseFile.purchase_id == old_purchase_id)
    )).scalars().all()
    old_receipts = (await db.execute(
        select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == old_purchase_id)
    )).scalars().all()
    if not old_files and not old_receipts:
        return

    existing_files = (await db.execute(
        select(PurchaseFile).where(PurchaseFile.purchase_id == new_purchase_id)
    )).scalars().all()
    existing_keys = {_file_key(f) for f in existing_files}

    existing_receipts = (await db.execute(
        select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == new_purchase_id)
    )).scalars().all()
    existing_rkeys = {_receipt_key(r) for r in existing_receipts}

    any_copied = False
    for f in old_files:
        key = _file_key(f)
        if key in existing_keys:
            counters.files_skipped_existing += 1
            continue
        db.add(clone_row(f, PurchaseFile, purchase_id=new_purchase_id))
        existing_keys.add(key)
        counters.files_copied += 1
        counters.by_file_type[f.file_type] = counters.by_file_type.get(f.file_type, 0) + 1
        any_copied = True

    for r in old_receipts:
        key = _receipt_key(r)
        if key in existing_rkeys:
            counters.receipts_skipped_existing += 1
            continue
        db.add(clone_row(
            r, PurchaseReceipt, purchase_id=new_purchase_id,
            fiscal_drive_number=None, fiscal_document_number=None, fiscal_sign=None,
        ))
        existing_rkeys.add(key)
        counters.receipts_copied += 1
        any_copied = True

    if any_copied:
        counters.pairs_with_docs += 1
        await db.flush()
