import os
import re
from io import BytesIO
from datetime import date
from decimal import Decimal
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.models.feo_category import FeoCategory
from app.models.event import Event
from app.auth.jwt import get_current_user
from app.routers.purchases import is_framework_head, _generate_temp_contract_number
from app.services.fio import compose_fio as _compose_fio
from app.services.responsible_role import is_responsible_role, is_blank_person_name, RESPONSIBLE_PLACEHOLDER
from typing import Optional
import logging

logger = logging.getLogger(__name__)


from app.services.documents.morphology import (
    _morph,
    _petro,
    _get_morph,
    _get_petro,
    _to_gen_word_heuristic,
    _to_gen_word,
    _to_gen_phrase,
    _inflect_phrase_genitive,
    _to_gen_fio,
)
from app.services.documents.doc_types import (
    TEMPLATES_DIR,
    SUBSIDY_TEMPLATES_DIR,
    RECEIPTS_TABLE_MARKER,
    DOC_TYPES,
    CONTRACT_FAMILY_DOC_TYPES,
    CONTRACT_TYPED_FORM_DOC_TYPES,
    DOC_TYPE_FALLBACK_FILES,
    _BASIS_LABELS,
    _PURCHASE_METHOD_LABELS,
    _COMPETITIVE_FORM_LABELS,
    PURCHASE_METHOD_REQUIRED_DOC_TYPES,
    VAT_RATE_PRINTED_DOC_TYPES,
    VAT_EXEMPTION_ARTICLE_NPD,
    VAT_EXEMPTION_ARTICLE_GPH_INDIVIDUAL,
    _GPH_INDIVIDUAL_CONTRACT_FORMS,
    FEO_PATH_UNRESOLVED_LABEL,
    FABRIKANT_PKG_FILE_NAMES,
    TEMPLATE_VARIABLES,
)
from app.services.documents.formatting import (
    _fmt_date,
    _clean_id,
    _fmt_money,
    _fmt_money_plain,
    _merge_identical_items,
    _signatory_position,
    _fio_to_genitive,
    _format_initials,
    _format_initials_safe,
    _INITIALS_WORD_RE,
    _resolve_responsible_person_update,
    _fio_to_initials,
    _fio_to_initials_prefix,
    _chunk_to_words,
    _rubles_to_words,
    _ONES,
    _TENS,
    _HUNDREDS,
    _ONES_F,
)
from app.services.documents.templates import (
    _sanitize_subject,
    _insert_receipts_table_if_marker,
    _resolve_doc_template_path,
    _purchase_method_label,
    _resolve_vat_exemption_basis,
    _require_vat_rate_for_doc,
    _vat_exemption_missing_hint,
    _require_purchase_method_for_doc,
)
from app.services.documents.contexts import (
    _signatory_split,
    _sum_items_price,
    _build_acceptance_doc_context,
    _build_contract_items_context,
    _build_contract_item_feo_paths,
    _build_items_list_from_contract_items,
    _build_items_list_from_purchase_items,
    _resolve_doc_amount,
    _require_contract_items_for_doc,
    _resolve_user_dept,
    _resolve_user_position,
    _format_service_term,
)
from app.services.documents.docx_post import _strip_tech_spec_legend, _strip_word_comments
from app.services.documents.fabrikant_package import render_fabrikant_package_files
from app.services.documents.kp_xlsx import build_kp_xlsx


router = APIRouter(prefix="/api/purchases", tags=["documents"])
guide_router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{pid}/documents/{doc_type}")
async def generate_document(
    pid: int,
    doc_type: str,
    approver_ids: Optional[str] = Query(default=None, description="ID согласующих через запятую"),
    initiator_id: Optional[int] = Query(default=None, description="ID инициатора служебной записки"),
    responsible_name: Optional[str] = Query(default=None, description="ФИО ответственного исполнителя (переопределяет поле закупки)"),
    tz_override_mode: Optional[str] = Query(default=None, description="Переопределить режим ТЗ: 'exact' или '44fz'"),
    merge: Optional[str] = Query(default=None, description="Phase 19.06: merge with another doc_type (e.g. 'tech_spec_contract') — appends its paragraphs/tables as a new section after the primary doc"),
    doc_indices: Optional[str] = Query(default=None, description="Phase 27.2: CSV индексов acceptance_docs для СЗ на оплату/аванс (напр. '0,2,3')"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"Неизвестный тип документа: {doc_type}. Доступны: {', '.join(DOC_TYPES)}")

    # Резолв шаблона: субсидийный override нужен по subsidy_id закупки, которая
    # ещё не загружена — на этом шаге резолвим без него (subsidy_id=None), только
    # чтобы рано отбить полностью отсутствующий шаблон (глобальный + fallback).
    # Полный резолв (с субсидийным override) повторяется ниже, после загрузки p.
    template_path, template_file, filename_base = _resolve_doc_template_path(doc_type, None)
    if not os.path.exists(template_path):
        raise HTTPException(
            404,
            f"Шаблон '{template_file}' не найден. "
            f"Поместите файл в backend/templates/{template_file}"
        )

    # Load purchase with related data
    from app.models.contract_item import ContractItem as _ContractItem  # Phase 27.1 CD-5
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.contract_items),  # Phase 27.1 CD-5: eager-load for docxtpl context
            selectinload(Purchase.assigned_user),  # B-dedup: для авто-инициалов responsible_person
            selectinload(Purchase.service_note_author),  # fallback «Ответственный исполнитель» = автор СЗ
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # Запоминаем выбранного ответственного (см. _resolve_responsible_person_update
    # выше) — чтобы он подставлялся сам при следующей генерации и не «терялся».
    _new_responsible_person = _resolve_responsible_person_update(p.responsible_person, responsible_name)
    if _new_responsible_person is not None:
        p.responsible_person = _new_responsible_person
        await db.commit()

    # Владелец (2026-08-31): рамочная голова может подписываться («лист
    # согласования») раньше, чем станут известны реальные номер и дата
    # договора — при первом формировании договорного документа для такой
    # закупки без contract_number система присваивает технический номер
    # («ВРЕМ-{№закупки}») и сегодняшнюю дату, отмечая их флагом
    # contract_number_is_temporary для последующей актуализации (см.
    # POST /api/purchases/{pid}/actualize-contract-number). Уже заполненный
    # пользователем contract_number НЕ трогаем.
    if doc_type in CONTRACT_FAMILY_DOC_TYPES and is_framework_head(p) and not p.contract_number:
        p.contract_number = await _generate_temp_contract_number(p, db)
        p.contract_date = date.today()
        p.contract_number_is_temporary = True
        # async_session(expire_on_commit=False) — объект и его eager-loaded
        # relationships (items/contract_items/...) остаются в памяти как есть,
        # refresh() здесь не нужен и опасен (expire + возможный lazy-load вне
        # async greenlet при последующем чтении relationship ниже по коду).
        await db.commit()

    # Требование владельца («Плановые не равно Договор»): для договорных
    # типов документа позиции/суммы обязаны быть заполнены в ContractItem —
    # никакого молчаливого отката на plan/НМЦК. Гейт стоит максимально рано,
    # до тяжёлых запросов ниже.
    _require_contract_items_for_doc(p, doc_type)
    _require_purchase_method_for_doc(p, doc_type)
    _require_vat_rate_for_doc(p, doc_type)

    # Override template path with subsidy-specific template if available
    template_path, template_file, filename_base = _resolve_doc_template_path(doc_type, p.subsidy_id)

    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()

    # Phase 23: Customer = Organization owning the subsidy. Loads linked Contractor (FK)
    # for banking details (r/s, bank_name, BIK, k/s).
    customer_org = None
    customer_ctr = None  # Contractor linked to org via FK
    if subsidy and subsidy.org_id:
        from app.models.organization import Organization
        org_r = await db.execute(select(Organization).where(Organization.id == subsidy.org_id))
        customer_org = org_r.scalar_one_or_none()
        if customer_org and customer_org.contractor_id:
            from app.models.contractor import Contractor as _CtrCust
            ctr_r = await db.execute(select(_CtrCust).where(_CtrCust.id == customer_org.contractor_id))
            customer_ctr = ctr_r.scalar_one_or_none()

    # Load event if linked
    event = None
    if p.event_id:
        ev_r = await db.execute(select(Event).where(Event.id == p.event_id))
        event = ev_r.scalar_one_or_none()

    # Load approvers if requested
    selected_approvers = []
    if approver_ids:
        ids = [int(x.strip()) for x in approver_ids.split(",") if x.strip().isdigit()]
        if ids:
            res = await db.execute(
                select(SubsidyApprover)
                .where(SubsidyApprover.id.in_(ids))
                .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
            )
            selected_approvers = res.scalars().all()

    # Load initiator if requested (frontend always sends User.id, not SubsidyApprover.id).
    # Бизнес-правило: за другого человека делать СЗ может только тот, кому
    # подчинён этот человек (видим через _get_visible_user_ids — тот же scope,
    # что для постановки задач). Самого себя — всегда можно.
    initiator = None
    if initiator_id and initiator_id != getattr(current_user, "id", None):
        from app.routers.task_visibility import _get_visible_user_ids
        visible = await _get_visible_user_ids(current_user, db)
        if visible is not None and initiator_id not in visible:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INITIATOR_FORBIDDEN",
                    "message": (
                        "Указанный инициатор вам не подчинён. Сделать служебную "
                        "записку за другого человека может только его руководитель."
                    ),
                },
            )
    # Стратегия резолва:
    #   1) SubsidyApprover.user_id == initiator_id (привязанный approver субсидии) →
    #      берём full_name/role_name из карточки approver'а
    #   2) Иначе SimpleNamespace из User (full_name/position/department)
    if initiator_id:
        # 1. Привязанный approver субсидии (если есть)
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.user_id == initiator_id)
            .options(selectinload(SubsidyApprover.user))
            .order_by(SubsidyApprover.id)
            .limit(1)
        )
        initiator = res.scalar_one_or_none()
        # 2. Виртуальный approver из User
        if initiator is None:
            from app.models.user import User as UserModel
            from types import SimpleNamespace
            u = (
                await db.execute(select(UserModel).where(UserModel.id == initiator_id))
            ).scalar_one_or_none()
            if u:
                # Rule #6: не читаем u.position напрямую — единственный резолвер
                # должности (org-aware, с legacy fallback внутри) уже здесь.
                initiator = SimpleNamespace(
                    full_name=u.full_name or u.username,
                    role_name=await _resolve_user_position(
                        u, db, getattr(subsidy, "org_id", None) if subsidy else None
                    ),
                    user=u,
                )

        # Membership-check: инициатор должен состоять в организации, к которой
        # привязана субсидия закупки. Без этого должность/отдел не определены,
        # СЗ от имени постороннего сотрудника недопустима.
        subsidy_org_id = getattr(subsidy, "org_id", None) if subsidy else None
        init_user = initiator.user if (initiator and getattr(initiator, "user", None)) else None
        if subsidy_org_id and init_user:
            from app.models.user_organization import UserOrganization
            mem = (await db.execute(
                select(UserOrganization.id).where(
                    UserOrganization.user_id == init_user.id,
                    UserOrganization.org_id == subsidy_org_id,
                ).limit(1)
            )).first()
            # Legacy fallback — User.org_id (primary)
            if not mem and getattr(init_user, "org_id", None) != subsidy_org_id:
                org_name = getattr(customer_org, "name", "") if customer_org else ""
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "INITIATOR_NOT_IN_ORG",
                        "message": (
                            f"Инициатор не состоит в организации"
                            + (f" «{org_name}»" if org_name else "")
                            + ", к которой привязана субсидия закупки. Выберите "
                            "сотрудника этой организации."
                        ),
                    },
                )

    # If no approvers specified — load defaults for this subsidy
    if not selected_approvers and p.subsidy_id:
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.subsidy_id == p.subsidy_id, SubsidyApprover.is_default == True)
            .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
        )
        selected_approvers = res.scalars().all()

    # Владелец (2026-09-03): «у рамочного договора тоже должен быть лист
    # согласования» — с реальными согласующими. Диагноз: до этой правки лист
    # для рамочной ГОЛОВЫ печатал selected_approvers из SubsidyApprover (выше)
    # — конфигурацию ДЕНЕЖНОГО согласования субсидии, никак не связанную с
    # цепочкой согласования НЕОБХОДИМОСТИ договора (PurchaseApproval-строки,
    # которые строит purchases.py::_build_framework_chain_approvals или
    # добавляет вручную purchase_approvals.py::add_approver — у них
    # subsidy_approver_id всегда NULL, поэтому approval_map по нему их вообще
    # не находил). Печатаем именно эту, реальную цепочку — approver_ids
    # (пикер по субсидии) и default-согласующие субсидии для рамочной головы
    # смысла не имеют.
    _fh_approval_rows: list = []
    _fh_pa_by_synth_id: dict = {}
    if doc_type == "approval_sheet" and is_framework_head(p):
        from app.models.purchase_approval import PurchaseApproval as _FhPA
        from types import SimpleNamespace as _FhNS
        fh_res = await db.execute(
            select(_FhPA).where(_FhPA.purchase_id == pid).order_by(_FhPA.order_num)
        )
        _fh_approval_rows = fh_res.scalars().all()
        selected_approvers = [
            _FhNS(
                id=f"fh-{row.id}",
                full_name=row.approver_full_name,
                role_name=row.role_name,
                show_feo_path=False,
            )
            for row in _fh_approval_rows
        ]
        _fh_pa_by_synth_id = {f"fh-{row.id}": row for row in _fh_approval_rows}

    # Build FEO category path (root → ... → selected) + individual levels
    feo_path = ""
    feo_level_1 = ""
    feo_level_2 = ""
    feo_level_3 = ""
    item_feo_paths: list = []  # [(path_str, Decimal total)] по позициям со своей категорией ФЭО

    # Требование владельца (2026-08-30): «В "Путь ФЭО" должны прописываться
    # договорные категории, они должны совпадать с Плановыми». Лист
    # согласования и остальные CONTRACT_FAMILY_DOC_TYPES визируют ДОГОВОРНЫЕ
    # позиции (ContractItem) — цены там уже договорные, поэтому путь ФЭО
    # тоже обязан идти от договорных позиций, иначе строки «цена / категория»
    # расходятся. См. _build_contract_item_feo_paths().
    _is_contract_family = doc_type in CONTRACT_FAMILY_DOC_TYPES
    if _is_contract_family:
        _plan_feo_by_id = {it.id: it.feo_category_id for it in (p.items or []) if it.feo_category_id}
        item_feo_ids = list(dict.fromkeys(
            _plan_feo_by_id[ci.source_item_id]
            for ci in (p.contract_items or [])
            if ci.source_item_id and ci.source_item_id in _plan_feo_by_id
        ))
    else:
        item_feo_ids = list(dict.fromkeys(it.feo_category_id for it in (p.items or []) if it.feo_category_id))

    if p.feo_category_id or item_feo_ids or (_is_contract_family and (p.contract_items or [])):
        feo_res = await db.execute(select(FeoCategory))
        all_feo = {f.id: f for f in feo_res.scalars().all()}

        def _feo_path_nodes(node_id):
            path_nodes: list = []
            visited: set = set()
            while node_id and node_id not in visited:
                visited.add(node_id)
                cat = all_feo.get(node_id)
                if not cat:
                    break
                path_nodes.append(cat)
                node_id = cat.parent_id
            path_nodes.reverse()  # root → leaf
            return path_nodes

        if p.feo_category_id:
            path_nodes = _feo_path_nodes(p.feo_category_id)
            feo_path = " → ".join(n.name.strip() for n in path_nodes)
            if len(path_nodes) >= 1: feo_level_1 = path_nodes[0].name.strip()
            if len(path_nodes) >= 2: feo_level_2 = path_nodes[1].name.strip()
            if len(path_nodes) >= 3: feo_level_3 = path_nodes[2].name.strip()

        if _is_contract_family:
            item_feo_paths = _build_contract_item_feo_paths(
                p.contract_items or [], p.items or [], _feo_path_nodes,
            )
        elif item_feo_ids:
            cat_sums: dict = {cid: Decimal("0") for cid in item_feo_ids}
            for it in (p.items or []):
                if it.feo_category_id and it.total_price is not None:
                    cat_sums[it.feo_category_id] += Decimal(str(it.total_price))
            for cid in item_feo_ids:
                cat_path = " → ".join(n.name.strip() for n in _feo_path_nodes(cid))
                if cat_path:
                    item_feo_paths.append((cat_path, cat_sums[cid]))

    # Resolved responsible person: priority = ?responsible_name → assigned_user.full_name
    # → p.responsible_person → автор служебной записки (последний фолбэк, чтобы клетка
    # «Ответственный исполнитель» никогда не оставалась привязанной к фиксированному
    # человеку из настроек субсидии — см. app/services/responsible_role.py)
    assigned_full = (getattr(p.assigned_user, "full_name", None) or "") if getattr(p, "assigned_user", None) else ""
    service_note_author_full = (
        (getattr(p.service_note_author, "full_name", None) or "")
        if getattr(p, "service_note_author", None) else ""
    )
    raw_responsible = responsible_name or assigned_full or p.responsible_person or service_note_author_full or ""
    resolved_responsible = _format_initials(raw_responsible) if raw_responsible else ""
    resolved_responsible_full = raw_responsible  # для шаблонов которым нужно полное ФИО

    # Build docxtpl template object early (needed for InlineImage)
    try:
        from docxtpl import DocxTemplate, InlineImage
        from docx.shared import Cm as _Cm

        # Templates are normalized at upload time (subsidies.py
        # _normalize_docx_template). For files uploaded BEFORE that fix
        # landed we lazily rewrite them on first render: scan + replace +
        # atomic rename, so subsequent renders hit the fast path with no
        # extra IO and InlineImage placeholders sit in a single contiguous
        # run (required for the drawing element to be inserted).
        try:
            import zipfile as _zf
            needs_norm = False
            with _zf.ZipFile(template_path, 'r') as _zin:
                for _name in _zin.namelist():
                    if _name == 'word/document.xml' or _name.startswith('word/header') or _name.startswith('word/footer'):
                        _bytes = _zin.read(_name)
                        if b'<w:proofErr' in _bytes or b'<w:bookmark' in _bytes or b'<w:commentRange' in _bytes or b'<w:lastRenderedPageBreak' in _bytes:
                            needs_norm = True
                            break
            if needs_norm:
                from app.routers.subsidies import _normalize_docx_template as _norm
                _stats = _norm(template_path)
                logger.info("lazy normalize on render %s: %s", template_path, _stats)
        except Exception as _scan_e:
            logger.warning("lazy normalize scan failed for %s: %s", template_path, _scan_e)

        tpl = DocxTemplate(template_path)
    except HTTPException:
        raise
    except Exception as e:
        import traceback as _tb
        logger.exception("Document template load failed for purchase %s, doc_type=%s", pid, doc_type)
        raise HTTPException(500, detail={
            "code": "DOCUMENT_GENERATION_FAILED",
            "message": f"Не удалось загрузить шаблон «{doc_type}»: {type(e).__name__}",
            "doc_type": doc_type,
            "purchase_id": pid,
            "error_class": type(e).__name__,
            "error_raw": str(e),
            "traceback": "".join(_tb.format_exception(type(e), e, e.__traceback__))[:4000],
            "hint": (
                "Ошибка при загрузке файла шаблона docxtpl. "
                "Возможные причины: повреждённый .docx файл шаблона, "
                "отсутствие библиотеки docxtpl/python-docx. "
                "Передайте администратору error_class + traceback."
            ),
        })

    UPLOADS_DIR = "/app/uploads/products"

    def _resolve_photo(photo_url):
        """Return InlineImage or empty string."""
        import tempfile, urllib.request as _ur
        if not photo_url:
            return ""
        url = str(photo_url).strip()
        local_path = None

        if url.startswith("/api/products/photos/"):
            fname = url.split("/")[-1]
            local_path = f"{UPLOADS_DIR}/{fname}"
        elif url.isdigit():
            for ext in ("jpg", "jpeg", "png"):
                p = f"{UPLOADS_DIR}/product_{url}.{ext}"
                if os.path.exists(p):
                    local_path = p
                    break
        elif url.startswith("http://") or url.startswith("https://"):
            # Download external image; convert webp via Pillow if available
            try:
                with _ur.urlopen(url, timeout=5) as r:
                    ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    raw = r.read()
                is_webp = "webp" in ct or url.lower().endswith(".webp")
                if is_webp:
                    try:
                        from PIL import Image as _Img
                        import io as _io
                        img = _Img.open(_io.BytesIO(raw)).convert("RGB")
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        img.save(tmp, format="JPEG", quality=85)
                        tmp.close()
                        local_path = tmp.name
                    except Exception:
                        return ""  # Pillow not available or conversion failed
                else:
                    ext_map = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
                               "image/gif": ".gif", "image/bmp": ".bmp", "image/tiff": ".tiff"}
                    suffix = ext_map.get(ct, ".jpg")
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    tmp.write(raw)
                    tmp.close()
                    local_path = tmp.name
            except Exception:
                return ""

        if not local_path or not os.path.exists(local_path):
            return ""
        try:
            return InlineImage(tpl, local_path, width=_Cm(2.5))
        except Exception:
            return ""

    # Build template context
    # «Плановые не равно Договор»: для CONTRACT_FAMILY_DOC_TYPES позиции
    # берутся ТОЛЬКО из ContractItem (гейт _require_contract_items_for_doc
    # выше уже гарантировал, что contract_items не пуст). Для остальных —
    # старое поведение (purchase_items).
    if doc_type in CONTRACT_FAMILY_DOC_TYPES:
        items_list = _build_items_list_from_contract_items(p, resolve_photo=_resolve_photo)
    else:
        items_list = _build_items_list_from_purchase_items(
            p, tz_override_mode=tz_override_mode, resolve_photo=_resolve_photo,
        )

    # Phase 23.1: auto-detect subject_kind for universal contract.docx
    # 'services' if ALL items have item_kind='услуга', otherwise 'goods' (default)
    subject_kind = "goods"
    if items_list:
        kinds = {it.get("item_kind", "товар").lower() for it in items_list}
        if kinds == {"услуга"}:
            subject_kind = "services"

    # Load existing PurchaseApproval records (electronic signatures)
    from app.models.purchase_approval import PurchaseApproval
    pa_res = await db.execute(
        select(PurchaseApproval)
        .where(PurchaseApproval.purchase_id == pid, PurchaseApproval.status == "approved")
        .order_by(PurchaseApproval.order_num)
    )
    # Map subsidy_approver_id → PurchaseApproval (for signature lookup)
    approval_map: dict[int, PurchaseApproval] = {}
    for pa in pa_res.scalars().all():
        if pa.subsidy_approver_id:
            approval_map[pa.subsidy_approver_id] = pa

    def _base64_to_inline(tpl_obj, b64_data: str):
        """Convert base64 PNG data URL to docxtpl InlineImage."""
        import tempfile, base64, re as _re
        try:
            from docxtpl import InlineImage
            from docx.shared import Cm as _Cm
            m = _re.match(r"data:image/\w+;base64,(.+)", b64_data, _re.DOTALL)
            if not m:
                return ""
            raw = base64.b64decode(m.group(1))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(raw)
            tmp.close()
            return InlineImage(tpl_obj, tmp.name, width=_Cm(3.0))
        except Exception:
            return ""

    # Collect unique product categories from items
    item_categories = list(dict.fromkeys(
        item.product.category
        for item in (p.items or [])
        if item.product and item.product.category
    ))
    item_categories_str = ", ".join(item_categories)

    approvers_list = []
    for i, a in enumerate(selected_approvers):
        raw_full = a.full_name or ""
        # «Ответственный исполнитель» — роль-слот (app/services/responsible_role.py):
        # хранимое в subsidy_approvers ФИО для неё ИГНОРИРУЕТСЯ ВСЕГДА, даже если там
        # почему-то оказалось живое имя — источник истины только резолв по закупке.
        # Для остальных ролей подставляем резолв только если сохранённое ФИО пустое/плейсхолдер.
        if is_responsible_role(a.role_name) or is_blank_person_name(raw_full):
            raw_full = resolved_responsible_full or RESPONSIBLE_PLACEHOLDER
        if getattr(a, "show_feo_path", False) and item_feo_paths:
            note = "; ".join(f"{path} — {_fmt_money(total)} ₽" for path, total in item_feo_paths)
        elif getattr(a, "show_feo_path", False) and feo_path:
            item_type_label = {"товар": "Товары", "услуга": "Услуги"}.get(p.item_type or "", "")
            note = feo_path + (f" ({item_type_label})" if item_type_label else "")
        else:
            note = ""

        # Electronic signature — approval_map keyed by SubsidyApprover.id (денежное
        # согласование); _fh_pa_by_synth_id — своя карта для цепочки необходимости
        # рамочной головы (см. блок выше, у тех строк subsidy_approver_id всегда NULL).
        pa = approval_map.get(a.id) or _fh_pa_by_synth_id.get(a.id)
        signature_img = ""
        decided_date = ""
        if pa and pa.signature_data and pa.signature_algorithm == "visual":
            signature_img = _base64_to_inline(tpl, pa.signature_data)
            if pa.decided_at:
                decided_date = pa.decided_at.strftime("%d.%m.%Y")

        approvers_list.append({
            "num": i + 1,
            "role_name": a.role_name,
            # Владелец: «в листе согласования ФИО целиком, а фамилия должна быть
            # целиком, имя-отчество инициалами» — печатаем сокращённую форму,
            # полное ФИО остаётся под отдельным ключом для шаблонов, которым
            # оно реально нужно (напр. текст договора).
            "full_name": _format_initials_safe(raw_full),
            "full_name_full": raw_full,
            "signature_img": signature_img,
            "decided_date": decided_date,
            "note": note,
            # Phase 26-V: родительный падеж — ОБЯЗАТЕЛЬНО от полного ФИО:
            # _to_gen_fio определяет пол по окончанию отчества
            # (parts[2].endswith(('вна','чна'))), от сокращённого «А.О.»
            # род не определится и склонение сломается.
            "full_name_gen": _to_gen_fio(raw_full),
            "role_name_gen": _to_gen_phrase(a.role_name or ""),
        })

    c = p.contractor

    # ── Contract-specific context helpers ────────────────────────────────────
    def _contract_date_parts():
        d = p.contract_date
        if not d:
            return "", "", ""
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                return "", "", ""
        months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        return str(d.day).zfill(2), months_ru[d.month - 1], str(d.year)

    cd_day, cd_month, cd_year = _contract_date_parts()

    # Short name: extract parenthetical or use first word
    def _short_name(full_name: str) -> str:
        import re
        m = re.search(r'[«""]([^»""]+)[»""]', full_name)
        if m:
            return m.group(1)
        parts = full_name.split()
        return parts[-1] if parts else full_name

    # Сумма закупки для документов.
    # items_sum_val — сумма ПЛАНОВЫХ позиций, нужна только как последний
    # фолбэк для total_nmcd/total_nmck/nmck ниже (они остаются плановыми
    # полями всегда, независимо от doc_type — НМЦК по определению начальная
    # плановая цена).
    # doc_amount_val/amount_is_planned — сумма ДОКУМЕНТА: для
    # CONTRACT_FAMILY_DOC_TYPES («Плановые не равно Договор») — ТОЛЬКО
    # p.contract_price / сумма ContractItem, без отката на НМЦК/план. Для
    # остальных типов — старое поведение (план/НМЦК до заключения договора).
    items_sum_val = float(sum(Decimal(str(it.total_price or 0)) for it in (p.items or [])))
    doc_amount_val, amount_is_planned = _resolve_doc_amount(p, doc_type)

    # VAT calculations.
    # Ставка берётся ТОЛЬКО из того, что ввёл пользователь — никаких
    # придуманных значений по умолчанию (владелец, 2026-09-04: «нет НДС
    # 20 — сами ставим процент НДС, он у всех разный»). None означает
    # «не указана», 0 — валидная ставка НДС 0%; `or 20` раньше путал эти
    # два случая. Для doc_type, которые реально печатают ставку,
    # None+vat_applicable уже отбит выше в _require_vat_rate_for_doc —
    # сюда с таким сочетанием можно дойти только для остальных doc_type,
    # где vat_rate/vat_info_line в шаблоне не используются.
    vat_app = bool(p.vat_applicable)
    vat_rate_val = p.vat_rate
    price_val = doc_amount_val
    if vat_app and price_val and vat_rate_val is not None:
        vat_amount_val = price_val * vat_rate_val / (100 + vat_rate_val)
    else:
        vat_amount_val = 0.0

    # НДС info for approval sheet
    # Phase 26-TT: для авансового отчёта не придумывать «НДС не облагается» если
    # в чеке/items нет данных VAT — пишем только то, что реально есть.
    is_advance = (p.purchase_method == 'advance')
    items_with_vat = [it for it in (p.items or []) if getattr(it, 'vat_rate', None)]

    if vat_app:
        if vat_rate_val is not None:
            vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
        else:
            # doc_type, печатающие ставку, уже отбиты раньше в
            # _require_vat_rate_for_doc — сюда попадают только те, где
            # vat_info_line в шаблоне не используется; не выдумываем число.
            vat_info_line = "НДС (ставка не указана)"
    elif is_advance:
        # Авансовый: данные из чеков ФНС; если в чеке нет НДС — не пишем ничего лишнего.
        if items_with_vat:
            # Per-item VAT — показать сводку по факту
            unique_rates = sorted({str(it.vat_rate) for it in items_with_vat if it.vat_rate})
            vat_info_line = f"НДС по позициям: {', '.join(unique_rates)}"
        else:
            vat_info_line = ""  # пусто — не придумываем
    else:
        # Основание — введённое человеком ИЛИ определённое автоматически
        # (самозанятый контрагент / договор ГПХ с физлицом), см.
        # _resolve_vat_exemption_basis. Для doc_type из VAT_RATE_PRINTED_DOC_TYPES
        # пустое основание уже отбито раньше в _require_vat_rate_for_doc —
        # сюда с пустым основанием можно дойти только для остальных doc_type.
        art = _resolve_vat_exemption_basis(p)
        vat_info_line = f"НДС не облагается" + (f" ({art})" if art else "")

    context = {
        # Закупка
        "purchase_number": p.purchase_number or "",
        "registry_number": p.registry_number or "",
        "purchase_method": _PURCHASE_METHOD_LABELS.get(p.purchase_method or "", p.purchase_method or ""),
        # order_purchase (приказ на закупку), п.2: способ закупки прописью.
        # Неизвестный код способа закупки — подставляем сам код, не пустую строку.
        # Конкурентная процедура с заполненной формой (competitive_form) —
        # подпись конкретной формы («Запрос цен» / «Аукцион (редукцион)» /
        # «Конкурс»), не общее «Конкурсная процедура» (см. _purchase_method_label).
        "purchase_method_label": _purchase_method_label(p),
        "subject": p.subject or "",
        "status": p.status or "",
        "purchase_basis": _BASIS_LABELS.get(p.purchase_basis or "", ""),
        "responsible_person": resolved_responsible,  # инициалы (по умолчанию)
        "responsible_person_full": resolved_responsible_full,  # полное ФИО (для шаблонов где надо)
        # Субсидия
        "subsidy_name": subsidy.name if subsidy else "",
        "subsidy_year": subsidy.year if subsidy else "",
        "subsidy_budget": _fmt_money(subsidy.budget) if subsidy else "",
        # Контрагент — основные
        "contractor_name": (c.name or "") if c else "",
        "contractor_inn": _clean_id(c.inn) if c else "",
        "contractor_kpp": _clean_id(c.kpp) if c else "",
        "contractor_address": (c.address or "") if c else "",
        "contractor_postal_address": (c.postal_address or "") if c else "",
        "contractor_ogrn": (c.ogrn or "") if c else "",
        "contractor_phone": (c.phone or "") if c else "",
        "contractor_email": (c.email or "") if c else "",
        # Контрагент — подписант
        "contractor_signatory": (c.signatory or "") if c else "",
        "contractor_signatory_basis": (c.signatory_basis or "") if c else "",
        # Контрагент — банк
        "contractor_settlement_account": (c.settlement_account or "") if c else "",
        "contractor_bank_name": (c.bank_name or "") if c else "",
        "contractor_bik": (c.bik or "") if c else "",
        "contractor_correspondent_account": (c.correspondent_account or "") if c else "",
        # Комбинированные поля контрагента для шаблонов
        "contractor_bank_details": (c.bank_name or "") if c else "",
        "contractor_signatory_line": (
            f"{c.signatory}, действует на основании {c.signatory_basis}"
            if c and c.signatory and c.signatory_basis
            else ((c.signatory or "") if c else "")
        ),
        # FEO
        "feo_category_name": p.feo_category.name if p.feo_category else "",
        "feo_path":    feo_path,
        "feo_level_1": feo_level_1,
        "feo_level_2": feo_level_2,
        "feo_level_3": feo_level_3,
        # Финансы
        # Phase 19: total_nmcd is the new canonical name (НМЦД — начальная
        # максимальная цена договора). total_nmck is kept as a deprecated
        # alias so existing templates keep rendering. Use total_nmcd in new
        # templates.
        # Phase: суммы в шапке документов не должны зависеть от стадии закупки —
        # фолбэк на doc_amount_val/items_sum_val, см. расчёт выше (перед НДС).
        "total_nmcd": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price or items_sum_val),
        "total_nmck": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price or items_sum_val),
        "nmck": _fmt_money(p.nmck or p.total_nmck or items_sum_val),
        "contract_price": _fmt_money(p.contract_price or doc_amount_val),
        "economy": _fmt_money(p.economy),
        "price_increase": _fmt_money(p.price_increase),
        # Договор
        "contract_number": p.contract_number or "",
        "contract_date": _fmt_date(p.contract_date) or "__.__._____ г.",
        "execution_term": _fmt_date(p.execution_term),
        "execution_term_changed": _fmt_date(p.execution_term_changed),
        "delivery_date": _fmt_date(p.delivery_date),
        "country_origin": p.country_origin or "",
        # Акт приёмки. Phase 26-lll: УБРАН fallback acceptance_doc_* → contract_*.
        # Phase 27.2-01: для СЗ на оплату/аванс читаем acceptance_docs JSONB
        # (source of truth после Phase 26-H). Legacy plain-поля — только fallback.
        **_build_acceptance_doc_context(p, doc_type, doc_indices),
        # Платёж
        "payment_doc_number": p.payment_doc_number or "",
        "payment_doc_date": _fmt_date(p.payment_doc_date),
        "payment_amount": _fmt_money(p.payment_amount),
        "payment_federal": _fmt_money(p.payment_federal),
        # Позиции
        "items": items_list,
        "items_count": len(items_list),
        "item_names": p.subject or ", ".join(i["name"] for i in items_list if i["name"]),
        "item_categories": item_categories_str,
        # Согласующие
        "approvers": approvers_list,
        # Инициатор: ФИО берётся как есть; должность и отдел резолвятся per-org
        # — по организации, к которой привязана субсидия закупки. Если у юзера
        # несколько отделов в этой org — первый.
        "initiator_name": initiator.full_name if initiator else "",
        "initiator_role": (
            await _resolve_user_position(
                initiator.user if (initiator and getattr(initiator, "user", None)) else None,
                db,
                getattr(subsidy, "org_id", None) if subsidy else None,
            )
            or (initiator.role_name if initiator else "")
        ),
        "initiator_dept": await _resolve_user_dept(
            initiator.user if (initiator and getattr(initiator, "user", None)) else None,
            db,
            getattr(subsidy, "org_id", None) if subsidy else None,
        ),
        # Мероприятие
        "event_name": event.name if event else "",
        # Тип договора
        "contract_type": {"single": "Единственный поставщик", "framework_cumulative": "Рамочный (накопительный)", "framework_with_amount": "Рамочный (с суммой)"}.get(p.purchase_contract_type or "", p.purchase_contract_type or ""),
        # Служебные
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
        # ── Расширенные поля для договорных шаблонов ─────────────────────────
        # Дата по частям
        "contract_date_day":   cd_day,
        "contract_date_month": cd_month,
        "contract_date_year":  cd_year,
        # Тип контрагента
        "contractor_org_type": (c.org_type or "") if c else "",
        # Phase 27.2-08: краткое название = поле "Краткое наименование *" из карточки контрагента
        # напрямую (Contractor.name), без вытаскивания из кавычек.
        "contractor_short_name": (c.name or "") if c else "",
        "contractor_signatory_position": _signatory_position(c.signatory) if c else "",
        # Предмет (сервисное имя)
        "service_name": p.subject or "",
        "service_name_gen": _inflect_phrase_genitive(p.subject or ""),
        # Срок оказания услуг
        # Phase 19: service_start_date / service_end_date now prefer the real
        # Purchase columns (used by 'range' mode). If those are empty we fall
        # back to the legacy mapping (contract_date / execution_term).
        "period_type": p.service_period_type or "period",
        "service_start_date": _fmt_date(p.service_start_date) or _fmt_date(p.contract_date),
        "service_end_date":   _fmt_date(p.service_end_date)   or _fmt_date(p.execution_term),
        "service_date":       _fmt_date(p.execution_term),
        # Phase 19: extended service-term context
        "service_term":            _format_service_term(p),
        "service_term_mode":       p.service_term_mode or "",
        "service_term_days":       p.service_term_days or "",
        "service_term_type":       p.service_term_type or "",
        "service_term_type_name":  {"calendar": "календарных", "working": "рабочих"}.get(p.service_term_type or "", ""),
        "service_deadline_date":   _fmt_date(p.service_deadline_date),
        # Дата окончания срока действия договора (п. 8.1) — поле Purchase.contract_end_date
        "contract_end_date":       _fmt_date(p.contract_end_date),
        # Phase 19: submission deadline (дата+время завершения приёма заявок)
        "submission_deadline_date":     p.submission_deadline.date().isoformat() if p.submission_deadline else "",
        "submission_deadline_time":     p.submission_deadline.strftime("%H:%M") if p.submission_deadline else "",
        "submission_deadline_datetime": p.submission_deadline.strftime("%d.%m.%Y %H:%M") if p.submission_deadline else "",
        # Phase 19: delivery location
        "delivery_location": p.delivery_location or "",
        # Phase 19: agreement text from subsidy
        "subsidy_agreement_text": (subsidy.agreement_text if (subsidy and subsidy.agreement_text) else ""),
        # Третьи лица
        "third_party_involved": bool(p.third_party_involved),
        # НДС
        "vat_applicable":        vat_app,
        "vat_rate":              vat_rate_val,
        "vat_amount_num":        _fmt_money_plain(vat_amount_val),
        "vat_amount_words":      _rubles_to_words(vat_amount_val),
        "vat_exemption_article": ("" if vat_app else art),
        "vat_info_line":         vat_info_line,
        # Цена прописью (фолбэк на doc_amount_val, если договор ещё не заключён)
        "contract_price_num":   _fmt_money_plain(p.contract_price or doc_amount_val),
        "contract_price_words": _rubles_to_words(p.contract_price or doc_amount_val),
        # Phase: сумма закупки для документов, не зависящая от стадии (план/договор).
        "doc_amount":         _fmt_money(doc_amount_val),
        "doc_amount_num":     _fmt_money_plain(doc_amount_val),
        "doc_amount_words":   _rubles_to_words(doc_amount_val),
        "amount_is_planned":  amount_is_planned,
        "amount_source_label": "НМЦК (план)" if amount_is_planned else "Цена договора",
        # Phase 23: service_subject alias (same as subject but clearer name in services template)
        "service_subject": p.subject or "",
        # Phase 23.1: subject_kind for universal contract.docx auto-switch
        "subject_kind": subject_kind,
    }

    # Phase 28: расширенные ключи для типовых договоров ─────────────────────────
    # Все ключи NULL-safe (пустая строка / ноль / пустой список при отсутствии данных).
    try:
        # Реквизиты субсидии-грантодателя (для рамочных и региональных договоров)
        # Phase 28: grantor_name / ministry_name берём из новых полей модели Subsidy
        context["subsidy_grantor_name"] = (subsidy.grantor_name or "").strip() if subsidy else ""
        context["subsidy_ministry_name"] = (subsidy.ministry_name or "").strip() if subsidy else ""
        # agreement_date: новое поле отсутствует в модели — используем basis_doc_date
        _subsidy_agreement_date_obj = (
            subsidy.basis_doc_date if subsidy and subsidy.basis_doc_date else None
        )
        context["subsidy_agreement_date"] = _fmt_date(_subsidy_agreement_date_obj) if _subsidy_agreement_date_obj else ""

        # Реквизиты физ.лица (ГПХ) — читаем из контрагента
        context["contractor_passport_series"]       = (c.passport_series or '') if c else ''
        context["contractor_passport_number"]       = (c.passport_number or '') if c else ''
        context["contractor_passport_issuer"]       = (c.passport_issuer or '') if c else ''
        context["contractor_passport_issued_date"]  = _fmt_date(c.passport_issued_date) if c and c.passport_issued_date else ''
        context["contractor_snils"]                 = (c.snils or '') if c else ''
        context["contractor_registration_address"]  = (c.registration_address or c.address or c.postal_address or '') if c else ''
        context["contractor_birth_date"]            = _fmt_date(c.birth_date) if c and c.birth_date else ''

        # Комиссия закупки (для протокола) — из полей закупки Phase 28
        context["commission_member_1_name"] = (p.commission_member_1_name or "").strip()
        context["commission_member_2_name"] = (p.commission_member_2_name or "").strip()
        context["commission_member_3_name"] = (p.commission_member_3_name or "").strip()
        _commission_members = [
            {"name": p.commission_member_1_name, "role": "Член комиссии"} if p.commission_member_1_name else None,
            {"name": p.commission_member_2_name, "role": "Член комиссии"} if p.commission_member_2_name else None,
            {"name": p.commission_member_3_name, "role": "Член комиссии"} if p.commission_member_3_name else None,
        ]
        context["commission_members"] = [x for x in _commission_members if x]

        # Прочие условия договора — из полей закупки Phase 28
        context["advance_amount"]              = _fmt_money(p.advance_amount) if p.advance_amount else ""
        context["acceptance_term_days"]        = p.acceptance_term_days if p.acceptance_term_days is not None else 5
        context["penalty_rate"]                = str(p.penalty_rate) if p.penalty_rate is not None else "0.1"
        context["procurement_protocol_number"] = (p.procurement_protocol_number or "").strip()
        context["procurement_order_number"]    = (p.procurement_order_number or "").strip()
        context["repair_request_number"]       = (p.repair_request_number or "").strip()
        context["contractor_ogrnip_date"]      = _fmt_date(p.contractor_ogrnip_date) if p.contractor_ogrnip_date else ""
        # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
        context["warranty_period_days"]        = p.warranty_period_days if p.warranty_period_days is not None else 15
        context["is_retroactive"]              = bool(p.is_retroactive)
        # delivery_by_supplier=True — поставщик доставляет; False — самовывоз.
        # has_stages=True — в Приложении №1 есть этапы оказания услуг.
        context["delivery_by_supplier"] = bool(getattr(p, "delivery_by_supplier", True))
        context["has_stages"]           = bool(getattr(p, "has_stages", False))
        # Phase 28: subsidy-specific clauses (пункты из субсидии — раздельный учёт и т.п.)
        context["subsidy_extra_clause_1"]      = (subsidy.extra_contract_clause_1 or '').strip() if subsidy else ''
        context["subsidy_extra_clause_2"]      = (subsidy.extra_contract_clause_2 or '').strip() if subsidy else ''
    except Exception as _e28:
        import logging as _log28
        _log28.getLogger(__name__).warning("Phase 28 context keys failed: %s", _e28)

    # Phase 26-V: родительный падеж для инициатора и ответственного
    context["initiator_name_gen"] = _to_gen_fio(context.get("initiator_name", ""))
    context["initiator_position_gen"] = _to_gen_phrase(context.get("initiator_role", ""))
    context["responsible_name_gen"] = _to_gen_fio(resolved_responsible)
    context["responsible_position_gen"] = _to_gen_phrase(p.responsible_position or "" if hasattr(p, "responsible_position") else "")

    # Phase 27.2-10: дедуп тавтологии "отдел Отдела ..." + gent для отдела
    # Если в должности уже есть корень "отдел*" — убираем leading "Отдел*" из имени отдела.
    # Пример: «Заместитель начальника отдела» + «Отдела МТО» → «МТО».
    import re as _re_dept
    def _strip_redundant_dept_word(position: str, dept: str) -> str:
        if not dept or not position:
            return dept or ""
        if not _re_dept.search(r'\bотдел\w*', position.lower()):
            return dept
        return _re_dept.sub(r'^отдел\w*\s+', '', dept, count=1, flags=_re_dept.IGNORECASE)

    _init_pos = context.get("initiator_role", "") or ""
    _init_dept_raw = context.get("initiator_dept", "") or ""
    _init_dept_clean = _strip_redundant_dept_word(_init_pos, _init_dept_raw)
    context["initiator_dept"] = _init_dept_clean
    context["initiator_dept_gen"] = _inflect_phrase_genitive(_init_dept_clean)

    # ── Phase 23: Заказчик (Customer = Organization владелец субсидии + linked Contractor) ──
    # Правило №6: реквизиты (full_name/inn/kpp/ogrn/address/подписант) — ОДИН
    # источник через org_requisites() (Contractor, если org.contractor_id задан
    # и контрагент найден; иначе deprecated-колонки Organization на переходный
    # период). Раньше здесь был свой inline-коалесинг "org, иначе ctr" — при
    # правке контрагента отдельно от org это расходилось с тем, что видно в
    # карточке организации (баг волны Правило №6, 2026-09).
    from app.services.org_requisites import org_requisites
    _cust_req = org_requisites(customer_org, customer_ctr) if customer_org else {}

    def _g(*sources, default=""):
        """Coalesce — return first non-empty value."""
        for s in sources:
            if s:
                return s
        return default

    cust_signatory_full = _cust_req.get('signatory') or ""
    _cust_last = _cust_req.get('signatory_last_name') or None
    _cust_first = _cust_req.get('signatory_first_name') or None
    _cust_middle = _cust_req.get('signatory_middle_name') or None
    _cust_position = _cust_req.get('signatory_position') or None
    cust_sig = _signatory_split(
        cust_signatory_full,
        last=_cust_last, first=_cust_first, middle=_cust_middle, position=_cust_position,
    )
    cust_signatory_basis = _g(
        customer_ctr.signatory_basis if customer_ctr else None,
        "Устава",
    )

    context.update({
        "customer_name":         _g(customer_org.name if customer_org else None,
                                    customer_ctr.name if customer_ctr else None),
        "customer_full_name":    _g(_cust_req.get('full_name'),
                                    customer_ctr.name if customer_ctr else None,
                                    customer_org.name if customer_org else None),
        # Phase 27.2-08: краткое название Заказчика = поле "Краткое наименование" из карточки
        # организации/контрагента напрямую, без вытаскивания из кавычек.
        "customer_short_name":   _g(customer_org.name if customer_org else None,
                                    customer_ctr.name if customer_ctr else None),
        "customer_address":      _g(_cust_req.get('address')),
        "customer_postal_address": _g(customer_ctr.postal_address if customer_ctr else None,
                                      _cust_req.get('address')),
        "customer_inn":          _clean_id(_g(_cust_req.get('inn'))),
        "customer_kpp":          _clean_id(_g(_cust_req.get('kpp'))),
        "customer_ogrn":         _g(_cust_req.get('ogrn')),
        "customer_bank_name":    _g(customer_ctr.bank_name if customer_ctr else None),
        "customer_settlement_account":    _g(customer_ctr.settlement_account if customer_ctr else None),
        "customer_correspondent_account": _g(customer_ctr.correspondent_account if customer_ctr else None),
        "customer_bik":          _g(customer_ctr.bik if customer_ctr else None),
        # Лицевой счёт Заказчика
        "customer_personal_account": _g(customer_ctr.personal_account if customer_ctr else None),
        "customer_phone":        _g(customer_ctr.phone if customer_ctr else None),
        "customer_email":        _g(customer_ctr.email if customer_ctr else None),
        # Подписант Заказчика
        "customer_signatory":                cust_signatory_full,
        "customer_signatory_position":       cust_sig["position"],
        "customer_signatory_name":           cust_sig["name_full"],
        "customer_signatory_name_genitive":  cust_sig["name_genitive"],
        "customer_signatory_initials":       cust_sig["name_initials"],
        # Инициалы впереди: «Е.В. Козеев» (для строки подписи _________________ / И.О. Фамилия)
        "customer_signatory_name_initials":  _fio_to_initials_prefix(cust_sig["name_full"]),
        "customer_signatory_basis":          cust_signatory_basis,
        # Город заключения — из поля Organization.contract_city; fallback «Москва»
        "contract_city": (customer_org.contract_city or "Москва") if customer_org else "Москва",
    })

    # Fabrikant context keys ────────────────────────────────────────────────────
    # notice_number — номер процедуры на ЭТП (platform_number), а не наш internal
    # requestId (external_id); откат на external_id, если platform_number ещё
    # не проставлен площадкой на момент рендера
    _notice_number = ""
    try:
        from app.models.platform_publication import PlatformPublication as _PlatPub
        _pub_q = await db.execute(
            select(_PlatPub.platform_number, _PlatPub.external_id)
            .where(
                _PlatPub.purchase_id == p.id,
                _PlatPub.platform == "fabrikant",
            )
            .order_by(_PlatPub.id.desc())
            .limit(1)
        )
        _pub_row = _pub_q.first()
        if _pub_row:
            _notice_number = _pub_row[0] or _pub_row[1] or ""
    except Exception:
        pass
    context["notice_number"] = _notice_number

    # subsidy_agreement_number — из Subsidy.agreement_number
    context["subsidy_agreement_number"] = (subsidy.agreement_number or "") if subsidy else ""

    # payment_term_days — из Purchase.payment_term_days; fallback 10
    context["payment_term_days"] = p.payment_term_days if (p.payment_term_days is not None) else 10

    # applications_review_date — из Purchase.applications_review_date;
    # fallback: submission_deadline + 1 рабочий день (пн-пт, без учёта праздников)
    if p.applications_review_date:
        context["applications_review_date"] = _fmt_date(p.applications_review_date)
    elif p.submission_deadline:
        from datetime import timedelta as _td
        _next = p.submission_deadline.date() + _td(days=1)
        while _next.weekday() >= 5:  # 5=сб, 6=вс
            _next += _td(days=1)
        context["applications_review_date"] = _next.strftime("%d.%m.%Y")
    else:
        context["applications_review_date"] = ""

    # Phase 23: расширенные поля подписанта Исполнителя (name_genitive, initials, ogrnip)
    ctr_sig = _signatory_split(
        c.signatory if c else "",
        last=getattr(c, 'signatory_last_name', None) if c else None,
        first=getattr(c, 'signatory_first_name', None) if c else None,
        middle=getattr(c, 'signatory_middle_name', None) if c else None,
        position=getattr(c, 'signatory_position', None) if c else None,
    )
    context.update({
        "contractor_signatory_name":          ctr_sig["name_full"],
        "contractor_signatory_name_genitive": ctr_sig["name_genitive"],
        "contractor_signatory_initials":      ctr_sig["name_initials"],
        "contractor_ogrnip":                  (c.ogrn or "") if (c and (c.org_type or "").lower().startswith("ип")) else "",
        # contractor_full_name — полное официальное название (fallback на name)
        "contractor_full_name":               (c.full_name or c.name or "") if c else "",
    })

    # Phase 27.1 CD-5: contract_items loop context (+ D-08 fallback on purchase_items)
    # Phase 26-U: wrap pre-render context building — any exception → structured DOCUMENT_GENERATION_FAILED
    receipt_png_paths: list[str] = []  # Phase 26-ggg: scope outside try для post-render таблицы
    try:
        ci_ctx = await _build_contract_items_context(p, db)
        context.update(ci_ctx)

        # Phase 26-R: receipts images for advance reports' service note
        if p.purchase_method == "advance":
            import tempfile as _tempfile
            from app.models.purchase_receipt import PurchaseReceipt as _PurchaseReceipt
            from app.routers.purchase_receipts import _render_receipt_png as _rrpng
            _receipts_q = await db.execute(
                select(_PurchaseReceipt)
                .where(_PurchaseReceipt.purchase_id == p.id)
                .order_by(_PurchaseReceipt.id.asc())
            )
            _receipts = _receipts_q.scalars().all()
            # Phase 26-fff: одно превью PNG используется для нескольких InlineImage
            # с разной шириной — для разных layouts в шаблоне.
            #   default (6.5cm) → одиночная колонка/полный текст СЗ
            #   small (4.5cm)   → 2-колоночная таблица с узкими ячейками
            #   full  (14cm)    → отдельная страница на чек
            receipt_images = []        # default 6.5 cm — backward compat
            receipt_images_small = []  # 4.5 cm — для 2-col layouts
            receipt_images_full = []   # 14 cm — для full-width layouts
            receipt_png_paths = []     # Phase 26-ggg: пути PNG для post-render таблицы
            for _r in _receipts:
                try:
                    _png_bytes = _rrpng(_r)
                    _tmp = _tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    _tmp.write(_png_bytes)
                    _tmp.close()
                    receipt_png_paths.append(_tmp.name)
                    receipt_images.append(InlineImage(tpl, _tmp.name, width=_Cm(6.5)))
                    receipt_images_small.append(InlineImage(tpl, _tmp.name, width=_Cm(4.5)))
                    receipt_images_full.append(InlineImage(tpl, _tmp.name, width=_Cm(14)))
                except Exception as _re:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(f"render receipt {_r.id} skipped: {_re}")
            context["receipts"] = receipt_images
            context["receipt_images"] = receipt_images  # alias
            context["receipts_small"] = receipt_images_small
            context["receipts_full"] = receipt_images_full
            # Phase 26-ggg: sentinel-маркер. Пользователь ставит {{ receipts_table }}
            # в шаблон одним параграфом — после render текст становится
            # RECEIPTS_TABLE_MARKER, post-process находит и заменяет на
            # настоящую docx-таблицу 2-col с PNG чеков в каждой ячейке.
            # Решает проблему clip'а inline-images в узких ячейках/параграфах.
            context["receipts_table"] = RECEIPTS_TABLE_MARKER
            # Phase 26-LL: chunked в пары для таблицы 2 колонки в шаблоне СЗ
            receipt_pairs = []
            for _i in range(0, len(receipt_images_small), 2):
                _left = receipt_images_small[_i]
                _right = receipt_images_small[_i + 1] if _i + 1 < len(receipt_images_small) else None
                receipt_pairs.append({'left': _left, 'right': _right})
            context["receipt_pairs"] = receipt_pairs
            # Phase 26-RR: split на 2 потока для статичной таблицы 1×2 в шаблоне.
            # left/right берут МАЛЫЕ изображения (4.5 cm) — таблица 2-колоночная,
            # узкие ячейки. Старый шаблон с _Cm(6.5) клипал картинку и пользователь
            # видел пустую узкую полоску.
            context["left_receipts"] = receipt_images_small[::2]
            context["right_receipts"] = receipt_images_small[1::2]
        else:
            context["receipts"] = []
            context["receipt_images"] = []
            context["receipts_small"] = []
            context["receipts_full"] = []
            context["receipt_pairs"] = []
            context["left_receipts"] = []
            context["right_receipts"] = []
            context["receipts_table"] = ""  # marker отсутствует — paragraph будет пустой
            receipt_png_paths = []
    except HTTPException:
        raise
    except Exception as _ctx_exc:
        import traceback as _tb
        logger.exception("Document context build failed (pre-render) for purchase %s, doc_type=%s", pid, doc_type)
        _err_class = type(_ctx_exc).__name__
        _err_msg = str(_ctx_exc)
        _err_tb = "".join(_tb.format_exception(type(_ctx_exc), _ctx_exc, _ctx_exc.__traceback__))[:4000]
        raise HTTPException(500, detail={
            "code": "DOCUMENT_GENERATION_FAILED",
            "message": f"Не удалось сформировать данные для «{doc_type}»: {_err_class}",
            "doc_type": doc_type,
            "purchase_id": pid,
            "error_class": _err_class,
            "error_raw": _err_msg,
            "traceback": _err_tb,
            "hint": (
                "Ошибка при сборке контекста шаблона (до рендеринга). "
                "Возможные причины: ошибка загрузки чеков/изображений, "
                "проблема с данными закупки (FK, пустые обязательные поля), "
                "отсутствующая зависимость (PIL, qrcode). "
                "Передайте администратору error_class + traceback."
            ),
        })

    _fallback_info: dict | None = None  # phase31-02: track silent fallback for response header
    try:
        tpl.render(context)
    except Exception as render_err:
        # phase26-nn: auto-fallback на базовый шаблон если кастомный из БД сломан.
        # Lessons.md (2026-05-15): кастомные шаблоны с {% tr %} вне таблицы или
        # повреждённой структурой валят TemplateSyntaxError → user видит белый экран.
        # Безопаснее упасть на базовый из репо и предупредить.
        is_custom_template = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))
        if is_custom_template:
            base_path = os.path.join(TEMPLATES_DIR, f"{doc_type}.docx")
            if os.path.exists(base_path) and base_path != template_path:
                import logging
                _fallback_reason = f"{type(render_err).__name__}: {str(render_err)[:300]}"
                logging.getLogger(__name__).warning(
                    f"Custom template {template_path} render failed ({_fallback_reason}). "
                    f"Falling back to base template {base_path}."
                )
                _fallback_info = {
                    "original": os.path.basename(template_path),
                    "fallback": os.path.basename(base_path),
                    "reason": _fallback_reason,
                }
                tpl = DocxTemplate(base_path)
                template_path = base_path
                tpl.render(context)
            else:
                raise
        else:
            raise

    try:
        # Post-process: fix approvers table if docxtpl loop didn't render all rows
        if doc_type == "approval_sheet" and len(approvers_list) > 0:
            from docx import Document as _DocxDoc
            from docx.shared import Pt
            from copy import deepcopy
            from lxml import etree

            _buf = BytesIO()
            tpl.save(_buf)
            _buf.seek(0)
            _doc = _DocxDoc(_buf)

            # Find the approvers table (has header row with "Должность" or "ФИО")
            target_table = None
            for _t in _doc.tables:
                hdr = " ".join(c.text.strip() for c in _t.rows[0].cells)
                if "Должность" in hdr or "ФИО" in hdr:
                    target_table = _t
                    break

            if target_table:
                # Count current data rows (skip header)
                current_data_rows = len(target_table.rows) - 1
                needed = len(approvers_list)

                ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

                def _set_cell_text(cell_el, text):
                    """Replace all cell content with plain text."""
                    for p_el in list(cell_el.findall(f'{ns}p')):
                        cell_el.remove(p_el)
                    p = etree.SubElement(cell_el, f'{ns}p')
                    r = etree.SubElement(p, f'{ns}r')
                    t = etree.SubElement(r, f'{ns}t')
                    t.text = text or ""

                def _set_cell_two_lines(cell_el, line1, line2):
                    """Replace cell content with two paragraphs."""
                    for p_el in list(cell_el.findall(f'{ns}p')):
                        cell_el.remove(p_el)
                    p1 = etree.SubElement(cell_el, f'{ns}p')
                    r1 = etree.SubElement(p1, f'{ns}r')
                    t1 = etree.SubElement(r1, f'{ns}t')
                    t1.text = line1 or ""
                    p2 = etree.SubElement(cell_el, f'{ns}p')
                    r2 = etree.SubElement(p2, f'{ns}r')
                    t2 = etree.SubElement(r2, f'{ns}t')
                    t2.text = line2 or ""

                if current_data_rows < needed:
                    # Rebuild table: template loop didn't render all rows
                    template_row_el = target_table.rows[1]._tr
                    for row in list(target_table.rows[1:]):
                        target_table._tbl.remove(row._tr)
                    for a in approvers_list:
                        new_tr = deepcopy(template_row_el)
                        cells = new_tr.findall(f'.//{ns}tc')
                        if len(cells) >= 4:
                            _set_cell_text(cells[0], str(a.get("num", "")))
                            _set_cell_two_lines(cells[1], a.get("role_name", ""), a.get("full_name", ""))
                            _set_cell_text(cells[2], "")
                            _set_cell_text(cells[3], a.get("note", ""))
                        target_table._tbl.append(new_tr)
                else:
                    # Rows match — patch note/FEO into last column of each data row
                    for idx, a in enumerate(approvers_list):
                        row_idx = idx + 1  # skip header
                        if row_idx >= len(target_table.rows):
                            break
                        row_el = target_table.rows[row_idx]._tr
                        cells = row_el.findall(f'.//{ns}tc')
                        note_val = a.get("note", "")
                        if note_val and len(cells) >= 4:
                            _set_cell_text(cells[-1], note_val)

                # Phase 26-ggg: receipts table (no-op если маркер отсутствует)
                _insert_receipts_table_if_marker(_doc, receipt_png_paths)
                buf = BytesIO()
                _doc.save(buf)
                buf.seek(0)
            else:
                _insert_receipts_table_if_marker(tpl.docx, receipt_png_paths)
                buf = BytesIO()
                tpl.save(buf)
                buf.seek(0)
        else:
            _insert_receipts_table_if_marker(tpl.docx, receipt_png_paths)
            buf = BytesIO()
            tpl.save(buf)
            buf.seek(0)
    except Exception as e:
        logger.exception("Document generation error for purchase %s, doc_type=%s, template=%s", pid, doc_type, template_path)

        # Phase 23.2: human-friendly error explanations for Jinja/docxtpl errors
        import re as _re
        err_class = type(e).__name__
        err_msg = str(e)
        template_name = os.path.basename(template_path) if template_path else f"{doc_type}.docx"
        is_custom = bool(template_path and template_path.startswith(SUBSIDY_TEMPLATES_DIR))

        detail = {
            "code": "TEMPLATE_RENDER_ERROR",
            "message": f"Не удалось сгенерировать «{template_name}»",
            "template": template_name,
            "template_source": "Шаблон субсидии (загруженный пользователем)" if is_custom else "Глобальный шаблон",
            "error_class": err_class,
            "error_raw": err_msg,
            "hint": None,
        }

        # Pattern: Jinja2 UndefinedError ('X' is undefined)
        m = _re.match(r"'([a-zA-Z_][a-zA-Z0-9_]*)' is undefined", err_msg)
        if m:
            var_name = m.group(1)
            detail["message"] = f"В шаблоне «{template_name}» используется переменная {{{{{var_name}.…}}}} вне цикла"
            loop_hints = {
                "a": "{% tr for a in approvers %}…{{a.full_name}}…{% tr endfor %}  — переменная для согласующих (approval_sheet, лист согласования)",
                "item": "{% tr for item in items %}…{{item.name}}…{% tr endfor %}  — переменная для позиций закупки",
            }
            if var_name in loop_hints:
                detail["hint"] = (
                    f"Переменная «{var_name}» доступна только внутри цикла. "
                    f"Оберните строки/ячейки таблицы в:\n  {loop_hints[var_name]}\n\n"
                    f"Либо удалите кастомный шаблон в UI «Субсидии → Шаблоны → {template_name} → 🗑» и используйте глобальный."
                )
            else:
                detail["hint"] = (
                    f"В словаре переменных нет «{var_name}». Возможно, переменная переименована или удалена. "
                    f"См. справочник «Руководство по переменным» в Subsidies → Шаблоны."
                )

        # Pattern: 'X' has no attribute 'Y'
        m2 = _re.match(r"'(\w+)' (?:object )?has no attribute '(\w+)'", err_msg)
        if not m and m2:
            obj_name = m2.group(1)
            attr = m2.group(2)
            detail["message"] = f"В шаблоне «{template_name}» используется {{{{{obj_name}.{attr}}}}} но поле «{attr}» отсутствует"
            detail["hint"] = (
                f"Возможные причины:\n"
                f"• опечатка в имени переменной — см. «Руководство по переменным»\n"
                f"• данные ещё не заполнены в закупке (например, попытка использовать {{{{{obj_name}.{attr}}}}} когда поле пустое)"
            )

        # Pattern: TemplateSyntaxError
        if err_class == "TemplateSyntaxError":
            detail["message"] = f"Синтаксическая ошибка в шаблоне «{template_name}»: {err_msg}"
            detail["hint"] = (
                "Проверьте парные теги в Word: `{% if ... %}` ↔ `{% endif %}`, "
                "`{% for ... %}` ↔ `{% endfor %}`. Откройте шаблон в Word и убедитесь, "
                "что все условные блоки закрыты."
            )

        # Pattern: file not found / permission
        if isinstance(e, FileNotFoundError) or "no such file" in err_msg.lower():
            detail["message"] = f"Файл шаблона не найден: {template_name}"
            detail["hint"] = "Загрузите шаблон через UI «Субсидии → Шаблоны → Загрузить свой шаблон»."

        raise HTTPException(500, detail=detail)

    # For contract docs: append ТЗ table with items
    if doc_type == "contract" and items_list:
        try:
            from docx import Document as _DocxDoc
            from docx.shared import Pt, Cm, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement

            doc = _DocxDoc(buf)

            # Add page break before ТЗ
            doc.add_page_break()

            # Title
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = title_para.add_run("ТЕХНИЧЕСКОЕ ЗАДАНИЕ")
            run.bold = True
            run.font.size = Pt(12)

            subtitle = doc.add_paragraph()
            subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
            subtitle.add_run(f"(Приложение к договору № {p.contract_number or '___'} от {_fmt_date(p.contract_date) or '__.__.____'})")

            doc.add_paragraph()  # spacer

            # Table with columns: №, Фото, Наименование и описание, Кол-во, Ед., Цена ед., Сумма
            table = doc.add_table(rows=1, cols=7)
            table.style = 'Table Grid'

            # Header row
            hdr_cells = table.rows[0].cells
            headers_tz = ["№", "Фото", "Наименование и описание", "Кол-во", "Ед.", "Цена ед., ₽", "Сумма, ₽"]
            col_widths_cm = [1.0, 2.5, 8.0, 1.8, 1.5, 2.8, 2.8]
            for i, (hdr_cell, hdr_text, w) in enumerate(zip(hdr_cells, headers_tz, col_widths_cm)):
                hdr_cell.width = Cm(w)
                para = hdr_cell.paragraphs[0]
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = para.add_run(hdr_text)
                run.bold = True
                run.font.size = Pt(9)
                # Blue background
                tc = hdr_cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:fill'), '1E40AF')
                shd.set(qn('w:color'), 'FFFFFF')
                shd.set(qn('w:val'), 'clear')
                tcPr.append(shd)
                # White font
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

            # Data rows
            total_sum = 0.0
            for item_data in items_list:
                row_cells = table.add_row().cells
                row_cells[0].text = str(item_data["num"])
                row_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                # Photo cell: leave empty
                row_cells[1].text = ""
                # Name + description
                name_cell = row_cells[2]
                name_para = name_cell.paragraphs[0]
                name_run = name_para.add_run(str(item_data["name"]))
                name_run.bold = True
                name_run.font.size = Pt(9)
                if item_data.get("description"):
                    desc_para = name_cell.add_paragraph()
                    desc_run = desc_para.add_run(str(item_data["description"]))
                    desc_run.font.size = Pt(8)
                    desc_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

                qty_val = item_data.get("quantity", "")
                row_cells[3].text = str(qty_val) if qty_val != "" else "—"
                row_cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                row_cells[4].text = str(item_data.get("unit", "") or "—")
                row_cells[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                row_cells[5].text = str(item_data.get("unit_price", "") or "—")
                row_cells[5].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                row_cells[6].text = str(item_data.get("total_price", "") or "—")
                row_cells[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

                # Font size for all data cells
                for cell in row_cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            if not run.font.size:
                                run.font.size = Pt(9)

                try:
                    price_str = str(item_data.get("total_price", "")).replace(" ", "").replace(",", ".").replace("₽", "").strip()
                    total_sum += float(price_str) if price_str else 0
                except Exception:
                    pass

            # Total row
            total_row_cells = table.add_row().cells
            # Merge cells 0-5
            total_row_cells[5].merge(total_row_cells[0])
            merged_para = total_row_cells[0].paragraphs[0]
            merged_run = merged_para.add_run("НМЦК итого:")
            merged_run.bold = True
            merged_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            total_row_cells[6].text = _fmt_money_plain(total_sum)
            if total_row_cells[6].paragraphs[0].runs:
                total_row_cells[6].paragraphs[0].runs[0].bold = True
            total_row_cells[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

            # Save back to buf
            buf2 = BytesIO()
            doc.save(buf2)
            buf2.seek(0)
            buf = buf2
        except Exception as tz_err:
            # Don't fail the whole request if ТЗ append fails — just log
            import traceback
            print(f"ТЗ append error: {tz_err}\n{traceback.format_exc()}")

    # ── Methodology attach: приклеиваем методичку к готовому договору ──────
    # Владелец: методичка (большая/малая) — отдельный документ, физически
    # отсутствующий во всех семи шаблонах договора (см. test_contract_templates.py,
    # _METHODOLOGY_MARKERS). Она приклеивается ПОСЛЕ рендера договора через
    # docxcompose.Composer — итоговый файл содержит и договор, и методичку.
    if doc_type in CONTRACT_TYPED_FORM_DOC_TYPES:
        methodology = getattr(p, "methodology", None)
        if methodology in ("large", "small"):
            methodology_doc_type = f"methodology_{methodology}"
            meth_label = "большие" if methodology == "large" else "малые"
            meth_path, _meth_file, _meth_base = _resolve_doc_template_path(
                methodology_doc_type, p.subsidy_id
            )
            if not os.path.exists(meth_path):
                raise HTTPException(
                    422,
                    detail={
                        "code": "METHODOLOGY_TEMPLATE_MISSING",
                        "message": f"Не найден файл методических рекомендаций ({meth_label})",
                        "hint": (
                            f"В закупке выбрана методичка «{meth_label}», но соответствующий "
                            f"файл шаблона ({DOC_TYPES[methodology_doc_type][0]}) не загружен "
                            "ни на субсидию, ни глобально. Загрузите файл в «Шаблоны документов» "
                            "субсидии или положите его в backend/templates/, либо снимите выбор "
                            "методички в закупке."
                        ),
                        "doc_type": doc_type,
                        "methodology": methodology,
                    },
                )
            try:
                from docxcompose.composer import Composer as _Composer
                from docx import Document as _ComposeDoc

                buf.seek(0)
                _master = _ComposeDoc(buf)
                _composer = _Composer(_master)
                _composer.append(_ComposeDoc(meth_path))
                _composed_buf = BytesIO()
                _composer.save(_composed_buf)
                _composed_buf.seek(0)
                buf = _composed_buf
            except HTTPException:
                raise
            except Exception as meth_err:
                logger.exception(
                    "Methodology attach error for purchase %s, doc_type=%s, methodology=%s",
                    pid, doc_type, methodology,
                )
                raise HTTPException(
                    422,
                    detail={
                        "code": "METHODOLOGY_ATTACH_FAILED",
                        "message": "Не удалось приклеить методические рекомендации к договору",
                        "hint": f"{type(meth_err).__name__}: {meth_err}",
                        "doc_type": doc_type,
                        "methodology": methodology,
                    },
                )

    # ── Phase 19.06: merge with secondary doc ──────────────────────────────
    # When ?merge=<doc_type> is passed, render the secondary template against
    # the same context and append its paragraphs/tables after a page break.
    if merge and merge in DOC_TYPES and merge != doc_type:
        try:
            from docxtpl import DocxTemplate as _Tpl
            from docx import Document as _Docx
            from copy import deepcopy

            secondary_file, secondary_base = DOC_TYPES[merge]
            secondary_path = os.path.join(TEMPLATES_DIR, secondary_file)
            # subsidy override for secondary
            if p.subsidy_id:
                sub_override = os.path.join(
                    SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{merge}.docx"
                )
                if os.path.exists(sub_override):
                    secondary_path = sub_override
            # fallback if the dedicated secondary file is missing
            if not os.path.exists(secondary_path):
                fb = DOC_TYPE_FALLBACK_FILES.get(merge)
                if fb:
                    fb_path = os.path.join(TEMPLATES_DIR, fb)
                    if os.path.exists(fb_path):
                        secondary_path = fb_path

            if os.path.exists(secondary_path):
                sec_tpl = _Tpl(secondary_path)
                sec_tpl.render(context)
                sec_buf = BytesIO()
                sec_tpl.save(sec_buf)
                sec_buf.seek(0)

                # Append secondary into primary
                buf.seek(0)
                main_doc = _Docx(buf)
                sec_doc = _Docx(sec_buf)

                main_doc.add_page_break()
                # Copy every top-level element (paragraphs, tables, etc.) from body
                for element in sec_doc.element.body:
                    main_doc.element.body.append(deepcopy(element))

                merged_buf = BytesIO()
                main_doc.save(merged_buf)
                merged_buf.seek(0)
                buf = merged_buf
                # Update filename to reflect merge
                filename_base = f"{filename_base}_и_{secondary_base}"
        except Exception as merge_err:
            import traceback
            print(f"Doc merge error ({doc_type} + {merge}): {merge_err}\n{traceback.format_exc()}")

    # ── Strip Word review comments (template-author hints) from the final file ──
    # Templates carry Word comments explaining {{tags}} to whoever edits the
    # .docx TEMPLATE; docxtpl's render leaves them in place, so they must be
    # cut here before the file reaches the counterparty. Runs after render,
    # ТЗ append, methodology attach and merge, so it always sees the final bytes.
    buf.seek(0)
    buf = BytesIO(_strip_word_comments(buf.read()))

    _subj = _sanitize_subject(getattr(p, "subject", "") or "")
    if _subj:
        safe_name = f"{filename_base}_{_subj}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    else:
        safe_name = f"{filename_base}_{p.registry_number or pid}.docx".replace("/", "-").replace(" ", "_")
    encoded_name = quote(safe_name, safe="-_.~")
    resp_headers: dict = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    # phase31-02: surface non-silent fallback via response headers
    if _fallback_info:
        resp_headers["X-Template-Fallback"] = "1"
        resp_headers["X-Template-Fallback-Reason"] = quote(_fallback_info["reason"][:200], safe="")
        resp_headers["X-Template-Fallback-Original"] = quote(_fallback_info["original"], safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=resp_headers,
    )


@router.get("/{pid}/fabrikant-package")
async def download_fabrikant_package(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Render and ZIP 5 documents for ЭТП Fabrikant.

    Individual render failures are tolerated: the failed doc is omitted from
    the ZIP and listed in errors.txt.  If ALL docs fail → HTTP 500.
    """
    import zipfile as _zipfile

    rendered, errors = await render_fabrikant_package_files(db, pid)

    if not rendered:
        raise HTTPException(
            500,
            detail={
                "code": "TEMPLATE_RENDER_ERROR",
                "message": "Не удалось сформировать ни один документ для пакета Фабрикант",
                "error_raw": "\n".join(errors),
            },
        )

    # ZIP archive names: Russian base + actual extension from ascii_name
    _ru_bases = ["Инструкция", "Форма_заявки", "Документация", "Проект_договора", "ТЗ"]
    zip_buf = BytesIO()
    with _zipfile.ZipFile(zip_buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        _ru_iter = iter(_ru_bases)
        for ascii_name, ru_title, data in rendered:
            _ru_base = next(_ru_iter, os.path.splitext(ascii_name)[0])
            _ext = os.path.splitext(ascii_name)[1] or ".docx"
            zf.writestr(_ru_base + _ext, data)
        if errors:
            zf.writestr("errors.txt", "\n\n".join(errors))
    zip_buf.seek(0)

    safe_zip_name = f"Фабрикант_закупка_{pid}.zip"
    encoded_zip_name = quote(safe_zip_name, safe="-_.~")
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip_name}"},
    )


# ── KP xlsx export ───────────────────────────────────────────────────────────

@guide_router.get("/purchases/{pid}/kp-xlsx")
async def download_kp_xlsx(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate xlsx with purchase items (for КП request attachment)."""
    return await build_kp_xlsx(pid, db)


@guide_router.get("/template-guide")
async def download_template_guide(
    current_user=Depends(get_current_user),
):
    """Download a .docx reference guide with all available template variables."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    doc.add_heading("Руководство по разметке шаблонов документов", 0)

    p = doc.add_paragraph(
        "Шаблоны документов используют синтаксис Jinja2 (docxtpl). "
        "Переменные заключаются в двойные фигурные скобки: {{variable}}. "
        "Для циклов используется синтаксис: {%tr for item in items %} ... {%tr endfor %}."
    )

    doc.add_heading("Доступные переменные", 1)

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Переменная"
    hdr[1].text = "Описание"
    hdr[2].text = "Пример записи"
    hdr[3].text = "Результат"
    for cell in hdr:
        for run in cell.paragraphs[0].runs:
            run.bold = True

    for var, desc, ex_t, ex_r in TEMPLATE_VARIABLES:
        if not var:
            # Section header row
            row = table.add_row().cells
            row[0].merge(row[3])
            p = row[0].paragraphs[0]
            run = p.add_run(desc)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
            continue
        row = table.add_row().cells
        row[0].text = var
        row[1].text = desc
        row[2].text = ex_t
        row[3].text = ex_r

    doc.add_heading("Примеры использования в шаблоне Word", 1)

    doc.add_heading("Таблица согласующих", 2)
    doc.add_paragraph(
        '{%tr for a in approvers %}\n'
        '| {{a.num}} | {{a.role_name}} | {{a.full_name}} | {{a.signature_img}} | {{a.decided_date}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Таблица позиций закупки", 2)
    doc.add_paragraph(
        '{%tr for item in items %}\n'
        '| {{item.num}} | {{item.name}} | {{item.quantity}} | {{item.unit}} | {{item.unit_price}} | {{item.total_price}} |\n'
        '{%tr endfor %}'
    )

    doc.add_heading("Уровни субсидии (ФЭО)", 2)
    doc.add_paragraph(
        "Вставьте одну из этих переменных в нужное место шаблона Word:\n\n"
        "  Полный путь одной строкой:\n"
        "    {{feo_path}}\n"
        "  → Пример: «Персонал → Зарплата → Основной ФОТ»\n\n"
        "  Отдельные уровни:\n"
        "    Направление: {{feo_level_1}}\n"
        "    Тип:         {{feo_level_2}}\n"
        "    Категория:   {{feo_level_3}}\n\n"
        "Если закупка без ФЭО-категорий — переменные будут пустыми.\n"
        "Если у субсидии только 1 уровень — feo_level_2 и feo_level_3 пустые."
    )

    doc.add_heading("Условные блоки (НДС)", 2)
    doc.add_paragraph(
        '{% if vat_applicable %}\n'
        'В том числе НДС {{vat_rate}}%: {{vat_amount_num}} руб.\n'
        '{% else %}\n'
        'НДС не облагается {{vat_exemption_article}}\n'
        '{% endif %}'
    )

    doc.add_heading("Частые ошибки", 1)
    doc.add_paragraph(
        "1. Русский текст внутри {{ }} — ошибка: {{ contract_date г. }}\n"
        "   Правильно: {{ contract_date }} г.\n\n"
        "2. Word разбивает переменную на фрагменты — удалите и наберите заново\n\n"
        "3. Пустое значение — поле не заполнено в карточке закупки"
    )

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('Инструкция_по_шаблонам.docx', safe='-_.~')}"},
    )


@guide_router.get("/template-vars")
async def get_template_vars(current_user=Depends(get_current_user)):
    """Return all template variables with description, example template text, and example result."""
    result = []
    for entry in TEMPLATE_VARIABLES:
        var, desc, ex_t, ex_r = entry
        if not var:
            continue  # skip section headers
        result.append({
            "var": var,
            "description": desc,
            "example_template": ex_t,
            "example_result": ex_r,
        })
    return result
