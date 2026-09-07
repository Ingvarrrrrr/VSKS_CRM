"""Справочники закупок для фронта — единая точка чтения словарей, чьи

значения определены в app/services/dictionaries.py (Правило №6). Раньше
фронт держал собственную копию подписей (frontend/src/constants/purchaseStatus.ts),
разошедшуюся с бэкендом (пример: 'wishes' — «Желания сотрудников» на бэке vs
«Желания» на фронте). Теперь frontend/src/data/dictionaries.json генерируется
из этого эндпоинта скриптом backend/scripts/export_dictionaries.py, а
purchaseStatus.ts импортирует JSON вместо своей копии.

GET /api/dictionaries/purchase — единственный путь в этом роутере.
"""
from fastapi import APIRouter, Depends

from app.auth.jwt import get_current_user
from app.routers.purchases import STATUS_ORDER
from app.services.dictionaries import (
    STATUS_LABELS,
    SUBSTATUS_LABELS,
    CONTRACT_TYPE_LABELS,
    PURCHASE_METHOD_LABELS,
    PURCHASE_BASIS_LABELS,
)

router = APIRouter(prefix="/api/dictionaries", tags=["dictionaries"])


def _entries(labels: dict, order: list[str] | None = None) -> list[dict]:
    """[{key, label, order}] — order — позиция в предпочтительном порядке
    (STATUS_ORDER для статусов), иначе порядок вставки словаря."""
    keys = order if order is not None else list(labels.keys())
    return [{"key": k, "label": labels[k], "order": i} for i, k in enumerate(keys) if k in labels]


@router.get("/purchase")
async def get_purchase_dictionaries(_=Depends(get_current_user)):
    return {
        "statuses": _entries(STATUS_LABELS, STATUS_ORDER),
        "substatuses": _entries(SUBSTATUS_LABELS),
        "contract_types": _entries(CONTRACT_TYPE_LABELS),
        "purchase_methods": _entries(PURCHASE_METHOD_LABELS),
        "purchase_bases": _entries(PURCHASE_BASIS_LABELS),
    }
