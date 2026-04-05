import os
import re
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.contractor import Contractor
from app.schemas.schemas import (
    SubsidyCreate, SubsidyOut,
    SubsidyContractorOverrideCreate, SubsidyContractorOverrideOut,
)
from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id, MANAGER_ROLES, ADMIN_ROLES
from app.models.user import User
from typing import List

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


async def calculate_budget_from_categories(db: AsyncSession, subsidy_id: int) -> float:
    """
    Рекурсивный подсчёт бюджета из ФЭО-дерева:
    - Листовой узел (нет детей): берём его budget
    - Родительский узел: если у детей есть бюджеты → сумма детей (рекурсивно)
                         если ни у одного ребёнка нет → свой budget (ручной)
    Итог = сумма по всем корневым (level-1) узлам.
    """
    stmt = select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    result = await db.execute(stmt)
    all_categories = result.scalars().all()

    if not all_categories:
        return 0.0

    by_id = {c.id: c for c in all_categories}
    children_map: dict = {}
    for c in all_categories:
        children_map.setdefault(c.id, [])
        if c.parent_id and c.parent_id in by_id:
            children_map.setdefault(c.parent_id, []).append(c)

    def _calc_node(cat) -> float:
        kids = children_map.get(cat.id, [])
        if not kids:
            return float(cat.budget) if cat.budget is not None and cat.budget > 0 else 0.0
        child_sum = sum(_calc_node(k) for k in kids)
        if child_sum > 0:
            return child_sum
        return float(cat.budget) if cat.budget is not None and cat.budget > 0 else 0.0

    roots = [c for c in all_categories if c.level == 1]
    return sum(_calc_node(r) for r in roots)


@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    q = select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name)
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        q = q.where(Subsidy.org_id.in_(org_ids))
    result = await db.execute(q)
    subsidies = result.scalars().all()

    out = []
    for s in subsidies:
        calc = await calculate_budget_from_categories(db, s.id)
        s.calculated_budget = calc
        # Синхронизируем budget с calculated_budget если ФЭО заполнено
        if calc > 0 and s.budget != calc:
            s.budget = calc

        d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
        d["calculated_budget"] = calc
        d["feo_filled"] = calc > 0
        d["feo_budget_total"] = calc
        # contractor info
        if s.contractor_id:
            from app.models.contractor import Contractor
            contractor = await db.get(Contractor, s.contractor_id)
            d["contractor_name"] = contractor.name if contractor else None
            d["contractor_inn"] = contractor.inn if contractor else None
        else:
            d["contractor_name"] = None
            d["contractor_inn"] = None
        # org inn
        if s.org_id:
            from app.models.organization import Organization
            org = await db.get(Organization, s.org_id)
            d["org_inn"] = org.inn if org else None
        else:
            d["org_inn"] = None
        out.append(d)

    await db.commit()
    return out

@router.get("/{subsidy_id}", response_model=SubsidyOut)
async def get_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    calc = await calculate_budget_from_categories(db, subsidy.id)
    subsidy.calculated_budget = calc
    if calc > 0 and subsidy.budget != calc:
        subsidy.budget = calc
    await db.commit()

    d = {c.name: getattr(subsidy, c.name) for c in subsidy.__table__.columns}
    d["calculated_budget"] = calc
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = calc
    if subsidy.contractor_id:
        contractor = await db.get(Contractor, subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.post("/", response_model=SubsidyOut)
async def create_subsidy(
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    data = subsidy.dict()
    data['org_id'] = get_single_org_id(current_user) or current_user.org_id
    db_subsidy = Subsidy(**data)
    db.add(db_subsidy)
    await db.commit()
    await db.refresh(db_subsidy)

    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = 0.0
    d["feo_filled"] = False
    d["feo_budget_total"] = 0.0
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.put("/{subsidy_id}", response_model=SubsidyOut)
async def update_subsidy(
    subsidy_id: int,
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")
    old_budget = db_subsidy.budget  # capture BEFORE setattr loop
    for key, value in subsidy.dict().items():
        setattr(db_subsidy, key, value)

    calc = await calculate_budget_from_categories(db, subsidy_id)
    db_subsidy.calculated_budget = calc

    # Budget history write hook — track subsidy limit changes only (NOT calculated_budget)
    if old_budget != db_subsidy.budget:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=subsidy_id,
            purchase_id=None,
            entity_type="subsidy",
            old_value=float(old_budget) if old_budget is not None else None,
            new_value=float(db_subsidy.budget) if db_subsidy.budget is not None else None,
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    await db.commit()
    await db.refresh(db_subsidy)

    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = calc
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = calc
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    return d

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "account_owner")),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # Check for linked purchases
    from app.models.purchase import Purchase
    p_count = await db.scalar(
        select(Purchase).where(Purchase.subsidy_id == subsidy_id).limit(1)
    )
    if p_count:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить субсидию: есть связанные закупки. Сначала удалите или перенесите их."
        )

    # Cascade delete FEO categories (all levels, bottom-up by level desc)
    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.level.desc())
    )).scalars().all()
    for cat in cats:
        await db.delete(cat)

    await db.delete(db_subsidy)
    await db.commit()
    return {"message": "Субсидия удалена"}


# ── Per-subsidy contractor override endpoints ──

@router.get("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def get_contractor_override(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    if not override:
        # Return base contractor data as initial override
        contractor = await db.get(Contractor, subsidy.contractor_id)
        if not contractor:
            raise HTTPException(404, "Контрагент не найден")
        return {
            "id": 0,
            "subsidy_id": subsidy_id,
            "contractor_id": subsidy.contractor_id,
            "org_type": contractor.org_type,
            "inn": contractor.inn,
            "kpp": contractor.kpp,
            "ogrn": contractor.ogrn,
            "signatory": contractor.signatory,
            "signatory_basis": contractor.signatory_basis,
            "address": contractor.address,
            "postal_address": contractor.postal_address,
            "bank_details": contractor.bank_details,
            "settlement_account": contractor.settlement_account,
            "bank_name": contractor.bank_name,
            "bik": contractor.bik,
            "correspondent_account": contractor.correspondent_account,
            "contact_person": contractor.contact_person,
            "phone": contractor.phone,
            "email": contractor.email,
        }
    return override


@router.put("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def upsert_contractor_override(
    subsidy_id: int,
    data: SubsidyContractorOverrideCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    if override:
        for key, value in data.dict(exclude_unset=True).items():
            setattr(override, key, value)
    else:
        override = SubsidyContractorOverride(
            subsidy_id=subsidy_id,
            contractor_id=subsidy.contractor_id,
            **data.dict()
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return override


# ── Per-subsidy document templates ──────────────────────────────────────────

TEMPLATES_BASE = "/app/templates"
SUPPORTED_DOC_TYPES = {
    "contract":              "Договор",
    "contract_tz":           "Договор с ТЗ",
    "contract_fadm":         "Договор ФАДМ",
    "service_note":          "Служебная записка",
    "service_note_delivery": "СЗ на выдачу",
    "service_note_payment":  "СЗ на оплату",
    "approval_sheet":        "Лист согласования",
    "order_purchase":        "Приказ на закупку",
}


@router.get("/{subsidy_id}/templates")
async def list_subsidy_templates(
    subsidy_id: int,
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """List which doc types have a subsidy-specific template override."""
    result = []
    subsidy_dir = os.path.join(TEMPLATES_BASE, "subsidies", str(subsidy_id))
    for doc_type, label in SUPPORTED_DOC_TYPES.items():
        path = os.path.join(subsidy_dir, f"{doc_type}.docx")
        global_path = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")
        result.append({
            "doc_type": doc_type,
            "label": label,
            "has_custom": os.path.exists(path),
            "has_global": os.path.exists(global_path),
        })
    return result


def _repair_docx_template(path: str) -> list[str]:
    """Fix common Jinja2 errors in uploaded .docx templates.

    Word often splits {{ variable }} across multiple XML runs, and users
    accidentally put Russian text like 'г.' inside Jinja tags.
    Returns list of fixes applied.
    """
    fixes = []
    try:
        from docx import Document
        doc = Document(path)

        def _fix_paragraph(para):
            if not para.runs:
                return False
            full = "".join(r.text for r in para.runs)
            if "{{" not in full and "{%" not in full:
                return False

            original = full
            # Fix: {{ var something_russian }} -> {{ var }} something_russian
            # Pattern: inside {{ }}, after a valid variable name, remove non-ASCII chars
            def _clean_tag(m):
                inner = m.group(1)
                # Split into variable name and trailing junk
                parts = inner.strip().split()
                if len(parts) <= 1:
                    return m.group(0)  # just {{ var }} — ok
                var_name = parts[0]
                # Check if first part looks like a variable (ascii, underscores, dots)
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', var_name):
                    return m.group(0)
                # Remaining parts — check if they contain non-ASCII (Russian text)
                rest = " ".join(parts[1:])
                if any(ord(c) > 127 for c in rest):
                    return "{{ " + var_name + " }} " + rest
                return m.group(0)

            fixed = re.sub(r'\{\{([^}]+)\}\}', _clean_tag, full)

            # Fix doubled text like "г. г." that can result from prior fixes
            fixed = re.sub(r'(\b\w+\.)\s+\1', r'\1', fixed)

            if fixed == original:
                return False
            # Write back: all text into first run, clear rest
            para.runs[0].text = fixed
            for r in para.runs[1:]:
                r.text = ""
            return True

        count = 0
        for para in doc.paragraphs:
            if _fix_paragraph(para):
                count += 1
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if _fix_paragraph(para):
                            count += 1

        if count:
            doc.save(path)
            fixes.append(f"Исправлено {count} Jinja-тегов")

        # Validate the template renders
        from docxtpl import DocxTemplate
        tpl = DocxTemplate(path)
        tpl.get_undeclared_template_variables()

    except Exception as e:
        logger.warning("Template repair/validation warning for %s: %s", path, e)
        fixes.append(f"Предупреждение: {e}")

    return fixes


@router.put("/{subsidy_id}/templates/{doc_type}")
async def upload_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    file: UploadFile = File(...),
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """Upload a .docx template override for a specific subsidy and doc type."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    subsidy_dir = os.path.join(TEMPLATES_BASE, "subsidies", str(subsidy_id))
    os.makedirs(subsidy_dir, exist_ok=True)
    dest = os.path.join(subsidy_dir, f"{doc_type}.docx")

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    repairs = _repair_docx_template(dest)
    return {"ok": True, "doc_type": doc_type, "label": SUPPORTED_DOC_TYPES[doc_type], "repairs": repairs}


@router.get("/{subsidy_id}/templates/{doc_type}/download")
async def download_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """Download the current subsidy-specific template (or global if no override)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    subsidy_path = os.path.join(TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
    global_path = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")

    if os.path.exists(subsidy_path):
        path = subsidy_path
    elif os.path.exists(global_path):
        path = global_path
    else:
        raise HTTPException(404, "Шаблон не найден")

    response = FileResponse(
        path,
        filename=f"{doc_type}_{subsidy_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@router.delete("/{subsidy_id}/templates/{doc_type}")
async def delete_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    current_user=Depends(require_role(*MANAGER_ROLES)),
):
    """Delete subsidy-specific template override (falls back to global)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    path = os.path.join(TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Индивидуальный шаблон не найден")

    os.remove(path)
    return {"ok": True}


# ── Global template upload (admin) ──────────────────────────────────────────

@router.put("/global-templates/{doc_type}")
async def upload_global_template(
    doc_type: str,
    file: UploadFile = File(...),
    current_user=Depends(require_role(*ADMIN_ROLES)),
):
    """Upload a global .docx template (superadmin/account_owner only)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    dest = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    repairs = _repair_docx_template(dest)
    return {"ok": True, "doc_type": doc_type, "repairs": repairs}


@router.get("/{subsidy_id}/history")
async def get_budget_history(
    subsidy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*MANAGER_ROLES)),
):
    from app.models.budget_history import BudgetHistory as BudgetHistoryModel
    from sqlalchemy import func as safunc

    base_q = (
        select(BudgetHistoryModel)
        .where(BudgetHistoryModel.subsidy_id == subsidy_id)
        .order_by(BudgetHistoryModel.changed_at.desc())
    )

    total = (
        await db.execute(select(safunc.count()).select_from(base_q.subquery()))
    ).scalar() or 0

    rows = (await db.execute(base_q.offset(offset).limit(limit))).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "purchase_id": r.purchase_id,
                "old_value": float(r.old_value) if r.old_value is not None else None,
                "new_value": float(r.new_value) if r.new_value is not None else None,
                "changed_by_name": r.changed_by_name,
                "reason": r.reason,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ],
    }
