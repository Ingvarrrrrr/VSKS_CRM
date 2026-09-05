"""VSKS CRM backend package.

До разрезания (Правило №5 — модульность кода) этот файл был монолитом на
2483 строки: импорты моделей, 3 фоновых asyncio-цикла, lifespan на 1400
строк (идемпотентные DDL/сиды/бэкфиллы), создание FastAPI-приложения,
exception handler'ы, include_router-блок и 5 диагностических эндпоинтов.

Всё это перенесено в модули без изменения поведения:
  - app/main.py           — создание `app`, middleware, сборка воедино
  - app/routes.py         — register_routes(app), порядок include_router 1:1
  - app/errors.py         — register_error_handlers(app), _save_incident
  - app/background/*.py   — фоновые asyncio-циклы
  - app/startup/*.py      — lifespan + идемпотентные DDL/сиды/бэкфиллы
  - app/routers/diag.py   — /api/diag/* эндпоинты

Здесь остаётся только реэкспорт `app` — docker запускает
`uvicorn app.main:app`, а тесты (conftest.py) делают `from app import app`.
"""
from .main import app

__all__ = ["app"]
