"""Владелец, 06.10.2026 (заявка №115, автор-исполнитель Цокало, статус
rejected): «На этапе Заявки превышение НЕ блокируется. Исполнитель должен
мочь сохранить и отправить заявку. Согласующий решает — согласует или
перераспределит».

Проверяем:
  (а) PUT /api/wishes/{id} с позицией дороже плановой позиции ФЭО НЕ бросает
      409 (старый жёсткий assert_tz_not_over_plan в update_wish снят) — 200,
      и ответ несёт непустой tz_over_plan_warnings.
  (б) GET /api/wishes/{id} той же заявки отдаёт тот же непустой warning.
  (в) Заявка БЕЗ превышения — tz_over_plan_warnings пуст и там, и там.

app.services.wish_tz_warnings.wish_tz_over_plan_warnings — единственный
источник (ПРАВИЛО №6), читает ту же collect_tz_over_plan_violations, которой
уже пользуются согласование/конвертация заявки.
"""
from decimal import Decimal

import pytest

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.wish_approval import WishApproval
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem


async def _make_subsidy_with_category(db_session, plan_amount: str):
    subsidy = Subsidy(
        name=f"TestSubsidy-tzwarn-{id(db_session)}", year=2026, budget=0,
        status="approved", require_planned_dates=False,
    )
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Категория плана")
    db_session.add(cat)
    await db_session.flush()
    planned = FeoPlannedItem(
        feo_category_id=cat.id, name="Плановая позиция", quantity=Decimal("1"),
        unit_price=Decimal(plan_amount), amount=Decimal(plan_amount), is_active=True,
    )
    db_session.add(planned)
    await db_session.commit()
    await db_session.refresh(subsidy)
    await db_session.refresh(cat)
    return subsidy, cat


@pytest.mark.asyncio
async def test_put_wish_over_plan_does_not_409_and_returns_warning(
    client, db_session, test_org, test_user, auth_headers,
):
    """Воспроизводит заявку №115: статус rejected, правка СУЩЕСТВУЮЩЕЙ позиции
    (ветка update_wish для non-draft — delete+recreate только у draft) на
    цену, превышающую план категории — старый жёсткий 409 здесь и стоял."""
    subsidy, cat = await _make_subsidy_with_category(db_session, "254046")

    w = Wish(
        org_id=test_org.id, title="Заявка №115", status="rejected",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    wi = WishItem(
        wish_id=w.id, item_name="Позиция ТЗ", quantity=Decimal("1"),
        unit_price=Decimal("1000"), total_price=Decimal("1000"),
        feo_category_id=cat.id,
    )
    db_session.add(wi)
    # Хотя бы один согласующий — иначе update_wish отказывает 409 ДО гейта
    # ТЗ/плана («согласующие не выбраны»), что не относится к этой задаче.
    db_session.add(WishApproval(wish_id=w.id, user_id=test_user.id, order_num=0))
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(wi)

    payload = {
        "items": [
            {
                "id": wi.id,
                "unit_price": 482350,
                "total_price": 482350,
            }
        ]
    }
    resp = await client.put(f"/api/wishes/{w.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tz_over_plan_warnings"], "ожидался непустой tz_over_plan_warnings"
    warn = body["tz_over_plan_warnings"][0]
    assert warn["feo_category_id"] == cat.id
    assert warn["category_name"] == cat.name
    assert warn["excess_amount"] > 0

    get_resp = await client.get(f"/api/wishes/{w.id}", headers=auth_headers)
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["tz_over_plan_warnings"], "GET обязан отдавать тот же warning"
    assert get_body["tz_over_plan_warnings"][0]["feo_category_id"] == cat.id


@pytest.mark.asyncio
async def test_wish_within_plan_has_no_warning(
    client, db_session, test_org, test_user, auth_headers,
):
    subsidy, cat = await _make_subsidy_with_category(db_session, "254046")

    w = Wish(
        org_id=test_org.id, title="Заявка без превышения", status="rejected",
        created_by=test_user.id, subsidy_id=subsidy.id, feo_category_id=cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    wi = WishItem(
        wish_id=w.id, item_name="Позиция ТЗ в рамках плана", quantity=Decimal("1"),
        unit_price=Decimal("500"), total_price=Decimal("500"),
        feo_category_id=cat.id,
    )
    db_session.add(wi)
    db_session.add(WishApproval(wish_id=w.id, user_id=test_user.id, order_num=0))
    await db_session.commit()
    await db_session.refresh(w)
    await db_session.refresh(wi)

    payload = {
        "items": [
            {
                "id": wi.id,
                "unit_price": 1000,
                "total_price": 1000,
            }
        ]
    }
    resp = await client.put(f"/api/wishes/{w.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["tz_over_plan_warnings"] == []

    get_resp = await client.get(f"/api/wishes/{w.id}", headers=auth_headers)
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["tz_over_plan_warnings"] == []
