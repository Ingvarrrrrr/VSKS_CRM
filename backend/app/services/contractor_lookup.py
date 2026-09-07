"""Хелперы поиска/проверки контрагента по ИНН (ЕГРЮЛ/ЕГРИП, НПД).

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Чистая логика без
FastAPI Depends — используется роутерами contractors.py (check-npd-status)
и contractors_lookup.py (lookup-inn, enrich-from-fns, enrich-all-fns).
"""


def _split_signatory(raw, position=None):
    """Тонкая обёртка над split_position_and_fio из fio.py.

    Сохраняет прежнюю сигнатуру и возврат (signatory_fio, signatory_position)
    для обратной совместимости со всеми вызывающими местами.
    """
    from app.services.fio import split_position_and_fio, compose_fio
    last, first, middle, pos = split_position_and_fio(raw, position)
    fio = compose_fio(last, first, middle) or raw
    return (fio, pos)


async def _check_npd_status(inn: str) -> dict:
    """Статус плательщика НПД (самозанятого) в реестре ФНС.

    ЕГРЮЛ/ЕГРИП самозанятых НЕ содержит — по такому ИНН egrul.nalog.ru отдаёт
    пустой rows, хотя человек реально работает и его находит проверка на
    npd.nalog.ru. Это единственный публичный источник по НПД, и он отдаёт
    только факт статуса — ни ФИО, ни адреса там нет.

    Возвращает {'state': 'yes' | 'no' | 'invalid' | 'unknown', 'message': str}.
    'invalid' — ИНН не проходит проверку контрольной цифры (ФНС: validation.failed).
    'unknown' — сервис недоступен либо упёрлись в его лимит запросов с одного IP
    (ФНС отдаёт taxpayer.status.service.limited.error); отличать от 'no' важно,
    иначе пользователю соврём, что человек не самозанятый.
    """
    import httpx
    import logging
    from datetime import date as _date

    logger = logging.getLogger(__name__)
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.post(
                "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status",
                json={"inn": inn, "requestDate": _date.today().isoformat()},
            )
            data = resp.json()
    except Exception as e:
        logger.warning("NPD status check failed for INN %s: %s", inn, e)
        return {"state": "unknown", "message": "сервис проверки самозанятых ФНС не ответил"}

    if data.get("code"):
        logger.warning("NPD status refused for INN %s: %s", inn, data)
        _msg = data.get("message") or str(data.get("code"))
        if data.get("code") == "validation.failed":
            return {"state": "invalid", "message": _msg}
        return {"state": "unknown", "message": _msg}
    if data.get("status") is True:
        return {"state": "yes", "message": data.get("message") or ""}
    return {"state": "no", "message": data.get("message") or ""}
