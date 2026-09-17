"""Срок гарантии договора: единица измерения (purchases.warranty_period_unit)

Владелец (жалоба, п.10): «Срок гарантии может быть в днях, в месяцах, в
годах.» Раньше было одно поле warranty_period_days — число, подписанное «в
раб.днях», и владелец вписывал туда 365, имея в виду год. Значение уходило в
документ как голое число дней без единицы.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - warranty_period_unit  VARCHAR(10)  NULL — 'days' | 'months' | 'years'.
      NULL = старые закупки (заведены до этой миграции) — трактуется как
      'days', само число в warranty_period_days не трогаем и не пересчитываем.

Обратная совместимость (ПРАВИЛО №6, один источник для «сколько ввёл
пользователь»): warranty_period_days ОСТАЁТСЯ существующей колонкой и
существующим ключом контекста документа — теперь хранит число, введённое
пользователем В ВЫБРАННОЙ ЕДИНИЦЕ (а не обязательно в днях), парой с
warranty_period_unit. Для старых записей (unit IS NULL) смысл не меняется —
там оно и раньше было числом дней. Новый человекочитаемый ключ шаблона
warranty_period_text (см. app/services/documents/contract_terms.py) собирает
«1 год» / «12 месяцев» / «30 дней» с правильным склонением — старые шаблоны,
использующие {{warranty_period_days}} как число, продолжают получать число,
как раньше.

Downgrade — DROP COLUMN IF EXISTS (тоже идемпотентно).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'w3x4y5z6a7b8'
down_revision = 't4v6x8z0b2d4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "warranty_period_unit" not in existing_cols:
        op.add_column(
            "purchases",
            sa.Column("warranty_period_unit", sa.String(10), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("purchases")}
    if "warranty_period_unit" in existing_cols:
        op.drop_column("purchases", "warranty_period_unit")
