"""Report configuration schemas (extracted from schemas.py)."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Literal
from datetime import datetime

class ReportConfigCreate(BaseModel):
    kind: Literal['list', 'pivot', 'dashboard']
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config_json: dict = Field(default_factory=dict)
    parameters_json: list = Field(default_factory=list)
    is_default: bool = False
    is_shared: bool = True


class ReportConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_json: Optional[dict] = None
    parameters_json: Optional[list] = None
    is_default: Optional[bool] = None
    is_shared: Optional[bool] = None


class ReportConfigOut(BaseModel):
    id: int
    org_id: int
    kind: str
    name: str
    description: Optional[str] = None
    config_json: dict
    parameters_json: list
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    is_default: bool
    is_shared: bool

    model_config = ConfigDict(from_attributes=True)


