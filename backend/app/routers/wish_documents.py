"""Wish documents router — generates docx service notes for wishes (D-07, Phase 13).

Separate from documents.py to keep contracts clean:
  - documents.py is keyed on purchase_id
  - wish_documents.py is keyed on wish_id (no purchase yet — pre-approval)

Endpoint: GET /api/wishes/{wish_id}/documents/service_note
  - Builds docxtpl context from Wish + WishItem directly (not from Purchase)
  - Phase 19.07: primary template is service_note_procurement.docx (СЗ на закупку),
    with fallback to legacy service_note.docx if the procurement template is
    not yet uploaded (globally or per-subsidy)
  - Defensive: fills empty strings for all purchase-only keys so render never crashes
  - Returns .docx as StreamingResponse with Content-Disposition filename
  - NOTE: Endpoint URL kept as /service_note (not /service_note_procurement)
    for backwards compat with frontend callers.
"""
import os
from io import BytesIO
from datetime import date
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
    _fmt_date, _fmt_money, TEMPLATES_DIR,
    _resolve_user_dept as _resolve_user_dept_for_wish,
    _resolve_user_position as _resolve_user_position_for_wish,
)

router = APIRouter(prefix="/api/wishes", tags=["wish-documents"])

SUBSIDY_TEMPLATES_DIR = "/app/uploads/templates"
UPLOADS_DIR = "/app/uploads/products"


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
    Phase 19.07: uses service_note_procurement.docx as the primary template
    (СЗ на закупку — the natural wish-stage SZ). Falls back to legacy
    service_note.docx if the procurement template hasn't been uploaded yet.
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

    # ── Resolve template path (subsidy-specific override supported) ─────────
    # Phase 19.07: prefer service_note_procurement.docx, fall back to legacy
    # service_note.docx so existing deployments keep working.
    PRIMARY_FILE = "service_note_procurement.docx"
    FALLBACK_FILE = "service_note.docx"

    template_path = None
    if w.subsidy_id:
        for fname in (PRIMARY_FILE, FALLBACK_FILE):
            candidate = os.path.join(
                SUBSIDY_TEMPLATES_DIR, "subsidies", str(w.subsidy_id), fname
            )
            if os.path.exists(candidate):
                template_path = candidate
                break
    if template_path is None:
        for fname in (PRIMARY_FILE, FALLBACK_FILE):
            candidate = os.path.join(TEMPLATES_DIR, fname)
            if os.path.exists(candidate):
                template_path = candidate
                break
    if template_path is None or not os.path.exists(template_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Шаблон {PRIMARY_FILE} (или {FALLBACK_FILE}) не найден. "
                f"Поместите файл в backend/templates/{PRIMARY_FILE}"
            ),
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
                initiator = SimpleNamespace(
                    full_name=u.full_name or u.username,
                    role_name=u.position or "",
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
        from docxtpl import DocxTemplate, InlineImage
        from docx.shared import Cm
        tpl = DocxTemplate(template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки шаблона: {e}")

    def _resolve_photo(photo_url):
        """Return InlineImage for local product photos, empty string otherwise."""
        if not photo_url:
            return ""
        url = str(photo_url).strip()
        local_path = None
        if url.startswith("/api/products/photos/"):
            fname = url.split("/")[-1]
            local_path = f"{UPLOADS_DIR}/{fname}"
        if not local_path or not os.path.exists(local_path):
            return ""
        try:
            return InlineImage(tpl, local_path, width=Cm(2.5))
        except Exception:
            return ""

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
            "photo": _resolve_photo(it.product.photo_url if it.product else None),
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
    def _format_initials(full: str) -> str:
        if not full:
            return ""
        parts = (full or "").strip().split()
        if not parts:
            return ""
        surname = parts[0]
        initials = []
        for p_word in parts[1:3]:
            if p_word and p_word[0].isalpha():
                initials.append(p_word[0].upper() + ".")
        return f"{surname} {''.join(initials)}".strip()

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

    safe_name = f"SZ_Wish_{w.id}.docx"
    encoded = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
