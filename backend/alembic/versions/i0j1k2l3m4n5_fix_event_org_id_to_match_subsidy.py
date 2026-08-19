"""Исправить org_id мероприятий на org_id их субсидии

БАГ (требование владельца, 2026-08-19): единственная точка ввода
мероприятий — карточка субсидии (Приложение №3); везде остальное — только
выбор из мероприятий ЭТОЙ субсидии. Раньше POST /api/events/ проставлял
org_id мероприятия от ПОЛЬЗОВАТЕЛЯ (get_single_org_id(current_user) или
current_user.org_id), а не от субсидии. GET фильтровал по Event.org_id —
из-за расхождения мероприятие, заведённое пользователем другой орг, пропадало
из выпадающих списков, и человек заводил дубликат с другим написанием
(«разночтения в названиях — я потом никогда ничего не посчитаю»).

Код теперь берёт org_id мероприятия от subsidy.org_id при создании и
фильтрует GET по org_id субсидии, а не события. Эта миграция чистит уже
накопившиеся расхождения в данных.

Идемпотентно: повторный прогон обновит 0 строк.

downgrade(): no-op — org_id мероприятия обязан совпадать с org_id его
субсидии, откатывать назад на «неправильные» значения незачем.

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-08-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'i0j1k2l3m4n5'
down_revision = 'h9i0j1k2l3m4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "events" in existing_tables and "subsidies" in existing_tables:
        result = bind.execute(sa.text(
            "UPDATE events e SET org_id = s.org_id FROM subsidies s "
            "WHERE e.subsidy_id = s.id AND (e.org_id IS DISTINCT FROM s.org_id)"
        ))
        print(f"[i0j1k2l3m4n5] events: org_id приведено к org_id субсидии, строк = {result.rowcount}")


def downgrade() -> None:
    # no-op: org_id мероприятия обязан совпадать с org_id его субсидии,
    # откатывать назад на рассогласованные значения незачем.
    pass
