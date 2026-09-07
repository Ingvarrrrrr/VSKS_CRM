"""Orchestrator for POST /api/purchases/{pid}/documents/{doc_type}.

Wave 3f refactor: app/routers/documents.py::generate_document (~1533 lines)
was split into stage functions across services/documents/stages_*.py and
services/documents/contexts_*.py. This module calls them in the EXACT same
order as the original inline code so behavior stays byte-for-byte identical
(same HTTPException codes/detail, same docxtpl context, same DB writes,
same rendered .docx bytes). The router is now a thin wrapper — see
app/routers/documents.py::generate_document.

Preserved bug (do not fix — see stages_amounts.py docstring): when
vat_applicable=False and purchase_method='advance', compute_amounts_and_vat()
raises UnboundLocalError on `art` (in its own `return {... "art": art}`
dict literal), uncaught here, exactly like the original inline code raised
it uncaught while building the big context dict.
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.documents.stages_load import (
    validate_doc_type,
    load_purchase_and_relations,
    apply_responsible_person_update,
    framework_contract_guard,
    resolve_final_template,
)
from app.services.documents.stages_relations import (
    load_subsidy,
    load_customer,
    load_event,
    resolve_approvers,
    resolve_initiator,
    build_feo_path,
    resolve_responsible_person,
)
from app.services.documents.stages_template_engine import (
    build_docx_template,
    make_photo_resolver,
    make_base64_to_inline,
)
from app.services.documents.stages_items import build_items_and_subject_kind
from app.services.documents.stages_approvers_list import (
    load_approval_map,
    build_item_categories_str,
    build_approvers_list,
)
from app.services.documents.stages_amounts import contract_date_parts, compute_amounts_and_vat
from app.services.documents.contexts_build import build_base_context_part1, build_base_context_part2
from app.services.documents.contexts_extra import (
    add_phase28_context,
    add_genitive_forms,
    add_customer_context,
    add_fabrikant_context,
    add_misc_purchase_context,
    add_contractor_signatory_context,
)
from app.services.documents.stages_receipts import build_contract_items_and_receipts_context
from app.services.documents.stages_render import render_template
from app.services.documents.stages_postprocess import build_final_buffer
from app.services.documents.stages_contract_tz import append_tz_table_for_contract
from app.services.documents.stages_methodology import attach_methodology
from app.services.documents.stages_merge import merge_secondary_doc
from app.services.documents.stages_finalize import finalize_response


async def generate_document_bytes(
    db: AsyncSession,
    pid: int,
    doc_type: str,
    current_user,
    approver_ids: Optional[str] = None,
    initiator_id: Optional[int] = None,
    responsible_name: Optional[str] = None,
    tz_override_mode: Optional[str] = None,
    merge: Optional[str] = None,
    doc_indices: Optional[str] = None,
):
    """Returns (buf: BytesIO, media_type: str, headers: dict) ready to hand
    straight to StreamingResponse."""

    # Stage 1: validate doc_type + globally-missing template.
    template_path, template_file, filename_base = validate_doc_type(doc_type)

    # Stage 2: load purchase + relations.
    p = await load_purchase_and_relations(db, pid)
    await apply_responsible_person_update(p, responsible_name, db)

    # Stage 3: framework-head temp contract number + doc-type gates.
    await framework_contract_guard(p, doc_type, db)

    # Re-resolve template now subsidy_id is known.
    template_path, template_file, filename_base = resolve_final_template(doc_type, p.subsidy_id)

    # Subsidy / customer / event / approvers / initiator / FEO path / responsible.
    subsidy = await load_subsidy(db, p)
    customer_org, customer_ctr = await load_customer(db, subsidy)
    event = await load_event(db, p)
    selected_approvers, fh_pa_by_synth_id = await resolve_approvers(db, p, pid, doc_type, approver_ids)
    initiator = await resolve_initiator(db, current_user, initiator_id, subsidy, customer_org)
    feo_path, feo_level_1, feo_level_2, feo_level_3, item_feo_paths = await build_feo_path(db, p, doc_type)
    resolved_responsible, resolved_responsible_full = resolve_responsible_person(p, responsible_name)

    # docxtpl template object + InlineImage-producing helpers.
    tpl = build_docx_template(template_path, pid, doc_type)
    resolve_photo = make_photo_resolver(tpl)

    # Items / subject_kind.
    items_list, subject_kind = build_items_and_subject_kind(p, doc_type, tz_override_mode, resolve_photo)

    # Approvers list (electronic signatures).
    approval_map = await load_approval_map(db, pid)
    base64_to_inline = make_base64_to_inline(tpl)
    item_categories_str = build_item_categories_str(p)
    approvers_list = build_approvers_list(
        selected_approvers, item_feo_paths, feo_path, p, resolved_responsible_full,
        approval_map, fh_pa_by_synth_id, tpl, base64_to_inline,
    )

    c = p.contractor
    cd_day, cd_month, cd_year = contract_date_parts(p)

    # Amounts / VAT (preserved UnboundLocalError('art') bug — see module docstring).
    amounts = compute_amounts_and_vat(p, doc_type)

    # Main docxtpl context.
    context = build_base_context_part1(
        p, subsidy, c, doc_indices, doc_type,
        feo_path, feo_level_1, feo_level_2, feo_level_3,
        resolved_responsible, resolved_responsible_full,
        items_list, item_categories_str,
        amounts,
    )
    await build_base_context_part2(
        context, p, subsidy, db,
        approvers_list, initiator, event,
        cd_day, cd_month, cd_year,
        c, subject_kind,
        amounts,
    )
    add_phase28_context(context, subsidy, c, p)
    add_genitive_forms(context, p, resolved_responsible)
    add_customer_context(context, customer_org, customer_ctr)
    await add_fabrikant_context(context, db, p)
    add_misc_purchase_context(context, p, subsidy)
    add_contractor_signatory_context(context, c)

    # Contract-items context + advance-report receipts (own try/except → 500).
    receipt_png_paths = await build_contract_items_and_receipts_context(context, p, db, tpl, pid, doc_type)

    # Render (with custom-template auto-fallback) + post-process buffer.
    tpl, template_path, fallback_info = render_template(tpl, context, template_path, doc_type)
    buf = build_final_buffer(tpl, doc_type, approvers_list, receipt_png_paths, pid, template_path)

    # Contract ТЗ table append, methodology attach, secondary-doc merge.
    buf = append_tz_table_for_contract(buf, doc_type, items_list, p)
    buf = attach_methodology(buf, doc_type, p, pid)
    buf, filename_base = merge_secondary_doc(buf, merge, doc_type, context, p, filename_base)

    # Strip Word comments, build filename + response headers.
    return finalize_response(buf, p, pid, filename_base, fallback_info)
