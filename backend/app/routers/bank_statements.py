"""Phase 22 — Bank Statements Import router.

POST   /api/payments/imports                upload xlsx → парсинг → bank_payments
GET    /api/payments/imports                список прогонов (журнал)
GET    /api/payments/imports/{id}           детали прогона + список строк
DELETE /api/payments/imports/{id}           откат прогона (cascade BankPayment + Payment)

GET    /api/payments/registry               общий реестр BankPayment с фильтрами
PATCH  /api/payments/registry/{id}/match    ручная привязка matched_contract_id
POST   /api/payments/registry/{id}/confirm  matched_confirmed=true → создать N Payment + recompute
POST   /api/payments/registry/{id}/unbind   удалить все linked Payment + recompute (откат подтверждения)
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_action, require_tab
from app.auth.jwt import get_current_user
from app.models.bank_statement import BankStatementImport, BankPayment
from app.models.payment import Payment
from app.services.bank_statement_parser import parse_workbook
# These services are created in Plan 22-03 (parallel wave) — they will exist at deploy time.
from app.services.payment_matcher import match_all_in_import  # noqa: F401
from app.services.purchase_payments import (  # noqa: F401
    create_payments_from_bank,
    unlink_bank_payment,
)
from app.schemas.schemas import (
    BankStatementImportOut,
    BankPaymentOut,
    BankPaymentMatchUpdate,
    BankPaymentConfirm,
)

router = APIRouter(prefix="/api/payments", tags=["bank-statements"])


# ---------------------------------------------------------------------------
# POST /api/payments/imports — загрузить xlsx
# ---------------------------------------------------------------------------

@router.post("/imports", response_model=BankStatementImportOut)
async def upload_bank_statement(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Query(None, description="Имя листа xlsx"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_action("payment.import")),
):
    """Парсит xlsx-выписку и создаёт BankPayment строки."""
    fname = file.filename or ""
    if not fname.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")

    # Создаём запись прогона
    import_run = BankStatementImport(
        status="processing",
        file_name=fname,
        sheet_name=sheet_name,
    )
    db.add(import_run)
    await db.flush()  # get import_run.id

    rows_total = 0
    rows_imported = 0
    rows_skipped = 0
    rows_dup = 0

    try:
        active_sheet, parsed_rows = parse_workbook(content, sheet_name)
        import_run.sheet_name = active_sheet
        rows_total = len(parsed_rows)

        for pr in parsed_rows:
            if pr.skip_reason:
                rows_skipped += 1
                continue

            bp = BankPayment(
                import_id=import_run.id,
                payment_number=pr.payment_number,
                payment_date=pr.payment_date,
                execution_datetime=pr.execution_datetime,
                status=pr.status,
                amount=pr.amount,
                payer_inn=pr.payer_inn,
                payer_kpp=pr.payer_kpp,
                payer_name=pr.payer_name,
                payer_account=pr.payer_account,
                payee_inn=pr.payee_inn,
                payee_kpp=pr.payee_kpp,
                payee_name=pr.payee_name,
                payee_account=pr.payee_account,
                payee_bik=pr.payee_bik,
                payee_bank=pr.payee_bank,
                purpose_text=pr.purpose_text,
                parsed_contract_number=pr.parsed_contract_number,
                parsed_contract_date=pr.parsed_contract_date,
                parsed_kbk=pr.parsed_kbk,
                parsed_documents=pr.parsed_documents,
                basis_doc_text=pr.basis_doc_text,
                basis_doc_number=pr.basis_doc_number,
                basis_doc_date=pr.basis_doc_date,
                subsidy_code=pr.subsidy_code,
                raw_json=pr.raw_json,
                source_row_hash=pr.source_row_hash,
                matched_confirmed=False,
            )
            db.add(bp)
            try:
                await db.flush()
                rows_imported += 1
            except IntegrityError:
                await db.rollback()
                rows_dup += 1
                continue

        # Авто-матч
        rows_matched = 0
        rows_unmatched = 0
        try:
            match_counts = await match_all_in_import(db, import_run.id)
            rows_matched = match_counts.get("matched_contract", 0)
            rows_unmatched = match_counts.get("total", rows_imported) - rows_matched
        except Exception:
            # Если matcher ещё не задеплоен — не падаем
            rows_unmatched = rows_imported

        import_run.rows_total = rows_total
        import_run.rows_imported = rows_imported
        import_run.rows_skipped = rows_skipped
        import_run.rows_dup = rows_dup
        import_run.rows_matched = rows_matched
        import_run.rows_unmatched = rows_unmatched
        import_run.status = "done"

    except HTTPException:
        raise
    except Exception as exc:
        import_run.status = "error"
        import_run.error_message = str(exc)[:1000]
        import_run.rows_total = rows_total
        import_run.rows_imported = rows_imported
        import_run.rows_skipped = rows_skipped
        import_run.rows_dup = rows_dup

    await db.commit()
    await db.refresh(import_run)
    return import_run


# ---------------------------------------------------------------------------
# GET /api/payments/imports — журнал прогонов
# ---------------------------------------------------------------------------

@router.get("/imports", response_model=List[BankStatementImportOut])
async def list_bank_imports(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("payment_registry")),
):
    result = await db.execute(
        select(BankStatementImport).order_by(BankStatementImport.id.desc()).limit(50)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /api/payments/imports/{import_id} — детали прогона
# ---------------------------------------------------------------------------

@router.get("/imports/{import_id}", response_model=BankStatementImportOut)
async def get_bank_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("payment_registry")),
):
    result = await db.execute(
        select(BankStatementImport).where(BankStatementImport.id == import_id)
    )
    imp = result.scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    return imp


# ---------------------------------------------------------------------------
# DELETE /api/payments/imports/{import_id} — откат прогона
# ---------------------------------------------------------------------------

@router.delete("/imports/{import_id}")
async def delete_bank_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_action("payment.import")),
):
    result = await db.execute(
        select(BankStatementImport).where(BankStatementImport.id == import_id)
    )
    imp = result.scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")

    # Открепляем Payment-ы связанные с BankPayment этого прогона
    bp_result = await db.execute(
        select(BankPayment).where(BankPayment.import_id == import_id)
    )
    bank_payments = bp_result.scalars().all()

    for bp in bank_payments:
        try:
            await unlink_bank_payment(db, bp.id)
        except Exception:
            pass

    await db.delete(imp)  # CASCADE удалит BankPayment
    await db.commit()
    return {"ok": True, "deleted_import_id": import_id}


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
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("payment_registry")),
):
    from app.models.organization import Organization
    from app.models.contractor import Contractor as ContractorModel

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

    out = []
    for bp in rows:
        d = BankPaymentOut.model_validate(bp).model_dump()
        d["payer_name_resolved"] = await _resolve_inn(bp.payer_inn)
        d["payee_name_resolved"] = await _resolve_inn(bp.payee_inn)
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
    _: bool = Depends(require_tab("payment_registry")),
):
    """Возвращает список уникальных ключей из raw_json BankPayment записей.

    Если import_id задан — только этот импорт. Иначе UNION по всем.
    Для каждого ключа считается count записей где он встречается.
    """
    from sqlalchemy import text

    if import_id is not None:
        sql = text("""
            SELECT k AS key, COUNT(*) AS cnt
            FROM bank_payments,
                 LATERAL jsonb_object_keys(raw_json) AS k
            WHERE import_id = :import_id AND raw_json IS NOT NULL
            GROUP BY k
            ORDER BY cnt DESC, k ASC
        """)
        result = await db.execute(sql, {"import_id": import_id})
    else:
        sql = text("""
            SELECT k AS key, COUNT(*) AS cnt
            FROM bank_payments,
                 LATERAL jsonb_object_keys(raw_json) AS k
            WHERE raw_json IS NOT NULL
            GROUP BY k
            ORDER BY cnt DESC, k ASC
        """)
        result = await db.execute(sql)

    return [{"key": row[0], "count": row[1]} for row in result.fetchall()]


# ---------------------------------------------------------------------------
# GET /api/payments/registry/{bp_id} — получить одну запись BankPayment
# ---------------------------------------------------------------------------

@router.get("/registry/{bp_id}", response_model=BankPaymentOut)
async def get_bank_payment(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab("payment_registry")),
):
    """Получить одну запись BankPayment по ID (для PaymentMatchDialog)."""
    bp = await db.get(BankPayment, bp_id)
    if not bp:
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
    _=Depends(require_action("payment.confirm")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
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
# POST /api/payments/registry/{bp_id}/confirm — подтвердить матч → создать Payment-ы
# ---------------------------------------------------------------------------

@router.post("/registry/{bp_id}/confirm")
async def confirm_bank_payment(
    bp_id: int,
    body: BankPaymentConfirm,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_action("payment.confirm")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
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
# POST /api/payments/imports/{import_id}/rematch — перематч строк прогона
# ---------------------------------------------------------------------------

@router.post("/imports/{import_id}/rematch", dependencies=[Depends(require_action("payment.import"))])
async def rematch_import(
    import_id: int,
    only_unmatched: bool = True,
    reparse: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Перезапустить auto_match для всех (или только unmatched) платежей данного импорта.

    Используется когда:
    - Изменились настройки субсидий (basis_doc_number/date)
    - Изменилась логика matcher
    - Загружены данные но контракты ещё не созданы в системе

    reparse=true — пересчитать parsed_documents из raw_json/purpose_text (нужно после
    смены regex, например разделения agreements от contracts).
    """
    from app.services.payment_matcher import auto_match
    from app.services.bank_statement_parser import extract_all_documents

    q = select(BankPayment).where(BankPayment.import_id == import_id)
    if only_unmatched:
        q = q.where(BankPayment.matched_contract_id.is_(None))

    result = await db.execute(q)
    rows = result.scalars().all()

    counts = {'total': len(rows), 'matched_contract': 0, 'matched_subsidy': 0, 'matched_purchase': 0}
    for bp in rows:
        if not only_unmatched:
            bp.matched_contractor_id = None
            bp.matched_subsidy_id = None
            bp.matched_contract_id = None
            bp.matched_purchase_id = None
        if reparse:
            from app.services.bank_statement_parser import reparse_bank_payment_typed
            reparse_bank_payment_typed(bp)
        await auto_match(bp, db)
        if bp.matched_contract_id:
            counts['matched_contract'] += 1
        if bp.matched_subsidy_id:
            counts['matched_subsidy'] += 1
        if bp.matched_purchase_id:
            counts['matched_purchase'] += 1

    await db.commit()
    return counts


# ---------------------------------------------------------------------------
# GET /api/payments/imports/{import_id}/diag — diagnostic: показать raw_json первой строки
# Без auth — только для отладки рассинхрона HEADER_MAP vs реального формата выписки.
# ---------------------------------------------------------------------------

@router.get("/imports/{import_id}/diag")
async def diag_import(import_id: int, db: AsyncSession = Depends(get_db)):
    """Возвращает первую строку BankPayment этого импорта: raw_json (все ключи и значения)
    + typed-поля. Помогает понять какие headers попали из xlsx в БД и почему HEADER_MAP их не находит.
    """
    q = await db.execute(
        select(BankPayment).where(BankPayment.import_id == import_id).limit(1)
    )
    bp = q.scalar_one_or_none()
    if not bp:
        return {"error": "no rows for this import_id"}

    # Вернём ключи raw_json + sample значения (укоротим длинные строки)
    raw_keys = sorted(list((bp.raw_json or {}).keys()))
    raw_sample = {}
    for k, v in (bp.raw_json or {}).items():
        s = str(v) if v is not None else None
        if s and len(s) > 200:
            s = s[:200] + "..."
        raw_sample[k] = s

    # Подсчёт строк с NULL payment_date в этом импорте
    from sqlalchemy import func as _func
    null_count = (await db.execute(
        select(_func.count()).select_from(BankPayment)
        .where(BankPayment.import_id == import_id)
        .where(BankPayment.payment_date.is_(None))
    )).scalar() or 0
    total_count = (await db.execute(
        select(_func.count()).select_from(BankPayment)
        .where(BankPayment.import_id == import_id)
    )).scalar() or 0

    return {
        "import_id": import_id,
        "rows_total": total_count,
        "rows_with_null_payment_date": null_count,
        "first_row": {
            "id": bp.id,
            "payment_number": bp.payment_number,
            "payment_date": bp.payment_date.isoformat() if bp.payment_date else None,
            "purpose_text": bp.purpose_text,
            "amount": str(bp.amount) if bp.amount else None,
            "parsed_contract_number": bp.parsed_contract_number,
            "parsed_contract_date": bp.parsed_contract_date.isoformat() if bp.parsed_contract_date else None,
            "parsed_documents": bp.parsed_documents,
            "raw_json_keys": raw_keys,
            "raw_json_sample": raw_sample,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/payments/imports/{import_id}/reparse-rows — пересборка typed полей из raw_json
# ---------------------------------------------------------------------------

@router.post("/imports/{import_id}/reparse-rows", dependencies=[Depends(require_action("payment.import"))])
async def reparse_existing_rows(
    import_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Пересобрать ВСЕ typed поля BankPayment из сохранённого raw_json без повторного импорта файла.

    Полезно когда парсер был исправлен (например найдена строка заголовков),
    а 76 уже импортированных записей имеют NULL во всех полях, так как при
    исходном импорте header_row=1 дал мусорные ключи и HEADER_MAP ничего не нашёл.
    """
    from app.services.bank_statement_parser import reparse_bank_payment_typed

    q = await db.execute(select(BankPayment).where(BankPayment.import_id == import_id))
    rows = q.scalars().all()
    fixed = 0

    for bp in rows:
        if not bp.raw_json:
            continue
        reparse_bank_payment_typed(bp)
        fixed += 1

    await db.commit()
    return {"updated": fixed}


# ---------------------------------------------------------------------------
# POST /api/payments/registry/{bp_id}/unbind — откат подтверждения
# ---------------------------------------------------------------------------

@router.post("/registry/{bp_id}/unbind", response_model=BankPaymentOut)
async def unbind_bank_payment(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_action("payment.unbind")),
):
    result = await db.execute(select(BankPayment).where(BankPayment.id == bp_id))
    bp = result.scalar_one_or_none()
    if not bp:
        raise HTTPException(status_code=404, detail="BankPayment не найден")

    await unlink_bank_payment(db, bp_id)
    bp.matched_confirmed = False
    await db.commit()
    await db.refresh(bp)
    return bp
