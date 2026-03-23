"""Telegram Bot polling — routes replies from Telegram back to task/purchase comments."""
import asyncio
import logging
import httpx
from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.models.task_comment import TaskComment
from app.models.task import TelegramMessageMap
from app.notifications import TELEGRAM_BOT_TOKEN
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])

_last_update_id = 0
_polling_started = False

# In-memory map: (chat_id, msg_id) → purchase_id for routing purchase replies
_purchase_msg_map: dict[tuple, int] = {}


async def _answer_cq(callback_query_id: str, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"callback_query_id": callback_query_id, "text": text})
    except Exception as e:
        logger.warning("answerCallbackQuery failed: %s", e)


async def _send_force_reply(chat_id: str, prompt: str, task_id: int = None, purchase_id: int = None) -> None:
    """Send a ForceReply message so user can reply without using Telegram's native Reply."""
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": prompt,
                "reply_markup": {"force_reply": True, "selective": True, "input_field_placeholder": "Введите комментарий..."},
            })
            if resp.status_code == 200:
                msg_id = resp.json().get("result", {}).get("message_id")
                if msg_id:
                    if task_id:
                        from app.notifications import _save_tg_mapping
                        await _save_tg_mapping(chat_id, msg_id, task_id)
                    elif purchase_id:
                        _purchase_msg_map[(chat_id, msg_id)] = purchase_id
    except Exception as e:
        logger.warning("ForceReply send failed: %s", e)


async def _handle_callback(cq: dict) -> None:
    """Handle inline keyboard callback — consent accept/decline."""
    import sqlalchemy
    cq_id = cq.get("id", "")
    data = cq.get("data", "")
    chat_id = str(cq.get("from", {}).get("id", ""))

    # ── Reply callbacks ──────────────────────────────────────────────────────
    if data.startswith("reply_task:"):
        task_id = int(data.split(":", 1)[1])
        await _answer_cq(cq_id, "")
        await _send_force_reply(chat_id, "✉️ Введите ваш комментарий к задаче:", task_id=task_id)
        return

    if data.startswith("reply_purchase:"):
        purchase_id = int(data.split(":", 1)[1])
        await _answer_cq(cq_id, "")
        await _send_force_reply(chat_id, "✉️ Введите ваш комментарий к закупке:", purchase_id=purchase_id)
        return

    # ── Purchase member consent ───────────────────────────────────────────────
    if data.startswith(("pm_consent_accept:", "pm_consent_decline:")):
        accept = data.startswith("pm_consent_accept:")
        parts = data.split(":", 1)[1].split(":")
        if len(parts) == 2:
            purchase_id, uid = int(parts[0]), int(parts[1])
            try:
                async with async_session() as db:
                    from app.models.purchase_event import PurchaseMember, PurchaseEvent
                    from app.models.user import User as UserModel
                    user = (await db.execute(
                        select(UserModel).where(UserModel.telegram_id == chat_id)
                    )).scalars().first()
                    if not user:
                        await _answer_cq(cq_id, "Пользователь не найден")
                        return
                    m = (await db.execute(
                        select(PurchaseMember).where(
                            PurchaseMember.purchase_id == purchase_id,
                            PurchaseMember.user_id == uid,
                        )
                    )).scalar_one_or_none()
                    if not m:
                        await _answer_cq(cq_id, "Запись не найдена")
                        return
                    if accept:
                        m.consent_pending = False
                        await db.commit()
                        await _answer_cq(cq_id, "✅ Принято!")
                    else:
                        added_by_id = m.added_by_id
                        await db.delete(m)
                        await db.commit()
                        # Notify who added
                        if added_by_id:
                            adder = await db.get(UserModel, added_by_id)
                            if adder:
                                from app.notifications import notify_user, _esc
                                await notify_user(adder,
                                    f"❌ <b>{user.full_name or user.username}</b> отклонил добавление в закупку #{purchase_id}"
                                )
                        await _answer_cq(cq_id, "❌ Отклонено")
            except Exception as e:
                logger.error("PM consent error: %s", e)
                await _answer_cq(cq_id, "Ошибка")
        return

    # ── Consent callbacks ────────────────────────────────────────────────────
    if not data.startswith(("consent_accept:", "consent_decline:")):
        await _answer_cq(cq_id, "")
        return

    accept = data.startswith("consent_accept:")
    task_id = int(data.split(":", 1)[1])

    try:
        async with async_session() as db:
            from app.models.task import Task, TaskAssignee
            from app.models.task_decline import TaskConsentDecline
            from app.models.user import User

            user = (await db.execute(
                select(User).where(User.telegram_id == chat_id)
            )).scalars().first()
            if not user:
                await _answer_cq(cq_id, "Пользователь не найден")
                return

            ta = (await db.execute(
                select(TaskAssignee).where(
                    TaskAssignee.task_id == task_id,
                    TaskAssignee.user_id == user.id,
                )
            )).scalar_one_or_none()
            if not ta:
                await _answer_cq(cq_id, "Задача не найдена")
                return

            task_obj = await db.get(Task, task_id)

            if accept:
                ta.consent_pending = False
                if task_obj:
                    db.add(TaskConsentDecline(
                        task_id=task_id, declined_user_id=user.id,
                        creator_id=task_obj.created_by_id, is_accepted=True,
                    ))
                    creator = await db.get(User, task_obj.created_by_id)
                    if creator:
                        from app.notifications import notify_user
                        await notify_user(creator,
                            f"✅ <b>{user.full_name or user.username}</b> принял задачу:\n"
                            f"<b>{task_obj.title}</b>"
                        )
                await db.commit()
                await _answer_cq(cq_id, "✅ Принято!")
            else:
                await db.execute(
                    sqlalchemy.delete(TaskAssignee).where(
                        TaskAssignee.task_id == task_id,
                        TaskAssignee.user_id == user.id,
                    )
                )
                if task_obj:
                    db.add(TaskConsentDecline(
                        task_id=task_id, declined_user_id=user.id,
                        creator_id=task_obj.created_by_id,
                    ))
                    creator = await db.get(User, task_obj.created_by_id)
                    if creator:
                        from app.notifications import notify_user
                        await notify_user(creator,
                            f"❌ <b>{user.full_name or user.username}</b> отклонил задачу:\n"
                            f"<b>{task_obj.title}</b>"
                        )
                await db.commit()
                await _answer_cq(cq_id, "❌ Отклонено")
    except Exception as e:
        logger.error("Callback handle error: %s", e)
        await _answer_cq(cq_id, "Ошибка")


async def _process_update(update: dict) -> None:
    """Process a single Telegram update — route reply to task comment."""
    callback_query = update.get("callback_query")
    if callback_query:
        await _handle_callback(callback_query)
        return

    message = update.get("message", {})
    text = message.get("text", "").strip()
    if not text:
        return

    reply_to = message.get("reply_to_message", {})
    reply_msg_id = reply_to.get("message_id")
    if not reply_msg_id:
        return

    chat_id = str(message.get("from", {}).get("id", ""))
    if not chat_id:
        return

    # ── Check purchase reply map (in-memory) ─────────────────────────────────
    purchase_id = _purchase_msg_map.get((chat_id, reply_msg_id))
    if purchase_id:
        try:
            async with async_session() as db:
                user = (await db.execute(
                    select(User).where(User.telegram_id == chat_id)
                )).scalars().first()
                if not user:
                    return
                from app.models.purchase_comment import PurchaseComment
                comment = PurchaseComment(
                    purchase_id=purchase_id,
                    user_id=user.id,
                    user_name=user.full_name or user.username,
                    text=f"[Telegram] {text}",
                )
                db.add(comment)
                await db.commit()
                logger.info("TG reply → purchase %d by %s", purchase_id, user.username)
        except Exception as e:
            logger.error("TG purchase reply error: %s", e)
        return

    # ── Check task reply map (DB) ─────────────────────────────────────────────
    try:
        async with async_session() as db:
            result = await db.execute(
                select(TelegramMessageMap.task_id)
                .where(
                    TelegramMessageMap.message_id == reply_msg_id,
                    TelegramMessageMap.chat_id == chat_id,
                )
            )
            task_id = result.scalar_one_or_none()
            if not task_id:
                return

            user = (await db.execute(
                select(User).where(User.telegram_id == chat_id)
            )).scalars().first()
            if not user:
                logger.info("TG reply from unknown chat_id=%s", chat_id)
                return

            comment = TaskComment(
                task_id=task_id,
                user_id=user.id,
                user_name=user.full_name or user.username,
                text=f"[Telegram] {text}",
            )
            db.add(comment)
            await db.commit()
            logger.info("TG reply → task %d by %s", task_id, user.username)

            try:
                from app.models.task import Task, TaskAssignee
                from sqlalchemy.orm import selectinload
                from app.notifications import notify_task_comment
                task = (await db.execute(
                    select(Task)
                    .options(selectinload(Task.assignees).selectinload(TaskAssignee.user))
                    .where(Task.id == task_id)
                )).scalar_one_or_none()
                if task:
                    await notify_task_comment(task, user.full_name or user.username, text)
            except Exception:
                pass
    except Exception as e:
        logger.error("TG process error: %s", e)


async def _poll_loop():
    """Long-polling loop for Telegram updates."""
    global _last_update_id
    if not TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_BOT_TOKEN not set, polling disabled")
        return

    # Delete webhook if any
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
    except Exception:
        pass

    logger.info("Telegram polling started")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": _last_update_id + 1}
            async with httpx.AsyncClient(timeout=35) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    await asyncio.sleep(5)
                    continue
                data = resp.json()
                for update in data.get("result", []):
                    _last_update_id = update["update_id"]
                    await _process_update(update)
        except Exception as e:
            logger.warning("TG poll error: %s", e)
            await asyncio.sleep(5)


def start_polling():
    """Start polling in background task. Call once at app startup."""
    global _polling_started
    if _polling_started:
        return
    _polling_started = True
    asyncio.create_task(_poll_loop())
