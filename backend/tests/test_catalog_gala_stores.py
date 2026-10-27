"""Тесты services/catalog_gala/stores.py — единственный справочник «домен
магазина → ИНН» (владелец, 26.10.2026). Проверяет домены, поддомены, www.,
и разбор текста source_store ("Магазин (домен.ru)")."""
from app.services.catalog_gala.stores import (
    domain_from_url, inn_checksum_valid, resolve_seller_inn,
    seller_inn_for_source_store, seller_inn_for_url,
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


def test_new_stores_27_10_requisites():
    """Реквизиты с сайта магазина, сверены 27.10.2026 (владелец — seller_inn
    в новых выгрузках был неверным у 5 из 6 магазинов)."""
    assert seller_inn_for_url("https://kns.ru/p/1") == "9723033526"
    assert seller_inn_for_url("https://www.regard.ru/p/1") == "7730234438"
    assert seller_inn_for_url("https://kuvalda.ru/p/1") == "6319060894"
    assert seller_inn_for_url("https://safe.ru/p/1") == "7751009218"
    assert seller_inn_for_url("https://promalper.com/p/1") == "7806293316"
    # inari.pro — реквизиты не подтверждены, сознательно не добавлен.
    assert seller_inn_for_url("https://inari.pro/p/1") is None


def test_inn_checksum_valid_10_digit():
    assert inn_checksum_valid("9723033526") is True  # kns.ru
    assert inn_checksum_valid("7730234438") is True  # regard.ru
    assert inn_checksum_valid("6319060894") is True  # kuvalda.ru
    assert inn_checksum_valid("7751009218") is True  # safe.ru
    assert inn_checksum_valid("7806293316") is True  # promalper.com
    assert inn_checksum_valid("1832034960") is False  # inari.pro — невалиден


def test_inn_checksum_valid_12_digit_and_garbage():
    assert inn_checksum_valid("772823702838") is True  # ice-age.ru (ИП)
    assert inn_checksum_valid("772823702839") is False  # сломанная последняя цифра
    assert inn_checksum_valid("12345") is False  # не 10/12 цифр
    assert inn_checksum_valid("abcdefghij") is False  # не цифры
    assert inn_checksum_valid(None) is False
    assert inn_checksum_valid("") is False


def test_resolve_seller_inn_known_domain_wins_over_file_value():
    # Выдуманный/неверный ИНН в файле + ссылка на известный магазин — ИНН
    # магазина побеждает, файловый игнорируется, причина — "заменён".
    inn, reason = resolve_seller_inn("7722395663", ["https://kns.ru/p/1"])
    assert inn == "9723033526"
    assert reason == "ИНН из файла заменён по сайту магазина"


def test_resolve_seller_inn_known_domain_matches_file_value_no_reason():
    inn, reason = resolve_seller_inn("9723033526", ["https://kns.ru/p/1"])
    assert inn == "9723033526"
    assert reason is None


def test_resolve_seller_inn_unknown_domain_valid_file_inn_accepted():
    inn, reason = resolve_seller_inn("7730234438", ["https://unknown-shop.example/p/1"])
    assert inn == "7730234438"
    assert reason is None


def test_resolve_seller_inn_unknown_domain_invalid_file_inn_rejected():
    # inari.pro — домен не в справочнике (реквизиты не подтверждены), ИНН
    # файла не проходит контрольную цифру → seller_inn=None.
    inn, reason = resolve_seller_inn("1832034960", ["https://inari.pro/p/1"])
    assert inn is None
    assert reason == "ИНН невалиден, магазин не определён"


def test_resolve_seller_inn_falls_back_to_second_url_candidate():
    inn, reason = resolve_seller_inn(None, [None, "https://kns.ru/p/1"])
    assert inn == "9723033526"
    assert reason is None


def test_resolve_seller_inn_empty_everything():
    assert resolve_seller_inn(None, [None, None]) == (None, None)
