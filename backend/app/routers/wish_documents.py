"""Wish documents router — generates docx service notes for wishes (D-07, Phase 13).

Separate from documents.py to keep contracts clean:
  - documents.py is keyed on purchase_id
  - wish_documents.py is keyed on wish_id (no purchase yet — pre-approval)

Endpoint: GET /api/wishes/{wish_id}/documents/service_note
  - Builds docxtpl context from Wish + WishItem directly (not from Purchase)
  - doc_type выбирается по wish.source: 'advance_report' → service_note_advance
    (СЗ на аванс), иначе — service_note_procurement (СЗ на закупку). Раньше
    здесь ВСЕГДА была служебка на закупку, независимо от source — авансовый
    компаньон заявки печатал не тот бланк.
  - Резолюция файла шаблона — ЧЕРЕЗ _resolve_doc_template_path (services/
    documents/templates.py), ТОТ ЖЕ приоритет «субсидия → глобальный →
    fallback», что использует общий /api/purchases/{pid}/documents/{doc_type}
    (см. Правило №6 — жалоба владельца 2026-09-17: своя копия резолвера здесь
    игнорировала субсидийный override для service_note_advance, потому что
    вообще не знала о таком doc_type).
  - Defensive: fills empty strings for all purchase-only keys so render never crashes
  - Returns .docx as StreamingResponse with Content-Disposition filename
  - NOTE: Endpoint URL kept as /service_note (not /service_note_procurement)
    for backwards compat with frontend callers.
"""
import os
from io import BytesIO
from datetime import date
import re as _re
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.subsidy_approver import SubsidyApprover
# Reuse formatters from documents.py — avoids duplicating money/date formatting logic
from app.routers.documents import (
    _fmt_date, _fmt_money,
    _format_initials,
    _resolve_user_dept as _resolve_user_dept_for_wish,
    _resolve_user_position as _resolve_user_position_for_wish,
)
# Правило №6 — единственный резолвер фото товара (app/services/documents/
# product_photos.py, канонический products.photo_data + запасные ветки),
# re-export'нутый здесь же, где его берёт и generate.py. Раньше в этом
# файле жила урезанная копия-дубль (_resolve_local_product_photo), умевшая
# только локальный /api/products/photos/<file> и не знавшая про photo_data.
from app.services.documents.stages_template_engine import make_photo_resolver
# Правило №6 — единственный резолвер пути к шаблону документа (субсидийный
# override → глобальный → DOC_TYPE_FALLBACK_FILES). До 2026-09-17 здесь жила
# урезанная копия-дубль (PRIMARY_FILE/FALLBACK_FILE ниже), которая не умела
# service_note_advance вовсе — авансовый компаньон заявки получал службу на
# закупку/глобальный бланк, даже когда для субсидии был загружен свой
# service_note_advance.docx.
from app.services.documents.templates import _resolve_doc_template_path

router = APIRouter(prefix="/api/wishes", tags=["wish-documents"])


@router.get("/{wish_id}/documents/service_note")
async def generate_wish_service_note(
    wish_id: int,
    initiator_id: Optional[int] = Query(
        default=None,
        description="ID инициатора (SubsidyApprover) — заполняет initiator_name/initiator_role в шаблоне",
    ),
    responsible_name: Optional[str] = Query(
        default=None,
        description="ФИО ответственного (переопределяет creator)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a Служебная Записка .docx from Wish data (pre-approval, no purchase required).

    D-07 requirement: download button in WishesView available BEFORE approve.
    doc_type: service_note_advance для авансового компаньона заявки
    (wish.source == 'advance_report'), иначе service_note_procurement (СЗ на
    закупку — обычная wish-stage СЗ). Резолюция файла — через
    _resolve_doc_template_path (см. докстринг модуля, Правило №6).
    """
    # ── Load wish with eager relations ──────────────────────────────────────
    result = await db.execute(
        select(Wish)
        .options(
            selectinload(Wish.creator),
            selectinload(Wish.executor),
            selectinload(Wish.subsidy),
            selectinload(Wish.items).selectinload(WishItem.product),
        )
        .where(Wish.id == wish_id)
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # ── Resolve doc_type + template path (subsidy override → global → fallback) ──
    _note_doc_type = "service_note_advance" if getattr(w, "source", None) == "advance_report" else "service_note_procurement"
    template_path, _tpl_file, _tpl_base = _resolve_doc_template_path(_note_doc_type, w.subsidy_id)
    if not os.path.exists(template_path):
        raise HTTPException(
            status_code=404,
            detail=f"Шаблон {_tpl_file} не найден. Поместите файл в backend/templates/{_tpl_file}",
        )

    # ── Load initiator if provided ──────────────────────────────────────────
    # Бизнес-правило: за другого человека делать СЗ может только тот, кому
    # подчинён этот человек (тот же scope что _get_visible_user_ids для задач).
    # Самого себя — всегда можно.
    initiator = None
    if initiator_id and initiator_id != getattr(current_user, "id", None):
        from app.routers.task_visibility import _get_visible_user_ids
        visible = await _get_visible_user_ids(current_user, db)
        if visible is not None and initiator_id not in visible:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INITIATOR_FORBIDDEN",
                    "message": (
                        "Указанный инициатор вам не подчинён. Сделать служебную "
                        "записку за другого человека может только его руководитель."
                    ),
                },
            )
    if initiator_id:
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.user_id == initiator_id)
            .options(selectinload(SubsidyApprover.user))
            .order_by(SubsidyApprover.id)
            .limit(1)
        )
        initiator = res.scalar_one_or_none()
        if initiator is None:
            from app.models.user import User as UserModel
            from types import SimpleNamespace
            u = (
                await db.execute(select(UserModel).where(UserModel.id == initiator_id))
            ).scalar_one_or_none()
            if u:
                # Rule #6: не читаем u.position напрямую — единственный резолвер
                # должности (org-aware, с legacy fallback внутри) уже здесь.
                initiator = SimpleNamespace(
                    full_name=u.full_name or u.username,
                    role_name=await _resolve_user_position_for_wish(
                        u, db, getattr(w.subsidy, "org_id", None) if w.subsidy else None
                    ),
                    user=u,
                )

        # Membership-check: инициатор должен состоять в организации, к которой
        # привязана субсидия заявки.
        subsidy_org_id = getattr(w.subsidy, "org_id", None) if w.subsidy else None
        init_user = initiator.user if (initiator and getattr(initiator, "user", None)) else None
        if subsidy_org_id and init_user:
            from app.models.user_organization import UserOrganization
            mem = (await db.execute(
                select(UserOrganization.id).where(
                    UserOrganization.user_id == init_user.id,
                    UserOrganization.org_id == subsidy_org_id,
                ).limit(1)
            )).first()
            if not mem and getattr(init_user, "org_id", None) != subsidy_org_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "INITIATOR_NOT_IN_ORG",
                        "message": (
                            "Инициатор не состоит в организации, к которой "
                            "привязана субсидия заявки. Выберите сотрудника "
                            "этой организации."
                        ),
                    },
                )

    # ── Build DocxTemplate object (needed early for InlineImage) ────────────
    try:
        from docxtpl import DocxTemplate
        tpl = DocxTemplate(template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки шаблона: {e}")

    resolve_photo = make_photo_resolver(tpl)

    # ── Build items list (same shape as documents.py items_list) ────────────
    items_list = []
    for idx, it in enumerate(w.items or [], start=1):
        items_list.append({
            "num": idx,
            "name": it.item_name or "",
            "description": (it.product.description if it.product else "") or "",
            "type": it.item_type or "",
            "quantity": float(it.quantity) if it.quantity else "",
            "unit": it.unit or "",
            "unit_price": _fmt_money(it.unit_price),
            "total_price": _fmt_money(it.total_price),
            "photo": resolve_photo(it.product),
        })

    # ── Unique product categories for {{item_categories}} ───────────────────
    item_categories = list(dict.fromkeys(
        it.product.category
        for it in (w.items or [])
        if it.product and it.product.category
    ))
    item_categories_str = ", ".join(item_categories)

    # ── Aggregates ───────────────────────────────────────────────────────────
    total_nmck = sum(float(i.total_price or 0) for i in (w.items or []))
    creator_full = (
        (w.creator.full_name if w.creator else "")
        or (w.creator.username if w.creator else "")
        or ""
    )

    # B-dedup: ФИО → инициалы для responsible_person в шаблоне
    executor_full = (w.executor.full_name if getattr(w, 'executor', None) else "") or ""
    responsible_raw = responsible_name or executor_full or creator_full
    responsible_initials = _format_initials(responsible_raw)

    # ── Build context dict ───────────────────────────────────────────────────
    # All keys from documents.py template context are present.
    # Purchase-only keys default to empty string/list so the template never errors.
    context = {
        # Wish presented as pseudo-purchase for template compatibility
        "purchase_number": f"заявка #{w.id}",
        "registry_number": f"WISH-{w.id}",
        "purchase_method": "",
        "subject": w.title or "",
        "status": w.status or "",
        "purchase_basis": "",
        "contract_type": "",
        "responsible_person": responsible_initials,  # инициалы (default)
        "responsible_person_full": responsible_raw,   # полное ФИО
        # B-exec: Срок исполнения и Исполнитель (ставит согласующий)
        "execution_deadline": _fmt_date(w.execution_deadline) if getattr(w, 'execution_deadline', None) else "",
        "executor_name": _format_initials(executor_full),
        "executor_name_full": executor_full,
        # Subsidy
        "subsidy_name": w.subsidy.name if w.subsidy else "",
        "subsidy_year": w.subsidy.year if w.subsidy else "",
        "subsidy_budget": "",
        # Initiator — должность/отдел per-org (org субсидии заявки)
        "initiator_name": (initiator.full_name if initiator else creator_full) or "",
        "initiator_role": (
            await _resolve_user_position_for_wish(
                initiator.user if (initiator and getattr(initiator, "user", None)) else None,
                db,
                getattr(w.subsidy, "org_id", None) if w.subsidy else None,
            )
            or (initiator.role_name if initiator else "")
        ),
        "initiator_dept": await _resolve_user_dept_for_wish(
            initiator.user if (initiator and getattr(initiator, "user", None)) else None,
            db,
            getattr(w.subsidy, "org_id", None) if w.subsidy else None,
        ),
        # Items
        "items": items_list,
        "items_count": len(items_list),
        "item_names": ", ".join(i["name"] for i in items_list if i["name"]),
        "item_categories": item_categories_str,
        # Totals
        # Phase 19: total_nmcd is the new canonical name; total_nmck kept
        # as a deprecated alias so legacy templates keep rendering.
        "total_nmcd": _fmt_money(total_nmck),
        "total_nmck": _fmt_money(total_nmck),
        "nmck": _fmt_money(total_nmck),
        # Approvers (empty — no signatures yet, wish is pre-approval)
        "approvers": [],
        # Dates
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
        # FEO paths (not resolved for wishes — template may reference these)
        "feo_category_name": "",
        "feo_path": "",
        "feo_level_1": "",
        "feo_level_2": "",
        "feo_level_3": "",
        # Contractor fields (no contractor before purchase)
        "contractor_name": "",
        "contractor_short_name": "",
        "contractor_org_type": "",
        "contractor_inn": "",
        "contractor_kpp": "",
        "contractor_ogrn": "",
        "contractor_address": "",
        "contractor_postal_address": "",
        "contractor_phone": "",
        "contractor_email": "",
        "contractor_signatory": "",
        "contractor_signatory_basis": "",
        "contractor_signatory_position": "",
        "contractor_signatory_line": "",
        "contractor_settlement_account": "",
        "contractor_bank_name": "",
        "contractor_bank_details": "",
        "contractor_bik": "",
        "contractor_correspondent_account": "",
        # Contract fields (no contract before approve)
        "contract_number": "",
        "contract_date": "",
        "contract_date_day": "",
        "contract_date_month": "",
        "contract_date_year": "",
        "contract_price": "",
        "contract_price_num": "",
        "contract_price_words": "",
        "economy": "",
        "price_increase": "",
        "execution_term": "",
        "execution_term_changed": "",
        "delivery_date": "",
        "country_origin": "",
        "service_name": w.title or "",
        "period_type": "period",
        "service_start_date": "",
        "service_end_date": "",
        "service_date": "",
        # Phase 19: extended service-term / submission / delivery / agreement
        # Wish stage has none of these — emit empty strings so templates don't error.
        "service_term": "",
        "service_term_mode": "",
        "service_term_days": "",
        "service_term_type": "",
        "service_term_type_name": "",
        "service_deadline_date": "",
        "submission_deadline_date": "",
        "submission_deadline_time": "",
        "submission_deadline_datetime": "",
        "delivery_location": "",
        "subsidy_agreement_text": (w.subsidy.agreement_text if (w.subsidy and w.subsidy.agreement_text) else ""),
        "third_party_involved": False,
        # VAT fields (not applicable pre-purchase)
        "vat_applicable": False,
        "vat_rate": 20,
        "vat_amount_num": "",
        "vat_amount_words": "",
        "vat_exemption_article": "",
        "vat_info_line": "НДС не применимо (заявка)",
        # Acceptance / payment (no documents yet)
        "acceptance_doc_name": "",
        "acceptance_doc_number": "",
        "acceptance_doc_date": "",
        "acceptance_doc_amount": "",
        "payment_doc_number": "",
        "payment_doc_date": "",
        "payment_amount": "",
        "payment_federal": "",
        # Event
        "event_name": "",
    }

    # ── Render template ──────────────────────────────────────────────────────
    try:
        tpl.render(context)
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации документа: {e}")

    _wish_title = (w.title or "").strip()
    _wish_title = _re.sub(r'[\\/:*?"<>|\r\n]+', "", _wish_title)
    _wish_title = _re.sub(r'\s+', "_", _wish_title)[:50]
    if _wish_title:
        safe_name = f"Служебная_записка_{_wish_title}.docx"
    else:
        safe_name = f"Служебная_записка_заявка_{w.id}.docx"
    encoded = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.get("/{wish_id}/documents/tech_spec")
async def generate_wish_tech_spec(
    wish_id: int,
    tz_override_mode: Optional[str] = Query(
        default=None,
        description="Переопределить режим ТЗ: 'exact' или '44fz' (по умолчанию — точное описание)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate Техническое задание .docx from Wish items (pre-approval, no purchase yet).

    Владелец (2026-09-16): «вкладка ТЗ, только свёрнутая, как в закупке» —
    свёрнутая секция ТЗ у заявки (WishTzSection.vue) скачивает документ отсюда.

    Построение items_list — ЧЕРЕЗ _build_items_list_from_purchase_items
    (services/documents/contexts.py), тот же построитель, что печатает ТЗ уже
    подтверждённой закупки — докстринг item_form_summary явно говорит, что он
    годится и для WishItem (Правило №6: не второй построитель контекста).
    Резолюция файла шаблона — ЧЕРЕЗ _resolve_doc_template_path (services/
    documents/templates.py), тот же приоритет «субсидия → глобальный →
    fallback», что использует общий /api/purchases/{pid}/documents/{doc_type};
    doc_type 'tech_spec' резолвится в contract_tz.docx (doc_types.DOC_TYPES) —
    тот же файл, что печатает ТЗ закупки по кнопкам «ТЗ для запроса цен» /
    «ТЗ для договора» (оба тоже падают на contract_tz.docx, см.
    DOC_TYPE_FALLBACK_FILES).

    Заявка ещё не одобрена — договорных/контрагентских полей шаблона нет,
    заполняются пустой строкой (тот же приём, что и в generate_wish_service_note
    выше)."""
    result = await db.execute(
        select(Wish)
        .options(
            selectinload(Wish.subsidy),
            selectinload(Wish.items).selectinload(WishItem.product),
        )
        .where(Wish.id == wish_id)
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if not (w.items or []):
        raise HTTPException(status_code=422, detail="В заявке нет позиций — нечего печатать в ТЗ")

    from app.services.documents.contexts import _build_items_list_from_purchase_items
    from app.services.documents.templates import _resolve_doc_template_path

    template_path, _tpl_file, _tpl_base = _resolve_doc_template_path("tech_spec", w.subsidy_id)
    if not os.path.exists(template_path):
        raise HTTPException(
            status_code=404,
            detail=f"Шаблон ТЗ ({_tpl_file}) не найден. Поместите файл в backend/templates/{_tpl_file}",
        )

    try:
        from docxtpl import DocxTemplate
        tpl = DocxTemplate(template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки шаблона: {e}")

    resolve_photo = make_photo_resolver(tpl)

    items_list = _build_items_list_from_purchase_items(
        w, tz_override_mode=tz_override_mode, resolve_photo=resolve_photo,
    )
    total_nmck_val = sum(float(it.total_price or 0) for it in (w.items or []))

    # Договорных/контрагентских полей у заявки ещё нет (пре-одобрение) — те же
    # пустые дефолты, что и в generate_wish_service_note выше, чтобы шаблон
    # contract_tz.docx не падал на отсутствующих плейсхолдерах.
    context = {
        "registry_number": f"WISH-{w.id}",
        "purchase_method": "",
        "subsidy_name": w.subsidy.name if w.subsidy else "",
        "subsidy_year": w.subsidy.year if w.subsidy else "",
        "total_nmck": _fmt_money(total_nmck_val),
        "contract_number": "",
        "contract_date": "",
        "contract_price": "",
        "economy": "",
        "execution_term": "",
        "contractor_name": "",
        "contractor_address": "",
        "contractor_inn": "",
        "contractor_kpp": "",
        "contractor_ogrn": "",
        "contractor_bank_details": "",
        "contractor_signatory_line": "",
        "items": items_list,
    }

    try:
        tpl.render(context)
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации документа: {e}")

    _wish_title = (w.title or "").strip()
    _wish_title = _re.sub(r'[\\/:*?"<>|\r\n]+', "", _wish_title)
    _wish_title = _re.sub(r'\s+', "_", _wish_title)[:50]
    safe_name = f"ТЗ_{_wish_title}.docx" if _wish_title else f"ТЗ_заявка_{w.id}.docx"
    encoded = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
