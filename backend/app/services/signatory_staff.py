"""Материализация подписанта организации (руководитель из ЕГРЮЛ/карточки
контрагента) в штатного сотрудника — без возможности войти в систему.

Повод (Правило владельца, 28.10.2026): «Ответственный исполнитель» закупки
(Purchase.assigned_user_id) теперь обязан быть штатом организации субсидии
(см. app.services.service_note_people). Если у организации субсидии ещё НЕТ
ни одного штатного сотрудника (User), выбрать некого — а подписант у
организации уже есть (ФИО/должность из ЕГРЮЛ, хранятся в карточке
контрагента, см. app.models.organization.Organization.signatory_*). Эта
функция делает подписанта реальной строкой users, чтобы FK assigned_user_id
на него сослался.

Идемпотентно по (org_id, ФИО) — повторный вызов с тем же ФИО находит уже
созданную запись среди штата этой орг (ПРАВИЛО №6 для дедупа — точное
совпадение ФИО, см. feedback_dedup_exact_only, без fuzzy-матчинга).

Созданный User НЕ может войти в систему: пароль — случайный, никому не
известный токен; email не указан; is_email_confirmed остаётся False (дефолт
колонки) — /api/auth/login требует подтверждённый email ДО выдачи токена
(см. app/routers/auth.py::login), подтвердить его здесь нечем (email не
указан). Отдельного флага «без логина» в схеме users нет — заводить под это
миграцию не стали (минимально корректное решение в рамках задачи
28.10.2026, без изменения схемы БД).
"""
from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import hash_password
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.services.fio import compose_fio
from app.services.service_note_initiators import org_staff_user_ids


async def get_or_create_signatory_staff_user(
    db: AsyncSession,
    org_id: int,
    last_name: Optional[str],
    first_name: Optional[str],
    middle_name: Optional[str],
    position: Optional[str] = None,
) -> User:
    """Возвращает (находит или создаёт) штатного User для подписанта org_id.

    Поиск — среди уже числящегося штата org_id (org_staff_user_ids —
    ЕДИНСТВЕННАЯ формула «штата», ПРАВИЛО №6), по точному совпадению
    full_name. Не находит — создаёт нового, сразу членом user_organizations
    этой org (без отдела — только организация), с той же должностью, что в
    карточке.
    """
    full_name = compose_fio(last_name, first_name, middle_name)
    if not full_name:
        raise ValueError("Нет ФИО подписанта — last_name/first_name пусты")

    staff_ids = await org_staff_user_ids(db, org_id)
    if staff_ids:
        existing = (await db.execute(
            select(User).where(User.id.in_(staff_ids), User.full_name == full_name)
        )).scalar_one_or_none()
        if existing:
            return existing

    # username — технический идентификатор, не логин (подписант не входит
    # в систему через него); уникализируем так же, как create_user.
    raw_base = "".join(ch for ch in full_name.lower() if ch.isalnum())
    base = f"signatory_{org_id}_{raw_base[:40]}" if raw_base else f"signatory_{org_id}"
    username = base
    suffix = 1
    while (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
        username = f"{base}{suffix}"
        suffix += 1

    user = User(
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="employee",
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        full_name=full_name,
        position=position,
        org_id=org_id,
        is_email_confirmed=False,
    )
    db.add(user)
    await db.flush()

    db.add(UserOrganization(user_id=user.id, org_id=org_id, position=position))
    await db.flush()
    return user


async def ensure_signatory_staff_for_org(db: AsyncSession, org: Organization) -> Optional[User]:
    """Автоматическая версия POST /api/organizations/{id}/signatory-to-staff
    (кнопка владельца, routers/organizations.py::materialize_signatory_as_staff) —
    тот же единственный источник подписанта (org_requisites → Contractor.signatory_*,
    ПРАВИЛО №6) и тот же find-or-create (get_or_create_signatory_staff_user выше,
    идемпотентно по точному ФИО, без fuzzy — feedback_dedup_exact_only).

    Жалоба владельца (28.10.2026, субсидия «ЗО_актуальная»/орг «ЗРО ВСКС»,
    id=69): руководитель из ЕГРЮЛ (Юрченкова А.Е., «Председатель совета»)
    не попадал в штат организации — карточку сотрудника заводили только
    вручную кнопкой, а эта кнопка в CreateOrderView была скрыта, когда у
    организации уже числился ЛЮБОЙ штат (условие signatoryCandidate), даже
    если среди него не было именно подписанта. Эта функция вызывается
    автоматически там, где организация получает/обновляет связь с
    контрагентом (ЕГРЮЛ) — app/services/org_dedup.py::
    _materialize_org_from_contractor — и скриптом backfill для уже
    существующих организаций (backend/scripts/backfill_signatory_staff.py),
    чтобы не ждать, что кто-то догадается нажать кнопку.

    Ничего не делает (возвращает None), если:
      • у организации нет contractor_id или подписант не заполнен в карточке
        контрагента (нет last_name/first_name);
      • подписант уже числится сотрудником (get_or_create_signatory_staff_user
        сам находит его по точному ФИО — вызов безопасен повторять).

    Не коммитит — ответственность вызывающего (как и get_or_create_signatory_staff_user).
    """
    if org is None or org.id is None:
        return None
    from app.models.contractor import Contractor
    from app.services.org_requisites import org_requisites

    contractor = None
    if org.contractor_id:
        contractor = await db.get(Contractor, org.contractor_id)
    req = org_requisites(org, contractor)
    last, first, middle = req.get("signatory_last_name"), req.get("signatory_first_name"), req.get("signatory_middle_name")
    if not (last or first):
        return None
    return await get_or_create_signatory_staff_user(
        db, org.id, last, first, middle, position=req.get("signatory_position"),
    )
