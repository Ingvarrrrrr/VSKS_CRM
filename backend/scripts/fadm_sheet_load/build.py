"""Создание субсидии «ФАДМ 2026_2» + дерева ФЭО + закупок/плановых позиций
из распарсенной Google-таблицы (parse.py) по правилам владельца (см.
docstring __main__.py). Переиспользует ШТАТНЫЕ сервисы создания закупки —
НЕ второй писатель денег/номеров (ПРАВИЛО №6):
  - insert_purchase_with_items (app.services.purchase_create_core) —
    регистрационный номер, framework_seq, матчинг товара и т.д.;
  - ensure_contract_linked (app.services.contracts_linking) — find-or-create
    Contract по номеру договора (используется и для «один номер = одна
    голова + её заказы делят контракт»);
  - copy_items_to_contract / recalc_purchase_money — как в
    app.services.historical_fact_import.commit;
  - create_auto_planned_item (app.services.plan_autoassign) — единственный
    конструктор авто-плановой позиции ФЭО;
  - find_or_create_contractor (app.services.contractor_resolve) — только
    когда ЧИТАЮЩИЙ превью (match.ContractorLookup) не нашёл ровно одного
    существующего (задание, п.2);
  - copy_feo_tree / copy_access_and_approvers / copy_templates
    (app.services.subsidy_copy) — копия дерева/участников старой субсидии.

ВАЖНО: эта функция (run_build) — ЕДИНСТВЕННОЕ место, которое импортирует
писателей (insert_purchase_with_items и т.п.). __main__.py --match-only
никогда не импортирует этот модуль — см. match_only.py, который использует
только parse.py/match.py (чтение)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
from app.services.contractor_resolve import find_or_create_contractor
from app.services.contracts_linking import ensure_contract_linked
from app.services.contract_items_materialize import copy_items_to_contract
from app.services.item_types import normalize_item_type
from app.services.plan_autoassign import create_auto_planned_item
from app.services.purchase_create_core import insert_purchase_with_items
from app.services.purchase_money_writer import recalc_purchase_money
from app.services.subsidy_copy.copy_tree import copy_feo_tree, copy_access_and_approvers, copy_templates
from app.services.temp_contract_number import generate_temp_contract_number
from app.routers.purchase_budget import _assign_framework_seq

from .parse import (
    KIND_GOODS, MatchUnit, PurchaseGroup, SheetRow, STATUS_LIKELY,
    group_rows, is_monthly_group, iter_match_units, monthly_schedule,
)
from .match import (
    ContractorLookup, Matcher, OldPurchase, find_na_category, find_source_subsidy,
    load_contractor_lookup, load_old_purchases, run_matching,
)
from .advance import EmployeeLookup, load_employee_lookup, resolve_advance_contractor_id

FRAMEWORK_TYPE = "framework_cumulative"
COMMITTED_SINGLE_STATUSES = {"contracted", "ordered", "delivered", "paid"}
# Заказ рамочного допускает ТОЛЬКО эти статусы (committed_amounts.py:49-75,
# FRAMEWORK_COMMITTED_STATUSES) — иначе сумма заказа не попадает в
# «Заключено». Прод-находка 04.10.2026: двойник в статусе 'contracted' отдавал
# его заказу БУКВАЛЬНО (contracted — элемент COMMITTED_SINGLE_STATUSES), хотя
# для заказа это невалидный статус (contracted — статус ГОЛОВЫ/разового
# договора, не заказа внутри него) — см. _resolve_framework_child_status.
FRAMEWORK_CHILD_ALLOWED_STATUSES = {"ordered", "delivered", "paid"}

MONTHLY_START_OVERRIDE: dict[tuple[str, str], int] = {
    ("егорова", "98"): 9,
}


def _kind_item_type(kind: str) -> Optional[str]:
    return normalize_item_type("товар" if kind == KIND_GOODS else "услуга")


def _group_item_type(rows: list[SheetRow]) -> Optional[str]:
    kinds = {r.kind for r in rows}
    if len(kinds) == 1:
        return _kind_item_type(next(iter(kinds)))
    return None


def _monthly_start_month(group: PurchaseGroup) -> int:
    for (substr, pno), start in MONTHLY_START_OVERRIDE.items():
        if substr in group.contractor_norm and group.purchase_no == pno:
            return start
    return 1


@dataclass
class MatchedEntry:
    label: str
    old_registry: Optional[str]
    method: str
    assigned_user_id: Optional[int]


@dataclass
class BuildCounters:
    single_purchases: int = 0
    framework_heads: int = 0
    framework_orders: int = 0
    monthly_purchases: int = 0
    planned_items_likely: int = 0
    planned_items_nice_to_have: int = 0
    contractors_created: int = 0
    contractors_created_names: list = field(default_factory=list)
    contractors_found_existing: int = 0
    matched: list = field(default_factory=list)       # [MatchedEntry]
    unmatched: list = field(default_factory=list)      # [{label, amount}]
    ambiguous: list = field(default_factory=list)      # [{label, amount}]
    old_without_pair: list = field(default_factory=list)  # [{registry_number, contractor, amount, status}]
    need_level_column_missing: bool = False


async def need_level_column_exists(db: AsyncSession) -> bool:
    row = (await db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='feo_planned_items' AND column_name='need_level'"
    ))).first()
    return row is not None


async def find_existing_target_subsidy(db: AsyncSession, name: str, source_id: int) -> Optional[Subsidy]:
    return (await db.execute(
        select(Subsidy).where(Subsidy.name == name, Subsidy.copied_from_id == source_id)
    )).scalars().first()


async def delete_target_subsidy(db: AsyncSession, subsidy: Subsidy) -> None:
    """--replace: Purchase.subsidy_id/Contract.subsidy_id — ondelete=SET NULL
    (не CASCADE) — удаляем закупки и договоры явно ДО удаления субсидии;
    остальное (FeoCategory→FeoPlannedItem, approvers, members, access,
    overrides, responsible persons) — ondelete=CASCADE от subsidies.id."""
    purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()
    if purchase_ids:
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids)))
        await db.execute(delete(Purchase).where(Purchase.id.in_(purchase_ids)))
    await db.execute(delete(Contract).where(Contract.subsidy_id == subsidy.id))
    await db.flush()
    await db.delete(subsidy)
    await db.flush()


async def create_subsidy(db: AsyncSession, source: Subsidy, name: str, budget: Decimal) -> Subsidy:
    from app.services.subsidy_copy._clone import clone_row
    new_subsidy = clone_row(
        source, Subsidy,
        name=name,
        budget=float(budget),
        calculated_budget=None,
        status=source.status,
        is_sandbox=False,
        copied_from_id=source.id,
        approved_by=None,
        approved_at=None,
    )
    db.add(new_subsidy)
    await db.flush()
    return new_subsidy


def _resolve_status(twin: Optional[OldPurchase], default: str) -> str:
    if twin and twin.status in COMMITTED_SINGLE_STATUSES:
        return twin.status
    return default


def _resolve_framework_child_status(twin: Optional[OldPurchase]) -> str:
    """Заказ рамочного — см. FRAMEWORK_CHILD_ALLOWED_STATUSES выше. 'contracted'
    (или что-то ниже по жизненному циклу) у двойника понижается до 'ordered',
    а не копируется как есть."""
    if twin and twin.status in FRAMEWORK_CHILD_ALLOWED_STATUSES:
        return twin.status
    return "ordered"


def _twin_fields(twin: Optional[OldPurchase]) -> dict:
    if not twin:
        return {}
    return {
        "assigned_user_id": twin.assigned_user_id,
        "service_note_to_user_id": twin.service_note_to_user_id,
        "service_note_by": twin.service_note_by,
        "responsible_person": twin.responsible_person,
    }


def _resolve_category(twin: Optional[OldPurchase], category_id_map: dict, na_category_id: Optional[int]) -> Optional[int]:
    if twin and twin.feo_category_id and twin.feo_category_id in category_id_map:
        return category_id_map[twin.feo_category_id]
    return na_category_id


async def _resolve_contractor(db: AsyncSession, group_contractor: str,
                               twin: Optional[OldPurchase], org_id: Optional[int],
                               lookup: ContractorLookup, counters: BuildCounters) -> Optional[int]:
    """Правило владельца (п.2): СНАЧАЛА искать среди ВСЕХ contractors по
    normalize_contractor_name; find_or_create_contractor (писатель, своя,
    более узкая нормализация) — только если lookup не нашёл ровно одного."""
    if twin and twin.contractor_id:
        return twin.contractor_id
    if not group_contractor:
        return None
    existing = lookup.find_one(group_contractor)
    if existing:
        counters.contractors_found_existing += 1
        return existing

    from sqlalchemy import func
    from app.models.contractor import Contractor
    max_id_before = (await db.execute(select(func.coalesce(func.max(Contractor.id), 0)))).scalar()
    cid = await find_or_create_contractor(db, group_contractor, None, org_id=org_id)
    if cid and cid > max_id_before:
        counters.contractors_created += 1
        counters.contractors_created_names.append(group_contractor)
    elif cid:
        counters.contractors_found_existing += 1
    return cid


def _employee_id_for_group(group_contractor: str, employee_lookup: EmployeeLookup) -> Optional[int]:
    """Правило владельца (задача 04.10.2026, --relink п.2а), применяется уже
    В САМОЙ загрузке для будущих прогонов (не только постфактум через
    --relink): контрагент строки/группы — ФИО сотрудника той же организации
    → это авансовый отчёт, не обычная закупка у поставщика. Неоднозначное
    совпадение (>1 сотрудник с таким ФИО) НЕ считается авансовым — та же
    осторожность, что в advance.resolve_assigned_user_id."""
    return employee_lookup.find_one(group_contractor)


def _apply_advance_fields(p: Purchase, employee_id: int, twin: Optional[OldPurchase],
                           employee_lookup: EmployeeLookup) -> None:
    p.purchase_method = "advance"
    p.assigned_user_id = employee_id
    p.reimbursement_user_id = employee_id
    p.contractor_id = resolve_advance_contractor_id(twin, employee_lookup)  # ПРАВИЛО №6 — см. advance.py


def _items_data(rows: list[SheetRow], fpi_id: Optional[int], category_id: Optional[int]) -> list[PurchaseItemCreate]:
    out = []
    for r in rows:
        out.append(PurchaseItemCreate(
            item_name=r.name,
            item_type=_kind_item_type(r.kind),
            quantity=Decimal("1"),
            total_price=r.amount,
            unit_price=r.amount,
            feo_planned_item_id=fpi_id,
            feo_category_id=category_id,
            match_confirmed=True,
        ))
    return out


async def _finalize_contract(db: AsyncSession, p: Purchase, *, is_head: bool = False) -> None:
    p.contract_number = await generate_temp_contract_number(p, db)
    p.contract_number_is_temporary = True
    await ensure_contract_linked(p, db)
    if not is_head:
        await copy_items_to_contract(db, p.id)
        await recalc_purchase_money(db, p)


async def build_single(db: AsyncSession, new_subsidy: Subsidy, group: PurchaseGroup,
                        twin: Optional[OldPurchase], category_id: Optional[int],
                        contractor_id: Optional[int], current_user, counters: BuildCounters,
                        employee_lookup: EmployeeLookup) -> Purchase:
    status = _resolve_status(twin, "contracted")
    fpi = await create_auto_planned_item(
        db,
        SimpleNamespace(item_name=group.first_name or f"Закупка {group.purchase_no}",
                        quantity=None, unit=None, total_price=group.total_amount,
                        unit_price=None, item_type=_group_item_type(group.rows)),
        category_id,
        note="импорт таблицы ФАДМ 2026_2 (разовая закупка)",
    ) if category_id else None

    items_data = _items_data(group.rows, fpi.id if fpi else None, category_id)
    data = PurchaseCreate(
        subsidy_id=new_subsidy.id,
        status=status,
        contractor_id=contractor_id,
        purchase_method="single",
        feo_category_id=category_id,
        item_type=_group_item_type(group.rows),
        subject=group.first_name or f"Закупка {group.purchase_no}",
        items=items_data,
        **_twin_fields(twin),
    )
    p, _items = await insert_purchase_with_items(db, data, current_user, items_data=items_data, total_nmck=group.total_amount)
    # PurchaseCreate НЕ знает поля task_comment (схема его не объявляет —
    # прод-находка 04.10.2026, см. docstring relink_plan.py) — ставим напрямую
    # ORM-атрибутом, иначе метка тихо потеряется, как у всех закупок id=80.
    p.task_comment = f"Таблица: закупка {group.purchase_no}"
    employee_id = _employee_id_for_group(group.contractor, employee_lookup)
    if employee_id:
        _apply_advance_fields(p, employee_id, twin, employee_lookup)
    elif twin is None:
        # Без двойника исполнитель должен остаться ПУСТЫМ (владелец,
        # --relink п.2в) — insert_purchase_with_items иначе молча подставил
        # бы current_user.id (Администратора), см. purchase_create_core.py.
        p.assigned_user_id = None
    await _finalize_contract(db, p)
    counters.single_purchases += 1
    return p


async def build_monthly(db: AsyncSession, new_subsidy: Subsidy, group: PurchaseGroup,
                         twin: Optional[OldPurchase], category_id: Optional[int],
                         contractor_id: Optional[int], current_user, counters: BuildCounters,
                         employee_lookup: EmployeeLookup) -> Purchase:
    sched = monthly_schedule(group)
    status = _resolve_status(twin, "contracted")
    start_month = _monthly_start_month(group)
    end_month = start_month + sched["monthly_payment_count"] - 1
    start_date = date(2026, start_month, 1)
    end_date = date(2026, min(end_month, 12), 1)

    fpi = await create_auto_planned_item(
        db,
        SimpleNamespace(item_name=group.first_name or f"Закупка {group.purchase_no}",
                        quantity=sched["monthly_payment_count"], unit="мес.",
                        total_price=sched["total_amount"], unit_price=sched["monthly_payment_amount"],
                        item_type=_group_item_type(group.rows)),
        category_id,
        note="импорт таблицы ФАДМ 2026_2 (помесячная)",
    ) if category_id else None

    item = PurchaseItemCreate(
        item_name=group.first_name or f"Закупка {group.purchase_no}",
        item_type=_group_item_type(group.rows),
        quantity=Decimal(sched["monthly_payment_count"]),
        unit="мес.",
        unit_price=sched["monthly_payment_amount"],
        total_price=sched["total_amount"],
        feo_planned_item_id=fpi.id if fpi else None,
        feo_category_id=category_id,
        match_confirmed=True,
    )
    items_data = [item]
    data = PurchaseCreate(
        subsidy_id=new_subsidy.id,
        status=status,
        contractor_id=contractor_id,
        purchase_method="single",
        feo_category_id=category_id,
        item_type=_group_item_type(group.rows),
        subject=group.first_name or f"Закупка {group.purchase_no}",
        is_monthly_payment=True,
        monthly_payment_count=sched["monthly_payment_count"],
        monthly_payment_amount=sched["monthly_payment_amount"],
        service_period_type="period",
        service_start_date=start_date,
        service_end_date=end_date,
        items=items_data,
        **_twin_fields(twin),
    )
    p, _items = await insert_purchase_with_items(db, data, current_user, items_data=items_data, total_nmck=sched["total_amount"])
    p.task_comment = f"Таблица: закупка {group.purchase_no} (помесячная)"  # см. комментарий в build_single
    employee_id = _employee_id_for_group(group.contractor, employee_lookup)
    if employee_id:
        _apply_advance_fields(p, employee_id, twin, employee_lookup)
    elif twin is None:
        p.assigned_user_id = None  # см. комментарий в build_single
    await _finalize_contract(db, p)
    counters.monthly_purchases += 1
    return p


async def build_framework(db: AsyncSession, new_subsidy: Subsidy, group: PurchaseGroup,
                           matches: dict, category_id_map: dict, na_category_id: Optional[int],
                           lookup: ContractorLookup, current_user, counters: BuildCounters,
                           employee_lookup: EmployeeLookup) -> Purchase:
    # Правило владельца (правки 3) — «контрагент, сумма пустая»: голова может
    # получить СВОЙ двойник (match.Matcher.match_contractor_only_zero сажает
    # его на ключ head_key) — тогда его исполнитель/направление/контрагент
    # идут на голову И на все заказы БЕЗ собственного двойника (effective_
    # twin ниже). Без такого twin'а голова резолвит контрагента заново, а
    # категория/исполнитель головы — most-common среди заказов (как раньше).
    head_key = (group.contractor_norm, group.purchase_no, None)
    head_match = matches.get(head_key)
    head_twin = head_match.twin if head_match else None

    # Контрагент — ФИО сотрудника (--relink п.2а, применено уже в загрузке)
    # — авансовый, не обычная закупка у поставщика; реального контрагента
    # (если есть) резолвим из twin'а ПОСЛЕ создания (_apply_advance_fields),
    # здесь контрагента вообще не заводим — иначе загрузчик создал бы
    # Contractor по имени сотрудника (прод-находка, см. advance.py).
    group_employee_id = _employee_id_for_group(group.contractor, employee_lookup)
    head_contractor_id = None if group_employee_id else (
        head_twin.contractor_id if (head_twin and head_twin.contractor_id)
        else await _resolve_contractor(db, group.contractor, None, new_subsidy.org_id, lookup, counters)
    )
    head_data = PurchaseCreate(
        subsidy_id=new_subsidy.id,
        status="contracted",
        contractor_id=head_contractor_id,
        purchase_method="single",
        purchase_contract_type=FRAMEWORK_TYPE,
        subject=f"{group.contractor} — рамочный договор (закупка {group.purchase_no})",
        items=[],
    )
    head, _ = await insert_purchase_with_items(db, head_data, current_user, items_data=[], total_nmck=None)
    head.task_comment = f"Таблица: закупка {group.purchase_no} (рамочный договор)"  # см. build_single
    await _finalize_contract(db, head, is_head=True)
    counters.framework_heads += 1

    order_rows: dict[str, list[SheetRow]] = {}
    for r in group.rows:
        order_rows.setdefault(r.order_no or "", []).append(r)

    child_totals = Decimal("0")
    child_categories: Counter = Counter()
    child_assignees: Counter = Counter()

    for order_no, rows in order_rows.items():
        key = (group.contractor_norm, group.purchase_no, order_no)
        match = matches.get(key)
        twin = match.twin if match else None
        # Заказ без своего двойника наследует исполнителя/направление от
        # twin'а ГОЛОВЫ (правило «контрагент, сумма пустая» — правки 3);
        # статус (ниже) НАМЕРЕННО читает только «свой» twin, не фолбэк.
        effective_twin = twin or head_twin

        category_id = _resolve_category(effective_twin, category_id_map, na_category_id)
        contractor_id = None if group_employee_id else (
            effective_twin.contractor_id if (effective_twin and effective_twin.contractor_id) else head_contractor_id
        )
        if category_id:
            child_categories[category_id] += 1
        if effective_twin and effective_twin.assigned_user_id:
            child_assignees[effective_twin.assigned_user_id] += 1

        fpi = await create_auto_planned_item(
            db,
            SimpleNamespace(item_name=rows[0].name if rows else f"Заказ {order_no}",
                            quantity=None, unit=None, total_price=sum((r.amount for r in rows), Decimal("0")),
                            unit_price=None, item_type=_group_item_type(rows)),
            category_id,
            note=f"импорт таблицы ФАДМ 2026_2 (заказ {order_no} рамочного {group.purchase_no})",
        ) if category_id else None

        items_data = _items_data(rows, fpi.id if fpi else None, category_id)
        order_total = sum((r.amount for r in rows), Decimal("0"))
        status = _resolve_framework_child_status(twin)
        child_data = PurchaseCreate(
            subsidy_id=new_subsidy.id,
            status=status,
            contractor_id=contractor_id,
            purchase_method="single",
            purchase_contract_type=FRAMEWORK_TYPE,
            contract_number=head.contract_number,
            feo_category_id=category_id,
            item_type=_group_item_type(rows),
            order_number=order_no or None,
            subject=rows[0].name if rows else f"Заказ {order_no}",
            items=items_data,
            **_twin_fields(effective_twin),
        )
        child, _ = await insert_purchase_with_items(db, child_data, current_user, items_data=items_data, total_nmck=order_total)
        child.task_comment = f"Таблица: закупка {group.purchase_no}, заказ {order_no}"  # см. build_single
        if group_employee_id:
            _apply_advance_fields(child, group_employee_id, effective_twin, employee_lookup)
        elif effective_twin is None:
            child.assigned_user_id = None  # см. build_single — без двойника пусто, не Администратор
        child.parent_purchase_id = head.id
        await ensure_contract_linked(child, db)
        await _assign_framework_seq(child, db)
        await copy_items_to_contract(db, child.id)
        await recalc_purchase_money(db, child)
        child_totals += child.contract_price or order_total
        counters.framework_orders += 1

        _record_match(counters, key, matches, label=f"{group.contractor} №{group.purchase_no}, заказ {order_no}",
                      amount=sum((r.amount for r in rows), Decimal("0")))

    head.contract_price = child_totals
    if head_twin:
        head.feo_category_id = _resolve_category(head_twin, category_id_map, na_category_id)
        _record_match(counters, head_key, matches, label=f"{group.contractor} №{group.purchase_no} (рамочная голова)",
                      amount=Decimal("0"))
    elif child_categories:
        head.feo_category_id = child_categories.most_common(1)[0][0]

    if group_employee_id:
        _apply_advance_fields(head, group_employee_id, head_twin, employee_lookup)
    elif head_twin:
        head.assigned_user_id = head_twin.assigned_user_id  # в т.ч. пусто — не Администратор
    else:
        # Без своего twin'а — most-common среди (уже определённых) заказов,
        # иначе пусто (НЕ Администратор по умолчанию, см. build_single).
        head.assigned_user_id = child_assignees.most_common(1)[0][0] if child_assignees else None
    return head


async def build_planned_only(db: AsyncSession, row: SheetRow, category_id: Optional[int],
                              need_level_ok: bool, counters: BuildCounters) -> FeoPlannedItem:
    is_likely = row.status == STATUS_LIKELY
    label = "Скорее всего понадобится" if is_likely else "Резерв, можно отказаться"
    notes = label if not row.basis else f"{label}. {row.basis}"

    kwargs = dict(
        feo_category_id=category_id,
        name=row.name,
        quantity=Decimal("1"),
        item_type=_kind_item_type(row.kind),
        amount=row.amount,
        is_active=True,
        auto_created=True,
        notes=notes,
    )
    if need_level_ok:
        # модуль появляется вместе с колонкой need_level; без неё не импортируем
        from app.services.plan_need_level import NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE
        kwargs["need_level"] = NEED_LEVEL_LIKELY if is_likely else NEED_LEVEL_NICE_TO_HAVE
    else:
        counters.need_level_column_missing = True

    fpi = FeoPlannedItem(**kwargs)
    db.add(fpi)
    await db.flush()
    if is_likely:
        counters.planned_items_likely += 1
    else:
        counters.planned_items_nice_to_have += 1
    return fpi


def _record_match(counters: BuildCounters, key: tuple, matches: dict, label: str, amount: Decimal) -> None:
    match = matches.get(key)
    if match and match.twin:
        counters.matched.append(MatchedEntry(
            label=label, old_registry=match.twin.registry_number,
            method=match.method or "?", assigned_user_id=match.twin.assigned_user_id,
        ))
    elif match and match.ambiguous:
        counters.ambiguous.append({"label": label, "amount": str(amount)})
    else:
        counters.unmatched.append({"label": label, "amount": str(amount)})


async def run_build(db: AsyncSession, *, rows: list[SheetRow], source_name: str, target_name: str,
                     budget: Decimal, current_user, replace: bool) -> tuple[Subsidy, BuildCounters]:
    source = await find_source_subsidy(db, source_name)

    existing = await find_existing_target_subsidy(db, target_name, source.id)
    if existing:
        if not replace:
            raise ValueError(
                f"Субсидия {target_name!r} (copied_from_id={source.id}) уже существует "
                f"(id={existing.id}) — передайте --replace, чтобы пересоздать."
            )
        await delete_target_subsidy(db, existing)

    new_subsidy = await create_subsidy(db, source, target_name, budget)

    tree = await copy_feo_tree(db, source.id, new_subsidy.id)
    if tree.category_id_map:
        await db.execute(delete(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(tree.category_id_map.values())
        ))
    await copy_access_and_approvers(db, source.id, new_subsidy.id)
    copy_templates(source.id, new_subsidy.id)

    na_category_id = await find_na_category(db, new_subsidy.id)
    need_level_ok = await need_level_column_exists(db)

    old_purchases = await load_old_purchases(db, source.id)
    lookup = await load_contractor_lookup(db)
    employee_lookup = await load_employee_lookup(db, new_subsidy.org_id)
    groups, planned_only_rows = group_rows(rows)
    units = iter_match_units(groups)
    matcher, matches = run_matching(groups, units, old_purchases)

    counters = BuildCounters()

    for group in groups:
        if is_monthly_group(group):
            key = (group.contractor_norm, group.purchase_no, None)
            match = matches.get(key)
            twin = match.twin if match else None
            _record_match(counters, key, matches, label=f"{group.contractor} №{group.purchase_no} (помесячная)",
                          amount=group.total_amount)
            category_id = _resolve_category(twin, tree.category_id_map, na_category_id)
            contractor_id = None if employee_lookup.find_one(group.contractor) else await _resolve_contractor(
                db, group.contractor, twin, new_subsidy.org_id, lookup, counters)
            await build_monthly(db, new_subsidy, group, twin, category_id, contractor_id, current_user, counters, employee_lookup)
            continue

        if len(group.distinct_order_nos) >= 2:
            await build_framework(db, new_subsidy, group, matches, tree.category_id_map, na_category_id, lookup,
                                   current_user, counters, employee_lookup)
            continue

        key = (group.contractor_norm, group.purchase_no, None)
        match = matches.get(key)
        twin = match.twin if match else None
        _record_match(counters, key, matches, label=f"{group.contractor} №{group.purchase_no}",
                      amount=group.total_amount)
        category_id = _resolve_category(twin, tree.category_id_map, na_category_id)
        contractor_id = None if employee_lookup.find_one(group.contractor) else await _resolve_contractor(
            db, group.contractor, twin, new_subsidy.org_id, lookup, counters)
        await build_single(db, new_subsidy, group, twin, category_id, contractor_id, current_user, counters, employee_lookup)

    for row in planned_only_rows:
        await build_planned_only(db, row, na_category_id, need_level_ok, counters)

    counters.old_without_pair = [
        {"registry_number": op.registry_number, "contractor": op.contractor_name,
         "amount": str(op.total), "status": op.status}
        for op in matcher.unused()
    ]

    await db.flush()
    return new_subsidy, counters
