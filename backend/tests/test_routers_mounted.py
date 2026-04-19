"""Smoke test — asserts every major router is mounted.

A 404 means the router was not included in backend/app/__init__.py.
A 500 means a startup or import error — router is mounted but broken.
A 401/403 is acceptable (auth required proves router IS mounted).
A 200 is ideal.
"""
import pytest
from httpx import AsyncClient


# (path, method) — endpoints that MUST exist before AND after refactor.
# Add entries here as new routers are extracted in later plans (16-02..16-10).
MOUNT_PROBES = [
    # Existing (baseline — must pass pre-refactor)
    ("/api/purchases/", "GET"),
    ("/api/purchases/export/columns", "GET"),
    ("/api/purchases/export/excel", "GET"),
    ("/api/purchases/items/import/template", "GET"),
    ("/api/tasks/", "GET"),
    ("/api/tasks/badges", "GET"),
    ("/api/tasks/org-summary", "GET"),
    ("/api/tasks/pending-consent", "GET"),
    ("/api/tasks/consent-declines", "GET"),
]


@pytest.mark.parametrize("path,method", MOUNT_PROBES)
async def test_router_mounted(client: AsyncClient, path: str, method: str) -> None:
    resp = await client.request(method, path)
    assert resp.status_code != 404, (
        f"{method} {path} returned 404 — router NOT mounted in app/__init__.py"
    )
    assert resp.status_code < 500, (
        f"{method} {path} returned {resp.status_code} — router import error"
    )


# Named markers for per-extract verify commands in later plans:
# pytest tests/test_routers_mounted.py::test_export_mount
async def test_export_mount(client: AsyncClient) -> None:
    resp = await client.get("/api/purchases/export/columns")
    assert resp.status_code != 404
    assert resp.status_code < 500


async def test_items_import_mount(client: AsyncClient) -> None:
    resp = await client.get("/api/purchases/items/import/template")
    assert resp.status_code != 404
    assert resp.status_code < 500


async def test_members_mount(client: AsyncClient) -> None:
    # PATCH requires body; use OPTIONS to detect mount without sending data
    resp = await client.request("OPTIONS", "/api/purchases/1/assign")
    # 200 or 405 (method not allowed) both prove the path exists at some method
    assert resp.status_code != 404


async def test_transitions_mount(client: AsyncClient) -> None:
    resp = await client.post("/api/purchases/1/transition?status=confirmed")
    assert resp.status_code != 404
    assert resp.status_code < 500


async def test_visibility_mount(client: AsyncClient) -> None:
    # task_visibility.py may be helper-only (no router); skip if so.
    # If it mounts anything, /api/tasks/ still proves enrichment path works.
    resp = await client.get("/api/tasks/")
    assert resp.status_code != 404


async def test_badges_mount(client: AsyncClient) -> None:
    resp = await client.get("/api/tasks/badges")
    assert resp.status_code != 404
    assert resp.status_code < 500


async def test_delegation_mount(client: AsyncClient) -> None:
    resp = await client.get("/api/tasks/pending-consent")
    assert resp.status_code != 404
    assert resp.status_code < 500


async def test_comments_mount(client: AsyncClient) -> None:
    resp = await client.get("/api/tasks/1/comments")
    assert resp.status_code != 404
    assert resp.status_code < 500
