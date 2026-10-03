"""152-ФЗ: /api/register обязан отказывать без согласия на ПДн и писать
UserConsent при согласии — backend/app/routers/organizations.py:register().

Один профильный файл на эту правку (см. feedback_scope_tests_to_change) —
без согласия → 400, с согласием → запись user_consents с document_version и
перечнем документов из REGISTRATION_CONSENT_DOCUMENTS.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.user_consent import UserConsent
from app.services.legal_constants import REGISTRATION_CONSENT_DOCUMENTS


def _payload(**overrides):
    email = f"consent-test-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "org_name": f"TestOrg-{uuid.uuid4().hex[:8]}",
        "password": "s3cret-password",
        "email": email,
        "consent_accepted": True,
        "consent_version": "privacy:1.0+consent:1.0",
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_register_without_consent_rejected(client):
    resp = await client.post("/api/register", json=_payload(consent_accepted=False))
    assert resp.status_code == 400
    assert "согласия" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_register_with_consent_missing_version_rejected(client):
    resp = await client.post(
        "/api/register",
        json=_payload(consent_accepted=True, consent_version=None),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_with_consent_creates_user_consent_record(client, db_session):
    payload = _payload()
    resp = await client.post("/api/register", json=payload)
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]

    result = await db_session.execute(
        select(UserConsent).where(UserConsent.user_id == user_id)
    )
    consent = result.scalar_one()
    assert consent.email == payload["email"]
    assert consent.document_version == payload["consent_version"]
    assert consent.documents == list(REGISTRATION_CONSENT_DOCUMENTS)
    assert consent.source == "registration"
