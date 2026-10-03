"""Версионирование JWT: смена пароля аннулирует все ранее выданные токены.

Каждая смена/сброс пароля инкрементирует users.token_version. JWT несёт
claim "tv" (проставляется в create_access_token на login/switch-org/
select-orgs — см. app/routers/auth.py). get_current_user (app/auth/jwt.py)
сверяет claim с текущим token_version и отклоняет токен, если они разошлись.

Токен без claim "tv" (выпущенный до этой задачи) считается tv=0 — значит
продолжает работать, пока владелец не сменит пароль (после чего
token_version станет >=1 и старый токен перестанет проходить).

Правило №6: единственное место инкремента — вызывать bump_token_version
отсюда из каждого места, где меняется password_hash, а не писать свой UPDATE.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def bump_token_version(db: AsyncSession, user_id: int) -> None:
    """Инкремент token_version. Не коммитит — вызывающий код коммитит вместе
    с остальными изменениями той же транзакции (смена password_hash и т.п.)."""
    await db.execute(
        text("UPDATE users SET token_version = token_version + 1 WHERE id = :user_id"),
        {"user_id": user_id},
    )
