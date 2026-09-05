"""Lifespan приложения: запуск фоновых задач + идемпотентные миграции/сиды
при старте, их остановка при выключении.

Перенесено из app/__init__.py.lifespan (было 1400 строк одной функции) при
разрезании монолитного файла на модули (Правило №5 — модульность кода).
Порядок вызовов и границы try/except сохранены 1:1, блоки сгруппированы по
смыслу в отдельные модули:
  - legacy_ddl.run()       — идемпотентные ALTER/CREATE TABLE, check_schema._ensure_*
  - permission_seeds.run() — идемпотентные сиды PermissionTab/Action/RolePermission
  - backfills.run()        — идемпотентные бэкфиллы данных
  - smoke_and_seeds.run()  — smoke-render docx-шаблонов + разовые xlsx-сиды

Группировка по категориям (а не построчный порядок исходника) безопасна:
все проверенные межблочные зависимости (например, ALTER purchase_items.
receipt_id из legacy_ddl ДОЛЖЕН отработать до fuzzy-link бэкфилла в
backfills) идут в направлении legacy_ddl → backfills, что совпадает с
порядком вызова ниже.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import ensure_phase22_columns
from app.background.deadline_reminders import _deadline_reminder_loop
from app.background.vehicle_alerts import _vehicle_alerts_task_creator
from app.background.waybill_overdue import _waybill_overdue_loop
from app.startup import legacy_ddl, permission_seeds, backfills, smoke_and_seeds


@asynccontextmanager
async def lifespan(app_: FastAPI):
    task = asyncio.create_task(_deadline_reminder_loop())
    # Phase 29 D-17: daily vehicle expiry alerts
    try:
        task_vehicle_alerts = asyncio.create_task(_vehicle_alerts_task_creator())
    except Exception as _e_va:
        logging.getLogger(__name__).warning(f"vehicle_alerts task start skipped (non-fatal): {_e_va}")
        task_vehicle_alerts = None
    # Phase 30: hourly waybill overdue auto-detection
    try:
        task_waybill_overdue = asyncio.create_task(_waybill_overdue_loop())
    except Exception as _e_wo:
        logging.getLogger(__name__).warning(f"waybill_overdue task start skipped: {_e_wo}")
        task_waybill_overdue = None
    # Start Telegram bot polling for reply-to-comment routing
    from app.routers.telegram_webhook import start_polling as _start_tg_polling
    _start_tg_polling()

    # Phase 22: idempotent ALTER для subsidies — добавить basis_doc_number/date
    await ensure_phase22_columns()

    await legacy_ddl.run()
    await permission_seeds.run()
    await backfills.run()
    await smoke_and_seeds.run()

    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if task_vehicle_alerts is not None:
        task_vehicle_alerts.cancel()
        try:
            await task_vehicle_alerts
        except asyncio.CancelledError:
            pass
    if task_waybill_overdue is not None:
        task_waybill_overdue.cancel()
        try:
            await task_waybill_overdue
        except asyncio.CancelledError:
            pass
