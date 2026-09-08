"""Сборка payload извещения из закупки — маппинг полей (волна резки publications.py)."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.organization import Organization
from app.services.ru_regions import get_region_info


async def _build_publish_payload(purchase_id: int, db: AsyncSession) -> dict:
    res = await db.execute(select(Purchase).where(Purchase.id == purchase_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    items_res = await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id))
    items = items_res.scalars().all()

    # ПРАВИЛО №6 (волна 4b-2d): «сумма закупки» для НМЦК извещения — единый
    # источник app.services.purchase_amounts (было `p.total_nmck or p.nmck or
    # p.planned_total_price or 0` с truthy-фолбэком на Σ items — три
    # поля-мирроры одного плана + маскирующий 0). Σ items считается тем же
    # per-item фолбэком, что и раньше (total_price ?? unit_price*quantity —
    # покрывает позиции без пересчитанного total_price), передаётся как
    # items_total, дальше purchase_amounts сама решает по стадии закупки
    # (для процедуры публикации это обычно «до договора» — plan ?? Σ items).
    from decimal import Decimal as _DecimalPub
    from app.services.purchase_amounts import purchase_amounts as _purchase_amounts_pub
    _items_total_pub = (
        _DecimalPub(str(sum(
            float(i.total_price or 0) or (float(i.unit_price or 0) * float(i.quantity or 0))
            for i in items
        )))
        if items else None
    )
    _pub_amounts = _purchase_amounts_pub(p, items_total=_items_total_pub)
    nmck_val = float(_pub_amounts.effective) if _pub_amounts.effective is not None else 0.0

    contractor = None
    if p.contractor_id:
        c_res = await db.execute(select(Contractor).where(Contractor.id == p.contractor_id))
        contractor = c_res.scalar_one_or_none()

    subsidy = None
    if p.subsidy_id:
        s_res = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
        subsidy = s_res.scalar_one_or_none()

    org_inn = None
    org_address = None
    org_region = None
    _sub_org = None
    if subsidy and subsidy.org_id:
        org_res = await db.execute(
            select(Organization)
            .where(Organization.id == subsidy.org_id)
            .options(selectinload(Organization.contractor))
        )
        _sub_org = org_res.scalar_one_or_none()
        if _sub_org:
            # Правило №6: реквизиты — через org_requisites() (Contractor —
            # источник истины при заданном contractor_id), не свой inline-merge.
            from app.services.org_requisites import org_requisites
            _sub_req = org_requisites(_sub_org, _sub_org.contractor)
            org_inn = _sub_req.get('inn')
            org_address = (_sub_req.get('address') or "").strip() or None
            org_region = (_sub_org.region or "").strip() or None

    # Субъект РФ доставки: сначала явное поле delivery_region, фолбэк — регион организации субсидии.
    # p.region — «Регион проведения мероприятия» (ДРУГОЕ поле, НЕ трогаем для места поставки).
    delivery_region_value = (p.delivery_region or "").strip() or (org_region or "")
    region_info = get_region_info(delivery_region_value) if delivery_region_value else None

    # Полный адрес доставки: собираем из структурных частей, фолбэк — свободные поля.
    def _build_delivery_address() -> str | None:
        parts = []
        if (p.delivery_postcode or "").strip():
            parts.append(p.delivery_postcode.strip())
        if delivery_region_value:
            parts.append(delivery_region_value)
        if (p.delivery_city or "").strip():
            parts.append(p.delivery_city.strip())
        if (p.delivery_street or "").strip():
            parts.append(p.delivery_street.strip())
        if (p.delivery_house or "").strip():
            parts.append("д. " + p.delivery_house.strip())
        if (p.delivery_building or "").strip():
            parts.append("к. " + p.delivery_building.strip())
        if parts:
            return ", ".join(parts)
        # Фолбэк: свободная строка → место доставки/услуг → адрес организации субсидии
        return (
            (p.delivery_address or "").strip()
            or (p.delivery_location or "").strip()
            or org_address
            or None
        )

    delivery_address = _build_delivery_address()

    return {
        "purchase_id":       p.id,
        "registry_number":   p.registry_number,
        "subject":           p.subject,
        "nmck":              nmck_val,
        "purchase_method":   p.purchase_method,
        "contract_type":     p.purchase_contract_type,
        "execution_term":    str(p.execution_term) if p.execution_term else None,
        "delivery_address":  delivery_address or None,
        "region":            p.region or None,
        # deliveryPlaceType: state (фед. округ) / region (субъект) / regionOkato (11 цифр)
        "delivery_state":    region_info["district"] if region_info else None,
        "delivery_region":   delivery_region_value if region_info else None,
        "delivery_okato":    region_info["okato"] if region_info else None,
        "org_inn":           org_inn,
        "contractor": {
            "name": contractor.name if contractor else None,
            "inn":  contractor.inn  if contractor else None,
        } if contractor else None,
        "items": [
            {
                "item_name":   i.item_name,
                "quantity":    float(i.quantity or 0),
                "unit":        i.unit,
                "unit_price":  float(i.unit_price or 0),
                "total_price": float(i.total_price or 0),
            }
            for i in items
        ],
    }
