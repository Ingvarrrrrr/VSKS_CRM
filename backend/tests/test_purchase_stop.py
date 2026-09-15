"""Остановка/возобновление закупки напрямую (владелец, 2026-09-15):
POST /api/purchases/{id}/stop и POST /api/purchases/{id}/resume
(backend/app/routers/purchase_stop.py). Плюс регресс: остановка ЗАЯВКИ
по-прежнему каскадом останавливает привязанные закупки через тот же общий
хелпер app.services.purchase_stop.can_stop_purchase (ПРАВИЛО №6) — отдельного
теста на это в проекте раньше не было (grep по test_*.py ничего не нашёл),
добавлен здесь как регресс-покрытие.
"""
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_stop_purchase_200_sets_fields(client, make_purchase, db_session, admin_headers, test_admin_user):
    p = await make_purchase(status="plan_schedule")
    resp = await client.post(
        f"/api/purchases/{p.id}/stop", json={"reason": "Бюджет пересмотрен"}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stopped_at"] is not None
    assert body["stopped_by"] == test_admin_user.id
    assert body["stopped_reason"] == "Бюджет пересмотрен"
    assert body["stopped_wish_id"] is None
    await db_session.refresh(p)
    assert p.stopped_at is not None
    assert p.stopped_reason == "Бюджет пересмотрен"


@pytest.mark.asyncio
async def test_stop_purchase_already_stopped_409(client, make_purchase, admin_headers):
    p = await make_purchase(status="plan_schedule")
    resp1 = await client.post(f"/api/purchases/{p.id}/stop", json={}, headers=admin_headers)
    assert resp1.status_code == 200, resp1.text
    resp2 = await client.post(f"/api/purchases/{p.id}/stop", json={}, headers=admin_headers)
    assert resp2.status_code == 409, resp2.text
    assert "уже остановлена" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_stop_purchase_contracted_409_with_readable_reason(client, make_purchase, admin_headers):
    p = await make_purchase(status="contracted")
    resp = await client.post(f"/api/purchases/{p.id}/stop", json={}, headers=admin_headers)
    assert resp.status_code == 409, resp.text
    message = resp.json()["message"]
    assert "Заключён договор" in message
    assert "остановить нельзя" in message


@pytest.mark.asyncio
async def test_resume_purchase_clears_fields(client, make_purchase, db_session, admin_headers):
    p = await make_purchase(status="plan_schedule")
    resp1 = await client.post(f"/api/purchases/{p.id}/stop", json={"reason": "x"}, headers=admin_headers)
    assert resp1.status_code == 200, resp1.text
    resp2 = await client.post(f"/api/purchases/{p.id}/resume", headers=admin_headers)
    assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    assert body["stopped_at"] is None
    assert body["stopped_by"] is None
    assert body["stopped_reason"] is None
    assert body["stopped_wish_id"] is None
    await db_session.refresh(p)
    assert p.stopped_at is None
    assert p.stopped_reason is None


@pytest.mark.asyncio
async def test_resume_purchase_not_stopped_409(client, make_purchase, admin_headers):
    p = await make_purchase(status="plan_schedule")
    resp = await client.post(f"/api/purchases/{p.id}/resume", headers=admin_headers)
    assert resp.status_code == 409, resp.text
    assert "не остановлена" in resp.json()["message"]


@pytest.mark.asyncio
async def test_wish_stop_still_cascades_to_linked_purchase(client, db_session, test_org, test_admin_user,
                                                             make_purchase, admin_headers):
    """Регресс: POST /api/wishes/{id}/stop должен по-прежнему останавливать
    привязанную закупку, не дошедшую до 'contracted' (см.
    app/routers/wish_transitions.py::stop_wish, теперь через
    app.services.purchase_stop.can_stop_purchase)."""
    from app.models.wish import Wish

    wish = Wish(org_id=test_org.id, title="Test wish for stop cascade", status="converted",
                created_by=test_admin_user.id)
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)

    p = await make_purchase(status="plan_schedule", wish_id=wish.id)

    resp = await client.post(f"/api/wishes/{wish.id}/stop", json={"reason": "cascade test"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(p)
    assert p.stopped_at is not None
    assert p.stopped_wish_id == wish.id
