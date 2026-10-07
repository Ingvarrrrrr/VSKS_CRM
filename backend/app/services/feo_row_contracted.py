"""feo_row_contracted.py — разрез «Законтрактовано / из них заказано /
зарезервировано» ПО КАТЕГОРИИ ФЭО субсидии (владелец, 06.10.2026, план
.planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаг 2): строка дерева ФЭО
нуждается в тех же трёх числах, что уже существуют на уровне субсидии
(app.services.stage_cumulative.contracted_total_by_subsidy/
contracted_not_ordered_by_subsidy), но per-категорию, без поддерева
(СОБСТВЕННЫЕ суммы — рекурсию по дереву делает вызывающий код, как и везде в
feo_plan_tree.py).

ПРАВИЛО №6 — ни одно число здесь НЕ пересчитывается второй формулой:
  - "contracted" — app.services.stage_cumulative.contracted_rows_by_category()
    (тот же построчный источник, из которого contracted_total_by_subsidy
    теперь суммирует свой subsidy-level "amount" — см. её докстринг; инвариант
    Σ contracted по категориям субсидии == contracted_total_by_subsidy
    гарантирован ПО ПОСТРОЕНИЮ, обе читают один словарь).
  - "ordered" — committed_status_predicate() (committed_amounts.py), та же
    пара статусных множеств (SINGLE_COMMITTED_STATUSES/FRAMEWORK_COMMITTED_STATUSES),
    что и "законтрактовано" в реестре договоров, С добавочным условием
    "framework-закупка без parent_purchase_id (голова) исключена" — голова не
    заказ, деньги заказа несёт сам заказ (parent_purchase_id IS NOT NULL).
  - "reserved" — stage_cumulative.reserved_child_predicate() (та же формула,
    что уже даёт contracted_not_ordered_by_subsidy() для карточки «Можно
    перераспределить», здесь просто разрезана по категории вместо субсидии).

Категория — Purchase.feo_category_id (не PurchaseItem-уровень: "законтрактовано"/
"заказано"/"резерв" по определению — о закупке/заказе ЦЕЛИКОМ, та же
гранулярность, что и у всех источников выше, ни один из которых не делает
item-level разрез)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_ as sqland, func, not_ as sqlnot, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.user import User
from app.services.committed_amounts import (
    FRAMEWORK_COMMITTED_STATUSES,
    SINGLE_COMMITTED_STATUSES,
    committed_status_predicate,
    is_framework_purchase_expr,
)
from app.services.purchase_amounts import aggregate_scope_expr, effective_amount_expr
from app.services.stage_cumulative import (
    committed_uncounted_expr,
    contracted_rows_by_category,
    reserved_child_predicate,
)


async def feo_row_contract_totals(db: AsyncSession, subsidy_id: int) -> dict[Optional[int], dict]:
    """{feo_category_id|None: {"contracted": float, "ordered": float, "reserved": float}}
    — None = «без категории». Собственные суммы категории (без поддерева —
    клиент этой функции, если нужен разрез по дереву, суммирует сам, как и
    compute_feo_plan_tree делает для любых других per-категорийных чисел)."""
    result: dict[Optional[int], dict] = {}

    def _bucket(cat_id: Optional[int]) -> dict:
        return result.setdefault(cat_id, {"contracted": 0.0, "ordered": 0.0, "reserved": 0.0})

    # ── contracted ────────────────────────────────────────────────────────
    cat_rows = await contracted_rows_by_category(db, subsidy_ids=[subsidy_id])
    for (sid, cat_id), amt in cat_rows.items():
        if sid != subsidy_id:
            continue
        _bucket(cat_id)["contracted"] += amt

    # ── ordered ───────────────────────────────────────────────────────────
    # Рамочная ГОЛОВА (is_fw И parent_purchase_id IS NULL) исключена — не
    # заказ, см. докстринг модуля; разовые (is_fw=False) этим не затрагиваются.
    is_fw = is_framework_purchase_expr(Purchase)
    not_unordered_head = sqlnot(sqland(is_fw, Purchase.parent_purchase_id.is_(None)))
    ordered_stmt = (
        select(
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.stopped_at.is_(None))
        .where(committed_status_predicate(Purchase))
        .where(not_unordered_head)
        .group_by(Purchase.feo_category_id)
    )
    for r in (await db.execute(ordered_stmt)).all():
        _bucket(r.cat_id)["ordered"] += float(r.amt or 0)

    # ── reserved ──────────────────────────────────────────────────────────
    reserved_stmt = (
        select(
            Purchase.feo_category_id.label("cat_id"),
            func.coalesce(func.sum(effective_amount_expr()), 0).label("amt"),
        )
        .where(Purchase.subsidy_id == subsidy_id)
        .where(Purchase.stopped_at.is_(None))
        .where(reserved_child_predicate())
        .group_by(Purchase.feo_category_id)
    )
    for r in (await db.execute(reserved_stmt)).all():
        _bucket(r.cat_id)["reserved"] += float(r.amt or 0)

    return result


_ROW_FIELDS = (
    Purchase.id, Purchase.registry_number, Purchase.purchase_number, Purchase.contractor_id,
    Purchase.reimbursement_user_id, Purchase.purchase_contract_type, Purchase.status,
    Purchase.subject, Purchase.feo_category_id,
)


def _row_base(r) -> dict:
    return {
        "purchase_id": r.id,
        "registry_number": r.registry_number or (str(r.purchase_number) if r.purchase_number else None),
        "contractor": None,  # заполняется вызывающим кодом после сбора contractor_id
        "reimbursement_user": None,  # то же для reimbursement_user_id
        "contract_type": r.purchase_contract_type,
        "status": r.status,
        "subject": r.subject,
        "feo_category_id": r.feo_category_id,
        "feo_category_name": None,  # заполняется вызывающим кодом
        "_contractor_id": r.contractor_id,
        "_reimbursement_user_id": r.reimbursement_user_id,
    }


async def _enrich_rows(db: AsyncSession, rows: list[dict], cat_names: dict[int, str]) -> list[dict]:
    """Проставляет имена контрагента/пользователя-возмещения/категории ПОСТФАКТУМ
    (один доп. запрос на список id, не N+1) и убирает служебные ключи `_*`."""
    contractor_ids = {r["_contractor_id"] for r in rows if r["_contractor_id"]}
    user_ids = {r["_reimbursement_user_id"] for r in rows if r["_reimbursement_user_id"]}
    contractor_names: dict[int, str] = {}
    user_names: dict[int, str] = {}
    if contractor_ids:
        contractor_names = {
            c.id: c.name for c in (
                await db.execute(select(Contractor).where(Contractor.id.in_(contractor_ids)))
            ).scalars().all()
        }
    if user_ids:
        user_names = {
            u.id: u.full_name for u in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all()
        }
    for r in rows:
        contractor_id = r.pop("_contractor_id", None)
        reimbursement_user_id = r.pop("_reimbursement_user_id", None)
        r["contractor"] = contractor_names.get(contractor_id) if contractor_id else None
        r["reimbursement_user"] = user_names.get(reimbursement_user_id) if reimbursement_user_id else None
        r["feo_category_name"] = cat_names.get(r["feo_category_id"]) if r["feo_category_id"] else None
    return rows


async def feo_row_drill(
    db: AsyncSession, *, subsidy_id: int, cat_ids: list[int], kind: str,
) -> dict:
    """Построчный состав суммы строки дерева для ОДНОГО из пяти kind
    (in_purchases/contracted/ordered/reserved/unallocated), по ПОДДЕРЕВУ
    категорий `cat_ids` (вызывающий роутер сам раскрывает поддерево через
    `_collect_subtree_ids`, Правило №6 — переиспользуем существующий
    рекурсивный сборщик, не второй). `total` ОБЯЗАН совпадать с суммой этого
    kind по тем же категориям из feo_row_contract_totals (in_purchases — из
    planned-purchase-totals) — см. инвариант-тест."""
    from app.models.feo_category import FeoCategory

    cat_names = {
        c.id: c.name for c in (
            await db.execute(select(FeoCategory).where(FeoCategory.id.in_(cat_ids)))
        ).scalars().all()
    }
    rows: list[dict] = []

    if kind == "in_purchases":
        from app.routers.purchase_budget import PLANNED_STATUSES

        cat_col = func.coalesce(PurchaseItem.feo_category_id, Purchase.feo_category_id)
        stmt = (
            select(
                Purchase.id, Purchase.registry_number, Purchase.purchase_number, Purchase.contractor_id,
                Purchase.reimbursement_user_id, Purchase.purchase_contract_type, Purchase.status,
                Purchase.subject, cat_col.label("feo_category_id"),
                func.coalesce(func.sum(PurchaseItem.total_price), 0).label("amt"),
            )
            .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
            .where(Purchase.subsidy_id == subsidy_id)
            .where(Purchase.status.in_(list(PLANNED_STATUSES)))
            .where(Purchase.stopped_at.is_(None))
            .where(cat_col.in_(cat_ids))
            .where(aggregate_scope_expr())
            .group_by(
                Purchase.id, Purchase.registry_number, Purchase.purchase_number, Purchase.contractor_id,
                Purchase.reimbursement_user_id, Purchase.purchase_contract_type, Purchase.status,
                Purchase.subject, cat_col,
            )
        )
        for r in (await db.execute(stmt)).all():
            d = _row_base(r)
            d["amount"] = float(r.amt or 0)
            rows.append(d)

    elif kind == "ordered":
        is_fw = is_framework_purchase_expr(Purchase)
        not_unordered_head = sqlnot(sqland(is_fw, Purchase.parent_purchase_id.is_(None)))
        stmt = (
            select(*_ROW_FIELDS, effective_amount_expr().label("amt"))
            .where(Purchase.subsidy_id == subsidy_id)
            .where(Purchase.stopped_at.is_(None))
            .where(committed_status_predicate(Purchase))
            .where(not_unordered_head)
            .where(Purchase.feo_category_id.in_(cat_ids))
        )
        for r in (await db.execute(stmt)).all():
            d = _row_base(r)
            d["amount"] = float(r.amt or 0)
            rows.append(d)

    elif kind == "reserved":
        stmt = (
            select(*_ROW_FIELDS, effective_amount_expr().label("amt"))
            .where(Purchase.subsidy_id == subsidy_id)
            .where(Purchase.stopped_at.is_(None))
            .where(reserved_child_predicate())
            .where(Purchase.feo_category_id.in_(cat_ids))
        )
        for r in (await db.execute(stmt)).all():
            d = _row_base(r)
            d["amount"] = float(r.amt or 0)
            rows.append(d)

    elif kind in ("contracted", "unallocated"):
        # single — одна закупка на контракт (типовой случай): amount = её
        # собственный effective_amount_expr(); контракты с НЕСКОЛЬКИМИ
        # committed-закупками делят max(recorded, Σ actual) пропорционально
        # их фактической доле — ТА ЖЕ математика, что и
        # contracted_rows_by_category() (тот же результат на одну категорию,
        # здесь просто с полями закупки для отображения строки).
        single_stmt = (
            select(
                Contract.id.label("contract_id"), Contract.max_amount,
                *_ROW_FIELDS,
                effective_amount_expr().label("actual"),
            )
            .join(Purchase, Purchase.contract_id == Contract.id)
            .where(Contract.status == "active")
            .where(Contract.contract_type == "single")
            .where(Contract.subsidy_id == subsidy_id)
            .where(Purchase.status.in_(list(SINGLE_COMMITTED_STATUSES)))
        )
        single_rows_raw = (await db.execute(single_stmt)).all()
        by_contract: dict[int, list] = {}
        for r in single_rows_raw:
            by_contract.setdefault(r.contract_id, []).append(r)
        single_rows: list[dict] = []
        for contract_id, prows in by_contract.items():
            recorded = float(prows[0].max_amount) if prows[0].max_amount is not None else 0.0
            total_actual = sum(float(p.actual or 0) for p in prows)
            final_total = max(recorded, total_actual)
            if final_total <= 0:
                continue
            for p in prows:
                share = final_total * (float(p.actual or 0) / total_actual) if total_actual > 0 else final_total / len(prows)
                d = _row_base(p)
                d["amount"] = share
                d["_remaining"] = 0.0  # single не несёт «остатка лимита» — только framework_with_amount
                single_rows.append(d)

        # framework_with_amount (владелец, правка 🔵 07.10.2026 — пересмотр В3,
        # см. докстринг stage_cumulative.contracted_rows_by_category): заказы
        # (ordered+reserved — ОБЕ группы) — КАЖДЫЙ своей строкой/суммой в
        # своей категории; остаток лимита max(0, лимит − Σ(ordered+reserved))
        # — ОДНОЙ строкой (на голову, если она есть и/или имеет категорию,
        # иначе фолбэк на категорию заказов/«без категории» — та же логика,
        # что в SQL-источнике, не вторая формула).
        fwa_contracts_stmt = (
            select(Contract.id.label("contract_id"), Contract.max_amount)
            .where(Contract.status == "active")
            .where(Contract.contract_type == "framework_with_amount")
            .where(Contract.subsidy_id == subsidy_id)
        )
        fwa_contracts = (await db.execute(fwa_contracts_stmt)).all()
        fwa_contract_ids = [c.contract_id for c in fwa_contracts]

        fwa_head_stmt = (
            select(Contract.id.label("contract_id"), *_ROW_FIELDS)
            .join(Purchase, Purchase.contract_id == Contract.id)
            .where(Contract.status == "active")
            .where(Contract.contract_type == "framework_with_amount")
            .where(Contract.subsidy_id == subsidy_id)
            # Голова — parent_purchase_id IS NULL (тот же критерий, что
            # stage_cumulative.contracted_rows_by_category), без требования к
            # Purchase.purchase_contract_type — см. её комментарий.
            .where(Purchase.parent_purchase_id.is_(None))
        )
        head_by_contract = {r.contract_id: r for r in (await db.execute(fwa_head_stmt)).all()}

        fwa_rows: list[dict] = []
        fwa_children_by_contract: dict[int, list] = {}
        if fwa_contract_ids:
            fwa_children_stmt = (
                select(Purchase.contract_id.label("contract_id"), *_ROW_FIELDS, effective_amount_expr().label("amt"))
                .where(Purchase.contract_id.in_(fwa_contract_ids))
                .where(Purchase.parent_purchase_id.isnot(None))
                .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
            )
            for r in (await db.execute(fwa_children_stmt)).all():
                fwa_children_by_contract.setdefault(r.contract_id, []).append(r)
                d = _row_base(r)
                d["amount"] = float(r.amt or 0)
                d["_remaining"] = 0.0
                fwa_rows.append(d)

        for c in fwa_contracts:
            kids = fwa_children_by_contract.get(c.contract_id, [])
            total_children = sum(float(k.amt or 0) for k in kids)
            recorded = float(c.max_amount) if c.max_amount is not None else 0.0
            remainder = max(0.0, recorded - total_children)
            if remainder <= 0:
                continue
            head_row = head_by_contract.get(c.contract_id)
            head_cat = head_row.feo_category_id if head_row is not None else None
            if head_cat is None:
                kid_cats = {k.feo_category_id for k in kids}
                head_cat = next(iter(kid_cats)) if len(kid_cats) == 1 else None
            if head_row is not None:
                d = _row_base(head_row)
            else:
                d = {
                    "purchase_id": None, "registry_number": None, "contractor": None,
                    "reimbursement_user": None, "contract_type": "framework_with_amount",
                    "status": None, "subject": "Остаток лимита договора (без головы)",
                    "feo_category_id": None, "feo_category_name": None,
                    "_contractor_id": None, "_reimbursement_user_id": None,
                }
            d["feo_category_id"] = head_cat
            d["amount"] = remainder
            d["_remaining"] = remainder
            fwa_rows.append(d)

        # framework_cumulative — Σ заказов-детей (ordered+reserved — та же
        # формула, что у framework_with_amount выше, владелец 🟣 07.10.2026),
        # каждый своей строкой.
        cfc_stmt = (
            select(*_ROW_FIELDS, effective_amount_expr().label("amt"))
            .join(Contract, Purchase.contract_id == Contract.id)
            .where(Contract.status == "active")
            .where(Contract.contract_type == "framework_cumulative")
            .where(Purchase.subsidy_id == subsidy_id)
            .where(sqlor(Purchase.status.in_(list(FRAMEWORK_COMMITTED_STATUSES)), reserved_child_predicate()))
        )
        cfc_rows: list[dict] = []
        for r in (await db.execute(cfc_stmt)).all():
            d = _row_base(r)
            d["amount"] = float(r.amt or 0)
            d["_remaining"] = 0.0
            cfc_rows.append(d)

        # committed-закупки без активного контракта известного типа.
        uncounted_stmt = (
            select(*_ROW_FIELDS, effective_amount_expr().label("amt"))
            .outerjoin(Contract, Purchase.contract_id == Contract.id)
            .where(Purchase.subsidy_id == subsidy_id)
            .where(Purchase.stopped_at.is_(None))
            .where(committed_uncounted_expr())
        )
        uncounted_rows: list[dict] = []
        for r in (await db.execute(uncounted_stmt)).all():
            d = _row_base(r)
            d["amount"] = float(r.amt or 0)
            d["_remaining"] = 0.0
            uncounted_rows.append(d)

        all_rows = single_rows + fwa_rows + cfc_rows + uncounted_rows
        all_rows = [r for r in all_rows if r["feo_category_id"] in cat_ids]
        if kind == "unallocated":
            # Остаток лимита рамочных-с-суммой (лимит − заказано − зарезервировано
            # по НЕЙ) ≠ 0 — единственный источник остатка, та же голова что в contracted.
            for r in all_rows:
                r["amount"] = r.pop("_remaining", 0.0)
            rows = [r for r in all_rows if abs(r["amount"]) > 0.005]
        else:
            for r in all_rows:
                r.pop("_remaining", None)
            rows = all_rows
    else:
        raise ValueError(f"unknown kind: {kind}")

    rows = await _enrich_rows(db, rows, cat_names)
    total = sum(r["amount"] for r in rows)
    return {"rows": rows, "total": total}
