"""POST /api/feo-categories/roundtrip/preview и /roundtrip/apply — загрузка
обратно файла «Выгрузить ФЭО» (владелец, 20.10.2026: «использовать такую
разбивку как загрузку субсидии с нуля»).

Права — ТОТ ЖЕ гейт, что у прямой правки одной категории/позиции этой
субсидии (ПРАВИЛО №8): require_tab('feo_categories') (видимость) +
fc._require_feo_category_write(current_user, db, subsidy_id) (право
feo_category.edit) + assert_direct_edit (корректировка утверждённой
субсидии) — второй механизм прав не заводится.

preview/apply делят ОДНУ функцию разбора плана (parse.parse_roundtrip_
workbook + diff.build_preview) — apply выполняет тот же план, что показал
preview (файл передаётся заново, план не кэшируется между запросами: между
preview и apply БД могла измениться, apply обязан видеть актуальное
состояние, не то, что было секунду назад)."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.routers import feo_categories as fc
from app.services.feo_roundtrip_import.parse import parse_roundtrip_workbook
from app.services.feo_roundtrip_import.diff import build_preview, check_meta_mismatch

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


async def _require_write(current_user, db: AsyncSession, subsidy_id: int) -> None:
    from app.services.subsidy_revision_guard import assert_direct_edit
    await fc._require_feo_category_write(current_user, db, subsidy_id)
    await assert_direct_edit(db, current_user, subsidy_id)


def _check_subsidy_exists_sync(sub) -> None:
    if sub is None:
        raise HTTPException(404, "Субсидия не найдена")


async def _load_subsidy(db: AsyncSession, subsidy_id: int):
    from app.models.subsidy import Subsidy
    sub = await db.get(Subsidy, subsidy_id)
    _check_subsidy_exists_sync(sub)
    return sub


def _preview_response(preview) -> dict:
    return {
        "changes": preview.changes,
        "created": preview.created,
        "moved": preview.moved,
        "missing": preview.missing,
        "errors": preview.errors,
        "warnings": preview.warnings,
    }


@router.post("/roundtrip/preview")
async def roundtrip_preview(
    subsidy_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Предпросмотр: что изменится в дереве категорий/плановых позиций,
    если загрузить этот файл обратно в субсидию `subsidy_id`. НЕ пишет в БД —
    build_preview делает только SELECT."""
    await _load_subsidy(db, subsidy_id)
    await _require_write(current_user, db, subsidy_id)

    fname = (file.filename or "").lower()
    if not fname.endswith(".xlsx"):
        raise HTTPException(400, "Поддерживается только файл .xlsx (выгрузка «Выгрузить ФЭО»)")
    content = await file.read()

    parsed = parse_roundtrip_workbook(content)
    if parsed.errors:
        raise HTTPException(400, {"message": "; ".join(parsed.errors)})
    _mismatch = check_meta_mismatch(parsed.meta, subsidy_id)
    if _mismatch:
        raise HTTPException(400, {"message": _mismatch})

    preview = await build_preview(db, subsidy_id, parsed.rows, parsed.meta)
    return _preview_response(preview)


@router.post("/roundtrip/apply")
async def roundtrip_apply(
    subsidy_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Применяет загрузку — тот же файл, что и предпросмотр. Отклоняется,
    если план содержит errors (повторная проверка на сервере — фронт мог
    прислать apply на устаревший предпросмотр). Одна транзакция, один
    FeoImportRun в журнале загрузок ФЭО (ПРАВИЛО №6 — тот же журнал, что у
    «Импорт ФЭО»)."""
    sub = await _load_subsidy(db, subsidy_id)
    await _require_write(current_user, db, subsidy_id)

    fname = (file.filename or "").lower()
    if not fname.endswith(".xlsx"):
        raise HTTPException(400, "Поддерживается только файл .xlsx (выгрузка «Выгрузить ФЭО»)")
    content = await file.read()

    parsed = parse_roundtrip_workbook(content)
    if parsed.errors:
        raise HTTPException(400, {"message": "; ".join(parsed.errors)})
    _mismatch = check_meta_mismatch(parsed.meta, subsidy_id)
    if _mismatch:
        raise HTTPException(400, {"message": _mismatch})

    preview = await build_preview(db, subsidy_id, parsed.rows, parsed.meta)
    if preview.errors:
        raise HTTPException(400, {
            "message": "В файле есть ошибки — загрузка отменена, исправьте и повторите",
            "errors": preview.errors,
        })

    from app.models.feo_import_run import FeoImportRun
    from app.services.feo_roundtrip_import.apply import apply_rows

    run = FeoImportRun(
        subsidy_id=subsidy_id,
        user_id=getattr(current_user, "id", None),
        user_name=getattr(current_user, "full_name", None),
        filename=file.filename,
        sheet_name="Выгрузить ФЭО (обратная загрузка)",
    )
    db.add(run)
    await db.flush()

    # Снимок ПРЕДЫДУЩЕЙ редакции плана — ДО применения строк (тот же порядок,
    # что и у «Импорт ФЭО», см. feo_import_apply.create_version_snapshot:
    # версия обязана снять состояние, пока дерево ещё не изменилось).
    will_change = bool(preview.changes or preview.created or preview.moved)
    if will_change:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=subsidy_id, db=db, user=current_user,
            note=f"Загрузка выгрузки ФЭО обратно (файл «{file.filename}»)",
        )

    counts = await apply_rows(db, current_user, subsidy_id, preview.resolved, run.id)

    from datetime import datetime, timezone
    run.finished_at = datetime.now(timezone.utc)
    run.created_count = counts["created"]
    run.updated_count = counts["updated"]
    run.skipped_count = 0
    run.comments_created = 0
    run.warnings_count = len(preview.warnings)
    run.summary = {"moved": counts["moved"], "missing": len(preview.missing)}

    await db.commit()

    return {
        "created": counts["created"],
        "updated": counts["updated"],
        "moved": counts["moved"],
        "missing": preview.missing,
        "warnings": preview.warnings,
        "import_run_id": run.id,
    }
