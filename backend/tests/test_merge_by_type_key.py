"""scripts/merge_by_type_key.py — правило однозначности 1-к-1 (владелец,
27.10.2026, QA-дефект: «три ОУ-3 Спасателя + одна М01» сливались бы в одну
карточку старой группировкой по точному key, без keys_match_unique).
Своей логики сравнения не пишет (ПРАВИЛО №6) — _plan должен звать ТОЛЬКО
product_type_keys.keys_match_unique, этот тест проверяет результат, не
внутреннюю реализацию."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.contractor_resolve import find_or_create_contractor
from scripts.merge_by_type_key import _plan


def _suf() -> str:
    return uuid.uuid4().hex[:8]


async def _make_product(db_session, name: str, contractor_id, store_article: str, price="500"):
    p = Product(name=name, category="Прочее", price=Decimal(price))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    db_session.add(ProductPriceHistory(
        product_id=p.id, price=Decimal(price), source="import",
        contractor_id=contractor_id, store_article=store_article,
    ))
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_one_to_one_different_stores_is_in_plan(db_session):
    """Одна карточка магазина A + одна карточка магазина B с одним и тем
    же полным ключом вида товара — 1-к-1, попадает в план слияния."""
    suf = _suf()
    name_a = f"Огнетушитель порошковый ОП-6 АВСЕ ИНГА {suf}A"
    name_b = f"Огнетушитель порошковый ОП-6-АВСЕ ИНГА {suf}B"

    inn_a = "7701000301"
    inn_b = "7701000302"
    contractor_a = await find_or_create_contractor(db_session, "МергТип-A", inn_a, match_by_name=False)
    contractor_b = await find_or_create_contractor(db_session, "МергТип-B", inn_b, match_by_name=False)

    p_a = await _make_product(db_session, name_a, contractor_a, f"MTK-A-{suf}")
    p_b = await _make_product(db_session, name_b, contractor_b, f"MTK-B-{suf}")

    plan = await _plan(db_session)
    matching = [
        g for g in plan
        if not g["conflict"] and {p_a.id, p_b.id} <= (set(g["loser_ids"]) | {g["winner_id"]})
    ]
    assert len(matching) == 1, plan
    group = matching[0]
    assert {group["winner_id"], *group["loser_ids"]} == {p_a.id, p_b.id}


@pytest.mark.asyncio
async def test_three_cards_one_store_plus_one_other_store_not_in_plan(db_session):
    """Три карточки магазина A с ОДНИМ ключом + одна карточка магазина B с
    тем же ключом — неоднозначно (у магазина A >1 карточки под этим
    ключом), НЕ попадает в план слияния ни в каком виде."""
    suf = _suf()
    names_a = [
        f"Огнетушитель порошковый ОП-7 АВСЕ ИНГА {suf}X1",
        f"Огнетушитель порошковый ОП-7-АВСЕ ИНГА {suf}X2",
        f"Огнетушитель порошковый ОП-7 (АВСЕ) ИНГА {suf}X3",
    ]
    name_b = f"Огнетушитель порошковый ОП-7 АВСЕ ИНГА {suf}Y"

    inn_a = "7701000303"
    inn_b = "7701000304"
    contractor_a = await find_or_create_contractor(db_session, "МергТип-TriA", inn_a, match_by_name=False)
    contractor_b = await find_or_create_contractor(db_session, "МергТип-TriB", inn_b, match_by_name=False)

    ids_a = []
    for i, name in enumerate(names_a):
        p = await _make_product(db_session, name, contractor_a, f"MTK-TRI-A-{i}-{suf}")
        ids_a.append(p.id)
    p_b = await _make_product(db_session, name_b, contractor_b, f"MTK-TRI-B-{suf}")

    plan = await _plan(db_session)
    group_ids = set(ids_a) | {p_b.id}
    touching = [
        g for g in plan
        if (set(g.get("product_ids", [])) & group_ids) or
           ({g.get("winner_id"), *g.get("loser_ids", [])} & group_ids)
    ]
    for g in touching:
        assert g["conflict"] is True, f"группа не должна автоматически сливаться: {g}"


@pytest.mark.asyncio
async def test_dry_run_does_not_write_to_db(db_session):
    """Пробный прогон (_plan) ничего не пишет — только читает и строит
    план; товары/история остаются как были (значения не менялись самим
    _plan — проверяем на уже созданной 1-к-1 паре, что повторный вызов
    _plan идемпотентен и товары не продублировались/не изменились)."""
    suf = _suf()
    name_a = f"Огнетушитель порошковый ОП-8 АВСЕ ИНГА {suf}A"
    name_b = f"Огнетушитель порошковый ОП-8-АВСЕ ИНГА {suf}B"
    inn_a = "7701000305"
    inn_b = "7701000306"
    contractor_a = await find_or_create_contractor(db_session, "МергТип-DryA", inn_a, match_by_name=False)
    contractor_b = await find_or_create_contractor(db_session, "МергТип-DryB", inn_b, match_by_name=False)
    p_a = await _make_product(db_session, name_a, contractor_a, f"MTK-DRY-A-{suf}")
    p_b = await _make_product(db_session, name_b, contractor_b, f"MTK-DRY-B-{suf}")

    await _plan(db_session)
    await _plan(db_session)

    rows = (await db_session.execute(
        select(Product).where(Product.id.in_([p_a.id, p_b.id]))
    )).scalars().all()
    assert len(rows) == 2, "пробный прогон не должен сливать/удалять карточки"
    names = {p.id: p.name for p in rows}
    assert names[p_a.id] == name_a
    assert names[p_b.id] == name_b
