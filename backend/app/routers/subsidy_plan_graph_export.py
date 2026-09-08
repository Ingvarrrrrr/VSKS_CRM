"""Экспорт плана-графика (plan-graph) субсидии в Excel/.docx.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09-07):
GET .../plan-graph/export (живое дерево ФЭО → .xlsx), GET .../versions/
{version_id:int}/export (снапшот версии → .xlsx), POST .../plan-graph/template
(загрузка .docx-шаблона для export-docx), GET .../plan-graph/export-docx.

Тонкий роутер (Правило №5, рефакторинг 2026-09-08) — сборка данных, рендер
xlsx/docx и форматирование вынесены в app/services/plan_graph_export_*:
  - plan_graph_export_data.gather_live_plan_graph_data — запросы к БД для
    живого экспорта;
  - plan_graph_export_xlsx.build_live_plan_graph_xlsx — рендер книги живого
    экспорта (каскад статусов, факт по позициям, лист «Сводная»);
  - plan_graph_export_render.render_plan_graph_workbook — общий рендерер
    книги по снапшоту версии (v1/v2-дерево);
  - plan_graph_export_docx — сохранение .docx-шаблона и его заполнение
    docxtpl.

Собственный APIRouter на префиксе /api/subsidies — регистрируется в
app/routes.py рядом с subsidies.router.
"""
import io
import os

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from app.utils.http import content_disposition as _content_disposition

try:
    import openpyxl
except ImportError:
    openpyxl = None

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, require_role, get_org_filter, ADMIN_ROLES
from app.models.user import User
from app.models.subsidy import Subsidy
from app.services.plan_graph_export_data import gather_live_plan_graph_data
from app.services.plan_graph_export_xlsx import build_live_plan_graph_xlsx
from app.services.plan_graph_export_render import render_plan_graph_workbook
from app.services.plan_graph_export_docx import (
    TEMPLATE_DIR,
    DocxTemplate,
    template_path_for,
    save_plan_graph_template,
    render_plan_graph_docx,
)

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


@router.get("/{subsidy_id}/plan-graph/export")
async def export_plan_graph_excel(
    subsidy_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export plan-graph as Excel file with full FEO hierarchy (live data)."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    data = await gather_live_plan_graph_data(db, subsidy_id)

    # Дубль исходной проверки (унаследован из router до рефакторинга 2026-09-08,
    # там был перед построением книги вручную) — фактически недостижим, т.к.
    # openpyxl уже проверен выше и не меняется в рантайме. Оставлен как есть
    # (Правило: не чинить найденные попутно дефекты, дефект приведён в отчёте).
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    base_url = str(request.base_url).rstrip("/")
    wb = build_live_plan_graph_xlsx(sub, base_url, data)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"План_график_{safe_name}_{sub.year}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/{subsidy_id}/plan-graph/versions/{version_id:int}/export")
async def export_plan_graph_version_excel(
    subsidy_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a specific plan-graph version snapshot as Excel."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    ver = (await db.execute(
        select(_PGV).where(
            _PGV.id == version_id,
            _PGV.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if not ver:
        raise HTTPException(404, "Версия плана закупок не найдена")

    snap = ver.snapshot or {}
    tree = snap.get("tree", [])
    flat_items = snap.get("items", [])

    eff_date = ver.effective_date.isoformat() if ver.effective_date else (
        snap.get("effective_date") or None
    )
    created_at_str = ver.created_at.strftime("%Y-%m-%d %H:%M UTC") if ver.created_at else None

    meta = {
        "subsidy_name": sub.name,
        "subsidy_year": str(sub.year) if sub.year else "",
        "version_number": ver.version_number,
        "effective_date": eff_date,
        "note": ver.note,
        "generated_at": created_at_str,
    }

    wb = render_plan_graph_workbook(tree, flat_items, meta)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    date_part = (eff_date or (ver.created_at.strftime("%Y-%m-%d") if ver.created_at else "nodate"))
    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:30]
    filename = f"Субсидия_{subsidy_id}_план_v{ver.version_number}_{date_part}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/{subsidy_id}/plan-graph/template")
async def upload_plan_graph_template(
    subsidy_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Upload a .docx Word template for this subsidy's plan-graph export."""
    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Только .docx файлы поддерживаются")

    content = await file.read()
    dest = await save_plan_graph_template(subsidy_id, content)

    return {"ok": True, "template_path": dest, "message": "Шаблон загружен"}


@router.get("/{subsidy_id}/plan-graph/export-docx")
async def export_plan_graph_docx(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fill the uploaded .docx template via docxtpl and return the filled document."""
    if DocxTemplate is None:
        raise HTTPException(500, "docxtpl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    template_path = template_path_for(subsidy_id)
    if not os.path.exists(template_path):
        raise HTTPException(404, "Шаблон не загружен. Загрузите через POST /plan-graph/template")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    latest_ver = (await db.execute(
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(1)
    )).scalar_one_or_none()

    buf = render_plan_graph_docx(template_path, sub, latest_ver)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"План_график_{safe_name}_{sub.year}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
