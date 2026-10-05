"""Создать закупку по строке казначейской выписки — БЕЗ заявки.

План .planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1, «Создать
закупку по платёжке»/🟢 «Без заявки». Аналог «Импорта факта»
(app/services/historical_fact_import/commit.py) — учётная запись уже
СОВЕРШЁННОЙ траты, не заявка на будущую: одна обобщённая позиция (детально
из платёжки не восстановить), статус «Договор заключён», направление ФЭО —
переданное либо штатная папка «Не определена» (app/services/feo_unallocated.py,
ПРАВИЛО №6 — не вторая копия find-or-create), плановая позиция —
app/services/plan_autoassign.py::create_auto_planned_item.

Контрагент — app/services/contractor_resolve.py::find_or_create_contractor по
ИНН/наименованию получателя (bp.payee_inn/payee_name) — тот же хелпер, что и
исторический импорт, ПРАВИЛО №6.

Авансовый признак сотрудника: если получатель платежа — на самом деле
сотрудник (ФИО совпадает с users.full_name той же организации, что и
субсидия — без регистра/ё, см. scripts/fadm_sheet_load/advance.py::
normalize_person_name/EmployeeLookup), закупка заводится как авансовый отчёт
(purchase_method='advance', reimbursement_user_id = assigned_user_id =
сотрудник) — общая часть (normalize_person_name) вынесена в
app/services/person_name.py и используется ОБОИМИ местами (ПРАВИЛО №6): этим
сервисом и scripts/fadm_sheet_load/advance.py (скрипт импортирует её, не
пишет вторую копию).

После создания закупки — штатный attach() (app/services/payment_lookup.py)
этой строки выписки к ней; дальше обычный путь «Оплачено через подтверждение
согласующим» (recompute_purchase_payments уже вызывается внутри attach()).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date as _date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.contractor_resolve import find_or_create_contractor
from app.services.payment_basis import (
    clean_purpose_subject,
    expense_code as _expense_code,
    expense_kind as _expense_kind,
)
from app.services.person_name import normalize_person_name


@dataclass
class CreateFromBankPaymentResult:
    purchase: Purchase
    warnings: list[str] = field(default_factory=list)


async def _find_employee_id(db: AsyncSession, org_id: Optional[int], payee_name: Optional[str]) -> Optional[int]:
    """Сотрудник org_id, чьё ФИО (нормализованное) точно совпадает с payee_name.
    Неоднозначность (>1 совпадения) → не считаем авансовым (то же правило, что
    scripts/fadm_sheet_load/advance.py::resolve_assigned_user_id)."""
    norm = normalize_person_name(payee_name)
    if not norm or not org_id:
        return None
    rows = (await db.execute(
        select(User.id, User.full_name).where(User.org_id == org_id)
    )).all()
    matches = [uid for uid, full_name in rows if normalize_person_name(full_name) == norm]
    return matches[0] if len(matches) == 1 else None


def _build_item_name(bp: BankPayment, code_name: Optional[str]) -> str:
    """Наименование позиции закупки, созданной по платёжке.

    Приёмка 05.10.2026 (дефект): сырое назначение платежа («(КБК;код)
    Соглашение № ... от ...  Договор ...») никому не читаемо как наименование
    позиции. Теперь: название СТАТЬИ РАСХОДОВ из справочника expense_codes,
    если код распознан (code_name передаёт вызывающий — ПРАВИЛО №6, он уже
    делает lookup для item_type, второй раз не ходим в БД); если кода в
    справочнике нет — очищенный предмет из назначения (без префикса «(КБК;код)»
    и без «Соглашение ... от ...», см. payment_basis.clean_purpose_subject —
    одна точка этой очистки). В обоих случаях — «по договору № ... от ...»,
    если договор распознан парсером (bp.parsed_contract_number/date)."""
    subject = (code_name or "").strip() or clean_purpose_subject(bp.purpose_text) or "Оплата по выписке"
    subject = subject[:300]
    if bp.parsed_contract_number:
        contract_part = f"по договору № {bp.parsed_contract_number}"
        if bp.parsed_contract_date:
            contract_part += f" от {bp.parsed_contract_date.strftime('%d.%m.%Y')}"
        subject = f"{subject} {contract_part}"
    return subject[:500]


async def create_purchase_from_bank_payment(
    db: AsyncSession,
    current_user,
    subsidy: Subsidy,
    bp: BankPayment,
    *,
    feo_category_id: Optional[int] = None,
) -> CreateFromBankPaymentResult:
    """Создаёт закупку из ОДНОЙ исполненной строки выписки + привязывает её
    (attach) — без заявки. Коммит — на вызывающем (роутер)."""
    if (bp.status or "").upper().strip() not in EXECUTED_STATUSES:
        raise HTTPException(422, f"Платёж №{bp.payment_number} не исполнен (статус «{bp.status}»)")

    warnings: list[str] = []

    from app.services.purchase_create_core import insert_purchase_with_items
    from app.services.contract_items_materialize import copy_items_to_contract
    from app.services.temp_contract_number import generate_temp_contract_number
    from app.routers.contracts import ensure_contract_linked
    from app.services.purchase_money_writer import recalc_purchase_money
    from app.services.plan_autoassign import create_auto_planned_item
    from app.services.feo_unallocated import get_or_create_unallocated

    amount = Decimal(str(bp.amount or 0))
    code = _expense_code(bp)
    code_kind = await _expense_kind(db, code)
    item_type = code_kind if code_kind in ("товар", "услуга", "работа") else "товар"

    code_name: Optional[str] = None
    if code:
        from app.models.expense_code import ExpenseCode
        code_row = (await db.execute(
            select(ExpenseCode.name).where(ExpenseCode.code == code)
        )).scalar_one_or_none()
        if code_row is None:
            prefix = code[:4]
            if prefix and prefix != code:
                code_row = (await db.execute(
                    select(ExpenseCode.name).where(ExpenseCode.code == prefix)
                )).scalar_one_or_none()
        code_name = code_row

    contractor_id = await find_or_create_contractor(
        db, bp.payee_name, bp.payee_inn, org_id=subsidy.org_id,
    )

    employee_id = await _find_employee_id(db, subsidy.org_id, bp.payee_name)
    is_advance = employee_id is not None

    # Направление ФЭО: переданное явно, иначе штатная папка «Не определена»
    # (ПРАВИЛО №6 — одна точка find-or-create, см. app/services/feo_unallocated.py).
    eff_category_id = feo_category_id
    if not eff_category_id:
        unallocated, _created = await get_or_create_unallocated(
            db, subsidy.id, None, current_user=current_user, source="autoassign",
        )
        eff_category_id = unallocated.id

    contract_date = bp.parsed_contract_date or bp.payment_date

    item = PurchaseItemCreate(
        item_name=_build_item_name(bp, code_name),
        item_type=item_type,
        quantity=Decimal("1"),
        unit="шт",
        unit_price=amount,
        total_price=amount,
        feo_category_id=eff_category_id,
        match_confirmed=True,
    )

    data = PurchaseCreate(
        subsidy_id=subsidy.id,
        status="contracted",
        contractor_id=contractor_id if not is_advance else None,
        purchase_method="advance" if is_advance else "single",
        feo_category_id=eff_category_id,
        contract_number=bp.parsed_contract_number or None,
        contract_date=contract_date,
        reimbursement_user_id=employee_id if is_advance else None,
        assigned_user_id=employee_id if is_advance else None,
        items=[item],
    )

    p, created_items = await insert_purchase_with_items(
        db, data, current_user, items_data=[item], total_nmck=amount,
    )
    p.created_from_bank_payment_id = bp.id
    p.task_comment = (
        f"Создана по платёжке № {bp.payment_number or bp.id} от "
        f"{bp.payment_date.strftime('%d.%m.%Y') if bp.payment_date else '?'} — "
        "позиции не детализированы, уточните"
    )

    if p.planned_total_price is None:
        p.planned_total_price = amount
        p.total_nmck = amount
        p.nmck = amount

    # Плановая позиция под закупку (ПРАВИЛО: план/факт должны сходиться) —
    # тот же create_auto_planned_item, что и остальные авто-планы проекта.
    new_fpi = await create_auto_planned_item(
        db, created_items[0], eff_category_id, note="созданием закупки по платёжке",
    )
    created_items[0].feo_planned_item_id = new_fpi.id

    p.contract_number = p.contract_number or await generate_temp_contract_number(p, db)
    p.contract_number_is_temporary = not bool(bp.parsed_contract_number)
    await copy_items_to_contract(db, p.id)
    await ensure_contract_linked(p, db)
    await recalc_purchase_money(db, p)
    await db.flush()

    # Привязка самой строки выписки — штатным attach(), не второй копией.
    from app.services.payment_target import PaymentGroup
    from app.services.payment_lookup import attach, PaymentAttachError

    group = PaymentGroup(
        group_key=f"bank-payment-{bp.id}",
        subsidy_id=subsidy.id,
        registry_number=p.registry_number,
        contract_number=p.contract_number,
        is_framework=False,
        contractor_id=contractor_id,
        contractor_inn=bp.payee_inn,
        contractor_name=bp.payee_name,
        goods_amount=amount if item_type == "товар" else Decimal(0),
        services_amount=amount if item_type != "товар" else Decimal(0),
        unspecified_amount=Decimal(0),
        purchase_ids=[p.id],
        payments=[],
    )
    try:
        await attach(
            db, group, [bp.id],
            allocations={p.id: amount},
            warnings_out=warnings,
        )
    except PaymentAttachError as exc:
        warnings.append(f"Закупка создана, но привязать платёж не удалось: {exc}")

    return CreateFromBankPaymentResult(purchase=p, warnings=warnings)
