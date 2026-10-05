"""Загрузчик v2 — создание субсидии «ФАДМ 2026_2» из листа GoodsService
(sheet_v2_parse.py) по заданию 05.10.2026. Переиспользует ШТАТНЫЕ сервисы
(ПРАВИЛО №6) — те же, что первый загрузчик (build.py):
  - find_or_create_contractor — по ИНН (R), затем по имени (H);
  - ensure_contract_linked — Contract по (номер S, контрагент, дата T);
  - copy_items_to_contract / recalc_purchase_money;
  - find_or_create_contractor / contracts_linking те же, что выше;
  - get_or_create_unallocated (app.services.feo_unallocated) — категория
    «Не определена», НЕ второй find-or-create (первый загрузчик был вынужден
    завести свою find_na_category под другое дерево — здесь дерево новое,
    используем общий штатный хелпер);
  - copy_feo_tree / copy_access_and_approvers / copy_templates — копия
    дерева/участников старой субсидии «ФАДМ_2026»;
  - app.services.payment_target.build_groups + app.services.payment_lookup.attach
    — привязка платежа к закупке (единственный писатель Payment);
  - scripts/fadm_sheet_load/advance.py::EmployeeLookup/load_employee_lookup —
    тот же поиск сотрудника по ФИО, что первый загрузчик, не копия.

Уведомления при первичной загрузке не шлём (решение владельца) — см.
_silence_paid_confirmation_notifications ниже: no-op подмена ОДНОЙ функции
на время run_build_v2, без правки app/notifications.py.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
from app.services.contractor_resolve import find_or_create_contractor
from app.services.contracts_linking import ensure_contract_linked
from app.services.contract_items_materialize import copy_items_to_contract
from app.services.feo_unallocated import get_or_create_unallocated
from app.services.item_types import normalize_item_type
from app.services.purchase_create_core import insert_purchase_with_items
from app.services.purchase_money_writer import recalc_purchase_money
from app.services.subsidy_copy.copy_tree import copy_feo_tree, copy_access_and_approvers, copy_templates
from app.services.temp_contract_number import generate_temp_contract_number
from app.routers.purchase_budget import _assign_framework_seq

from .advance import EmployeeLookup, load_employee_lookup
from .match import find_source_subsidy
from .sheet_v2_parse import (
    PurchaseGroupV2, SheetRowV2, group_rows_v2, need_level_for, resolve_status, valid_inn,
)
from .sheet_v2_payments import PendingPayment, attach_pending_payments

FRAMEWORK_TYPE = "framework_cumulative"
# Строка 1 листа GoodsService: E1=15 880 100 (план), F1=4 380 000 (товары),
# G1=11 500 100 (услуги) — целевые числа карточки «Бюджет (ФЭО)» (владелец,
# доп. задание 05.10.2026), см. комментарий у места использования ниже.
GOODSSERVICE_PLAN_GOODS = Decimal("4380000.00")
GOODSSERVICE_PLAN_SERVICES = Decimal("11500100.00")

# Значения колонки S «Номер договора», которые на самом деле означают
# «номер неизвестен» (проверено на реальном листе GoodsService — «Нет
# данных» встречается 37 раз У РАЗНЫХ рамочных голов разных ИНН; буквальное
# использование этой строки как Contract.number сталкивало бы их все в один
# Contract — ensure_contract_linked ищет ПО ВСЕЙ БД при contractor_id/date
# пустых, см. app/services/contracts_linking.py). Такой голове присваивается
# технический номер (generate_temp_contract_number — тот же, что у первого
# загрузчика для голов без номера).
PLACEHOLDER_CONTRACT_NUMBERS = {"", "нет данных", "без номера", "не указан", "n/a"}


def _real_contract_number(raw: str) -> Optional[str]:
    v = (raw or "").strip()
    return None if v.lower() in PLACEHOLDER_CONTRACT_NUMBERS else v


# ---------------------------------------------------------------------------
# Уведомления «Оплачено» — отключаем на время загрузки (решение владельца,
# п. задания «Платежи»). Подмена ОДНОЙ функции в её модуле, восстановление в
# finally — не второй код-путь, просто временно отключённый побочный эффект.
# ---------------------------------------------------------------------------
@contextmanager
def _silence_paid_confirmation_notifications():
    import app.notifications as notif_mod

    name = "notify_purchase_paid_confirmation_requested"
    original = getattr(notif_mod, name, None)
    if original is None:
        yield
        return

    async def _noop(*args, **kwargs):
        return None

    setattr(notif_mod, name, _noop)
    try:
        yield
    finally:
        setattr(notif_mod, name, original)


# ---------------------------------------------------------------------------
# Счётчики / отчёт
# ---------------------------------------------------------------------------
@dataclass
class BuildCountersV2:
    single_purchases: int = 0
    framework_heads: int = 0
    framework_orders: int = 0
    advance_purchases: int = 0
    contractors_created: int = 0
    contractors_found_existing: int = 0
    feo_matched: int = 0
    feo_unmatched: list = field(default_factory=list)   # [{label, ae, af}]
    payments_attached: int = 0
    payments_attached_amount: Decimal = Decimal("0")
    payments_not_found: list = field(default_factory=list)  # [{doc_no, inn, amount, reason}]
    payments_u_mismatch: list = field(default_factory=list)  # [{label, note}] — контроль U (не фильтр)
    contract_filled_from_payment: int = 0  # номер/дата договора разобраны из назначения платежа (S/T были «Нет данных»)
    inn_missing: int = 0  # строки без настоящего ИНН (R = заглушка/пусто)
    advance_entries: list = field(default_factory=list)  # [{label, employee_name, employee_id, contractor_from_source}]
    executor_from_source: int = 0  # сколько закупок получили исполнителя от двойника в старой ФАДМ_2026
    by_status_amount: dict = field(default_factory=dict)
    by_kind_amount: dict = field(default_factory=dict)


def _kind_item_type(kind: str) -> Optional[str]:
    return normalize_item_type("товар" if kind == "goods" else "услуга")


def _group_item_type(rows: list[SheetRowV2]) -> Optional[str]:
    kinds = {r.item_kind for r in rows}
    return _kind_item_type(next(iter(kinds))) if len(kinds) == 1 else None


# ---------------------------------------------------------------------------
# ФЭО-категории по имени (AE/AF) — построено один раз на субсидию
# ---------------------------------------------------------------------------
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[.)]\s*")


def _norm_category_name(raw: str) -> str:
    """Нормализация имени направления для сравнения AE/AF (строка) с именем
    категории в дереве ФЭО: дерево хранит имена БЕЗ номера («Техническое
    оснащение деятельности штаба»), AE/AF в листе — С номером пункта
    («1. Техническое оснащение деятельности штаба») — прод-находка
    dry-run 05.10.2026 (0 реальных совпадений без этой нормализации, все 178
    строк уходили в «Не определена»). Снимаем ведущий «N.»/«N)» И пробелы."""
    v = (raw or "").strip().lower()
    return _LEADING_NUMBER_RE.sub("", v).strip()


class FeoNameLookup:
    def __init__(self) -> None:
        self.by_name: dict[str, int] = {}

    def add(self, name: str, category_id: int, level: int) -> None:
        norm = _norm_category_name(name)
        if not norm:
            return
        # Глубже — приоритетнее (AF точнее AE); при равной глубине — первый найденный.
        prev = self._level.get(norm, -1) if hasattr(self, "_level") else -1
        if not hasattr(self, "_level"):
            self._level = {}
        if norm not in self.by_name or level > self._level.get(norm, -1):
            self.by_name[norm] = category_id
            self._level[norm] = level

    def find(self, *names: str) -> Optional[int]:
        for name in names:
            norm = _norm_category_name(name)
            if norm and norm in self.by_name:
                return self.by_name[norm]
        return None


async def _load_feo_lookup(db: AsyncSession, subsidy_id: int) -> FeoNameLookup:
    rows = (await db.execute(
        select(FeoCategory.name, FeoCategory.id, FeoCategory.level)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )).all()
    lookup = FeoNameLookup()
    for name, cid, level in rows:
        lookup.add(name, cid, level or 0)
    return lookup


def _resolve_feo_category(row: SheetRowV2, lookup: FeoNameLookup, na_category_id: Optional[int],
                           counters: BuildCountersV2, label: str) -> Optional[int]:
    cid = lookup.find(row.feo_type, row.feo_direction, row.feo_appendix_direction)
    if cid:
        counters.feo_matched += 1
        return cid
    if row.feo_type or row.feo_direction:
        counters.feo_unmatched.append({"label": label, "ae": row.feo_direction, "af": row.feo_type})
    return na_category_id


# ---------------------------------------------------------------------------
# Контрагент / сотрудник
# ---------------------------------------------------------------------------
async def _resolve_contractor_id(db: AsyncSession, row: SheetRowV2, org_id: Optional[int],
                                  counters: BuildCountersV2) -> Optional[int]:
    from sqlalchemy import func
    inn = valid_inn(row.inn)
    if not inn:
        counters.inn_missing += 1
    max_id_before = (await db.execute(select(func.coalesce(func.max(Contractor.id), 0)))).scalar()
    cid = await find_or_create_contractor(db, row.contractor, inn, org_id=org_id)
    if cid and cid > max_id_before:
        counters.contractors_created += 1
    elif cid:
        counters.contractors_found_existing += 1
    return cid


async def _load_source_executors_by_contractor(db: AsyncSession, source_id: int) -> dict[int, tuple]:
    """contractor_id → (assigned_user_id, responsible_person), самый частый
    исполнитель этого контрагента в СТАРОЙ ФАДМ_2026 — владелец, уточнение
    05.10.2026, п.5: «исполнители ... из старой ФАДМ_2026». contractor_id
    ОБЩИЙ между субсидиями (find_or_create_contractor не делит по subsidy_id,
    см. app/services/contractor_resolve.py) — тот же ИНН в новой закупке даёт
    ТОТ ЖЕ Contractor.id, что и в старой, поэтому матч по contractor_id —
    настоящий twin, не угадывание. Полного переноса файлов/чеков (files_copy.py
    первого загрузчика) здесь НЕТ — он работан по id ЗАКУПКИ-двойника, которого
    у v2 нет построчного сопоставления; см. отчёт."""
    rows = (await db.execute(
        select(Purchase.contractor_id, Purchase.assigned_user_id, Purchase.responsible_person).where(
            Purchase.subsidy_id == source_id, Purchase.contractor_id.isnot(None),
        )
    )).all()
    counts: dict[tuple, int] = {}
    for cid, uid, resp in rows:
        if uid is None and not resp:
            continue
        key = (cid, uid, resp)
        counts[key] = counts.get(key, 0) + 1
    best: dict[int, tuple] = {}
    best_count: dict[int, int] = {}
    for (cid, uid, resp), cnt in counts.items():
        if cnt > best_count.get(cid, 0):
            best[cid] = (uid, resp)
            best_count[cid] = cnt
    return best


async def _load_source_advance_contractors(db: AsyncSession, source_id: int) -> dict[int, int]:
    """employee_id → контрагент (магазин), чаще всего встречавшийся на его
    авансовых закупках в СТАРОЙ субсидии ФАДМ_2026 — владелец, уточнение
    05.10.2026: «контрагент — магазин из старой ФАДМ, если был». Упрощённая
    версия twin-поиска первого загрузчика (match.py) — там двойник ищется
    построчно по контрагенту+сумме; здесь, раз у v2 нет построчного
    сопоставления со старой субсидией вообще, берём САМЫЙ ЧАСТЫЙ контрагент
    того же сотрудника в источнике (не выдумываем — это реальный исторический
    магазин этого человека, не угадывание)."""
    rows = (await db.execute(
        select(Purchase.reimbursement_user_id, Purchase.contractor_id).where(
            Purchase.subsidy_id == source_id,
            Purchase.purchase_method == "advance",
            Purchase.reimbursement_user_id.isnot(None),
            Purchase.contractor_id.isnot(None),
        )
    )).all()
    counts: dict[tuple[int, int], int] = {}
    for uid, cid in rows:
        counts[(uid, cid)] = counts.get((uid, cid), 0) + 1
    best: dict[int, int] = {}
    best_count: dict[int, int] = {}
    for (uid, cid), cnt in counts.items():
        if cnt > best_count.get(uid, 0):
            best[uid], best_count[uid] = cid, cnt
    return best


def _apply_source_executor(p: Purchase, contractor_id: Optional[int], source_executors: dict[int, tuple],
                            counters: BuildCountersV2) -> None:
    """Исполнитель/ответственный — от двойника в старой ФАДМ_2026 по тому же
    контрагенту (см. _load_source_executors_by_contractor). Только если
    закупка ещё НЕ авансовая (там исполнитель — сам сотрудник, см.
    _apply_advance_fields) и сама ещё без исполнителя (insert_purchase_with_items
    иначе мог подставить current_user по умолчанию — не перетираем решение
    этого хелпера возможной более поздней подстановкой: вызывать ДО любых
    других присвоений assigned_user_id)."""
    if not contractor_id or p.purchase_method == "advance":
        return
    hit = source_executors.get(contractor_id)
    if not hit:
        return
    uid, resp = hit
    if uid:
        p.assigned_user_id = uid
    if resp and not p.responsible_person:
        p.responsible_person = resp
    counters.executor_from_source += 1


def _apply_advance_fields(p: Purchase, employee_id: int, *, counters: BuildCountersV2, label: str,
                           employee_name: str, source_advance_contractors: dict[int, int]) -> None:
    p.purchase_method = "advance"
    p.assigned_user_id = employee_id
    p.reimbursement_user_id = employee_id
    # Контрагент авансовой закупки — НЕ сам сотрудник (ПРАВИЛО №6, advance.py);
    # если у этого сотрудника в старой ФАДМ_2026 уже встречался магазин —
    # переносим его (владелец, уточнение 05.10.2026), иначе пусто.
    p.contractor_id = source_advance_contractors.get(employee_id)
    counters.advance_purchases += 1
    counters.advance_entries.append({
        "label": label, "employee_name": employee_name, "employee_id": employee_id,
        "contractor_from_source": p.contractor_id,
    })


def _items_data(rows: list[SheetRowV2], category_id: Optional[int]) -> list[PurchaseItemCreate]:
    out = []
    for r in rows:
        out.append(PurchaseItemCreate(
            item_name=r.item_name or r.subject,
            item_type=_kind_item_type(r.item_kind),
            quantity=r.qty if r.qty else Decimal("1"),
            unit=r.unit or None,
            total_price=r.amount,
            unit_price=r.final_price or r.plan_price or None,
            feo_category_id=category_id,
            match_confirmed=True,
        ))
    return out


# Привязка платежей — вынесена в sheet_v2_payments.py (ПРАВИЛО №5), см. импорт
# PendingPayment/attach_pending_payments выше.


# ---------------------------------------------------------------------------
# Создание закупок
# ---------------------------------------------------------------------------
async def _finalize_contract(db: AsyncSession, p: Purchase, *, is_head: bool = False) -> None:
    await ensure_contract_linked(p, db)
    if not is_head:
        await copy_items_to_contract(db, p.id)
        await recalc_purchase_money(db, p)


async def build_single(db: AsyncSession, subsidy: Subsidy, group: PurchaseGroupV2,
                        category_id: Optional[int], contractor_id: Optional[int],
                        employee_id: Optional[int], current_user, counters: BuildCountersV2,
                        pending_payments: list, source_advance_contractors: dict[int, int],
                        source_executors: dict[int, tuple]) -> Purchase:
    rows = group.rows
    main = rows[0]
    status = resolve_status(main) if len(rows) == 1 else max(
        (resolve_status(r) for r in rows), key=lambda s: ["draft", "work_in_progress", "contracted", "ordered", "delivered"].index(s)
    )
    items_data = _items_data(rows, category_id)
    real_number = _real_contract_number(main.contract_number)
    data = PurchaseCreate(
        subsidy_id=subsidy.id,
        status=status,
        contractor_id=None if employee_id else contractor_id,
        purchase_method="advance" if employee_id else "single",
        feo_category_id=category_id,
        item_type=_group_item_type(rows),
        subject=group.first_name,
        contract_number=real_number,
        contract_date=main.contract_date if real_number else None,
        items=items_data,
    )
    p, _items = await insert_purchase_with_items(db, data, current_user, items_data=items_data, total_nmck=group.total_amount)
    p.task_comment = f"Таблица GoodsService: закупка {group.purchase_no} (ИНН {group.inn})"
    label = f"{group.contractor} №{group.purchase_no}"
    if employee_id:
        _apply_advance_fields(p, employee_id, counters=counters, label=label,
                              employee_name=group.contractor, source_advance_contractors=source_advance_contractors)
    else:
        _apply_source_executor(p, contractor_id, source_executors, counters)
    if not real_number:
        p.contract_number = await generate_temp_contract_number(p, db)
        p.contract_number_is_temporary = True
    await _finalize_contract(db, p)
    counters.single_purchases += 1
    for r in rows:
        pending_payments.append(PendingPayment(purchase_id=p.id, row=r, label=label))
    return p


async def build_framework(db: AsyncSession, subsidy: Subsidy, group: PurchaseGroupV2,
                           feo_lookup: FeoNameLookup, na_category_id: Optional[int],
                           employee_lookup: EmployeeLookup, org_id: Optional[int],
                           current_user, counters: BuildCountersV2, pending_payments: list,
                           source_advance_contractors: dict[int, int],
                           source_executors: dict[int, tuple]) -> Purchase:
    group_employee_id = employee_lookup.find_one(group.contractor)
    head_contractor_id = None if group_employee_id else await _resolve_contractor_id(db, SheetRowV2(
        row=0, event="", contract_kind=group.contract_kind, purchase_no=group.purchase_no,
        order_no="", subject="", item_name="", contractor=group.contractor, qty=Decimal("0"),
        unit="", plan_price=Decimal("0"), plan_sum=Decimal("0"), confirmed=True,
        final_price=Decimal("0"), final_sum=Decimal("0"), sum_to_pay_delivery=Decimal("0"),
        sum_to_pay_contract=Decimal("0"), inn=group.inn, contract_number="", contract_date=None,
        payment_numbers=[], payment_purpose="", payment_date=None, goods_services="",
        feo_direction="", feo_type="", feo_appendix_direction="", purchase_done=False,
        contract_signed=False, ordered=False, delivered=False, paid=False,
    ), org_id, counters)

    raw_contract_number = group.limit_row.contract_number if group.limit_row else (group.rows[0].contract_number if group.rows else "")
    head_contract_date = group.limit_row.contract_date if group.limit_row else (group.rows[0].contract_date if group.rows else None)
    head_contract_number = _real_contract_number(raw_contract_number)

    head_data = PurchaseCreate(
        subsidy_id=subsidy.id,
        status="contracted",
        contractor_id=head_contractor_id,
        purchase_method="single",
        purchase_contract_type=FRAMEWORK_TYPE,
        subject=f"{group.contractor} — рамочный договор (закупка {group.purchase_no})",
        contract_number=head_contract_number,
        contract_date=head_contract_date if head_contract_number else None,
        items=[],
    )
    head, _ = await insert_purchase_with_items(db, head_data, current_user, items_data=[], total_nmck=None)
    head.task_comment = f"Таблица GoodsService: закупка {group.purchase_no} (рамочный договор, ИНН {group.inn})"
    if not group_employee_id:
        _apply_source_executor(head, head_contractor_id, source_executors, counters)
    if not head_contract_number:
        head.contract_number = await generate_temp_contract_number(head, db)
        head.contract_number_is_temporary = True
    await _finalize_contract(db, head, is_head=True)
    if group.limit_amount:
        contract = await db.get(Contract, head.contract_id)
        if contract:
            contract.max_amount = group.limit_amount
    counters.framework_heads += 1

    order_rows: dict[str, list[SheetRowV2]] = {}
    for r in group.rows:
        order_rows.setdefault(r.order_no, []).append(r)

    child_totals = Decimal("0")
    for order_no, rows in order_rows.items():
        main = rows[0]
        category_id = _resolve_feo_category(main, feo_lookup, na_category_id, counters,
                                             label=f"{group.contractor} №{group.purchase_no}, заказ {order_no}")
        contractor_id = None if group_employee_id else await _resolve_contractor_id(db, main, org_id, counters)
        items_data = _items_data(rows, category_id)
        order_total = sum((r.amount for r in rows), Decimal("0"))
        status = resolve_status(main)
        if status == "draft":
            status = "ordered"  # заказ рамочного не может быть draft — минимум ordered при AT (задание)

        child_data = PurchaseCreate(
            subsidy_id=subsidy.id,
            status=status,
            contractor_id=contractor_id,
            purchase_method="advance" if group_employee_id else "single",
            purchase_contract_type=FRAMEWORK_TYPE,
            contract_number=head.contract_number,
            contract_date=head.contract_date,
            feo_category_id=category_id,
            item_type=_group_item_type(rows),
            order_number=order_no or None,
            subject=main.subject or main.item_name or f"Заказ {order_no}",
            items=items_data,
        )
        child, _ = await insert_purchase_with_items(db, child_data, current_user, items_data=items_data, total_nmck=order_total)
        child.task_comment = f"Таблица GoodsService: закупка {group.purchase_no}, заказ {order_no}"
        if group_employee_id:
            _apply_advance_fields(child, group_employee_id, counters=counters,
                                  label=f"{group.contractor} №{group.purchase_no}, заказ {order_no}",
                                  employee_name=group.contractor, source_advance_contractors=source_advance_contractors)
        else:
            _apply_source_executor(child, contractor_id, source_executors, counters)
        child.parent_purchase_id = head.id
        await ensure_contract_linked(child, db)
        await _assign_framework_seq(child, db)
        await copy_items_to_contract(db, child.id)
        await recalc_purchase_money(db, child)
        child_totals += child.contract_price or order_total
        counters.framework_orders += 1
        label = f"{group.contractor} №{group.purchase_no}, заказ {order_no}"
        for r in rows:
            pending_payments.append(PendingPayment(purchase_id=child.id, row=r, label=label))

    head.contract_price = child_totals
    return head


# ---------------------------------------------------------------------------
# Создание/удаление субсидии
# ---------------------------------------------------------------------------
async def find_existing_target_subsidy(db: AsyncSession, name: str, source_id: int) -> Optional[Subsidy]:
    return (await db.execute(
        select(Subsidy).where(Subsidy.name == name, Subsidy.copied_from_id == source_id)
    )).scalars().first()


async def delete_target_subsidy(db: AsyncSession, subsidy: Subsidy) -> None:
    """--replace: см. docstring build.py::delete_target_subsidy — то же самое,
    расширено на bank_payment-привязки ЭТОЙ субсидии. Строки bank_payments
    (сама выписка) НЕ удаляются — только Payment (разноска)."""
    from app.models.payment import Payment
    from app.models.bank_statement import BankPayment
    purchase_ids = (await db.execute(
        select(Purchase.id).where(Purchase.subsidy_id == subsidy.id)
    )).scalars().all()
    contract_ids = (await db.execute(
        select(Contract.id).where(Contract.subsidy_id == subsidy.id)
    )).scalars().all()
    # Строки выписки остаются, но их «легаси»-привязки (авто-матч при загрузке
    # выписки) к удаляемым договорам/закупкам надо снять, иначе FK не даст удалить.
    if contract_ids:
        await db.execute(update(BankPayment).where(BankPayment.matched_contract_id.in_(contract_ids))
                         .values(matched_contract_id=None))
    if purchase_ids:
        await db.execute(update(BankPayment).where(BankPayment.matched_purchase_id.in_(purchase_ids))
                         .values(matched_purchase_id=None))
    if purchase_ids:
        await db.execute(delete(Payment).where(Payment.purchase_id.in_(purchase_ids)))
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids)))
        await db.execute(delete(Purchase).where(Purchase.id.in_(purchase_ids)))
    await db.execute(delete(Contract).where(Contract.subsidy_id == subsidy.id))
    category_ids = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy.id)
    )).scalars().all()
    if category_ids:
        # Явные bulk DELETE, а не полагание на ON DELETE CASCADE в БД: если
        # эти FeoCategory уже в identity map сессии (этим же прогоном только
        # что созданы — copy_feo_tree), ORM при db.delete(subsidy) сначала
        # пытается NULL-ить их subsidy_id (session-level cascade), что падает
        # на NOT NULL раньше, чем дойдёт до реального DELETE (прод-находка,
        # тест test_fadm_goodsservice_load.py::test_goodsservice_loader_replace).
        await db.execute(delete(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_(category_ids)))
        await db.execute(delete(FeoCategory).where(FeoCategory.id.in_(category_ids)))
    await db.flush()
    await db.delete(subsidy)
    await db.flush()


async def create_subsidy(db: AsyncSession, source: Subsidy, name: str, budget: Decimal,
                          agreement_number: str) -> Subsidy:
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
        agreement_number=agreement_number,
    )
    db.add(new_subsidy)
    await db.flush()
    return new_subsidy


async def run_build_v2(db: AsyncSession, *, rows: list[SheetRowV2], source_name: str, target_name: str,
                        budget: Decimal, agreement_number: str, current_user, replace: bool) -> tuple[Subsidy, BuildCountersV2]:
    source = await find_source_subsidy(db, source_name)

    existing = await find_existing_target_subsidy(db, target_name, source.id)
    if existing:
        if not replace:
            raise ValueError(
                f"Субсидия {target_name!r} (copied_from_id={source.id}) уже существует "
                f"(id={existing.id}) — передайте --replace."
            )
        await delete_target_subsidy(db, existing)

    new_subsidy = await create_subsidy(db, source, target_name, budget, agreement_number)

    tree = await copy_feo_tree(db, source.id, new_subsidy.id)
    if tree.category_id_map:
        await db.execute(delete(FeoPlannedItem).where(
            FeoPlannedItem.feo_category_id.in_(tree.category_id_map.values())
        ))
        # Владелец, доп. задание 05.10.2026 («Бюджет (ФЭО)» карточка): clone_row
        # копирует FeoCategory.budget ТОЖЕ — компьютинг бюджета
        # (app/services/subsidy_budget.py::compute_budget_map) берёт явный
        # budget узла КАК ЕСТЬ, не складывая ничего снизу, и
        # app/services/feo_plan_tree.py::_feo_by_kind кладёт такой явный budget
        # ЦЕЛИКОМ в «без типа» — отсюда карточка новой субсидии показывала
        # 21 880 100 / без типа, унаследованные от ФАДМ_2026. Снимаем явный
        # budget на ВСЕХ узлах (любой уровень — override срабатывает на
        # каждом), тогда сумма считается по FeoPlannedItem.feo_amount снизу
        # вверх — ниже заводим ровно эту сумму.
        await db.execute(update(FeoCategory).where(
            FeoCategory.id.in_(tree.category_id_map.values())
        ).values(budget=None))
    await copy_access_and_approvers(db, source.id, new_subsidy.id)
    copy_templates(source.id, new_subsidy.id)

    na_category, _created = await get_or_create_unallocated(db, new_subsidy.id, current_user=None)
    na_category_id = na_category.id if na_category else None
    feo_lookup = await _load_feo_lookup(db, new_subsidy.id)

    if na_category_id:
        # Бюджет ФЭО листа GoodsService — строка 1 листа даёт его НАПРЯМУЮ
        # (E1=15 880 100 план, F1=4 380 000 товары, G1=11 500 100 услуги),
        # владелец подтвердил эти три числа как целевые для карточки. Не
        # распределяем по реальным направлениям дерева (владелец явно
        # запретил «выдумывать суммы направлений» — у 19 направлений уровня 1
        # нет своего разбиения план/товар/услуга в листе) — кладём ДВЕ
        # агрегатные строки под «Не определена»: feo_amount, не amount —
        # feo_quantity/feo_unit_price/feo_amount (ПРАВИЛО №6, см. докстринг
        # FeoPlannedItem) НЕ участвуют ни в одной формуле плана/контроля
        # превышения (assert_tz_not_over_plan и т.п.), только в сумме «Бюджет
        # (ФЭО)» — ровно то, что нужно здесь, без побочных эффектов на
        # контроль превышения реальных закупок.
        db.add(FeoPlannedItem(
            feo_category_id=na_category_id,
            name="План ФЭО (лист GoodsService, F1) — товары",
            item_type=_kind_item_type("goods"),
            feo_amount=GOODSSERVICE_PLAN_GOODS,
            is_feo_breakdown=True,
            is_active=True,
            auto_created=True,
            notes="Плановый бюджет ФЭО по строке 1 листа GoodsService (F1)",
        ))
        db.add(FeoPlannedItem(
            feo_category_id=na_category_id,
            name="План ФЭО (лист GoodsService, G1) — услуги",
            item_type=_kind_item_type("services"),
            feo_amount=GOODSSERVICE_PLAN_SERVICES,
            is_feo_breakdown=True,
            is_active=True,
            auto_created=True,
            notes="Плановый бюджет ФЭО по строке 1 листа GoodsService (G1)",
        ))
        await db.flush()

    employee_lookup = await load_employee_lookup(db, new_subsidy.org_id)
    source_advance_contractors = await _load_source_advance_contractors(db, source.id)
    source_executors = await _load_source_executors_by_contractor(db, source.id)
    groups, plan_rows = group_rows_v2(rows)

    counters = BuildCountersV2()
    pending_payments: list[PendingPayment] = []

    with _silence_paid_confirmation_notifications():
        for group in groups:
            if group.is_framework and len(group.distinct_orders) >= 1:
                await build_framework(db, new_subsidy, group, feo_lookup, na_category_id,
                                      employee_lookup, new_subsidy.org_id, current_user, counters,
                                      pending_payments, source_advance_contractors, source_executors)
                continue

            main = group.rows[0] if group.rows else None
            employee_id = employee_lookup.find_one(group.contractor)
            category_id = _resolve_feo_category(main, feo_lookup, na_category_id, counters,
                                                 label=f"{group.contractor} №{group.purchase_no}") if main else na_category_id
            contractor_id = None if employee_id else (await _resolve_contractor_id(db, main, new_subsidy.org_id, counters) if main else None)
            await build_single(db, new_subsidy, group, category_id, contractor_id, employee_id, current_user, counters,
                               pending_payments, source_advance_contractors, source_executors)

        for row in plan_rows:
            # Плановые позиции (M=False, задание) — здесь на реальной выгрузке
            # GoodsService их 0 (все строки подтверждены), ветка оставлена на
            # случай будущих строк с M=False.
            category_id = _resolve_feo_category(row, feo_lookup, na_category_id, counters, label=row.subject)
            fpi = FeoPlannedItem(
                feo_category_id=category_id,
                name=row.item_name or row.subject,
                quantity=row.qty or Decimal("1"),
                item_type=_kind_item_type(row.item_kind),
                amount=row.amount,
                is_active=True,
                auto_created=True,
                notes=f"импорт GoodsService ({need_level_for(row)})",
            )
            db.add(fpi)

        await db.flush()
        if pending_payments:
            await attach_pending_payments(db, new_subsidy.id, pending_payments, counters)

    await db.flush()
    return new_subsidy, counters
