# -*- coding: utf-8 -*-
"""«Без НМЦД» → «Не определена» (владелец, 28.10.2026, TASKS.md: пакет жалоб
28.10, пункт «без НМЦД» → «Не определена»).

До правки: выбор «Опубликовать без НМЦД» (PublishRequest.no_nmcd,
app/routers/publications.py) не доходил до документов, прилагаемых к той же
публикации (fabrikant_package.py) — total_nmcd/total_nmck/nmck считались как
обычно (реальное число или "0,00"), хотя в SOAP-пакет та же НМЦД уже не
уходит (_initial_sum_xml пропускает элемент при no_nmcd).

Тест проверяет единственную функцию-источник — apply_no_nmcd_override
(app.services.documents.nmcd_undetermined) — без БД/HTTP, плюс то, что
render_fabrikant_package_files реально зовёт именно её (а не вторую копию
проверки флага где-то ещё, ПРАВИЛО №6)."""
from app.services.documents.nmcd_undetermined import (
    NMCD_VARIABLE_KEYS,
    NMCD_UNDETERMINED_TEXT,
    apply_no_nmcd_override,
)
from app.services.documents import fabrikant_package as fp


def test_no_nmcd_overrides_all_three_aliases_to_undetermined():
    context = {
        "total_nmcd": "130 000,00",
        "total_nmck": "130 000,00",
        "nmck": "130 000,00",
        "other_key": "не трогать",
    }
    apply_no_nmcd_override(context, no_nmcd=True)
    for key in NMCD_VARIABLE_KEYS:
        assert context[key] == "Не определена" == NMCD_UNDETERMINED_TEXT
    assert context["other_key"] == "не трогать"


def test_no_nmcd_false_leaves_context_untouched():
    context = {"total_nmcd": "130 000,00", "total_nmck": "130 000,00", "nmck": "130 000,00"}
    original = dict(context)
    apply_no_nmcd_override(context, no_nmcd=False)
    assert context == original


def test_no_nmcd_overrides_zero_amount_too():
    """Закупка без заполненной НМЦД (0/"0,00") — тоже должна стать "Не
    определена", не остаться нулём: именно 0 раньше печаталось, когда
    НМЦД физически нет и выбрано «без НМЦД» при публикации."""
    context = {"total_nmcd": "0,00", "total_nmck": "0,00", "nmck": "0,00"}
    apply_no_nmcd_override(context, no_nmcd=True)
    assert all(context[k] == "Не определена" for k in NMCD_VARIABLE_KEYS)


def test_render_fabrikant_package_files_uses_canonical_override():
    """generate.py/fabrikant_package.py не должны заводить вторую проверку
    `if no_nmcd: ...` где-то ещё — единственный расчёт, ПРАВИЛО №6."""
    assert fp.apply_no_nmcd_override is apply_no_nmcd_override
