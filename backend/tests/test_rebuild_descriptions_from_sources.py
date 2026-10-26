"""Юнит-тест scripts/rebuild_descriptions_from_sources.py (владелец,
26.10.2026) — без реальной БД/докера: маленький фикстурный JSON (формат
store_nomenclature, тот же, что у sima_land_catalog_all.json) и маленький
CSV вместо выгрузки прода (--db-source csv). Проверяет _pick_converter и
полный проход _process_file: описание заменяется, даже если новое короче
старого (финальное решение владельца), а товар без совпадения в файле не
трогается.

Задача 4 (26.10.2026, дополнена): маленькая фикстура в формате
k_spasatel_rescue_nomenclature.json (ключи "Страна производства"/"Страна
производитель"/"Страна-производитель" в specifications) — тест с реальной
тестовой БД (db_session/test_user из conftest.py) и --apply: country_origin
заменяется из 'РФ' на значение из файла; товар, у которого в файле страны
нет, не трогается (ПРАВИЛО владельца — файл не даёт значение, поле не
трогаем)."""
import csv
import json

import pytest

from app.models.product import Product
from scripts.rebuild_descriptions_from_sources import (
    _load_csv_match_index, _pick_converter, _process_file,
)
from app.services.products_import_match import ProductMatchIndex


def test_pick_converter_detects_store_nomenclature_by_signature():
    raw = [{"name": "A", "price_rub": 10, "source_store": "Магазин"}]
    assert _pick_converter("sima_land_catalog_all.json", raw) == "store_nomenclature"


def test_pick_converter_falls_back_to_basename_prefix():
    raw = [{"name": "A", "price": 10, "url": "x"}]
    assert _pick_converter("baucenter_construction_all.json", raw) == "baucenter"


def test_pick_converter_unknown_returns_none():
    raw = [{"name": "A"}]
    assert _pick_converter("mystery_source.json", raw) is None


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "description", "characteristics", "import_note", "article", "manufacturer"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


@pytest.mark.asyncio
async def test_process_file_replaces_shorter_description_and_skips_unmatched(tmp_path):
    raw = [
        {
            "name": "Ластик фигурный «Панда»",
            "category": "Канцтовары",
            "unit": "шт",
            "price_rub": 15,
            "source_store": "Сима-ленд (sima-land.ru)",
            "link_1": "https://example.com/1",
            "photo_url": None,
            "description": "Описание Ластик фигурный «Панда» Мягкий ластик для канцелярии.",
            "specifications": {"Страна-производитель": "Китай"},
        },
        {
            "name": "Товар без совпадения в БД",
            "category": "Прочее",
            "unit": "шт",
            "price_rub": 5,
            "source_store": "Сима-ленд (sima-land.ru)",
            "link_1": None,
            "photo_url": None,
            "description": "Что угодно",
            "specifications": {},
        },
    ]
    json_path = tmp_path / "sima_land_catalog_all.json"
    json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    csv_path = tmp_path / "prod_export.csv"
    _write_csv(csv_path, [
        {
            "id": "152085", "name": "Ластик фигурный «Панда»",
            "description": "Старое длинное описание товара с кучей подробностей о материале и размере",
            "characteristics": "[]", "import_note": "Импорт каталога из файла «sima_land_catalog_all.json»",
            "article": "", "manufacturer": "",
        },
    ])

    match_index = _load_csv_match_index(str(csv_path))
    report = await _process_file(str(json_path), match_index, apply=False)

    assert report.error is None
    assert report.total_items == 2
    assert report.matched == 1
    assert report.unmatched == 1
    assert report.changed == 1
    assert report.lastik_sample is not None
    assert report.lastik_sample["id"] == 152085
    assert "Мягкий ластик" in report.lastik_sample["new"]


@pytest.mark.asyncio
async def test_process_file_ad_only_item_counted_as_no_data_not_shorter(tmp_path):
    """Г-600/КПА (fire_equipment_nomenclature.json): description — только
    реклама магазина (strip_ad_sentences даёт None), specifications — только
    заглушка "#PROP_TITLE#"/"#PROP_VALUE#" (тоже даёт пустой список
    характеристик) → build_tech_description(characteristics=[], base_text=None)
    возвращает None → защита apply_products_import/rebuild-скрипта (новый
    desc пуст — старое описание не трогаем) должна сработать: товар попадает
    в report.no_data_in_file, а НЕ в report.changed/shorter_count (владелец,
    26.10.2026, Задача 1 — проверка существующей защиты явным тестом)."""
    raw = [{
        "name": "Гидроэлеватор пожарный Г-600",
        "category": "Пожарное оборудование",
        "unit": "шт",
        "price_rub": 1000,
        "source_store": "Magazin01",
        "link_1": None,
        "photo_url": None,
        "description": (
            "Гидроэлеватор пожарный Г-600 по низким ценам в Москве в компании "
            "Magazin01. На нашем сайте большой выбор пожарного оборудования, у "
            "нас вы можете купить гидроэлеватор Г-600 с доставкой по России."
        ),
        "specifications": {"#PROP_TITLE#": "#PROP_VALUE#"},
    }]
    json_path = tmp_path / "fire_equipment_nomenclature.json"
    json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    csv_path = tmp_path / "prod_export.csv"
    _write_csv(csv_path, [
        {
            "id": "999001", "name": "Гидроэлеватор пожарный Г-600",
            "description": "Старое короткое описание.",
            "characteristics": "[]",
            "import_note": "Импорт каталога из файла «fire_equipment_nomenclature.json»",
            "article": "", "manufacturer": "",
        },
    ])

    match_index = _load_csv_match_index(str(csv_path))
    report = await _process_file(str(json_path), match_index, apply=False)

    assert report.error is None
    assert report.matched == 1
    assert report.no_data_in_file == 1
    assert report.changed == 0
    assert report.shorter_count == 0


@pytest.mark.asyncio
async def test_process_file_change_samples_capped_at_three(tmp_path):
    """Задача 3 (26.10): change_samples хранит не более 3 примеров
    «было/станет» на файл, даже если изменилось больше товаров."""
    raw = [
        {
            "name": f"Товар {i}", "category": "C", "unit": "шт", "price_rub": 10,
            "source_store": "S", "link_1": "", "photo_url": None,
            "description": f"Описание Товар {i} Технический текст {i}.",
            "specifications": {},
        }
        for i in range(5)
    ]
    json_path = tmp_path / "sima_land_catalog_all.json"
    json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    csv_path = tmp_path / "prod_export.csv"
    _write_csv(csv_path, [
        {"id": str(i), "name": f"Товар {i}", "description": "Старое", "characteristics": "[]",
         "import_note": "", "article": "", "manufacturer": ""}
        for i in range(5)
    ])

    match_index = _load_csv_match_index(str(csv_path))
    report = await _process_file(str(json_path), match_index, apply=False)

    assert report.changed == 5
    assert len(report.change_samples) == 3


@pytest.mark.asyncio
async def test_process_file_apply_fills_country_origin_from_file_leaves_other_untouched(
    db_session, test_user,
):
    """Задача 4 (26.10.2026): фикстура в формате
    k_spasatel_rescue_nomenclature.json — два товара в БД с дефолтом
    country_origin='РФ'. У первого в файле специфика даёт
    "Страна производства": country_origin должен ЗАМЕНИТЬСЯ (безусловно,
    даже если старое значение было непустым). У второго товара в файле нет
    страны вообще — country_origin НЕ трогается (остаётся 'РФ')."""
    p_with_country = Product(
        name="Аптечка автомобильная", category="Медицина",
        country_origin="РФ",
    )
    p_without_country = Product(
        name="Жилет сигнальный", category="Безопасность",
        country_origin="РФ",
    )
    db_session.add_all([p_with_country, p_without_country])
    await db_session.commit()
    await db_session.refresh(p_with_country)
    await db_session.refresh(p_without_country)

    raw = [
        {
            "name": "Аптечка автомобильная", "category": "Медицина", "unit": "шт",
            "price_rub": 500, "source_store": "К-Спасатель",
            "link_1": "", "photo_url": None, "description": "",
            "specifications": {"Страна производства": "Франция"},
        },
        {
            "name": "Жилет сигнальный", "category": "Безопасность", "unit": "шт",
            "price_rub": 200, "source_store": "К-Спасатель",
            "link_1": "", "photo_url": None, "description": "",
            "specifications": {},
        },
    ]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        json_path = Path(tmp) / "k_spasatel_rescue_nomenclature.json"
        json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        match_index = ProductMatchIndex([p_with_country, p_without_country])
        report = await _process_file(
            str(json_path), match_index, apply=True, db=db_session, current_user=test_user,
        )
        await db_session.commit()

    assert report.error is None
    assert report.matched == 2
    assert report.country_will_change == 1
    assert report.country_to_non_rf == 1

    await db_session.refresh(p_with_country)
    await db_session.refresh(p_without_country)
    assert p_with_country.country_origin == "Франция"
    assert p_without_country.country_origin == "РФ"
