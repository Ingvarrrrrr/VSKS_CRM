"""GET /api/dashboard/type-drill — расшифровка строки «товары/услуги/без
типа» карточки этапа дашборда. Повод (владелец, 2026-09-21): диалог-расшифровка
считал сумму САМ на клиенте и расходился с карточкой (План-график·товары:
карточка 24 559 275, диалог 36,7 млн; 84 закупки vs 82) — теперь сервер отдаёт
построчный разбор той же самой суммы, что показывает карточка.

Под-роутер dashboard_charts.py (Правило №5 — не раздувать сам роутер):
подключается там же `router.include_router(type_drill_router)` БЕЗ своего
prefix в вызове include_router — полный путь складывается из префикса
родителя "/api/dashboard" (dashboard_charts.router) + "/type-drill" здесь.
routes.py не трогается — dashboard_charts.router уже зарегистрирован.

Правило №6: сумма по этапу и доли по типам считает ИСКЛЮЧИТЕЛЬНО
app.services.dashboard_type_split.compute_type_split_detail — та же формула
(compute_type_split_raw/_stage_contributions/purchase_type_shares/kind_of),
что widgets[stage]/widget[stage] в GET /api/dashboard/charts?type_split=true.
Видимость — те же get_org_filter/get_visible_subsidy_ids/
_apply_purchase_org_filter, что и /dashboard/charts для того же scope.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter
from app.auth.visibility import get_visible_subsidy_ids
from app.database import get_db
from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.user import User
from app.routers.dashboard import _apply_purchase_org_filter
from app.services.dashboard_type_split import STAGE_KEYS, compute_type_split_detail

router = APIRouter(prefix="/type-drill", tags=["dashboard"])

_STAGE_REGEX = "^(" + "|".join(STAGE_KEYS) + ")$"
_KIND_REGEX = "^(goods|services|unspecified)$"


def _parse_subsidy_ids(raw: Optional[str]) -> Optional[set]:
    """'1,2,3' → {1,2,3}; пусто/None → None (без доп. сужения)."""
    if not raw:
        return None
    out: set = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return out or None


@router.get("")
async def dashboard_type_drill(
    stage: str = Query(..., regex=_STAGE_REGEX),
    kind: str = Query(..., regex=_KIND_REGEX),
    scope: str = Query(..., regex="^(dashboard|managed)$"),
    subsidy_ids: Optional[str] = Query(
        None, description="через запятую — доп. сужение ПОВЕРХ видимости scope",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_ids = get_org_filter(current_user)
    managed = scope == "managed"
    # Тот же вызов, что dashboard_charts.py::dashboard_charts для managed/dashboard
    # (Правило №6 — не переизобретать видимость).
    if managed:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db)
    else:
        visible_subsidy_ids = await get_visible_subsidy_ids(current_user, db, scope)

    # subsidy_ids — доп. сужение ПОВЕРХ уже посчитанной видимости, не замена:
    # пересечение с уже ограниченным набором, иначе (видимость безлимитна,
    # None) — сам запрошенный набор.
    narrow_ids = _parse_subsidy_ids(subsidy_ids)
    if narrow_ids is not None:
        visible_subsidy_ids = (
            visible_subsidy_ids & narrow_ids if visible_subsidy_ids is not None else narrow_ids
        )

    def _purchase_filter(q):
        return _apply_purchase_org_filter(q, current_user, subsidy_ids=visible_subsidy_ids)

    detail = await compute_type_split_detail(
        db, apply_filter=_purchase_filter, use_sids=True,
        visible_subsidy_ids=visible_subsidy_ids, org_ids=org_ids, stage=stage,
    )
    matched = [r for r in detail["rows"] if r["kind"] == kind]

    purchase_ids = {r["purchase_id"] for r in matched if r["purchase_id"] is not None}
    contract_ids = {
        r["contract_id"] for r in matched
        if r["purchase_id"] is None and r["contract_id"] is not None
    }

    purchases_map = {}
    if purchase_ids:
        purchases_map = {
            p.id: p for p in (await db.execute(
                select(Purchase).where(Purchase.id.in_(purchase_ids))
            )).scalars().all()
        }
    contracts_map = {}
    if contract_ids:
        contracts_map = {
            c.id: c for c in (await db.execute(
                select(Contract).where(Contract.id.in_(contract_ids))
            )).scalars().all()
        }

    subsidy_ids_needed = {p.subsidy_id for p in purchases_map.values() if p.subsidy_id}
    subsidy_ids_needed |= {c.subsidy_id for c in contracts_map.values() if c.subsidy_id}
    subsidy_names = {}
    if subsidy_ids_needed:
        subsidy_names = {
            s.id: s.name for s in (await db.execute(
                select(Subsidy).where(Subsidy.id.in_(subsidy_ids_needed))
            )).scalars().all()
        }

    feo_ids_needed = {p.feo_category_id for p in purchases_map.values() if p.feo_category_id}
    feo_names = {}
    if feo_ids_needed:
        feo_names = {
            f.id: f.name for f in (await db.execute(
                select(FeoCategory).where(FeoCategory.id.in_(feo_ids_needed))
            )).scalars().all()
        }

    rows_out = []
    for r in matched:
        p = purchases_map.get(r["purchase_id"]) if r["purchase_id"] is not None else None
        if p is not None:
            row_out = {
                "purchase_id": p.id,
                "purchase_number": p.purchase_number if p.purchase_number is not None else p.id,
                "subject": p.subject or "",
                "status": p.status,
                "subsidy_id": p.subsidy_id,
                "subsidy_name": subsidy_names.get(p.subsidy_id),
                "feo_category_id": p.feo_category_id,
                "feo_category_name": feo_names.get(p.feo_category_id),
            }
        else:
            # Договор (single/framework_with_amount) без единой привязанной
            # закупки — вся сумма уже "без позиции" (см. compute_type_split_detail),
            # закупки как таковой нет, показываем сам договор.
            c = contracts_map.get(r["contract_id"])
            row_out = {
                "purchase_id": None,
                "purchase_number": None,
                "subject": (c.subject if c and c.subject else None) or (f"Договор {c.number}" if c else "— (без закупки)"),
                "status": c.status if c else None,
                "subsidy_id": c.subsidy_id if c else None,
                "subsidy_name": subsidy_names.get(c.subsidy_id) if c else None,
                "feo_category_id": None,
                "feo_category_name": None,
            }
        row_out.update({
            "item_id": r["item_id"],
            "item_name": r["item_name"],
            "item_type": r["item_type"],
            "kind": r["kind"],
            "stage_amount": float(r["amount"]),
        })
        rows_out.append(row_out)

    total = sum((r["amount"] for r in matched), Decimal(0))
    purchases_count = len({r["purchase_id"] for r in matched if r["purchase_id"] is not None})

    return {
        "stage": stage,
        "kind": kind,
        "total": float(total),
        "purchases_count": purchases_count,
        "rows": rows_out,
    }
