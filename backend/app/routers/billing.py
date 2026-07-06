"""Billing router — тарифы по кол-ву сотрудников."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, require_superadmin, OWNER_ROLES
from app.models.user_organization import UserOrganization
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.org_billing import OrgBillingPaid

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ── Тарифные константы ─────────────────────────────────────────────────────────
TIER_FREE_MONTHS = 1    # первые N месяцев — бесплатно
TIER_FLAT_MONTHS = 3    # до этого месяца включительно — фиксированная цена
FLAT_PRICE = 5000       # ₽/мес для месяцев 2-3
PER_USER_PRICE = 300    # ₽/чел для месяца 4+


def _month_number(created_at: datetime, target: date) -> int:
    """Номер месяца с момента создания орг (1 = первый месяц)."""
    ca = created_at.date() if hasattr(created_at, 'date') else created_at
    return (target.year - ca.year) * 12 + (target.month - ca.month) + 1


def _calc_tier(month_num: int, user_count: int) -> dict:
    """Рассчитать тариф для месяца."""
    if month_num <= TIER_FREE_MONTHS:
        return {"tier": "free", "tier_label": "Бесплатно", "amount_due": 0, "user_count": user_count}
    elif month_num <= TIER_FLAT_MONTHS:
        return {"tier": "flat", "tier_label": f"{FLAT_PRICE:,} ₽/мес".replace(",", " "), "amount_due": FLAT_PRICE, "user_count": user_count}
    else:
        amount = PER_USER_PRICE * max(user_count, 0)
        return {"tier": "per_user", "tier_label": f"{PER_USER_PRICE} ₽/чел", "amount_due": amount, "user_count": user_count}


# ── Схемы ──────────────────────────────────────────────────────────────────────

class BillingMonthOut(BaseModel):
    year: int
    month: int
    month_num: int
    tier: str
    tier_label: str
    amount_due: int
    user_count: int        # unique users in contour (billing basis)
    is_paid: bool
    paid_at: Optional[datetime]

    class Config:
        from_attributes = True


class OrgUserCount(BaseModel):
    """Per-org employee count (non-unique, for breakdown display)."""
    org_id: int
    org_name: str
    user_count: int


class BillingOrgOut(BaseModel):
    org_id: int
    org_name: str
    created_at: datetime
    current: BillingMonthOut
    # Breakdown: per-org counts and unique total
    unique_user_count: int = 0           # unique users across contour (= current.user_count)
    org_breakdown: List[OrgUserCount] = []  # per-org raw counts


class PayRequest(BaseModel):
    year: int
    month: int


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_org_or_403(org_id: int, current_user: User, db: AsyncSession) -> Organization:
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")
    if current_user.role == "superadmin":
        return org
    if current_user.role == "account_owner":
        # Can see any org in their contour
        if org.owner_user_id != current_user.id:
            raise HTTPException(403, "Нет доступа")
        return org
    # admin/manager/employee — only own org
    if current_user.org_id != org_id:
        raise HTTPException(403, "Нет доступа")
    return org


async def _contour_org_ids(owner_user_id: int, db: AsyncSession) -> list[int]:
    """Контур ПЛАТЕЛЬЩИКА: все орги с этим owner_user_id.

    Намеренно НЕ visibility.compute_account_contour_org_ids (root_org_id-дерево):
    биллинг считает по владельцу-плательщику, а не по дереву орг — у одного
    account_owner могут быть несколько независимых корневых орг."""
    rows = await db.execute(
        select(Organization.id).where(Organization.owner_user_id == owner_user_id)
    )
    return [r[0] for r in rows.all()]


async def _user_count(org_id: int, db: AsyncSession, owner_user_id: int | None = None) -> int:
    """Count unique users in org (or entire contour if owner_user_id given)."""
    if owner_user_id is not None:
        contour_ids = await _contour_org_ids(owner_user_id, db)
        from sqlalchemy import union
        primary = select(User.id).where(User.org_id.in_(contour_ids))
        extra = select(UserOrganization.user_id).where(UserOrganization.org_id.in_(contour_ids))
        combined = union(primary, extra).subquery()
        res = await db.execute(select(func.count()).select_from(combined))
    else:
        res = await db.execute(select(func.count()).where(User.org_id == org_id))
    return res.scalar() or 0


async def _org_breakdown(contour_ids: list[int], all_orgs: list[Organization], db: AsyncSession) -> list[OrgUserCount]:
    """Per-org employee counts (non-deduplicated) for display purposes."""
    breakdown = []
    for org in all_orgs:
        if org.id not in contour_ids:
            continue
        cnt = (await db.execute(select(func.count()).where(User.org_id == org.id))).scalar() or 0
        breakdown.append(OrgUserCount(org_id=org.id, org_name=org.name, user_count=cnt))
    return breakdown


async def _paid_set(org_id: int, db: AsyncSession) -> set[tuple[int, int]]:
    rows = (await db.execute(
        select(OrgBillingPaid.year, OrgBillingPaid.month)
        .where(OrgBillingPaid.org_id == org_id)
    )).all()
    return {(r[0], r[1]) for r in rows}


async def _paid_map_for_many(org_ids: list[int], db: AsyncSession, year: int, month: int) -> set[int]:
    """Вернуть множество org_id, у которых оплачен указанный месяц."""
    rows = (await db.execute(
        select(OrgBillingPaid.org_id)
        .where(
            OrgBillingPaid.org_id.in_(org_ids),
            OrgBillingPaid.year == year,
            OrgBillingPaid.month == month,
        )
    )).scalars().all()
    return set(rows)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[BillingOrgOut])
async def list_billing(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    """Superadmin: текущий месяц. Одна строка = один контур (root org = billing unit)."""
    all_orgs = (await db.execute(select(Organization).order_by(Organization.name))).scalars().all()
    all_orgs_map = {o.id: o for o in all_orgs}
    today = datetime.now(timezone.utc).date()

    # Show only root orgs (root_org_id IS NULL) — one billing unit per contour.
    # Legacy orgs without owner_user_id are treated as standalone.
    root_orgs = [o for o in all_orgs if o.root_org_id is None]
    root_org_ids = [o.id for o in root_orgs]
    paid_set = await _paid_map_for_many(root_org_ids, db, today.year, today.month)

    result = []
    for org in root_orgs:
        # Contour = this org + all child orgs with same owner_user_id
        if org.owner_user_id:
            contour_ids = await _contour_org_ids(org.owner_user_id, db)
        else:
            contour_ids = [org.id]

        unique_uc = await _user_count(org.id, db, owner_user_id=org.owner_user_id)
        breakdown = await _org_breakdown(contour_ids, all_orgs, db)

        mn = _month_number(org.created_at, today)
        tier_info = _calc_tier(mn, unique_uc)

        paid_row = (await db.execute(
            select(OrgBillingPaid)
            .where(OrgBillingPaid.org_id == org.id,
                   OrgBillingPaid.year == today.year,
                   OrgBillingPaid.month == today.month)
        )).scalar_one_or_none()

        result.append(BillingOrgOut(
            org_id=org.id,
            org_name=org.name,
            created_at=org.created_at,
            unique_user_count=unique_uc,
            org_breakdown=breakdown,
            current=BillingMonthOut(
                year=today.year, month=today.month, month_num=mn,
                is_paid=org.id in paid_set,
                paid_at=paid_row.paid_at if paid_row else None,
                **tier_info,
            ),
        ))
    return result


@router.get("/{org_id}", response_model=List[BillingMonthOut])
async def get_org_billing(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Superadmin или account_owner своей орг: полная история месяцев."""
    org = await _get_org_or_403(org_id, current_user, db)
    today = datetime.now(timezone.utc).date()
    uc = await _user_count(org.id, db, owner_user_id=org.owner_user_id)
    paid = await _paid_set(org.id, db)

    # Получить paid_at для каждого оплаченного месяца
    paid_rows = {
        (r.year, r.month): r.paid_at
        for r in (await db.execute(
            select(OrgBillingPaid).where(OrgBillingPaid.org_id == org_id)
        )).scalars().all()
    }

    result = []
    ca = org.created_at.date() if hasattr(org.created_at, 'date') else org.created_at
    # Iterate from creation month to current month
    cur = date(ca.year, ca.month, 1)
    end = date(today.year, today.month, 1)
    while cur <= end:
        mn = _month_number(org.created_at, cur)
        tier_info = _calc_tier(mn, uc)
        key = (cur.year, cur.month)
        result.append(BillingMonthOut(
            year=cur.year, month=cur.month, month_num=mn,
            is_paid=key in paid,
            paid_at=paid_rows.get(key),
            **tier_info,
        ))
        # next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    result.reverse()  # newest first
    return result


@router.post("/{org_id}/pay", status_code=200)
async def mark_paid(
    org_id: int,
    body: PayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_superadmin()),
):
    """Superadmin: отметить месяц как оплаченный."""
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Организация не найдена")

    existing = (await db.execute(
        select(OrgBillingPaid).where(
            OrgBillingPaid.org_id == org_id,
            OrgBillingPaid.year == body.year,
            OrgBillingPaid.month == body.month,
        )
    )).scalar_one_or_none()

    if not existing:
        db.add(OrgBillingPaid(
            org_id=org_id,
            year=body.year,
            month=body.month,
            paid_by_id=current_user.id,
        ))
        await db.commit()
    return {"ok": True}


@router.post("/{org_id}/unpay", status_code=200)
async def mark_unpaid(
    org_id: int,
    body: PayRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_superadmin()),
):
    """Superadmin: снять отметку оплаты."""
    await db.execute(
        delete(OrgBillingPaid).where(
            OrgBillingPaid.org_id == org_id,
            OrgBillingPaid.year == body.year,
            OrgBillingPaid.month == body.month,
        )
    )
    await db.commit()
    return {"ok": True}
