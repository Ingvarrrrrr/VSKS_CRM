"""152-ФЗ: единственный источник правды «актуально ли согласие пользователя» —
ПРАВИЛО №6. Используется и гейтом после входа (backend/app/routers/legal.py,
GET /api/legal/consent-status), и регистрацией (organizations.py), и будущими
местами, которым нужен тот же ответ — ни одно из них не считает его заново.

Версии согласий по назначению (PD_CONSENT_VERSION — политика+согласие на
обработку ПДн; PORUCHENIE_VERSION — условия поручения обработки ПДн
организации) приходят из backend/app/services/legal_generated.py
(генерируется legal/build.py из legal/operator.json) — сервер знает текущую
версию сам, не верит фронту (см. docstring UserConsent.document_version).

Совместимость со старыми записями: UserConsent.document_version исторически
писался как склейка ВСЕХ опубликованных документов сразу (напр.
"consent:1.0+cookies:1.0+privacy:1.0", без учёта появившихся позже
документов). parse_document_version() разбирает её в {slug: version};
versions_satisfy() требует присутствия КАЖДОЙ нужной пары slug:version —
лишние пары (cookies, offer, появившийся позже poruchenie) игнорируются.
Поэтому старая запись по-прежнему считается актуальной для pd-согласия,
даже если версия строкой целиком не совпадает с текущей PD_CONSENT_VERSION.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_consent import UserConsent
from app.services.legal_constants import PD_CONSENT_VERSION, PORUCHENIE_VERSION

__all__ = [
    "parse_document_version",
    "versions_satisfy",
    "is_consent_current",
    "pd_consent_required",
    "poruchenie_required",
]


def parse_document_version(document_version: Optional[str]) -> dict[str, str]:
    """"slug:ver+slug:ver" -> {slug: ver}. Пустая/кривая строка -> {}."""
    result: dict[str, str] = {}
    if not document_version:
        return result
    for part in document_version.split("+"):
        if ":" not in part:
            continue
        slug, _, version = part.partition(":")
        slug = slug.strip()
        if slug:
            result[slug] = version.strip()
    return result


# Требуемые версии разобраны ОДИН раз на старте процесса из тех же строк,
# что экспортирует legal_generated.py — не второй расчёт (ПРАВИЛО №6).
PD_REQUIRED_VERSIONS: dict[str, str] = parse_document_version(PD_CONSENT_VERSION)
PORUCHENIE_REQUIRED_VERSIONS: dict[str, str] = parse_document_version(PORUCHENIE_VERSION)


def _major_version(version: str) -> str:
    """Старшая часть версии документа (до первой точки). Правовой смысл версий
    "X.Y" — X растёт при существенном изменении порядка обработки (privacy.md
    п.18.2: "при внесении существенных изменений... Оператор уведомляет";
    то же для текста самого согласия/поручения), Y — при уточнении
    формулировки без изменения смысла (пример: privacy 1.0->1.1 08.10.2026,
    переписан п.16.1 — какие меры защиты применяются, без изменения состава
    или назначения обработки ПДн). Повторное согласие — только на X."""
    return (version or "").split(".", 1)[0]


def versions_satisfy(have: dict[str, str], required: dict[str, str]) -> bool:
    """`have` актуален против `required`, если для КАЖДОГО требуемого slug
    совпадает СТАРШАЯ версия (см. _major_version) — младшая (уточнение
    формулировки) не требует повторного согласия. Лишние пары в `have`
    игнорируются."""
    return all(
        _major_version(have.get(slug, "")) == _major_version(version)
        for slug, version in required.items()
    )


def is_consent_current(document_version: Optional[str], required: dict[str, str]) -> bool:
    """Удобный вариант versions_satisfy() для ОДНОЙ строки document_version
    (напр. для теста или когда согласие точно лежит в одной записи)."""
    return versions_satisfy(parse_document_version(document_version), required)


async def _merged_versions(
    db: AsyncSession,
    user_id: int,
    org_id: Optional[int],
) -> dict[str, str]:
    """Склейка slug:version пар из ВСЕХ неотозванных согласий пользователя,
    подходящих под org_id (None — согласия пользователя вне организации,
    напр. pd; конкретный id — согласия именно этой организации, напр.
    poruchenie). Несколько записей могут вместе покрывать разные документы
    (напр. старая регистрация дала privacy+consent одной записью, новое
    согласие на обновлённую политику — другой)."""
    query = select(UserConsent).where(
        UserConsent.user_id == user_id,
        UserConsent.withdrawn_at.is_(None),
    )
    if org_id is None:
        query = query.where(UserConsent.org_id.is_(None))
    else:
        query = query.where(UserConsent.org_id == org_id)
    rows = (await db.execute(query)).scalars().all()
    merged: dict[str, str] = {}
    for row in rows:
        merged.update(parse_document_version(row.document_version))
    return merged


async def pd_consent_required(db: AsyncSession, user_id: int) -> bool:
    """Нужно ли пользователю заново подтвердить согласие на обработку ПДн
    (политика + согласие, PD_CONSENT_VERSION)."""
    have = await _merged_versions(db, user_id, org_id=None)
    return not versions_satisfy(have, PD_REQUIRED_VERSIONS)


async def poruchenie_required(db: AsyncSession, user_id: int, org_id: int) -> bool:
    """Нужно ли владельцу организации org_id принять актуальные Условия
    поручения обработки персональных данных (PORUCHENIE_VERSION)."""
    have = await _merged_versions(db, user_id, org_id=org_id)
    return not versions_satisfy(have, PORUCHENIE_REQUIRED_VERSIONS)
