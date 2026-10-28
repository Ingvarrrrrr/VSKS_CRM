"""Список включённых адаптеров живого поиска (ПРАВИЛО №5 — каждый адаптер в
своём файле, здесь только реестр ключ → экземпляр, service.py не знает про
конкретные магазины напрямую)."""
from __future__ import annotations

from app.services.store_search.avtoall import AvtoallAdapter
from app.services.store_search.base import StoreAdapter
from app.services.store_search.chipdip import ChipdipAdapter
from app.services.store_search.emex import EmexAdapter
from app.services.store_search.ice_age import IceAgeAdapter
from app.services.store_search.kns import KnsAdapter
from app.services.store_search.kuvalda import KuvaldaAdapter
from app.services.store_search.magazin01 import Magazin01Adapter
from app.services.store_search.medtehno import MedtehnoAdapter
from app.services.store_search.promalper import PromalperAdapter
from app.services.store_search.regard import RegardAdapter
from app.services.store_search.safe import SafeAdapter
from app.services.store_search.sima_land import SimaLandAdapter

ADAPTERS: dict[str, StoreAdapter] = {
    a.key: a for a in (
        KuvaldaAdapter(),
        SafeAdapter(),
        ChipdipAdapter(),
        SimaLandAdapter(),
        Magazin01Adapter(),
        PromalperAdapter(),
        # Вторая волна (владелец, 28.10.2026):
        RegardAdapter(),
        MedtehnoAdapter(),
        IceAgeAdapter(),
        AvtoallAdapter(),
        KnsAdapter(),
        EmexAdapter(),
    )
}

# emex.ru ищет ТОЛЬКО по артикулу (см. docstring emex.py) — service.py
# проверяет это ДО похода в сеть (не на каждый обычный текстовый запрос),
# тем же признаком, что встроенный поиск по своей базе (ПРАВИЛО №6).
ARTICLE_ONLY_STORES = frozenset({"emex"})
