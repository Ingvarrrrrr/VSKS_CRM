"""Закупки старой «ФАДМ_2026» → субсидия, загруженная из листа GoodsService
(сейчас «ФАДМ 2026_3»). Владелец 15.10.2026.

Пары:
  1. ИНН + сумма (у авансовых вместо ИНН — сотрудник, которому возмещаем:
     reimbursement_user_id, иначе assigned_user_id), одинаковые — по порядку;
  2. пары, которые владелец назвал сам (OWNER_PAIRS: номер РЕЕ старой →
     номер закупки D листа).
По паре — sheet_v2_enrich.transfer_pair (исполнитель/участники в пустые поля,
документы, состав при равных суммах, комментарии и история; старая
останавливается, если стадия позволяет).
MOVE_AS_IS — закупки старой, которых нет в листе, переносятся целиком
(sheet_v2_enrich.move_purchase_to_subsidy).
Остальные без пары остаются в старой — в отчёте.

    python -m scripts.fadm_sheet_load.pair_old_to_target --source-id 7 --target-id 100 [--apply]
Без --apply — всё в транзакции и откат. С --apply — бэкап-таблицы bk_<дата>_pair_*.
"""
from __future__ import annotations

import argparse
import asyncio
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text

from app.database import async_session
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_transfer.match import build_purchase_key

from .auto_approve_excess import auto_approve_subsidy_excess
from .feo_path_resolve import load_feo_tree
from .sheet_v2_enrich import (
    find_na_category_id, move_purchase_to_subsidy, pair_already_transferred, transfer_pair,
)

# Владелец 15.10.2026, разбор пар: РЕЕ старой → (№ закупки D листа, голова рамочного?)
OWNER_PAIRS: dict[str, tuple[str, bool]] = {
    "РЕЕ-2026-00776": ("15", False),   # авансовый, Голичков
    "РЕЕ-2026-00784": ("29", False),   # авансовый, Лягин 17 000
    "РЕЕ-2026-00841": ("42", False),   # авансовый, Голичков 4 000
    "РЕЕ-2026-00876": ("99", False),
    "РЕЕ-2026-00877": ("78", False),
    "РЕЕ-2026-00880": ("93", False),   # авансовый, Любарец
    "РЕЕ-2026-00885": ("92", False),   # авансовый, Любарец
    "РЕЕ-2026-00886": ("91", False),   # авансовый, Любарец
    "РЕЕ-2026-00973": ("108", False),  # авансовый, Дрелих
    "РЕЕ-2026-00976": ("119", False),  # 64 590
    "РЕЕ-2026-00773": ("3", True),     # ЦЕНТРАВТО, рамочный 600 000 → голова рамочного №3
}
# «Забыл занести в GoodsService» / «ещё не успел занести» — перенести целиком.
MOVE_AS_IS = ("РЕЕ-2026-00792", "РЕЕ-2026-04247")

_D_RE = re.compile(r"закупка\s+(\S+?)(?:,|\s|$)")


def _sheet_d(task_comment: str | None) -> str | None:
    m = _D_RE.search(task_comment or "")
    return m.group(1) if m else None


async def _active(db, sid: int) -> list[Purchase]:
    return list((await db.execute(select(Purchase).where(
        Purchase.subsidy_id == sid, Purchase.stopped_at.is_(None),
        Purchase.status.notin_(("cancelled", "draft")),
    ).order_by(Purchase.id))).scalars())


async def run(source_id: int, target_id: int, apply: bool, approve_as: int | None, requested_by: int | None) -> None:
    async with async_session() as db:
        old, new = await _active(db, source_id), await _active(db, target_id)
        inns = dict((await db.execute(select(Contractor.id, Contractor.inn))).all())
        amounts = await load_purchase_amounts(db, [p.id for p in old + new])

        def key(p: Purchase):
            # ПЕРЕНЕСЕНО в app.services.purchase_transfer.match.build_purchase_key
            # (ПРАВИЛО №6) — здесь только перевод в (поставщик_или_None, сумма),
            # формат, который использует остальной код этого модуля (pool/by_reg_old).
            amt = amounts[p.id].effective if p.id in amounts else None
            k = build_purchase_key(p, contractor_inn=inns.get(p.contractor_id), effective_amount=amt)
            supplier = k.supplier_key or k.inn or None
            return (supplier or None, k.amount)

        by_reg_old = {p.registry_number: p for p in old}
        pairs: list[tuple[Purchase, Purchase, str]] = []
        used_new: set[int] = set()

        # 2. Пары владельца — первыми, чтобы автопроход их не занял.
        for reg, (d, head) in OWNER_PAIRS.items():
            o = by_reg_old.get(reg)
            cand = [n for n in new if _sheet_d(n.task_comment) == d and n.id not in used_new
                    and (("рамочный договор" in (n.task_comment or "")) if head else n.parent_purchase_id is None)]
            if o is not None and len(cand) > 1:  # у закупки D несколько строк — та, что на ту же сумму
                same = [n for n in cand if o.id in amounts and n.id in amounts
                        and amounts[n.id].effective == amounts[o.id].effective]
                cand = same or cand
            if o is None or len(cand) != 1:
                print(f"  ! пара владельца {reg} → закупка {d}: старая {'есть' if o else 'НЕ НАЙДЕНА'}, кандидатов {len(cand)}")
                continue
            pairs.append((o, cand[0], "названа владельцем"))
            used_new.add(cand[0].id)
        owner_old_ids = {o.id for o, _, _ in pairs}

        # 1. ИНН (или сотрудник у авансового) + сумма, одинаковые — по порядку.
        pool = defaultdict(list)
        for n in new:
            k = key(n)
            if n.id not in used_new and k[0] and k[1]:
                pool[k].append(n)
        for o in old:
            if o.id in owner_old_ids or o.registry_number in MOVE_AS_IS:
                continue
            k = key(o)
            if k[0] and k[1] and pool.get(k):
                n = pool[k].pop(0)
                pairs.append((o, n, "ИНН + сумма" if not k[0].startswith("employee:") else "сотрудник + сумма"))
                used_new.add(n.id)

        paired_old = {o.id for o, _, _ in pairs}
        to_move = [p for p in old if p.registry_number in MOVE_AS_IS]
        left = [p for p in old if p.id not in paired_old and p.registry_number not in MOVE_AS_IS]

        print(f"старая: {len(old)} закупок, получатель: {len(new)}")
        print(f"пар: {len(pairs)} (владелец {len(owner_old_ids)}, автоматически {len(pairs) - len(owner_old_ids)}); "
              f"перенос целиком: {len(to_move)}; остаются в старой: {len(left)}")

        if apply:
            stamp = date.today().strftime("%Y%m%d")
            for t in ("purchases", "purchase_items", "purchase_members", "wishes", "contracts"):
                await db.execute(text(f"CREATE TABLE IF NOT EXISTS bk_{stamp}_pair_{t} AS TABLE {t}"))

        stopped = not_stopped = 0
        for o, n, how in pairs:
            if await pair_already_transferred(db, n.id):
                print(f"  = {o.registry_number} → {n.registry_number}: уже перенесено")
                continue
            r = await transfer_pair(db, o, n)
            stopped += r.stopped
            not_stopped += not r.stopped
            docs = r.docs
            print(f"  {o.registry_number} → {n.registry_number} [{how}] {amounts[o.id].effective if o.id in amounts else ''}: "
                  f"участников +{r.members_added}, файлов +{getattr(docs, 'files_copied', 0)}, "
                  f"состав {'перенесён' if r.items_transferred else 'нет (' + r.items_skip_reason + ')'}, "
                  f"комментариев {r.comments_copied}, событий {r.events_copied}, "
                  f"старая {'остановлена' if r.stopped else 'НЕ остановлена: ' + r.stop_skip_reason}")

        if to_move:
            src_tree, dst_tree = await load_feo_tree(db, source_id), await load_feo_tree(db, target_id)
            na_id = await find_na_category_id(db, target_id)
            for p in to_move:
                r = await move_purchase_to_subsidy(db, p, target_subsidy_id=target_id, source_tree=src_tree,
                                                   target_tree=dst_tree, na_category_id=na_id)
                twins = [n.registry_number for n in new if amounts.get(n.id) and p.id in amounts
                         and amounts[n.id].effective == amounts[p.id].effective]
                print(f"  ПЕРЕНОС {p.registry_number} {amounts[p.id].effective if p.id in amounts else ''}: "
                      f"{'перенесена' if r.moved else 'нет: ' + r.reason}, категория {'по пути' if r.category_matched else '«не определена»'}"
                      + (f"; в получателе та же сумма у {', '.join(twins)} — проверить, не дубль" if twins else ""))

        print(f"старых остановлено: {stopped}, не остановлено (стадия дальше договора): {not_stopped}")
        print("ОСТАЮТСЯ в старой (пары нет):")
        for p in left:
            print(f"  {p.registry_number} {p.status} {p.purchase_method or ''} {amounts[p.id].effective if p.id in amounts else ''} "
                  f"{(p.subject or p.item_name or '')[:40]}")

        if approve_as:
            approvals = await auto_approve_subsidy_excess(
                db, target_id, requester_id=requested_by or approve_as, approver_id=approve_as,
                comment="автосогласование: перенос ФАДМ_2026 → ФАДМ 2026_3",
            )
            print(f"согласовано превышений: {len(approvals)}")
            for a in approvals:
                print(f"  {a.category_name[:70]} — {a.kind}: {a.amount}")

        if apply:
            await db.commit()
            print("ЗАПИСАНО")
        else:
            await db.rollback()
            print("пробно, откат")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", type=int, required=True)
    ap.add_argument("--target-id", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approve-excess-as", type=int, help="id пользователя, от чьего имени согласовать превышение")
    ap.add_argument("--requested-by", type=int, help="id пользователя-инициатора запроса согласования")
    a = ap.parse_args()
    asyncio.run(run(a.source_id, a.target_id, a.apply, a.approve_excess_as, a.requested_by))


if __name__ == "__main__":
    main()
