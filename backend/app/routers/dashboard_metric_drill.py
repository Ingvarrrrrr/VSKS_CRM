"""GET /api/dashboard/metric-drill — расшифровка строк карточек субсидии,
для которых раньше не было отдельного drill-роутера: «Заключено → ещё уйдёт
помесячно», «Можно перераспределить» (4 строки), «Оплачено», «Остаток
субсидии», «Экономия по закупкам» (план abstract-noodling-pelican.md,
15.10.2026, п.4 техчасти).

Под-роутер dashboard_charts.py (Правило №5 — по образцу dashboard_type_drill.py/
dashboard_redistributable_drill.py): подключается там же
`router.include_router(metric_drill_router)` БЕЗ своего prefix — полный путь
складывается из префикса родителя "/api/dashboard" + "/metric-drill" здесь.

Видимость — ТЕ ЖЕ get_visible_subsidy_ids/_parse_subsidy_ids, что и у
остальных drill-роутеров (dashboard_contracts_drill.py/
dashboard_redistributable_drill.py) — вторая реализация видимости не
вводится.

Сами суммы и построчные данные — app.services.metric_drill_rows (ПРАВИЛО №6,
см. её докстринг)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.metric_drill_rows import (
    METRICS,
    balance_drill,
    economy_drill,
    monthly_future_drill,
    monthly_future_not_started_drill,
    not_committed_level_drill,
    paid_drill,
)

router = APIRouter(prefix="/metric-drill", tags=["dashboard"])

_METRIC_REGEX = "^(" + "|".join(METRICS) + ")$"


def _parse_subsidy_ids(raw: Optional[str]) -> Optional[set]:
    """'1,2,3' → {1,2,3}; пусто/None → None — та же мелкая обёртка, что в
    остальных drill-роутерах."""
    if not raw:
        return None
    out: set = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out or None


@router.get("")
async def dashboard_metric_drill(
    metric: str = Query(..., regex=_METRIC_REGEX),
    scope: str = Query("managed", regex="^(dashboard|managed)$"),
    subsidy_ids: Optional[str] = Query(
        None, description="через запятую — доп. сужение ПОВЕРХ видимости scope",
    ),
    kind: Optional[str] = Query(
        None, regex="^(goods|services)$",
        description="только для paid_declared/paid_confirmed — разбивка товар/услуга",
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

    if visible_subsidy_ids is None:
        sid_rows = (await db.execute(select(Subsidy.id))).all()
        sid_list = [r.id for r in sid_rows]
    else:
        sid_list = list(visible_subsidy_ids)

    if metric == "monthly_future":
        result = await monthly_future_drill(db, sid_list)
    elif metric == "monthly_future_not_started":
        result = await monthly_future_not_started_drill(db, sid_list)
    elif metric in ("not_committed_nice", "not_committed_likely"):
        result = await not_committed_level_drill(db, sid_list, metric)
    elif metric in ("paid_declared", "paid_confirmed"):
        result = await paid_drill(db, sid_list, metric, kind=kind)
    elif metric in ("balance_marked", "balance_confirmed"):
        result = await balance_drill(db, sid_list, metric)
    elif metric == "economy":
        result = await economy_drill(db, sid_list)
    else:  # pragma: no cover — regex Query уже отсекает неизвестные значения
        raise HTTPException(status_code=400, detail=f"Неизвестная метрика: {metric}")

    return result
