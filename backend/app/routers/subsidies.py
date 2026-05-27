import io
import os
import re
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    openpyxl = None

try:
    from docxtpl import DocxTemplate
except ImportError:
    DocxTemplate = None

logger = logging.getLogger(__name__)
from sqlalchemy import select, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, ProgrammingError
from app.database import get_db, engine
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.contractor import Contractor
from app.schemas.schemas import (
    SubsidyCreate, SubsidyOut,
    SubsidyContractorOverrideCreate, SubsidyContractorOverrideOut,
)
from app.auth.jwt import get_current_user, require_role, get_org_filter, get_single_org_id, MANAGER_ROLES, ADMIN_ROLES, ALL_ROLES
from app.auth.permissions import require_tab, require_action
from app.models.user import User
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])


@router.get("/diag/columns")
async def diag_columns(db: AsyncSession = Depends(get_db)):
    """Diagnostic endpoint — возвращает реальные колонки таблицы subsidies из information_schema."""
    result = await db.execute(text(
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_name = 'subsidies' "
        "ORDER BY ordinal_position"
    ))
    rows = result.fetchall()
    columns = [{"column_name": r[0], "data_type": r[1], "is_nullable": r[2]} for r in rows]
    logger.info("diag_columns: subsidies has %d columns: %s", len(columns), [c["column_name"] for c in columns])
    return {"table": "subsidies", "columns": columns}


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
            # Leaf node: use its budget
            return float(cat.budget) if cat.budget is not None else 0.0
        # Parent node: if budget is set manually (not null) → use it
        if cat.budget is not None:
            return float(cat.budget)
        # Auto mode (budget is null) → sum of children
        return sum(_calc_node(k) for k in kids)

    roots = [c for c in all_categories if c.level == 1]
    return sum(_calc_node(r) for r in roots)


@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # GET list is intentionally open to all authenticated users (incl. employee) so
    # that WishesView can populate the subsidy selector. Org-filter below already
    # limits visible subsidies to the user's own organisations. Write operations
    # (POST/PUT/DELETE/templates) remain gated by require_tab('subsidies').
    q = select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name)
    org_ids = get_org_filter(current_user)
    # 27.4-06: hard fallback для не-SaaS-ролей. Если JWT не содержит org_id/org_ids
    # И users.org_id = NULL — get_org_filter вернёт None → раньше employee видел ВСЕ
    # субсидии. Теперь подтягиваем все его memberships из user_organizations; если
    # их тоже нет — возвращаем пустой список (не привязан → ничего не видит).
    if org_ids is None and current_user.role not in ('superadmin', 'account_owner'):
        from app.models.user_organization import UserOrganization
        uo_rows = (await db.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == current_user.id)
        )).all()
        org_ids = list({r[0] for r in uo_rows if r[0]})
        # Fallback на legacy users.org_id (Багаутдинов и другие до backfill 26-G)
        if not org_ids and current_user.org_id:
            org_ids = [current_user.org_id]
        if not org_ids:
            return []
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
    current_user: User = Depends(require_tab('subsidies')),
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
    current_user: User = Depends(require_action('subsidy.edit')),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    old_budget = db_subsidy.budget  # capture BEFORE setattr loop

    # Step 1: log incoming payload
    payload = subsidy.model_dump() if hasattr(subsidy, 'model_dump') else subsidy.dict()
    logger.info("update_subsidy id=%s incoming payload: %s", subsidy_id, payload)

    calc = await calculate_budget_from_categories(db, subsidy_id)

    # Step 2: try normal setattr → commit
    for key, value in payload.items():
        setattr(db_subsidy, key, value)
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

    logger.info(
        "update_subsidy id=%s db_subsidy state before commit: name=%r year=%r budget=%r "
        "basis_doc_number=%r basis_doc_date=%r",
        subsidy_id,
        db_subsidy.name, db_subsidy.year, db_subsidy.budget,
        getattr(db_subsidy, 'basis_doc_number', '<attr_missing>'),
        getattr(db_subsidy, 'basis_doc_date', '<attr_missing>'),
    )

    try:
        await db.commit()
        await db.refresh(db_subsidy)
    except (ProgrammingError, IntegrityError) as exc:
        logger.warning(
            "update_subsidy id=%s commit failed (%s: %s), attempting ALTER fallback",
            subsidy_id, type(exc).__name__, exc,
        )
        await db.rollback()

        # ALTER fallback — отдельная транзакция вне текущей сессии
        from app.database import ensure_phase22_columns as _ensure_p22
        await _ensure_p22()

        # Перезагружаем объект и повторяем setattr
        result2 = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
        db_subsidy = result2.scalar_one_or_none()
        if not db_subsidy:
            raise HTTPException(status_code=404, detail="Subsidy not found after ALTER fallback")
        db.expire_all()

        for key, value in payload.items():
            setattr(db_subsidy, key, value)
        db_subsidy.calculated_budget = calc

        if old_budget != db_subsidy.budget:
            from app.models.budget_history import BudgetHistory as _BH2
            db.add(_BH2(
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
        logger.info("update_subsidy id=%s ALTER fallback commit succeeded", subsidy_id)

    # Step 4: raw SELECT to verify final DB state
    raw = await db.execute(
        text("SELECT id, name, year, budget, basis_doc_number, basis_doc_date FROM subsidies WHERE id = :id"),
        {"id": subsidy_id},
    )
    raw_row = raw.fetchone()
    logger.info("update_subsidy id=%s post-commit raw SELECT: %s", subsidy_id, raw_row)

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
    current_user: User = Depends(require_tab('subsidies')),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # Pre-check FK references to avoid 500 ForeignKeyViolationError
    from app.models.purchase import Purchase
    from app.models.contract import Contract

    p_count = await db.scalar(
        select(func.count()).select_from(Purchase).where(Purchase.subsidy_id == subsidy_id)
    )
    c_count = await db.scalar(
        select(func.count()).select_from(Contract).where(Contract.subsidy_id == subsidy_id)
    )
    if p_count or c_count:
        parts = []
        if p_count:
            parts.append(f"{p_count} закупок")
        if c_count:
            parts.append(f"{c_count} контрактов")
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить субсидию: связано {' и '.join(parts)}. Сначала удалите или перепривяжите их."
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
SUBSIDY_TEMPLATES_BASE = "/app/uploads/templates"
SUPPORTED_DOC_TYPES = {
    "contract":                 "Договор",
    "contract_tz":              "ТЗ (общий шаблон)",
    # tech_spec slot removed from SubsidiesView UI 2026-04-21 — the endpoint
    # still resolves to contract_tz.docx (see documents.py DOC_TYPES fallback)
    # for any client that requests /documents/tech_spec directly.
    "service_note_delivery":    "СЗ на выдачу",
    "service_note_payment":     "СЗ на оплату",
    # Phase 19.05: split ТЗ and dedicated SZ на закупку
    "service_note_procurement": "СЗ на закупку",
    # Phase 19.07: СЗ на аванс
    "service_note_advance":     "СЗ на аванс",
    "tech_spec_request":        "ТЗ для запроса цен",
    "tech_spec_contract":       "ТЗ для договора",
    "approval_sheet":           "Лист согласования",
    "order_purchase":           "Приказ на закупку",
    # Phase 28: typed contract forms per-subsidy
    "contract_services_large":      "Договор услуг (большая отчётность)",
    "contract_services_small":      "Договор услуг (малая отчётность)",
    "contract_services_food":       "Договор услуг (питание)",
    "contract_goods_single":        "Договор поставки (разовый)",
    "contract_gph_individual":      "Договор ГПХ с физ.лицом (без РИД)",
    "contract_gph_individual_rid":  "Договор ГПХ с физ.лицом (+РИД)",
    "contract_repair_vehicle":      "Договор на ремонт ТС",
    "contract_repair_framework":    "Рамочный договор на ремонт ТС",
}


@router.get("/{subsidy_id}/templates")
async def list_subsidy_templates(
    subsidy_id: int,
    current_user=Depends(require_tab('subsidies')),
):
    """List which doc types have a subsidy-specific template override."""
    result = []
    subsidy_dir = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id))
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


def _normalize_docx_template(path: str) -> dict:
    """Strip Word-internal markers that split jinja-placeholders across runs.

    Word inserts <w:proofErr/>, bookmarks, comments, lastRenderedPageBreak
    between runs inside `{{ var }}` / `{% ... %}` blocks during user editing.
    For text placeholders docxtpl can recover, but for InlineImage the tag
    MUST be inside a single contiguous run — otherwise the drawing element
    is silently dropped.

    Touches ONLY xml files where jinja syntax may live (document/header/
    footer/footnotes/endnotes). Avoiding [Content_Types].xml and *.rels —
    rewriting those breaks the package and was the root cause of the
    Phase 26-VV revert.

    Writes the cleaned bytes through a tempfile + atomic replace so the
    on-disk file stays valid even if a write is interrupted.
    """
    import zipfile as _zipfile
    import tempfile as _tempfile

    JINJA_BEARING = ('word/document.xml',)
    JINJA_BEARING_PREFIXES = ('word/header', 'word/footer')
    JINJA_BEARING_SUFFIXES = ('word/footnotes.xml', 'word/endnotes.xml')

    def _is_jinja_bearing(name: str) -> bool:
        if name in JINJA_BEARING or name in JINJA_BEARING_SUFFIXES:
            return True
        return any(name.startswith(p) and name.endswith('.xml') for p in JINJA_BEARING_PREFIXES)

    stats = {"proofErr": 0, "bookmark": 0, "comment": 0, "pageBreak": 0}
    tmp_fd, tmp_path = _tempfile.mkstemp(suffix=".docx", dir=os.path.dirname(path) or None)
    os.close(tmp_fd)
    try:
        with _zipfile.ZipFile(path, 'r') as zin:
            with _zipfile.ZipFile(tmp_path, 'w', _zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if _is_jinja_bearing(item.filename):
                        xml = data.decode('utf-8', errors='replace')
                        before_proof = xml.count('<w:proofErr')
                        xml = re.sub(r'<w:proofErr\s[^/]*?/>', '', xml)
                        stats["proofErr"] += before_proof - xml.count('<w:proofErr')

                        before_bm = xml.count('<w:bookmark')
                        xml = re.sub(r'<w:bookmarkStart\s[^/]*?/>', '', xml)
                        xml = re.sub(r'<w:bookmarkEnd\s[^/]*?/>', '', xml)
                        stats["bookmark"] += before_bm - xml.count('<w:bookmark')

                        before_cm = xml.count('<w:comment')
                        xml = re.sub(r'<w:commentRangeStart\s[^/]*?/>', '', xml)
                        xml = re.sub(r'<w:commentRangeEnd\s[^/]*?/>', '', xml)
                        xml = re.sub(r'<w:commentReference\s[^/]*?/>', '', xml)
                        stats["comment"] += before_cm - xml.count('<w:comment')

                        before_pb = xml.count('<w:lastRenderedPageBreak')
                        xml = re.sub(r'<w:lastRenderedPageBreak\s*/>', '', xml)
                        stats["pageBreak"] += before_pb - xml.count('<w:lastRenderedPageBreak')

                        data = xml.encode('utf-8')
                    zout.writestr(item, data)
        os.replace(tmp_path, path)
        logger.info("docx normalize %s: %s", path, stats)
    except Exception as e:
        logger.warning("docx normalize failed for %s: %s", path, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return stats


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

            # Fix: {{полностью_русский текст}} — снимаем маркеры, оставляем текст
            def _strip_if_all_non_ascii(m):
                inner = m.group(1).strip()
                if not inner:
                    return m.group(0)
                # Если ни одного ASCII-идентификаторного символа — это ремарка, не переменная
                if not re.search(r'[a-zA-Z_]', inner):
                    return inner
                return m.group(0)
            fixed = re.sub(r'\{\{([^}]+)\}\}', _strip_if_all_non_ascii, fixed)

            # Fix: {% русский текст %} — снимаем маркеры если не Jinja keyword
            _JINJA_KEYWORDS = {
                'if', 'else', 'elif', 'endif', 'for', 'endfor', 'set',
                'with', 'endwith', 'tr', 'block', 'endblock', 'macro',
                'endmacro', 'include', 'extends', 'import', 'from',
                'do', 'raw', 'endraw', 'call', 'endcall', 'filter',
                'endfilter', 'autoescape', 'endautoescape',
            }
            def _strip_pct_if_no_keyword(m):
                inner = m.group(1).strip().lstrip('-').rstrip('-').strip()
                if not inner:
                    return m.group(0)
                first = inner.split()[0].lower() if inner.split() else ''
                # Если первое слово — не Jinja keyword И не похоже на ASCII identifier — ремарка
                if first not in _JINJA_KEYWORDS and not re.match(r'^[a-zA-Z_]', first):
                    return inner
                return m.group(0)
            fixed = re.sub(r'\{%([^%]+)%\}', _strip_pct_if_no_keyword, fixed)

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
    current_user=Depends(require_tab('subsidies')),
):
    """Upload a .docx template override for a specific subsidy and doc type."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    subsidy_dir = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id))
    os.makedirs(subsidy_dir, exist_ok=True)
    dest = os.path.join(subsidy_dir, f"{doc_type}.docx")

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    norm_stats = _normalize_docx_template(dest)
    repairs = _repair_docx_template(dest)
    return {
        "ok": True,
        "doc_type": doc_type,
        "label": SUPPORTED_DOC_TYPES[doc_type],
        "repairs": repairs,
        "normalized": norm_stats,
    }


@router.get("/{subsidy_id}/templates/{doc_type}/download")
async def download_subsidy_template(
    subsidy_id: int,
    doc_type: str,
    current_user=Depends(require_tab('subsidies')),
):
    """Download the current subsidy-specific template (or global if no override)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    subsidy_path = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
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
    current_user=Depends(require_tab('subsidies')),
):
    """Delete subsidy-specific template override (falls back to global)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")

    path = os.path.join(SUBSIDY_TEMPLATES_BASE, "subsidies", str(subsidy_id), f"{doc_type}.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Индивидуальный шаблон не найден")

    os.remove(path)
    return {"ok": True}


# ── Global template upload (admin) ──────────────────────────────────────────

@router.put("/global-templates/{doc_type}")
async def upload_global_template(
    doc_type: str,
    file: UploadFile = File(...),
    current_user=Depends(require_action('subsidy.edit')),
):
    """Upload a global .docx template (superadmin/account_owner only)."""
    if doc_type not in SUPPORTED_DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}")
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "Допускаются только .docx файлы")

    dest = os.path.join(TEMPLATES_BASE, f"{doc_type}.docx")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    norm_stats = _normalize_docx_template(dest)
    repairs = _repair_docx_template(dest)
    return {"ok": True, "doc_type": doc_type, "repairs": repairs, "normalized": norm_stats}


@router.post("/templates/normalize-all")
async def normalize_all_existing_templates(
    current_user=Depends(require_action('subsidy.edit')),
):
    """One-shot migration: normalize every existing .docx template in place.

    Walks SUBSIDY_TEMPLATES_BASE and TEMPLATES_BASE, strips Word-internal
    markers from each file. Idempotent — safe to call multiple times.
    """
    processed = []
    errors = []

    def _walk_and_normalize(root: str):
        if not os.path.isdir(root):
            return
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".docx"):
                    continue
                fpath = os.path.join(dirpath, fn)
                try:
                    stats = _normalize_docx_template(fpath)
                    processed.append({"path": fpath, "stripped": stats})
                    try:
                        repairs = _repair_docx_template(fpath)
                        if repairs:
                            processed[-1]["repairs"] = repairs
                    except Exception as re_err:
                        errors.append({"path": fpath, "error": f"repair: {re_err}"})
                except Exception as e:
                    errors.append({"path": fpath, "error": str(e)})

    _walk_and_normalize(SUBSIDY_TEMPLATES_BASE)
    _walk_and_normalize(TEMPLATES_BASE)

    return {"ok": True, "processed": len(processed), "errors": len(errors), "details": processed, "error_details": errors}


@router.get("/{subsidy_id}/history")
async def get_budget_history(
    subsidy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('subsidies')),
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


# ── Plan-Graph Version endpoints (Phase 12-03) ────────────────────────────────

@router.get("/{subsidy_id}/plan-graph/versions")
async def list_plan_graph_versions(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return list of plan-graph versions for a subsidy (summary, no full snapshot)."""
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    vers = (await db.execute(
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(100)
    )).scalars().all()

    out = []
    for v in vers:
        snap = v.snapshot or {}
        out.append({
            "id": v.id,
            "version_number": v.version_number,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "created_by_name": v.created_by_name,
            "note": v.note,
            "effective_date": v.effective_date.isoformat() if v.effective_date else None,
            "total_planned": snap.get("total_planned", 0),
            "total_used": snap.get("total_used", 0),
            "item_count": len(snap.get("items", [])),
        })
    return out


@router.get("/{subsidy_id}/plan-graph/versions/{version_id}")
async def get_plan_graph_version(
    subsidy_id: int,
    version_id: int,
    with_reconciliation: bool = Query(False, description="Добавить факт по текущим закупкам"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return full snapshot for a specific plan-graph version.

    Optional ?with_reconciliation=true adds current actual PurchaseItem totals
    matched to snapshot tree nodes via composite-key matcher.
    """
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    ver = (await db.execute(
        select(_PGV).where(
            _PGV.id == version_id,
            _PGV.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()

    if not ver:
        raise HTTPException(404, "Версия план-графика не найдена")

    resp = {
        "id": ver.id,
        "subsidy_id": ver.subsidy_id,
        "version_number": ver.version_number,
        "created_at": ver.created_at.isoformat() if ver.created_at else None,
        "created_by_id": ver.created_by_id,
        "created_by_name": ver.created_by_name,
        "note": ver.note,
        "effective_date": ver.effective_date.isoformat() if ver.effective_date else None,
        "snapshot": ver.snapshot,
    }

    if with_reconciliation:
        snap = ver.snapshot or {}
        snap_tree = snap.get("tree")
        reconciliation: dict = {}

        if snap_tree:
            from app.models.feo_planned_item import FeoPlannedItem as _FPI
            from app.models.purchase_item import PurchaseItem as _PI

            # Load current live FeoCategory tree for this subsidy
            live_cats = (await db.execute(
                select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id).order_by(FeoCategory.id)
            )).scalars().all()

            def _build_live_tree_simple(cats, parent_id=None):
                nodes = []
                for c in cats:
                    if c.parent_id == parent_id:
                        nodes.append({
                            "id": c.id,
                            "name": c.name,
                            "level": c.level,
                            "code": c.code,
                            "children": _build_live_tree_simple(cats, parent_id=c.id),
                        })
                return nodes

            live_tree = _build_live_tree_simple(list(live_cats))
            live_cats_by_id = {c.id: c for c in live_cats}

            # Match snapshot tree → live tree
            match_result = _match_feo_nodes(snap_tree, live_tree)
            # match_result["matches"] = [(snap_node, live_node, match_type), ...]

            # For each live category, get PurchaseItem totals via FeoPlannedItem OR feo_category_id
            live_cat_ids = [c.id for c in live_cats]
            # FCAT-B3: SUM via feo_planned_item_id (legacy) + feo_category_id (new)
            cat_actual_map: dict[int, float] = {}
            if live_cat_ids:
                # Source 1: via FeoPlannedItem join (legacy ФАДМ_2026)
                actual_rows_via_fpi = (await db.execute(
                    select(
                        _FPI.feo_category_id,
                        func.coalesce(func.sum(_PI.total_price), 0).label("actual"),
                    )
                    .join(_PI, _PI.feo_planned_item_id == _FPI.id)
                    .where(_FPI.feo_category_id.in_(live_cat_ids))
                    .group_by(_FPI.feo_category_id)
                )).all()
                for r in actual_rows_via_fpi:
                    cat_actual_map[r.feo_category_id] = float(r.actual)

                # Source 2: via PurchaseItem.feo_category_id (FCAT-B1 new column)
                actual_rows_via_cat = (await db.execute(
                    select(
                        _PI.feo_category_id,
                        func.coalesce(func.sum(_PI.total_price), 0).label("actual"),
                    )
                    .where(_PI.feo_category_id.in_(live_cat_ids))
                    .group_by(_PI.feo_category_id)
                )).all()
                for r in actual_rows_via_cat:
                    cat_id = r.feo_category_id
                    cat_actual_map[cat_id] = cat_actual_map.get(cat_id, 0.0) + float(r.actual)

            def _subtree_actual(cat_id: int) -> float:
                """Recursively sum actual from cat and all its descendants."""
                total = cat_actual_map.get(cat_id, 0.0)
                cat = live_cats_by_id.get(cat_id)
                if cat:
                    for child in live_cats:
                        if child.parent_id == cat_id:
                            total += _subtree_actual(child.id)
                return total

            # Build reconciliation map keyed by snapshot node id
            for snap_node, live_node, match_type in match_result["matches"]:
                snap_id = snap_node.get("id")
                if snap_id is None:
                    continue
                live_id = live_node.get("id")
                budget_snap = float(snap_node.get("budget") or 0)
                actual = _subtree_actual(live_id) if live_id else 0.0
                reconciliation[str(snap_id)] = {
                    "matched_current_id": live_id,
                    "actual_used": round(actual, 2),
                    "actual_residual": round(budget_snap - actual, 2),
                    "match_type": match_type,
                }

            # Unmatched snapshot nodes → null
            for snap_node in match_result["only_a"]:
                snap_id = snap_node.get("id")
                if snap_id is not None:
                    reconciliation[str(snap_id)] = {
                        "matched_current_id": None,
                        "actual_used": 0.0,
                        "actual_residual": float(snap_node.get("budget") or 0),
                        "match_type": None,
                    }

        resp["reconciliation"] = reconciliation

    return resp


class PlanGraphVersionCreate(BaseModel):
    note: Optional[str] = None
    effective_date: Optional[date] = None


@router.post("/{subsidy_id}/plan-graph/versions")
async def create_plan_graph_version_manual(
    subsidy_id: int,
    body: PlanGraphVersionCreate = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Manually publish a plan-graph version (admin only)."""
    from app.routers.purchases import _create_plan_graph_version
    body = body or PlanGraphVersionCreate()
    await _create_plan_graph_version(
        subsidy_id,
        db,
        current_user,
        note=body.note or "Ручная публикация",
        effective_date=body.effective_date,
    )
    await db.commit()
    return {"ok": True, "message": "Версия план-графика сохранена"}


# ── Plan-Graph Export (Phase 12-04) ───────────────────────────────────────────

TEMPLATE_DIR = "media/plan_graph_templates"


def _render_plan_graph_workbook(tree: list, items: list, meta: dict):
    """
    Common renderer for plan-graph Excel workbook.

    Args:
        tree: recursive list of FeoCategory nodes
              [{id, name, level, code, appendix, budget, planned_amount,
                planned_quantity, unit, children:[...]}]
              If empty — fallback to flat `items` (v1 backward-compat).
        items: flat list of snapshot items (v1 backward-compat)
               [{name, planned_amount, used_amount, residual}]
        meta: dict with keys:
              subsidy_name, subsidy_year (optional), effective_date (str|None),
              version_number (int|None), note (str|None), generated_at (str|None)

    Returns:
        openpyxl.Workbook
    """
    if openpyxl is None:
        raise RuntimeError("openpyxl не установлен")

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    L1_FILL      = PatternFill("solid", fgColor="DBEAFE")
    L1_FONT      = Font(bold=True, size=9)
    L2_FILL      = PatternFill("solid", fgColor="F0F9FF")
    L2_FONT      = Font(bold=True, size=9, color="0C4A6E")
    L3_FILL      = PatternFill("solid", fgColor="F0FDF4")
    L3_FONT      = Font(size=9, color="166534")
    ITEM_FONT    = Font(size=9)
    RED_FONT     = Font(size=9, color="EF4444", bold=True)
    META_FONT    = Font(size=9, italic=True, color="374151")
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center")
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    HEADERS = [
        "№", "Направление расходов", "Тип расходов", "Наименование",
        "Ед.", "Кол-во план", "Плановая сумма, ₽",
        "Фактическая сумма, ₽", "Остаток, ₽",
        "% исполнения", "Исполнитель", "Статус",
    ]
    COL_WIDTHS = [5, 30, 25, 40, 8, 10, 18, 18, 18, 12, 30, 15]
    n_cols = len(HEADERS)
    last_col_letter = chr(64 + n_cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План-график"

    # ── Title row ─────────────────────────────────────────────────────────────
    subsidy_name = meta.get("subsidy_name", "")
    subsidy_year = meta.get("subsidy_year", "")
    title_text = f"ПЛАН-ГРАФИК — {subsidy_name}"
    if subsidy_year:
        title_text += f" ({subsidy_year})"
    ws.append([title_text] + [""] * (n_cols - 1))
    title_cell = ws.cell(row=1, column=1)
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{last_col_letter}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    # ── Meta info rows (version, effective_date, note, generated_at) ──────────
    meta_start_row = 2
    meta_rows = []
    if meta.get("version_number") is not None:
        meta_rows.append(f"Версия: {meta['version_number']}")
    if meta.get("effective_date"):
        meta_rows.append(f"Дата редакции: {meta['effective_date']}")
    if meta.get("note"):
        meta_rows.append(f"Примечание: {meta['note']}")
    if meta.get("generated_at"):
        meta_rows.append(f"Сформировано: {meta['generated_at']}")

    for i, mtext in enumerate(meta_rows):
        r = meta_start_row + i
        ws.append([mtext] + [""] * (n_cols - 1))
        cell = ws.cell(row=r, column=1)
        cell.font = META_FONT
        cell.alignment = LEFT_ALIGN
        ws.merge_cells(f"A{r}:{last_col_letter}{r}")
        ws.row_dimensions[r].height = 16

    # ── Column headers ────────────────────────────────────────────────────────
    header_row = meta_start_row + len(meta_rows)
    ws.append(HEADERS)
    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[header_row].height = 32
    ws.freeze_panes = f"A{header_row + 1}"

    row_num = header_row + 1
    seq = 0

    def _write_row(values, fill, font, height=20):
        nonlocal row_num
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            cell.alignment = RIGHT_ALIGN if col_idx >= 6 else LEFT_ALIGN
        ws.row_dimensions[row_num].height = height
        row_num += 1

    if tree:
        # ── Tree mode (schema_version=2) ──────────────────────────────────────
        def _traverse_node(node, direction_name="", type_name=""):
            nonlocal seq
            level = node.get("level", 1)
            name = node.get("name", "")
            code = node.get("code") or ""
            budget = node.get("budget")

            if level == 1:
                direction_name = name
                _write_row(
                    [code, name, "", "", "", "", budget or "", "", "", "", "", ""],
                    L1_FILL, L1_FONT, height=22,
                )
            elif level == 2:
                type_name = name
                _write_row(
                    ["", direction_name, name, "", "", "", budget or "", "", "", "", "", ""],
                    L2_FILL, L2_FONT,
                )
            elif level == 3:
                _write_row(
                    ["", direction_name, type_name, name, "", "", budget or "", "", "", "", "", ""],
                    L3_FILL, L3_FONT,
                )

            for child in node.get("children", []):
                _traverse_node(child, direction_name, type_name)

        for root in tree:
            _traverse_node(root)
    else:
        # ── Flat mode (v1 backward-compat) ─────────────────────────────────────
        for item in items:
            seq += 1
            planned = float(item.get("planned_amount") or 0)
            used = float(item.get("used_amount") or 0)
            residual = float(item.get("residual") or (planned - used))
            pct = round(used / planned * 100) if planned > 0 else 0
            status = "Выполнено" if pct >= 100 else ("В работе" if used > 0 else "Не начато")
            font = RED_FONT if used > planned else ITEM_FONT
            _write_row(
                [
                    seq, "", "", item.get("name", ""),
                    "", "",
                    round(planned, 2), round(used, 2), round(residual, 2),
                    f"{pct}%", "", status,
                ],
                PatternFill(), font,
            )

    return wb


@router.get("/{subsidy_id}/plan-graph/export")
async def export_plan_graph_excel(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export plan-graph as Excel file with full FEO hierarchy (live data)."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase import Purchase as _P
    from app.models.contractor import Contractor as _C

    cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
        .order_by(FeoCategory.level, FeoCategory.id)
    )).scalars().all()

    feo_items = (await db.execute(
        select(_FPI)
        .join(FeoCategory, _FPI.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(_FPI.is_active == True)
        .order_by(_FPI.id)
    )).scalars().all()

    item_ids = [i.id for i in feo_items]
    used_map: dict[int, float] = {}
    if item_ids:
        used_rows = (await db.execute(
            select(
                _PI.feo_planned_item_id,
                func.coalesce(func.sum(_PI.total_price), 0).label("used"),
            )
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .group_by(_PI.feo_planned_item_id)
        )).all()
        used_map = {r.feo_planned_item_id: float(r.used) for r in used_rows}

    contractor_map: dict[int, str] = {}
    if item_ids:
        c_rows = (await db.execute(
            select(_PI.feo_planned_item_id, _C.name.label("cname"))
            .join(_P, _PI.purchase_id == _P.id)
            .join(_C, _P.contractor_id == _C.id)
            .where(_PI.feo_planned_item_id.in_(item_ids))
            .distinct()
        )).all()
        for r in c_rows:
            if r.feo_planned_item_id not in contractor_map:
                contractor_map[r.feo_planned_item_id] = r.cname

    items_by_cat: dict[int, list] = {}
    for item in feo_items:
        items_by_cat.setdefault(item.feo_category_id, []).append(item)

    # Build live tree for _render_plan_graph_workbook
    def _build_live_tree(all_cats, parent_id=None):
        nodes = []
        for c in all_cats:
            if c.parent_id == parent_id:
                cat_items = items_by_cat.get(c.id, [])
                children = _build_live_tree(all_cats, parent_id=c.id)
                node = {
                    "id": c.id,
                    "name": c.name,
                    "level": c.level,
                    "code": c.code,
                    "appendix": c.appendix,
                    "budget": float(c.budget) if c.budget is not None else None,
                    "planned_amount": float(c.planned_amount) if c.planned_amount is not None else None,
                    "planned_quantity": float(c.planned_quantity) if c.planned_quantity is not None else None,
                    "unit": c.unit,
                    "children": children,
                    # live items embedded for leaf rendering
                    "_live_items": cat_items,
                    "_used_map": used_map,
                    "_contractor_map": contractor_map,
                }
                nodes.append(node)
        return nodes

    live_tree = _build_live_tree(list(cats))

    # Use dedicated live-render path (keeps contractor/used columns populated)
    from datetime import datetime as _dt
    meta = {
        "subsidy_name": sub.name,
        "subsidy_year": str(sub.year) if sub.year else "",
        "generated_at": _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Build workbook manually using existing logic (live tree with items)
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    HEADER_FILL  = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT  = Font(color="FFFFFF", bold=True, size=9)
    L1_FILL      = PatternFill("solid", fgColor="DBEAFE")
    L1_FONT      = Font(bold=True, size=9)
    L2_FILL      = PatternFill("solid", fgColor="F0F9FF")
    L2_FONT      = Font(bold=True, size=9, color="0C4A6E")
    L3_FILL      = PatternFill("solid", fgColor="F0FDF4")
    L3_FONT      = Font(size=9, color="166534")
    ITEM_FONT    = Font(size=9)
    RED_FONT     = Font(size=9, color="EF4444", bold=True)
    CENTER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN   = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center")
    THIN_BORDER  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    HEADERS = [
        "№", "Направление расходов", "Тип расходов", "Наименование",
        "Ед.", "Кол-во план", "Плановая сумма, ₽",
        "Фактическая сумма, ₽", "Остаток, ₽",
        "% исполнения", "Исполнитель", "Статус",
    ]
    COL_WIDTHS = [5, 30, 25, 40, 8, 10, 18, 18, 18, 12, 30, 15]

    cats_by_parent: dict = {}
    for c in cats:
        cats_by_parent.setdefault(c.parent_id, []).append(c)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "План-график"

    ws.append(HEADERS)
    for col_idx, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"

    row_num = 2
    seq = 0

    def _write_row(values, fill, font, height=20):
        nonlocal row_num
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.fill = fill
            cell.font = font
            cell.border = THIN_BORDER
            cell.alignment = RIGHT_ALIGN if col_idx >= 6 else LEFT_ALIGN
        ws.row_dimensions[row_num].height = height
        row_num += 1

    def _traverse(cat, direction_name="", type_name=""):
        nonlocal seq
        if cat.level == 1:
            direction_name = cat.name
            _write_row(
                [cat.code or "", cat.name, "", "", "", "", "", "", "", "", "", ""],
                L1_FILL, L1_FONT, height=22
            )
        elif cat.level == 2:
            type_name = cat.name
            _write_row(
                ["", direction_name, cat.name, "", "", "", "", "", "", "", "", ""],
                L2_FILL, L2_FONT
            )
        elif cat.level == 3:
            _write_row(
                ["", direction_name, type_name, cat.name, "", "", "", "", "", "", "", ""],
                L3_FILL, L3_FONT
            )
            for item in items_by_cat.get(cat.id, []):
                seq += 1
                planned = float(item.amount or 0)
                used = used_map.get(item.id, 0.0)
                residual = planned - used
                pct = round(used / planned * 100) if planned > 0 else 0
                contractor = contractor_map.get(item.id, "")
                status = "Выполнено" if pct >= 100 else ("В работе" if used > 0 else "Не начато")
                font = RED_FONT if used > planned else ITEM_FONT
                _write_row(
                    [
                        seq, direction_name, type_name, item.name,
                        item.unit or "", float(item.quantity or 0),
                        round(planned, 2), round(used, 2), round(residual, 2),
                        f"{pct}%", contractor, status,
                    ],
                    PatternFill(), font
                )

        for child in cats_by_parent.get(cat.id, []):
            _traverse(child, direction_name, type_name)

    for root in cats_by_parent.get(None, []):
        _traverse(root)

    ws.insert_rows(1)
    title_cell = ws.cell(row=1, column=1, value=f"ПЛАН-ГРАФИК — {sub.name} ({sub.year})")
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{chr(64 + len(HEADERS))}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"plan_graph_{safe_name}_{sub.year}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{subsidy_id}/plan-graph/versions/{version_id}/export")
async def export_plan_graph_version_excel(
    subsidy_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a specific plan-graph version snapshot as Excel."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from datetime import datetime as _dt

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    ver = (await db.execute(
        select(_PGV).where(
            _PGV.id == version_id,
            _PGV.subsidy_id == subsidy_id,
        )
    )).scalar_one_or_none()
    if not ver:
        raise HTTPException(404, "Версия план-графика не найдена")

    snap = ver.snapshot or {}
    tree = snap.get("tree", [])
    flat_items = snap.get("items", [])

    eff_date = ver.effective_date.isoformat() if ver.effective_date else (
        snap.get("effective_date") or None
    )
    created_at_str = ver.created_at.strftime("%Y-%m-%d %H:%M UTC") if ver.created_at else None

    meta = {
        "subsidy_name": sub.name,
        "subsidy_year": str(sub.year) if sub.year else "",
        "version_number": ver.version_number,
        "effective_date": eff_date,
        "note": ver.note,
        "generated_at": created_at_str,
    }

    wb = _render_plan_graph_workbook(tree, flat_items, meta)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    date_part = (eff_date or (ver.created_at.strftime("%Y-%m-%d") if ver.created_at else "nodate"))
    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:30]
    filename = f"subsidy-{subsidy_id}_v{ver.version_number}_{date_part}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Plan-Graph Compare (Phase 12-05) ─────────────────────────────────────────


def _normalize_name(name: str) -> str:
    """Normalize FeoCategory name for matching: lowercase, strip, collapse spaces."""
    return re.sub(r"\s+", " ", (name or "").lower().strip())


def _match_feo_nodes(tree_a: list, tree_b: list) -> dict:
    """
    Match nodes from two FeoCategory trees using composite key priority:
      1. code (if both non-empty)
      2. (level, parent_path, normalized_name) — parent_path = tuple of normalized ancestor names
      3. (level, normalized_name) — fallback if parent renamed → marked as 'moved'

    Returns:
      {
        "matches": [(node_a, node_b, match_type)],  # match_type: 'code'|'path'|'fallback'
        "only_a": [node_a, ...],
        "only_b": [node_b, ...],
      }
    """
    def _flatten(tree, parent_path=()):
        nodes = []
        for node in tree:
            path = parent_path + (_normalize_name(node.get("name", "")),)
            nodes.append((node, path))
            nodes.extend(_flatten(node.get("children", []), path))
        return nodes

    flat_a = _flatten(tree_a)
    flat_b = _flatten(tree_b)

    matched_b = set()
    matched_a = set()
    matches = []

    # Pass 1: match by code
    code_map_b: dict[str, tuple] = {}
    for nb, pb in flat_b:
        code = (nb.get("code") or "").strip()
        if code:
            code_map_b[code] = (nb, pb)

    for na, pa in flat_a:
        code = (na.get("code") or "").strip()
        if code and code in code_map_b:
            nb, pb = code_map_b[code]
            id_b = id(nb)
            id_a = id(na)
            if id_b not in matched_b and id_a not in matched_a:
                matches.append((na, nb, "code"))
                matched_a.add(id_a)
                matched_b.add(id_b)

    # Pass 2: match by (level, parent_path, normalized_name)
    path_map_b: dict[tuple, tuple] = {}
    for nb, pb in flat_b:
        if id(nb) not in matched_b:
            key = (nb.get("level", 0), pb[:-1], _normalize_name(nb.get("name", "")))
            if key not in path_map_b:
                path_map_b[key] = (nb, pb)

    for na, pa in flat_a:
        if id(na) in matched_a:
            continue
        key = (na.get("level", 0), pa[:-1], _normalize_name(na.get("name", "")))
        if key in path_map_b:
            nb, pb = path_map_b[key]
            if id(nb) not in matched_b:
                matches.append((na, nb, "path"))
                matched_a.add(id(na))
                matched_b.add(id(nb))

    # Pass 3: fallback (level, normalized_name) — marks as 'fallback' → UI shows 'moved'
    name_level_map_b: dict[tuple, tuple] = {}
    for nb, pb in flat_b:
        if id(nb) not in matched_b:
            key = (nb.get("level", 0), _normalize_name(nb.get("name", "")))
            if key not in name_level_map_b:
                name_level_map_b[key] = (nb, pb)

    for na, pa in flat_a:
        if id(na) in matched_a:
            continue
        key = (na.get("level", 0), _normalize_name(na.get("name", "")))
        if key in name_level_map_b:
            nb, pb = name_level_map_b[key]
            if id(nb) not in matched_b:
                matches.append((na, nb, "fallback"))
                matched_a.add(id(na))
                matched_b.add(id(nb))

    only_a = [na for na, pa in flat_a if id(na) not in matched_a]
    only_b = [nb for nb, pb in flat_b if id(nb) not in matched_b]

    return {"matches": matches, "only_a": only_a, "only_b": only_b}


def _build_compare_rows(tree_a: list, tree_b: list) -> list:
    """
    Build flat list of comparison rows for JSON/Excel output.
    Each row: {path, level, name_v1, name_v2, code, budget_v1, budget_v2,
               delta, delta_pct, status}
    status: unchanged | changed | new | removed | moved
    """
    match_result = _match_feo_nodes(tree_a, tree_b)
    match_by_a_id = {id(na): (nb, mtype) for na, nb, mtype in match_result["matches"]}
    matched_b_ids = {id(nb) for _, nb, _ in match_result["matches"]}

    rows = []

    def _walk_a(nodes, parent_path=()):
        for node in nodes:
            path = parent_path + (node.get("name", ""),)
            v1 = float(node.get("budget") or 0)
            mid = id(node)
            if mid in match_by_a_id:
                nb, mtype = match_by_a_id[mid]
                v2 = float(nb.get("budget") or 0)
                delta = v2 - v1
                delta_pct = round(delta / v1 * 100, 2) if v1 != 0 else None
                if mtype == "fallback":
                    status = "moved"
                elif abs(delta) < 0.01:
                    status = "unchanged"
                else:
                    status = "changed"
                rows.append({
                    "path": list(path),
                    "level": node.get("level", 0),
                    "name_v1": node.get("name"),
                    "name_v2": nb.get("name"),
                    "code": node.get("code") or nb.get("code"),
                    "budget_v1": round(v1, 2),
                    "budget_v2": round(v2, 2),
                    "delta": round(delta, 2),
                    "delta_pct": delta_pct,
                    "status": status,
                })
            else:
                rows.append({
                    "path": list(path),
                    "level": node.get("level", 0),
                    "name_v1": node.get("name"),
                    "name_v2": None,
                    "code": node.get("code"),
                    "budget_v1": round(v1, 2),
                    "budget_v2": 0.0,
                    "delta": round(-v1, 2),
                    "delta_pct": -100.0 if v1 != 0 else None,
                    "status": "removed",
                })
            _walk_a(node.get("children", []), path)

    def _walk_only_b(nodes):
        for node in nodes:
            if id(node) not in matched_b_ids:
                v2 = float(node.get("budget") or 0)
                rows.append({
                    "path": [node.get("name", "")],
                    "level": node.get("level", 0),
                    "name_v1": None,
                    "name_v2": node.get("name"),
                    "code": node.get("code"),
                    "budget_v1": 0.0,
                    "budget_v2": round(v2, 2),
                    "delta": round(v2, 2),
                    "delta_pct": None,
                    "status": "new",
                })

    _walk_a(tree_a)

    def _collect_b_nodes(nodes):
        result = []
        for n in nodes:
            result.append(n)
            result.extend(_collect_b_nodes(n.get("children", [])))
        return result

    all_b = _collect_b_nodes(tree_b)
    for nb in all_b:
        if id(nb) not in matched_b_ids:
            v2 = float(nb.get("budget") or 0)
            rows.append({
                "path": [nb.get("name", "")],
                "level": nb.get("level", 0),
                "name_v1": None,
                "name_v2": nb.get("name"),
                "code": nb.get("code"),
                "budget_v1": 0.0,
                "budget_v2": round(v2, 2),
                "delta": round(v2, 2),
                "delta_pct": None,
                "status": "new",
            })

    return rows


@router.get("/{subsidy_id}/plan-graph/versions/compare")
async def compare_plan_graph_versions(
    subsidy_id: int,
    v1: int = Query(..., description="ID первой версии"),
    v2: int = Query(..., description="ID второй версии"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two plan-graph versions and return JSON diff."""
    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    ver1 = (await db.execute(
        select(_PGV).where(_PGV.id == v1, _PGV.subsidy_id == subsidy_id)
    )).scalar_one_or_none()
    ver2 = (await db.execute(
        select(_PGV).where(_PGV.id == v2, _PGV.subsidy_id == subsidy_id)
    )).scalar_one_or_none()

    if not ver1:
        raise HTTPException(404, f"Версия {v1} не найдена")
    if not ver2:
        raise HTTPException(404, f"Версия {v2} не найдена")

    snap1 = ver1.snapshot or {}
    snap2 = ver2.snapshot or {}
    tree1 = snap1.get("tree")
    tree2 = snap2.get("tree")

    if not tree1:
        raise HTTPException(
            422,
            f"Старая версия v{ver1.version_number} не содержит дерева ФЭО "
            f"(создана до Phase 12-05). Сравнение недоступно.",
        )
    if not tree2:
        raise HTTPException(
            422,
            f"Старая версия v{ver2.version_number} не содержит дерева ФЭО "
            f"(создана до Phase 12-05). Сравнение недоступно.",
        )

    rows = _build_compare_rows(tree1, tree2)

    def _ver_meta(ver, snap):
        return {
            "id": ver.id,
            "version_number": ver.version_number,
            "effective_date": ver.effective_date.isoformat() if ver.effective_date else snap.get("effective_date"),
            "note": ver.note,
            "created_at": ver.created_at.isoformat() if ver.created_at else None,
            "total_planned": snap.get("total_planned", 0),
        }

    return {
        "v1_meta": _ver_meta(ver1, snap1),
        "v2_meta": _ver_meta(ver2, snap2),
        "rows": rows,
    }


@router.get("/{subsidy_id}/plan-graph/versions/compare.xlsx")
async def compare_plan_graph_versions_excel(
    subsidy_id: int,
    v1: int = Query(..., description="ID первой версии"),
    v2: int = Query(..., description="ID второй версии"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two plan-graph versions and return Excel diff."""
    if openpyxl is None:
        raise HTTPException(500, "openpyxl не установлен")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к субсидии")

    ver1 = (await db.execute(
        select(_PGV).where(_PGV.id == v1, _PGV.subsidy_id == subsidy_id)
    )).scalar_one_or_none()
    ver2 = (await db.execute(
        select(_PGV).where(_PGV.id == v2, _PGV.subsidy_id == subsidy_id)
    )).scalar_one_or_none()

    if not ver1:
        raise HTTPException(404, f"Версия {v1} не найдена")
    if not ver2:
        raise HTTPException(404, f"Версия {v2} не найдена")

    snap1 = ver1.snapshot or {}
    snap2 = ver2.snapshot or {}
    tree1 = snap1.get("tree")
    tree2 = snap2.get("tree")

    if not tree1:
        raise HTTPException(
            422,
            f"Старая версия v{ver1.version_number} не содержит дерева ФЭО "
            f"(создана до Phase 12-05). Сравнение недоступно.",
        )
    if not tree2:
        raise HTTPException(
            422,
            f"Старая версия v{ver2.version_number} не содержит дерева ФЭО "
            f"(создана до Phase 12-05). Сравнение недоступно.",
        )

    rows = _build_compare_rows(tree1, tree2)

    # ── Build Excel ──────────────────────────────────────────────────────────
    HEADER_FILL   = PatternFill("solid", fgColor="1E3A5F")
    HEADER_FONT   = Font(color="FFFFFF", bold=True, size=9)
    META_FONT     = Font(size=9, italic=True, color="374151")
    ITEM_FONT     = Font(size=9)
    CENTER_ALIGN  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT_ALIGN    = Alignment(horizontal="left", vertical="center", wrap_text=True)
    RIGHT_ALIGN   = Alignment(horizontal="right", vertical="center")
    THIN_BORDER   = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    STATUS_FILLS = {
        "changed":   PatternFill("solid", fgColor="FFF3CD"),
        "new":       PatternFill("solid", fgColor="D4EDDA"),
        "removed":   PatternFill("solid", fgColor="F8D7DA"),
        "moved":     PatternFill("solid", fgColor="D1ECF1"),
        "unchanged": PatternFill(),
    }
    STATUS_LABELS = {
        "changed": "Изменено",
        "new": "Новое",
        "removed": "Удалено",
        "moved": "Перемещено",
        "unchanged": "Без изменений",
    }

    HEADERS = [
        "№", "Уровень", "Наименование", "Код",
        f"План v{ver1.version_number} (₽)", f"План v{ver2.version_number} (₽)",
        "Дельта (₽)", "Дельта (%)", "Статус",
    ]
    COL_WIDTHS = [5, 8, 50, 15, 18, 18, 18, 12, 15]
    n_cols = len(HEADERS)
    last_col = chr(64 + n_cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сравнение версий"

    # Title
    title_v1_date = ver1.effective_date.isoformat() if ver1.effective_date else (snap1.get("effective_date") or ver1.created_at.strftime("%Y-%m-%d") if ver1.created_at else "—")
    title_v2_date = ver2.effective_date.isoformat() if ver2.effective_date else (snap2.get("effective_date") or ver2.created_at.strftime("%Y-%m-%d") if ver2.created_at else "—")
    ws.append([f"СРАВНЕНИЕ ВЕРСИЙ — {sub.name}"] + [""] * (n_cols - 1))
    title_cell = ws.cell(row=1, column=1)
    title_cell.font = Font(bold=True, size=12, color="1E3A5F")
    ws.merge_cells(f"A1:{last_col}1")
    title_cell.alignment = CENTER_ALIGN
    ws.row_dimensions[1].height = 28

    # Meta rows
    meta_texts = [
        f"v{ver1.version_number}: {title_v1_date}" + (f" — {ver1.note}" if ver1.note else ""),
        f"v{ver2.version_number}: {title_v2_date}" + (f" — {ver2.note}" if ver2.note else ""),
        f"Итого v{ver1.version_number}: {snap1.get('total_planned', 0):,.2f} ₽  |  "
        f"Итого v{ver2.version_number}: {snap2.get('total_planned', 0):,.2f} ₽  |  "
        f"Дельта: {(snap2.get('total_planned', 0) - snap1.get('total_planned', 0)):+,.2f} ₽",
    ]
    for i, mtext in enumerate(meta_texts):
        r = 2 + i
        ws.append([mtext] + [""] * (n_cols - 1))
        cell = ws.cell(row=r, column=1)
        cell.font = META_FONT
        cell.alignment = LEFT_ALIGN
        ws.merge_cells(f"A{r}:{last_col}{r}")
        ws.row_dimensions[r].height = 16

    # Column headers
    header_row = 2 + len(meta_texts)
    ws.append(HEADERS)
    for col_idx, (h, w) in enumerate(zip(HEADERS, COL_WIDTHS), 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[header_row].height = 32
    ws.freeze_panes = f"A{header_row + 1}"

    # Data rows
    for seq_i, row in enumerate(rows, 1):
        level = row["level"]
        indent = "    " * (level - 1) if level > 0 else ""
        name = row["name_v2"] or row["name_v1"] or ""
        status = row["status"]
        fill = STATUS_FILLS.get(status, PatternFill())
        delta_pct_str = f"{row['delta_pct']:+.1f}%" if row["delta_pct"] is not None else "—"

        data_row_num = header_row + seq_i
        values = [
            seq_i, level, indent + name, row.get("code") or "",
            row["budget_v1"], row["budget_v2"],
            row["delta"], delta_pct_str,
            STATUS_LABELS.get(status, status),
        ]
        ws.append(values)
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=data_row_num, column=col_idx)
            cell.fill = fill
            cell.font = ITEM_FONT
            cell.border = THIN_BORDER
            if col_idx == 3:
                cell.alignment = LEFT_ALIGN
            elif col_idx >= 5:
                cell.alignment = RIGHT_ALIGN
            else:
                cell.alignment = CENTER_ALIGN
        ws.row_dimensions[data_row_num].height = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"subsidy-{subsidy_id}_compare_v{ver1.version_number}_vs_v{ver2.version_number}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{subsidy_id}/plan-graph/template")
async def upload_plan_graph_template(
    subsidy_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
):
    """Upload a .docx Word template for this subsidy's plan-graph export."""
    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Только .docx файлы поддерживаются")

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    dest = os.path.join(TEMPLATE_DIR, f"subsidy_{subsidy_id}.docx")
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return {"ok": True, "template_path": dest, "message": "Шаблон загружен"}


@router.get("/{subsidy_id}/plan-graph/export-docx")
async def export_plan_graph_docx(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fill the uploaded .docx template via docxtpl and return the filled document."""
    if DocxTemplate is None:
        raise HTTPException(500, "docxtpl не установлен")

    sub = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Субсидия не найдена")

    template_path = os.path.join(TEMPLATE_DIR, f"subsidy_{subsidy_id}.docx")
    if not os.path.exists(template_path):
        raise HTTPException(404, "Шаблон не загружен. Загрузите через POST /plan-graph/template")

    org_ids = get_org_filter(current_user)
    if org_ids is not None and sub.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа")

    from app.models.plan_graph_version import PlanGraphVersion as _PGV
    from datetime import datetime as _dt

    latest_ver = (await db.execute(
        select(_PGV)
        .where(_PGV.subsidy_id == subsidy_id)
        .order_by(_PGV.version_number.desc())
        .limit(1)
    )).scalar_one_or_none()

    if latest_ver and latest_ver.snapshot:
        snap = latest_ver.snapshot
        items_ctx = snap.get("items", [])
        total_planned = snap.get("total_planned", 0)
        total_used = snap.get("total_used", 0)
    else:
        items_ctx = []
        total_planned = 0.0
        total_used = 0.0

    context = {
        "subsidy_name": sub.name,
        "subsidy_year": sub.year,
        "items": items_ctx,
        "total_planned": f"{total_planned:,.2f}",
        "total_used": f"{total_used:,.2f}",
        "total_residual": f"{total_planned - total_used:,.2f}",
        "export_date": _dt.now().strftime("%d.%m.%Y"),
    }

    doc = DocxTemplate(template_path)
    doc.render(context)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    safe_name = sub.name.replace(" ", "_").replace("/", "_")[:40]
    filename = f"plan_graph_{safe_name}_{sub.year}.docx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
