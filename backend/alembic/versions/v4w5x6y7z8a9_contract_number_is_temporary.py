"""Технический номер договора для рамочной головы (contract_number_is_temporary)

Владелец (2026-08-31), «рамочные договора без закупок внутри должны
согласовываться и печататься»: «...на тот момент, когда подписывают лист
согласования, могут быть ещё неизвестны номер и дата. Надо присваивать
какой-то технический номер на данный момент времени и ставить примечание,
что надо актуализировать номер: подтвердить проставленный тобой или задать
новый».

При формировании договорного документа для рамочной головы (is_framework_head,
см. app/routers/purchases.py) без заполненного contract_number система
присваивает технический номер вида «ВРЕМ-{№закупки}» + сегодняшнюю дату и
ставит этот флаг в True. Снимается по POST
/api/purchases/{pid}/actualize-contract-number (подтверждение текущего номера
либо задание нового).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - contract_number_is_temporary  BOOLEAN  NOT NULL DEFAULT false

Revision ID: v4w5x6y7z8a9
Revises: q7r8s9t0u1v2
Create Date: 2026-08-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'v4w5x6y7z8a9'
down_revision = 'aa1b2c3d4e5f'
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    existing = _cols('purchases')

    if 'contract_number_is_temporary' not in existing:
        op.add_column('purchases', sa.Column(
            'contract_number_is_temporary', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))


def downgrade():
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS contract_number_is_temporary'
    ))
