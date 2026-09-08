"""Разрезание bank_statements.py (Правило №5, сессия 2026-09-08): журнал
прогонов импорта — всё под /api/payments/imports* КРОМЕ POST /imports (upload
остаётся в ядре, app/routers/bank_statements.py, см. его docstring).

GET    /api/payments/imports                список прогонов (журнал)
GET    /api/payments/imports/{id}           детали прогона
DELETE /api/payments/imports/{id}           удаляет партию (?with_payments=true
                                             — cascade BankPayment + Payment)
POST   /api/payments/imports/{id}/rematch   перезапустить auto_match
GET    /api/payments/imports/{id}/diag      diagnostic: raw_json первой строки
POST   /api/payments/imports/{id}/reparse-rows  пересборка typed-полей из raw_json

Org-скоуп хелперы (_apply_org_scope/_row_visible/_ACCOUNT_ADMIN_ROLES) — один
источник в bank_statements.py (ядро), здесь только импортируются (Правило №6).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_action
from app.auth.jwt import get_current_user
from app.models.bank_statement import BankStatementImport, BankPayment
from app.schemas.schemas import BankStatementImportOut
from app.routers.bank_statements import _apply_org_scope, _row_visible

router = APIRouter(prefix="/api/payments", tags=["bank-statements"])


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
        from app.services.purchase_payments import unlink_bank_payment
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
