"""Два требования площадки Росэлторг.Бизнес к лоту, проверенных разработчиком
живьём (29.10.2026, 13 размещённых процедур ДНР), не связанных с позициями
(см. items.py) — вынесены в отдельный файл (ПРАВИЛО №5):

1. lot.region — массив [{"id": <guid>, "name": <fullname>}] населённого
   пункта доставки из справочника площадки (cities.json, 8076 городов и пгт).
   Без него: «Регионы доставки: Место поставки должно быть заполнено».
2. lot.payment — условия оплаты закупки (purchase.payment_terms_type и
   связанные поля, ПРАВИЛО №6 — читаются отсюда, не пересчитываются заново).

cities.json лежит рядом с кодом (не в корне репозитория) — образ бэкенда не
видит корень репо вне build-контекста ./backend (см. docstring
app/services/ru_regions.py, тот же приём).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

CITIES_PATH = Path(__file__).parent / "cities.json"


@lru_cache(maxsize=1)
def _load_cities() -> list[tuple[str, str, str, str]]:
    """[name, subject, guid, fullname] × 8076 — формат файла-справочника
    площадки как есть (см. задание/docstring модуля)."""
    with open(CITIES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return [tuple(row) for row in data]


def _norm_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("ё", "е")).strip()


def _norm_subject(s: str | None) -> str:
    """Сравнение субъекта РФ устойчиво к сокращениям площадки («Ростовская
    обл» в cities.json) против полных названий из справочника проекта
    («Ростовская область», app/data/ru_regions.json) — оба сводятся к одной
    короткой форме перед сравнением."""
    t = _norm_text(s)
    for full, short in (
        ("область", "обл"),
        ("республика", "респ"),
        ("автономный округ", "ао"),
        ("автономная область", "ао"),
    ):
        t = t.replace(full, short)
    return t.rstrip(".").strip()


_CITY_PREFIX_RE = re.compile(r"\bг(?:\.\s*|\s+)([^,;]+)", re.IGNORECASE)


def extract_city_from_text(text: str | None) -> str | None:
    """«…, г. Донецк, ул. …» → «Донецк» — фолбэк, когда purchase.delivery_city
    не заполнен: ищем город и в адресе доставки."""
    if not text:
        return None
    m = _CITY_PREFIX_RE.search(text)
    if m:
        return m.group(1).strip().strip(",")
    return None


def resolve_roseltorg_region(payload: dict) -> dict | None:
    """payload (_build_publish_payload, publications_payload.py) → населённый
    пункт площадки {"id","name"} для lot.region, либо None, если не нашли.
    ПРАВИЛО №6: единственное место, где решается, какой город искать — вызывают
    и preflight в роутере (ошибка ДО создания черновика), и client.py (сборка
    тела лота) — один расчёт, не два. Город — purchase.delivery_city, иначе
    «г. X» из адреса доставки; субъект — delivery_region_raw (сырой текст
    поля, не только совпавший со справочником ru_regions.py)."""
    city_name = payload.get("delivery_city_raw") or extract_city_from_text(payload.get("delivery_address"))
    if not city_name:
        return None
    return find_delivery_city(city_name, payload.get("delivery_region_raw"))


def find_delivery_city(city_name: str | None, subject_name: str | None) -> dict | None:
    """Населённый пункт доставки в справочнике площадки → {"id", "name"}
    (fullname), либо None, если не найден / неоднозначен без субъекта (две
    Донецк — ДНР и Ростовская обл, ПРАВИЛО: разруливаем субъектом)."""
    name = _norm_text(city_name)
    if not name:
        return None
    candidates = [row for row in _load_cities() if _norm_text(row[0]) == name]
    if not candidates:
        return None
    if len(candidates) == 1:
        row = candidates[0]
        return {"id": row[2], "name": row[3]}
    subject_norm = _norm_subject(subject_name)
    if subject_norm:
        subj_matches = [row for row in candidates if _norm_subject(row[1]) == subject_norm]
        if subj_matches:
            row = subj_matches[0]
            return {"id": row[2], "name": row[3]}
    # Город федерального статуса (Москва/Санкт-Петербург/Севастополь) в
    # справочнике площадки может идти с ПУСТЫМ полем субъекта (город сам себе
    # субъект) — однозначный фолбэк, если такая запись ровно одна.
    empty_subject_matches = [row for row in candidates if not _norm_text(row[1])]
    if len(empty_subject_matches) == 1:
        row = empty_subject_matches[0]
        return {"id": row[2], "name": row[3]}
    return None


# ── Условия оплаты ───────────────────────────────────────────────────────────
# purchase.payment_terms_type → тип lot.payment площадки (формат объекта
# lot.payment проверен разработчиком живьём 29.10.2026). Значения
# purchase.payment_terms_type: postpayment / postponement / prepayment / other
# (см. миграцию d4f6h8j0k2m4, модель Purchase, PATCHABLE_FIELDS).
_PAYMENT_TYPE_MAP = {
    "postpayment": "fact",
    "postponement": "postponement",
    "prepayment": "prepayment",
    "other": "other",
}

_DAY_TYPE_MAP = {
    "calendar": "calendarDays",
    "work": "workDays",
}


def build_lot_payment(
    payment_terms_type: str | None,
    postpone_days: int | None,
    postpone_day_type: str | None,
    other_terms: str | None,
) -> dict:
    """purchase.payment_terms_type + связанные поля → тело lot.payment ровно
    в форме, которую принимает publish (PUT не проверяет, publish — да, см.
    докстринг client.py/публикация). Отсутствующий/нераспознанный тип → 'fact'
    (постоплата — дефолт у существующих закупок, решение владельца)."""
    api_type = _PAYMENT_TYPE_MAP.get(payment_terms_type or "postpayment", "fact")
    payment: dict = {
        "type": api_type,
        "prepayment_amount": None,
        "typePostponeDays": None,
        "postpone_days": None,
        "other_terms": None,
    }
    if api_type == "postponement":
        payment["postpone_days"] = postpone_days
        payment["typePostponeDays"] = _DAY_TYPE_MAP.get(postpone_day_type or "calendar", "calendarDays")
    elif api_type == "other":
        payment["other_terms"] = other_terms
    return payment
