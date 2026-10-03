"""Поиск возможных дублей закупок (та же субсидия+контрагент+сумма).

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения. Оба GET зарегистрированы в app/routes.py ДО purchases.router —
иначе Starlette матчит "/duplicate-check"/"/duplicate-groups" на catch-all
"/{pid}" (pid: int) и падает с 422, так и не доходя до этих роутов.

`duplicate_check` переведён на общий `services/purchase_similar.
find_similar_purchases` (ПРАВИЛО №6, план breezy-mixing-lovelace.md, Часть А)
— та же SQL-выборка, что и раньше (OR по total_nmck/contract_price/
payment_amount, ORDER BY id DESC LIMIT 10), без include_payment_rows (эта
ручка исторически не заглядывала в отдельные Payment.amount — поведение не
меняем) и без exclude_statuses (split не исключался и раньше)."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, distinct, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import ADMIN_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.auth.permissions import require_tab
from app.services.purchase_similar import find_similar_purchases

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


@router.get("/duplicate-check")
async def duplicate_check(
    subsidy_id: int = Query(...),
    contractor_id: int = Query(...),
    amount: float = Query(...),
    exclude_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('purchases')),
):
    """Возможные повторы: разовые закупки (НЕ ежемесячные платежи) в той же субсидии
    с тем же контрагентом и той же итоговой суммой. Ежемесячные платежи исключены
    намеренно — это повторяющиеся платежи, а не дубли."""
    matches = await find_similar_purchases(
        db,
        subsidy_id=subsidy_id,
        contractor_ids=[contractor_id],
        amount=amount,
        exclude_ids=[exclude_id] if exclude_id else None,
        limit=10,
    )
    return [
        {
            "id": m["id"],
            "purchase_number": m["purchase_number"],
            "name": m["item_name"] or m["subject"],
            "total_nmck": m["total_nmck"],
            "status": m["status"],
            "contract_date": m["contract_date"],
            "contractor_name": m["contractor_name"],
            "match_reason": m["match_reason"] or "",
        }
        for m in matches
    ]


@router.get("/duplicate-groups")
async def duplicate_groups(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('purchases')),
):
    """Батч-версия duplicate_check для всего реестра сразу (без N+1 по строкам).

    Группа = 2+ закупки с одинаковой субсидией + контрагентом + совпадающей
    суммой (round 2 знака) хотя бы по одному из total_nmck/contract_price/
    payment_amount. is_monthly_payment IS NOT TRUE — ежемесячные платежи
    намеренно НЕ считаются дублями (то же правило, что в duplicate_check выше).

    Видимость реплицирует ЕДИНСТВЕННЫЙ сценарий, которым реестр закупок
    реально пользуется: OrdersView.vue грузит список через
    `/purchases/?scope=purchases` (см. list_purchases выше, scope="purchases",
    org_id=None ветка) — get_visible_subsidy_ids(..., "purchases") для
    орг-/суб-видимости субсидий + build_visibility_clause('purchase') для
    видимости самой закупки + org-lead safety-net для assigned_user_id IS NULL
    (см. list_purchases, покрывает legacy-закупки без владельца).
    """
    base_q = select(Purchase.id).where(
        Purchase.contractor_id.isnot(None),
        Purchase.is_monthly_payment.isnot(True),
        Purchase.status != "split",
    )
    if subsidy_id:
        base_q = base_q.where(Purchase.subsidy_id == subsidy_id)

    vis = await get_visible_subsidy_ids(current_user, db, "purchases")
    if vis is not None:
        base_q = base_q.join(Subsidy, Purchase.subsidy_id == Subsidy.id).where(Subsidy.id.in_(vis))
    clause = await build_visibility_clause(current_user, db, "purchase")
    if clause is not None:
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (
            current_user.role in ADMIN_ROLES
            or (vuids is not None and len(vuids) > 1)
        )
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        base_q = base_q.where(clause)

    visible_cte = base_q.cte("dup_visible_purchases")

    # Unpivot: одна строка на (закупка × непустое поле-сумма), чтобы совпадение
    # ЛЮБОГО из трёх полей у пары закупок попало в одну группу по amount.
    amount_fields = [Purchase.total_nmck, Purchase.contract_price, Purchase.payment_amount]
    unpivot = union_all(*[
        select(
            Purchase.id.label("purchase_id"),
            Purchase.subsidy_id.label("subsidy_id"),
            Purchase.contractor_id.label("contractor_id"),
            func.round(field, 2).label("amount"),
        ).where(Purchase.id.in_(select(visible_cte.c.id)), field.isnot(None))
        for field in amount_fields
    ]).subquery("amt")

    group_q = (
        select(
            unpivot.c.subsidy_id,
            unpivot.c.contractor_id,
            unpivot.c.amount,
            func.array_agg(distinct(unpivot.c.purchase_id)).label("purchase_ids"),
        )
        .group_by(unpivot.c.subsidy_id, unpivot.c.contractor_id, unpivot.c.amount)
        .having(func.count(distinct(unpivot.c.purchase_id)) > 1)
    )
    rows = (await db.execute(group_q)).all()
    if not rows:
        return []

    # Одна и та же пара закупок может совпасть сразу по нескольким полям
    # (напр. total_nmck == contract_price у обеих) — тогда group_q вернёт
    # несколько строк с одинаковым набором purchase_ids. Схлопываем в одну
    # карточку дубликата по набору id, а не по (subsidy,contractor,amount).
    merged: dict[frozenset, dict] = {}
    for row in rows:
        ids = frozenset(int(x) for x in row.purchase_ids)
        if len(ids) < 2:
            continue
        entry = merged.setdefault(ids, {
            "subsidy_id": row.subsidy_id,
            "contractor_id": row.contractor_id,
            "amounts": set(),
        })
        entry["amounts"].add(float(row.amount))

    if not merged:
        return []

    all_ids = sorted({pid for ids in merged for pid in ids})
    contractor_ids = {e["contractor_id"] for e in merged.values()}

    purchases_r = await db.execute(
        select(
            Purchase.id, Purchase.registry_number, Purchase.purchase_number,
            Purchase.subject, Purchase.item_name, Purchase.status,
        ).where(Purchase.id.in_(all_ids))
    )
    purchase_map = {row.id: row for row in purchases_r.all()}
    contractors_r = await db.execute(
        select(Contractor.id, Contractor.name).where(Contractor.id.in_(contractor_ids))
    )
    contractor_map = {row.id: row.name for row in contractors_r.all()}

    result = []
    for ids, meta in merged.items():
        sorted_ids = sorted(ids)
        items = []
        for pid in sorted_ids:
            pr = purchase_map.get(pid)
            if not pr:
                continue
            items.append({
                "id": pid,
                "registry_number": pr.registry_number,
                "purchase_number": pr.purchase_number,
                "name": pr.subject or pr.item_name,
                "status": pr.status,
            })
        result.append({
            "key": "-".join(str(i) for i in sorted_ids),
            "subsidy_id": meta["subsidy_id"],
            "contractor_id": meta["contractor_id"],
            "contractor_name": contractor_map.get(meta["contractor_id"]),
            "amount": min(meta["amounts"]),
            "purchase_ids": sorted_ids,
            "items": items,
        })
    return result
