"""Номер закупки/заказа «листа владельца» для одной закупки.

План .planning/quick/2026-10-06-statement-control/PLAN.md, контракт API:
GET /api/subsidies/{id}/payment-control — у purchases[] поле sheet_ref
(«номер закупки/заказа из таблицы владельца, если есть»). ПРАВИЛО №6 —
единственное место этого резолва: используется и контрольным листом
(app/services/subsidy_payment_control.py), и его экспортом в Excel
(app/services/payment_control_export.py) — второй копии не заводить.

Источник (по приоритету):
  1. Purchase.purchase_number / Purchase.order_number — штатные поля закупки;
  2. Purchase.task_comment — метка вида «Таблица: закупка X, заказ Y»,
     которую мог оставить импорт факта/ручная правка (см. контракт задачи);
     если ни штатных полей, ни метки нет — None (фронт показывает прочерк).
"""
from __future__ import annotations

import re
from typing import Optional

from app.models.purchase import Purchase

_TABLE_LABEL_RE = re.compile(r"Таблица:\s*(.+)", re.IGNORECASE)


def resolve_sheet_ref(p: Optional[Purchase]) -> Optional[str]:
    if p is None:
        return None
    parts = []
    if getattr(p, "purchase_number", None) is not None:
        parts.append(f"закупка {p.purchase_number}")
    if getattr(p, "order_number", None):
        parts.append(f"заказ {p.order_number}")
    if parts:
        return ", ".join(parts)

    comment = getattr(p, "task_comment", None)
    if comment:
        m = _TABLE_LABEL_RE.search(comment)
        if m:
            label = m.group(1).strip()
            if label:
                return label
    return None
