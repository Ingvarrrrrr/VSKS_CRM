# -*- coding: utf-8 -*-
"""Жалоба владельца по заявке №88 / компаньону авансового отчёта РЕЕ-2026-00962
(2026-09-30): на авто-заявке (Wish source='advance_report'), создаваемой
create_purchase для авансового без wish_id, были пустые «Форма договора» и
контрагент, и плашка «позиции не привязаны к плановой позиции», хотя в самом
авансовом всё было привязано к плану. Причина — copy-блок в
app/routers/purchases.py не переносил contract_form/contractor_id/
contractor_name/feo_planned_item_id с закупки на WishItem-и компаньона (см.
app/services/advance_wish_sync.py — общий хелпер, теперь единственный
источник для create_purchase И для синхронизации при PUT, ПРАВИЛО №6).

Покрытие:
  1. Создание авансового БЕЗ contract_form/contractor_id на закупке и БЕЗ
     плановой позиции → компаньон получает contract_form по умолчанию
     (ADVANCE_DEFAULT_CONTRACT_FORM) и contractor_name = ФИО создателя.
  2. Позиция авансового привязана к реальной FeoPlannedItem
     (feo_planned_item_id) → WishItem компаньона получает ту же привязку
     (раньше терялась — источник прод-жалобы).
  3. Закупка указывает contractor_id (контрагент из справочника) → компаньон
     копирует contractor_id, а НЕ ФИО создателя.
  4. PUT уже существующей авансовой закупки (contract_form/contractor_id
     проставлены на закупке ПОСЛЕ создания) → синхронизация докатывает их до
     уже существующей заявки-компаньона (та же ветка, что пересобирает
     WishItems, см. test_advance_reimbursement_wish_draft.py::
     test_put_advance_purchase_draft_still_syncs_companion_items).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.contractor import Contractor
from app.services.advance_wish_sync import ADVANCE_DEFAULT_CONTRACT_FORM


async def _make_subsidy(db_session, org_id, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
        status="approved",  # assert_subsidy_approved_for_binding гейтит create_purchase
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        budget=kwargs.pop("budget", Decimal("1000000")),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=kwargs.pop("name", "Такси до вокзала"),
        quantity=kwargs.pop("quantity", Decimal("1")),
        unit=kwargs.pop("unit", "шт"),
        amount=kwargs.pop("amount", Decimal("500")),
        **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_advance_companion_wish_gets_default_contract_form_and_creator_name(
    client, auth_headers, db_session,
):
    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест дефолтов",
        "items": [
            {
                "item_name": "Канцтовары",
                "item_type": "товар",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 300,
                "total_price": 300,
            }
        ],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    wish_id = resp.json()["wish_id"]
    assert wish_id is not None

    wish = await db_session.get(Wish, wish_id)
    assert wish.contract_form == ADVANCE_DEFAULT_CONTRACT_FORM
    assert wish.contractor_id is None
    assert wish.contractor_name  # ФИО/логин создателя, не пусто


@pytest.mark.asyncio
async def test_advance_companion_wish_copies_planned_item_link_and_contractor(
    client, auth_headers, db_session, test_org,
):
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)

    contractor = Contractor(name="ИП Тестовый поставщик", org_id=test_org.id)
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест привязки к плану",
        "subsidy_id": subsidy.id,
        "contractor_id": contractor.id,
        "contract_form": "services",
        "items": [
            {
                "item_name": "Такси до вокзала",
                "item_type": "услуга",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 500,
                "total_price": 500,
                "feo_category_id": cat.id,
                "feo_planned_item_id": fpi.id,
            }
        ],
    }
    resp = await client.post("/api/purchases/", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    wish_id = resp.json()["wish_id"]

    wish = await db_session.get(Wish, wish_id)
    assert wish.contract_form == "services"  # с закупки, не дефолт
    assert wish.contractor_id == contractor.id
    assert wish.contractor_name is None  # контрагент из справочника — свободное имя не нужно

    wish_items = (await db_session.execute(
        select(WishItem).where(WishItem.wish_id == wish_id)
    )).scalars().all()
    assert len(wish_items) == 1
    assert wish_items[0].feo_planned_item_id == fpi.id


@pytest.mark.asyncio
async def test_put_advance_purchase_keeps_companion_choices(
    client, auth_headers, db_session, test_org,
):
    contractor = Contractor(name="ИП Второй поставщик", org_id=test_org.id)
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    create_payload = {
        "purchase_method": "advance",
        "subject": "Авансовый отчёт — тест синхронизации",
        "items": [
            {
                "item_name": "Такси",
                "item_type": "услуга",
                "quantity": 1,
                "unit": "шт",
                "unit_price": 500,
                "total_price": 500,
            }
        ],
    }
    create_resp = await client.post("/api/purchases/", json=create_payload, headers=auth_headers)
    assert create_resp.status_code in (200, 201), create_resp.text
    data = create_resp.json()
    purchase_id = data["id"]
    wish_id = data["wish_id"]

    wish_before = await db_session.get(Wish, wish_id)
    assert wish_before.contractor_id is None  # ещё не задан на закупке при создании
    # Человек выбрал в заявке сотрудника-контрагента руками.
    wish_before.contractor_name = "Иванов Иван Иванович"
    await db_session.commit()

    put_payload = dict(create_payload)
    put_payload["contract_form"] = "services_food"
    put_payload["contractor_id"] = contractor.id
    resp = await client.put(f"/api/purchases/{purchase_id}", json=put_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(wish_before)
    wish_after = wish_before
    # Правка авансового не затирает заполненное в заявке (владелец: выбранное
    # руками не меняется само) — форма уже стояла по умолчанию, контрагент выбран.
    assert wish_after.contract_form == "goods_single"
    assert wish_after.contractor_name == "Иванов Иван Иванович"
    assert wish_after.contractor_id is None
