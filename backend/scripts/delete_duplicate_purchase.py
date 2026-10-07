#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Удаление ОДНОЙ конкретной закупки-дубля и её заявки-спутника (владелец,
08.10.2026): закупка РЕЕ-2026-03211 (Purchase.id=3211, subsidy_id=89,
status='wishes', purchase_method='advance', contract_id=1243 — техническая
копия договора «2026/973») и Wish.id=123 («Возмещение по авансовому отчёту
РЕЕ-2026-00973», status='submitted').

МЕХАНИЗМ (ПРАВИЛО №6 — не второй каскад, используется СУЩЕСТВУЮЩИЙ):
  - закупка — app.routers.purchases.delete_purchase_core(p, db): тело того же
    DELETE /api/purchases/{pid}. Сама функция — db.delete(p); каскады
    (purchase_items/purchase_receipts/purchase_files/purchase_comments/
    purchase_events/purchase_approvals/subsidy_allocations/contract_items
    этой закупки/platform_publications/paid_confirmations) — на уровне БД,
    ondelete=CASCADE (см. соответствующие models/*.py);
  - заявка — то же тело, что DELETE /api/wishes/{wish_id}: db.delete(wish)
    (каскад БД: wish_items/wish_approvals/wish_members);
  - договор 1243 — app.routers.contracts.delete_contract core: db.delete(c),
    ТОЛЬКО если на него после удаления закупки не ссылается больше ни одна
    другая Purchase.contract_id (иначе он используется кем-то ещё и не
    трогается).

ПОРЯДОК УДАЛЕНИЯ (важно для FK):
  1) Wish — Wish.purchase_id -> purchases.id БЕЗ ondelete (NO ACTION); если
     удалить закупку раньше, это будет violation. Удаление wish убирает
     ссылающуюся строку целиком, конфликта нет.
  2) Purchase — purchases.wish_id -> wishes.id ondelete SET NULL, к этому
     моменту wish уже удалён, так что это неважно.
  3) Contract — только если ничья другая Purchase.contract_id на него не
     ссылается.

ФАЙЛЫ (acceptance_docs, PurchaseFile 72..82 у покупки 3211): по коду копии
субсидии (app/services/subsidy_copy/copy_purchases.py:181-186 — «Файлы — та
же ссылка на физический файл (filepath), новая строка») строки PurchaseFile
копируемой закупки — это НОВЫЕ строки БД с ТЕМ ЖЕ filepath, что у оригинала
973. Физический файл на диске может быть ОБЩИЙ. Поэтому этот скрипт НИКОГДА
не трогает файловую систему — удаляются только строки purchase_files (CASCADE
по purchase_id=3211), filepath на диске не затрагивается ни в --apply, ни
иначе. Перед удалением скрипт печатает filepath каждого файла и помечает,
встречается ли тот же filepath у других PurchaseFile (в т.ч. у оригинала) —
если встречается, это подтверждает, что файл shared и удалять его с диска
было бы НЕЛЬЗЯ (мы и не удаляем).

ПРЕДОХРАНИТЕЛИ (жёстко, без --force):
  purchase.id == 3211, registry_number == 'РЕЕ-2026-03211',
  subsidy_id == 89, status == 'wishes';
  wish.id == 123, purchase.wish_id == 123 (или Wish.purchase_id == 3211).
  Любое расхождение -> отказ без изменений.

ДАМП ПЕРЕД УДАЛЕНИЕМ: все удаляемые строки (purchases, purchase_items,
purchase_receipts, purchase_files, purchase_comments, purchase_events,
purchase_approvals, subsidy_allocations, contract_items, platform_publications,
purchase_paid_confirmations, wishes, wish_items, wish_approvals, wish_members,
contracts — если удаляется) сериализуются в JSON (Decimal/date/datetime -> str)
в /tmp/deleted_purchase_<id>_<ts>.json, путь печатается.

РЕЖИМЫ:
  без --apply — печатает план и дамп, в конце ROLLBACK (безопасно гонять
                повторно для проверки);
  --apply     — то же, в конце COMMIT.

ЗАПУСК (backend/scripts НЕ смонтирован volume'ом — нужен docker cp ПЕРЕД
запуском, см. docstring соседних backend/scripts/*.py):
    MSYS_NO_PATHCONV=1 docker cp backend/scripts/delete_duplicate_purchase.py \\
        vsks_crm-backend_a-1:/app/scripts/delete_duplicate_purchase.py
    docker exec vsks_crm-backend_a-1 python scripts/delete_duplicate_purchase.py \\
        --purchase-id 3211 --wish-id 123
    (повторить с --apply, когда план одобрен владельцем)

ЛОКАЛЬНАЯ ПРОВЕРКА ЛОГИКИ (без --apply, предохранители ослаблены флагом
--unsafe-local-check ТОЛЬКО для этого): см. --unsafe-local-check ниже — он
отключает проверки registry_number/subsidy_id/wish-id и принимает любые
--purchase-id/--wish-id, но НИКОГДА не коммитит (игнорирует --apply).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.purchase_receipt import PurchaseReceipt  # noqa: E402
from app.models.purchase_file import PurchaseFile  # noqa: E402
from app.models.purchase_comment import PurchaseComment  # noqa: E402
from app.models.purchase_approval import PurchaseApproval  # noqa: E402
from app.models.subsidy_allocation import PurchaseSubsidyAllocation  # noqa: E402
from app.models.contract import Contract  # noqa: E402
from app.models.contract_item import ContractItem  # noqa: E402
from app.models.wish import Wish  # noqa: E402
from app.models.wish_item import WishItem  # noqa: E402
from app.routers.purchases import delete_purchase_core  # noqa: E402

try:
    from app.models.purchase_event import PurchaseEvent  # noqa: E402
except Exception:  # pragma: no cover - имя модели может отличаться
    PurchaseEvent = None

try:
    from app.models.platform_publication import PlatformPublication  # noqa: E402
except Exception:  # pragma: no cover
    PlatformPublication = None

try:
    from app.models.purchase_paid_confirmation import PurchasePaidConfirmation  # noqa: E402
except Exception:  # pragma: no cover
    PurchasePaidConfirmation = None

try:
    from app.models.wish_approval import WishApproval  # noqa: E402
except Exception:  # pragma: no cover
    WishApproval = None

try:
    from app.models.wish_member import WishMember  # noqa: E402
except Exception:  # pragma: no cover
    WishMember = None


EXPECTED_PURCHASE_ID = 3211
EXPECTED_WISH_ID = 123
EXPECTED_REGISTRY_NUMBER = "РЕЕ-2026-03211"
EXPECTED_SUBSIDY_ID = 89
EXPECTED_STATUS = "wishes"


def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)


def _row_to_dict(obj) -> dict:
    out = {}
    for col in obj.__table__.columns:
        out[col.name] = getattr(obj, col.name)
    return out


async def _rows(db, model, **filters) -> list:
    stmt = select(model)
    for k, v in filters.items():
        stmt = stmt.where(getattr(model, k) == v)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _check_safety(db, purchase_id: int, wish_id: int, unsafe_local: bool):
    """Предохранители. unsafe_local отключает все проверки, кроме
    существования строк — используется ТОЛЬКО для локальной проверки логики
    на произвольной закупке, и НИКОГДА разрешает --apply (см. main())."""
    p = await db.get(Purchase, purchase_id)
    if p is None:
        raise SystemExit(f"Purchase.id={purchase_id} не найден")
    w = await db.get(Wish, wish_id)
    if w is None:
        raise SystemExit(f"Wish.id={wish_id} не найден")

    if unsafe_local:
        return p, w

    if purchase_id != EXPECTED_PURCHASE_ID:
        raise SystemExit(f"Отказ: --purchase-id должен быть {EXPECTED_PURCHASE_ID}")
    if wish_id != EXPECTED_WISH_ID:
        raise SystemExit(f"Отказ: --wish-id должен быть {EXPECTED_WISH_ID}")
    if (p.registry_number or "") != EXPECTED_REGISTRY_NUMBER:
        raise SystemExit(
            f"Отказ: registry_number={p.registry_number!r}, ожидалось {EXPECTED_REGISTRY_NUMBER!r}"
        )
    if p.subsidy_id != EXPECTED_SUBSIDY_ID:
        raise SystemExit(f"Отказ: subsidy_id={p.subsidy_id}, ожидалось {EXPECTED_SUBSIDY_ID}")
    if p.status != EXPECTED_STATUS:
        raise SystemExit(f"Отказ: status={p.status!r}, ожидалось {EXPECTED_STATUS!r}")

    linked = (p.wish_id == wish_id) or (w.purchase_id == purchase_id)
    if not linked:
        raise SystemExit(
            f"Отказ: заявка {wish_id} и закупка {purchase_id} не связаны "
            f"(purchase.wish_id={p.wish_id}, wish.purchase_id={w.purchase_id})"
        )
    return p, w


async def run_delete(db, purchase_id: int, wish_id: int, unsafe_local: bool = False):
    p, w = await _check_safety(db, purchase_id, wish_id, unsafe_local)

    purchase_items = await _rows(db, PurchaseItem, purchase_id=purchase_id)
    receipts = await _rows(db, PurchaseReceipt, purchase_id=purchase_id)
    files = await _rows(db, PurchaseFile, purchase_id=purchase_id)
    comments = await _rows(db, PurchaseComment, purchase_id=purchase_id)
    approvals = await _rows(db, PurchaseApproval, purchase_id=purchase_id)
    allocations = await _rows(db, PurchaseSubsidyAllocation, purchase_id=purchase_id)
    contract_items = await _rows(db, ContractItem, purchase_id=purchase_id)
    events = await _rows(db, PurchaseEvent, purchase_id=purchase_id) if PurchaseEvent is not None else []
    publications = (
        await _rows(db, PlatformPublication, purchase_id=purchase_id) if PlatformPublication is not None else []
    )
    paid_confirmations = (
        await _rows(db, PurchasePaidConfirmation, purchase_id=purchase_id)
        if PurchasePaidConfirmation is not None else []
    )

    wish_items = await _rows(db, WishItem, wish_id=wish_id)
    wish_approvals = await _rows(db, WishApproval, wish_id=wish_id) if WishApproval is not None else []
    wish_members = await _rows(db, WishMember, wish_id=wish_id) if WishMember is not None else []

    # Все FK на contracts.id без ondelete=CASCADE/SET NULL, которые реально
    # блокируют DELETE (найдено локальной проверкой, см. docstring):
    # purchases.contract_id, payments.contract_id, bank_payments.matched_contract_id.
    # contract_items.contract_id — ondelete=SET NULL, не блокирует.
    # contract_subsidies.contract_id — ondelete=CASCADE, не блокирует.
    from app.models.payment import Payment as _Payment
    from app.models.bank_statement import BankPayment as _BankPayment

    contract = None
    contract_other_refs = 0
    contract_blockers = {}
    if p.contract_id:
        contract = await db.get(Contract, p.contract_id)
        if contract is not None:
            other_purchases = await _rows(db, Purchase, contract_id=p.contract_id)
            other_purchases_n = len([o for o in other_purchases if o.id != purchase_id])
            other_payments_n = len(await _rows(db, _Payment, contract_id=p.contract_id))
            other_bank_payments_n = len(await _rows(db, _BankPayment, matched_contract_id=p.contract_id))
            contract_blockers = {
                "other_purchases": other_purchases_n,
                "payments": other_payments_n,
                "bank_payments_matched": other_bank_payments_n,
            }
            contract_other_refs = other_purchases_n + other_payments_n + other_bank_payments_n

    # Проверка shared-файлов: совпадает ли filepath этой закупки с чьим-то ещё.
    file_rows = []
    for f in files:
        same_path = await _rows(db, PurchaseFile, filepath=f.filepath)
        other_owners = sorted({r.purchase_id for r in same_path if r.purchase_id != purchase_id})
        file_rows.append({
            **_row_to_dict(f),
            "filepath_shared_with_purchase_ids": other_owners,
        })

    dump = {
        "purchase": _row_to_dict(p),
        "purchase_items": [_row_to_dict(x) for x in purchase_items],
        "purchase_receipts": [_row_to_dict(x) for x in receipts],
        "purchase_files": file_rows,
        "purchase_comments": [_row_to_dict(x) for x in comments],
        "purchase_events": [_row_to_dict(x) for x in events],
        "purchase_approvals": [_row_to_dict(x) for x in approvals],
        "subsidy_allocations": [_row_to_dict(x) for x in allocations],
        "contract_items_of_this_purchase": [_row_to_dict(x) for x in contract_items],
        "platform_publications": [_row_to_dict(x) for x in publications],
        "purchase_paid_confirmations": [_row_to_dict(x) for x in paid_confirmations],
        "wish": _row_to_dict(w),
        "wish_items": [_row_to_dict(x) for x in wish_items],
        "wish_approvals": [_row_to_dict(x) for x in wish_approvals],
        "wish_members": [_row_to_dict(x) for x in wish_members],
        "contract": _row_to_dict(contract) if contract is not None else None,
        "contract_will_be_deleted": bool(contract is not None and contract_other_refs == 0),
        "contract_other_refs": contract_blockers,
    }

    print("=" * 100)
    print(f"Закупка id={p.id} {p.registry_number!r} subsidy_id={p.subsidy_id} status={p.status!r} contract_id={p.contract_id}")
    print(f"  позиций: {len(purchase_items)}, чеков: {len(receipts)}, файлов: {len(files)}, "
          f"комментариев: {len(comments)}, событий: {len(events)}, approvals: {len(approvals)}, "
          f"аллокаций субсидии: {len(allocations)}, contract_items (этой закупки): {len(contract_items)}, "
          f"publications: {len(publications)}, paid_confirmations: {len(paid_confirmations)}")
    for fr in file_rows:
        shared = fr["filepath_shared_with_purchase_ids"]
        tag = f" shared с purchase_id={shared}" if shared else " (НЕ shared, уникальный путь)"
        print(f"    file_id={fr['id']} filepath={fr['filepath']}{tag}")
    print(f"  Файлы с диска НЕ удаляются (только строки purchase_files).")
    print(f"Заявка id={w.id} {w.title!r} status={w.status!r} purchase_id={w.purchase_id}")
    print(f"  позиций заявки: {len(wish_items)}, approvals: {len(wish_approvals)}, members: {len(wish_members)}")
    if contract is not None:
        action = "БУДЕТ удалён" if contract_other_refs == 0 else f"НЕ трогаем — ссылки: {contract_blockers}"
        print(f"Договор id={contract.id} number={contract.number!r} subsidy_id={contract.subsidy_id} -> {action}")
    else:
        print("Договор: contract_id не задан или не найден — ничего не удаляем")

    ts = int(time.time())
    dump_path = f"/tmp/deleted_purchase_{purchase_id}_{ts}.json"
    with open(dump_path, "w", encoding="utf-8") as fh:
        json.dump(dump, fh, ensure_ascii=False, indent=2, default=_json_default)
    print(f"Дамп удаляемых строк: {dump_path}")

    # 1) заявка (Wish.purchase_id -> purchases.id без ondelete — удалить раньше закупки)
    await db.delete(w)
    await db.flush()

    # 2) закупка — тот же код, что DELETE /api/purchases/{pid}
    await delete_purchase_core(p, db)
    await db.flush()

    # 3) договор — тот же код, что DELETE /api/contracts/{cid}, только если осиротел
    # (проверены все известные FK на contracts.id без CASCADE/SET NULL: purchases.
    # contract_id, payments.contract_id, bank_payments.matched_contract_id — см. выше).
    # Доп. try/except — страховка на случай непредвиденного FK: если БД всё равно
    # отказала, договор просто НЕ удаляется, а закупка/заявка уже удалены успешно.
    if contract is not None and contract_other_refs == 0:
        try:
            await db.delete(contract)
            await db.flush()
        except Exception as exc:  # pragma: no cover - страховка, см. комментарий выше
            await db.rollback()
            raise SystemExit(
                f"Не удалось удалить договор id={contract.id}: {exc}. "
                f"Закупка/заявка НЕ удалены (вся транзакция откатана) — проверьте "
                f"неучтённую FK-ссылку на contracts.id и повторите запуск."
            )

    return dump, dump_path


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--purchase-id", type=int, required=True)
    ap.add_argument("--wish-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--unsafe-local-check", action="store_true",
        help="Только для локальной проверки на произвольной закупке; отключает "
             "предохранители registry_number/subsidy_id/status/wish-link, но "
             "ИГНОРИРУЕТ --apply (всегда ROLLBACK).",
    )
    args = ap.parse_args()

    apply = args.apply and not args.unsafe_local_check

    async with async_session() as db:
        try:
            dump, dump_path = await run_delete(
                db, args.purchase_id, args.wish_id, unsafe_local=args.unsafe_local_check
            )
        except SystemExit:
            await db.rollback()
            raise

        if apply:
            await db.commit()
            print(f"COMMIT. Дамп: {dump_path}")
        else:
            await db.rollback()
            reason = " (--unsafe-local-check: --apply игнорируется)" if args.unsafe_local_check else ""
            print(f"ROLLBACK (dry-run{reason}). Запустите с --apply для применения. Дамп: {dump_path}")


if __name__ == "__main__":
    asyncio.run(main())
