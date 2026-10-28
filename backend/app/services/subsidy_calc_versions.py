"""subsidy_calc_versions.py — чтение отметок изменений (версий) по субсидиям
для кросс-запросного кэша compute_feo_plan_tree (владелец, 28.10.2026, замер
прода: GET /api/purchases/?with_feo_excess=true 3,35с, compute_feo_plan_tree
1,64с на 11 субсидий — recompute на каждый запрос, пока данные не менялись).

ПЕРЕДЕЛКА (ревью координатора, 28.10.2026, ДО применения на проде): версия —
НЕ отдельная UPDATE-строка на субсидию (та схема держала row lock до конца
транзакции и была риском deadlock при переносе данных между субсидиями в
разном порядке у двух параллельных транзакций), а MAX(id) в append-only
журнале subsidy_calc_changes/account_contour_changes (миграция
f5a7c9e1b3d5, см. её докстринг за полным списком триггеров/таблиц).
INSERT новой строки не блокирует НИКОГО — это и была цель переделки.

ПРАВИЛО №6: единственное место, которое читает subsidy_calc_changes/
account_contour_changes — кэш (feo_plan_tree_cache.py/account_contour_cache.py)
зовёт ТОЛЬКО функции этого модуля, не пишет свой SQL."""
import time
from typing import Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

GLOBAL_SUBSIDY_VERSION_ROW = 0

# Throttle чистки (владелец: «лёгкий DELETE, не обязательно на каждом
# запросе» — раз в час на процесс достаточно, таблица растёт медленно:
# одна строка на STATEMENT, не на отдельную запись). Module-level — общий на
# все запросы этого процесса, НЕ per-request (иначе чистка гонялась бы на
# каждый HTTP-запрос, тот же антипаттерн, который переделка должна убрать).
_CLEANUP_INTERVAL_SECONDS = 3600.0
_last_subsidy_cleanup_at = 0.0
_last_contour_cleanup_at = 0.0


async def _cleanup_subsidy_calc_changes() -> None:
    """Удаляет строки subsidy_id, для которых уже есть более новая строка
    того же subsidy_id — журнал не растёт бесконечно. На СВОЁМ отдельном
    соединении (не на db_session вызывающего запроса!) — commit() чужой,
    возможно ещё не завершённой транзакции запроса был бы опасным побочным
    эффектом; DELETE живёт в собственной короткой транзакции и не блокирует
    параллельные INSERT в журнал дольше обычной короткой DELETE."""
    from app.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM subsidy_calc_changes a WHERE EXISTS ("
            "  SELECT 1 FROM subsidy_calc_changes b"
            "  WHERE b.subsidy_id = a.subsidy_id AND b.id > a.id"
            ")"
        ))


async def _cleanup_account_contour_changes() -> None:
    """То же для account_contour_changes (своё соединение, см. docstring
    _cleanup_subsidy_calc_changes) — там одно "измерение" (нет subsidy_id),
    оставляем только самую свежую строку."""
    from app.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM account_contour_changes a WHERE EXISTS ("
            "  SELECT 1 FROM account_contour_changes b WHERE b.id > a.id"
            ")"
        ))


async def get_subsidy_versions(db: AsyncSession, subsidy_ids: Iterable[int]) -> dict[int, int]:
    """{subsidy_id: version} для каждого id из `subsidy_ids` + глобальная
    строка (id=0) — ВСЕГДА включена (входит в ключ кэша каждой субсидии).
    version = MAX(id) среди строк subsidy_calc_changes этой субсидии (0, если
    строк ещё нет — не должно случаться после миграции, см. INSERT ... SELECT
    там, но на всякий случай)."""
    global _last_subsidy_cleanup_at
    ids = sorted({int(x) for x in subsidy_ids} | {GLOBAL_SUBSIDY_VERSION_ROW})
    result = {sid: 0 for sid in ids}
    stmt = text(
        "SELECT subsidy_id, max(id) FROM subsidy_calc_changes "
        "WHERE subsidy_id IN :ids GROUP BY subsidy_id"
    ).bindparams(bindparam("ids", expanding=True))
    rows = (await db.execute(stmt, {"ids": ids})).all()
    for sid, ver in rows:
        result[int(sid)] = int(ver)

    now = time.monotonic()
    if now - _last_subsidy_cleanup_at > _CLEANUP_INTERVAL_SECONDS:
        _last_subsidy_cleanup_at = now
        await _cleanup_subsidy_calc_changes()
    return result


async def get_account_contour_version(db: AsyncSession) -> int:
    """Версия глобального «контурного» счётчика — MAX(id) в
    account_contour_changes, бампается триггером ТОЛЬКО на organizations
    (единственная таблица, которую реально читает
    compute_account_contour_org_ids — см. докстринг миграции f5a7c9e1b3d5)."""
    global _last_contour_cleanup_at
    row = (await db.execute(
        text("SELECT max(id) FROM account_contour_changes")
    )).first()
    version = int(row[0]) if row and row[0] is not None else 0

    now = time.monotonic()
    if now - _last_contour_cleanup_at > _CLEANUP_INTERVAL_SECONDS:
        _last_contour_cleanup_at = now
        await _cleanup_account_contour_changes()
    return version
