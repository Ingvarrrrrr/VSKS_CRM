"""Тесты services/catalog_gala/stores.py — единственный справочник «домен
магазина → ИНН» (владелец, 26.10.2026). Проверяет домены, поддомены, www.,
и разбор текста source_store ("Магазин (домен.ru)")."""
from app.services.catalog_gala.stores import (
    domain_from_url, seller_inn_for_source_store, seller_inn_for_url,
    store_for_domain, store_for_inn,
)


def test_domain_from_url_strips_scheme_www_path_query():
    assert domain_from_url("https://www.sima-land.ru/item/123?utm=x") == "sima-land.ru"
    assert domain_from_url("http://baucenter.ru/item/1") == "baucenter.ru"
    assert domain_from_url(None) is None
    assert domain_from_url("") is None


def test_seller_inn_for_url_known_domains():
    assert seller_inn_for_url("https://sima-land.ru/item/123") == "6679104850"
    assert seller_inn_for_url("https://www.baucenter.ru/item/1") == "7702596813"
    assert seller_inn_for_url("https://electro-mpo.ru/p/1") == "7719079370"
    assert seller_inn_for_url("https://vkusvill.ru/p/1") == "7734443270"
    assert seller_inn_for_url("https://k-spasatel.ru/p/1") == "9718172669"
    assert seller_inn_for_url("https://magazin01.ru/p/1") == "7718595621"
    assert seller_inn_for_url("https://medtehno.ru/p/1") == "7725810446"
    assert seller_inn_for_url("https://ice-age.ru/p/1") == "772823702838"


def test_seller_inn_for_url_subdomain_matches():
    assert seller_inn_for_url("https://m.sima-land.ru/item/123") == "6679104850"
    assert seller_inn_for_url("https://shop.vkusvill.ru/p/1") == "7734443270"


def test_seller_inn_for_url_unknown_domain_is_none():
    assert seller_inn_for_url("https://vseinstrumenti.ru/product/123") is None
    assert seller_inn_for_url(None) is None
    assert seller_inn_for_url("не ссылка") is None


def test_seller_inn_for_source_store_text():
    assert seller_inn_for_source_store("Сима-ленд (sima-land.ru)") == "6679104850"
    assert seller_inn_for_source_store("Бауцентр (baucenter.ru)") == "7702596813"
    assert seller_inn_for_source_store("Магазин 01 (magazin01.ru)") == "7718595621"
    assert seller_inn_for_source_store("АльпИндустрия / Ледниковый период (ice-age.ru)") == "772823702838"
    assert seller_inn_for_source_store("Неизвестный (other-shop.ru)") is None
    assert seller_inn_for_source_store(None) is None
    assert seller_inn_for_source_store("без скобок") is None


def test_store_for_inn_reverse_lookup():
    info = store_for_inn("6679104850")
    assert info is not None
    assert info["name"] == "ООО ТД «Сима-ленд»"
    assert info["ogrn"] == "1176658004929"
    assert store_for_inn("0000000000") is None
    assert store_for_inn(None) is None


def test_store_for_domain_exact_only_no_fuzzy():
    # lesson feedback_dedup_exact_only — поддомен распознаётся, но похожий
    # домен другого сайта НЕ должен совпасть.
    assert store_for_domain("sima-land.ru") is not None
    assert store_for_domain("notsima-land.ru") is None
    assert store_for_domain("sima-land.ru.evil.com") is None
