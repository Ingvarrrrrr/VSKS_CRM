"""GET /api/dashboard/paid-over-delivered-drill — расшифровка плашки «Оплачено
больше, чем поставлено» (владелец, 07.10.2026, прод id=74 «ЛНР»: карточки
«Поставлено» 3 381 872,26 / «Поставлено, не оплачено» 0,00 / «Оплачено»
3 385 009,26 — оплачено больше поставленного; причина — РЕЕ-2026-03421,
status work_in_progress, оплата по отметке 3 137, договора нет).

Под-роутер dashboard_charts.py (Правило №5 — по образцу dashboard_contracts_
drill.py/dashboard_type_drill.py): подключается там же
`router.include_router(paid_over_delivered_drill_router)` БЕЗ своего prefix —
полный путь = "/api/dashboard" (родитель) + "/paid-over-delivered-drill" здесь.

Видимость — ТЕ ЖЕ get_org_filter/get_visible_subsidy_ids/_apply_purchase_org_filter,
что и остальные drill-эндпоинты дашборда (вторая реализация видимости не
вводится). Сумма строки = app.services.paid_over_delivered.paid_over_delivered_rows
(ПРАВИЛО №6 — та же функция считает и список, и сумму для сверки с картой).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.user import User
from app.routers.dashboard import _apply_purchase_org_filter
from app.routers.purchase_transitions import STATUS_LABELS
from app.services.paid_over_delivered import paid_over_delivered_by_subsidy, paid_over_delivered_rows

router = APIRouter(prefix="/paid-over-delivered-drill", tags=["dashboard"])


def _parse_subsidy_ids(raw: Optional[str]) -> Optional[set]:
    """'1,2,3' → {1,2,3}; пусто/None → None (та же мелкая обёртка, что
    dashboard_type_drill.py/dashboard_contracts_drill.py — Правило №5 не
    требует общий модуль ради 8-строчной функции без побочных эффектов)."""
    if not raw:
        return None
    out: set = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out or None


@router.get("")
async def dashboard_paid_over_delivered_drill(
    scope: str = Query(..., regex="^(dashboard|managed)$"),
    subsidy_ids: Optional[str] = Query(
        None, description="через запятую — доп. сужение ПОВЕРХ видимости scope",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    managed = scope == "managed"
    if managed:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db)
    else:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db, scope)

    narrow_ids = _parse_subsidy_ids(subsidy_ids)
    if narrow_ids is not None:
        visible_subsidy_ids = (
            visible_subsidy_ids & narrow_ids if visible_subsidy_ids is not None else narrow_ids
        )

    def _purchase_filter(q):
        return _apply_purchase_org_filter(
            q, current_user, subsidy_ids=visible_subsidy_ids, explicit_subsidy_ids=narrow_ids,
        )

    detail = await paid_over_delivered_rows(db, apply_filter=_purchase_filter, status_labels=STATUS_LABELS)

    subsidy_ids_needed = {r["subsidy_id"] for r in detail["rows"] if r.get("subsidy_id")}
    subsidy_names = {}
    if subsidy_ids_needed:
        subsidy_names = {
            s.id: s.name for s in (await db.execute(
                select(Subsidy).where(Subsidy.id.in_(subsidy_ids_needed))
            )).scalars().all()
        }
    for r in detail["rows"]:
        r["subsidy_name"] = subsidy_names.get(r.get("subsidy_id"))

    # Сверка с картой дашборда (НЕ второй расчёт — та же функция
    # paid_over_delivered_by_subsidy, что dashboard_charts.py использует для
    # карточки/widgets["paid_over_delivered"], Правило №6).
    if visible_subsidy_ids is None:
        sid_rows = (await db.execute(select(Subsidy.id))).all()
        sid_list = [r.id for r in sid_rows]
    else:
        sid_list = list(visible_subsidy_ids)
    card_map = await paid_over_delivered_by_subsidy(db, sid_list)
    card_total = sum((v.get("total", 0.0) for v in card_map.values()), 0.0)

    return {
        "scope": scope,
        "total": detail["total"],
        "card_total": card_total,
        "prepayment_total": detail["prepayment_total"],
        "purchases_count": detail["purchases_count"],
        "rows": detail["rows"],
    }
