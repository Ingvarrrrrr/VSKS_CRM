"""
Waybill auto-numbering — Phase 30-PR1.

Генерирует номер путевого листа вида NN-MM/YYYY.
Порядковый номер NN обнуляется ежемесячно.
"""
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trip import Trip


async def generate_waybill_number(db: AsyncSession, dt: datetime = None) -> str:
    """Возвращает следующий номер вида NN-MM/YYYY для месяца dt (default = now).

    Алгоритм: ищет все путевые листы с number LIKE '%-MM/YYYY',
    берёт MAX(NN) и возвращает (MAX+1) с zero-padding до 2 знаков.
    Thread-safe при наличии UNIQUE constraint на trips.number.
    """
    if dt is None:
        dt = datetime.now()
    yyyy = dt.year
    mm = dt.month
    # SQL LIKE pattern для текущего месяца
    pattern = f"%-{mm:02d}/{yyyy}"
    res = await db.execute(
        select(Trip.number).where(Trip.number.like(pattern))
    )
    numbers = [n for n in res.scalars().all() if n]
    max_n = 0
    for num in numbers:
        m = re.match(r'^(\d+)-', num)
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                continue
    return f"{max_n + 1:02d}-{mm:02d}/{yyyy}"
