"""Тесты app.services.store_search.cross_store_prices._offer_matches —
«тот же товар» в другом магазине (этап 2, вариант А, задача «цены того же
товара в других магазинах», владелец 29-30.10.2026). Чистая логика сравнения
(без сети/БД, ПРАВИЛО того же подхода, что test_store_take.py::_no_network) —
проверяет ровно дефект QA 30.10.2026: «Взять» из chipdip (manufacturer
предложения ВСЕГДА пуст — нет store_pages-парсера, см. docstring take.py) не
находило ни одной цены в других магазинах, хотя бренд буквально есть в
названии («Перфоратор Makita HR2652»). Фикс — offer_brand/own_brand_norm
падают на brand_dictionary.find_in_name(), когда manufacturer пуст (ПРАВИЛО
№6 — тот же словарь, что product_query_parse/service.search_stores)."""
from decimal import Decimal

from app.services.product_name_signature import build_signature
from app.services.store_search.base import StoreOffer
from app.services.store_search.cross_store_prices import _norm_code, _offer_matches


class _FakeBrandDictionary:
    """.find_in_name того же контракта, что ManufacturerBrandDictionary —
    только буквально ищет «Makita»/«Bosch» в тексте (без фонетики/регулярки,
    достаточно для теста этого модуля, см. docstring)."""

    def find_in_name(self, name: str):
        lowered = (name or "").lower()
        if "makita" in lowered:
            return "Makita"
        if "bosch" in lowered:
            return "Bosch"
        return None


def _offer(name: str, manufacturer=None, store_article=None, price=Decimal("100")) -> StoreOffer:
    return StoreOffer(
        store_key="regard",
        store_name="Регард",
        seller_inn=None,
        name=name,
        price=price,
        url="https://www.regard.ru/catalog?x=1",
        store_article=store_article,
        manufacturer=manufacturer,
    )


def test_offer_matches_uses_brand_dictionary_when_manufacturer_missing():
    """chipdip-подобный случай: manufacturer ни у товара, ни у предложения
    (оба None), но бренд есть в тексте названия обеих сторон — ДОЛЖНО
    совпасть по артикулу. Без фикса own_brand_norm/offer_brand_norm были бы
    пустыми строками, _offer_matches вернул бы False всегда."""
    brand_dictionary = _FakeBrandDictionary()
    own_sig = build_signature(
        {"name": "Перфоратор Makita HR2652, 800 Вт", "manufacturer": None, "characteristics": []},
        brand_dictionary,
    )
    own_brand_norm = _norm_code("Makita")
    own_article_norm = _norm_code("HR2652")
    offer = _offer("Перфоратор Makita HR2652", manufacturer=None, store_article="HR2652")

    assert _offer_matches(offer, own_article_norm, own_brand_norm, own_sig, brand_dictionary) is True


def test_offer_matches_rejects_different_brand_even_with_dictionary():
    """Разные бренды (Makita vs Bosch) — НЕ совпадение, даже если оба
    распознаны словарём из текста названия (ОБЯЗАТЕЛЬНОЕ совпадение бренда,
    ПРАВИЛО задания — никакого fuzzy)."""
    brand_dictionary = _FakeBrandDictionary()
    own_sig = build_signature(
        {"name": "Перфоратор Makita HR2652", "manufacturer": None, "characteristics": []},
        brand_dictionary,
    )
    own_brand_norm = _norm_code("Makita")
    own_article_norm = _norm_code("HR2652")
    offer = _offer("Перфоратор Bosch GBH 2-26", manufacturer=None, store_article="GBH226")

    assert _offer_matches(offer, own_article_norm, own_brand_norm, own_sig, brand_dictionary) is False


def test_offer_matches_without_brand_dictionary_falls_back_to_manufacturer_field():
    """brand_dictionary=None (вызывающий код всегда передаёт построенный
    словарь, но функция не должна падать без него, деградация как у
    остальных мест, использующих этот словарь) — сравнение работает, когда
    manufacturer заполнен явно."""
    own_sig = build_signature(
        {"name": "Перфоратор Makita HR2652", "manufacturer": "Makita", "characteristics": []},
    )
    own_brand_norm = _norm_code("Makita")
    own_article_norm = _norm_code("HR2652")
    offer = _offer("Перфоратор HR2652", manufacturer="Makita", store_article="HR2652")

    assert _offer_matches(offer, own_article_norm, own_brand_norm, own_sig, None) is True


def test_offer_matches_champion_chainsaw_bar_across_chipdip_and_avtoall():
    """Шина для бензопилы CHAMPION 140SPEA041 из ChipDip и AvtoAll (с разными
    внутренними store_article '8040965460' и '307792') распознаётся как один и
    тот же товар по сигнатуре названия и артикулу производителя в названии."""
    own_sig = build_signature({
        "name": '140SPEA041, Шина для бензопилы 14" 3/8" 1.3мм 52 звена CHAMPION',
        "manufacturer": "Champion",
        "characteristics": [],
    })
    own_brand_norm = _norm_code("Champion")
    own_article_norm = _norm_code("8040965460")
    avtoall_offer = _offer(
        'Шина для бензопилы 14" 3/8" 1.3мм 52 звена CHAMPION 140SPEA041',
        manufacturer="CHAMPION",
        store_article="307792",
        price=Decimal("620"),
    )
    assert _offer_matches(avtoall_offer, own_article_norm, own_brand_norm, own_sig, None) is True


def test_take_find_existing_product_merges_across_stores_by_name_signature(monkeypatch):
    """Если товар уже взят из первого магазина (ChipDip), нажатие «Взять» на
    предложении второго магазина (AvtoAll) находит существующую карточку через
    load_name_model_candidates + match() == 'auto', а не создаёт вторую."""
    import asyncio
    from app.models.product import Product
    from app.services.product_name_signature import grouping_key
    from app.services.products_import_match_name_model import NameModelCandidate
    from app.services.store_search import take as take_module

    existing_product = Product(
        id=42,
        name='140SPEA041, Шина для бензопилы 14" 3/8" 1.3мм 52 звена CHAMPION',
        manufacturer="Champion",
        article="8040965460",
    )
    existing_sig = build_signature({
        "name": existing_product.name,
        "manufacturer": existing_product.manufacturer,
        "characteristics": [],
    })

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeDb:
        async def execute(self, stmt):
            return _FakeScalarResult()

    async def _no_store_art(db, pairs):
        return {}

    async def _no_brand_art(db, pairs):
        return {}

    async def _fake_brand_dict(db):
        return None

    async def _fake_nm_candidates(db, sigs, brand_dictionary=None):
        key = grouping_key(existing_sig)
        return {
            key: [
                NameModelCandidate(
                    product=existing_product,
                    signature=existing_sig,
                    history_count=1,
                    store_pairs={(10, "8040965460")},
                )
            ]
        }

    monkeypatch.setattr(take_module, "load_candidates_by_store_article", _no_store_art)
    monkeypatch.setattr(take_module, "load_candidates_by_brand_article", _no_brand_art)
    monkeypatch.setattr(take_module, "get_manufacturer_brand_dictionary", _fake_brand_dict)
    monkeypatch.setattr(take_module, "load_name_model_candidates", _fake_nm_candidates)

    avtoall_offer = _offer(
        'Шина для бензопилы 14" 3/8" 1.3мм 52 звена CHAMPION 140SPEA041',
        manufacturer="CHAMPION",
        store_article="307792",
        price=Decimal("620"),
    )
    found = asyncio.run(
        take_module._find_existing_product(
            _FakeDb(),
            avtoall_offer,
            contractor_id=20,
            manufacturer="CHAMPION",
            article="307792",
            characteristics=[],
        )
    )
    assert found is existing_product


