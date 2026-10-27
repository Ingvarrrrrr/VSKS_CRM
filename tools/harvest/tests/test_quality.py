"""Тесты гейта качества (tools/harvest/core/quality.py) — синтетические
каталоги, без живых запросов, без БД."""
from tools.harvest.core import quality
from tools.harvest.core.gala_writer import build_item, build_manifest


def _catalog(items):
    doc = build_manifest("test", "test.json")
    doc["items"] = items
    return doc


def test_reject_on_majority_bogus_manufacturer():
    items = []
    for i in range(10):
        bogus = i < 6  # 60% bogus
        items.append(build_item(
            name=f"Товар {i}",
            manufacturer="Производитель" if bogus else "Makita",
            price=100.0,
            links=[{"url": f"https://example.com/{i}"}],
        ))
    report = quality.quality_report(_catalog(items))
    assert report["verdict"] == "reject"
    assert any("mfr_bogus_rate" in r for r in report["reasons"])


def test_ok_on_clean_catalog():
    items = [
        build_item(
            name="Дрель Makita DP4010",
            manufacturer="Makita",
            manufacturer_article="DP4010",
            price=11699.0,
            characteristics=[{"name": "Мощность", "value": "720 Вт"}],
            links=[{"url": "https://www.kuvalda.ru/catalog/9045/product-23241/", "price": 11699.0}],
            seller_inn="6319060894",
        )
        for _ in range(5)
    ]
    report = quality.quality_report(_catalog(items))
    assert report["verdict"] == "ok"
    assert report["schema_errors"] == []


def test_reject_on_placeholder_specs():
    items = []
    for i in range(10):
        chars = [{"name": f"Параметр {j}", "value": "x"} for j in range(3)] if i < 3 else [
            {"name": "Мощность", "value": "100 Вт"}
        ]
        items.append(build_item(
            name=f"Товар {i}",
            manufacturer="Makita",
            price=100.0,
            characteristics=chars,
            links=[{"url": f"https://example.com/{i}"}],
        ))
    report = quality.quality_report(_catalog(items))
    assert report["verdict"] == "reject"


def test_write_catalog_rejected_goes_to_rejected_json(tmp_path):
    items = [
        build_item(name=f"Товар {i}", manufacturer="Производитель", price=None, links=[])
        for i in range(5)
    ]
    out_path = str(tmp_path / "catalog.json")
    report = quality.write_catalog(_catalog(items), out_path)

    assert report["verdict"] == "reject"
    assert not (tmp_path / "catalog.json").exists()
    assert (tmp_path / "catalog.rejected.json").exists()


def test_write_catalog_ok_goes_to_main_file(tmp_path):
    items = [
        build_item(
            name="Дрель Makita DP4010",
            manufacturer="Makita",
            price=11699.0,
            links=[{"url": "https://example.com/1", "price": 11699.0}],
        )
    ]
    out_path = str(tmp_path / "catalog.json")
    report = quality.write_catalog(_catalog(items), out_path)

    assert report["verdict"] == "ok"
    assert (tmp_path / "catalog.json").exists()
    assert not (tmp_path / "catalog.rejected.json").exists()
