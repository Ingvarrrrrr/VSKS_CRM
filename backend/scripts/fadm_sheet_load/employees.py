"""--relink, опция --ensure-employee: заводит сотрудника организации ШТАТНЫМ
путём (как app/routers/users.py::create_user), когда владелец называет ФИО
человека, который по факту сотрудник (его закупки должны стать авансовыми —
см. advance.py), но в users его нет и приглашать/давать вход ему не нужно
(задача 04.10.2026, п.2а — Маргарян, Никитин).

Повторяет минимально необходимые поля и связи create_user (email/username
уникальны, full_name пересобирается из last/first/middle через
app.services.fio.resolve_user_name_input — ПРАВИЛО №6, тот же источник
истины, что и у роутера/Excel-импорта/регистрации), БЕЗ HTTP-слоя:
  - role='employee' (минимальная роль)
  - password — случайный токен, НИКОМУ не сообщается и не проходит политику
    пароля (не нужна — только что заведённый пользователь и так не должен
    входить); в кодовой базе нет отдельного флага "не может входить"
    (проверено по app/models/user.py), поэтому непригодность для входа
    обеспечивается только непередаваемостью пароля
  - email — служебный, НЕ рабочий домен: no-login+<транслит-ФИО>@gala.local
  - exclude_from_directory=True — не телефонный справочник сотрудников, а
    техническая запись для авансового возврата
  - ensure_user_org_access(..., role='employee') — та же синхронизация
    user_org_access, что и create_user (Phase 17.1-05), не вторая копия

Идемпотентность: ищем среди ЖИВЫХ пользователей этой организации по тому же
normalize_person_name, что использует advance.EmployeeLookup — то есть ровно
то сравнение ФИО, которое потом решает «авансовый ли». Если совпадение уже
есть — ничего не создаём, возвращаем существующего.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import hash_password
from app.auth.permissions import ensure_user_org_access
from app.models.user import User
from app.services.fio import resolve_user_name_input, split_fio

from .advance import normalize_person_name

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit(raw: str) -> str:
    out = []
    for ch in raw.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
    s = "".join(out)
    return re.sub(r"[^a-z0-9]+", "", s) or "user"


@dataclass
class EnsureEmployeeResult:
    user: User
    created: bool


async def _find_by_name_in_org(db: AsyncSession, org_id: int, full_name: str) -> User | None:
    norm = normalize_person_name(full_name)
    if not norm:
        return None
    rows = (await db.execute(select(User).where(User.org_id == org_id))).scalars().all()
    for u in rows:
        if normalize_person_name(u.full_name) == norm:
            return u
    return None


async def _unique_value(db: AsyncSession, column, base: str) -> str:
    value = base
    suffix = 1
    while (await db.execute(select(User).where(column == value))).scalar_one_or_none():
        suffix += 1
        value = f"{base}{suffix}"
    return value


async def ensure_employee(db: AsyncSession, org_id: int, full_name: str) -> EnsureEmployeeResult:
    """Идемпотентно гарантирует существование сотрудника с данным ФИО в
    организации org_id. Вызывать ДО load_employee_lookup/матчинга —
    в той же транзакции (ничего не коммитит, только flush)."""
    existing = await _find_by_name_in_org(db, org_id, full_name)
    if existing is not None:
        return EnsureEmployeeResult(user=existing, created=False)

    last, first, middle, composed_full = resolve_user_name_input(None, None, None, full_name)
    if not last or not first:
        # split_fio уже вызван внутри resolve_user_name_input; если ФИО совсем
        # куцее (одно слово) — всё равно заводим, составное имя не обязательно.
        last, first, middle = split_fio(full_name)
        composed_full = full_name.strip()

    base_login = _translit(f"{last or ''}{first or ''}")
    username = await _unique_value(db, User.username, f"noauth_{base_login}")
    email = await _unique_value(db, User.email, f"no-login+{base_login}@gala.local")

    random_password = secrets.token_urlsafe(32)  # никому не передаётся — вход не предполагается

    user = User(
        username=username,
        password_hash=hash_password(random_password),
        role="employee",
        last_name=last,
        first_name=first,
        middle_name=middle,
        full_name=composed_full or full_name.strip(),
        email=email,
        is_email_confirmed=True,
        org_id=org_id,
        exclude_from_directory=True,
    )
    db.add(user)
    await db.flush()
    await ensure_user_org_access(user.id, org_id, "employee", db)
    return EnsureEmployeeResult(user=user, created=True)


async def ensure_employees(db: AsyncSession, org_id: int, full_names: list[str]) -> list[EnsureEmployeeResult]:
    results: list[EnsureEmployeeResult] = []
    for name in full_names:
        name = (name or "").strip()
        if not name:
            continue
        results.append(await ensure_employee(db, org_id, name))
    return results
