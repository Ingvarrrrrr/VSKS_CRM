"""simulate()/revision_author_for() + общие хелперы чтения op/after, которые
нужны и apply_ops (subsidy_revision_apply.py), и check_floor/compute_balance
(subsidy_revision_floor.py), и preview (subsidy_revision_preview.py). Вынесено
из subsidy_revision_ops.py (ПРАВИЛО №5 — тот файл подходил к 500 строкам);
реэкспортировано оттуда (см. импорт в subsidy_revision_ops.py), поэтому
`ops_svc.simulate`/`ops_svc._effective_after`/`ops_svc._op_attr` продолжают
работать для существующих вызывающих мест и тестов.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_revision import SubsidyRevision, SubsidyRevisionOp


def _effective_after(op, reviewer_overrides: dict) -> dict:
    """op — либо ORM SubsidyRevisionOp, либо dict того же формата (transient,
    только для preview). reviewer_overrides — {op_id: {...}} с фронта
    /preview, подменяет значения для ЕЩЁ не сохранённого решения проверяющего
    (reviewer_after в БД пишется только в decide_and_apply)."""
    if isinstance(op, SubsidyRevisionOp):
        override = reviewer_overrides.get(op.id)
        if override:
            merged = dict(op.after or {})
            merged.update(override)
            return merged
        if op.reviewer_after:
            return dict(op.reviewer_after)
        return dict(op.after or {})
    return dict(op.get("after") or {})


def _op_attr(op, name, default=None):
    if isinstance(op, SubsidyRevisionOp):
        return getattr(op, name, default)
    return op.get(name, default)


async def simulate(
    db: AsyncSession, revision: SubsidyRevision,
    accepted_op_ids: Optional[list[int]] = None,
    reviewer_overrides: Optional[dict] = None,
    extra_ops: Optional[list[dict]] = None,
) -> dict:
    """Применяет черновик/принятую часть корректировки ВНУТРИ SAVEPOINT и
    ВСЕГДА откатывает его (см. nested.rollback() ниже — безусловно, независимо
    от того, были ли у apply_ops ошибки: они собраны в result["problems"], а
    не бросаются), ничего не должна менять в БД по-настоящему. Возвращает
    результат apply_ops (ref_map/applied/problems ТОЛЬКО от самого apply —
    без check_floor/compute_balance). Приёмка 02.10.2026: POST /submit больше
    НЕ зовёт эту функцию саму по себе (она не знает порог «не ниже
    законтрактованного») — submit_revision делает ПОЛНЫЙ /preview
    (subsidy_revision_preview.preview, который сам зовёт apply_ops+check_floor+
    compute_balance), тот же путь, что и GET /preview (ПРАВИЛО №6, один
    источник проверки). simulate() остаётся отдельной лёгкой функцией для
    мест, которым нужен только факт применимости пачки (см.
    test_simulate_does_not_persist_changes).
    """
    # Локальные импорты — избегают цикла модулей (apply.py импортирует ИЗ
    # subsidy_revision_ops.py, который реэкспортирует ИЗ этого модуля).
    from app.services.subsidy_revision_apply import apply_ops
    from app.services.subsidy_revision_ops import load_ops

    ops = await load_ops(db, revision.id)
    if accepted_op_ids is not None:
        accepted_set = set(accepted_op_ids)
        ops = [o for o in ops if o.id in accepted_set]
    full_ops: list = list(ops) + list(extra_ops or [])

    nested = await db.begin_nested()
    try:
        result = await apply_ops(
            db, await revision_author_for(db, revision), revision.subsidy_id, full_ops,
            reviewer_overrides=reviewer_overrides, source_ref=revision.id, create_version=False,
        )
    finally:
        await nested.rollback()
    return result


async def revision_author_for(db: AsyncSession, revision: SubsidyRevision):
    """apply_ops пишет source_ref/author и проверяет право feo_categories
    (user.org_id) — внутри SAVEPOINT предпросмотра используется НАСТОЯЩИЙ
    автор, не проверяющий. Фолбэк-заглушка — только если автор удалён."""
    from app.models.user import User
    author = await db.get(User, revision.author_id) if revision.author_id else None
    if author is not None:
        return author

    class _Stub:
        def __init__(self, uid):
            self.id = uid
            self.full_name = None
            self.username = f"user:{uid}"
            self.role = None
            self.org_id = None
    return _Stub(revision.author_id)
