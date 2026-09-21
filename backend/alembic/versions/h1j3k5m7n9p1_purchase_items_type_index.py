"""Индекс purchase_items(purchase_id, item_type) — товары/услуги по этапам

Задача владельца (план ancient-prancing-music.md, раздел B, 2026-09-21):
GET /api/dashboard/charts?type_split=true расширяет корзины этапов join'ом на
PurchaseItem и агрегатами по kind_of(item_type) (app.services.dashboard_type_split) —
запрос идёт по каждой закупке в скоупе видимости (potenциально все закупки
субсидии/аккаунта), выборка позиций — по purchase_id IN (...). Индекс покрывает
и сам join (purchase_id), и агрегат по типу (item_type) без отдельного чтения
таблицы.

Идемпотентно (inspector-guard — migrate.py гонит upgrade head на старте прода,
DDL обязан переживать повторный прогон, см. память проекта).
"""
from alembic import op
from sqlalchemy import inspect


revision = 'h1j3k5m7n9p1'
down_revision = 'g5h7j9k1m3n5'
branch_labels = None
depends_on = None


TABLE = "purchase_items"
INDEX_NAME = "ix_purchase_items_purchase_id_item_type"


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    if INDEX_NAME not in existing_indexes:
        op.create_index(INDEX_NAME, TABLE, ["purchase_id", "item_type"])


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE)
