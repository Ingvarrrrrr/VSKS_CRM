# -*- coding: utf-8 -*-
"""Контекст договора: предоплата (is_prepayment/prepayment_date) и правка
реквизитов исполнителя на уровне субсидии (SubsidyContractorOverride).

Владелец (05.10.2026, план «Шаблоны договоров» .planning/quick/
2026-10-05-contract-templates/PLAN.md, п.3 и п.5):
- is_prepayment/prepayment_date должны попадать в контекст документа
  (advance_amount/payment_term_days уже были — не трогаем);
- правка реквизитов исполнителя на уровне субсидии (роутер
  PUT /subsidies/{id}/contractor-override) должна перекрывать карточку
  контрагента в контексте, а сам Contractor в БД не меняться.

Покрытие не end-to-end (см. test_contract_documents_use_contract_items.py —
тот же подход): чистые функции сборки контекста
(contexts_extra.add_prepayment_context, contexts_build.build_base_context_part1,
contractor_override.merge_contractor_override) на SimpleNamespace, плюс
один async-тест на реальной загрузке SubsidyContractorOverride из БД
(db_session — транзакция теста откатывается, см. conftest.py).
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.documents.contexts_extra import (
    add_prepayment_context,
    add_day_words_context,
    add_phase28_context,
    add_misc_purchase_context,
    contractor_org_type_for_docs,
)
from app.services.documents.contractor_override import (
    load_contractor_override,
    merge_contractor_override,
)


def _mk_purchase(**overrides):
    defaults = dict(is_prepayment=False, prepayment_date=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mk_contractor(**overrides):
    defaults = dict(
        name="ООО Ромашка", full_name="ООО «Ромашка»",
        inn="7700000000", kpp="770001001", ogrn="1027700000000",
        address="г. Москва", postal_address="",
        phone="+7 900 000-00-00", email="info@romashka.ru",
        signatory="Иванов Иван Иванович", signatory_basis="Устава",
        signatory_last_name="Иванов", signatory_first_name="Иван",
        signatory_middle_name="Иванович", signatory_position="Директор",
        settlement_account="40702810000000000001", bank_name="ПАО Банк",
        bik="044525225", correspondent_account="30101810000000000225",
        org_type="Юр.лицо", contact_person="", bank_details="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mk_override(**overrides):
    """Поля, не переданные в overrides, остаются None — _OverriddenContractor
    должен в этом случае откатываться на contractor."""
    fields = (
        "org_type", "inn", "kpp", "ogrn",
        "signatory", "signatory_position", "signatory_basis",
        "signatory_last_name", "signatory_first_name", "signatory_middle_name",
        "address", "postal_address", "bank_details",
        "settlement_account", "bank_name", "bik", "correspondent_account",
        "contact_person", "phone", "email",
    )
    data = {f: None for f in fields}
    data.update(overrides)
    return SimpleNamespace(**data)


# ---------------------------------------------------------------------------
# (а) is_prepayment / prepayment_date
# ---------------------------------------------------------------------------

def test_prepayment_true_with_date():
    p = _mk_purchase(is_prepayment=True, prepayment_date=date(2026, 10, 5))
    context = {}
    add_prepayment_context(context, p)
    assert context["is_prepayment"] is True
    assert context["prepayment_date"] == "05.10.2026"


def test_postpayment_false_empty_date():
    p = _mk_purchase(is_prepayment=False, prepayment_date=None)
    context = {}
    add_prepayment_context(context, p)
    assert context["is_prepayment"] is False
    assert context["prepayment_date"] == ""


def test_prepayment_missing_attrs_default_false_and_empty():
    """Закупка без этих колонок (старый объект/фикстура) — не падаем."""
    p = SimpleNamespace()
    context = {}
    add_prepayment_context(context, p)
    assert context["is_prepayment"] is False
    assert context["prepayment_date"] == ""


# ---------------------------------------------------------------------------
# Доработка (05.10, живая генерация): «X (X) рабочих дней» без прописи между
# скобками — payment_term_days_words / service_term_days_words /
# acceptance_term_days_words через formatting._chunk_to_words.
# ---------------------------------------------------------------------------

def _mk_full_purchase_for_days(**overrides):
    """Покрывает атрибуты, которые реально читают add_phase28_context
    (acceptance_term_days → умолчание 5) и add_misc_purchase_context
    (payment_term_days → умолчание 10) — чтобы воспроизвести ровно то, что
    видит add_day_words_context на живом пути генерации."""
    defaults = dict(
        commission_member_1_name=None, commission_member_2_name=None, commission_member_3_name=None,
        advance_amount=None, acceptance_term_days=None, penalty_rate=None,
        procurement_protocol_number=None, procurement_order_number=None, repair_request_number=None,
        contractor_ogrnip_date=None, warranty_period_days=None, warranty_period_unit=None,
        is_retroactive=False, delivery_by_supplier=True, has_stages=False,
        payment_term_days=None, applications_review_date=None, submission_deadline=None,
        service_term_days=None,
        subsidy_extra_clause_1=None, subsidy_extra_clause_2=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_day_words_reads_from_context_not_raw_p():
    """Функция обязана брать значение из уже собранного контекста (там, где
    уже применён фолбэк 5/10), а не заново читать p — context и p намеренно
    разные, чтобы доказать источник чтения."""
    context = {"payment_term_days": 7, "service_term_days": 15, "acceptance_term_days": None}
    p = _mk_purchase(payment_term_days=999, service_term_days=999, acceptance_term_days=999)
    add_day_words_context(context, p)
    assert context["payment_term_days_words"] == "семь"
    assert context["service_term_days_words"] == "пятнадцать"
    assert context["acceptance_term_days_words"] == ""


def test_day_words_full_path_uses_defaults_not_empty():
    """Дефект (05.10): «в течение 5 () рабочих дней» — пропись считалась от
    сырого p (None → ""), хотя цифрой печаталось умолчание 5/10.
    acceptance_term_days/payment_term_days=None на Purchase → в контексте
    после add_phase28_context/add_misc_purchase_context лежат умолчания
    5/10 → пропись должна быть «пять»/«десять», НЕ "".
    """
    p = _mk_full_purchase_for_days(acceptance_term_days=None, payment_term_days=None, service_term_days=None)
    context = {}
    add_phase28_context(context, None, None, p)
    add_misc_purchase_context(context, p, None)
    context["service_term_days"] = ""  # build_base_context_part2: p.service_term_days or ""
    add_day_words_context(context, p)

    assert context["acceptance_term_days"] == 5
    assert context["acceptance_term_days_words"] == "пять"
    assert context["payment_term_days"] == 10
    assert context["payment_term_days_words"] == "десять"
    assert context["service_term_days_words"] == ""


def test_day_words_missing_keys_default_empty():
    p = SimpleNamespace()
    context = {}
    add_day_words_context(context, p)
    assert context["payment_term_days_words"] == ""
    assert context["service_term_days_words"] == ""
    assert context["acceptance_term_days_words"] == ""


# ---------------------------------------------------------------------------
# Доработка (05.10): contractor_org_type_for_docs — пустой org_type + ИНН из
# 12 цифр («ИП»/физлицо) → 'ИП', иначе пустой org_type → "".
# ---------------------------------------------------------------------------

def test_org_type_empty_with_12_digit_inn_is_ip():
    c = _mk_contractor(org_type="", inn="123456789012")
    assert contractor_org_type_for_docs(c) == "ИП"


def test_org_type_empty_with_10_digit_inn_is_empty():
    c = _mk_contractor(org_type="", inn="1234567890")
    assert contractor_org_type_for_docs(c) == ""


def test_org_type_nonempty_passed_through():
    c = _mk_contractor(org_type="Юр.лицо", inn="1234567890")
    assert contractor_org_type_for_docs(c) == "Юр.лицо"


def test_org_type_samozanyaty_not_touched():
    c = _mk_contractor(org_type="Самозанятый", inn="123456789012")
    assert contractor_org_type_for_docs(c) == "Самозанятый"


def test_org_type_none_contractor_is_empty():
    assert contractor_org_type_for_docs(None) == ""


# ---------------------------------------------------------------------------
# (б) override субсидии перекрывает ИНН/банк исполнителя
# ---------------------------------------------------------------------------

def test_merge_override_overrides_inn_and_bank():
    contractor = _mk_contractor(inn="7700000000", bank_name="ПАО Банк", bik="044525225")
    override = _mk_override(inn="9900000099", bank_name="АО Другой Банк", bik="044000001")

    merged = merge_contractor_override(contractor, override)

    assert merged.inn == "9900000099"
    assert merged.bank_name == "АО Другой Банк"
    assert merged.bik == "044000001"
    # Поля, не заданные в override (None) — откат на contractor.
    assert merged.kpp == contractor.kpp
    assert merged.signatory == contractor.signatory
    # Поля ВНЕ override (passport_* и т.п. — не входят в override) читаются
    # из contractor без изменений.
    assert merged.name == contractor.name


def test_merge_override_does_not_mutate_contractor():
    contractor = _mk_contractor(inn="7700000000")
    override = _mk_override(inn="9900000099")

    merge_contractor_override(contractor, override)

    assert contractor.inn == "7700000000"  # ORM-объект (здесь SimpleNamespace) не тронут


def test_merge_override_empty_override_fields_fall_back_to_contractor():
    """Override существует (строка в БД), но конкретное поле не заполнено
    (пустая строка/None) — в контракте остаётся значение контрагента."""
    contractor = _mk_contractor(phone="+7 900 000-00-00")
    override = _mk_override(phone="")  # пустая строка, не None

    merged = merge_contractor_override(contractor, override)

    assert merged.phone == "+7 900 000-00-00"


# ---------------------------------------------------------------------------
# (в) без override — значения из Contractor как есть
# ---------------------------------------------------------------------------

def test_merge_without_override_returns_contractor_unchanged():
    contractor = _mk_contractor(inn="7700000000")
    merged = merge_contractor_override(contractor, None)
    assert merged is contractor
    assert merged.inn == "7700000000"


def test_merge_with_none_contractor_returns_none():
    override = _mk_override(inn="9900000099")
    assert merge_contractor_override(None, override) is None


# ---------------------------------------------------------------------------
# load_contractor_override — реальный запрос к БД (SubsidyContractorOverride)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_contractor_override_from_db(db_session):
    from app.models.contractor import Contractor
    from app.models.subsidy import Subsidy
    from app.models.subsidy_contractor_override import SubsidyContractorOverride

    contractor = Contractor(name="ООО Тестовый", inn="7711111111", bank_name="Старый банк")
    db_session.add(contractor)
    await db_session.flush()

    subsidy = Subsidy(name="Тестовая субсидия", year=2026, contractor_id=contractor.id)
    db_session.add(subsidy)
    await db_session.flush()

    override = SubsidyContractorOverride(
        subsidy_id=subsidy.id,
        contractor_id=contractor.id,
        inn="7799999999",
        bank_name="Новый банк (субсидия)",
    )
    db_session.add(override)
    await db_session.commit()

    loaded = await load_contractor_override(db_session, subsidy.id, contractor.id)
    assert loaded is not None
    assert loaded.inn == "7799999999"

    merged = merge_contractor_override(contractor, loaded)
    assert merged.inn == "7799999999"
    assert merged.bank_name == "Новый банк (субсидия)"
    # Contractor в БД не изменён.
    await db_session.refresh(contractor)
    assert contractor.inn == "7711111111"
    assert contractor.bank_name == "Старый банк"


@pytest.mark.asyncio
async def test_load_contractor_override_returns_none_when_absent(db_session):
    from app.models.contractor import Contractor

    contractor = Contractor(name="ООО Без правки", inn="7722222222")
    db_session.add(contractor)
    await db_session.flush()

    loaded = await load_contractor_override(db_session, 999999, contractor.id)
    assert loaded is None
