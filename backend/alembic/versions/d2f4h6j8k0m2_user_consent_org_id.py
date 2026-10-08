"""152-ФЗ: UserConsent.org_id — привязка «Условий поручения обработки ПДн»
к конкретной организации.

Повод: гейт согласия после входа (consent_status.py) обязан различать
«владелец принял поручение для организации A» и «...для организации B» —
владелец нескольких организаций принимает поручение по каждой отдельно
(регистрация и POST /api/legal/consent kind='poruchenie'). UserConsent для
kind='pd' (privacy+consent) org_id не ставит — это согласие пользователя,
не организации.

nullable + ON DELETE SET NULL: согласие остаётся историческим фактом
(кто, когда, на какую редакцию согласился) даже если организацию позже
удалили — запись не обязана исчезать вместе с org_id.

Идемпотентно (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS) —
проект гоняет `alembic upgrade head` при старте контейнера, неидемпотентный
DDL даёт 502 на повторном деплое.

Revision ID: d2f4h6j8k0m2
Revises: e3f5g7h9i1j3
Create Date: 2026-10-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd2f4h6j8k0m2'
down_revision = 'f2h4j6l8n0p2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE user_consents ADD COLUMN IF NOT EXISTS org_id INTEGER "
        "REFERENCES organizations(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_user_consents_org_id ON user_consents (org_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_consents_org_id"))
    op.execute(sa.text("ALTER TABLE user_consents DROP COLUMN IF EXISTS org_id"))
