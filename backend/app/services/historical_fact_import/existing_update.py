"""Задача B (план breezy-mixing-lovelace.md): строка файла, чья плановая
позиция уже лежит в СУЩЕСТВУЮЩЕЙ закупке (match.state == 'already_purchased',
см. matching.py::build_matching_context/ctx['bound_purchases']), не создаёт
новую закупку — она ОБНОВЛЯЕТ найденную по статусу/оплате из файла.

Три входа, по одному на каждый вызывающий модуль (ПРАВИЛО №5/№6 — новая
логика в своём файле, не в preview.py/commit.py/rollback.py):
  - `RANK`/`rank_of()` — единственная таблица ранга статуса для «поднимаем
    статус существующей закупки ТОЛЬКО вверх». commit.py переиспользует ЭТУ
    таблицу для выбора наивысшего статуса группы новой закупки (раньше была
    вторая копия _RANK в commit.py).
  - `build_preview_entries()` — preview.py вызывает один раз на весь
    предпросмотр: агрегирует строки файла с одной и той же существующей
    закупкой в `totals.existing_updates`/`existing_updates` контракта.
  - `materialize_contract()` — переход в contracted+ делает РОВНО то же, что
    commit.py уже делает для только что созданной закупки (temp-номер,
    договорные позиции, привязка договора, пересчёт денег) — вынесено сюда,
    чтобы не копировать тот же кусок для пути «обновить существующую».
  - `apply_existing_updates()` — commit.py: применяет `preview['existing_
    updates']` (тот же расчёт, что и предпросмотр — ПРАВИЛО №6, без второго
    подсчёта) к существующим закупкам, возвращает backups для rollback.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent

# Ранг статуса — ОДИН источник (ПРАВИЛО №6): и наивысшая стадия группы новой
# закупки (commit.py), и решение «поднимать ли статус существующей» здесь
# читают эту таблицу, не копию.
RANK = {"work_in_progress": 1, "contracted": 2, "ordered": 3, "delivered": 4, "paid": 5}


def rank_of(status: Optional[str]) -> int:
    """Ранг статуса закупки. Любой статус вне RANK (plan_schedule, wishes,
    черновики/согласования и т.п.) — ранг 0, т.е. «ниже всех шести» (владелец:
    статус существующей закупки поднимается, но никогда не опускается)."""
    return RANK.get(status, 0)


async def build_preview_entries(db: AsyncSession, buckets: dict[int, dict]) -> list[dict]:
    """`buckets`: {purchase_id: {registry_number, status_from, rows: [...],
    paid_sum: Decimal, target_status: str|None, is_advance: bool}} — собрано
    preview.py по строкам файла, у которых row['existing_purchase'] указывает
    на ОДНУ закупку (match.state=='already_purchased', ровно один кандидат).

    Возвращает [{purchase_id, registry_number, status_from, status_to,
    paid_add, rows, is_advance}]. `status_to` — наивысший статус строк файла,
    если он РАНГОМ выше текущего статуса закупки, иначе сам `status_from`
    (статус не опускается и не трогается, если строки файла ниже рангом).
    `paid_add` = Σ paid строк файла по этой закупке МИНУС уже заведённые
    Payment.amount закупки (не меньше 0, текущие платежи не пересоздаём)."""
    out: list[dict] = []
    for purchase_id, info in buckets.items():
        existing_paid = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.purchase_id == purchase_id)
        )).scalar() or Decimal(0)
        paid_add = info["paid_sum"] - Decimal(str(existing_paid))
        if paid_add < 0:
            paid_add = Decimal(0)

        target = info.get("target_status")
        status_from = info["status_from"]
        status_to = target if target and rank_of(target) > rank_of(status_from) else status_from

        out.append({
            "purchase_id": purchase_id,
            "registry_number": info.get("registry_number"),
            "status_from": status_from,
            "status_to": status_to,
            "paid_add": float(paid_add),
            "rows": list(info["rows"]),
            "is_advance": bool(info.get("is_advance")),
        })
    return out


async def materialize_contract(db: AsyncSession, p: Purchase, *, force_temp_number: bool = False) -> None:
    """Переход закупки в contracted+ — РОВНО тот же набор действий, что
    commit.py делает для только что созданной закупки: временный № договора,
    договорные позиции (copy_items_to_contract сам идемпотентен — не
    создаёт вторую ContractItem на одну PurchaseItem, см. его докстринг),
    привязка договора, пересчёт денег. ПРАВИЛО №6 — один источник действия
    для обоих путей (insert_purchase_with_items и apply_existing_updates
    ниже), не копия кода.

    `force_temp_number=True` — путь «новая закупка»: insert_purchase_with_
    items (purchase_create_core.py) УЖЕ подставил contract_number по
    умолчанию («{год}/{id}»), если он был пуст — ВСЕГДА перезаписываем его
    временным «ВРЕМ-…» (так вело себя commit.py до выноса сюда). Путь
    «обновить существующую» (apply_existing_updates) — force_temp_number=
    False (умолчание): у существующей закупки может быть настоящий №
    договора, трогаем ТОЛЬКО если он пуст (владелец, задача B)."""
    from app.services.contract_items_materialize import copy_items_to_contract
    from app.services.contracts_linking import ensure_contract_linked
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.temp_contract_number import generate_temp_contract_number

    if force_temp_number or not p.contract_number:
        p.contract_number = await generate_temp_contract_number(p, db)
        p.contract_number_is_temporary = True
    await copy_items_to_contract(db, p.id)
    await ensure_contract_linked(p, db)
    await recalc_purchase_money(db, p)


async def apply_existing_updates(
    db: AsyncSession,
    *,
    run_id: int,
    current_user,
    entries: list[dict],
) -> list[dict]:
    """commit.py вызывает ОДНИМ циклом (`for eu in preview['existing_
    updates']: ...` — см. docstring commit.py) на каждый entry из
    build_preview_entries(). Возвращает created_refs['existing_update_
    backups'] — всё, что нужно rollback.py, чтобы вернуть закупку как было."""
    from app.services.purchase_payments import recompute_purchase_payments

    backups: list[dict] = []
    for entry in entries:
        p = await db.get(Purchase, entry["purchase_id"])
        if not p:
            continue

        backup = {
            "purchase_id": p.id,
            "status": p.status,
            "contract_number": p.contract_number,
            "contract_number_is_temporary": p.contract_number_is_temporary,
            "is_prepayment": p.is_prepayment,
            "contract_price": p.contract_price,
            "contract_id": p.contract_id,
        }

        cur_rank = rank_of(p.status)
        target_status = entry["status_to"]
        target_rank = rank_of(target_status)
        paid_add = Decimal(str(entry.get("paid_add") or 0))

        # Аванс (владелец, 05.10.2026, тот же путь, что и новая закупка в
        # commit.py) — независимо от того, двигается ли статус рангом:
        # «оплачено до поставки» на существующей закупке тоже фиксируется.
        prepayment_changed = bool(entry.get("is_advance")) and not backup["is_prepayment"]
        if prepayment_changed:
            p.is_prepayment = True

        status_changed = False
        if target_rank > cur_rank:
            p.status = target_status
            status_changed = True
            if rank_of(p.status) >= rank_of("contracted"):
                await materialize_contract(db, p)

        if paid_add > 0:
            db.add(Payment(
                purchase_id=p.id, amount=paid_add, payment_source="manual",
                confirmed_by_statement=False, import_run_id=run_id,
            ))
            await db.flush()
            await recompute_purchase_payments(db, p.id)

        if status_changed or paid_add > 0 or prepayment_changed:
            db.add(PurchaseEvent(
                purchase_id=p.id,
                user_id=getattr(current_user, "id", None),
                event_type="fact_import_existing_update",
                data={
                    "import_run_id": run_id,
                    "rows": entry["rows"],
                    "status_from": backup["status"],
                    "status_to": p.status,
                    "paid_add": float(paid_add),
                },
            ))
            backups.append(backup)

    return backups
