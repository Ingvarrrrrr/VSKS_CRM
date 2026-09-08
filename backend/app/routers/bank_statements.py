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

РАЗРЕЗАНО (Правило №5, сессия 2026-09-08) из монолитного bank_statements.py
(1024 строки) на:
  - app/routers/bank_statements_imports.py — GET/DELETE /imports/{id},
    GET /imports (журнал), POST /imports/{id}/rematch, GET /imports/{id}/diag,
    POST /imports/{id}/reparse-rows.
  - app/routers/bank_statements_registry.py — GET /registry (+raw-columns,
    {bp_id}), PATCH .../match, GET /reconciliation, GET .../match-suggestions,
    POST .../confirm, POST .../unbind.
Этот файл (ядро) несёт org-скоуп хелперы _apply_org_scope/_row_visible/
_ACCOUNT_ADMIN_ROLES (импортируются siblings-роутерами отсюда — единый
источник правила видимости, Правило №6) и POST /imports (upload) — самую
объёмную и наиболее чувствительную к monkeypatch в тестах функцию
(test_bank_statements_router.py патчит `app.routers.bank_statements.
match_all_in_import` — имя обязано остаться module-level именно здесь).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_action
from app.auth.jwt import get_org_filter
from app.models.bank_statement import BankStatementImport, BankPayment
from app.services.bank_statement_parser import parse_workbook
# These services are created in Plan 22-03 (parallel wave) — they will exist at deploy time.
from app.services.payment_matcher import match_all_in_import, resolve_subsidy  # noqa: F401
from app.schemas.schemas import BankStatementImportOut

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
