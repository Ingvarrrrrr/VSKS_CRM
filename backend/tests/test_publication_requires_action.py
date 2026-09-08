"""Phase 17 Plan 04: D-06 publications.py migrates from inline can_publish to require_action('publication.create')."""
import pytest


@pytest.mark.asyncio
async def test_publication_requires_action_403_without_override(
    client, auth_headers, test_user, user_org_access, make_role_permission
):
    """User without publication.create in role seed AND no override → 403.

    Real route is POST /api/publications/purchases/{purchase_id} (see
    app/routers/publications.py:51), not /api/publications/ — the purchase
    doesn't need to exist: require_action('publication.create') runs as a
    Depends and rejects before the handler body/purchase lookup runs.
    """
    r = await client.post(
        "/api/publications/purchases/999999",
        headers=auth_headers,
        json={"platform": "roseltorg_rb"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_publication_granted_via_override_returns_200(
    client, auth_headers, test_user, user_org_access, make_override, make_purchase, monkeypatch
):
    """User with per-user publication.create override → 200.

    Publishing schedules a real background call to the marketplace client
    (app/routers/publications.py:139, _call_roseltorg for platform
    'roseltorg_rb') which the ASGI test client actually runs inline — mock it
    out so the test never touches a real trading-platform API (see
    services/publications_fabrikant_client / _roseltorg_client; same rule as
    for Фабрикант — no live calls from tests).
    """
    async def _fake_call_roseltorg(pub_id, payload):
        return None

    monkeypatch.setattr(
        "app.routers.publications._call_roseltorg", _fake_call_roseltorg
    )

    await make_override(user_org_access.id, "publication.create", True)
    purchase = await make_purchase()
    r = await client.post(
        f"/api/publications/purchases/{purchase.id}",
        headers=auth_headers,
        json={"platform": "roseltorg_rb"},
    )
    assert r.status_code in (200, 201)


@pytest.mark.asyncio
async def test_publications_router_has_no_inline_can_publish():
    """Grep-style assert: the source of publications.py must not contain inline `if not current_user.can_publish` after Plan 17-04 Task 4."""
    from pathlib import Path
    src = Path("/app/app/routers/publications.py").read_text(encoding="utf-8")
    # After migration: zero inline can_publish checks (the DB column still exists on User, but runtime gate uses require_action)
    assert "can_publish" not in src, "publications.py still contains can_publish — Plan 17-04 Task 4 D-06 migration incomplete"
