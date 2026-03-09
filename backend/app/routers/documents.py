import os
from io import BytesIO
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.auth.jwt import get_current_user
from typing import Optional

router = APIRouter(prefix="/api/purchases", tags=["documents"])

TEMPLATES_DIR = "/app/templates"

DOC_TYPES = {
    "service_note":   ("service_note.docx",   "Service_Note"),
    "contract_tz":    ("contract_tz.docx",    "Contract_TZ"),
    "approval_sheet": ("approval_sheet.docx", "Approval_Sheet"),
}

_BASIS_LABELS = {
    "plan_schedule": "план-график",
    "service_note": "служебная записка",
}


def _fmt_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d
    return d.strftime("%d.%m.%Y")


def _fmt_money(v) -> str:
    if v is None:
        return ""
    return f"{float(v):,.2f}".replace(",", " ").replace(".", ",") + " ₽"


@router.get("/{pid}/documents/{doc_type}")
async def generate_document(
    pid: int,
    doc_type: str,
    approver_ids: Optional[str] = Query(default=None, description="ID согласующих через запятую"),
    initiator_id: Optional[int] = Query(default=None, description="ID инициатора служебной записки"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}. Доступны: {', '.join(DOC_TYPES)}")

    template_file, filename_base = DOC_TYPES[doc_type]
    template_path = os.path.join(TEMPLATES_DIR, template_file)
    if not os.path.exists(template_path):
        raise HTTPException(
            404,
            f"Шаблон '{template_file}' не найден. "
            f"Поместите файл в backend/templates/{template_file}"
        )

    # Load purchase with related data
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()

    # Load approvers if requested
    selected_approvers = []
    if approver_ids:
        ids = [int(x.strip()) for x in approver_ids.split(",") if x.strip().isdigit()]
        if ids:
            res = await db.execute(
                select(SubsidyApprover)
                .where(SubsidyApprover.id.in_(ids))
                .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
            )
            selected_approvers = res.scalars().all()

    # Load initiator if requested
    initiator = None
    if initiator_id:
        res = await db.execute(select(SubsidyApprover).where(SubsidyApprover.id == initiator_id))
        initiator = res.scalar_one_or_none()

    # If no approvers specified — load defaults for this subsidy
    if not selected_approvers and p.subsidy_id:
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.subsidy_id == p.subsidy_id, SubsidyApprover.is_default == True)
            .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
        )
        selected_approvers = res.scalars().all()

    # Build template context
    items_list = []
    for idx, item in enumerate(p.items or [], start=1):
        items_list.append({
            "num": idx,
            "name": item.item_name or "",
            "description": (item.product.description if item.product and item.product.description else ""),
            "type": item.item_type or "",
            "quantity": float(item.quantity) if item.quantity else "",
            "unit": item.unit or "",
            "unit_price": _fmt_money(item.unit_price),
            "total_price": _fmt_money(item.total_price),
        })

    approvers_list = [
        {
            "num": i + 1,
            "role_name": a.role_name,
            "full_name": a.full_name,
            "note": "",
        }
        for i, a in enumerate(selected_approvers)
    ]

    c = p.contractor
    context = {
        # Закупка
        "purchase_number": p.purchase_number or "",
        "registry_number": p.registry_number or "",
        "purchase_method": {"single": "Единственный поставщик", "competitive": "Конкурсная процедура", "advance": "Авансовый отчёт"}.get(p.purchase_method or "", p.purchase_method or ""),
        "subject": p.subject or "",
        "status": p.status or "",
        "purchase_basis": _BASIS_LABELS.get(p.purchase_basis or "", ""),
        "responsible_person": p.responsible_person or "",
        # Субсидия
        "subsidy_name": subsidy.name if subsidy else "",
        "subsidy_year": subsidy.year if subsidy else "",
        "subsidy_budget": _fmt_money(subsidy.budget) if subsidy else "",
        # Контрагент — основные
        "contractor_name": c.name if c else "",
        "contractor_inn": c.inn if c else "",
        "contractor_kpp": c.kpp if c else "",
        "contractor_address": c.address if c else "",
        "contractor_postal_address": c.postal_address if c else "",
        "contractor_ogrn": c.ogrn if c else "",
        "contractor_phone": c.phone if c else "",
        "contractor_email": c.email if c else "",
        # Контрагент — подписант
        "contractor_signatory": c.signatory if c else "",
        "contractor_signatory_basis": c.signatory_basis if c else "",
        # Контрагент — банк
        "contractor_settlement_account": c.settlement_account if c else "",
        "contractor_bank_name": c.bank_name if c else "",
        "contractor_bik": c.bik if c else "",
        "contractor_correspondent_account": c.correspondent_account if c else "",
        # FEO
        "feo_category_name": p.feo_category.name if p.feo_category else "",
        # Финансы
        "total_nmck": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price),
        "nmck": _fmt_money(p.nmck or p.total_nmck),
        "contract_price": _fmt_money(p.contract_price),
        "economy": _fmt_money(p.economy),
        "price_increase": _fmt_money(p.price_increase),
        # Договор
        "contract_number": p.contract_number or "",
        "contract_date": _fmt_date(p.contract_date),
        "execution_term": _fmt_date(p.execution_term),
        "execution_term_changed": _fmt_date(p.execution_term_changed),
        "delivery_date": _fmt_date(p.delivery_date),
        "country_origin": p.country_origin or "",
        # Акт приёмки
        "acceptance_doc_name": p.acceptance_doc_name or "",
        "acceptance_doc_number": p.acceptance_doc_number or "",
        "acceptance_doc_date": _fmt_date(p.acceptance_doc_date),
        "acceptance_doc_amount": _fmt_money(p.acceptance_doc_amount),
        # Платёж
        "payment_doc_number": p.payment_doc_number or "",
        "payment_doc_date": _fmt_date(p.payment_doc_date),
        "payment_amount": _fmt_money(p.payment_amount),
        "payment_federal": _fmt_money(p.payment_federal),
        # Позиции
        "items": items_list,
        "items_count": len(items_list),
        "item_names": ", ".join(i["name"] for i in items_list if i["name"]),
        # Согласующие
        "approvers": approvers_list,
        "initiator_name": initiator.full_name if initiator else "",
        "initiator_role": initiator.role_name if initiator else "",
        # Служебные
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
    }

    try:
        from docxtpl import DocxTemplate
        tpl = DocxTemplate(template_path)
        tpl.render(context)
        buf = BytesIO()
        tpl.save(buf)
        buf.seek(0)
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации документа: {e}")

    safe_name = f"{filename_base}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    encoded_name = quote(safe_name, safe="-_.~")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
