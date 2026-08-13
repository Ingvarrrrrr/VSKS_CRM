"""Остановка заявки/закупки (владелец, 2026-08-13).

ЗАЧЕМ. «После согласования заявку править нельзя, только в закупке. Надо
добавить возможность ОСТАНОВКИ заявки. Останавливать могут все. Исполнителю
приходит уведомление... Если заявка остановлена, из плана закупок она
исчезает, но НЕ удаляется. Закупки, к ней привязанные, тоже останавливаются —
те, которые не в стадии договора (для рамочных — которые не заказаны).
Остановленное не удаляется... пишется, кем и когда остановлено.»

Обратной операции (возобновление) владелец не просил — только остановка,
поэтому колонок для «отмены остановки» здесь нет.

  wishes:
    stopped_at      TIMESTAMPTZ NULL — когда остановлена
    stopped_by      INTEGER NULL REFERENCES users(id) ON DELETE SET NULL — кто остановил
    stopped_reason  TEXT NULL — необязательная причина
    stopped_partial BOOLEAN NOT NULL DEFAULT FALSE — остановились не все привязанные закупки
                     (часть уже была на стадии договора/заказано — см. purchases.stopped_at)

  purchases:
    stopped_at        TIMESTAMPTZ NULL — когда остановлена (каскадом от заявки)
    stopped_by        INTEGER NULL REFERENCES users(id) ON DELETE SET NULL — кто остановил
    stopped_wish_id   INTEGER NULL REFERENCES wishes(id) ON DELETE SET NULL —
                       из-за какой заявки остановлена эта закупка

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema (migrate.py гонит upgrade head на старте, конфликт DDL
роняет прод в 502).

Revision ID: n0o1p2q3r4s5
Revises: m8n9o0p1q2r3
Create Date: 2026-08-13 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'n0o1p2q3r4s5'
down_revision = 'm8n9o0p1q2r3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if 'wishes' in table_names:
        op.execute(sa.text(
            "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS stopped_at TIMESTAMPTZ"
        ))
        op.execute(sa.text(
            "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS stopped_by INTEGER "
            "REFERENCES users(id) ON DELETE SET NULL"
        ))
        op.execute(sa.text(
            "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS stopped_reason TEXT"
        ))
        op.execute(sa.text(
            "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS stopped_partial "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))

    if 'purchases' in table_names:
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS stopped_at TIMESTAMPTZ"
        ))
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS stopped_by INTEGER "
            "REFERENCES users(id) ON DELETE SET NULL"
        ))
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS stopped_wish_id INTEGER "
            "REFERENCES wishes(id) ON DELETE SET NULL"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if 'purchases' in table_names:
        op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS stopped_wish_id"))
        op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS stopped_by"))
        op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS stopped_at"))

    if 'wishes' in table_names:
        op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS stopped_partial"))
        op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS stopped_reason"))
        op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS stopped_by"))
        op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS stopped_at"))
