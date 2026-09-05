"""
Бизнес-логика разовых запросов местоположения через мессенджер — владелец
(организация спасателей), 2026-09.

Отделено от роутера (app/routers/staff_location_requests.py — только HTTP-слой)
и от telegram_webhook.py (транспорт) по Правилу модульности: сюда попадает всё,
что должно работать одинаково независимо от канала, которым пришёл ответ.

ПЕРСОНАЛЬНЫЕ ДАННЫЕ: координаты нигде не логируются (см. record_location_response).
Telegram-payload логируется БЕЗ текста сообщения полностью, только факт отправки
и chat_id — исключение сделано намеренно для проверки формирования сообщения
(см. _send_telegram_location_request), т.к. текст не содержит координат.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.staff_location import StaffLocationPoint
from app.models.staff_location_request import StaffLocationRequest

log = logging.getLogger(__name__)

REQUEST_TTL = timedelta(minutes=30)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def effective_status(req: StaffLocationRequest) -> str:
    """Статус с ленивым учётом истечения — см. докстринг модели.

    НЕ пишет в БД сама — вызывающий код (роутер) решает, когда коммитить
    (обычно пачкой на список запросов, а не по одному)."""
    if req.status == "sent" and _ensure_utc(req.expires_at) < datetime.now(timezone.utc):
        return "expired"
    return req.status


async def find_active_request(db: AsyncSession, user_id: int) -> Optional[StaffLocationRequest]:
    """Последний НЕ истёкший запрос со статусом 'sent' для пользователя, если есть.

    Если самый свежий запрос 'sent' на деле уже истёк — статус лениво
    перезаписывается в объекте (коммит — на совести вызывающего кода) и
    функция возвращает None (истёкший запрос больше не активен)."""
    req = (await db.execute(
        select(StaffLocationRequest)
        .where(StaffLocationRequest.user_id == user_id, StaffLocationRequest.status == "sent")
        .order_by(StaffLocationRequest.created_at.desc())
    )).scalars().first()
    if not req:
        return None
    if _ensure_utc(req.expires_at) < datetime.now(timezone.utc):
        req.status = "expired"
        return None
    return req


def _telegram_location_keyboard() -> dict:
    """Reply-клавиатура (НЕ inline!) с кнопкой запроса геопозиции.

    Telegram Bot API: KeyboardButton.request_location = true — при нажатии
    клиент сам отправляет боту сообщение с полем location, без необходимости
    вводить что-либо руками. one_time_keyboard — клавиатура исчезает после
    одного использования (она разовая, не постоянная замена обычной).
    Источник: https://core.telegram.org/bots/api#keyboardbutton
    """
    return {
        "keyboard": [[{"text": "📍 Отправить моё местоположение", "request_location": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def build_telegram_location_request_payload(chat_id: str, text: str) -> dict:
    """Собирает payload sendMessage — вынесено ОТДЕЛЬНО от сети, чтобы формирование
    сообщения можно было проверить без реальной отправки (боевой бот, живые люди —
    см. запрет в задании). Вызывается и из _send_telegram_location_request, и
    напрямую в диагностике/тестах."""
    return {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": _telegram_location_keyboard(),
    }


async def _send_telegram_location_request(chat_id: str, text: str) -> dict:
    """Отправляет сообщение-запрос геопозиции в Telegram. Возвращает собранный
    payload независимо от того, ушла ли реальная отправка (TELEGRAM_BOT_TOKEN
    пуст в dev-окружении — см. app/notifications.py — тогда это чистая сборка
    payload без сети, что и используется для проверки формата сообщения)."""
    from app.notifications import TELEGRAM_BOT_TOKEN, TELEGRAM_API
    payload = build_telegram_location_request_payload(chat_id, text)
    log.info(
        "staff_location_request: telegram payload собран (chat_id=%s, keyboard=request_location)",
        chat_id,
    )
    if TELEGRAM_BOT_TOKEN and chat_id:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN), json=payload)
                if resp.status_code != 200:
                    log.warning("staff_location_request: telegram send error %d: %s", resp.status_code, resp.text)
        except Exception as e:
            log.warning("staff_location_request: telegram send failed: %s", e)
    return payload


async def _send_max_location_request_text(chat_id: str, text: str) -> None:
    """MAX: только текстовая просьба прислать геопозицию вручную.

    MAX Bot API официально поддерживает кнопку request_geo_location в
    клавиатуре (dev.max.ru/docs-api, тип кнопки RequestGeoLocationButton) —
    НО: (1) точный формат запроса для endpoint'а, уже используемого в этом
    проекте (app.notifications._send_max, botapi.max.ru/messages/send), не
    удалось однозначно подтвердить по документации (актуальные примеры
    описывают другой домен/библиотеку), (2) в проекте нет приёма входящих
    обновлений от MAX вовсе (только исходящая отправка) — принять ответ на
    кнопку было бы просто нечем. Рисковать поломкой боевой интеграции ради
    непроверенного формата не стали — решение задания: "если не удалось
    подтвердить — не выдумывай, текстовая просьба". Как только появится MAX
    webhook/polling (по аналогии с telegram_webhook.py) и подтверждённый
    формат кнопки — это единственное место, которое нужно поменять."""
    from app.notifications import _send_max
    await _send_max(chat_id, text)


async def create_request(db: AsyncSession, requester: User, target: User) -> StaffLocationRequest:
    """Создаёт запрос местоположения и рассылает его по каналам ПО ПРИОРИТЕТУ.

    2026-09, уточнение владельца: push — ОСНОВНОЙ канал (открывает экран
    подтверждения прямо в приложении), Telegram/MAX — ЗАПАСНЫЕ, включаются
    только если push не доставлен (нет подписки, подписка мертва, ошибка
    отправки — см. app/services/push_sender.py). Раньше (до уточнения) все
    доступные каналы использовались одновременно — теперь это было бы для
    сотрудника тремя одинаковыми требованиями сразу, чего явно просили
    избежать.

    Идемпотентно: если у target уже есть активный (не истёкший) запрос со
    статусом 'sent' — возвращает его, не плодя дубли и не спамя повторной
    отправкой (тот же приём, что StaffShift.start_shift).
    """
    from app.services.push_sender import has_subscription, send_push_notifications

    tg = getattr(target, "telegram_id", None)
    mx = getattr(target, "max_chat_id", None)
    has_push = await has_subscription(db, target.id)
    if not has_push and not tg and not mx:
        name = target.full_name or target.username or f"id {target.id}"
        raise HTTPException(
            status_code=400,
            detail=(
                f"У сотрудника «{name}» нет ни оформленной подписки на "
                "push-уведомления, ни привязанного Telegram, ни MAX — "
                "запросить местоположение нельзя. Попросите его включить "
                "уведомления в приложении (страница «Моё местоположение») "
                "или привязать Telegram/MAX в профиле."
            ),
        )

    existing = await find_active_request(db, target.id)
    if existing:
        return existing

    now = datetime.now(timezone.utc)
    req = StaffLocationRequest(
        requested_by_id=requester.id,
        user_id=target.id,
        status="sent",
        created_at=now,
        expires_at=now + REQUEST_TTL,
    )
    db.add(req)
    await db.flush()

    requester_name = requester.full_name or requester.username or "Диспетчер"
    channels: list[str] = []

    # ── 1) Push — основной канал ────────────────────────────────────────────
    push_delivered = False
    if has_push:
        push_title = "📍 Запрос местоположения"
        push_body = f"{requester_name} просит ваше местоположение — нажмите, чтобы ответить"
        delivered = await send_push_notifications(
            db,
            user_ids=[target.id],
            title=push_title,
            body=push_body,
            url=f"/location-request/{req.id}",
            tag=f"loc-req-{req.id}",
            extra={"type": "location_request", "request_id": req.id},
        )
        push_delivered = delivered.get(target.id, False)
        if push_delivered:
            channels.append("push")
        log.info(
            "staff_location_request id=%s push_delivered=%s",
            req.id, push_delivered,
        )

    # ── 2) Мессенджеры — ЗАПАСНОЙ канал, только если push не доставлен ──────
    if not push_delivered:
        from app.notifications import _esc
        text_tg = (
            f"📍 <b>Запрос местоположения</b>\n\n"
            f"<i>{_esc(requester_name)}</i> просит вас поделиться текущим "
            f"местоположением — разово, это не постоянная передача координат.\n\n"
            f"Нажмите кнопку ниже, чтобы отправить геопозицию."
        )
        text_max = (
            f"📍 Запрос местоположения\n\n"
            f"{requester_name} просит вас поделиться текущим местоположением. "
            f"Пожалуйста, пришлите координаты (геопозицию/адрес) ответным "
            f"сообщением — автоматическая кнопка отправки геопозиции для MAX "
            f"в системе пока не подключена."
        )
        if tg:
            await _send_telegram_location_request(str(tg), text_tg)
            channels.append("telegram")
        if mx:
            await _send_max_location_request_text(str(mx), text_max)
            channels.append("max")

    req.channels_sent = ",".join(channels)
    if not channels:
        # Редкий край: единственным доступным каналом был push, и его
        # отправка не удалась в момент создания записи (мёртвая подписка,
        # сеть) — мессенджеров нет. Запись остаётся 'sent' и лениво истечёт
        # по TTL как обычно; диспетчер увидит пустой channels_sent — честный
        # сигнал "ничего фактически не ушло", а не молчаливый успех.
        log.warning(
            "staff_location_request id=%s: ни один канал не сработал (push_delivered=%s, tg=%s, mx=%s)",
            req.id, push_delivered, bool(tg), bool(mx),
        )

    log.info(
        "staff_location_request created id=%s target_user_id=%s channels=%s",
        req.id, target.id, req.channels_sent,
    )
    return req


async def cancel_request(db: AsyncSession, req: StaffLocationRequest) -> None:
    req.status = "cancelled"


async def record_location_response(
    db: AsyncSession,
    req: StaffLocationRequest,
    lat: float,
    lon: float,
    accuracy_m: Optional[float],
    source: str,
    recorded_at: Optional[datetime] = None,
) -> StaffLocationPoint:
    """Пишет точку-ответ НАПРЯМУЮ (минуя проверку активной смены из
    staff_location.py::submit_points — задание п.2: для ответов на запрос
    нужен свой путь записи, не ломающий существующее ограничение) и помечает
    запрос отвеченным.

    ПЕРСОНАЛЬНЫЕ ДАННЫЕ: параметры lat/lon никогда не попадают в log.* —
    вызывающий код (webhook) логирует только user_id/request_id.
    """
    now = datetime.now(timezone.utc)
    point = StaffLocationPoint(
        user_id=req.user_id,
        lat=lat,
        lon=lon,
        accuracy_m=accuracy_m,
        recorded_at=_ensure_utc(recorded_at) if recorded_at else now,
        source=source[:20],
    )
    db.add(point)
    await db.flush()

    req.status = "answered"
    req.responded_at = now
    req.point_id = point.id
    return point


async def decline_request(db: AsyncSession, req: StaffLocationRequest) -> None:
    """Сотрудник ЯВНО отказался отправлять местоположение (кнопка «Отказаться»
    на экране подтверждения push — см. LocationRequestRespondView.vue).

    Отличается от cancel_request (диспетчер отменяет ДО ответа) тем, что
    здесь решение принял сам сотрудник — диспетчер должен увидеть именно
    отказ, а не гадать, увидел ли человек запрос вообще (задание владельца:
    "диспетчер должен видеть, что человек отказался, а не думать, что тот
    не увидел")."""
    req.status = "declined"
    req.responded_at = datetime.now(timezone.utc)
