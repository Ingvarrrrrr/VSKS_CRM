# -*- coding: utf-8 -*-
"""ПРАВИЛО №6 (14.10.2026, обход fabrikant_package.py/contexts_build.py):
подписанты Заказчика/Исполнителя и номер/дата соглашения о субсидии раньше
считались ДВАЖДЫ — черновой копией прямо в литерале `context = {...}`
(и в fabrikant_package.py, и в contexts_build.py::build_base_context_part2),
и ещё раз канонически в add_customer_context/add_contractor_signatory_context/
add_subsidy_agreement_context (contexts_extra.py), которые вызывались ПОСЛЕ
и просто перекрывали черновик. Рабочий результат совпадал случайно — пока
кто-то не поправил только одну из копий.

Этот файл:
  (а) офлайн (без БД, SimpleNamespace) доказывает, что generate.py-путь и
      fabrikant_package.py-путь вызывают БУКВАЛЬНО ОДНИ И ТЕ ЖЕ функции
      (идентичность объектов) — расхождение между путями теперь физически
      невозможно, а не "совпадает по значению сейчас";
  (б) на одних и тех же входных данных (contractor/customer_org/customer_ctr/
      subsidy) гоняет эти функции в ДВА независимых пустых контекста и
      проверяет побайтовое совпадение подписантских/субсидийных ключей —
      имитация двух путей (generate.py строит context литералом, затем
      add_*_context; fabrikant_package.py — свой литерал, затем те же
      add_*_context) без необходимости поднимать БД;
  (в) статический guard по исходнику: в литерале `context = {...}` внутри
      fabrikant_package.py и в context.update({...}) внутри
      build_base_context_part2 (contexts_build.py) не должно быть черновых
      ключей подписантов/субсидии — защита от повторного заведения второй
      копии (см. feedback_single_source_of_truth.md).
"""
import os
import re
from types import SimpleNamespace

from app.services.documents import fabrikant_package as fp
from app.services.documents import contexts_build as cb
from app.services.documents import generate as gen
from app.services.documents.contexts_extra import (
    add_customer_context,
    add_contractor_signatory_context,
    add_subsidy_agreement_context,
)


# ── (а) идентичность функций — оба пути дёргают один и тот же объект ───────

def test_fabrikant_package_uses_canonical_functions():
    assert fp.add_customer_context is add_customer_context
    assert fp.add_contractor_signatory_context is add_contractor_signatory_context
    assert fp.add_subsidy_agreement_context is add_subsidy_agreement_context


def test_generate_uses_canonical_functions():
    assert gen.add_customer_context is add_customer_context
    assert gen.add_contractor_signatory_context is add_contractor_signatory_context


# ── (б) одни и те же входные данные → побайтово одинаковый результат ───────

def _stub_contractor():
    return SimpleNamespace(
        name="ООО «Ромашка»", full_name=None, inn="7701234567", kpp="770101001",
        address="г. Москва, ул. Садовая, д. 5", postal_address="", ogrn="1027701234567",
        phone="", email="", signatory="Сидоров Пётр Павлович",
        signatory_basis="Устава", signatory_last_name=None, signatory_first_name=None,
        signatory_middle_name=None, signatory_position="Директор",
        settlement_account="", bank_name="", bik="", correspondent_account="",
        personal_account="", org_type="ООО",
    )


def _stub_customer_org():
    return SimpleNamespace(name="АНО «ВСКС»", contractor_id=None, contract_city="Москва")


def _stub_customer_ctr():
    return SimpleNamespace(
        name="АНО «ВСКС»", full_name="Автономная некоммерческая организация «ВСКС»",
        inn="7700000001", kpp="770001001", address="г. Москва, ул. Ленина, д. 1",
        postal_address="г. Москва, ул. Ленина, д. 1", ogrn="1027700000001",
        bank_name="ПАО «Сбербанк»", settlement_account="40703810400000000001",
        correspondent_account="30101810400000000225", bik="044525225",
        personal_account="", phone="+7 (495) 000-00-01", email="info@vsks.ru",
        signatory="Козеев Евгений Викторович", signatory_basis="Устава",
        signatory_last_name=None, signatory_first_name=None, signatory_middle_name=None,
        signatory_position="Президент",
    )


def _stub_subsidy():
    return SimpleNamespace(
        name="ФАДМ-2026", year=2026, budget=1_000_000, grantor_name="ФАДМ",
        ministry_name="Минтруд", basis_doc_number="091-10-2025-032",
        basis_doc_date=None, agreement_number=None, agreement_text="",
        extra_contract_clause_1="", extra_contract_clause_2="",
    )


_SIGNATORY_SUBSIDY_KEYS = (
    "customer_signatory", "customer_signatory_position", "customer_signatory_name",
    "customer_signatory_name_genitive", "customer_signatory_initials",
    "customer_signatory_name_initials", "customer_signatory_basis",
    "customer_name", "customer_full_name", "customer_inn", "customer_kpp",
    "contract_city",
    "contractor_signatory_position", "contractor_signatory_name",
    "contractor_signatory_name_genitive", "contractor_signatory_initials",
    "contractor_signatory_name_initials", "contractor_ogrnip", "contractor_full_name",
    "subsidy_agreement_number", "subsidy_agreement_date",
)


def test_generate_and_fabrikant_paths_produce_identical_signatory_values():
    """Симулирует оба пути: generate.py кладёт свой литерал (здесь — минимальный
    стенд, не весь build_base_context_part1/2), fabrikant_package.py — свой,
    затем ОБА вызывают одни и те же add_*_context. Результат по ключам
    подписантов/субсидии обязан совпасть побайтово."""
    c = _stub_contractor()
    customer_org = _stub_customer_org()
    customer_ctr = _stub_customer_ctr()
    subsidy = _stub_subsidy()

    ctx_generate_style: dict = {"_marker": "generate.py"}
    add_subsidy_agreement_context(ctx_generate_style, subsidy)
    add_customer_context(ctx_generate_style, customer_org, customer_ctr)
    add_contractor_signatory_context(ctx_generate_style, c)

    ctx_fabrikant_style: dict = {"_marker": "fabrikant_package.py"}
    add_subsidy_agreement_context(ctx_fabrikant_style, subsidy)
    add_contractor_signatory_context(ctx_fabrikant_style, c)
    add_customer_context(ctx_fabrikant_style, customer_org, customer_ctr)

    for key in _SIGNATORY_SUBSIDY_KEYS:
        assert key in ctx_generate_style, f"{key} не попал в generate.py-контекст"
        assert key in ctx_fabrikant_style, f"{key} не попал в fabrikant_package.py-контекст"
        assert ctx_generate_style[key] == ctx_fabrikant_style[key], (
            f"{key} расходится между путями: "
            f"{ctx_generate_style[key]!r} != {ctx_fabrikant_style[key]!r}"
        )


# ── (в) статический guard — черновик не возвращается в литералы ────────────

_FABRIKANT_PACKAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "services", "documents", "fabrikant_package.py",
)
_CONTEXTS_BUILD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "services", "documents", "contexts_build.py",
)

# Ключи, единственный расчёт которых — add_customer_context/
# add_contractor_signatory_context/add_subsidy_agreement_context. Второй
# прямой литерал с этими ключами в context={...}/context.update({...}) —
# регрессия (вторая копия той же формулы, ПРАВИЛО №6).
_SINGLE_SOURCE_KEY_LITERALS = (
    '"customer_signatory"', '"customer_signatory_position"',
    '"customer_signatory_name"', '"customer_name"', '"customer_full_name"',
    '"contractor_signatory_position"', '"contractor_signatory_name"',
    '"contractor_ogrnip"',
    '"subsidy_agreement_number"', '"subsidy_agreement_date"',
)


def _literal_dict_source(full_source: str, start_marker: str) -> str:
    """Вырезает текст от start_marker (строка с `context = {` или
    `context.update({`) до закрывающей `}` на том же уровне вложенности —
    достаточно грубо (нет вложенных словарей с фигурными скобками глубже
    одного уровня в этих литералах), но хватает для guard-проверки ключей."""
    idx = full_source.index(start_marker)
    depth = 0
    i = full_source.index("{", idx)
    start = i
    for j in range(i, len(full_source)):
        if full_source[j] == "{":
            depth += 1
        elif full_source[j] == "}":
            depth -= 1
            if depth == 0:
                return full_source[start:j + 1]
    raise AssertionError(f"не нашёл закрывающую скобку для {start_marker!r}")


def test_fabrikant_package_literal_has_no_draft_signatory_keys():
    with open(_FABRIKANT_PACKAGE_PATH, encoding="utf-8") as f:
        src = f.read()
    literal = _literal_dict_source(src, "    context = {")
    found = [k for k in _SINGLE_SOURCE_KEY_LITERALS if k in literal]
    assert not found, (
        f"fabrikant_package.py: черновые ключи вернулись в литерал context={{...}}: {found}"
    )


def test_contexts_build_literal_has_no_draft_signatory_position():
    with open(_CONTEXTS_BUILD_PATH, encoding="utf-8") as f:
        src = f.read()
    literal = _literal_dict_source(src, "    context.update({")
    assert '"contractor_signatory_position"' not in literal, (
        "contexts_build.py: contractor_signatory_position вернулся в "
        "build_base_context_part2 черновиком — единственный расчёт в "
        "add_contractor_signatory_context (generate.py вызывает её позже)"
    )


# ── doc_kind — найденный обходом шаблонов пробел (service_note_*.docx) ─────

def test_doc_kind_derived_from_service_note_doc_type():
    """14.10.2026: обход backend/templates/*.docx нашёл {% if doc_kind == ... %}
    в service_note_advance/payment/procurement.docx — переменная никогда не
    клалась в контекст. Единственный расчёт — build_base_context_part1
    (contexts_build.py), по doc_type."""
    for doc_type, expected in (
        ("service_note_advance", "advance"),
        ("service_note_delivery", "delivery"),
        ("service_note_payment", "payment"),
        ("service_note_procurement", "procurement"),
        ("contract", ""),
        (None, ""),
    ):
        ctx = cb.build_base_context_part1(
            p=SimpleNamespace(
                purchase_number="", registry_number="", purchase_method=None,
                subject="", status="", purchase_basis=None, responsible_person="",
                responsible_position=None,
                feo_category=None, contract_price=None, economy=None,
                contract_number="", contract_date=None, execution_term=None,
                execution_term_changed=None, price_increase=None,
                delivery_date=None, country_origin=None, payment_doc_number="",
                payment_doc_date=None, payment_amount=None, payment_federal=None,
                purchase_contract_type=None, acceptance_docs=None,
                acceptance_doc_amount=None, planned_total_price=None, total_nmck=None,
                items=[],
            ),
            subsidy=None, c=None, doc_indices=None, doc_type=doc_type,
            feo_path="", feo_level_1="", feo_level_2="", feo_level_3="",
            resolved_responsible="", resolved_responsible_full="",
            items_list=[], item_categories_str="",
            amounts={
                "items_sum_val": 0.0, "doc_amount_val": 0.0,
                "plan_amount_val": 0.0, "contract_amount_val": 0.0,
            },
        )
        assert ctx["doc_kind"] == expected, f"doc_type={doc_type!r}"
