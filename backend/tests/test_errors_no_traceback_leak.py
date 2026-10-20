"""Аудит безопасности 2026-10-20: unhandled_exception_handler (app/errors.py)
раньше возвращал полный traceback.format_exception(...) клиенту в поле
"details" ответа 500 (пути на сервере, SQL, внутренние имена модулей).
Трейсбек должен уходить ТОЛЬКО в SystemIncident (_save_incident), клиенту —
code/message/correlation_id без details.

Изолированный FastAPI-инстанс (не трогает реальные роуты) — регистрируем
ТОЛЬКО app.errors.register_error_handlers и один роут, который гарантированно
бросает исключение, чтобы проверить именно обработчик, а не конкретный бизнес-путь.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_error_handlers


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/__boom__")
    async def boom():
        raise RuntimeError("секретная внутренняя деталь /app/backend/app/services/x.py:42")

    return app


def test_unhandled_exception_hides_traceback_from_client():
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/__boom__")

    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["details"] is None
    # Ничего из текста исключения/трейсбека не должно просочиться в сериализованный ответ.
    assert "секретная внутренняя деталь" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "services/x.py" not in resp.text
    assert set(body.keys()) == {"code", "message", "details", "correlation_id"}
