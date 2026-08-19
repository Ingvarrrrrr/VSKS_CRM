"""Phase 22 — Bank Statements Import router. Этап 1 (2026-08-19): org-скоуп,
subsidy_id/external_doc_id, автоудаление успешной партии — см. миграцию
y2z3a4b5c6d7 и docstring там для полного описания.

POST   /api/payments/imports                upload xlsx → парсинг → bank_payments;
                                             успешная ('done') партия удаляется
                                             автоматически, платежи остаются
GET    /api/payments/imports                список прогонов (журнал; только 'error'
                                             партии живут долго, 'done' самоудаляются)
GET    /api/payments/imports/{id}           детали прогона + список строк
DELETE /api/payments/imports/{id}           удаляет партию; ?with_payments=true —
                                             старое поведение (cascade BankPayment + Payment)

GET    /api/payments/registry               общий реестр BankPayment с фильтрами
PATCH  /api/payments/registry/{id}/match    ручная привязка matched_contract_id
POST   /api/payments/registry/{id}/confirm  matched_confirmed=true → создать N Payment + recompute
POST   /api/payments/registry/{id}/unbind   удалить все linked Payment + recompute (откат подтверждения)
"""
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_action
from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.models.bank_statement import BankStatementImport, BankPayment
from app.models.payment import Payment
from app.services.bank_statement_parser import parse_workbook
# These services are created in Plan 22-03 (parallel wave) — they will exist at deploy time.
from app.services.payment_matcher import match_all_in_import, resolve_subsidy  # noqa: F401
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
# Этап 1 — SaaS-изоляция: org-скоуп для bank_payments / bank_statement_imports.
#
# Роли уровня «админ аккаунта» (admin/account_owner/superadmin — весь аккаунт,
# в отличие от org_admin, который управляет одной орг) видят ещё и строки с
# org_id IS NULL (субсидия не опознана при импорте — их нужно кому-то разобрать).
# Остальные роли org_id IS NULL не видят вовсе.
# ---------------------------------------------------------------------------

_ACCOUNT_ADMIN_ROLES = ("admin", "account_owner", "superadmin")


def _apply_org_scope(q, current_user, org_col):
    """Применяет org-фильтр к запросу по колонке org_col (BankPayment.org_id или
    BankStatementImport.org_id). None от get_org_filter — фильтр не нужен (SaaS)."""
    org_ids = get_org_filter(current_user)
    if org_ids is None:
        return q
    if current_user.role in _ACCOUNT_ADMIN_ROLES:
        return q.where(or_(org_col.in_(org_ids), org_col.is_(None)))
    return q.where(org_col.in_(org_ids))


def _row_visible(current_user, org_id: Optional[int]) -> bool:
    """Та же логика _apply_org_scope, но для одной уже загруженной строки."""
    org_ids = get_org_filter(current_user)
    if org_ids is None:
        return True
    if org_id is None:
        return current_user.role in _ACCOUNT_ADMIN_ROLES
    return org_id in org_ids


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
    rows_no_subsidy = 0
    import_org_id: Optional[int] = None  # первая опознанная орг прогона — на весь import_run

    try:
        active_sheet, parsed_rows = parse_workbook(content, sheet_name)
        import_run.sheet_name = active_sheet
        rows_total = len(parsed_rows)

        # Дедуп по external_doc_id — устойчивый natural key («Идентификатор
        # документа»), в отличие от source_row_hash не требует побайтового
        # совпадения строки. Если идентификатор уже есть в БД (или дважды
        # встречается внутри этого же файла) — строка пропускается ЦЕЛИКОМ,
        # существующая запись НЕ обновляется (уникальный идентификатор = платёж
        # уже загружен, перезаписи не нужно).
        ext_ids_in_file = {pr.external_doc_id for pr in parsed_rows if pr.external_doc_id}
        seen_external_ids: set = set()
        if ext_ids_in_file:
            existing_rows = (await db.execute(
                select(BankPayment.external_doc_id).where(
                    BankPayment.external_doc_id.in_(ext_ids_in_file)
                )
            )).scalars().all()
            seen_external_ids.update(x for x in existing_rows if x)

        for pr in parsed_rows:
            # Строки с отклонёнными/аннулированными статусами теперь ИМПОРТИРУЮТСЯ
            # (status хранит фактический статус) — иначе аннулированный платёж
            # негде увидеть. skip_reason остаётся общим механизмом на случай
            # будущих причин реального пропуска строки.
            if pr.skip_reason:
                rows_skipped += 1
                continue

            if pr.external_doc_id and pr.external_doc_id in seen_external_ids:
                rows_dup += 1
                continue

            # Субсидия/орг — прямая привязка по basis_doc_number (независимо
            # от того, опознан ли контрагент; ср. auto_match, который требует
            # контрагента раньше). Если соглашение не опознано — subsidy_id/org_id
            # остаются NULL, строка всё равно импортируется.
            subsidy = await resolve_subsidy(
                db, pr.basis_doc_number, pr.basis_doc_date, pr.parsed_documents, pr.subsidy_code
            )
            if subsidy is None:
                rows_no_subsidy += 1
            elif import_org_id is None:
                import_org_id = subsidy.org_id

            bp = BankPayment(
                import_id=import_run.id,
                org_id=subsidy.org_id if subsidy else None,
                subsidy_id=subsidy.id if subsidy else None,
                external_doc_id=pr.external_doc_id,
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
                expense_code=pr.expense_code,
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
                if pr.external_doc_id:
                    seen_external_ids.add(pr.external_doc_id)
            except IntegrityError:
                await db.rollback()
                rows_dup += 1
                continue

        import_run.org_id = import_org_id

        # Авто-матч
        rows_matched = 0
        rows_unmatched = 0
        try:
            match_counts = await match_all_in_import(db, import_run.id)
            rows_matched = match_counts.get("matched_contract", 0)
            rows_unmatched = match_counts.get("total", rows_imported) - rows_matched
        except Exception as match_exc:
            # Matcher не должен ронять импорт, но сбой нельзя глотать молча —
            # иначе импорт помечается done, а авто-матч тихо пропущен (счётчики врут).
            logging.getLogger(__name__).warning(
                f"match_all_in_import failed for import {import_run.id}: {match_exc}",
                exc_info=True,
            )
            rows_unmatched = rows_imported

        import_run.rows_total = rows_total
        import_run.rows_imported = rows_imported
        import_run.rows_skipped = rows_skipped
        import_run.rows_dup = rows_dup
        import_run.rows_matched = rows_matched
        import_run.rows_unmatched = rows_unmatched
        import_run.rows_no_subsidy = rows_no_subsidy
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
        import_run.rows_no_subsidy = rows_no_subsidy

    await db.commit()
    await db.refresh(import_run)

    # Этап 1: успешная партия ('done') удаляется автоматически — платежи
    # остаются (у них уже проставлены external_doc_id/org_id/subsidy_id, партия
    # им больше не нужна для идентификации; import_id → NULL через ON DELETE
    # SET NULL). Партии с ошибкой ('error') остаются в журнале для разбора.
    if import_run.status == "done":
        out = BankStatementImportOut.model_validate(import_run)
        await db.delete(import_run)
        await db.commit()
        return out

    return import_run


# ---------------------------------------------------------------------------
# GET /api/payments/imports — журнал прогонов
# ---------------------------------------------------------------------------

@router.get("/imports", response_model=List[BankStatementImportOut])
async def list_bank_imports(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.registry_view")),
):
    q = select(BankStatementImport).order_by(BankStatementImport.id.desc()).limit(50)
    q = _apply_org_scope(q, current_user, BankStatementImport.org_id)
    result = await db.execute(q)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /api/payments/imports/{import_id} — детали прогона
# ---------------------------------------------------------------------------

@router.get("/imports/{import_id}", response_model=BankStatementImportOut)
async def get_bank_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.registry_view")),
):
    result = await db.execute(
        select(BankStatementImport).where(BankStatementImport.id == import_id)
    )
    imp = result.scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    if not _row_visible(current_user, imp.org_id):
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    return imp


# ---------------------------------------------------------------------------
# DELETE /api/payments/imports/{import_id} — откат прогона
# ---------------------------------------------------------------------------

@router.delete("/imports/{import_id}")
async def delete_bank_import(
    import_id: int,
    with_payments: bool = Query(
        False,
        description="true — старое поведение: открепить и удалить все BankPayment этой партии. "
                     "По умолчанию false: удаляется только запись партии, платежи остаются "
                     "(import_id → NULL).",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.import")),
):
    result = await db.execute(
        select(BankStatementImport).where(BankStatementImport.id == import_id)
    )
    imp = result.scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    if not _row_visible(current_user, imp.org_id):
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")

    if with_payments:
        # Прежнее поведение: открепляем Payment-ы, затем удаляем все BankPayment партии.
        bp_result = await db.execute(
            select(BankPayment).where(BankPayment.import_id == import_id)
        )
        bank_payments = bp_result.scalars().all()

        for bp in bank_payments:
            try:
                await unlink_bank_payment(db, bp.id)
            except Exception:
                pass
            await db.delete(bp)

    # По умолчанию: удаляем только партию. bank_payments.import_id → NULL
    # автоматически (ON DELETE SET NULL) — платежи остаются в реестре.
    await db.delete(imp)
    await db.commit()
    return {"ok": True, "deleted_import_id": import_id, "with_payments": with_payments}


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
# POST /api/payments/imports/{import_id}/rematch — перематч строк прогона
# ---------------------------------------------------------------------------

@router.post("/imports/{import_id}/rematch")
async def rematch_import(
    import_id: int,
    only_unmatched: bool = True,
    reparse: bool = False,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.import")),
):
    """Перезапустить auto_match для всех (или только unmatched) платежей данного импорта.

    Используется когда:
    - Изменились настройки субсидий (basis_doc_number/date)
    - Изменилась логика matcher
    - Загружены данные но контракты ещё не созданы в системе

    reparse=true — пересчитать parsed_documents из raw_json/purpose_text (нужно после
    смены regex, например разделения agreements от contracts).

    Этап 0 (попутная гигиена): only_unmatched=false раньше слепо обнуляло
    matched_* у ВСЕХ строк, включая уже ПОДТВЕРЖДЁННЫЕ (matched_confirmed=True) —
    у которых есть реальные Payment-записи, привязанные к закупкам и посчитанные
    в их агрегатах. Обнуление matched_purchase_id/matched_contract_id у такой
    строки не удаляет Payment, но рвёт связность: реестр начинает показывать
    платёж как «не сматчен», хотя он фактически разнесён и учтён в закупке —
    Payment остаётся сиротой без актуального matched_*. Подтверждённые строки
    теперь ВСЕГДА пропускаются, если явно не передан force=true — тогда
    подтверждение сначала штатно откатывается (unlink_bank_payment: сносит
    Payment + пересчитывает агрегаты закупки), и только потом матч сбрасывается.

    NB: успешные ('done') партии удаляются автоматически после импорта (Этап 1) —
    их import_id у платежей уже NULL, поэтому rematch по такому import_id больше
    не найдёт строк. Работает для ещё живых ('error') партий и в течение самого
    запроса импорта.
    """
    from app.services.payment_matcher import auto_match, resolve_subsidy
    from app.services.purchase_payments import unlink_bank_payment

    q = select(BankPayment).where(BankPayment.import_id == import_id)
    if only_unmatched:
        q = q.where(BankPayment.matched_contract_id.is_(None))
    q = _apply_org_scope(q, current_user, BankPayment.org_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    counts = {
        'total': len(rows), 'matched_contract': 0, 'matched_subsidy': 0,
        'matched_purchase': 0, 'skipped_confirmed': 0,
    }
    for bp in rows:
        if not only_unmatched:
            if bp.matched_confirmed:
                if not force:
                    counts['skipped_confirmed'] += 1
                    continue
                # force=true: откатываем подтверждение штатно (сносит Payment +
                # пересчитывает агрегаты закупки), а не просто обнуляем поля.
                await unlink_bank_payment(db, bp.id)
                bp.matched_confirmed = False
            bp.matched_contractor_id = None
            bp.matched_subsidy_id = None
            bp.matched_contract_id = None
            bp.matched_purchase_id = None
        if reparse:
            from app.services.bank_statement_parser import reparse_bank_payment_typed
            reparse_bank_payment_typed(bp)
        # Прямая привязка subsidy_id/org_id (Этап 1) — обновляем на случай если
        # basis_doc_number субсидии поменялся с момента импорта.
        s = await resolve_subsidy(db, bp.basis_doc_number, bp.basis_doc_date, bp.parsed_documents, bp.subsidy_code)
        if s:
            bp.subsidy_id = s.id
            bp.org_id = s.org_id
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
# Этап 1: раньше был БЕЗ auth вовсе — дампил raw_json (реквизиты/суммы платежей)
# кому угодно без токена. Теперь требует аутентификации + org-скоуп как остальной реестр.
# ---------------------------------------------------------------------------

@router.get("/imports/{import_id}/diag")
async def diag_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Возвращает первую строку BankPayment этого импорта: raw_json (все ключи и значения)
    + typed-поля. Помогает понять какие headers попали из xlsx в БД и почему HEADER_MAP их не находит.
    """
    base_q = select(BankPayment).where(BankPayment.import_id == import_id)
    base_q = _apply_org_scope(base_q, current_user, BankPayment.org_id)

    q = await db.execute(base_q.limit(1))
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

    # Подсчёт строк с NULL payment_date в этом импорте (в пределах видимых org)
    from sqlalchemy import func as _func
    null_count = (await db.execute(
        _apply_org_scope(
            select(_func.count()).select_from(BankPayment)
            .where(BankPayment.import_id == import_id)
            .where(BankPayment.payment_date.is_(None)),
            current_user, BankPayment.org_id,
        )
    )).scalar() or 0
    total_count = (await db.execute(
        _apply_org_scope(
            select(_func.count()).select_from(BankPayment)
            .where(BankPayment.import_id == import_id),
            current_user, BankPayment.org_id,
        )
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

@router.post("/imports/{import_id}/reparse-rows")
async def reparse_existing_rows(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_action("payment.import")),
):
    """Пересобрать ВСЕ typed поля BankPayment из сохранённого raw_json без повторного импорта файла.

    Полезно когда парсер был исправлен (например найдена строка заголовков),
    а 76 уже импортированных записей имеют NULL во всех полях, так как при
    исходном импорте header_row=1 дал мусорные ключи и HEADER_MAP ничего не нашёл.
    """
    from app.services.bank_statement_parser import reparse_bank_payment_typed
    from app.services.payment_matcher import resolve_subsidy

    base_q = select(BankPayment).where(BankPayment.import_id == import_id)
    base_q = _apply_org_scope(base_q, current_user, BankPayment.org_id)
    q = await db.execute(base_q)
    rows = q.scalars().all()
    fixed = 0

    for bp in rows:
        if not bp.raw_json:
            continue
        reparse_bank_payment_typed(bp)
        # Этап 1: subsidy_id/org_id тоже пересчитываем — reparse чинит basis_doc_number,
        # без обновления subsidy_id/org_id останутся привязанными к старому значению.
        s = await resolve_subsidy(db, bp.basis_doc_number, bp.basis_doc_date, bp.parsed_documents, bp.subsidy_code)
        if s:
            bp.subsidy_id = s.id
            bp.org_id = s.org_id
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
