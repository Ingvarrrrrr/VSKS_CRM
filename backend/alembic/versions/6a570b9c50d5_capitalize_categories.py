"""capitalize_categories — привести СУЩЕСТВУЮЩИЕ данные к единому виду
«первая буква заглавная, остальное как есть» (владелец: «приведи, чтобы все
категории начинались с большой буквы»; уточнение 14.10.2026: «где
аббревиатуры и всё большими буквами — не трогать, исправлять только там, где
должно быть с большой, а написано с маленькой»).

Источник капитализации для НОВЫХ записей — backend/app/services/text_case.py
::capitalize_first (ПРАВИЛО №6), уже применяется в коде. Эта миграция
догоняет данные, заведённые до того, как capitalize_first стал вызываться
везде: purchase_categories.name (справочник категорий закупки, name UNIQUE)
и products.category (свободный текст).

Импорт app.services.text_case здесь допустим (не нарушает «миграции не
импортируют app»-конвенцию де-факто): модуль не содержит ни одного импорта,
не трогает БД/настройки/конфиг — чистая функция над строкой. Если это
когда-нибудь изменится — скопировать функцию сюда с комментарием «копия на
дату миграции», а не импортировать модуль с посторонними зависимостями.

Что делает upgrade():
  1. Бэкапы затронутых строк (IF NOT EXISTS — не пересоздаёт, если миграция
     уже гонялась и бэкап остался):
     - bk_20261014_purchase_categories — строки purchase_categories со
       строчной первой буквой (до правки);
     - bk_20261014_ppc_links — связи product_purchase_categories для ЭТИХ
       категорий (до правки, до слияния дублей);
     - bk_20261014_products_category — id+category товаров со строчной
       первой буквой (до правки).
  2. purchase_categories: для каждой строчной категории (по возрастанию id)
     считаем new_name = Upper(первая буква) + остальное как есть.
     - если категория с именем new_name уже существует под другим id —
       это дубль: связи product_purchase_categories переносятся на
       существующую (ON CONFLICT DO NOTHING — пара (product_id,
       purchase_category_id) уже PK), дубль и его связи удаляются;
     - иначе — просто UPDATE name.
     Обработка по возрастанию id делает цепочку "мебель"+" мебель" →
     одна "Мебель" устойчивой: первая строчная переименовывается, вторая
     на следующей итерации видит уже переименованную и сливается в неё.
  3. products.category: прямой UPDATE по тем же правилам, без слияния
     (это свободный текст, не справочник с уникальностью).

Идемпотентно: условие строчной первой буквы (left(btrim(x),1) <>
upper(left(btrim(x),1))) после прогона везде ложно, повторный upgrade
ничего не меняет (кроме CREATE TABLE IF NOT EXISTS бэкапов — те просто
не пересоздаются). downgrade — no-op, данные на случай отката лежат в
bk_20261014_*.

Revision ID: 6a570b9c50d5
Revises: d4f6h8j0k2l4
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from app.services.text_case import capitalize_first

revision = '6a570b9c50d5'
down_revision = 'd4f6h8j0k2l4'
branch_labels = None
depends_on = None


_IS_LOWER_SQL = "left(btrim({col}), 1) <> upper(left(btrim({col}), 1))"


def _capitalize_categories(bind) -> dict:
    """Основная логика — вынесена из upgrade(), чтобы тест мог вызвать её
    напрямую (importlib по пути файла миграции) на тестовой БД без прогона
    самой миграции. bind — синхронный Connection (как из op.get_bind(), так
    и из AsyncConnection.run_sync(...) в тесте — интерфейс .execute()
    одинаковый).

    Возвращает {"renamed": N, "merged": M, "products_updated": K}.
    """
    renamed = 0
    merged = 0

    rows = bind.execute(text(
        f"""
        SELECT id, name FROM purchase_categories
        WHERE {_IS_LOWER_SQL.format(col='name')}
        ORDER BY id
        """
    )).fetchall()

    for cat_id, name in rows:
        new_name = capitalize_first(name)
        if not new_name or new_name == name:
            # Аббревиатура (напр. "лкп") — capitalize_first её не трогает,
            # SQL-предвыбор по регистру первой буквы это не знает, поэтому
            # отфильтровываем здесь (ПРАВИЛО №6: решение владельца 14.10.2026).
            continue

        existing = bind.execute(
            text("SELECT id FROM purchase_categories WHERE name = :new_name AND id <> :cat_id"),
            {"new_name": new_name, "cat_id": cat_id},
        ).fetchone()

        if existing:
            target_id = existing[0]
            bind.execute(
                text(
                    """
                    INSERT INTO product_purchase_categories (product_id, purchase_category_id)
                    SELECT product_id, :target_id
                    FROM product_purchase_categories
                    WHERE purchase_category_id = :cat_id
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"target_id": target_id, "cat_id": cat_id},
            )
            bind.execute(
                text("DELETE FROM product_purchase_categories WHERE purchase_category_id = :cat_id"),
                {"cat_id": cat_id},
            )
            bind.execute(
                text("DELETE FROM purchase_categories WHERE id = :cat_id"),
                {"cat_id": cat_id},
            )
            merged += 1
        else:
            bind.execute(
                text("UPDATE purchase_categories SET name = :new_name WHERE id = :cat_id"),
                {"new_name": new_name, "cat_id": cat_id},
            )
            renamed += 1

    # SQL-предвыбор (по регистру первой буквы) — только грубый фильтр
    # кандидатов; решение "менять/не менять" (аббревиатура или нет) принимает
    # capitalize_first в Python, поэтому обновляем по одной строке, а не
    # одним UPDATE на всю таблицу.
    product_rows = bind.execute(text(
        f"""
        SELECT id, category FROM products
        WHERE category IS NOT NULL
          AND {_IS_LOWER_SQL.format(col='category')}
        """
    )).fetchall()

    products_updated = 0
    for product_id, category in product_rows:
        new_category = capitalize_first(category)
        if not new_category or new_category == category:
            continue
        bind.execute(
            text("UPDATE products SET category = :new_category WHERE id = :product_id"),
            {"new_category": new_category, "product_id": product_id},
        )
        products_updated += 1

    return {"renamed": renamed, "merged": merged, "products_updated": products_updated}


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text(
        f"""
        CREATE TABLE IF NOT EXISTS bk_20261014_purchase_categories AS
        SELECT * FROM purchase_categories
        WHERE {_IS_LOWER_SQL.format(col='name')}
        """
    ))
    bind.execute(text(
        f"""
        CREATE TABLE IF NOT EXISTS bk_20261014_ppc_links AS
        SELECT ppc.* FROM product_purchase_categories ppc
        WHERE ppc.purchase_category_id IN (
            SELECT id FROM purchase_categories
            WHERE {_IS_LOWER_SQL.format(col='name')}
        )
        """
    ))
    bind.execute(text(
        f"""
        CREATE TABLE IF NOT EXISTS bk_20261014_products_category AS
        SELECT id, category FROM products
        WHERE category IS NOT NULL
          AND {_IS_LOWER_SQL.format(col='category')}
        """
    ))

    stats = _capitalize_categories(bind)
    print(
        "[6a570b9c50d5 capitalize_categories] "
        f"переименовано={stats['renamed']} слито={stats['merged']} "
        f"товаров_обновлено={stats['products_updated']}"
    )


def downgrade() -> None:
    # Разовый бэкфилл — откат не восстанавливает прежний регистр из кода;
    # исходные строки лежат в bk_20261014_purchase_categories /
    # bk_20261014_ppc_links / bk_20261014_products_category на случай
    # ручного восстановления.
    pass
