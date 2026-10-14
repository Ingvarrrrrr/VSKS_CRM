"""Средняя цена по региону и партии (план clever-bouncing-lantern.md, Часть 2).

Новые колонки product_price_history — region/quantity/unit/purchase_item_id —
дают возможность отфильтровать историю цены по месту поставки и по размеру
партии (compute_price_stats, отдельная сессия). purchase_item_id уникален
(там, где не NULL) — защита от повторной записи той же позиции при повторном
прогоне досчёта или повторном переходе статуса.

Три backfill-шага, каждый идемпотентен (безопасно гонять повторно):
  (a) точки истории для уже заключённых закупок, у которых позиция каталожного
      товара ещё не попала в историю ни старым способом (product_id+source_ref
      +collected_at — как раньше писал purchase_transition_core), ни новым
      (purchase_item_id) — пишем НОВУЮ строку истории на каждую такую позицию.
      Старые 33 строки (до этой ревизии) не трогаем — у них своя природа
      (одна строка на контракт, не на позицию), трогать задним числом рискованно.
  (b) region только что созданных строк — из Purchase.delivery_region, через
      app.services.ru_regions.canonical_region_name (тот же нормализатор, что
      и новый писатель actualize_contract_item_prices) — единственная функция
      нормализации, здесь не копируется.
  (c) organizations.region — из юр. адреса (app.services.region_from_text.
      find_region_in_text), ТОЛЬКО если region ещё NULL (ручное значение не
      перетираем).

Downgrade: удаляет колонки (данные истории по региону/партии теряются —
это ожидаемо для отката такой миграции).

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-10-14 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("product_price_history")}

    if "region" not in existing_cols:
        op.add_column("product_price_history", sa.Column("region", sa.String(100), nullable=True))
    if "quantity" not in existing_cols:
        op.add_column("product_price_history", sa.Column("quantity", sa.Numeric(15, 4), nullable=True))
    if "unit" not in existing_cols:
        op.add_column("product_price_history", sa.Column("unit", sa.String(50), nullable=True))
    if "purchase_item_id" not in existing_cols:
        op.add_column(
            "product_price_history",
            sa.Column("purchase_item_id", sa.Integer(), sa.ForeignKey("purchase_items.id", ondelete="SET NULL"), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("product_price_history")}
    if "ix_product_price_history_purchase_item_id_unique" not in existing_indexes:
        op.create_index(
            "ix_product_price_history_purchase_item_id_unique",
            "product_price_history",
            ["purchase_item_id"],
            unique=True,
            postgresql_where=sa.text("purchase_item_id IS NOT NULL"),
        )

    # (a) Досчёт точек истории для позиций заключённых закупок, которых ещё
    # нет в истории ни старым, ни новым способом записи.
    result_a = conn.execute(sa.text(
        """
        INSERT INTO product_price_history
            (product_id, price, source, source_ref, contractor_id, collected_at,
             purchase_item_id, quantity, unit, created_by)
        SELECT
            pi.product_id,
            COALESCE(pi.final_unit_price, pi.unit_price),
            'contract',
            p.contract_number,
            p.contractor_id,
            p.contract_date,
            pi.id,
            pi.quantity,
            pi.unit,
            NULL
        FROM purchase_items pi
        JOIN purchases p ON p.id = pi.purchase_id
        WHERE pi.product_id IS NOT NULL
          AND p.contract_price IS NOT NULL
          AND COALESCE(pi.final_unit_price, pi.unit_price) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM product_price_history h2 WHERE h2.purchase_item_id = pi.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM product_price_history h
              WHERE h.product_id = pi.product_id AND h.source = 'contract'
                AND h.source_ref = p.contract_number AND h.collected_at = p.contract_date
          )
        """
    ))
    print(f"[n4o5p6q7r8s9] (a) новых точек истории цены из позиций закупок: {result_a.rowcount}")

    # (b) region у строк, у которых уже проставлен purchase_item_id (новые +
    # любые, у которых он мог быть выставлен раньше) — читаем distinct
    # delivery_region и нормализуем python-функцией (тот же нормализатор,
    # что и живой писатель).
    from app.services.ru_regions import canonical_region_name

    raw_regions = conn.execute(sa.text(
        """
        SELECT DISTINCT p.delivery_region
        FROM purchases p
        JOIN purchase_items pi ON pi.purchase_id = p.id
        JOIN product_price_history h ON h.purchase_item_id = pi.id
        WHERE p.delivery_region IS NOT NULL AND h.region IS NULL
        """
    )).fetchall()
    region_updates = 0
    for (raw,) in raw_regions:
        canonical = canonical_region_name(raw)
        if not canonical:
            continue
        res = conn.execute(sa.text(
            """
            UPDATE product_price_history h
            SET region = :canonical
            FROM purchase_items pi
            JOIN purchases p ON p.id = pi.purchase_id
            WHERE h.purchase_item_id = pi.id
              AND h.region IS NULL
              AND p.delivery_region = :raw
            """
        ), {"canonical": canonical, "raw": raw})
        region_updates += res.rowcount
    print(f"[n4o5p6q7r8s9] (b) строк истории с проставленным регионом: {region_updates}")

    # (c) organizations.region из юр. адреса, не перетирая уже заполненное.
    from app.services.region_from_text import find_region_in_text

    orgs = conn.execute(sa.text(
        "SELECT id, address FROM organizations WHERE region IS NULL AND address IS NOT NULL"
    )).fetchall()
    org_updates = 0
    for org_id, address in orgs:
        canonical = find_region_in_text(address)
        if not canonical:
            continue
        conn.execute(
            sa.text("UPDATE organizations SET region = :canonical WHERE id = :id AND region IS NULL"),
            {"canonical": canonical, "id": org_id},
        )
        org_updates += 1
    print(f"[n4o5p6q7r8s9] (c) организаций с регионом, заполненным из адреса: {org_updates}")


def downgrade() -> None:
    op.drop_index("ix_product_price_history_purchase_item_id_unique", table_name="product_price_history")
    op.drop_column("product_price_history", "purchase_item_id")
    op.drop_column("product_price_history", "unit")
    op.drop_column("product_price_history", "quantity")
    op.drop_column("product_price_history", "region")
