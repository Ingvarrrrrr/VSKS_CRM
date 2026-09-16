"""Черновая раскладка позиций закупки по колонкам канбана «Разбить на несколько»

Владелец (2026-09-16): «если я начал перекидывать в канбане между категориями
и случайно вышел из окна, сейчас всё слетает — хотелось бы, чтобы не слетало».
Раньше PurchaseSplitKanban.vue держал раскладку колонок только в памяти
компонента (ref, пересобирается из product.category при каждом открытии) —
любое закрытие диалога до нажатия «Разбить» теряло ручные перемещения.

purchase_items.split_column_key — то же самое поле по смыслу и по формату,
что wish_items.target_column_key (backend/app/models/wish_item.py): null —
колонка = product.category (или «Не определено»), непустая строка — ручной
override, сохраняется PATCH-ом на каждый бросок карточки (см.
app/routers/purchase_split_columns.py) и очищается после успешного
POST /purchases/{id}/split (раскладка одноразовая, использована — не нужна).

Идемпотентно, под inspector-guard, по образцу
s3u5w7y9a1c3_purchase_categories.py.

Revision ID: t4v6x8z0b2d4
Revises: s3u5w7y9a1c3
Create Date: 2026-09-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 't4v6x8z0b2d4'
down_revision = 's3u5w7y9a1c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("purchase_items")}
    if "split_column_key" not in cols:
        op.add_column(
            "purchase_items",
            sa.Column("split_column_key", sa.String(200), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("purchase_items")}
    if "split_column_key" in cols:
        op.drop_column("purchase_items", "split_column_key")
