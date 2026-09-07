"""Purchase import router.

Handles:
  POST /api/purchases/import           — Scroller-format xlsx import
  POST /api/purchases/import/preview   — preview without committing

The actual parsing/grouping logic (`_parse_and_group` and everything it
uses — column maps, ФЭО resolution, cell coercion helpers) lives in
services/purchase_import_parser.py; this module only owns the permission
gate and the two thin HTTP endpoints.

Split out of the former backend/app/routers/purchase_export.py (refactor,
2026-09). Keeps the same `router = APIRouter(prefix="/api/purchases",
tags=["purchase-export"])` as the original module so the OpenAPI schema is
unchanged.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.services.purchase_import_parser import _parse_and_group, load_workbook

router = APIRouter(prefix="/api/purchases", tags=["purchase-export"])


async def _check_purchases_import_permission(
    subsidy_id: int, db: AsyncSession, current_user
) -> Subsidy:
    """Заливать закупки из Excel может только тот, у кого есть право
    редактировать ИМЕННО эту субсидию (subsidy.edit) — просто «залогинен»
    недостаточно (требование владельца, 2026-08-19). Тот же паттерн, что
    events._get_subsidy_for_events(edit=True) и
    subsidy_approvers._get_subsidy_or_404(edit=True)."""
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(404, "Субсидия не найдена")
    if not await has_org_key(current_user, db, subsidy.org_id, 'subsidy.edit', subsidy_id=subsidy_id):
        raise HTTPException(
            403,
            "Импортировать закупки в эту субсидию может только тот, у кого есть право "
            "её редактирования",
        )
    return subsidy


# ---------------------------------------------------------------------------
# POST /import
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_purchases_from_excel(
    file: UploadFile = File(...),
    subsidy_id: int = Query(..., description="ID субсидии (обязательно)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Импорт закупок из Excel. Возвращает {created_purchases, created_items, created_payments, skipped, errors}."""
    await _check_purchases_import_permission(subsidy_id, db, current_user)
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    return await _parse_and_group(content, subsidy_id, db, commit=True)


# ---------------------------------------------------------------------------
# POST /import/preview
# ---------------------------------------------------------------------------

@router.post("/import/preview")
async def preview_purchases_import(
    file: UploadFile = File(...),
    subsidy_id: int = Query(..., description="ID субсидии (обязательно)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Превью импорта без сохранения. Возвращает {purchases, payments_errors, skipped, errors}."""
    await _check_purchases_import_permission(subsidy_id, db, current_user)
    if load_workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Поддерживаются только файлы .xlsx и .xls")

    content = await file.read()
    return await _parse_and_group(content, subsidy_id, db, commit=False)
