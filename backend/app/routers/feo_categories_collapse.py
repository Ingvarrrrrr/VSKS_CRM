"""«Сделать из категории просто плановую позицию» (владелец, 2026-09-20).

Действие над 240 боевыми категориями-обёртками, оставшимися от старого
фолбэка импорта ФЭО (см. докстринг app.services.feo_category_collapse) — лист
БЕЗ подкатегорий, содержащий РОВНО одну активную плановую позицию своего же
имени, сворачивается: позиция переезжает в родительскую категорию, ссылки
закупок/товаров/заявок на удаляемую категорию — тоже, сама категория
удаляется.

Правило №5 (модульность): этот файл несёт ТОЛЬКО HTTP-оркестрацию (гейты,
коммит, сборка ответа) — вся проверочная/переносная логика в
app.services.feo_category_collapse (Правило №6 — не дублировать условия
между GET-превью и POST-действием).

Подключается как ПОД-роутер feo_categories.router (`router.include_router`
в конце feo_categories.py) — у этого APIRouter здесь сознательно НЕТ
собственного prefix: FastAPI применяет prefix РОДИТЕЛЯ ("/api/feo-categories")
к каждому пути при include_router, поэтому пути ниже пишутся АБСОЛЮТНО от
корня subresource (см. app.routers.feo_import/feo_tree_ops про этот же
раздельный-файл-приём, хотя те регистрируются в routes.py, а не через
include_router — здесь иначе по прямому указанию задачи, чтобы не трогать
routes.py).

Права — та же матрица, что и у DELETE /feo-categories/{id} (require_tab
('feo_categories') как FastAPI-гейт видимости + _require_feo_category_write
по субсидии ЗАГРУЖЕННОЙ из БД категории как гейт записи, см. докстринг
_require_feo_category_write в feo_categories.py — субсидия ИЗ БД, а не из
тела/query, чтобы право нельзя было обойти подменой поля).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.feo_category_collapse import (
    bulk_relink_category_refs,
    category_own_feo_pair,
    check_collapse_conflict,
    relink_remaining_planned_items,
    transfer_feo_money,
)
from app.services.text_match import normalize as _norm_name

router = APIRouter(tags=["feo_categories_collapse"])


def _detail_message(detail) -> str:
    """HTTPException.detail здесь бывает либо строкой, либо {"message": ...,
    ...} (как у блокировки закупками) — единая точка извлечения текста для
    blocked_reason, чтобы GET и POST показывали дословно один и тот же текст
    (Правило №6)."""
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


@router.get("/collapse-candidates")
async def get_collapse_candidates(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Предпросмотр кандидатов на свёртку: категории субсидии БЕЗ
    подкатегорий, ровно с ОДНОЙ активной плановой позицией. blocked_reason
    заполняется ТЕМИ ЖЕ проверками, что и POST (check_collapse_conflict) —
    не падает 409, а сообщает причину в списке (родительская категория не
    задана / есть закупки в работе)."""
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not cats:
        return {"items": []}

    by_id = {c.id: c for c in cats}
    has_children: set[int] = set()
    for c in cats:
        if c.parent_id is not None:
            has_children.add(c.parent_id)
    leaf_ids = [c.id for c in cats if c.id not in has_children]
    if not leaf_ids:
        return {"items": []}

    items_rows = (await db.execute(
        select(FeoPlannedItem)
        .where(FeoPlannedItem.feo_category_id.in_(leaf_ids))
        .where(FeoPlannedItem.is_active.is_(True))
        .order_by(FeoPlannedItem.feo_category_id, FeoPlannedItem.id)
    )).scalars().all()
    items_by_cat: dict[int, list] = {}
    for it in items_rows:
        items_by_cat.setdefault(it.feo_category_id, []).append(it)

    out = []
    for cat_id in leaf_ids:
        its = items_by_cat.get(cat_id) or []
        # Селекция кандидата (не просто blocked_reason): категория с 0 или
        # 2+ активными позициями в список вообще не попадает — «сворачивать
        # нечего»/«не ровно одна» это разные категории задач, не эта функция.
        if len(its) != 1:
            continue
        cat = by_id[cat_id]
        item = its[0]
        parent = by_id.get(cat.parent_id) if cat.parent_id is not None else None

        blocked_reason: Optional[str] = None
        try:
            await check_collapse_conflict(db, cat)
        except HTTPException as e:
            blocked_reason = _detail_message(e.detail)

        own = category_own_feo_pair(cat)
        out.append({
            "category_id": cat.id,
            "name": cat.name,
            "parent_id": cat.parent_id,
            "parent_name": parent.name if parent else None,
            "planned_item_id": item.id,
            "planned_item_name": item.name,
            "is_name_duplicate": _norm_name(cat.name) == _norm_name(item.name),
            "category_feo_amount": float(own[0]) if own else None,
            "item_amount": float(item.amount) if item.amount is not None else None,
            "blocked_reason": blocked_reason,
        })
    return {"items": out}


async def _perform_collapse(db: AsyncSession, cat_id: int, current_user) -> dict:
    """Единственная точка выполнения свёртки — переиспользуется и
    POST /{cat_id}/collapse-to-item (одна категория, ошибка = 409 наружу), и
    POST /collapse-bulk (много категорий, каждая в своей транзакции — см.
    докстринг ниже). Коммитит сама."""
    from app.routers import feo_categories as fc

    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == cat_id)
    )).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # Гейт записи — субсидия ИЗ ЗАГРУЖЕННОЙ категории (та же защита от
    # обхода подменой поля, что и у DELETE/PUT в feo_categories.py).
    await fc._require_feo_category_write(current_user, db, cat.subsidy_id)

    item = await check_collapse_conflict(db, cat)
    parent_id = cat.parent_id  # родитель гарантирован check_collapse_conflict

    # (а) деньги ФЭО категории → на позицию, если у позиции своих нет
    transfer_feo_money(cat, item)

    # (б) ссылки закупок/товаров/заявок cat_id → parent_id
    moved_refs = await bulk_relink_category_refs(db, cat.id, parent_id)

    # (в) сама позиция → parent_id через существующую move_planned_item_to_category
    # (та же функция, что и у PUT /feo-planned-items/{id} и автопереноса —
    # Правило №6, не вторая копия переноса; заодно синхронизирует
    # purchase_items/wish_items, привязанные к ЭТОЙ позиции через
    # feo_planned_item_id, которые bulk-релинк по feo_category_id мог не
    # захватить, если их feo_category_id почему-то уже разошёлся).
    from app.services.plan_autoassign import move_planned_item_to_category
    await move_planned_item_to_category(db, item, parent_id)

    # Подчистить архивные (неактивные) плановые позиции, если остались под
    # категорией — иначе ON DELETE CASCADE feo_planned_items.feo_category_id
    # унесёт их вместе с категорией ниже (см. докстринг функции).
    await relink_remaining_planned_items(db, cat.id, parent_id, skip_item_id=item.id)

    # (д) пересчёт/снимок версии плана — тот же механизм, что и у PUT
    # категории/плановой позиции при изменении плановых показателей.
    from app.services.plan_graph_versions import _create_plan_graph_version
    await _create_plan_graph_version(
        subsidy_id=cat.subsidy_id, db=db, user=current_user,
        note=f"Авто-версия: категория «{cat.name}» свёрнута в плановую позицию «{item.name}»",
    )

    # (г) удалить саму категорию — ссылки и позиция уже переехали, полный
    # _purge_feo_categories здесь не нужен (тот ОБНУЛЯЕТ ссылки и УДАЛЯЕТ
    # позиции — прямо противоположно тому, что нужно при свёртке).
    await db.flush()
    await db.execute(FeoCategory.__table__.delete().where(FeoCategory.id == cat.id))
    await db.commit()

    return {
        "category_id": cat_id,
        "planned_item_id": item.id,
        "parent_id": parent_id,
        "moved_refs": moved_refs,
    }


@router.post("/{cat_id}/collapse-to-item")
async def collapse_category_to_item(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    return await _perform_collapse(db, cat_id, current_user)


class _CollapseBulkBody(BaseModel):
    category_ids: List[int]


@router.post("/collapse-bulk")
async def collapse_bulk(
    body: _CollapseBulkBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Массовая свёртка — по одной категории, КАЖДАЯ в своей транзакции:
    ошибка одной (409/404) не откатывает уже свёрнутые (см. докстринг
    _perform_collapse — коммитит сама на каждой успешной итерации; на
    ошибке явный rollback() отменяет только незакоммиченные изменения ЭТОЙ
    попытки, предыдущие commit() уже необратимы)."""
    results = []
    for cat_id in body.category_ids:
        try:
            res = await _perform_collapse(db, cat_id, current_user)
            results.append({
                "category_id": cat_id, "ok": True, "error": None,
                "planned_item_id": res["planned_item_id"],
            })
        except HTTPException as e:
            await db.rollback()
            results.append({
                "category_id": cat_id, "ok": False,
                "error": _detail_message(e.detail), "planned_item_id": None,
            })
    return {"results": results}
