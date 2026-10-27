"""Приёмочные тесты (владелец, 14.10.2026): «нет в переменных для шаблонов
способа закупки, номера и даты субсидии, должности подписанта в родительном
падеже, ФИО подписанта в родительном падеже».

Офлайн, без БД и сети — контекст строится на заглушках (SimpleNamespace),
как и в test_contract_context_prepay_override.py.

ПРАВИЛО №6: проверяем, что
  (а) ключи, реально кладущиеся в контекст add_customer_context /
      add_contractor_signatory_context / add_subsidy_agreement_context,
      присутствуют в единственном справочнике TEMPLATE_VARIABLES;
  (б) ключи comments_ru.py — тоже подмножество TEMPLATE_VARIABLES;
  (в) склонение ФИО (petrovich) и должности (pymorphy3) в родительный падеж
      работает корректно на примерах из задания;
  (г) subsidy_agreement_number берётся из Subsidy.basis_doc_number.
"""
import os
import sys
import types as _types
from types import SimpleNamespace

from app.services.documents.template_variables import TEMPLATE_VARIABLES
from app.services.documents.contexts_extra import (
    add_customer_context,
    add_contractor_signatory_context,
    add_subsidy_agreement_context,
)
from app.services.documents.morphology import _to_gen_fio, _to_gen_phrase

TEMPLATE_VAR_NAMES = {v for (v, _d, _et, _er) in TEMPLATE_VARIABLES if v}


def _var_names_in(context_keys) -> set[str]:
    return {"{{" + k + "}}" for k in context_keys}


def _stub_subsidy(**kw):
    base = dict(
        name="Тест", year=2026, budget=None, grantor_name=None, ministry_name=None,
        basis_doc_number=None, basis_doc_date=None, agreement_number=None,
        agreement_text=None, extra_contract_clause_1=None, extra_contract_clause_2=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _stub_contractor(**kw):
    base = dict(
        name="ООО «Ромашка»", full_name=None, inn="7700000002", kpp="770001002",
        address="", postal_address="", ogrn="1027700000002", phone="", email="",
        signatory="", signatory_basis="Устава", signatory_last_name=None,
        signatory_first_name=None, signatory_middle_name=None, signatory_position=None,
        settlement_account="", bank_name="", bik="", correspondent_account="",
        personal_account="", org_type="ООО",
        # Карточка контрагента, не вошедшие в базовый стаб выше — владелец,
        # 27.10.2026: поля карточки казначейства, для которых не было
        # переменных шаблона (см. test_*_extra_requisite_keys_* ниже).
        website="", okpo="", okved="", registration_date=None,
        treasury_account="", single_treasury_account="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _stub_org():
    return None


def _stub_org_linked_to(contractor, **kw):
    """Organization, привязанная к контрагенту (org.contractor_id ==
    contractor.id) — org_requisites() в этом случае читает реквизиты, включая
    подписанта, ИЗ КОНТРАГЕНТА (см. app.services.org_requisites)."""
    contractor.id = kw.pop("contractor_id_value", 1)
    base = dict(
        id=1, contractor_id=contractor.id, name="ВСКС", contract_city=None,
        full_name=None, inn=None, kpp=None, ogrn=None, address=None,
        signatory=None, signatory_position=None,
        signatory_last_name=None, signatory_first_name=None, signatory_middle_name=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── (а) ключи контекста ⊆ TEMPLATE_VARIABLES ────────────────────────────────

def test_contractor_signatory_context_keys_in_template_variables():
    c = _stub_contractor(
        signatory_last_name="Иванов", signatory_first_name="Пётр",
        signatory_middle_name="Сергеевич", signatory_position="Генеральный директор",
    )
    ctx: dict = {}
    add_contractor_signatory_context(ctx, c)
    missing = _var_names_in(ctx.keys()) - TEMPLATE_VAR_NAMES
    assert not missing, f"ключи отсутствуют в TEMPLATE_VARIABLES: {missing}"
    assert "contractor_signatory_position_genitive" in ctx
    assert "contractor_signatory_name_initials" in ctx


def test_customer_context_keys_in_template_variables():
    ctr = _stub_contractor(
        signatory_last_name="Козеев", signatory_first_name="Евгений",
        signatory_middle_name="Викторович", signatory_position="Президент",
    )
    ctx: dict = {}
    add_customer_context(ctx, None, ctr)
    missing = _var_names_in(ctx.keys()) - TEMPLATE_VAR_NAMES
    assert not missing, f"ключи отсутствуют в TEMPLATE_VARIABLES: {missing}"
    assert "customer_signatory_position_genitive" in ctx


def test_subsidy_agreement_context_keys_in_template_variables():
    ctx: dict = {}
    add_subsidy_agreement_context(ctx, _stub_subsidy(basis_doc_number="091-10-2025-032"))
    missing = _var_names_in(ctx.keys()) - TEMPLATE_VAR_NAMES
    assert not missing, f"ключи отсутствуют в TEMPLATE_VARIABLES: {missing}"


# ── (б) comments_ru ⊆ TEMPLATE_VARIABLES ────────────────────────────────────

def _ensure_backend_package_importable() -> None:
    """Та же обёртка, что и в test_contract_templates_hints.py: в контейнере
    backend_b рабочая папка /app уже содержит backend/ без самой папки
    `backend` на диске — регистрируем namespace-пакет вручную."""
    if "backend" in sys.modules:
        return
    pkg = _types.ModuleType("backend")
    pkg.__path__ = [os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))]
    sys.modules["backend"] = pkg


def test_comments_ru_keys_subset_of_template_variables():
    _ensure_backend_package_importable()
    from backend.templates.build.comments_ru import VAR_COMMENTS
    # r/l/item — имена переменных ВНУТРИ jinja-циклов (for r in receipts,
    # for l in item.menu_lines, item внутри {%tr for item in items %}), не
    # самостоятельные ключи контекста — в TEMPLATE_VARIABLES описаны сами
    # циклы и item.* поля, а не эти служебные однобуквенные имена.
    _LOOP_VAR_EXCEPTIONS = {"r", "l", "item"}
    comment_tags = {"{{" + k + "}}" for k in VAR_COMMENTS if k not in _LOOP_VAR_EXCEPTIONS}
    missing = comment_tags - TEMPLATE_VAR_NAMES
    assert not missing, f"ключи comments_ru.py отсутствуют в TEMPLATE_VARIABLES: {missing}"


# ── (в) склонение ────────────────────────────────────────────────────────────

def test_fio_genitive_female():
    assert _to_gen_fio("Иванова Анна Сергеевна") == "Ивановой Анны Сергеевны"


def test_fio_genitive_male():
    assert _to_gen_fio("Козеев Евгений Викторович") == "Козеева Евгения Викторовича"


def test_fio_genitive_foreign_name_not_truncated():
    # Баг: «Дефассье Лоран, Луи, Клод» → petrovich брал только 3 слова и
    # терял «Клод» + лепил двойную запятую. Иностранное ФИО с запятыми —
    # не склоняем вовсе, возвращаем как есть (без потери слов).
    assert _to_gen_fio("Дефассье Лоран, Луи, Клод") == "Дефассье Лоран, Луи, Клод"


def test_fio_genitive_ogly_suffix():
    # Тюркский патронимик «оглы» не склоняется, первые три слова — склоняются.
    result = _to_gen_fio("Мамедов Эльчин Гусейн оглы")
    assert result.endswith(" оглы")
    # все слова на месте (без потерь)
    assert len(result.split()) == 4


def test_fio_genitive_empty_string():
    assert _to_gen_fio("") == ""


def test_position_genitive_general_director():
    assert _to_gen_phrase("Генеральный директор") == "Генерального директора"


def test_position_genitive_lowercase_director():
    assert _to_gen_phrase("директор") == "директора"


# ── (г) subsidy_agreement_number ← basis_doc_number ──────────────────────────

def test_subsidy_agreement_number_from_basis_doc_number():
    ctx: dict = {}
    add_subsidy_agreement_context(
        ctx, _stub_subsidy(basis_doc_number="091-10-2025-032", agreement_number="СТАРЫЙ-000")
    )
    assert ctx["subsidy_agreement_number"] == "091-10-2025-032"


def test_subsidy_agreement_number_falls_back_to_agreement_number():
    ctx: dict = {}
    add_subsidy_agreement_context(ctx, _stub_subsidy(basis_doc_number=None, agreement_number="СТАРЫЙ-000"))
    assert ctx["subsidy_agreement_number"] == "СТАРЫЙ-000"


def test_subsidy_agreement_number_empty_without_subsidy():
    ctx: dict = {}
    add_subsidy_agreement_context(ctx, None)
    assert ctx["subsidy_agreement_number"] == ""
    assert ctx["subsidy_agreement_date"] == ""


def test_contractor_signatory_position_prefers_explicit_field():
    c = _stub_contractor(
        signatory="Петров Пётр Петрович", signatory_position="Генеральный директор",
    )
    ctx: dict = {}
    add_contractor_signatory_context(ctx, c)
    assert ctx["contractor_signatory_position"] == "Генеральный директор"
    assert ctx["contractor_signatory_position_genitive"] == "Генерального директора"


def test_contractor_signatory_position_falls_back_to_guess():
    # signatory_position не заполнено — угадывание по строке signatory
    # (formatting._signatory_position, по умолчанию «Директор»).
    c = _stub_contractor(signatory="Петров Пётр Петрович", signatory_position=None)
    ctx: dict = {}
    add_contractor_signatory_context(ctx, c)
    assert ctx["contractor_signatory_position"] == "Директор"


# ── (д) должность ЕГРЮЛ заглавными → нормализация регистра (14.10.2026) ──────

def test_position_case_normalize_single_word():
    from app.services.documents.formatting import _normalize_signatory_position
    assert _normalize_signatory_position("ПРЕЗИДЕНТ") == "Президент"


def test_position_case_normalize_two_words():
    from app.services.documents.formatting import _normalize_signatory_position
    assert _normalize_signatory_position("ГЕНЕРАЛЬНЫЙ ДИРЕКТОР") == "Генеральный директор"
    assert _normalize_signatory_position("ПРЕДСЕДАТЕЛЬ СОВЕТА") == "Председатель совета"


def test_position_case_normalize_strips_trailing_colon():
    from app.services.documents.formatting import _normalize_signatory_position
    assert _normalize_signatory_position("ПРЕЗИДЕНТ:") == "Президент"


def test_position_case_normalize_leaves_mixed_case_as_is():
    # должность не целиком заглавными — не трогаем (аббревиатуры ИП/ООО внутри
    # обычной должности не ломаем).
    from app.services.documents.formatting import _normalize_signatory_position
    assert _normalize_signatory_position("Директор") == "Директор"
    assert _normalize_signatory_position("ИП Иванов") == "ИП Иванов"


# ── (е) защитный разбор ФИО при сдвиге «ДОЛЖНОСТЬ: ФИО» (ВСКС id 2693) ───────

def test_customer_signatory_split_fixes_shifted_fio_vsks():
    # Бага: signatory_last_name='ПРЕЗИДЕНТ:' (должность с двоеточием попала
    # в фамилию), signatory_middle_name='Евгений Викторович' (сдвинуто).
    ctr = _stub_contractor(
        signatory="ПРЕЗИДЕНТ: Козеев Евгений Викторович",
        signatory_last_name="ПРЕЗИДЕНТ:", signatory_first_name="Козеев",
        signatory_middle_name="Евгений Викторович", signatory_position="ПРЕЗИДЕНТ",
    )
    org = _stub_org_linked_to(ctr)
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_signatory_name"] == "Козеев Евгений Викторович"
    assert ctx["customer_signatory_name_genitive"] == "Козеева Евгения Викторовича"
    assert ctx["customer_signatory_position"] == "Президент"
    assert ctx["customer_signatory_position_genitive"] == "Президента"


def test_customer_signatory_split_keeps_correct_fio_as_is():
    # Корректная запись (Юрченкова) — защитный разбор НЕ должен её трогать.
    ctr = _stub_contractor(
        signatory="ПРЕДСЕДАТЕЛЬ СОВЕТА: Юрченкова Анастасия Евгеньевна",
        signatory_last_name="Юрченкова", signatory_first_name="Анастасия",
        signatory_middle_name="Евгеньевна", signatory_position="ПРЕДСЕДАТЕЛЬ СОВЕТА",
    )
    org = _stub_org_linked_to(ctr)
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_signatory_name"] == "Юрченкова Анастасия Евгеньевна"
    assert ctx["customer_signatory_position"] == "Председатель совета"


def test_customer_signatory_split_fixes_shifted_two_word_position():
    # Расширение защиты 14.10.2026 (ВСКС id 2693, продолжение): должность из
    # ДВУХ слов разъехалась по last/first — last='ГЕНЕРАЛЬНЫЙ' не совпадает
    # с должностью целиком (старое условие его не ловило), но должность
    # НАЧИНАЕТСЯ с last. 4 контрагента на проде были затронуты.
    ctr = _stub_contractor(
        signatory="ГЕНЕРАЛЬНЫЙ ДИРЕКТОР: Цыганков Сергей Михайлович",
        signatory_last_name="ГЕНЕРАЛЬНЫЙ", signatory_first_name="ДИРЕКТОР:",
        signatory_middle_name="Цыганков Сергей Михайлович",
        signatory_position="ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
    )
    org = _stub_org_linked_to(ctr)
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_signatory_name"] == "Цыганков Сергей Михайлович"
    assert ctx["customer_signatory_position"] == "Генеральный директор"


def test_customer_signatory_split_fixes_shifted_first_has_colon():
    # Двоеточие попало в first, а не в last: last='ПРЕДСЕДАТЕЛЬ' (без ':'),
    # first='СОВЕТА:'.
    ctr = _stub_contractor(
        signatory="ПРЕДСЕДАТЕЛЬ СОВЕТА: Мельников Олег Иванович",
        signatory_last_name="ПРЕДСЕДАТЕЛЬ", signatory_first_name="СОВЕТА:",
        signatory_middle_name="Мельников Олег Иванович",
        signatory_position="ПРЕДСЕДАТЕЛЬ СОВЕТА",
    )
    org = _stub_org_linked_to(ctr)
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_signatory_name"] == "Мельников Олег Иванович"
    assert ctx["customer_signatory_position"] == "Председатель совета"


# ── (ж) новые поля карточки казначейства — владелец, 27.10.2026 ─────────────

def test_contractor_extra_requisite_keys_from_card_fields():
    c = _stub_contractor(
        website="https://romashka.ru", okpo="12345678", okved="94.99",
        registration_date=__import__("datetime").date(2010, 3, 15),
        treasury_account="03234643107010000001",
        single_treasury_account="40102810000000000001",
        personal_account="71234Ц56789",
        signatory_last_name="Юрченкова", signatory_first_name="Анастасия",
        signatory_middle_name="Евгеньевна",
    )
    ctx: dict = {}
    add_contractor_signatory_context(ctx, c)
    assert ctx["contractor_website"] == "https://romashka.ru"
    assert ctx["contractor_okpo"] == "12345678"
    assert ctx["contractor_okved"] == "94.99"
    assert ctx["contractor_registration_date"] == "15.03.2010"
    assert ctx["contractor_treasury_account"] == "03234643107010000001"
    assert ctx["contractor_single_treasury_account"] == "40102810000000000001"
    assert ctx["contractor_personal_account"] == "71234Ц56789"
    assert ctx["contractor_signatory_last_name"] == "Юрченкова"
    assert ctx["contractor_signatory_first_name"] == "Анастасия"
    assert ctx["contractor_signatory_middle_name"] == "Евгеньевна"


def test_customer_extra_requisite_keys_from_card_fields():
    ctr = _stub_contractor(
        website="https://primer.ru", okpo="87654321", okved="85.11",
        registration_date=__import__("datetime").date(2012, 7, 1),
        treasury_account="03234643107010000002",
        single_treasury_account="40102810000000000002",
        signatory_last_name="Артеева", signatory_first_name="Анна",
        signatory_middle_name="Игоревна",
    )
    # customer_signatory_* читаются через org_requisites(org, ctr) — требует
    # Organization, привязанную к контрагенту (как в тестах выше), а не "голый"
    # контрагент без org (см. add_customer_context/org_requisites).
    org = _stub_org_linked_to(ctr, signatory_last_name="Артеева", signatory_first_name="Анна",
                               signatory_middle_name="Игоревна")
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_website"] == "https://primer.ru"
    assert ctx["customer_okpo"] == "87654321"
    assert ctx["customer_okved"] == "85.11"
    assert ctx["customer_registration_date"] == "01.07.2012"
    assert ctx["customer_treasury_account"] == "03234643107010000002"
    assert ctx["customer_single_treasury_account"] == "40102810000000000002"
    assert ctx["customer_signatory_last_name"] == "Артеева"
    assert ctx["customer_signatory_first_name"] == "Анна"
    assert ctx["customer_signatory_middle_name"] == "Игоревна"


def test_customer_signatory_split_initials_in_last_name_kept_as_is():
    # Инициалы попали в фамилию: last='В.Г.', first='Мельничук', middle=''.
    # Без двоеточия в signatory порядок слов надёжно не восстановить —
    # берём строку signatory как есть, не выдумывая перестановку.
    ctr = _stub_contractor(
        signatory="В.Г. Мельничук",
        signatory_last_name="В.Г.", signatory_first_name="Мельничук",
        signatory_middle_name="", signatory_position="Директор",
    )
    org = _stub_org_linked_to(ctr)
    ctx: dict = {}
    add_customer_context(ctx, org, ctr)
    assert ctx["customer_signatory_name"] == "В.Г. Мельничук"
    assert ctx["customer_signatory_position"] == "Директор"
