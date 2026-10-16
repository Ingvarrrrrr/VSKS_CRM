"""find_or_create_contractor — единая точка поиска/создания Contractor по
ИНН-приоритетной точной нормализации (app.services.vehicle_org_matching.
normalize_inn/normalize_org_name — та же normalize_org_name, что уже
используется для организаций в импорте транспорта, см. её докстринг:
«приоритет 1) точный ИНН после нормализации, 2) точное совпадение
нормализованного названия», без нечёткого сопоставления, lesson
feedback_dedup_exact_only).

Подготовка к импорту исторических закупок (задача 02.10.2026). Существующие
парсеры покупок (app/services/purchase_import_parser_group.py,
app/routers/purchase_items_import_feo.py) НЕ переведены на эту функцию —
их текущая логика поиска контрагента НЕ эквивалентна ни этой функции, ни
друг другу (см. отчёт задачи): один использует ИНН+(нормализованное иначе)
имя без org_id на новом контрагенте, другой — имя+КПП (не ИНН вообще).
Перевод на общий хелпер изменил бы набор строк, которые считаются «тем же
контрагентом» — запрещено явным условием задачи («если логика эквивалентна»).
Новый код (историчный импорт и будущие парсеры) должен использовать именно
find_or_create_contractor, чтобы не плодить третий вариант нормализации.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.services.vehicle_org_matching import normalize_inn, normalize_org_name


async def find_or_create_contractor(
    db: AsyncSession,
    name: Optional[str],
    inn: Optional[Any],
    org_id: Optional[int] = None,
    match_by_name: bool = True,
) -> Optional[int]:
    """Возвращает id существующего контрагента (точный ИНН, иначе точное
    нормализованное имя) или создаёт новый, если оба пусты/не нашли
    совпадения. None — если ни name, ни inn не переданы (нечего искать и
    нечего создать).

    `match_by_name=False` (владелец, 16.10.2026, импорт факта без ИНН
    поставщика) — пропускает поиск по имени целиком: без ИНН (или если ИНН
    не распознан) совпадение одних и тех же слов в названии организации у
    РАЗНЫХ контрагентов (опечатки, сокращения, тёзки) слишком легко даёт
    ложное «тот же поставщик» — владелец явно просил не привязывать такую
    закупку к существующему контрагенту по имени, только создавать новый.
    По умолчанию `True` — поведение и для ЭТОЙ функции, и для всех остальных
    вызывающих (purchase_from_bank_payment.py, fadm_sheet_load/*) НЕ меняется.
    """
    norm_inn = normalize_inn(inn)
    norm_name = normalize_org_name(name)
    if not norm_inn and not norm_name:
        return None

    rows = (await db.execute(select(Contractor))).scalars().all()

    if norm_inn:
        for c in rows:
            if normalize_inn(c.inn) == norm_inn:
                return c.id

    if norm_name and match_by_name:
        for c in rows:
            if normalize_org_name(c.name) == norm_name:
                return c.id

    new_contractor = Contractor(
        name=(name or (inn if isinstance(inn, str) else str(inn))),
        inn=(inn if isinstance(inn, str) else (str(inn) if inn is not None else None)),
        org_id=org_id,
    )
    db.add(new_contractor)
    await db.flush()
    return new_contractor.id


async def find_contractors_by_name(db: AsyncSession, name: Optional[str]) -> list[int]:
    """ВСЕ id контрагентов с тем же нормализованным именем (normalize_org_name —
    точное сравнение, без нечёткого сопоставления, та же нормализация, что и
    find_or_create_contractor выше) — только найти, НИЧЕГО не создаёт.

    Несколько id возможны из-за дублей контрагентов (разные записи Contractor
    с одинаковым названием после нормализации — учитываются все, а не только
    первая).

    Владелец (16.10.2026): «Похожие закупки в импорте факта» (existing_link.py)
    на эту функцию больше НЕ переходит — поиск уже существующей закупки там
    теперь только по ИНН (find_contractor_ids_by_inns ниже), совпадение по
    имени даёт слишком много ложных «сопоставлено» (одни и те же слова у
    разных организаций). Функция оставлена как есть для прочих возможных
    вызывающих вне historical_fact_import."""
    norm_name = normalize_org_name(name)
    if not norm_name:
        return []
    rows = (await db.execute(select(Contractor.id, Contractor.name))).all()
    return [r.id for r in rows if normalize_org_name(r.name) == norm_name]


async def find_contractor_ids_by_inns(db: AsyncSession, inns: Any) -> dict:
    """{нормализованный ИНН → [contractor_id, ...]} ОДНИМ запросом
    `Contractor.inn.in_(...)` сразу по ВСЕМ переданным ИНН (владелец,
    16.10.2026) — вместо запроса на каждую группу файла импорта факта
    (замер: 113 групп × полный SELECT Contractor на каждую — главная причина
    107 с в find_existing_matches_for_group, см. отчёт задачи).

    `inns` — любой iterable «сырых» значений ИНН (как из строки файла —
    строка/число/с пробелами), каждое нормализуется `normalize_inn()` (та же
    функция, что и find_or_create_contractor — ПРАВИЛО №6, не вторая
    нормализация); невалидные (не 10/12 цифр) и дубликаты отбрасываются до
    запроса. Сравнение — ТОЧНОЕ (lesson feedback_dedup_exact_only): ищет
    строгое совпадение с `Contractor.inn` как он хранится в БД, без
    повторной нормализации значения в БД на стороне SQL — контрагент с
    «грязным» ИНН (пробел/лишняя точка/потерянный ведущий ноль — такие есть
    в проде) этим запросом не находится, как и обычным точным поиском по
    строке. Пустой `inns` → пустой словарь без обращения к БД."""
    canonical = sorted({normalize_inn(i) for i in inns} - {None})
    if not canonical:
        return {}
    rows = (await db.execute(
        select(Contractor.id, Contractor.inn).where(Contractor.inn.in_(canonical))
    )).all()
    out: dict = {}
    for r in rows:
        out.setdefault(r.inn, []).append(r.id)
    return out
