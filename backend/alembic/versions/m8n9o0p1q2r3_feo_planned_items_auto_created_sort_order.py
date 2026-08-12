"""feo_planned_items: auto_created + sort_order (владелец, 2026-08-12,
«закупка сама становится планом»).

ПРИЧИНА. Категория 3716 «Приобретение брендированных футболок участников
финала» (МИНПРОС) имела финансирование по ФЭО 175 000 ₽, ни одной плановой
позиции и закупку на 149 282,50 ₽ в статусе «Поставлено» — панель писала
«план 0 · остаток −149 282,50», хотя деньги потрачены в рамках ФЭО. Причина:
автозаведение плановой позиции жило только на пути «заявка → закупка»
(wishes.py._auto_assign_planned_items), а эта закупка создана в обход заявки.
Решение: та же логика теперь зовётся и со стороны закупки (см.
app/services/plan_autoassign.py, backend/app/routers/purchases.py) — плановая
позиция может быть заведена автоматически, а не только человеком.

  - auto_created BOOLEAN NOT NULL DEFAULT FALSE — «эта плановая позиция
    заведена автоматически из закупки/заявки, а не человеком»; фронту нужно
    отдельно помечать такие строки (не гейт бизнес-логики, только UI-признак,
    по образцу wish_items.feo_planned_item_match_confirmed).
  - sort_order INTEGER NULL — порядок позиций внутри категории (владелец
    просил менять их местами); сортировка выдачи — sort_order NULLS LAST, id
    (см. GET /feo-planned-items/).

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema (migrate.py гонит upgrade head на старте, конфликт DDL
роняет прод в 502).

Revision ID: m8n9o0p1q2r3
Revises: l5m6n7o8p9q0
Create Date: 2026-08-12 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'm8n9o0p1q2r3'
down_revision = 'l5m6n7o8p9q0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "auto_created BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS sort_order"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS auto_created"
    ))
