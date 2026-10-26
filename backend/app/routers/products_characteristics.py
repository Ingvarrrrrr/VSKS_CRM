"""Разбор вставленного текста в характеристики и предпросмотр техописания
(владелец, задача «ручное заполнение характеристик в карточке товара»,
26.10.2026).

Два отдельных пути, оба НЕ сохраняют ничего в БД (как и соседний
products_tz44.py::preview_tz_44fz — только текст для предпросмотра, запись
делает обычный PUT/PATCH товара тем же механизмом, что и description,
ПРАВИЛО №6):
  - POST /api/products/characteristics/parse — текст, вставленный
    пользователем копированием с сайта поставщика, → список характеристик
    [{"name","value","unit"}]. Парсер — app/services/product_characteristics_parse.py
    (единственное такое место, второй не заводим).
  - POST /api/products/characteristics/describe — список характеристик →
    собранный текст описания через build_tech_description
    (app/services/product_tech_description.py, ТОТ ЖЕ единственный сборщик,
    что и везде в проекте).

Регистрация — ДО products.router (как и products_tz44.py), иначе
"/characteristics/parse" перехватится путём GET/PUT/PATCH/DELETE
"/{product_id}" из products.router (там нет явного int-конвертера на
product_id, а FastAPI матчит по порядку регистрации роутеров).

Доступ — вход обязателен (ПРАВИЛО №8, п.1-2): та же зависимость
get_current_user, что и у соседей на этом префиксе; личность пользователя
здесь не используется вообще (эти два пути не читают/не пишут ничего
по конкретному товару), только факт входа.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt import get_current_user
from app.models.user import User
from app.schemas.products import ProductCharacteristic
from app.services.product_characteristics_parse import (
    MAX_TEXT_LENGTH,
    parse_pasted_characteristics,
)
from app.services.product_tech_description import build_tech_description

router = APIRouter(prefix="/api/products/characteristics", tags=["products"])


class CharacteristicsParseIn(BaseModel):
    text: str


class CharacteristicsParseOut(BaseModel):
    items: list[ProductCharacteristic]


@router.post("/parse", response_model=CharacteristicsParseOut)
async def parse_characteristics(
    body: CharacteristicsParseIn,
    current_user: User = Depends(get_current_user),
):
    text = body.text or ""
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Текст длиннее {MAX_TEXT_LENGTH} символов — вставьте частями.",
        )
    items = parse_pasted_characteristics(text)
    return CharacteristicsParseOut(items=[ProductCharacteristic(**i) for i in items])


class CharacteristicsDescribeIn(BaseModel):
    characteristics: list[ProductCharacteristic] = []
    base_text: str | None = None


class CharacteristicsDescribeOut(BaseModel):
    text: str | None


@router.post("/describe", response_model=CharacteristicsDescribeOut)
async def describe_characteristics(
    body: CharacteristicsDescribeIn,
    current_user: User = Depends(get_current_user),
):
    raw = [c.model_dump() for c in body.characteristics]
    text = build_tech_description(characteristics=raw, base_text=body.base_text)
    return CharacteristicsDescribeOut(text=text)
