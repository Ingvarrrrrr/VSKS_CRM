import pytest
from sqlalchemy import select
from app.models.wish import Wish
from app.services.wish_filters import apply_wish_filters, _parse_id_list


def test_parse_id_list():
    assert _parse_id_list(None) is None
    assert _parse_id_list("") is None
    assert _parse_id_list("   ") is None
    assert _parse_id_list("1, 2, 3") == [1, 2, 3]
    assert _parse_id_list([5, "6", None, "abc"]) == [5, 6]
    assert _parse_id_list(10) == [10]


@pytest.mark.asyncio
async def test_apply_wish_filters_logic():
    q = select(Wish)

    # Проверяем creator_id (обратная совместимость)
    q1 = await apply_wish_filters(q, None, creator_id=5)
    assert "wishes.created_by" in str(q1)

    # Проверяем creator_ids (список через запятую)
    q2 = await apply_wish_filters(q, None, creator_ids="1,2,3")
    assert "wishes.created_by" in str(q2)

    # Проверяем wish_types='advance_report'
    q_adv = await apply_wish_filters(q, None, wish_types="advance_report")
    assert "wishes.source" in str(q_adv)

    # Проверяем wish_types='regular'
    q_reg = await apply_wish_filters(q, None, wish_types="regular")
    assert "wishes.source" in str(q_reg)

    # Проверяем wish_types='advance_report,regular' (оба — условие не добавляется или не ограничивает)
    q_both = await apply_wish_filters(q, None, wish_types="advance_report,regular")
    # Строковое представление не должно содержать жесткого фильтра источника
    assert str(q_both) == str(q)
