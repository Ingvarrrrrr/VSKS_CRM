import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.schemas.schemas import SubsidyApproverCreate, SubsidyApproverOut
from app.auth.jwt import get_current_user
from typing import List

SUBSIDY_TEMPLATES_DIR = "/app/templates/subsidies"

router = APIRouter(prefix="/api/subsidies", tags=["subsidy-approvers"])


async def _get_subsidy_or_404(sid: int, db: AsyncSession) -> Subsidy:
    result = await db.execute(select(Subsidy).where(Subsidy.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    return s


@router.get("/{sid}/approvers", response_model=List[SubsidyApproverOut])
async def list_approvers(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    result = await db.execute(
        select(SubsidyApprover)
        .where(SubsidyApprover.subsidy_id == sid)
        .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
    )
    return result.scalars().all()


@router.post("/{sid}/approvers", response_model=SubsidyApproverOut)
async def create_approver(
    sid: int,
    data: SubsidyApproverCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    approver = SubsidyApprover(subsidy_id=sid, **data.model_dump())
    db.add(approver)
    await db.commit()
    await db.refresh(approver)
    return approver


@router.put("/{sid}/approvers/{aid}", response_model=SubsidyApproverOut)
async def update_approver(
    sid: int,
    aid: int,
    data: SubsidyApproverCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(SubsidyApprover).where(
            SubsidyApprover.id == aid, SubsidyApprover.subsidy_id == sid
        )
    )
    approver = result.scalar_one_or_none()
    if not approver:
        raise HTTPException(404, "Согласующий не найден")
    for k, v in data.model_dump().items():
        setattr(approver, k, v)
    await db.commit()
    await db.refresh(approver)
    return approver


@router.delete("/{sid}/approvers/{aid}")
async def delete_approver(
    sid: int,
    aid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(SubsidyApprover).where(
            SubsidyApprover.id == aid, SubsidyApprover.subsidy_id == sid
        )
    )
    approver = result.scalar_one_or_none()
    if not approver:
        raise HTTPException(404, "Согласующий не найден")
    await db.delete(approver)
    await db.commit()
    return {"ok": True}


# ── Per-subsidy contract template ─────────────────────────────────────────────

@router.get("/{sid}/contract-template/status")
async def contract_template_status(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    return {"exists": os.path.exists(path)}


@router.post("/{sid}/contract-template")
async def upload_contract_template(
    sid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Разрешены только .docx файлы")
    folder = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "contract.docx")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return {"ok": True}


@router.get("/{sid}/contract-template/download")
async def download_contract_template(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Шаблон не загружен")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"contract_template_subsidy_{sid}.docx",
    )


@router.delete("/{sid}/contract-template")
async def delete_contract_template(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}
