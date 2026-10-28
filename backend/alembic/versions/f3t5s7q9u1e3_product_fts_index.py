"""Полнотекстовый GIN-индекс каталога товаров под поиск «как помнит»
(владелец, 28.10.2026 — встроенный полнотекстовый поиск PostgreSQL вместо
самописного AND/словоформ, см. app/services/product_search.py::
_FTS_DOC_SQL/_search_products_specific).

Выражение индекса ТЕКСТУАЛЬНО совпадает с app/services/product_search.py
::_FTS_DOC_SQL (Правило №6 — один источник формулы, не плодим второй
литерал здесь) — иначе планировщик не свяжет запрос с этим индексом (сверено
EXPLAIN ANALYZE, см. отчёт сессии: без точного совпадения выражения — Seq
Scan вместо Bitmap Index Scan).

CREATE INDEX CONCURRENTLY — тем же приёмом autocommit_block, что и
r5s7u9w1y3a5 (не блокирует запись в products во время построения на проде)."""
from alembic import op


# revision identifiers, used by Alembic.
revision = "f3t5s7q9u1e3"
down_revision = "c3d5e7f9a1b3"
branch_labels = None
depends_on = None

# ДОЛЖНО быть идентично app/services/product_search.py::_FTS_DOC_SQL.
_FTS_DOC_SQL = (
    "to_tsvector('russian', coalesce(name,'') || ' ' || "
    "coalesce(manufacturer,'') || ' ' || coalesce(article,''))"
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_products_fts "
            f"ON products USING gin ({_FTS_DOC_SQL})"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_products_fts")
