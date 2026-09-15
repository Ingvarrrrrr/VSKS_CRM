"""Единая проверка «можно ли остановить эту закупку сейчас» (ПРАВИЛО №6 —
одна формула границы, не копия в двух местах).

Используется:
  - каскадной остановкой из POST /api/wishes/{wish_id}/stop
    (app/routers/wish_transitions.py::stop_wish) — останавливает привязанные
    закупки, ещё не дошедшие до договора;
  - прямой остановкой закупки POST /api/purchases/{id}/stop
    (app/routers/purchase_stop.py).

Граница (владелец, 2026-08-13, подтверждена 2026-09-15 для прямой остановки):
обычная закупка — можно остановить, пока статус СТРОГО раньше 'contracted' по
STATUS_ORDER; рамочная (Purchase.purchase_contract_type в FRAMEWORK_TYPES) —
пока раньше 'ordered' (у рамочного договора отдельная граница: сам договор —
отдельная сущность, не по каждой закупке внутри него).
"""
from __future__ import annotations

from typing import Optional


def can_stop_purchase(p) -> tuple[bool, Optional[str]]:
    """(True, None) — закупку можно остановить сейчас.

    (False, причина) — нельзя: либо уже остановлена, либо стадия ушла дальше
    границы (текст причины — готовая строка для HTTPException.detail/тултипа).
    """
    # Ленивые импорты — избежать циклов на уровне модуля (purchases.py и
    # purchase_budget.py импортируют друг друга и другие сервисы).
    from app.routers.purchases import STATUS_ORDER
    from app.routers.purchase_budget import FRAMEWORK_TYPES
    from app.routers.purchase_transitions import STATUS_LABELS

    if getattr(p, "stopped_at", None) is not None:
        return False, "Закупка уже остановлена"

    is_framework = getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
    threshold_status = "ordered" if is_framework else "contracted"
    cur_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
    threshold_idx = STATUS_ORDER.index(threshold_status)
    if cur_idx >= threshold_idx:
        label = STATUS_LABELS.get(p.status, p.status)
        return False, f"Закупка уже на стадии «{label}» — остановить нельзя"
    return True, None
