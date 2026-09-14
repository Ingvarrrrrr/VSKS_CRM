"""Схемы комментариев (мини-чат) к плановым позициям/категориям ФЭО.

Новый файл (Волна 4, п.16 владельца, 2026-09-13) — намеренно НЕ добавлено в
schemas/feo.py (тот файл в этой волне занят параллельным исполнителем,
редактировать нельзя).
"""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class FeoCommentCreate(BaseModel):
    """Тело POST /api/feo-comments/ — новый комментарий верхнего уровня.
    Ровно один из feo_planned_item_id/feo_category_id обязателен (см.
    валидатор ниже) — то же правило, что и CHECK-констрейнт модели
    FeoComment, продублировано на входе ради понятного 422 вместо 500 при
    нарушении констрейнта в БД."""
    feo_planned_item_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    text: str

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "FeoCommentCreate":
        has_item = self.feo_planned_item_id is not None
        has_cat = self.feo_category_id is not None
        if has_item == has_cat:  # оба или ни одного
            raise ValueError(
                "Нужно указать ровно одно из полей: feo_planned_item_id или feo_category_id"
            )
        if not self.text or not self.text.strip():
            raise ValueError("Текст комментария не может быть пустым")
        return self


class FeoCommentReplyCreate(BaseModel):
    """Тело POST /api/feo-comments/{comment_id}/reply — сущность (плановая
    позиция/категория) берётся из комментария, на который отвечают, не из
    тела запроса."""
    text: str

    @model_validator(mode="after")
    def _text_not_blank(self) -> "FeoCommentReplyCreate":
        if not self.text or not self.text.strip():
            raise ValueError("Текст ответа не может быть пустым")
        return self


class FeoCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feo_planned_item_id: Optional[int] = None
    feo_category_id: Optional[int] = None
    parent_id: Optional[int] = None
    user_id: Optional[int] = None
    author_name: Optional[str] = None
    text: str
    created_at: datetime


class FeoCommentsVisibilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subsidy_id: int
    comments_visible: bool


class FeoCommentsVisibilityUpdate(BaseModel):
    subsidy_id: int
    comments_visible: bool


class FeoCommentCountsOut(BaseModel):
    """Тело GET /api/feo-comments/counts — сколько комментариев (корневых +
    ответов, то же множество строк, что вернул бы GET /?feo_category_id=...
    построчно) лежит на каждой категории/плановой позиции ОДНОЙ субсидии,
    одним запросом (жалоба владельца 2026-09-15: «раскрыть всё» слало запрос
    на КАЖДУЮ ветку дерева разом). Сущность, у которой комментариев нет,
    в словаре ПРОСТО ОТСУТСТВУЕТ (не приходит с value=0) — экономит объём
    ответа на большом дереве, фронт трактует «нет ключа» как 0."""
    category_counts: Dict[int, int] = {}
    planned_item_counts: Dict[int, int] = {}
