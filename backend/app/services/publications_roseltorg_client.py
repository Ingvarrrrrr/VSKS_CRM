"""Реэкспорт клиента Росэлторг.Бизнес (ПРАВИЛО №5 — разрезан на app/services/roseltorg/:
auth.py — JWT/HTTP, items.py — позиции лота, client.py — оркестрация черновика).

Этот файл оставлен тонким, чтобы не менять существующие импорты
(app/routers/publications.py: `from app.services.publications_roseltorg_client
import _call_roseltorg`).
"""
from app.services.roseltorg.auth import (  # noqa: F401
    ROSELTORG_TOKEN,
    ROSELTORG_AUTH_URL,
    ROSELTORG_BASE_URL,
    ROSELTORG_TEMPLATE_IDS,
    get_roseltorg_jwt as _get_roseltorg_jwt,
    rb_call as _rb_call,
)
from app.services.roseltorg.client import (  # noqa: F401
    _call_roseltorg,
    publish_roseltorg_draft,
    refresh_roseltorg_status,
)
