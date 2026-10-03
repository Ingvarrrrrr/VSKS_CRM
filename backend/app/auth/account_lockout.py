"""Блокировка учётной записи после серии неверных паролей (подбор пароля).

Отдельный механизм от IP-лимита в app/auth/rate_limit.py (см. его докстринг):
тот — in-memory, по IP, общий лимит на процесс backend_a/backend_b по
отдельности. Этот — в БД, по конкретной учётной записи, общий для ОБЕИХ
реплик (счётчик живёт в users.*, а не в памяти процесса).

Правило №6 (один источник истины): все обновления счётчика — через функции
этого модуля, никому не плодить второй UPDATE users SET failed_login_count.

Атомарность
-----------
Инкремент — один SQL UPDATE ... RETURNING, НЕ read-modify-write в питоне:
при двух одновременных неверных попытках (round-robin на backend_a/backend_b)
каждая должна увеличить счётчик РОВНО на 1, без потери инкремента из-за двух
параллельных "прочитал 3 -> записал 4".
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.utils.email import send_account_locked_email

MAX_ATTEMPTS = 10
WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_remaining_minutes(user: User) -> Optional[int]:
    """None — не заблокирован. Иначе сколько минут осталось (округление вверх, минимум 1)."""
    locked_until = user.locked_until
    if not locked_until:
        return None
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    remaining = (locked_until - _now()).total_seconds()
    if remaining <= 0:
        return None
    return max(1, int(remaining // 60) + (1 if remaining % 60 else 0))


async def record_failed_password(db: AsyncSession, user: User) -> bool:
    """Регистрирует неверный пароль для СУЩЕСТВУЮЩЕГО пользователя.

    Если окно (15 мин от failed_login_first_at) истекло — счётчик начинается
    заново с 1. На MAX_ATTEMPTS-й неудаче подряд выставляет locked_until и
    сбрасывает счётчик. Возвращает True, если именно этим вызовом блокировка
    СРАБОТАЛА (вызывающий код должен отправить письмо-предупреждение).
    """
    now = _now()
    window_start = now - WINDOW
    result = await db.execute(
        text("""
            UPDATE users
            SET failed_login_count = CASE
                    WHEN failed_login_first_at IS NULL OR failed_login_first_at < :window_start
                        THEN 1
                    ELSE failed_login_count + 1
                END,
                failed_login_first_at = CASE
                    WHEN failed_login_first_at IS NULL OR failed_login_first_at < :window_start
                        THEN :now
                    ELSE failed_login_first_at
                END
            WHERE id = :user_id
            RETURNING failed_login_count
        """),
        {"window_start": window_start, "now": now, "user_id": user.id},
    )
    new_count = result.scalar_one()

    triggered = False
    if new_count >= MAX_ATTEMPTS:
        await db.execute(
            text("""
                UPDATE users
                SET locked_until = :locked_until,
                    failed_login_count = 0,
                    failed_login_first_at = NULL
                WHERE id = :user_id
            """),
            {"locked_until": now + LOCK_DURATION, "user_id": user.id},
        )
        triggered = True

    await db.commit()

    if triggered and user.email:
        # Ошибка отправки не должна ронять логин — send_account_locked_email
        # сама глотает исключения (см. app/utils/email.py), как и остальные
        # отправщики писем в проекте.
        await send_account_locked_email(user.email)

    return triggered


async def reset_login_lockout(db: AsyncSession, user: User) -> None:
    """Успешный вход — сбрасывает счётчик/окно/блокировку."""
    if not (user.failed_login_count or user.failed_login_first_at or user.locked_until):
        return
    await db.execute(
        text("""
            UPDATE users
            SET failed_login_count = 0, failed_login_first_at = NULL, locked_until = NULL
            WHERE id = :user_id
        """),
        {"user_id": user.id},
    )
    await db.commit()
