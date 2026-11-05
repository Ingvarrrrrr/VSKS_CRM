"""Контрольные суммы «выписка ↔ закупки» по субсидии — план
.planning/quick/2026-10-05-payment-control/PLAN.md, раздел 1.

GET  /api/subsidies/{id}/payment-control                       — сверка целиком
GET  /api/subsidies/{id}/payment-control/codes                  — выбор статей (GET)
PUT  /api/subsidies/{id}/payment-control/codes                  — выбор статей (PUT, subsidy.edit)
GET  /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/candidates
POST /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/attach
POST /api/subsidies/{id}/payment-control/bank-payments/{bp_id}/create-purchase

Права GET — видимость субсидии (та же двухуровневая модель, что у других
subsidy-scoped вкладок, см. app/auth/visibility.py::get_visible_subsidy_ids,
tab_key="payment_registry" — тот же, что уже использует реестр платежей для
субсидийного среза, ПРАВИЛО №6: не заводим отдельный tab_key только для этой
вкладки). Действия (PUT codes / attach / create-purchase) — subsidy.edit
(app/auth/permissions.py::has_org_key), тот же гейт, что у разнесения платежей
(app/routers/purchase_payment_matching.py::_get_subsidy_for_payments).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.auth.visibility import get_visible_subsidy_ids
from app.models.bank_statement import BankPayment
from app.models.subsidy import Subsidy

router = APIRouter(prefix="/api/subsidies", tags=["subsidy-payment-control"])

_PAYMENT_CONTROL_TAB_KEY = "payment_registry"


async def _get_subsidy_for_read(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await db.get(Subsidy, sid)
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    vis = await get_visible_subsidy_ids(current_user, db, _PAYMENT_CONTROL_TAB_KEY)
    if vis is not None and sid not in vis:
        raise HTTPException(403, "Нет доступа к сверке платежей этой субсидии")
    return s


async def _get_subsidy_for_write(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await _get_subsidy_for_read(sid, db, current_user)
    if not await has_org_key(current_user, db, s.org_id, "subsidy.edit", subsidy_id=sid):
        raise HTTPException(
            403,
            "Действие доступно только тому, у кого есть право редактировать субсидию",
        )
    return s


async def _get_bank_payment_or_404(bp_id: int, db: AsyncSession) -> BankPayment:
    bp = await db.get(BankPayment, bp_id)
    if not bp:
        raise HTTPException(404, "Платёж не найден")
    return bp


# ---------------------------------------------------------------------------
# GET /payment-control
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control")
async def get_payment_control(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.services.subsidy_payment_control import build_payment_control

    subsidy = await _get_subsidy_for_read(sid, db, current_user)
    return await build_payment_control(db, subsidy)


# ---------------------------------------------------------------------------
# GET/PUT /payment-control/codes
# ---------------------------------------------------------------------------

class _CodesBody(BaseModel):
    codes: List[str]


@router.get("/{sid}/payment-control/codes")
async def get_payment_control_codes(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.expense_code import ExpenseCode
    from sqlalchemy import select
    from app.services.subsidy_payment_control import get_search_codes

    await _get_subsidy_for_read(sid, db, current_user)
    codes, is_default = await get_search_codes(db, sid)
    directory_rows = (await db.execute(
        select(ExpenseCode).where(ExpenseCode.is_active.is_(True)).order_by(ExpenseCode.code)
    )).scalars().all()
    return {
        "codes": sorted(codes),
        "is_default": is_default,
        "directory": [
            {"code": c.code, "name": c.name, "kind": c.kind, "is_procurement": c.is_procurement}
            for c in directory_rows
        ],
    }


@router.put("/{sid}/payment-control/codes")
async def put_payment_control_codes(
    sid: int,
    body: _CodesBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.models.expense_code import ExpenseCode
    from sqlalchemy import select
    from app.services.subsidy_payment_control import get_search_codes, set_search_codes

    await _get_subsidy_for_write(sid, db, current_user)
    await set_search_codes(db, sid, body.codes)
    await db.commit()

    codes, is_default = await get_search_codes(db, sid)
    directory_rows = (await db.execute(
        select(ExpenseCode).where(ExpenseCode.is_active.is_(True)).order_by(ExpenseCode.code)
    )).scalars().all()
    return {
        "codes": sorted(codes),
        "is_default": is_default,
        "directory": [
            {"code": c.code, "name": c.name, "kind": c.kind, "is_procurement": c.is_procurement}
            for c in directory_rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /payment-control/bank-payments/{bp_id}/candidates
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control/bank-payments/{bp_id}/candidates")
async def get_bank_payment_candidates(
    sid: int,
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Кандидаты-закупки ЭТОЙ субсидии для строки выписки — переиспользует
    app/services/match_candidates.py::build_candidates (та же логика, что и
    общий /api/payments/registry/{bp_id}/match-suggestions), с фильтром по
    subsidy_id (ПРАВИЛО №6 — не второй скоринг).

    build_candidates() ищет среди закупок matched_contract_id/matched_contractor_id
    строки — для свежей (не прошедшей /match) строки оба пусты; подставляем
    contractor_id по ИНН получателя ВРЕМЕННО (на объекте ORM в памяти, без
    flush/commit — GET ничего не пишет) — тот же приём, что и обычный
    /match перед вызовом сверки, но без сохранения выбора."""
    await _get_subsidy_for_read(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from sqlalchemy import select
    from app.models.contractor import Contractor
    from app.models.purchase import Purchase as _Purchase
    from app.services.match_candidates import build_candidates

    orig_contractor_id = bp.matched_contractor_id
    if not bp.matched_contract_id and not bp.matched_contractor_id and bp.payee_inn:
        c = (await db.execute(
            select(Contractor).where(Contractor.inn == bp.payee_inn)
        )).scalars().first()
        if c:
            bp.matched_contractor_id = c.id
    try:
        candidates = await build_candidates(bp, db)
    finally:
        bp.matched_contractor_id = orig_contractor_id

    items = []
    seen_purchase_ids: set[int] = set()
    for c in candidates:
        for pid in c.get("purchase_ids", []):
            if pid in seen_purchase_ids:
                continue
            p = await db.get(_Purchase, pid)
            if p is None or p.subsidy_id != sid:
                continue
            seen_purchase_ids.add(pid)
            contractor_name = None
            if p.contractor_id:
                contractor = await db.get(Contractor, p.contractor_id)
                contractor_name = contractor.name if contractor else None
            items.append({
                "purchase_id": p.id,
                "registry_number": p.registry_number,
                "subject": p.subject or p.item_name,
                "contractor_name": contractor_name,
                "contract_price": float(p.contract_price) if p.contract_price is not None else None,
                "paid_by_statement": float(p.payment_amount) if p.payment_amount is not None else None,
                "reason": c.get("label"),
            })

    # Умный перебор составных сумм (Subset Sum) с оценкой близости категорий
    # («Очень вероятно» vs «Маловероятно») — в т.ч. среди закупок без контрагента
    # («напокупали, а проставить у кого и как забыли»).
    from decimal import Decimal
    from app.services.payment_smart_combo_matcher import (
        split_uncontracted_multi_item_purchases,
        load_unpaid_candidate_units,
        find_subset_sum_combinations,
        find_sign_error_candidates,
        is_unit_contractor_conflicting,
        detect_semantic_cluster,
        _word_stems,
    )
    split_cnt = await split_uncontracted_multi_item_purchases(db, sid)
    if split_cnt > 0:
        await db.commit()

    combo_suggestions: list[dict] = []
    sign_error_hints: list[dict] = []
    partial_purchases: list[dict] = []
    if bp.amount is not None:
        bp_amt = Decimal(str(bp.amount))
        units = await load_unpaid_candidate_units(db, sid, preferred_contractor_inn=bp.payee_inn)
        combo_suggestions = find_subset_sum_combinations(
            units,
            bp_amt,
            purpose_text=bp.purpose_text,
            payee_name=bp.payee_name,
            payee_inn=bp.payee_inn,
        )
        sign_error_hints = find_sign_error_candidates(units, bp_amt)
        # Если штатный поиск по контрагенту ничего не нашёл, добавляем одиночные
        # совпадения (count==1) также в плоский список items для обратной совместимости.
        for cs in combo_suggestions:
            if cs["count"] == 1:
                first_it = cs["items"][0]
                pid = first_it["purchase_id"]
                if pid not in seen_purchase_ids:
                    seen_purchase_ids.add(pid)
                    items.append({
                        "purchase_id": pid,
                        "registry_number": first_it.get("registry_number"),
                        "subject": first_it.get("subject"),
                        "contractor_name": first_it.get("contractor_name"),
                        "contract_price": first_it.get("amount"),
                        "paid_by_statement": None,
                        "reason": f"{cs['probability_label']}: {cs['coherence_reason']}",
                    })

        # Крупные/сводные закупки субсидии (остаток > суммы платёжки, напр. 1694 ГСМ 413 050,66 ₽
        # или 1695 Проезд 407 184,10 ₽), к которым платёж можно привязать как частичную оплату (транш).
        all_units = await load_unpaid_candidate_units(db, sid)
        p_stems = _word_stems(bp.purpose_text or "")
        p_sem = detect_semantic_cluster(bp.purpose_text or "")
        p_low = (bp.purpose_text or "").lower()
        for u in all_units:
            if u.is_sub_item:
                continue
            if is_unit_contractor_conflicting(u, payee_name=bp.payee_name, payee_inn=bp.payee_inn):
                continue
            u_text = " ".join([u.subject or ""] + (u.item_names or []))
            u_stems = _word_stems(u_text)
            u_sem = detect_semantic_cluster(u_text)
            match_score = 0
            reasons_list = []
            if u.amount > bp_amt:
                reasons_list.append(f"остаток к оплате {float(u.amount):,.2f} ₽ (транш)".replace(",", " "))
                match_score += 10
            if p_stems & u_stems:
                match_score += 50
                reasons_list.append("совпадает с назначением платежа")
            elif ("гсм" in p_low or "топлив" in p_low or "бензин" in p_low) and "гсм" in u_text.lower():
                match_score += 50
                reasons_list.append("сводная закупка ГСМ")
            elif ("перевозк" in p_low or "проезд" in p_low or "пассажир" in p_low or "билет" in p_low) and "проезд" in u_text.lower():
                match_score += 50
                reasons_list.append("сводная закупка Проезд")
            elif p_sem and u_sem and p_sem == u_sem:
                match_score += 30
                if u.feo_category_name:
                    reasons_list.append(f"путь в субсидии: «{u.feo_category_name}»")
            elif u.feo_category_name:
                reasons_list.append(f"путь в субсидии: «{u.feo_category_name}»")
            if u.is_temp_plan:
                reasons_list.append("из «План закупок» («Да», временная закупка)")

            partial_purchases.append({
                "purchase_id": u.purchase_id,
                "registry_number": u.registry_number,
                "sheet_ref": u.sheet_ref,
                "subject": u.subject,
                "feo_category_path": u.feo_category_name,
                "is_temp_plan": u.is_temp_plan,
                "contractor_name": u.contractor_name,
                "contract_price": float(u.amount),
                "paid_by_statement": None,
                "match_score": match_score,
                "is_larger_parent": u.amount > bp_amt,
                "reason": " · ".join(reasons_list) if reasons_list else (u.sheet_ref or "Доступная закупка субсидии"),
            })

        partial_purchases.sort(
            key=lambda x: (x["match_score"], 1 if x["is_larger_parent"] else 0, x["contract_price"] or 0),
            reverse=True,
        )

    from app.models.bank_statement import ExpenseCode
    ec = str(bp.expense_code or "").strip()
    if not ec and bp.purpose_text:
        m_ec = re.search(r';\s*(\d{4,})', bp.purpose_text)
        if m_ec:
            ec = m_ec.group(1)
    ec_name = None
    if ec:
        ec_row = (await db.execute(select(ExpenseCode.name).where(ExpenseCode.code == ec))).scalar_one_or_none()
        ec_name = ec_row
    bp_dir_str = f"{ec} — {ec_name}" if (ec and ec_name) else (ec_name or ec or None)

    return {
        "bank_payment": {
            "id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "amount": float(bp.amount) if bp.amount is not None else 0.0,
            "payee_name": bp.payee_name,
            "payee_inn": bp.payee_inn,
            "expense_direction": bp_dir_str,
            "purpose_text": bp.purpose_text,
        },
        "items": items,
        "combo_suggestions": combo_suggestions,
        "sign_error_hints": sign_error_hints,
        "all_unpaid_purchases": partial_purchases,
    }


# ---------------------------------------------------------------------------
# POST /payment-control/bank-payments/{bp_id}/attach-combo
# ---------------------------------------------------------------------------

class _AttachComboBody(BaseModel):
    purchase_ids: List[int]
    merge_purchases: bool = True
    approve_amount_diff: bool = False


@router.post("/{sid}/payment-control/bank-payments/{bp_id}/attach-combo")
async def attach_bank_payment_combo(
    sid: int,
    bp_id: int,
    body: _AttachComboBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Группирует выбранную комбинацию позиций/закупок в одну закупку (при
    merge_purchases=True), проставляет контрагента из банковской платёжки и
    привязывает платёж."""
    await _get_subsidy_for_write(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from app.services.payment_smart_combo_matcher import merge_and_attach_combo
    result = await merge_and_attach_combo(
        db,
        sid,
        bp,
        body.purchase_ids,
        merge_purchases=body.merge_purchases,
        approve_amount_diff=body.approve_amount_diff,
    )
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Пакетный комбинаторный подбор (Subset Sum) и пакетное применение
# ---------------------------------------------------------------------------

class _SingleComboApply(BaseModel):
    bank_payment_id: int
    purchase_ids: List[int]
    merge_purchases: bool = True
    approve_amount_diff: bool = False


class _BatchApplyBody(BaseModel):
    matches: List[_SingleComboApply]


@router.get("/{sid}/payment-control/batch-combos")
async def get_batch_combos(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Строгий пошаговый поиск сопоставлений (по правилу владельца 04.11.2026):
    0) Разделение многопозиционных закупок без контрагента на отдельные закупки с виртуальными номерами РЕЕ-...;
    1) Закупки с уже известным подрядчиком сопоставляются ТОЛЬКО с выплатами того же подрядчика и ТОЛЬКО при точном совпадении суммы (Δ = 0.00 ₽);
    2) Одиночные совпадения 1-к-1 (Δ = 0.00 ₽) среди единичных закупок без подрядчика;
    3) Комбинаторика 2–4 единичных закупок без подрядчика, дающих точную сумму выплаты (Δ = 0.00 ₽), с объединением в одну закупку;
    4) Одиночные кандидаты с расхождением в копейки и рубли (0 < |Δ| <= 5.00 ₽) — строго со статусом «Требует согласования суммы» на подтверждение человека."""
    subsidy = await _get_subsidy_for_read(sid, db, current_user)

    from decimal import Decimal
    import datetime
    import re
    from sqlalchemy import select
    from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
    from app.services.payment_lookup import _attached_bank_payment_ids_in_subsidy, EXECUTED_STATUSES
    from app.services.payment_smart_combo_matcher import (
        split_uncontracted_multi_item_purchases,
        load_unpaid_candidate_units,
        find_subset_sum_combinations,
        is_same_contractor_unit,
    )

    # Шаг 0: гарантируем, что каждая позиция без контрагента выделена в отдельную закупку с виртуальным номером РЕЕ-...
    split_cnt = await split_uncontracted_multi_item_purchases(db, sid)
    if split_cnt > 0:
        await db.commit()

    # 1. Загружаем все строки выписки, относящиеся к субсидии (строго в хронологическом порядке)
    bp_rows = (await db.execute(
        select(BankPayment).where(subsidy_scope_clause(subsidy)).order_by(BankPayment.payment_date.asc(), BankPayment.id.asc())
    )).scalars().all()

    def _is_procurement_payment(bp: BankPayment) -> bool:
        """Проверяет, относится ли платёж к закупкам товаров, работ и услуг (200 и 300 коды).
        Исключает заработную плату (01*), налоги/ЕНП и командировочные выплаты (08*)."""
        ec = str(bp.expense_code or "").strip()
        if not ec and bp.purpose_text:
            m = re.search(r';\s*(\d{4,})', bp.purpose_text)
            if m:
                ec = m.group(1)
        if ec:
            if not (ec.startswith("02") or ec.startswith("03") or ec.startswith("200") or ec.startswith("300")):
                return False

        txt = f"{bp.payee_name or ''} {bp.purpose_text or ''}".lower()
        forbidden_markers = (
            "единый налоговый платеж", "енп", "фнс россии", "отпускные",
            "заработная плата", "заработной платы", "аванс за первую половину",
            "выплата зарплаты", "налог на доходы", "страховые взносы",
            "командирован", "суточн", "выплаты,связанные с командированием",
            "выплаты, связанные с командированием",
        )
        if any(m in txt for m in forbidden_markers):
            return False
        return True

    # 2. Исключаем уже привязанные в этой субсидии, неисполненные и НЕ-закупочные (ФОТ/налоги/командировки)
    bp_ids = [bp.id for bp in bp_rows]
    attached_ids = await _attached_bank_payment_ids_in_subsidy(db, bp_ids, sid)
    unattached_bps = [
        bp for bp in bp_rows
        if bp.id not in attached_ids
        and bp.amount is not None
        and bp.amount > 0
        and (bp.status or "").upper().strip() in EXECUTED_STATUSES
        and _is_procurement_payment(bp)
    ]

    sorted_bps = sorted(
        unattached_bps,
        key=lambda b: (
            b.payment_date or datetime.date.min,
            b.payment_number or "",
            b.id,
        ),
    )

    # 3. Загружаем все неоплаченные закупки субсидии + временные закупки из «План закупок» («Да»)
    units = await load_unpaid_candidate_units(db, sid, include_planned_items=True)

    from app.models.bank_statement import ExpenseCode
    code_rows = (await db.execute(select(ExpenseCode.code, ExpenseCode.name))).all()
    code_names = {r.code: r.name for r in code_rows}

    def _bp_expense_dir(bp: BankPayment) -> Optional[str]:
        ec = str(bp.expense_code or "").strip()
        if not ec and bp.purpose_text:
            m = re.search(r';\s*(\d{4,})', bp.purpose_text)
            if m:
                ec = m.group(1)
        ename = code_names.get(ec) if ec else None
        return f"{ec} — {ename}" if (ec and ename) else (ename or ec or None)

    matches = []
    used_whole_purchase_ids: set[int] = set()
    matched_bp_ids: set[int] = set()

    def _record_match(bp: BankPayment, best_combo: dict, combos: list[dict]):
        matched_bp_ids.add(bp.id)
        for it in best_combo["items"]:
            used_whole_purchase_ids.add(it["purchase_id"])
        matches.append({
            "bank_payment_id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "amount": float(bp.amount),
            "payee_name": bp.payee_name,
            "payee_inn": bp.payee_inn,
            "expense_direction": _bp_expense_dir(bp),
            "purpose_text": bp.purpose_text,
            "combo": best_combo,
            "alternatives": combos[:3],
        })

    # =========================================================================
    # ШАГ 1: Закупки с уже известным подрядчиком (тот же подрядчик + точная сумма Δ = 0.00 ₽)
    # =========================================================================
    for bp in sorted_bps:
        if bp.id in matched_bp_ids:
            continue
        same_contractor_units = [
            u for u in units
            if u.purchase_id not in used_whole_purchase_ids
            and u.contractor_id is not None
            and is_same_contractor_unit(u, bp.payee_name, bp.payee_inn)
        ]
        if not same_contractor_units:
            continue
        bp_amt = Decimal(str(bp.amount))
        combos = find_subset_sum_combinations(
            same_contractor_units,
            bp_amt,
            purpose_text=bp.purpose_text,
            payee_name=bp.payee_name,
            payee_inn=bp.payee_inn,
            allow_single=True,
            allow_multi=True,
            allow_approval_tol=False,
        )
        if combos and combos[0]["probability"] in ("high", "medium"):
            _record_match(bp, combos[0], combos)

    # =========================================================================
    # ШАГ 2: Единичные совпадения 1-к-1 среди позиций БЕЗ подрядчика (точная сумма Δ = 0.00 ₽)
    # Сначала среди позиций, уже отмеченных оплаченными в факте, затем среди всех
    # остальных позиций (включая «Да» в столбце «План закупок» — временные закупки)
    # =========================================================================
    for only_declared_paid in (True, False):
        for allowed_probs in (("high",), ("high", "medium")):
            for bp in sorted_bps:
                if bp.id in matched_bp_ids:
                    continue
                uncontracted_units = [
                    u for u in units
                    if u.purchase_id not in used_whole_purchase_ids
                    and u.contractor_id is None
                    and (u.is_declared_paid if only_declared_paid else True)
                ]
                if not uncontracted_units:
                    break
                bp_amt = Decimal(str(bp.amount))
                combos = find_subset_sum_combinations(
                    uncontracted_units,
                    bp_amt,
                    purpose_text=bp.purpose_text,
                    payee_name=bp.payee_name,
                    payee_inn=bp.payee_inn,
                    allow_single=True,
                    allow_multi=False,
                    allow_approval_tol=False,
                )
                if combos and combos[0]["probability"] in allowed_probs:
                    _record_match(bp, combos[0], combos)

    # =========================================================================
    # ШАГ 3: Комбинаторика 2–100+ единичных позиций БЕЗ подрядчика (точная сумма Δ = 0.00 ₽)
    # Сначала среди отмеченных оплаченными в факте, затем включая позиции «План закупок» («Да»)
    # =========================================================================
    for only_declared_paid in (True, False):
        for allowed_probs in (("high",), ("high", "medium")):
            for bp in sorted_bps:
                if bp.id in matched_bp_ids:
                    continue
                uncontracted_units = [
                    u for u in units
                    if u.purchase_id not in used_whole_purchase_ids
                    and u.contractor_id is None
                    and (u.is_declared_paid if only_declared_paid else True)
                ]
                if not uncontracted_units:
                    break
                bp_amt = Decimal(str(bp.amount))
                combos = find_subset_sum_combinations(
                    uncontracted_units,
                    bp_amt,
                    purpose_text=bp.purpose_text,
                    payee_name=bp.payee_name,
                    payee_inn=bp.payee_inn,
                    allow_single=False,
                    allow_multi=True,
                    allow_approval_tol=False,
                )
                if combos and combos[0]["probability"] in allowed_probs:
                    _record_match(bp, combos[0], combos)

    # =========================================================================
    # ШАГ 4: Расхождения в копейки и рубли (0 < |Δ| <= 5.00 ₽) — строго на согласование человека
    # =========================================================================
    for bp in sorted_bps:
        if bp.id in matched_bp_ids:
            continue
        candidate_units = [
            u for u in units
            if u.purchase_id not in used_whole_purchase_ids
            and (
                u.contractor_id is None
                or is_same_contractor_unit(u, bp.payee_name, bp.payee_inn)
            )
        ]
        if not candidate_units:
            break
        bp_amt = Decimal(str(bp.amount))
        combos = find_subset_sum_combinations(
            candidate_units,
            bp_amt,
            purpose_text=bp.purpose_text,
            payee_name=bp.payee_name,
            payee_inn=bp.payee_inn,
            allow_single=True,
            allow_multi=False,
            allow_approval_tol=True,
        )
        approval_combos = [c for c in combos if c.get("needs_amount_approval")]
        if approval_combos:
            _record_match(bp, approval_combos[0], approval_combos)

    # Сортируем итоговые совпадения по дате платежа
    matches.sort(key=lambda m: (m.get("payment_date") or "", m.get("bank_payment_id") or 0))

    return {
        "unattached_payments_count": len(unattached_bps),
        "matches_count": len(matches),
        "matches": matches,
    }


@router.post("/{sid}/payment-control/batch-apply-combos")
async def batch_apply_combos(
    sid: int,
    body: _BatchApplyBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Массовое применение подтверждённых комбинаций: объединяет закупки,
    проставляет контрагента и закрывающие документы из платёжки и привязывает оплату."""
    await _get_subsidy_for_write(sid, db, current_user)
    from app.services.payment_smart_combo_matcher import merge_and_attach_combo

    applied = 0
    errors: list[dict] = []
    for item in body.matches:
        try:
            async with db.begin_nested():
                bp = await _get_bank_payment_or_404(item.bank_payment_id, db)
                await merge_and_attach_combo(
                    db,
                    sid,
                    bp,
                    item.purchase_ids,
                    merge_purchases=item.merge_purchases,
                    approve_amount_diff=item.approve_amount_diff,
                )
            applied += 1
        except Exception as e:
            err_msg = getattr(e, "detail", None) or str(e)
            errors.append({
                "bank_payment_id": item.bank_payment_id,
                "error": str(err_msg),
            })

    await db.commit()
    return {"applied": applied, "errors": errors}


# ---------------------------------------------------------------------------
# GET /payment-control/discrepancy-workspace
# POST /payment-control/reconcile-selection
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control/discrepancy-workspace")
async def get_discrepancy_workspace(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Рабочее окно сверки расхождения карточки «Оплачено»:
    показывает позиции закупок, которые отмечены оплаченными в факте, но НЕ
    подтверждены выпиской (а также остальные неоплаченные позиции субсидии),
    и непривязанные платежи из банковской выписки, позволяя выбрать одну или
    несколько позиций и сопоставить их с выгрузкой."""
    import datetime
    import re
    from decimal import Decimal
    from app.models.bank_statement import BankPayment, ExpenseCode
    from app.models.purchase import Purchase
    from app.services.bank_payment_subsidy_scope import subsidy_scope_clause
    from app.services.subsidy_payment_control import EXECUTED_STATUSES
    from app.services.subsidy_paid_breakdown import paid_breakdown_rows, paid_breakdown_by_subsidy
    from app.services.payment_smart_combo_matcher import (
        load_unpaid_candidate_units,
        split_uncontracted_multi_item_purchases,
    )

    subsidy = await _get_subsidy_for_read(sid, db, current_user)

    split_count = await split_uncontracted_multi_item_purchases(db, sid)
    if split_count > 0:
        await db.commit()

    # 1. Данные карточки «Оплачено» (единый источник — ПРАВИЛО №6)
    b_rows = await paid_breakdown_rows(db, [sid])
    b_summary = (await paid_breakdown_by_subsidy(db, [sid])).get(sid, {})
    declared_by_pid: dict[int, Decimal] = {}
    confirmed_by_pid: dict[int, Decimal] = {}
    is_payroll_by_pid: dict[int, bool] = {}
    for r in b_rows:
        pid = r["purchase_id"]
        declared_by_pid[pid] = Decimal(str(r.get("declared") or 0))
        confirmed_by_pid[pid] = Decimal(str(r.get("confirmed") or 0))
        is_payroll_by_pid[pid] = bool(r.get("is_payroll"))

    # 2. Загружаем все неоплаченные/неподтверждённые позиции с полным путём ФЭО в субсидии
    units = await load_unpaid_candidate_units(db, sid)
    p_rows = (await db.execute(
        select(Purchase.id, Purchase.purchase_number, Purchase.status)
        .where(Purchase.subsidy_id == sid)
    )).all()
    pnum_map = {r.id: r.purchase_number for r in p_rows}
    pstatus_map = {r.id: r.status for r in p_rows}

    positions: list[dict] = []
    for u in units:
        if is_payroll_by_pid.get(u.purchase_id):
            continue
        decl_amt = declared_by_pid.get(u.purchase_id, Decimal(0))
        conf_amt = confirmed_by_pid.get(u.purchase_id, Decimal(0))
        disc_amt = max(Decimal(0), decl_amt - conf_amt)
        in_discrepancy = bool(disc_amt > Decimal("0.005") or u.is_declared_paid)
        positions.append({
            "purchase_id": u.purchase_id,
            "purchase_number": pnum_map.get(u.purchase_id),
            "registry_number": u.registry_number,
            "subject": u.subject,
            "feo_category_path": u.feo_category_name,
            "contractor_id": u.contractor_id,
            "contractor_name": u.contractor_name,
            "contractor_inn": u.contractor_inn,
            "item_type": u.item_type,
            "status": pstatus_map.get(u.purchase_id) or ("plan_schedule" if u.is_temp_plan else None),
            "remaining_amount": float(u.amount),
            "declared_paid_amount": float(decl_amt),
            "confirmed_paid_amount": float(conf_amt),
            "discrepancy_amount": float(disc_amt if disc_amt > 0 else u.amount),
            "is_in_discrepancy": in_discrepancy,
            "is_temp_plan": u.is_temp_plan,
            "sheet_ref": u.sheet_ref,
        })

    # Сортируем: сначала позиции, входящие в расхождение карточки «Оплачено», затем остальные
    positions.sort(
        key=lambda x: (
            0 if x["is_in_discrepancy"] else (1 if not x["is_temp_plan"] else 2),
            x["purchase_number"] or abs(x["purchase_id"]),
            abs(x["purchase_id"]),
        )
    )

    # 3. Загружаем непривязанные платежи из банковской выписки
    bp_rows = (await db.execute(
        select(BankPayment)
        .where(subsidy_scope_clause(subsidy))
        .order_by(BankPayment.payment_date.asc(), BankPayment.id.asc())
    )).scalars().all()

    code_rows = (await db.execute(select(ExpenseCode.code, ExpenseCode.name))).all()
    code_names = {r.code: r.name for r in code_rows}

    def _is_procurement_bp(bp: BankPayment) -> tuple[bool, Optional[str]]:
        ec = str(bp.expense_code or "").strip()
        if not ec and bp.purpose_text:
            m = re.search(r';\s*(\d{4,})', bp.purpose_text)
            if m:
                ec = m.group(1)
        ename = code_names.get(ec) if ec else None
        dir_str = f"{ec} — {ename}" if (ec and ename) else (ename or ec or None)
        if ec and not (ec.startswith("02") or ec.startswith("03") or ec.startswith("200") or ec.startswith("300")):
            return False, dir_str
        txt = f"{bp.payee_name or ''} {bp.purpose_text or ''}".lower()
        forbidden = (
            "единый налоговый платеж", "енп", "фнс россии", "отпускные",
            "заработная плата", "заработной платы", "аванс за первую половину",
            "выплата зарплаты", "налог на доходы", "страховые взносы",
            "командирован", "суточн", "выплаты,связанные с командированием",
            "выплаты, связанные с командированием",
        )
        if any(f in txt for f in forbidden):
            return False, dir_str
        return True, dir_str

    bp_ids = [bp.id for bp in bp_rows]
    attached_ids = await _attached_bank_payment_ids_in_subsidy(db, bp_ids, sid)
    unattached_payments: list[dict] = []
    for bp in bp_rows:
        if bp.id in attached_ids:
            continue
        if bp.amount is None or bp.amount <= 0:
            continue
        if (bp.status or "").upper().strip() not in EXECUTED_STATUSES:
            continue
        is_proc, dir_str = _is_procurement_bp(bp)
        if not is_proc:
            continue
        unattached_payments.append({
            "id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "amount": float(bp.amount),
            "payee_name": bp.payee_name,
            "payee_inn": bp.payee_inn,
            "expense_direction": dir_str,
            "purpose_text": bp.purpose_text,
            "contract_number": getattr(bp, "parsed_contract_number", None),
            "contract_date": (
                bp.parsed_contract_date.isoformat()
                if getattr(bp, "parsed_contract_date", None)
                else None
            ),
        })

    declared_total = float(b_summary.get("declared") or 0.0)
    confirmed_total = float(b_summary.get("confirmed") or 0.0)
    return {
        "totals": {
            "declared_total": declared_total,
            "confirmed_total": confirmed_total,
            "discrepancy_total": round(declared_total - confirmed_total, 2),
            "discrepancy_positions_count": sum(1 for p in positions if p["is_in_discrepancy"]),
            "unattached_payments_count": len(unattached_payments),
            "unattached_payments_total": round(sum(p["amount"] for p in unattached_payments), 2),
        },
        "positions": positions,
        "unattached_payments": unattached_payments,
    }


class _ReconcileSelectionBody(BaseModel):
    purchase_ids: list[int]
    bank_payment_ids: list[int]
    merge_purchases: bool = True
    approve_amount_diff: bool = False


@router.post("/{sid}/payment-control/reconcile-selection")
async def reconcile_selected_positions(
    sid: int,
    body: _ReconcileSelectionBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Сопоставляет выбранные пользователем позиции закупок (1 или несколько)
    с выбранными платежами из выписки (1 или несколько траншей)."""
    await _get_subsidy_for_write(sid, db, current_user)
    from decimal import Decimal
    from app.models.purchase import Purchase
    from app.models.contractor import Contractor
    from app.services.contractor_resolve import find_or_create_contractor
    from app.services.payment_smart_combo_matcher import (
        merge_and_attach_combo,
        enrich_purchase_from_bank_payment,
    )
    from app.services.payment_target import PaymentGroup
    from app.services.payment_lookup import attach, PaymentAttachError, ServicePeriodAttachConflict
    from app.services.payment_service_period import service_period_conflict_detail

    pids = list(dict.fromkeys(body.purchase_ids))
    bp_ids = list(dict.fromkeys(body.bank_payment_ids))
    if not pids:
        raise HTTPException(400, "Выберите хотя бы одну позицию закупки")
    if not bp_ids:
        raise HTTPException(400, "Выберите хотя бы один платёж из выписки")

    # Случай 1: Выбрано 1 или несколько позиций и ровно 1 платёж из выписки
    if len(bp_ids) == 1:
        bp = await _get_bank_payment_or_404(bp_ids[0], db)
        result = await merge_and_attach_combo(
            db,
            sid,
            bp,
            pids,
            merge_purchases=body.merge_purchases,
            approve_amount_diff=body.approve_amount_diff,
        )
        await db.commit()
        return result

    # Случай 2: Выбрано несколько платежей выписки (траншей) для одной (или объединённой) закупки
    if len(pids) > 1 and not body.merge_purchases:
        raise HTTPException(
            422,
            "При выборе нескольких платежей выписки и нескольких позиций закупок необходимо объединить позиции в одну закупку.",
        )

    # Сначала привязываем 1-й платёж (он же при необходимости объединит pids в main_purchase)
    first_bp = await _get_bank_payment_or_404(bp_ids[0], db)
    first_res = await merge_and_attach_combo(
        db,
        sid,
        first_bp,
        pids,
        merge_purchases=body.merge_purchases,
        approve_amount_diff=False,
    )
    main_pid = first_res["main_purchase_id"]
    main_p = await db.get(Purchase, main_pid)
    if not main_p:
        raise HTTPException(404, "Целевая закупка не найдена")

    warnings: list[str] = list(first_res.get("warnings") or [])
    for extra_bp_id in bp_ids[1:]:
        bp = await _get_bank_payment_or_404(extra_bp_id, db)
        contractor_obj: Optional[Contractor] = None
        if bp.matched_contractor_id:
            contractor_obj = await db.get(Contractor, bp.matched_contractor_id)
        if not contractor_obj and (bp.payee_inn or bp.payee_name):
            cid = await find_or_create_contractor(db, bp.payee_name, bp.payee_inn)
            if cid:
                contractor_obj = await db.get(Contractor, cid)
                bp.matched_contractor_id = cid

        group = PaymentGroup(
            group_key=f"reconcile-multi-{main_p.id}-{bp.id}",
            subsidy_id=sid,
            registry_number=main_p.registry_number,
            contract_number=main_p.contract_number,
            is_framework=False,
            contractor_id=main_p.contractor_id,
            contractor_inn=bp.payee_inn,
            contractor_name=bp.payee_name,
            goods_amount=Decimal(0),
            services_amount=Decimal(0),
            unspecified_amount=Decimal(0),
            purchase_ids=[main_p.id],
            payments=[],
        )
        bp_amt_dec = Decimal(str(bp.amount or 0))
        try:
            await attach(
                db,
                group,
                [bp.id],
                allocations={main_p.id: bp_amt_dec},
                warnings_out=warnings,
            )
        except ServicePeriodAttachConflict as exc:
            await db.rollback()
            raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
        except PaymentAttachError as exc:
            await db.rollback()
            raise HTTPException(409, str(exc))

        await enrich_purchase_from_bank_payment(db, main_p, bp, bp_amt_dec, contractor_obj=contractor_obj)

    await db.commit()
    return {
        "ok": True,
        "main_purchase_id": main_p.id,
        "registry_number": main_p.registry_number,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# GET /payment-control/find-discrepancy
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control/find-discrepancy")
async def find_payment_discrepancy(
    sid: int,
    amount: float,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Поиск источника расхождения на заданную сумму (например, 28 000 ₽ или 800 ₽):
    1) Составные суммы из 1–4 позиций/закупок (Subset Sum) с ранжированием по
       близости категорий («Очень вероятно» / «Маловероятно»);
    2) Ловушка знака (сумма ÷ 2, например 14 000 ₽ для расхождения 28 000 ₽)."""
    await _get_subsidy_for_read(sid, db, current_user)
    from decimal import Decimal
    from app.services.payment_smart_combo_matcher import (
        load_unpaid_candidate_units,
        find_subset_sum_combinations,
        find_sign_error_candidates,
    )
    target = Decimal(str(abs(amount)))
    units = await load_unpaid_candidate_units(db, sid)
    combos = find_subset_sum_combinations(units, target)
    sign_errors = find_sign_error_candidates(units, target)
    return {
        "target_amount": float(target),
        "combo_suggestions": combos,
        "sign_error_hints": sign_errors,
    }


# ---------------------------------------------------------------------------
# POST /payment-control/bank-payments/{bp_id}/attach
# ---------------------------------------------------------------------------

class _AttachBody(BaseModel):
    purchase_id: int
    fix_amount: Optional[bool] = False


@router.post("/{sid}/payment-control/bank-payments/{bp_id}/attach")
async def attach_bank_payment(
    sid: int,
    bp_id: int,
    body: _AttachBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    subsidy = await _get_subsidy_for_write(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from app.models.purchase import Purchase
    from app.models.contractor import Contractor
    from app.services.contractor_resolve import find_or_create_contractor
    from app.services.payment_smart_combo_matcher import (
        enrich_purchase_from_bank_payment,
        materialize_temp_plan_purchase,
    )
    from decimal import Decimal

    if body.purchase_id < 0:
        purchase = await materialize_temp_plan_purchase(db, sid, body.purchase_id)
    else:
        purchase = await db.get(Purchase, body.purchase_id)
        if not purchase or purchase.subsidy_id != sid:
            raise HTTPException(404, "Закупка не найдена в этой субсидии")

    contractor_obj: Optional[Contractor] = None
    if bp.matched_contractor_id:
        contractor_obj = await db.get(Contractor, bp.matched_contractor_id)
    if not contractor_obj and (bp.payee_inn or bp.payee_name):
        cid = await find_or_create_contractor(db, bp.payee_name, bp.payee_inn)
        if cid:
            contractor_obj = await db.get(Contractor, cid)
            bp.matched_contractor_id = cid
    if contractor_obj and not purchase.contractor_id:
        purchase.contractor_id = contractor_obj.id
        await db.flush()

    fixed_amount: Optional[dict] = None
    if body.fix_amount:
        from app.services.payment_control_fix_amount import fix_purchase_amount, AmountFixNotAllowed
        try:
            fixed_amount = await fix_purchase_amount(db, purchase, Decimal(str(bp.amount or 0)))
        except AmountFixNotAllowed as exc:
            await db.rollback()
            raise HTTPException(422, str(exc))

    from app.services.payment_target import PaymentGroup
    from app.services.payment_lookup import attach, PaymentAttachError, ServicePeriodAttachConflict
    from app.services.payment_service_period import service_period_conflict_detail

    group = PaymentGroup(
        group_key=f"payment-control-{purchase.id}",
        subsidy_id=sid,
        registry_number=purchase.registry_number,
        contract_number=purchase.contract_number,
        is_framework=False,
        contractor_id=purchase.contractor_id,
        contractor_inn=bp.payee_inn,
        contractor_name=bp.payee_name,
        goods_amount=Decimal(0),
        services_amount=Decimal(0),
        unspecified_amount=Decimal(0),
        purchase_ids=[purchase.id],
        payments=[],
    )
    warnings: list[str] = []
    bp_amt_dec = Decimal(str(bp.amount or 0))
    try:
        await attach(
            db, group, [bp.id],
            allocations={purchase.id: bp_amt_dec},
            warnings_out=warnings,
        )
    except ServicePeriodAttachConflict as exc:
        await db.rollback()
        raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
    except PaymentAttachError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))

    await enrich_purchase_from_bank_payment(db, purchase, bp, bp_amt_dec, contractor_obj=contractor_obj)
    await db.commit()
    result = {"ok": True, "warnings": warnings}
    if fixed_amount is not None:
        result["fixed_amount"] = fixed_amount
    return result


# ---------------------------------------------------------------------------
# POST /payment-control/bank-payments/{bp_id}/create-purchase
# ---------------------------------------------------------------------------

class _CreatePurchaseBody(BaseModel):
    feo_category_id: Optional[int] = None


@router.post("/{sid}/payment-control/bank-payments/{bp_id}/create-purchase")
async def create_purchase_from_bank_payment_endpoint(
    sid: int,
    bp_id: int,
    body: _CreatePurchaseBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    subsidy = await _get_subsidy_for_write(sid, db, current_user)
    bp = await _get_bank_payment_or_404(bp_id, db)

    from app.services.purchase_from_bank_payment import create_purchase_from_bank_payment

    try:
        result = await create_purchase_from_bank_payment(
            db, current_user, subsidy, bp, feo_category_id=body.feo_category_id,
        )
    except HTTPException:
        await db.rollback()
        raise

    await db.commit()
    await db.refresh(result.purchase)
    return {
        "purchase_id": result.purchase.id,
        "registry_number": result.purchase.registry_number,
        "warnings": result.warnings,
    }


# ---------------------------------------------------------------------------
# GET /payment-control/export.xlsx
# ---------------------------------------------------------------------------

@router.get("/{sid}/payment-control/export.xlsx")
async def export_payment_control_xlsx(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Контрольный лист в Excel — ПРАВИЛО №6, переиспользует тот же
    build_payment_control(), что и GET /payment-control (см. докстринг
    app/services/payment_control_export.py)."""
    from app.services.subsidy_payment_control import build_payment_control
    from app.services.payment_control_export import build_payment_control_xlsx

    subsidy = await _get_subsidy_for_read(sid, db, current_user)
    data = await build_payment_control(db, subsidy)
    buf = build_payment_control_xlsx(data, subsidy.name or f"Субсидия №{subsidy.id}")

    filename = f"payment-control-{sid}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /statement — лист «Выписка» субсидии
# ---------------------------------------------------------------------------

@router.get("/{sid}/statement")
async def get_subsidy_statement(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.services.subsidy_statement_sheet import build_statement_sheet

    subsidy = await _get_subsidy_for_read(sid, db, current_user)
    return await build_statement_sheet(db, subsidy)
