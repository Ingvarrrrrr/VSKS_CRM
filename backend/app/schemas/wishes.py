from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from decimal import Decimal


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

    class Config:
        from_attributes = True
