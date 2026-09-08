"""Генерация ежемесячных этапов (Purchase-заявок) для рамочного договора.

Вынесено из app/routers/contracts.py (Правило №5, резка волны 2026-09-08).
Тот же префикс /api/contracts, путь POST "/{contract_id}/generate-monthly-stages"
на сегмент длиннее catch-all PUT/DELETE "/{cid}" ядра — порядок регистрации
относительно contracts.router не важен (см. комментарий в routes.py).
"""
import calendar
from datetime import date as date_type
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_tab
from app.database import get_db
from app.models.contract import Contract
from app.models.purchase import Purchase
from app.routers.purchase_budget import _assign_framework_seq

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

RU_MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
RU_MONTHS_NOM = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


class MonthlyStagesRequest(BaseModel):
    count: int = Field(..., ge=1, le=36)
    amount_per_stage: float
    start_year: int
    start_month: int = Field(..., ge=1, le=12)
    deadline_kind: Literal["end_of_month", "specific_day"]
    deadline_day: Optional[int] = Field(None, ge=1, le=31)
    subject_template: str = "{contract_name} — {month_name} {year}"
    subsidy_id: int
    feo_category_id: Optional[int] = None
    is_likely_needed: bool = True


@router.post("/{contract_id}/generate-monthly-stages")
async def generate_monthly_stages(
    contract_id: int,
    body: MonthlyStagesRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('contracts')),
):
    """Сгенерировать N ежемесячных этапов для рамочного договора."""
    contract = (await db.execute(select(Contract).where(Contract.id == contract_id))).scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Договор не найден")
    if not (contract.contract_type or "").startswith("framework_"):
        raise HTTPException(400, "Генерация этапов доступна только для рамочных договоров (framework_*)")

    contract_name = contract.subject or contract.number or f"Договор #{contract_id}"

    created_items = []
    skipped_items = []

    year = body.start_year
    month = body.start_month

    for i in range(body.count):
        # compute (year, month) for this stage
        cur_year = year + (month - 1 + i) // 12
        cur_month = (month - 1 + i) % 12 + 1

        last_day = calendar.monthrange(cur_year, cur_month)[1]
        if body.deadline_kind == "end_of_month":
            deadline = date_type(cur_year, cur_month, last_day)
        else:
            day = min(body.deadline_day or last_day, last_day)
            deadline = date_type(cur_year, cur_month, day)

        # Idempotency check
        existing = (await db.execute(
            select(Purchase).where(
                Purchase.contract_id == contract_id,
                Purchase.service_deadline_date == deadline,
            )
        )).scalar_one_or_none()
        if existing:
            skipped_items.append({"deadline": deadline.isoformat(), "reason": "already_exists"})
            continue

        month_name_gen = RU_MONTHS_GEN[cur_month - 1]
        month_name_nom = RU_MONTHS_NOM[cur_month - 1]

        subject = (
            body.subject_template
            .replace("{contract_name}", contract_name)
            .replace("{month_name}", month_name_gen)
            .replace("{year}", str(cur_year))
        )
        stage_label = f"{month_name_nom} {cur_year}"

        p = Purchase(
            status="planned",
            contract_id=contract_id,
            subsidy_id=body.subsidy_id,
            feo_category_id=body.feo_category_id,
            contractor_id=contract.contractor_id,
            service_term_mode="deadline",
            service_deadline_date=deadline,
            planned_total_price=Decimal(str(body.amount_per_stage)),
            contract_price=Decimal(str(body.amount_per_stage)),
            subject=subject,
            is_likely_needed=body.is_likely_needed,
            stage_label=stage_label,
            purchase_contract_type=contract.contract_type,
        )
        db.add(p)
        await db.flush()  # get p.id

        await _assign_framework_seq(p, db)

        created_items.append({
            "id": p.id,
            "deadline": deadline.isoformat(),
            "label": stage_label,
            "subject": subject,
        })

    await db.commit()
    return {"created": created_items, "skipped": skipped_items}
