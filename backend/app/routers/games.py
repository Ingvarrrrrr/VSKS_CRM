"""Лидерборды мини-игр окна ожидания (duck/brick/tank/egg) — владелец,
30.10.2026. См. app/models/game_score.py для схемы и обоснования.

Правило №8 п.1-2: все пути за get_current_user (закрыто по умолчанию,
роутер не публичный — не добавлен в список исключений); identity — ТОЛЬКО
из токена (current_user), никогда из тела/query. Личный кабинет (аккаунт) —
org_id/контур current_user, не чужой id из запроса.

Глобальный список НЕ отдаёт fio/org/user_id — только nickname (или дефолт
«Игрок») и score (п. безопасности задания).
"""
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_org_filter, get_single_org_id
from app.database import get_db
from app.models.game_score import GameScore, GameProfile, GAME_IDS
from app.models.user import User

router = APIRouter(prefix="/api/games", tags=["games"])

DEFAULT_NICKNAME = "Игрок"
MAX_SCORE = 10_000_000
NICKNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9 _\-.]{2,24}$")

# Простая защита от спама POST /score с одного пользователя — не БД-таблица,
# процесс-локальный кэш «последний раз когда» хватает для цели (погасить
# дребезг кликов/автосабмитов, не полноценный rate-limiter).
_last_submit_at: dict[tuple[int, str], float] = {}
_RATE_LIMIT_SECONDS = 2.0


def _validate_game(game: str) -> str:
    if game not in GAME_IDS:
        raise HTTPException(status_code=400, detail="Неизвестная игра")
    return game


class ScoreIn(BaseModel):
    score: int
    nickname: Optional[str] = None

    @field_validator("score")
    @classmethod
    def _check_range(cls, v: int) -> int:
        if v < 0 or v > MAX_SCORE:
            raise ValueError("score вне допустимого диапазона")
        return v

    @field_validator("nickname")
    @classmethod
    def _check_nickname(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not NICKNAME_RE.match(v):
            raise ValueError(
                "Ник: 2-24 символа, буквы/цифры/пробел/._-"
            )
        return v


class NicknameIn(BaseModel):
    nickname: Optional[str] = None

    @field_validator("nickname")
    @classmethod
    def _check_nickname(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not NICKNAME_RE.match(v):
            raise ValueError(
                "Ник: 2-24 символа, буквы/цифры/пробел/._-"
            )
        return v


async def _account_org_ids(current_user: User) -> list[int]:
    """Список org_id «аккаунта» текущего пользователя для личного (не
    глобального) рейтинга — контур видимости, тот же источник, что везде
    (get_org_filter), а не только одна org."""
    ids = get_org_filter(current_user)
    if ids:
        return list(ids)
    single = get_single_org_id(current_user)
    if single:
        return [single]
    if current_user.org_id:
        return [current_user.org_id]
    return []


@router.post("/{game}/score")
async def submit_score(
    game: str,
    payload: ScoreIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = _validate_game(game)

    # 1. Если передан nickname, сохраняем/обновляем в GameProfile
    if payload.nickname:
        prof_res = await db.execute(
            select(GameProfile).where(GameProfile.user_id == current_user.id)
        )
        prof = prof_res.scalar_one_or_none()
        if prof is None:
            prof = GameProfile(user_id=current_user.id, nickname=payload.nickname)
            db.add(prof)
        else:
            prof.nickname = payload.nickname

    # 2. Аккаунт пользователя
    acc_id = get_single_org_id(current_user) or current_user.org_id

    # 3. Находим или создаем GameScore
    result = await db.execute(
        select(GameScore).where(
            GameScore.user_id == current_user.id, GameScore.game == game
        )
    )
    row = result.scalar_one_or_none()

    key = (current_user.id, game)
    now = time.monotonic()
    last = _last_submit_at.get(key)
    is_throttled = last is not None and (now - last) < _RATE_LIMIT_SECONDS

    if row is None:
        row = GameScore(
            user_id=current_user.id,
            account_id=acc_id,
            game=game,
            best_score=payload.score,
            plays=1,
        )
        db.add(row)
        _last_submit_at[key] = now
    else:
        if not is_throttled:
            row.plays = (row.plays or 0) + 1
            _last_submit_at[key] = now
        if payload.score > row.best_score:
            row.best_score = payload.score
        if row.account_id is None and acc_id is not None:
            row.account_id = acc_id

    await db.commit()

    best_result = await db.execute(
        select(GameScore).where(
            GameScore.user_id == current_user.id, GameScore.game == game
        )
    )
    my_row = best_result.scalar_one_or_none()
    best = my_row.best_score if my_row else 0

    rank_global = await _rank_for(db, game, best, account_ids=None)
    account_ids = await _account_org_ids(current_user)
    rank_account = await _rank_for(db, game, best, account_ids=account_ids)

    return {"best": best, "rank_account": rank_account, "rank_global": rank_global}


async def _rank_for(
    db: AsyncSession, game: str, best_score: int, account_ids: Optional[list[int]]
) -> int:
    """1-based место по best_score DESC (больше результатов с тем же score —
    делят место, считаем по числу строк СТРОГО лучше + 1)."""
    q = select(func.count()).select_from(GameScore).where(
        GameScore.game == game, GameScore.best_score > best_score
    )
    if account_ids is not None:
        if not account_ids:
            return 1
        q = q.where(GameScore.account_id.in_(account_ids))
    result = await db.execute(q)
    better_count = result.scalar() or 0
    return int(better_count) + 1


@router.get("/{game}/leaderboard")
async def get_leaderboard(
    game: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = _validate_game(game)

    account_ids = await _account_org_ids(current_user)

    # --- Аккаунт (компания): топ-10 по нику (ТОЛЬКО НИК, никакого ФИО!) -----
    account_rows: list = []
    if account_ids:
        q = (
            select(GameScore, GameProfile.nickname)
            .join(User, User.id == GameScore.user_id)
            .outerjoin(GameProfile, GameProfile.user_id == GameScore.user_id)
            .where(
                GameScore.game == game,
                GameScore.best_score > 0,
                (GameScore.account_id.in_(account_ids)) | (User.org_id.in_(account_ids)),
            )
            .order_by(GameScore.best_score.desc())
            .limit(10)
        )
        result = await db.execute(q)
        account_rows = result.all()

    account_list = [
        {
            "nickname": nickname or DEFAULT_NICKNAME,
            "fio": nickname or DEFAULT_NICKNAME,  # обратная совместимость (но содержит только ник!)
            "score": gs.best_score,
            "is_me": gs.user_id == current_user.id,
        }
        for gs, nickname in account_rows
    ]

    # --- Глобальный: топ-10 по нику (НЕ отдаём fio/org/user_id) --------------
    gq = (
        select(GameScore, GameProfile.nickname)
        .outerjoin(GameProfile, GameProfile.user_id == GameScore.user_id)
        .where(GameScore.game == game, GameScore.best_score > 0)
        .order_by(GameScore.best_score.desc())
        .limit(10)
    )
    gresult = await db.execute(gq)
    global_rows = gresult.all()
    global_list = [
        {
            "nickname": nickname or DEFAULT_NICKNAME,
            "score": gs.best_score,
            "is_me": gs.user_id == current_user.id,
        }
        for gs, nickname in global_rows
    ]

    # --- Моё лучшее + мой ник --------------------------------------------------
    my_result = await db.execute(
        select(GameScore).where(
            GameScore.user_id == current_user.id, GameScore.game == game
        )
    )
    my_row = my_result.scalar_one_or_none()
    my_best = my_row.best_score if my_row else 0

    profile_result = await db.execute(
        select(GameProfile).where(GameProfile.user_id == current_user.id)
    )
    my_profile = profile_result.scalar_one_or_none()
    my_nickname = my_profile.nickname if my_profile else None

    my_global_rank = (
        await _rank_for(db, game, my_best, account_ids=None)
        if (my_row and my_best > 0)
        else None
    )

    return {
        "me": {"best": my_best, "nickname": my_nickname or DEFAULT_NICKNAME},
        "account": account_list,
        "global": global_list,
        "my_global_rank": my_global_rank,
    }


@router.put("/nickname")
async def set_nickname(
    payload: NicknameIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GameProfile).where(GameProfile.user_id == current_user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = GameProfile(user_id=current_user.id, nickname=payload.nickname)
        db.add(row)
    else:
        row.nickname = payload.nickname
    await db.commit()
    return {"nickname": row.nickname or DEFAULT_NICKNAME}


@router.get("/nickname")
async def get_nickname(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GameProfile).where(GameProfile.user_id == current_user.id)
    )
    row = result.scalar_one_or_none()
    return {"nickname": (row.nickname if row else None) or DEFAULT_NICKNAME}
