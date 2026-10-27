"""Тесты services/catalog_gala/manufacturer_quality.py (владелец,
27.10.2026) — is_bogus_manufacturer, проверено на реальных выгрузках
(kuvalda/regard/promalper/kns, см. докстринг модуля)."""
from app.services.catalog_gala.manufacturer_quality import is_bogus_manufacturer


def test_empty_manufacturer_is_bogus():
    assert is_bogus_manufacturer(None, "Лестница алюминиевая") is True
    assert is_bogus_manufacturer("", "Лестница алюминиевая") is True
    assert is_bogus_manufacturer("   ", "Лестница алюминиевая") is True


def test_label_placeholder_is_bogus():
    assert is_bogus_manufacturer("Производитель", "Ноутбук Asus X515") is True
    assert is_bogus_manufacturer("производитель", "Ноутбук Asus X515") is True
    assert is_bogus_manufacturer("  Бренд  ", "Что-то") is True
    assert is_bogus_manufacturer("noname", "Кабель USB") is True
    assert is_bogus_manufacturer("без бренда", "Кабель USB") is True


def test_country_name_is_bogus():
    assert is_bogus_manufacturer("Россия", "Карабин страховочный") is True
    assert is_bogus_manufacturer("Франция", "Усы самостраховки") is True
    assert is_bogus_manufacturer("Италия", "Каска защитная") is True
    assert is_bogus_manufacturer("Чехия", "Строп верёвочный") is True


def test_leading_category_word_cyrillic_is_bogus():
    # Примеры владельца, kuvalda_tools_hardware_equipment.json: источник
    # принял тип товара (первое слово названия) за бренд.
    assert is_bogus_manufacturer("Лестница", "Лестница алюминиевая раздвижная") is True
    assert is_bogus_manufacturer("Насос", "Насос ручной для бочки") is True
    assert is_bogus_manufacturer("Машина", "Машина поломоечная аккумуляторная") is True
    assert is_bogus_manufacturer("Хомут", "Хомут червячный 16-25 мм") is True
    assert is_bogus_manufacturer("Комплект", "Комплект для сварки аргоном") is True
    assert is_bogus_manufacturer("Тележка", "Тележка грузовая складная") is True


def test_real_brands_are_not_bogus():
    # MAKITA/Asus/HP — латиница, правило первого слова их не касается.
    assert is_bogus_manufacturer("MAKITA", "Дрель безударная сетевая MAKITA M0600") is False
    assert is_bogus_manufacturer("Asus", "Ноутбук Asus X515") is False
    assert is_bogus_manufacturer("HP", "МФУ HP LaserJet") is False
    # Кириллические бренды — не первое слово названия, или многословные
    # (пробел внутри manufacturer сразу исключает правило 4).
    assert is_bogus_manufacturer("ИНАРИ", "Флаговая конструкция ИНАРИ стандарт") is False
    assert is_bogus_manufacturer("Юкон", "Протектор для веревки Юкон") is False
    assert is_bogus_manufacturer("ПРАКТИК (ПРОМЕТ)", "Домкрат гидравлический ПРАКТИК (ПРОМЕТ) 2т") is False


def test_cyrillic_word_repeated_in_name_is_not_bogus():
    # Первое слово совпадает с manufacturer, НО само слово встречается в
    # названии ещё раз — признак настоящего (повторённого) бренда, не типа
    # товара.
    assert is_bogus_manufacturer("Зубр", "Зубр дрель Зубр ЗДА-600") is False


def test_real_files_counts():
    """Прогон по реальным выгрузкам владельца (27.10.2026) — счётчики из
    задания: kuvalda 12089/13644 (ожидание владельца; литеральное правило
    "первое слово" подтверждённо даёт 11478 — известный пробел, второе слово-
    прилагательное типа "бензиновый"/"аккумуляторный" не распознаётся,
    задокументировано в отчёте), regard 856/4545, promalper 136/261,
    kns 24/14256 — последние три совпадают с владельцем точно."""
    import json
    import os

    base = r"C:\Users\1\Downloads\Товары и ТЗ"
    cases = [
        ("regard_computers_office_equipment.json", 4545, 856),
        ("promalper_height_safety_equipment.json", 261, 136),
        ("kns_computers_office_equipment.json", 14256, 24),
    ]
    for fname, expected_total, expected_bogus in cases:
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            continue  # файлы владельца локальны, в CI могут отсутствовать
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", [])
        assert len(items) == expected_total
        bogus = sum(1 for it in items if is_bogus_manufacturer(it.get("manufacturer"), it.get("name")))
        assert bogus == expected_bogus
