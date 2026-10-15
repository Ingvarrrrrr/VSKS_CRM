#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Шаги 2-4 плана «пересборка ФАДМ 2026_2» (15.10.2026,
.claude/plans/sleepy-fluttering-walrus.md) — после того, как закупки листа
GoodsService загружены в субсидию-получатель (ТЕКУЩИЙ загрузчик
sheet_v2_build.py/sheet_v2_parse.py/__main__.py — их дорабатывает ПАРАЛЛЕЛЬНАЯ
сессия режимом --rebuild-in-place, этот модуль их НЕ трогает):

  A/B. Сопоставить закупку листа (получатель) с закупкой старой субсидии
       «ФАДМ_2026» (источник) по ИНН + поставщику + сумме, перенести в
       закупку получателя исполнителя/инициатора/участников/документы/
       подробный состав/комментарии/историю, остановить закупку-источник.
  C.   Закупки источника без пары перенести в получатель как есть (смена
       subsidy_id у закупки/заявки/договора, категория — по пути имён между
       деревьями).
  D.   Перенести подтверждения «Оплачено» по снимку шага 0.

ПРАВИЛО №5 — новый модуль, не трогает sheet_v2_build.py/sheet_v2_parse.py/
__main__.py (их меняет параллельный исполнитель).

ПРАВИЛО №6 — ничего из переноса не считается второй раз, всё взято из уже
существующих сервисов:
  - app.services.purchase_amounts.load_purchase_amounts/effective_amount_expr
    — «эффективная сумма закупки» для пары и для суммы заказа у рамочных
    (голова рамочного через Contract.max_amount, заказ — обычная цепочка по
    стадии на самом заказе, parent_purchase_id у заказа учтён уже этой
    функцией — отдельной «суммы заказа» не считаем).
  - scripts/fadm_sheet_load/files_copy.py::copy_purchase_documents — файлы/
    чеки (идемпотентно по content_hash/фискальной тройке).
  - app/services/subsidy_copy/clone_items.py::clone_purchase_items и условия
    переноса из scripts/fadm_restore_items.py::validate_split — подробный
    состав (та же проверка «сумма совпадает, у получателя позиций меньше»,
    ИМПОРТИРУЕТСЯ отсюда, не копируется).
  - app/services/purchase_stop.py::can_stop_purchase — та же граница стадии,
    что и штатная кнопка «Остановить» (app/routers/purchase_stop.py). Сам
    HTTP-роутер не вызывается (там нужен Request/current_user ради
    уведомлений, которых здесь не должно быть) — пишутся те же три поля
    (stopped_at/stopped_by/stopped_reason), что и роутер, ПОСЛЕ той же
    проверки can_stop_purchase (одна граница, не вторая копия).
  - app/services/subsidy_draft_guard.py::assert_subsidy_approved_for_binding
    — та же проверка «субсидия утверждена», что и PATCH /purchases/{id}
    (app/routers/purchases.py::SUBSIDY_PATCHABLE_STATUSES).
  - scripts/fadm_sheet_load/feo_path_resolve.py::normalize_feo_name/
    names_match — то же сравнение имён категорий, что resolve_feo_path
    использует для листа (НЕ дублируем алгоритм, только сравнение строк).
  - app.routers.purchase_paid_confirmations._walk_to_paid — тот же штатный
    пошаговый переход в 'paid' (contracted→ordered→delivered→paid), что и
    настоящий confirm; вызывается с commit=False/send_notification=False
    снаружи транзакции шага и коммитится один раз в конце ЭТОГО модуля
    (как и сам confirm делает для цепочки из нескольких шагов).

СЛУЖЕБНАЯ ФУНКЦИЯ (нет штатного аналога — объяснение по ПРАВИЛУ №6):
  - `move_purchase_to_subsidy` ниже. PATCH /api/purchases/{id} меняет
    subsidy_id ТОЛЬКО для status in SUBSIDY_PATCHABLE_STATUSES = {'draft',
    'wishes', 'plan_schedule'} (app/routers/purchases.py:1915) — закупки
    источника без пары переносятся «с любой стадии, статус сохраняется»
    (решение владельца, п.2 плана), включая стадии ПОСЛЕ договора, где
    штатный путь намеренно отказывает. Это НЕ вторая копия той проверки —
    она переиспользует ту же assert_subsidy_approved_for_binding (черновик
    субсидии-получателя блокирует перенос и здесь), просто без ограничения
    по статусу закупки (которого в задании для этого шага явно нет), и
    дополнительно пишет PurchaseEvent «перенесена из ФАДМ_2026» — то, что
    PATCH вообще не делает.

СНИМОК ШАГА 0 (--snapshot, JSON) — пишет `sheet_v2_rebuild.py::
snapshot_before_rebuild` (параллельный исполнитель, готово 15.10.2026).
Формат — см. докстринг у `snapshot_before_rebuild` в sheet_v2_rebuild.py
(здесь НЕ копируется второй раз, только напоминание формы верхнего уровня):
    {"subsidy_id": int, "subsidy_name": str, "taken_at": iso,
     "purchases": [
       {"purchase_id", "registry_number", "task_comment",
        "purchase_no", "order_no",   # из parse_loader_key_from_task_comment
        "inn", "contractor_name", "status",
        "confirmations": [{"id","status","amount_confirmed","decided_by",
                            "decided_at","requested_at","comment"}, ...],
        "payments": [{"id","bank_payment_id","amount","payment_source",
                      "confirmed_by_statement"}, ...],
        "manual_events_since_2026-10-06": [...]}, ...]}
Ключ закупки — (inn, purchase_no, order_no); purchase_no/order_no разобраны
ИЗ task_comment самой функцией снимка — `confirmation_entries_from_snapshot`
ниже не парсит их заново, читает уже готовые поля. Для закупки НОВОЙ (после
пересборки) тот же ключ строится `parse_loader_key_from_task_comment`
(ИМПОРТИРУЕТСЯ из sheet_v2_rebuild.py — ПРАВИЛО №6, один разбор
task_comment на весь пакет, не два разных регэкспа)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_comment import PurchaseComment
from app.models.purchase_event import PurchaseEvent, PurchaseMember
from app.models.purchase_item import PurchaseItem
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.purchase_amounts import load_purchase_amounts
from app.services.purchase_stop import can_stop_purchase
from app.services.subsidy_copy._clone import clone_row
from app.services.subsidy_copy.clone_items import clone_purchase_items
from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding

from .feo_path_resolve import FeoTree, load_feo_tree, names_match, normalize_feo_name
from .files_copy import DocCopyCounters, copy_purchase_documents
# ПРАВИЛО №6: маркер закупки загрузчика и разбор её task_comment — ОДНА
# функция/константа на весь пакет, не вторая копия регэкспа здесь.
from .sheet_v2_rebuild import (
    LOADER_TASK_COMMENT_PREFIX,
    parse_loader_key_from_task_comment,
)

# Маркер в тексте/данных переноса (п.1/п.2 плана: "перенесено из ФАДМ_2026,
# РЕЕ-...") — единая формулировка, не собирается по месту использования.
_TRANSFER_NOTE = "перенесено из ФАДМ_2026, РЕЕ-{old_reg}"
_STOP_REASON = "перенесена в ФАДМ 2026_2, РЕЕ-{new_reg}"
_MOVE_NOTE = "перенесена из ФАДМ_2026"

AMOUNT_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# A. Сопоставление закупка-листа <-> закупка-источника — ЧИСТАЯ функция,
#    без БД (тестируется напрямую, см. tests/test_fadm_enrich.py).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PurchaseKey:
    """Ключ сопоставления ОДНОЙ закупки — ИНН контрагента + "поставщик" +
    сумма. Для авансового (purchase_method='advance') "поставщик" =
    сотрудник-получатель возмещения (reimbursement_user_id, см. memory
    project_service_note_roles) — ИНН контрагента у авансового нет (чек
    выписан на организацию, не на сотрудника), inn остаётся пустой строкой у
    ОБЕИХ сторон сравнения, различает их supplier_key."""
    purchase_id: int
    registry_number: str
    inn: str
    supplier_key: str
    amount: Decimal


def build_purchase_key(
    p: Purchase, *, contractor_inn: Optional[str], effective_amount: Optional[Decimal],
) -> PurchaseKey:
    is_advance = getattr(p, "purchase_method", None) == "advance"
    if is_advance:
        inn = ""
        supplier_key = f"employee:{p.reimbursement_user_id}"
    else:
        inn = (contractor_inn or "").strip()
        supplier_key = f"contractor:{p.contractor_id}"
    amount = effective_amount if effective_amount is not None else Decimal("0")
    return PurchaseKey(
        purchase_id=p.id, registry_number=p.registry_number or "",
        inn=inn, supplier_key=supplier_key, amount=amount,
    )


@dataclass
class PairMatch:
    listed_purchase_id: int
    source_purchase_id: int


@dataclass
class AmbiguousMatch:
    listed_purchase_id: int
    candidate_source_ids: list


@dataclass
class MatchResult:
    pairs: list  # [PairMatch]
    ambiguous: list  # [AmbiguousMatch]
    unmatched_source_ids: list  # закупки источника без пары -> шаг C


def find_pairs(listed: list, source: list) -> MatchResult:
    """Один-к-одному по (inn, supplier_key, amount) ТОЧНО (до копейки — Decimal
    сравнивается как есть, вызывающий код обязан квантовать до 2 знаков тем же
    способом, что и остальной проект, см. build_purchase_key). "Только по
    сумме" (scripts/fadm_sheet_load/sheet_v2_docs.py — запасной матч) здесь
    НЕ используется (явный запрет в задании) — несовпадение любого из трёх
    полей = не пара."""
    by_key: dict = {}
    for s in source:
        by_key.setdefault((s.inn, s.supplier_key, s.amount), []).append(s)

    pairs: list[PairMatch] = []
    ambiguous: list[AmbiguousMatch] = []
    used_source_ids: set = set()
    for l in listed:
        key = (l.inn, l.supplier_key, l.amount)
        candidates = [c for c in by_key.get(key, []) if c.purchase_id not in used_source_ids]
        if len(candidates) == 1:
            pairs.append(PairMatch(l.purchase_id, candidates[0].purchase_id))
            used_source_ids.add(candidates[0].purchase_id)
        elif len(candidates) > 1:
            ambiguous.append(AmbiguousMatch(l.purchase_id, [c.purchase_id for c in candidates]))
        # 0 кандидатов — не пара, не ошибка; "лист без пары" не бывает (п.2
        # плана касается источника без пары, не листа).

    # ИСПРАВЛЕНИЕ (найдено прогоном на 7320, 15.10.2026): кандидаты
    # неоднозначной пары НЕ должны попадать в unmatched_source_ids — иначе
    # шаг C молча переносит их как «превышение сверх плана», хотя задание
    # прямым текстом требует «неоднозначно — в отчёт, НЕ сливать» (то есть и
    # не переносить без пары — один из кандидатов МОЖЕТ быть настоящей парой,
    # владелец должен решить сам). used_source_ids расширяется кандидатами
    # неоднозначных записей ТОЛЬКО для этого исключения — без ambiguous они
    # в used_source_ids не попадают.
    ambiguous_candidate_ids = {cid for a in ambiguous for cid in a.candidate_source_ids}
    unmatched_source_ids = [
        s.purchase_id for s in source
        if s.purchase_id not in used_source_ids and s.purchase_id not in ambiguous_candidate_ids
    ]
    return MatchResult(pairs=pairs, ambiguous=ambiguous, unmatched_source_ids=unmatched_source_ids)


# ---------------------------------------------------------------------------
# Категория по пути имён между деревьями (шаг C) — переиспользует СРАВНЕНИЕ
# имён resolve_feo_path (normalize_feo_name/names_match), не весь алгоритм
# (тот заточен под AE/AF/AG листа + 3 фиксированных уровня; здесь — путь
# произвольной длины между двумя деревьями категорий).
# ---------------------------------------------------------------------------
def match_category_by_path(source_tree: FeoTree, target_tree: FeoTree, source_category_id: Optional[int]) -> Optional[int]:
    if source_category_id is None:
        return None
    node = source_tree.by_id.get(source_category_id)
    if node is None:
        return None
    path_names = source_tree.path_to(node)

    matched_id: Optional[int] = None
    candidates = target_tree.roots
    for name in path_names:
        norm = normalize_feo_name(name)
        found = [n for n in candidates if names_match(norm, normalize_feo_name(n.name))]
        if len(found) != 1:
            return None  # нет совпадения ГДЕ-ЛИБО на пути -> "Не определена" у вызывающего
        matched_id = found[0].id
        candidates = target_tree.kids(found[0].id)
    return matched_id


async def find_na_category_id(db: AsyncSession, subsidy_id: int) -> Optional[int]:
    row = (await db.execute(
        select(FeoCategory).where(
            FeoCategory.subsidy_id == subsidy_id, FeoCategory.parent_id.is_(None),
            FeoCategory.name.ilike("не определена"),
        )
    )).scalars().first()
    return row.id if row else None


# ---------------------------------------------------------------------------
# B. Перенос данных пары
# ---------------------------------------------------------------------------
@dataclass
class PairTransferResult:
    old_purchase_id: int
    new_purchase_id: int
    members_added: int = 0
    docs: Optional[DocCopyCounters] = None
    items_transferred: bool = False
    items_skip_reason: str = ""
    comments_copied: int = 0
    events_copied: int = 0
    stopped: bool = False
    stop_skip_reason: str = ""


async def _transfer_pair_people(db: AsyncSession, old: Purchase, new: Purchase) -> int:
    """Исполнитель/инициатор/"на чьё имя"/получатель возмещения — поля
    Purchase напрямую (роли по memory project_service_note_roles:
    assigned_user_id=исполнитель, service_note_by=инициатор,
    service_note_to_user_id="на чьё имя", reimbursement_user_id=авансовый)."""
    for attr in ("assigned_user_id", "service_note_by", "service_note_to_user_id", "reimbursement_user_id"):
        old_value = getattr(old, attr)
        if old_value is not None:
            setattr(new, attr, old_value)

    existing = {m.user_id for m in (await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == new.id)
    )).scalars().all()}
    old_members = (await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == old.id)
    )).scalars().all()
    added = 0
    for m in old_members:
        if m.user_id in existing:
            continue
        db.add(clone_row(m, PurchaseMember, purchase_id=new.id))
        existing.add(m.user_id)
        added += 1
    return added


async def _transfer_pair_items(db: AsyncSession, old: Purchase, new: Purchase) -> tuple[bool, str]:
    """Подробный состав — та же проверка, что scripts/fadm_restore_items.py
    (ПРАВИЛО №6, validate_split импортируется, не копируется), расширенная
    ОДНОЙ дополнительной проверкой, которой там не было (тип товар/услуга
    получателя обязан быть единственным, чтобы перенести его на ВСЕ
    клонированные позиции — validate_split об item_type ничего не знает)."""
    from scripts.fadm_restore_items import validate_split  # lazy: соседний top-level script, не пакет

    old_items = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == old.id))).scalars().all()
    new_items = (await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == new.id))).scalars().all()

    sum_old = sum((it.total_price for it in old_items if it.total_price is not None), Decimal("0"))
    sum_new = sum((it.total_price for it in new_items if it.total_price is not None), Decimal("0"))
    fpi_ids = {it.feo_planned_item_id for it in new_items if it.feo_planned_item_id is not None}
    cat_ids = {it.feo_category_id for it in new_items if it.feo_category_id is not None}
    type_ids = {it.item_type for it in new_items if it.item_type is not None}

    reason = validate_split(
        n_old=len(old_items), n_new=len(new_items), sum_old=sum_old, sum_new=sum_new,
        fpi_ids=fpi_ids, cat_ids=cat_ids,
    )
    if reason:
        return False, reason
    if len(type_ids) > 1:
        return False, f"у позиций получателя несколько РАЗНЫХ типов товар/услуга ({type_ids}) — пропуск"

    overrides: dict = {}
    if fpi_ids:
        overrides["feo_planned_item_id"] = next(iter(fpi_ids))
    if cat_ids:
        overrides["feo_category_id"] = next(iter(cat_ids))
    if type_ids:
        overrides["item_type"] = next(iter(type_ids))

    new_item_ids = [it.id for it in new_items]
    if new_item_ids:
        await db.execute(PurchaseItem.__table__.delete().where(PurchaseItem.id.in_(new_item_ids)))
        await db.flush()
    await clone_purchase_items(db, old.id, new.id, overrides=overrides)
    return True, ""


async def _transfer_pair_comments_events(db: AsyncSession, old: Purchase, new: Purchase) -> tuple[int, int]:
    note = _TRANSFER_NOTE.format(old_reg=old.registry_number or old.id)

    old_comments = (await db.execute(
        select(PurchaseComment).where(PurchaseComment.purchase_id == old.id)
    )).scalars().all()
    n_comments = 0
    for c in old_comments:
        db.add(clone_row(c, PurchaseComment, purchase_id=new.id, text=f"{c.text}\n\n[{note}]"))
        n_comments += 1

    old_events = (await db.execute(
        select(PurchaseEvent).where(PurchaseEvent.purchase_id == old.id)
    )).scalars().all()
    n_events = 0
    for e in old_events:
        merged_data = dict(e.data or {})
        merged_data["fadm_enrich_transfer_note"] = note
        db.add(clone_row(e, PurchaseEvent, purchase_id=new.id, data=merged_data))
        n_events += 1
    return n_comments, n_events


async def transfer_pair(db: AsyncSession, old: Purchase, new: Purchase) -> PairTransferResult:
    """Весь перенос данных одной пары (п.1 решений владельца) — собранные
    куски выше, каждый переиспользует существующий механизм там, где он есть."""
    out = PairTransferResult(old_purchase_id=old.id, new_purchase_id=new.id)

    out.members_added = await _transfer_pair_people(db, old, new)

    counters = DocCopyCounters()
    await copy_purchase_documents(db, old.id, new.id, counters)
    out.docs = counters

    out.items_transferred, out.items_skip_reason = await _transfer_pair_items(db, old, new)

    out.comments_copied, out.events_copied = await _transfer_pair_comments_events(db, old, new)

    can_stop, stop_reason = can_stop_purchase(old)
    if can_stop:
        old.stopped_at = datetime.now(timezone.utc)
        # stopped_by: нет "решающего" пользователя в скрипте-переносе —
        # сознательно NULL (как и stopped_wish_id), причина несёт весь смысл;
        # так же молчит и каскадная остановка из wish_transitions.py.
        old.stopped_reason = _STOP_REASON.format(new_reg=new.registry_number or new.id)
        db.add(PurchaseEvent(
            purchase_id=old.id, event_type="fadm_enrich_stopped",
            data={"reason": old.stopped_reason, "new_purchase_id": new.id},
        ))
        out.stopped = True
    else:
        out.stopped = False
        out.stop_skip_reason = stop_reason or ""

    db.add(PurchaseEvent(
        purchase_id=new.id, event_type="fadm_enrich_pair_transfer",
        data={"note": _TRANSFER_NOTE.format(old_reg=old.registry_number or old.id), "old_purchase_id": old.id},
    ))
    await db.flush()
    return out


async def pair_already_transferred(db: AsyncSession, new_purchase_id: int) -> bool:
    """Идемпотентность (шаг E: повторный --apply = 0 изменений) — метка пишет
    transfer_pair() в PurchaseEvent новой закупки, второй прогон её находит и
    пропускает пару целиком."""
    row = (await db.execute(
        select(PurchaseEvent.id).where(
            PurchaseEvent.purchase_id == new_purchase_id,
            PurchaseEvent.event_type == "fadm_enrich_pair_transfer",
        )
    )).scalars().first()
    return row is not None


# ---------------------------------------------------------------------------
# C. Закупки источника без пары -> перенос в получатель как есть
# ---------------------------------------------------------------------------
@dataclass
class MoveResult:
    source_purchase_id: int
    moved: bool
    category_matched: bool
    reason: str = ""


async def move_purchase_to_subsidy(
    db: AsyncSession, p: Purchase, *, target_subsidy_id: int,
    source_tree: FeoTree, target_tree: FeoTree, na_category_id: Optional[int],
) -> MoveResult:
    """Служебная функция (см. докстринг модуля — нет штатного аналога для
    закупок после стадии договора). Переносит ЦЕЛИКОМ: Purchase.subsidy_id,
    её категорию (по пути имён — match_category_by_path), заявку-источник
    (Wish/WishItem.subsidy_id/feo_category_id), договор (Contract.subsidy_id)
    — ТОЛЬКО если он не общий с другой закупкой источника (иначе перенос
    испортил бы субсидию соседней закупке, которая сама по себе не
    переносится/ещё не перенесена).

    Плановых позиций НЕ создаёт (решение владельца — закупки без пары видны
    как превышение сверх плана листа, п.2)."""
    if p.subsidy_id == target_subsidy_id:
        return MoveResult(p.id, moved=False, category_matched=False, reason="уже перенесена")

    try:
        await assert_subsidy_approved_for_binding(db, target_subsidy_id)
    except Exception as exc:  # HTTPException — субсидия-получатель не утверждена
        return MoveResult(p.id, moved=False, category_matched=False, reason=str(exc))

    old_subsidy_id = p.subsidy_id
    old_category_id = p.feo_category_id

    new_category_id = match_category_by_path(source_tree, target_tree, old_category_id)
    category_matched = new_category_id is not None
    if new_category_id is None:
        new_category_id = na_category_id

    p.subsidy_id = target_subsidy_id
    p.feo_category_id = new_category_id

    # Позиции закупки — та же сопоставленная категория (ПРАВИЛО №6: одна
    # категория на закупку и её строки, как и остальной проект считает это
    # согласованным, см. purchase_mismatch в remap_feo_categories.py — там,
    # где позиции расходятся, это считается аномалией, не нормой).
    await db.execute(
        PurchaseItem.__table__.update()
        .where(PurchaseItem.purchase_id == p.id)
        .values(feo_category_id=new_category_id)
    )

    if p.wish_id:
        wish = await db.get(Wish, p.wish_id)
        if wish is not None:
            wish.subsidy_id = target_subsidy_id
            wish_cat = match_category_by_path(source_tree, target_tree, wish.feo_category_id)
            wish.feo_category_id = wish_cat if wish_cat is not None else na_category_id
            await db.execute(
                WishItem.__table__.update()
                .where(WishItem.wish_id == wish.id)
                .values(feo_category_id=wish.feo_category_id)
            )

    if p.contract_id:
        other_purchase_on_contract = (await db.execute(
            select(Purchase.id).where(
                Purchase.contract_id == p.contract_id, Purchase.id != p.id,
                Purchase.subsidy_id == old_subsidy_id,
            )
        )).scalars().first()
        if other_purchase_on_contract is None:
            contract = await db.get(Contract, p.contract_id)
            if contract is not None:
                contract.subsidy_id = target_subsidy_id

    db.add(PurchaseEvent(
        purchase_id=p.id, event_type="fadm_enrich_moved_no_pair",
        data={"note": _MOVE_NOTE, "from_subsidy_id": old_subsidy_id, "to_subsidy_id": target_subsidy_id,
              "category_matched": category_matched},
    ))
    await db.flush()
    return MoveResult(p.id, moved=True, category_matched=category_matched)


async def purchase_already_moved(db: AsyncSession, source_purchase_id: int, target_subsidy_id: int) -> bool:
    p = await db.get(Purchase, source_purchase_id)
    return p is not None and p.subsidy_id == target_subsidy_id


# ---------------------------------------------------------------------------
# D. Перенос подтверждений «Оплачено»
# ---------------------------------------------------------------------------
@dataclass
class ConfirmationSnapshotEntry:
    inn: str
    purchase_no: str
    order_no: str
    user_id: int
    confirmed_at: datetime
    bank_payment_id: Optional[int]
    amount: Decimal


def load_snapshot(path: str) -> dict:
    """Парсит JSON снимка шага 0 — формат `sheet_v2_rebuild.py::
    snapshot_before_rebuild` целиком (см. докстринг модуля), НЕ только раздел
    подтверждений: оркестратор (sheet_v2_full_rebuild.py) читает отсюда и
    registry_number «было» для таблицы «было РЕЕ -> стало РЕЕ»."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def confirmation_entries_from_snapshot(snapshot: dict) -> list:
    """Разворачивает снимок sheet_v2_rebuild.py (список закупок, у каждой
    список confirmations) в плоский список записей для
    transfer_paid_confirmation — одна строка на ОДНО confirmed-подтверждение.
    Ключ (inn, purchase_no, order_no) берётся ПРЯМО из снимка — тот уже
    разобрал task_comment через parse_loader_key_from_task_comment
    (sheet_v2_rebuild.py), здесь второй раз НЕ парсим (ПРАВИЛО №6).
    pending/rejected подтверждения снимка не переносятся — переносить решено
    только то, что было РЕШЕНО «Оплачено» (план, п.4: «подтверждения
    Оплачено — перенести»)."""
    out: list[ConfirmationSnapshotEntry] = []
    for p in snapshot.get("purchases", []):
        inn = str(p.get("inn") or "").strip()
        purchase_no = str(p.get("purchase_no") or "").strip()
        order_no = str(p.get("order_no") or "").strip()
        bank_payment_id = next(
            (pay.get("bank_payment_id") for pay in p.get("payments", []) if pay.get("bank_payment_id") is not None),
            None,
        )
        for c in p.get("confirmations", []):
            if c.get("status") != "confirmed" or c.get("decided_by") is None or c.get("decided_at") is None:
                continue
            out.append(ConfirmationSnapshotEntry(
                inn=inn, purchase_no=purchase_no, order_no=order_no,
                user_id=int(c["decided_by"]), confirmed_at=datetime.fromisoformat(c["decided_at"]),
                bank_payment_id=bank_payment_id,
                amount=Decimal(str(c["amount_confirmed"])) if c.get("amount_confirmed") is not None else Decimal("0"),
            ))
    return out


@dataclass
class ConfirmationTransferResult:
    key: tuple
    transferred: bool
    reason: str = ""


async def transfer_paid_confirmation(
    db: AsyncSession, entry: ConfirmationSnapshotEntry, new_purchase: Purchase,
) -> ConfirmationTransferResult:
    """Записывает подтверждение «Оплачено» тем же путём, что и настоящее
    подтверждение (app/routers/purchase_paid_confirmations.py::_walk_to_paid —
    штатный пошаговый переход contracted->ordered->delivered->paid), но от
    имени ПРЕЖНЕГО пользователя/датой из снимка и БЕЗ уведомлений
    (commit=False/send_notification=False здесь, как и внутри настоящего
    confirm при многошаговой цепочке — коммитит и шлёт события вызывающий
    оркестратор один раз для всего прогона, см. run_enrich)."""
    from app.routers.purchase_paid_confirmations import _walk_to_paid  # reuse штатного перехода (ПРАВИЛО №6)
    from app.services.purchase_payments import PAID_CONFIRMATION_ELIGIBLE_STATUSES

    key = (entry.inn, entry.purchase_no, entry.order_no)

    existing = (await db.execute(
        select(PurchasePaidConfirmation).where(
            PurchasePaidConfirmation.purchase_id == new_purchase.id,
            PurchasePaidConfirmation.status == "confirmed",
        )
    )).scalars().first()
    if existing is not None:
        return ConfirmationTransferResult(key, transferred=False, reason="уже подтверждена ранее этим прогоном")

    if new_purchase.status == "paid":
        visited = []  # уже оплачена (например, перенос пары дошёл до paid раньше) — только запись подтверждения
    elif new_purchase.status not in PAID_CONFIRMATION_ELIGIBLE_STATUSES:
        return ConfirmationTransferResult(
            key, transferred=False,
            reason=f"закупка в статусе «{new_purchase.status}» — подтверждение недоступно",
        )
    else:
        decider = await db.get(User, entry.user_id)
        if decider is None:
            return ConfirmationTransferResult(key, transferred=False, reason=f"пользователь {entry.user_id} не найден")
        visited, blocked = await _walk_to_paid(db, new_purchase, decider, commit=False, send_notification=False)
        if blocked is not None:
            next_status, detail = blocked
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
            return ConfirmationTransferResult(key, transferred=False, reason=f"блокировка на «{next_status}»: {message}")

    confirmation = PurchasePaidConfirmation(
        purchase_id=new_purchase.id, subsidy_id=new_purchase.subsidy_id,
        requested_at=entry.confirmed_at, amount_confirmed=entry.amount,
        status="confirmed", decided_by=entry.user_id, decided_at=entry.confirmed_at,
        comment="перенесено из ФАДМ_2026 (снимок перед пересборкой)",
    )
    db.add(confirmation)

    if entry.bank_payment_id is not None:
        payment = (await db.execute(
            select(Payment).where(
                Payment.purchase_id == new_purchase.id, Payment.bank_payment_id == entry.bank_payment_id,
            )
        )).scalars().first()
        if payment is None:
            return ConfirmationTransferResult(
                key, transferred=False,
                reason=f"платёжка {entry.bank_payment_id} не привязана к новой закупке — подтверждение не записано",
            )

    await db.flush()
    return ConfirmationTransferResult(key, transferred=True)


# ---------------------------------------------------------------------------
# Оркестрация / отчёт / CLI
# ---------------------------------------------------------------------------
@dataclass
class EnrichReport:
    pairs: list = field(default_factory=list)          # [(PairMatch, PairTransferResult)]
    ambiguous: list = field(default_factory=list)       # [AmbiguousMatch]
    moved_no_pair: list = field(default_factory=list)   # [MoveResult]
    confirmations: list = field(default_factory=list)   # [ConfirmationTransferResult]
    skipped_source_ids: list = field(default_factory=list)
    # «Было РЕЕ -> стало РЕЕ» (п.з оркестратора) — заполняется ТОЛЬКО если
    # run_enrich получил snapshot (сам снимок несёт старый registry_number).
    registry_number_changes: list = field(default_factory=list)  # [{"key","old_reg","new_reg"}]


async def _load_contractor_inns(db: AsyncSession, contractor_ids: set) -> dict:
    if not contractor_ids:
        return {}
    rows = (await db.execute(select(Contractor.id, Contractor.inn).where(Contractor.id.in_(contractor_ids)))).all()
    return {cid: inn for cid, inn in rows}


async def _build_keys(db: AsyncSession, purchases: list) -> list:
    contractor_ids = {p.contractor_id for p in purchases if p.contractor_id}
    inns = await _load_contractor_inns(db, contractor_ids)
    amounts = await load_purchase_amounts(db, [p.id for p in purchases])
    return [
        build_purchase_key(
            p, contractor_inn=inns.get(p.contractor_id),
            effective_amount=amounts[p.id].effective if p.id in amounts else None,
        )
        for p in purchases
    ]


def _listed_purchase_key(p: Purchase, contractor_inn: Optional[str]) -> tuple:
    """(inn, purchase_no, order_no) закупки листа ПОСЛЕ пересборки — тот же
    ключ, что снимок (sheet_v2_rebuild.py) писал ДО удаления, построенный ТЕМ
    ЖЕ parse_loader_key_from_task_comment (ПРАВИЛО №6 — не второй разбор
    task_comment, см. docstring модуля)."""
    purchase_no, order_no = parse_loader_key_from_task_comment(p.task_comment)
    return (str(contractor_inn or "").strip(), str(purchase_no or "").strip(), str(order_no or "").strip())


async def run_enrich(
    db: AsyncSession, *, source_subsidy_id: int, target_subsidy_id: int,
    snapshot: Optional[dict] = None, snapshot_path: Optional[str] = None,
    skip_source_ids: Optional[list] = None,
) -> EnrichReport:
    """snapshot — словарь уже прочитанного/только что снятого снимка
    (sheet_v2_full_rebuild.py передаёт его напрямую из RebuildResult.snapshot
    — ОДНА транзакция, снимок уже в памяти, второй раз файл не открываем).
    snapshot_path — для автономного запуска этого модуля (CLI ниже) — тогда
    снимок читается с диска через load_snapshot. Если задано и то, и то —
    snapshot (в памяти) побеждает."""
    skip_source_ids = set(skip_source_ids or [])
    report = EnrichReport(skipped_source_ids=sorted(skip_source_ids))

    listed = (await db.execute(
        select(Purchase).where(
            Purchase.subsidy_id == target_subsidy_id,
            Purchase.task_comment.ilike(f"{LOADER_TASK_COMMENT_PREFIX}%"),
        )
    )).scalars().all()
    source_conditions = [Purchase.subsidy_id == source_subsidy_id]
    if skip_source_ids:
        source_conditions.append(~Purchase.id.in_(skip_source_ids))
    source = (await db.execute(select(Purchase).where(*source_conditions))).scalars().all()

    listed_keys = await _build_keys(db, listed)
    source_keys = await _build_keys(db, source)
    match = find_pairs(listed_keys, source_keys)
    report.ambiguous = match.ambiguous

    listed_by_id = {p.id: p for p in listed}
    source_by_id = {p.id: p for p in source}
    for pair in match.pairs:
        new_p = listed_by_id[pair.listed_purchase_id]
        old_p = source_by_id[pair.source_purchase_id]
        if await pair_already_transferred(db, new_p.id):
            continue
        result = await transfer_pair(db, old_p, new_p)
        report.pairs.append((pair, result))

    source_tree = await load_feo_tree(db, source_subsidy_id)
    target_tree = await load_feo_tree(db, target_subsidy_id)
    na_category_id = await find_na_category_id(db, target_subsidy_id)
    for sid in match.unmatched_source_ids:
        if await purchase_already_moved(db, sid, target_subsidy_id):
            continue
        p = source_by_id[sid]
        move_result = await move_purchase_to_subsidy(
            db, p, target_subsidy_id=target_subsidy_id,
            source_tree=source_tree, target_tree=target_tree, na_category_id=na_category_id,
        )
        report.moved_no_pair.append(move_result)

    if snapshot is None and snapshot_path:
        snapshot = load_snapshot(snapshot_path)

    if snapshot:
        listed_contractor_ids = {p.contractor_id for p in listed if p.contractor_id}
        listed_inns = await _load_contractor_inns(db, listed_contractor_ids)
        listed_by_key: dict = {}
        for p in listed:
            key = _listed_purchase_key(p, listed_inns.get(p.contractor_id))
            listed_by_key[key] = p

        # п.з оркестратора — «было РЕЕ -> стало РЕЕ»: снимок несёт
        # registry_number ДО удаления, listed_by_key — закупку ПОСЛЕ
        # пересборки с тем же (inn, purchase_no, order_no).
        for p_snap in snapshot.get("purchases", []):
            key = (str(p_snap.get("inn") or "").strip(), str(p_snap.get("purchase_no") or "").strip(),
                   str(p_snap.get("order_no") or "").strip())
            new_p = listed_by_key.get(key)
            report.registry_number_changes.append({
                "key": key, "old_reg": p_snap.get("registry_number"),
                "new_reg": new_p.registry_number if new_p is not None else None,
            })

        for entry in confirmation_entries_from_snapshot(snapshot):
            key = (entry.inn, entry.purchase_no, entry.order_no)
            new_p = listed_by_key.get(key)
            if new_p is None:
                report.confirmations.append(ConfirmationTransferResult(key, transferred=False, reason="закупка листа по ключу не найдена"))
                continue
            report.confirmations.append(await transfer_paid_confirmation(db, entry, new_p))

    return report


def render_report(report: EnrichReport, *, apply: bool) -> str:
    lines = [f"=== sheet_v2_enrich — {'APPLY' if apply else 'DRY-RUN (откат)'} ==="]
    lines.append(f"Пары перенесены: {len(report.pairs)}")
    for pair, result in report.pairs:
        extra = []
        if not result.items_transferred:
            extra.append(f"состав НЕ перенесён: {result.items_skip_reason}")
        if not result.stopped:
            extra.append(f"не остановлена: {result.stop_skip_reason}")
        suffix = f" ({'; '.join(extra)})" if extra else ""
        lines.append(f"  - лист#{pair.listed_purchase_id} <- источник#{pair.source_purchase_id}{suffix}")
    lines.append(f"Неоднозначные пары (не слиты): {len(report.ambiguous)}")
    for a in report.ambiguous:
        lines.append(f"  - лист#{a.listed_purchase_id}: кандидаты источника {a.candidate_source_ids}")
    moved_ok = [m for m in report.moved_no_pair if m.moved]
    moved_fail = [m for m in report.moved_no_pair if not m.moved]
    lines.append(f"Источник без пары — перенесено: {len(moved_ok)}, не перенесено: {len(moved_fail)}")
    for m in moved_fail:
        lines.append(f"  - источник#{m.source_purchase_id}: {m.reason}")
    no_cat = [m for m in moved_ok if not m.category_matched]
    if no_cat:
        lines.append(f"  из них без совпадения категории (ушли в «Не определена»): {len(no_cat)}")
    confirmed = [c for c in report.confirmations if c.transferred]
    not_confirmed = [c for c in report.confirmations if not c.transferred]
    lines.append(f"Подтверждения «Оплачено»: перенесено {len(confirmed)} из {len(report.confirmations)}")
    for c in not_confirmed:
        lines.append(f"  - {c.key}: {c.reason}")
    if report.skipped_source_ids:
        lines.append(f"Исключены из переноса (--skip-source-ids): {report.skipped_source_ids}")
    if report.registry_number_changes:
        lines.append("Было РЕЕ -> стало РЕЕ (закупки листа, пересборка меняет номер):")
        for row in report.registry_number_changes:
            if row["old_reg"] == row["new_reg"]:
                continue
            lines.append(f"  - {row['key']}: {row['old_reg']} -> {row['new_reg']}")
    return "\n".join(lines)


async def _create_backups(db: AsyncSession, target_subsidy_id: int) -> None:
    today = date.today().strftime("%Y%m%d")
    suffix = f"{today}_enrich_{target_subsidy_id}"
    await db.execute(text(
        f"CREATE TABLE IF NOT EXISTS bk_{suffix}_purchases AS "
        "SELECT * FROM purchases WHERE subsidy_id = :sid"
    ), {"sid": target_subsidy_id})
    await db.execute(text(
        f"CREATE TABLE IF NOT EXISTS bk_{suffix}_items AS "
        "SELECT pi.* FROM purchase_items pi JOIN purchases p ON p.id = pi.purchase_id "
        "WHERE p.subsidy_id = :sid"
    ), {"sid": target_subsidy_id})
    await db.execute(text(
        f"CREATE TABLE IF NOT EXISTS bk_{suffix}_confirmations AS "
        "SELECT c.* FROM purchase_paid_confirmations c JOIN purchases p ON p.id = c.purchase_id "
        "WHERE p.subsidy_id = :sid"
    ), {"sid": target_subsidy_id})


async def main_async(args: argparse.Namespace) -> int:
    skip_ids = [int(x) for x in args.skip_source_ids.split(",") if x.strip()] if args.skip_source_ids else []
    async with async_session() as db:
        try:
            if args.apply:
                await _create_backups(db, args.target_subsidy_id)
            report = await run_enrich(
                db, source_subsidy_id=args.source_subsidy_id, target_subsidy_id=args.target_subsidy_id,
                snapshot_path=args.snapshot, skip_source_ids=skip_ids,
            )
        except Exception:
            await db.rollback()
            raise

        print(render_report(report, apply=args.apply))
        if args.apply:
            await db.commit()
        else:
            await db.rollback()
            print("\nБЕЗ --apply: изменения НЕ применены (rollback).")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-subsidy-id", type=int, default=7, help="ФАДМ_2026 (источник)")
    ap.add_argument("--target-subsidy-id", type=int, default=89, help="ФАДМ 2026_2 (получатель)")
    ap.add_argument("--snapshot", default=None, help="JSON снимка шага 0 (подтверждения «Оплачено»)")
    ap.add_argument("--skip-source-ids", default=None, help="id закупок источника, которые уже есть в получателе — через запятую")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    args.apply = bool(args.apply)
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
