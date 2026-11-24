import os
import time
import asyncio
import logging
import httpx
from fastapi import HTTPException
from app.services.receipts_parsing import classify_proverkacheka_error

logger = logging.getLogger(__name__)

# Single global lock to serialize requests to proverkacheka.com per worker
_PROVERKACHEKA_LOCK = asyncio.Lock()
_LAST_REQUEST_TIME = 0.0
_MIN_INTERVAL = 1.6  # minimum 1600ms between calls to avoid anti-bot / FNS rate limits


async def fetch_proverkacheka_check(qr_str: str) -> dict:
    """Единый клиент обращения к proverkacheka.com (Правило №6 — Single Source of Truth).

    Включает:
    - Проверку наличия PROVERKACHEKA_TOKEN
    - Строгую сериализацию и троттлинг запросов (_PROVERKACHEKA_LOCK + _MIN_INTERVAL)
    - Автоматический повтор при code=4 («Не вышло время ожидания перед повторным запросом»,
      возникает при одновременных запросах с нескольких реплик backend_a / backend_b)
    - Понятные сообщения при сетевых таймаутах и ошибках соединения (без пустого str(e))
    - Классификацию бизнес-ошибок через classify_proverkacheka_error
    """
    token = os.getenv("PROVERKACHEKA_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "PROVERKACHEKA_TOKEN не настроен на сервере")

    global _LAST_REQUEST_TIME
    async with _PROVERKACHEKA_LOCK:
        elapsed = time.monotonic() - _LAST_REQUEST_TIME
        if _LAST_REQUEST_TIME > 0 and elapsed < _MIN_INTERVAL:
            await asyncio.sleep(_MIN_INTERVAL - elapsed)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        proxy = os.getenv("PROVERKACHEKA_PROXY", "").strip() or None
        source_ip = os.getenv("PROVERKACHEKA_SOURCE_IP", "").strip() or None
        transport = httpx.AsyncHTTPTransport(local_address=source_ip) if source_ip else None

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(22.0, connect=8.0),
                headers=headers,
                follow_redirects=True,
                proxy=proxy,
                transport=transport,
                trust_env=False,
            ) as client:
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        resp = await client.post(
                            "https://proverkacheka.com/api/v1/check/get",
                            data={"qrraw": qr_str, "token": token},
                        )
                        resp.raise_for_status()
                        payload = resp.json()
                    except (httpx.TransportError, httpx.TimeoutException):
                        if attempt < 2:
                            await asyncio.sleep(1.5)
                            continue
                        raise

                    # code=4: «Не вышло время ожидания перед повторным запросом» (гонка между репликами)
                    if isinstance(payload, dict) and payload.get("code") == 4 and attempt < 3:
                        await asyncio.sleep(2.0)
                        continue
                    break
        except httpx.TimeoutException:
            raise HTTPException(
                502,
                "Ошибка запроса к proverkacheka.com: превышено время ожидания ответа от шлюза ФНС",
            )
        except httpx.ConnectError as e:
            reason = str(e).strip() or "сброс сетевого соединения"
            raise HTTPException(502, f"Ошибка запроса к proverkacheka.com: ошибка соединения ({reason})")
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                502,
                f"Ошибка запроса к proverkacheka.com: внешний сервер вернул HTTP {e.response.status_code}",
            )
        except httpx.HTTPError as e:
            err_msg = str(e).strip() or e.__class__.__name__
            raise HTTPException(502, f"Ошибка запроса к proverkacheka.com: {err_msg}")
        except ValueError:
            raise HTTPException(502, "Не удалось распарсить JSON-ответ proverkacheka.com")
        finally:
            _LAST_REQUEST_TIME = time.monotonic()

    if not isinstance(payload, dict) or payload.get("code") != 1:
        msg = (payload or {}).get("data") if isinstance(payload, dict) else None
        msg_str = msg if isinstance(msg, str) else ""
        classified = classify_proverkacheka_error(msg_str)
        raise HTTPException(classified["status"], detail={
            "code": classified["code"],
            "message": classified["message"],
            "hint": classified["hint"],
        })

    return payload
