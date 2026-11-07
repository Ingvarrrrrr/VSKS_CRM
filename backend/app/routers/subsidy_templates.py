"""Шаблоны документов субсидии — глобальные и per-subsidy overrides.

Вынесено из app/routers/subsidies.py (Правило №5, рефакторинг 2026-09-07):
list/upload/download/delete per-subsidy шаблонов, global-templates upload,
массовая нормализация (.docx normalize-all) + вспомогательные
_check_template_render_ok / _normalize_docx_template / _repair_docx_template.

Собственный APIRouter на том же префиксе /api/subsidies — регистрируется в
app/routes.py РЯДОМ с subsidies.router (см. комментарий про порядок там):
"/global-templates/*" и "/templates/normalize-all" — статические литеральные
пути, должны резолвиться раньше catch-all "/{subsidy_id}" в subsidies.router.

`_normalize_docx_template` используется лениво из documents.py (рендер
шаблона) — re-export оставлен в app/routers/subsidies.py для обратной
совместимости этого импорта.
"""
import os
import re
import shutil
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab, require_action

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


# ── Per-subsidy document templates ──────────────────────────────────────────

TEMPLATES_BASE = "/app/templates"
SUBSIDY_TEMPLATES_BASE = "/app/uploads/templates"
SUPPORTED_DOC_TYPES = {
    # Слоты «Договор» (contract) и «ТЗ (общий шаблон)» (contract_tz) убраны из UI
    # карточки субсидии — договоры выбираются по типу (contract_goods_single,
    # contract_services и т.д.), а ТЗ к договору прикрепляется из tech_spec_contract.
    # В DOC_TYPES (doc_types.py) ключи contract/contract_tz/tech_spec сохранены для
    # обратной совместимости прямых API-запросов.
    "service_note_delivery":    "СЗ на выдачу",
    "service_note_payment":     "СЗ на оплату",
    # Phase 19.05: split ТЗ and dedicated SZ на закупку
    "service_note_procurement": "СЗ на закупку",
    # Phase 19.07: СЗ на аванс
    "service_note_advance":     "СЗ на аванс",
    "tech_spec_request":        "ТЗ для запроса цен",
    "tech_spec_contract":       "ТЗ для договора",
    "approval_sheet":           "Лист согласования",
    "order_purchase":           "Приказ на закупку",
    # Phase 28: typed contract forms per-subsidy
    # Форма «услуги» объединена в один шаблон; большая/малая отчётность теперь
    # выбирается отдельной методичкой (methodology_large/small), приклеиваемой
    # к любому из семи договоров, а не отдельным шаблоном текста договора.
    "contract_services":             "Договор услуг",
    "contract_services_food":       "Договор услуг (питание)",
    "contract_goods_single":        "Договор поставки (разовый)",
    "contract_gph_individual":      "Договор ГПХ с физ.лицом (без РИД)",
    "contract_gph_individual_rid":  "Договор ГПХ с физ.лицом (+РИД)",
    "contract_repair_vehicle":      "Договор на ремонт ТС",
    "contract_repair_framework":    "Рамочный договор на ремонт ТС",
    # Методические рекомендации — приклеиваются к договору по Purchase.methodology
    "methodology_large":            "Методические рекомендации — большие",
    "methodology_small":            "Методические рекомендации — малые",
    # Fabrikant ЭТП package
    "fabrikant_instruction":        "Инструкция по заполнению заявки (Фабрикант)",
    "fabrikant_application_form":   "Форма заявки (Фабрикант)",
    "fabrikant_documentation":      "Документация к закупке (Фабрикант)",
    "fabrikant_contract_project":   "Проект договора (Фабрикант)",
    # Протокол закупочной комиссии
    "procurement_protocol":         "Протокол закупочной комиссии",
}


def _check_template_render_ok(path: str) -> bool:
    """Try a trial render with empty context; return True if template is valid."""
    if not os.path.exists(path):
        return False
    try:
        if DocxTemplate is None:
            return True  # docxtpl not installed — assume ok
        tpl = DocxTemplate(path)
        tpl.render({})
        return True
    except Exception:
        return False


@router.get("/{subsidy_id}/templates")
async def list_subsidy_templates(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('subsidies')),
):
    """List which doc types have a subsidy-specific template override."""
    # ИСПРАВЛЕНИЕ К2 (19.10.2026): require_tab('subsidies') — гейт «есть ли
    # вкладка хоть в одной своей орге», НЕ привязан к субсидии из path —
    # любой с вкладкой «Субсидии» читал шаблоны ЧУЖОЙ субсидии по id.
    from app.auth.object_visibility import ensure_subsidy_visible
    await ensure_subsidy_visible(current_user, subsidy_id, db)
    result = []
    subsidy_dir = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id))
    proto_path = os.path.join(subsidy_dir, "procurement_protocol.docx")
    if not os.path.exists(proto_path) and os.path.exists(subsidy_dir):
        try:
            from app.services.documents.protocol_docx_helpers import resolve_or_build_subsidy_protocol_base_doc
            resolve_or_build_subsidy_protocol_base_doc(subsidy_id, custom_dir=subsidy_dir)
        except Exception as e:
            logger.debug("Failed auto-generating protocol template for %s: %s", subsidy_id, e)

    for doc_type, label in SUPPORTED_DOC_TYPES.items():
        path = os.path.join(subsidy_dir, f"{doc_type}.docx")
        global_path = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")
        has_custom = os.path.exists(path)
        render_ok: bool | None = None
        if has_custom:
            render_ok = _check_template_render_ok(path)
        result.append({
            "doc_type": doc_type,
            "label": label,
            "has_custom": has_custom,
            "has_global": os.path.exists(global_path),
            "render_ok": render_ok,
        })
    return result


from app.services.documents.docx_normalization import (
    _normalize_docx_bytes,
    _normalize_docx_template,
    _peek_normalize_stats,
    _validate_renders_in_memory,
    _repair_docx_template,
)


@router.put("/{subsidy_id}/templates/{doc_type}")
async def upload_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    file: UploadFile = File(...),
    current_user=Depends(require_tab('subsidies')),
):
    """Upload a .docx template override for a specific subsidy and doc type."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    subsidy_dir = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id))
    os.makedirs(subsidy_dir, exist_ok=True)
    dest = os.path.join(subsidy_dir, f"{doc_type}.docx")

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # НЕ нормализуем файл на диске — организация загружает свой шаблон со
    # своими комментариями-подсказками, он должен остаться на диске ровно
    # таким, каким загружен (тот же дефект, что был в генерации — см.
    # stages_template_engine.py). Нормализация при необходимости происходит
    # лениво, в памяти, на каждом рендере (build_docx_template). Здесь —
    # только диагностическая оценка (informational, не применяется к файлу).
    norm_stats = _peek_normalize_stats(dest)
    repairs = _repair_docx_template(dest)

    # Trial render: validate docxtpl syntax before confirming upload — на
    # НОРМАЛИЗОВАННОЙ IN-MEMORY копии (нормализация могла быть нужна, чтобы
    # шаблон вообще собрался корректно для InlineImage), файл на диске не
    # трогаем.
    _validate_renders_in_memory(dest, doc_type)

    return {
        "ok": True,
        "doc_type": doc_type,
        "label": SUPPORTED_DOC_TYPES[doc_type],
        "repairs": repairs,
        "normalized": norm_stats,
    }


@router.get("/{subsidy_id}/templates/{doc_type}/download")
async def download_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    current_user=Depends(require_tab('subsidies')),
):
    """Download the current subsidy-specific template (or global if no override)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    subsidy_path = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
    global_path = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")

    if os.path.exists(subsidy_path):
        path = subsidy_path
    elif os.path.exists(global_path):
        path = global_path
    else:
        raise HTTPException(404, "Шаблон не найден")

    response = FileResponse(
        path,
        filename=f"{doc_type}_{subsidy_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@router.delete("/{subsidy_id}/templates/{doc_type}")
async def delete_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    current_user=Depends(require_tab('subsidies')),
):
    """Delete subsidy-specific template override (falls back to global)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    path = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Индивидуальный шаблон не найден")

    os.remove(path)
    return {"ok": True}


# ── Global template upload (admin) ──────────────────────────────────────────

@router.put("/global-templates/{doc_type}")
async def upload_global_template(
    doc_type: str,
    file: UploadFile = File(...),
    current_user=Depends(require_action('subsidy.edit')),
):
    """Upload a global .docx template (superadmin/account_owner only)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    dest = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # НЕ нормализуем на диске — та же причина, что в upload_subsidy_template
    # выше: загруженный глобальный шаблон должен сохранить свои комментарии-
    # подсказки на диске ровно как загружен.
    norm_stats = _peek_normalize_stats(dest)
    repairs = _repair_docx_template(dest)

    # Trial render на нормализованной IN-MEMORY копии — файл на диске не трогаем.
    _validate_renders_in_memory(dest, doc_type)

    return {"ok": True, "doc_type": doc_type, "repairs": repairs, "normalized": norm_stats}


@router.post("/templates/normalize-all")
async def normalize_all_existing_templates(
    current_user=Depends(require_action('subsidy.edit')),
):
    """One-shot migration: normalize every existing .docx template in place.

    Walks SUBSIDY_TEMPLATES_BASE and TEMPLATES_BASE, strips Word-internal
    markers from each file. Idempotent — safe to call multiple times.

    ⚠️ ОСОЗНАННО РАЗРУШИТЕЛЬНО: вместе с proofErr/bookmark/pageBreak-маркерами
    безвозвратно СТИРАЕТ Word-комментарии (подсказки к полям) из КАЖДОГО
    затронутого файла на диске — ровно то, что раньше происходило случайно,
    на каждом рендере (см. _normalize_docx_template выше). Вызывать только
    сознательно, понимая, что подсказки пользователей после этого исчезнут.
    Обычная генерация и upload-эндпоинты нормализацию на диск больше не
    делают — она им не нужна (in-memory на рендере / peek-only на upload).
    """
    processed = []
    errors = []

    def _walk_and_normalize(root: str):
        if not os.path.isdir(root):
            return
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".docx"):
                    continue
                fpath = os.path.join(dirpath, fn)
                try:
                    stats = _normalize_docx_template(fpath)
                    processed.append({"path": fpath, "stripped": stats})
                    try:
                        repairs = _repair_docx_template(fpath)
                        if repairs:
                            processed[-1]["repairs"] = repairs
                    except Exception as re_err:
                        errors.append({"path": fpath, "error": f"repair: {re_err}"})
                except Exception as e:
                    errors.append({"path": fpath, "error": str(e)})

    _walk_and_normalize(SUBSIDY_TEMPLATES_BASE)
    _walk_and_normalize(TEMPLATES_BASE)

    return {"ok": True, "processed": len(processed), "errors": len(errors), "details": processed, "error_details": errors}

