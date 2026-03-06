import os
from io import BytesIO
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/purchases", tags=["documents"])

TEMPLATES_DIR = "/app/templates"

DOC_TYPES = {
    "service_note":   ("service_note.docx",   "Service_Note"),
    "contract_tz":    ("contract_tz.docx",    "Contract_TZ"),
    "approval_sheet": ("approval_sheet.docx", "Approval_Sheet"),
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

    c = p.contractor
    context = {
        # Закупка
        "purchase_number": p.purchase_number or "",
        "registry_number": p.registry_number or "",
        "purchase_method": {"single": "Единственный поставщик", "competitive": "Конкурсная процедура", "advance": "Авансовый отчёт"}.get(p.purchase_method or "", p.purchase_method or ""),
        "subject": p.subject or "",
        "status": p.status or "",
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
