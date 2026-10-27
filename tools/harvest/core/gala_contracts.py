"""Единственное место, которое решает, КАК импортировать format.py/stores.py/
manufacturer_quality.py/country_names.py из backend/app/services/catalog_gala
без обязательной загрузки backend/app/__init__.py (которая тянет app.main и
настройки БД — обычный `import app` в окружении сборщика без БД упадёт).
ПРАВИЛО №6 — остальные файлы tools/harvest вызывают только load_gala_contracts(),
сами в sys.modules не лезут и свою копию этих правил не заводят.

Порядок попытки:
  1. Обычный `import app.services.catalog_gala.<mod>` — сработает, если
     backend/app на PYTHONPATH и его импорт не падает (например, запущено из
     окружения, где настройки БД заданы).
  2. Если (1) не удалась (любая ошибка импорта — обычно из-за отсутствия
     настроек БД в app/__init__.py -> app/main.py) — грузим нужные
     submodule-файлы напрямую по пути через importlib, подставляя в
     sys.modules пустые объекты-пакеты "app"/"app.services"/"app.services.
     catalog_gala" (их настоящие __init__.py НЕ выполняются), чтобы
     абсолютный импорт `from app.services.catalog_gala.country_names import
     is_country_name` внутри manufacturer_quality.py нашёл уже загруженный по
     пути country_names в sys.modules, а не попытался пройти через настоящий
     app/__init__.py."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Callable, NamedTuple

_CATALOG_GALA_DIR = (
    Path(__file__).resolve().parents[3]
    / "backend" / "app" / "services" / "catalog_gala"
)


class GalaContracts(NamedTuple):
    validate_gala_catalog: Callable[[dict], list]
    GALA_FORMAT_NAME: str
    GALA_FORMAT_VERSION: int
    domain_from_url: Callable
    store_for_url: Callable
    seller_inn_for_url: Callable
    inn_checksum_valid: Callable
    is_bogus_manufacturer: Callable


def _load_by_path(dotted_name: str, filename: str) -> types.ModuleType:
    path = _CATALOG_GALA_DIR / filename
    spec = importlib.util.spec_from_file_location(dotted_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_via_fake_packages():
    for pkg_name in ("app", "app.services", "app.services.catalog_gala"):
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # помечаем как пакет; настоящий __init__.py не исполняется
            sys.modules[pkg_name] = pkg

    # country_names грузится первым — manufacturer_quality импортирует его
    # абсолютным путём и найдёт готовый модуль в sys.modules.
    _load_by_path("app.services.catalog_gala.country_names", "country_names.py")
    format_mod = _load_by_path("app.services.catalog_gala.format", "format.py")
    stores_mod = _load_by_path("app.services.catalog_gala.stores", "stores.py")
    mq_mod = _load_by_path("app.services.catalog_gala.manufacturer_quality", "manufacturer_quality.py")
    return format_mod, stores_mod, mq_mod


def load_gala_contracts() -> GalaContracts:
    """ЕДИНСТВЕННАЯ точка входа — все файлы tools/harvest вызывают только её."""
    try:
        format_mod = importlib.import_module("app.services.catalog_gala.format")
        stores_mod = importlib.import_module("app.services.catalog_gala.stores")
        mq_mod = importlib.import_module("app.services.catalog_gala.manufacturer_quality")
    except Exception:
        format_mod, stores_mod, mq_mod = _load_via_fake_packages()

    return GalaContracts(
        validate_gala_catalog=format_mod.validate_gala_catalog,
        GALA_FORMAT_NAME=format_mod.GALA_FORMAT_NAME,
        GALA_FORMAT_VERSION=format_mod.GALA_FORMAT_VERSION,
        domain_from_url=stores_mod.domain_from_url,
        store_for_url=stores_mod.store_for_url,
        seller_inn_for_url=stores_mod.seller_inn_for_url,
        inn_checksum_valid=stores_mod.inn_checksum_valid,
        is_bogus_manufacturer=mq_mod.is_bogus_manufacturer,
    )
