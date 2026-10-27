"""Тесты core/runner.py: --previous (инкремент, товар с полными данными не
открывается повторно) и --prices-only (товарные страницы не открываются
вовсе) — на игрушечном StoreSpec, без живых запросов (fetch подменяется
счётчиком вызовов)."""
from tools.harvest.core import http as http_module
from tools.harvest.core.runner import StoreSpec, harvest

CATEGORY_HTML = "ok"


def _make_spec(fetch_calls: list, concurrency: int = 1) -> StoreSpec:
    def page_url(category_url, page):
        return category_url if page == 1 else f"{category_url}?page={page}"

    def parse_category_page(html):
        if html != CATEGORY_HTML:
            return []
        return [
            {"name": "Товар A", "url": "https://x.ru/a/", "price": 100.0},
            {"name": "Товар B", "url": "https://x.ru/b/", "price": 200.0},
        ]

    def needs_product_visit(candidate):
        return True

    def parse_product_page(html, url):
        fetch_calls.append(("product", url))
        return {"brand": "ACME", "characteristics": [{"name": "Вес", "value": "1кг", "unit": None, "in_description": False}]}

    def build_item(candidate, enrichment, known_brands):
        return {
            "name": candidate["name"],
            "category": None,
            "category_path": [],
            "product_type": None,
            "unit": "шт",
            "price": candidate.get("price"),
            "price_date": None,
            "currency": "RUB" if candidate.get("price") is not None else None,
            "manufacturer": enrichment.get("brand"),
            "manufacturer_article": None,
            "store_article": None,
            "description": None,
            "characteristics": enrichment.get("characteristics") or [],
            "photos": [],
            "links": [{"url": candidate["url"], "price": candidate.get("price")}],
            "source_url": candidate["url"],
            "source_id": None,
            "country_origin": None,
            "barcodes": [],
            "seller_inn": None,
        }

    return StoreSpec(
        name="toy",
        categories=[("https://x.ru/cat/", "Категория", ["Товары"])],
        page_url=page_url,
        parse_category_page=parse_category_page,
        needs_product_visit=needs_product_visit,
        parse_product_page=parse_product_page,
        build_item=build_item,
        max_pages_per_category=1,
        concurrency=concurrency,
        default_pause_per_domain=0.0,
        category_has_price=True,
    )


def _patch_fetch(monkeypatch, fetch_calls):
    # Подменяем HttpClient.fetch целиком: раздел отдаёт CATEGORY_HTML,
    # товарные URL идут в parse_product_page через обычный путь runner'а —
    # здесь просто считаем факт вызова.
    def patched_fetch(self, url):
        fetch_calls.append(("fetch", url))
        if url == "https://x.ru/cat/":
            return CATEGORY_HTML
        return "<html>product</html>"

    monkeypatch.setattr(http_module.HttpClient, "fetch", patched_fetch)


def test_previous_complete_item_skips_product_visit(tmp_path, monkeypatch):
    fetch_calls: list = []
    _patch_fetch(monkeypatch, fetch_calls)
    spec = _make_spec(fetch_calls)

    previous_items = [
        {
            "name": "Товар A (старый)",
            "manufacturer": "ACME",
            "characteristics": [{"name": "Вес", "value": "1кг", "unit": None, "in_description": False}],
            "description": None,
            "source_url": "https://x.ru/a/",
            "links": [{"url": "https://x.ru/a/", "price": 90.0}],
            "price": 90.0,
        }
    ]

    out = tmp_path / "out.json"
    manifest = harvest(spec, str(out), previous_items=previous_items)

    product_fetches = [c for c in fetch_calls if c[1] == "https://x.ru/a/"]
    assert product_fetches == []  # товар A не открывался повторно

    item_a = next(i for i in manifest["items"] if i["source_url"] == "https://x.ru/a/")
    assert item_a["price"] == 100.0  # цена обновлена из раздела
    assert item_a["manufacturer"] == "ACME"  # остальное — из --previous

    # Товар B не из --previous — для него визит должен был случиться.
    assert any(c[1] == "https://x.ru/b/" for c in fetch_calls)


def test_prices_only_never_fetches_product_pages(tmp_path, monkeypatch):
    fetch_calls: list = []
    _patch_fetch(monkeypatch, fetch_calls)
    spec = _make_spec(fetch_calls)

    out = tmp_path / "out.json"
    manifest = harvest(spec, str(out), prices_only=True)

    product_urls = {"https://x.ru/a/", "https://x.ru/b/"}
    fetched_product_urls = {c[1] for c in fetch_calls if c[1] in product_urls}
    assert fetched_product_urls == set()  # ни один товар не открыт

    prices = {i["source_url"]: i["price"] for i in manifest["items"]}
    assert prices["https://x.ru/a/"] == 100.0
    assert prices["https://x.ru/b/"] == 200.0


def test_prices_only_warns_when_category_has_no_price(tmp_path, monkeypatch, capsys):
    fetch_calls: list = []
    _patch_fetch(monkeypatch, fetch_calls)
    spec = _make_spec(fetch_calls)
    spec.category_has_price = False

    out = tmp_path / "out.json"
    harvest(spec, str(out), prices_only=True)

    captured = capsys.readouterr()
    assert "цена" in captured.out.lower()
