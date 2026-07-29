from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.okpd2_code import Okpd2Code

router = APIRouter(prefix="/api/okpd2", tags=["okpd2"])


@router.get("")
async def search_okpd2(
    q: str = Query(..., description="Строка поиска (код или название)"),
    limit: int = Query(default=50, le=100, ge=1),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Поиск по справочнику ОКПД2.

    Если q начинается с цифры — ищем по коду (prefix LIKE).
    Иначе — по названию (ILIKE substring).
    Минимальная длина q: 2 символа.
    """
    q = q.strip()
    if len(q) < 2:
        return []

    if q[0].isdigit():
        # Search by code prefix
        stmt = (
            select(Okpd2Code)
            .where(Okpd2Code.code.like(q + "%"))
            .order_by(Okpd2Code.code)
            .limit(limit)
        )
    else:
        # Search by name substring (case-insensitive)
        stmt = (
            select(Okpd2Code)
            .where(func.lower(Okpd2Code.name).like("%" + q.lower() + "%"))
            .order_by(Okpd2Code.code)
            .limit(limit)
        )

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [{"code": r.code, "name": r.name, "section": r.section} for r in rows]
