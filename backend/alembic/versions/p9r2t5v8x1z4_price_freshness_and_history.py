"""Актуализация цены товара: история, настраиваемые сроки, курс USD, оффера КП

Владелец (2026-08-29): «При формировании заявок люди выбирают товар и цена
вставляется автоматически. Но цена может быть уже неактуальна. Надо
показывать дату последней актуализации этой цены... Срок актуальности
РАЗНЫЙ для разных видов товаров... Дополнительный критерий — курс доллара
к рублю».

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  products:
    - price_updated_at            TIMESTAMP
    - price_source                VARCHAR(20)   'contract'|'kp'|'manual'|'import'|'monitoring'
    - price_source_ref            VARCHAR(300)
    - price_source_contractor_id  INTEGER  FK contractors(id) ON DELETE SET NULL
    - price_ttl_days              INTEGER  (персональный override срока актуальности)

Создаёт (под inspector.has_table() guard):
  - product_price_history          история цен товара
  - price_freshness_rules          настраиваемые сроки актуальности по scope (org/category/...)
  - fx_rates                       курсы валют ЦБ РФ
  - commercial_request_offers      предложения (цены), полученные от получателей запроса КП

Сиды price_freshness_rules (только если строки ещё нет):
  ('default', '*', 60), ('category', 'Продукты питания', 14), ('category', 'Продукты', 14)

Backfill (безопасный, только для строк с price_updated_at IS NULL):
  - из contract_date/contract_number, если есть законтрактованная цена
  - иначе из updated_at (ручное обновление)
  Плюс перенос уже существующей цены в product_price_history (идемпотентно,
  через NOT EXISTS — повторный прогон не плодит дубли).

Revision ID: p9r2t5v8x1z4
Revises: n4p6r8t0v2x4
Create Date: 2026-08-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'p9r2t5v8x1z4'
down_revision = 'n4p6r8t0v2x4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # ── products: новые колонки (идемпотентно) ──────────────────────────────
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_updated_at TIMESTAMP"
    ))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_source VARCHAR(20)"
    ))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_source_ref VARCHAR(300)"
    ))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_source_contractor_id "
        "INTEGER REFERENCES contractors(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_ttl_days INTEGER"
    ))

    # ── product_price_history ────────────────────────────────────────────────
    if not insp.has_table("product_price_history"):
        op.create_table(
            "product_price_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(),
                      sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("price", sa.Numeric(15, 2), nullable=True),
            sa.Column("source", sa.String(20), nullable=True),
            sa.Column("source_ref", sa.String(300), nullable=True),
            sa.Column("contractor_id", sa.Integer(),
                      sa.ForeignKey("contractors.id", ondelete="SET NULL"), nullable=True),
            sa.Column("collected_at", sa.Date(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "ix_product_price_history_product_id", "product_price_history", ["product_id"]
        )

    # ── price_freshness_rules ────────────────────────────────────────────────
    if not insp.has_table("price_freshness_rules"):
        op.create_table(
            "price_freshness_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.Integer(),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("scope_kind", sa.String(20), nullable=False),
            sa.Column("scope_key", sa.String(200), nullable=False),
            sa.Column("ttl_days", sa.Integer(), nullable=False),
            sa.UniqueConstraint(
                "org_id", "scope_kind", "scope_key", name="uq_price_freshness_rule_scope"
            ),
        )

    # ── fx_rates ──────────────────────────────────────────────────────────────
    if not insp.has_table("fx_rates"):
        op.create_table(
            "fx_rates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(3), nullable=False),
            sa.Column("rate_date", sa.Date(), nullable=False),
            sa.Column("value", sa.Numeric(14, 6), nullable=False),
            sa.UniqueConstraint("code", "rate_date", name="uq_fx_rate_code_date"),
        )

    # ── commercial_request_offers ────────────────────────────────────────────
    if not insp.has_table("commercial_request_offers"):
        op.create_table(
            "commercial_request_offers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_id", sa.Integer(),
                      sa.ForeignKey("commercial_requests.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recipient_id", sa.Integer(),
                      sa.ForeignKey("commercial_request_recipients.id", ondelete="CASCADE"), nullable=True),
            sa.Column("product_id", sa.Integer(),
                      sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
            sa.Column("item_name", sa.String(500), nullable=True),
            sa.Column("unit", sa.String(50), nullable=True),
            sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
            sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
        )
        op.create_index(
            "ix_commercial_request_offers_request_id", "commercial_request_offers", ["request_id"]
        )

    # ── Сиды price_freshness_rules (idempotent — только если строки нет) ────
    for scope_kind, scope_key, ttl_days in (
        ("default", "*", 60),
        ("category", "Продукты питания", 14),
        ("category", "Продукты", 14),
    ):
        # asyncpg готовит один PREPARE на весь текст запроса: :scope_kind/:scope_key
        # встречаются дважды (в SELECT-списке без контекста типа и в WHERE против
        # varchar-колонки) — без явного bindparam(type_=...) asyncpg иногда выводит
        # разные типы для одного $N и падает с AmbiguousParameterError ("text versus
        # character varying"), см. правку 2026-08-29 (обнаружено при рестарте backend).
        conn.execute(
            sa.text(
                """
                INSERT INTO price_freshness_rules (org_id, scope_kind, scope_key, ttl_days)
                SELECT NULL, :scope_kind, :scope_key, :ttl_days
                WHERE NOT EXISTS (
                    SELECT 1 FROM price_freshness_rules
                    WHERE org_id IS NULL AND scope_kind = :scope_kind AND scope_key = :scope_key
                )
                """
            ).bindparams(
                sa.bindparam("scope_kind", type_=sa.String(20)),
                sa.bindparam("scope_key", type_=sa.String(200)),
                sa.bindparam("ttl_days", type_=sa.Integer()),
            ),
            {"scope_kind": scope_kind, "scope_key": scope_key, "ttl_days": ttl_days},
        )

    # ── Backfill price_updated_at / price_source для существующих товаров ───
    conn.execute(sa.text(
        """
        UPDATE products SET price_updated_at = contract_date::timestamp,
                             price_source = 'contract',
                             price_source_ref = contract_number
        WHERE price_updated_at IS NULL AND contract_date IS NOT NULL AND price IS NOT NULL
        """
    ))
    conn.execute(sa.text(
        """
        UPDATE products SET price_updated_at = updated_at,
                             price_source = 'manual'
        WHERE price_updated_at IS NULL AND updated_at IS NOT NULL AND price IS NOT NULL
        """
    ))

    # ── Перенос уже существующей цены в историю (идемпотентно) ──────────────
    conn.execute(sa.text(
        """
        INSERT INTO product_price_history
            (product_id, price, source, source_ref, contractor_id, collected_at, created_at)
        SELECT p.id, p.price, p.price_source, p.price_source_ref,
               p.price_source_contractor_id, p.price_updated_at::date, now()
        FROM products p
        WHERE p.price_updated_at IS NOT NULL AND p.price IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM product_price_history h WHERE h.product_id = p.id
          )
        """
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS commercial_request_offers"))
    op.execute(sa.text("DROP TABLE IF EXISTS product_price_history"))
    op.execute(sa.text("DROP TABLE IF EXISTS price_freshness_rules"))
    op.execute(sa.text("DROP TABLE IF EXISTS fx_rates"))

    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS price_ttl_days"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS price_source_contractor_id"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS price_source_ref"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS price_source"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS price_updated_at"))
