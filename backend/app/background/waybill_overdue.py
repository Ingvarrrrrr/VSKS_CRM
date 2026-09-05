"""Phase 30: почасовая проверка просроченных путевых листов.

Перенесено 1:1 из app/__init__.py._waybill_overdue_loop при разрезании
монолитного файла на модули (Правило №5). Логика не менялась.

⚠ Побочный эффект переноса: в исходнике эта функция вызывала
`logging.getLogger(__name__)` в блоке except БЕЗ собственного `import logging`
в области видимости — работало только потому, что `lifespan()` в
app/__init__.py делал `import logging` первым statement, а Python делает имя
локальным для ВСЕЙ функции lifespan (см. комментарий там же), и эта функция
была объявлена в том же модуле ДО lifespan, так что действовал уже
МОДУЛЬНЫЙ `logging` (импортированный где-то раньше в файле) — то есть
реально это не было гарантированным поведением, а скрытым NameError,
если бы модульного импорта logging не было к моменту первого вызова.
Теперь модуль имеет собственный `import logging` на верхнем уровне —
латентный риск устранён явно.
"""
import asyncio
import logging
from datetime import datetime, timezone


async def _waybill_overdue_loop():
    """Phase 30: Каждый час — путевые листы с date_end < NOW() AND status NOT IN (closed/overdue) → status=overdue."""
    while True:
        try:
            from app.database import async_session as _async_session
            from sqlalchemy import update, text as _text
            from app.models.trip import Trip
            from datetime import datetime, timezone
            async with _async_session() as db:
                now = datetime.now(timezone.utc)
                res = await db.execute(
                    update(Trip)
                    .where(
                        Trip.date_end.isnot(None),
                        Trip.date_end < now,
                        Trip.status.notin_(['closed', 'overdue', 'rendered']),
                    )
                    .values(status='overdue')
                    .returning(Trip.id)
                )
                updated = list(res.scalars().all())
                if updated:
                    logging.getLogger(__name__).info(
                        f"Waybill overdue: {len(updated)} путевок переведено в overdue"
                    )
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.getLogger(__name__).warning(f"Waybill overdue loop error (non-fatal): {e}")
        await asyncio.sleep(3600)  # 1 час
