"""Курс USD/RUB (ЦБ РФ) — владелец, 2026-08-29.

Владелец: «Дополнительный критерий — курс доллара к рублю: если USD/RUB
изменился более чем на 10%, срок актуальности сокращается до месяца».

refresh_cbr_rates() тянет ежедневный курс с cbr.ru и апсертит в fx_rates.
Сетевые ошибки НЕ фатальны — только warning в лог (см. вызов в lifespan,
app/__init__.py). Никаких бесконечных ретраев внутри — вызывающий код сам
решает периодичность (см. _fx_rates_refresh_loop в app/__init__.py).
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.etree import ElementTree

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fx_rate import FxRate

_log = logging.getLogger(__name__)

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_DYNAMIC_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"
USD_VALUTE_ID = "R01235"
USD_CODE = "USD"
BACKFILL_MIN_ROWS = 30


def _parse_cbr_date(raw: str) -> Optional[date]:
    """CBR отдаёт дату документа в атрибуте Date="DD.MM.YYYY"."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_cbr_value(raw_value: str, raw_nominal: str) -> Optional[Decimal]:
    """CBR использует запятую как десятичный разделитель и Nominal (напр. USD
    почти всегда Nominal=1, но на будущее — на случай изменения формата)."""
    try:
        value = Decimal(raw_value.strip().replace(",", "."))
        nominal = Decimal((raw_nominal or "1").strip().replace(",", ".") or "1")
        if nominal == 0:
            return None
        return value / nominal
    except (InvalidOperation, ValueError, AttributeError):
        return None


async def _upsert_rate(db: AsyncSession, code: str, rate_date: date, value: Decimal) -> None:
    existing = (await db.execute(
        select(FxRate).where(FxRate.code == code, FxRate.rate_date == rate_date)
    )).scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(FxRate(code=code, rate_date=rate_date, value=value))


async def refresh_cbr_rates(db: AsyncSession) -> None:
    """Подтянуть сегодняшний курс USD с cbr.ru, если его ещё нет в fx_rates.

    Все ошибки (сеть/парсинг) — не фатальны: логируем warning и выходим,
    ничего не поднимаем наверх (вызывающий код в lifespan обёрнут try/except,
    но эта функция сама себя защищает — её могут звать и из ручного эндпоинта).
    """
    today = datetime.utcnow().date()
    already = (await db.execute(
        select(FxRate.id).where(FxRate.code == USD_CODE, FxRate.rate_date == today)
    )).scalar_one_or_none()
    if already is not None:
        return  # за сегодня уже есть — сетевой запрос не делаем

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(CBR_DAILY_URL)
            resp.raise_for_status()
            content = resp.content
    except Exception as e:
        _log.warning("refresh_cbr_rates: сеть/HTTP ошибка, пропускаем (non-fatal): %s", e)
        return

    try:
        root = ElementTree.fromstring(content)
        doc_date = _parse_cbr_date(root.attrib.get("Date", "")) or today
        usd_value: Optional[Decimal] = None
        for valute in root.findall("Valute"):
            if valute.attrib.get("ID") != USD_VALUTE_ID:
                continue
            value_el = valute.find("Value")
            nominal_el = valute.find("Nominal")
            if value_el is None or value_el.text is None:
                continue
            usd_value = _parse_cbr_value(value_el.text, nominal_el.text if nominal_el is not None else "1")
            break
        if usd_value is None:
            _log.warning("refresh_cbr_rates: USD (%s) не найден в ответе ЦБ, пропускаем", USD_VALUTE_ID)
            return
        await _upsert_rate(db, USD_CODE, doc_date, usd_value)
        await db.commit()
        _log.info("refresh_cbr_rates: USD/RUB на %s = %s", doc_date.isoformat(), usd_value)
    except Exception as e:
        _log.warning("refresh_cbr_rates: ошибка парсинга ответа ЦБ, пропускаем (non-fatal): %s", e)
        return


async def backfill_cbr_history(db: AsyncSession, days: int = 400) -> None:
    """Разовый бэкафилл истории курса USD (ревью 2026-08-29): без него в
    fx_rates всегда лежит только «сегодня» (refresh_cbr_rates тянет только
    дневной курс) — get_rate_on_or_before(db, 'USD', <любая прошлая дата>)
    всегда возвращает None, usd_change_pct всегда None, и курсовой триггер
    (app/services/price_freshness.py) не срабатывает НИКОГДА, ни на одной
    цене, ни через месяц. Владелец просил именно этот критерий.

    Идемпотентно и «тихо»: если истории уже достаточно (>= BACKFILL_MIN_ROWS
    строк И самая старая запись не свежее `today - (days - 30)`), выходим
    без сетевого запроса. Иначе тянем диапазон за `days` дней с cbr.ru
    (XML_dynamic.asp) и апсертим пачкой. Все ошибки — non-fatal warning,
    как и в refresh_cbr_rates. Никаких ретраев/циклов внутри.
    """
    today = datetime.utcnow().date()
    row = (await db.execute(
        select(func.count(FxRate.id), func.min(FxRate.rate_date)).where(FxRate.code == USD_CODE)
    )).first()
    existing_count = (row[0] or 0) if row else 0
    oldest_date = row[1] if row else None
    threshold_date = today - timedelta(days=max(days - 30, 0))
    if existing_count >= BACKFILL_MIN_ROWS and oldest_date is not None and oldest_date <= threshold_date:
        return  # истории достаточно — сетевой запрос не делаем

    date_from = today - timedelta(days=days)
    params = {
        "date_req1": date_from.strftime("%d/%m/%Y"),
        "date_req2": today.strftime("%d/%m/%Y"),
        "VAL_NM_RQ": USD_VALUTE_ID,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(CBR_DYNAMIC_URL, params=params)
            resp.raise_for_status()
            content = resp.content
    except Exception as e:
        _log.warning("backfill_cbr_history: сеть/HTTP ошибка, пропускаем (non-fatal): %s", e)
        return

    try:
        root = ElementTree.fromstring(content)
        parsed: dict[date, Decimal] = {}
        for record in root.findall("Record"):
            d = _parse_cbr_date(record.attrib.get("Date", ""))
            if d is None:
                continue
            value_el = record.find("Value")
            nominal_el = record.find("Nominal")
            if value_el is None or value_el.text is None:
                continue
            v = _parse_cbr_value(value_el.text, nominal_el.text if nominal_el is not None else "1")
            if v is not None:
                parsed[d] = v

        if not parsed:
            _log.warning("backfill_cbr_history: пустой/нераспознанный ответ ЦБ, пропускаем")
            return

        existing_rows = (await db.execute(
            select(FxRate).where(FxRate.code == USD_CODE, FxRate.rate_date.in_(list(parsed.keys())))
        )).scalars().all()
        existing_by_date = {r.rate_date: r for r in existing_rows}

        added = 0
        for d, v in parsed.items():
            existing = existing_by_date.get(d)
            if existing:
                existing.value = v
            else:
                db.add(FxRate(code=USD_CODE, rate_date=d, value=v))
                added += 1
        await db.commit()
        _log.info(
            "backfill_cbr_history: %d новых дат USD/RUB из %d записей ЦБ (диапазон %s..%s)",
            added, len(parsed), date_from.isoformat(), today.isoformat(),
        )
    except Exception as e:
        _log.warning("backfill_cbr_history: ошибка парсинга ответа ЦБ, пропускаем (non-fatal): %s", e)
        return


async def get_rate_on_or_before(db: AsyncSession, code: str, d: date) -> Optional[Decimal]:
    """Последний известный курс на дату <= d (None если данных нет вообще)."""
    row = (await db.execute(
        select(FxRate.value)
        .where(FxRate.code == code, FxRate.rate_date <= d)
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    )).scalar_one_or_none()
    return Decimal(row) if row is not None else None


async def usd_change_pct(db: AsyncSession, since_date: date) -> Optional[float]:
    """Процентное изменение последнего известного курса USD относительно курса
    на since_date. None, если данных недостаточно (нет курса на since_date
    или нет более свежего курса)."""
    latest_row = (await db.execute(
        select(FxRate.rate_date, FxRate.value)
        .where(FxRate.code == USD_CODE)
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    )).first()
    if latest_row is None:
        return None
    latest_date, latest_value = latest_row

    base_value = await get_rate_on_or_before(db, USD_CODE, since_date)
    if base_value is None or base_value == 0:
        return None

    latest_value = Decimal(latest_value)
    pct = (latest_value - base_value) / base_value * Decimal(100)
    return float(pct)
