import os
from io import BytesIO
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.jwt import get_current_user
from typing import Optional

# NOTE: this router is also used as a re-export facade by other modules
# (app/routers/wish_documents.py, app/routers/publications.py, and several
# tests import helpers directly from `app.routers.documents` / `docs.<name>`).
# Wave 3f split the generate_document() BODY out into services/documents/*,
# but these re-exports must stay so nothing outside this file breaks — do
# NOT trim this block just because generate_document() itself no longer
# calls most of these directly.
from app.services.documents.morphology import (
    _morph,
    _petro,
    _get_morph,
    _get_petro,
    _to_gen_word_heuristic,
    _to_gen_word,
    _to_gen_phrase,
    _inflect_phrase_genitive,
    _to_gen_fio,
)
from app.services.documents.doc_types import (
    TEMPLATES_DIR,
    SUBSIDY_TEMPLATES_DIR,
    RECEIPTS_TABLE_MARKER,
    DOC_TYPES,
    CONTRACT_FAMILY_DOC_TYPES,
    CONTRACT_TYPED_FORM_DOC_TYPES,
    DOC_TYPE_FALLBACK_FILES,
    _BASIS_LABELS,
    _PURCHASE_METHOD_LABELS,
    _COMPETITIVE_FORM_LABELS,
    PURCHASE_METHOD_REQUIRED_DOC_TYPES,
    VAT_RATE_PRINTED_DOC_TYPES,
    VAT_EXEMPTION_ARTICLE_NPD,
    VAT_EXEMPTION_ARTICLE_GPH_INDIVIDUAL,
    _GPH_INDIVIDUAL_CONTRACT_FORMS,
    FEO_PATH_UNRESOLVED_LABEL,
    FABRIKANT_PKG_FILE_NAMES,
    TEMPLATE_VARIABLES,
)
from app.services.documents.formatting import (
    _fmt_date,
    _clean_id,
    _fmt_money,
    _fmt_money_plain,
    _merge_identical_items,
    _signatory_position,
    _fio_to_genitive,
    _format_initials,
    _format_initials_safe,
    _INITIALS_WORD_RE,
    _resolve_responsible_person_update,
    _fio_to_initials,
    _fio_to_initials_prefix,
    _chunk_to_words,
    _rubles_to_words,
    _ONES,
    _TENS,
    _HUNDREDS,
    _ONES_F,
)
from app.services.documents.templates import (
    _sanitize_subject,
    _insert_receipts_table_if_marker,
    _resolve_doc_template_path,
    _purchase_method_label,
    _resolve_vat_exemption_basis,
    _require_vat_rate_for_doc,
    _vat_exemption_missing_hint,
    _require_purchase_method_for_doc,
)
from app.services.documents.contexts import (
    _signatory_split,
    _sum_items_price,
    _build_acceptance_doc_context,
    _build_contract_items_context,
    _build_contract_item_feo_paths,
    _build_items_list_from_contract_items,
    _build_items_list_from_purchase_items,
    _resolve_doc_amount,
    _require_contract_items_for_doc,
    _resolve_user_dept,
    _resolve_user_position,
    _format_service_term,
)
from app.services.documents.docx_post import _strip_tech_spec_legend, _strip_word_comments
from app.services.documents.fabrikant_package import render_fabrikant_package_files
from app.services.documents.kp_xlsx import build_kp_xlsx
from app.services.documents.generate import generate_document_bytes


router = APIRouter(prefix="/api/purchases", tags=["documents"])
guide_router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{pid}/documents/{doc_type}")
async def generate_document(
    pid: int,
    doc_type: str,
    approver_ids: Optional[str] = Query(default=None, description="ID согласующих через запятую"),
    initiator_id: Optional[int] = Query(default=None, description="ID инициатора служебной записки"),
    responsible_name: Optional[str] = Query(default=None, description="ФИО ответственного исполнителя (переопределяет поле закупки)"),
    tz_override_mode: Optional[str] = Query(default=None, description="Переопределить режим ТЗ: 'exact' или '44fz'"),
    merge: Optional[str] = Query(default=None, description="Phase 19.06: merge with another doc_type (e.g. 'tech_spec_contract') — appends its paragraphs/tables as a new section after the primary doc"),
    doc_indices: Optional[str] = Query(default=None, description="Phase 27.2: CSV индексов acceptance_docs для СЗ на оплату/аванс (напр. '0,2,3')"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Thin wrapper (wave 3f refactor) — see services/documents/generate.py for
    the actual stage-by-stage orchestration; behavior is unchanged."""
    buf, media_type, resp_headers = await generate_document_bytes(
        db, pid, doc_type, current_user,
        approver_ids=approver_ids,
        initiator_id=initiator_id,
        responsible_name=responsible_name,
        tz_override_mode=tz_override_mode,
        merge=merge,
        doc_indices=doc_indices,
    )
    return StreamingResponse(buf, media_type=media_type, headers=resp_headers)



@router.get("/{pid}/fabrikant-package")
async def download_fabrikant_package(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Render and ZIP 5 documents for ЭТП Fabrikant.

    Individual render failures are tolerated: the failed doc is omitted from
    the ZIP and listed in errors.txt.  If ALL docs fail → HTTP 500.
    """
    import zipfile as _zipfile

    rendered, errors = await render_fabrikant_package_files(db, pid)

    if not rendered:
        raise HTTPException(
            500,
            detail={
                "code": "TEMPLATE_RENDER_ERROR",
                "message": "Не удалось сформировать ни один документ для пакета Фабрикант",
                "error_raw": "\n".join(errors),
            },
        )

    # ZIP archive names: Russian base + actual extension from ascii_name
    _ru_bases = ["Инструкция", "Форма_заявки", "Документация", "Проект_договора", "ТЗ"]
    zip_buf = BytesIO()
    with _zipfile.ZipFile(zip_buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        _ru_iter = iter(_ru_bases)
        for ascii_name, ru_title, data in rendered:
            _ru_base = next(_ru_iter, os.path.splitext(ascii_name)[0])
            _ext = os.path.splitext(ascii_name)[1] or ".docx"
            zf.writestr(_ru_base + _ext, data)
        if errors:
            zf.writestr("errors.txt", "\n\n".join(errors))
    zip_buf.seek(0)

    safe_zip_name = f"Фабрикант_закупка_{pid}.zip"
    encoded_zip_name = quote(safe_zip_name, safe="-_.~")
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip_name}"},
    )


# ── KP xlsx export ───────────────────────────────────────────────────────────

@guide_router.get("/purchases/{pid}/kp-xlsx")
async def download_kp_xlsx(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate xlsx with purchase items (for КП request attachment)."""
    return await build_kp_xlsx(pid, db)


@guide_router.get("/template-guide")
async def download_template_guide(
    current_user=Depends(get_current_user),
):
    """Download a .docx reference guide with all available template variables."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    doc.add_heading("Руководство по разметке шаблонов документов", 0)

    p = doc.add_paragraph(
        "Шаблоны документов используют синтаксис Jinja2 (docxtpl). "
        "Переменные заключаются в двойные фигурные скобки: {{variable}}. "
        "Для циклов используется синтаксис: {%tr for item in items %} ... {%tr endfor %}."
    )

    doc.add_heading("Доступные переменные", 1)

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Переменная"
    hdr[1].text = "Описание"
    hdr[2].text = "Пример записи"
    hdr[3].text = "Результат"
    for cell in hdr:
        for run in cell.paragraphs[0].runs:
            run.bold = True

    for var, desc, ex_t, ex_r in TEMPLATE_VARIABLES:
        if not var:
            # Section header row
            row = table.add_row().cells
            row[0].merge(row[3])
            p = row[0].paragraphs[0]
            run = p.add_run(desc)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
            continue
        row = table.add_row().cells
        row[0].text = var
        row[1].text = desc
        row[2].text = ex_t
        row[3].text = ex_r

    doc.add_heading("Примеры использования в шаблоне Word", 1)

    doc.add_heading("Таблица согласующих", 2)
    doc.add_paragraph(
        '{%tr for a in approvers %}\n'
        '| {{a.num}} | {{a.role_name}} | {{a.full_name}} | {{a.signature_img}} | {{a.decided_date}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Таблица позиций закупки", 2)
    doc.add_paragraph(
        '{%tr for item in items %}\n'
        '| {{item.num}} | {{item.name}} | {{item.quantity}} | {{item.unit}} | {{item.unit_price}} | {{item.total_price}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Уровни субсидии (ФЭО)", 2)
    doc.add_paragraph(
        "Вставьте одну из этих переменных в нужное место шаблона Word:\n\n"
        "  Полный путь одной строкой:\n"
        "    {{feo_path}}\n"
        "  → Пример: «Персонал → Зарплата → Основной ФОТ»\n\n"
        "  Отдельные уровни:\n"
        "    Направление: {{feo_level_1}}\n"
        "    Тип:         {{feo_level_2}}\n"
        "    Категория:   {{feo_level_3}}\n\n"
        "Если закупка без ФЭО-категорий — переменные будут пустыми.\n"
        "Если у субсидии только 1 уровень — feo_level_2 и feo_level_3 пустые."
    )

    doc.add_heading("Условные блоки (НДС)", 2)
    doc.add_paragraph(
        '{% if vat_applicable %}\n'
        'В том числе НДС {{vat_rate}}%: {{vat_amount_num}} руб.\n'
        '{% else %}\n'
        'НДС не облагается {{vat_exemption_article}}\n'
        '{% endif %}'
    )

    doc.add_heading("Частые ошибки", 1)
    doc.add_paragraph(
        "1. Русский текст внутри {{ }} — ошибка: {{ contract_date г. }}\n"
        "   Правильно: {{ contract_date }} г.\n\n"
        "2. Word разбивает переменную на фрагменты — удалите и наберите заново\n\n"
        "3. Пустое значение — поле не заполнено в карточке закупки"
    )

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('Инструкция_по_шаблонам.docx', safe='-_.~')}"},
    )


@guide_router.get("/template-vars")
async def get_template_vars(current_user=Depends(get_current_user)):
    """Return all template variables with description, example template text, and example result."""
    result = []
    for entry in TEMPLATE_VARIABLES:
        var, desc, ex_t, ex_r = entry
        if not var:
            continue  # skip section headers
        result.append({
            "var": var,
            "description": desc,
            "example_template": ex_t,
            "example_result": ex_r,
        })
    return result
