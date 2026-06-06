"""Reusable consent-needed helper.

Computes which target users require consent to be added to a resource
(wish, purchase, task) based on the current user's hierarchy authority.

Logic mirrors tasks.py:174-230 — extracted here for reuse in wish_members router.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_hierarchy import UserHierarchy


async def compute_consent_needed(
    current_user: User,
    target_user_ids: list[int],
    db: AsyncSession,
) -> set[int]:
    """Return set of user IDs from *target_user_ids* that require consent.

    Rules (same as tasks.py):
    - Assigning to self → never needs consent.
    - If target user is a direct subordinate (UserHierarchy) → no consent.
    - If target user belongs to an org managed by current_user (ManagerOrganization) → no consent.
    - If target user is in a department managed by current_user (ManagerDepartment) → no consent.
    - Otherwise → consent required.
    """
    consent_needed: set[int] = set()
    non_self = [uid for uid in target_user_ids if uid != current_user.id]
    if not non_self:
        return consent_needed

    # Load hierarchy: current user's subordinates
    hier_res = await db.execute(
        select(UserHierarchy.subordinate_id).where(
            UserHierarchy.manager_id == current_user.id
        )
    )
    subordinate_ids = {r[0] for r in hier_res.all()}

    # Load orgs managed by current user
    from app.models.manager_organization import ManagerOrganization
    mo_res = await db.execute(
        select(ManagerOrganization.org_id).where(
            ManagerOrganization.manager_user_id == current_user.id
        )
    )
    managed_org_ids = {r[0] for r in mo_res.all()}

    # Load depts managed by current user
    from app.models.manager_department import ManagerDepartment
    from app.models.department import DepartmentMember
    md_res = await db.execute(
        select(ManagerDepartment.dept_id).where(
            ManagerDepartment.manager_user_id == current_user.id
        )
    )
    managed_dept_ids = {r[0] for r in md_res.all()}

    managed_dept_user_ids: set[int] = set()
    if managed_dept_ids:
        dm_res = await db.execute(
            select(DepartmentMember.user_id).where(
                DepartmentMember.department_id.in_(managed_dept_ids)
            )
        )
        managed_dept_user_ids = {r[0] for r in dm_res.all()}

    # Load org_id for each target to check ManagerOrganization
    assignee_org_map: dict[int, int] = {}
    if managed_org_ids:
        assignee_users = (await db.execute(
            select(User.id, User.org_id).where(User.id.in_(non_self))
        )).all()
        assignee_org_map = {r[0]: r[1] for r in assignee_users}

    for uid in non_self:
        if uid in subordinate_ids:
            continue  # direct subordinate
        if assignee_org_map.get(uid) in managed_org_ids:
            continue  # manages their org
        if uid in managed_dept_user_ids:
            continue  # manages their dept
        consent_needed.add(uid)

    return consent_needed
