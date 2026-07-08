"""Push notifications via Telegram and MAX (VK) bots."""
import os
import re
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "https://gaaala.duckdns.org")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_API = "https://botapi.max.ru/messages/send?access_token={token}"


async def _save_tg_mapping(chat_id: str, message_id: int, task_id: int) -> None:
    """Save telegram message_id → task_id mapping to DB."""
    try:
        from app.database import async_session
        from app.models.task import TelegramMessageMap
        async with async_session() as db:
            db.add(TelegramMessageMap(
                chat_id=str(chat_id),
                message_id=message_id,
                task_id=task_id,
            ))
            await db.commit()
    except Exception as e:
        logger.warning("Failed to save TG mapping: %s", e)


def _button(url: str, label: str = "Открыть") -> dict:
    """Build Telegram inline keyboard with one URL button."""
    return {
        "inline_keyboard": [[{"text": f"➡️ {label}", "url": url}]]
    }


def _callback_keyboard(buttons: list) -> dict:
    """Build Telegram inline keyboard with callback_data buttons.
    buttons: list of (label, callback_data)
    """
    return {
        "inline_keyboard": [[{"text": label, "callback_data": data} for label, data in buttons]]
    }


def _task_keyboard(task_id: int) -> dict:
    """Keyboard: open CRM + Reply button for task notifications."""
    return {
        "inline_keyboard": [[
            {"text": "➡️ Открыть", "url": _task_url(task_id)},
            {"text": "✉️ Ответить", "callback_data": f"reply_task:{task_id}"},
        ]]
    }


def _purchase_keyboard(purchase_id: int) -> dict:
    """Keyboard: open CRM + Reply button for purchase notifications."""
    return {
        "inline_keyboard": [[
            {"text": "➡️ Открыть", "url": _purchase_url(purchase_id)},
            {"text": "✉️ Ответить", "callback_data": f"reply_purchase:{purchase_id}"},
        ]]
    }


def _purchase_consent_keyboard(purchase_id: int, user_id: int) -> dict:
    """Keyboard: Accept/Decline + Reply for purchase membership consent."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Принять", "callback_data": f"pm_consent_accept:{purchase_id}:{user_id}"},
                {"text": "❌ Отклонить", "callback_data": f"pm_consent_decline:{purchase_id}:{user_id}"},
            ],
            [
                {"text": "➡️ Открыть", "url": _purchase_url(purchase_id)},
                {"text": "✉️ Ответить", "callback_data": f"reply_purchase:{purchase_id}"},
            ],
        ]
    }


def _consent_keyboard(task_id: int) -> dict:
    """Keyboard: Accept/Decline row + Reply button for consent notifications."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Принять", "callback_data": f"consent_accept:{task_id}"},
                {"text": "❌ Отклонить", "callback_data": f"consent_decline:{task_id}"},
            ],
            [
                {"text": "➡️ Открыть", "url": _task_url(task_id)},
                {"text": "✉️ Ответить", "callback_data": f"reply_task:{task_id}"},
            ],
        ]
    }


async def _send_telegram(chat_id: str, text: str, task_id: int = None,
                          button_url: str = None, button_label: str = None,
                          reply_markup_override: dict = None) -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.debug("Telegram send skipped: no token")
        return
    if not chat_id:
        logger.debug("Telegram send skipped: no chat_id")
        return
    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup_override:
        payload["reply_markup"] = reply_markup_override
    elif button_url:
        payload["reply_markup"] = _button(button_url, button_label or "Открыть")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Telegram API error %d: %s", resp.status_code, resp.text)
                return
            # Save mapping for reply routing
            if task_id:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id")
                if msg_id:
                    await _save_tg_mapping(chat_id, msg_id, task_id)
            logger.info("Telegram sent to %s", chat_id)
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)


async def _send_max(chat_id: str, text: str) -> None:
    if not MAX_BOT_TOKEN or not chat_id:
        return
    url = MAX_API.format(token=MAX_BOT_TOKEN)
    clean = re.sub(r"<[^>]+>", "", text)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={
                "user_id": int(chat_id),
                "text": clean,
            })
    except Exception as e:
        logger.warning("MAX send failed: %s", e)


async def notify_user(user, text: str, task_id: int = None,
                       button_url: str = None, button_label: str = None,
                       reply_markup_override: dict = None) -> None:
    """Send notification to user via all configured channels."""
    tg = getattr(user, "telegram_id", None)
    mx = getattr(user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text, task_id=task_id,
                              button_url=button_url, button_label=button_label,
                              reply_markup_override=reply_markup_override)
    if mx:
        await _send_max(str(mx), text)


def _task_url(task_id: int) -> str:
    return f"{BASE_URL}/my-tasks?task={task_id}"


def _purchase_url(purchase_id: int) -> str:
    return f"{BASE_URL}/orders/{purchase_id}/edit"


def _esc(s: str) -> str:
    """Escape HTML special chars for Telegram."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Task notifications ────────────────────────────────────────────────────────

async def notify_task_assigned(task, assignee_user, assigner_name: str) -> None:
    due = f"\n📅 Срок: {task.due_date.strftime('%d.%m.%Y')}" if task.due_date else ""
    priority_val = task.priority.value if hasattr(task.priority, 'value') else str(task.priority)
    PRIORITY_LABELS = {"low": "Низкий", "medium": "Средний", "high": "Высокий", "urgent": "Срочно"}
    priority_label = PRIORITY_LABELS.get(priority_val, priority_val)
    text = (
        f"📋 <b>Новая задача</b>\n\n"
        f"📌 <b>{_esc(task.title)}</b>{due}\n"
        f"👤 Назначил: <i>{_esc(assigner_name)}</i>\n"
        f"Приоритет: {priority_label}"
    )
    tg = getattr(assignee_user, "telegram_id", None)
    mx = getattr(assignee_user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text, task_id=task.id,
                              reply_markup_override=_consent_keyboard(task.id))
    if mx:
        await _send_max(str(mx), text)


async def notify_consent_required(task, assignee_user, assigner_name: str) -> None:
    due = f"\n📅 Срок: {task.due_date.strftime('%d.%m.%Y')}" if task.due_date else ""
    text = (
        f"🤝 <b>Требуется согласие</b>\n\n"
        f"📌 <b>{_esc(task.title)}</b>{due}\n"
        f"👤 От: <i>{_esc(assigner_name)}</i>"
    )
    tg = getattr(assignee_user, "telegram_id", None)
    mx = getattr(assignee_user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text, task_id=task.id,
                              reply_markup_override=_consent_keyboard(task.id))
    if mx:
        await _send_max(str(mx), text)


async def notify_deadline_soon(task, assignee_user, days_left: int) -> None:
    label = "сегодня!" if days_left == 0 else f"через {days_left} дн."
    text = (
        f"⏰ <b>Срок подходит</b> ({label})\n\n"
        f"📌 <b>{_esc(task.title)}</b>\n"
        f"Статус: {task.status}"
    )
    await notify_user(assignee_user, text, task_id=task.id,
                       reply_markup_override=_task_keyboard(task.id))


async def notify_task_status_changed(task, changed_by_name: str, new_status: str, changed_by_id: int = 0) -> None:
    """Notify all task assignees about status change (except the one who changed it)."""
    status_labels = {
        "todo": "К выполнению", "in_progress": "В работе",
        "done": "✅ Выполнена", "cancelled": "❌ Отменена",
    }
    label = status_labels.get(new_status, new_status)
    text = (
        f"🔄 <b>Статус задачи изменён</b>\n\n"
        f"📌 <b>{_esc(task.title)}</b>\n"
        f"Новый статус: {label}\n"
        f"👤 Изменил: <i>{_esc(changed_by_name)}</i>"
    )
    if hasattr(task, "assignees"):
        for ta in task.assignees:
            if hasattr(ta, "user") and ta.user and ta.user.id != changed_by_id:
                await notify_user(ta.user, text, task_id=task.id,
                                   reply_markup_override=_task_keyboard(task.id))


async def notify_task_comment(task, comment_user_name: str, comment_text: str, mentioned_users=None) -> None:
    # Strip @mentions (e.g. "@Иванов Иван Иванович") — they're metadata, not content
    # Match @ followed by 1-3 Russian/Latin words (full name format)
    clean_text = re.sub(r'@[А-ЯЁа-яёA-Za-z]+(?:\s[А-ЯЁа-яёA-Za-z]+){0,2}', '', comment_text).strip()
    clean_text = re.sub(r'\s{2,}', ' ', clean_text)  # collapse whitespace
    if not clean_text:
        clean_text = comment_text  # fallback if only mentions
    preview = _esc(clean_text[:150] + ("..." if len(clean_text) > 150 else ""))
    # If there are @mentioned users — only they get Telegram notification
    if mentioned_users:
        text = (
            f"💬 <b>Вас упомянули в задаче</b>\n\n"
            f"📌 <b>{_esc(task.title)}</b>\n"
            f"👤 <i>{_esc(comment_user_name)}</i>:\n"
            f"{preview}"
        )
        for user in mentioned_users:
            await notify_user(user, text, task_id=task.id,
                               reply_markup_override=_task_keyboard(task.id))
    # No @mentions — no Telegram, comments visible in CRM only


# ── Purchase notifications ────────────────────────────────────────────────────

async def notify_purchase_status_changed(purchase, changed_by_name: str, new_status: str, notify_users=None) -> None:
    status_labels = {
        "planned": "Запланирована", "confirmed": "Подтверждена",
        "work_in_progress": "В работе", "contracted": "Договор заключён",
        "delivered": "Доставлено", "paid": "Оплачено",
    }
    label = status_labels.get(new_status, new_status)
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"📦 <b>Статус закупки изменён</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"Новый статус: {label}\n"
        f"👤 Изменил: <i>{_esc(changed_by_name)}</i>"
    )
    if notify_users:
        for user in notify_users:
            await notify_user(user, text,
                               reply_markup_override=_purchase_keyboard(purchase.id))


# ── Approval notifications ────────────────────────────────────────────────────

async def notify_approval_started(purchase, approver_users=None) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"✅ <b>Согласование запущено</b>\n\n"
        f"📌 <b>{subject}</b>"
    )
    if approver_users:
        for user in approver_users:
            await notify_user(user, text,
                               reply_markup_override=_purchase_keyboard(purchase.id))


async def notify_approval_decided(purchase, approver_name: str, action: str, comment: str = "", notify_users=None) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    icon = "✅" if action == "approved" else "❌"
    action_label = "Согласовано" if action == "approved" else "Отклонено"
    comment_line = f"\n💬 {_esc(comment)}" if comment else ""
    text = (
        f"{icon} <b>{action_label}</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 Решение: <i>{_esc(approver_name)}</i>{comment_line}"
    )
    if notify_users:
        for user in notify_users:
            await notify_user(user, text,
                               reply_markup_override=_purchase_keyboard(purchase.id))


async def notify_approval_your_turn(purchase, approver_user) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"🔔 <b>Ваша очередь согласовать</b>\n\n"
        f"📌 <b>{subject}</b>"
    )
    await notify_user(approver_user, text,
                       reply_markup_override=_purchase_keyboard(purchase.id))


async def notify_approval_completed(purchase, notify_users=None) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"🎉 <b>Согласование завершено</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"Все согласующие приняли решение."
    )
    if notify_users:
        for user in notify_users:
            await notify_user(user, text,
                               reply_markup_override=_purchase_keyboard(purchase.id))


# ── Purchase deadline notifications ──────────────────────────────────────────

async def notify_purchase_consent_required(purchase, added_user, added_by_name: str) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"🤝 <b>Вас добавляют в обсуждение закупки</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 Добавил: <i>{_esc(added_by_name)}</i>\n\n"
        f"Примите или отклоните участие:"
    )
    tg = getattr(added_user, "telegram_id", None)
    mx = getattr(added_user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text,
                              reply_markup_override=_purchase_consent_keyboard(purchase.id, added_user.id))
    if mx:
        await _send_max(str(mx), text)


async def notify_purchase_member_added(purchase, added_user, added_by_name: str) -> None:
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")
    text = (
        f"👥 <b>Вас добавили в обсуждение закупки</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 Добавил: <i>{_esc(added_by_name)}</i>"
    )
    await notify_user(added_user, text,
                       reply_markup_override=_purchase_keyboard(purchase.id))


def _wish_url(wish_id: int) -> str:
    return f"{BASE_URL}/wishes/{wish_id}"


def _wish_keyboard(wish_id: int) -> dict:
    """Keyboard: open CRM for wish notifications."""
    return {
        "inline_keyboard": [[
            {"text": "➡️ Открыть", "url": _wish_url(wish_id)},
        ]]
    }


def _wish_consent_keyboard(wish_id: int, user_id: int) -> dict:
    """Keyboard: Accept/Decline for wish membership consent."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Принять", "callback_data": f"wm_consent_accept:{wish_id}:{user_id}"},
                {"text": "❌ Отклонить", "callback_data": f"wm_consent_decline:{wish_id}:{user_id}"},
            ],
            [
                {"text": "➡️ Открыть", "url": _wish_url(wish_id)},
            ],
        ]
    }


async def notify_wish_consent_required(wish, added_user, added_by_name: str) -> None:
    """Notify user that they've been added to a wish and consent is required."""
    title = _esc(getattr(wish, 'title', None) or f"Заявка №{wish.id}")
    text = (
        f"🤝 <b>Вас добавляют в заявку</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"👤 Добавил: <i>{_esc(added_by_name)}</i>\n\n"
        f"Примите или отклоните участие:"
    )
    tg = getattr(added_user, "telegram_id", None)
    mx = getattr(added_user, "max_chat_id", None)
    if tg:
        await _send_telegram(str(tg), text,
                              reply_markup_override=_wish_consent_keyboard(wish.id, added_user.id))
    if mx:
        await _send_max(str(mx), text)


async def notify_wish_member_added(wish, added_user, added_by_name: str) -> None:
    """Notify user that they've been added to a wish (no consent needed)."""
    title = _esc(getattr(wish, 'title', None) or f"Заявка №{wish.id}")
    text = (
        f"👥 <b>Вас добавили в заявку</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"👤 Добавил: <i>{_esc(added_by_name)}</i>"
    )
    await notify_user(added_user, text,
                      reply_markup_override=_wish_keyboard(wish.id))


async def notify_wish_approval_step(wish, approver_user, requester_name: str | None = None) -> None:
    """Notify an approver that it's their turn to decide on a wish."""
    title = _esc(getattr(wish, 'title', None) or f"Заявка №{wish.id}")
    text = (
        f"✍️ <b>Требуется ваше согласование</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"Откройте заявку, чтобы согласовать или отклонить."
    )
    await notify_user(approver_user, text, reply_markup_override=_wish_keyboard(wish.id))


async def notify_wish_rejected(wish, creator_user, decided_by_name: str, reason: str | None = None) -> None:
    """Notify the wish creator that their wish was rejected and returned to them."""
    title = _esc(getattr(wish, 'title', None) or f"Заявка №{wish.id}")
    reason_line = f"\n💬 Причина: <i>{_esc(reason)}</i>" if reason else ""
    text = (
        f"❌ <b>Заявка не согласована</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"👤 Отклонил: <i>{_esc(decided_by_name)}</i>{reason_line}\n\n"
        f"Заявка возвращена вам на доработку."
    )
    await notify_user(creator_user, text, reply_markup_override=_wish_keyboard(wish.id))


async def notify_wish_approved(wish, creator_user) -> None:
    """Notify the wish creator that their wish was fully approved."""
    title = _esc(getattr(wish, 'title', None) or f"Заявка №{wish.id}")
    text = (
        f"✅ <b>Заявка согласована</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"Все согласующие одобрили заявку."
    )
    await notify_user(creator_user, text, reply_markup_override=_wish_keyboard(wish.id))


async def notify_purchase_deadline(purchase, user, days_left: int, deadline_type: str) -> None:
    """Notify about approaching purchase deadline."""
    subject = _esc(purchase.subject or f"Закупка №{purchase.purchase_number}")

    if deadline_type == "payment_overdue":
        text = (
            f"💰 <b>Оплата просрочена</b>\n\n"
            f"📌 <b>{subject}</b>\n"
            f"Товар доставлен {days_left} дн. назад, но не оплачен"
        )
    elif deadline_type == "approval_overdue":
        text = (
            f"⚠️ <b>Согласование просрочено</b>\n\n"
            f"📌 <b>{subject}</b>\n"
            f"Срок согласования истёк {days_left} дн. назад"
        )
    else:
        labels = {"execution_term": "Срок исполнения", "delivery": "Срок поставки"}
        label = labels.get(deadline_type, "Срок")
        if days_left == 0:
            time_label = "сегодня!"
        elif days_left < 0:
            time_label = f"просрочен на {-days_left} дн."
        else:
            time_label = f"через {days_left} дн."
        text = (
            f"⏰ <b>{label}</b> ({time_label})\n\n"
            f"📌 <b>{subject}</b>"
        )
    await notify_user(user, text,
                       button_url=_purchase_url(purchase.id), button_label="Открыть закупку")
