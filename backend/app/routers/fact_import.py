"""«Импорт факта» — POST/GET /api/subsidies/{subsidy_id}/fact-import/*.

Уже совершённые закупки из таблиц ведения субсидии (план breezy-mixing-
lovelace.md, часть 2, задача 02.10.2026). Подключён как под-роутер
`subsidies.router` (см. конец app/routers/subsidies.py) — НЕ через
app/routes.py (его правит параллельная сессия, см. задачу), тот же приём,
что уже применяется для under-router-инклюзии в этом проекте.

Право — как у импорта закупок: subsidy.edit на конкретную субсидию (тот же
паттерн, что app.routers.purchase_import._check_purchases_import_permission).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from urllib.parse import quote

from app.database import get_db
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key

router = APIRouter(prefix="/{subsidy_id}/fact-import", tags=["fact-import"])


async def _check_permission(subsidy_id: int, db: AsyncSession, current_user) -> Subsidy:
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(404, "Субсидия не найдена")
    if not await has_org_key(current_user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy_id):
        raise HTTPException(
            403,
            "Импортировать факт закупок в эту субсидию может только тот, у кого есть право "
            "её редактирования",
        )
    return subsidy


def _parse_json_form(raw: Optional[str], field_name: str) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"Некорректный JSON в поле «{field_name}»: {e}")


@router.get("/template")
async def fact_import_template(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.services.historical_fact_import.template import build_template_workbook

    content = await build_template_workbook(db, subsidy_id)
    filename = f"fact_import_template_{subsidy_id}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/sheets")
async def fact_import_sheets(
    subsidy_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.services.historical_fact_import.columns import list_sheets

    content = await file.read()
    return list_sheets(content, file.filename or "")


@router.post("/preview")
async def fact_import_preview(
    subsidy_id: int,
    file: UploadFile = File(...),
    sheet: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
    decisions: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.services.historical_fact_import.preview import build_preview

    content = await file.read()
    mapping_dict = _parse_json_form(mapping, "mapping")
    decisions_dict = _parse_json_form(decisions, "decisions")
    return await build_preview(
        db, subsidy_id, content, file.filename or "", sheet, mapping_dict, decisions_dict,
    )


@router.post("/commit")
async def fact_import_commit(
    subsidy_id: int,
    file: UploadFile = File(...),
    sheet: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
    decisions: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.services.historical_fact_import.commit import commit_import

    content = await file.read()
    mapping_dict = _parse_json_form(mapping, "mapping")
    decisions_dict = _parse_json_form(decisions, "decisions")
    result = await commit_import(
        db, subsidy_id, current_user, content, file.filename or "", sheet, mapping_dict, decisions_dict,
    )
    await db.commit()
    return result


@router.get("/runs")
async def fact_import_runs_list(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.models.fact_import_run import FactImportRun
    from app.models.user import User

    runs = (await db.execute(
        select(FactImportRun)
        .where(FactImportRun.subsidy_id == subsidy_id)
        .order_by(FactImportRun.created_at.desc())
    )).scalars().all()
    user_ids = {r.user_id for r in runs if r.user_id}
    users = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u for u in rows}

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "sheet": r.sheet,
            "user_name": users[r.user_id].full_name if r.user_id in users else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "status": r.status,
            "purchases_created": r.purchases_created,
            "payments_created": r.payments_created,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def fact_import_run_detail(
    subsidy_id: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.models.fact_import_run import FactImportRun

    run = await db.get(FactImportRun, run_id)
    if not run or run.subsidy_id != subsidy_id:
        raise HTTPException(404, "Прогон импорта не найден")

    return {
        "run": {
            "id": run.id,
            "filename": run.filename,
            "sheet": run.sheet,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "purchases_created": run.purchases_created,
            "payments_created": run.payments_created,
            "contractors_created": run.contractors_created,
        },
        "report": run.report or [],
    }


@router.post("/runs/{run_id}/rollback")
async def fact_import_run_rollback(
    subsidy_id: int,
    run_id: int,
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _check_permission(subsidy_id, db, current_user)
    from app.models.fact_import_run import FactImportRun
    from app.services.historical_fact_import.rollback import preview_rollback, execute_rollback

    run = await db.get(FactImportRun, run_id)
    if not run or run.subsidy_id != subsidy_id:
        raise HTTPException(404, "Прогон импорта не найден")
    if run.status == "rolled_back":
        raise HTTPException(400, "Этот прогон уже откатан")

    if dry_run:
        return await preview_rollback(db, run)

    result = await execute_rollback(db, run)
    if not result.get("can_rollback"):
        return result
    await db.commit()
    return result
