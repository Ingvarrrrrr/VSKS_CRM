"""purchases.procurement_order_date — дата приказа о закупке (владелец,
28.10.2026): «нужна переменная для номера приказа» — номер
(procurement_order_number) уже существовал (Phase 28 T6/T7), не хватало
даты к нему. Присваивается автоматически (сегодняшней датой), если не
заполнена вручную — см. app/services/purchase_order_numbering.py
::assign_procurement_order_number_if_missing, вызывается из
app/services/documents/generate.py при первой генерации документа по
закупке (та же схема, что и временный номер договора для рамочной головы,
app/services/temp_contract_number.py).

Idempotent: ADD COLUMN IF NOT EXISTS под inspector-guard, как соседние
миграции на purchases (см. c3d5e7f9a1b3_org_doc_name_exceptions.py).

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b3, w2x4y6z8a0b2
Create Date: 2026-10-28 00:00:00.000000

Merge (28.10.2026): на момент создания этой миграции в alembic было ДВА head —
c3d5e7f9a1b3 (эта ветка) и f3t5s7q9u1e3→w2x4y6z8a0b2 (product_fts_index/
product_words_mv, параллельная сессия). Обе ветки начинаются от одного
родителя c3d5e7f9a1b3, поэтому слияние здесь не теряет и не переупорядочивает
ничью работу — просто сводит дерево обратно в одну линию (единственный head —
f5a7c9e1b3d5, следующая миграция после этой). down_revision — tuple из двух
родителей (merge revision), а не depends_on: по правилам alembic только
down_revision определяет порядок/branch point в `alembic history`, depends_on
используется для меток веток без упорядочивания.
"""
import sqlalchemy as sa
from alembic import op

revision = 'd4e6f8a0b2c4'
down_revision = ('c3d5e7f9a1b3', 'w2x4y6z8a0b2')
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'purchases' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('purchases')}
    if 'procurement_order_date' not in cols:
        op.execute(sa.text(
            "ALTER TABLE purchases ADD COLUMN IF NOT EXISTS procurement_order_date DATE"
        ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE purchases DROP COLUMN IF EXISTS procurement_order_date"))
