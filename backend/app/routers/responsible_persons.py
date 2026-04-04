from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.responsible_person import ResponsiblePerson
from app.models.subsidy import Subsidy
from app.schemas.schemas import ResponsiblePersonCreate, ResponsiblePersonOut
from app.auth.jwt import get_current_user
from typing import List

router = APIRouter(prefix="/api/subsidies", tags=["responsible-persons"])


async def _get_subsidy_or_404(sid: int, db: AsyncSession) -> Subsidy:
    result = await db.execute(select(Subsidy).where(Subsidy.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    return s


@router.get("/{sid}/responsible-persons", response_model=List[ResponsiblePersonOut])
async def list_responsible_persons(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    result = await db.execute(
        select(ResponsiblePerson)
        .where(ResponsiblePerson.subsidy_id == sid, ResponsiblePerson.is_active == True)
        .order_by(ResponsiblePerson.full_name)
    )
    return result.scalars().all()


@router.post("/{sid}/responsible-persons", response_model=ResponsiblePersonOut)
async def create_responsible_person(
    sid: int,
    body: ResponsiblePersonCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    person = ResponsiblePerson(subsidy_id=sid, full_name=body.full_name, position=body.position)
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{sid}/responsible-persons/{pid}")
async def delete_responsible_person(
    sid: int,
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(ResponsiblePerson).where(
            ResponsiblePerson.id == pid, ResponsiblePerson.subsidy_id == sid
        )
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(404, "Не найден")
    person.is_active = False
    await db.commit()
    return {"ok": True}
