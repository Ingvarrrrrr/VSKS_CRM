"""Комментарии (мини-чат) к плановым позициям ФЭО и категориям дерева ФЭО.

Владелец, Волна 4, п.16 (2026-09-13): «Должна быть возможность оставлять
комментарии, которые тоже видны постоянно... отображается, кто оставил
комментарий и когда, и текст комментария, и на него должна быть возможность
ответить». Область — ТОЛЬКО плановые позиции (FeoPlannedItem) и узлы дерева
ФЭО (FeoCategory), закупки/договоры в эту волну не входят (решение владельца).

ПРИВЯЗКА К СУЩНОСТИ (обоснование выбора): ДВЕ nullable FK-колонки
(feo_planned_item_id / feo_category_id) с CHECK «ровно одна заполнена» —
вместо одной полиморфной пары (entity_type, entity_id). Причина: настоящий
FK ON DELETE CASCADE на каждую колонку гарантирует отсутствие висячих
комментариев СРЕДСТВАМИ САМОЙ БД при удалении позиции/категории — не нужно
помнить почистить комментарии в каждом месте, которое когда-либо удаляет
FeoPlannedItem/FeoCategory (сейчас это и remove/delete_planned_item, и
delete_category, и каскад категории-родителя на дочерние). Полиморфная пара
entity_type+entity_id не может нести FK на две разные таблицы одновременно —
целостность легла бы на прикладной код и её было бы легко забыть в новом
месте удаления. Именно такой баг уже был в проекте: PurchaseItem/WishItem.
feo_planned_item_id какое-то время не имел настоящего FK — см. миграцию
x9y8z7w6v5u4_feo_planned_item_fk_integrity.py — и оставлял битые ссылки после
удаления плановой позиции. Не повторяем эту ошибку здесь.

parent_id — ответ на другой комментарий ТОЙ ЖЕ ветки (self-FK, тоже
ON DELETE CASCADE: удаление комментария с ответами не оставляет их сиротами).
Ответы хранятся в той же таблице, с теми же feo_planned_item_id/
feo_category_id, что и у корневого комментария ветки (задаётся роутером при
создании ответа, не пользователем) — выборка всей ветки одной сущности
остаётся одним WHERE по entity-колонке независимо от глубины ответов.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class FeoComment(Base):
    __tablename__ = "feo_comments"

    id = Column(Integer, primary_key=True, index=True)
    feo_planned_item_id = Column(
        Integer, ForeignKey("feo_planned_items.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    feo_category_id = Column(
        Integer, ForeignKey("feo_categories.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    parent_id = Column(Integer, ForeignKey("feo_comments.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Снимок ФИО автора на момент публикации (как TaskComment.user_name) —
    # переживает удаление/переименование пользователя, комментарий не
    # становится анонимным задним числом.
    author_name = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parent = relationship("FeoComment", remote_side=[id], backref="replies")

    __table_args__ = (
        CheckConstraint(
            "(feo_planned_item_id IS NOT NULL AND feo_category_id IS NULL) OR "
            "(feo_planned_item_id IS NULL AND feo_category_id IS NOT NULL)",
            name="ck_feo_comment_exactly_one_target",
        ),
    )


class FeoCommentsVisibility(Base):
    """Один флаг видимости комментариев НА ВСЮ СУБСИДИЮ (владелец: «переключатель
    делать, для видимости комментариев, сразу для всей субсидии») — чисто
    UI-настройка (что показывать в дереве ФЭО), не право доступа: комментарии
    в БД остаются и создаются независимо от этого флага, он только прячет их
    из интерфейса всем сразу.

    ОТДЕЛЬНАЯ таблица, а не колонка Subsidy.comments_visible — в этой волне
    backend/app/models/subsidy.py занят другим исполнителем (файл вне списка
    разрешённых для этой задачи), трогать его нельзя. Одна строка на субсидию;
    отсутствие строки трактуется как comments_visible=True (см.
    get_comments_visibility в routers/feo_comments.py) — по умолчанию новая
    функциональность включена, а не спрятана.
    """
    __tablename__ = "feo_comments_visibility"

    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), primary_key=True)
    comments_visible = Column(Boolean, nullable=False, server_default='true')
