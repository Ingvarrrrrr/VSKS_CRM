"""Разрезание bank_statements.py (Правило №5, сессия 2026-09-08): реестр
BankPayment — просмотр/матчинг/подтверждение/откат + сверка.

GET    /api/payments/registry                        реестр с фильтрами (+обогащение)
GET    /api/payments/registry/raw-columns             уникальные ключи raw_json
GET    /api/payments/registry/{bp_id}                 одна запись
PATCH  /api/payments/registry/{bp_id}/match           ручная привязка matched_contract_id
GET    /api/payments/reconciliation                   сверка реестр vs привязанные платежи
GET    /api/payments/registry/{bp_id}/match-suggestions  кандидаты матча
POST   /api/payments/registry/{bp_id}/confirm         matched_confirmed=true → создать Payment-ы
POST   /api/payments/registry/{bp_id}/unbind          откат подтверждения

raw-columns регистрируется в этом файле ДО {bp_id} (тот же порядок функций,
что был в исходном bank_statements.py) — иначе Starlette матчит литеральный
путь /registry/raw-columns на catch-all-подобный GET /registry/{bp_id}.

Org-скоуп хелперы (_apply_org_scope/_row_visible/_ACCOUNT_ADMIN_ROLES) — один
источник в bank_statements.py (ядро), здесь только импортируются (Правило №6).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_action
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.models.bank_statement import BankPayment
from app.models.payment import Payment
from app.services.purchase_payments import (
    create_payments_from_bank,
    unlink_bank_payment,
)
from app.schemas.schemas import (
    BankPaymentOut,
    BankPaymentMatchUpdate,
    BankPaymentConfirm,
)
from app.routers.bank_statements import _ACCOUNT_ADMIN_ROLES, _apply_org_scope, _row_visible

router = APIRouter(prefix="/api/payments", tags=["bank-statements"])


# ---------------------------------------------------------------------------
# GET /api/payments/registry — реестр BankPayment с фильтрами
# ---------------------------------------------------------------------------

@router.get("/registry", response_model=List[BankPaymentOut])
async def list_bank_payment_registry(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    matched: Optional[bool] = Query(None),
    confirmed: Optional[bool] = Query(None),
    payee_inn: Optional[str] = Query(None),
    import_id: Optional[int] = Query(None, description="Фильтр по ID прогона импорта"),
    disposition: Optional[str] = Query(
        None,
        description="Этап 7в: 'free' — не разнесённые ни на одну закупку, "
                     "'attached' — уже разнесённые (есть Payment с matched_confirmed=true).",
    ),
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.registry_view")),
):
    from app.models.organization import Organization
    from app.models.contractor import Contractor as ContractorModel
    from app.models.contract import Contract as ContractModel
    from app.models.subsidy import Subsidy as SubsidyModel
    from app.models.purchase import Purchase as PurchaseModel
    from app.models.expense_code import ExpenseCode

    filters = []
    if import_id is not None:
        filters.append(BankPayment.import_id == import_id)
    if date_from:
        filters.append(BankPayment.payment_date >= date_from)
    if date_to:
        filters.append(BankPayment.payment_date <= date_to)
    if status:
        filters.append(BankPayment.status == status)
    if matched is not None:
        if matched:
            filters.append(BankPayment.matched_contract_id.isnot(None))
        else:
            filters.append(BankPayment.matched_contract_id.is_(None))
    if confirmed is not None:
        filters.append(BankPayment.matched_confirmed == confirmed)
    if payee_inn:
        filters.append(BankPayment.payee_inn == payee_inn)

    q = select(BankPayment)
    if filters:
        q = q.where(and_(*filters))
    if disposition in ("free", "attached"):
        # Этап 7в: «разнесён» = есть хотя бы один Payment с этим bank_payment_id
        # и matched_confirmed=true (см. app/services/payment_lookup.py::attach —
        # именно так туда попадают Payment-ы, созданные новым групповым разнесением;
        # ручное подтверждение через /registry/{id}/confirm тоже ставит этот флаг).
        attached_subq = select(Payment.bank_payment_id).where(
            Payment.matched_confirmed == True,  # noqa: E712
            Payment.bank_payment_id.isnot(None),
        )
        if disposition == "attached":
            q = q.where(BankPayment.id.in_(attached_subq))
        else:
            q = q.where(BankPayment.id.notin_(attached_subq))
    # Этап 1: org-скоуп по прямой BankPayment.org_id (не зависит от матчера —
    # проставляется при импорте по basis_doc_number). Это ОСНОВНОЙ гейт SaaS-
    # изоляции; org_id IS NULL (соглашение не опознано) видят только роли
    # уровня админа аккаунта.
    q = _apply_org_scope(q, current_user, BankPayment.org_id)
    # Двухуровневая видимость по вкладке «Реестр платежей» — сохранена как
    # дополнительное сужение для персональных грантов на конкретную субсидию
    # (see get_visible_subsidy_ids). Unmatched (matched_subsidy_id IS NULL) всегда
    # видны на этом уровне — конкретную org уже отфильтровали строкой выше.
    vis = await get_visible_subsidy_ids(current_user, db, "payment_registry")
    if vis is not None:
        q = q.where(
            or_(
                BankPayment.matched_subsidy_id.is_(None),
                BankPayment.matched_subsidy_id.in_(vis),
            )
        )
    q = q.order_by(BankPayment.payment_date.desc()).limit(limit)

    result = await db.execute(q)
    rows = result.scalars().all()

    # Обогащаем payer_name_resolved / payee_name_resolved по ИНН (lookup Organization → Contractor)
    # Кеш ИНН → имя внутри запроса, чтобы не гонять N запросов на одинаковые ИНН
    inn_name_cache: dict[str, str] = {}

    async def _resolve_inn(inn: Optional[str]) -> Optional[str]:
        if not inn:
            return None
        if inn in inn_name_cache:
            return inn_name_cache[inn]
        # Сначала Organization
        org_q = await db.execute(select(Organization).where(Organization.inn == inn).limit(1))
        org = org_q.scalars().first()
        if org:
            inn_name_cache[inn] = org.name
            return org.name
        # Затем Contractor
        contr_q = await db.execute(select(ContractorModel).where(ContractorModel.inn == inn).limit(1))
        c = contr_q.scalars().first()
        if c:
            inn_name_cache[inn] = c.name
            return c.name
        inn_name_cache[inn] = None  # type: ignore[assignment]
        return None

    # 27.4-23: batch-обогащение match-колонок именами/предметами/суммами
    contractor_ids = {bp.matched_contractor_id for bp in rows if bp.matched_contractor_id}
    subsidy_ids = {bp.matched_subsidy_id for bp in rows if bp.matched_subsidy_id}
    contract_ids = {bp.matched_contract_id for bp in rows if bp.matched_contract_id}
    purchase_ids = {bp.matched_purchase_id for bp in rows if bp.matched_purchase_id}

    contractor_map: dict[int, str] = {}
    if contractor_ids:
        r = await db.execute(select(ContractorModel.id, ContractorModel.name).where(ContractorModel.id.in_(contractor_ids)))
        contractor_map = {row[0]: row[1] for row in r.all()}

    subsidy_map: dict[int, str] = {}
    if subsidy_ids:
        r = await db.execute(select(SubsidyModel.id, SubsidyModel.name).where(SubsidyModel.id.in_(subsidy_ids)))
        subsidy_map = {row[0]: row[1] for row in r.all()}

    contract_map: dict[int, dict] = {}
    if contract_ids:
        r = await db.execute(
            select(ContractModel.id, ContractModel.number, ContractModel.date, ContractModel.subject, ContractModel.max_amount)
            .where(ContractModel.id.in_(contract_ids))
        )
        for row in r.all():
            contract_map[row[0]] = {
                "number": row[1],
                "date": row[2].isoformat() if row[2] else None,
                "subject": row[3],
                "max_amount": float(row[4]) if row[4] is not None else None,
            }

    purchase_map: dict[int, dict] = {}
    if purchase_ids:
        r = await db.execute(
            select(
                PurchaseModel.id,
                PurchaseModel.purchase_number,
                PurchaseModel.item_name,
                PurchaseModel.contract_price,
                PurchaseModel.planned_total_price,
            ).where(PurchaseModel.id.in_(purchase_ids))
        )
        for row in r.all():
            amt = row[3] if row[3] is not None else row[4]
            purchase_map[row[0]] = {
                "purchase_number": row[1],
                "item_name": row[2],
                "amount": float(amt) if amt is not None else None,
            }

    # Этап 7в: расшифровка кода расходов из справочника.
    expense_codes_present = {bp.expense_code for bp in rows if bp.expense_code}
    expense_code_names: dict[str, str] = {}
    if expense_codes_present:
        r = await db.execute(
            select(ExpenseCode.code, ExpenseCode.name).where(ExpenseCode.code.in_(expense_codes_present))
        )
        expense_code_names = {row[0]: row[1] for row in r.all()}

    # Этап 7в: «Куда отнесён» — Payment-записи (matched_confirmed=true), созданные
    # групповым разнесением (app/services/payment_lookup.py::attach) ИЛИ ручным
    # подтверждением (/registry/{id}/confirm). Один bank_payment может быть разнесён
    # на НЕСКОЛЬКО закупок сразу (allocations), поэтому список, а не одно значение.
    attached_by_bp: dict[int, list[dict]] = {}
    bp_ids_all = [bp.id for bp in rows]
    if bp_ids_all:
        pay_r = await db.execute(
            select(Payment.bank_payment_id, Payment.purchase_id, Payment.amount, Payment.basis_label)
            .where(Payment.bank_payment_id.in_(bp_ids_all), Payment.matched_confirmed == True)  # noqa: E712
        )
        pay_rows = pay_r.all()
        attach_purchase_ids = {row[1] for row in pay_rows if row[1]}
        attach_purchase_info: dict[int, dict] = {}
        if attach_purchase_ids:
            apr = await db.execute(
                select(PurchaseModel.id, PurchaseModel.purchase_number, PurchaseModel.item_name, PurchaseModel.subject)
                .where(PurchaseModel.id.in_(attach_purchase_ids))
            )
            attach_purchase_info = {row[0]: row for row in apr.all()}
        for bp_id, purchase_id, amount, basis_label in pay_rows:
            if not purchase_id:
                continue
            info = attach_purchase_info.get(purchase_id)
            attached_by_bp.setdefault(bp_id, []).append({
                "purchase_id": purchase_id,
                "purchase_number": info[1] if info else None,
                "item_name": (info[2] or info[3]) if info else None,
                "amount": float(amount) if amount is not None else None,
                "basis_label": basis_label,
            })

    out = []
    for bp in rows:
        d = BankPaymentOut.model_validate(bp).model_dump()
        d["payer_name_resolved"] = await _resolve_inn(bp.payer_inn)
        d["payee_name_resolved"] = await _resolve_inn(bp.payee_inn)
        # 27.4-23: match-enrichment
        d["matched_contractor_name"] = contractor_map.get(bp.matched_contractor_id) if bp.matched_contractor_id else None
        d["matched_subsidy_name"] = subsidy_map.get(bp.matched_subsidy_id) if bp.matched_subsidy_id else None
        c = contract_map.get(bp.matched_contract_id) if bp.matched_contract_id else None
        d["matched_contract_number"] = c["number"] if c else None
        d["matched_contract_subject"] = c["subject"] if c else None
        d["matched_contract_date"] = c["date"] if c else None
        p = purchase_map.get(bp.matched_purchase_id) if bp.matched_purchase_id else None
        d["matched_purchase_number"] = p["purchase_number"] if p else None
        d["matched_purchase_item_name"] = p["item_name"] if p else None
        d["matched_purchase_amount"] = p["amount"] if p else None
        # Этап 7в
        d["expense_code_name"] = expense_code_names.get(bp.expense_code) if bp.expense_code else None
        d["attached_purchases"] = attached_by_bp.get(bp.id, [])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# GET /api/payments/registry/raw-columns — уникальные ключи raw_json
# ---------------------------------------------------------------------------

@router.get("/registry/raw-columns")
async def get_raw_columns(
    import_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: bool = Depends(require_action("payment.registry_view")),
):
    """Возвращает список уникальных ключей из raw_json BankPayment записей.

    Если import_id задан — только этот импорт. Иначе UNION по всем.
    Для каждого ключа считается count записей где он встречается.
    """
    from sqlalchemy import text

    org_ids = get_org_filter(current_user)
    org_clause = ""
    params: dict = {}
    if org_ids is not None:
        if current_user.role in _ACCOUNT_ADMIN_ROLES:
            org_clause = " AND (org_id = ANY(:org_ids) OR org_id IS NULL)"
        else:
            org_clause = " AND org_id = ANY(:org_ids)"
        params["org_ids"] = list(org_ids)

    if import_id is not None:
        params["import_id"] = import_id
        sql = text(f"""
            SELECT k AS key, COUNT(*) AS cnt
            FROM bank_payments,
                 LATERAL jsonb_object_keys(raw_json) AS k
            WHERE import_id = :import_id AND raw_json IS NOT NULL{org_clause}
            GROUP BY k
            ORDER BY cnt DESC, k ASC
        """)
        result = await db.execute(sql, params)
    else:
        sql = text(f"""
            SELECT k AS key, COUNT(*) AS cnt
            FROM bank_payments,
                 LATERAL jsonb_object_keys(raw_json) AS k
            WHERE raw_json IS NOT NULL{org_clause}
            GROUP BY k
            ORDER BY cnt DESC, k ASC
        """)
        result = await db.execute(sql, params)

    return [{"key": row[0], "count": row[1]} for row in result.fetchall()]


# ---------------------------------------------------------------------------
# GET /api/payments/registry/{bp_id} — получить одну запись BankPayment
# ---------------------------------------------------------------------------

@router.get("/registry/{bp_id}", response_model=BankPaymentOut)
async def get_bank_payment(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.registry_view")),
):
    """Получить одну запись BankPayment по ID (для PaymentMatchDialog)."""
    bp = await db.get(BankPayment, bp_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    if not _row_visible(current_user, bp.org_id):
        raise HTTPException(status_code=404, detail="Платёж не найден")
    return bp


# ---------------------------------------------------------------------------
# PATCH /api/payments/registry/{bp_id}/match — ручная привязка
# ---------------------------------------------------------------------------

@router.patch("/registry/{bp_id}/match", response_model=BankPaymentOut)
async def match_bank_payment(
    bp_id: int,
    body: BankPaymentMatchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.confirm")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
        raise HTTPException(status_code=404, detail="BankPayment не найден")
    if not _row_visible(current_user, bp.org_id):
        raise HTTPException(status_code=404, detail="BankPayment не найден")
    if bp.matched_confirmed:
        raise HTTPException(status_code=409, detail="Платёж уже подтверждён — сначала откатите (unbind)")

    if body.contract_id is not None:
        bp.matched_contract_id = body.contract_id
        # Если contractor_id не передан явно — попробуем вытащить из контракта
        if body.contractor_id is not None:
            bp.matched_contractor_id = body.contractor_id
        else:
            from app.models.contract import Contract
            c_result = await db.execute(select(Contract).where(Contract.id == body.contract_id))
            contract = c_result.scalar_one_or_none()
            if contract:
                bp.matched_contractor_id = contract.contractor_id

    elif body.contractor_id is not None:
        bp.matched_contractor_id = body.contractor_id

    await db.commit()
    await db.refresh(bp)
    return bp


# ---------------------------------------------------------------------------
# GET /api/payments/reconciliation — сверка реестр vs привязанные платежи
# ---------------------------------------------------------------------------

@router.get("/reconciliation")
async def reconciliation(
    import_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.confirm")),
    __=Depends(require_action("payment.registry_view")),
):
    """27.4-21: построчная сверка по payment_number.

    Возвращает список строк с status:
    - match (зелёный): есть в реестре и в закупках, суммы совпадают
    - amount_mismatch (красный): есть в обоих, суммы разные
    - registry_only (красный): orphan — есть в реестре, нигде не привязан
    - purchases_only (жёлтый): привязан к закупке и подтверждено выпиской, в реестре
      этого прогона отсутствует
    - declared_unconfirmed (жёлтый, владелец 2026-08-19): «у нас отмечено, в
      выписке нет» — ручной платёж, который человек считает прошедшим, но
      казначейство его ещё не подтвердило
    """
    from app.services.payment_reconciliation import build_reconciliation
    org_ids = get_org_filter(current_user)
    rows = await build_reconciliation(
        db, import_id=import_id,
        org_ids=org_ids,
        include_null_org=current_user.role in _ACCOUNT_ADMIN_ROLES,
    )
    return {
        "import_id": import_id,
        "total": len(rows),
        "match_count": sum(1 for r in rows if r["status"] == "match"),
        "mismatch_count": sum(1 for r in rows if r["status"] == "amount_mismatch"),
        "registry_only_count": sum(1 for r in rows if r["status"] == "registry_only"),
        "purchases_only_count": sum(1 for r in rows if r["status"] == "purchases_only"),
        "declared_unconfirmed_count": sum(1 for r in rows if r["status"] == "declared_unconfirmed"),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# GET /api/payments/registry/{bp_id}/match-suggestions — кандидаты для матчинга
# ---------------------------------------------------------------------------

@router.get("/registry/{bp_id}/match-suggestions")
async def match_suggestions(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.confirm")),
):
    """27.4-20: ранжированный список кандидатов матча (exact / subset-sum /
    delivered / split / text). Frontend показывает топ-N с preselected #1
    для подтверждения одним кликом."""
    bp = (await db.execute(select(BankPayment).where(BankPayment.id == bp_id))).scalar_one_or_none()
    if not bp:
        raise HTTPException(404, "BankPayment не найден")
    if not _row_visible(current_user, bp.org_id):
        raise HTTPException(404, "BankPayment не найден")
    from app.services.match_candidates import build_candidates
    candidates = await build_candidates(bp, db)
    return {
        "bank_payment_id": bp.id,
        "amount": float(bp.amount) if bp.amount else None,
        "payee_name": bp.payee_name,
        "payee_inn": bp.payee_inn,
        "purpose_text": bp.purpose_text,
        "matched_contract_id": bp.matched_contract_id,
        "matched_contractor_id": bp.matched_contractor_id,
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# POST /api/payments/registry/{bp_id}/confirm — подтвердить матч → создать Payment-ы
# ---------------------------------------------------------------------------

@router.post("/registry/{bp_id}/confirm")
async def confirm_bank_payment(
    bp_id: int,
    body: BankPaymentConfirm,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.confirm")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
        raise HTTPException(status_code=404, detail="BankPayment не найден")
    if not _row_visible(current_user, bp.org_id):
        raise HTTPException(status_code=404, detail="BankPayment не найден")
    if not bp.matched_contract_id:
        raise HTTPException(status_code=422, detail="BankPayment не привязан к контракту — выполните /match сначала")
    if bp.matched_confirmed:
        raise HTTPException(status_code=409, detail="Платёж уже подтверждён")
    if not body.purchase_ids:
        raise HTTPException(status_code=422, detail="Список purchase_ids не может быть пустым")

    created_payments = await create_payments_from_bank(db, bp.id, body.purchase_ids)
    bp.matched_confirmed = True
    await db.commit()
    await db.refresh(bp)

    return {
        "bank_payment": BankPaymentOut.model_validate(bp),
        "payments_created": len(created_payments),
        "payment_ids": [p.id for p in created_payments],
    }


# ---------------------------------------------------------------------------
# POST /api/payments/registry/{bp_id}/unbind — откат подтверждения
# ---------------------------------------------------------------------------

@router.post("/registry/{bp_id}/unbind", response_model=BankPaymentOut)
async def unbind_bank_payment(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.unbind")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
        raise HTTPException(status_code=404, detail="BankPayment не найден")
    if not _row_visible(current_user, bp.org_id):
        raise HTTPException(status_code=404, detail="BankPayment не найден")

    await unlink_bank_payment(db, bp_id)
    bp.matched_confirmed = False
    await db.commit()
    await db.refresh(bp)
    return bp
