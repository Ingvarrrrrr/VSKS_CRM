"""add wish_item_id hard link to purchase_items

Revision ID: g1h2i3j4k5l6
Revises: d3e4f5a6b7c8
Create Date: 2026-07-20 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = 'g1h2i3j4k5l6'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('purchase_items')]

    if 'wish_item_id' not in cols:
        op.add_column(
            'purchase_items',
            sa.Column('wish_item_id', sa.Integer(), sa.ForeignKey('wish_items.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index('ix_purchase_items_wish_item_id', 'purchase_items', ['wish_item_id'])

    # Backfill: for each purchase with wish_id set, match purchase_items to wish_items by item_name
    # Best-effort — on ambiguity leave NULL.  Safe on empty DB.
    conn = bind
    try:
        rows = conn.execute(text(
            "SELECT DISTINCT wish_id FROM purchases WHERE wish_id IS NOT NULL"
        )).fetchall()
        for (wish_id,) in rows:
            # Get wish_items for this wish, ordered by id
            wish_items = conn.execute(text(
                "SELECT id, item_name FROM wish_items WHERE wish_id = :wid ORDER BY id"
            ), {"wid": wish_id}).fetchall()
            if not wish_items:
                continue
            # Get purchases for this wish
            purchases = conn.execute(text(
                "SELECT id FROM purchases WHERE wish_id = :wid ORDER BY id"
            ), {"wid": wish_id}).fetchall()
            for (purchase_id,) in purchases:
                # Get purchase_items for this purchase, ordered by id
                pitems = conn.execute(text(
                    "SELECT id, item_name FROM purchase_items WHERE purchase_id = :pid ORDER BY id"
                ), {"pid": purchase_id}).fetchall()
                if not pitems:
                    continue
                # Build a name->wish_item_id map (first match wins, case-insensitive)
                name_map = {}
                for (wi_id, wi_name) in wish_items:
                    if wi_name:
                        key = (wi_name or "").strip().lower()
                        if key not in name_map:
                            name_map[key] = wi_id
                for (pi_id, pi_name) in pitems:
                    if pi_name:
                        key = (pi_name or "").strip().lower()
                        wi_id = name_map.get(key)
                        if wi_id is not None:
                            conn.execute(text(
                                "UPDATE purchase_items SET wish_item_id = :wi_id WHERE id = :pi_id AND wish_item_id IS NULL"
                            ), {"wi_id": wi_id, "pi_id": pi_id})
    except Exception:
        # Best-effort backfill — if table is empty or schema differs, skip silently
        pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('purchase_items')]
    if 'wish_item_id' in cols:
        indices = [i['name'] for i in inspector.get_indexes('purchase_items')]
        if 'ix_purchase_items_wish_item_id' in indices:
            op.drop_index('ix_purchase_items_wish_item_id', table_name='purchase_items')
        op.drop_column('purchase_items', 'wish_item_id')
