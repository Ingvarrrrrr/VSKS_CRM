"""Сервис автоматического создания и обогащения контрагентов из выгрузок по ИНН.

Правило №6: единый вызов app.services.contractor_lookup.fetch_egrul_row к egrul.nalog.ru.
При импорте выписок / чеков / реестров контрагенты по ИНН сразу добавляются в таблицу `contractors`,
а их реквизиты (наименование, ОГРН, КПП, адрес, руководитель/подписант, банковские данные)
автоматически заполняются из ЕГРЮЛ/ЕГРИП.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.services.contractor_lookup import fetch_egrul_row, _split_signatory

logger = logging.getLogger(__name__)


async def ensure_contractor_from_inn(
    inn: Optional[str],
    name_hint: Optional[str],
    db: AsyncSession,
    *,
    bik: Optional[str] = None,
    bank_name: Optional[str] = None,
    account: Optional[str] = None,
    kpp: Optional[str] = None,
) -> Optional[Contractor]:
    """Находит или создаёт контрагента по ИНН с автозаполнением реквизитов из ЕГРЮЛ.

    - Если контрагент уже есть в БД — возвращает его (при необходимости дозаполняет банковские реквизиты).
    - Если нет — запрашивает ЕГРЮЛ/ЕГРИП и создаёт полную карточку.
    - При недоступности ЕГРЮЛ или самозанятом — создаёт с name_hint и не падает.
    """
    clean_inn = str(inn or "").strip()
    if not clean_inn or not clean_inn.isdigit() or len(clean_inn) not in (10, 12):
        return None

    # 1. Поиск в БД
    q = await db.execute(select(Contractor).where(Contractor.inn == clean_inn).limit(1))
    c = q.scalar_one_or_none()
    if c:
        # Дозаполняем банковские реквизиты, если их не было
        changed = False
        if bik and not c.bik:
            c.bik = bik
            changed = True
        if bank_name and not c.bank_name:
            c.bank_name = bank_name
            changed = True
        if account and not c.settlement_account:
            c.settlement_account = account
            changed = True
        if kpp and not c.kpp:
            c.kpp = kpp
            changed = True
        if changed:
            await db.flush()
        return c

    # 2. Запрос в ЕГРЮЛ/ЕГРИП
    row = None
    try:
        row = await asyncio.wait_for(
            fetch_egrul_row(clean_inn, timeout=5, max_attempts=3, poll_delay=0.8),
            timeout=8,
        )
    except Exception as e:
        logger.warning("ЕГРЮЛ lookup для ИНН %s не удался (%s), fallback на name_hint: %s", clean_inn, e, name_hint)

    signatory = None
    signatory_position = None
    if row:
        signatory, signatory_position = _split_signatory(row.get("g"))
        org_type = "ИП" if len(clean_inn) == 12 else ("Юр.лицо" if row.get("o") else None)
        c = Contractor(
            inn=clean_inn,
            name=row.get("c") or row.get("n") or name_hint or f"ИНН {clean_inn}",
            full_name=row.get("n") or name_hint,
            ogrn=row.get("o"),
            kpp=row.get("p") or kpp,
            address=row.get("a"),
            org_type=org_type,
            signatory=signatory,
            signatory_position=signatory_position,
            bik=bik,
            bank_name=bank_name,
            settlement_account=account,
        )
    else:
        org_type = "ИП" if len(clean_inn) == 12 else "Юр.лицо"
        c = Contractor(
            inn=clean_inn,
            name=name_hint or f"ИНН {clean_inn}",
            full_name=name_hint,
            kpp=kpp,
            org_type=org_type,
            bik=bik,
            bank_name=bank_name,
            settlement_account=account,
        )

    db.add(c)
    await db.flush()
    logger.info("Создан контрагент %s (ИНН %s) из выгрузки (ЕГРЮЛ: %s)", c.name, clean_inn, bool(row))
    return c

