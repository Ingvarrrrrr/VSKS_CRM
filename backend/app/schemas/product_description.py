"""Схемы истории описаний / предложений правок каталога (Этап В, план
item-tz-description.md, 14.10.2026). Отдельный файл — НЕ дописывать в
schemas/products.py (его параллельно правит другая сессия, см. задание)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProductDescriptionHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    changed_at: datetime
    source: str
    proposal_id: Optional[int] = None


class ProductDescriptionRevertRequest(BaseModel):
    pass


class ProductDescriptionProposalCreate(BaseModel):
    field: str
    proposed_value: Optional[str] = None
    wish_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None


class ProductDescriptionProposalDecision(BaseModel):
    comment: Optional[str] = None


class ProductDescriptionProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    field: str
    proposed_value: Optional[str] = None
    current_value_at_proposal: Optional[str] = None
    wish_item_id: Optional[int] = None
    purchase_item_id: Optional[int] = None
    proposed_by: Optional[int] = None
    proposed_by_name: Optional[str] = None
    proposed_at: datetime
    status: str
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    decision_comment: Optional[str] = None


class ProductDescriptionProposalAcceptOut(BaseModel):
    proposal: ProductDescriptionProposalOut
    changed_since_proposal: bool
