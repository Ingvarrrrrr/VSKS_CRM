"""152-ФЗ: гейт согласия после входа — GET/POST /api/legal/consent-status,
/api/legal/consent (backend/app/routers/legal.py) + единая проверка
backend/app/services/consent_status.py.

Один профильный файл на эту правку (см. feedback_scope_tests_to_change):
- без согласия → pd_consent_required=true; после POST pd → false;
- старый формат document_version (без poruchenie) остаётся актуальным для pd;
- владелец организации без поручения → poruchenie_required=true, не-владелец
  той же организации → false;
- POST poruchenie за чужую организацию → 403.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user_consent import UserConsent
from app.services.consent_status import is_consent_current, parse_document_version
from app.services.legal_constants import (
    PD_CONSENT_DOCUMENTS,
    PD_CONSENT_VERSION,
    PORUCHENIE_DOCUMENTS,
    PORUCHENIE_VERSION,
)


def test_parse_document_version():
    assert parse_document_version("privacy:1.0+consent:1.0") == {
        "privacy": "1.0",
        "consent": "1.0",
    }
    assert parse_document_version("") == {}
    assert parse_document_version(None) == {}


def test_is_consent_current_ignores_extra_pairs():
    # Старая запись (до добавления poruchenie) со склейкой ВСЕХ публичных
    # документов, а не только PD_CONSENT_DOCUMENTS — лишние пары игнорируются.
    old = "consent:1.0+cookies:1.0+privacy:1.0"
    required = parse_document_version(PD_CONSENT_VERSION)
    assert is_consent_current(old, required) is True


def test_is_consent_current_fails_on_version_mismatch():
    required = parse_document_version(PD_CONSENT_VERSION)
    assert is_consent_current("privacy:0.9+consent:1.0", required) is False


@pytest.mark.asyncio
async def test_status_pd_required_without_any_consent(client, test_user, auth_headers):
    resp = await client.get("/api/legal/consent-status", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pd_consent_required"] is True
    assert body["poruchenie_required"] is False  # не владелец ни одной организации
    assert body["pd_version"] == PD_CONSENT_VERSION
    assert body["poruchenie_version"] == PORUCHENIE_VERSION


@pytest.mark.asyncio
async def test_post_pd_consent_satisfies_status(client, test_user, auth_headers, db_session):
    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "pd", "accepted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    row = (
        await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == test_user.id)
        )
    ).scalar_one()
    assert row.documents == list(PD_CONSENT_DOCUMENTS)
    assert row.document_version == PD_CONSENT_VERSION
    assert row.org_id is None
    assert row.source == "login"

    status_resp = await client.get("/api/legal/consent-status", headers=auth_headers)
    assert status_resp.json()["pd_consent_required"] is False


@pytest.mark.asyncio
async def test_old_format_consent_record_is_current(client, test_user, auth_headers, db_session):
    db_session.add(UserConsent(
        user_id=test_user.id,
        email=f"{test_user.username}@example.com",
        document_version="consent:1.0+cookies:1.0+privacy:1.0",
        documents=["privacy", "consent"],
        source="registration",
    ))
    await db_session.commit()

    resp = await client.get("/api/legal/consent-status", headers=auth_headers)
    assert resp.json()["pd_consent_required"] is False


@pytest.mark.asyncio
async def test_poruchenie_required_for_owner_not_for_other_user(
    client, test_user, auth_headers, test_org, db_session, admin_headers, test_admin_user,
):
    test_org.owner_user_id = test_user.id
    await db_session.commit()

    owner_status = await client.get("/api/legal/consent-status", headers=auth_headers)
    assert owner_status.status_code == 200, owner_status.text
    body = owner_status.json()
    assert body["poruchenie_required"] is True
    assert body["poruchenie_org"]["id"] == test_org.id

    other_status = await client.get("/api/legal/consent-status", headers=admin_headers)
    assert other_status.json()["poruchenie_required"] is False


@pytest.mark.asyncio
async def test_post_poruchenie_for_own_org(client, test_user, auth_headers, test_org, db_session):
    test_org.owner_user_id = test_user.id
    await db_session.commit()

    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "poruchenie", "accepted": True, "org_id": test_org.id},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    row = (
        await db_session.execute(
            select(UserConsent).where(
                UserConsent.user_id == test_user.id,
                UserConsent.org_id == test_org.id,
            )
        )
    ).scalar_one()
    assert row.documents == list(PORUCHENIE_DOCUMENTS)
    assert row.document_version == PORUCHENIE_VERSION

    status_resp = await client.get("/api/legal/consent-status", headers=auth_headers)
    assert status_resp.json()["poruchenie_required"] is False


@pytest.mark.asyncio
async def test_post_poruchenie_for_someone_elses_org_forbidden(
    client, test_admin_user, admin_headers, db_session,
):
    foreign_org = Organization(name=f"ForeignOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(foreign_org)
    await db_session.commit()
    await db_session.refresh(foreign_org)
    # Не владелец (owner_user_id пуст/чужой) — попытка принять поручение
    # за эту организацию должна быть отказана.

    resp = await client.post(
        "/api/legal/consent",
        json={"kind": "poruchenie", "accepted": True, "org_id": foreign_org.id},
        headers=admin_headers,
    )
    assert resp.status_code == 403
