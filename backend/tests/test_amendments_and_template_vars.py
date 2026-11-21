# -*- coding: utf-8 -*-
"""Целевые тесты волны 4c: Дополнительные соглашения к договору и справочник шаблонных переменных.

Проверяет:
1. Фильтрацию и группы справочника переменных (Заказчик, Подрядчик, поиск по ключу/описанию/примеру).
2. Склонение подписантов и авто-генерацию пунктов Доп. соглашения (цена с НДС, срок, спецификация).
3. Smoke-рендер шаблона contract_amendment.docx через DocxTemplate (без {% tr %} / {% tc %}).
4. Полный цикл генерации .docx Дополнительного соглашения со спецификацией позиций.
"""
import io
import os
import zipfile
from datetime import date
from pathlib import Path

import pytest
from docxtpl import DocxTemplate

from app.services.documents.contract_amendment import (
    build_amendment_clauses,
    build_amendment_context,
    generate_contract_amendment_docx,
)
from app.services.documents.template_variables import TEMPLATE_VARIABLES


def test_template_variables_has_customer_and_contractor_sections():
    """Справочник переменных чётко разделяет секции Заказчика и Подрядчика."""
    headers = [desc for (var, desc, _, _) in TEMPLATE_VARIABLES if not var]
    customer_headers = [h for h in headers if "ЗАКАЗЧИК" in h.upper()]
    contractor_headers = [h for h in headers if "ПОДРЯДЧИК" in h.upper()]

    assert len(customer_headers) >= 1, "Должна быть минимум 1 секция Заказчика"
    assert len(contractor_headers) >= 1, "Должна быть минимум 1 секция Подрядчика"

    # Переменные Заказчика и Подрядчика
    customer_vars = [v for (v, _, _, _) in TEMPLATE_VARIABLES if "customer_" in v]
    contractor_vars = [v for (v, _, _, _) in TEMPLATE_VARIABLES if "contractor_" in v]

    assert len(customer_vars) >= 15, "Реквизиты Заказчика должны содержать базовые поля"
    assert len(contractor_vars) >= 15, "Реквизиты Подрядчика должны содержать базовые поля"

    # Проверка ключевых полей
    assert "{{customer_inn}}" in customer_vars
    assert "{{customer_signatory_genitive}}" in customer_vars
    assert "{{contractor_inn}}" in contractor_vars
    assert "{{contractor_signatory_genitive}}" in contractor_vars


def test_template_variables_has_amendment_vars():
    """Справочник содержит переменные волны 4c для Дополнительных соглашений."""
    vars_dict = {v: desc for (v, desc, _, _) in TEMPLATE_VARIABLES if v}
    assert "{{amendment_number}}" in vars_dict
    assert "{{amendment_date}}" in vars_dict
    assert "{{clauses_text}}" in vars_dict
    assert "{{new_contract_price}}" in vars_dict
    assert "{{new_delivery_term}}" in vars_dict


def test_template_vars_filtering_logic():
    """Фильтрация по переменной, русскому описанию и примеру работает регистронезависимо."""
    # Поиск по ключу {{customer
    matches_key = [v for (v, d, et, er) in TEMPLATE_VARIABLES if "customer" in v.lower()]
    assert len(matches_key) > 0

    # Поиск по русскому описанию «родительном»
    matches_desc = [v for (v, d, et, er) in TEMPLATE_VARIABLES if "родительном" in d.lower()]
    assert len(matches_desc) > 0

    # Поиск по примеру «сбербанк»
    matches_ex = [
        v for (v, d, et, er) in TEMPLATE_VARIABLES
        if "сбербанк" in (et.lower() + " " + er.lower())
    ]
    assert len(matches_ex) > 0


def test_build_amendment_clauses_price_and_vat():
    """Формирование пункта об изменении цены договора с НДС и прописью."""
    price_change = {
        "new_price": 150000.0,
        "clause_ref": "3.1",
        "vat_applicable": True,
        "vat_rate": 20.0,
    }
    clauses = build_amendment_clauses(price_change=price_change)

    assert "1. Изложить пункт 3.1 Договора в следующей редакции:" in clauses
    assert "150 000,00 руб." in clauses
    assert "сто пятьдесят тысяч рублей 00 копеек" in clauses
    assert "в том числе НДС 20%" in clauses
    assert "Настоящее Дополнительное соглашение составлено в двух подлинных экземплярах" in clauses


def test_build_amendment_clauses_no_vat_and_term():
    """Формирование пунктов при УСН (без НДС) и продлении срока договора."""
    price_change = {
        "new_price": 75000.50,
        "clause_ref": "2.1",
        "vat_applicable": False,
    }
    term_change = {
        "new_date": date(2026, 12, 31),
        "clause_ref": "4.2",
    }
    clauses = build_amendment_clauses(price_change=price_change, term_change=term_change)

    assert "1. Изложить пункт 2.1 Договора" in clauses
    assert "75 000,50 руб." in clauses
    assert "НДС не облагается" in clauses
    assert "2. Изложить пункт 4.2 Договора" in clauses
    assert "31" in clauses and "декабря" in clauses and "2026" in clauses


def test_build_amendment_context_signatory_inflection():
    """Контекст ДС автоматически склоняет подписантов обеих сторон через contexts_signatory_cases."""
    contract_data = {
        "number": "Д-2026/042",
        "date": date(2026, 5, 10),
        "city": "Москва",
    }
    amendment_data = {
        "amendment_number": "1",
        "amendment_date": date(2026, 11, 15),
    }
    customer_data = {
        "full_name": "Всероссийский студенческий корпус спасателей",
        "short_name": "ВСКС",
        "signatory_name": "Козырев Евгений Викторович",
        "signatory_position": "Генеральный директор",
        "signatory_basis": "Устава",
    }
    contractor_data = {
        "full_name": "Общество с ограниченной ответственностью «Поставка-Плюс»",
        "short_name": "ООО «Поставка-Плюс»",
        "signatory_name": "Иванов Иван Иванович",
        "signatory_position": "Директор",
        "signatory_basis": "доверенности № 5",
    }

    ctx = build_amendment_context(
        contract_data=contract_data,
        amendment_data=amendment_data,
        customer_data=customer_data,
        contractor_data=contractor_data,
    )

    # Проверяем автоматическое склонение в родительный падеж
    assert "Генерального директора" in ctx["customer_signatory_genitive"]
    assert "Козырева Евгения Викторовича" in ctx["customer_signatory_genitive"]
    assert "Директора" in ctx["contractor_signatory_genitive"]
    assert "Иванова Ивана Ивановича" in ctx["contractor_signatory_genitive"]
    assert ctx["contract_number"] == "Д-2026/042"
    assert ctx["amendment_day"] == "15"
    assert ctx["amendment_month"] == "ноября"
    assert ctx["amendment_year"] == "2026"


def test_contract_amendment_template_smoke_render():
    """Smoke-рендер contract_amendment.docx через DocxTemplate без ошибок синтаксиса.

    В шаблоне КАТЕГОРИЧЕСКИ запрещены {% tr %} / {% tc %}.
    """
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    template_path = templates_dir / "contract_amendment.docx"
    assert template_path.exists(), f"Файл шаблона {template_path} должен существовать"

    # Проверяем, что в xml шаблона НЕТ тегов {% tr %} или {% tc %}
    with zipfile.ZipFile(template_path, "r") as z:
        for name in z.namelist():
            if name.endswith(".xml"):
                content = z.read(name).decode("utf-8", errors="ignore")
                assert "{% tr" not in content, f"Запрещённый тег '{{% tr' найден в {name}!"
                assert "{%tc" not in content and "{% tc" not in content, f"Запрещённый тег '{{% tc' найден в {name}!"

    # Smoke render через DocxTemplate
    tpl = DocxTemplate(str(template_path))
    dummy_ctx = {
        "amendment_number": "1",
        "contract_number": "42-ТЗ",
        "contract_date": "10.05.2026",
        "contract_city": "Москва",
        "amendment_day": "15",
        "amendment_month": "ноября",
        "amendment_year": "2026",
        "customer_full_name": "Организация Заказчика",
        "customer_short_name": "Заказчик",
        "customer_signatory_genitive": "Генерального директора Иванова И.И.",
        "customer_signatory_basis": "Устава",
        "contractor_full_name": "Организация Подрядчика",
        "contractor_short_name": "Подрядчик",
        "contractor_signatory_genitive": "Директора Петрова П.П.",
        "contractor_signatory_basis": "Устава",
        "clauses_text": "1. Пункт 1.\n\n2. Пункт 2.",
        "customer_address": "г. Москва",
        "customer_inn": "7700000001",
        "customer_kpp": "770001001",
        "customer_ogrn": "1027700000001",
        "customer_settlement_account": "40702810000000000001",
        "customer_bank_name": "Банк",
        "customer_bik": "044525225",
        "customer_correspondent_account": "30101810400000000225",
        "customer_signatory_position": "Гендиректор",
        "customer_signatory_name_initials": "И.И. Иванов",
        "contractor_address": "г. Москва",
        "contractor_inn": "7701234567",
        "contractor_kpp": "770101001",
        "contractor_ogrn": "1027701234567",
        "contractor_settlement_account": "40702810000000000002",
        "contractor_bank_name": "Банк",
        "contractor_bik": "044525225",
        "contractor_correspondent_account": "30101810400000000225",
        "contractor_signatory_position": "Директор",
        "contractor_signatory_name_initials": "П.П. Петров",
    }
    tpl.render(dummy_ctx)
    buf = io.BytesIO()
    tpl.save(buf)
    assert buf.getvalue().startswith(b"PK"), "Результат рендера должен быть валидным zip/docx файлом"


def test_generate_contract_amendment_docx_full_cycle():
    """Полный цикл генерации ДС со спецификацией позиций возвращает валидный .docx."""
    contract_data = {
        "number": "№ 128/2026",
        "date": date(2026, 4, 1),
        "city": "Москва",
    }
    amendment_data = {
        "amendment_number": "2",
        "amendment_date": date(2026, 11, 20),
        "price_change": {
            "new_price": 320000.0,
            "clause_ref": "3.1",
            "vat_applicable": True,
            "vat_rate": 20.0,
        },
        "term_change": {
            "new_date": date(2026, 12, 25),
            "clause_ref": "5.1",
        },
        "specification_items": [
            {"name": "Оборудование серверное", "unit": "компл.", "quantity": 2, "unit_price": 100000.0, "total": 200000.0},
            {"name": "Лицензии ПО", "unit": "шт.", "quantity": 10, "unit_price": 12000.0, "total": 120000.0},
        ],
    }
    customer_data = {
        "full_name": "Автономная некоммерческая организация Развития",
        "signatory_name": "Сидоров Алексей Петрович",
        "signatory_position": "Президент",
    }
    contractor_data = {
        "full_name": "ООО «ТехноИмпульс»",
        "signatory_name": "Васильев Игорь Олегович",
        "signatory_position": "Генеральный директор",
    }

    docx_bytes = generate_contract_amendment_docx(
        contract_data=contract_data,
        amendment_data=amendment_data,
        customer_data=customer_data,
        contractor_data=contractor_data,
    )

    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 1000
    assert docx_bytes.startswith(b"PK")

    # Проверяем, что внутри docx присутствует сгенерированный текст
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        xml_content = z.read("word/document.xml").decode("utf-8")
        assert "ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 2" in xml_content
        assert "№ 128/2026" in xml_content
        assert "320 000,00" in xml_content
        assert "Оборудование серверное" in xml_content
        assert "Лицензии ПО" in xml_content
