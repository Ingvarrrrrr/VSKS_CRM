"""Режим `--rebuild-in-place` (задание владельца 15.10.2026, Шаг 1 плана
sleepy-fluttering-walrus.md) — пересборка УЖЕ существующей субсидии («ФАДМ
2026_2», id=89 на проде) из листа GoodsService БЕЗ трогания дерева ФЭО
(категории + budget на них), участников и шаблонов. Отдельный файл (ПРАВИЛО
№5 — sheet_v2_build.py уже > 500 строк, второй режим сборки сюда не
дописываем) — реально создающая логика ПЕРЕИСПОЛЬЗУЕТСЯ целиком
(sheet_v2_build.py::populate_subsidy_v2, ПРАВИЛО №6), этот модуль только:
  1. находит целевую субсидию (по id или по имени);
  2. снимает JSON-снимок того, что будет удалено (см. snapshot_before_rebuild
     ниже — формат читает sheet_v2_enrich.py на Шаге 4 плана, перенос
     подтверждений «Оплачено»);
  3. удаляет ТОЛЬКО то, что создал загрузчик (закупки/договоры/плановые
     позиции/платежи), используя ТЕ ЖЕ приёмы, что delete_target_subsidy
     (sheet_v2_build.py) — explicit DELETE Payment/PurchaseItem, обнуление
     bank_payments.matched_* — но НЕ трогает FeoCategory/Subsidy;
  4. вызывает populate_subsidy_v2(create_feo_plan_rows=False) на этой же
     субсидии.

ПРИЗНАК «закупка загрузчика» — Purchase.task_comment LIKE 'Таблица
GoodsService:%' (проставляется в build_single/build_framework,
sheet_v2_build.py — единственное надёжное маркер-поле: task_comment не
редактируется людьми через обычный UI закупки, в отличие от subject/notes).
Плановая позиция загрузчика — FeoPlannedItem.notes LIKE 'Создано импорт
GoodsService (план Y,%' (_build_plan_items_v2 передаёт текст в
create_auto_planned_item, а тот ВСЕГДА добавляет префикс "Создано ",
app/services/plan_autoassign.py — тот же префикс, что ищет
remap_feo_categories.py::_LOADER_NOTE_PREFIX, ПРАВИЛО №6) — такие позиции с
рамочным текстом заметок не пишет никто, кроме загрузчика.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseEvent
from app.models.purchase_item import PurchaseItem
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.subsidy import Subsidy

from .sheet_v2_build import BuildCountersV2, populate_subsidy_v2
from .sheet_v2_parse import SheetRowV2

LOADER_TASK_COMMENT_PREFIX = "Таблица GoodsService:"
LOADER_PLAN_ITEM_NOTE_PREFIX = "Создано импорт GoodsService (план Y, ключ"
# «Ручные правки после загрузки листа» (риск плана, раздел «Риски») — снимок
# показывает purchase_events НОВЕЕ этой даты, чтобы владелец увидел, что
# именно пропадёт при пересборке (последняя сессия загрузчика — 06.10.2026).
MANUAL_EDITS_SINCE = datetime(2026, 10, 6, 0, 0, 0)

_TASK_COMMENT_RE = re.compile(
    r"^Таблица GoodsService: закупка (?P<no>[^\s,(]+)(?:, заказ (?P<order>\S+))?"
)


def parse_loader_key_from_task_comment(task_comment: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(purchase_no, order_no) из task_comment загрузчика — используется
    только для диагностики/отчёта (сам ключ листа для платежей и ФЭО —
    ИНН+D+E — восстанавливается надёжнее через Contractor.inn закупки, см.
    snapshot_before_rebuild, т.к. голова/заказ рамочного не всегда несут ИНН
    в тексте task_comment)."""
    if not task_comment:
        return None, None
    m = _TASK_COMMENT_RE.match(task_comment)
    if not m:
        return None, None
    return m.group("no"), m.group("order")


async def find_target_subsidy(db: AsyncSession, *, target_id: Optional[int],
                               target_name: Optional[str]) -> Subsidy:
    if target_id:
        subsidy = await db.get(Subsidy, target_id)
        if subsidy is None:
            raise ValueError(f"Субсидия id={target_id} не найдена")
        return subsidy
    if target_name:
        subsidy = (await db.execute(
            select(Subsidy).where(Subsidy.name == target_name)
        )).scalars().first()
        if subsidy is None:
            raise ValueError(f"Субсидия «{target_name}» не найдена")
        return subsidy
    raise ValueError("--rebuild-in-place требует --target-id или --name")


async def _loader_purchase_ids(db: AsyncSession, subsidy_id: int) -> list[int]:
    return list((await db.execute(
        select(Purchase.id).where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.task_comment.ilike(f"{LOADER_TASK_COMMENT_PREFIX}%"),
        )
    )).scalars().all())


async def _loader_plan_item_ids(db: AsyncSession, subsidy_id: int) -> list[int]:
    category_ids = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not category_ids:
        return []
    return list((await db.execute(
        select(FeoPlannedItem.id).where(
            FeoPlannedItem.feo_category_id.in_(category_ids),
            FeoPlannedItem.notes.ilike(f"{LOADER_PLAN_ITEM_NOTE_PREFIX}%"),
        )
    )).scalars().all())


# ---------------------------------------------------------------------------
# Снимок перед удалением (п.5 задания) — ЧИТАЕТ sheet_v2_enrich.py (Шаг 4
# плана, перенос подтверждений «Оплачено»). ФОРМАТ JSON:
# {
#   "subsidy_id": int, "taken_at": "ISO8601",
#   "purchases": [
#     {
#       "purchase_id": int, "registry_number": str|null,
#       "task_comment": str, "purchase_no": str|null, "order_no": str|null,
#       "inn": str|null, "contractor_name": str|null, "status": str,
#       "confirmations": [
#         {"id", "status", "amount_confirmed", "decided_by", "decided_at",
#          "requested_at", "comment"}
#       ],
#       "payments": [{"id", "bank_payment_id", "amount", "payment_source"}],
#       "manual_events_since_2026-10-06": [
#         {"event_type", "user_id", "data", "created_at"}
#       ]
#     }, ...
#   ]
# }
# Ключ листа (ИНН, D, E) — "inn"/"purchase_no"/"order_no" на каждой закупке;
# purchase_no/order_no парсятся из task_comment (слабее ИНН, но единственный
# способ восстановить D/E для закупки, раз сама SheetRowV2 к этому моменту не
# хранится в БД) — sheet_v2_enrich.py сопоставляет по (inn, purchase_no,
# order_no), order_no=None у разовых/голов.
# ---------------------------------------------------------------------------
async def snapshot_before_rebuild(db: AsyncSession, subsidy: Subsidy) -> dict:
    purchase_ids = await _loader_purchase_ids(db, subsidy.id)
    out: dict = {
        "subsidy_id": subsidy.id, "subsidy_name": subsidy.name,
        "taken_at": datetime.utcnow().isoformat(), "purchases": [],
    }
    if not purchase_ids:
        return out

    purchases = (await db.execute(
        select(Purchase).where(Purchase.id.in_(purchase_ids))
    )).scalars().all()
    contractor_ids = {p.contractor_id for p in purchases if p.contractor_id}
    contractors = {}
    if contractor_ids:
        rows = (await db.execute(
            select(Contractor.id, Contractor.inn, Contractor.name).where(Contractor.id.in_(contractor_ids))
        )).all()
        contractors = {cid: (inn, name) for cid, inn, name in rows}

    confirmations_by_purchase: dict[int, list] = {}
    conf_rows = (await db.execute(
        select(PurchasePaidConfirmation).where(PurchasePaidConfirmation.purchase_id.in_(purchase_ids))
    )).scalars().all()
    for c in conf_rows:
        confirmations_by_purchase.setdefault(c.purchase_id, []).append({
            "id": c.id, "status": c.status,
            "amount_confirmed": str(c.amount_confirmed) if c.amount_confirmed is not None else None,
            "decided_by": c.decided_by, "decided_at": c.decided_at.isoformat() if c.decided_at else None,
            "requested_at": c.requested_at.isoformat() if c.requested_at else None,
            "comment": c.comment,
        })

    payments_by_purchase: dict[int, list] = {}
    pay_rows = (await db.execute(
        select(Payment).where(Payment.purchase_id.in_(purchase_ids))
    )).scalars().all()
    for p in pay_rows:
        payments_by_purchase.setdefault(p.purchase_id, []).append({
            "id": p.id, "bank_payment_id": p.bank_payment_id,
            "amount": str(p.amount) if p.amount is not None else None,
            "payment_source": p.payment_source,
            "confirmed_by_statement": bool(p.confirmed_by_statement),
        })

    events_by_purchase: dict[int, list] = {}
    ev_rows = (await db.execute(
        select(PurchaseEvent).where(
            PurchaseEvent.purchase_id.in_(purchase_ids),
            PurchaseEvent.created_at >= MANUAL_EDITS_SINCE,
        )
    )).scalars().all()
    for e in ev_rows:
        events_by_purchase.setdefault(e.purchase_id, []).append({
            "event_type": e.event_type, "user_id": e.user_id, "data": e.data,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    for p in purchases:
        purchase_no, order_no = parse_loader_key_from_task_comment(p.task_comment)
        inn, contractor_name = contractors.get(p.contractor_id, (None, None))
        out["purchases"].append({
            "purchase_id": p.id, "registry_number": p.registry_number,
            "task_comment": p.task_comment, "purchase_no": purchase_no, "order_no": order_no,
            "inn": inn, "contractor_name": contractor_name, "status": p.status,
            "confirmations": confirmations_by_purchase.get(p.id, []),
            "payments": payments_by_purchase.get(p.id, []),
            "manual_events_since_2026-10-06": events_by_purchase.get(p.id, []),
        })
    return out


def default_snapshot_path(subsidy_id: int) -> Path:
    today = datetime.utcnow().strftime("%Y%m%d")
    return Path(__file__).resolve().parent.parent / "data" / f"fadm_rebuild_snapshot_{subsidy_id}_{today}.json"


def write_snapshot(data: dict, path: Optional[str | Path]) -> Path:
    out_path = Path(path) if path else default_snapshot_path(data["subsidy_id"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Удаление того, что создал загрузчик (п.1 задания) — те же приёмы, что
# delete_target_subsidy (sheet_v2_build.py:635-675, ПРАВИЛО №6), но НЕ трогает
# Subsidy/FeoCategory — только закупки/договоры/плановые позиции загрузчика.
# ---------------------------------------------------------------------------
@dataclass
class RebuildDeleteCounters:
    purchases_deleted: int = 0
    contracts_deleted: int = 0
    contracts_kept_shared: int = 0  # договор delete пропущен — на нём висит ЧУЖАЯ закупка
    plan_items_deleted: int = 0


async def delete_loader_created_data(db: AsyncSession, subsidy: Subsidy) -> RebuildDeleteCounters:
    counters = RebuildDeleteCounters()
    purchase_ids = await _loader_purchase_ids(db, subsidy.id)

    contract_ids = set((await db.execute(
        select(Purchase.contract_id).where(Purchase.id.in_(purchase_ids), Purchase.contract_id.isnot(None))
    )).scalars().all()) if purchase_ids else set()

    # Договор делим с ЧУЖОЙ (не загрузчика) закупкой этой же субсидии —
    # не трогаем его (ПРАВИЛО №6 — Contract.subsidy_id/бюджетные суммы одной
    # закупки не должны зависеть от удаления другой, редкое совпадение, но
    # возможно у разовых без номера/контрагента, см. docstring
    # _finalize_single_contract_amounts).
    safe_contract_ids = set(contract_ids)
    if contract_ids:
        other_purchases = (await db.execute(
            select(Purchase.contract_id).where(
                Purchase.contract_id.in_(contract_ids),
                Purchase.id.notin_(purchase_ids) if purchase_ids else True,
            )
        )).scalars().all()
        if other_purchases:
            counters.contracts_kept_shared = len(set(other_purchases))
            safe_contract_ids -= set(other_purchases)

    if purchase_ids:
        await db.execute(update(BankPayment).where(BankPayment.matched_purchase_id.in_(purchase_ids))
                          .values(matched_purchase_id=None))
    if safe_contract_ids:
        await db.execute(update(BankPayment).where(BankPayment.matched_contract_id.in_(safe_contract_ids))
                          .values(matched_contract_id=None))

    if purchase_ids:
        await db.execute(delete(Payment).where(Payment.purchase_id.in_(purchase_ids)))
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids)))
        await db.execute(delete(Purchase).where(Purchase.id.in_(purchase_ids)))
        counters.purchases_deleted = len(purchase_ids)

    if safe_contract_ids:
        await db.execute(delete(Contract).where(Contract.id.in_(safe_contract_ids)))
        counters.contracts_deleted = len(safe_contract_ids)

    plan_item_ids = await _loader_plan_item_ids(db, subsidy.id)
    if plan_item_ids:
        await db.execute(delete(FeoPlannedItem).where(FeoPlannedItem.id.in_(plan_item_ids)))
        counters.plan_items_deleted = len(plan_item_ids)

    await db.flush()
    return counters


async def root_budget_total(db: AsyncSession, subsidy_id: int) -> Decimal:
    """Σ budget корневых (level=1) категорий — для отчёта п.4 задания
    (сверка с 15 880 100, без создания строк F1/G1 в rebuild-in-place —
    бюджет уже должен стоять на категориях)."""
    rows = (await db.execute(
        select(FeoCategory.budget).where(FeoCategory.subsidy_id == subsidy_id, FeoCategory.parent_id.is_(None))
    )).scalars().all()
    return sum((Decimal(str(b)) for b in rows if b is not None), Decimal("0"))


@dataclass
class RebuildResult:
    subsidy: Subsidy
    counters: BuildCountersV2
    delete_counters: RebuildDeleteCounters
    snapshot: dict
    snapshot_path: Optional[Path]
    root_budget_total: Decimal = Decimal("0")


async def run_rebuild_in_place(db: AsyncSession, *, rows: list[SheetRowV2], target_id: Optional[int],
                                target_name: Optional[str], current_user,
                                snapshot_out: Optional[str] = None) -> RebuildResult:
    subsidy = await find_target_subsidy(db, target_id=target_id, target_name=target_name)

    snapshot = await snapshot_before_rebuild(db, subsidy)
    snapshot_path = write_snapshot(snapshot, snapshot_out)

    delete_counters = await delete_loader_created_data(db, subsidy)

    # Дерево/бюджет/участники/шаблоны НЕ трогаем (решение владельца, п.1) —
    # create_feo_plan_rows=False: бюджет направлений уже стоит на категориях,
    # строки F1/G1 задвоили бы его (п.4 задания).
    counters = await populate_subsidy_v2(db, subsidy, rows, current_user, create_feo_plan_rows=False)

    budget_total = await root_budget_total(db, subsidy.id)

    return RebuildResult(
        subsidy=subsidy, counters=counters, delete_counters=delete_counters,
        snapshot=snapshot, snapshot_path=snapshot_path, root_budget_total=budget_total,
    )
