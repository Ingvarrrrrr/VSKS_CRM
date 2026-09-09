"""POST /api/feo-categories/import-preview — читает Excel/DOCX/XLS/PDF и
возвращает заголовки + примеры строк для ручного маппинга колонок (мастер
сопоставления перед /import-mapped).

Вынесено из app/routers/feo_import.py (Правило №5, разрезание 1088-строчного
роутера) без изменения поведения — самодостаточен (не вызывает _do_feo_import,
только читает файл и определяет заголовки). Путь статичный (без {cat_id}) —
регистрируется в app/routes.py рядом с feo_import.router и ДО
feo_categories.router (несёт catch-all GET/PUT/DELETE "/{cat_id}"), как и
остальные соседи feo_import_*.

2026-09-09 (план dreamy-booping-piglet.md, задача B, п.1): само чтение
листов/детект заголовка вынесено в services/import_preview_sheets.py — общий
сервис с мастером импорта товаров (ПРАВИЛО №6, третьей копии нет). Поведение
ЭТОГО эндпоинта не поменялось — те же hints, тот же формат ответа.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.routers import feo_categories as fc
from app.services.import_preview_sheets import read_preview_sheets

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])

_FEO_HINTS = (
    "субсидия", "наименован", "направлен", "расходов", "уровень",
    "код", "финансирован", "количеств", "ед. изм", "ед.изм",
    "активн", "приложен", "бюджет", "плановый", "тип расх",
)


@router.post("/import-preview")
async def feo_import_preview(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Read Excel/DOCX file and return headers + sample rows for column mapping."""
    # B2: файл ещё не связан с конкретной субсидией на этом шаге (маппинг колонок
    # выбирается ПОСЛЕ) — subsidy_id=None, право проверяется по любой доступной орге.
    await fc._require_feo_category_write(current_user, db, None)
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls", ".docx", ".doc", ".pdf")):
        raise HTTPException(400, "Поддерживаются файлы .xlsx, .xls, .docx, .pdf")

    content = await file.read()
    return read_preview_sheets(content, file.filename or "", _FEO_HINTS)
