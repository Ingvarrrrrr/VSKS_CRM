"""Правило №6 (миграция w6x7y8z9a0b1, 16.10.2026): контрагент — ЕДИНСТВЕННЫЙ
источник юр. реквизитов организации (inn/kpp/ogrn/address/подписант/
full_name) — Organization.<field> САМИ являются column_property, читающими
Contractor.<field> (app/models/organization.py). Нет больше "непустое
значение org, иначе contractor" (это и была прошлая болезнь: контрагента
правили отдельно через ContractorEditDialog, organizations.* оставались
устаревшими — именно их показывал API). Теперь org.<field> БУКВАЛЬНО равно
contractor.<field> — расхождению взяться неоткуда, пустое у контрагента
означает пустое и у org, без фолбэка на org._legacy_* колонки.
См. app/services/org_requisites.py, app/routers/organizations.py.
"""
import uuid

import pytest

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.services.org_requisites import org_requisites


def _uniq_inn(prefix: str = "77") -> str:
    return (prefix + uuid.uuid4().hex)[:10]


@pytest.mark.asyncio
async def test_org_requisites_helper_reads_only_contractor_when_linked():
    """Прямой юнит-тест хелпера: contractor передан — реквизиты берутся
    ЦЕЛИКОМ из контрагента. org.<field> не участвует (не читается вовсе —
    org.inn/kpp/... — column_property, значения в конструкторе ниже заданы
    только чтобы доказать, что они ИГНОРИРУЮТСЯ, а не персистируются —
    присвоение column_property молча не сохраняется, Правило №6)."""
    contractor = Contractor(
        id=1, name="Fresh Contractor", inn="7700000099", kpp="770001001",
        ogrn="1027700000099", address="г. Москва, ул. Новая, д. 1",
        signatory="Свежий Иванов Иванович",
    )
    org = Organization(id=1, name="Org", contractor_id=1)
    req = org_requisites(org, contractor)
    assert req["inn"] == "7700000099"
    assert req["kpp"] == "770001001"
    assert req["ogrn"] == "1027700000099"
    assert req["address"] == "г. Москва, ул. Новая, д. 1"
    assert req["signatory"] == "Свежий Иванов Иванович"


def test_org_requisites_helper_blank_contractor_field_stays_blank():
    """Миграция w6x7y8z9a0b1 (16.10.2026) переделала прошлый пополейный
    фолбэк "контрагент непустой — побеждает, пустой — бери org": теперь
    Contractor — ЕДИНСТВЕННЫЙ источник, пусто у контрагента значит пусто у
    org, никакого фолбэка на org._legacy_* нет. (Прод-регрессия 2026-09-07,
    на которую отвечал старый фолбэк, закрыта по-другому — backfill-миграция
    дозаполнила контрагента значениями org ОДИН раз при переходе, см.
    w6x7y8z9a0b1_org_contractor_single_source.py шаг 2.)"""
    contractor = Contractor(
        id=10, name="Contractor Incomplete", inn="7700000010",
        full_name=None, address="",  # пусто/NULL
        signatory="Подписант Контрагента",
    )
    req = org_requisites(Organization(id=10, name="Org", contractor_id=10), contractor)

    assert req["inn"] == "7700000010"
    assert req["signatory"] == "Подписант Контрагента"
    # Пустое поле контрагента — пусто и у org, без фолбэка.
    assert req["full_name"] is None
    assert req["address"] == ""


@pytest.mark.asyncio
async def test_org_requisites_helper_returns_blank_when_no_contractor():
    """org без contractor_id (не должно происходить после миграции, но
    защитная ветка): все реквизиты пусты, org._legacy_* НЕ читается (не тот
    источник — Правило №6, и опасно читать org.<field> column_property без
    await в произвольном месте, см. docstring org_requisites())."""
    org = Organization(id=2, name="Org No Contractor")
    req = org_requisites(org, None)
    assert req["inn"] is None
    assert req["address"] is None


@pytest.mark.asyncio
async def test_serializer_returns_contractor_requisites_not_stale_org_columns(
    client, superadmin_headers, db_session, test_org,
):
    """GET /api/organizations/{id}: org.inn устарел (расходится с
    контрагентом) — API обязан отдать актуальный ИНН контрагента, не
    устаревшую копию organizations.inn (баг волны Правило №6)."""
    contractor = Contractor(name="Свежий Контрагент 090126", inn=_uniq_inn())
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    stale_inn = _uniq_inn("88")
    org = Organization(
        name="Org With Stale Columns",
        inn=stale_inn, address="устаревший адрес до правки контрагента",
        contractor_id=contractor.id,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    r = await client.get(f"/api/organizations/{org.id}", headers=superadmin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inn"] == contractor.inn
    assert body["inn"] != stale_inn


@pytest.mark.asyncio
async def test_put_organization_with_contractor_writes_to_contractor_not_org(
    client, superadmin_headers, db_session, test_org,
):
    """PUT /api/organizations/{id} с заданным contractor_id: новые реквизиты
    уходят В КОНТРАГЕНТА. org.address (column_property) после этого РАВЕН
    contractor.address — это и есть Правило №6 (один источник, не вторая
    копия); проверяем, что физическая legacy-колонка organizations.address
    (org._legacy_address) НЕ тронута — новый код в неё не пишет."""
    contractor = Contractor(name="Контрагент до правки", inn=_uniq_inn())
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    org = Organization(name="Org To Edit", contractor_id=contractor.id)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    new_address = "г. Санкт-Петербург, Невский пр-т, д. 100"
    r = await client.put(
        f"/api/organizations/{org.id}",
        json={"name": "Org To Edit", "address": new_address, "contractor_id": contractor.id},
        headers=superadmin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == new_address

    await db_session.refresh(contractor)
    await db_session.refresh(org)
    assert contractor.address == new_address
    assert org.address == new_address  # column_property = Contractor.address
    assert org._legacy_address != new_address  # физическая колонка НЕ тронута


@pytest.mark.asyncio
async def test_put_organization_without_contractor_autolinks_and_writes_to_contractor(
    client, superadmin_headers, db_session, test_org,
):
    """org без contractor_id (не должно происходить после миграции
    w6x7y8z9a0b1, но защитная ветка): PUT привязывает/создаёт контрагента по
    ИНН (_auto_link_contractor_by_inn) и пишет реквизиты СРАЗУ в него —
    organizations.* (physical legacy-колонки) не трогаются вовсе."""
    org = Organization(name="Org No Link Yet")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    assert org.contractor_id is None

    inn = _uniq_inn("66")
    r = await client.put(
        f"/api/organizations/{org.id}",
        json={"name": "Org No Link Yet", "inn": inn, "address": "г. Казань"},
        headers=superadmin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inn"] == inn
    assert body["contractor_id"] is not None  # автопривязка сработала

    from sqlalchemy import select
    ctr = (await db_session.execute(
        select(Contractor).where(Contractor.id == body["contractor_id"])
    )).scalar_one()
    assert ctr.inn == inn
    await db_session.refresh(org)
    assert org._legacy_address is None  # физическая колонка org не тронута
