"""Единый гейт персональных данных физлица-контрагента (ГПХ-реквизиты).

Владелец (2026-10-08): паспорт/СНИЛС/адрес регистрации/дату рождения
исполнителя-физлица должны видеть и писать ТОЛЬКО пользователи, у которых
есть право работать с разделом «Договоры» — вкладка `contracts`
(app/auth/permissions.py::require_tab). Раньше GET /api/contractors/ и
GET /api/contractors/{id} отдавали эти поля любому вошедшему пользователю
(response_model=ContractorOut включает их без всякого гейта).

ПРАВИЛО №6: это ЕДИНСТВЕННОЕ место, которое решает (а) какие поля считаются
личными данными контрагента-физлица и (б) виден/записываем ли этот набор
полей текущему пользователю. Все роутеры и сервисы генерации документов
зовут функции отсюда — не заводить вторую проверку/второй список полей.

Выбор права: отдельного tab_key под «паспортные данные контрагентов» в
системе нет; вкладка `contracts` — единственная, которая однозначно
соответствует работе с договорами (и ГПХ-договор с физлицом — единственное
место в проекте, где эти поля вообще используются, см. комментарий в
app/models/contractor.py про шаблоны contract_gph_individual). tab_key
`contracts` по сидам (alembic/versions/perm_seed_hotfix.sql) уже выдан ровно
superadmin/account_owner/admin/org_admin/manager — рядовой employee его не
получает, что и требовалось.
"""
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import _has_key_in_any_org
from app.models.user import User

# tab_key, дающий право видеть/писать личные данные контрагента-физлица.
CONTRACTOR_PII_TAB_KEY = "contracts"

# Единственный список полей-ПДн контрагента (физлицо по ГПХ). ИНН/название/
# банковские реквизиты организаций сюда НЕ входят — они не персональные
# данные и остаются видимыми всем, как и раньше.
CONTRACTOR_PII_FIELDS: tuple[str, ...] = (
    "passport_series",
    "passport_number",
    "passport_issuer",
    "passport_issued_date",
    "snils",
    "registration_address",
    "birth_date",
)


async def user_can_view_contractor_pii(user: User, db: AsyncSession) -> bool:
    """True, если у пользователя есть право видеть/писать ПДн контрагента —
    вкладка `contracts` хотя бы в одной доступной организации, либо
    superadmin/account_owner (у них ключ `contracts` уже в эффективном
    наборе через _get_effective_simple, см. app/auth/permissions.py)."""
    if user.role == "superadmin":
        return True
    return await _has_key_in_any_org(user, db, CONTRACTOR_PII_TAB_KEY)


def strip_contractor_pii(data: dict) -> dict:
    """Убирает PII-ключи из словаря (на входе — уже .model_dump() от
    ContractorOut/аналогичного дикта). Мутирует и возвращает тот же dict."""
    for f in CONTRACTOR_PII_FIELDS:
        data.pop(f, None)
    return data


async def filter_contractor_payload(payload: Any, user: User, db: AsyncSession) -> Any:
    """Принимает dict ИЛИ список dict-ов (контрагент(ы), уже сериализованные
    в обычный dict) и вырезает ПДн-поля, если у пользователя нет права.
    С правом — возвращает как есть (без копирования)."""
    if await user_can_view_contractor_pii(user, db):
        return payload
    if isinstance(payload, list):
        return [strip_contractor_pii(dict(item)) for item in payload]
    return strip_contractor_pii(dict(payload))


def sanitize_contractor_write_fields(data: dict, can_write_pii: bool) -> dict:
    """Запись (create/update контрагента): если нет права — убрать ПДн-ключи
    из `data` ДО применения к модели, чтобы без права их было невозможно ни
    задать, ни (что важнее) затереть существующие значения чужим PATCH/PUT
    без этих полей. С правом — `data` возвращается без изменений."""
    if can_write_pii:
        return data
    return {k: v for k, v in data.items() if k not in CONTRACTOR_PII_FIELDS}


def contractor_pii_doc_fields(
    c: Optional[Any],
    can_view_pii: bool,
    fmt_date: Callable[[Any], str],
) -> dict:
    """Единый расчёт ключей контекста документов (ГПХ-паспорт/СНИЛС/адрес
    регистрации/дата рождения) — используется и в
    app/services/documents/contexts_extra.py (обычная генерация документа),
    и в app/services/documents/fabrikant_package.py (пакет для Фабрикант).
    Без права — отдаёт пустые строки (как если бы контрагента не было),
    документ всё равно формируется, просто с пустыми этими полями.

    `fmt_date` — вызывающая сторона передаёт свой `_fmt_date` (разные модули
    разного пакета, чтобы не тянуть сюда зависимость на services/documents).
    """
    src = c if (c is not None and can_view_pii) else None
    return {
        "contractor_passport_series": (src.passport_series or '') if src else '',
        "contractor_passport_number": (src.passport_number or '') if src else '',
        "contractor_passport_issuer": (src.passport_issuer or '') if src else '',
        "contractor_passport_issued_date": fmt_date(src.passport_issued_date) if src and src.passport_issued_date else '',
        "contractor_snils": (src.snils or '') if src else '',
        "contractor_registration_address": (
            (src.registration_address or src.address or getattr(src, 'postal_address', None) or '')
            if src else ''
        ),
        "contractor_birth_date": fmt_date(src.birth_date) if src and src.birth_date else '',
    }
