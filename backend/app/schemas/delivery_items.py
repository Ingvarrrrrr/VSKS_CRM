from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field


class DeliveryItemBase(BaseModel):
    name: str
    unit: Optional[str] = None
    qty: Decimal = Field(default=Decimal("0"))
    unit_price: Decimal = Field(default=Decimal("0"))
    delivery_date: Optional[date] = None
    doc_number: Optional[str] = None
    status: str = "pending"
    notes: Optional[str] = None
    contract_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    product_id: Optional[int] = None


class DeliveryItemCreate(BaseModel):
    name: str
    unit: Optional[str] = None
    qty: Decimal = Field(default=Decimal("0"))
    unit_price: Decimal = Field(default=Decimal("0"))
    delivery_date: Optional[Union[date, str]] = None
    doc_number: Optional[str] = None
    status: Optional[str] = "pending"
    notes: Optional[str] = None
    contract_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    product_id: Optional[int] = None


class DeliveryItemUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    qty: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    delivery_date: Optional[Union[date, str]] = None
    doc_number: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    contract_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    product_id: Optional[int] = None


class DeliveryItemOut(BaseModel):
    id: int
    purchase_id: int
    contract_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    product_id: Optional[int] = None
    name: str
    unit: Optional[str] = None
    qty: Decimal
    unit_price: Decimal
    total: Decimal
    delivery_date: Optional[date] = None
    doc_number: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DeliverySummary(BaseModel):
    contract_total: Decimal
    delivered_total: Decimal
    delivered_qty_pct: float
    delivered_amount_pct: float
    status_counts: Dict[str, int]


class DeliveryItemsResponse(BaseModel):
    items: List[DeliveryItemOut]
    summary: DeliverySummary


class WaybillParsedItem(BaseModel):
    raw_name: str
    qty: Decimal
    unit_price: Decimal
    total: Decimal
    unit: Optional[str] = None
    doc_number: Optional[str] = None
    delivery_date: Optional[date] = None
    suggested_contract_item_id: Optional[int] = None
    suggested_purchase_item_id: Optional[int] = None
    confidence: float = 0.0


class WaybillParseResponse(BaseModel):
    doc_number: Optional[str] = None
    delivery_date: Optional[date] = None
    items: List[WaybillParsedItem]
    warnings: List[str] = []


class WaybillApplyItem(BaseModel):
    name: str
    qty: Decimal = Field(default=Decimal("0"))
    unit_price: Decimal = Field(default=Decimal("0"))
    unit: Optional[str] = None
    delivery_date: Optional[Union[date, str]] = None
    doc_number: Optional[str] = None
    contract_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    product_id: Optional[int] = None
    status: Optional[str] = "delivered"
    notes: Optional[str] = None


class WaybillApplyRequest(BaseModel):
    items: List[WaybillApplyItem]
    doc_number: Optional[str] = None
    delivery_date: Optional[Union[date, str]] = None
