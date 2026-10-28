"""Баг (прод, субсидия 111 «ЗО_актуальная», 28.10.2026): строка приказа
«Ответственным лицом за проведение закупки назначить
{{responsible_position_gen}}– {{responsible_name_gen}}» печатала
«– Титов Р.А.» — должность пустая, ФИО в именительном (не склонялось).

Причины и правки — см. docstring'и:
  - app.services.documents.contexts_org_people.responsible_case_context
    (вход теперь ПОЛНОЕ ФИО, а не уже сокращённое «Фамилия И.О.»)
  - app.services.documents.contexts_org_people.resolve_responsible_position
    (должность — единственный резолвер app.services.user_position.
    resolve_user_position, не Purchase.responsible_position — такого поля
    в модели нет, старое `hasattr` было всегда False)
  - app.services.documents.morphology._to_case_fio_initials (bare
    «Фамилия И.О.» без восстановления полного ФИО — склоняем хотя бы
    фамилию, best-effort)

Этот файл — чистые юнит-тесты (без БД) на падежи/инициалы +
интеграционный тест на БД для resolve_responsible_position (тот же
резолвер должности, что в generate.py/fabrikant_package.py).
"""
import pytest

from app.services.documents.contexts_org_people import (
    responsible_case_context,
    resolve_responsible_position,
)
from app.services.documents.morphology import (
    _to_gen_fio,
    _to_dat_fio,
    _to_gen_fio_initials,
    _to_dat_fio_initials,
    _to_gen_phrase,
)


def test_responsible_case_context_full_fio_declines_name_and_initials():
    """Полное ФИО на входе (а не уже сокращённое) — responsible_name_gen/_dat
    дают ПОЛНУЮ склонённую форму (см. template_variables.py — описание
    «ФИО… в родительном падеже», как у customer_signatory_name_genitive),
    а responsible_initials_gen/_dat — сокращённую «Фамилия И.О.» в падеже,
    это и есть то, что нужно печатать в приказе вместо {{responsible_name_gen}}."""
    ctx = responsible_case_context("Титов Ростислав Алексеевич")
    assert ctx["responsible_name_gen"] == "Титова Ростислава Алексеевича"
    assert ctx["responsible_name_dat"] == "Титову Ростиславу Алексеевичу"
    assert ctx["responsible_initials_gen"] == "Титова Р.А."
    assert ctx["responsible_initials_dat"] == "Титову Р.А."


def test_responsible_case_context_already_abbreviated_input_regression():
    """Воспроизводит прежний баг: если бы на вход (как раньше) пришла уже
    сокращённая строка «Титов Р.А.», `_to_gen_fio`/`_to_dat_fio` (полное ФИО)
    не распознают 2 слова как классическое ФИО и возвращают строку без
    изменений — отсюда и ненаклонённое «Титов Р.А.» в приказе. После фикса
    это входное значение в responsible_case_context больше не передаётся
    (передаётся полное ФИО), но сам факт поведения `_to_gen_fio` на bare
    инициалах фиксируем явно, чтобы не полагаться на него молча."""
    assert _to_gen_fio("Титов Р.А.") == "Титов Р.А."


def test_bare_surname_initials_declines_surname_best_effort():
    """Новая ветка морфологии (28.10.2026): если полного ФИО нет и пришла
    уже сокращённая «Фамилия И.О.» строка, хотя бы фамилия склоняется —
    пол угадывается по окончанию (мужской по умолчанию)."""
    assert _to_gen_fio_initials("Титов Р.А.") == "Титова Р.А."
    assert _to_dat_fio_initials("Титов Р.А.") == "Титову Р.А."
    # Женская фамилия угадывается по типичному окончанию -ова.
    assert _to_gen_fio_initials("Иванова А.С.") == "Ивановой А.С."


def test_position_genitive_phrase_lowercase():
    """{{responsible_position_gen}} — через тот же единственный разбор
    головной группы _to_gen_phrase, что и у initiator_position_gen —
    регистр должности сохраняется как в должности (с большой буквы), сама
    фраза используется в шаблоне уже после тире, поэтому строчные буквы
    ожидает сам шаблон/справочник (см. template_variables.py пример
    «заместителя руководителя»)."""
    assert _to_gen_phrase("заместитель руководителя") == "заместителя руководителя"


@pytest.mark.asyncio
async def test_resolve_responsible_position_from_string_name_exact_match_in_staff(db_session, test_org, test_user):
    """responsible_person_name (строка ФИО) ищется среди штата организации
    по точному совпадению — найден единственный → должность через
    resolve_user_position (здесь — legacy users.position, у test_user нет
    UserOrganization-членства)."""
    test_user.full_name = "Титов Ростислав Алексеевич"
    test_user.position = "Заместитель руководителя"
    db_session.add(test_user)
    await db_session.commit()

    position = await resolve_responsible_position(
        db_session, test_org.id,
        responsible_person_name="Титов Ростислав Алексеевич",
    )
    assert position == "Заместитель руководителя"


@pytest.mark.asyncio
async def test_resolve_responsible_position_assigned_user_object_priority(db_session, test_org, test_user):
    """assigned_user (уже объект User, не строка) — должность берётся сразу,
    без поиска по ФИО."""
    test_user.position = "Главный специалист"
    db_session.add(test_user)
    await db_session.commit()

    position = await resolve_responsible_position(
        db_session, test_org.id,
        assigned_user=test_user,
        responsible_person_name="Кто-то другой, кого нет в штате",
    )
    assert position == "Главный специалист"


@pytest.mark.asyncio
async def test_resolve_responsible_position_no_match_returns_empty(db_session, test_org):
    """Ни одного совпадения по ФИО в штате — должность пустая, не гадаем."""
    position = await resolve_responsible_position(
        db_session, test_org.id,
        responsible_person_name="Несуществующий Сотрудник Иванович",
    )
    assert position == ""


@pytest.mark.asyncio
async def test_resolve_responsible_position_no_org_id_returns_empty(db_session, test_user):
    """org_id не определён (например, у субсидии нет организации) —
    должность не резолвится вовсе (нет штата, по которому искать)."""
    position = await resolve_responsible_position(
        db_session, None,
        assigned_user=test_user,
    )
    assert position == ""
