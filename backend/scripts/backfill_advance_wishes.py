#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бэкфилл заявок-компаньонов для старых авансовых отчётов без заявки.

ПОВОД (владелец, 2026-10-07). Авансовый отчёт (Purchase.purchase_method=
'advance') должен иметь заявку-компаньона (Wish source='advance_report',
title «Возмещение по авансовому отчёту <реестровый №>») — так он попадает
во вкладку «Заявки» и проходит обычное согласование возмещения. С 16.09
это заводится автоматически при создании (routers/purchases.py::
create_purchase, ветка is_advance) через общую функцию
app/services/advance_companion_wish.py::create_advance_companion_wish —
этот скрипт зовёт ТУ ЖЕ функцию, а не второй механизм (ПРАВИЛО №6).
На проде нашлось 44 таких закупки (созданы импортом или до 16.09).

ОТБОР (идемпотентность). Purchase.purchase_method='advance' И wish_id IS
NULL И нет ни одной Wish, title которой СОДЕРЖИТ её registry_number (так
повторный запуск не плодит дублей даже если предыдущий --apply откатили
руками, а не через --rollback).

СТАТУС БУДУЩЕЙ ЗАЯВКИ. purchase.status == 'wishes' → заявка 'draft' (как у
обычного только что созданного компаньона, который ещё не отправляли на
согласование). Любой другой статус закупки (в работе/оплачена и т.д.) →
заявка 'converted' — закупка уже прошла стадию, которую заявка обычно
подтверждает, заводить её «на подпись» задним числом бессмысленно.

АВТОР (created_by). Purchase.reimbursement_user_id ИЛИ assigned_user_id
ИЛИ service_note_by — первый заполненный. Если ВСЕ три пустые — закупка
пропускается с причиной (нет кого указать автором заявки).

ORG_ID. У Purchase своего org_id нет (в отличие от роутера, где берётся у
current_user через get_single_org_id) — используем org_id автора (того же
пользователя, что и created_by).

ESTIMATED_PRICE. purchase.total_nmck или purchase.contract_price — то же
правило, что внутри create_advance_companion_wish (там этот источник уже
единственный, скрипт его не переопределяет).

БЕЗ побочных эффектов: никаких уведомлений/пересчётов превышения — только
Wish/WishItem insert и purchase.wish_id/purchase_item.wish_item_id.

Запуск (backend-код смонтирован, перезапуск контейнера не нужен):
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_advance_wishes.py
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_advance_wishes.py --apply
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_advance_wishes.py --purchase-ids 101,102
  docker compose -p vsks_crm exec -T backend_a python scripts/backfill_advance_wishes.py --rollback /tmp/backfill_advance_wishes_20261007_120000.json

Без --apply — только печать (dry-run), в конце ROLLBACK.
"""
import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.purchase import Purchase  # noqa: E402
from app.models.purchase_item import PurchaseItem  # noqa: E402
from app.models.wish import Wish  # noqa: E402
from app.models.wish_item import WishItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.subsidy import Subsidy  # noqa: E402
from app.services.advance_companion_wish import create_advance_companion_wish  # noqa: E402
from app.services.fio import compose_fio  # noqa: E402

COMPANION_TITLE_PREFIX = "Возмещение по авансовому отчёту"


async def _already_has_companion(db, purchase: Purchase) -> bool:
    """Идемпотентность: Wish с title, содержащим registry_number этой закупки."""
    reg = (purchase.registry_number or "").strip()
    if not reg:
        return False
    res = await db.execute(select(Wish.id).where(Wish.title.contains(reg)).limit(1))
    return res.scalar_one_or_none() is not None


def _pick_creator_id(purchase: Purchase):
    """created_by с причиной пропуска, если все кандидаты пусты."""
    for field in ("reimbursement_user_id", "assigned_user_id", "service_note_by"):
        val = getattr(purchase, field)
        if val:
            return val, field
    return None, None


def companion_status_for_purchase(purchase_status: str) -> str:
    """ПРАВИЛО №6 — единственное место, где решается статус заявки-бэкфилла
    (используется и скриптом, и тестами, см. test_advance_companion_wish.py)."""
    return "draft" if purchase_status == "wishes" else "converted"


async def _candidates(db, purchase_ids=None):
    stmt = select(Purchase).where(
        Purchase.purchase_method == "advance",
        Purchase.wish_id.is_(None),
    ).order_by(Purchase.id)
    if purchase_ids:
        stmt = stmt.where(Purchase.id.in_(purchase_ids))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def run_backfill(db, purchase_ids=None, apply: bool = False):
    """Ядро скрипта — отдельная функция, чтобы тест мог звать её напрямую
    без subprocess (см. test_advance_companion_wish.py)."""
    candidates = await _candidates(db, purchase_ids)

    rows = []
    rollback_entries = []
    created = 0
    skipped = 0

    for p in candidates:
        if await _already_has_companion(db, p):
            rows.append({
                "purchase_id": p.id, "registry_number": p.registry_number,
                "skip": "уже есть заявка с таким реестровым номером в title (идемпотентность)",
            })
            skipped += 1
            continue

        created_by, source_field = _pick_creator_id(p)
        if not created_by:
            rows.append({
                "purchase_id": p.id, "registry_number": p.registry_number,
                "skip": "нет reimbursement_user_id/assigned_user_id/service_note_by — некого указать автором",
            })
            skipped += 1
            continue

        creator = await db.get(User, created_by)
        if creator is None:
            rows.append({
                "purchase_id": p.id, "registry_number": p.registry_number,
                "skip": f"created_by={created_by} (поле {source_field}) — пользователь не найден в БД",
            })
            skipped += 1
            continue

        items_res = await db.execute(
            select(PurchaseItem).where(PurchaseItem.purchase_id == p.id).order_by(PurchaseItem.id)
        )
        purchase_items = list(items_res.scalars().all())

        wish_status = companion_status_for_purchase(p.status)

        subsidy_name = None
        if p.subsidy_id:
            subsidy_name = (await db.execute(
                select(Subsidy.name).where(Subsidy.id == p.subsidy_id)
            )).scalar_one_or_none()

        wish = await create_advance_companion_wish(
            db, p, purchase_items,
            created_by=created_by,
            org_id=creator.org_id,
            status=wish_status,
            creator=creator,
        )
        await db.flush()

        rows.append({
            "purchase_id": p.id,
            "registry_number": p.registry_number,
            "subsidy": subsidy_name,
            "purchase_status": p.status,
            "amount": str(p.total_nmck if p.total_nmck is not None else (p.contract_price or "")),
            "items": len(purchase_items),
            "created_by": compose_fio(creator.last_name, creator.first_name, creator.middle_name) or creator.full_name or creator.username,
            "wish_status": wish_status,
            "wish_id": wish.id,
        })
        rollback_entries.append({
            "purchase_id": p.id,
            "wish_id": wish.id,
            "wish_item_ids": list((await db.execute(
                select(WishItem.id).where(WishItem.wish_id == wish.id)
            )).scalars().all()),
            "purchase_item_ids": [pi.id for pi in purchase_items],
        })
        created += 1

    return rows, rollback_entries, created, skipped


def _print_report(rows, created, skipped):
    print(f"{'purchase_id':>11}  {'реестровый №':<18}  {'субсидия':<28}  {'статус закупки':<16}  {'сумма':>14}  поз.  {'автор':<28}  статус заявки")
    print("-" * 160)
    for r in rows:
        if "skip" in r:
            print(f"{r['purchase_id']:>11}  {str(r.get('registry_number') or ''):<18}  — пропуск: {r['skip']}")
            continue
        print(
            f"{r['purchase_id']:>11}  {str(r['registry_number'] or ''):<18}  "
            f"{(r['subsidy'] or '')[:28]:<28}  {r['purchase_status']:<16}  {r['amount']:>14}  "
            f"{r['items']:>4}  {(r['created_by'] or '')[:28]:<28}  {r['wish_status']} (wish_id={r['wish_id']})"
        )
    print("-" * 160)
    print(f"Итого: кандидатов {len(rows)}, создано заявок {created}, пропущено {skipped}.")


async def do_rollback(db, payload_path: str):
    with open(payload_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    reverted = 0
    for e in entries:
        wish = await db.get(Wish, e["wish_id"])
        if wish is None:
            print(f"  wish_id={e['wish_id']}: уже не существует, пропуск.")
            continue
        if not (wish.title or "").startswith(COMPANION_TITLE_PREFIX):
            print(f"  wish_id={e['wish_id']}: title не похож на бэкфилл-компаньона ({wish.title!r}) — пропуск, НЕ трогаю.")
            continue
        updated_at = getattr(wish, "updated_at", None)
        created_at = getattr(wish, "created_at", None)
        if updated_at is not None and created_at is not None and updated_at != created_at:
            print(f"  wish_id={e['wish_id']}: заявка менялась после создания (updated_at != created_at) — пропуск, НЕ трогаю.")
            continue

        await db.execute(
            Purchase.__table__.update()
            .where(Purchase.id == e["purchase_id"])
            .values(wish_id=None)
        )
        if e["purchase_item_ids"]:
            await db.execute(
                PurchaseItem.__table__.update()
                .where(PurchaseItem.id.in_(e["purchase_item_ids"]))
                .values(wish_item_id=None)
            )
        if e["wish_item_ids"]:
            await db.execute(delete(WishItem).where(WishItem.id.in_(e["wish_item_ids"])))
        await db.execute(delete(Wish).where(Wish.id == e["wish_id"]))
        reverted += 1
        print(f"  wish_id={e['wish_id']} (purchase_id={e['purchase_id']}): откатано.")

    print(f"Откатано {reverted} из {len(entries)}.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="применить изменения (без флага — только печать, в конце ROLLBACK)")
    parser.add_argument("--purchase-ids", type=str, default=None, help="ограничить конкретными id закупок, через запятую")
    parser.add_argument("--rollback", type=str, default=None, metavar="JSON_PATH", help="откатить ранее сделанный --apply по файлу отката")
    args = parser.parse_args()

    purchase_ids = None
    if args.purchase_ids:
        purchase_ids = [int(x) for x in args.purchase_ids.split(",") if x.strip()]

    async with async_session() as db:
        if args.rollback:
            await do_rollback(db, args.rollback)
            await db.commit()
            return 0

        rows, rollback_entries, created, skipped = await run_backfill(db, purchase_ids, apply=args.apply)
        _print_report(rows, created, skipped)

        if args.apply:
            if rollback_entries:
                ts = time.strftime("%Y%m%d_%H%M%S")
                out_path = f"/tmp/backfill_advance_wishes_{ts}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(rollback_entries, f, ensure_ascii=False, indent=2)
                print(f"Файл отката: {out_path}")
            await db.commit()
            print(f"COMMIT — применено, создано заявок: {created}.")
        else:
            await db.rollback()
            print("ROLLBACK — это был dry-run (--apply не передан), изменения НЕ применены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
