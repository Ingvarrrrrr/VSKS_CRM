"""Определение «руководителя организации» — единственный источник истины.

Владелец (2026-09-29, финальная версия ТЗ): «Подписант может быть по
доверенности. Руководитель организации — это руководитель организации (из
налоговой по ИНН)». Значит подписант (signatory_*) и руководитель — РАЗНЫЕ
сущности, и:

  • Organization.head_user_id — НЕ используется (ни первично, ни как
    фолбэк). Историческое поле, для этой цепочки больше не источник.
  • Organization.signatory_* — НЕ используется. Подписант может быть
    доверенным лицом, не руководителем (contractors_lookup.py исторически
    клал директора из ЕГРЮЛ прямо в signatory_*, что и смешивало сущности).
  • Единственный источник — Organization.director_last_name/first_name/
    middle_name (руководитель по ЕГРЮЛ, отдельные колонки, миграция
    c5d7e9f1a3b5). Если они пусты, а у организации есть ИНН (через
    app.services.org_requisites.org_requisites — ПРАВИЛО №6, Contractor
    источник истины для inn, если привязан) — руководитель запрашивается из
    ЕГРЮЛ ОДИН РАЗ тем же сервисом, что и карточка контрагента
    (app.routers.contractors_lookup.lookup_inn, force_egrul=True — второй
    механизм похода в ЕГРЮЛ не заводим), director_* сохраняется на
    Organization и используется дальше.
  • Найденное ФИО руководителя сопоставляется (после нормализации регистра/
    ё-е/пробелов) с сотрудником организации (User.org_id == org.id ИЛИ
    членство в UserOrganization на эту org_id).
  • Владелец аккаунта (Organization.owner_user_id / account_owner) — ДРУГАЯ
    роль, на неё НЕ фолбэчить (feedback_no_false_absence_claims /
    feedback_permission_check_vs_candidate_pool: не путать роли).

ПРАВИЛО №6 (один показатель — один источник истины): три места читали
Organization.head_user_id напрямую как «руководителя организации» для
построения цепочки согласования:
  • app/services/approval_chain.py::build_ascending_chain
  • app/routers/purchase_ops.py::_build_framework_chain_approvals
  • app/routers/wish_transitions.py::submit_wish (авто-подбор для
    компаньона авансового отчёта)
Все три переведены на resolve_org_head_user_id() ниже.
"""
import logging
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.services.documents.formatting import _format_initials_safe
from app.services.fio import compose_fio
from app.services.org_requisites import org_requisites

logger = logging.getLogger(__name__)


def _normalize_name_part(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(s.strip().casefold().replace("ё", "е").split())


def _normalize_fio(last: Optional[str], first: Optional[str], middle: Optional[str]) -> str:
    parts = [p for p in (
        _normalize_name_part(last), _normalize_name_part(first), _normalize_name_part(middle)
    ) if p]
    return " ".join(parts)


async def _fetch_org_inn(db: AsyncSession, org: Organization) -> Optional[str]:
    """ИНН организации через org_requisites (ПРАВИЛО №6: Contractor —
    источник истины, если org.contractor_id указывает на него)."""
    contractor = None
    if org.contractor_id:
        contractor = await db.get(Contractor, org.contractor_id)
    reqs = org_requisites(org, contractor)
    inn = reqs.get("inn")
    return inn.strip() if inn and inn.strip() else None


async def refresh_director_from_egrul(db: AsyncSession, org: Organization, *, force: bool = False) -> bool:
    """Запросить ЕГРЮЛ (тем же сервисом lookup_inn, что и карточка
    контрагента — второй механизм похода в ЕГРЮЛ не заводим) и сохранить
    director_* на организацию.

    force=False (путь по умолчанию, вызывается из resolve_org_head_user_id/
    describe_org_head_missing_reason): если director_* уже заполнены —
    ничего не делает, запрос ОДИН РАЗ.
    force=True (кнопка «Обновить по ИНН» на карточке организации,
    routers/organization_director.py): запрашивает ЕГРЮЛ заново независимо
    от того, что уже сохранено.

    Не коммитит — вызывающий отвечает за commit/flush в своей транзакции
    (submit_wish/build_ascending_chain уже делают flush перед возвратом).
    Возвращает True, если director_* были обновлены.

    Бросает HTTPException, если force=True и ИНН не найден в ЕГРЮЛ/налоговая
    недоступна — вызывающий эндпоинт (POST /director/refresh) должен вернуть
    эту ошибку пользователю, а не проглатывать её молча (в отличие от
    ленивого force=False пути, где отсутствие ответа только логируется).
    """
    if not force and (org.director_last_name or org.director_first_name or org.director_middle_name):
        return False
    inn = await _fetch_org_inn(db, org)
    if not inn:
        if force:
            from fastapi import HTTPException
            raise HTTPException(400, "У организации не заполнен ИНН — заполните реквизиты")
        return False
    try:
        from app.routers.contractors_lookup import lookup_inn
        data = await lookup_inn(inn, force_egrul=True, db=db)
    except Exception as exc:  # HTTPException (не найден в ЕГРЮЛ) и сетевые сбои
        logger.warning("refresh_director_from_egrul: lookup_inn(%s) failed for org %s: %s", inn, org.id, exc)
        if force:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                raise HTTPException(exc.status_code, f"ЕГРЮЛ по ИНН {inn}: {exc.detail}")
            raise HTTPException(502, f"Налоговая (ЕГРЮЛ) недоступна для ИНН {inn} — попробуйте позже")
        return False
    d_last = data.get("director_last_name")
    d_first = data.get("director_first_name")
    d_middle = data.get("director_middle_name")
    if not (d_last or d_first or d_middle):
        if force:
            from fastapi import HTTPException
            raise HTTPException(404, f"ЕГРЮЛ по ИНН {inn} не вернул данные о руководителе")
        return False
    org.director_last_name = d_last
    org.director_first_name = d_first
    org.director_middle_name = d_middle
    org.director_position = data.get("director_position")
    db.add(org)
    return True


async def _ensure_director_from_egrul(db: AsyncSession, org: Organization) -> None:
    """Обёртка для внутренних вызовов (resolve_org_head_user_id/
    describe_org_head_missing_reason) — ленивый путь, см. refresh_director_from_egrul."""
    await refresh_director_from_egrul(db, org, force=False)


async def resolve_org_head_user_id(db: AsyncSession, org: Optional[Organization]) -> Optional[int]:
    """Вернуть id пользователя-сотрудника организации, чьё ФИО совпадает с
    руководителем по ЕГРЮЛ (Organization.director_*, при необходимости
    дозапрошенным по ИНН — см. _ensure_director_from_egrul). None, если
    руководителя не удалось определить или среди сотрудников нет совпадения
    — см. describe_org_head_missing_reason для текста отказа в этом случае.
    """
    if org is None:
        return None

    await _ensure_director_from_egrul(db, org)

    target_fio = _normalize_fio(org.director_last_name, org.director_first_name, org.director_middle_name)
    if not target_fio:
        return None

    rows = (await db.execute(
        select(User.id, User.last_name, User.first_name, User.middle_name)
        .distinct()
        .outerjoin(UserOrganization, UserOrganization.user_id == User.id)
        .where(or_(User.org_id == org.id, UserOrganization.org_id == org.id))
    )).all()

    for uid, u_last, u_first, u_middle in rows:
        candidate_fio = _normalize_fio(u_last, u_first, u_middle)
        if candidate_fio and candidate_fio == target_fio:
            return uid

    return None


def get_org_director_full_name(org: Optional[Organization]) -> Optional[str]:
    """ФИО руководителя по ЕГРЮЛ одной строкой (для сообщений) — None, если
    в карточке организации не заполнено (и по ИНН ещё не дозапрашивалось)."""
    if org is None:
        return None
    return compose_fio(org.director_last_name, org.director_first_name, org.director_middle_name)


async def describe_org_head_missing_reason(db: AsyncSession, org: Optional[Organization]) -> str:
    """Текст отказа, когда resolve_org_head_user_id вернул None — называет,
    что именно проверено (владелец: «как он не указан?» — ответ должен
    показывать факт проверки ЕГРЮЛ/сотрудников, а не молчать)."""
    org_name = (getattr(org, "name", None) or f"№{getattr(org, 'id', '?')}") if org else "?"
    if org is not None:
        await _ensure_director_from_egrul(db, org)
    director_full = get_org_director_full_name(org) if org else None
    if not director_full:
        inn = await _fetch_org_inn(db, org) if org is not None else None
        if not inn:
            return (
                f"не удалось определить руководителя организации «{org_name}» по ИНН: "
                f"у организации не заполнен ИНН — заполните реквизиты"
            )
        return (
            f"не удалось определить руководителя организации «{org_name}» по ИНН {inn} "
            f"(ЕГРЮЛ не вернул данные) — укажите руководителя вручную"
        )
    director_short = _format_initials_safe(director_full)
    return (
        f"руководитель по ЕГРЮЛ — {director_short}, но такого сотрудника нет "
        f"в организации «{org_name}» — добавьте его сотрудником"
    )
