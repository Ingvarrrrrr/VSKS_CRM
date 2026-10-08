"""СГЕНЕРИРОВАНО legal/build.py — не редактировать руками.

Источник данных: legal/operator.json (блок deadlines_working_days) и
legal/build.py (PD_CONSENT_DOCUMENTS/PORUCHENIE_DOCUMENTS — перечни
документов по назначению согласия, это решение процесса
регистрации/входа, а не реквизит оператора, поэтому в operator.json
его нет).

Существует, потому что backend-образ собирается из каталога backend/ и
не видит legal/ (см. legal/CONTRACT.md) — этот файл едет в образ вместе
с остальным кодом. Читает его только
backend/app/services/legal_constants.py.

Пересобрать: python legal/build.py
"""
from __future__ import annotations

DEADLINES_WORKING_DAYS: dict[str, int] = {
    "act_retention_years": 3,
    "breach_investigation_hours": 72,
    "breach_notify_hours": 24,
    "correction": 7,
    "destruction_on_withdrawal": 10,
    "info_request": 10,
    "info_request_extension": 5,
    "repeat_request_cooldown_days": 30,
    "stop_unlawful_processing": 3,
}

PD_CONSENT_DOCUMENTS: tuple[str, ...] = (
    "privacy",
    "consent",
)

PD_CONSENT_VERSION: str = "consent:1.0+privacy:1.1"

PORUCHENIE_DOCUMENTS: tuple[str, ...] = (
    "poruchenie",
)

PORUCHENIE_VERSION: str = "poruchenie:1.0"
