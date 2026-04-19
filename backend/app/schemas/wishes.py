from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal


class WishItemOut(BaseModel):
    id: int
    item_name: str
    item_type: Optional[str] = "товар"
    quantity: Optional[float] = 1
    unit: Optional[str] = "шт"
    unit_price: Optional[float] = 0
    total_price: Optional[float] = 0
    country_origin: Optional[str] = "Россия"
    model_config = ConfigDict(from_attributes=True)


class WishCreate(BaseModel):
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    assigned_to: Optional[int] = None
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin


class WishUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    subsidy_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    assigned_to: Optional[int] = None
    items: Optional[list] = None  # list of dicts with item_name, item_type, quantity, unit, unit_price, total_price, country_origin


class WishReject(BaseModel):
    rejection_reason: str


class WishConvert(BaseModel):
    approved_quantity: Optional[Decimal] = None
    approved_price: Optional[Decimal] = None
    subsidy_id: Optional[int] = None


class WishOut(BaseModel):
    id: int
    org_id: int
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    link: Optional[str] = None
    priority: Optional[str] = None
    desired_date: Optional[date] = None
    justification: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    approved_by: Optional[int] = None
    approver_name: Optional[str] = None
    purchase_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    subsidy_id: Optional[int] = None
    subsidy_name: Optional[str] = None
    feo_category_id: Optional[int] = None
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    items: List[WishItemOut] = []

    class Config:
        from_attributes = True
