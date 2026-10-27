"""POST /api/products/merge и GET /api/products/similar-groups — право
products.edit_catalog (ПРАВИЛО №8 п.1/6): без входа 401, с входом но без
права 403, кривые id 422/404 (не 500)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product


def _name(suffix: str) -> str:
    return f"ТестМерджЭндпоинт {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_merge_requires_auth(client):
    resp = await client.post("/api/products/merge", json={"winner_id": 1, "loser_ids": [2]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_merge_requires_catalog_edit_right(client, auth_headers):
    resp = await client.post(
        "/api/products/merge", json={"winner_id": 1, "loser_ids": [2]}, headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_merge_rejects_winner_in_losers_422(client, superadmin_headers):
    resp = await client.post(
        "/api/products/merge", json={"winner_id": 1, "loser_ids": [1, 2]}, headers=superadmin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_merge_unknown_ids_404(client, superadmin_headers):
    resp = await client.post(
        "/api/products/merge",
        json={"winner_id": 999_999_990, "loser_ids": [999_999_991]},
        headers=superadmin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_success_via_endpoint(client, superadmin_headers, db_session):
    winner = Product(name=_name("winner"))
    loser = Product(name=_name("loser"), manufacturer="Тест")
    db_session.add_all([winner, loser])
    await db_session.commit()

    resp = await client.post(
        "/api/products/merge",
        json={"winner_id": winner.id, "loser_ids": [loser.id]},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["winner_id"] == winner.id

    assert (await db_session.execute(
        select(Product).where(Product.id == loser.id)
    )).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_similar_groups_requires_auth(client):
    resp = await client.get("/api/products/similar-groups", params={"q": "тест"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_similar_groups_short_query_422(client, superadmin_headers):
    resp = await client.get(
        "/api/products/similar-groups", params={"q": "аб"}, headers=superadmin_headers,
    )
    assert resp.status_code == 422
