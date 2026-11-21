"""Service for merging duplicate staff accounts (POST /api/users/{keep_id}/merge).

Handles multi-tenancy access checks, unique constraint deduplication,
and bulk foreign key repointing in a single transaction.
"""
from typing import List, Dict, Any, Type
from fastapi import HTTPException
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_organization import UserOrganization
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride
from app.models.user_subsidy_access import UserSubsidyAccess, UserSubsidyPermissionOverride
from app.models.chat_room import ChatParticipant, ChatRoom
from app.models.chat_message import MessageRead, ChatMessage
from app.models.purchase import Purchase
from app.models.purchase_event import PurchaseMember, PurchaseEvent
from app.models.purchase_approval import PurchaseApproval
from app.models.purchase_comment import PurchaseComment
from app.models.purchase_file import PurchaseFile
from app.models.purchase_paid_confirmation import PurchasePaidConfirmation
from app.models.task import Task, TaskAssignee
from app.models.task_comment import TaskComment
from app.models.task_change import TaskChange, TaskFieldSeen
from app.models.task_decline import TaskConsentDecline
from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.wish_member import WishMember
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.models.subsidy_member import SubsidyMember
from app.models.subsidy_revision import SubsidyRevision
from app.models.department import Department, TaskEditDelegate
from app.models.organization import Organization
from app.models.manager_department import ManagerDepartment
from app.models.manager_organization import ManagerOrganization
from app.models.trip import Trip
from app.models.checklist import Checklist
from app.models.incident import Incident
from app.models.vehicle_fine import VehicleFine
from app.models.vehicle_repair import VehicleRepair
from app.models.vehicle_odometer import VehicleOdometer
from app.models.vehicle_attachment import VehicleAttachment
from app.models.vehicle_field_history import VehicleFieldHistory
from app.models.vehicle_transfer_history import VehicleTransferHistory
from app.models.fleet_document import FleetDocument
from app.models.external_driver import ExternalDriver
from app.models.fuel_log import FuelLog
from app.models.commercial_request import CommercialRequest
from app.models.budget_history import BudgetHistory
from app.models.bank_statement import BankStatementImport
from app.models.entity_change import EntityChange, EntityFieldSeen
from app.models.fact_import_run import FactImportRun
from app.models.feo_comment import FeoComment
from app.models.feo_import_run import FeoImportRun
from app.models.feo_category import FeoCategory
from app.models.game_score import GameScore, GameProfile
from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
from app.models.plan_graph_version import PlanGraphVersion
from app.models.product_description_history import ProductDescriptionHistory
from app.models.product_description_proposal import ProductDescriptionProposal
from app.models.product_price_history import ProductPriceHistory
from app.models.push_subscription import PushSubscription
from app.models.repair_attachment import RepairAttachment
from app.models.report_config import ReportConfig
from app.models.staff_location import StaffLocationPoint
from app.models.staff_location_request import StaffLocationRequest
from app.models.staff_shift import StaffShift
from app.models.system_incident import SystemIncident
from app.models.user_address import UserAddress
from app.models.user_consent import UserConsent, PersonalDataRequest
from app.models.user_hierarchy import UserHierarchy
from app.models.user_platform_credential import UserPlatformCredential
from app.models.approval_signature_key import ApprovalSignatureKey

from app.auth.permissions import (
    assert_target_in_owner_account,
    assert_target_user_visible,
    assert_not_last_account_owner,
)


_FK_UPDATE_MAP: list[tuple[Any, str]] = [
    (Purchase, "assigned_user_id"),
    (Purchase, "service_note_by"),
    (Purchase, "stopped_by"),
    (Purchase, "reimbursement_user_id"),
    (Purchase, "service_note_to_user_id"),
    (Purchase, "tz_waived_by_user_id"),
    (PurchaseApproval, "user_id"),
    (PurchaseApproval, "decided_by_user_id"),
    (PurchaseComment, "user_id"),
    (PurchaseEvent, "user_id"),
    (PurchaseFile, "uploaded_by_id"),
    (PurchasePaidConfirmation, "decided_by"),
    (Task, "assigned_user_id"),
    (Task, "created_by_id"),
    (TaskComment, "user_id"),
    (TaskChange, "changed_by_id"),
    (TaskFieldSeen, "user_id"),
    (TaskConsentDecline, "declined_user_id"),
    (TaskConsentDecline, "creator_id"),
    (Wish, "created_by"),
    (Wish, "approved_by"),
    (Wish, "rejected_by"),
    (Wish, "assigned_to"),
    (Wish, "executor_id"),
    (Wish, "stopped_by"),
    (Wish, "tz_waived_by_user_id"),
    (WishApproval, "user_id"),
    (WishApproval, "decided_by_user_id"),
    (Subsidy, "created_by"),
    (Subsidy, "approved_by"),
    (SubsidyApprover, "user_id"),
    (SubsidyRevision, "author_id"),
    (SubsidyRevision, "decided_by_id"),
    (Department, "head_user_id"),
    (Department, "deputy_head_user_id"),
    (Department, "curator_user_id"),
    (Organization, "head_user_id"),
    (Organization, "owner_user_id"),
    (Trip, "driver_user_id"),
    (Trip, "created_by_id"),
    (Trip, "dispatcher_id"),
    (Trip, "pre_trip_mechanic_id"),
    (Trip, "pre_trip_doctor_id"),
    (Trip, "post_trip_mechanic_id"),
    (Trip, "post_trip_doctor_id"),
    (Checklist, "driver_user_id"),
    (Incident, "driver_user_id"),
    (Incident, "notify_user_id"),
    (VehicleFine, "driver_user_id"),
    (VehicleFine, "created_by_id"),
    (VehicleRepair, "created_by_id"),
    (VehicleOdometer, "entered_by_id"),
    (VehicleAttachment, "uploaded_by_id"),
    (VehicleFieldHistory, "changed_by_user_id"),
    (VehicleTransferHistory, "changed_by_user_id"),
    (FleetDocument, "created_by_user_id"),
    (ExternalDriver, "created_by_id"),
    (FuelLog, "created_by_id"),
    (ChatMessage, "sender_id"),
    (ChatRoom, "created_by"),
    (CommercialRequest, "created_by"),
    (BudgetHistory, "changed_by_id"),
    (BankStatementImport, "uploaded_by_id"),
    (EntityChange, "changed_by_id"),
    (EntityFieldSeen, "user_id"),
    (FactImportRun, "user_id"),
    (FeoComment, "user_id"),
    (FeoImportRun, "user_id"),
    (FeoCategory, "payroll_closed_by_user_id"),
    (GameScore, "user_id"),
    (PlanExcessApproval, "requested_by_id"),
    (PlanExcessApprovalStep, "user_id"),
    (PlanExcessApprovalStep, "decided_by_user_id"),
    (PlanGraphVersion, "created_by_id"),
    (ProductDescriptionHistory, "user_id"),
    (ProductDescriptionProposal, "proposed_by"),
    (ProductDescriptionProposal, "decided_by"),
    (ProductPriceHistory, "created_by"),
    (PushSubscription, "user_id"),
    (RepairAttachment, "uploaded_by_id"),
    (ReportConfig, "created_by_id"),
    (StaffLocationPoint, "user_id"),
    (StaffLocationRequest, "requested_by_id"),
    (StaffLocationRequest, "user_id"),
    (StaffShift, "user_id"),
    (SystemIncident, "user_id"),
    (UserAddress, "user_id"),
    (UserConsent, "user_id"),
    (PersonalDataRequest, "user_id"),
    (PersonalDataRequest, "handled_by_user_id"),
    (UserHierarchy, "manager_id"),
    (UserHierarchy, "subordinate_id"),
    (UserPlatformCredential, "user_id"),
    (User, "superior_user_id"),
]


async def _dedup_m2m(
    db: AsyncSession,
    model: Type[Any],
    user_col: str,
    scope_col: str,
    keep_id: int,
    merge_ids: list[int],
) -> int:
    """Repoint or deduplicate rows having UniqueConstraint(user_col, scope_col)."""
    keep_scopes = set(
        (await db.execute(
            select(getattr(model, scope_col)).where(getattr(model, user_col) == keep_id)
        )).scalars().all()
    )
    dup_res = await db.execute(
        delete(model).where(
            getattr(model, user_col).in_(merge_ids),
            getattr(model, scope_col).in_(keep_scopes) if keep_scopes else False,
        )
    )
    deleted = dup_res.rowcount or 0
    upd_res = await db.execute(
        update(model)
        .where(getattr(model, user_col).in_(merge_ids))
        .values({user_col: keep_id})
    )
    return deleted + (upd_res.rowcount or 0)


async def _dedup_user_org_access(db: AsyncSession, keep_id: int, merge_ids: list[int]) -> int:
    """Deduplicate UserOrgAccess and merge any overrides."""
    keep_uoa = {
        uoa.org_id: uoa.id
        for uoa in (await db.execute(
            select(UserOrgAccess).where(UserOrgAccess.user_id == keep_id)
        )).scalars().all()
    }
    merge_uoas = (await db.execute(
        select(UserOrgAccess).where(UserOrgAccess.user_id.in_(merge_ids))
    )).scalars().all()

    total = 0
    for uoa in merge_uoas:
        if uoa.org_id in keep_uoa:
            target_uoa_id = keep_uoa[uoa.org_id]
            existing_keys = set((await db.execute(
                select(UserOrgPermissionOverride.key).where(
                    UserOrgPermissionOverride.user_org_access_id == target_uoa_id
                )
            )).scalars().all())
            await db.execute(
                delete(UserOrgPermissionOverride).where(
                    UserOrgPermissionOverride.user_org_access_id == uoa.id,
                    UserOrgPermissionOverride.key.in_(existing_keys) if existing_keys else False,
                )
            )
            await db.execute(
                update(UserOrgPermissionOverride)
                .where(UserOrgPermissionOverride.user_org_access_id == uoa.id)
                .values(user_org_access_id=target_uoa_id)
            )
            await db.delete(uoa)
            total += 1
        else:
            uoa.user_id = keep_id
            keep_uoa[uoa.org_id] = uoa.id
            total += 1
    return total


async def merge_users(
    keep_id: int,
    merge_user_ids: List[int],
    current_user: User,
    db: AsyncSession,
) -> Dict[str, Any]:
    """Merge duplicate user accounts into keep_id within a single transaction."""
    clean_merge_ids = list(dict.fromkeys(int(x) for x in merge_user_ids if int(x) != keep_id))
    if not clean_merge_ids:
        raise HTTPException(400, "Список объединяемых пользователей пуст или совпадает с основным.")
    if keep_id == current_user.id or current_user.id in clean_merge_ids:
        raise HTTPException(409, "Нельзя объединить или удалить собственный аккаунт.")

    keep_user = await db.get(User, keep_id)
    if not keep_user:
        raise HTTPException(404, "Основной пользователь не найден.")

    merge_users_list = (await db.execute(
        select(User).where(User.id.in_(clean_merge_ids))
    )).scalars().all()
    if len(merge_users_list) != len(clean_merge_ids):
        raise HTTPException(404, "Один или несколько объединяемых пользователей не найдены.")

    # Authorization and multi-tenancy contour checks (Rule #8)
    all_users = [keep_user] + list(merge_users_list)
    if current_user.role != "superadmin":
        if any(u.role == "superadmin" for u in all_users):
            raise HTTPException(403, "Действие над superadmin запрещено.")
        if current_user.role == "account_owner":
            for u in all_users:
                await assert_target_in_owner_account(current_user, u, db)
        else:
            for u in all_users:
                await assert_target_user_visible(current_user, u, db)
            if current_user.role == "org_admin":
                if any(u.org_id != current_user.org_id for u in all_users):
                    raise HTTPException(403, "Сливать можно только сотрудников своей организации.")

    for u in merge_users_list:
        await assert_not_last_account_owner(u.id, db, action="слить сотрудника")

    updated_relations = 0

    # 1. Deduplicate M2M with UniqueConstraints
    updated_relations += await _dedup_m2m(db, UserOrganization, "user_id", "org_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_user_org_access(db, keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, UserSubsidyAccess, "user_id", "subsidy_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, ChatParticipant, "user_id", "room_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, MessageRead, "user_id", "room_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, PurchaseMember, "user_id", "purchase_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, TaskAssignee, "user_id", "task_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, SubsidyMember, "user_id", "subsidy_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, WishMember, "user_id", "wish_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, ManagerDepartment, "manager_user_id", "dept_id", keep_id, clean_merge_ids)
    updated_relations += await _dedup_m2m(db, ManagerOrganization, "manager_user_id", "org_id", keep_id, clean_merge_ids)

    # 2. Special single-user uniques (approval_signature_keys, game_profiles)
    for model_cls in (ApprovalSignatureKey, GameProfile):
        has_keep = (await db.execute(
            select(func.count()).select_from(model_cls).where(model_cls.user_id == keep_id)
        )).scalar_one() > 0
        if has_keep:
            del_res = await db.execute(delete(model_cls).where(model_cls.user_id.in_(clean_merge_ids)))
            updated_relations += del_res.rowcount or 0
        else:
            upd_res = await db.execute(
                update(model_cls).where(model_cls.user_id.in_(clean_merge_ids)).values(user_id=keep_id)
            )
            updated_relations += upd_res.rowcount or 0

    # TaskEditDelegate cleanup
    await db.execute(
        delete(TaskEditDelegate).where(
            (TaskEditDelegate.delegate_user_id.in_(clean_merge_ids) & (TaskEditDelegate.target_user_id == keep_id))
            | (TaskEditDelegate.target_user_id.in_(clean_merge_ids) & (TaskEditDelegate.delegate_user_id == keep_id))
        )
    )
    updated_relations += (await db.execute(
        update(TaskEditDelegate)
        .where(TaskEditDelegate.delegate_user_id.in_(clean_merge_ids))
        .values(delegate_user_id=keep_id)
    )).rowcount or 0
    updated_relations += (await db.execute(
        update(TaskEditDelegate)
        .where(TaskEditDelegate.target_user_id.in_(clean_merge_ids))
        .values(target_user_id=keep_id)
    )).rowcount or 0

    # 3. Bulk repoint all non-unique FK relations
    for model_cls, col_name in _FK_UPDATE_MAP:
        col = getattr(model_cls, col_name)
        res = await db.execute(
            update(model_cls).where(col.in_(clean_merge_ids)).values({col_name: keep_id})
        )
        updated_relations += res.rowcount or 0

    # 4. Fill in missing fields on keep_user from merged accounts
    for mu in merge_users_list:
        for attr in ("phone", "inn", "snils", "position", "full_name", "department_id"):
            if not getattr(keep_user, attr, None) and getattr(mu, attr, None):
                setattr(keep_user, attr, getattr(mu, attr))

    # 5. Delete duplicate user records
    await db.execute(delete(User).where(User.id.in_(clean_merge_ids)))
    await db.commit()

    return {
        "ok": True,
        "keep_id": keep_id,
        "merged_count": len(clean_merge_ids),
        "updated_relations": updated_relations,
    }
