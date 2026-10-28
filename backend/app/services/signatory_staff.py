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
