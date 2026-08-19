"""Деактивировать ничейные записи справочника responsible_persons

БАГ (владелец, 2026-08-19): в backend/app/routers/responsible_persons.py
GET /{sid}/responsible-persons был расширен на выдачу глобальных записей
(subsidy_id IS NULL) вместе с записями конкретной субсидии. Из-за этого
запись id=1 «Филиппов Д.П.» (должность «Ведущий специалист отдела МТО»,
subsidy_id=NULL) стала предлагаться «Ответственным исполнителем» сразу во
ВСЕХ субсидиях — ровно то, чего владелец не хочет («убери Филиппова как
ответственного по умолчанию, такого быть не должно»).

Приложение уже откатили на выдачу только своей субсидии (subsidy_id == sid).
Эта миграция чистит сами данные: запись справочника без привязки к
субсидии — сирота, у неё нет легитимного сценария использования (диалоги
подмешивают сотрудников субсидии отдельно, см. responsibleOptions в
CreateOrderView.vue), поэтому активных ничейных записей быть не должно.
Деактивируем (is_active=False), а не удаляем — история/ссылки в других
таблицах не рвутся.

Идемпотентно: повторный прогон обновит 0 строк.

downgrade(): no-op — обратно поднимать ничейные записи справочника незачем,
это и есть источник бага.

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-08-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'h9i0j1k2l3m4'
down_revision = 'g8h9i0j1k2l3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "responsible_persons" in existing_tables:
        result = bind.execute(sa.text(
            "UPDATE responsible_persons SET is_active = FALSE "
            "WHERE subsidy_id IS NULL AND is_active IS NOT FALSE"
        ))
        print(f"[h9i0j1k2l3m4] responsible_persons: ничейных записей деактивировано = {result.rowcount}")


def downgrade() -> None:
    # no-op: обратно поднимать ничейные записи справочника (subsidy_id IS
    # NULL) незачем — они были источником бага «Филиппов предлагается везде».
    pass
