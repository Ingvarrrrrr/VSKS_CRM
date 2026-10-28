"""Третья форма ФИО («И.О. Фамилия», инициалы впереди) — задача владельца
29.10.2026: у каждого человека в документах должна быть тройка полное ФИО /
«Фамилия И.О.» / «И.О. Фамилия» (initiator, главный бухгалтер, ответственный
исполнитель — по образцу подписанта Заказчика, см. app/services/documents/
case_forms.py и contexts_build.py/contexts_org_people.py).
"""
from app.services.documents.case_forms import CASE_FORM_VARIABLES, CASES, decline_value
from app.services.documents.formatting import _fio_to_initials, _fio_to_initials_prefix
from app.services.documents.morphology import _to_case_initials_prefix
from app.services.documents.template_variables import TEMPLATE_VARIABLES


FIO_MALE = "Титов Ростислав Алексеевич"
FIO_FEMALE = "Юрченкова Анастасия Евгеньевна"


# ── нижний уровень: nominative-функции формата «Фамилия И.О.»/«И.О. Фамилия» ──

def test_fio_to_initials_male():
    assert _fio_to_initials(FIO_MALE) == "Титов Р.А."
    assert _fio_to_initials_prefix(FIO_MALE) == "Р.А. Титов"


def test_fio_to_initials_female():
    assert _fio_to_initials(FIO_FEMALE) == "Юрченкова А.Е."
    assert _fio_to_initials_prefix(FIO_FEMALE) == "А.Е. Юрченкова"


# ── склонение «И.О. Фамилия» — новый вид 'initials_first' ──────────────────

def test_initials_first_declension_male():
    value = _fio_to_initials_prefix(FIO_MALE)  # "Р.А. Титов"
    assert value == "Р.А. Титов"
    assert _to_case_initials_prefix(value, 'GENITIVE') == "Р.А. Титова"
    assert _to_case_initials_prefix(value, 'DATIVE') == "Р.А. Титову"
    assert _to_case_initials_prefix(value, 'INSTRUMENTAL') == "Р.А. Титовым"


def test_initials_first_declension_female():
    value = _fio_to_initials_prefix(FIO_FEMALE)  # "А.Е. Юрченкова"
    assert value == "А.Е. Юрченкова"
    assert _to_case_initials_prefix(value, 'GENITIVE') == "А.Е. Юрченковой"
    assert _to_case_initials_prefix(value, 'DATIVE') == "А.Е. Юрченковой"
    assert _to_case_initials_prefix(value, 'INSTRUMENTAL') == "А.Е. Юрченковой"


def test_initials_first_declension_empty_and_nontypical():
    assert _to_case_initials_prefix("", 'GENITIVE') == ""
    # Нетиповой формат (не 2 слова, или первое не похоже на инициалы) — без изменений.
    assert _to_case_initials_prefix("Иванов Иван Иванович", 'GENITIVE') == "Иванов Иван Иванович"


# ── decline_value('initials_first', ...) через реестр case_forms ───────────

def test_decline_value_initials_first_all_cases():
    value = "Р.А. Титов"
    assert decline_value('initials_first', value, 'gent', []) == "Р.А. Титова"
    assert decline_value('initials_first', value, 'datv', []) == "Р.А. Титову"
    assert decline_value('initials_first', value, 'accs', []) == "Р.А. Титова"
    assert decline_value('initials_first', value, 'ablt', []) == "Р.А. Титовым"
    assert decline_value('initials_first', value, 'loct', []) == "Р.А. Титове"


# ── реестр CASE_FORM_VARIABLES содержит новые переменные ───────────────────

def test_registry_has_new_person_variables():
    assert CASE_FORM_VARIABLES["initiator_initials"][0] == "fio_initials"
    assert CASE_FORM_VARIABLES["initiator_name_initials"][0] == "initials_first"
    assert CASE_FORM_VARIABLES["chief_accountant_name_initials"][0] == "initials_first"
    assert CASE_FORM_VARIABLES["responsible_person_name_initials"][0] == "initials_first"


def test_registry_examples_declined_as_expected():
    base = CASE_FORM_VARIABLES["initiator_name_initials"]
    assert base[1] == "Р.А. Титов"
    assert decline_value(base[0], base[1], 'gent', []) == "Р.А. Титова"


# ── справочник TEMPLATE_VARIABLES: базовые переменные и падежи присутствуют ─

def test_template_variables_has_base_entries_for_new_vars():
    names = {v for (v, _d, _et, _er) in TEMPLATE_VARIABLES if v}
    for var in (
        "initiator_initials", "initiator_name_initials",
        "chief_accountant_name_initials",
        "responsible_person_full", "responsible_person_name_initials",
    ):
        assert "{{" + var + "}}" in names, f"{var} отсутствует в справочнике"


def test_template_variables_has_case_rows_for_new_vars():
    names = {v for (v, _d, _et, _er) in TEMPLATE_VARIABLES if v}
    for base_var in (
        "initiator_initials", "initiator_name_initials",
        "chief_accountant_name_initials", "responsible_person_name_initials",
    ):
        for _short, suffix, *_rest in CASES:
            tag = "{{" + f"{base_var}_{suffix}" + "}}"
            assert tag in names, f"{tag} отсутствует в справочнике"
