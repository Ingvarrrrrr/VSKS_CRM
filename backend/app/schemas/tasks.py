"""Events, purchase approvals, tasks, and task comments schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime

# ── Events (Мероприятия) ──────────────────────────────────────────────────────

class EventCreate(BaseModel):
    subsidy_id: int
    name: str
    is_active: bool = True
    region: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    order_decree: Optional[str] = None
    planned_indicators: Optional[str] = None
    actual_indicators: Optional[str] = None
    media_link_1: Optional[str] = None
    media_link_2: Optional[str] = None
    media_link_3: Optional[str] = None

class EventOut(EventCreate):
    # __module__ pinned to the pre-split facade path: app/routers/purchase_events.py
    # independently defines its own unrelated `EventOut`. FastAPI disambiguates
    # same-named OpenAPI components by each class's __module__, so leaving this
    # at its physical location (app.schemas.tasks) would rename the component
    # and change every /api/events response $ref versus before the schemas.py
    # split. Pin it to preserve byte-identical OpenAPI output.
    __module__ = "app.schemas.schemas"

    id: int
    model_config = {"from_attributes": True}


# ── Purchase Approvals (электронное согласование) ─────────────────────────────

class PurchaseApprovalOut(BaseModel):
    id: int
    purchase_id: int
    subsidy_approver_id: Optional[int] = None
    order_num: int
    role_name: str
    approver_full_name: str
    user_id: Optional[int] = None
    status: str
    comment: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[int] = None
    decided_by_username: Optional[str] = None
    created_at: Optional[datetime] = None
    has_signature: bool = False
    signature_algorithm: Optional[str] = None
    model_config = {"from_attributes": True}

class ApprovalDecisionRequest(BaseModel):
    action: str  # "approve" | "reject"
    comment: Optional[str] = None
    sign_electronically: bool = False

# Task (общие задачи, не связанные с закупками)
class TaskAssigneeOut(BaseModel):
    user_id: int
    user_name: Optional[str] = None
    consent_pending: bool = False
    model_config = {"from_attributes": True}

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    assignee_ids: List[int] = []
    category: Optional[str] = None
    parent_task_id: Optional[int] = None
    purchase_id: Optional[int] = None
    import_to_parent: bool = False

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    assignee_ids: Optional[List[int]] = None
    category: Optional[str] = None
    purchase_id: Optional[int] = None
    import_to_parent: Optional[bool] = None

class ReviewCompleteRequest(BaseModel):
    confirm: bool

class TaskOut(BaseModel):
    id: int
    task_number: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[datetime] = None
    assignees: List[TaskAssigneeOut] = []
    # legacy single-assignee fields (for backward compat in frontend)
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    org_id: Optional[int] = None
    category: Optional[str] = None
    parent_task_id: Optional[int] = None
    purchase_id: Optional[int] = None
    purchase_subject: Optional[str] = None
    purchase_number: Optional[int] = None
    purchase_status: Optional[str] = None
    import_to_parent: bool = False
    subtask_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_comment: Optional[str] = None
    last_comment_user: Optional[str] = None
    last_comment_at: Optional[datetime] = None
    comment_count: int = 0
    needs_my_consent: bool = False
    unseen_changes_count: int = 0
    unseen_fields: List[str] = []
    model_config = {"from_attributes": True}


class DismissFieldRequest(BaseModel):
    field_name: str

# Task Comments
class TaskCommentCreate(BaseModel):
    text: str

class TaskCommentOut(BaseModel):
    id: int
    task_id: int
    user_id: int
    user_name: Optional[str] = None
    text: str
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


