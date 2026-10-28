"""Переменные документа про организацию-заказчика и её сотрудников, не
поместившиеся в contexts_extra.py (ПРАВИЛО №5 — файл и так ~380 строк):
падежи названия организации-заказчика, главный бухгалтер заказчика
(требует асинхронного запроса к БД — единственное место здесь так делает),
падежи/сокращения ФИО «Ответственного исполнителя» (ПРАВИЛО №6 — раньше
`responsible_name_gen` считался дважды, в contexts_extra.py и отдельной
строкой в fabrikant_package.py).

Владелец, 20.10.2026 (задача «переменные шаблонов документов, п.2-4»).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional

from app.models.user import User
from app.models.user_organization import UserOrganization
from app.services.user_position import resolve_user_position, bulk_load_memberships
from app.services.service_note_initiators import org_staff_user_ids
from app.services.documents.morphology import (
    _to_case_position, _to_gen_fio, _to_dat_fio, _to_gen_fio_initials, _to_dat_fio_initials,
)
from app.services.documents.formatting import _fio_to_initials

CHIEF_ACCOUNTANT_POSITION = "главный бухгалтер"


def _to_case_org_name(name: str, case: str) -> str:
    """Склонить название организации (полное или краткое) в падеж *case*
    ('gent'/'datv') — тонкая обёртка над `_to_case_position` (тот же разбор
    головной группы: первые прилагательные + одно существительное, хвост с
    аббревиатурами/кавычками не трогается, ПРАВИЛО №6 — второй алгоритм
    разбора не заводим).

    Единственное отличие от должности: если фраза ЦЕЛИКОМ начинается с
    кавычки («Форма «Х»» или уже «Краткое «Х»») — название не склоняем
    вообще, возвращаем как есть. `_to_case_position` и так не ломает
    кавычки внутри/в конце фразы (кавычка — не буква, abbreviation-проверка
    их игнорирует), но имя, начинающееся с кавычки сразу, не содержит
    опорного слова для разбора и могло бы попасть под эвристику без
    pymorphy3 — безопаснее не трогать.

    Примеры (см. тест test_doc_vars_city_org_cases.py):
        gent: «Автономная некоммерческая организация «ВСКС»»
            → «Автономной некоммерческой организации «ВСКС»»
        gent: «Региональное отделение Общероссийской общественной
               организации «Х»»
            → «Регионального отделения Общероссийской общественной
               организации «Х»» (хвост после опорного слова не склоняется)
        gent: «АНО «ВСКС»» → «АНО «ВСКС»» (целиком аббревиатура — без изменений)
    """
    if not name or not name.strip():
        return name or ""
    stripped = name.strip()
    if stripped[0] in ('«', '"', '“', '‘'):
        return name
    return _to_case_position(name, case)


def _to_gen_org_name(name: str) -> str:
    """Название организации в родительном падеже — см. `_to_case_org_name`."""
    return _to_case_org_name(name, 'gent')


def _to_dat_org_name(name: str) -> str:
    """Название организации в дательном падеже — см. `_to_case_org_name`."""
    return _to_case_org_name(name, 'datv')


def _to_ablt_org_name(name: str) -> str:
    """Название организации в творительном падеже — см. `_to_case_org_name`
    (владелец, 22.10.2026: {{subsidy_grantor_name_instrumental}})."""
    return _to_case_org_name(name, 'ablt')


def responsible_case_context(resolved_responsible_full: str) -> dict:
    """Падежи/сокращения ФИО «Ответственного исполнителя» — единственный
    расчёт (ПРАВИЛО №6). До этой функции `responsible_name_gen` считался
    дважды: в `add_genitive_forms` (contexts_extra.py, путь generate.py) и
    отдельной строкой в fabrikant_package.py (~516) с тем же вызовом
    `_to_gen_fio`. Дательный падеж и сокращённые инициалы в родительном/
    дательном — новые переменные (владелец, 20.10.2026), добавлены сюда же,
    чтобы оба пути их получили одним вызовом.

    Владелец (28.10.2026, баг «Титов Р.А.» не склонялось): вход — ПОЛНОЕ
    ФИО (`resolved_responsible_full`, то же значение, что кладётся в
    `responsible_person_full`), а не уже сокращённая «Фамилия И.О.». До
    этой правки оба вызывающих места передавали сюда уже сокращённую
    строку (`resolved_responsible`, после `_format_initials`) — `_to_gen_fio`
    на двух словах («Титов Р.А.») не распознаёт классическое ФИО (нужно 3
    слова с отчеством) и возвращает строку без изменений, поэтому падежи
    не появлялись. `_to_gen_fio`/`_to_dat_fio` на полном ФИО — полное ФИО
    в падеже («Титова Ростислава Алексеевича»); `_to_gen_fio_initials`/
    `_to_dat_fio_initials` — «Фамилия И.О.» уже в падеже («Титова Р.А.»),
    это и есть то сокращение, что печатают приказы (см. справочник
    template_variables.py — описание `responsible_name_gen` говорит «ФИО…
    в родительном падеже», это полная форма; для сокращённой — отдельная
    переменная `responsible_initials_gen`, шаблоны должны использовать её,
    если нужна короткая форма).

    Если полного ФИО нет (пустая строка) — поведение не изменилось: все
    четыре `_to_*` на пустой/нетиповой строке возвращают её без изменений.
    """
    return {
        "responsible_name_gen": _to_gen_fio(resolved_responsible_full),
        "responsible_name_dat": _to_dat_fio(resolved_responsible_full),
        "responsible_initials_gen": _to_gen_fio_initials(resolved_responsible_full),
        "responsible_initials_dat": _to_dat_fio_initials(resolved_responsible_full),
    }


async def _find_staff_user_by_full_name(db: AsyncSession, org_id: Optional[int], full_name: Optional[str]):
    """Находит пользователя среди «штата» организации `org_id`
    (app.services.service_note_initiators.org_staff_user_ids — единственная
    формула штата, ПРАВИЛО №6) по ТОЧНОМУ совпадению `full_name` (без
    fuzzy-матчинга, см. feedback_dedup_exact_only). Несколько совпадений или
    ни одного — None (должность в этом случае остаётся пустой, не гадаем)."""
    name = (full_name or "").strip()
    if not name or not org_id:
        return None
    staff_ids = await org_staff_user_ids(db, org_id)
    if not staff_ids:
        return None
    rows = (
        await db.execute(select(User).where(User.id.in_(staff_ids), User.full_name == name))
    ).scalars().all()
    return rows[0] if len(rows) == 1 else None


async def resolve_responsible_position(
    db: AsyncSession,
    org_id: Optional[int],
    *,
    explicit_name: Optional[str] = None,
    assigned_user=None,
    responsible_person_name: Optional[str] = None,
    fallback_user=None,
) -> str:
    """Должность «Ответственного исполнителя» закупки для
    `{{responsible_position}}`/`{{responsible_position_gen}}` — единственный
    расчёт (ПРАВИЛО №6), вызывается и из generate.py (путь обычных
    документов, через `add_genitive_forms`), и из fabrikant_package.py —
    второй копии не заводим.

    Приоритет определения ПОЛЬЗОВАТЕЛЯ — тот же, что в
    `stages_relations.resolve_responsible_person` (явно выбранное имя →
    `p.assigned_user` → `p.responsible_person` → автор служебки), но здесь
    принимает уже разложенные кандидаты, а не сам объект Purchase — чтобы не
    трогать `p.service_note_author`/`p.assigned_user` без уверенности, что
    они eager-loaded (иначе async-лениволадка упадёт).

    Строковые кандидаты (`explicit_name`/`responsible_person_name`) не
    являются объектом User — ищутся среди штата `org_id` ТОЛЬКО по точному
    совпадению ФИО (`_find_staff_user_by_full_name`); несколько совпадений
    или ни одного — должность остаётся пустой.

    Должность самого найденного пользователя берётся ЕДИНСТВЕННЫМ
    резолвером `app.services.user_position.resolve_user_position` (не
    `users.position`/`user_organizations.position` напрямую).
    """
    if not org_id:
        return ""

    user = None
    if explicit_name:
        user = await _find_staff_user_by_full_name(db, org_id, explicit_name)
    elif assigned_user is not None:
        user = assigned_user
    elif responsible_person_name:
        user = await _find_staff_user_by_full_name(db, org_id, responsible_person_name)
    elif fallback_user is not None:
        user = fallback_user

    if not user:
        return ""

    memberships = await bulk_load_memberships(db, {user.id})
    return resolve_user_position(user, org_id=org_id, memberships=memberships.get(user.id)) or ""


_CHIEF_ACCOUNTANT_KEYS = (
    "chief_accountant_name", "chief_accountant_name_genitive", "chief_accountant_name_dative",
    "chief_accountant_initials", "chief_accountant_initials_genitive", "chief_accountant_initials_dative",
)


async def add_chief_accountant_context(context: dict, db: AsyncSession, customer_org) -> None:
    """Главный бухгалтер организации-заказчика — в модели нет отдельного
    поля-подписанта, ищем среди сотрудников `customer_org` того, у кого
    действующая должность (через единственный резолвер
    `app.services.user_position.resolve_user_position`, ПРАВИЛО №6 — не
    второй разбор user_organizations.position/users.position) точно равна
    «Главный бухгалтер» (без учёта регистра, после strip). Несколько
    совпадений — берём первого по id пользователя. Не нашли — все ключи
    пустые строки, документ всё равно формируется.

    Кандидаты — те же два источника, что в `resolve_user_position`: все
    пользователи с членством (`UserOrganization.org_id == customer_org.id`)
    и legacy-сотрудники с `users.org_id == customer_org.id` напрямую
    (нужны, если у человека вообще нет ни одной строки `UserOrganization` —
    тогда резолвер падает на `users.position`). Флага активности у
    User/UserOrganization в модели нет — фильтр по нему не применяется.
    """
    for key in _CHIEF_ACCOUNTANT_KEYS:
        context[key] = ""
    org_id = getattr(customer_org, "id", None)
    if not org_id:
        return

    uo_rows = (
        await db.execute(
            select(UserOrganization).where(UserOrganization.org_id == org_id)
        )
    ).scalars().all()
    legacy_users = (
        await db.execute(select(User).where(User.org_id == org_id))
    ).scalars().all()

    candidate_ids = {m.user_id for m in uo_rows} | {u.id for u in legacy_users}
    if not candidate_ids:
        return

    memberships_by_user = await bulk_load_memberships(db, candidate_ids)
    users_by_id = {u.id: u for u in legacy_users}
    missing_ids = [uid for uid in candidate_ids if uid not in users_by_id]
    if missing_ids:
        more_users = (
            await db.execute(select(User).where(User.id.in_(missing_ids)))
        ).scalars().all()
        for u in more_users:
            users_by_id[u.id] = u

    found = None
    for uid in sorted(candidate_ids):
        user = users_by_id.get(uid)
        if not user:
            continue
        position = resolve_user_position(user, org_id=org_id, memberships=memberships_by_user.get(uid))
        if position and position.strip().lower() == CHIEF_ACCOUNTANT_POSITION:
            found = user
            break
    if not found:
        return

    full_name = (found.full_name or "").strip()
    if not full_name:
        return
    context["chief_accountant_name"] = full_name
    context["chief_accountant_name_genitive"] = _to_gen_fio(full_name)
    context["chief_accountant_name_dative"] = _to_dat_fio(full_name)
    context["chief_accountant_initials"] = _fio_to_initials(full_name)
    context["chief_accountant_initials_genitive"] = _to_gen_fio_initials(full_name)
    context["chief_accountant_initials_dative"] = _to_dat_fio_initials(full_name)
