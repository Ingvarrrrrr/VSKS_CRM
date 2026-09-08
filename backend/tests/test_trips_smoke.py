"""Smoke tests for the trips (ПЛ/vehicles) endpoints — no heavy fixtures,
just confirm the routes are wired and answer 200 under an authorized admin.

GET /api/trips           — app/routers/trips.py::list_trips
GET /api/trips/stats      — app/routers/trips_reports.py::waybill_stats
GET /api/trips/last-fuel  — app/routers/trips_reports.py::last_fuel_for_vehicle

All three gate on require_tab("vehicles") — admin_headers (role=org_admin)
has it via the global startup seed (_phase29_vehicles_tab_and_actions).
"""
import pytest


@pytest.mark.asyncio
async def test_list_trips_returns_200(client, admin_headers):
    resp = await client.get("/api/trips", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_trips_stats_returns_200(client, admin_headers):
    resp = await client.get("/api/trips/stats", headers=admin_headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_trips_last_fuel_returns_200(client, admin_headers):
    resp = await client.get(
        "/api/trips/last-fuel", params={"vehicle_id": 1}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "fuel_remaining_l" in body
