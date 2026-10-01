"""Гейт «прямая правка / корректировка / запрещено» для утверждённой субсидии
(волна 1, владелец, 2026-10-02).

Утверждённую (Subsidy.status == 'approved') субсидию правят:
  - обладатели subsidy.edit (или superadmin) — напрямую, как и раньше;
  - обладатели subsidy.correct БЕЗ subsidy.edit — правка должна пойти через
    корректировку (see app.models.subsidy_revision) и дождаться проверки;
  - остальные — только просмотр.
Черновик (status != 'approved') этого не касается — там действуют обычные
правила subsidy.edit, функция всегда отдаёт 'direct'.

ИНТЕРФЕЙС ЗАФИКСИРОВАН — по нему параллельно пишут другие исполнители волны 1,
сигнатуры трогать нельзя:
    def revision_enabled() -> bool
    async def subsidy_edit_mode(db, user, subsidy_id) -> str
    async def assert_direct_edit(db, user, subsidy_id) -> None

Пока SUBSIDY_REVISION_ENABLED не включён (по умолчанию выключен), гейт всегда
возвращает 'direct' — поведение не меняется относительно текущего кода.
Правило №6: право пользователя проверяется через уже существующий
has_org_key() (app.auth.permissions) — здесь НЕ заводится второй механизм
проверки прав.
"""
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

MODE_DIRECT = "direct"
MODE_REVISION = "revision"
MODE_FORBIDDEN = "forbidden"


def revision_enabled() -> bool:
    """Читается при КАЖДОМ вызове (не кэшируется) — флаг может переключаться
    без перезапуска процесса в тестах/проде."""
    return os.getenv("SUBSIDY_REVISION_ENABLED", "0") == "1"


async def subsidy_edit_mode(db: AsyncSession, user, subsidy_id: "int | None") -> str:
    """'direct' | 'revision' | 'forbidden' для правки данной субсидии данным
    пользователем. subsidy_id=None, флаг выключен, субсидия не найдена или не
    'approved' -> всегда 'direct' (текущее поведение, ничего не меняется)."""
    if not revision_enabled():
        return MODE_DIRECT
    if subsidy_id is None:
        return MODE_DIRECT
    if user is None:
        return MODE_FORBIDDEN

    from app.auth.permissions import has_org_key
    from app.models.subsidy import Subsidy

    if getattr(user, "role", None) == "superadmin":
        return MODE_DIRECT

    subsidy = (await db.execute(
        select(Subsidy).where(Subsidy.id == subsidy_id)
    )).scalar_one_or_none()
    if subsidy is None or subsidy.status != "approved":
        return MODE_DIRECT

    if await has_org_key(user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy_id):
        return MODE_DIRECT
    if await has_org_key(user, db, subsidy.org_id, "subsidy.correct", subsidy_id=subsidy_id):
        return MODE_REVISION
    return MODE_FORBIDDEN


async def assert_direct_edit(db: AsyncSession, user, subsidy_id: "int | None") -> None:
    """Бросает, если прямая правка недоступна. 'revision' -> 409 (правьте через
    корректировку); 'forbidden' -> 403. 'direct' -> не бросает (пропускает)."""
    mode = await subsidy_edit_mode(db, user, subsidy_id)
    if mode == MODE_DIRECT:
        return
    if mode == MODE_REVISION:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subsidy_revision_required",
                "message": "Субсидия утверждена: ваши правки идут через корректировку и ждут проверки",
            },
        )
    raise HTTPException(
        status_code=403,
        detail={
            "code": "subsidy_correct_required",
            "message": "Нет права корректировать утверждённую субсидию — нужна галочка «Корректировать субсидию»",
        },
    )
