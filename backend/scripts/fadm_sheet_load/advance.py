"""--relink, шаг 2: исполнитель/авансовые/статусы рамочных заказов.

Авансовые (правило владельца, задача 04.10.2026, п.2а): если КОНТРАГЕНТ
строки/группы таблицы — на самом деле сотрудник (ФИО в CSV, КАПСОМ, совпадает
с users.full_name того же org_id, что и субсидия — без регистра, ё→е), это
авансовый отчёт, не обычная закупка у поставщика: деньги возвращают
сотруднику, а не платят контрагенту. Признак — ТРИ поля разом:
  purchase_method = 'advance'
  reimbursement_user_id = сотрудник
  assigned_user_id = сотрудник (он же исполнитель)
Контрагент на шапке закупки (Purchase.contractor_id) у авансового по образцу
живых авансовых на проде (см. запрос `purchase_method='advance'`) бывает И
пустым, И содержать магазин (см. purchase_contractor_display.py — реальный
продавец для реестра авансовых всё равно берётся с чека/позиций, шапка —
опциональный фолбэк): если у ДВОЙНИКА старой закупки есть контрагент И он сам
не совпадает с сотрудником (двойник — не сам себе «продавец Иванов Иванов»),
переносим его контрагента на шапку; иначе — пусто (загрузчик по ошибке завёл
здесь контрагента-сотрудника по имени из таблицы — см. cleanup_employee_
contractors ниже).

Не-авансовые (п.2б/в): исполнитель — ТОЛЬКО от двойника (в т.ч. пустой twin →
пустой исполнитель), НИКОГДА не Администратор по умолчанию. Голова рамочного
пересчитывается по прежнему правилу build.py (свой двойник, иначе самый
частый исполнитель среди (уже исправленных) заказов).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.user import User
from app.services.person_name import normalize_person_name  # ПРАВИЛО №6 — одна точка нормализации

from .match import STATUS_RANK, OldPurchase
from .relink_plan import PlanEntry

_WS_RE = re.compile(r"\s+")


@dataclass
class EmployeeLookup:
    by_name: dict = field(default_factory=dict)  # normalized full_name -> [user_id,...]

    def find_one(self, raw_name: str) -> Optional[int]:
        norm = normalize_person_name(raw_name)
        if not norm:
            return None
        ids = self.by_name.get(norm) or []
        return ids[0] if len(ids) == 1 else None

    def is_employee(self, raw_name: str) -> bool:
        norm = normalize_person_name(raw_name)
        return bool(norm and self.by_name.get(norm))


def resolve_advance_contractor_id(twin: Optional[OldPurchase], lookup: EmployeeLookup) -> Optional[int]:
    """ПРАВИЛО №6 — единственное место решения «какой контрагент остаётся на
    шапке авансовой закупки»: используется и build.py (авансовые уже в самой
    загрузке), и apply_relink_fields ниже (постфактум через --relink) — не
    две копии одной и той же проверки «двойник не сам себе продавец»."""
    if twin and twin.contractor_id and not lookup.is_employee(twin.contractor_name or ""):
        return twin.contractor_id
    return None


async def load_employee_lookup(db: AsyncSession, org_id: Optional[int]) -> EmployeeLookup:
    if not org_id:
        return EmployeeLookup()
    rows = (await db.execute(
        select(User.id, User.full_name).where(User.org_id == org_id)
    )).all()
    lookup = EmployeeLookup()
    for uid, full_name in rows:
        norm = normalize_person_name(full_name)
        if not norm:
            continue
        lookup.by_name.setdefault(norm, []).append(uid)
    return lookup


@dataclass
class AdvanceEntry:
    label: str
    employee_user_id: int
    purchase_id: int
    contractor_id: Optional[int]


@dataclass
class RelinkCounters:
    advance_count: int = 0
    advance_entries: list = field(default_factory=list)       # [AdvanceEntry]
    advance_ambiguous: list = field(default_factory=list)      # [label] — ФИО совпало с >1 сотрудником
    from_twin_count: int = 0
    empty_count: int = 0
    kept_admin_from_twin_count: int = 0
    framework_heads_fixed: int = 0
    framework_statuses_fixed: list = field(default_factory=list)  # [purchase_id]
    unlinked_plan: list = field(default_factory=list)           # план без пары (длины разъехались)
    employees_contractors_deleted: list = field(default_factory=list)   # [(id, name)]
    employees_contractors_kept: list = field(default_factory=list)      # [(id, name, reason)]


def resolve_assigned_user_id(
    entry: PlanEntry, lookup: EmployeeLookup, counters: RelinkCounters,
) -> tuple[Optional[int], bool, Optional[int]]:
    """Возвращает (assigned_user_id, is_advance, contractor_id_override).

    contractor_id_override — None означает «не трогать контрагент» (не
    авансовый путь); для авансового пути — явное значение (может быть тоже
    None — «очистить контрагента»)."""
    employee_id = lookup.find_one(entry.group.contractor)
    if len(lookup.by_name.get(normalize_person_name(entry.group.contractor), [])) > 1:
        counters.advance_ambiguous.append(entry.label)
        employee_id = None  # неоднозначно — НЕ считаем авансовым, правило владельца п.2 требует «ровно сотрудник»

    if employee_id:
        return employee_id, True, resolve_advance_contractor_id(entry.twin, lookup)

    twin = entry.twin
    if twin is None:
        counters.empty_count += 1
        return None, False, None
    counters.from_twin_count += 1
    if twin.assigned_user_id == 1:
        counters.kept_admin_from_twin_count += 1
    return twin.assigned_user_id, False, None


async def apply_relink_fields(
    db: AsyncSession, pairs: list[tuple[PlanEntry, Purchase]],
    lookup: EmployeeLookup, counters: RelinkCounters,
) -> None:
    """Применяет исполнителя/авансовый признак/статус к уже СУЩЕСТВУЮЩИМ
    закупкам (pairs — [(PlanEntry, Purchase)], см. relink_plan.build_creation_plan
    + zip с Purchase.id ASC целевой субсидии). Голова рамочного обрабатывается
    ПОСЛЕДНЕЙ в каждой рамочной группе (после всех её заказов) — её правило
    зависит от уже исправленных заказов."""
    # 1-й проход: все НЕ-головы (single/monthly/framework_order).
    resolved_assigned: dict[int, Optional[int]] = {}  # id(entry) -> итоговый assigned_user_id
    heads: list[tuple[PlanEntry, Purchase]] = []

    for entry, purchase in pairs:
        if entry.role == "framework_head":
            heads.append((entry, purchase))
            continue

        assigned_id, is_advance, contractor_override = resolve_assigned_user_id(entry, lookup, counters)
        resolved_assigned[id(entry)] = assigned_id
        purchase.assigned_user_id = assigned_id

        if is_advance:
            purchase.purchase_method = "advance"
            purchase.reimbursement_user_id = assigned_id
            purchase.contractor_id = contractor_override
            counters.advance_count += 1
            counters.advance_entries.append(AdvanceEntry(
                label=entry.label, employee_user_id=assigned_id,
                purchase_id=purchase.id, contractor_id=contractor_override,
            ))

        if entry.role == "framework_order" and purchase.parent_purchase_id:
            if STATUS_RANK.get(purchase.status or "", 0) <= STATUS_RANK["contracted"]:
                old_status = purchase.status
                purchase.status = "ordered"
                if old_status != "ordered":
                    counters.framework_statuses_fixed.append(purchase.id)

    # 2-й проход: головы рамочных — свой двойник, иначе most-common среди
    # (уже исправленных) заказов ЭТОЙ ЖЕ группы (build.py::build_framework).
    children_by_group: dict[int, list] = {}
    for entry, purchase in pairs:
        if entry.role == "framework_order":
            children_by_group.setdefault(id(entry.group), []).append((entry, purchase))

    for entry, head_purchase in heads:
        employee_id = lookup.find_one(entry.group.contractor)
        if employee_id and not counters_ambiguous(lookup, entry.group.contractor):
            head_purchase.assigned_user_id = employee_id
            head_purchase.purchase_method = "advance"
            head_purchase.reimbursement_user_id = employee_id
            head_purchase.contractor_id = resolve_advance_contractor_id(entry.twin, lookup)
            counters.advance_count += 1
            counters.advance_entries.append(AdvanceEntry(
                label=entry.label, employee_user_id=employee_id,
                purchase_id=head_purchase.id, contractor_id=head_purchase.contractor_id,
            ))
            counters.framework_heads_fixed += 1
            continue

        if entry.twin is not None:
            head_purchase.assigned_user_id = entry.twin.assigned_user_id
            counters.framework_heads_fixed += 1
            continue

        child_assignees: Counter = Counter()
        for child_entry, child_purchase in children_by_group.get(id(entry.group), []):
            val = resolved_assigned.get(id(child_entry))
            if val:
                child_assignees[val] += 1
        head_purchase.assigned_user_id = child_assignees.most_common(1)[0][0] if child_assignees else None
        counters.framework_heads_fixed += 1

    await db.flush()


def counters_ambiguous(lookup: EmployeeLookup, raw_name: str) -> bool:
    return len(lookup.by_name.get(normalize_person_name(raw_name), [])) > 1


async def _contractor_fk_refs(db: AsyncSession, contractor_id: int) -> list[str]:
    """Динамический обход information_schema — ЛЮБАЯ таблица с FK на
    contractors.id, не только те четыре, что нашлись grep'ом на момент
    написания (ПРАВИЛО №6 — не хардкодить список, он устареет при новой FK)."""
    fk_rows = (await db.execute(text(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'contractors' AND ccu.column_name = 'id'
        """
    ))).all()
    used_in: list[str] = []
    for table_name, column_name in fk_rows:
        cnt = (await db.execute(text(
            f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" = :cid'
        ), {"cid": contractor_id})).scalar()
        if cnt:
            used_in.append(f"{table_name}.{column_name} ({cnt})")
    return used_in


async def cleanup_employee_contractors(
    db: AsyncSession, candidate_ids: set[int], counters: RelinkCounters,
) -> None:
    """Контрагенты-сотрудники, которые загрузчик по ошибке создал по имени из
    таблицы (до того, как relink распознал их как авансовые), и которые ПОСЛЕ
    правки (контрагент авансовых обнулён/заменён на реального двойника-
    магазина) больше нигде не используются — удаляются; использованные —
    остаются и идут в отчёт поимённо (задание, п.2а)."""
    for cid in sorted(candidate_ids):
        contractor = await db.get(Contractor, cid)
        if contractor is None:
            continue
        refs = await _contractor_fk_refs(db, cid)
        if refs:
            counters.employees_contractors_kept.append((cid, contractor.name, ", ".join(refs)))
            continue
        counters.employees_contractors_deleted.append((cid, contractor.name))
        await db.delete(contractor)
    if candidate_ids:
        await db.flush()
