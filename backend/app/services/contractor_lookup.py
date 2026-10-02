"""Хелперы поиска/проверки контрагента по ИНН (ЕГРЮЛ/ЕГРИП, НПД).

ПЕРЕНЕСЕНО (не изменено) из app/routers/contractors.py при разрезании
монолитного роутера (Правило №5, сессия 2026-09-08). Чистая логика без
FastAPI Depends — используется роутерами contractors.py (check-npd-status)
и contractors_lookup.py (lookup-inn, enrich-from-fns, enrich-all-fns).

fetch_egrul_row (добавлено 02.10.2026, ПРАВИЛО №6) — ЕДИНСТВЕННЫЙ HTTP-клиент
к egrul.nalog.ru. Раньше та же пара запросов (POST поиска + поллинг GET по
токену) была продублирована инлайном дважды: в
app.routers.contractors_lookup.lookup_inn и в
app.services.receipts_creation._create_or_enrich_contractor_from_receipt
(создание контрагента-продавца из нового чека). Второй экземпляр отставал —
короче timeout/retries, поэтому на проде у части продавцов из чеков нет
ОГРН/адреса (они есть у lookup_inn, которым карточка контрагента правится
руками). Оба места теперь зовут fetch_egrul_row; второй клиент не заводить.
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


async def fetch_egrul_row(
    inn: str,
    *,
    timeout: float = 15,
    max_attempts: int = 5,
    poll_delay: float = 1,
) -> dict | None:
    """Ищет `inn` в ЕГРЮЛ/ЕГРИП (egrul.nalog.ru), возвращает первую строку
    сырого ответа ФНС (ключи c/n/i/o/p/a/g/s/r — короткое/полное имя, ИНН,
    ОГРН, КПП, адрес, руководитель, статус, дата регистрации) либо None,
    если ничего не нашлось ИЛИ запрос не удался (сеть/таймаут/нет токена) —
    сетевая ошибка здесь НЕ бросает исключение, вызывающий сам решает, что
    делать при None (lookup_inn — 404 с проверкой НПД; создание контрагента
    из чека — fallback на данные чека, см. receipts_creation.py).

    `timeout` — httpx-таймаут на один HTTP-запрос; общее время может быть
    больше (max_attempts * poll_delay опроса по токену) — вызывающий с более
    жёстким бюджетом (например, не блокировать загрузку чека дольше ~5 c)
    оборачивает вызов в asyncio.wait_for снаружи.
    """
    import httpx
    import asyncio
    import logging

    logger = logging.getLogger(__name__)
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp1 = await client.post(
                "https://egrul.nalog.ru/",
                json={"query": inn, "region": "", "page": ""},
            )
            token = resp1.json().get("t")
            if not token:
                return None
            for _ in range(max_attempts):
                await asyncio.sleep(poll_delay)
                resp2 = await client.get(f"https://egrul.nalog.ru/search-result/{token}")
                rows = resp2.json().get("rows", [])
                if rows:
                    return rows[0]
    except Exception as e:
        logger.warning("fetch_egrul_row: lookup failed for INN %s: %s", inn, e)
        return None
    return None
