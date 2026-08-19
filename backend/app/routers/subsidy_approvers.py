import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.models.user import User
from app.schemas.schemas import SubsidyApproverCreate, SubsidyApproverOut
from app.auth.jwt import get_current_user, get_org_filter
from app.services.responsible_role import is_responsible_role, RESPONSIBLE_PLACEHOLDER
from typing import List

SUBSIDY_TEMPLATES_DIR = "/app/uploads/templates/subsidies"

router = APIRouter(prefix="/api/subsidies", tags=["subsidy-approvers"])


async def _get_subsidy_or_404(
    sid: int, db: AsyncSession, current_user=None, edit: bool = False
) -> Subsidy:
    result = await db.execute(select(Subsidy).where(Subsidy.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    if current_user:
        if edit:
            # Wave 3: управление согласующими/шаблонами = право subsidy.edit
            # именно в орге ЭТОЙ субсидии (get_org_filter теперь контур всего
            # аккаунта и для write-операций недостаточен).
            from app.auth.permissions import has_org_key
            if not await has_org_key(
                current_user, db, s.org_id, 'subsidy.edit', subsidy_id=sid
            ):
                raise HTTPException(
                    403,
                    "Нет права управлять согласующими и шаблонами этой субсидии: "
                    "право «Редактирование субсидий» не выдано для организации-грантополучателя",
                )
        else:
            org_ids = get_org_filter(current_user)
            if org_ids is not None and s.org_id not in org_ids:
                raise HTTPException(403, "Нет доступа к этой субсидии")
    return s


@router.get("/{sid}/approvers", response_model=List[SubsidyApproverOut])
async def list_approvers(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db, current_user)
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
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
    payload = data.model_dump()
    user_id = payload.get("user_id")
    if user_id is not None:
        target_user = await db.get(User, user_id)
        if target_user and target_user.role == "superadmin":
            raise HTTPException(400, "Суперадмина нельзя назначить согласующим")
    if is_responsible_role(payload.get("role_name")):
        # «Ответственный исполнитель» — роль-слот, ФИО определяется по
        # закупке, а не хранится фиксированным в настройках субсидии.
        payload["full_name"] = RESPONSIBLE_PLACEHOLDER
        payload["user_id"] = None
    approver = SubsidyApprover(subsidy_id=sid, **payload)
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
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
    result = await db.execute(
        select(SubsidyApprover).where(
            SubsidyApprover.id == aid, SubsidyApprover.subsidy_id == sid
        )
    )
    approver = result.scalar_one_or_none()
    if not approver:
        raise HTTPException(404, "Согласующий не найден")
    payload = data.model_dump()
    user_id = payload.get("user_id")
    if user_id is not None:
        target_user = await db.get(User, user_id)
        if target_user and target_user.role == "superadmin":
            raise HTTPException(400, "Суперадмина нельзя назначить согласующим")
    if is_responsible_role(payload.get("role_name")):
        payload["full_name"] = RESPONSIBLE_PLACEHOLDER
        payload["user_id"] = None
    for k, v in payload.items():
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
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
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
    await _get_subsidy_or_404(sid, db, current_user)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    return {"exists": os.path.exists(path)}


@router.post("/{sid}/contract-template")
async def upload_contract_template(
    sid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
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
    await _get_subsidy_or_404(sid, db, current_user)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Шаблон не загружен")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"contract_template_subsidy_{sid}.docx",
    )


@router.post("/{sid}/approvers/copy-from/{source_sid}")
async def copy_approvers_from(
    sid: int,
    source_sid: int,
    replace: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Копирует ВСЕХ согласующих из source_sid → sid.
    replace=true — удалить существующих перед копированием.
    replace=false — добавить в конец (с правкой order_num).
    """
    if sid == source_sid:
        raise HTTPException(400, "Целевая и источник — одна субсидия")
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
    await _get_subsidy_or_404(source_sid, db, current_user)

    if replace:
        existing = (await db.execute(
            select(SubsidyApprover).where(SubsidyApprover.subsidy_id == sid)
        )).scalars().all()
        for a in existing:
            await db.delete(a)
        await db.flush()
        max_order = -1
    else:
        max_order_row = (await db.execute(
            select(SubsidyApprover.order_num)
            .where(SubsidyApprover.subsidy_id == sid)
            .order_by(SubsidyApprover.order_num.desc())
            .limit(1)
        )).scalar()
        max_order = max_order_row if max_order_row is not None else -1

    source_approvers = (await db.execute(
        select(SubsidyApprover)
        .where(SubsidyApprover.subsidy_id == source_sid)
        .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
    )).scalars().all()

    copied = 0
    for src in source_approvers:
        max_order += 1
        new_a = SubsidyApprover(
            subsidy_id=sid,
            role_name=src.role_name,
            user_id=src.user_id,
            full_name=src.full_name,
            is_default=src.is_default,
            can_initiate=src.can_initiate,
            show_feo_path=src.show_feo_path,
            order_num=max_order,
        )
        db.add(new_a)
        copied += 1

    await db.commit()
    return {"copied": copied, "replaced": replace}


@router.post("/{sid}/templates/copy-from/{source_sid}")
async def copy_templates_from(
    sid: int,
    source_sid: int,
    doc_types: str | None = None,
    replace: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Копирует кастомные .docx шаблоны из source_sid → sid.
    doc_types: CSV (например "contract,service_note_payment") — если задан, копируются только эти.
    replace=false — пропустить doc_type если у target уже есть свой кастом.
    replace=true — перезаписать.
    """
    if sid == source_sid:
        raise HTTPException(400, "Целевая и источник — одна субсидия")
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
    await _get_subsidy_or_404(source_sid, db, current_user)

    src_dir = os.path.join(SUBSIDY_TEMPLATES_DIR, str(source_sid))
    dst_dir = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid))

    if not os.path.isdir(src_dir):
        return {"copied": [], "skipped": [], "reason": "В исходной субсидии нет кастомных шаблонов"}

    os.makedirs(dst_dir, exist_ok=True)

    requested_types = set(doc_types.split(",")) if doc_types else None
    copied = []
    skipped = []
    for fn in os.listdir(src_dir):
        if not fn.endswith(".docx"):
            continue
        doc_type = fn[:-5]  # strip .docx
        if requested_types and doc_type not in requested_types:
            continue
        src_path = os.path.join(src_dir, fn)
        dst_path = os.path.join(dst_dir, fn)
        if os.path.exists(dst_path) and not replace:
            skipped.append(doc_type)
            continue
        shutil.copy2(src_path, dst_path)
        copied.append(doc_type)

    return {"copied": copied, "skipped": skipped}


@router.delete("/{sid}/contract-template")
async def delete_contract_template(
    sid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_subsidy_or_404(sid, db, current_user, edit=True)
    path = os.path.join(SUBSIDY_TEMPLATES_DIR, str(sid), "contract.docx")
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}
