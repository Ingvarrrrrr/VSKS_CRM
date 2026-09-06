"""python-jose -> PyJWT migration (backend/app/auth/jwt.py).

Покрывает инвариант задачи: формат токена (claims, HS256, exp) не меняется,
исключения из PyJWT (`jwt.PyJWTError`/`ExpiredSignatureError`) продолжают
приводить к 401 через тот же путь (get_current_user), что и раньше с
python-jose (`JWTError`).
"""
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from jwt.exceptions import InvalidSubjectError

from app.auth.jwt import create_access_token
from app.config import settings


def test_encode_decode_roundtrip():
    """create_access_token() -> jwt.decode() возвращает исходные claims."""
    token = create_access_token({"sub": "alice", "role": "employee", "org_id": 7})
    assert isinstance(token, str)
    payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "alice"
    assert payload["role"] == "employee"
    assert payload["org_id"] == 7
    assert "exp" in payload


def test_expired_token_raises_pyjwt_error():
    token = create_access_token({"sub": "bob"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    # ExpiredSignatureError is-a PyJWTError — то, что ловит get_current_user.
    with pytest.raises(pyjwt.PyJWTError):
        pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def test_invalid_signature_raises_pyjwt_error():
    token = create_access_token({"sub": "carol"})
    with pytest.raises(pyjwt.PyJWTError):
        pyjwt.decode(token, "wrong-secret-key", algorithms=[settings.ALGORITHM])


def test_non_string_sub_is_rejected():
    """requirements.txt пинит latest PyJWT (2.13.0) — с 2.10+ decode() требует
    `sub` строкой и роняет InvalidSubjectError на нестроковом значении. В этом
    проекте `sub` всегда строка (user.username, см. routers/auth.py), поэтому
    приложению эта проверка ничем не грозит — но если это когда-нибудь
    изменится (кто-то положит в sub числовой user.id), decode должен явно
    падать, а не тихо пропускать нестроковый sub дальше по коду."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = pyjwt.encode(
        {"sub": 12345, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    with pytest.raises(InvalidSubjectError):
        pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


@pytest.mark.asyncio
async def test_expired_token_401_via_app(client, test_user):
    """End-to-end: get_current_user() ловит jwt.PyJWTError и отдаёт 401,
    ровно как раньше ловил jose.JWTError."""
    token = create_access_token({"sub": test_user.username}, expires_delta=timedelta(seconds=-1))
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_200_via_app(client, test_user):
    token = create_access_token({"sub": test_user.username})
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == test_user.username


@pytest.mark.asyncio
async def test_tampered_signature_401_via_app(client, test_user):
    token = create_access_token({"sub": test_user.username})
    tampered = token[:-4] + ("0000" if not token.endswith("0000") else "1111")
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401
