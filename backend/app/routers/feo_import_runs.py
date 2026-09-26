"""Список прогонов импорта ФЭО + детали одного прогона (волна 3, 26.09) —
«человек должен это увидеть».

Владелец: «нужно знать, кто загрузил файл импорта и что он перезаписал».
FeoImportRun (app/models/feo_import_run.py) — один прогон (кто, файл, лист,
когда, счётчики). Построчные факты, что этот прогон создал/перезаписал, —
entity_changes с source='import', source_ref=id этого прогона (см.
app/services/feo_history.py — единственная точка записи, ничего здесь не
пишем, только читаем).

Правило №5 (модульность): отдельный файл, не дописано в уже большой
feo_import.py (движок самого импорта) — здесь ТОЛЬКО чтение готового журнала.

Подключение — БЕЗ правки backend/app/routes.py (файл в списке запрещённых:
им сейчас занята параллельная сессия 152-ФЗ). Тот же приём, что и
app/routers/feo_categories_collapse.py (см. её докстринг): подключается как
ПОД-роутер feo_categories.router (`router.include_router(...)` в хвосте
feo_categories.py) — у router здесь сознательно НЕТ собственного prefix,
FastAPI досоставляет его из префикса РОДИТЕЛЯ ("/api/feo-categories"). Итоговые
пути:
    GET /api/feo-categories/import-runs?subsidy_id=...
    GET /api/feo-categories/import-runs/{run_id}/changes
⚠️ Задание волны 3 просило "/api/feo-import-runs" — это НЕ то же самое, что
получилось здесь; расхождение осознанное, разрешено в пользу запрета трогать
routes.py (см. отчёт агента). Если понадобится ровно "/api/feo-import-runs" —
единственный способ без этого компромисса — отдельная регистрация в
routes.py, которую делает уже владелец сессии.

Доступ — ТОТ ЖЕ хелпер, что и у истории feo_item/feo_category
(_check_feo_history_read_access, app/routers/entity_changes.py):
get_visible_subsidy_ids(current_user, db, 'feo_categories') (Правило №6 —
второй способ проверки прав не заводим).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.entity_change import EntityChange
from app.models.feo_category import FeoCategory
from app.models.feo_import_run import FeoImportRun
from app.models.feo_planned_item import FeoPlannedItem
from app.models.user import User

router = APIRouter(tags=["feo_import_runs"])


class FeoImportRunOut(BaseModel):
    id: int
    subsidy_id: Optional[int] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    filename: Optional[str] = None
    sheet_name: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_count: int
    updated_count: int
    skipped_count: int
    comments_created: int
    warnings_count: int

    class Config:
        from_attributes = True


class FeoImportRunListOut(BaseModel):
    items: List[FeoImportRunOut]
    total: int


class FeoImportRunChangeOut(BaseModel):
    """Одна строка журнала, которую создал/перезаписал прогон импорта.

    entity_name — имя позиции/категории на МОМЕНТ ЧТЕНИЯ (владелец требует
    называть сущности именами, не голыми id, см. память проекта
    feedback_name_entities_not_ids). None — сущность с тех пор удалена
    (её собственная запись __deleted__ будет отдельной строкой этого же
    прогона, если удаление тоже было им).
    """
    id: int
    entity_type: str
    entity_id: int
    entity_name: Optional[str] = None
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: Optional[str] = None
    is_created: bool
    is_deleted: bool


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


async def _check_subsidy_read_access(subsidy_id: int, current_user: User, db: AsyncSession) -> None:
    """Дублирует докстринг _check_feo_history_read_access (entity_changes.py):
    ЧТЕНИЕ, не правило права ПИСАТЬ — переиспользует ту же видимость субсидий,
    что и остальные ФЭО-эндпоинты чтения."""
    from app.auth.visibility import get_visible_subsidy_ids

    visible = await get_visible_subsidy_ids(current_user, db, "feo_categories")
    if visible is not None and subsidy_id not in visible:
        raise HTTPException(status_code=403, detail="Нет доступа к ФЭО этой субсидии")


@router.get("/import-runs", response_model=FeoImportRunListOut)
async def list_import_runs(
    subsidy_id: int = Query(..., description="Субсидия, для которой смотрим журнал загрузок"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Прогоны импорта ФЭО по субсидии, новые сверху, с пагинацией."""
    await _check_subsidy_read_access(subsidy_id, current_user, db)

    total = (await db.execute(
        select(func.count()).select_from(FeoImportRun).where(FeoImportRun.subsidy_id == subsidy_id)
    )).scalar_one()

    rows = (await db.execute(
        select(FeoImportRun)
        .where(FeoImportRun.subsidy_id == subsidy_id)
        .order_by(FeoImportRun.started_at.desc(), FeoImportRun.id.desc())
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    items = [_run_out(r) for r in rows]
    return FeoImportRunListOut(items=items, total=total)


def _run_out(r: FeoImportRun) -> FeoImportRunOut:
    return FeoImportRunOut(
        id=r.id, subsidy_id=r.subsidy_id, user_id=r.user_id, user_name=r.user_name,
        filename=r.filename, sheet_name=r.sheet_name,
        started_at=_iso(r.started_at), finished_at=_iso(r.finished_at),
        created_count=r.created_count, updated_count=r.updated_count,
        skipped_count=r.skipped_count, comments_created=r.comments_created,
        warnings_count=r.warnings_count,
    )


@router.get("/import-runs/{run_id}", response_model=FeoImportRunOut)
async def get_import_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Одна карточка прогона (для ленты истории позиции/категории — «Загружена
    импортом файла «X», ФИО, дата» — без нужды тянуть subsidy_id заранее)."""
    run = await db.get(FeoImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    if run.subsidy_id is not None:
        await _check_subsidy_read_access(run.subsidy_id, current_user, db)
    return _run_out(run)


@router.get("/import-runs/{run_id}/changes", response_model=List[FeoImportRunChangeOut])
async def get_import_run_changes(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Что именно этот прогон создал и перезаписал — entity_changes с
    source='import' и source_ref=этот прогон, с именами сущностей вместо id."""
    run = await db.get(FeoImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Прогон импорта не найден")
    if run.subsidy_id is not None:
        await _check_subsidy_read_access(run.subsidy_id, current_user, db)

    rows = (await db.execute(
        select(EntityChange)
        .where(EntityChange.source == "import", EntityChange.source_ref == run_id)
        .order_by(EntityChange.entity_type, EntityChange.entity_id, EntityChange.changed_at)
    )).scalars().all()

    item_ids = {r.entity_id for r in rows if r.entity_type == "feo_item"}
    cat_ids = {r.entity_id for r in rows if r.entity_type == "feo_category"}
    names: dict[tuple[str, int], str] = {}
    if item_ids:
        for iid, name in (await db.execute(
            select(FeoPlannedItem.id, FeoPlannedItem.name).where(FeoPlannedItem.id.in_(item_ids))
        )).all():
            names[("feo_item", iid)] = name
    if cat_ids:
        for cid, name in (await db.execute(
            select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids))
        )).all():
            names[("feo_category", cid)] = name

    return [
        FeoImportRunChangeOut(
            id=r.id, entity_type=r.entity_type, entity_id=r.entity_id,
            entity_name=names.get((r.entity_type, r.entity_id)),
            field_name=r.field_name, old_value=r.old_value, new_value=r.new_value,
            changed_at=_iso(r.changed_at),
            is_created=r.field_name == "__created__",
            is_deleted=r.field_name == "__deleted__",
        )
        for r in rows
    ]
