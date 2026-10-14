"""Тест миграции 6a570b9c50d5 (capitalize_categories) — владелец: «приведи,
чтобы все категории начинались с большой буквы».

Логика вынесена в _capitalize_categories внутри самого файла миграции
(importlib по пути, см. docstring миграции) — тест грузит эту функцию и
гоняет её на тестовой БД (db_session).

db_session — реальная локальная БД (SAVEPOINT-изоляция, см. conftest), в ней
могут уже лежать строчные категории из обычной работы стенда — поэтому перед
проверкой счётчиков делаем «прогрев»: один вызов _capitalize_categories,
который приводит к единому виду всё, что уже было в базе. После прогрева
делаем свои вставки с уникальным суффиксом (uuid) — тогда счётчики из
следующего вызова относятся ровно к тестовым данным, а не к посторонним
строкам стенда.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "6a570b9c50d5_capitalize_categories.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("capitalize_categories_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run(conn, migration):
    return await conn.run_sync(lambda sync_conn: migration._capitalize_categories(sync_conn))


@pytest.mark.asyncio
async def test_capitalize_categories_merge_and_products(db_session, test_org):
    """"мебель"+"Мебель" с разными товарами -> одна "Мебель", оба товара
    связаны; "сиз оборудование" -> "Сиз оборудование"; "СИЗ" не меняется;
    products.category "прочее" -> "Прочее"."""
    migration = _load_migration_module()
    conn = await db_session.connection()

    # Прогрев — приводим к единому виду то, что уже было в стенде до теста,
    # чтобы дальнейшие счётчики считали только наши тестовые строки.
    await _run(conn, migration)

    sfx = uuid.uuid4().hex[:8]
    name_lower = f"мебель_{sfx}"
    name_upper = f"Мебель_{sfx}"
    name_siz_oborud = f"сиз оборудование_{sfx}"
    name_siz = f"СИЗ_{sfx}"

    res = await db_session.execute(text(
        "INSERT INTO purchase_categories (name) VALUES (:a), (:b), (:c), (:d) RETURNING id, name"
    ), {"a": name_lower, "b": name_upper, "c": name_siz_oborud, "d": name_siz})
    rows = {name: cid for cid, name in res.fetchall()}
    lower_mebel_id = rows[name_lower]
    upper_mebel_id = rows[name_upper]
    siz_oborud_id = rows[name_siz_oborud]
    siz_id = rows[name_siz]

    # Товары: по одному на каждую из "мебель" (lower) и "Мебель" (upper) —
    # после слияния оба должны оказаться привязаны к выжившей записи.
    res = await db_session.execute(text(
        "INSERT INTO products (name, category, org_id) VALUES "
        "('Стол', 'Прочее', :org), ('Стул', 'Прочее', :org) "
        "RETURNING id"
    ), {"org": test_org.id})
    product_ids = [r[0] for r in res.fetchall()]
    table_id, chair_id = product_ids

    await db_session.execute(text(
        "INSERT INTO product_purchase_categories (product_id, purchase_category_id) VALUES "
        "(:p1, :c1), (:p2, :c2)"
    ), {"p1": table_id, "c1": lower_mebel_id, "p2": chair_id, "c2": upper_mebel_id})

    # products.category со строчной буквы (уникальный маркер в имени, чтобы
    # UPDATE WHERE-условие по регистру не задело посторонние строки стенда)
    gloves_category = f"прочее_{sfx}"
    res = await db_session.execute(text(
        "INSERT INTO products (name, category, org_id) VALUES "
        "('Перчатки', :cat, :org) RETURNING id"
    ), {"cat": gloves_category, "org": test_org.id})
    gloves_id = res.fetchone()[0]

    await db_session.commit()

    stats = await _run(conn, migration)

    assert stats["merged"] == 1  # "мебель_sfx" слилась в "Мебель_sfx"
    assert stats["renamed"] == 1  # "сиз оборудование_sfx" -> "Сиз оборудование_sfx"
    assert stats["products_updated"] == 1  # "прочее_sfx" -> "Прочее_sfx"

    # "мебель_sfx" (lower id) удалена, "Мебель_sfx" осталась
    res = await db_session.execute(
        text("SELECT id, name FROM purchase_categories WHERE id IN (:a, :b)"),
        {"a": lower_mebel_id, "b": upper_mebel_id},
    )
    survivors = res.fetchall()
    assert survivors == [(upper_mebel_id, name_upper)]

    # Оба товара привязаны к выжившей "Мебель_sfx"
    res = await db_session.execute(
        text("SELECT product_id FROM product_purchase_categories WHERE purchase_category_id = :c"),
        {"c": upper_mebel_id},
    )
    linked = {r[0] for r in res.fetchall()}
    assert linked == {table_id, chair_id}

    # "сиз оборудование_sfx" переименована
    res = await db_session.execute(
        text("SELECT name FROM purchase_categories WHERE id = :c"), {"c": siz_oborud_id}
    )
    assert res.fetchone()[0] == f"Сиз оборудование_{sfx}"

    # "СИЗ_sfx" не тронута (первая буква уже заглавная, акроним не меняем)
    res = await db_session.execute(text("SELECT name FROM purchase_categories WHERE id = :c"), {"c": siz_id})
    assert res.fetchone()[0] == name_siz

    # products.category "прочее_sfx" -> "Прочее_sfx"
    res = await db_session.execute(text("SELECT category FROM products WHERE id = :p"), {"p": gloves_id})
    assert res.fetchone()[0] == f"Прочее_{sfx}"


@pytest.mark.asyncio
async def test_capitalize_categories_idempotent(db_session, test_org):
    """Повторный вызов на уже капитализированных данных ничего не меняет."""
    migration = _load_migration_module()
    conn = await db_session.connection()

    # Прогрев — та же причина, что и в первом тесте.
    await _run(conn, migration)

    sfx = uuid.uuid4().hex[:8]
    name_lower = f"строчная_{sfx}"
    category_lower = f"строчная_{sfx}"

    await db_session.execute(text("INSERT INTO purchase_categories (name) VALUES (:n)"), {"n": name_lower})
    await db_session.execute(text(
        "INSERT INTO products (name, category, org_id) VALUES ('Молоток', :cat, :org)"
    ), {"cat": category_lower, "org": test_org.id})
    await db_session.commit()

    first = await _run(conn, migration)
    assert first["renamed"] == 1
    assert first["merged"] == 0
    assert first["products_updated"] == 1

    second = await _run(conn, migration)
    assert second == {"renamed": 0, "merged": 0, "products_updated": 0}
