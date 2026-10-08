"""152-ФЗ: /api/register обязан отказывать без согласия на ПДн и без принятия
условий поручения обработки ПДн, и писать ОБЕ записи UserConsent при согласии —
backend/app/routers/organizations.py:register().

Один профильный файл на эту правку (см. feedback_scope_tests_to_change) —
без согласия/поручения → 400, с обоими → две записи user_consents: pd
(document_version = серверная PD_CONSENT_VERSION, documents = PD_CONSENT_DOCUMENTS,
org_id = NULL) и poruchenie (PORUCHENIE_VERSION, PORUCHENIE_DOCUMENTS,
org_id = id созданной организации).
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.user_consent import UserConsent
from app.services.legal_constants import (
    PD_CONSENT_DOCUMENTS,
    PD_CONSENT_VERSION,
    PORUCHENIE_DOCUMENTS,
    PORUCHENIE_VERSION,
)


def _payload(**overrides):
    email = f"consent-test-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "org_name": f"TestOrg-{uuid.uuid4().hex[:8]}",
        "password": "s3cret-password",
        "email": email,
        "consent_accepted": True,
        "consent_version": "privacy:1.0+consent:1.0",
        "poruchenie_accepted": True,
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
async def test_register_without_poruchenie_rejected(client):
    resp = await client.post("/api/register", json=_payload(poruchenie_accepted=False))
    assert resp.status_code == 400
    assert "поручения" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_register_with_consent_creates_user_consent_records(client, db_session):
    payload = _payload()
    resp = await client.post("/api/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user_id = body["id"]
    org_id = body["org_id"]
    assert org_id is not None

    rows = (
        await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == user_id)
        )
    ).scalars().all()
    by_documents = {tuple(c.documents): c for c in rows}

    pd_consent = by_documents[tuple(PD_CONSENT_DOCUMENTS)]
    assert pd_consent.email == payload["email"]
    # Серверная версия, НЕ то, что прислал фронт (ПРАВИЛО №6).
    assert pd_consent.document_version == PD_CONSENT_VERSION
    assert pd_consent.org_id is None
    assert pd_consent.source == "registration"

    poruchenie_consent = by_documents[tuple(PORUCHENIE_DOCUMENTS)]
    assert poruchenie_consent.document_version == PORUCHENIE_VERSION
    assert poruchenie_consent.org_id == org_id
    assert poruchenie_consent.source == "registration"
