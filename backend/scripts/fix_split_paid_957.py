#!/usr/bin/env python3
"""
CLI: разовая починка прода — закупка РЕЕ-2026-00957 (субсидия «ЛНР» id 74,
по умолчанию --source-id 957) была в статусе paid (договор с временным
номером, ручной платёж 473 413,18 из импорта факта, 4 позиции), владелец её
«Разбил» (POST /api/purchases/{pid}/split) ДО исправления бага (см. docstring
app/services/purchase_split.py) — получились 4 части (03445-03448) в статусе
'planned', без договора/контрагента/платежей/feo_category_id у позиций, а
платёж остался висеть на исходной (статус 'split' — вне дашборда).

Эта «починка» применяет ТУ ЖЕ логику, что теперь делает корректный split
(ПРАВИЛО №6 — переиспользует app.services.purchase_split, не копию):
  1. feo_category_id позиций частей — из FeoPlannedItem (позиций исходной уже
     нет, связь только через PurchaseItem.feo_planned_item_id).
  2. Денормализованные поля договора (STAGE_CONTRACT_FIELDS) — из исходной,
     т.к. части уже в paid/contracted/ordered/delivered (STAGE_STATUSES).
  3. Договор каждой части — materialize_part_contract (тот же механизм:
     реальный номер расходится на все части, временный — свой у каждой).
  4. Платежи исходной — делятся пропорционально Σ total_price позиций
     каждой части (split_payments_amount), исходные удаляются.
  5. Договор/ContractItem/деньги исходной — зачищаются (cleanup_source_contract).

Статус частей НЕ трогается (владелец уже вручную перевёл их в «Оплачено») —
только недостающие поля договора/деньги/ФЭО.

РЕЖИМЫ: без --apply — отчёт печатается, вся работа идёт в ОДНОЙ транзакции,
которая откатывается (ROLLBACK), безопасно гонять повторно; --apply — та же
работа, в конце COMMIT.

ЗАПУСК (backend/scripts НЕ примонтирован volume'ом — нужен docker cp перед
запуском, как у других backend/scripts/*.py):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/fix_split_paid_957.py \\
        vsks_crm-backend_a-1:/app/scripts/fix_split_paid_957.py
    docker exec vsks_crm-backend_a-1 python scripts/fix_split_paid_957.py
    (повторить с --apply, когда отчёт одобрен)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.feo_planned_item import FeoPlannedItem  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.services.purchase_split import (  # noqa: E402
    PAYMENT_COPY_FIELDS,
    STAGE_CONTRACT_FIELDS,
    STAGE_STATUSES,
    cleanup_source_contract,
    ensure_payments_splittable,
    materialize_part_contract,
    split_payments_amount,
)


async def main_async(args: argparse.Namespace) -> int:
    lines: list[str] = []

    async with async_session() as db:
        try:
            source = await db.get(Purchase, args.source_id)
            if source is None:
                print(f"Закупка id={args.source_id} не найдена.")
                return 1

            children = (await db.execute(
                select(Purchase).where(Purchase.parent_purchase_id == source.id)
            )).scalars().all()
            if not children:
                print(f"У закупки id={source.id} нет частей (parent_purchase_id) — нечего чинить.")
                return 1

            lines.append(
                f"=== Починка split: источник РЕЕ id={source.id} "
                f"(status={source.status}) -> {len(children)} частей ==="
            )

            # --- 1) feo_category_id позиций частей, из FeoPlannedItem.
            fpi_ids = {
                it.feo_planned_item_id
                for c in children for it in c.items
                if it.feo_category_id is None and it.feo_planned_item_id is not None
            }
            fpi_cat_map: dict[int, int] = {}
            if fpi_ids:
                rows = (await db.execute(
                    select(FeoPlannedItem.id, FeoPlannedItem.feo_category_id)
                    .where(FeoPlannedItem.id.in_(fpi_ids))
                )).all()
                fpi_cat_map = {fid: cat_id for fid, cat_id in rows if cat_id is not None}

            for c in children:
                for it in c.items:
                    if it.feo_category_id is None and it.feo_planned_item_id in fpi_cat_map:
                        old = it.feo_category_id
                        it.feo_category_id = fpi_cat_map[it.feo_planned_item_id]
                        lines.append(
                            f"  Закупка id={c.id} позиция id={it.id}: feo_category_id "
                            f"{old} -> {it.feo_category_id} (из плановой позиции {it.feo_planned_item_id})"
                        )

            # --- 2+3) денормализованные поля договора + договор каждой части,
            # только если ЧАСТЬ уже "в договоре" (владелец вручную перевёл её,
            # например, в paid). Источник к этому моменту ВСЕГДА status='split'
            # (это сделал сам баг) — его status не несёт сигнала, его
            # contract_number/contract_number_is_temporary/contract_date — несут
            # (баг их не трогал, только удалил позиции и пометил 'split').
            eligible = [c for c in children if c.status in STAGE_STATUSES]
            if not eligible:
                lines.append(
                    f"  Ни одна часть не в статусе {STAGE_STATUSES} — договор/деньги частям не переносим."
                )

            for c in eligible:
                for f in STAGE_CONTRACT_FIELDS:
                    setattr(c, f, getattr(source, f))
                await db.flush()
                before_contract_id = c.contract_id
                await materialize_part_contract(db, c, source)
                lines.append(
                    f"  Закупка id={c.id}: договор {before_contract_id} -> {c.contract_id} "
                    f"(contract_number={c.contract_number!r}, contract_price={c.contract_price})"
                )

            # --- 4) платежи источника -> по частям, пропорционально позициям.
            source_payments = (await db.execute(
                select(Payment).where(Payment.purchase_id == source.id)
            )).scalars().all()
            if source_payments:
                ensure_payments_splittable(source_payments)
                group_totals = [
                    sum(
                        (Decimal(str(it.total_price)) if it.total_price is not None else Decimal("0")
                         for it in c.items),
                        Decimal("0"),
                    )
                    for c in children
                ]
                for pay in source_payments:
                    shares = split_payments_amount(Decimal(str(pay.amount or 0)), group_totals)
                    for c, share in zip(children, shares):
                        copy_kwargs = {f: getattr(pay, f) for f in PAYMENT_COPY_FIELDS}
                        db.add(Payment(purchase_id=c.id, amount=share, **copy_kwargs))
                        lines.append(f"  Платёж источника id={pay.id} -> закупка id={c.id}: {share}")
                    await db.delete(pay)
                await db.flush()

                from app.services.purchase_payments import recompute_purchase_payments
                for c in children:
                    await recompute_purchase_payments(db, c.id)
            else:
                lines.append("  У источника нет платежей — ничего не распределяем.")

            # --- 5) зачистка источника (договор/ContractItem/деньги).
            if source.status in STAGE_STATUSES or source.contract_id or source_payments:
                await cleanup_source_contract(db, source)
                if source_payments:
                    from app.services.purchase_payments import recompute_purchase_payments
                    await recompute_purchase_payments(db, source.id)
                lines.append(
                    f"  Источник id={source.id}: contract_id=None, "
                    f"planned_total_price={source.planned_total_price}, contract_price={source.contract_price}"
                )

        finally:
            if args.apply:
                await db.commit()
            else:
                await db.rollback()

    print("\n".join(lines))
    print()
    print("=== РЕЖИМ: COMMIT (--apply) ===" if args.apply else "=== РЕЖИМ: DRY-RUN (без --apply, откат) ===")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-id", type=int, default=957, help="id исходной (разбитой) закупки")
    parser.add_argument("--apply", action="store_true", help="закоммитить изменения (по умолчанию — dry-run)")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
