from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.org_section_config import OrgSectionConfig
from app.models.user import User

router = APIRouter(prefix="/api/org", tags=["org-config"])

ALLOWED_SECTIONS = {
    "financial_indicators",
    "contract_type",
    "contract_params",
    "acceptance",
    "payment",
    "commercial_requests",
    "platform_publication",
}


class SectionConfigItem(BaseModel):
    section_key: str
    is_hidden: bool


class SectionConfigOut(BaseModel):
    hidden_sections: List[str]


@router.get("/section-config", response_model=SectionConfigOut)
async def get_section_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.org_id
    if not org_id:
        return SectionConfigOut(hidden_sections=[])
    result = await db.execute(
        select(OrgSectionConfig).where(
            OrgSectionConfig.org_id == org_id,
            OrgSectionConfig.is_hidden == True,
        )
    )
    rows = result.scalars().all()
    return SectionConfigOut(hidden_sections=[r.section_key for r in rows])


@router.put("/section-config")
async def update_section_config(
    items: List[SectionConfigItem],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("superadmin", "org_admin", "admin"):
        raise HTTPException(403, "Недостаточно прав")
    org_id = current_user.org_id
    if not org_id:
        raise HTTPException(400, "Суперадмин без организации не может менять настройки")

    await db.execute(delete(OrgSectionConfig).where(OrgSectionConfig.org_id == org_id))
    for item in items:
        if item.section_key in ALLOWED_SECTIONS and item.is_hidden:
            db.add(OrgSectionConfig(org_id=org_id, section_key=item.section_key, is_hidden=True))
    await db.commit()
    return {"ok": True}
