"""Комментарии (мини-чат) к плановым позициям ФЭО и категориям дерева ФЭО —
Волна 4, п.16 владельца (2026-09-13). См. докстринг модели app/models/
feo_comment.py для обоснования схемы данных.

Права (владелец: «смотри, как устроен доступ к плановым позициям... и не
заводи новых прав, если хватает существующих») — ПЕРЕИСПОЛЬЗУЕМ 1:1 матрицу
из app/routers/feo_planned_items.py, ничего нового не заводим:
  - _check_planned_item_write_access(user, db, cat) — тот же гейт, что и у
    создания/удаления плановой позиции (superadmin ИЛИ вкладка feo_categories
    ИЛИ wish.edit_feo по субсидии ИЛИ вкладка wishes/purchases) — используется
    для ДОБАВЛЕНИЯ комментария/ответа (и к позиции, и к категории: у категории
    подставляется сама категория).
  - _can_edit_feo_origin(user, db) — тот же гейт, что и у смены признаков
    происхождения плановой позиции (superadmin ИЛИ вкладка feo_categories) —
    используется для переключателя видимости комментариев НА ВСЮ СУБСИДИЮ
    (это структурная настройка уровня субсидии, не разовое действие с одной
    позицией, поэтому уже гейт чуть строже, а не тот же самый).
  - ЧТЕНИЕ (список ветки, настройка видимости) — только get_current_user, по
    аналогии с list_planned_items в том же файле (там тоже без require_tab).

Регистрация — свой собственный префикс /api/feo-comments, не пересекается ни
с одним catch-all другого роутера, поэтому порядок app.include_router(...)
относительно других роутеров ФЭО не важен (см. app/routes.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.feo_category import FeoCategory
from app.models.feo_comment import FeoComment, FeoCommentsVisibility
from app.models.feo_planned_item import FeoPlannedItem
from app.schemas.feo_comment import (
    FeoCommentCountsOut, FeoCommentCreate, FeoCommentOut, FeoCommentReplyCreate,
    FeoCommentsVisibilityOut, FeoCommentsVisibilityUpdate,
)
from app.routers.feo_planned_items import _check_planned_item_write_access, _can_edit_feo_origin

router = APIRouter(prefix="/api/feo-comments", tags=["feo_comments"])


async def _load_category_for_planned_item(db: AsyncSession, item_id: int) -> FeoCategory:
    item = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.id == item_id)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Плановая позиция не найдена")
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == item.feo_category_id)
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")
    return cat


async def _load_category(db: AsyncSession, category_id: int) -> FeoCategory:
    cat = (await db.execute(
        select(FeoCategory).where(FeoCategory.id == category_id)
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")
    return cat


# ---------------------------------------------------------------------------
# Видимость комментариев — один флаг на всю субсидию
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=FeoCommentsVisibilityOut)
async def get_comments_visibility(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    row = (await db.execute(
        select(FeoCommentsVisibility).where(FeoCommentsVisibility.subsidy_id == subsidy_id)
    )).scalar_one_or_none()
    # Отсутствие строки = видимость по умолчанию включена (см. докстринг модели).
    return FeoCommentsVisibilityOut(
        subsidy_id=subsidy_id,
        comments_visible=row.comments_visible if row is not None else True,
    )


@router.put("/settings", response_model=FeoCommentsVisibilityOut)
async def set_comments_visibility(
    data: FeoCommentsVisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not await _can_edit_feo_origin(current_user, db):
        raise HTTPException(
            403,
            "Нет доступа к справочнику ФЭО — переключение видимости комментариев для всей "
            "субсидии доступно только тем, кто может редактировать дерево ФЭО.",
        )
    row = (await db.execute(
        select(FeoCommentsVisibility).where(FeoCommentsVisibility.subsidy_id == data.subsidy_id)
    )).scalar_one_or_none()
    if row is None:
        row = FeoCommentsVisibility(subsidy_id=data.subsidy_id, comments_visible=data.comments_visible)
        db.add(row)
    else:
        row.comments_visible = data.comments_visible
    await db.commit()
    return FeoCommentsVisibilityOut(subsidy_id=data.subsidy_id, comments_visible=data.comments_visible)


# ---------------------------------------------------------------------------
# Счётчики по субсидии — ОДИН запрос вместо N (жалоба владельца 2026-09-15:
# «раскрыть всё» на дереве ФЭО открывало пустую карточку «Комментариев пока
# нет» под каждым направлением/позицией, а до этой правки каждая раскрытая
# ветка ещё и грузила себя ОТДЕЛЬНЫМ GET /?feo_category_id=... /
# ?feo_planned_item_id=... — «развернуть все» на большом дереве стреляло
# десятками запросов разом). Единственный источник и для решения «раскрывать
# ли ветку при массовом раскрытии» (пустые не раскрываются), и для бейджа-
# счётчика у иконки — второй способ посчитать «есть ли комментарии» нигде не
# заводим (ПРАВИЛО №6): count(*) по той же entity-колонке, которую уже
# фильтрует list_comments ниже, ничего не пересчитывается по-другому.
# ---------------------------------------------------------------------------

@router.get("/counts", response_model=FeoCommentCountsOut)
async def get_comment_counts(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Права — ТЕ ЖЕ, что и у list_comments/get_comments_visibility ниже
    (только аутентификация, без require_tab/org-scoping) — см. докстринг
    модуля про «ЧТЕНИЕ... только get_current_user, по аналогии с
    list_planned_items». Новый, более строгий гейт для чтения здесь не
    заводится."""
    cat_ids = (await db.execute(
        select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    if not cat_ids:
        return FeoCommentCountsOut(category_counts={}, planned_item_counts={})

    cat_rows = (await db.execute(
        select(FeoComment.feo_category_id, func.count(FeoComment.id))
        .where(FeoComment.feo_category_id.in_(cat_ids))
        .group_by(FeoComment.feo_category_id)
    )).all()
    category_counts = {cid: cnt for cid, cnt in cat_rows}

    item_ids = (await db.execute(
        select(FeoPlannedItem.id).where(FeoPlannedItem.feo_category_id.in_(cat_ids))
    )).scalars().all()
    planned_item_counts: dict[int, int] = {}
    if item_ids:
        item_rows = (await db.execute(
            select(FeoComment.feo_planned_item_id, func.count(FeoComment.id))
            .where(FeoComment.feo_planned_item_id.in_(item_ids))
            .group_by(FeoComment.feo_planned_item_id)
        )).all()
        planned_item_counts = {iid: cnt for iid, cnt in item_rows}

    return FeoCommentCountsOut(category_counts=category_counts, planned_item_counts=planned_item_counts)


# ---------------------------------------------------------------------------
# Ветка комментариев
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[FeoCommentOut])
async def list_comments(
    feo_planned_item_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if (feo_planned_item_id is None) == (feo_category_id is None):
        raise HTTPException(400, "Нужно указать ровно один из параметров: feo_planned_item_id или feo_category_id")
    if feo_planned_item_id is not None:
        cond = FeoComment.feo_planned_item_id == feo_planned_item_id
    else:
        cond = FeoComment.feo_category_id == feo_category_id
    rows = (await db.execute(
        select(FeoComment).where(cond).order_by(FeoComment.created_at, FeoComment.id)
    )).scalars().all()
    return rows


@router.post("/", response_model=FeoCommentOut)
async def add_comment(
    data: FeoCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if data.feo_planned_item_id is not None:
        cat = await _load_category_for_planned_item(db, data.feo_planned_item_id)
    else:
        cat = await _load_category(db, data.feo_category_id)  # type: ignore[arg-type]

    await _check_planned_item_write_access(current_user, db, cat)

    comment = FeoComment(
        feo_planned_item_id=data.feo_planned_item_id,
        feo_category_id=data.feo_category_id,
        parent_id=None,
        user_id=current_user.id,
        author_name=current_user.full_name or current_user.username,
        text=data.text.strip(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post("/{comment_id}/reply", response_model=FeoCommentOut)
async def reply_to_comment(
    comment_id: int,
    data: FeoCommentReplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    parent = (await db.execute(
        select(FeoComment).where(FeoComment.id == comment_id)
    )).scalar_one_or_none()
    if parent is None:
        raise HTTPException(404, "Комментарий не найден")

    if parent.feo_planned_item_id is not None:
        cat = await _load_category_for_planned_item(db, parent.feo_planned_item_id)
    else:
        cat = await _load_category(db, parent.feo_category_id)

    await _check_planned_item_write_access(current_user, db, cat)

    reply = FeoComment(
        # Ответ живёт на той же сущности, что и корневой комментарий ветки —
        # НЕ берётся из тела запроса (см. докстринг модели), иначе выборка
        # ветки по entity-колонке пропустила бы собственные ответы.
        feo_planned_item_id=parent.feo_planned_item_id,
        feo_category_id=parent.feo_category_id,
        parent_id=parent.id,
        user_id=current_user.id,
        author_name=current_user.full_name or current_user.username,
        text=data.text.strip(),
    )
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return reply
