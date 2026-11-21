# -*- coding: utf-8 -*-
"""Роутер для Дополнительных соглашений (ДС №1..N) к договору (Волна 4c).

ПРАВИЛО №5: < 500 строк.
ПРАВИЛО №6: единый источник генерации через app.services.documents.contract_amendment.
"""
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.subsidy import Subsidy
from app.services.documents.contract_amendment import generate_contract_amendment_docx

router = APIRouter(tags=["contracts"])


class PriceChangeSchema(BaseModel):
    new_price: float = Field(..., description="Новая цена договора")
    clause_ref: str = Field("3.1", description="Номер пункта договора о цене")
    vat_applicable: bool = Field(True, description="Облагается ли НДС")
    vat_rate: Optional[float] = Field(20.0, description="Ставка НДС (например 20)")


class TermChangeSchema(BaseModel):
    new_date: date = Field(..., description="Новая дата окончания / поставки")
    clause_ref: str = Field("4.1", description="Номер пункта договора о сроке")


class AmendmentItemSchema(BaseModel):
    name: str = Field(..., description="Наименование товара / услуги")
    unit: str = Field("шт.", description="Единица измерения")
    quantity: float = Field(1.0, description="Количество")
    unit_price: float = Field(0.0, description="Цена за единицу с НДС")
    total: Optional[float] = Field(None, description="Общая стоимость с НДС")


class GenerateAmendmentRequest(BaseModel):
    amendment_number: str = Field("1", description="Номер доп. соглашения (№1..N)")
    amendment_date: Optional[date] = Field(default_factory=date.today, description="Дата доп. соглашения")
    price_change: Optional[PriceChangeSchema] = None
    term_change: Optional[TermChangeSchema] = None
    specification_items: Optional[List[AmendmentItemSchema]] = None
    custom_clauses: Optional[List[str]] = None


@router.post("/{contract_id}/amendments/generate-docx")
async def generate_contract_amendment_endpoint(
    contract_id: int,
    body: GenerateAmendmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab("contracts")),
):
    """Генерация и скачивание .docx Дополнительного соглашения к договору."""
    # Загружаем договор с контрагентом и субсидией
    res = await db.execute(
        select(Contract)
        .options(selectinload(Contract.contractor), selectinload(Contract.subsidy))
        .where(Contract.id == contract_id)
    )
    contract = res.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Договор не найден")

    # Получаем данные организации Заказчика
    customer_org = None
    if contract.subsidy and contract.subsidy.organization_id:
        c_res = await db.execute(
            select(Organization).where(Organization.id == contract.subsidy.organization_id)
        )
        customer_org = c_res.scalar_one_or_none()

    if not customer_org:
        # Фолбэк на дефолтную/первую организацию
        o_res = await db.execute(select(Organization).limit(1))
        customer_org = o_res.scalar_one_or_none()

    # Формируем реквизиты Заказчика
    customer_data: Dict[str, Any] = {
        "full_name": customer_org.full_name if customer_org else "Всероссийский студенческий корпус спасателей",
        "short_name": customer_org.short_name if customer_org else "ВКСКС",
        "inn": customer_org.inn if customer_org else "",
        "kpp": customer_org.kpp if customer_org else "",
        "ogrn": customer_org.ogrn if customer_org else "",
        "address": customer_org.legal_address if customer_org else (customer_org.address if customer_org else ""),
        "settlement_account": customer_org.settlement_account if customer_org else "",
        "bank_name": customer_org.bank_name if customer_org else "",
        "bik": customer_org.bik if customer_org else "",
        "correspondent_account": customer_org.correspondent_account if customer_org else "",
        "signatory": customer_org.director_name if customer_org else "",
        "signatory_name": customer_org.director_name if customer_org else "",
        "signatory_position": customer_org.director_position if customer_org else "Руководитель",
        "signatory_basis": getattr(customer_org, "director_basis", "Устава") or "Устава",
    }

    # Формируем реквизиты Подрядчика
    contractor = contract.contractor
    contractor_data: Dict[str, Any] = {
        "full_name": contractor.full_name if contractor else (contractor.name if contractor else "Подрядчик"),
        "short_name": contractor.short_name if contractor else (contractor.name if contractor else "Подрядчик"),
        "inn": contractor.inn if contractor else "",
        "kpp": contractor.kpp if contractor else "",
        "ogrn": contractor.ogrn if contractor else "",
        "address": contractor.legal_address if contractor else (contractor.address if contractor else ""),
        "settlement_account": contractor.settlement_account if contractor else "",
        "bank_name": contractor.bank_name if contractor else "",
        "bik": contractor.bik if contractor else "",
        "correspondent_account": contractor.correspondent_account if contractor else "",
        "signatory": contractor.signatory if contractor else "",
        "signatory_name": contractor.signatory_name if contractor else (contractor.signatory if contractor else ""),
        "signatory_position": contractor.signatory_position if contractor else "Директор",
        "signatory_basis": contractor.signatory_basis if contractor else "Устава",
    }

    contract_data: Dict[str, Any] = {
        "id": contract.id,
        "number": contract.number,
        "date": contract.date,
        "city": getattr(customer_org, "contract_city", "Москва") or "Москва",
        "max_amount": float(contract.max_amount) if contract.max_amount else None,
    }

    amendment_data: Dict[str, Any] = {
        "amendment_number": body.amendment_number,
        "amendment_date": body.amendment_date or date.today(),
        "price_change": body.price_change.dict() if body.price_change else None,
        "term_change": body.term_change.dict() if body.term_change else None,
        "specification_items": [i.dict() for i in body.specification_items] if body.specification_items else None,
        "custom_clauses": body.custom_clauses,
    }

    docx_bytes = generate_contract_amendment_docx(
        contract_data=contract_data,
        amendment_data=amendment_data,
        customer_data=customer_data,
        contractor_data=contractor_data,
    )

    clean_num = str(body.amendment_number).strip().replace("/", "_")
    clean_contract = str(contract.number).strip().replace("/", "_")
    filename = f"Доп_соглашение_{clean_num}_к_договору_{clean_contract}.docx"

    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='-_.~')}"},
    )
