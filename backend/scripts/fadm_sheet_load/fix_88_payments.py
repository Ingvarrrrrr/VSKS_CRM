#!/usr/bin/env python3
"""Разовый data-fix для субсидии «ФАДМ 2026_2» (найдена ПО ИМЕНИ — на проде это
id=88 на момент задачи 2026-10-05, но id не хардкодится — номер меняется между
окружениями, см. тот же приём в __main__.py этого пакета).

ПРИЧИНА (разбор сверки ФАДМ 2026_2, задача 2026-10-05): пять п/п были разнесены
штатным автосопоставлением НЕПРАВИЛЬНО, пока были в силе баги п.1-3 того же
задания (app/services/payment_lookup.py::_used_basis_index — текстовый
дубль-блок; app/services/subsidy_payment_control.py — ложный «дубль» на
помесячных заказах рамки; backend/scripts/fadm_sheet_load/sheet_v2_payments.py —
суммовый, а не номерной, подбор для помесячных):
  - Егорова (ИНН 930702695519, рамочный договор 01-26): п/п 354 ошибочно
    привязан к заказу №6/3 вместо №6/5 (ошибка листа — колонка U заказа №6/8
    тоже указывала 354, см. sheet_v2_payments.py::find_bank_payment_candidates);
    правильные месяцы — 242→заказ3, 290→заказ4, 354→заказ5, 483→заказ7.
  - Текстиль М №81 заказ 3: п/п 379 не была привязана вовсе (basis_key-дубль
    с п/п 297 того же назначения — payment_lookup.py, п.1).
  - УНИВЕРСИС №100 заказ 2: п/п 296 аналогично не была привязана.

ЕДИНСТВЕННЫЙ писатель Payment — штатный app.services.payment_lookup.attach()
(ПРАВИЛО №6): этот скрипт сам НЕ создаёт/не трогает Payment напрямую, только
находит закупки/группы/строки выписки и вызывает attach()/unlink_bank_payment()
— те же функции, что использует router в проде. Уведомления согласующим
(«Оплачено» confirmation requested) подавляются тем же приёмом, что в
sheet_v2_build.py::_silence_paid_confirmation_notifications (не второй
механизм — импортируется оттуда).

Закупки находятся по task_comment (sheet_v2_build.py пишет туда
"Таблица GoodsService: закупка {purchase_no}, заказ {order_no}" — это
единственный надёжный текстовый якорь на исходную нумерацию листа, Purchase не
хранит purchase_no отдельной колонкой) + проверка contractor_id/ИНН для
безопасности (не перепутать однофамильцев).

РЕЖИМЫ (как у backend/scripts/fadm_sheet_load/__main__.py):
  --dry-run  — выполняет все операции в транзакции, печатает что было/что
               стало и Σ «подтверждено выпиской» по субсидии до/после, затем
               ROLLBACK (ничего не остаётся в БД).
  --yes      — применяет по-настоящему (COMMIT). Без --dry-run и без --yes —
               по умолчанию ведёт себя как --dry-run (защита от случайного
               запуска).

ЗАПУСК (docker cp обязателен — backend/scripts не смонтирован volume'ом):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/fadm_sheet_load vsks_crm-backend_b-1:/app/scripts/fadm_sheet_load
    docker exec vsks_crm-backend_b-1 python -m scripts.fadm_sheet_load.fix_88_payments --dry-run
    docker exec vsks_crm-backend_b-1 python -m scripts.fadm_sheet_load.fix_88_payments --yes

На проде — те же команды, контейнер backend продовый (НЕ выполнять из этой
сессии — владелец запускает сам)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.bank_statement import BankPayment  # noqa: E402
from app.models.contractor import Contractor  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.services.bank_payment_subsidy_scope import subsidy_scope_clause  # noqa: E402
from app.services.bank_statement_parser import EXECUTED_STATUSES  # noqa: E402
from app.services.payment_lookup import PaymentAttachError, attach  # noqa: E402
from app.services.payment_target import build_groups  # noqa: E402
from app.services.purchase_payments import unlink_bank_payment  # noqa: E402

from .sheet_v2_build import _silence_paid_confirmation_notifications  # noqa: E402

SUBSIDY_NAME = "ФАДМ 2026_2"
EGOROVA_INN = "930702695519"
TEXTIL_M_INN = "5031069379"
UNIVERSIS_INN = "7718840513"


@dataclass
class Relink:
    payment_number: str
    payee_inn: str            # ИНН строки выписки (payee_inn у BankPayment — надёжен)
    contractor_name_like: str  # подстрока Contractor.name закупки-цели
    task_comment_like: str     # подстрока task_comment закупки-цели
    label: str


# Задание владельца, п.4 (см. docstring): отвязать 354 от №6/3, привязать
# 242→№6/3, 290→№6/4, 354→№6/5, 483→№6/7, 379→№81/3, 296→№100/2.
#
# Contractor.inn у этих трёх контрагентов в базе ПУСТОЙ (sheet_v2_build.py
# создаёт/использует контрагента по имени из листа, ИНН колонкой не хранит,
# проверено на локальной копии 2026-10-05: contractors.name='ЕГОРОВА ЛЮДМИЛА
# ВЛАДИМИРОВНА'/'Текстиль М'/'УНИВЕРСИС' — все inn IS NULL) — закупка ищется
# по имени контрагента + task_comment, строка выписки — по payee_inn (там ИНН
# реальный, из казначейской выгрузки).
DETACH_PAYMENT_NUMBER = "354"
DETACH_FROM_TASK_COMMENT_LIKE = "закупка 6, заказ 3"
DETACH_CONTRACTOR_NAME_LIKE = "ЕГОРОВА ЛЮДМИЛА"

RELINKS: list[Relink] = [
    Relink("242", EGOROVA_INN, "ЕГОРОВА ЛЮДМИЛА", "закупка 6, заказ 3", "Егорова №6 заказ 3"),
    Relink("290", EGOROVA_INN, "ЕГОРОВА ЛЮДМИЛА", "закупка 6, заказ 4", "Егорова №6 заказ 4"),
    Relink("354", EGOROVA_INN, "ЕГОРОВА ЛЮДМИЛА", "закупка 6, заказ 5", "Егорова №6 заказ 5"),
    Relink("483", EGOROVA_INN, "ЕГОРОВА ЛЮДМИЛА", "закупка 6, заказ 7", "Егорова №6 заказ 7"),
    # Текстиль М №81 / УНИВЕРСИС №100 — ОДНА Purchase объединяет НЕСКОЛЬКО
    # заказов листа (group_rows_v2 группирует только по (ИНН, D), без E — см.
    # app/scripts/fadm_sheet_load/sheet_v2_payments.py::_order_target_amounts),
    # поэтому task_comment у них БЕЗ ", заказ N" — "закупка 81 (ИНН ...)".
    Relink("379", TEXTIL_M_INN, "Текстиль М", "закупка 81 (ИНН", "Текстиль М №81 заказ 3"),
    Relink("296", UNIVERSIS_INN, "УНИВЕРСИС", "закупка 100 (ИНН", "УНИВЕРСИС №100 заказ 2"),
]


async def _get_subsidy(db: AsyncSession) -> Subsidy:
    sub = (await db.execute(
        select(Subsidy).where(Subsidy.name == SUBSIDY_NAME)
    )).scalars().first()
    if sub is None:
        raise RuntimeError(f"Субсидия {SUBSIDY_NAME!r} не найдена — сначала загрузить sheet_v2 загрузчиком")
    return sub


async def _find_purchase(db: AsyncSession, subsidy_id: int, contractor_name_like: str, task_comment_like: str) -> Optional[Purchase]:
    rows = (await db.execute(
        select(Purchase)
        .join(Contractor, Contractor.id == Purchase.contractor_id)
        .where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.task_comment.ilike(f"%{task_comment_like}%"),
            Contractor.name.ilike(f"%{contractor_name_like}%"),
        )
    )).scalars().all()
    out = list(rows)
    if len(out) > 1:
        raise RuntimeError(f"Неоднозначно: {len(out)} закупок по {task_comment_like!r} + контрагент~{contractor_name_like!r}")
    return out[0] if out else None


async def _find_bank_payment(db: AsyncSession, subsidy: Subsidy, payment_number: str, payee_inn: str) -> Optional[BankPayment]:
    rows = (await db.execute(
        select(BankPayment).where(
            subsidy_scope_clause(subsidy),
            BankPayment.payment_number == payment_number,
            BankPayment.payee_inn == payee_inn,
        )
    )).scalars().all()
    executed = [bp for bp in rows if (bp.status or "").upper().strip() in EXECUTED_STATUSES]
    if len(executed) > 1:
        raise RuntimeError(f"Неоднозначно: {len(executed)} исполненных строк с №{payment_number}/ИНН {payee_inn}")
    return executed[0] if executed else None


async def _confirmed_total(db: AsyncSession, subsidy_id: int) -> Decimal:
    rows = (await db.execute(
        select(Payment.amount)
        .join(Purchase, Purchase.id == Payment.purchase_id)
        .where(Purchase.subsidy_id == subsidy_id, Payment.confirmed_by_statement.is_(True))
    )).scalars().all()
    return sum((Decimal(str(a or 0)) for a in rows), Decimal("0"))


async def run(apply_changes: bool) -> int:
    with _silence_paid_confirmation_notifications():
      async with async_session() as db:
        subsidy = await _get_subsidy(db)
        print(f"Субсидия: {subsidy.name!r} id={subsidy.id}")

        before_total = await _confirmed_total(db, subsidy.id)
        print(f"Σ «подтверждено выпиской» ДО: {before_total:.2f}")

        # --- 1. Отвязать 354 от заказа №6/3 (штатная отвязка) ---
        detach_purchase = await _find_purchase(db, subsidy.id, DETACH_CONTRACTOR_NAME_LIKE, DETACH_FROM_TASK_COMMENT_LIKE)
        if detach_purchase is None:
            print(f"ПРОПУСК отвязки: закупка «{DETACH_FROM_TASK_COMMENT_LIKE}» не найдена")
        else:
            bp354 = await _find_bank_payment(db, subsidy, DETACH_PAYMENT_NUMBER, EGOROVA_INN)
            if bp354 is None:
                print(f"ПРОПУСК отвязки: п/п №{DETACH_PAYMENT_NUMBER} не найден в выписке")
            else:
                existing = (await db.execute(
                    select(Payment).where(
                        Payment.purchase_id == detach_purchase.id,
                        Payment.bank_payment_id == bp354.id,
                    )
                )).scalars().all()
                if not existing:
                    print(f"ПРОПУСК отвязки: п/п №{DETACH_PAYMENT_NUMBER} не привязан к закупке id={detach_purchase.id} (заказ 6/3) — уже чисто")
                else:
                    deleted = await unlink_bank_payment(db, bp354.id)
                    print(f"ОТВЯЗАНО: п/п №{DETACH_PAYMENT_NUMBER} от закупки id={detach_purchase.id} "
                          f"(Егорова №6 заказ 3) — удалено Payment: {deleted}")

        # --- 2. Привязать штатным attach() ---
        results = []
        for r in RELINKS:
            purchase = await _find_purchase(db, subsidy.id, r.contractor_name_like, r.task_comment_like)
            if purchase is None:
                print(f"ПРОПУСК {r.label}: закупка не найдена (task_comment~{r.task_comment_like!r})")
                continue
            bp = await _find_bank_payment(db, subsidy, r.payment_number, r.payee_inn)
            if bp is None:
                print(f"ПРОПУСК {r.label}: п/п №{r.payment_number} не найден в выписке (ИНН {r.payee_inn})")
                continue

            groups = await build_groups(db, subsidy.id)
            group = next((g for g in groups if purchase.id in g.purchase_ids), None)
            if group is None:
                print(f"ПРОПУСК {r.label}: закупка id={purchase.id} не входит ни в одну платёжную группу")
                continue

            try:
                created = await attach(db, group, [bp.id])
            except PaymentAttachError as exc:
                print(f"ОТКАЗ {r.label}: п/п №{r.payment_number} -> закупка id={purchase.id}: {exc}")
                continue

            mine = [p for p in created if p.purchase_id == purchase.id]
            amount = sum((Decimal(str(p.amount or 0)) for p in mine), Decimal("0"))
            print(f"ПРИВЯЗАНО {r.label}: п/п №{r.payment_number} -> закупка id={purchase.id}, "
                  f"сумма {amount:.2f}, Payment id={[p.id for p in mine]}")
            results.append((r, purchase, mine))

        after_total = await _confirmed_total(db, subsidy.id)
        print(f"\nΣ «подтверждено выпиской» ДО:    {before_total:.2f}")
        print(f"Σ «подтверждено выпиской» ПОСЛЕ: {after_total:.2f}")
        print(f"Разница: {(after_total - before_total):.2f}")

        if apply_changes:
            await db.commit()
            print("\nПРИМЕНЕНО (commit).")
        else:
            await db.rollback()
            print("\nDRY-RUN — изменения НЕ сохранены (rollback). Передайте --yes для реального применения.")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="выполнить и откатить (поведение по умолчанию)")
    parser.add_argument("--yes", action="store_true", help="применить по-настоящему (commit)")
    args = parser.parse_args()

    apply_changes = args.yes and not args.dry_run
    return await run(apply_changes)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
