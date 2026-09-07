"""Единый источник юридических реквизитов организации (Правило №6).

Контекст: `organizations.*` (inn/kpp/ogrn/address/подписант/full_name)
дублирует `contractors.*` — исторически они копировались один раз при
создании (`app/routers/subsidies.py::_materialize_org_from_contractor`,
`app/routers/organizations.py::_auto_link_contractor_by_inn`), а дальше
могли править независимо: карточка контрагента (`ContractorEditDialog`)
меняет `contractors.*`, но `organizations.*` оставались как были — итог,
документы/сериализатор показывали устаревшие реквизиты, хотя владелец
поправил их через контрагента.

Contractor — источник истины, когда `Organization.contractor_id` указывает
на существующего контрагента. Колонки `Organization.inn/kpp/ogrn/address/
signatory*/full_name` считаются deprecated (см. комментарии в
`app/models/organization.py`) и читаются напрямую ТОЛЬКО как переходный
фолбэк для организаций без контрагента.

Один хелпер — везде, где нужен набор реквизитов организации (сериализатор
`/api/organizations`, генерация документов, публикации), обязаны вызывать
`org_requisites()` вместо прямого чтения `Organization.inn` и т.п. и вместо
повторного изобретения своего merge-паттерна "org или contractor".

2026-09-07 (по факту на проде, org id=5 «АНО ЦЕНТРПОИСК»): контрагент
побеждает целиком, НО если конкретное поле у контрагента пусто/NULL, а у
org есть значение — контрагент неполный (например, создан вручную без
части реквизитов), и слепое "контрагент побеждает" стирало бы то, что уже
было видно пользователю (пропадало наименование заказчика в документах).
Поэтому фолбэк — ПОПОЛЕЙНО: пустое поле контрагента подменяется значением
org с предупреждением в лог (см. `org_requisites()`); миграция
`t2v4x6z8b0d2` тем же критерием дозаполняет такие пустые поля контрагента
из org напрямую в БД, чтобы предупреждение не повторялось на каждый запрос.
"""
import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.organization import Organization

logger = logging.getLogger(__name__)

# Поля-реквизиты: при наличии привязанного контрагента читаются ИСКЛЮЧИТЕЛЬНО
# из него (не смешиваются "бери непустое" — иначе ровно та же болезнь
# расхождения, которую эта волна чинит). `name` (короткое отображаемое имя)
# сюда сознательно не входит — это рабочее поле organizations, а не
# юридический реквизит (см. _merge_org_with_contractor до этой правки).
REQUISITE_FIELDS: tuple[str, ...] = (
    "full_name",
    "inn",
    "kpp",
    "ogrn",
    "address",
    "signatory",
    "signatory_position",
    "signatory_last_name",
    "signatory_first_name",
    "signatory_middle_name",
)


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == '')


def org_requisites(org: Organization, contractor: Optional[Contractor] = None) -> dict:
    """Вернуть словарь реквизитов организации `org`.

    - `org.contractor_id` задан И `contractor` передан (и это тот самый
      контрагент) → реквизиты берутся ИЗ КОНТРАГЕНТА, ПОПОЛЕЙНО. Контрагент
      побеждает по каждому полю, где у него есть значение; там, где у
      контрагента пусто/NULL, а у org — есть, отдаётся значение org (иначе
      неполный контрагент стирал бы то, что пользователь уже видел) с
      предупреждением в лог — сигнал дозаполнить контрагента.
    - Иначе (org ещё не привязана к контрагенту, либо контрагент не
      передан/не найден) → переходный период: собственные deprecated
      колонки Organization.
    """
    c = contractor if (org.contractor_id and contractor is not None and contractor.id == org.contractor_id) else None
    if c is None:
        return {field: getattr(org, field, None) for field in REQUISITE_FIELDS}

    result = {}
    for field in REQUISITE_FIELDS:
        c_val = getattr(c, field, None)
        if not _blank(c_val):
            result[field] = c_val
            continue
        org_val = getattr(org, field, None)
        result[field] = org_val
        if not _blank(org_val):
            logger.warning(
                "org_requisites: пустое поле %s у контрагента %s, взято из организации %s",
                field, c.id, org.id,
            )
    return result


async def bulk_org_requisites(db: AsyncSession, orgs: Iterable[Organization]) -> dict[int, dict]:
    """Реквизиты для набора организаций без N+1 запросов к contractors.

    Собирает все `contractor_id` разом в один SELECT. Полезно там, где
    Organization выбрана без eager-load связи `contractor` (в отличие от
    большинства запросов в app/routers/organizations.py, которые уже делают
    `selectinload(Organization.contractor)` — там N+1 и так не возникает,
    достаточно звать `org_requisites(org, org.contractor)`).
    """
    orgs = list(orgs)
    contractor_ids = {o.contractor_id for o in orgs if o.contractor_id}
    contractors_by_id: dict[int, Contractor] = {}
    if contractor_ids:
        rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors_by_id = {c.id: c for c in rows}
    return {
        o.id: org_requisites(o, contractors_by_id.get(o.contractor_id) if o.contractor_id else None)
        for o in orgs
    }
