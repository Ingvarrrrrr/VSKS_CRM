"""wishes.contract_id — необязательная ссылка на договор заявки

Владелец (12.10.2026, план lazy-swimming-hollerith.md, п.2): «В заявке должна
быть возможность выбрать Договор, к которому относится заявка; необязательное
поле». В списке выбора — только РАМОЧНЫЕ договоры (Contract.contract_type in
framework_cumulative/framework_with_amount), фильтрация на фронте/бэкенде
(GET /contracts/), не здесь. При переводе заявки в закупку contract_id
переезжает на Purchase (см. app/services/wish_distribution.py,
app/routers/wish_convert.py) — закупка становится заказом этого рамочного
договора существующим механизмом Purchase.contract_id + framework_seq
(app/routers/purchase_budget.py::_assign_framework_seq).

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  wishes:
    - contract_id  INTEGER  NULL  FK contracts.id ON DELETE SET NULL

Downgrade — DROP COLUMN IF EXISTS (идемпотентно).

Проверено upgrade локально (down_revision сначала указывал на реальный head
r3s5u7w9y1a3, пока параллельный исполнитель не создал s4t6v8x0z2b4 — после
его появления down_revision переставлен на s4t6v8x0z2b4 и upgrade перепроверен,
см. отчёт сессии)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 't5u7w9y1a3c5'
down_revision = 's4t6v8x0z2b4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    w_cols = {c["name"] for c in inspector.get_columns("wishes")}
    if "contract_id" not in w_cols:
        op.add_column(
            "wishes",
            sa.Column("contract_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_wishes_contract_id",
            "wishes", "contracts",
            ["contract_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    w_cols = {c["name"] for c in inspector.get_columns("wishes")}
    if "contract_id" in w_cols:
        try:
            op.drop_constraint("fk_wishes_contract_id", "wishes", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("wishes", "contract_id")
