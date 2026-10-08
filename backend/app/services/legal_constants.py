"""152-ФЗ: правовые константы и расчёт сроков — единственный источник истины.

Значения (сроки по 152-ФЗ, перечень документов согласия для регистрации)
приходят из backend/app/services/legal_generated.py — файла, который
генерирует legal/build.py из legal/operator.json (Правило №6 — тот же
operator.json подставляется в тексты документов, поэтому бумага и код
обязаны говорить одно и то же число).

Раньше этот модуль читал legal/operator.json напрямую с диска по пути
относительно __file__. Это работало локально, но не в контейнере: образ
бэкенда собирается из каталога backend/ (см. backend/Dockerfile, `COPY . .`
после `WORKDIR /app` из backend/), каталог legal/ в него не копируется —
путь разрешался в несуществующий файл, и модуль падал при импорте, а вместе
с ним весь backend/app/routers/legal.py (RuntimeError на старте — 502 сразу
после деплоя). legal_generated.py — обычный питоновский код рядом с
остальным кодом бэкенда, поэтому едет в образ вместе с ним без исключений
в Dockerfile и без монтирования тома.

Правило №5 (модульность): отдельный файл — эти константы/расчёты не
принадлежат ни одному предметному домену (users/organizations/purchases/...),
а обслуживают исключительно юридический контур 152-ФЗ (регистрация +
обращения субъектов ПДн, backend/app/routers/legal.py и
backend/app/routers/organizations.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Union

from app.services.legal_generated import (
    DEADLINES_WORKING_DAYS,
    PD_CONSENT_DOCUMENTS,
    PD_CONSENT_VERSION,
    PORUCHENIE_DOCUMENTS,
    PORUCHENIE_VERSION,
)

__all__ = [
    "DEADLINES_WORKING_DAYS",
    "PD_CONSENT_DOCUMENTS",
    "PD_CONSENT_VERSION",
    "PORUCHENIE_DOCUMENTS",
    "PORUCHENIE_VERSION",
    "add_working_days",
    "get_response_deadline_days",
    "get_response_due_at",
]


def _deadline_days(key: str) -> int:
    try:
        return int(DEADLINES_WORKING_DAYS[key])
    except KeyError as exc:
        raise RuntimeError(
            "В backend/app/services/legal_generated.py -> DEADLINES_WORKING_DAYS "
            f"отсутствует ключ '{key}'. Он берётся из legal/operator.json -> "
            "deadlines_working_days — пересоберите: python legal/build.py."
        ) from exc


# Сопоставление типа обращения (PersonalDataRequestType) со сроком ответа —
# ключ в deadlines_working_days. Если для нового типа обращения срока нет,
# get_response_deadline_days() обязан упасть, а не молчать.
_REQUEST_TYPE_TO_DEADLINE_KEY: dict = {
    "info": "info_request",
    "correction": "correction",
    "withdrawal": "destruction_on_withdrawal",
    "deletion": "destruction_on_withdrawal",
}


def get_response_deadline_days(request_type: str) -> int:
    """Срок ответа в рабочих днях для данного типа обращения субъекта ПДн."""
    try:
        deadline_key = _REQUEST_TYPE_TO_DEADLINE_KEY[request_type]
    except KeyError as exc:
        raise RuntimeError(
            f"Для типа обращения '{request_type}' не определён срок ответа в "
            "legal_constants._REQUEST_TYPE_TO_DEADLINE_KEY. Добавьте "
            "сопоставление на ключ deadlines_working_days из legal/operator.json."
        ) from exc
    return _deadline_days(deadline_key)


def add_working_days(start: Union[date, datetime], n: int) -> Union[date, datetime]:
    """Прибавляет N РАБОЧИХ дней к дате, пропуская субботы и воскресенья.

    ВАЖНО (осознанный компромисс, не недоделка): нерабочие праздничные дни
    производственного календаря РФ здесь НЕ учитываются — считать их рабочими
    выгоднее для субъекта ПДн (срок ответа получается короче/строже к
    оператору, а не мягче), чем ошибиться в другую сторону и пропустить
    законный срок. Учёт полного производственного календаря — отдельная
    задача, требующая внешнего справочника праздников на каждый год.
    """
    current = start
    remaining = n
    one_day = timedelta(days=1)
    while remaining > 0:
        current = current + one_day
        if current.weekday() < 5:  # 0=понедельник .. 4=пятница
            remaining -= 1
    return current


def get_response_due_at(received_at: datetime, request_type: str) -> datetime:
    """Дата истечения законного срока ответа на обращение request_type,
    поступившее received_at. Единственное место в проекте, где считается
    response_due_at — см. backend/app/routers/legal.py, POST /api/legal/request.
    """
    days = get_response_deadline_days(request_type)
    return add_working_days(received_at, days)
