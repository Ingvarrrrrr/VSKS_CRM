"""Клиент Росэлторг.Бизнес: JWT-авторизация и создание/публикация процедуры (волна резки publications.py)."""
import asyncio
import json
import os
import urllib.request
import urllib.error

from app.services.publications_status import _make_ssl_ctx, _set_pub_success, _set_pub_error

ROSELTORG_TOKEN = os.getenv("ROSELTORG_TOKEN", "")

ROSELTORG_AUTH_URL = "https://lk.roseltorg.ru/api/app/api/auth-integration/v1/auth"

ROSELTORG_BASE_URL = "https://business.roseltorg.ru/integration/v1"

ROSELTORG_TEMPLATE_IDS = {
    "request_quotations": 8,
    "request_proposals":  9,
    "competition":        10,
    "auction":            11,
}


async def _get_roseltorg_jwt() -> str:
    """Обменивает интеграционный токен на JWT (двухшаговая авторизация по документации v2.0)."""
    body = json.dumps({
        "grant_type": "integration",
        "token": ROSELTORG_TOKEN,
        "platform": "b2b",
        "client": "b2b",
    }).encode("utf-8")
    req = urllib.request.Request(
        ROSELTORG_AUTH_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "VSKS-CRM/1.0"},
    )
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
    )
    data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


async def _rb_call(jwt: str, url: str, body: dict = None, method: str = "POST"):
    """Выполняет запрос к Росэлторг.Бизнес API с JWT."""
    data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "User-Agent": "VSKS-CRM/1.0",
        },
    )
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=30, context=_make_ssl_ctx())
        )
        return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        return {"_error": text, "_code": e.code}, e.code


async def _call_roseltorg(pub_id: int, payload: dict):
    if not ROSELTORG_TOKEN:
        await _set_pub_error(pub_id, "Не задан ROSELTORG_TOKEN в окружении сервера")
        return

    # Шаг 1: получаем JWT
    try:
        jwt = await _get_roseltorg_jwt()
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка авторизации Росэлторг: {str(e)[:200]}")
        return

    procedure_type = payload.get("procedure_type", "request_quotations")
    template_id = ROSELTORG_TEMPLATE_IDS.get(procedure_type, 8)
    subject = payload.get("subject") or f"Закупка {payload.get('registry_number', '')}"
    nmck = payload.get("nmck", 0)
    base = ROSELTORG_BASE_URL

    try:
        # Шаг 2: создаём черновик процедуры
        result, status = await _rb_call(jwt, f"{base}/notices/{template_id}/new")
        if status not in (200, 201) or not result.get("data", {}).get("noticeId"):
            await _set_pub_error(pub_id, f"Росэлторг создание процедуры {status}: {str(result)[:250]}")
            return
        notice_id = result["data"]["noticeId"]

        # Шаг 3: задаём название процедуры
        await _rb_call(jwt, f"{base}/notices/{notice_id}",
            body={"data": {"ProcedureMainInfo": {"name": subject}}}, method="PUT")

        # Шаг 4: создаём лот
        lot_body = {"name": subject, "initialSum": str(nmck), "currency": "RUB"}
        lot_result, lot_status = await _rb_call(jwt, f"{base}/notices/{notice_id}/notice-lot", lot_body)
        if lot_status not in (200, 201):
            await _set_pub_error(pub_id, f"Росэлторг создание лота {lot_status}: {str(lot_result)[:250]}")
            return
        notice_lot_id = (lot_result.get("data") or {}).get("noticeLotId") or (lot_result.get("data") or {}).get("id")

        # Шаг 5: добавляем позиции лота
        if notice_lot_id:
            for idx, item in enumerate(payload.get("items", []), 1):
                if not item.get("item_name"):
                    continue
                item_body = {"data": {
                    "name": item["item_name"],
                    "quantity": str(item.get("quantity", 1)),
                    "unit": item.get("unit", "Штука"),
                    "okeiId": "796",
                    "ordinalNumber": idx,
                }}
                if item.get("unit_price"):
                    item_body["data"]["commodityItemPrice"] = str(item["unit_price"])
                await _rb_call(jwt, f"{base}/notice/lot/{notice_lot_id}/items", item_body)

        # Шаг 6: публикуем
        pub_result, pub_status = await _rb_call(jwt, f"{base}/notices/{notice_id}/publish")
        if pub_status in (200, 201):
            procedure_id = (pub_result.get("data") or {}).get("procedureId") or notice_id
            await _set_pub_success(
                pub_id,
                external_id=str(procedure_id),
                external_url=f"https://business.roseltorg.ru/procedures/{procedure_id}",
            )
        else:
            await _set_pub_error(pub_id, f"Росэлторг публикация {pub_status}: {str(pub_result)[:300]}")
    except Exception as e:
        await _set_pub_error(pub_id, f"Ошибка Росэлторг: {str(e)[:200]}")


