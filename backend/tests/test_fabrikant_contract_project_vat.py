# -*- coding: utf-8 -*-
"""Баг (владелец, прод, 28.10.2026): «Проект договора» в пакете Фабрикант
(/api/purchases/{pid}/fabrikant-package, fabrikant_contract_project.docx)
отказывался рендериться, если на закупке не указана ставка НДС (при
vat_applicable=True) или основание освобождения от НДС (при
vat_applicable=False) — закупка 4441 (субсидия 111) осталась без договора
в пакете. Этот документ — ПРОЕКТ, его показывают участникам ДО выбора
поставщика, когда НДС объективно ещё не определён.

Исправление (app/services/documents/fabrikant_package.py): оба отказа
убраны для doc_key == "fabrikant_contract_project"; вместо них в контекст
добавлен признак context["vat_undetermined"], шаблон сам решает, что
печатать в п.4.1 (три ветки: не определён / облагается / не облагается).

Тест рендерит сам шаблон fabrikant_contract_project.docx через docxtpl с
минимальным контекстом (без БД/HTTP) в трёх случаях и проверяет текст п.4.1.
"""
import os
import re
import sys
import zipfile
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docxtpl import DocxTemplate

from app.services.documents.fabrikant_contract_blank import (
    EXPLICIT_BLANK_FIELDS,
    apply_contract_project_blanks,
)

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "fabrikant_contract_project.docx"
)

# Минимальный набор переменных, которые шаблон реально использует (см.
# список {{ }} в документе) — остальные поля context строит generate.py/
# fabrikant_package.py на реальных данных закупки, здесь не нужны для
# проверки именно блока НДС.
_BASE_CTX = dict(
    contract_city="",
    contract_date="__.__._____ г.",
    contract_date_day="",
    contract_date_month="",
    contract_date_year="",
    contract_end_date="",
    contract_number="",
    contract_price_num="100 000,00",
    contract_price_words="сто тысяч",
    contractor_full_name="",
    contractor_signatory_basis="",
    contractor_signatory_name="",
    contractor_signatory_position="",
    customer_address="",
    customer_full_name="",
    customer_short_name="",
    customer_signatory_basis="",
    customer_signatory_name="",
    customer_signatory_position="",
    delivery_date="",
    procurement_protocol_number="",
    subsidy_agreement_date="",
    subsidy_agreement_number="",
    subsidy_grantor_name="",
    subsidy_ministry_name="",
    vat_exemption_article="",
    vat_rate=None,
    vat_applicable=False,
    vat_undetermined=True,
)


def _render_clause_4_1(ctx: dict) -> str:
    """Рендерит шаблон и возвращает текст абзаца п.4.1 (без XML-тегов)."""
    tpl = DocxTemplate(TEMPLATE_PATH)
    tpl.render(ctx)
    buf = BytesIO()
    tpl.save(buf)
    with zipfile.ZipFile(buf) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    # "4.1." как подстрока встречается раньше в документе внутри "2.4.1."
    # (другой пункт) — искать абзац НАДЁЖНО по сумме договора, которая
    # печатается только в п.4.1 этого шаблона.
    idx = xml.find("100 000")
    assert idx != -1, "сумма договора не найдена в сгенерированном документе"
    p_start = xml.rfind("<w:p ", 0, idx)
    p_end = xml.find("</w:p>", idx) + len("</w:p>")
    para_xml = xml[p_start:p_end]
    return re.sub(r"<[^>]+>", "", para_xml)


def test_vat_undetermined_renders_conditional_phrase():
    text = _render_clause_4_1({**_BASE_CTX})
    assert "НДС, если Поставщик является плательщиком НДС" in text
    assert "НДС не облагается, если Поставщик не является плательщиком НДС" in text


def test_vat_applicable_with_rate_renders_rate():
    ctx = {
        **_BASE_CTX,
        "vat_applicable": True,
        "vat_rate": 20,
        "vat_undetermined": False,
    }
    text = _render_clause_4_1(ctx)
    assert "в том числе НДС в размере 20%" in text
    assert "если Поставщик" not in text


def test_vat_exempt_with_article_renders_article():
    ctx = {
        **_BASE_CTX,
        "vat_applicable": False,
        "vat_exemption_article": "п.п. 1 п. 2 ст. 346.11 НК РФ",
        "vat_undetermined": False,
    }
    text = _render_clause_4_1(ctx)
    assert "НДС не облагается на основании п.п. 1 п. 2 ст. 346.11 НК РФ" in text


def _render_full_text(ctx: dict) -> str:
    """Рендерит шаблон целиком и возвращает весь видимый текст документа."""
    tpl = DocxTemplate(TEMPLATE_PATH)
    tpl.render(ctx)
    buf = BytesIO()
    tpl.save(buf)
    with zipfile.ZipFile(buf) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def test_contract_project_blanks_hide_price_contractor_and_number():
    """28.10.2026: ПРОЕКТ договора вешается на площадку ДО выбора поставщика —
    цена/номер/дата договора, протокол закупки и реквизиты Поставщика на
    этом этапе не существуют и не должны попадать в документ."""
    full_ctx = {
        **_BASE_CTX,
        "contract_number": "77/2026",
        "contract_date": "15.11.2026",
        "contract_price_num": "383 271,00",
        "contract_price_words": "триста восемьдесят три тысячи двести семьдесят один",
        "contractor_full_name": "ООО «Ромашка»",
        "contractor_short_name": "ООО Ромашка",
        "contractor_signatory_name": "Иванов И.И.",
        "procurement_protocol_number": "15",
        "vat_applicable": True,
        "vat_rate": 20,
        "vat_undetermined": False,
        "customer_full_name": "ГБУ «Тестовый заказчик»",
    }
    blanked = apply_contract_project_blanks(full_ctx)
    text = _render_full_text(blanked)

    assert "383" not in text
    assert "Ромашка" not in text
    assert "77/2026" not in text
    assert "20%" not in text
    assert "15.11.2026" not in text
    assert "ГБУ «Тестовый заказчик»" in text
    assert "None" not in text
    # vat_undetermined принудительно True для этого документа — печатается
    # условная фраза про НДС, а не ставка/основание.
    assert "НДС, если Поставщик является плательщиком НДС" in text


def test_apply_contract_project_blanks_contractor_prefix_blanked():
    ctx = {
        "contractor_full_name": "ООО «Ромашка»",
        "contractor_inn": "1234567890",
        "customer_full_name": "ГБУ «Тестовый заказчик»",
        "customer_short_name": "ГБУ ТЗ",
        "subsidy_grantor_name": "Минтруд",
        "contract_city": "Москва",
        "subject": "Поставка оборудования",
    }
    out = apply_contract_project_blanks(ctx)

    assert out is not ctx
    assert ctx["contractor_full_name"] == "ООО «Ромашка»"  # исходный dict не мутирован

    assert out["contractor_full_name"] != "ООО «Ромашка»"
    assert set(out["contractor_full_name"]) == {"_"}
    assert out["contractor_inn"] != "1234567890"

    assert out["customer_full_name"] == "ГБУ «Тестовый заказчик»"
    assert out["customer_short_name"] == "ГБУ ТЗ"
    assert out["subsidy_grantor_name"] == "Минтруд"
    assert out["contract_city"] == "Москва"
    assert out["subject"] == "Поставка оборудования"  # не subsidy_/customer_/contractor_, но и не в EXPLICIT — не трогаем

    assert out["vat_undetermined"] is True


def test_apply_contract_project_blanks_explicit_fields_blanked():
    ctx = {k: "ЗНАЧЕНИЕ" for k in EXPLICIT_BLANK_FIELDS}
    out = apply_contract_project_blanks(ctx)
    for key in EXPLICIT_BLANK_FIELDS:
        assert out[key] != "ЗНАЧЕНИЕ"
        assert "_" in out[key]
        assert "ЗНАЧЕНИЕ" not in out[key]
