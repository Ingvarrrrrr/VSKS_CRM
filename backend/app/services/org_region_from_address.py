"""Organization.region заполняется САМ из юр. адреса — владелец, план
clever-bouncing-lantern.md, 🟡 правка 1: «регион показа = юр. адрес
организации». Если регион уже стоит (вручную или предыдущим вызовом) —
НЕ перетирается: ручная правка всегда важнее автоопределения.

Единственное место, которое пишет Organization.region из текста адреса —
вызывается из routers/organizations.py (создание/правка организации) и из
миграции (backfill существующих организаций). Поиск субъекта в тексте —
services/region_from_text.find_region_in_text (единственная функция такого
поиска, ПРАВИЛО №6 — не дублировать).
"""
from app.models.organization import Organization
from app.services.region_from_text import find_region_in_text


def maybe_set_org_region_from_address(org: Organization, address: str | None) -> None:
    """Пытается проставить org.region по address, если region ещё пуст."""
    if org.region:
        return
    canonical = find_region_in_text(address)
    if canonical:
        org.region = canonical
