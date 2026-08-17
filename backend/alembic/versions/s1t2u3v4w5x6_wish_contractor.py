"""wishes.contractor_id / contractor_name — необязательный контрагент заявки
(владелец, 2026-08-17): «должна быть возможность указывать контрагента и его
имя, но это по желанию».

ПРИЧИНА. У Wish не было ни одного поля контрагента (только PurchaseItem уже
имел contractor_id/contractor_inn/contractor_name — см. app/models/purchase_item.py).
Задача — дать то же самое на уровне заявки, ДО того, как она станет закупкой,
и оба поля строго необязательны (никакой валидации/блокировки сохранения).

  wishes:
    contractor_id    INTEGER NULL REFERENCES contractors(id) ON DELETE SET NULL —
                      ссылка на справочник контрагентов.
    contractor_name  VARCHAR(500) NULL — свободный ввод, когда контрагента в
                      справочнике ещё нет (mirrors PurchaseItem.contractor_name).

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema (migrate.py гонит upgrade head на старте, конфликт DDL
роняет прод в 502).

Revision ID: s1t2u3v4w5x6
Revises: r6s7t8u9v0w1
Create Date: 2026-08-17 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 's1t2u3v4w5x6'
down_revision = 'r6s7t8u9v0w1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'wishes' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS "
        "contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE wishes ADD COLUMN IF NOT EXISTS "
        "contractor_name VARCHAR(500)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'wishes' not in inspector.get_table_names():
        return
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS contractor_name"))
    op.execute(sa.text("ALTER TABLE wishes DROP COLUMN IF EXISTS contractor_id"))
