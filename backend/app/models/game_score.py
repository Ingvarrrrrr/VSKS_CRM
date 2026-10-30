"""Таблицы счёта мини-игр окна ожидания (duck/brick/tank/egg, см.
frontend/src/components/games/gameRegistry.ts) — задача владельца, 30.10.2026:
личный рекорд внутри аккаунта (org_id — тот же ключ аренды, что везде в
проекте, см. app/auth/jwt.py::get_single_org_id/current_user.org_id) и в
общем (глобальном) рейтинге по всем аккаунтам.

GameScore — ОДИН лучший результат на пользователя на игру (UNIQUE), не
история попыток: только max(score) нужен для обеих таблиц лидеров, историю
никто не просил и нигде не читает (Правило №6 — не плодить лишнего).

GameProfile — отдельная маленькая таблица под ник для глобального рейтинга
(не колонка в users — правка users.py требует сопровождать все её места
использования, а ник — опциональная деталь только этой фичи). Публичный ник
НЕ привязан к ФИО/аккаунту напрямую с точки зрения глобального списка (роутер
не отдаёт туда fio/org/user_id — см. app/routers/games.py).
"""
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base

GAME_IDS = ("duck", "brick", "tank", "egg")


class GameScore(Base):
    __tablename__ = "game_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "game", name="uq_game_score_user_game"),
        CheckConstraint(
            "game IN ('duck', 'brick', 'tank', 'egg')",
            name="ck_game_score_game_id",
        ),
        CheckConstraint("best_score >= 0", name="ck_game_score_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Снимок аккаунта (org_id) на момент первой записи — тот же тенант-ключ,
    # что в user_org_access/current_user.org_id. Nullable: у пользователя
    # org_id тоже nullable (см. app/models/user.py).
    account_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    game = Column(String(16), nullable=False)
    best_score = Column(Integer, nullable=False, default=0)
    plays = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GameProfile(Base):
    """Публичный ник для глобального рейтинга (owner, может быть null —
    тогда в глобальном списке показывается «Игрок», см. роутер)."""

    __tablename__ = "game_profiles"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    nickname = Column(String(24), nullable=True)
