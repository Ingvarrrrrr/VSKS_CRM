import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product import Product
from app.product_matcher import find_matching_product, name_similarity, _tokens


@pytest.mark.asyncio
async def test_product_matcher_oom_cases(db_session: AsyncSession):
    # Создаем тестовые товары
    p1 = Product(name="Карабин стальной с муфтой", price=100.0, is_active=True, org_id=1)
    p2 = Product(name="Обычный товар без совпадений", price=50.0, is_active=True, org_id=1)
    db_session.add_all([p1, p2])
    await db_session.commit()

    # 1. Пустая строка / спецсимволы
    assert await find_matching_product(db_session, "") is None
    assert await find_matching_product(db_session, "   ") is None
    assert await find_matching_product(db_session, "%_") is None

    # 2. Точное совпадение
    res_exact = await find_matching_product(db_session, "Карабин стальной с муфтой", org_id=1)
    assert res_exact is not None
    assert res_exact.id == p1.id

    # 3. Fuzzy совпадение
    res_fuzzy = await find_matching_product(db_session, "Карабин муфтой", org_id=1)
    assert res_fuzzy is not None
    assert res_fuzzy.id == p1.id

    # 4. Проверка org_id фильтрации
    res_wrong_org = await find_matching_product(db_session, "Карабин стальной с муфтой", org_id=999)
    assert res_wrong_org is None


def test_tokens_and_similarity():
    tokens = _tokens("Карабин стальной с муфтой 12%")
    assert "карабин" in tokens
    assert "стальной" in tokens
    assert "муфтой" in tokens
    assert "с" not in tokens  # стоп-слово

    sim = name_similarity("Карабин муфтой", "Карабин стальной с муфтой")
    assert sim >= 0.7
