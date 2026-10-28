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
from app.services.purchase_economy import purchase_economy_one
from app.services.purchase_order_numbering import assign_procurement_order_number_if_missing
from app.services.documents.contexts_build import build_base_context_part1, build_base_context_part2
from app.services.documents.contexts_extra import (
    add_phase28_context,
    add_genitive_forms,
    add_customer_context,
    add_fabrikant_context,
    add_misc_purchase_context,
    add_contractor_signatory_context,
    add_prepayment_context,
    add_day_words_context,
)
from app.services.documents.contractor_override import (
    load_contractor_override,
    merge_contractor_override,
)
from app.services.documents.contexts_org_people import add_chief_accountant_context
from app.services.documents.case_forms import add_all_case_forms
from app.services.documents.org_name_case import org_name_exceptions
from app.services.documents.stages_receipts import build_contract_items_and_receipts_context
from app.services.documents.stages_render import render_template
from app.services.documents.stages_postprocess import build_final_buffer
from app.services.documents.stages_contract_tz import append_tz_table_for_contract
from app.services.tz_items import tz_required
from app.services.documents.stages_methodology import attach_methodology
from app.services.documents.stages_merge import merge_secondary_doc
from app.services.documents.stages_finalize import finalize_response
from app.services.contractor_pii import user_can_view_contractor_pii


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
    # ИСПРАВЛЕНИЕ К2 (19.10.2026): видимость по id = видимость в списке —
    # сотрудник чужой орг. скачивал ТЗ/договор по известному pid, хотя сама
    # закупка/субсидия ему не видны (object_visibility.py, Правило №6).
    from app.auth.object_visibility import ensure_purchase_visible
    await ensure_purchase_visible(current_user, pid, db)
    await apply_responsible_person_update(p, responsible_name, db)

    # Stage 3: framework-head temp contract number + doc-type gates.
    await framework_contract_guard(p, doc_type, db)

    # Владелец (28.10.2026): номер приказа о закупке — та же схема присвоения
    # «при первом использовании», что и временный номер договора выше, но для
    # ЛЮБОГО doc_type (не только договорных) — см. docstring
    # purchase_order_numbering.py. Ручной номер не трогается.
    await assign_procurement_order_number_if_missing(db, p)

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
    # Фото товаров — один запрос в product_photos на все позиции закупки,
    # а не N синхронных попыток читать bytea с уже удалённой колонки
    # products.photo_data (владелец, 26.10.2026 — фото в отдельной таблице).
    from app.services.product_photo_store import load_photos_bulk
    _photo_map = await load_photos_bulk(db, [it.product_id for it in (p.items or [])])
    resolve_photo = make_photo_resolver(tpl, photo_map=_photo_map)

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
    # Владелец (05.10.2026, план «Шаблоны договоров», п.5): правка реквизитов
    # исполнителя на уровне субсидии (SubsidyContractorOverride) перекрывает
    # карточку контрагента в документе — не мутирует ORM Contractor.
    _contractor_override = await load_contractor_override(db, p.subsidy_id, p.contractor_id)
    c = merge_contractor_override(c, _contractor_override)
    cd_day, cd_month, cd_year = contract_date_parts(p)

    # Amounts / VAT (preserved UnboundLocalError('art') bug — see module docstring).
    amounts = compute_amounts_and_vat(p, doc_type)
    # ПРАВИЛО №6 (02.10.2026, шаг 3 плана «Деньги субсидии»): Purchase.economy
    # больше не заполняется — контекст документа читает расчёт
    # (app.services.purchase_economy, planned_total − факт законтрактованных
    # позиций), см. build_base_context_part1 (contexts_build.py).
    amounts["economy_val"] = await purchase_economy_one(db, p.id)

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
    # Паспорт/СНИЛС/адрес регистрации/дата рождения контрагента-физлица в
    # печатаемый документ — только с правом на раздел «Договоры» (владелец,
    # 2026-10-08; app/services/contractor_pii.py, ПРАВИЛО №6).
    _can_view_pii = await user_can_view_contractor_pii(current_user, db)
    add_phase28_context(context, subsidy, c, p, can_view_pii=_can_view_pii)
    await add_genitive_forms(
        context, p, resolved_responsible_full, db,
        getattr(subsidy, "org_id", None), responsible_name,
    )
    add_customer_context(context, customer_org, customer_ctr)
    # Главный бухгалтер Заказчика — единственный расчёт (ПРАВИЛО №6), см.
    # contexts_org_people.add_chief_accountant_context (тот же вызывается из
    # fabrikant_package.py).
    await add_chief_accountant_context(context, db, customer_org)
    await add_fabrikant_context(context, db, p)
    add_misc_purchase_context(context, p, subsidy)
    add_contractor_signatory_context(context, c, customer_org=customer_org)
    add_prepayment_context(context, p)
    add_day_words_context(context, p)

    # Все 5 косвенных падежей для каждой склоняемой переменной (задача
    # 29.10.2026, case_forms.py, ПРАВИЛО №6) — последний шаг сборки контекста,
    # все add_*_context выше уже положили финальные значения базовых
    # переменных (включая initiator_dept после дедупа тавтологии выше).
    add_all_case_forms(context, org_name_exceptions(customer_org))

    # Contract-items context + advance-report receipts (own try/except → 500).
    receipt_png_paths = await build_contract_items_and_receipts_context(context, p, db, tpl, pid, doc_type)

    # Render (with custom-template auto-fallback) + post-process buffer.
    tpl, template_path, fallback_info = render_template(tpl, context, template_path, doc_type)
    buf = build_final_buffer(tpl, doc_type, approvers_list, receipt_png_paths, pid, template_path)

    # Contract ТЗ table append, methodology attach, secondary-doc merge.
    # Владелец (30.09, заявка №92): «можно провести без ТЗ» — закупка с
    # tz_not_required=True (или purchase_method='advance') печатается БЕЗ
    # отдельного приложения «ТЕХНИЧЕСКОЕ ЗАДАНИЕ» после разрыва страницы;
    # простой перечень позиций внутри самого договора (context["items"],
    # см. build_base_context_part1 выше) никуда не девается — это ДРУГОЙ,
    # более лёгкий список, не формальное приложение ТЗ. Единый источник —
    # app.services.tz_items.tz_required (ПРАВИЛО №6).
    if tz_required(p):
        buf = append_tz_table_for_contract(buf, doc_type, items_list, p, photo_map=_photo_map)
    buf = attach_methodology(buf, doc_type, p, pid)
    buf, filename_base = merge_secondary_doc(buf, merge, doc_type, context, p, filename_base)

    # Strip Word comments, build filename + response headers.
    return finalize_response(buf, p, pid, filename_base, fallback_info)
