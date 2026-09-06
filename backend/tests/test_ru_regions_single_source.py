"""Единый источник справочника субъектов РФ (ПРАВИЛО №6).

backend/app/data/ru_regions.json — единственное место, где хранятся 89 субъектов
РФ, их коды ОКАТО и федеральные округа. backend/app/services/ru_regions.py и обе
фронтовые константы (frontend/src/constants/russian_regions.ts,
frontend/src/constants/ru_region_okato.ts) читают этот файл, а не хранят копию.

Эти тесты проверяют сам JSON и то, что модуль ru_regions.py действительно
построен из него (а не из собственной захардкоженной копии).
"""
import json
from pathlib import Path

from app.services import ru_regions

DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "ru_regions.json"


def _load_json() -> list[dict[str, str]]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_json_file_exists():
    assert DATA_PATH.is_file(), f"Единый источник не найден: {DATA_PATH}"


def test_json_has_exactly_89_regions():
    data = _load_json()
    assert len(data) == 89, f"Ожидалось 89 субъектов РФ, получено {len(data)}"


def test_json_names_are_unique():
    data = _load_json()
    names = [item["name"] for item in data]
    assert len(names) == len(set(names)), "Дублирующиеся названия субъектов в JSON"


def test_json_okato_codes_are_unique():
    data = _load_json()
    okatos = [item["okato"] for item in data]
    assert len(okatos) == len(set(okatos)), "Дублирующиеся коды ОКАТО в JSON"


def test_json_entries_have_required_fields():
    data = _load_json()
    for item in data:
        assert set(item.keys()) >= {"name", "okato", "district"}
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["okato"], str) and item["okato"]
        assert isinstance(item["district"], str) and item["district"]


def test_ru_regions_module_matches_json():
    """RU_REGIONS в ru_regions.py обязан быть построен из JSON, 1:1, без расхождений."""
    data = _load_json()
    expected = {item["name"]: (item["okato"], item["district"]) for item in data}
    assert ru_regions.RU_REGIONS == expected


def test_ru_regions_has_89_entries():
    assert len(ru_regions.RU_REGIONS) == 89


def test_okato11_pads_to_eleven_digits():
    assert ru_regions.okato11("45") == "45000000000"
    assert len(ru_regions.okato11("45")) == 11
    assert len(ru_regions.okato11("71100")) == 11


def test_get_region_info_exact_match():
    info = ru_regions.get_region_info("Москва")
    assert info == {"okato": "45000000000", "district": "Центральный федеральный округ"}


def test_get_region_info_handles_aliases_and_dashes():
    # ХМАО через алиас
    info = ru_regions.get_region_info("ХМАО")
    assert info is not None
    assert info["okato"] == "71100000000"
    # Официальное имя с обычным дефисом вместо длинного тире тоже должно резолвиться
    info2 = ru_regions.get_region_info("Ханты-Мансийский автономный округ - Югра")
    assert info2 == info


def test_get_region_info_unknown_returns_none():
    assert ru_regions.get_region_info("Не определён") is None
    assert ru_regions.get_region_info(None) is None
    assert ru_regions.get_region_info("") is None
