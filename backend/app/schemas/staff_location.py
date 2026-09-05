"""
Pydantic-схемы отслеживания местоположения сотрудников (владелец, 2026-09).

Только backend-контракт — мобильный интерфейс/карта заказываются отдельно.
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    is_active: bool


class LocationPointIn(BaseModel):
    """Одна точка в пакете от устройства."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    recorded_at: datetime
    source: str = Field(default="browser", max_length=20)


class LocationBatchIn(BaseModel):
    """Пакет точек — приложение копит их при потере связи и досылает разом."""
    points: List[LocationPointIn] = Field(min_length=1, max_length=500)


class LocationBatchResult(BaseModel):
    accepted: int
    ignored_old: int
    ignored_duplicate: int


class LocationPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    lat: float
    lon: float
    accuracy_m: Optional[float] = None
    recorded_at: datetime
    received_at: datetime
    source: str


class OnShiftUserOut(BaseModel):
    """Строка списка «кто сейчас на смене» для диспетчера — сотрудник + последняя точка.

    2026-09 (запрос местоположения через мессенджер): в списке теперь могут
    быть и сотрудники БЕЗ активной смены — если они ответили на разовый
    запрос местоположения (via_request=True). Для них shift_started_at=None.
    """
    user_id: int
    full_name: Optional[str] = None
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    shift_started_at: Optional[datetime] = None
    last_point: Optional[LocationPointOut] = None
    via_request: bool = False


# ─────────────── Разовый запрос местоположения через мессенджер (2026-09) ───

class LocationRequestCreateIn(BaseModel):
    user_id: int = Field(description="Кому запросить местоположение")


class LocationRequestRespondIn(BaseModel):
    """Тело ответа с экрана подтверждения (LocationRequestRespondView.vue) —
    сотрудник нажал «Отправить моё местоположение», координаты взяты через
    navigator.geolocation на клиенте."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)


class LocationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requested_by_id: int
    requested_by_name: Optional[str] = None
    user_id: int
    status: str = Field(description="sent | answered | declined | expired | cancelled")
    channels_sent: Optional[str] = Field(default=None, description="какие каналы реально сработали: push/telegram/max, обычно один (push первый, мессенджеры — запасной)")
    created_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime] = None
    point: Optional[LocationPointOut] = None


class RosterEntryOut(BaseModel):
    """Строка панели «Запросить местоположение» — сотрудник своей организации +
    какие каналы у него доступны + последний запрос к нему (если был)."""
    user_id: int
    full_name: str
    org_id: Optional[int] = None
    org_name: Optional[str] = None
    has_push: bool = False
    has_telegram: bool
    has_max: bool
    can_request: bool
    latest_request: Optional[LocationRequestOut] = None
