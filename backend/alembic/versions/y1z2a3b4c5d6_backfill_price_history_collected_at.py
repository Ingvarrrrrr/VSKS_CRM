"""Backfill: ProductPriceHistory.collected_at и Product.price_updated_at для
строк, у которых дата актуализации осталась NULL (владелец, 2026-09-20: «все
цены старше 60 дней», «на основании 1 цены», прочерки в колонке «Дата» —
после импорта ТЗ, purchase_items_import(_mapped).py → items_import_catalog.py).

Причина: обе ветки _upsert_product_to_catalog/_apply_import_to_existing_product
(app/services/items_import_catalog.py) звали actualize_product_price БЕЗ
collected_at — ProductPriceHistory.collected_at оставался NULL, а у нового
товара price вообще ставился напрямую в конструкторе Product(...), в обход
actualize_product_price — price_updated_at тоже оставался NULL. Код исправлен
отдельно (та же ревизия сессии); эта миграция — только backfill уже
загруженных данных, ОДНА функция-источник (actualize_product_price) не
дублируется здесь второй формулой.

Два шага, идемпотентны (WHERE ... IS NULL — повторный прогон ничего не меняет):
  (a) product_price_history.collected_at IS NULL → created_at::date
      (created_at — server_default=now(), всегда заполнен, дата вставки строки
      истории = дата фактической актуализации).
  (b) products.price_updated_at IS NULL, price IS NOT NULL → MAX(collected_at)
      среди строк истории этого товара (после шага (a) — уже заполнен там, где
      история вообще есть; товары без единой строки истории (цена когда-то
      попала в БД мимо actualize_product_price) остаются NULL — «never», что и
      есть честная оценка: неизвестно, откуда и когда взята эта цена).

Downgrade: намеренно no-op — откат означал бы стирание уже верных дат.

Revision ID: y1z2a3b4c5d6
Revises: x9y1z3a5b7c9
Create Date: 2026-09-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "y1z2a3b4c5d6"
down_revision = "x9y1z3a5b7c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    result_a = conn.execute(sa.text(
        """
        UPDATE product_price_history
        SET collected_at = created_at::date
        WHERE collected_at IS NULL
        """
    ))
    print(f"[y1z2a3b4c5d6] (a) product_price_history.collected_at заполнен из created_at: {result_a.rowcount}")

    result_b = conn.execute(sa.text(
        """
        UPDATE products p
        SET price_updated_at = h.max_collected::timestamp
        FROM (
            SELECT product_id, MAX(collected_at) AS max_collected
            FROM product_price_history
            WHERE collected_at IS NOT NULL
            GROUP BY product_id
        ) h
        WHERE p.id = h.product_id
          AND p.price IS NOT NULL
          AND p.price_updated_at IS NULL
        """
    ))
    print(f"[y1z2a3b4c5d6] (b) products.price_updated_at заполнен из MAX(collected_at) истории: {result_b.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
