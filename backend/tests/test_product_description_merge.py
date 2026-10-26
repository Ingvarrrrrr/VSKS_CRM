"""Тесты backend/app/services/product_description_merge.py (владелец,
26.10.2026, Задача 1, ПРАВИЛО №6 — один источник истины для критерия
"короче/не короче" и для сборки "старое+новое").

Данные для теста merge — РЕАЛЬНЫЙ товар «Сетка всасывающая СВ-100» из
C:\\Users\\1\\Downloads\\Товары и ТЗ\\k_spasatel_rescue_nomenclature.json
(вторая запись, с непустыми specifications) и
C:\\Users\\1\\Downloads\\Товары и ТЗ\\fire_equipment_nomenclature.json
(запись Magazin01, где description — целиком реклама и после
strip_ad_sentences даёт None, а характеристики короче и менее подробные,
чем у k_spasatel) — взяты как есть."""
from app.services.product_description_merge import (
    is_new_description_shorter, merge_missing_lines,
)

# Старое описание в БД — РЕАЛЬНЫЕ характеристики СВ-100 из k_spasatel
# (вторая запись fire_equipment: "Диаметр условного прохода" и т.д.),
# собранные строками, как их бы дал build_tech_description.
_SV100_OLD_DB_DESCRIPTION = (
    "Фильтрующая сетка всасывающая СВ 100 с клапаном применяется при "
    "водозаборе из источника открытого типа (пруда, озера, реки, "
    "водохранилища).\n\n"
    "Диаметр условного прохода: 100 мм.\n"
    "Рекомендуемая пропускная способность: не больше 20 л/с.\n"
    "Коэфф.гидравлич.сопротивления: не превышает 1,5.\n"
    "Габариты: 185х215 мм.\n"
    "Масса изделия: 3 кг.\n"
    "Гарантия производителя: 24 месяца.\n"
    "Средний срок эксплуатации: от 8 лет."
)

# Новое из файла — РЕАЛЬНЫЕ характеристики СВ-100 из
# fire_equipment_nomenclature.json (Magazin01: только "Диаметр, мм" и
# "Вид", description там целиком реклама и после strip_ad_sentences даёт
# None — build_tech_description собрал бы только эти две строки).
_SV100_NEW_FILE_DESCRIPTION = "Диаметр, мм: 100\nВид: Сетка всасывающая"


def test_sv100_new_file_description_is_shorter_than_old():
    """Факт на реальных данных: файловое описание СВ-100 (2 строки
    характеристик, без базового текста — реклама вырезана) заметно короче
    старого описания в БД (абзац текста + 7 строк характеристик)."""
    assert is_new_description_shorter(
        _SV100_OLD_DB_DESCRIPTION, _SV100_NEW_FILE_DESCRIPTION,
    ) is True


def test_sv100_merge_keeps_old_entirely_and_appends_missing_lines():
    """merge_missing_lines на реальных данных СВ-100: старое описание
    сохраняется ЦЕЛИКОМ (каждая строка old присутствует в результате,
    порядок не нарушен), а обе строки файлового описания (ни одна из них
    не совпадает ПОСИМВОЛЬНО/по norm_key с какой-либо строкой old — у
    "Диаметр условного прохода: 100 мм." и "Диаметр, мм: 100" разный
    текст, сравнение точное, не по смыслу) дописываются в конец."""
    merged = merge_missing_lines(_SV100_OLD_DB_DESCRIPTION, _SV100_NEW_FILE_DESCRIPTION)

    old_lines = _SV100_OLD_DB_DESCRIPTION.split("\n")
    for line in old_lines:
        assert line in merged, f"строка старого описания потеряна: {line!r}"

    assert merged.startswith(_SV100_OLD_DB_DESCRIPTION)
    assert "Диаметр, мм: 100" in merged
    assert "Вид: Сетка всасывающая" in merged
    # Результат объединения по построению не короче старого.
    assert is_new_description_shorter(_SV100_OLD_DB_DESCRIPTION, merged) is False


def test_merge_missing_lines_old_empty_returns_new_as_is():
    assert merge_missing_lines("", "Новое описание") == "Новое описание"
    assert merge_missing_lines("   ", "Новое описание") == "Новое описание"


def test_merge_missing_lines_new_fully_contained_in_old_returns_old_unchanged():
    old = "Строка один.\nСтрока два.\nСтрока три."
    new = "Строка два.\nСтрока три."
    assert merge_missing_lines(old, new) == old


def test_merge_missing_lines_deduplicates_within_new_itself():
    old = "Старое."
    new = "Новая строка.\nновая строка.\nЕщё одна."
    merged = merge_missing_lines(old, new)
    assert merged.count("Новая строка.") + merged.count("новая строка.") == 1
    assert "Ещё одна." in merged


def test_is_new_description_shorter_threshold_and_empty_old():
    # Старое пустое — не может быть "короче", замена ничего не теряет.
    assert is_new_description_shorter("", "что угодно") is False
    # Новое ровно 80% от старого по непробельным символам — не "заметно
    # короче" (строго <, не <=).
    old = "а" * 100
    new = "а" * 80
    assert is_new_description_shorter(old, new) is False
    new_shorter = "а" * 79
    assert is_new_description_shorter(old, new_shorter) is True
