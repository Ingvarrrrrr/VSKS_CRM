"""Правило №6 (D1): контрагент — единственный источник истины для юр.
реквизитов организации (inn/kpp/ogrn/address/подписант/full_name), когда
Organization.contractor_id задан. Раньше сериализатор брал "непустое
значение org, иначе contractor" — если контрагента правили отдельно
(ContractorEditDialog), organizations.* оставались устаревшими и именно их
показывал API. См. app/services/org_requisites.py, app/routers/organizations.py.
"""
import uuid

import pytest

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.services.org_requisites import org_requisites


def _uniq_inn(prefix: str = "77") -> str:
    return (prefix + uuid.uuid4().hex)[:10]


@pytest.mark.asyncio
async def test_org_requisites_helper_prefers_contractor_when_linked():
    """Прямой юнит-тест хелпера: contractor_id задан и контрагент передан —
    реквизиты берутся ЦЕЛИКОМ из контрагента, даже если org хранит другие
    (устаревшие) значения в своих deprecated-колонках."""
    contractor = Contractor(
        id=1, name="Fresh Contractor", inn="7700000099", kpp="770001001",
        ogrn="1027700000099", address="г. Москва, ул. Новая, д. 1",
        signatory="Свежий Иванов Иванович",
    )
    org = Organization(
        id=1, name="Org", contractor_id=1,
        inn="7700000000", kpp="000000000", ogrn="0000000000000",
        address="устаревший адрес", signatory="Старый Петров Петрович",
    )
    req = org_requisites(org, contractor)
    assert req["inn"] == "7700000099"
    assert req["kpp"] == "770001001"
    assert req["ogrn"] == "1027700000099"
    assert req["address"] == "г. Москва, ул. Новая, д. 1"
    assert req["signatory"] == "Свежий Иванов Иванович"


def test_org_requisites_helper_falls_back_per_field_when_contractor_field_blank(caplog):
    """Прод-регрессия 2026-09-07 (org id=5 «АНО ЦЕНТРПОИСК»): у контрагента
    full_name пусто, у org — заполнено. Слепое "контрагент побеждает целиком"
    стирало бы наименование заказчика в документах. Теперь фолбэк — ПОПОЛЕЙНО:
    контрагент побеждает там, где у него есть значение (inn), а по пустому
    полю (full_name) отдаётся значение org + WARNING в лог."""
    contractor = Contractor(
        id=10, name="Contractor Incomplete", inn="7700000010",
        full_name=None, address="",  # пусто/NULL — ровно прод-кейс
        signatory="Подписант Контрагента",
    )
    org = Organization(
        id=10, name="Org", contractor_id=10,
        full_name="ПОЛНОЕ НАИМЕНОВАНИЕ ОРГАНИЗАЦИИ",
        address="г. Москва, org-адрес",
        signatory="Подписант Организации (не должен победить)",
    )
    with caplog.at_level("WARNING"):
        req = org_requisites(org, contractor)

    # Контрагент побеждает там, где у него есть значение
    assert req["inn"] == "7700000010"
    assert req["signatory"] == "Подписант Контрагента"
    # Пустое поле контрагента — фолбэк на org, а не пропажа значения
    assert req["full_name"] == "ПОЛНОЕ НАИМЕНОВАНИЕ ОРГАНИЗАЦИИ"
    assert req["address"] == "г. Москва, org-адрес"
    # Предупреждение в лог — сигнал дозаполнить контрагента
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("full_name" in w and "10" in w for w in warnings)
    assert any("address" in w for w in warnings)


@pytest.mark.asyncio
async def test_org_requisites_helper_falls_back_to_org_columns_when_no_contractor():
    """Переходный период: org без contractor_id — старые (deprecated) колонки
    Organization остаются единственным источником."""
    org = Organization(
        id=2, name="Org No Contractor",
        inn="7711111111", kpp="771101001", ogrn="1027711111111",
        address="г. Тверь", signatory="Сидоров Сидор Сидорович",
    )
    req = org_requisites(org, None)
    assert req["inn"] == "7711111111"
    assert req["address"] == "г. Тверь"


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
    уходят В КОНТРАГЕНТА, а organizations.* (deprecated) не перезаписываются
    новым значением — источник истины один."""
    contractor = Contractor(name="Контрагент до правки", inn=_uniq_inn())
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    org = Organization(name="Org To Edit", contractor_id=contractor.id, inn=contractor.inn)
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    new_address = "г. Санкт-Петербург, Невский пр-т, д. 100"
    r = await client.put(
        f"/api/organizations/{org.id}",
        json={"name": org.name, "address": new_address, "contractor_id": contractor.id},
        headers=superadmin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == new_address

    await db_session.refresh(contractor)
    await db_session.refresh(org)
    assert contractor.address == new_address
    assert org.address != new_address  # deprecated-колонка НЕ тронута


@pytest.mark.asyncio
async def test_put_organization_without_contractor_keeps_legacy_behavior_and_autolinks(
    client, superadmin_headers, db_session, test_org,
):
    """org без contractor_id: PUT по-прежнему пишет в organizations.* (переходный
    период) И привязывает/создаёт контрагента по ИНН — поведение существовавшего
    _auto_link_contractor_by_inn не должно было сломаться."""
    org = Organization(name="Org No Link Yet")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    assert org.contractor_id is None

    inn = _uniq_inn("66")
    r = await client.put(
        f"/api/organizations/{org.id}",
        json={"name": org.name, "inn": inn, "address": "г. Казань"},
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
