"""product_description_history / product_description_proposals — защита
общего каталога товаров (Этап В, план item-tz-description.md, владелец
14.10.2026): история правок описания + предложения правок (без галочки
products.edit_catalog — на рассмотрение). См. app/models/
product_description_history.py, app/models/product_description_proposal.py.

Идемпотентно: CREATE TABLE IF NOT EXISTS.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-10-14
"""
from alembic import op
from sqlalchemy import text

revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        """
        CREATE TABLE IF NOT EXISTS product_description_proposals (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            field VARCHAR(30) NOT NULL,
            proposed_value TEXT,
            current_value_at_proposal TEXT,
            wish_item_id INTEGER REFERENCES wish_items(id) ON DELETE SET NULL,
            purchase_item_id INTEGER REFERENCES purchase_items(id) ON DELETE SET NULL,
            proposed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            proposed_at TIMESTAMP NOT NULL DEFAULT now(),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMP,
            decision_comment TEXT
        )
        """
    ))
    bind.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_product_description_proposals_product_id "
        "ON product_description_proposals (product_id)"
    ))
    bind.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_product_description_proposals_status "
        "ON product_description_proposals (status)"
    ))

    bind.execute(text(
        """
        CREATE TABLE IF NOT EXISTS product_description_history (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            field VARCHAR(30) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            changed_at TIMESTAMP NOT NULL DEFAULT now(),
            source VARCHAR(20) NOT NULL DEFAULT 'edit',
            proposal_id INTEGER REFERENCES product_description_proposals(id) ON DELETE SET NULL
        )
        """
    ))
    bind.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_product_description_history_product_id "
        "ON product_description_history (product_id)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP TABLE IF EXISTS product_description_history"))
    bind.execute(text("DROP TABLE IF EXISTS product_description_proposals"))
