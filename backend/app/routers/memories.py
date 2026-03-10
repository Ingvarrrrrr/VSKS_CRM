from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.memory import Memory
from app.schemas.schemas import MemoryCreate, MemoryOut
from typing import List

router = APIRouter(prefix="/api/memories", tags=["memories"])

@router.get("/", response_model=List[MemoryOut])
async def list_memories(
    q: str = "",
    db: AsyncSession = Depends(get_db)
):
    """Поиск и список всех заметок"""
    if q:
        # Поиск по title, problem, solution, tags
        search = f"%{q}%"
        stmt = select(Memory).where(
            or_(
                Memory.title.ilike(search),
                Memory.problem.ilike(search),
                Memory.solution.ilike(search),
                Memory.tags.ilike(search)
            )
        ).order_by(Memory.is_pinned.desc(), Memory.updated_at.desc())
    else:
        stmt = select(Memory).order_by(Memory.is_pinned.desc(), Memory.updated_at.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory

@router.post("/", response_model=MemoryOut)
async def create_memory(
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db)
):
    db_memory = Memory(**memory.dict())
    db.add(db_memory)
    await db.commit()
    await db.refresh(db_memory)
    return db_memory

@router.put("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: int,
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    db_memory = result.scalar_one_or_none()
    if not db_memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    for key, value in memory.dict().items():
        setattr(db_memory, key, value)
    
    await db.commit()
    await db.refresh(db_memory)
    return db_memory

@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    await db.delete(memory)
    await db.commit()
    return {"message": "Memory deleted"}
