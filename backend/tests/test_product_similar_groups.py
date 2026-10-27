"""find_similar_groups — проверка правок после прогона на проде (owner,
27.10.2026): две карточки одного магазина не образуют группу, diff_tokens
реально отличается, артикул производителя группирует «уверенно» независимо
от base_model, типоразмер батарейки (CR2016) у разных брендов — не группа."""
import uuid

import pytest
from sqlalchemy import select

from app.models.contractor import Contractor
from app.models.product import Product
from app.services.product_similar import find_similar_groups

_UNIQ = "ТестПохожГруппы"


def _name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


async def _contractor(db_session, inn: str) -> Contractor:
    existing = (await db_session.execute(
        select(Contractor).where(Contractor.inn == inn)
    )).scalar_one_or_none()
    if existing:
        return existing
    c = Contractor(name=f"Тест {inn}", inn=inn)
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_same_store_two_cards_do_not_form_group(db_session):
    store = await _contractor(db_session, "1110000001")
    db_session.add_all([
        Product(name=_name("ОП-2 Ярпожинвест А"), manufacturer="Ярпожинвест",
                price_source_contractor_id=store.id),
        Product(name=_name("ОП-2 Ярпожинвест Б"), manufacturer="Ярпожинвест",
                price_source_contractor_id=store.id),
    ])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    assert groups == []


@pytest.mark.asyncio
async def test_different_stores_form_group_with_diff_tokens(db_session):
    store1 = await _contractor(db_session, "1110000002")
    store2 = await _contractor(db_session, "1110000003")
    p1 = Product(
        name=_name("Огнетушитель порошковый Ярпожинвест ОП-10(з) ВСЕ ЗПУ Китай"),
        manufacturer="Ярпожинвест",
        price_source_contractor_id=store1.id,
    )
    p2 = Product(
        name=_name("Огнетушитель порошковый Ярпожинвест ОП-10(з) ВСЕ ЗПУ Россия разборное"),
        manufacturer="Ярпожинвест",
        price_source_contractor_id=store2.id,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p1.id in {c.id for c in g.cards})
    by_id = {c.id: c for c in group.cards}
    assert "китай" in by_id[p1.id].diff_tokens
    assert "китай" not in by_id[p2.id].diff_tokens
    assert "россия" in by_id[p2.id].diff_tokens or "разборное" in by_id[p2.id].diff_tokens


@pytest.mark.asyncio
async def test_manufacturer_article_match_is_confident_regardless_of_store(db_session):
    store1 = await _contractor(db_session, "7719079370")  # electro-mpo.ru — article_is_manufacturer=True
    store2 = await _contractor(db_session, "9718172669")  # k-spasatel.ru — article_is_manufacturer=True
    p1 = Product(
        name=_name("Автоматический выключатель DEKraft ВА-1"), manufacturer="DEKraft",
        article="14054DEK", price_source_contractor_id=store1.id,
    )
    p2 = Product(
        name=_name("Выключатель автоматический DEKraft ВА-1"), manufacturer="DEKraft",
        article="14054DEK", price_source_contractor_id=store2.id,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p1.id in {c.id for c in g.cards})
    assert group.confidence == "уверенно"
    assert group.match_key == "article"


@pytest.mark.asyncio
async def test_sima_land_article_not_used_as_manufacturer_code(db_session):
    sima = await _contractor(db_session, "6679104850")  # sima-land.ru — article_is_manufacturer=False
    other = await _contractor(db_session, "1110000004")
    # Оба магазина указывают "одинаковый" СВОЙ номер — не должен сработать
    # как совпадение артикула производителя для sima-land'а (у второго
    # магазина article_is_manufacturer тоже False по умолчанию — тест
    # проверяет именно sima-land отдельно, что его article игнорируется).
    p1 = Product(
        name=_name("Огнетушитель Ярпожинвест ОП-2"), manufacturer="Ярпожинвест",
        article="1431671", price_source_contractor_id=sima.id,
    )
    p2 = Product(
        name=_name("Огнетушитель Ярпожинвест ОП-2"), manufacturer="Ярпожинвест",
        article="1431671", price_source_contractor_id=other.id,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p1.id in {c.id for c in g.cards})
    # Группа есть (по base_model ОП-2), но НЕ по артикулу sima-land'а.
    assert group.match_key == "model"


@pytest.mark.asyncio
async def test_winner_prefers_history_then_store_then_photo_then_description(db_session):
    """Owner 27.10.2026: побеждала карточка без магазина/истории (ОП-2 #2415,
    Makita #4500 без магазина против Бауцентра). Порядок: история → магазин
    → фото → описание → меньший id."""
    store = await _contractor(db_session, "1110000007")
    no_store = Product(
        name=_name("ОП-2 Ярпожинвест без магазина"), manufacturer="Ярпожинвест",
        price_source_contractor_id=None, description="x" * 50,
    )
    with_store = Product(
        name=_name("ОП-2 Ярпожинвест с магазином"), manufacturer="Ярпожинвест",
        price_source_contractor_id=store.id,
    )
    db_session.add_all([no_store, with_store])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if no_store.id in {c.id for c in g.cards})
    assert group.suggested_winner_id == with_store.id


@pytest.mark.asyncio
async def test_same_store_as_winner_not_set_when_both_null(db_session):
    """Owner 27.10.2026: NULL=NULL не считается «тем же магазином» (NULL —
    отдельный источник у каждой карточки, не одна общая метка)."""
    store = await _contractor(db_session, "1110000008")
    p_store = Product(
        name=_name("ОП-2 Ярпожинвест с магазином"), manufacturer="Ярпожинвест",
        price_source_contractor_id=store.id,
    )
    p_null1 = Product(
        name=_name("ОП-2 Ярпожинвест без магазина 1"), manufacturer="Ярпожинвест",
        price_source_contractor_id=None,
    )
    p_null2 = Product(
        name=_name("ОП-2 Ярпожинвест без магазина 2"), manufacturer="Ярпожинвест",
        price_source_contractor_id=None,
    )
    db_session.add_all([p_store, p_null1, p_null2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p_store.id in {c.id for c in g.cards})
    # winner — карточка с магазином (приоритет из предыдущего теста);
    # NULL-карточки не должны быть помечены "тот же магазин, что winner".
    assert group.suggested_winner_id == p_store.id
    by_id = {c.id: c for c in group.cards}
    assert by_id[p_null1.id].same_store_as_winner is False
    assert by_id[p_null2.id].same_store_as_winner is False


@pytest.mark.asyncio
async def test_makita_code_with_cyrillic_lookalike_x_is_confident(db_session):
    """Owner 27.10.2026: «Makita GA5090X01» у двух магазинов (#6857 без
    магазина, #132739 Бауцентра) попал в «проверить» вместо «уверенно» по
    артикулу — источник данных печатает код с кириллической «Х» вместо
    латинской "X" (визуальный гомоглиф)."""
    store = await _contractor(db_session, "1110000009")
    p1 = Product(
        name=_name("Болгарка Makita GA5090X01"), manufacturer="Makita",
        price_source_contractor_id=None,
    )
    p2 = Product(
        # кириллическая "Х" вместо латинской "X" — та самая находка с прода
        name=_name("Makita GA5090Х01 угловая шлифмашина"), manufacturer="Makita",
        price_source_contractor_id=store.id,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p1.id in {c.id for c in g.cards})
    assert group.confidence == "уверенно"
    assert group.match_key == "article"


@pytest.mark.asyncio
async def test_brand_display_not_folded(db_session):
    store1 = await _contractor(db_session, "1110000010")
    store2 = await _contractor(db_session, "1110000011")
    p1 = Product(name=_name("Дрель-шуруповёрт Makita DHP482Z"), manufacturer="Makita",
                 price_source_contractor_id=store1.id)
    p2 = Product(name=_name("Шуруповёрт Makita DHP482Z"), manufacturer="Makita",
                 price_source_contractor_id=store2.id)
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    group = next(g for g in groups if p1.id in {c.id for c in g.cards})
    assert group.brand == "Makita"


@pytest.mark.asyncio
async def test_cr2016_different_brands_not_grouped(db_session):
    store1 = await _contractor(db_session, "1110000005")
    store2 = await _contractor(db_session, "1110000006")
    p1 = Product(name=_name("Батарейка CR2016 Philips"), manufacturer="Philips",
                 price_source_contractor_id=store1.id)
    p2 = Product(name=_name("Батарейка CR2016 Kodak"), manufacturer="Kodak",
                 price_source_contractor_id=store2.id)
    db_session.add_all([p1, p2])
    await db_session.commit()
    groups = await find_similar_groups(db_session, _UNIQ, limit_groups=50)
    ids_in_groups = {c.id for g in groups for c in g.cards}
    assert p1.id not in ids_in_groups
    assert p2.id not in ids_in_groups
