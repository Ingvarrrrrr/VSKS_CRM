"""Словарь слов каталога — materialized view product_words (владелец,
28.10.2026, доработка «этап 0»: исправление опечаток ПО СЛОВАМ, а не
trgm-похожестью по ВСЕЙ строке названия — тот старый механизм матчил
посторонние товары, см. отчёт сессии: «огнетушитель порошковый 4 кг»
находил кабели/автоматы).

product_words — ОДНА колонка word: буквенные (без цифр) слова ≥3 символов,
встречающиеся в products.name, lower-case, DISTINCT. Источник — обычные
слова названия (regexp-разбор), НЕ стеммированные лексемы ts_stat() —
исправление опечаток должно предлагать РЕАЛЬНОЕ написание слова из
каталога («огнетушитель»), не стеммированный обрубок («огнетушител»).

UNIQUE индекс по word — обязателен для REFRESH MATERIALIZED VIEW
CONCURRENTLY (app/services/product_words_correction.py вызывает именно
CONCURRENTLY — не блокирует чтение словаря во время обновления). GIN trgm-
индекс по word — для similarity()/оператора `%` при подборе ближайшего
слова (та же экстеншн pg_trgm, что уже используется ix_products_name_trgm
и др., CREATE EXTENSION уже выполнен в r5s7u9w1y3a5, здесь не дублируем)."""
from alembic import op


# revision identifiers, used by Alembic.
revision = "w2x4y6z8a0b2"
down_revision = "f3t5s7q9u1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS product_words AS
        SELECT DISTINCT lower(m[1]) AS word
        FROM products, regexp_matches(name, '[a-zA-Zа-яёА-ЯЁ]{3,}', 'g') AS m
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_product_words_word "
            "ON product_words (word)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_product_words_word_trgm "
            "ON product_words USING gin (word gin_trgm_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_product_words_word_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_product_words_word")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS product_words")
