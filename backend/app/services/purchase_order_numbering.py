"""Авто-номер приказа о закупке (purchases.procurement_order_number).

Владелец (28.10.2026): «пусть генерируются номера приказов на закупку внутри
организации; если номер не ввели вручную — генерировать; нужен только чтобы
приложение к приказу было к чему привязать». Поле procurement_order_number
само уже существовало (Phase 28 T6/T7, форма — PurchaseCommissionSection.vue,
переменная шаблона {{procurement_order_number}}), не хватало только
авто-номера и даты к нему.

Момент присвоения — первая генерация ЛЮБОГО документа по закупке (вызывается
из app/services/documents/generate.py::generate_document_bytes), а не
создание/сохранение закупки: номер нужен ровно затем, чтобы на него могло
сослаться приложение к приказу (документ) — закупка, которая так и не дошла
до генерации документа, номер не расходует. Тот же приём уже применяется для
временного номера договора рамочной головы, см.
app/services/temp_contract_number.py + app/services/documents/
stages_load.py::framework_contract_guard (ПРАВИЛО №6 — переиспользуем идею
«присвоить при первом использовании», не второй механизм).

Формат — простое целое число («17», см. пример в
backend/templates/build/comments_ru.py: «Номер приказа о проведении
закупки. Пример: 17»), последовательное в пределах организации
(Subsidy.org_id закупки) и года (year её procurement_order_date — та же
дата, которой при этом присваивается сегодняшнее число, если ещё не
заполнена). Ручной номер (пользователь ввёл сам, форма закупки) никогда не
трогается и не пересчитывается.

Защита от гонки (две одновременные генерации документа по закупкам одной
организации/года дают одинаковый номер): перед чтением max захватывается
`pg_advisory_xact_lock` через общий хелпер app/services/numbering_lock.py
(тот же хелпер использует temp_contract_number.py — один механизм,
ПРАВИЛО №6).
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.numbering_lock import acquire_numbering_lock

_NUMERIC = re.compile(r"^\d+$")


async def assign_procurement_order_number_if_missing(db: AsyncSession, p: Purchase) -> None:
    """Если у закупки уже есть номер приказа (введён вручную или присвоен
    раньше) — не трогаем. Иначе считаем следующий номер в пределах
    организации и года и сразу коммитим (как framework_contract_guard для
    временного номера договора — session здесь request-scoped, без
    явного commit правка потеряется при закрытии сессии)."""
    if (p.procurement_order_number or "").strip():
        return

    order_date = p.procurement_order_date or date.today()
    year = order_date.year

    org_id = None
    if p.subsidy_id is not None:
        org_id = (await db.execute(
            select(Subsidy.org_id).where(Subsidy.id == p.subsidy_id)
        )).scalar_one_or_none()

    # Блокировка ДО чтения max — в той же транзакции, что и запись номера
    # ниже (держится до commit этой сессии).
    await acquire_numbering_lock(db, "procurement_order_number", org_id, year)

    org_filter = (Subsidy.org_id == org_id) if org_id is not None else Subsidy.org_id.is_(None)
    existing = (await db.execute(
        select(Purchase.procurement_order_number)
        .join(Subsidy, Subsidy.id == Purchase.subsidy_id)
        .where(
            Purchase.procurement_order_number.isnot(None),
            Purchase.procurement_order_date.isnot(None),
            func.extract('year', Purchase.procurement_order_date) == year,
            org_filter,
        )
    )).scalars().all()

    max_n = 0
    for raw in existing:
        raw = (raw or "").strip()
        if _NUMERIC.match(raw):
            max_n = max(max_n, int(raw))

    p.procurement_order_number = str(max_n + 1)
    if not p.procurement_order_date:
        p.procurement_order_date = order_date
    await db.commit()
