from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.contractor import Contractor
from app.schemas.schemas import (
    SubsidyCreate, SubsidyOut,
    SubsidyContractorOverrideCreate, SubsidyContractorOverrideOut,
)
from app.auth.jwt import get_current_user, get_org_filter, get_single_org_id
from app.models.user import User
from typing import List

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


async def calculate_budget_from_categories(db: AsyncSession, subsidy_id: int) -> float:
    """
    Рекурсивный подсчёт бюджета из ФЭО-дерева:
    - Листовой узел (нет детей): берём его budget
    - Родительский узел: если у детей есть бюджеты → сумма детей (рекурсивно)
                         если ни у одного ребёнка нет → свой budget (ручной)
    Итог = сумма по всем корневым (level-1) узлам.
    """
    stmt = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    result = await db.execute(stmt)
    all_categories = result.scalars().all()

    if not all_categories:
        return 0.0

    by_id = {c.id: c for c in all_categories}
    children_map: dict = {}
    for c in all_categories:
        children_map.setdefault(c.id, [])
        if c.parent_id and c.parent_id in by_id:
            children_map.setdefault(c.parent_id, []).append(c)

    def _calc_node(cat) -> float:
        kids = children_map.get(cat.id, [])
        if not kids:
            return float(cat.budget) if cat.budget is not None and cat.budget > 0 else 0.0
        child_sum = sum(_calc_node(k) for k in kids)
        if child_sum > 0:
            return child_sum
        return float(cat.budget) if cat.budget is not None and cat.budget > 0 else 0.0

    roots = [c for c in all_categories if c.level == 1]
    return sum(_calc_node(r) for r in roots)


@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q)
    subsidies = result.scalars().all()

    out = []
    for s in subsidies:
        calc = await calculate_budget_from_categories(db, s.id)
        s.calculated_budget = calc
        # Синхронизируем budget с calculated_budget если ФЭО заполнено
        if calc > 0 and s.budget != calc:
            s.budget = calc

        d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
        d["calculated_budget"] = calc
        d["feo_filled"] = calc > 0
        d["feo_budget_total"] = calc
        # contractor info
        if s.contractor_id:
            from app.models.contractor import Contractor
            contractor = await db.get(Contractor, s.contractor_id)
            d["contractor_name"] = contractor.name if contractor else None
            d["contractor_inn"] = contractor.inn if contractor else None
        else:
            d["contractor_name"] = None
            d["contractor_inn"] = None
        out.append(d)

    await db.commit()
    return out

@router.get("/{subsidy_id}", response_model=SubsidyOut)
async def get_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    calc = await calculate_budget_from_categories(db, subsidy.id)
    subsidy.calculated_budget = calc
    if calc > 0 and subsidy.budget != calc:
        subsidy.budget = calc
    await db.commit()

    d = {c.name: getattr(subsidy, c.name) for c in subsidy.__table__.columns}
    d["calculated_budget"] = calc
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = calc
    if subsidy.contractor_id:
        contractor = await db.get(Contractor, subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.post("/", response_model=SubsidyOut)
async def create_subsidy(
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = subsidy.dict()
    data['org_id'] = get_single_org_id(current_user) or current_user.org_id
    db_subsidy = Subsidy(**data)
    db.add(db_subsidy)
    await db.commit()
    await db.refresh(db_subsidy)

    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = 0.0
    d["feo_filled"] = False
    d["feo_budget_total"] = 0.0
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.put("/{subsidy_id}", response_model=SubsidyOut)
async def update_subsidy(
    subsidy_id: int,
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    for key, value in subsidy.dict().items():
        setattr(db_subsidy, key, value)

    calc = await calculate_budget_from_categories(db, subsidy_id)
    db_subsidy.calculated_budget = calc
    await db.commit()
    await db.refresh(db_subsidy)

    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = calc
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = calc
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # Check for linked purchases
    from app.models.purchase import Purchase
    p_count = await db.scalar(
        select(Purchase).where(Purchase.subsidy_id == subsidy_id).limit(1)
    )
    if p_count:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить субсидию: есть связанные закупки. Сначала удалите или перенесите их."
        )

    # Delete linked wishes
    from sqlalchemy import text
    await db.execute(text("DELETE FROM wishes WHERE subsidy_id = :sid"), {"sid": subsidy_id})

    # Cascade delete FEO categories (all levels, bottom-up by level desc)
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.level.desc())
    )).scalars().all()
    for cat in cats:
        await db.delete(cat)

    await db.delete(db_subsidy)
    await db.commit()
    return {"message": "Субсидия удалена"}


# ── Per-subsidy contractor override endpoints ──

@router.get("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def get_contractor_override(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    if not override:
        # Return base contractor data as initial override
        contractor = await db.get(Contractor, subsidy.contractor_id)
        if not contractor:
            raise HTTPException(404, "Контрагент не найден")
        return {
            "id": 0,
            "subsidy_id": subsidy_id,
            "contractor_id": subsidy.contractor_id,
            "signatory": contractor.signatory,
            "signatory_basis": contractor.signatory_basis,
            "address": contractor.address,
            "postal_address": contractor.postal_address,
            "bank_details": contractor.bank_details,
            "settlement_account": contractor.settlement_account,
            "bank_name": contractor.bank_name,
            "bik": contractor.bik,
            "correspondent_account": contractor.correspondent_account,
            "contact_person": contractor.contact_person,
            "phone": contractor.phone,
            "email": contractor.email,
        }
    return override


@router.put("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def upsert_contractor_override(
    subsidy_id: int,
    data: SubsidyContractorOverrideCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    if override:
        for key, value in data.dict(exclude_unset=True).items():
            setattr(override, key, value)
    else:
        override = SubsidyContractorOverride(
            subsidy_id=subsidy_id,
            contractor_id=subsidy.contractor_id,
            **data.dict()
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return override
