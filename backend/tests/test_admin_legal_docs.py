"""Тесты для app/routers/admin_legal_docs.py — закрытый раздел «Документы»
админки (внутренние документы по 152-ФЗ, модель угроз, уведомление в РКН
и т. п., см. docstring самого роутера).

Проверяется только периметр доступа и форма ответа:
- без токена → 401 (get_current_user внутри require_role);
- роль employee → 403 (require_role('superadmin', 'admin', 'account_owner'));
- superadmin/admin/account_owner → 200, непустой список, заголовки
  Cache-Control: no-store и X-Robots-Tag: noindex (документы не должны
  оседать в кэше/поиске);
- документ по известному slug → 200 + html;
- неизвестный slug и попытка path traversal в slug → 404 (slug ищется
  только по словарю реестра app/services/internal_legal_docs.py, см. его
  docstring — файловая система не читается вообще, поэтому traversal
  не может утечь за пределы реестра).

Паттерн fixtures — как в test_require_tab.py / test_account_owner_all_rights.py
(client, make_user + create_access_token для произвольной роли).
"""
import pytest


def _headers_for(user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    r = await client.get("/api/admin/legal-docs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_403_for_employee(client, auth_headers):
    r = await client.get("/api/admin/legal-docs", headers=auth_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["account_owner", "admin", "superadmin"])
async def test_list_200_for_allowed_roles(client, db_session, test_org, make_user, role):
    user = await make_user(role=role, org_id=test_org.id)
    r = await client.get("/api/admin/legal-docs", headers=_headers_for(user))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert r.headers.get("cache-control") == "no-store"
    assert r.headers.get("x-robots-tag") == "noindex"


@pytest.mark.asyncio
async def test_get_doc_200_for_known_slug(client, db_session, test_org, make_user):
    owner = await make_user(role="account_owner", org_id=test_org.id)
    listed = await client.get("/api/admin/legal-docs", headers=_headers_for(owner))
    slug = listed.json()[0]["slug"]

    r = await client.get(f"/api/admin/legal-docs/{slug}", headers=_headers_for(owner))
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert r.headers.get("x-robots-tag") == "noindex"
    doc = r.json()
    assert doc["slug"] == slug
    assert "html" in doc and doc["html"]


@pytest.mark.asyncio
async def test_get_doc_404_for_unknown_slug(client, db_session, test_org, make_user):
    owner = await make_user(role="account_owner", org_id=test_org.id)
    r = await client.get("/api/admin/legal-docs/does-not-exist", headers=_headers_for(owner))
    assert r.status_code == 404
    assert r.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_get_doc_404_for_traversal_slug(client, db_session, test_org, make_user):
    """'..%2F..%2Fetc%2Fpasswd' percent-decodes to a slash, so Starlette's own
    routing (not our handler) 404s it before get_internal_legal_doc() is even
    called — a stronger guarantee than ours, since it never reaches the slug
    lookup at all. No Cache-Control assertion here: this 404 is the generic
    Starlette "Not Found" response, not one our router built."""
    owner = await make_user(role="account_owner", org_id=test_org.id)
    r = await client.get(
        "/api/admin/legal-docs/..%2F..%2Fetc%2Fpasswd", headers=_headers_for(owner)
    )
    assert r.status_code == 404
