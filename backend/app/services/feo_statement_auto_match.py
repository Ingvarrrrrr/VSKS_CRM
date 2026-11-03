"""feo_statement_auto_match.py — системный фоновый подбор и создание закупок
из непривязанных строк казначейской выписки под плановые позиции ФЭО (задача 03.11.2026).

Проблема:
Штатный `run_match_payments` работает только по УЖЕ существующим в CRM закупкам
(Purchase). Если по субсидии заведено много платежей в выписке (напр. 456 платежей),
но заведено мало закупок (напр. 16), то сотни реальных платежей остаются
непривязанными, а смета ФЭО — без факта оплаты.

Решение:
1. Выбираются все непривязанные исполненные платежи (BankPayment) субсидии.
2. Выбираются активные позиции ФЭО (FeoPlannedItem), ещё не покрытые закупками.
3. Сопоставление по точной сумме и семантике (стемминг/корни контрагента, назначения,
   названия позиции, категории и комментариев).
4. Поддержка комбинированных платежей (несколько позиций ФЭО одной категории = сумма 1 платежа).
5. При dry_run=False: создание Purchase (status=paid) + PurchaseItem (hard-link к fpi.id),
   создание/привязка контрагента, договора, вызов attach() для связи с BankPayment
   и пересчёт статусов/денег.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_statement import BankPayment
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.schemas.purchases import PurchaseCreate, PurchaseItemCreate
from app.services.bank_statement_parser import EXECUTED_STATUSES
from app.services.contractor_resolve import find_or_create_contractor
from app.services.contract_items_materialize import copy_items_to_contract
from app.services.item_types import normalize_item_type
from app.services.payment_basis import (
    clean_purpose_subject,
    expense_code as _expense_code,
    expense_kind as _expense_kind,
)
from app.services.payment_lookup import attach, PaymentAttachError
from app.services.payment_target import PaymentGroup
from app.services.purchase_create_core import insert_purchase_with_items
from app.services.purchase_money_writer import recalc_purchase_money
from app.services.purchase_payments import recompute_purchase_payments
from app.services.temp_contract_number import generate_temp_contract_number
from app.routers.contracts import ensure_contract_linked

logger = logging.getLogger(__name__)


def _is_procurement_bank_payment(bp: BankPayment) -> bool:
    """Проверка, относится ли платёж к закупкам товаров, работ и услуг.
    Исключает зарплату (0100*), налоги/ЕНП (0810*, 0820*) и пособия/стипендии."""
    ec = str(bp.expense_code or "").strip()
    if ec:
        if not (ec.startswith("02") or ec.startswith("03") or ec.startswith("200") or ec.startswith("300")):
            return False

    # Защита по семантике: налоги и зарплата никогда не привязываются к закупкам ТРУ
    txt = f"{bp.payee_name or ''} {bp.purpose_text or ''}".lower()
    forbidden_markers = (
        "единый налоговый платеж", "енп", "фнс россии", "отпускные",
        "заработная плата", "заработной платы", "аванс за первую половину",
        "выплата зарплаты", "налог на доходы", "страховые взносы",
    )
    if any(m in txt for m in forbidden_markers):
        return False
    return True


def _clean_text(t: Optional[str]) -> str:
    return (t or "").lower().replace("ё", "е")


def _stems(text: Optional[str]) -> Set[str]:
    """Извлечение корней слов (длина от 4 символов, усечение до 6)."""
    words = [w.strip("«»\"'(),.:;-/*#№") for w in _clean_text(text).split()]
    res = set()
    stop_words = {
        "индивидуальный", "предприниматель", "общество", "ограниченной",
        "ответственностью", "соглашение", "платеж", "оплата", "договор",
        "казначейство", "донецкой", "народной", "республике", "управление",
        "федерального", "казначейства", "согласно", "счету", "акту",
    }
    for w in words:
        if len(w) >= 4 and w not in stop_words:
            res.add(w[:6])
    return res


async def match_unattached_statement_to_feo(
    db: AsyncSession,
    subsidy_id: int,
    *,
    current_user=None,
    used_bp_ids: Optional[Set[int]] = None,
    dry_run: bool = True,
) -> dict:
    """Системный подбор и создание закупок из непривязанных строк выписки
    под плановые позиции ФЭО субсидии."""
    used_bp_ids = set(used_bp_ids or [])

    subsidy = await db.get(Subsidy, subsidy_id)
    if not subsidy:
        return {"error": f"Субсидия {subsidy_id} не найдена"}

    if current_user is None:
        current_user = (await db.execute(
            select(User).where(User.role == "superadmin").limit(1)
        )).scalar_one_or_none()

    # 1. Непривязанные исполненные платежи (для копии-песочницы берём платежи оригинала)
    bps_subsidy_id = subsidy.copied_from_id if (subsidy.is_sandbox and subsidy.copied_from_id) else subsidy.id

    already_attached_bps = set((await db.execute(
        select(Payment.bank_payment_id)
        .join(Purchase, Payment.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy.id, Payment.bank_payment_id.is_not(None))
    )).scalars().all())

    bps = (await db.execute(
        select(BankPayment)
        .where(
            BankPayment.subsidy_id == bps_subsidy_id,
            BankPayment.status.in_(EXECUTED_STATUSES),
        )
        .order_by(BankPayment.payment_date.asc().nulls_last(), BankPayment.id.asc())
    )).scalars().all()

    unattached_bps = [
        b for b in bps
        if b.id not in already_attached_bps
        and b.id not in used_bp_ids
        and (b.amount or 0) > 0
        and _is_procurement_bank_payment(b)
    ]

    # 2. Активные позиции ФЭО субсидии
    fpi_rows = (await db.execute(
        select(FeoPlannedItem, FeoCategory.name.label("cat_name"))
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id, FeoPlannedItem.is_active.is_(True))
        .order_by(FeoPlannedItem.id.asc())
    )).all()

    # Позиции, уже покрытые существующими закупками
    covered_fpi_ids = set((await db.execute(
        select(PurchaseItem.feo_planned_item_id)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(Purchase.subsidy_id == subsidy_id, PurchaseItem.feo_planned_item_id.is_not(None))
    )).scalars().all())

    available_fpis = [(f, c) for f, c in fpi_rows if f.id not in covered_fpi_ids and (f.amount or 0) > 0]

    # 3. Алгоритм сопоставления
    matched_pairs: list[dict] = []
    used_fpi_ids: set[int] = set()

    # Группируем свободные позиции ФЭО по сумме
    fpi_by_amt = defaultdict(list)
    for f, c in available_fpis:
        amt_key = round(float(f.amount or 0), 2)
        fpi_by_amt[amt_key].append((f, c))

    for bp in unattached_bps:
        bp_amt = round(float(bp.amount or 0), 2)
        candidates = fpi_by_amt.get(bp_amt, [])
        free_cands = [(f, c) for f, c in candidates if f.id not in used_fpi_ids]
        if not free_cands:
            continue

        bp_inn = (bp.payee_inn or "").strip()
        bp_name = bp.payee_name or ""
        bp_purpose = bp.purpose_text or ""
        bp_stems = _stems(f"{bp_name} {bp_purpose}")

        best_cand = None
        best_score = 0

        for f, c in free_cands:
            score = 0
            f_text = f"{f.name} {c} {f.notes or ''}"
            f_stems = _stems(f_text)

            # Совпадение ИНН в тексте позиции или примечаниях
            if bp_inn and bp_inn in f_text:
                score += 100

            # Пересечение корней слов (контрагент, наименование, назначение)
            common_stems = bp_stems & f_stems
            score += len(common_stems) * 25

            # Если среди кандидатов с такой суммой позиция ровно одна
            if len(free_cands) == 1:
                score += 15

            if score > best_score:
                best_score = score
                best_cand = (f, c)

        # Порог совпадения: минимум 15 баллов
        if best_cand and best_score >= 15:
            f, c = best_cand
            used_fpi_ids.add(f.id)
            used_bp_ids.add(bp.id)
            matched_pairs.append({
                "bp": bp,
                "fpi": f,
                "cat_name": c,
                "score": best_score,
                "amount": bp_amt,
            })

    # 4. Применение сопоставлений (создание закупок и привязка платежей)
    created_purchases: list[dict] = []
    attach_warnings: list[str] = []

    if not dry_run and matched_pairs:
        assigned_uid = None
        if subsidy.org_id:
            from app.services.service_note_people import org_staff_user_ids
            staff_uids = await org_staff_user_ids(db, subsidy.org_id)
            if current_user and current_user.id in staff_uids:
                assigned_uid = current_user.id
            elif staff_uids:
                assigned_uid = next(iter(staff_uids))

        for m in matched_pairs:
            bp: BankPayment = m["bp"]
            fpi: FeoPlannedItem = m["fpi"]
            amt = Decimal(str(bp.amount or 0))

            contractor_id = await find_or_create_contractor(
                db, bp.payee_name, bp.payee_inn, org_id=subsidy.org_id,
            )

            code = _expense_code(bp)
            code_kind = await _expense_kind(db, code)
            raw_kind = fpi.item_type or code_kind or "товар"
            item_type = normalize_item_type(raw_kind)

            item = PurchaseItemCreate(
                item_name=fpi.name,
                item_type=item_type,
                quantity=Decimal(str(fpi.quantity or 1)),
                unit=fpi.unit or "шт",
                unit_price=Decimal(str(fpi.unit_price or amt)),
                total_price=amt,
                feo_category_id=fpi.feo_category_id,
                match_confirmed=True,
            )

            contract_date = bp.parsed_contract_date or bp.payment_date
            p_data = PurchaseCreate(
                subsidy_id=subsidy.id,
                status="contracted",
                contractor_id=contractor_id,
                purchase_method="single",
                feo_category_id=fpi.feo_category_id,
                contract_number=bp.parsed_contract_number or None,
                contract_date=contract_date,
                assigned_user_id=assigned_uid,
                items=[item],
            )

            p, created_items = await insert_purchase_with_items(
                db, p_data, current_user, items_data=[item], total_nmck=amt,
            )
            p.created_from_bank_payment_id = bp.id
            p.task_comment = (
                f"Создана автосопоставлением с выпиской казначейства: платёж № {bp.payment_number} "
                f"от {bp.payment_date.strftime('%d.%m.%Y') if bp.payment_date else '?'}"
            )

            if p.planned_total_price is None:
                p.planned_total_price = amt
                p.total_nmck = amt
                p.nmck = amt

            # Связываем позицию закупки напрямую со строкой ФЭО
            created_items[0].feo_planned_item_id = fpi.id

            p.contract_number = p.contract_number or await generate_temp_contract_number(p, db)
            p.contract_number_is_temporary = not bool(bp.parsed_contract_number)
            await copy_items_to_contract(db, p.id)
            await ensure_contract_linked(p, db)
            await recalc_purchase_money(db, p)
            await db.flush()

            # Привязываем строку выписки к созданной закупке через attach()
            group = PaymentGroup(
                group_key=f"auto-match-bp-{bp.id}",
                subsidy_id=subsidy.id,
                registry_number=p.registry_number,
                contract_number=p.contract_number,
                is_framework=False,
                contractor_id=contractor_id,
                contractor_inn=bp.payee_inn,
                contractor_name=bp.payee_name,
                goods_amount=amt if item_type == "товар" else Decimal(0),
                services_amount=amt if item_type != "товар" else Decimal(0),
                unspecified_amount=Decimal(0),
                purchase_ids=[p.id],
                payments=[],
            )

            try:
                await attach(
                    db, group, [bp.id],
                    allocations={p.id: amt},
                    warnings_out=attach_warnings,
                )
                await recompute_purchase_payments(db, p.id)
            except PaymentAttachError as exc:
                attach_warnings.append(f"Закупка #{p.id} создана, но привязать платёж #{bp.id} не удалось: {exc}")

            created_purchases.append({
                "purchase_id": p.id,
                "purchase_number": p.purchase_number,
                "registry_number": p.registry_number,
                "bank_payment_id": bp.id,
                "bank_payment_number": bp.payment_number,
                "fpi_id": fpi.id,
                "fpi_name": fpi.name,
                "amount": float(amt),
            })

        await db.commit()

    total_matched_amt = sum(m["amount"] for m in matched_pairs)
    return {
        "subsidy_id": subsidy_id,
        "dry_run": dry_run,
        "unattached_payments_total": len(unattached_bps),
        "available_feo_items_total": len(available_fpis),
        "matched_count": len(matched_pairs),
        "matched_total_amount": round(total_matched_amt, 2),
        "matched_items": [
            {
                "payment_number": m["bp"].payment_number,
                "payment_date": m["bp"].payment_date.isoformat() if m["bp"].payment_date else None,
                "payee_name": m["bp"].payee_name,
                "payee_inn": m["bp"].payee_inn,
                "amount": m["amount"],
                "fpi_id": m["fpi"].id,
                "fpi_name": m["fpi"].name,
                "category_name": m["cat_name"],
                "score": m["score"],
            }
            for m in matched_pairs
        ],
        "created_purchases": created_purchases,
        "warnings": attach_warnings,
    }

