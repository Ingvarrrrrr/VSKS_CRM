"""Проверяет, что ORM-выражение группировки дублей
(app.services.product_dedup_sql.sql_dedup_normalized_name_expr) и текст
функционального индекса (dedup_normalized_name_sql_text, использован в
миграции r5s7u9w1y3a5::ix_products_dedup_normalized_name) дают ОДИН И ТОТ
ЖЕ ключ на одних и тех же строках — т.е. GROUP BY в
POST /api/products/deduplicate реально опирается на формулу индекса, не на
текстуально похожую, но фактически другую.

Сравнение сделано через живой запрос к БД (не через сравнение
скомпилированного SQL-текста): SQLAlchemy при compile(literal_binds=True)
экранирует '%' под paramstyle драйвера (получается '%%'), текстовое
сравнение с ручным SQL дало бы ложное расхождение, см. докстринг
product_dedup_sql.py."""
import pytest
from sqlalchemy import func, select, text

from app.models.product import Product
from app.services.product_dedup_sql import (
    dedup_normalized_name_sql_text,
    sql_dedup_normalized_name_expr,
)


@pytest.mark.asyncio
async def test_orm_expr_and_index_sql_text_agree(db_session):
    samples = [
        "Кабель ВВГнг-LS 3x2.5",
        "кабель  ввгнг-ls   3x2.5!!",
        "Карабин «Ozone» (с муфтой), red/blue",
        "ЁЖИК ТЕСТ ё-Е",
        "100% шерсть — пряжа_тест",
    ]
    ids = []
    for name in samples:
        p = Product(name=name)
        db_session.add(p)
        await db_session.flush()
        ids.append(p.id)
    await db_session.commit()

    orm_rows = (await db_session.execute(
        select(Product.id, sql_dedup_normalized_name_expr()).where(Product.id.in_(ids))
    )).all()
    orm_keys = {row[0]: row[1] for row in orm_rows}

    index_expr_sql = dedup_normalized_name_sql_text("name")
    id_list_sql = ",".join(str(i) for i in ids)
    raw_rows = (await db_session.execute(
        text(f"SELECT id, {index_expr_sql} FROM products WHERE id IN ({id_list_sql})")
    )).all()
    raw_keys = {row[0]: row[1] for row in raw_rows}

    assert orm_keys == raw_keys
    # И содержательно не пустые/различающиеся — не совпадение по "оба вернули None".
    assert all(v for v in orm_keys.values())
