"""Все 5 косвенных падежей для каждой склоняемой переменной документа —
задача владельца 29.10.2026 (см. app/services/documents/case_forms.py).

Проверяем:
  (а) на примерах владельца — все 5 падежей для организации/ФИО/
      «Фамилия И.О.»/должности;
  (б) ПРАВИЛО №6 — там, где старые падежные переменные сопоставимы с новыми
      (та же величина, тот же расчёт), значения совпадают;
  (в) каждая переменная реестра × 5 падежей присутствует в справочнике
      TEMPLATE_VARIABLES (кроме случаев, где старое имя уже совпало с
      новым именем — тогда новая строка не дублируется, старая уже там).
"""
from app.services.documents.case_forms import CASE_FORM_VARIABLES, CASES, decline_value, add_all_case_forms
from app.services.documents.morphology import _to_gen_fio, _to_dat_fio, _to_gen_fio_initials, _to_dat_fio_initials
from app.services.documents.contexts_org_people import _to_ablt_org_name
from app.services.documents.template_variables import TEMPLATE_VARIABLES


ORG_NAME = (
    'ЗАПОРОЖСКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ '
    'ОРГАНИЗАЦИИ "ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ"'
)
FIO_FULL = "Юрченкова Анастасия Евгеньевна"
FIO_INITIALS = "Юрченкова А.Е."
POSITION = "Председатель совета"


# ── (а) примеры владельца, все 5 падежей ────────────────────────────────────

def test_org_name_all_cases():
    assert decline_value('org_name', ORG_NAME, 'gent', []) == (
        'Запорожского регионального отделения всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )
    assert decline_value('org_name', ORG_NAME, 'datv', []) == (
        'Запорожскому региональному отделению всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )
    assert decline_value('org_name', ORG_NAME, 'ablt', []) == (
        'Запорожским региональным отделением всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )
    assert decline_value('org_name', ORG_NAME, 'loct', []) == (
        'Запорожском региональном отделении всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )
    # Винительный «отделения» (среднего рода, неодуш.) = именительному —
    # нормальная русская грамматика, не баг.
    assert decline_value('org_name', ORG_NAME, 'accs', []) == (
        'Запорожское региональное отделение всероссийской общественной '
        'молодежной организации «Всероссийский студенческий корпус спасателей»'
    )


def test_fio_all_cases():
    assert decline_value('fio', FIO_FULL, 'gent', []) == "Юрченковой Анастасии Евгеньевны"
    assert decline_value('fio', FIO_FULL, 'datv', []) == "Юрченковой Анастасии Евгеньевне"
    assert decline_value('fio', FIO_FULL, 'accs', []) == "Юрченкову Анастасию Евгеньевну"
    assert decline_value('fio', FIO_FULL, 'ablt', []) == "Юрченковой Анастасией Евгеньевной"
    assert decline_value('fio', FIO_FULL, 'loct', []) == "Юрченковой Анастасии Евгеньевне"


def test_fio_initials_all_cases():
    assert decline_value('fio_initials', FIO_INITIALS, 'gent', []) == "Юрченковой А.Е."
    assert decline_value('fio_initials', FIO_INITIALS, 'datv', []) == "Юрченковой А.Е."
    assert decline_value('fio_initials', FIO_INITIALS, 'accs', []) == "Юрченкову А.Е."
    assert decline_value('fio_initials', FIO_INITIALS, 'ablt', []) == "Юрченковой А.Е."
    assert decline_value('fio_initials', FIO_INITIALS, 'loct', []) == "Юрченковой А.Е."


def test_position_all_cases():
    assert decline_value('position', POSITION, 'gent', []) == "Председателя совета"
    assert decline_value('position', POSITION, 'datv', []) == "Председателю совета"
    assert decline_value('position', POSITION, 'accs', []) == "Председателя совета"
    assert decline_value('position', POSITION, 'ablt', []) == "Председателем совета"
    assert decline_value('position', POSITION, 'loct', []) == "Председателе совета"


# ── add_all_case_forms: не перетирает существующие ключи, добавляет недостающие ──

def test_add_all_case_forms_fills_missing_keeps_existing():
    ctx = {
        "customer_full_name": ORG_NAME,
        # Старое значение той же переменной, что new-naming тоже бы дал —
        # add_all_case_forms НЕ должна его пересчитывать/перетирать.
        "customer_full_name_genitive": "УЖЕ-ЕСТЬ-НЕ-ТРОГАТЬ",
    }
    add_all_case_forms(ctx, [])
    assert ctx["customer_full_name_genitive"] == "УЖЕ-ЕСТЬ-НЕ-ТРОГАТЬ"
    assert ctx["customer_full_name_dative"] == decline_value('org_name', ORG_NAME, 'datv', [])
    assert ctx["customer_full_name_accusative"] == decline_value('org_name', ORG_NAME, 'accs', [])
    assert ctx["customer_full_name_instrumental"] == decline_value('org_name', ORG_NAME, 'ablt', [])
    assert ctx["customer_full_name_prepositional"] == decline_value('org_name', ORG_NAME, 'loct', [])


def test_add_all_case_forms_empty_value_gives_empty_cases():
    ctx = {"responsible_person_full": ""}
    add_all_case_forms(ctx, [])
    for _short, suffix, *_ in CASES:
        assert ctx[f"responsible_person_full_{suffix}"] == ""


def test_add_all_case_forms_skips_absent_base_var():
    ctx = {}
    add_all_case_forms(ctx, [])
    assert "customer_full_name_genitive" not in ctx


# ── (б) ПРАВИЛО №6: старые падежные переменные == новым, где сопоставимо ────

def test_rule6_fio_matches_old_gen_dat_helpers():
    assert decline_value('fio', FIO_FULL, 'gent', []) == _to_gen_fio(FIO_FULL)
    assert decline_value('fio', FIO_FULL, 'datv', []) == _to_dat_fio(FIO_FULL)


def test_rule6_fio_initials_matches_old_gen_dat_helpers():
    assert decline_value('fio_initials', FIO_INITIALS, 'gent', []) == _to_gen_fio_initials(FIO_INITIALS)
    assert decline_value('fio_initials', FIO_INITIALS, 'datv', []) == _to_dat_fio_initials(FIO_INITIALS)


def test_rule6_org_name_instrumental_matches_old_subsidy_grantor_helper():
    # subsidy_grantor_name_instrumental (contexts_subsidy_grantor.py) уже
    # называется ровно как новая переменная — то же вычисление.
    grantor = "Федеральное агентство по делам молодёжи"
    assert decline_value('org_name', grantor, 'ablt', []) == _to_ablt_org_name(grantor)


def test_rule6_responsible_person_full_genitive_same_value_as_responsible_name_gen():
    # responsible_name_gen (contexts_org_people.responsible_case_context) и
    # новая responsible_person_full_genitive — разные имена, тот же вход
    # (полное ФИО) и тот же алгоритм (_to_gen_fio) — должны совпасть.
    assert decline_value('fio', FIO_FULL, 'gent', []) == _to_gen_fio(FIO_FULL)


# ── (в) реестр × 5 падежей присутствует в справочнике ───────────────────────

def test_every_registry_variable_case_in_template_variables():
    names = {v for (v, _d, _et, _er) in TEMPLATE_VARIABLES if v}
    missing = []
    for base_var, (_kind, _example, _descr) in CASE_FORM_VARIABLES.items():
        for _short, suffix, *_rest in CASES:
            tag = "{{" + f"{base_var}_{suffix}" + "}}"
            if tag not in names:
                missing.append(tag)
    assert not missing, f"переменные падежей отсутствуют в справочнике: {missing}"
