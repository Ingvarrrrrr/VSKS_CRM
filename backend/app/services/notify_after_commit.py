"""Отложенная отправка уведомлений до фактического коммита транзакции.

QA-находка (05.10.2026): app/services/purchase_payments.py::
_request_paid_confirmation слал notify_purchase_paid_confirmation_requested
сразу после db.flush() — ДО того, как вызывающий код реально закоммитил
транзакцию. Для большинства вызывающих (прямой confirm одной закупки) разницы
не видно — commit идёт следом почти сразу. Но:
  - импорт выписки (app/routers/bank_statements.py) крутит
    recompute_if_now_executed (app/services/bank_payment_dedup.py) ВНУТРИ
    цикла по строкам, коммитит ОДИН раз в конце — уведомление уходило
    согласующему, даже если импорт потом упадёт на более поздней строке и
    откатит всё;
  - app/routers/purchase_paid_confirmations.py::reject вызывает
    recompute_purchase_payments ДО своего финального commit — тот же риск.

queue_after_commit(db, coro_factory) — ОДНА точка: откладывает отправку до
события SQLAlchemy `after_commit` на реальной (sync) сессии под AsyncSession
(session.sync_session — тот же приём, что и event-хуки в
app/models/purchase.py::_assign_purchase_registry_number). Если транзакция
вместо коммита откатывается (after_rollback / after_soft_rollback — второе
бьёт и по откату SAVEPOINT, см. app/routers/purchase_paid_confirmations.py::
_simulate_confirm_chain, которое НЕ должно слать уведомления из сухого
прогона) — очередь на этой сессии просто отбрасывается, ничего не уходит.

coro_factory — ОБЯЗАН быть вызываемым без аргументов и возвращать ЕЩЁ НЕ
запущенную корутину (`lambda: notify_user(...)`, НЕ сам `notify_user(...)`)
— иначе корутина создастся (и SQLAlchemy привяжет her к текущему event loop)
раньше, чем станет известно, нужна ли она вообще.

Отправка из after_commit — через asyncio.create_task (тот же обработчик
исключений, что и обычный прямой await: notifications.py._send_telegram/
_send_max сами ловят Exception и только логируют — не роняют ни вызывающего,
ни тем более фоновую задачу)."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

logger = logging.getLogger(__name__)

_QUEUE_KEY = "notify_after_commit_queue"
_ATTACHED_KEY = "notify_after_commit_listeners_attached"


def queue_after_commit(db, coro_factory: Callable[[], Coroutine]) -> None:
    """Поставить coro_factory() в очередь — выполнится фоновой задачей ПОСЛЕ
    того, как сессия db реально закоммитит текущую транзакцию. Откат
    (полный или SAVEPOINT) очередь очищает — отправки не будет."""
    sync_session = db.sync_session
    queue = sync_session.info.setdefault(_QUEUE_KEY, [])
    queue.append(coro_factory)
    _ensure_listeners(sync_session)


def _ensure_listeners(sync_session) -> None:
    if sync_session.info.get(_ATTACHED_KEY):
        return
    sync_session.info[_ATTACHED_KEY] = True

    from sqlalchemy import event

    def _flush_queue_after_commit(session) -> None:
        queue = session.info.pop(_QUEUE_KEY, [])
        for factory in queue:
            try:
                asyncio.create_task(factory())
            except Exception:
                logger.warning("queue_after_commit: failed to schedule notification", exc_info=True)

    def _drop_queue_on_rollback(session) -> None:
        session.info.pop(_QUEUE_KEY, None)

    def _drop_queue_on_soft_rollback(session, previous_transaction) -> None:
        session.info.pop(_QUEUE_KEY, None)

    event.listen(sync_session, "after_commit", _flush_queue_after_commit)
    event.listen(sync_session, "after_rollback", _drop_queue_on_rollback)
    # after_soft_rollback — срабатывает и на откате SAVEPOINT (begin_nested),
    # которого after_rollback не видит (тот только про настоящий ROLLBACK) —
    # см. app/routers/purchase_paid_confirmations.py::_simulate_confirm_chain.
    # Сигнатура этого события несёт ВТОРОЙ позиционный аргумент (previous_transaction).
    event.listen(sync_session, "after_soft_rollback", _drop_queue_on_soft_rollback)
