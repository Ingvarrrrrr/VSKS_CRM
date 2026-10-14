"""from_plan — признак «позиция пришла из Плана закупок» на purchase_items и
wish_items (владелец, 14.10.2026, жалобы (а)-(г): замок категории ФЭО должен
стоять ТОЛЬКО у позиций, реально загруженных из плана, а не у любой позиции с
wish_item_id/feo_planned_item_id — та связь возникает и у ручных позиций
(auto_assign_planned_items/привязка человеком), которые должны оставаться
редактируемыми).

Колонка — булева, NOT NULL DEFAULT false, ставится явно в момент создания
позиции (build_items_from_plan → plan_to_wish.py/plan_to_purchase.py, затем
переносится, а не выставляется заново, при конвертации заявки в закупку и при
пересборке компаньона авансового). НЕ меняется с фронта (ПРАВИЛО памяти «новое
поле — три места»): PATCHABLE_FIELDS/_ItemPatchBody его не содержат.

Бэкфилла НЕТ — решение владельца (14.10.2026): старые позиции свободны
(from_plan=false), признак ставится только НОВЫМ закупкам/заявкам, созданным
из плана (build_items_from_plan → plan_to_wish.py/plan_to_purchase.py). На
проде отличить задним числом «позиция реально загружена из плана» от «ручная
позиция, привязанная к плановой человеком/автосборкой» надёжно нельзя —
привязка (feo_planned_item_id/wish_item_id) возникает в обоих случаях, более
точного критерия в данных нет. Первая версия миграции (без согласования)
содержала бэкфилл по косвенному признаку (FeoPlannedItem.auto_created=false) —
убран как основанный на предположении, а не факте.

Идемпотентно: ADD COLUMN IF NOT EXISTS (повторный прогон не меняет уже
проставленные значения).

Revision ID: f1a2b3c4d5e6
Revises: 6a570b9c50d5
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = 'f1a2b3c4d5e6'
down_revision = '6a570b9c50d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text(
        "ALTER TABLE purchase_items ADD COLUMN IF NOT EXISTS from_plan boolean NOT NULL DEFAULT false"
    ))
    bind.execute(text(
        "ALTER TABLE wish_items ADD COLUMN IF NOT EXISTS from_plan boolean NOT NULL DEFAULT false"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("ALTER TABLE purchase_items DROP COLUMN IF EXISTS from_plan"))
    bind.execute(text("ALTER TABLE wish_items DROP COLUMN IF EXISTS from_plan"))
