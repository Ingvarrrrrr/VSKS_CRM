"""Справочник категорий закупки — добавить все категории товара (владелец,
пункт «С22», 2026-10-07): «В категории закупки добавь сразу все категории
товара, а то там сейчас только те, которые я сам добавлял».

purchase_categories — отдельный глобальный справочник (см.
app/models/purchase_category.py). До этой миграции в нём были только строки,
которые владелец заводил руками через UI; сама категория товара
(Product.category, одна строка на товар, каталог общий, org_id=NULL) никогда
туда не копировалась.

Data-миграция: берём DISTINCT trim(products.category) по ВСЕМ товарам
(активным и нет — справочник категорий закупки не завязан на активность
товара), игнорируем пустые, и вставляем в purchase_categories те значения,
которых там ещё нет. Сравнение на «уже есть» — без учёта регистра и повторных
пробелов (lower(regexp_replace(trim(name), '\s+', ' ', 'g'))), но вставляем
исходную строку КАК ЕСТЬ — без fuzzy-объединения соседних написаний
(«СИЗ» и «сиз» в products.category — это будет ДВЕ разные строки в
purchase_categories, если обе уже не совпадают с тем, что есть; разбирать
дубли написания — отдельная ручная задача владельца, не эта миграция).

sort_order — после всех существующих, по алфавиту (так новые категории не
перемешиваются с уже расставленным владельцем порядком).

Идемпотентно: INSERT … WHERE NOT EXISTS, безопасно гонять повторно (alembic
upgrade head при каждом деплое).

downgrade: ничего не удаляет. Любая из этих категорий могла быть использована
заявками/закупками уже в момент применения миграции (это активно используемый
справочник, не черновая таблица) — откатывать значило бы рвать внешние ключи
или тихо прятать категории, которыми уже воспользовались. Если понадобится
убрать конкретные ошибочные строки — отдельная ручная операция, не downgrade.

Revision ID: f2h4j6l8n0p2
Revises: e3f5g7h9i1j3
Create Date: 2026-10-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2h4j6l8n0p2'
down_revision = 'e3f5g7h9i1j3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        WITH distinct_categories AS (
            SELECT DISTINCT btrim(category) AS name
            FROM products
            WHERE coalesce(btrim(category), '') <> ''
        ),
        to_insert AS (
            SELECT dc.name
            FROM distinct_categories dc
            WHERE NOT EXISTS (
                SELECT 1 FROM purchase_categories pc
                WHERE lower(regexp_replace(btrim(pc.name), '\\s+', ' ', 'g'))
                    = lower(regexp_replace(dc.name, '\\s+', ' ', 'g'))
            )
        ),
        ordered AS (
            SELECT name, row_number() OVER (ORDER BY name) AS rn
            FROM to_insert
        ),
        base AS (
            SELECT coalesce(max(sort_order), 0) AS max_sort FROM purchase_categories
        )
        INSERT INTO purchase_categories (name, sort_order, is_active, created_at)
        SELECT ordered.name, base.max_sort + ordered.rn, true, now()
        FROM ordered, base
        """
    ))


def downgrade() -> None:
    # Ничего не удаляем — см. пояснение в заголовке файла: категории,
    # вставленные этой миграцией, могли уже попасть в закупки/заявки.
    pass
