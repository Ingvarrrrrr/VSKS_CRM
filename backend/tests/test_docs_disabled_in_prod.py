"""/docs, /redoc, /openapi.json выключаются на проде (аудит безопасности
2026-10-20). ENVIRONMENT — единственная переменная, которой прод отличается
от стенда в docker-compose.yml/config.py (Правило №6 — не завели вторую)."""
import importlib

import pytest


def _build_app(monkeypatch, environment: str):
    monkeypatch.setenv("ENVIRONMENT", environment)
    import app.config as config_module
    importlib.reload(config_module)
    import app.main as main_module
    importlib.reload(main_module)
    return main_module.app, config_module


@pytest.fixture(autouse=True)
def _restore_modules():
    yield
    # Вернуть модули в исходное состояние (ENVIRONMENT=local по умолчанию),
    # чтобы следующий тест в этом процессе не унаследовал prod-конфигурацию.
    import os
    os.environ.pop("ENVIRONMENT", None)
    import app.config as config_module
    importlib.reload(config_module)
    import app.main as main_module
    importlib.reload(main_module)


def test_docs_enabled_by_default_local(monkeypatch):
    app, _ = _build_app(monkeypatch, "local")
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"


def test_docs_disabled_in_production(monkeypatch):
    app, _ = _build_app(monkeypatch, "production")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
