"""Все 5 косвенных падежей для КАЖДОЙ склоняемой переменной документа —
задача владельца (29.10.2026): раньше у каждой переменной склонялся только
один-два падежа «по одной» (где родительный, где дательный, творительный
только у `subsidy_grantor_name_instrumental`) — теперь единый реестр и
единый проход по контексту.

ПРАВИЛО №6: один реестр (`CASE_FORM_VARIABLES`), один вызов склонения на
вид переменной (`decline_value`) — используется и генерацией обычных
документов (generate.py), и пакетом Фабриканта/Росэлторга
(fabrikant_package.py), второй копии не заводим.

Новые ключи — `{базовая_переменная}_{genitive,dative,accusative,
instrumental,prepositional}`. СТАРЫЕ переменные с другими суффиками
(`responsible_name_gen`, `customer_full_name_genitive`,
`subsidy_grantor_name_instrumental` и т.д.) — не трогаем, они считаются
своим кодом, как и раньше; там, где старое имя СОВПАДАЕТ с новым
(`customer_full_name_genitive`, `subsidy_grantor_name_instrumental`),
`add_all_case_forms` не перезатирает уже положенное значение (см. её
докстринг) — это тот же расчёт, значения совпадают.
"""
from typing import Optional, Sequence

from app.services.documents.morphology import (
    _to_case_position, _to_case_fio, _to_case_fio_initials, _to_case_initials_prefix,
)
from app.services.documents.org_name_case import doc_case_org_name_case


# (короткий код падежа для _to_case_position/doc_case_org_name_case,
#  суффикс новой переменной, падеж по-русски для описания, вопрос падежа,
#  имя атрибута petrovich.enums.Case)
CASES = [
    ('gent', 'genitive', 'родительном', 'кого? чего?', 'GENITIVE'),
    ('datv', 'dative', 'дательном', 'кому? чему?', 'DATIVE'),
    ('accs', 'accusative', 'винительном', 'кого? что?', 'ACCUSATIVE'),
    ('ablt', 'instrumental', 'творительном', 'кем? чем?', 'INSTRUMENTAL'),
    ('loct', 'prepositional', 'предложном', 'о ком? о чём?', 'PREPOSITIONAL'),
]

# base_var -> (kind, пример значения в именительном падеже, человекочитаемое
# описание базовой переменной — для справочника TEMPLATE_VARIABLES).
# kind: 'org_name' | 'fio' | 'fio_initials' | 'initials_first' | 'position'.
CASE_FORM_VARIABLES: dict[str, tuple[str, str, str]] = {
    # ── Организации ──
    "customer_full_name": (
        "org_name", "Автономная некоммерческая организация «Пример»",
        "Заказчик: полное наименование",
    ),
    "contractor_full_name": (
        "org_name", "Общество с ограниченной ответственностью «Ромашка»",
        "Подрядчик (исполнитель): полное наименование",
    ),
    "subsidy_grantor_name": (
        "org_name", "Федеральное агентство по делам молодёжи",
        "Грантодатель субсидии",
    ),
    "subsidy_ministry_name": (
        "org_name", "Министерство труда и социальной защиты РФ",
        "Министерство/ведомство субсидии",
    ),
    # ── ФИО (полное) ──
    "customer_signatory_name": (
        "fio", "Орлов Андрей Викторович",
        "Заказчик, подписант: ФИО",
    ),
    "contractor_signatory_name": (
        "fio", "Сидоров Пётр Павлович",
        "Подрядчик (исполнитель), подписант: ФИО",
    ),
    "chief_accountant_name": (
        "fio", "Петрова Ирина Сергеевна",
        "Заказчик: ФИО главного бухгалтера",
    ),
    "responsible_person_full": (
        "fio", "Иванов Иван Иванович",
        "ФИО ответственного исполнителя закупки (полная форма)",
    ),
    "initiator_name": (
        "fio", "Иванов Иван Иванович",
        "ФИО инициатора (служебная записка)",
    ),
    # ── ФИО сокращённое «Фамилия И.О.» ──
    "customer_signatory_initials": (
        "fio_initials", "Орлов А.В.",
        "Заказчик, подписант: фамилия + инициалы",
    ),
    "contractor_signatory_initials": (
        "fio_initials", "Сидоров П.П.",
        "Подрядчик (исполнитель), подписант: фамилия + инициалы",
    ),
    "chief_accountant_initials": (
        "fio_initials", "Петрова И.С.",
        "Заказчик: фамилия + инициалы главного бухгалтера",
    ),
    "responsible_person": (
        "fio_initials", "Иванов И.И.",
        "ФИО ответственного исполнителя закупки (сокращённая форма «Фамилия И.О.»)",
    ),
    "initiator_initials": (
        "fio_initials", "Титов Р.А.",
        "ФИО инициатора (служебная записка): фамилия + инициалы",
    ),
    # ── ФИО сокращённое «И.О. Фамилия» (инициалы впереди, для строки подписи) ──
    "initiator_name_initials": (
        "initials_first", "Р.А. Титов",
        "ФИО инициатора (служебная записка): инициалы впереди фамилии",
    ),
    "chief_accountant_name_initials": (
        "initials_first", "И.С. Петрова",
        "Заказчик: инициалы впереди фамилии главного бухгалтера",
    ),
    "responsible_person_name_initials": (
        "initials_first", "И.И. Иванов",
        "ФИО ответственного исполнителя закупки: инициалы впереди фамилии",
    ),
    # ── Должности/подразделения/предмет (разбор головной группы) ──
    "customer_signatory_position": (
        "position", "Президент",
        "Заказчик, подписант: должность",
    ),
    "contractor_signatory_position": (
        "position", "Директор",
        "Подрядчик (исполнитель), подписант: должность",
    ),
    "initiator_role": (
        "position", "начальник отдела",
        "Должность инициатора (служебная записка)",
    ),
    "initiator_dept": (
        "position", "Отдел спасательных операций",
        "Отдел инициатора",
    ),
    "responsible_position": (
        "position", "заместитель руководителя",
        "Должность ответственного исполнителя закупки",
    ),
    "service_name": (
        "position", "Оказание услуг связи",
        "Предмет закупки (синоним subject)",
    ),
}


def decline_value(kind: str, value: str, case: str, org_exceptions: Sequence[str]) -> str:
    """Склонить *value* в падеж *case* (короткий код — 'gent'/'datv'/
    'accs'/'ablt'/'loct') по правилу вида *kind*.

    ПРАВИЛО №6 — единственная точка выбора алгоритма по виду переменной:
      - 'org_name'      → `doc_case_org_name_case` (org_name_case.py, сама
                           нормализует регистр ЕГРЮЛ-капса перед склонением);
      - 'fio'            → `_to_case_fio` (petrovich, полное «Фамилия Имя
                           Отчество»);
      - 'fio_initials'   → `_to_case_fio_initials` (petrovich на фамилии,
                           инициалы не трогаются);
      - 'initials_first' → `_to_case_initials_prefix` (та же фамилия через
                           petrovich, инициалы впереди — «И.О. Фамилия»,
                           задача 29.10.2026: третья форма ФИО);
      - 'position'       → `_to_case_position` (pymorphy3, разбор ГОЛОВНОЙ
                           группы — должности/подразделения/предмета).
    Пустое значение → пустая строка (не выдумываем падеж из ничего, тот же
    принцип, что у всех вызываемых функций ниже).
    """
    if not value:
        return ""
    petro_case_by_short = {c[0]: c[4] for c in CASES}
    if kind == "org_name":
        return doc_case_org_name_case(value, org_exceptions, case)
    if kind == "fio":
        return _to_case_fio(value, petro_case_by_short[case])
    if kind == "fio_initials":
        return _to_case_fio_initials(value, petro_case_by_short[case])
    if kind == "initials_first":
        return _to_case_initials_prefix(value, petro_case_by_short[case])
    if kind == "position":
        return _to_case_position(value, case)
    raise ValueError(f"Неизвестный вид склоняемой переменной: {kind!r}")


def add_all_case_forms(context: dict, org_exceptions: Optional[Sequence[str]] = None) -> None:
    """Для каждой базовой переменной реестра, если она ЕСТЬ в `context`
    (положена одной из add_*_context выше по конвейеру), дописывает все 5
    падежных ключей `{base}_{genitive,dative,accusative,instrumental,
    prepositional}` — КРОМЕ тех, что уже существуют в `context` (старые
    переменные с тем же именем — например, `customer_full_name_genitive`,
    `subsidy_grantor_name_instrumental` — НЕ перетираются; это тот же
    расчёт, их значение не должно измениться при повторном вызове).

    Вызывать ОДИН раз, в самом конце сборки контекста документа (после всех
    add_*_context — значения переменных на момент вызова финальные, включая
    правки типа `_strip_redundant_dept_word` над `initiator_dept`).

    Пустая базовая переменная (не найдена/пустая строка) → все 5 падежных
    ключей — пустая строка (а не отсутствие ключа — шаблон может их
    использовать безусловно).
    """
    org_exceptions = list(org_exceptions or [])
    for base_var, (kind, _example, _description) in CASE_FORM_VARIABLES.items():
        if base_var not in context:
            continue
        value = context.get(base_var) or ""
        for short_case, suffix, _case_ru, _question, _petro_case in CASES:
            key = f"{base_var}_{suffix}"
            if key in context:
                continue
            context[key] = decline_value(kind, value, short_case, org_exceptions) if value else ""
