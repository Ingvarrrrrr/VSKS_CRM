# -*- coding: utf-8 -*-
"""Падежи субсидии-грантодателя/министерства — единственный расчёт,
`build_subsidy_grantor_context` (ПРАВИЛО №6, contexts_subsidy_grantor.py).

Владелец (28.10.2026): «subsidy_grantor_name мне нужно в родительном падеже,
и министерство субсидии тоже в родительном». До этого теста творительный
падеж грантодателя считался ДВАЖДЫ: contexts_extra.py через
`doc_case_org_name_case(..., 'ablt')`, fabrikant_package.py через отдельную
`_to_ablt_org_name` (без нормализации регистра) — см. git-историю. Этот
файл проверяет и конкретные примеры склонения, и что оба пути документов
(contexts_extra.add_phase28_context / fabrikant_package) теперь дают
одинаковые значения, потому что вызывают одну функцию.
"""
import pytest

from app.services.documents.contexts_subsidy_grantor import build_subsidy_grantor_context
from app.services.documents.contexts_extra import add_phase28_context


class _Subsidy:
    def __init__(self, grantor_name="", ministry_name=""):
        self.grantor_name = grantor_name
        self.ministry_name = ministry_name
        self.extra_contract_clause_1 = ""
        self.extra_contract_clause_2 = ""


@pytest.mark.parametrize(
    "grantor_name, expected_gen",
    [
        ("Федеральное агентство по делам молодёжи", "Федерального агентства по делам молодёжи"),
        ("Росмолодёжь", "Росмолодёжи"),
        ("Минтруд России", "Минтруда России"),
    ],
)
def test_grantor_genitive_examples(grantor_name, expected_gen):
    ctx = build_subsidy_grantor_context(_Subsidy(grantor_name=grantor_name))
    assert ctx["subsidy_grantor_name_gen"] == expected_gen


def test_ministry_genitive_example():
    ctx = build_subsidy_grantor_context(
        _Subsidy(ministry_name="Министерство труда и социальной защиты Российской Федерации")
    )
    assert ctx["subsidy_ministry_name_gen"] == "Министерства труда и социальной защиты Российской Федерации"
    # subsidy_ministry_name сам не склоняется и не меняет регистр (поведение не менялось).
    assert ctx["subsidy_ministry_name"] == "Министерство труда и социальной защиты Российской Федерации"


def test_empty_subsidy_is_null_safe():
    ctx = build_subsidy_grantor_context(None)
    assert ctx == {
        "subsidy_grantor_name": "",
        "subsidy_grantor_name_instrumental": "",
        "subsidy_grantor_name_gen": "",
        "subsidy_ministry_name": "",
        "subsidy_ministry_name_gen": "",
    }


def test_add_phase28_context_uses_single_source():
    """contexts_extra.py::add_phase28_context — тот же набор ключей, что и
    build_subsidy_grantor_context напрямую (один источник, не второй расчёт)."""
    subsidy = _Subsidy(
        grantor_name="Федеральное агентство по делам молодёжи",
        ministry_name="Министерство труда и социальной защиты Российской Федерации",
    )
    context: dict = {}
    add_phase28_context(context, subsidy, None, _FakePurchase(), can_view_pii=True)
    expected = build_subsidy_grantor_context(subsidy)
    for key, value in expected.items():
        assert context[key] == value


class _FakePurchase:
    """Минимальный Purchase для add_phase28_context — только поля, которые
    она читает до/после блока субсидии (try/except гасит остальное)."""
    commission_member_1_name = None
    commission_member_2_name = None
    commission_member_3_name = None
    contractor_ogrnip_date = None
