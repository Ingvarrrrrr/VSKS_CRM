"""Permission matrix and role override schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

# ---------------------------------------------------------------------------
# Phase 17 Plan 05: permission matrix + per-user overrides schemas
# ---------------------------------------------------------------------------

class PermissionTabOut(BaseModel):
    tab_key: str
    title: str
    model_config = ConfigDict(from_attributes=True)


class PermissionActionOut(BaseModel):
    action_key: str
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class RolePermissionOut(BaseModel):
    role_name: str
    key: str
    granted: bool
    model_config = ConfigDict(from_attributes=True)


class RoleMatrixRow(BaseModel):
    role_name: str
    tabs: List[str]        # tab_keys where granted=True
    actions: List[str]     # action_keys where granted=True


class PermissionUpdate(BaseModel):
    key: str
    granted: bool


class RoleUpdate(BaseModel):
    role: str


class OverrideOut(BaseModel):
    key: str
    granted: bool
    model_config = ConfigDict(from_attributes=True)
    changed_at: Optional[datetime] = None


