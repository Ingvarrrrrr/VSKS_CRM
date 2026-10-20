"""GET /api/feo-categories/export — экспорт дерева категорий ФЭО одной
субсидии в Excel; GET /api/feo-categories/export/columns — каталог столбцов.

Вынесено из app/routers/feo_import.py (Правило №5, разрезание 1088-строчного
роутера) без изменения поведения — самодостаточен (не связан с импортом,
только читает дерево категорий и суммы закупок). Путь статичный (без
{cat_id}) — регистрируется в app/routes.py рядом с feo_import.router и ДО
feo_categories.router (несёт catch-all GET/PUT/DELETE "/{cat_id}"), как и
остальные соседи feo_import_*.

ИЗМЕНЕНО (владелец 20.10.2026): построение книги вынесено в
app.services.feo_export_xlsx (Правило №5 — роутер тонкий); выбор столбцов —
app.services.feo_export_columns (Правило №6, тот же приём, что
/api/subsidies/plan-graph/export/columns)."""
from io import BytesIO

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

from app.database import get_db
from app.auth.permissions import require_tab
from app.utils.http import content_disposition
from app.services.feo_export_columns import columns_catalog, resolve_selected_keys
from app.services.feo_export_xlsx import build_feo_export_workbook

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


_content_disposition = content_disposition


@router.get("/export/columns")
async def get_feo_export_columns(_=Depends(require_tab('feo_categories'))):
    """Столбцы выгрузки «Выгрузить ФЭО» для выбора перед экспортом — тот же
    приём, что GET /api/subsidies/plan-graph/export/columns (ПРАВИЛО №6)."""
    return columns_catalog()


@router.get("/export")
async def export_feo_to_excel(
    subsidy_id: int = Query(...),
    columns: str | None = Query(None),
    with_summary: bool = Query(False, description="Включать листы «Сводная»/«Дашборд»"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('feo_categories')),
):
    """Экспорт дерева категорий ФЭО в Excel. `columns` — через запятую
    (пусто/не передан → столбцы по умолчанию, см. feo_export_columns).
    `with_summary` (владелец 20.10.2026, часть 3) — листы «Сводная»/«Дашборд»,
    см. app.services.feo_export_summary."""
    if Workbook is None:
        raise HTTPException(500, "openpyxl не установлен")
    from app.models.subsidy import Subsidy

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    selected_keys = resolve_selected_keys(columns)
    wb = await build_feo_export_workbook(db, sub, selected_keys, with_summary=with_summary)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = sub.name.replace(" ", "_").replace("/", "-")[:40]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(f"ФЭО_{safe_name}.xlsx")},
    )
