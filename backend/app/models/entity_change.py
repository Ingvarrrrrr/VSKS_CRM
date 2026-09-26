from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base


class EntityChange(Base):
    """Records field-level changes for entities (purchases, wishes).

    entity_type discriminator: 'purchase' | 'wish' | 'task'
    old_value/new_value stored as Text (str representation) for portability.
    changed_by_id nullable for audit trail safety (SET NULL on user delete).
    """
    __tablename__ = "entity_changes"
    __table_args__ = (
        Index("ix_entity_changes_type_id_at", "entity_type", "entity_id", "changed_at"),
    )

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(20), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    field_name = Column(String(64), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by_name = Column(String(200), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    # Журнал изменений ФЭО (волна 1, 22.09) — откуда пришло изменение и на что
    # оно ссылается. NULL у всех строк, заведённых до этой правки (легаси —
    # 'purchase'/'wish'/'task' через record_entity_changes без source).
    # Единственный источник допустимых значений source — app/services/
    # feo_history.py::SOURCES (Правило №6, не заводить второй список строк):
    #   'manual'     — человек поправил поле руками (source_ref=NULL).
    #   'import'     — импорт Excel ФЭО (source_ref=feo_import_runs.id).
    #   'wish'       — позиция появилась/изменилась из заявки (source_ref=wishes.id).
    #   'purchase'   — из закупки (source_ref=purchases.id).
    #   'autoassign' — автоматическая привязка закупки/заявки к плану (source_ref=NULL
    #                  либо id закупки/заявки, см. вызывающий код волны 2).
    #   'collapse'   — сворачивание категорий-дублей (source_ref=NULL либо id
    #                  категории-источника, см. вызывающий код волны 2).
    source = Column(String(20), nullable=True)
    source_ref = Column(Integer, nullable=True)


class EntityFieldSeen(Base):
    """Tracks per-user dismissed (seen) state for a specific field on an entity.

    UniqueConstraint on (user_id, entity_type, entity_id, field_name) allows
    upsert via on_conflict_do_update or delete+insert.
    """
    __tablename__ = "entity_field_seen"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", "field_name",
                         name="uq_entity_field_seen"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(Integer, nullable=False)
    field_name = Column(String(64), nullable=False)
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
