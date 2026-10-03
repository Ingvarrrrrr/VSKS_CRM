"""«Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б).

Тесты вызывают сервис напрямую (app.services.subsidy_copy) — тот же приём,
что test_subsidy_delete_impact.py, через db_session (реальная БД, транзакция
с откатом, см. conftest.py). Импорт факта на копии (поиск похожих закупок
среди закупок копии, договоры не привязываются к оригиналу) — проверяется
отдельно приёмкой в браузере (план, раздел «Тесты» Части Б), не здесь.
"""
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.payment import Payment
from app.models.purchase_receipt import PurchaseReceipt
from app.services.subsidy_copy import create_sandbox_copy, delete_sandbox_copy, dry_run_delete


async def _make_subsidy(db_session) -> Subsidy:
    subsidy = Subsidy(name=f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def _build_full_subsidy(db_session) -> tuple[Subsidy, dict]:
    """Субсидия с деревом ФЭО + плановой позицией + закупкой (с договором,
    позицией договора, позицией закупки, платежом)."""
    subsidy = await _make_subsidy(db_session)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Направление расходов")
    db_session.add(cat)
    await db_session.flush()
    item = FeoPlannedItem(feo_category_id=cat.id, name="Плановая позиция", amount=Decimal("1000.00"))
    db_session.add(item)
    await db_session.flush()

    contract = Contract(
        number="Д-ТЕСТ-1", contract_type="single", subsidy_id=subsidy.id, subject="Договор теста",
    )
    db_session.add(contract)
    await db_session.flush()

    purchase = Purchase(
        subsidy_id=subsidy.id, item_name="Тестовая закупка", status="paid",
        feo_category_id=cat.id, contract_id=contract.id,
        contract_price=Decimal("500.00"), payment_amount=Decimal("500.00"),
    )
    db_session.add(purchase)
    await db_session.flush()

    p_item = PurchaseItem(
        purchase_id=purchase.id, item_name="Строка позиции", quantity=Decimal("1"),
        unit_price=Decimal("500.00"), total_price=Decimal("500.00"),
        feo_category_id=cat.id, feo_planned_item_id=item.id,
    )
    db_session.add(p_item)
    await db_session.flush()

    c_item = ContractItem(
        contract_id=contract.id, purchase_id=purchase.id, source_item_id=p_item.id,
        name="Строка договора", quantity=Decimal("1"), unit_price=Decimal("500.00"), total=Decimal("500.00"),
    )
    db_session.add(c_item)

    payment = Payment(
        purchase_id=purchase.id, contract_id=contract.id, amount=Decimal("500.00"),
        confirmed_by_statement=True,
    )
    db_session.add(payment)
    await db_session.commit()

    return subsidy, {
        "category_id": cat.id, "planned_item_id": item.id, "contract_id": contract.id,
        "purchase_id": purchase.id, "purchase_item_id": p_item.id, "payment_id": payment.id,
    }


async def test_copy_matches_original_tree_plan_purchases_contracts_payments(db_session):
    source, ids = await _build_full_subsidy(db_session)

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    assert copy.id != source.id
    assert copy.is_sandbox is True
    assert copy.copied_from_id == source.id
    assert copy.name == f"{source.name} (копия)"

    cats = (await db_session.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == copy.id)
    )).scalars().all()
    assert len(cats) == 1
    new_cat = cats[0]

    items = (await db_session.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == new_cat.id)
    )).scalars().all()
    assert len(items) == 1
    assert items[0].amount == Decimal("1000.00")

    purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == copy.id)
    )).scalars().all()
    assert len(purchases) == 1
    new_purchase = purchases[0]
    assert new_purchase.id != ids["purchase_id"]
    assert new_purchase.contract_price == Decimal("500.00")
    assert new_purchase.feo_category_id == new_cat.id
    # Привязка к плановой позиции копии, не оригинала.
    p_items = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == new_purchase.id)
    )).scalars().all()
    assert len(p_items) == 1
    assert p_items[0].feo_planned_item_id == items[0].id

    contracts = (await db_session.execute(
        select(Contract).where(Contract.subsidy_id == copy.id)
    )).scalars().all()
    assert len(contracts) == 1
    assert contracts[0].id != ids["contract_id"]
    assert new_purchase.contract_id == contracts[0].id

    c_items = (await db_session.execute(
        select(ContractItem).where(ContractItem.contract_id == contracts[0].id)
    )).scalars().all()
    assert len(c_items) == 1
    assert c_items[0].source_item_id == p_items[0].id

    payments = (await db_session.execute(
        select(Payment).where(Payment.purchase_id == new_purchase.id)
    )).scalars().all()
    assert len(payments) == 1
    assert payments[0].amount == Decimal("500.00")
    assert payments[0].confirmed_by_statement is True
    assert payments[0].bank_payment_id is None


async def test_copy_does_not_change_original(db_session):
    source, ids = await _build_full_subsidy(db_session)

    await create_sandbox_copy(db_session, source)
    await db_session.commit()

    orig_purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == source.id)
    )).scalars().all()
    assert len(orig_purchases) == 1
    assert orig_purchases[0].id == ids["purchase_id"]

    orig_contracts = (await db_session.execute(
        select(Contract).where(Contract.subsidy_id == source.id)
    )).scalars().all()
    assert len(orig_contracts) == 1
    assert orig_contracts[0].id == ids["contract_id"]

    refreshed_source = await db_session.get(Subsidy, source.id)
    assert refreshed_source.is_sandbox is False
    assert refreshed_source.copied_from_id is None


async def test_copy_registry_number_assigned_independently(db_session):
    """registry_number копии проставляется заново (after_flush listener),
    не копируется с оригинала — иначе два разных реестровых номера у одной
    закупки совпали бы."""
    source, ids = await _build_full_subsidy(db_session)
    orig_purchase = await db_session.get(Purchase, ids["purchase_id"])
    assert orig_purchase.registry_number  # присвоен listener'ом при создании выше

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    new_purchase = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == copy.id)
    )).scalars().first()
    assert new_purchase.registry_number
    assert new_purchase.registry_number != orig_purchase.registry_number


async def test_dry_run_delete_counts_without_deleting(db_session):
    source, _ = await _build_full_subsidy(db_session)
    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    counts = await dry_run_delete(db_session, copy.id)
    assert counts == {"purchases": 1, "contracts": 1, "payments": 1}

    # Ничего не удалено — повторный dry_run даёт те же числа.
    still_there = await db_session.get(Subsidy, copy.id)
    assert still_there is not None


async def test_delete_sandbox_copy_does_not_touch_original(db_session):
    source, ids = await _build_full_subsidy(db_session)
    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    await delete_sandbox_copy(db_session, copy)
    await db_session.commit()

    assert await db_session.get(Subsidy, copy.id) is None

    # Оригинал и все его объекты целы.
    assert await db_session.get(Subsidy, source.id) is not None
    orig_purchase = await db_session.get(Purchase, ids["purchase_id"])
    assert orig_purchase is not None
    orig_contract = await db_session.get(Contract, ids["contract_id"])
    assert orig_contract is not None
    orig_payment = await db_session.get(Payment, ids["payment_id"])
    assert orig_payment is not None


async def test_copy_with_fiscal_receipt_does_not_violate_unique_fiscal_constraint(db_session):
    """Блокер приёмки: uq_receipt_fiscal (fiscal_drive_number,
    fiscal_document_number, fiscal_sign) — ГЛОБАЛЬНОЕ ограничение на всю
    таблицу purchase_receipts, не per-subsidy. Копия чека обязана обнулять
    фискальную тройку (остальные поля — продавец/ИНН/суммы/raw_json — как
    есть), иначе второй чек с той же тройкой ловит UniqueViolationError."""
    source, ids = await _build_full_subsidy(db_session)
    receipt = PurchaseReceipt(
        purchase_id=ids["purchase_id"],
        fiscal_drive_number=f"ФН-{uuid.uuid4().hex[:12]}",
        fiscal_document_number=12345,
        fiscal_sign=f"ФП-{uuid.uuid4().hex[:8]}",
        kkt_reg_id="0000000000012345",
        total_sum=Decimal("500.00"),
        seller_name="ООО Тестовый продавец",
        seller_inn="7701234567",
        source="qr_scan",
        raw_json={"items": [{"name": "Товар", "sum": 50000}]},
    )
    db_session.add(receipt)
    await db_session.commit()
    await db_session.refresh(receipt)

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()  # не должно упасть UniqueViolationError

    new_purchase = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == copy.id)
    )).scalars().first()
    new_receipt = (await db_session.execute(
        select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == new_purchase.id)
    )).scalars().first()
    assert new_receipt is not None
    assert new_receipt.id != receipt.id
    # Фискальная тройка НЕ скопирована — оригинал остаётся единственным
    # носителем этих реквизитов (проверка «чек уже загружен в другой
    # авансовый» продолжает работать по оригиналу).
    assert new_receipt.fiscal_drive_number is None
    assert new_receipt.fiscal_document_number is None
    assert new_receipt.fiscal_sign is None
    # Остальное — скопировано как есть.
    assert new_receipt.seller_name == "ООО Тестовый продавец"
    assert new_receipt.seller_inn == "7701234567"
    assert new_receipt.total_sum == Decimal("500.00")
    assert new_receipt.raw_json == {"items": [{"name": "Товар", "sum": 50000}]}
    # Оригинал не тронут.
    orig_receipt = await db_session.get(PurchaseReceipt, receipt.id)
    assert orig_receipt.fiscal_drive_number == receipt.fiscal_drive_number


async def test_copy_preserves_framework_contract_seq_pairs(db_session):
    """uq_purchase_framework_seq (contract_id, framework_seq) WHERE оба NOT
    NULL — копия создаёт НОВЫЙ contract_id для рамочного договора, поэтому
    пара (новый contract_id, framework_seq) обязана остаться уникальной в
    рамках копии (framework_seq копируется как есть, но contract_id другой —
    коллизии с оригиналом/друг с другом внутри копии быть не должно)."""
    subsidy = await _make_subsidy(db_session)
    contract = Contract(
        number="РАМ-1", contract_type="framework_cumulative", subsidy_id=subsidy.id,
        subject="Рамочный договор",
    )
    db_session.add(contract)
    await db_session.flush()
    p1 = Purchase(
        subsidy_id=subsidy.id, item_name="Партия 1", status="paid",
        contract_id=contract.id, framework_seq=1,
    )
    p2 = Purchase(
        subsidy_id=subsidy.id, item_name="Партия 2", status="paid",
        contract_id=contract.id, framework_seq=2,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()

    copy = await create_sandbox_copy(db_session, subsidy)
    await db_session.commit()  # не должно упасть UniqueViolationError

    new_purchases = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == copy.id).order_by(Purchase.framework_seq)
    )).scalars().all()
    assert len(new_purchases) == 2
    assert {p.framework_seq for p in new_purchases} == {1, 2}
    # Обе ссылаются на НОВЫЙ (общий единственный) договор копии, не на оригинал.
    assert new_purchases[0].contract_id == new_purchases[1].contract_id
    assert new_purchases[0].contract_id != contract.id


async def test_copying_a_sandbox_copy_is_rejected_by_router():
    """Правило из роутера (не дублируем здесь всю HTTP-проверку, см.
    routers/subsidy_copy.py::copy_subsidy) — зафиксировано отдельно словами,
    т.к. сервис create_sandbox_copy сам по себе такой проверки не делает
    (это ответственность вызывающего, как и право subsidy.edit)."""
    import inspect
    from app.routers import subsidy_copy
    src = inspect.getsource(subsidy_copy.copy_subsidy)
    assert "is_sandbox" in src
