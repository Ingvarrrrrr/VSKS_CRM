"""merge_products (владелец, 27.10.2026) — слияние карточек каталога БЕЗ
ПОТЕРЬ: история цен/фото/ссылки wish_items/purchase_items/contract_items на
winner = сумма до, loser удалён, import_note дописан, описание не стало
короче (ПРАВИЛО №6, app/services/product_merge.py)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.product import Product
from app.models.product_photo import ProductPhoto
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.product_merge import merge_products

_UNIQ = "ТестМерджЯрпожинвест"


def _name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


async def _make_products(db_session):
    winner = Product(name=_name("winner"), description="Короткое")
    loser = Product(name=_name("loser"), description="Длинное описание со множеством технических деталей и характеристик товара")
    db_session.add_all([winner, loser])
    await db_session.flush()
    return winner, loser


@pytest.mark.asyncio
async def test_merge_transfers_everything_and_deletes_loser(db_session, test_user, test_org):
    winner, loser = await _make_products(db_session)

    # история цен
    db_session.add(ProductPriceHistory(product_id=winner.id, price=100, source="manual"))
    db_session.add(ProductPriceHistory(product_id=loser.id, price=110, source="manual"))
    db_session.add(ProductPriceHistory(product_id=loser.id, price=120, source="manual"))

    # фото только у loser'а
    db_session.add(ProductPhoto(product_id=loser.id, data=b"\x00\x01", mime="image/webp", size=2))

    # покупки/заявки/договоры, ссылающиеся на loser
    wish = Wish(org_id=test_org.id, title="test wish " + uuid.uuid4().hex[:6])
    purchase = Purchase()
    db_session.add_all([wish, purchase])
    await db_session.flush()

    wish_item = WishItem(wish_id=wish.id, product_id=loser.id, item_name="x")
    purchase_item = PurchaseItem(purchase_id=purchase.id, product_id=loser.id, item_name="x")
    db_session.add_all([wish_item, purchase_item])
    await db_session.flush()

    contract = Contract(number="C-1", contract_type="single")
    db_session.add(contract)
    await db_session.flush()
    contract_item = ContractItem(purchase_id=purchase.id, contract_id=contract.id, product_id=loser.id, name="x")
    db_session.add(contract_item)
    await db_session.commit()

    report = await merge_products(db_session, winner.id, [loser.id], test_user)
    await db_session.commit()

    assert report["transferred"]["product_price_history"] == 2
    assert report["transferred"]["purchase_items"] == 1
    assert report["transferred"]["wish_items"] == 1
    assert report["transferred"]["contract_items"] == 1
    assert report["transferred"]["product_photo"] == 1

    # loser удалён (Core DELETE не обновляет identity map — проверяем через
    # свежий SELECT, не db_session.get, который вернул бы закэшированный объект)
    assert (await db_session.execute(
        select(Product).where(Product.id == loser.id)
    )).scalar_one_or_none() is None

    # история цен — сумма до (1 исходная + 2 перенесённые)
    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == winner.id)
    )).scalars().all()
    assert len(hist) == 3

    await db_session.refresh(wish_item)
    await db_session.refresh(purchase_item)
    await db_session.refresh(contract_item)
    assert wish_item.product_id == winner.id
    assert purchase_item.product_id == winner.id
    assert contract_item.product_id == winner.id

    winner_photo = await db_session.get(ProductPhoto, winner.id)
    assert winner_photo is not None

    winner_after = await db_session.get(Product, winner.id)
    assert f"№{loser.id}" in (winner_after.import_note or "")
    # описание winner'а не стало короче исходного и несёт данные loser'а
    assert len(winner_after.description) >= len("Короткое")
    assert "техническ" in winner_after.description.lower()


@pytest.mark.asyncio
async def test_merge_fills_empty_scalar_fields_from_loser(db_session, test_user):
    winner = Product(name=_name("winner2"))
    loser = Product(name=_name("loser2"), manufacturer="Ярпожинвест", article="ART-1", unit="шт")
    db_session.add_all([winner, loser])
    await db_session.commit()

    await merge_products(db_session, winner.id, [loser.id], test_user)
    await db_session.commit()

    winner_after = await db_session.get(Product, winner.id)
    assert winner_after.manufacturer == "Ярпожинвест"
    assert winner_after.article == "ART-1"
    assert winner_after.unit == "шт"


@pytest.mark.asyncio
async def test_merge_never_replaces_winner_description_only_appends(db_session, test_user):
    """Owner 27.10.2026: даже когда loser не короче — winner'а не заменяем
    целиком (его выбрал человек в UI, его текст главный), только дописываем
    строки loser'а, которых у winner ещё не было."""
    winner = Product(
        name=_name("winner3"),
        description="Строка winner 1\nСтрока winner 2 уникальная",
    )
    loser = Product(
        name=_name("loser3"),
        description="Строка winner 1\nСтрока только у loser",
    )
    db_session.add_all([winner, loser])
    await db_session.commit()

    await merge_products(db_session, winner.id, [loser.id], test_user)
    await db_session.commit()

    winner_after = await db_session.get(Product, winner.id)
    assert "Строка winner 2 уникальная" in winner_after.description
    assert "Строка только у loser" in winner_after.description


@pytest.mark.asyncio
async def test_merge_does_not_overwrite_verified_description_44fz(db_session, test_user):
    """Owner 27.10.2026: непустое description_44fz winner'а могло быть
    верифицировано (tz_44fz_verified_at) — слияние его не трогает."""
    winner = Product(
        name=_name("winner4"), description_44fz="Проверенное ТЗ 44-ФЗ winner'а",
    )
    loser = Product(
        name=_name("loser4"), description_44fz="Другое ТЗ 44-ФЗ loser'а",
    )
    db_session.add_all([winner, loser])
    await db_session.commit()

    await merge_products(db_session, winner.id, [loser.id], test_user)
    await db_session.commit()

    winner_after = await db_session.get(Product, winner.id)
    assert winner_after.description_44fz == "Проверенное ТЗ 44-ФЗ winner'а"


@pytest.mark.asyncio
async def test_merge_fills_empty_description_44fz_from_loser(db_session, test_user):
    winner = Product(name=_name("winner5"))
    loser = Product(name=_name("loser5"), description_44fz="ТЗ 44-ФЗ loser'а")
    db_session.add_all([winner, loser])
    await db_session.commit()

    await merge_products(db_session, winner.id, [loser.id], test_user)
    await db_session.commit()

    winner_after = await db_session.get(Product, winner.id)
    assert winner_after.description_44fz == "ТЗ 44-ФЗ loser'а"


@pytest.mark.asyncio
async def test_merge_rejects_winner_in_losers(db_session, test_user):
    winner, loser = await _make_products(db_session)
    await db_session.commit()
    with pytest.raises(ValueError):
        await merge_products(db_session, winner.id, [winner.id, loser.id], test_user)


@pytest.mark.asyncio
async def test_merge_rejects_unknown_loser_id(db_session, test_user):
    winner, _loser = await _make_products(db_session)
    await db_session.commit()
    with pytest.raises(ValueError):
        await merge_products(db_session, winner.id, [999_999_999], test_user)
