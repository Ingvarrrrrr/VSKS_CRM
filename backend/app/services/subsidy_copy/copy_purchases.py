"""Копия закупок целиком (с договорами/позициями/чеками/платежами/файлами) —
часть «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md,
Часть Б, 03.10.2026, ПРАВИЛО №5).

НЕ копируется (решение владельца): заявки (Wish), история согласований
(PurchaseApproval), события/комментарии (Event), прогоны импорта факта,
публикации на ЭТП (PlatformPublication) — у копии их никогда не было.

Порядок (из-за FK): договоры → закупки (шапка) → чеки → позиции закупки
(нужен receipt_id копии) → файлы → позиции договора (нужен purchase_id/
item_id копии) → платежи → аллокации по субсидии.
"""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_file import PurchaseFile
from app.models.purchase_receipt import PurchaseReceipt
from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.payment import Payment
from app.models.subsidy_allocation import PurchaseSubsidyAllocation

from ._clone import clone_row


class PurchaseCopyResult:
    __slots__ = ("purchase_count", "contract_count", "payment_count")

    def __init__(self) -> None:
        self.purchase_count = 0
        self.contract_count = 0
        self.payment_count = 0


async def copy_purchases(
    db: AsyncSession,
    source_sid: int,
    new_sid: int,
    category_id_map: dict[int, int],
    planned_item_id_map: dict[int, int],
) -> PurchaseCopyResult:
    result = PurchaseCopyResult()

    purchases = (await db.execute(
        select(Purchase).where(Purchase.subsidy_id == source_sid)
    )).scalars().all()
    if not purchases:
        return result

    # 1. Договоры — один раз на contract_id, даже если на него ссылаются
    # несколько закупок (рамочный договор + его дочерние закупки).
    source_contract_ids = {p.contract_id for p in purchases if p.contract_id}
    contract_id_map: dict[int, int] = {}
    if source_contract_ids:
        contracts = (await db.execute(
            select(Contract).where(Contract.id.in_(source_contract_ids))
        )).scalars().all()
        for c in contracts:
            new_c = clone_row(c, Contract, subsidy_id=new_sid)
            db.add(new_c)
            await db.flush()
            contract_id_map[c.id] = new_c.id
        result.contract_count = len(contract_id_map)

    # Номер закупки — один запрос max(), затем последовательная выдача (не
    # max+1 в цикле — план, Часть Б, «Сервис copy_purchases.py»).
    max_num = (await db.execute(select(func.max(Purchase.purchase_number)))).scalar() or 0
    next_num = max_num + 1

    purchase_id_map: dict[int, int] = {}
    item_id_map: dict[int, int] = {}
    old_parent_by_new: dict[int, int] = {}  # new_purchase_id -> old parent_purchase_id (2-й проход)

    for p in purchases:
        new_p = clone_row(
            p, Purchase,
            subsidy_id=new_sid,
            purchase_number=next_num,
            registry_number=None,  # присвоится сам (after_flush listener, models/purchase.py)
            contract_id=contract_id_map.get(p.contract_id) if p.contract_id else None,
            feo_category_id=category_id_map.get(p.feo_category_id) if p.feo_category_id else None,
            import_run_id=None,
            wish_id=None,
            stopped_wish_id=None,
            event_id=None,
            parent_purchase_id=None,  # перепривязка — 2-й проход ниже
        )
        next_num += 1
        db.add(new_p)
        await db.flush()
        purchase_id_map[p.id] = new_p.id
        if p.parent_purchase_id:
            old_parent_by_new[new_p.id] = p.parent_purchase_id

        # Чеки — ДО позиций (PurchaseItem.receipt_id ссылается на них).
        receipts = (await db.execute(
            select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == p.id)
        )).scalars().all()
        receipt_id_map: dict[int, int] = {}
        for rcpt in receipts:
            new_r = clone_row(rcpt, PurchaseReceipt, purchase_id=new_p.id)
            db.add(new_r)
            await db.flush()
            receipt_id_map[rcpt.id] = new_r.id

        items = (await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
        )).scalars().all()
        for it in items:
            new_it = clone_row(
                it, PurchaseItem,
                purchase_id=new_p.id,
                feo_planned_item_id=planned_item_id_map.get(it.feo_planned_item_id) if it.feo_planned_item_id else None,
                feo_category_id=category_id_map.get(it.feo_category_id) if it.feo_category_id else None,
                receipt_id=receipt_id_map.get(it.receipt_id) if it.receipt_id else None,
                wish_item_id=None,
            )
            db.add(new_it)
            await db.flush()
            item_id_map[it.id] = new_it.id

        # Файлы — та же ссылка на физический файл (filepath), новая строка.
        files = (await db.execute(
            select(PurchaseFile).where(PurchaseFile.purchase_id == p.id)
        )).scalars().all()
        for f in files:
            db.add(clone_row(f, PurchaseFile, purchase_id=new_p.id))

        result.purchase_count += 1

    # 2-й проход: перепривязка parent_purchase_id (родитель создаётся раньше
    # или позже ребёнка в этом же цикле — проще один финальный проход).
    if old_parent_by_new:
        for new_id, old_parent_id in old_parent_by_new.items():
            new_parent_id = purchase_id_map.get(old_parent_id)
            if new_parent_id:
                new_p = await db.get(Purchase, new_id)
                new_p.parent_purchase_id = new_parent_id
        await db.flush()

    # Позиции договора — после того, как purchase_id_map/item_id_map полны.
    if contract_id_map:
        contract_items = (await db.execute(
            select(ContractItem).where(ContractItem.contract_id.in_(contract_id_map.keys()))
        )).scalars().all()
        for ci in contract_items:
            new_purchase_id = purchase_id_map.get(ci.purchase_id) if ci.purchase_id else None
            if ci.purchase_id and not new_purchase_id:
                # Договор делят закупки из разных субсидий — чужая закупка сюда
                # не копируется, строка договора без "своей" закупки бессмысленна.
                continue
            db.add(clone_row(
                ci, ContractItem,
                contract_id=contract_id_map[ci.contract_id],
                purchase_id=new_purchase_id,
                source_item_id=item_id_map.get(ci.source_item_id) if ci.source_item_id else None,
            ))

    # Платежи — без bank_payment_id (копия не связана с реальной банковской
    # выпиской), «подтверждено выпиской» (confirmed_by_statement) сохраняется
    # как флаг истории, сама связь с BankPayment — нет (план, раздел «Что
    # копировать»).
    payments = (await db.execute(
        select(Payment).where(Payment.purchase_id.in_(purchase_id_map.keys()))
    )).scalars().all()
    for pay in payments:
        db.add(clone_row(
            pay, Payment,
            purchase_id=purchase_id_map[pay.purchase_id],
            contract_id=contract_id_map.get(pay.contract_id) if pay.contract_id else None,
            bank_payment_id=None,
            import_run_id=None,
        ))
        result.payment_count += 1

    # Аллокации по субсидии — только те, что числятся за ИСХОДНОЙ субсидией.
    # Аллокация на ДРУГУЮ (не копируемую) субсидию не переносится: иначе
    # закупка копии задела бы реальный бюджет чужой субсидии.
    allocations = (await db.execute(
        select(PurchaseSubsidyAllocation).where(
            PurchaseSubsidyAllocation.purchase_id.in_(purchase_id_map.keys()),
            PurchaseSubsidyAllocation.subsidy_id == source_sid,
        )
    )).scalars().all()
    for alloc in allocations:
        db.add(clone_row(
            alloc, PurchaseSubsidyAllocation,
            purchase_id=purchase_id_map[alloc.purchase_id],
            subsidy_id=new_sid,
        ))

    await db.flush()
    return result
