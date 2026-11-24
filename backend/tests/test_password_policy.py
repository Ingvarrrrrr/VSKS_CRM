"""Тесты политики паролей (единый источник правил — app.services.password_policy).

Проверяет:
- кейсы простого пароля (123456, qwerty и т.д.)
- короткий пароль (< 8 символов)
- отсутствие букв или цифр
- совпадение с email/логином
- валидный пароль (буквы + цифры, >= 8 символов)
- HTTP 400 и человекочитаемый текст ответа API без технических префиксов
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.services.password_policy import validate_new_password, MIN_LENGTH
from app.errors import register_error_handlers


def test_validate_new_password_empty():
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("")
    assert exc_info.value.status_code == 400
    assert "не может быть пустым" in exc_info.value.detail
    assert f"не менее {MIN_LENGTH} символов" in exc_info.value.detail


def test_validate_new_password_common():
    # 123456 — частый пароль
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("123456")
    assert exc_info.value.status_code == 400
    assert "Пароль слишком простой — легко угадывается" in exc_info.value.detail
    assert "не менее 8 символов" in exc_info.value.detail
    assert "буквы и цифры" in exc_info.value.detail

    # qwerty
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("qwerty")
    assert exc_info.value.status_code == 400
    assert "Пароль слишком простой" in exc_info.value.detail


def test_validate_new_password_short():
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("Ab1!")
    assert exc_info.value.status_code == 400
    assert "Пароль слишком короткий" in exc_info.value.detail
    assert "не менее 8 символов" in exc_info.value.detail
    assert "Требуются буквы и цифры" in exc_info.value.detail


def test_validate_new_password_missing_letters():
    # Длина >= 8, но только цифры и символы (не в common)
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("9876543210!")
    assert exc_info.value.status_code == 400
    assert "отсутствуют буквы" in exc_info.value.detail
    assert "не менее 8 символов" in exc_info.value.detail


def test_validate_new_password_missing_digits():
    # Длина >= 8, но только буквы
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("SecurePassword")
    assert exc_info.value.status_code == 400
    assert "отсутствуют цифры" in exc_info.value.detail
    assert "не менее 8 символов" in exc_info.value.detail


def test_validate_new_password_matches_identifier():
    with pytest.raises(HTTPException) as exc_info:
        validate_new_password("admin@example.com", identifiers=["admin@example.com", "admin"])
    assert exc_info.value.status_code == 400
    assert "не должен совпадать с логином или email" in exc_info.value.detail


def test_validate_new_password_valid():
    # Латиница + цифры
    validate_new_password("Password123!")
    validate_new_password("testpass123")
    # Кириллица + цифры
    validate_new_password("Пароль123")
    # Со спецсимволами
    validate_new_password("S3cur3#P@ss")


class ChangePasswordDto(BaseModel):
    password: str
    username: str = "testuser"
    email: str = "test@example.com"


def test_api_password_policy_error_formatting():
    """Проверка ответа API: HTTP 400, чистый message без технических префиксов."""
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/api/test-password")
    def change_pwd(dto: ChangePasswordDto):
        validate_new_password(dto.password, identifiers=[dto.email, dto.username])
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)

    # Кейс 1: 123456
    resp = client.post("/api/test-password", json={"password": "123456"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["code"] == "HTTP_400"
    assert "Пароль слишком простой — легко угадывается" in data["message"]
    assert "не менее 8 символов" in data["message"]
    assert "Value error" not in data["message"]

    # Кейс 2: короткий пароль
    resp = client.post("/api/test-password", json={"password": "a1!"})
    assert resp.status_code == 400
    data = resp.json()
    assert "Пароль слишком короткий" in data["message"]

    # Кейс 3: валидный пароль
    resp = client.post("/api/test-password", json={"password": "Password123!"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
