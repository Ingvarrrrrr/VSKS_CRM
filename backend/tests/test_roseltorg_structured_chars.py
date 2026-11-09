# -*- coding: utf-8 -*-
"""Тесты структурированных характеристик товара в бланках ТКП (Excel/PDF) и парсерах."""

import io
import json
import pytest
from decimal import Decimal
import openpyxl
import fitz

from app.services.roseltorg.analog_matcher import (
    extract_item_structured_chars,
    is_range_or_vague_value,
    extract_default_exact_value,
    evaluate_characteristic_compliance,
    evaluate_position_characteristics,
)
from app.services.documents.tkp_form_xlsx import (
    build_standardized_tkp_xlsx,
    load_standardized_tkp_rows,
)
from app.services.documents.tkp_form_pdf import build_standardized_tkp_pdf
from app.services.roseltorg.xlsx_protocol_parser import parse_standardized_tkp_workbook
from app.services.roseltorg.pdf_tkp_parser import parse_standardized_tkp_pdf


def test_extract_item_structured_chars_from_tz_text():
    """Тест извлечения структурированных характеристик из текста ТЗ."""
    tz_text = """
    Объем топливного бака: не менее 15 л
    Мощность номинальная: от 2.5 до 4.0 кВт
    Уровень шума: не более 72 дБ
    Цвет корпуса: ярко-оранжевый
    """
    chars = extract_item_structured_chars(tz_text=tz_text)
    assert len(chars) == 4

    # 1. Объем топливного бака
    c0 = chars[0]
    assert "объем" in c0["name"].lower()
    assert "15" in c0["req_value"]
    assert c0["unit"] == "л"

    # 2. Мощность
    c1 = chars[1]
    assert "мощность" in c1["name"].lower()
    assert "от 2.5 до 4.0" in c1["req_value"]
    assert c1["unit"] == "кВт"

    # 3. Шум
    c2 = chars[2]
    assert "шум" in c2["name"].lower()
    assert "72" in c2["req_value"]
    assert c2["unit"] == "дБ"

    # 4. Цвет
    c3 = chars[3]
    assert "цвет" in c3["name"].lower()
    assert c3["req_value"] == "ярко-оранжевый"


def test_is_range_or_vague_value():
    """Тест детектора разброса и неопределённых формулировок."""
    assert is_range_or_vague_value("не менее 15 л") is True
    assert is_range_or_vague_value("от 2.5 до 3.5") is True
    assert is_range_or_vague_value("18-24") is True
    assert is_range_or_vague_value("не более 72") is True
    assert is_range_or_vague_value(">= 10") is True
    assert is_range_or_vague_value("или эквивалент") is True

    # Точные значения
    assert is_range_or_vague_value("16") is False
    assert is_range_or_vague_value("16 л") is False
    assert is_range_or_vague_value("3.0") is False
    assert is_range_or_vague_value("ярко-оранжевый") is False
    assert is_range_or_vague_value("FUBAG TI 6000") is False
    assert is_range_or_vague_value("КВТ ГР-24") is False


def test_evaluate_characteristic_compliance():
    """Тест оценки соответствия значений характеристик (диапазоны, границы, равенство)."""
    # 1. Попытка участника оставить разброс или неопределённость -> отказ!
    res_vague1 = evaluate_characteristic_compliance("Бак", "не менее 15 л", "не менее 15 л", "л")
    assert res_vague1["compliant"] is False
    assert "диапазон" in res_vague1["note"] or "неопределённое" in res_vague1["note"]

    res_vague2 = evaluate_characteristic_compliance("Мощность", "от 2.0 до 3.5 кВт", "от 2.0 до 3.5", "кВт")
    assert res_vague2["compliant"] is False

    # Пустое значение -> отказ!
    res_empty = evaluate_characteristic_compliance("Бак", "не менее 15 л", "", "л")
    assert res_empty["compliant"] is False

    # 2. Конкретное число в рамках требования минимума ("не менее 15 л")
    res1 = evaluate_characteristic_compliance("Бак", "не менее 15 л", "16 л", "л")
    assert res1["compliant"] is True
    assert res1["is_changed"] is True

    res1_exact = evaluate_characteristic_compliance("Бак", "не менее 15 л", "15", "л")
    assert res1_exact["compliant"] is True

    # Недобор ("12 л" при "не менее 15 л")
    res2 = evaluate_characteristic_compliance("Бак", "не менее 15 л", "12", "л")
    assert res2["compliant"] is False
    assert "12" in res2["note"] and "15" in res2["note"]

    # 3. Максимум ("не более 70 дБ")
    res4 = evaluate_characteristic_compliance("Шум", "не более 70", "65", "дБ")
    assert res4["compliant"] is True
    res5 = evaluate_characteristic_compliance("Шум", "не более 70", "75", "дБ")
    assert res5["compliant"] is False

    # 4. Диапазон ("от 2.0 до 3.5 кВт")
    res6 = evaluate_characteristic_compliance("Мощность", "от 2.0 до 3.5", "3.0", "кВт")
    assert res6["compliant"] is True
    res7 = evaluate_characteristic_compliance("Мощность", "от 2.0 до 3.5", "1.5", "кВт")
    assert res7["compliant"] is False

    # 5. Модель Заказчика с уточнением ошибки/опечатки в ТЗ (tz_warning)
    res_tz = evaluate_characteristic_compliance("Вес", "не более 55", "58", "кг", ref_value="55", is_exact_model_offer=True)
    assert res_tz["compliant"] is False
    assert res_tz.get("tz_corrected_by_supplier") is True
    assert res_tz.get("needs_tz_review") is True


def test_extract_default_exact_value():
    """Тест извлечения конкретного значения по умолчанию из формулировок ТЗ."""
    assert extract_default_exact_value("не менее 15 л") == "15"
    assert extract_default_exact_value("от 2.5 до 3.5 кВт") == "2.5"
    assert extract_default_exact_value("не более 72 дБ") == "72"
    assert extract_default_exact_value("не более 650×500×550 мм") == "650×500×550"
    assert extract_default_exact_value("ярко-оранжевый") == "ярко-оранжевый"


def test_tkp_xlsx_with_structured_chars_roundtrip_compliant():
    """Тест генерации и парсинга бланка Excel ТКП: конкретная модель и конкретные параметры."""
    items_rows = [
        {
            "num": 1,
            "purchase_item_id": 101,
            "name": "Генератор бензиновый 3 кВт",
            "unit": "шт",
            "quantity": 2,
            "initial_unit_price": 50000.0,
            "initial_total": 100000.0,
            "vat_rate": "20%",
            "characteristics": [
                {"name": "Объем бака", "req_value": "не менее 15", "unit": "л"},
                {"name": "Мощность", "req_value": "от 2.5 до 3.5", "unit": "кВт"},
            ],
        }
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(
        rows=items_rows,
        purchase_subject="Закупка оборудования",
        customer_name="ВСКС",
    )

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
    ws = wb.active
    assert ws.protection.sheet is True
    assert ws.protection.selectLockedCells is False

    # В незаполненном бланке ячейка характеристики содержит формулу автоподстановки для модели Заказчика
    assert ws["A13"].value == 1
    assert ws["A14"].value == "1.1"
    assert "Объем бака" in str(ws["C14"].value)
    assert ws["D14"].value == "не менее 15"
    assert "SEARCH(" in str(ws["H14"].value)

    # Имитируем заполнение поставщиком:
    # 1. В строке товара указывает конкретную марку/модель, выбирает "Эквивалент (аналог)" и цены
    ws["G13"].value = "Эквивалент (аналог)"
    ws["H13"].value = "Генератор инверторный FUBAG TI 3000"
    ws["I13"].value = 45000.0
    ws["J13"].value = "в т.ч. НДС 20%"
    ws["K13"].value = 90000.0

    # 2. В строках характеристик указывает конкретные точные значения (без разброса!)
    ws["H14"].value = "18"
    ws["H15"].value = "3.0"

    out_buf = io.BytesIO()
    wb.save(out_buf)
    out_buf.seek(0)

    parsed = parse_standardized_tkp_workbook(out_buf.getvalue())
    assert parsed is not None
    app = parsed["application"]
    assert len(app["positions"]) == 1
    p1 = app["positions"][0]
    assert p1["offered_name"] == "Генератор инверторный FUBAG TI 3000"
    assert p1["unit_price"] == 45000.0
    assert p1["total_price"] == 90000.0
    assert p1["is_alternative"] is True
    assert p1["compliance_status"] == "analog_pending"
    assert app["admitted"] is True

    # Проверяем разобранные характеристики позиции
    chars = p1["characteristics"]
    assert len(chars) == 2
    assert chars[0]["offered_value"] == "18"
    assert chars[0]["compliant"] is True
    assert chars[1]["offered_value"] == "3.0"
    assert chars[1]["compliant"] is True


def test_tkp_xlsx_with_structured_chars_rejection():
    """Тест отбраковки заявки в Excel при указании разброса или несоответствующего параметра."""
    items_rows = [
        {
            "num": 1,
            "purchase_item_id": 102,
            "name": "Генератор бензиновый",
            "unit": "шт",
            "quantity": 1,
            "initial_unit_price": 60000.0,
            "initial_total": 60000.0,
            "characteristics": [
                {"name": "Объем бака", "req_value": "не менее 15", "unit": "л"},
            ],
        }
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(
        rows=items_rows,
        purchase_subject="Закупка генератора",
        customer_name="ВСКС",
    )

    # Вариант 1: Поставщик указал "Эквивалент (аналог)", но оставил формулировку разброса "не менее 15"
    wb1 = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws1 = wb1.active
    ws1["G13"].value = "Эквивалент (аналог)"
    ws1["H13"].value = "Модель X"
    ws1["I13"].value = 55000.0
    ws1["K13"].value = 55000.0
    ws1["H14"].value = "не менее 15"
    buf1 = io.BytesIO()
    wb1.save(buf1)
    buf1.seek(0)
    parsed1 = parse_standardized_tkp_workbook(buf1.getvalue())
    assert parsed1["application"]["admitted"] is False
    assert parsed1["application"]["positions"][0]["compliance_status"] == "analog_rejected"
    assert "диапазон" in parsed1["application"]["rejection_reason"] or "неопределённое" in parsed1["application"]["rejection_reason"]

    # Вариант 2: Поставщик указал "Эквивалент (аналог)" с числом 10 при требовании "не менее 15"
    wb2 = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws2 = wb2.active
    ws2["G13"].value = "Эквивалент (аналог)"
    ws2["H13"].value = "Модель Y"
    ws2["I13"].value = 55000.0
    ws2["K13"].value = 55000.0
    ws2["H14"].value = "10"
    buf2 = io.BytesIO()
    wb2.save(buf2)
    buf2.seek(0)
    parsed2 = parse_standardized_tkp_workbook(buf2.getvalue())
    assert parsed2["application"]["admitted"] is False
    assert parsed2["application"]["positions"][0]["compliance_status"] == "analog_rejected"
    assert "10" in parsed2["application"]["rejection_reason"]


def test_tkp_xlsx_with_exact_model_tz_correction():
    """Тест модели Заказчика с уточнением опечатки в ТЗ (tz_warning, заявка допускается)."""
    items_rows = [
        {
            "num": 1,
            "purchase_item_id": 103,
            "name": "Генератор бензиновый FUBAG TI 3000",
            "unit": "шт",
            "quantity": 1,
            "initial_unit_price": 60000.0,
            "initial_total": 60000.0,
            "characteristics": [
                {"name": "Объем бака", "req_value": "не менее 15", "unit": "л"},
            ],
        }
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(
        rows=items_rows,
        purchase_subject="Закупка генератора",
        customer_name="ВСКС",
    )

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    assert "Заказчика" in str(ws["G13"].value)
    ws["I13"].value = 58000.0
    ws["K13"].value = 58000.0
    # Участник вводит реальный объем бака модели 12 л (в ТЗ ошибочно запросили не менее 15)
    ws["H14"].value = "12"

    out_buf = io.BytesIO()
    wb.save(out_buf)
    out_buf.seek(0)

    parsed = parse_standardized_tkp_workbook(out_buf.getvalue())
    assert parsed is not None
    app = parsed["application"]
    pos = app["positions"][0]
    assert pos["is_exact_model_offer"] is True
    assert pos["has_tz_correction"] is True
    assert pos["compliance_status"] == "tz_warning"
    assert app["admitted"] is True  # Заявку НЕ отклонять!
    assert any("ТЗ" in w for w in app.get("warnings", []))


def test_tkp_pdf_with_structured_chars_roundtrip():
    """Тест генерации интерактивного PDF ТКП со структурированными характеристиками и roundtrip-парсинга."""
    items_rows = [
        {
            "num": 1,
            "purchase_item_id": 201,
            "name": "Компрессор воздушный",
            "unit": "шт",
            "quantity": 1,
            "initial_unit_price": 30000.0,
            "initial_total": 30000.0,
            "vat_rate": "20%",
            "characteristics": [
                {"name": "Производительность", "req_value": "не менее 200", "unit": "л/мин"},
            ],
        }
    ]

    pdf_bytes = build_standardized_tkp_pdf(
        rows=items_rows,
        purchase_subject="Закупка компрессора",
        customer_name="ВСКС",
    )

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    widget_names = [w.field_name for page in doc for w in page.widgets()]
    assert "item_0_unit_price" in widget_names
    assert "item_0_char_0_val" in widget_names

    # Заполняем форму через fitz конкретной моделью и конкретным числом:
    for page in doc:
        for w in page.widgets():
            if w.field_name == "item_0_offer_type":
                w.field_value = "Эквивалент (аналог)"
                w.update()
            elif w.field_name == "item_0_offered_specs":
                w.field_value = "Компрессор масляный Ремеза СБ4"
                w.update()
            elif w.field_name == "item_0_unit_price":
                w.field_value = "28000"
                w.update()
            elif w.field_name == "item_0_total_price":
                w.field_value = "28000"
                w.update()
            elif w.field_name == "item_0_char_0_val":
                w.field_value = "250"  # 250 л/мин >= 200 -> соответствует!
                w.update()

    filled_pdf_bytes = doc.tobytes()
    doc.close()

    parsed = parse_standardized_tkp_pdf(filled_pdf_bytes)
    assert parsed is not None
    app = parsed["application"]
    assert len(app["positions"]) == 1
    pos = app["positions"][0]
    assert pos["offered_name"] == "Компрессор масляный Ремеза СБ4"
    assert pos["unit_price"] == 28000.0
    assert pos["is_alternative"] is True
    assert pos["compliance_status"] == "analog_pending"
    assert app["admitted"] is True
    assert len(pos["characteristics"]) == 1
    assert pos["characteristics"][0]["offered_value"] == "250"
    assert pos["characteristics"][0]["compliant"] is True
