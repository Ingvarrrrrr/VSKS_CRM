"""Единственное место, где считается «фискальная идентичность чека» (ПРАВИЛО №6).

Повод: subsidy_copy/copy_purchases.py клонирует PurchaseReceipt с
fiscal_drive_number/fiscal_document_number/fiscal_sign = NULL (иначе падает
глобальный uq_receipt_fiscal — ограничение на всю таблицу, не per-subsidy).
Копия НЕ теряет данные — тройка жива внутри raw_json['qr'] (строка вида
`t=...&s=...&fn=...&i=...&fp=...&n=...`, см. receipts_parsing._parse_qr_string/
_build_qr_string) — но все проверки «чек уже загружен в другой документ»
(receipts_creation.py::_create_receipt_with_items,
routers/purchase_receipts_import.py::_fetch_and_create_receipt_from_qr) искали
дубль только по трём колонкам, поэтому копию не видели. На проде это привело
к тому, что одни и те же 11 чеков оказались одновременно в оригинальной
закупке РЕЕ-2026-00973 и в двух её копиях (03193, 03211).

Здесь — единственная функция разбора тройки (из колонок, а если они пусты —
из raw_json['qr']) и единственная функция поиска существующего чека с той же
тройкой где угодно в таблице (колонки ИЛИ raw_json['qr'] у копий). Все места,
которые раньше запрашивали PurchaseReceipt по fiscal_drive_number/
fiscal_document_number/fiscal_sign напрямую, переведены на эти функции —
второй механизм поиска дублей в проекте не заводится.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_receipt import PurchaseReceipt

FiscalKey = tuple[str, int, str]


def receipt_fiscal_key(source) -> Optional[FiscalKey]:
    """Фискальная тройка (fn, fd, fp) чека — из колонок, а если колонки пусты
    (копия субсидии обнуляет их, см. docstring модуля) — разобранная из
    raw_json['qr'].

    `source` — либо ORM-объект PurchaseReceipt (есть .fiscal_drive_number/
    .fiscal_document_number/.fiscal_sign/.raw_json), либо dict с теми же
    ключами (поле raw_json опционально — используется парсерами чека перед
    созданием строки, когда raw_json ещё отдельный параметр, а не атрибут
    объекта).

    Возвращает None, если тройку собрать не удалось (ни колонки, ни QR не
    дали всех трёх значений).
    """
    if source is None:
        return None

    if isinstance(source, dict):
        fn = source.get('fiscal_drive_number')
        fd = source.get('fiscal_document_number')
        fp = source.get('fiscal_sign')
        raw_json = source.get('raw_json')
    else:
        fn = getattr(source, 'fiscal_drive_number', None)
        fd = getattr(source, 'fiscal_document_number', None)
        fp = getattr(source, 'fiscal_sign', None)
        raw_json = getattr(source, 'raw_json', None)

    if not (fn and fd and fp):
        qr = raw_json.get('qr') if isinstance(raw_json, dict) else None
        if qr:
            # Локальный импорт — receipts_parsing не импортирует этот модуль,
            # цикла нет, но держим импорт рядом с единственным использованием.
            from app.services.receipts_parsing import _parse_qr_string
            parsed = _parse_qr_string(qr)
            fn = fn or parsed.get('fiscal_drive_number')
            fd = fd or parsed.get('fiscal_document_number')
            fp = fp or parsed.get('fiscal_sign')

    if fn and fd and fp:
        try:
            return (str(fn), int(fd), str(fp))
        except (TypeError, ValueError):
            return None
    return None


async def find_duplicate_receipt(
    db: AsyncSession,
    fn: str,
    fd: int,
    fp: str,
    exclude_purchase_id: Optional[int] = None,
) -> Optional[PurchaseReceipt]:
    """Найти уже существующий PurchaseReceipt с той же фискальной тройкой —
    по колонкам (обычный случай) ИЛИ по raw_json['qr'] у строк с пустыми
    колонками (копии субсидии, см. docstring модуля).

    exclude_purchase_id — не считать совпадением чек, лежащий в этой же
    закупке (нужно и при обычной повторной загрузке того же чека в тот же
    документ, и при copy_purchases.py, где это закупка-источник).

    Контур поиска — вся таблица purchase_receipts, без фильтра по
    организации/субсидии: ровно так же, как раньше искала проверка по
    колонкам (uq_receipt_fiscal — тоже глобальное ограничение), это не новое
    сужение/расширение контура.
    """
    # 1) Точные колонки — основной случай (не копия).
    q = select(PurchaseReceipt).where(
        PurchaseReceipt.fiscal_drive_number == fn,
        PurchaseReceipt.fiscal_document_number == fd,
        PurchaseReceipt.fiscal_sign == fp,
    )
    if exclude_purchase_id is not None:
        q = q.where(PurchaseReceipt.purchase_id != exclude_purchase_id)
    row = (await db.execute(q.limit(1))).scalar_one_or_none()
    if row:
        return row

    # 2) Копии: колонки NULL, тройка жива только в raw_json['qr']. Кандидаты —
    # по грубому LIKE на fn (дешёвый фильтр, чеков сотни — полный скан taблицы
    # не нужен), точное совпадение (fn, fd, fp) проверяется в Python через
    # receipt_fiscal_key на каждом кандидате.
    candidates_q = select(PurchaseReceipt).where(
        PurchaseReceipt.fiscal_drive_number.is_(None),
        PurchaseReceipt.raw_json['qr'].astext.like(f"%fn={fn}%"),
    )
    if exclude_purchase_id is not None:
        candidates_q = candidates_q.where(PurchaseReceipt.purchase_id != exclude_purchase_id)
    candidates = (await db.execute(candidates_q)).scalars().all()
    for cand in candidates:
        if receipt_fiscal_key(cand) == (str(fn), int(fd), str(fp)):
            return cand
    return None
