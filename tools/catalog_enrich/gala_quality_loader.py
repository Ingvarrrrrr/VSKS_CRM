"""Загружает backend.app.services.catalog_gala.{manufacturer_quality,format,
country_names} и backend.app.services.brand_code_fold — БЕЗ запуска реальной
БД — через обычный import с backend/ в sys.path и фиктивными SECRET_KEY/
DATABASE_URL (Settings требует их на импорте, к БД при этом никто не
подключается — модели SQLAlchemy просто объявляются).

ПРАВИЛО №6: это не копия логики "неправильный производитель"/"свёртка
бренда" — единственный способ ИМПОРТИРОВАТЬ существующий код приложения для
разового обогащающего скрипта вне backend-окружения.
"""
import os
import sys
from pathlib import Path
import types

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


def _ensure_importable() -> None:
    backend_str = str(_BACKEND_DIR)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)
    # Фиктивные значения ТОЛЬКО для прохождения валидации Settings на
    # импорте — реального подключения к БД эти модули не делают.
    os.environ.setdefault("SECRET_KEY", "dummy_secret_for_offline_enrich_script_not_real")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")


def load_catalog_gala():
    """Возвращает namespace с is_bogus_manufacturer, validate_gala_catalog,
    GALA_FORMAT_NAME, GALA_FORMAT_VERSION, is_country_name, fold_brand_or_code
    — ровно тем, что определено в backend/app/services/*.py, без копирования."""
    _ensure_importable()

    from app.services.catalog_gala.country_names import is_country_name
    from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer
    from app.services.catalog_gala import format as fmt
    from app.services.brand_code_fold import fold_brand_or_code

    return types.SimpleNamespace(
        is_bogus_manufacturer=is_bogus_manufacturer,
        is_country_name=is_country_name,
        validate_gala_catalog=fmt.validate_gala_catalog,
        GALA_FORMAT_NAME=fmt.GALA_FORMAT_NAME,
        GALA_FORMAT_VERSION=fmt.GALA_FORMAT_VERSION,
        fold_brand_or_code=fold_brand_or_code,
    )
