"""Push notifications via Telegram and MAX (VK) bots."""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_API = "https://botapi.max.ru/messages/send?access_token={token}"


async def _send_telegram(chat_id: str, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            })
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")


async def _send_max(chat_id: str, text: str) -> None:
    if not MAX_BOT_TOKEN or not chat_id:
        return
    url = MAX_API.format(token=MAX_BOT_TOKEN)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={
                "user_id": int(chat_id),
                "text": text,
            })
    except Exception as e:
        logger.warning(f"MAX send failed: {e}")


async def notify_user(user, text: str) -> None:
    """Send notification to user via all configured channels."""
    tg = getattr(user, "telegram_id", None)
    mx = getattr(user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text)
    if mx:
        await _send_max(str(mx), text)


async def notify_task_assigned(task, assignee_user, assigner_name: str) -> None:
    due = ""
    if task.due_date:
        due = f"\n📅 Срок: {task.due_date.strftime('%d.%m.%Y')}"
    text = (
        f"📋 <b>Новая задача</b>\n"
        f"Назначил: {assigner_name}\n"
        f"<b>{task.title}</b>{due}\n"
        f"Приоритет: {task.priority}"
    )
    await notify_user(assignee_user, text)


async def notify_consent_required(task, assignee_user, assigner_name: str) -> None:
    due = ""
    if task.due_date:
        due = f"\n📅 Срок: {task.due_date.strftime('%d.%m.%Y')}"
    text = (
        f"🤝 <b>Требуется согласие на задачу</b>\n"
        f"От: {assigner_name}\n"
        f"<b>{task.title}</b>{due}\n"
        f"Войдите в CRM → Задачи → примите или отклоните."
    )
    await notify_user(assignee_user, text)


async def notify_deadline_soon(task, assignee_user, days_left: int) -> None:
    label = "сегодня!" if days_left == 0 else f"через {days_left} дн."
    text = (
        f"⏰ <b>Срок подходит</b> ({label})\n"
        f"Задача: <b>{task.title}</b>\n"
        f"Статус: {task.status}"
    )
    await notify_user(assignee_user, text)
