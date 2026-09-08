"""Marketplace publishing, commercial requests, and suppliers schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# Platform credentials (per-user)
class PlatformCredentialUpsert(BaseModel):
    login: str
    password: Optional[str] = None  # если None — обновить только login

class PlatformCredentialOut(BaseModel):
    platform: str
    login: str
    has_password: bool = True

    model_config = {"from_attributes": True}


# Platform publications
class PublishRequest(BaseModel):
    platform: str  # fabrikant / roseltorg_rb
    procedure_type: Optional[str] = None  # roseltorg_rb: request_quotations/...; fabrikant: zp | reduction | price_monitoring
    proposal_start: Optional[str] = None       # ISO datetime, Фабрикант: начало приёма предложений
    proposal_end: Optional[str] = None         # ISO datetime, Фабрикант: конец приёма предложений
    determination_date: Optional[str] = None   # ISO datetime, Фабрикант: определение победителя
    summing_up_date: Optional[str] = None      # ISO datetime, Фабрикант: подведение итогов
    okpd2_code: Optional[str] = None           # ОКПД2 для всех позиций закупки (Фабрикант)
    attach_documents: bool = False             # Фабрикант: прикрепить пакет из 5 документов после публикации
    no_nmcd: bool = False                      # Фабрикант: опубликовать без НМЦД (nmck=0)
    # Фабрикант Редукцион — дополнительные поля
    auction_date_start: Optional[str] = None   # ISO datetime, дата начала редукциона
    auction_bet_limit_from: Optional[float] = None  # граница ставки от
    auction_bet_limit_to: Optional[float] = None    # граница ставки до

class PublicationStatusUpdate(BaseModel):
    status: str             # published / error
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_text: Optional[str] = None

class PublicationOut(BaseModel):
    id: int
    purchase_id: int
    platform: str
    status: str
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    error_text: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    platform_number: Optional[str] = None
    platform_state: Optional[str] = None

    class Config:
        from_attributes = True


# ── Commercial Requests ────────────────────────────────────────────────────────

class CommercialRequestRecipientOut(BaseModel):
    id: int
    contractor_id: Optional[int] = None
    contractor_name: Optional[str] = None
    email: Optional[str] = None
    status: str

class FreeRecipient(BaseModel):
    name: Optional[str] = None
    email: str

class CommercialRequestCreate(BaseModel):
    purchase_id: int
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None
    recipient_ids: Optional[List[int]] = None
    free_recipients: Optional[List[FreeRecipient]] = None

class CommercialRequestUpdate(BaseModel):
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None

class CommercialRequestStatusUpdate(BaseModel):
    status: str

class CommercialRequestRecipientStatusUpdate(BaseModel):
    status: str

class CommercialRequestOut(BaseModel):
    id: int
    purchase_id: int
    subject: Optional[str] = None
    intro_text: Optional[str] = None
    delivery_date: Optional[str] = None
    status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    recipients: List[CommercialRequestRecipientOut] = []


# ── Commercial Request Offers (владелец, 2026-08-29) — цены, полученные от
# получателей запроса КП. Принятое предложение актуализирует цену товара. ──
class CommercialRequestOfferIn(BaseModel):
    id: Optional[int] = None  # существующий offer при обновлении набора; None → создать
    recipient_id: Optional[int] = None
    product_id: Optional[int] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    note: Optional[str] = None


class CommercialRequestOfferOut(BaseModel):
    id: int
    request_id: int
    recipient_id: Optional[int] = None
    product_id: Optional[int] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    is_accepted: bool = False
    note: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Suppliers ──────────────────────────────────────────────────────────────────

class SupplierProductOut(BaseModel):
    id: int
    supplier_id: int
    product_id: Optional[int] = None
    price_notes: Optional[str] = None
    source: Optional[str] = None

class SupplierCreate(BaseModel):
    name: str
    inn: Optional[str] = None
    kpp: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None

class SupplierOut(BaseModel):
    id: int
    name: str
    inn: Optional[str] = None
    kpp: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    products: List[SupplierProductOut] = []

class SupplierProductCreate(BaseModel):
    product_id: Optional[int] = None
    price_notes: Optional[str] = None
    source: Optional[str] = None


