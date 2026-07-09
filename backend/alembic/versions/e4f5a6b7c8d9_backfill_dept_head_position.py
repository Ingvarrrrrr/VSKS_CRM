"""backfill: сверка существующих должностей членов ↔ head/deputy отделов

Двусторонний синхрон (dept_role_sync) срабатывает только при записи и не трогает
уже лежащие в БД данные. Здесь разово заполняем пробелы в обе стороны:
  • должность члена «Начальник/Заместитель начальника отдела» → head/deputy_user_id
    отдела (если поле пустое);
  • head/deputy_user_id отдела → position соответствующего членства (если пусто).
Конфликты (обе стороны заполнены по-разному) НЕ трогаем.

Idempotent: только заполнение NULL-полей, повторный прогон ничего не меняет.

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
Create Date: 2026-07-09 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'e4f5a6b7c8d9'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None

POS_HEAD = 'Начальник отдела'
POS_DEPUTY = 'Заместитель начальника отдела'


def _fill_dept_from_position(field: str, position: str) -> str:
    # position (в членстве, с fallback на users.position) → departments.<field>,
    # только когда поле пустое. Из нескольких кандидатов берём минимальный user_id.
    return f"""
        UPDATE departments d SET {field} = (
            SELECT uo.user_id FROM user_organizations uo
            JOIN users u ON u.id = uo.user_id
            WHERE uo.dept_id = d.id AND uo.org_id = d.org_id
              AND COALESCE(NULLIF(uo.position, ''), u.position) = :pos
            ORDER BY uo.user_id LIMIT 1
        )
        WHERE d.{field} IS NULL
          AND EXISTS (
            SELECT 1 FROM user_organizations uo2
            JOIN users u2 ON u2.id = uo2.user_id
            WHERE uo2.dept_id = d.id AND uo2.org_id = d.org_id
              AND COALESCE(NULLIF(uo2.position, ''), u2.position) = :pos
          );
    """


def _fill_position_from_dept(field: str, position: str) -> str:
    # departments.<field> → position конкретного членства, если оно пустое.
    return f"""
        UPDATE user_organizations uo SET position = :pos
        FROM departments d
        WHERE d.{field} = uo.user_id
          AND uo.dept_id = d.id AND uo.org_id = d.org_id
          AND (uo.position IS NULL OR uo.position = '');
    """


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if not {'departments', 'user_organizations', 'users'} <= set(tables):
        return
    dcols = {c['name'] for c in inspector.get_columns('departments')}
    if 'head_user_id' not in dcols or 'deputy_head_user_id' not in dcols:
        return

    op.execute(sa.text(_fill_dept_from_position('head_user_id', POS_HEAD)).bindparams(pos=POS_HEAD))
    op.execute(sa.text(_fill_dept_from_position('deputy_head_user_id', POS_DEPUTY)).bindparams(pos=POS_DEPUTY))
    op.execute(sa.text(_fill_position_from_dept('head_user_id', POS_HEAD)).bindparams(pos=POS_HEAD))
    op.execute(sa.text(_fill_position_from_dept('deputy_head_user_id', POS_DEPUTY)).bindparams(pos=POS_DEPUTY))


def downgrade() -> None:
    # Backfill данных не откатывается (безопасно оставить заполненные поля).
    pass
