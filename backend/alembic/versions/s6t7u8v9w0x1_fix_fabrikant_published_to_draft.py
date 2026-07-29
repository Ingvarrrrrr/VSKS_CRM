"""fix fabrikant published->draft where platform_state is null

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-07-28 00:00:00.000000

Площадка Фабрикант по WSDL-API умеет только создать черновик процедуры —
операции «разместить» не существует (проверено по 18 операциям WSDL).
Старый код ошибочно выставлял status='published', когда getProcedureInfo
не отвечал. Исправляем накопившиеся записи:
  - platform = 'fabrikant'
  - status = 'published'
  - platform_state IS NULL  (состояние НЕ подтверждено площадкой через «Обновить статус»)
"""

from alembic import op
import sqlalchemy as sa


revision = 's6t7u8v9w0x1'
down_revision = 'r5s6t7u8v9w0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Идемпотентная проверка: таблица и нужные колонки должны существовать
    tables = inspector.get_table_names()
    if 'platform_publications' not in tables:
        return

    columns = {c['name'] for c in inspector.get_columns('platform_publications')}
    if not {'status', 'platform', 'platform_state'}.issubset(columns):
        return

    op.execute(
        sa.text(
            """
            UPDATE platform_publications
               SET status = 'draft'
             WHERE platform = 'fabrikant'
               AND status = 'published'
               AND platform_state IS NULL
            """
        )
    )


def downgrade():
    # Намеренно пустой: обратно выставлять 'published' нельзя —
    # это было ошибочное значение, реального размещения через API не было.
    pass
