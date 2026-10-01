"""Корректировка утверждённой субсидии через проверку (волна 1).

Владелец: субсидию в статусе 'approved' правят либо напрямую (право
subsidy.edit — оно же «утверждать корректировки»), либо через корректировку
(право subsidy.correct, без subsidy.edit) — правки ждут проверки обладателем
subsidy.edit. Черновик (status='draft') этого не касается — там действуют
обычные правила. Гейт, который решает direct/revision/forbidden — см.
app.services.subsidy_revision_guard; пока функция не принята, всё поведение
спрятано за env-флагом SUBSIDY_REVISION_ENABLED (по умолчанию выключен).

SubsidyRevision — одна «Корректировка №N» в пределах субсидии: пачка правок
одного автора, которую тот набирает (status='draft'), отправляет на проверку
('submitted'), проверяющий разбирает по операциям ('partially_decided' — часть
решена, часть ждёт) и в итоге закрывает ('closed') либо автор отзывает
('withdrawn'). Частичный уникальный индекс не даёт одному автору держать
одновременно две ОТКРЫТЫЕ (draft/submitted/partially_decided) корректировки
на одну субсидию — новую правку кладём в уже открытую, а не плодим вторую.

SubsidyRevisionOp — одна операция внутри корректировки (создать/изменить/
удалить/перенести узел дерева ФЭО или саму субсидию). target_id — id уже
существующей сущности (update/delete/move); target_ref — временная метка
("c1"/"i3" и т.п.) для сущности, которую создаёт ЭТА ЖЕ корректировка и у
которой ещё нет id в БД, пока корректировка не применена; parent_ref —
аналогичная временная ссылка на родителя (например, новая позиция внутри
новой же категории). depends_on_op_id — операция обязана применяться не
раньше другой операции той же корректировки (например, create категории
раньше create позиции в ней). bundle_no группирует операции одной «связки»
перераспределения (принимаются/отклоняются вместе). reviewer_after —
значения, которые проверяющий утвердил ВМЕСТО предложенных author'ом (правка
проверяющего поверх правки автора), added_by_reviewer — операция, которой не
было у автора, а добавил сам проверяющий в ходе разбора.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SubsidyRevision(Base):
    __tablename__ = "subsidy_revisions"
    __table_args__ = (
        Index(
            "ux_subsidy_revisions_one_open_per_author",
            "subsidy_id", "author_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'submitted', 'partially_decided')"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    subsidy_id = Column(Integer, ForeignKey("subsidies.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)  # «Корректировка №N», порядковый в пределах субсидии
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    # draft / submitted / partially_decided / closed / withdrawn

    author_comment = Column(Text, nullable=True)
    reviewer_comment = Column(Text, nullable=True)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subsidy = relationship("Subsidy")
    author = relationship("User", foreign_keys=[author_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])
    ops = relationship(
        "SubsidyRevisionOp",
        back_populates="revision",
        order_by="SubsidyRevisionOp.seq",
        cascade="all, delete-orphan",
    )


class SubsidyRevisionOp(Base):
    __tablename__ = "subsidy_revision_ops"

    id = Column(Integer, primary_key=True, index=True)
    revision_id = Column(Integer, ForeignKey("subsidy_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)

    op_type = Column(String(20), nullable=False)  # create / update / delete / move
    entity_type = Column(String(20), nullable=False)  # subsidy / feo_category / feo_item

    target_id = Column(Integer, nullable=True)
    target_ref = Column(String(40), nullable=True)
    parent_ref = Column(String(40), nullable=True)
    depends_on_op_id = Column(Integer, ForeignKey("subsidy_revision_ops.id", ondelete="CASCADE"), nullable=True)

    field_group = Column(String(60), nullable=True)
    before = Column(JSONB, nullable=True)
    after = Column(JSONB, nullable=True)
    reviewer_after = Column(JSONB, nullable=True)
    added_by_reviewer = Column(Boolean, nullable=False, default=False, server_default="false")

    bundle_no = Column(Integer, nullable=True)

    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    # pending / accepted / applied / rejected / auto_rejected

    review_comment = Column(Text, nullable=True)
    applied_entity_id = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    revision = relationship("SubsidyRevision", back_populates="ops")
    depends_on = relationship("SubsidyRevisionOp", remote_side=[id])
