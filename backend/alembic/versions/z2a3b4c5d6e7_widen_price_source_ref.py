"""Расширение source_ref/price_source_ref до 1000 символов (владелец,
26.10.2026) — ссылка на страницу товара у части магазинов каталога GALA
(vseinstrumenti.ru с utm-метками и т.п., проверено на реальных файлах из
C:\\Users\\1\\Downloads) доходит до 607 символов, старые String(300) обрезали
бы такую запись. ПРАВИЛО №6 — обе колонки хранят одну и ту же величину
("источник цены — ссылка/№", см. app/services/price_actualization.py), расширены
вместе в одной миграции.

Идемпотентно: ALTER COLUMN ... TYPE на VARCHAR с большей длиной безопасен и
повторный прогон не ломается (Postgres молча не делает ничего, если тип уже
совпадает — проверка через information_schema не нужна, см. аналогичную
f3a4b5c6d7e8_widen_wish_item_type.py).
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "z2a3b4c5d6e7"
down_revision = "r5s7u9w1y3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE product_price_history ALTER COLUMN source_ref TYPE VARCHAR(1000);")
    op.execute("ALTER TABLE products ALTER COLUMN price_source_ref TYPE VARCHAR(1000);")


def downgrade() -> None:
    op.execute("ALTER TABLE product_price_history ALTER COLUMN source_ref TYPE VARCHAR(300);")
    op.execute("ALTER TABLE products ALTER COLUMN price_source_ref TYPE VARCHAR(300);")
