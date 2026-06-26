"""Reusable hierarchy/consent helpers.

Computes:
- compute_assignable_user_ids: the set of users the current user may assign work to
  WITHOUT consent (subordinates, members of managed orgs/depts, self). None = all
  (super-roles see/assign everyone).
- compute_consent_needed: which target users require consent (i.e. NOT assignable).

Logic mirrors tasks.py:174-230 — extracted here for reuse in wish_members router
and the /users assignment-listing endpoint.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_hierarchy import UserHierarchy

# Roles that may assign to anyone (no hierarchy restriction, no consent).
SUPER_ROLES = ("superadmin", "account_owner")


async def compute_assignable_user_ids(
    current_user: User,
    db: AsyncSession,
) -> Optional[set[int]]:
    """Return the set of user IDs *current_user* can assign work to without consent.

    Returns None when the caller may assign to ANYONE (super-roles) — callers should
    treat None as "no restriction / all users".

    For everyone else the set is: self + direct subordinates (UserHierarchy) +
    members of orgs they manage (ManagerOrganization, primary org_id + M2M) +
    members of departments they manage (ManagerDepartment → user_organizations.dept_id).
    Members may belong to other organizations — that is intentional.
    """
    if current_user.role in SUPER_ROLES:
        return None

    assignable: set[int] = {current_user.id}

    # Direct subordinates
    hier_res = await db.execute(
        select(UserHierarchy.subordinate_id).where(
            UserHierarchy.manager_id == current_user.id
        )
    )
    assignable.update(r[0] for r in hier_res.all())

    # Orgs managed by current user → all their members (primary + M2M)
    from app.models.manager_organization import ManagerOrganization
    mo_res = await db.execute(
        select(ManagerOrganization.org_id).where(
            ManagerOrganization.manager_user_id == current_user.id
        )
    )
    managed_org_ids = {r[0] for r in mo_res.all()}
    if managed_org_ids:
        org_list = list(managed_org_ids)
        members = await db.execute(
            select(User.id).where(User.org_id.in_(org_list))
        )
        assignable.update(r[0] for r in members.all())
        from app.models.user_organization import UserOrganization
        m2m = await db.execute(
            select(UserOrganization.user_id).where(
                UserOrganization.org_id.in_(org_list)
            )
        )
        assignable.update(r[0] for r in m2m.all())

    # Departments managed by current user → their members
    from app.models.manager_department import ManagerDepartment
    from app.models.user_organization import UserOrganization as _UO_consent
    md_res = await db.execute(
        select(ManagerDepartment.dept_id).where(
            ManagerDepartment.manager_user_id == current_user.id
        )
    )
    managed_dept_ids = {r[0] for r in md_res.all()}
    if managed_dept_ids:
        dm_res = await db.execute(
            select(_UO_consent.user_id).where(
                _UO_consent.dept_id.in_(list(managed_dept_ids))
            )
        )
        assignable.update(r[0] for r in dm_res.all())

    return assignable


async def compute_consent_needed(
    current_user: User,
    target_user_ids: list[int],
    db: AsyncSession,
) -> set[int]:
    """Return set of user IDs from *target_user_ids* that require consent.

    A target needs consent iff the current user cannot assign work to them
    (i.e. they are not in the assignable set). Super-roles never need consent.
    Assigning to self never needs consent.
    """
    assignable = await compute_assignable_user_ids(current_user, db)
    if assignable is None:
        return set()  # super-role — can add anyone without consent
    return {
        uid for uid in target_user_ids
        if uid != current_user.id and uid not in assignable
    }
