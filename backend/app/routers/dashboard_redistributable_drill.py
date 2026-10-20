"""GET /api/dashboard/redistributable-drill — расшифровка строк «Товары»/
«Услуги» карточки «Можно перераспределить» (владелец, 06.10.2026, доп. задача
после sleepy-fluttering-walrus.md п.1): по клику — список плановых позиций,
из которых сложилась сумма (contribution − законтрактовано, см. докстринг
app.services.redistributable_raw.not_committed_raw_rows), по образцу
dashboard_contracts_drill.py.

Под-роутер dashboard_charts.py (Правило №5): подключается там же
`router.include_router(redistributable_drill_router)` БЕЗ своего prefix —
полный путь складывается из префикса родителя "/api/dashboard" +
"/redistributable-drill" здесь.

ПРАВИЛО №6 — Σ rows["raw"] по kind ОБЯЗАНА равняться card_total =
redistributable_by_kind[kind] из app.services.subsidy_money_summary
(та же функция, что читает карточка SubsidyMoneyCards.vue) — построчная
расшифровка читает не_committed_raw_rows (ОДНО место формулы `raw`), не
считает сумму заново.

Видимость — ТЕ ЖЕ get_org_filter/get_visible_subsidy_ids, что и
/dashboard/contracts-drill для того же scope (вторая реализация видимости не
вводится)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.user import User
from app.services.redistributable_raw import not_committed_raw_rows
from app.services.subsidy_money_summary import subsidy_money_summary
from app.utils.parse_ids import parse_id_set as _parse_subsidy_ids

router = APIRouter(prefix="/redistributable-drill", tags=["dashboard"])


@router.get("")
async def dashboard_redistributable_drill(
    kind: str = Query(..., regex="^(goods|services)$"),
    scope: str = Query("managed", regex="^(dashboard|managed)$"),
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
        sid_rows = (await db.execute(select(Subsidy.id))).all()
        sid_list = [r.id for r in sid_rows]
    else:
        sid_list = list(visible_subsidy_ids)

    # Сверка с карточкой «Можно перераспределить» (НЕ второй расчёт, ПРАВИЛО
    # №6) — та же subsidy_money_summary, что читает SubsidyMoneyCards.vue.
    # Карточка СОЗНАТЕЛЬНО гасит redistributable_by_kind в None, когда у
    # субсидии feo_entered=False («ФЭО не введено», решение владельца
    # 07.10.2026, см. subsidy_money_summary.py:392-397) — окно обязано
    # повторить тот же гейт, а не показывать построчно то, что карточка
    # считает пустым (иначе Σ rows расходится с card_total — находка С3,
    # tests/behavior/REPORT.md). Поэтому строки субсидий без feo_entered
    # ЗДЕСЬ ЖЕ отбрасываются, до построения rows, а не после сверки сумм.
    summary = await subsidy_money_summary(db, sid_list)
    entered_ids = {
        sid for sid in sid_list
        if summary.get(sid, {}).get("redistributable_by_kind") is not None
    }

    rows_by_sid = await not_committed_raw_rows(db, list(entered_ids))
    rows = [
        {**row, "subsidy_id": sid}
        for sid, item_rows in rows_by_sid.items()
        for row in item_rows
        if row["kind"] == kind
    ]

    subsidy_names = {}
    sid_needed = {r["subsidy_id"] for r in rows}
    if sid_needed:
        subsidy_names = {
            s.id: s.name for s in (await db.execute(
                select(Subsidy).where(Subsidy.id.in_(sid_needed))
            )).scalars().all()
        }
    for r in rows:
        r["subsidy_name"] = subsidy_names.get(r["subsidy_id"])

    total = sum(r["raw"] for r in rows)
    card_total = sum(
        (summary.get(sid, {}).get("redistributable_by_kind") or {}).get(kind, 0.0)
        for sid in sid_list
    )

    rows.sort(key=lambda r: (r["subsidy_id"] or 0, r["category_path"], r["name"] or ""))

    return {
        "kind": kind,
        "total": total,
        "card_total": card_total,
        "rows": rows,
    }
