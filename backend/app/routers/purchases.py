import difflib
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import select, func, delete, or_, distinct, union_all
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.feo_category import FeoCategory
from app.schemas.schemas import PurchaseCreate, PurchaseOut, PurchaseOutFull, PurchaseItemOut, PurchaseFileOut, SubsidyAllocationOut
from app.models.subsidy_allocation import PurchaseSubsidyAllocation
from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id, ADMIN_ROLES, MANAGER_ROLES, ALL_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.auth.permissions import require_tab, require_action, has_org_key
from app.models.user import User
from app.models.user_org_access import UserOrgAccess
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.services.feo_plan import assert_no_unapproved_excess, assert_tz_not_over_plan, assert_tz_batch_not_over_plan, compute_feo_plan_tree
# Владелец (2026-08-12, «закупка сама становится планом»): та же логика
# автозаведения плановой позиции, что и в wishes.py, нужна и здесь — для
# закупок, созданных/меняемых в обход заявки (см. вызовы ниже в update_purchase
# и patch_purchase_item). См. app/services/plan_autoassign.py.
from app.services.plan_autoassign import auto_assign_planned_items, move_or_detach_planned_item, deactivate_if_orphaned
from app.product_matcher import find_matching_product
from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, date
from app.models.user_hierarchy import UserHierarchy
router = APIRouter(prefix="/api/purchases", tags=["purchases"])

# Phase 31: fields tracked for diff-highlighting (D-05..D-09)
PURCHASE_TRACKED_FIELDS: set[str] = {
    "subject", "contractor_id", "planned_total_price",
    "status", "subsidy_id", "contract_number", "contract_date",
}


async def _sync_purchase_from_contract(p: Purchase, db: AsyncSession):
    """Когда установлен contract_id — копируем number/date/contract_type/contractor_id из contracts в purchases.

    Поля в purchases являются денормализованным снапшотом (для list-view без JOIN),
    но при наличии FK должны строго следовать связанному контракту.

    Phase 26-lll: contractor_id ОБЯЗАТЕЛЬНО синхронизируется — иначе в реестре
    закупок колонка «Контрагент» пустая (—), хотя в договоре контрагент есть.
    """
    if not p.contract_id:
        return
    c = await db.get(Contract, p.contract_id)
    if not c:
        return
    if c.number:
        p.contract_number = c.number.strip()
    if c.date:
        p.contract_date = c.date
    if c.contract_type:
        p.purchase_contract_type = c.contract_type
    if c.contractor_id and not p.contractor_id:
        # Не перетираем уже установленного контрагента (multi-contractor сценарии),
        # только заполняем NULL.
        p.contractor_id = c.contractor_id


async def _has_purchase_write_access(user: User, db: AsyncSession) -> bool:
    """True for any authenticated user.

    Дизайн: доступ к конкретной закупке гейтится через org_filter +
    _get_visible_user_ids в list_purchases. GET /{pid} вообще без auth — кто
    смог прочесть, тот может и сохранить (autosave PATCH). Бизнес-проверки
    (статус-переходы, согласование) — отдельные эндпоинты с require_action.

    Раньше эта функция гейтила MANAGER_ROLES + user_org_access — но у юзеров
    созданных давно (до Phase 17.1) могло не быть ни role, ни UOA-row,
    ни org_id (data-issue), что приводило к 403 при autosave формы закупки.
    """
    return user is not None


async def _auto_match_feo_item(
    item_name: str,
    purchase_subsidy_id: Optional[int],
    purchase_feo_category_id: Optional[int],
    db: AsyncSession,
) -> Optional[tuple]:
    """
    Find best matching FeoPlannedItem for item_name.
    Returns (feo_planned_item_id, matched_name, confidence) or None.
    Threshold: 0.6.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC

    if not item_name:
        return None

    if purchase_feo_category_id:
        q = select(_FPI).where(
            _FPI.feo_category_id == purchase_feo_category_id,
            _FPI.is_active == True,
        )
    elif purchase_subsidy_id:
        q = (
            select(_FPI)
            .join(_FC, _FPI.feo_category_id == _FC.id)
            .where(_FC.subsidy_id == purchase_subsidy_id, _FPI.is_active == True)
        )
    else:
        return None

    candidates = (await db.execute(q)).scalars().all()
    if not candidates:
        return None

    name_lower = item_name.lower().strip()
    best_score = 0.0
    best_item = None
    for cand in candidates:
        score = difflib.SequenceMatcher(
            None, name_lower, cand.name.lower().strip()
        ).ratio()
        if score > best_score:
            best_score = score
            best_item = cand

    if best_score >= 0.6 and best_item is not None:
        return (best_item.id, best_item.name, round(best_score, 2))
    return None


async def _create_plan_graph_version(
    subsidy_id: int,
    db: AsyncSession,
    user,
    note: Optional[str] = None,
    effective_date: Optional[date] = None,
) -> bool:
    """
    Build a snapshot of all active FeoPlannedItems for the subsidy with residuals
    and save as a new PlanGraphVersion row. Increments version_number.
    schema_version=2: includes recursive FeoCategory tree with budget.
    Returns True if a new version was created, False if deduplicated.
    Caller must commit after this call.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC
    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from app.models.purchase import Purchase as _Purchase

    # Fetch all active FEO items for this subsidy
    items_q = (
        select(_FPI, _FC.id.label("cat_id"))
        .join(_FC, _FPI.feo_category_id == _FC.id)
        .where(_FC.subsidy_id == subsidy_id, _FPI.is_active == True)
        .order_by(_FPI.id)
    )
    rows = (await db.execute(items_q)).all()
    item_ids = [r[0].id for r in rows]

    # Версия строится из дерева ФЭО-категорий даже без FeoPlannedItem'ов
    # (субсидия может иметь только категории с бюджетом). Пустой рынок позиций
    # даёт пустые агрегаты, но дерево всё равно снапшотится ниже.
    used_map: dict[int, float] = {}
    used_actual_map: dict[int, float] = {}
    links_map: dict[int, list] = {}
    if item_ids:
        # Aggregate used amounts (all statuses)
        used_q = (
            select(
                PurchaseItem.feo_planned_item_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
            .group_by(PurchaseItem.feo_planned_item_id)
        )
        used_map = {
            r.feo_planned_item_id: float(r.used)
            for r in (await db.execute(used_q)).all()
        }

        # Aggregate used amounts (fact: only delivered/paid)
        used_actual_q = (
            select(
                PurchaseItem.feo_planned_item_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
            .where(
                PurchaseItem.feo_planned_item_id.in_(item_ids),
                _Purchase.status.in_(("delivered", "paid")),
            )
            .group_by(PurchaseItem.feo_planned_item_id)
        )
        used_actual_map = {
            r.feo_planned_item_id: float(r.used)
            for r in (await db.execute(used_actual_q)).all()
        }

        # Collect linked purchase ids
        links_q = (
            select(PurchaseItem.feo_planned_item_id, PurchaseItem.purchase_id)
            .where(PurchaseItem.feo_planned_item_id.in_(item_ids))
        )
        for lr in (await db.execute(links_q)).all():
            links_map.setdefault(lr.feo_planned_item_id, [])
            if lr.purchase_id not in links_map[lr.feo_planned_item_id]:
                links_map[lr.feo_planned_item_id].append(lr.purchase_id)

    snapshot_items = []
    total_planned = 0.0
    total_used = 0.0
    for r in rows:
        item = r[0]
        planned = float(item.amount or 0)
        used = used_map.get(item.id, 0.0)
        used_actual = used_actual_map.get(item.id, 0.0)
        total_planned += planned
        total_used += used
        snapshot_items.append({
            "feo_item_id": item.id,
            "name": item.name,
            "category_id": item.feo_category_id,
            "planned_amount": planned,
            "used_amount": used,
            "used_actual_amount": used_actual,
            "residual": planned - used,
            "linked_purchase_ids": links_map.get(item.id, []),
        })

    # Build FeoCategory tree for schema_version=2
    cats_q = select(_FC).where(_FC.subsidy_id == subsidy_id).order_by(_FC.id)
    all_cats = (await db.execute(cats_q)).scalars().all()

    if not rows and not all_cats:
        return False  # ни позиций, ни категорий — версионировать нечего

    # FCAT-B3: aggregate used_amount via PurchaseItem.feo_category_id for leaf nodes
    all_cat_ids = [c.id for c in all_cats]
    cat_used_map: dict[int, float] = {}
    cat_used_actual_map: dict[int, float] = {}
    if all_cat_ids:
        cat_used_q = (
            select(
                PurchaseItem.feo_category_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .where(PurchaseItem.feo_category_id.in_(all_cat_ids))
            .group_by(PurchaseItem.feo_category_id)
        )
        cat_used_map = {
            r.feo_category_id: float(r.used)
            for r in (await db.execute(cat_used_q)).all()
        }

        cat_used_actual_q = (
            select(
                PurchaseItem.feo_category_id,
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("used"),
            )
            .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
            .where(
                PurchaseItem.feo_category_id.in_(all_cat_ids),
                _Purchase.status.in_(("delivered", "paid")),
            )
            .group_by(PurchaseItem.feo_category_id)
        )
        cat_used_actual_map = {
            r.feo_category_id: float(r.used)
            for r in (await db.execute(cat_used_actual_q)).all()
        }

    def _build_tree(cats, parent_id=None):
        nodes = []
        for c in cats:
            if c.parent_id == parent_id:
                nodes.append({
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "used_amount": cat_used_map.get(c.id, 0.0),  # FCAT-B3: агрегат через feo_category_id
                    "used_actual_amount": cat_used_actual_map.get(c.id, 0.0),
                    "children": _build_tree(cats, parent_id=c.id),
                })
        return nodes

    feo_tree = _build_tree(all_cats)

    # Без FeoPlannedItem'ов план берём из бюджетов листовых категорий,
    # чтобы «Итого план» в списке редакций не было нулевым.
    if not snapshot_items:
        def _leaf_budget_sum(nodes):
            total = 0.0
            for n in nodes:
                children = n.get("children") or []
                if children:
                    total += _leaf_budget_sum(children)
                elif n.get("budget"):
                    total += float(n["budget"])
            return total
        total_planned = _leaf_budget_sum(feo_tree)

    # manual_plan_total — рекурсивно по дереву ФЭО (ручной план qty*amt или бюджет листа)
    def _node_manual_plan(n):
        own = 0.0
        qty = float(n.get("planned_quantity") or 0)
        amt = float(n.get("planned_amount") or 0)
        children = n.get("children") or []
        if qty > 0 and amt > 0:
            own = qty * amt
        elif not children and n.get("budget"):
            own = float(n["budget"])
        return own + sum(_node_manual_plan(c) for c in children)
    manual_plan_total = sum(_node_manual_plan(n) for n in feo_tree)

    # purchases_plan_total / purchases_calc_total — суммы закупок в статусах плана закупок
    _PLAN_STATUSES = ("plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid")
    purch_rows = (await db.execute(
        select(_Purchase.id, _Purchase.status, _Purchase.planned_total_price, _Purchase.total_nmck, _Purchase.nmck, _Purchase.contract_price, _Purchase.payment_amount)
        .where(_Purchase.subsidy_id == subsidy_id, _Purchase.status.in_(_PLAN_STATUSES))
    )).all()
    purchases_calc_total = 0.0
    for pr in purch_rows:
        _plan = float(pr.planned_total_price or 0) or float(pr.total_nmck or 0) or float(pr.nmck or 0)
        if pr.status in ("delivered", "paid"):
            _calc = float(pr.payment_amount or 0) or float(pr.contract_price or 0) or _plan
        else:
            _calc = _plan
        purchases_calc_total += _calc
    purchase_statuses = {str(pr.id): pr.status for pr in purch_rows}

    # purchases_plan_total — на уровне PurchaseItem (не Purchase.planned_total_price), чтобы
    # частично привязанная к плану закупка не тянула в снапшот всю свою сумму целиком, и
    # исключая позиции с feo_planned_item_id IS NOT NULL — они расходуют ручной план дерева
    # ФЭО (manual_plan_total), а не складываются с ним поверх.
    # (informational — плоская сумма по всей субсидии, без учёта дерева; для KPI-совместимой
    # величины см. total_plan_combined ниже)
    plan_item_total_q = (
        select(func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .join(_Purchase, PurchaseItem.purchase_id == _Purchase.id)
        .where(_Purchase.subsidy_id == subsidy_id)
        .where(_Purchase.status.in_(_PLAN_STATUSES))
        .where(PurchaseItem.feo_planned_item_id.is_(None))
    )
    purchases_plan_total = float((await db.execute(plan_item_total_q)).scalar() or 0)

    # total_effective = ручной план дерева ФЭО + фактические суммы закупок
    total_effective = manual_plan_total + purchases_calc_total

    # total_plan_combined — единая формула дерева ФЭО (app.services.feo_plan.
    # compute_feo_plan_tree/feo_plan_subsidy_totals), та же, что и в
    # _calculate_feo_planned_tree_bulk (subsidies.py) — единый источник KPI
    # «Запланировано». Раньше здесь была наивная сумма manual_plan_total +
    # purchases_plan_total — задваивала план, когда позиция закупки лежала
    # ОДНОВРЕМЕННО на группе и на её дочернем листе (см. docstring
    # compute_feo_plan_tree). Значение обязано совпадать с текущим KPI, иначе
    # история версий плана закупок расходится с тем, что видно на вкладке
    # «Субсидии».
    from app.services.feo_plan import feo_plan_subsidy_totals
    total_plan_combined = (await feo_plan_subsidy_totals(db, [subsidy_id])).get(subsidy_id, 0.0)

    snapshot = {
        "schema_version": 2,
        "subsidy_id": subsidy_id,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "total_planned": total_planned,
        "total_used": total_used,
        "total_effective": total_effective,
        "manual_plan_total": manual_plan_total,
        "purchases_plan_total": purchases_plan_total,
        "purchases_calc_total": purchases_calc_total,
        "total_plan_combined": total_plan_combined,
        "purchase_statuses": purchase_statuses,
        "items": snapshot_items,  # backward-compat
        "tree": feo_tree,
    }

    # Dedup: skip if identical to last version (ignoring effective_date)
    last_ver_q = (
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(1)
    )
    last_ver = (await db.execute(last_ver_q)).scalar_one_or_none()
    if last_ver is not None:
        prev_snap = {k: v for k, v in (last_ver.snapshot or {}).items() if k != "effective_date"}
        new_snap = {k: v for k, v in snapshot.items() if k != "effective_date"}
        if prev_snap == new_snap:
            return False

    # Get next version_number
    max_ver_q = select(
        func.coalesce(func.max(_PGV.version_number), 0)
    ).where(_PGV.subsidy_id == subsidy_id)
    next_ver = int((await db.execute(max_ver_q)).scalar() or 0) + 1

    pgv = _PGV(
        subsidy_id=subsidy_id,
        version_number=next_ver,
        created_by_id=getattr(user, "id", None),
        created_by_name=getattr(user, "full_name", None) or getattr(user, "username", None),
        snapshot=snapshot,
        note=note,
        effective_date=effective_date,
    )
    db.add(pgv)
    return True


# Status workflow
STATUS_ORDER = ["wishes", "plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid"]
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform", "contractor_negotiations", "contract_signing")


async def _compute_purchase_feo_excess(db: AsyncSession, purchases: list) -> dict:
    """Владелец (2026-08-12, дополнено планом crystalline-soaring-heron.md, п.4):
    «превышение плана ФЭО» по закупке(ам) — по категории, к которой отнесена сама
    закупка или хотя бы одна её позиция. Единый код для GET /api/purchases
    (список, ?with_feo_excess=true) и GET /api/purchases/{id} (карточка) — раньше
    карточка эти поля вообще не считала (только список), значок пропадал при
    открытии закупки.

    Владелец (п.4): согласованное превышение больше НЕ гасит сам факт превышения —
    feo_excess остаётся True всегда, когда план категории больше её финансирования
    по ФЭО; feo_excess_state отдельно различает «не запрошено/на согласовании/
    согласовано» (тот же PlanExcessApproval, что уже использует compute_feo_plan_tree —
    вторая копия чтения approval не заводится).

    Возвращает {purchase_id: {feo_excess, feo_excess_hint, feo_excess_amount,
    feo_excess_category, feo_excess_state, feo_excess_approved_by,
    feo_excess_approved_at}} — на КАЖДУЮ закупку из `purchases` (нули/None/"none",
    если превышения нет или у закупки вовсе нет субсидии/категории).
    `purchases` обязаны иметь загруженные `.items` (selectinload/joinedload) — по
    ним ищется категория-виновник, если сама закупка без feo_category_id.
    """
    _empty = {
        "feo_excess": False, "feo_excess_hint": None, "feo_excess_amount": None,
        "feo_excess_category": None, "feo_excess_state": "none",
        "feo_excess_approved_by": None, "feo_excess_approved_at": None,
    }
    result: dict = {p.id: dict(_empty) for p in purchases}
    subsidy_ids = list({p.subsidy_id for p in purchases if p.subsidy_id})
    if not subsidy_ids:
        return result

    tree = await compute_feo_plan_tree(db, subsidy_ids)
    bad_cats = {
        cid: node for cid, node in (tree or {}).items()
        if (node.get("excess_over_feo") or node.get("excess_amount") or 0.0) > 0.005
    }
    if not bad_cats:
        return result

    names_r = await db.execute(
        select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(bad_cats.keys()))
    )
    cat_names = {row[0]: row[1] for row in names_r.all()}

    for p in purchases:
        cat_ids = {it.feo_category_id for it in (p.items or []) if it.feo_category_id}
        if p.feo_category_id:
            cat_ids.add(p.feo_category_id)
        hit_cid = next((cid for cid in cat_ids if cid in bad_cats), None)
        if hit_cid is None:
            continue
        node = bad_cats[hit_cid]
        excess = float(node.get("excess_over_feo") or node.get("excess_amount") or 0.0)
        name = cat_names.get(hit_cid, f"#{hit_cid}")
        if node.get("excess_approved"):
            state = "approved"
        elif node.get("excess_pending"):
            state = "pending"
        else:
            state = "not_requested"
        result[p.id] = {
            "feo_excess": True,
            "feo_excess_hint": f"Категория «{name}»: план превышает ФЭО на {excess:,.2f} ₽",
            "feo_excess_amount": excess,
            "feo_excess_category": name,
            "feo_excess_state": state,
            "feo_excess_approved_by": node.get("excess_approval_by_name"),
            "feo_excess_approved_at": node.get("excess_approval_at"),
        }
    return result


def _item_to_out(item: PurchaseItem, plan_residual=None, plan_planned_amount=None) -> PurchaseItemOut:
    product_name = None
    product_photo_url = None
    product_description = None
    product_description_44fz = None
    if item.product:
        product_name = item.product.name
        product_photo_url = item.product.photo_url
        product_description = item.product.description
        product_description_44fz = item.product.description_44fz
    return PurchaseItemOut(
        id=item.id,
        product_id=item.product_id,
        item_name=item.item_name,
        item_type=item.item_type,
        quantity=item.quantity,
        unit=item.unit,
        unit_price=item.unit_price,
        total_price=item.total_price,
        final_unit_price=item.final_unit_price,
        final_total=item.final_total,
        # Снимок плана (Шаг 1 «план ≠ факт») — отдаём фронту вместе с текущей ценой,
        # иначе дерево ФЭО/панели план-vs-факт (Шаг 5) не смогут отличить план от ТЗ.
        planned_quantity=getattr(item, 'planned_quantity', None),
        planned_unit_price=getattr(item, 'planned_unit_price', None),
        planned_total=getattr(item, 'planned_total', None),
        country_origin=item.country_origin,
        # Phase 26-V/W/BB: contractor + match + receipt linkage — критично для UI
        contractor_id=item.contractor_id,
        contractor_inn=item.contractor_inn,
        contractor_name=item.contractor_name,
        match_confirmed=item.match_confirmed if item.match_confirmed is not None else True,
        receipt_id=getattr(item, 'receipt_id', None),
        vat_rate=getattr(item, 'vat_rate', None),
        vat_amount=getattr(item, 'vat_amount', None),
        total_with_vat=getattr(item, 'total_with_vat', None),
        feo_planned_item_id=getattr(item, 'feo_planned_item_id', None),
        feo_category_id=getattr(item, 'feo_category_id', None),
        over_plan=getattr(item, 'over_plan', False) or False,
        needed_date=getattr(item, 'needed_date', None),
        accepted_name=getattr(item, 'accepted_name', None),
        accepted_quantity=getattr(item, 'accepted_quantity', None),
        accepted_unit=getattr(item, 'accepted_unit', None),
        product_name=product_name,
        product_photo_url=product_photo_url,
        product_description=product_description,
        product_description_44fz=product_description_44fz,
        plan_residual=plan_residual,
        plan_planned_amount=plan_planned_amount,
    )


def _purchase_to_full(
    p: Purchase, contractors: dict, subsidies: dict, allocations: list | None = None,
    contractor_inns: dict | None = None, receipt_map: dict | None = None, ru_map: dict | None = None,
    su_map: dict | None = None, feo_excess_map: dict | None = None, item_plan_map: dict | None = None,
    wish_title_map: dict | None = None, wish_status_map: dict | None = None,
) -> PurchaseOutFull:
    data = {c.name: getattr(p, c.name) for c in Purchase.__table__.columns}
    _ipm = item_plan_map or {}
    items = [
        _item_to_out(i, *(_ipm.get(i.id) or (None, None)))
        for i in (p.items or [])
    ]
    files = [
        PurchaseFileOut(
            id=f.id,
            purchase_id=f.purchase_id,
            filename=f.filename,
            mime_type=f.mime_type,
            size=f.size,
            file_type=f.file_type,
            doc_format=f.doc_format,
            is_active=f.is_active if f.is_active is not None else True,
            content_hash=f.content_hash,
            uploaded_by_id=f.uploaded_by_id,
            created_at=str(f.created_at) if f.created_at else None,
        )
        for f in (p.files or [])
    ]
    alloc_out = None
    if allocations is not None:
        alloc_out = [
            SubsidyAllocationOut(
                id=a.id,
                subsidy_id=a.subsidy_id,
                subsidy_name=a.subsidy.name if a.subsidy else subsidies.get(a.subsidy_id),
                amount=a.amount,
            )
            for a in allocations
        ]
    # Multi-contractor label for advance reports
    multi_contractor_label: str | None = None
    if p.purchase_method == 'advance' and p.items:
        unique_names = {item.contractor_name for item in p.items if item.contractor_name}
        if len(unique_names) > 1:
            multi_contractor_label = "Множественный контрагент"
        elif len(unique_names) == 1:
            multi_contractor_label = next(iter(unique_names))

    _excess = (feo_excess_map or {}).get(p.id) or {}
    return PurchaseOutFull(
        **data,
        items=items,
        files=files,
        files_count=len(files),
        contractor_name=contractors.get(p.contractor_id),
        contractor_inn=(contractor_inns or {}).get(p.contractor_id),
        feo_category_name=p.feo_category.name if p.feo_category else None,
        subsidy_name=subsidies.get(p.subsidy_id),
        event_name=p.event.name if p.event else None,
        subsidy_allocations=alloc_out,
        last_receipt_date=(receipt_map or {}).get(p.id),
        reimbursement_user_name=(ru_map or {}).get(p.reimbursement_user_id),
        multi_contractor_label=multi_contractor_label,
        # Остановка закупки (владелец, 2026-08-13) — имя того, кто остановил
        # (см. Wish._enrich stopped_by_name: тот же приём — full_name или username).
        stopped_by_name=(su_map or {}).get(p.stopped_by),
        # Превышение плана ФЭО (план crystalline-soaring-heron.md, п.4) — см.
        # _compute_purchase_feo_excess; пусто (feo_excess=False), если карта не
        # передана (вызывающий не просил ?with_feo_excess) или превышения нет.
        feo_excess=_excess.get("feo_excess", False),
        feo_excess_hint=_excess.get("feo_excess_hint"),
        feo_excess_amount=_excess.get("feo_excess_amount"),
        feo_excess_category=_excess.get("feo_excess_category"),
        feo_excess_state=_excess.get("feo_excess_state", "none"),
        feo_excess_approved_by=_excess.get("feo_excess_approved_by"),
        feo_excess_approved_at=_excess.get("feo_excess_approved_at"),
        # Родительская заявка (план crystalline-soaring-heron.md, п.3) — «Создана
        # из заявки №N «…»» на карточке закупки.
        wish_title=(wish_title_map or {}).get(p.wish_id) if p.wish_id else None,
        # Статус заявки — карточке закупки в статусе 'wishes' нужно объяснить,
        # ждёт она одобрения или отцеплена (владелец, 2026-08-21, дефект 1).
        wish_status=(wish_status_map or {}).get(p.wish_id) if p.wish_id else None,
    )


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
    from decimal import ROUND_HALF_UP
    amt = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    stmt = (
        select(Purchase)
        .where(
            Purchase.subsidy_id == subsidy_id,
            Purchase.contractor_id == contractor_id,
            Purchase.is_monthly_payment.isnot(True),
            or_(
                func.round(func.coalesce(Purchase.total_nmck, 0), 2) == amt,
                func.round(func.coalesce(Purchase.contract_price, 0), 2) == amt,
                func.round(func.coalesce(Purchase.payment_amount, 0), 2) == amt,
            ),
        )
        .options(selectinload(Purchase.contractor))
        .order_by(Purchase.id.desc())
        .limit(10)
    )
    if exclude_id:
        stmt = stmt.where(Purchase.id != exclude_id)
    rows = (await db.execute(stmt)).scalars().all()

    def _dup_reason(p):
        fa = float(amt)
        if p.total_nmck is not None and round(float(p.total_nmck), 2) == fa:
            return "НМЦК"
        if p.contract_price is not None and round(float(p.contract_price), 2) == fa:
            return "цена договора"
        if p.payment_amount is not None and round(float(p.payment_amount), 2) == fa:
            return "платёж"
        return ""

    return [
        {
            "id": p.id,
            "purchase_number": p.purchase_number,
            "name": p.item_name or p.subject,
            "total_nmck": float(p.total_nmck) if p.total_nmck is not None else None,
            "status": p.status,
            "contract_date": p.contract_date.isoformat() if p.contract_date else None,
            "contractor_name": p.contractor.name if p.contractor else None,
            "match_reason": _dup_reason(p),
        }
        for p in rows
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


@router.get("/responsible-persons")
async def list_responsible_persons(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Уникальные ответственные исполнители из закупок (для выпадающего списка)."""
    q = select(Purchase.responsible_person).where(Purchase.responsible_person.isnot(None))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    q = q.distinct().order_by(Purchase.responsible_person)
    result = await db.execute(q)
    return [row[0] for row in result.fetchall()]


@router.get("/", response_model=List[PurchaseOutFull])
async def list_purchases(
    contract_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    org_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    purchase_basis: Optional[str] = Query(None),
    framework_seq: Optional[int] = Query(None),
    vehicle_id: Optional[int] = Query(None),
    wish_id: Optional[int] = Query(None),
    limit: Optional[int] = Query(None),
    scope: Optional[str] = Query(None),
    with_feo_excess: bool = Query(
        False,
        description=(
            "Владелец (2026-08-12): значок «закупка создаёт превышение плана ФЭО» — "
            "считается ОПЦИОНАЛЬНО (compute_feo_plan_tree по субсидиям видимой страницы, "
            "не N+1, но заметно тяжелее обычного списка), фронт запрашивает явно."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
        selectinload(Purchase.items).selectinload(PurchaseItem.product),
        selectinload(Purchase.files),
        selectinload(Purchase.event),
    )
    org_ids = get_org_filter(current_user)
    # #8: явный grant субсидии (user_subsidy_access) расширяет org-фильтр —
    # пользователь видит закупки субсидии вне своего контура.
    from app.models.user_subsidy_access import UserSubsidyAccess
    granted_ids = set((await db.execute(
        select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == current_user.id)
    )).scalars().all())
    _SCOPED_TABS = {"purchases", "advance_reports", "service_notes"}
    needs_subsidy_join = org_ids is not None or org_id is not None
    if scope is not None and scope in _SCOPED_TABS and org_id is None:
        # Двухуровневая видимость по конкретной вкладке (purchases / advance_reports / service_notes).
        vis = await get_visible_subsidy_ids(current_user, db, scope)
        if vis is not None:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            q = q.where(Subsidy.id.in_(vis))
    else:
        if needs_subsidy_join:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            if org_id is not None:
                # Explicit org filter takes precedence; still validate user has access to this org
                if org_ids is not None and org_id not in org_ids:
                    return []
                q = q.where(Subsidy.org_id == org_id)
            elif org_ids is not None:
                q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))
    # Phase 28: unified visibility helper.
    # — build_visibility_clause возвращает None для SaaS-ролей (фильтр не нужен),
    #   иначе or_() с правилами 1-5 (иерархия + участие).
    clause = await build_visibility_clause(current_user, db, 'purchase')
    if clause is not None:
        # Safety-net: для org-lead'ов всё ещё пропускаем закупки с
        # assigned_user_id IS NULL — на проде осталась 1 legacy-закупка
        # (id 779 без subsidy_id), будет удалена после ручного triage.
        # Org-lead = admin/account_owner ИЛИ есть head/managed dept/org/UOA.
        # Используем visible_user_ids: если size > 1 → user управляет ≥1 чел.
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (
            current_user.role in ADMIN_ROLES
            or (vuids is not None and len(vuids) > 1)
        )
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        q = q.where(clause)
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        # Фильтр по всему поддереву: закупки часто привязаны к дочерним категориям
        from app.routers.feo_categories import _collect_subtree_ids
        _sub_ids = await _collect_subtree_ids(feo_category_id, db)
        q = q.where(Purchase.feo_category_id.in_(_sub_ids))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        # Обратная совместимость: confirmed упразднён, маппируем в work_in_progress
        if status == "confirmed":
            status = "work_in_progress"
        q = q.where(Purchase.status == status)
    if purchase_method:
        q = q.where(Purchase.purchase_method == purchase_method)
    if purchase_basis:
        q = q.where(Purchase.purchase_basis == purchase_basis)
    if framework_seq is not None:
        q = q.where(Purchase.framework_seq == framework_seq)
    if vehicle_id is not None:
        q = q.where(Purchase.vehicle_id == vehicle_id)
    if wish_id is not None:
        q = q.where(Purchase.wish_id == wish_id)
    # Hide purchases that were split into children unless explicitly requested
    if status != "split":
        q = q.where(Purchase.status != "split")
    # Владелец (2026-08-21, дефект «отцеплённая закупка»): скрытые закупки
    # (status='wishes' — ещё не прошли гейт одобрения заявки ИЛИ принудительно
    # возвращены обратно через force_wish_status/_withdraw_wish_from_plan) не
    # должны попадать в реестр закупок — план они не расходуют, «не в работе»
    # (см. wishes.py._withdraw_wish_from_plan). Ограничено scope="purchases" —
    # ЕДИНСТВЕННЫЙ сценарий, которым пользуется реестр (OrdersView.vue грузит
    # /purchases/?scope=purchases, см. docstring duplicate_groups выше). Другие
    # места, где 'wishes' показывается НАМЕРЕННО (my-tasks/kanban «Желания
    # сотрудников», PlanView.vue scope=plan со справочным draft-чипом,
    # purchase_export.py, dashboard-виджеты), используют другие
    # запросы/scope и этим фильтром не затрагиваются. Явный status=wishes
    # запрос выполняем как есть (задан пользователем).
    if scope == "purchases" and status != "wishes":
        q = q.where(Purchase.status != "wishes")
    if search:
        like = f"%{search}%"
        from sqlalchemy import cast, String as SAString
        search_filters = [
            Purchase.item_name.ilike(like),
            Purchase.subject.ilike(like),
            Purchase.registry_number.ilike(like),
            Purchase.contract_number.ilike(like),
            Purchase.order_number.ilike(like),
        ]
        # Search by purchase_number if numeric
        if search.strip().isdigit():
            search_filters.append(Purchase.purchase_number == int(search.strip()))
        q = q.where(or_(*search_filters))
    q = q.order_by(Purchase.id.desc())
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors_list = contractors_r.scalars().all()
    contractors = {c.id: c.name for c in contractors_list}
    contractor_inns = {c.id: c.inn for c in contractors_list}
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}

    # Batch-fetch reimbursement user names
    ru_ids = [p.reimbursement_user_id for p in purchases if p.reimbursement_user_id]
    ru_map: dict = {}
    if ru_ids:
        res = await db.execute(select(User.id, User.full_name).where(User.id.in_(ru_ids)))
        ru_map = {uid: name for uid, name in res.all()}

    # Остановка закупки (владелец, 2026-08-13): batch-fetch имён остановивших
    # (full_name или username, как для остальных «кто сделал» полей) — одним
    # запросом на всю страницу, без N+1.
    su_ids = [p.stopped_by for p in purchases if p.stopped_by]
    su_map: dict = {}
    if su_ids:
        res = await db.execute(select(User.id, User.full_name, User.username).where(User.id.in_(su_ids)))
        su_map = {uid: (fn or un) for uid, fn, un in res.all()}

    # Batch-fetch last receipt date for advance purchases
    from app.models.purchase_receipt import PurchaseReceipt
    adv_ids = [p.id for p in purchases if p.purchase_method == 'advance']
    receipt_map: dict = {}
    if adv_ids:
        res = await db.execute(
            select(PurchaseReceipt.purchase_id, func.max(PurchaseReceipt.receipt_datetime))
            .where(PurchaseReceipt.purchase_id.in_(adv_ids))
            .group_by(PurchaseReceipt.purchase_id)
        )
        receipt_map = {pid: dt for pid, dt in res.all()}

    # phase26-m: batch-load framework_contract_total (max_amount or SUM(contract_price))
    framework_contract_ids = {
        p.contract_id for p in purchases
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount')
    }
    display_total_by_contract: dict = {}
    if framework_contract_ids:
        contracts_r = await db.execute(
            select(Contract.id, Contract.max_amount).where(Contract.id.in_(framework_contract_ids))
        )
        contracts_by_id = {row[0]: row[1] for row in contracts_r.all()}
        for cid in framework_contract_ids:
            max_amount = contracts_by_id.get(cid)
            if max_amount is not None:
                display_total_by_contract[cid] = max_amount
            else:
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(func.coalesce(
                        Purchase.contract_price,
                        Purchase.planned_total_price,
                        Purchase.total_nmck,
                        Decimal("0"),
                    )), Decimal("0"))).where(Purchase.contract_id == cid)
                )
                display_total_by_contract[cid] = sum_r.scalar() or Decimal("0")

    # Phase 31: batch unseen_fields/unseen_changes_count (2 queries, no N+1) (D-05..D-09)
    purchase_ids = [p.id for p in purchases]
    unseen_map: dict[int, list[str]] = {}
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        unseen_map = await _get_unseen_map(db, 'purchase', purchase_ids, current_user.id)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen purchase map failed: %s", _exc)

    # Phase 31-04: batch contract_conflict — 1 query for all linked contracts (no N+1)
    linked_contract_ids = {p.contract_id for p in purchases if p.contract_id}
    contract_data_map: dict[int, tuple] = {}  # contract_id -> (number, date)
    if linked_contract_ids:
        _cr = await db.execute(
            select(Contract.id, Contract.number, Contract.date).where(Contract.id.in_(linked_contract_ids))
        )
        contract_data_map = {row[0]: (row[1], row[2]) for row in _cr.all()}

    # Владелец (2026-08-12): значок «закупка создаёт превышение плана ФЭО» — опционален
    # (?with_feo_excess=true), считается ОДНИМ вызовом compute_feo_plan_tree на все субсидии
    # видимой страницы (не N+1), без новых колонок в БД. Общий код с GET /{id} — см.
    # _compute_purchase_feo_excess (план crystalline-soaring-heron.md, п.4).
    _feo_excess_map: dict = {}
    if with_feo_excess and purchases:
        _feo_excess_map = await _compute_purchase_feo_excess(db, purchases)

    result_rows = []
    for p in purchases:
        out = _purchase_to_full(
            p, contractors, subsidies, contractor_inns=contractor_inns, receipt_map=receipt_map,
            ru_map=ru_map, su_map=su_map, feo_excess_map=_feo_excess_map,
        )
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
            out.framework_contract_total = display_total_by_contract.get(p.contract_id)
        _unseen = unseen_map.get(p.id, [])
        out.unseen_fields = _unseen
        out.unseen_changes_count = len(_unseen)
        # contract_conflict: purchase has linked contract but copy of number/date doesn't match
        if p.contract_id and p.contract_id in contract_data_map:
            c_number, c_date = contract_data_map[p.contract_id]
            out.contract_conflict = (
                (c_number is not None and p.contract_number != c_number)
                or (c_date is not None and p.contract_date != c_date)
            )
        result_rows.append(out)
    return result_rows


@router.get("/my-tasks")
async def my_tasks(
    include_archive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kanban: purchases assigned to current user."""
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
    ).where(Purchase.assigned_user_id == current_user.id)
    if not include_archive:
        q = q.where(Purchase.status != "paid")
    q = q.order_by(Purchase.execution_term.asc().nulls_last(), Purchase.id.desc())
    result = await db.execute(q)
    purchases = result.scalars().all()
    return [
        {
            "id": p.id, "subject": p.subject or p.item_name or "",
            "status": p.status, "purchase_number": p.purchase_number,
            "registry_number": p.registry_number,
            "execution_term": str(p.execution_term) if p.execution_term else None,
            "delivery_date": str(p.delivery_date) if p.delivery_date else None,
            "planned_total_price": float(p.planned_total_price or 0),
            "contract_price": float(p.contract_price or 0),
            "contractor_name": p.contractor.name if p.contractor else None,
            "feo_category_name": p.feo_category.name if p.feo_category else None,
            "task_comment": p.task_comment,
            "subsidy_id": p.subsidy_id,
        }
        for p in purchases
    ]


@router.get("/kanban-all")
async def kanban_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kanban: all purchases grouped by assigned user (for managers/admins)."""
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
    ).where(Purchase.assigned_user_id.isnot(None))
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id).where(Subsidy.org_id.in_(org_ids))
    q = q.order_by(Purchase.assigned_user_id, Purchase.execution_term.asc().nulls_last())
    result = await db.execute(q)
    purchases = result.scalars().all()

    # Group by user
    users_result = await db.execute(select(User))  # superadmin-bypass-ok: internal enrichment map by ID, not a user-list endpoint
    users_map = {u.id: u.full_name or u.username for u in users_result.scalars().all()}

    grouped = {}
    for p in purchases:
        uid = p.assigned_user_id
        if uid not in grouped:
            grouped[uid] = {"user_id": uid, "user_name": users_map.get(uid, f"User #{uid}"), "tasks": []}
        grouped[uid]["tasks"].append({
            "id": p.id, "subject": p.subject or p.item_name or "",
            "status": p.status, "purchase_number": p.purchase_number,
            "execution_term": str(p.execution_term) if p.execution_term else None,
            "contractor_name": p.contractor.name if p.contractor else None,
            "planned_total_price": float(p.planned_total_price or 0),
            "task_comment": p.task_comment,
        })
    return list(grouped.values())


@router.get("/{pid}/kp-items")
async def get_purchase_kp_items(pid: int, db: AsyncSession = Depends(get_db)):
    """Items in a purchase with product category info for КП smart sending."""
    from app.models.purchase_item import PurchaseItem
    from app.models.product import Product

    stmt = (
        select(
            PurchaseItem.id,
            PurchaseItem.item_name,
            PurchaseItem.quantity,
            PurchaseItem.unit,
            PurchaseItem.unit_price,
            Product.name.label("product_name"),
            Product.category.label("product_category"),
        )
        .outerjoin(Product, Product.id == PurchaseItem.product_id)
        .where(PurchaseItem.purchase_id == pid)
        .order_by(PurchaseItem.id)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "item_name": r.product_name or r.item_name,
            "quantity": float(r.quantity or 0),
            "unit": r.unit or "шт.",
            "unit_price": float(r.unit_price or 0),
            "category": r.product_category or None,
        }
        for r in rows
    ]


# Третья очередь плана (`synchronous-knitting-thacker.md`), Этапы 4-5:
# эти два GET обязаны быть объявлены ДО общего "/{pid}" ниже — иначе Starlette
# матчит "/payment-groups"/"/payment-candidates" на "/{pid}" (pid: int) и падает
# с 422 «ожидается целое число», так и не доходя до нужного роута. POST-версии
# (attach-payments, match-payments) этой проблемы не имеют — совпадающего по
# методу и глубине пути "/{pid}" на POST нет — и остаются в конце файла рядом
# со своими помощниками (_get_subsidy_for_payments и т.д.).
@router.get("/payment-groups")
async def list_payment_groups(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Группы оплаты по закупкам субсидии (Этап 4) + отчёт «подозрительные
    дубли», которые в группировку не попали — их надо разобрать вручную сначала."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import build_groups, suspicious_groups

    groups = await build_groups(db, subsidy_id)
    susp = await suspicious_groups(db, subsidy_id=subsidy_id)
    return {
        "groups": [_payment_group_to_dict(g) for g in groups],
        "suspicious": [_suspicious_group_to_dict(s) for s in susp],
    }


@router.get("/payment-candidates")
async def list_payment_candidates(
    subsidy_id: int = Query(...),
    group_key: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Кандидаты-платежи для одной группы (Этап 5), раздельно по товарной и
    сервисной сумме — см. app/services/payment_lookup.py::find_candidates."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import find_group
    from app.services.payment_lookup import find_candidates

    group = await find_group(db, subsidy_id, group_key)
    if not group:
        raise HTTPException(404, "Группа не найдена — пересчитайте /api/purchases/payment-groups")

    cands = await find_candidates(db, group)
    return {
        "goods": [_payment_candidate_to_dict(c) for c in cands["goods"]],
        "services": [_payment_candidate_to_dict(c) for c in cands["services"]],
    }


@router.get("/{pid}/payment-candidates")
async def list_purchase_payment_candidates(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Тонкая обёртка над /payment-candidates (Этап 7б) для карточки закупки —
    кнопка «Найти платежи в реестре» в PaymentsBlock.vue: находит группу
    (см. app/services/payment_target.py::build_groups), содержащую ЭТУ закупку,
    без явного group_key, и отдаёт кандидатов, как и общий эндпоинт."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not p.subsidy_id:
        return {"group": None, "goods": [], "services": [], "reason": "у закупки не указана субсидия"}
    await _get_subsidy_for_payments(p.subsidy_id, db, current_user)
    from app.services.payment_target import build_groups
    from app.services.payment_lookup import find_candidates

    groups = await build_groups(db, p.subsidy_id)
    group = next((g for g in groups if pid in g.purchase_ids), None)
    if not group:
        return {
            "group": None, "goods": [], "services": [],
            "reason": "закупка не входит ни в одну группу оплаты — либо у неё нет "
                      "реестрового номера, либо она попала в «подозрительные дубли» "
                      "(см. /api/purchases/payment-groups) и требует ручного разбора",
        }
    cands = await find_candidates(db, group)
    return {
        "group": _payment_group_to_dict(group),
        "goods": [_payment_candidate_to_dict(c) for c in cands["goods"]],
        "services": [_payment_candidate_to_dict(c) for c in cands["services"]],
    }


@router.get("/{pid}", response_model=PurchaseOutFull)
async def get_purchase(pid: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
            selectinload(Purchase.reimbursement_user),
            selectinload(Purchase.stopped_by_user),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")

    # Phase 26-Z-bootstrap: для advance закупок — silent idempotent recompute если
    # есть чеки и items с NULL contractor_id ИЛИ receipts без записи в acceptance_docs.
    if p.purchase_method == 'advance':
        try:
            from sqlalchemy import select as _sel
            from app.models.purchase_receipt import PurchaseReceipt as _PR
            from app.models.purchase_item import PurchaseItem as _PI
            receipts_count = (await db.execute(
                _sel(func.count(_PR.id)).where(_PR.purchase_id == pid)
            )).scalar() or 0
            if receipts_count > 0:
                null_items_count = (await db.execute(
                    _sel(func.count(_PI.id)).where(
                        _PI.purchase_id == pid,
                        _PI.contractor_id.is_(None),
                    )
                )).scalar() or 0
                current_docs = p.acceptance_docs or []
                receipt_ids_in_docs = {d.get("receipt_id") for d in current_docs if isinstance(d, dict) and d.get("receipt_id")}
                receipt_ids_actual = set((await db.execute(
                    _sel(_PR.id).where(_PR.purchase_id == pid)
                )).scalars().all())
                # Mismatch detection: позиция привязана к чеку, но контрагент не из этого чека
                mismatch_count = 0
                linked_items_q = await db.execute(
                    _sel(_PI).where(
                        _PI.purchase_id == pid,
                        _PI.receipt_id.is_not(None),
                    )
                )
                for _it in linked_items_q.scalars().all():
                    _r = await db.get(_PR, _it.receipt_id)
                    if not _r or not _r.seller_inn:
                        continue
                    if _it.contractor_inn != _r.seller_inn:
                        mismatch_count += 1
                        break  # достаточно одного для триггера
                # Phase 26-DD: receipts с raw_json items, но 0 PurchaseItem с этими receipt_id
                from app.routers.purchase_receipts import _extract_items as _ext_items
                orphan_receipts = 0
                if receipt_ids_actual:
                    for _rid in receipt_ids_actual:
                        _r = await db.get(_PR, _rid)
                        if not _r:
                            continue
                        _has_items = (await db.execute(
                            _sel(func.count(_PI.id)).where(_PI.receipt_id == _rid)
                        )).scalar() or 0
                        if _has_items == 0:
                            _raw_items = _ext_items(_r.raw_json or {})
                            if _raw_items:
                                orphan_receipts += 1
                                break
                need_recompute = bool(null_items_count) or bool(receipt_ids_actual - receipt_ids_in_docs) or bool(mismatch_count) or bool(orphan_receipts)
                if need_recompute:
                    from app.routers.purchase_receipts import _recompute_from_receipts_core
                    await _recompute_from_receipts_core(pid, db)
                    # Re-fetch p после recompute с теми же relationships
                    result = await db.execute(
                        select(Purchase)
                        .options(
                            selectinload(Purchase.contractor),
                            selectinload(Purchase.feo_category),
                            selectinload(Purchase.items).selectinload(PurchaseItem.product),
                            selectinload(Purchase.files),
                            selectinload(Purchase.event),
                            selectinload(Purchase.reimbursement_user),
                        )
                        .where(Purchase.id == pid)
                    )
                    p = result.scalar_one()
        except Exception as _re:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"auto-recompute on GET /purchases/{pid} skipped: {_re}")

    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    alloc_r = await db.execute(
        select(PurchaseSubsidyAllocation)
        .options(selectinload(PurchaseSubsidyAllocation.subsidy))
        .where(PurchaseSubsidyAllocation.purchase_id == pid)
    )
    allocations = alloc_r.scalars().all()
    single_ru_map: dict = {}
    if p.reimbursement_user_id and p.reimbursement_user:
        single_ru_map = {p.reimbursement_user_id: p.reimbursement_user.full_name}
    single_su_map: dict = {}
    if p.stopped_by and p.stopped_by_user:
        single_su_map = {p.stopped_by: (p.stopped_by_user.full_name or p.stopped_by_user.username)}

    # Превышение плана ФЭО (план crystalline-soaring-heron.md, п.4) — раньше
    # считалось только в списке (?with_feo_excess=true), карточка отдавала пусто.
    # Общий код с list_purchases — см. _compute_purchase_feo_excess.
    _single_feo_excess_map = await _compute_purchase_feo_excess(db, [p])

    # Остаток плановой позиции на КАЖДУЮ строку закупки (план п.4, «по позициям
    # отдавать остаток их плановой позиции, чтобы строку можно было подсветить»):
    #   - позиция привязана к FeoPlannedItem (Ур.5) — остаток берём с точностью
    #     до позиции (planned_item_consumption — тот же расчёт, что и в
    #     /feo-planned-items/residuals, БЕЗ exclude — это read-only карточка
    #     закупки, а не форма редактирования, своя же строка обязана входить в
    #     «съедено», иначе остаток был бы неправдой);
    #   - позиция только с feo_category_id (без Ур.5, план листа целиком) —
    #     остаток узла дерева ФЭО (compute_feo_plan_tree.residual), тот же расчёт,
    #     что использует /feo-categories/plan-positions для строк kind='feo_article'.
    _item_plan_map: dict = {}
    if p.items and p.subsidy_id:
        from app.models.feo_planned_item import FeoPlannedItem
        _fpi_ids = list({it.feo_planned_item_id for it in p.items if it.feo_planned_item_id})
        _fpi_residual: dict = {}
        if _fpi_ids:
            from app.services.feo_plan import planned_item_consumption as _planned_item_consumption
            _fpi_rows = (await db.execute(
                select(FeoPlannedItem.id, FeoPlannedItem.amount).where(FeoPlannedItem.id.in_(_fpi_ids))
            )).all()
            _fpi_amounts = {r[0]: float(r[1] or 0) for r in _fpi_rows}
            _fpi_cons = await _planned_item_consumption(db, _fpi_ids)
            for _fid in _fpi_ids:
                _amt = _fpi_amounts.get(_fid, 0.0)
                _used = (_fpi_cons.get(_fid) or {}).get("used", 0.0)
                _fpi_residual[_fid] = (_amt - _used, _amt)
        _need_tree = any(not it.feo_planned_item_id and (it.feo_category_id or p.feo_category_id) for it in p.items)
        _tree = await compute_feo_plan_tree(db, [p.subsidy_id]) if _need_tree else {}
        for it in p.items:
            if it.feo_planned_item_id and it.feo_planned_item_id in _fpi_residual:
                _item_plan_map[it.id] = _fpi_residual[it.feo_planned_item_id]
                continue
            _cid = it.feo_category_id or p.feo_category_id
            _node = _tree.get(_cid) if _cid else None
            if _node is not None:
                _item_plan_map[it.id] = (_node.get("residual"), _node.get("plan"))

    _wish_title_map: dict = {}
    _wish_status_map: dict = {}
    if p.wish_id:
        from app.models.wish import Wish as _Wish
        _w = await db.get(_Wish, p.wish_id)
        if _w:
            _wish_title_map[p.wish_id] = _w.title
            _wish_status_map[p.wish_id] = _w.status

    out = _purchase_to_full(
        p, contractors, subsidies, allocations=allocations, ru_map=single_ru_map, su_map=single_su_map,
        feo_excess_map=_single_feo_excess_map, item_plan_map=_item_plan_map, wish_title_map=_wish_title_map,
        wish_status_map=_wish_status_map,
    )
    # phase26-m: populate framework_contract_total for single purchase view
    if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
        c = await db.get(Contract, p.contract_id)
        if c:
            if c.max_amount is not None:
                out.framework_contract_total = c.max_amount
            else:
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(func.coalesce(
                        Purchase.contract_price,
                        Purchase.planned_total_price,
                        Purchase.total_nmck,
                        Decimal("0"),
                    )), Decimal("0"))).where(Purchase.contract_id == p.contract_id)
                )
                out.framework_contract_total = sum_r.scalar() or Decimal("0")

    # Phase 31: unseen_fields for single purchase GET (D-05..D-09)
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        _unseen_single = await _get_unseen_map(db, 'purchase', [pid], current_user.id)
        _unseen_fields = _unseen_single.get(pid, [])
        out.unseen_fields = _unseen_fields
        out.unseen_changes_count = len(_unseen_fields)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen purchase single failed: %s", _exc)

    # Phase 31-04: contract_conflict — single GET (1 extra query, only if contract_id set)
    if p.contract_id:
        _c = await db.get(Contract, p.contract_id)
        if _c:
            out.contract_conflict = (
                (_c.number is not None and p.contract_number != _c.number)
                or (_c.date is not None and p.contract_date != _c.date)
            )

    return out


@router.post("/", response_model=PurchaseOut)
async def create_purchase(
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    context: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    is_advance = (data.purchase_method == 'advance')
    is_sn = (context == 'service_note_delivery')
    if not is_advance and not is_sn:
        raise HTTPException(
            403,
            detail="Прямое создание закупки отключено. Создайте заявку в разделе «Заявки на закупку» и отправьте на согласование — после одобрения она автоматически станет закупкой в «Плане закупок». Исключения: авансовые отчёты и СЗ на выдачу."
        )

    items_data = data.items or []
    # Compute total_nmck from items
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override and data.purchase_basis != 'service_note':
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, None, db)

    # Задача владельца (2026-08-05) «блокировать пока не согласовано превышение плана
    # ФЭО»: создание закупки — увеличивающее план действие. Проверяем по КАЖДОЙ
    # категории ФЭО, к которой отнесены позиции (per-item feo_category_id,
    # fallback — категория закупки целиком).
    if not admin_override:
        _cat_amounts: dict[int, Decimal] = {}
        for _i in items_data:
            _cid = _i.feo_category_id or data.feo_category_id
            if _cid:
                _cat_amounts[_cid] = _cat_amounts.get(_cid, Decimal("0")) + (_i.total_price or Decimal("0"))
        if not _cat_amounts and data.feo_category_id:
            _cat_amounts[data.feo_category_id] = total_nmck or Decimal("0")
        for _cid, _amt in _cat_amounts.items():
            await assert_no_unapproved_excess(db, _cid, adding_amount=_amt)

    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): по каждой позиции,
    # ДО создания закупки. over_plan=true пропускаем — такая позиция сознательно
    # сверх плана и уже проходит через assert_no_unapproved_excess выше.
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): позиции, привязанные
    # к ОДНОЙ и той же плановой позиции, накапливаются в пределах ЭТОЙ закупки
    # (assert_tz_batch_not_over_plan), а не проверяются поштучно против ПОЛНОГО
    # плана — иначе две строки в сумме превышают план, каждая проходя поодиночке.
    if not admin_override:
        await assert_tz_batch_not_over_plan(db, items_data, fallback_category_id=data.feo_category_id)

    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    dump = data.model_dump(exclude={"items", "subsidy_allocations"})
    dump["total_nmck"] = total_nmck
    # Phase 28 B4: validate provided assigned_user_id
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    # Auto-assign current user as owner when frontend did not specify one.
    # Без этого закупка с assigned_user_id=NULL становится невидимой для рядового
    # автора (list_purchases фильтрует по visible_user_ids; NULL IN (...) = false).
    if not dump.get("assigned_user_id"):
        dump["assigned_user_id"] = current_user.id
    # SN-UX: для СЗ авто-заполнить автора (текущий) и дату (сейчас) если фронт не прислал
    if dump.get("purchase_basis") == "service_note":
        if not dump.get("service_note_by"):
            dump["service_note_by"] = current_user.id
        if not dump.get("service_note_at"):
            from datetime import datetime, timezone
            dump["service_note_at"] = datetime.now(timezone.utc)
    p = Purchase(**dump)
    db.add(p)
    await db.flush()  # get p.id before commit

    year = date.today().year
    if not p.registry_number:
        p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
    # removed in phase26-j-1: only set when single contract без FK на existing contracts row
    # auto-generate мусорит номером вида "2026/42" для рамочных закупок с реальным contract_id.
    if not p.contract_number and not p.contract_id:
        p.contract_number = f"{year}/{p.id}"

    # phase26-j-1: sync number/date/type из связанного контракта, если contract_id задан
    await _sync_purchase_from_contract(p, db)

    await _assign_framework_seq(p, db)

    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=p.id, **d)
        # Снимок плана (Шаг 1 «план ≠ факт»): позиция создаётся напрямую (не из
        # заявки) — план фиксируется как введённые сейчас значения, если снимок
        # не передан явно клиентом.
        if item.planned_quantity is None and item.planned_unit_price is None and item.planned_total is None:
            item.planned_quantity = item.quantity
            item.planned_unit_price = item.unit_price
            item.planned_total = item.total_price
        db.add(item)

    # Авансовый без wish_id → авто-заявка на возмещение (source='advance_report', status='submitted')
    if is_advance and not data.wish_id:
        from app.models.wish import Wish
        from app.models.wish_item import WishItem as WishItemModel
        wish_title = f"Возмещение по авансовому отчёту {p.registry_number or f'#{p.id}'}"
        auto_wish = Wish(
            source='advance_report',
            status='submitted',
            title=wish_title[:499],
            created_by=current_user.id,
            org_id=get_single_org_id(current_user) or current_user.org_id,
            subsidy_id=p.subsidy_id,
            feo_category_id=p.feo_category_id,
            event_id=p.event_id,
            justification=p.service_note_text,
            estimated_price=total_nmck,
        )
        db.add(auto_wish)
        await db.flush()  # get auto_wish.id
        p.wish_id = auto_wish.id
        # Копируем позиции закупки → WishItem
        for item_d in items_data:
            d = item_d.model_dump()
            db.add(WishItemModel(
                wish_id=auto_wish.id,
                item_name=d.get('item_name', ''),
                item_type=d.get('item_type'),
                quantity=d.get('quantity'),
                unit=d.get('unit'),
                unit_price=d.get('unit_price'),
                total_price=d.get('total_price'),
                country_origin=d.get('country_origin'),
                product_id=d.get('product_id'),
                feo_category_id=d.get('feo_category_id'),
            ))

    # Save subsidy allocations
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=p.id,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # Contract price: авто-пересчёт из items для ВСЕХ типов закупок (phase26-l-1).
    # Рамочный (framework_cumulative / framework_with_amount) тоже должен суммироваться в total_ordered контракта.
    _items_sum_create = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck
    if _items_sum_create:
        p.contract_price = _items_sum_create

    # Budget history write hook — record initial planned_total_price
    if p.subsidy_id and p.planned_total_price:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=p.subsidy_id,
            purchase_id=p.id,
            entity_type="purchase",
            old_value=None,
            new_value=float(p.planned_total_price),
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    await db.commit()
    await db.refresh(p)
    return p


@router.put("/{pid}")
async def update_purchase(
    pid: int,
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    old_planned_total_price = p.planned_total_price  # capture BEFORE setattr loop
    # Задача владельца, план zany-fluttering-mountain.md п.4 (2026-08-10): PUT
    # заменяет ВСЕ позиции закупки (delete+recreate ниже), у каждой может быть
    # СВОЯ feo_category_id, отличная от p.feo_category_id. Старая проверка ниже
    # смотрела только на p.feo_category_id целиком — если позиции распределены
    # по нескольким категориям (feo_per_item), рост суммы в ОДНОЙ из них проходил
    # мимо гейта, пока «нетто» по закупке не рос. Снимок «сколько СЕЙЧАС числится
    # по каждой категории» — ДО удаления старых позиций — нужен для сравнения.
    old_item_cat_amounts: dict[int, Decimal] = {}
    for _oi in p.items:
        _ocid = _oi.feo_category_id or p.feo_category_id
        if _ocid:
            old_item_cat_amounts[_ocid] = old_item_cat_amounts.get(_ocid, Decimal("0")) + Decimal(str(_oi.total_price or 0))
    # Phase 31: capture old values for diff-tracking BEFORE any mutation
    _old_purchase_values = {f: getattr(p, f, None) for f in PURCHASE_TRACKED_FIELDS}
    # Employees/managers can save any purchase they have access to (org-level access checked at list level)
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    items_data = data.items or []
    items_sum = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    # Phase 28 B4: validate assigned_user_id on PUT
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    elif data.assigned_user_id == 0:
        raise HTTPException(422, "Укажите ответственного исполнителя")

    # Opportunistic backfill: legacy purchases с assigned_user_id=NULL
    # становятся видимыми создателю через первое же сохранение.
    if p.assigned_user_id is None and not getattr(data, "assigned_user_id", None):
        p.assigned_user_id = current_user.id

    # Auto-assign purchase_number if missing
    if not p.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        p.purchase_number = max_result.scalar() + 1

    # НМЦК logic: frozen after "contracted" status
    CONTRACTED_STATUSES = ("contracted", "ordered", "delivered", "paid")
    is_contracted = p.status in CONTRACTED_STATUSES

    if is_contracted:
        # НМЦК зафиксирована — НЕ пересчитываем, берём из БД
        # Обновляем только цену договора из текущих цен позиций
        pass
    else:
        # До стадии "Договор" — НМЦК = сумма позиций
        p.total_nmck = items_sum
        p.planned_total_price = items_sum or p.planned_total_price

    if not admin_override and data.purchase_basis != 'service_note':
        budget_amount = p.total_nmck if is_contracted else items_sum
        # 12-02: per-item FEO budget check
        _feo_check_items = [
            {"feo_planned_item_id": i.feo_planned_item_id, "amount": i.total_price}
            for i in items_data
            if i.feo_planned_item_id and i.total_price
        ]
        await _check_budget(
            data.subsidy_id,
            budget_amount or data.planned_total_price,
            pid,
            db,
            feo_items=_feo_check_items,
            is_admin=current_user.role in ADMIN_ROLES,
        )

    # If contract_id or type changed, reset seq so it gets re-assigned
    old_contract_id = p.contract_id
    old_type = p.purchase_contract_type
    payload_dict = data.model_dump(exclude={"items", "subsidy_allocations"}, exclude_unset=True)
    # Phase 27.1.4: race-defence — если payload приходит с contractor_id=None,
    # а в БД он был установлен И contract_id не меняется → игнорируем stale null.
    # Это защищает от race в editFrameworkSeq: форма шлёт PUT до завершения async fetch контрагента.
    if (
        'contractor_id' in payload_dict
        and payload_dict['contractor_id'] is None
        and p.contractor_id is not None
        and payload_dict.get('contract_id', p.contract_id) == p.contract_id
    ):
        payload_dict.pop('contractor_id')

    for k, v in payload_dict.items():
        # Don't overwrite frozen total_nmck
        if is_contracted and k in ("total_nmck", "planned_total_price"):
            continue
        setattr(p, k, v)
    # JSONB columns need explicit dirty-flag so SQLAlchemy detects mutations
    if "acceptance_docs" in data.model_fields_set:
        flag_modified(p, "acceptance_docs")

    # Владелец (2026-08-12, «закупка сама становится планом»): PUT — единственный
    # путь добавить/поменять позицию в УЖЕ СУЩЕСТВУЮЩЕЙ закупке напрямую (в обход
    # заявки — реальный случай с прода: категория 3716 «Приобретение брендированных
    # футболок» получила закупку на 149 282,50 ₽ без единой плановой позиции, ФЭО
    # автозаведения тогда не видело). Каждая позиция с категорией ФЭО (своей или
    # закупки целиком, items_data уже несёт её из payload'а — категория «применена»
    # раньше любых расчётных проверок ниже) без явной привязки находит/заводит
    # FeoPlannedItem — ДО assert_no_unapproved_excess/assert_tz_not_over_plan ниже,
    # иначе им не с чем сравнивать (тот же порядок, что в wishes.py._distribute_
    # wish_to_purchases). Работает на items_data (ещё pydantic, не персистентные
    # PurchaseItem) — auto_assign_planned_items требует только атрибуты
    # item_name/quantity/unit/total_price/feo_category_id/feo_planned_item_id/
    # over_plan, которые есть у обеих сторон; итоговый feo_planned_item_id/
    # over_plan, проставленные функцией на items_data, попадают в PurchaseItem
    # ниже через item_d.model_dump().
    await auto_assign_planned_items(
        items_data, p.feo_category_id, db,
        note=f"закупкой №{p.purchase_number or p.id} (правка вне заявки)",
    )

    # Задача владельца (2026-08-05) «блокировать пока не согласовано превышение плана
    # ФЭО», расширено 2026-08-10 (план zany-fluttering-mountain.md п.4) на ПЕР-ITEM
    # категории: изменение закупки, увеличивающее сумму В КОНКРЕТНОЙ категории ФЭО
    # (не только на уровне закупки целиком) — УВЕЛИЧИВАЮЩЕЕ план действие. Сравниваем
    # НОВЫЙ снимок по категориям (из items_data, только что распределённого PUT'ом,
    # тот же принцип, что и в create_purchase per-item) со СТАРЫМ (old_item_cat_amounts,
    # снят до удаления старых позиций выше) — категория, чья сумма ВЫРОСЛА (в т.ч. с
    # нуля — позиция перевешена в неё из другой категории), проходит гейт с дельтой
    # роста; категории, чья сумма НЕ выросла (уменьшилась/не изменилась), не трогаем —
    # это путь возврата в рамки плана, блокировать нельзя (см. assert_no_unapproved_excess
    # docstring).
    if not admin_override:
        _new_item_cat_amounts: dict[int, Decimal] = {}
        for _i in items_data:
            _ncid = _i.feo_category_id or p.feo_category_id
            if _ncid:
                _new_item_cat_amounts[_ncid] = _new_item_cat_amounts.get(_ncid, Decimal("0")) + (_i.total_price or Decimal("0"))
        if not _new_item_cat_amounts and p.feo_category_id:
            _new_item_cat_amounts[p.feo_category_id] = Decimal(str(p.total_nmck or 0))
        _touched_cat_ids = set(_new_item_cat_amounts) | set(old_item_cat_amounts)
        for _cid in _touched_cat_ids:
            _new_amt = _new_item_cat_amounts.get(_cid, Decimal("0"))
            _old_amt = old_item_cat_amounts.get(_cid, Decimal("0"))
            if _new_amt > _old_amt:
                await assert_no_unapproved_excess(db, _cid, adding_amount=_new_amt - _old_amt)

    # Задача владельца «план ≠ факт» (шаг C, сессия 2026-08-06): переход закупки
    # в «Договор» — превентивная точка контроля. С этого момента итог закупки
    # (факт по договорным позициям/КП, см. FACT_PRICED_STATUSES в feo_plan.py)
    # уже мог сложиться дороже плана ещё на «Ведётся работа» — если превышение
    # факт-над-планом не согласовано, подписывать договор нельзя (иначе перерасход
    # закрывают постфактум поиском доп. финансирования — ровно то, что владелец
    # просил предотвратить). Проверяем по каждой категории ФЭО позиций закупки
    # (per-item feo_category_id, fallback — категория закупки целиком), как и
    # в create_purchase выше.
    _old_status_for_gate = _old_purchase_values.get("status")
    if not admin_override and p.status == "contracted" and _old_status_for_gate != "contracted":
        _gate_cat_ids: set[int] = set()
        for _i in items_data:
            _cid = _i.feo_category_id or p.feo_category_id
            if _cid:
                _gate_cat_ids.add(_cid)
        if not _gate_cat_ids and p.feo_category_id:
            _gate_cat_ids.add(p.feo_category_id)
        for _cid in _gate_cat_ids:
            await assert_no_unapproved_excess(db, _cid)

    # Contract price: авто-пересчёт из items для ВСЕХ типов закупок (phase26-l-1).
    # Рамочный (framework_cumulative / framework_with_amount) тоже должен суммироваться в total_ordered контракта.
    if items_sum:
        p.contract_price = items_sum
    if (p.contract_id != old_contract_id or p.purchase_contract_type != old_type) and data.framework_seq is None:
        p.framework_seq = None  # force re-assignment below
    # phase26-j-1 (fix: hotfix после регрессии): sync только при ИЗМЕНЕНИИ contract_id,
    # иначе ручные правки contract_number перетираются на каждом save (Vue v-model шлёт contract_id всегда).
    if p.contract_id and p.contract_id != old_contract_id:
        await _sync_purchase_from_contract(p, db)
    await _assign_framework_seq(p, db, exclude_id=pid)

    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): по каждой НОВОЙ позиции,
    # ДО удаления старых (PUT заменяет все позиции целиком — старые снимки плана
    # старых строк тут не помогут, проверяем именно то, что придёт в базу).
    # over_plan=true пропускаем — сознательно сверх плана, см. create_purchase выше.
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): накопление по общей
    # плановой позиции в пределах ЭТОЙ закупки — см. assert_tz_batch_not_over_plan.
    if not admin_override:
        await assert_tz_batch_not_over_plan(db, items_data, fallback_category_id=p.feo_category_id)

    # Replace items (auto-link to catalog via fuzzy match if product_id missing)
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=pid, **d)
        # Снимок плана (Шаг 1 «план ≠ факт»): PUT удаляет и пересоздаёт ВСЕ позиции
        # (нет id для сопоставления со старым снимком), поэтому снимок фиксируем из
        # введённых значений только пока закупка ещё в статусе «План закупок» — так
        # же, как PATCH одной позиции ниже. Для более поздних статусов снимок НЕ
        # восстановить из уже удалённой строки — оставляем NULL, а не подставляем
        # текущую (возможно уже не плановую) цену как будто это план.
        if (
            p.status == "plan_schedule"
            and item.planned_quantity is None and item.planned_unit_price is None and item.planned_total is None
        ):
            item.planned_quantity = item.quantity
            item.planned_unit_price = item.unit_price
            item.planned_total = item.total_price
        db.add(item)

    # Phase 26-Z: при PUT — проставить contractor_id во все позиции без контрагента,
    # если на уровне закупки contractor_id установлен. Идемпотентно.
    if p.contractor_id:
        await db.flush()  # flush чтобы только что созданные items видны в SELECT
        _ctr_put = await db.get(Contractor, p.contractor_id)
        if _ctr_put:
            _null_items_put = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == pid, PurchaseItem.contractor_id.is_(None))
            )).scalars().all()
            for _it in _null_items_put:
                _it.contractor_id = _ctr_put.id
                _it.contractor_inn = _ctr_put.inn
                _it.contractor_name = _ctr_put.name

    # 12-02: Auto-match FEO items for purchase items without feo_planned_item_id
    suggested_feo_matches = []
    await db.flush()  # ensure new items are visible
    _flushed_items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
    )).scalars().all()
    for idx, pi in enumerate(_flushed_items):
        if pi.feo_planned_item_id is not None:
            continue  # already linked
        match = await _auto_match_feo_item(
            pi.item_name,
            p.subsidy_id,
            p.feo_category_id,
            db,
        )
        if match:
            suggested_feo_matches.append({
                "item_index": idx,
                "purchase_item_id": pi.id,
                "item_name": pi.item_name,
                "suggested_item_id": match[0],
                "suggested_name": match[1],
                "confidence": match[2],
            })

    # Replace subsidy allocations
    await db.execute(delete(PurchaseSubsidyAllocation).where(PurchaseSubsidyAllocation.purchase_id == pid))
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=pid,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # Auto-create/link contract record when contract_number is set
    await ensure_contract_linked(p, db)

    # Budget history write hook
    if p.subsidy_id:
        _old = float(old_planned_total_price or 0)
        _new = float(p.planned_total_price or 0)
        if _old != _new:
            from app.models.budget_history import BudgetHistory as _BH
            db.add(_BH(
                subsidy_id=p.subsidy_id,
                purchase_id=p.id,
                entity_type="purchase",
                old_value=_old,
                new_value=_new,
                changed_by_id=current_user.id,
                changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                reason=None,
            ))

    # Авансовый: синхронизировать связанную авто-заявку если она ещё не одобрена
    if p.purchase_method == 'advance' and p.wish_id:
        from app.models.wish import Wish
        from app.models.wish_item import WishItem as WishItemModel
        _wish = await db.get(Wish, p.wish_id)
        if _wish and getattr(_wish, 'source', None) == 'advance_report' and _wish.status in ('draft', 'submitted', 'rejected'):
            _wish.estimated_price = items_sum or p.planned_total_price
            _wish.justification = p.service_note_text
            _wish.title = f"Возмещение по авансовому отчёту {p.registry_number or f'#{p.id}'}"[:499]
            # Пересобрать WishItems из позиций закупки
            await db.execute(delete(WishItemModel).where(WishItemModel.wish_id == _wish.id))
            for item_d in items_data:
                d = item_d.model_dump()
                db.add(WishItemModel(
                    wish_id=_wish.id,
                    item_name=d.get('item_name', ''),
                    item_type=d.get('item_type'),
                    quantity=d.get('quantity'),
                    unit=d.get('unit'),
                    unit_price=d.get('unit_price'),
                    total_price=d.get('total_price'),
                    country_origin=d.get('country_origin'),
                    product_id=d.get('product_id'),
                    feo_category_id=d.get('feo_category_id'),
                ))

    # 12-03: Auto-create plan-graph version on status→fact or FEO-linked items
    _old_status = _old_purchase_values.get("status")
    _status_became_fact = (
        p.status in ("delivered", "paid")
        and _old_status not in ("delivered", "paid")
    )
    _has_feo_items = any(i.feo_planned_item_id for i in items_data if i.feo_planned_item_id)
    if p.subsidy_id and (_status_became_fact or _has_feo_items):
        if _status_became_fact:
            _st_label = "Оплачено" if p.status == "paid" else "Поставлено"
            _pgv_note = f"Авто-версия: закупка №{p.purchase_number or p.id} → {_st_label}"
        else:
            _pgv_note = f"Авто-версия при сохранении закупки #{p.purchase_number or p.id}"
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=_pgv_note)

    await db.commit()
    await db.refresh(p)

    # Phase 31: record EntityChange for each TRACKED_FIELD that changed (D-05..D-09)
    # Only record changes made by OTHER users (D-07: own changes are not highlighted)
    try:
        from app.models.entity_change import EntityChange as _EC
        _changes = []
        for _fname in PURCHASE_TRACKED_FIELDS:
            _old = _old_purchase_values.get(_fname)
            _new = getattr(p, _fname, None)
            _old_s = str(_old) if _old is not None else None
            _new_s = str(_new) if _new is not None else None
            if _old_s != _new_s:
                _changes.append(_EC(
                    entity_type='purchase',
                    entity_id=p.id,
                    field_name=_fname,
                    old_value=_old_s,
                    new_value=_new_s,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        if _changes:
            for _c in _changes:
                db.add(_c)
            await db.commit()
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed: %s", _exc)

    # 12-02: Return suggestions if any
    if suggested_feo_matches:
        from app.schemas.schemas import PurchaseOut as _POut
        base = _POut.model_validate(p).model_dump()
        base["suggested_feo_matches"] = suggested_feo_matches
        return base
    return p


# Phase 27.1 D-07: helper — авто-пересчёт purchase.contract_price = SUM(contract_items.total)
async def _recalc_contract_price_from_contract_items(purchase_id: int, db: AsyncSession) -> None:
    """Phase 27.1 D-07: авто-пересчёт purchase.contract_price = SUM(contract_items.total).

    Применимо: разовая (purchase_contract_type='single' или NULL), авансовая
    (purchase_method='advance'), дочерняя рамочного (parent_purchase_id IS NOT NULL).
    НЕ применимо для рамочного головного (framework_cumulative/framework_limited
    AND parent_purchase_id IS NULL) — manual entry сохраняется.
    """
    from app.models.contract_item import ContractItem
    p = await db.get(Purchase, purchase_id)
    if not p:
        return
    is_framework_head = (
        p.purchase_contract_type in ('framework_cumulative', 'framework_limited')
        and p.parent_purchase_id is None
    )
    if is_framework_head:
        return
    result = await db.execute(
        select(func.sum(ContractItem.total)).where(ContractItem.purchase_id == purchase_id)
    )
    ci_sum = result.scalar() or Decimal('0')
    if ci_sum > 0:
        p.contract_price = ci_sum
        await db.commit()


# Phase 26: автосохранение полей карточки закупки.
# Принимает произвольный частичный JSON; обновляет только переданные поля.
# Не пересчитывает items/НМЦК/contract_price (этим занимается PUT при явном Save).
PATCHABLE_FIELDS = {
    "subject", "description", "contractor_id", "feo_category_id",
    "purchase_method", "competitive_form", "purchase_contract_type",
    "contract_number", "contract_date", "contract_price", "contract_end_date",
    "nmck", "planned_total_price",
    "delivery_date", "delivery_location", "delivery_address",
    "delivery_region", "delivery_city", "delivery_street",
    "delivery_house", "delivery_building", "delivery_postcode",
    "submission_deadline", "service_term_mode", "service_start_date",
    "service_end_date", "service_term_days", "service_term_type",
    "service_deadline_date", "third_party_involved",
    "vat_applicable", "vat_rate", "vat_exemption_article", "vat_mode", "feo_per_item",
    "acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number",
    "acceptance_doc_amount",
    # Phase 24 D-08: JSONB-массив закрывающих документов (АКТ/УПД/СЧФ/ТТН/...)
    "acceptance_docs",
    "payment_doc_number", "payment_doc_date",
    "payment_amount", "country_origin", "purchase_basis",
    "responsible_person_id", "initiator_id", "subject_kind", "execution_term",
    "event_id", "delivery_location_kind", "region",
    # Phase 24: stages + financial plan
    "is_likely_needed", "is_prepayment", "prepayment_date", "stage_label",
    # Авансовый отчёт: кому возмещать
    "reimbursement_user_id",
    # Phase 28 B4: ответственный исполнитель
    "assigned_user_id",
    # Phase 26-K: доп. соглашение и дата заказа
    "agreement_number", "agreement_date", "order_date",
    # Phase 28: форма договора (выбор шаблона при генерации)
    "contract_form",
    # Методичка, приклеиваемая к договору (large / small / none)
    "methodology",
    # Phase 28: contract-specific поля (условия конкретного договора)
    'acceptance_term_days', 'penalty_rate', 'contractor_ogrnip_date',
    'repair_request_number',
    'commission_member_1_name', 'commission_member_2_name', 'commission_member_3_name',
    'advance_amount',
    # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
    'warranty_period_days', 'is_retroactive',
    # Phase 29: связь закупки с ТС
    'vehicle_id',
    # SN-UX: адресат служебной записки
    'service_note_to_user_id',
    # ЭТП: ссылка на конкурсную процедуру
    'etp_url',
    # Fabrikant: срок оплаты и дата рассмотрения заявок
    'payment_term_days', 'applications_review_date',
    # Импорт/экспорт: квартал обязательств и планируемый месяц платежа
    "commitment_quarter", "planned_payment_month",
    # Phase 28 T6/T7: условные блоки шаблонов + протокол/приказ закупки
    "delivery_by_supplier", "has_stages",
    "procurement_protocol_number", "procurement_order_number",
}


# Имена полей с типом DATE/DATETIME — для коэрсии строк в date-объекты в PATCH.
# Фронт шлёт ISO-строки ('2026-05-08'), asyncpg ожидает date()/datetime().
# Полный список из backend/app/models/purchase.py — все Column(Date)/Column(DateTime).
_DATE_FIELDS = {
    "contract_date", "execution_term", "execution_term_changed",
    "delivery_date", "acceptance_doc_date", "payment_doc_date",
    "contract_end_date", "service_start_date", "service_end_date",
    "procurement_planned_date", "service_deadline_date", "prepayment_date",
    # Phase 26-K
    "agreement_date", "order_date",
    # Phase 28
    "contractor_ogrnip_date",
    # Fabrikant
    "applications_review_date",
    "planned_payment_month",
}
_DATETIME_FIELDS = {"submission_deadline", "service_note_at"}


def _coerce_patch_value(field: str, value):
    """Конвертирует ISO-строку в date/datetime для DATE-полей; пустые строки → None."""
    if value == "":
        return None
    if value is None:
        return None
    if field in _DATE_FIELDS and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    if field in _DATETIME_FIELDS and isinstance(value, str):
        try:
            # Поддержка и 'YYYY-MM-DD', и 'YYYY-MM-DDTHH:MM[:SS]'
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return date.fromisoformat(value[:10])
            except Exception:
                return None
    return value


@router.patch("/{pid}")
async def patch_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Not found")
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")

    # Phase 28 B4: нельзя снять ответственного через PATCH
    if "assigned_user_id" in (body or {}):
        val = body["assigned_user_id"]
        if val is None or val == 0:
            raise HTTPException(422, "Нельзя снять ответственного исполнителя")
        target = await db.get(User, val)
        if target is None:
            raise HTTPException(422, f"Пользователь {val} не найден")

    # Opportunistic backfill: первый PATCH (autosave) от user'а закрепляет
    # за ним legacy-закупку без assigned_user_id — иначе после save она опять
    # пропадёт из его OrdersView.
    if p.assigned_user_id is None and "assigned_user_id" not in (body or {}):
        p.assigned_user_id = current_user.id

    # phase26-j-1 (fix): запоминаем contract_id ДО setattr, чтобы sync вызвался
    # только при реальном изменении FK, а не на каждый autosave с тем же contract_id.
    old_contract_id_patch = p.contract_id

    changed: list[str] = []
    for k, v in (body or {}).items():
        if k not in PATCHABLE_FIELDS:
            continue
        if not hasattr(p, k):
            continue
        v = _coerce_patch_value(k, v)
        if getattr(p, k) != v:
            setattr(p, k, v)
            changed.append(k)
            # JSONB колонки: SQLAlchemy не детектирует мутации без flag_modified
            if k == "acceptance_docs":
                flag_modified(p, "acceptance_docs")
    # phase26-j-1 (fix): sync только при ИЗМЕНЕНИИ contract_id, иначе ручные правки
    # contract_number перетираются на каждом autosave (Phase 26 patches шлют contract_id вместе с другими полями).
    if p.contract_id and p.contract_id != old_contract_id_patch:
        await _sync_purchase_from_contract(p, db)
        for f in ("contract_number", "contract_date", "purchase_contract_type"):
            if f not in changed:
                changed.append(f)
    # Phase 26-Z: при установке contractor_id на закупке — проставить во все
    # позиции без указанного контрагента (наследование одним подрядчиком).
    if p.contractor_id and "contractor_id" in changed:
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.contractor import Contractor as _Ctr
        c_row = await db.get(_Ctr, p.contractor_id)
        if c_row:
            upd_q = await db.execute(
                select(_PI).where(_PI.purchase_id == p.id, _PI.contractor_id.is_(None))
            )
            for it in upd_q.scalars().all():
                it.contractor_id = c_row.id
                it.contractor_inn = c_row.inn
                it.contractor_name = c_row.name
    if changed:
        await db.commit()
        await db.refresh(p)
    return {"id": p.id, "changed": changed}


class _SetProductBody(BaseModel):
    product_id: Optional[int] = None  # None — снять привязку


@router.post("/{pid}/items/{item_id}/set-product")
async def set_item_product(
    pid: int,
    item_id: int,
    body: _SetProductBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """27.4-14: точечная запись PurchaseItem.product_id без full PUT.
    Вызывается фронтом сразу после «Добавить в каталог» / выбора товара,
    чтобы привязка пережила F5 без необходимости нажимать общий «Сохранить»."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    if body.product_id is not None:
        prod = await db.get(Product, body.product_id)
        if not prod:
            raise HTTPException(404, "Товар каталога не найден")
        it.product_id = body.product_id
        it.match_confirmed = True
    else:
        it.product_id = None
    await db.commit()
    return {"ok": True, "item_id": item_id, "product_id": it.product_id}


class _ItemPatchBody(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    feo_category_id: Optional[int] = None
    clear_feo_category: bool = False
    # Владелец (2026-08-18, прод-инцидент — «Огнетушитель ОУ-2» перенесён в новую
    # категорию, auto_assign_planned_items не нашёл точное совпадение имени и молча
    # завёл вторую плановую позицию рядом с уже подходящей): явный выбор плановой
    # позиции пользователем в диалоге «Редактировать позицию» — приоритет над
    # автоподбором. Optional[int] с default=None НЕ различает «поле не прислали» и
    # «прислали null» — различаем через `body.model_fields_set` (см. эндпоинт ниже):
    # null, присланный явно, значит «осознанно оставить без плановой позиции».
    feo_planned_item_id: Optional[int] = None
    # Шаг 2 «план ≠ факт» (сессия 2026-08-06): осознанный обход заморозки ТЗ —
    # только ADMIN_ROLES, только явным флагом в теле запроса, пишется в EntityChange.
    admin_override: bool = False


# Шаг 2 «план ≠ факт»: с этих статусов закупка считается объявленной — количество/
# цена ТЗ позиции замораживаются (иначе правка «съедает» зафиксированный план,
# см. purchase_items.planned_* и compute_feo_plan_tree). Итоговую цену по факту
# закупки/КП вносят в подстроке «Договор» позиции (contract_items), не здесь.
TZ_FROZEN_STATUSES = {"work_in_progress", "contracted", "ordered", "delivered", "paid"}


async def _recalc_purchase_totals(p: Purchase, db: AsyncSession) -> None:
    """Пересчёт сумм закупки из позиций (та же логика, что в update_purchase)."""
    items_sum = (await db.execute(
        select(func.coalesce(func.sum(PurchaseItem.total_price), 0))
        .where(PurchaseItem.purchase_id == p.id)
    )).scalar() or Decimal("0")
    if p.status not in ("contracted", "ordered", "delivered", "paid"):
        p.total_nmck = items_sum
        p.planned_total_price = items_sum or p.planned_total_price
    if items_sum:
        p.contract_price = items_sum


@router.patch("/{pid}/items/{item_id}")
async def patch_purchase_item(
    pid: int,
    item_id: int,
    body: _ItemPatchBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Точечная правка позиции (название/кол-во/цена/ФЭО-привязка) без full PUT закупки."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    # W3 (сужено — принцип владельца, 2026-08-18): «когда перевели в Закупку,
    # редактироваться должно в Закупке — зачем перебрасывает в заявку?». Пока
    # закупка ещё на стадии `wishes` (скрытая закупка-заготовка, которую видно
    # только через дашборд ФЭО, — план закупок её ещё не видел) источник
    # правды остаётся заявка, поэтому правка позиции здесь запрещена. С
    # момента, когда закупка попала в план закупок (`plan_schedule` и дальше),
    # источник правды — сама закупка: правка идёт прямо тут, а не редиректом в
    # заявку (раньше запрет действовал для ЛЮБОГО статуса — правка открывалась
    # в диалоге, но 409'ила при сохранении, тупик с другим текстом). Смена
    # категории ФЭО (feo_category_id / clear_feo_category) была разрешена уже
    # тогда — остаётся разрешена и здесь. Ниже по коду продолжает работать
    # своя, отдельная заморозка ТЗ (TZ_FROZEN_STATUSES) — именно она теперь
    # настоящий ограничитель для объявленных закупок, и её сообщение понятное
    # («закупка объявлена, ТЗ зафиксировано»), а не молчаливый редирект.
    if it.wish_item_id is not None and p.status == "wishes":
        substantive_keys = set(body.model_dump(exclude_unset=True).keys()) - {"feo_category_id", "clear_feo_category"}
        if substantive_keys:
            raise HTTPException(
                409,
                f"Позиция привязана к заявке #{p.wish_id} — редактируйте её в заявке",
            )
    # Шаг 2 «план ≠ факт» (сессия 2026-08-06): заморозка ТЗ с момента объявления
    # закупки. Приоритет ниже гейта W3 выше (тот уже отсёк позиции, привязанные к
    # заявке, — для них редактирование в принципе идёт через заявку, а не сюда).
    # Здесь — отдельная проверка для позиций БЕЗ привязки к заявке (созданных
    # прямо в закупке) и как страховка на случай снятия W3 в будущем.
    _old_qty = _old_price = None
    _wants_tz_change = body.quantity is not None or body.unit_price is not None
    if _wants_tz_change and p.status in TZ_FROZEN_STATUSES:
        if body.admin_override and current_user.role in ADMIN_ROLES:
            _old_qty, _old_price = it.quantity, it.unit_price
        else:
            from app.routers.purchase_export import _STATUS_LABELS
            stage = _STATUS_LABELS.get(p.status, p.status)
            raise HTTPException(
                409,
                f"Закупка №{p.purchase_number or p.id} объявлена (стадия «{stage}») — ТЗ зафиксировано. "
                "Цену по итогам закупки внесите в подстроке «Договор» позиции.",
            )
    # Владелец (2026-08-12, «закупка сама становится планом»): категорию ФЭО
    # применяем ДО расчётных проверок ниже (Шаг 5 и Шаг 4), а не после них, как
    # было раньше, — так гейты и автозаведение плана видят актуальную категорию.
    # Перенос позиции в ДРУГУЮ категорию (боевой случай — категория 3716
    # «Приобретение брендированных футболок» получила закупку без единой
    # плановой позиции) означает, что старая привязка feo_planned_item_id
    # принадлежит прежней категории и в категории-получателе может не быть
    # ничего — очищаем её и заводим/находим план в новой категории тем же
    # общим сервисом, что и wishes.py (app/services/plan_autoassign.py).
    _cat_id_before_patch = it.feo_category_id
    _category_changing = False
    if body.clear_feo_category:
        if it.feo_category_id is not None:
            _category_changing = True
        it.feo_category_id = None
    elif body.feo_category_id is not None:
        cat = await db.get(FeoCategory, body.feo_category_id)
        if not cat:
            raise HTTPException(404, "Категория ФЭО не найдена")
        if p.subsidy_id and cat.subsidy_id != p.subsidy_id:
            raise HTTPException(422, "Категория ФЭО относится к другой субсидии")
        if body.feo_category_id != it.feo_category_id:
            _category_changing = True
        it.feo_category_id = body.feo_category_id
    # Синхронизировать feo_category_id с WishItem при category-only правке wish-позиции
    if it.wish_item_id is not None and (body.clear_feo_category or body.feo_category_id is not None):
        from app.models.wish_item import WishItem as _WishItem
        wi = await db.get(_WishItem, it.wish_item_id)
        if wi is not None:
            wi.feo_category_id = it.feo_category_id
    # Плановые позиции следуют за сменой категории (владелец, 2026-08-17):
    # если у переносимой позиции есть СОБСТВЕННАЯ плановая позиция (никто
    # больше на неё не ссылается — см. move_or_detach_planned_item), она
    # переезжает в новую категорию ВМЕСТЕ с этой позицией — та же строка, тот
    # же id, история не теряется. Если позиция — не единственный владелец
    # плановой строки (общий план на несколько закупок/заявку и её уже
    # сконвертированную закупку), плановая строка НЕ трогается, привязка
    # переносимой позиции снимается, а предупреждение уходит в ответ явно
    # (см. _plan_transfer_warning в теле ответа ниже).
    # Владелец (2026-08-18): пользователь выбрал плановую позицию САМ (диалог
    # «Редактировать позицию», FeoPlannedItemsSelect) — приоритет над автоподбором
    # по имени. `"feo_planned_item_id" in body.model_fields_set` отличает «поле не
    # прислали» (прежнее поведение, автоподбор ниже) от «прислали, в т.ч. null»
    # (осознанный выбор/снятие выбора человеком). При явном выборе НЕ вызываем ни
    # move_or_detach_planned_item, ни auto_assign_planned_items — иначе они, отработав
    # по СТАРОЙ привязке it.feo_planned_item_id (переезд/автоподбор смотрят именно на
    # неё), либо молча переедут/создадут не то, что выбрал человек, либо (что хуже)
    # move_or_detach_planned_item отработает первым и его результат применится ДО
    # явного выбора и будет им тут же перезаписан — вычислять его вообще незачем.
    _explicit_planned_item_chosen = "feo_planned_item_id" in body.model_fields_set
    _plan_transfer_warning: Optional[str] = None
    if not _explicit_planned_item_chosen:
        if _category_changing and it.feo_planned_item_id is not None:
            if it.feo_category_id is not None:
                _plan_transfer_warning = await move_or_detach_planned_item(db, it, it.feo_category_id)
            else:
                # clear_feo_category: категории больше нет — плановой позиции
                # переезжать некуда, привязка просто снимается (как и раньше).
                _old_fpi_id = it.feo_planned_item_id
                it.feo_planned_item_id = None
                it.over_plan = False
                from app.models.feo_planned_item import FeoPlannedItem as _FPI
                _old_fpi = await db.get(_FPI, _old_fpi_id)
                await deactivate_if_orphaned(db, _old_fpi)
        if _category_changing and it.feo_category_id is not None and it.feo_planned_item_id is None:
            # auto_assign_planned_items смотрит на текущие item_name/quantity/
            # total_price позиции — если это ЖЕ тело правки одновременно меняет и
            # название/кол-во/цену (мутируются НИЖЕ), новая плановая позиция (если
            # заводится с нуля) фиксирует снимок ДО этих правок; для типичного
            # случая «просто перенести позицию в другую категорию» разницы нет.
            await auto_assign_planned_items(
                [it], it.feo_category_id, db,
                note=f"переносом позиции в закупке №{p.purchase_number or p.id}",
            )
    else:
        from app.models.feo_planned_item import FeoPlannedItem as _FPIExplicit
        _old_fpi_id_explicit = it.feo_planned_item_id
        if body.feo_planned_item_id is not None:
            _chosen_fpi = await db.get(_FPIExplicit, body.feo_planned_item_id)
            if not _chosen_fpi:
                raise HTTPException(404, "Плановая позиция не найдена")
            # Деактивированная плановая позиция исключена из UI-подбора
            # (/feo-categories/plan-positions фильтрует is_active == True), но
            # явный выбор идёт по id и обходит этот фильтр. Привязка к погашенной
            # позиции делает сумму невидимой для
            # plan_consumption_by_category(exclude_planned_item_linked=True) —
            # позиция числится «привязанной к плану», а плана нет. Находка QA
            # 2026-08-18.
            if not _chosen_fpi.is_active:
                raise HTTPException(
                    409,
                    f"Плановая позиция «{_chosen_fpi.name}» деактивирована (удалена из плана), "
                    f"привязка к ней невозможна — выберите действующую или создайте новую.",
                )
            if it.feo_category_id is None or _chosen_fpi.feo_category_id != it.feo_category_id:
                _chosen_cat_name = (await db.execute(
                    select(FeoCategory.name).where(FeoCategory.id == _chosen_fpi.feo_category_id)
                )).scalar_one_or_none() or f"#{_chosen_fpi.feo_category_id}"
                if it.feo_category_id is not None:
                    _target_cat_name = (await db.execute(
                        select(FeoCategory.name).where(FeoCategory.id == it.feo_category_id)
                    )).scalar_one_or_none() or f"#{it.feo_category_id}"
                else:
                    _target_cat_name = "без категории ФЭО"
                raise HTTPException(
                    409,
                    f"Плановая позиция «{_chosen_fpi.name}» относится к категории «{_chosen_cat_name}», "
                    f"а позиция закупки — к категории «{_target_cat_name}». Выберите плановую позицию той же категории.",
                )
            it.feo_planned_item_id = body.feo_planned_item_id
            it.over_plan = False
        else:
            # Явный null — пользователь снял выбор, осознанно оставляем без плана.
            it.feo_planned_item_id = None
            it.over_plan = False
        # Старая привязка (если была и реально сменилась) больше не имеет прежнего
        # владельца — если она была заведена автоматически и осиротела, деактивируем
        # (тот же порядок уборки, что и у move_or_detach_planned_item/clear-ветки выше).
        if _old_fpi_id_explicit is not None and _old_fpi_id_explicit != it.feo_planned_item_id:
            _old_fpi_explicit = await db.get(_FPIExplicit, _old_fpi_id_explicit)
            await deactivate_if_orphaned(db, _old_fpi_explicit)
    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): проверяем ДО записи
    # цены/кол-ва — прогнозные значения (patch частичный, недостающие берём из
    # текущей строки). admin_override (та же роль/флаг, что и для заморозки ТЗ
    # выше) — осознанный обход, как и у остальных гейтов превышения плана.
    # feo_planned_item_id/feo_category_id берём УЖЕ ФИНАЛЬНЫМИ с it (категория и
    # автозаведение применены выше).
    if _wants_tz_change and not (body.admin_override and current_user.role in ADMIN_ROLES):
        _prospective_qty = body.quantity if body.quantity is not None else it.quantity
        _prospective_price = body.unit_price if body.unit_price is not None else it.unit_price
        _prospective_total = (_prospective_qty or Decimal("0")) * (_prospective_price or Decimal("0"))
        # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): PATCH правит ОДНУ
        # позицию — «братья» (другие строки ЭТОЙ ЖЕ закупки на ту же плановую
        # позицию) лежат в БД, а не в памяти, как у create/PUT. Считаем их сумму
        # отдельным запросом и передаём как sibling_quantity/sibling_total, иначе
        # эта позиция пройдёт гейт поодиночке, даже если вместе с братьями план
        # уже превышен (см. assert_tz_batch_not_over_plan в feo_plan.py).
        _sib_qty = Decimal("0")
        _sib_total = Decimal("0")
        if it.feo_planned_item_id is not None:
            _sib_row = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(PurchaseItem.quantity), 0),
                        func.coalesce(func.sum(PurchaseItem.total_price), 0),
                    ).where(
                        PurchaseItem.purchase_id == pid,
                        PurchaseItem.feo_planned_item_id == it.feo_planned_item_id,
                        PurchaseItem.id != it.id,
                        func.coalesce(PurchaseItem.over_plan, False).is_(False),
                    )
                )
            ).one()
            _sib_qty = Decimal(str(_sib_row[0] or 0))
            _sib_total = Decimal(str(_sib_row[1] or 0))
        await assert_tz_not_over_plan(
            db,
            feo_planned_item_id=it.feo_planned_item_id,
            feo_category_id=it.feo_category_id,
            quantity=_prospective_qty,
            unit_price=_prospective_price,
            total_price=_prospective_total,
            item_name=body.item_name if body.item_name is not None else it.item_name,
            sibling_quantity=_sib_qty,
            sibling_total=_sib_total,
        )
    # Задача владельца, план zany-fluttering-mountain.md п.4 (2026-08-10): точечная
    # правка позиции — тоже «добавление позиции в категорию» (рост суммы позиции
    # ИЛИ смена её категории ФЭО на другую) — увеличивающее план действие. Раньше
    # здесь проверялось только «ТЗ не выше своей плановой позиции» (assert_tz_not_over_plan
    # выше) — сторону «категория не превышает финансирование ФЭО» (assert_no_unapproved_excess)
    # этот эндпоинт вообще не видел. Считаем ДО и ПОСЛЕ отдельно от _wants_tz_change
    # выше — смена ТОЛЬКО feo_category_id (без правки qty/price) тоже обязана
    # пройти гейт, а _wants_tz_change в этом случае False. Старая категория —
    # _cat_id_before_patch (снята ДО применения категории выше), новая — it.feo_category_id
    # (уже финальная).
    if not (body.admin_override and current_user.role in ADMIN_ROLES):
        _old_item_cat_id = _cat_id_before_patch
        _old_item_total = Decimal(str(it.total_price or 0))
        _new_item_cat_id = it.feo_category_id
        if body.quantity is not None or body.unit_price is not None:
            _new_qty_g = body.quantity if body.quantity is not None else it.quantity
            _new_price_g = body.unit_price if body.unit_price is not None else it.unit_price
            _new_item_total = (_new_qty_g or Decimal("0")) * (_new_price_g or Decimal("0"))
        else:
            _new_item_total = _old_item_total
        if _new_item_cat_id:
            _item_delta = _new_item_total - _old_item_total
            if _new_item_cat_id == _old_item_cat_id:
                if _item_delta > 0:
                    await assert_no_unapproved_excess(db, _new_item_cat_id, adding_amount=_item_delta)
            else:
                # Владелец (2026-08-12): «Когда заявка идёт с превышением ... должна
                # быть возможность передвижки, уменьшения». Боевой случай — позиции
                # «Перчатки нитриловые» нельзя было перенести 3710→3691, потому что у
                # их общего предка 3676 висело непогашенное превышение, хотя перенос
                # не тратит ни рубля сверху и как раз чинит перерасход категории-
                # источника. Смена категории — ПЕРЕКЛАДЫВАНИЕ, а не новая трата: сумма
                # уходит из старой категории (там это путь возврата в рамки плана — не
                # блокируется) и появляется в новой БЕЗ прироста суммарно по субсидии.
                # Блокируем ТОЛЬКО реальный прирост денег (если позиция одновременно с
                # переездом ещё и подорожала) — против НОВОЙ категории, а не всю сумму
                # позиции целиком.
                if _item_delta > 0:
                    await assert_no_unapproved_excess(db, _new_item_cat_id, adding_amount=_item_delta)
    if body.item_name is not None:
        name = body.item_name.strip()
        if not name:
            raise HTTPException(422, "Название позиции не может быть пустым")
        it.item_name = name
    if body.quantity is not None:
        it.quantity = body.quantity
    if body.unit is not None:
        it.unit = body.unit.strip() or None
    if body.unit_price is not None:
        it.unit_price = body.unit_price
    if body.quantity is not None or body.unit_price is not None:
        qty = it.quantity or Decimal("0")
        price = it.unit_price or Decimal("0")
        it.total_price = qty * price
        # Снимок плана (Шаг 1 «план ≠ факт»): пока закупка в статусе «План закупок» —
        # правка кол-ва/цены двигает и снимок плана вместе с ТЗ (план ещё формируется).
        # С «Ведётся работа» и далее сюда попасть можно только через admin_override
        # (гейт TZ_FROZEN_STATUSES выше) — снимок плана в этом случае намеренно НЕ
        # трогаем: план обязан остаться зафиксированным даже при осознанном обходе
        # заморозки ТЗ администратором.
        if p.status == "plan_schedule":
            it.planned_quantity = it.quantity
            it.planned_unit_price = it.unit_price
            it.planned_total = it.total_price
    # Зеркалим правку обратно в позицию заявки (принцип владельца, 2026-08-18):
    # раз W3 выше больше не запрещает править позицию прямо в закупке для
    # закупок, ушедших в план (см. комментарий у W3), позиция закупки и
    # связанная wish_items начнут расходиться — ровно тот дефект, на который
    # жаловался владелец («заявка показывает одну плановую позицию, дашборд
    # другую»). Симметрично зеркалированию в POST /api/feo-planned-items/map
    # (app/routers/feo_planned_items.py::map_purchase_item_to_planned).
    # Синхронизируем ТОЛЬКО то, что реально пришло/изменилось этим запросом —
    # не переписывать в заявке то, чего не трогали (выбранное на предыдущем
    # этапе не меняется само). _category_changing/it.feo_planned_item_id уже
    # финальные на этом месте (категория и автоподбор плана применены выше).
    if it.wish_item_id is not None:
        _patch_keys = set(body.model_dump(exclude_unset=True).keys())
        _qty_or_price_changed = "quantity" in _patch_keys or "unit_price" in _patch_keys
        # Явный выбор плановой позиции (см. _explicit_planned_item_chosen выше) тоже
        # обязан зеркалиться в WishItem — иначе он мирроится только при СМЕНЕ
        # категории, а «выбрал другую плановую позицию внутри той же категории»
        # (типичный случай диалога «Редактировать позицию») расходится с заявкой.
        if _patch_keys & {"item_name", "quantity", "unit", "unit_price"} or _category_changing or _explicit_planned_item_chosen:
            from app.models.wish_item import WishItem as _WishItem
            wi = await db.get(_WishItem, it.wish_item_id)
            if wi is not None:
                if "item_name" in _patch_keys:
                    wi.item_name = it.item_name
                if "quantity" in _patch_keys:
                    wi.quantity = it.quantity
                if "unit" in _patch_keys:
                    wi.unit = it.unit
                if "unit_price" in _patch_keys:
                    wi.unit_price = it.unit_price
                if _qty_or_price_changed:
                    wi.total_price = it.total_price
                if _category_changing or _explicit_planned_item_chosen:
                    wi.feo_category_id = it.feo_category_id
                    wi.feo_planned_item_id = it.feo_planned_item_id
    await db.flush()
    await _recalc_purchase_totals(p, db)
    if p and p.subsidy_id:
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение позиций закупки #{p.purchase_number or p.id}")
    # Шаг 2 «план ≠ факт»: admin_override обошёл заморозку ТЗ на объявленной
    # закупке — фиксируем в EntityChange, чтобы правка была видна в истории.
    if body.admin_override and current_user.role in ADMIN_ROLES and p.status in TZ_FROZEN_STATUSES:
        try:
            from app.models.entity_change import EntityChange as _EC
            if _old_qty is not None and str(_old_qty) != str(it.quantity):
                db.add(_EC(
                    entity_type='purchase_item', entity_id=it.id, field_name='quantity',
                    old_value=str(_old_qty), new_value=str(it.quantity),
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
            if _old_price is not None and str(_old_price) != str(it.unit_price):
                db.add(_EC(
                    entity_type='purchase_item', entity_id=it.id, field_name='unit_price',
                    old_value=str(_old_price), new_value=str(it.unit_price),
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        except Exception as _exc:
            import logging as _log
            _log.getLogger(__name__).warning("entity_change record failed for purchase_item admin_override: %s", _exc)
    await db.commit()
    return {
        "ok": True, "item_id": it.id, "item_name": it.item_name,
        "quantity": float(it.quantity or 0), "unit": it.unit,
        "unit_price": float(it.unit_price or 0), "total_price": float(it.total_price or 0),
        "feo_category_id": it.feo_category_id,
        "feo_planned_item_id": it.feo_planned_item_id,
        "planned_quantity": float(it.planned_quantity) if it.planned_quantity is not None else None,
        "planned_unit_price": float(it.planned_unit_price) if it.planned_unit_price is not None else None,
        "planned_total": float(it.planned_total) if it.planned_total is not None else None,
        # Плановые позиции следуют за сменой категории: не None, если плановая
        # позиция была общей с другими закупками/заявкой и её пришлось
        # отвязать вместо переезда (см. move_or_detach_planned_item) — фронт
        # обязан показать это пользователю, а не проглатывать молча.
        "plan_transfer_warning": _plan_transfer_warning,
    }


class _ItemSplitPart(BaseModel):
    quantity: Decimal
    feo_category_id: Optional[int] = None
    feo_planned_item_id: Optional[int] = None


class _ItemSplitBody(BaseModel):
    parts: list[_ItemSplitPart]


def _split_by_quantity(
    total,
    original_qty: Decimal,
    quantities: list[Decimal],
    precision: Decimal,
) -> list[Optional[Decimal]]:
    """Раскладывает `total` на доли, пропорциональные `quantities` от `original_qty`
    — владелец (2026-08-18, разбивка позиции закупки, см. split_purchase_item).

    `total is None` → весь результат None (снимка/поля не было — незачем его
    придумывать). Последняя доля получает остаток (`total − Σ предыдущих`), а не
    свою пропорциональную долю — иначе округление до `precision` может увести
    сумму долей от исходного `total` на копейки («баланс копейка в копейку»).
    """
    if total is None:
        return [None] * len(quantities)
    total_d = Decimal(str(total))
    n = len(quantities)
    shares: list[Decimal] = []
    running = Decimal("0")
    for i, q in enumerate(quantities):
        if i < n - 1:
            share = (total_d * q / original_qty).quantize(precision)
            shares.append(share)
            running += share
        else:
            shares.append(total_d - running)
    return shares


@router.post("/{pid}/items/{item_id}/split")
async def split_purchase_item(
    pid: int,
    item_id: int,
    body: _ItemSplitBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разбивка ОДНОЙ позиции закупки на несколько частей по разным категориям
    ФЭО / плановым позициям — владелец (2026-08-18, закупка №890 «Огнетушители»,
    status=ordered): 66 шт нужно разложить 41+25 по разным ФЭО, а добавление
    НОВОЙ позиции в проведённую/поставленную закупку справедливо запрещено
    (см. TZ_FROZEN_STATUSES у patch_purchase_item).

    Ключевое отличие от patch_purchase_item: разбивка НЕ меняет ни Σ количества,
    ни Σ суммы позиции (66 остаются 66, 54 318 ₽ остаются 54 318 ₽) — меняется
    только распределение по категориям/плановым позициям. Поэтому TZ_FROZEN_STATUSES
    ЗДЕСЬ СОЗНАТЕЛЬНО НЕ ПРИМЕНЯЕТСЯ (в отличие от patch_purchase_item) — заморозка
    защищает от изменения зафиксированного ТЗ, а не от его перекладки по одной и
    той же сумме между категориями.

    Порядок: СНАЧАЛА все проверки (включая гейт «ТЗ не выше плана» на
    получившийся набор частей целиком), ПОТОМ любые мутации/db.add — при отказе
    на любом шаге в сессии нет ни одной применённой правки (общий паттерн ORM-
    сессии в этом роутере: без явного db.commit() правки не переживают закрытие
    сессии, но здесь валидация вынесена перед мутациями even more строго — чтобы
    не зависеть от этого поведения).
    """
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    parts = body.parts
    if len(parts) < 2:
        raise HTTPException(400, "Для разбивки нужно минимум 2 части")
    for idx, part in enumerate(parts, start=1):
        if part.quantity is None or part.quantity <= 0:
            raise HTTPException(400, f"Количество части {idx} должно быть больше нуля")

    original_qty = Decimal(str(it.quantity or 0))
    quantities = [Decimal(str(pt.quantity)) for pt in parts]
    parts_qty_sum = sum(quantities, Decimal("0"))
    if parts_qty_sum != original_qty:
        raise HTTPException(
            409,
            f"Сумма количества частей ({parts_qty_sum}) не равна количеству позиции «{it.item_name}» "
            f"({original_qty}) — разбивка не меняет ни количество, ни сумму позиции, только распределение "
            "по категориям ФЭО.",
        )

    # Категории/плановые позиции частей — те же проверки и формулировки ошибок,
    # что и в patch_purchase_item (см. ветки feo_category_id / _explicit_planned_item_chosen).
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    for idx, part in enumerate(parts, start=1):
        if part.feo_category_id is not None:
            cat = await db.get(FeoCategory, part.feo_category_id)
            if not cat:
                raise HTTPException(404, f"Категория ФЭО части {idx} не найдена")
            if p.subsidy_id and cat.subsidy_id != p.subsidy_id:
                raise HTTPException(422, f"Категория ФЭО части {idx} относится к другой субсидии")
        if part.feo_planned_item_id is not None:
            fpi = await db.get(_FPI, part.feo_planned_item_id)
            if not fpi:
                raise HTTPException(404, f"Плановая позиция части {idx} не найдена")
            if not fpi.is_active:
                raise HTTPException(
                    409,
                    f"Плановая позиция «{fpi.name}» (часть {idx}) деактивирована (удалена из плана), "
                    "привязка к ней невозможна — выберите действующую или создайте новую.",
                )
            if part.feo_category_id is None or fpi.feo_category_id != part.feo_category_id:
                _fpi_cat_name = (await db.execute(
                    select(FeoCategory.name).where(FeoCategory.id == fpi.feo_category_id)
                )).scalar_one_or_none() or f"#{fpi.feo_category_id}"
                if part.feo_category_id is not None:
                    _target_cat_name = (await db.execute(
                        select(FeoCategory.name).where(FeoCategory.id == part.feo_category_id)
                    )).scalar_one_or_none() or f"#{part.feo_category_id}"
                else:
                    _target_cat_name = "без категории ФЭО"
                raise HTTPException(
                    409,
                    f"Плановая позиция «{fpi.name}» относится к категории «{_fpi_cat_name}», "
                    f"а часть {idx} — к категории «{_target_cat_name}». Выберите плановую позицию той же категории.",
                )

    # Договорные строки (contract_items.source_item_id == item_id): решение
    # владельца (2026-08-18) — разбить в ТОЙ ЖЕ пропорции количества. Если строк
    # больше одной, однозначного правила разложения нет («какая из двух строк
    # какую часть представляет?») — отказываем, а не гадаем.
    from app.models.contract_item import ContractItem
    contract_rows = (await db.execute(
        select(ContractItem).where(ContractItem.source_item_id == item_id)
    )).scalars().all()
    if len(contract_rows) > 1:
        raise HTTPException(
            409,
            f"К позиции «{it.item_name}» привязано {len(contract_rows)} строк договора — "
            "разбивка позиций с несколькими договорными строками не поддерживается.",
        )

    # unit_price всех частей — как у исходной позиции (правило 4: не принимается
    # из тела вовсе). total_price части = quantity × unit_price, последняя часть
    # добирает остаток (исходный total_price − сумма предыдущих) — так Σ total
    # сходится копейка в копейку даже при округлении quantity × unit_price.
    unit_price = it.unit_price if it.unit_price is not None else Decimal("0")
    original_total = Decimal(str(it.total_price or 0))
    n = len(parts)
    part_totals: list[Decimal] = []
    _running_total = Decimal("0")
    for i, q in enumerate(quantities):
        if i < n - 1:
            t = (q * unit_price).quantize(Decimal("0.01"))
            part_totals.append(t)
            _running_total += t
        else:
            part_totals.append(original_total - _running_total)

    # Снимок плана — пропорционально quantity; planned_unit_price копируется как
    # есть (не пересчитывается), planned_total — тем же правилом остатка, что и total_price.
    planned_quantities = _split_by_quantity(it.planned_quantity, original_qty, quantities, Decimal("0.0001"))
    planned_totals = _split_by_quantity(it.planned_total, original_qty, quantities, Decimal("0.01"))
    # НДС-поля и final_total — тоже денежные величины, зависящие от суммы позиции;
    # раскладываем той же пропорцией с остатком у последней части, иначе у новых
    # частей осталась бы сумма НДС/факт-итог ВСЕЙ исходной позиции целиком.
    vat_amounts = _split_by_quantity(it.vat_amount, original_qty, quantities, Decimal("0.01"))
    total_with_vats = _split_by_quantity(it.total_with_vat, original_qty, quantities, Decimal("0.01"))
    final_totals = _split_by_quantity(it.final_total, original_qty, quantities, Decimal("0.01"))

    # Гейт «ТЗ не выше плана» — на получившийся набор частей ЦЕЛИКОМ, через уже
    # существующий assert_tz_batch_not_over_plan (правило 8): он группирует по
    # feo_planned_item_id и накапливает, чтобы две части на одну плановую позицию
    # считались вместе, а не проходили гейт поодиночке. Лёгкие объекты
    # (SimpleNamespace), а не реальные ORM-строки — проверка идёт ДО каких-либо
    # мутаций/db.add (см. docstring выше).
    from types import SimpleNamespace
    _check_rows = [
        SimpleNamespace(
            item_name=it.item_name,
            quantity=quantities[i],
            unit_price=unit_price,
            total_price=part_totals[i],
            feo_planned_item_id=parts[i].feo_planned_item_id,
            feo_category_id=parts[i].feo_category_id,
            # over_plan исходной позиции наследуется частями (не сбрасывается в
            # False) — разбивка не меняет ни количество, ни сумму позиции в
            # целом, значит уже согласованное превышение плана не растёт;
            # assert_tz_batch_not_over_plan пропускает строки с over_plan=True
            # целиком (см. её docstring), поэтому легитимная разбивка
            # согласованной сверх-плана позиции не должна получать 409
            # (находка QA 2026-08-18).
            over_plan=bool(it.over_plan),
        )
        for i in range(n)
    ]
    await assert_tz_batch_not_over_plan(db, _check_rows, fallback_category_id=it.feo_category_id)

    # --- Все проверки пройдены — дальше только мутации. ---

    # Снимок «прочих» полей исходной позиции ДО мутации — копируется в новые части.
    # accepted_name/accepted_quantity/accepted_unit (стадия «Приняли») сознательно
    # НЕ копируются в новые части: это факт приёмки уже поставленного количества,
    # привязанный к конкретной приёмке, а не к распределению по ФЭО — слепое
    # копирование задвоило бы принятое количество на бумаге. Остаётся только у
    # исходной строки (первая часть).
    _src_item_name = it.item_name
    _src_item_type = it.item_type
    _src_unit = it.unit
    _src_product_id = it.product_id
    _src_country_origin = it.country_origin
    _src_contractor_id = it.contractor_id
    _src_contractor_inn = it.contractor_inn
    _src_contractor_name = it.contractor_name
    _src_match_confirmed = it.match_confirmed
    _src_vat_rate = it.vat_rate
    _src_receipt_id = it.receipt_id
    _src_needed_date = it.needed_date
    _src_final_unit_price = it.final_unit_price
    _src_planned_unit_price = it.planned_unit_price

    # Часть 1 — мутируем исходную строку: id, история (EntityChange), wish_item_id
    # и прочие ссылки сохраняются (правило: «исходная строка сохраняется»).
    it.quantity = quantities[0]
    it.total_price = part_totals[0]
    it.feo_category_id = parts[0].feo_category_id
    it.feo_planned_item_id = parts[0].feo_planned_item_id
    # over_plan НЕ сбрасывается — см. комментарий у _check_rows выше
    # (находка QA 2026-08-18): количество/сумма позиции не меняются разбивкой,
    # значит и статус согласованного превышения плана остаётся тем же.
    it.planned_quantity = planned_quantities[0]
    it.planned_total = planned_totals[0]
    it.vat_amount = vat_amounts[0]
    it.total_with_vat = total_with_vats[0]
    it.final_total = final_totals[0]

    created_items: list[PurchaseItem] = [it]
    for i in range(1, n):
        new_item = PurchaseItem(
            purchase_id=pid,
            product_id=_src_product_id,
            item_name=_src_item_name,
            item_type=_src_item_type,
            quantity=quantities[i],
            unit=_src_unit,
            unit_price=unit_price,
            total_price=part_totals[i],
            final_unit_price=_src_final_unit_price,
            final_total=final_totals[i],
            planned_quantity=planned_quantities[i],
            planned_unit_price=_src_planned_unit_price,
            planned_total=planned_totals[i],
            country_origin=_src_country_origin,
            feo_planned_item_id=parts[i].feo_planned_item_id,
            feo_category_id=parts[i].feo_category_id,
            match_confirmed=_src_match_confirmed,
            contractor_id=_src_contractor_id,
            contractor_inn=_src_contractor_inn,
            contractor_name=_src_contractor_name,
            vat_rate=_src_vat_rate,
            vat_amount=vat_amounts[i],
            total_with_vat=total_with_vats[i],
            receipt_id=_src_receipt_id,
            needed_date=_src_needed_date,
            # W1 (hard link заявка↔строка закупки): одна позиция заявки не может
            # соответствовать двум строкам закупки — у НОВЫХ частей wish_item_id
            # всегда NULL, привязку к заявке «наследует» только исходная строка.
            wish_item_id=None,
            # over_plan наследуется от исходной позиции — см. комментарий у
            # _check_rows выше (находка QA 2026-08-18).
            over_plan=bool(it.over_plan),
        )
        db.add(new_item)
        created_items.append(new_item)
    await db.flush()  # получить id новых позиций — нужны для source_item_id договорных строк и ответа

    # Договорные строки (максимум одна — отказ выше при 2+, правило владельца):
    # разбиваются в ТОЙ ЖЕ пропорции quantity, что и сама позиция закупки. Сумма
    # договора не меняется — та же логика остатка у последней части.
    new_contract_ids: list[int] = []
    if contract_rows:
        cr = contract_rows[0]
        cr_quantities = _split_by_quantity(cr.quantity, original_qty, quantities, Decimal("0.0001"))
        cr_totals = _split_by_quantity(cr.total, original_qty, quantities, Decimal("0.01"))
        cr.quantity = cr_quantities[0]
        cr.total = cr_totals[0]
        # source_item_id у исходной строки договора не меняется (it.id тот же).
        for i in range(1, n):
            new_cr = ContractItem(
                purchase_id=pid,
                source_item_id=created_items[i].id,
                contract_id=cr.contract_id,
                product_id=cr.product_id,
                name=cr.name,
                quantity=cr_quantities[i],
                unit=cr.unit,
                unit_price=cr.unit_price,
                total=cr_totals[i],
                vat_rate=cr.vat_rate,
                match_confirmed=cr.match_confirmed,
            )
            db.add(new_cr)
            new_contract_ids.append(new_cr)
        await db.flush()
        new_contract_ids = [c.id for c in new_contract_ids]

    await _recalc_purchase_totals(p, db)
    if p.subsidy_id:
        await _create_plan_graph_version(
            subsidy_id=p.subsidy_id, db=db, user=current_user,
            note=f"Авто-версия: разбивка позиции закупки #{p.purchase_number or p.id}",
        )

    # История — тем же способом, что patch_purchase_item (EntityChange), с
    # осмысленным описанием («разбита позиция N на M частей»); ошибка записи
    # истории не должна ронять уже прошедшую валидацию операцию (см. try/except
    # у admin_override-ветки patch_purchase_item выше).
    try:
        from app.models.entity_change import EntityChange as _EC
        _parts_desc = "; ".join(
            f"#{ci.id}: {q} шт / {t} ₽" for ci, q, t in zip(created_items, quantities, part_totals)
        )
        db.add(_EC(
            entity_type='purchase_item', entity_id=item_id, field_name='split',
            old_value=f"1 позиция «{_src_item_name}»: {original_qty} шт / {original_total} ₽",
            new_value=f"разбита на {n} частей — {_parts_desc}",
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
        ))
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed for purchase_item split: %s", _exc)

    await db.commit()
    for ci in created_items:
        await db.refresh(ci)

    return {
        "ok": True,
        "item_ids": [ci.id for ci in created_items],
        "parts": [
            {
                "item_id": ci.id,
                "quantity": float(ci.quantity or 0),
                "total_price": float(ci.total_price or 0),
                "feo_category_id": ci.feo_category_id,
                "feo_planned_item_id": ci.feo_planned_item_id,
            }
            for ci in created_items
        ],
        "contract_item_ids": new_contract_ids,
    }


@router.delete("/{pid}/items/{item_id}")
async def delete_purchase_item(
    pid: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Удаление одной позиции закупки с пересчётом сумм."""
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    it = await db.get(PurchaseItem, item_id)
    if not it or it.purchase_id != pid:
        raise HTTPException(404, "Позиция не найдена")
    p = await db.get(Purchase, pid)
    # W3: позиция привязана к заявке — удалять только через заявку
    if p is not None and p.wish_id is not None:
        raise HTTPException(
            409,
            f"Позиция привязана к заявке #{p.wish_id} — редактируйте её в заявке",
        )
    await db.delete(it)
    await db.flush()
    if p:
        await _recalc_purchase_totals(p, db)
    if p and p.subsidy_id:
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=f"Авто-версия: изменение позиций закупки #{p.purchase_number or p.id}")
    await db.commit()
    return {"ok": True, "deleted_item_id": item_id}


@router.delete("/bulk")
async def bulk_delete_purchases(
    ids: List[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('purchases')),
):
    deleted, failed = [], []
    for pid in ids:
        try:
            result = await db.execute(select(Purchase).where(Purchase.id == pid))
            p = result.scalar_one_or_none()
            if not p:
                failed.append({"id": pid, "reason": "Не найдено"})
                continue
            await db.delete(p)
            await db.flush()
            deleted.append(pid)
        except Exception as e:
            await db.rollback()
            failed.append({"id": pid, "reason": str(e)[:200]})
    if deleted:
        await db.commit()
    return {"deleted": deleted, "failed": failed}


@router.delete("/{pid}")
async def delete_purchase(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    # 27.4-09: авансовый owner может удалить свой отчёт; остальным нужен tab 'purchases'
    from app.auth.permissions import can_manage_purchase
    if not await can_manage_purchase(current_user, p, db):
        raise HTTPException(403, "Нет прав на удаление: нужна вкладка «Закупки» (роль менеджер и выше) либо авторство своего авансового отчёта")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.get("/by-contract/{contract_id}", response_model=List[PurchaseOutFull])
async def purchases_by_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Все закупки в рамках одного договора, отсортированные по framework_seq."""
    result = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items), selectinload(Purchase.contractor))
        .where(Purchase.contract_id == contract_id)
        .order_by(
            Purchase.framework_seq.asc().nulls_last(),
            Purchase.id.asc()
        )
    )
    purchases = result.scalars().all()
    out = []
    for p in purchases:
        d = PurchaseOutFull.model_validate(p)
        if p.contractor:
            d.contractor_name = p.contractor.name
        out.append(d)
    return out


@router.get("/{pid}/tasks")
async def list_purchase_tasks(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tasks linked to a purchase."""
    from app.models.task import Task
    from app.routers.task_visibility import _enrich_tasks
    from app.schemas.schemas import TaskOut
    result = await db.execute(
        select(Task).where(Task.purchase_id == pid).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    return await _enrich_tasks(list(tasks), db, current_user_id=current_user.id)


@router.get("/users-list")
async def users_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users available for assignment."""
    q = select(User.id, User.full_name, User.username, User.role)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(User.org_id.in_(org_ids))
    result = await db.execute(q.order_by(User.full_name))
    return [
        {"id": r.id, "name": r.full_name or r.username, "role": r.role}
        for r in result
    ]


# ── Purchase members (discussion participants) ───────────────────────────────

def _member_dict(m):
    return {
        "id": m.id,
        "purchase_id": m.purchase_id,
        "user_id": m.user_id,
        "role": m.role,
        "added_by_id": m.added_by_id,
        "username": m.user.username if m.user else "",
        "full_name": m.user.full_name if m.user else None,
        "added_by_name": (m.added_by.full_name or m.added_by.username) if m.added_by else None,
        "consent_pending": bool(getattr(m, "consent_pending", False)),
    }


@router.get("/{pid}/members")
async def list_purchase_members(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember
    result = await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )
    return [_member_dict(m) for m in result.scalars().all()]


@router.post("/{pid}/members")
async def add_purchase_member(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember, PurchaseEvent
    user_id = int(body.get("user_id", 0))
    role = body.get("role", "viewer")

    existing = await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == user_id,
        )
    )
    m = existing.scalar_one_or_none()
    is_new = m is None
    if m:
        m.role = role
    else:
        m = PurchaseMember(
            purchase_id=pid, user_id=user_id, role=role,
            added_by_id=current_user.id, consent_pending=(user_id != current_user.id),
        )
        db.add(m)
    await db.flush()

    u = await db.get(User, user_id)
    ev = PurchaseEvent(
        purchase_id=pid,
        user_id=current_user.id,
        event_type="member_added",
        data={"username": (u.full_name or u.username) if u else str(user_id)},
    )
    db.add(ev)
    await db.commit()
    await db.refresh(m)

    # Notify added user
    if u and u.id != current_user.id and is_new:
        try:
            purchase = await db.get(Purchase, pid)
            if purchase:
                if m.consent_pending:
                    from app.notifications import notify_purchase_consent_required
                    await notify_purchase_consent_required(
                        purchase, u, current_user.full_name or current_user.username
                    )
                else:
                    from app.notifications import notify_purchase_member_added
                    await notify_purchase_member_added(
                        purchase, u, current_user.full_name or current_user.username
                    )
        except Exception as e:
            logger.warning("Member add notify failed: %s", e)

    return _member_dict(m)


@router.delete("/{pid}/members/{user_id}")
async def remove_purchase_member(
    pid: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_event import PurchaseMember, PurchaseEvent
    result = await db.execute(
        select(PurchaseMember).where(
            PurchaseMember.purchase_id == pid,
            PurchaseMember.user_id == user_id,
        )
    )
    m = result.scalar_one_or_none()
    if m:
        u = await db.get(User, user_id)
        ev = PurchaseEvent(
            purchase_id=pid,
            user_id=current_user.id,
            event_type="member_removed",
            data={"username": (u.full_name or u.username) if u else str(user_id)},
        )
        db.add(ev)
        await db.delete(m)
        await db.commit()
    return {"ok": True}


# ── Purchase comments (chat) ────────────────────────────────────────────────

@router.get("/{pid}/comments")
async def list_purchase_comments(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    result = await db.execute(
        select(PurchaseComment)
        .where(PurchaseComment.purchase_id == pid)
        .order_by(PurchaseComment.created_at.asc())
    )
    return result.scalars().all()


@router.post("/{pid}/comments")
async def add_purchase_comment(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    import re as _re

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Комментарий не может быть пустым")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    comment = PurchaseComment(
        purchase_id=pid,
        user_id=current_user.id,
        user_name=current_user.full_name or current_user.username,
        text=text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Notify @mentioned users via Telegram
    try:
        from app.notifications import notify_user, _esc, _purchase_url
        mentions = _re.findall(r'@(\S+)', text)
        if mentions:
            all_users = (await db.execute(select(User))).scalars().all()  # superadmin-bypass-ok: @mention lookup for notifications
            clean_text = _re.sub(r'@[A-Za-zА-Яа-яёЁ\s]{2,40}', '', text).strip()
            clean_text = _re.sub(r'\s{2,}', ' ', clean_text) or text
            preview = _esc(clean_text[:150])
            subject = _esc(p.subject or f"Закупка №{p.purchase_number}")
            sender = _esc(current_user.full_name or current_user.username)
            msg = (
                f"💬 <b>Вас упомянули в закупке</b>\n\n"
                f"📌 <b>{subject}</b>\n"
                f"👤 <i>{sender}</i>:\n"
                f"{preview}"
            )
            for u in all_users:
                for m in mentions:
                    if (u.username and m.lower() == u.username.lower()) or \
                       (u.full_name and m.lower() in u.full_name.lower()):
                        if u.id != current_user.id:
                            await notify_user(u, msg,
                                               button_url=_purchase_url(p.id),
                                               button_label="Открыть закупку")
                            break
    except Exception:
        pass

    return comment


@router.delete("/{pid}/comments/{comment_id}")
async def delete_purchase_comment(
    pid: int, comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.purchase_comment import PurchaseComment
    c = await db.get(PurchaseComment, comment_id)
    if not c or c.purchase_id != pid:
        raise HTTPException(404, "Комментарий не найден")
    if c.user_id != current_user.id and current_user.role not in ("superadmin", "org_admin", "admin"):
        raise HTTPException(403, "Нельзя удалить чужой комментарий")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{pid}/broadcast")
async def broadcast_from_purchase(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Broadcast from purchase context."""
    from app.models.organization import Organization
    from app.models.department import Department
    from app.models.user_organization import UserOrganization as _UO_broadcast
    from app.models.purchase_comment import PurchaseComment
    from app.notifications import notify_user, _esc, _purchase_url

    BROADCAST_ROLES = ("superadmin", "org_admin", "admin", "manager")
    if current_user.role not in BROADCAST_ROLES:
        raise HTTPException(403, "Рассылка доступна только администраторам и менеджерам")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Текст сообщения обязателен")

    scope = body.get("scope", "")
    scope_id = body.get("scope_id")

    q = select(User).where(User.id != current_user.id)  # superadmin-bypass-ok: broadcast notifications, not a user-list endpoint returned to client
    if scope == "department" and scope_id:
        member_uids = select(_UO_broadcast.user_id).where(_UO_broadcast.dept_id == int(scope_id))
        q = q.where(User.id.in_(member_uids))
    elif scope == "organization" and scope_id:
        q = q.where(User.org_id == int(scope_id))
    elif scope == "all":
        org_ids = get_org_filter(current_user)
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
    else:
        raise HTTPException(422, "Укажите scope")

    users = (await db.execute(q)).scalars().all()

    sender_name = current_user.full_name or current_user.username
    subject = _esc(p.subject or f"Закупка №{p.purchase_number}")
    msg = (
        f"📢 <b>Рассылка</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 <i>{_esc(sender_name)}</i>:\n"
        f"{_esc(text)}"
    )

    sent = 0
    for u in users:
        if getattr(u, "telegram_id", None) or getattr(u, "max_chat_id", None):
            await notify_user(u, msg, button_url=_purchase_url(p.id), button_label="Открыть закупку")
            sent += 1

    # Save as comment
    scope_label = {"department": "отделу", "organization": "организации", "all": "всем"}.get(scope, scope)
    db.add(PurchaseComment(
        purchase_id=pid, user_id=current_user.id, user_name=sender_name,
        text=f"[Рассылка {scope_label}] {text}",
    ))
    await db.commit()

    return {"ok": True, "sent": sent, "total_users": len(users)}


@router.post("/{pid}/split")
async def split_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разбить закупку на N дочерних по группам позиций.

    Body: {"groups": [{"column_key": "str", "item_ids": [int, ...]}, ...]}
    - N <= 1 → 400.
    - До status in (contracted, delivered, paid) — разрешено всем, кто имеет доступ.
    - В этих статусах — только ADMIN_ROLES.
    - Наследует subsidy_id, feo_category_id, assigned_user_id, service_note_*, members.
    - Копирует PurchaseItem по item_ids в соответствующие дочерние.
    - Исходная помечается status='split'.
    """
    from app.models.purchase_event import PurchaseMember

    # Load purchase with items
    res = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id == pid)
    )
    purchase = res.scalar_one_or_none()
    if purchase is None:
        raise HTTPException(404, "Закупка не найдена")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        subsidy_res = await db.execute(select(Subsidy).where(Subsidy.id == purchase.subsidy_id))
        subsidy = subsidy_res.scalar_one_or_none()
        if subsidy and subsidy.org_id not in org_ids:
            raise HTTPException(403, "Нет доступа к закупке")

    LOCKED_STATUSES = {"contracted", "delivered", "paid"}
    if purchase.status in LOCKED_STATUSES and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Перераспределять закупку в статусе 'Договор' и далее могут только администраторы")
    if purchase.status == "split":
        raise HTTPException(400, "Закупка уже разбита")

    groups = body.get("groups") or []
    groups = [g for g in groups if g.get("item_ids")]
    if len(groups) < 2:
        raise HTTPException(400, "Разбиение требует минимум 2 непустые группы")

    # Validate all item_ids belong to this purchase and are unique + complete
    own_item_ids = {it.id for it in purchase.items}
    all_supplied_ids: list[int] = []
    for g in groups:
        for iid in g["item_ids"]:
            if iid not in own_item_ids:
                raise HTTPException(400, f"Позиция {iid} не принадлежит закупке {pid}")
            all_supplied_ids.append(iid)
    if len(all_supplied_ids) != len(set(all_supplied_ids)):
        raise HTTPException(400, "Одна позиция указана в нескольких группах")
    if set(all_supplied_ids) != own_item_ids:
        raise HTTPException(400, "Не все позиции распределены по группам")

    # Load members of source
    mem_res = await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )
    source_members = mem_res.scalars().all()

    items_by_id = {it.id: it for it in purchase.items}
    created_ids: list[int] = []

    try:
        for g in groups:
            column_key = (g.get("column_key") or "").strip() or "__uncategorized__"
            display_key = "Не определено" if column_key == "__uncategorized__" else column_key
            group_items = [items_by_id[iid] for iid in g["item_ids"]]
            total = sum(float(it.total_price or 0) for it in group_items)

            base_subject = (purchase.subject or purchase.item_name or "").strip()
            new_subject = f"{base_subject} — {display_key}".strip(" —") if base_subject else display_key

            new_p = Purchase(
                subsidy_id=purchase.subsidy_id,
                feo_category_id=purchase.feo_category_id,
                item_name=purchase.item_name or f"Закупка #{purchase.id}",
                subject=new_subject,
                planned_total_price=total,
                total_nmck=total,
                nmck=total,
                status="wishes" if purchase.status == "wishes" else "planned",
                assigned_user_id=purchase.assigned_user_id,
                service_note_text=purchase.service_note_text,
                service_note_by=purchase.service_note_by,
                parent_purchase_id=purchase.id,
            )
            db.add(new_p)
            await db.flush()
            created_ids.append(new_p.id)

            # Copy items into new purchase
            for src_it in group_items:
                db.add(PurchaseItem(
                    purchase_id=new_p.id,
                    product_id=src_it.product_id,
                    item_name=src_it.item_name,
                    item_type=src_it.item_type,
                    quantity=src_it.quantity,
                    unit=src_it.unit,
                    unit_price=src_it.unit_price,
                    total_price=src_it.total_price,
                    # Снимок плана (Шаг 1): разбиение закупки на подгруппы — переносим
                    # УЖЕ зафиксированный план исходной позиции, а не текущую цену
                    # (иначе разбиение задним числом «размораживало» бы план). Fallback
                    # на текущие значения только если снимка ещё не было (позиция создана
                    # до этой миграции/до бэкофилла).
                    planned_quantity=src_it.planned_quantity if src_it.planned_quantity is not None else src_it.quantity,
                    planned_unit_price=src_it.planned_unit_price if src_it.planned_unit_price is not None else src_it.unit_price,
                    planned_total=src_it.planned_total if src_it.planned_total is not None else src_it.total_price,
                    country_origin=src_it.country_origin,
                    feo_planned_item_id=src_it.feo_planned_item_id,
                    over_plan=getattr(src_it, 'over_plan', False) or False,
                ))
            # Copy members
            for m in source_members:
                db.add(PurchaseMember(
                    purchase_id=new_p.id,
                    user_id=m.user_id,
                    role=m.role,
                    added_by_id=current_user.id,
                    consent_pending=False,
                ))
            await db.flush()

        # Delete original items (explicit — keeps source row stable with status='split')
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
        purchase.status = "split"
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка разбиения закупки: {e}")

    return {"source_purchase_id": pid, "purchase_ids": created_ids, "count": len(created_ids)}


@router.post("/sync-from-contracts")
async def sync_all_purchases_from_contracts(
    only_mismatched: bool = Query(True, description="Только закупки где denorm-поля расходятся с contract"),
    current_user=Depends(require_action('purchases.edit')),
    db: AsyncSession = Depends(get_db),
):
    """Phase 26-lll: глобальный backfill денормализованных полей purchases из contracts.

    Для каждой purchase с contract_id IS NOT NULL прогоняет
    _sync_purchase_from_contract — выравнивает contract_number / contract_date /
    purchase_contract_type / contractor_id с реальным contracts.*.

    Чинит исторические рассинхронизации до Phase 26-j-1 (sync на save) и до
    Phase 26-k-2 (UPDATE 2 row backfill — недостаточно). Также покрывает баг
    «Контрагент пустой в реестре закупок» — раньше sync не копировал
    contractor_id из contract.
    """
    q = await db.execute(
        select(Purchase).where(Purchase.contract_id.is_not(None))
    )
    purchases_list = q.scalars().all()
    stats = {"total": len(purchases_list), "updated": 0, "skipped_no_contract": 0, "details": []}
    for p in purchases_list:
        before = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        await _sync_purchase_from_contract(p, db)
        after = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        if before != after:
            stats["updated"] += 1
            if len(stats["details"]) < 50:  # cap response size
                stats["details"].append({
                    "purchase_id": p.id,
                    "registry_number": p.registry_number,
                    "contract_id": p.contract_id,
                    "before": {"number": before[0], "date": str(before[1]) if before[1] else None,
                               "type": before[2], "contractor_id": before[3]},
                    "after": {"number": after[0], "date": str(after[1]) if after[1] else None,
                              "type": after[2], "contractor_id": after[3]},
                })
    await db.commit()


# =============================================================================
# Третья очередь плана (`synchronous-knitting-thacker.md`), Этапы 4-5:
# разнесение казначейских платежей по группам закупок (товары/услуги отдельно).
# Сервисный слой — app/services/payment_target.py (группы + подозрительные
# дубли) и app/services/payment_lookup.py (поиск кандидатов + attach).
# Права — subsidy.edit конкретной субсидии, тот же гейт, что у мероприятий
# (events.py::_get_subsidy_for_events) и импорта закупок.
# =============================================================================

async def _get_subsidy_for_payments(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await db.get(Subsidy, sid)
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    if not await has_org_key(current_user, db, s.org_id, 'subsidy.edit', subsidy_id=sid):
        raise HTTPException(
            403,
            "Разнесение платежей доступно только тому, у кого есть право редактировать субсидию",
        )
    return s


def _payment_group_to_dict(g) -> dict:
    return {
        "group_key": g.group_key,
        "subsidy_id": g.subsidy_id,
        "registry_number": g.registry_number,
        "contract_number": g.contract_number,
        "is_framework": g.is_framework,
        "contractor_id": g.contractor_id,
        "contractor_inn": g.contractor_inn,
        "contractor_name": g.contractor_name,
        "goods_amount": float(g.goods_amount),
        "services_amount": float(g.services_amount),
        "unspecified_amount": float(g.unspecified_amount),
        "purchase_ids": g.purchase_ids,
        "payments": [
            {
                "id": p.id,
                "purchase_id": p.purchase_id,
                "amount": float(p.amount) if p.amount is not None else None,
                "document_number": p.document_number,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "basis_label": p.basis_label,
                "expense_code": p.expense_code,
            }
            for p in g.payments
        ],
    }


def _suspicious_group_to_dict(s) -> dict:
    return {
        "registry_number": s.registry_number,
        "purchase_ids": s.purchase_ids,
        "row_count": s.row_count,
        "shared_amount": float(s.shared_amount) if s.shared_amount is not None else None,
        "reason": s.reason,
    }


def _payment_candidate_to_dict(c) -> dict:
    return {
        "bank_payment_id": c.bank_payment_id,
        "amount": float(c.amount),
        "kind": c.kind,
        "checks": c.checks,
        "auto": c.auto,
        "free": c.free,
        "reason": c.reason,
        "basis_label": c.basis_label,
        "payment_number": c.payment_number,
        "payment_date": c.payment_date.isoformat() if c.payment_date else None,
    }


class AttachPaymentsRequest(BaseModel):
    subsidy_id: int
    group_key: str
    bank_payment_ids: List[int]
    allocations: Optional[dict] = None   # {purchase_id: amount}, только для одного bank_payment_id


@router.post("/attach-payments")
async def attach_payments_endpoint(
    data: AttachPaymentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Явная загрузка платежей в группу — Этап 5. bank_payment_ids обычно один
    элемент (кандидат, выбранный вручную или auto-предложенный), но можно
    передать несколько сразу (каждый станет отдельной Payment-записью)."""
    await _get_subsidy_for_payments(data.subsidy_id, db, current_user)
    from app.services.payment_target import find_group
    from app.services.payment_lookup import attach, PaymentAttachError

    group = await find_group(db, data.subsidy_id, data.group_key)
    if not group:
        raise HTTPException(404, "Группа не найдена — пересчитайте /api/purchases/payment-groups")

    allocations = None
    if data.allocations:
        allocations = {int(k): Decimal(str(v)) for k, v in data.allocations.items()}

    try:
        created = await attach(db, group, data.bank_payment_ids, allocations=allocations)
    except PaymentAttachError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))

    await db.commit()
    return {
        "created": [
            {
                "id": p.id,
                "purchase_id": p.purchase_id,
                "amount": float(p.amount) if p.amount is not None else None,
                "bank_payment_id": p.bank_payment_id,
                "basis_label": p.basis_label,
            }
            for p in created
        ]
    }


@router.post("/match-payments")
async def match_payments_endpoint(
    subsidy_id: int = Query(...),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Прогон по субсидии (Этап 5): для каждой группы и каждой её суммы
    (товары/услуги) авто-разносит РОВНО ОДНОГО свободного кандидата, если он
    единственный (см. find_candidates — auto=True); неоднозначные и ненайденные
    остаются в отчёте без изменений. dry_run=true (умолчание) — ничего не
    пишет, только считает, что было бы сделано."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import build_groups, suspicious_groups
    from app.services.payment_lookup import find_candidates, attach, PaymentAttachError

    groups = await build_groups(db, subsidy_id)
    susp = await suspicious_groups(db, subsidy_id=subsidy_id)

    report = {
        "subsidy_id": subsidy_id,
        "dry_run": dry_run,
        "groups_total": len(groups),
        "attached": [],
        "ambiguous": [],
        "not_found": [],
        "suspicious": [_suspicious_group_to_dict(s) for s in susp],
    }

    for g in groups:
        cands = await find_candidates(db, g)
        group_attached: list[dict] = []
        group_ambiguous: list[dict] = []
        group_had_target = False

        for kind in ("goods", "services"):
            kind_amount = g.goods_amount if kind == "goods" else g.services_amount
            if not kind_amount:
                continue
            group_had_target = True
            kind_cands = cands.get(kind, [])
            auto_cand = next((c for c in kind_cands if c.auto), None)

            if auto_cand:
                if dry_run:
                    group_attached.append({
                        "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                        "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                    })
                else:
                    try:
                        created = await attach(db, g, [auto_cand.bank_payment_id])
                        group_attached.append({
                            "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                            "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                            "payment_ids": [p.id for p in created],
                        })
                    except PaymentAttachError as exc:
                        await db.rollback()
                        group_ambiguous.append({"kind": kind, "reason": str(exc)})
            elif kind_cands:
                reasons = sorted({c.reason for c in kind_cands if c.reason} or {"нет свободного кандидата"})
                group_ambiguous.append({"kind": kind, "reason": "; ".join(reasons)})

        if group_attached:
            report["attached"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_attached,
            })
        if group_ambiguous:
            report["ambiguous"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_ambiguous,
            })
        if group_had_target and not group_attached and not group_ambiguous:
            report["not_found"].append({"group_key": g.group_key, "registry_number": g.registry_number})

    if not dry_run:
        await db.commit()

    return report
    return stats
