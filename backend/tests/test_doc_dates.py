# -*- coding: utf-8 -*-
"""Единый формат дат в документах закупки — ДД.ММ.ГГГГ везде (владелец,
28.10.2026, TASKS.md: «дата завершения закупки — откуда и формат ДД.ММ.ГГ
везде»).

app.services.documents.formatting._fmt_date — ЕДИНСТВЕННЫЙ источник формата
дат для документов (ПРАВИЛО №6, уже существовал и уже использовался почти
везде — см. 28.10.2026 обход contexts.py/contexts_build.py/fabrikant_package.py/
contexts_extra.py/stages_approvers_list.py, где несколько мест звали
`d.strftime('%d.%m.%Y')` напрямую вместо общей функции — переведены на неё).
Новый хелпер здесь НЕ создаётся — проверяем существующий `_fmt_date` и прогоняем
через него builder контекста документа (contexts_build.py) на Purchase-заглушке
(SimpleNamespace, без БД — тот же приём, что в test_fabrikant_contexts_single_source.py
и test_document_formatting.py).

Явные исключения из общей проверки «каждая дата = ДД.ММ.ГГГГ» (по имени ключа):
  - today_iso — машинный ISO-формат для JSON (имя явно это объявляет);
  - submission_deadline_time — отдельное ЧЧ:ММ, не дата;
  - submission_deadline_datetime — составной «ДД.ММ.ГГГГ ЧЧ:ММ», не
    голая дата, формат проверяется отдельным тестом ниже.
    submission_deadline_date (28.10.2026, баг) раньше печатался как
    ISO (`.date().isoformat()`) прямо в docx — переведён на `_fmt_date`,
    больше не исключение, проверяется общим циклом ниже;
  - contract_date_day / contract_date_month / contract_date_year — «дата
    прописью» ПО ЧАСТЯМ (день / месяц словом / год) — отдельная функция
    (_cd_parts в fabrikant_package.py, её копия в stages_amounts.py), по
    заданию её трогать и путать с обычным форматированием нельзя.
"""
from datetime import date, datetime
from types import SimpleNamespace
import re

import pytest

from app.services.documents.formatting import _fmt_date
from app.services.documents import contexts_build as cb


_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

# Ключи, которые СОДЕРЖАТ "date"/«дата» в имени, но по дизайну не обязаны
# быть датой-строкой ДД.ММ.ГГГГ — см. докстринг модуля.
_NON_HUMAN_DATE_KEYS = {
    "today_iso",
    "submission_deadline_time",
    "submission_deadline_datetime",
    "contract_date_day",
    "contract_date_month",
    "contract_date_year",
}

# acceptance_doc_date умеет несколько дат через "; " (несколько документов
# приёмки) — каждая часть всё равно должна быть ДД.ММ.ГГГГ.
_MULTI_DATE_KEYS = {"acceptance_doc_date"}

_DATE_KEY_HINTS = ("date", "дата")

# Поля-даты, чьё имя НЕ содержит подстроку "date"/«дата» (унаследованные
# от модели Purchase названия — execution_term/execution_term_changed/today),
# но которые обязаны быть датой ДД.ММ.ГГГГ в контексте документа. Хинт по
# подстроке их не находит, поэтому они в отдельном явном списке.
_EXTRA_DATE_KEYS = {"execution_term", "execution_term_changed", "today"}


# ---------------------------------------------------------------------------
# _fmt_date сама по себе — единственный источник формата (ПРАВИЛО №6)
# ---------------------------------------------------------------------------

def test_fmt_date_formats_date_object():
    assert _fmt_date(date(2026, 3, 7)) == "07.03.2026"


def test_fmt_date_formats_datetime_object():
    assert _fmt_date(datetime(2026, 3, 7, 17, 30)) == "07.03.2026"


def test_fmt_date_parses_iso_string():
    assert _fmt_date("2026-03-07") == "07.03.2026"


def test_fmt_date_none_and_empty_render_as_empty_string():
    assert _fmt_date(None) == ""
    assert _fmt_date("") == ""


def test_fmt_date_non_iso_string_returned_as_is():
    # Нераспознанная строка (не ISO) — не падает, возвращается как есть
    # (formatting.py: ValueError → return d).
    assert _fmt_date("не дата") == "не дата"


# ---------------------------------------------------------------------------
# Полный контекст документа закупки — НИ ОДНА дата не остаётся в "сыром"
# виде (.isoformat(), str(date), ручной strftime с другим форматом и т.п.)
# ---------------------------------------------------------------------------

def _make_purchase_stub():
    d = date(2026, 3, 7)
    return SimpleNamespace(
        purchase_number=17, registry_number="РЕЕ-2026-00017",
        purchase_method="single", subject="Тестовая закупка", status="contracted",
        purchase_basis="plan_schedule",
        feo_category=None,
        total_nmck=100000, nmck=100000, planned_total_price=100000,
        contract_price=100000, price_increase=0,
        contract_number="17/2026", contract_date=d,
        execution_term=d, execution_term_changed=d, delivery_date=d,
        country_origin="Россия",
        payment_doc_number="ПП-1", payment_doc_date=d,
        payment_amount=50000, payment_federal=0,
        purchase_contract_type="single",
        service_period_type="period", service_start_date=d, service_end_date=d,
        service_term_mode="range", service_term_days=None, service_term_type=None,
        service_deadline_date=d, contract_end_date=d,
        submission_deadline=datetime(2026, 1, 10, 17, 0),
        delivery_location="", third_party_involved=False,
        acceptance_docs=[], acceptance_doc_name="Акт", acceptance_doc_number="1",
        acceptance_doc_date=d, acceptance_doc_amount=50000,
        items=[],
    )


@pytest.mark.asyncio
async def test_purchase_document_context_all_dates_ddmmyyyy():
    p = _make_purchase_stub()
    subsidy = SimpleNamespace(name="Тест", year=2026, budget=0, agreement_text="")

    context = cb.build_base_context_part1(
        p=p, subsidy=subsidy, c=None, doc_indices=None, doc_type="contract",
        feo_path="", feo_level_1="", feo_level_2="", feo_level_3="",
        resolved_responsible="", resolved_responsible_full="",
        items_list=[], item_categories_str="",
        amounts={
            "items_sum_val": 0.0, "doc_amount_val": 100000.0,
            "plan_amount_val": 100000.0, "contract_amount_val": 100000.0,
            "economy_val": 0.0,
        },
    )
    await cb.build_base_context_part2(
        context, p=p, subsidy=subsidy, db=None,
        approvers_list=[], initiator=None, event=None,
        cd_day="07", cd_month="марта", cd_year="2026",
        c=None, subject_kind="goods",
        amounts={
            "doc_amount_val": 100000.0, "contract_amount_val": 100000.0,
            "vat_app": True, "vat_rate_val": None, "vat_amount_val": 0.0,
            "vat_info_line": "", "amount_is_planned": False, "is_advance": False,
        },
    )

    checked = []
    for key, value in context.items():
        if key in _NON_HUMAN_DATE_KEYS:
            continue
        if not isinstance(value, str) or not value:
            continue
        is_date_key = key in _EXTRA_DATE_KEYS or any(hint in key.lower() for hint in _DATE_KEY_HINTS)
        if not is_date_key:
            continue
        checked.append(key)
        if key in _MULTI_DATE_KEYS:
            parts = value.split("; ")
            assert all(_DATE_RE.match(part) for part in parts), (
                f"{key}={value!r} — не ДД.ММ.ГГГГ"
            )
        else:
            assert _DATE_RE.match(value), f"{key}={value!r} — не ДД.ММ.ГГГГ"

    # Страховка самого теста: при пустой заглушке ничего не проверилось бы,
    # а тест бы молча «прошёл» — такие даты должны реально встретиться.
    assert "contract_date" in checked
    assert "execution_term" in checked
    assert "payment_doc_date" in checked
    assert "service_deadline_date" in checked
    assert "contract_end_date" in checked
    assert "acceptance_doc_date" in checked
    assert "submission_deadline_date" in checked

    # Явная проверка на баг 28.10.2026: submission_deadline_date выводился
    # как ISO (2026-01-10) вместо ДД.ММ.ГГГГ.
    assert context["submission_deadline_date"] == "10.01.2026"
