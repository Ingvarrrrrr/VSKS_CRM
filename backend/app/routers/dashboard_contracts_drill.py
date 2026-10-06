"""GET /api/dashboard/contracts-drill — расшифровка карточки «Заключено
договоров» (владелец, 06.10.2026, план sleepy-fluttering-walrus.md, п.2): по
клику на карточку список ДОГОВОРОВ (не позиций закупок, как у type-drill) —
номер, контрагент, тип, сумма, заказано, остаток. Итог списка = карточке
(app.services.stage_cumulative.contracted_total_by_subsidy, ПРАВИЛО №6, см.
докстринг app.services.dashboard_contracts_drill за формулой каждой строки).

Под-роутер dashboard_charts.py (Правило №5 — по образцу dashboard_type_drill.py):
подключается там же `router.include_router(contracts_drill_router)` БЕЗ
своего prefix — полный путь складывается из префикса родителя "/api/dashboard"
+ "/contracts-drill" здесь.

Видимость — ТЕ ЖЕ get_org_filter/get_visible_subsidy_ids/_apply_purchase_org_filter
(точнее — тот же набор subsidy_ids, который contracted_total_by_subsidy уже
принимает в dashboard_charts.py), что и /dashboard/charts/type-drill для
того же scope — вторая реализация видимости не вводится.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.dashboard_contracts_drill import contracts_drill_rows
from app.services.stage_cumulative import contracted_total_by_subsidy

router = APIRouter(prefix="/contracts-drill", tags=["dashboard"])


def _parse_subsidy_ids(raw: Optional[str]) -> Optional[set]:
    """'1,2,3' → {1,2,3}; пусто/None → None — та же мелкая обёртка, что
    dashboard_type_drill.py::_parse_subsidy_ids (Правило №5 не требует общий
    модуль ради 8-строчной функции без побочных эффектов, но формула разбора
    идентична: trim/int/непустые)."""
    if not raw:
        return None
    out: set = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out or None


@router.get("")
async def dashboard_contracts_drill(
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

    if visible_subsidy_ids is None:
        # Видимость безлимитна (superadmin/admin без сужения) — тот же случай,
        # что dashboard_charts.py sid_list строит из ПОЛНОГО списка субсидий в
        # scope; здесь запрашиваем все id субсидий явно (contracted_total_by_subsidy
        # не умеет "все", ей нужен список).
        sid_rows = (await db.execute(select(Subsidy.id))).all()
        sid_list = [r.id for r in sid_rows]
    else:
        sid_list = list(visible_subsidy_ids)

    rows = await contracts_drill_rows(db, subsidy_ids=sid_list)

    subsidy_names = {}
    sid_needed = {r["subsidy_id"] for r in rows if r.get("subsidy_id")}
    if sid_needed:
        subsidy_names = {
            s.id: s.name for s in (await db.execute(
                select(Subsidy).where(Subsidy.id.in_(sid_needed))
            )).scalars().all()
        }
    for r in rows:
        r["subsidy_name"] = subsidy_names.get(r.get("subsidy_id"))

    total = sum(r["contract_amount"] for r in rows)
    # Сверка с картой "Заключено договоров" (не второй расчёт — читаем ТУ ЖЕ
    # функцию, что и карточка в dashboard_charts.py, ПРАВИЛО №6).
    _card_map = await contracted_total_by_subsidy(db, subsidy_ids=sid_list)
    card_total = sum(d["amount"] for d in _card_map.values())

    return {
        "scope": scope,
        "total": total,
        "card_total": card_total,
        "contracts_count": len(rows),
        "rows": rows,
    }
