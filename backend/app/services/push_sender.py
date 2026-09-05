"""
Общий сервис отправки Web Push — вынесен из app/routers/chat.py (2026-09).

Причина выноса: запрос местоположения (staff_location_requests.py) должен
слать push тем же кодом, что чат, а не копией — и по плану владельца это
будет переиспользовано ещё раз (push для новых задач/добавления в чат и
т.п.). Правило модульности: этот файл НЕ знает про чат и НЕ знает про
геозапросы — только общий примитив "отправить push списку user_id с таким-то
заголовком/текстом/ссылкой/данными". Специфика — забота вызывающего кода.

Формат payload, который улетает в event 'push' у frontend/public/custom-sw.js:
  {
    title, body,   — обязательные
    icon, badge,   — фиксированные иконки приложения (не настраиваются вызывающим)
    url,           — куда открыть/сфокусировать вкладку по клику
                     (notificationclick уже читает event.notification.data.url —
                     см. custom-sw.js). Если не передан, SW откатывается на
                     '/chat' — это старое поведение чата, оставлено как default
                     ради обратной совместимости (чат не передаёт url явно).
    tag,           — group notifications; если не передан, SW использует
                     'vsks-chat' — тоже старое поведение чата по умолчанию.
    ...extra / per_user_extra — произвольные дополнительные поля (например,
                     unread_count у чата, request_id/type у геозапроса).
  }

Мёртвые подписки: pywebpush поднимает WebPushException с status_code 404/410,
когда push-сервис говорит "этой подписки больше не существует" — такие
подписки удаляются сразу. Любая другая ошибка (сеть, 5xx, таймаут) считается
транзиентной и подписку НЕ трогает — это точнее старого поведения чата
(которое раньше удаляло подписку на любую ошибку вообще), см. задание
владельца 2026-09 про "аккуратную обработку мёртвых подписок".
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription

log = logging.getLogger(__name__)


async def get_user_ids_with_subscription(db: AsyncSession, user_ids: Sequence[int]) -> Set[int]:
    """Кто из перечисленных user_id имеет хотя бы одну push-подписку.

    Используется (1) для UI — "доступен ли push этому сотруднику" (диалог
    запроса местоположения), (2) чтобы решить, пробовать ли push вообще ДО
    отправки — см. staff_location_requests.py::create_request."""
    ids = [uid for uid in user_ids if uid is not None]
    if not ids:
        return set()
    rows = (await db.execute(
        select(PushSubscription.user_id).where(PushSubscription.user_id.in_(ids)).distinct()
    )).scalars().all()
    return set(rows)


async def has_subscription(db: AsyncSession, user_id: int) -> bool:
    """Удобный частный случай get_user_ids_with_subscription для одного user_id."""
    return bool(await get_user_ids_with_subscription(db, [user_id]))


async def send_push_notifications(
    db: AsyncSession,
    user_ids: Sequence[int],
    title: str,
    body: str,
    url: Optional[str] = None,
    tag: Optional[str] = None,
    extra: Optional[dict] = None,
    per_user_extra: Optional[Dict[int, dict]] = None,
) -> Dict[int, bool]:
    """Шлёт Web Push каждой подписке перечисленных пользователей.

    Возвращает {user_id: True/False}: True — хотя бы одна подписка этого
    пользователя приняла push (HTTP 2xx от push-сервиса); False — подписок не
    было вовсе ИЛИ все попытки не удались. Пользователи без единой подписки
    тоже присутствуют в результате со значением False (удобно для readable
    `if not result.get(uid): fallback()`).

    Вызывающий код решает, что делать при False — например, геозапрос
    местоположения (владелец, 2026-09: push — основной канал, мессенджеры —
    запасной) откатывается на Telegram/MAX только если здесь вернулось False.
    """
    result: Dict[int, bool] = {uid: False for uid in user_ids}
    if not user_ids:
        return result

    try:
        from pywebpush import webpush, WebPushException  # type: ignore
    except ImportError:
        log.warning("push_sender: pywebpush не установлен — push отправка невозможна")
        return result

    vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
    vapid_public = os.environ.get("VAPID_PUBLIC_KEY", "")
    if not vapid_private or not vapid_public:
        log.warning("push_sender: VAPID ключи не настроены — push отправка невозможна")
        return result

    subs = (await db.execute(
        select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
    )).scalars().all()

    if not subs:
        log.info("push_sender: у user_ids=%s нет ни одной push-подписки", list(user_ids))
        return result

    expired_ids: List[int] = []
    for sub in subs:
        payload_dict: dict = {
            "title": title,
            "body": body,
            "icon": "/pwa-192x192.png",
            "badge": "/pwa-192x192.png",
        }
        if url:
            payload_dict["url"] = url
        if tag:
            payload_dict["tag"] = tag
        if extra:
            payload_dict.update(extra)
        if per_user_extra and sub.user_id in per_user_extra:
            payload_dict.update(per_user_extra[sub.user_id])
        payload = json.dumps(payload_dict)

        log.info(
            "push_sender: попытка отправки sub_id=%s user_id=%s title=%r",
            sub.id, sub.user_id, title[:60],
        )
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": "mailto:z@vsks.ru"},
            )
            result[sub.user_id] = True
            log.info("push_sender: push доставлен sub_id=%s user_id=%s", sub.id, sub.user_id)
        except WebPushException as e:
            status_code = e.status_code
            if status_code in (404, 410):
                log.info(
                    "push_sender: подписка мертва (HTTP %s) sub_id=%s user_id=%s — удаляю",
                    status_code, sub.id, sub.user_id,
                )
                expired_ids.append(sub.id)
            else:
                log.warning(
                    "push_sender: ошибка отправки (HTTP %s) sub_id=%s user_id=%s: %s",
                    status_code, sub.id, sub.user_id, e,
                )
        except Exception as e:
            log.warning(
                "push_sender: неожиданная ошибка отправки sub_id=%s user_id=%s: %s",
                sub.id, sub.user_id, e,
            )

    if expired_ids:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired_ids)))
        await db.commit()

    return result
