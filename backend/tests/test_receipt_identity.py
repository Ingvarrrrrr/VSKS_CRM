"""Фискальная идентичность чека (app/services/receipt_identity.py) — задание
08.10.2026: программа не должна давать возможность ввести один и тот же чек
дважды, включая случай, когда дубль — КОПИЯ чека без фискальной тройки в
колонках (subsidy_copy/copy_purchases.py обнуляет fiscal_drive_number/
fiscal_document_number/fiscal_sign у клона, см. docstring receipt_identity.py).
Прод-инцидент: 11 чеков легли в оригинал РЕЕ-2026-00973 и в его копии 03193/03211.

Приём теста — тот же, что test_subsidy_copy.py/test_copy_into_subsidy.py:
db_session — реальная БД в одной транзакции с откатом (conftest.py).
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.purchase import Purchase
from app.models.purchase_receipt import PurchaseReceipt
from app.services.receipt_identity import receipt_fiscal_key, find_duplicate_receipt
from app.services.receipts_creation import _create_receipt_with_items
from app.services.subsidy_copy.copy_purchases import copy_purchases

QR = "t=20260101T1200&s=500.00&fn=9999000000000001&i=12345&fp=1111111111&n=1"


async def _make_subsidy(db_session) -> Subsidy:
    subsidy = Subsidy(name=f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def _make_purchase(db_session, subsidy_id: int, **kwargs) -> Purchase:
    purchase = Purchase(subsidy_id=subsidy_id, item_name="Закупка", status="paid", **kwargs)
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


# --- receipt_fiscal_key ------------------------------------------------

def test_parses_triple_from_raw_json_qr_when_columns_empty():
    """Копия: колонки NULL, тройка жива только в raw_json['qr']."""
    data = {
        "fiscal_drive_number": None,
        "fiscal_document_number": None,
        "fiscal_sign": None,
        "raw_json": {"qr": QR},
    }
    assert receipt_fiscal_key(data) == ("9999000000000001", 12345, "1111111111")


def test_prefers_columns_over_qr_when_both_present():
    data = {
        "fiscal_drive_number": "ФН-КОЛОНКА",
        "fiscal_document_number": 777,
        "fiscal_sign": "ФП-КОЛОНКА",
        "raw_json": {"qr": QR},
    }
    assert receipt_fiscal_key(data) == ("ФН-КОЛОНКА", 777, "ФП-КОЛОНКА")


def test_none_when_neither_columns_nor_qr_give_full_triple():
    assert receipt_fiscal_key({"raw_json": {"qr": "t=20260101T1200&s=1&n=1"}}) is None
    assert receipt_fiscal_key({}) is None
    assert receipt_fiscal_key(None) is None


async def test_works_on_orm_row_not_only_dict(db_session):
    subsidy = await _make_subsidy(db_session)
    purchase = await _make_purchase(db_session, subsidy.id)
    receipt = PurchaseReceipt(
        purchase_id=purchase.id,
        source="json_import",
        raw_json={"qr": QR},
    )
    db_session.add(receipt)
    await db_session.commit()
    await db_session.refresh(receipt)
    assert receipt_fiscal_key(receipt) == ("9999000000000001", 12345, "1111111111")


# --- find_duplicate_receipt / _create_receipt_with_items ----------------

async def test_upload_rejected_when_copy_without_columns_already_holds_same_qr(db_session):
    """Копия чека (fiscal_* = NULL, тройка только в raw_json['qr']) лежит в
    закупке A. Повторная загрузка ТОГО ЖЕ чека (с реальной фискальной тройкой
    в данных) в закупку B обязана отказать со ссылкой на закупку A — иначе
    ровно прод-баг 08.10.2026."""
    subsidy = await _make_subsidy(db_session)
    purchase_a = await _make_purchase(db_session, subsidy.id, registry_number="РЕЕ-2026-00001")
    purchase_b = await _make_purchase(db_session, subsidy.id)

    copy_receipt = PurchaseReceipt(
        purchase_id=purchase_a.id,
        fiscal_drive_number=None,
        fiscal_document_number=None,
        fiscal_sign=None,
        source="json_import",
        raw_json={"qr": QR},
    )
    db_session.add(copy_receipt)
    await db_session.commit()

    data = {
        "fiscal_drive_number": "9999000000000001",
        "fiscal_document_number": 12345,
        "fiscal_sign": "1111111111",
        "total_sum": Decimal("500.00"),
        "seller_inn": "7701234567",
    }
    with pytest.raises(HTTPException) as exc_info:
        await _create_receipt_with_items(purchase_b.id, dict(data), "json_import", {"qr": QR}, db_session)

    detail = exc_info.value.detail
    assert detail["code"] == "RECEIPT_DUPLICATE"
    assert detail["purchase_id"] == purchase_a.id
    assert "РЕЕ-2026-00001" in detail["message"]


async def test_find_duplicate_receipt_matches_columns_normal_case(db_session):
    subsidy = await _make_subsidy(db_session)
    purchase = await _make_purchase(db_session, subsidy.id)
    receipt = PurchaseReceipt(
        purchase_id=purchase.id,
        fiscal_drive_number="9999000000000002",
        fiscal_document_number=555,
        fiscal_sign="2222222222",
        source="qr_scan",
        raw_json={"qr": "t=20260101T1200&s=1&fn=9999000000000002&i=555&fp=2222222222"},
    )
    db_session.add(receipt)
    await db_session.commit()

    found = await find_duplicate_receipt(db_session, "9999000000000002", 555, "2222222222")
    assert found is not None
    assert found.id == receipt.id


async def test_first_upload_passes_when_no_duplicate_exists(db_session):
    """Обычная первая загрузка чека — не должна ничего блокировать."""
    subsidy = await _make_subsidy(db_session)
    purchase = await _make_purchase(db_session, subsidy.id)

    data = {
        "fiscal_drive_number": "9999000000000003",
        "fiscal_document_number": 1,
        "fiscal_sign": "3333333333",
        "total_sum": Decimal("100.00"),
    }
    receipt = await _create_receipt_with_items(purchase.id, dict(data), "json_import", {"qr": "x"}, db_session)
    assert receipt is not None
    assert receipt.purchase_id == purchase.id


# --- copy_purchases: пропустить закупку с уже существующим дублем чека ---

async def test_copy_purchases_skips_purchase_whose_receipt_already_in_target(db_session):
    """Задание 08.10.2026, п.3: если чек закупки-источника уже лежит (как
    копия без фискальной тройки) в ЦЕЛЕВОЙ субсидии — закупка целиком не
    копируется, предупреждение попадает в result.warnings."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)

    source_purchase = await _make_purchase(db_session, source.id)
    source_receipt = PurchaseReceipt(
        purchase_id=source_purchase.id,
        fiscal_drive_number="9999000000000004",
        fiscal_document_number=42,
        fiscal_sign="4444444444",
        source="json_import",
        raw_json={"qr": "t=20260101T1200&s=1&fn=9999000000000004&i=42&fp=4444444444"},
    )
    db_session.add(source_receipt)

    # Копия того же чека уже лежит в целевой субсидии (NULL-тройка, как и
    # реальные копии на проде).
    target_purchase = await _make_purchase(db_session, target.id, registry_number="РЕЕ-2026-00973")
    target_receipt_copy = PurchaseReceipt(
        purchase_id=target_purchase.id,
        fiscal_drive_number=None,
        fiscal_document_number=None,
        fiscal_sign=None,
        source="json_import",
        raw_json={"qr": "t=20260101T1200&s=1&fn=9999000000000004&i=42&fp=4444444444"},
    )
    db_session.add(target_receipt_copy)
    await db_session.commit()

    result = await copy_purchases(
        db_session, source.id, target.id,
        category_id_map={}, planned_item_id_map={},
    )

    assert result.purchase_count == 0
    assert any("РЕЕ-2026-00973" in w for w in result.warnings)

    purchases_in_target = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    # Только та закупка, что уже была в target заранее — copy_purchases
    # не добавила вторую копию.
    assert len(purchases_in_target) == 1
    assert purchases_in_target[0].id == target_purchase.id


async def test_copy_purchases_copies_normally_when_no_duplicate_in_target(db_session):
    """Контроль: обычное копирование без существующего дубля — проходит,
    новая проверка ничего не блокирует зря."""
    source = await _make_subsidy(db_session)
    target = await _make_subsidy(db_session)

    source_purchase = await _make_purchase(db_session, source.id)
    source_receipt = PurchaseReceipt(
        purchase_id=source_purchase.id,
        fiscal_drive_number="9999000000000005",
        fiscal_document_number=7,
        fiscal_sign="5555555555",
        source="json_import",
        raw_json={"qr": "t=20260101T1200&s=1&fn=9999000000000005&i=7&fp=5555555555"},
    )
    db_session.add(source_receipt)
    await db_session.commit()

    result = await copy_purchases(
        db_session, source.id, target.id,
        category_id_map={}, planned_item_id_map={},
    )

    assert result.purchase_count == 1
    assert result.warnings == []

    copied_receipts = (await db_session.execute(
        select(PurchaseReceipt).join(Purchase, PurchaseReceipt.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == target.id)
    )).scalars().all()
    assert len(copied_receipts) == 1
    assert copied_receipts[0].fiscal_drive_number is None  # тройка обнулена, как и раньше
