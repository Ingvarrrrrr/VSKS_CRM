"""Владелец, 02.10: при добавлении чека в авансовый, если продавца с таким
ИНН в справочнике контрагентов нет — создавать его с реквизитами из ЕГРЮЛ
(наименование/КПП/ОГРН/адрес/руководитель), а не только именем+ИНН+КПП, как
раньше (на проде у 6 из 22 продавцов чеков нет ОГРН, у 16 нет адреса).

ЕГРЮЛ-запрос — app.services.contractor_lookup.fetch_egrul_row, тот же
HTTP-клиент, что и у GET /api/contractors/lookup-inn (ПРАВИЛО №6, второй
клиент не заводим, см. app.services.receipts_creation._create_or_enrich_contractor_from_receipt).
Эти тесты мокают fetch_egrul_row — ни один реально не ходит в сеть.
"""
import uuid

import pytest

from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.services.receipts_creation import _create_receipt_with_items


async def _make_advance_purchase(db_session, test_org):
    p = Purchase(
        item_name=f"Аванс-{uuid.uuid4().hex[:8]}",
        purchase_method="advance",
        status="planned",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


def _receipt_data(seller_inn, seller_name, **extra):
    data = {
        "seller_inn": seller_inn,
        "seller_name": seller_name,
        "receipt_datetime": None,
        "total_sum": None,
        "items": [{"name": "Товар", "quantity": 1, "price": 100, "sum": 100}],
    }
    data.update(extra)
    return data


@pytest.mark.asyncio
async def test_new_seller_inn_enriched_from_egrul(db_session, test_org, monkeypatch):
    p = await _make_advance_purchase(db_session, test_org)
    inn = "7700000011"

    async def _fake_fetch_egrul_row(_inn, **kwargs):
        assert _inn == inn
        return {
            "c": "ООО «БЭСТ ПРАЙС»",
            "n": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «БЭСТ ПРАЙС»",
            "i": inn,
            "o": "1117700000011",
            "p": "770001001",
            "a": "г. Москва, ул. Тестовая, д. 1",
            "g": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Иванов Иван Иванович",
        }

    import app.services.contractor_lookup as _cl
    monkeypatch.setattr(_cl, "fetch_egrul_row", _fake_fetch_egrul_row)

    receipt = await _create_receipt_with_items(
        p.id, _receipt_data(inn, "Бест Прайс из чека"), "manual", {}, db_session,
    )
    assert receipt.id is not None

    from sqlalchemy import select
    c = (await db_session.execute(select(Contractor).where(Contractor.inn == inn))).scalar_one()
    assert c.name == "ООО «БЭСТ ПРАЙС»"
    assert c.ogrn == "1117700000011"
    assert c.kpp == "770001001"
    assert c.address == "г. Москва, ул. Тестовая, д. 1"
    assert c.signatory and "Иванов" in c.signatory


@pytest.mark.asyncio
async def test_existing_seller_contractor_not_touched(db_session, test_org, monkeypatch):
    p = await _make_advance_purchase(db_session, test_org)
    inn = "7700000022"
    existing = Contractor(name="Старое Имя", inn=inn, address="Старый адрес")
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    called = False

    async def _fake_fetch_egrul_row(_inn, **kwargs):
        nonlocal called
        called = True
        return {"c": "Новое Имя", "a": "Новый адрес"}

    import app.services.contractor_lookup as _cl
    monkeypatch.setattr(_cl, "fetch_egrul_row", _fake_fetch_egrul_row)

    await _create_receipt_with_items(
        p.id, _receipt_data(inn, "Что угодно из чека"), "manual", {}, db_session,
    )

    await db_session.refresh(existing)
    assert existing.name == "Старое Имя"
    assert existing.address == "Старый адрес"
    assert not called  # существующий контрагент — в ЕГРЮЛ вообще не ходим


@pytest.mark.asyncio
async def test_egrul_failure_falls_back_to_receipt_data(db_session, test_org, monkeypatch):
    p = await _make_advance_purchase(db_session, test_org)
    inn = "7700000033"

    async def _fake_fetch_egrul_row(_inn, **kwargs):
        raise TimeoutError("ФНС не ответила")

    import app.services.contractor_lookup as _cl
    monkeypatch.setattr(_cl, "fetch_egrul_row", _fake_fetch_egrul_row)

    receipt = await _create_receipt_with_items(
        p.id, _receipt_data(inn, "Продавец из чека"), "manual", {}, db_session,
    )
    assert receipt.id is not None

    from sqlalchemy import select
    c = (await db_session.execute(select(Contractor).where(Contractor.inn == inn))).scalar_one()
    assert c.name == "Продавец из чека"
    assert c.ogrn is None
