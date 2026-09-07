"""Рендер пакета из 5 документов для запроса цен на ЭТП «Фабрикант»."""


import os
from datetime import date
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.event import Event
from app.models.feo_category import FeoCategory

from .doc_types import (
    DOC_TYPES,
    TEMPLATES_DIR,
    SUBSIDY_TEMPLATES_DIR,
    DOC_TYPE_FALLBACK_FILES,
    CONTRACT_FAMILY_DOC_TYPES,
    FABRIKANT_PKG_FILE_NAMES,
)
from .formatting import (
    _fmt_date,
    _fmt_money,
    _fmt_money_plain,
    _clean_id,
    _signatory_position,
    _fio_to_initials_prefix,
    _rubles_to_words,
    _merge_identical_items,
)
from .templates import _resolve_vat_exemption_basis, _vat_exemption_missing_hint
from .contexts import _signatory_split, _build_contract_items_context, _format_service_term
from .morphology import _to_gen_fio, _inflect_phrase_genitive
from .docx_post import _strip_tech_spec_legend
from app.services.acceptance_docs import derived_scalars as _acceptance_derived_scalars

import logging

logger = logging.getLogger(__name__)


async def render_fabrikant_package_files(
    db: AsyncSession,
    purchase_id: int,
) -> tuple[list[tuple[str, str, bytes]], list[str]]:
    """Render 5 Fabrikant documents for *purchase_id*.

    Returns:
        rendered: list of (ascii_file_name, ru_title, bytes)
        errors:   list of human-readable error strings for failed docs
    """
    import traceback as _traceback
    from docxtpl import DocxTemplate as _DxTpl
    from app.models.contract_item import ContractItem as _CI

    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.contract_items),
            selectinload(Purchase.assigned_user),
        )
        .where(Purchase.id == purchase_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        return [], [f"Закупка {purchase_id} не найдена"]

    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    subsidy = subsidy_r.scalar_one_or_none()

    customer_org = None
    customer_ctr = None
    if subsidy and subsidy.org_id:
        from app.models.organization import Organization as _Org
        org_r = await db.execute(select(_Org).where(_Org.id == subsidy.org_id))
        customer_org = org_r.scalar_one_or_none()
        if customer_org and customer_org.contractor_id:
            from app.models.contractor import Contractor as _CtrC
            ctr_r = await db.execute(select(_CtrC).where(_CtrC.id == customer_org.contractor_id))
            customer_ctr = ctr_r.scalar_one_or_none()

    # Правило №6: единый источник реквизитов Заказчика — org_requisites()
    # (Contractor, если org.contractor_id задан и найден; иначе deprecated
    # колонки Organization). См. app/routers/documents.py — тот же паттерн.
    from app.services.org_requisites import org_requisites
    _cust_req = org_requisites(customer_org, customer_ctr) if customer_org else {}

    event = None
    if p.event_id:
        ev_r = await db.execute(select(Event).where(Event.id == p.event_id))
        event = ev_r.scalar_one_or_none()

    feo_path = feo_level_1 = feo_level_2 = feo_level_3 = ""
    if p.feo_category_id:
        feo_res = await db.execute(select(FeoCategory))
        all_feo = {f.id: f for f in feo_res.scalars().all()}
        path_nodes: list = []
        node_id = p.feo_category_id
        visited: set = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            cat = all_feo.get(node_id)
            if not cat:
                break
            path_nodes.append(cat)
            node_id = cat.parent_id
        path_nodes.reverse()
        feo_path = " → ".join(n.name.strip() for n in path_nodes)
        if len(path_nodes) >= 1: feo_level_1 = path_nodes[0].name.strip()
        if len(path_nodes) >= 2: feo_level_2 = path_nodes[1].name.strip()
        if len(path_nodes) >= 3: feo_level_3 = path_nodes[2].name.strip()

    def _fmt_initials(full: str) -> str:
        if not full:
            return ""
        parts = full.strip().split()
        if not parts:
            return ""
        surname = parts[0]
        initials = [w[0].upper() + "." for w in parts[1:3] if w and w[0].isalpha()]
        return f"{surname} {''.join(initials)}".strip()

    assigned_full = (getattr(p.assigned_user, "full_name", None) or "") if getattr(p, "assigned_user", None) else ""
    raw_responsible = assigned_full or p.responsible_person or ""
    resolved_responsible = _fmt_initials(raw_responsible) if raw_responsible else ""

    # Этот эндпоинт всегда рендерит один и тот же фиксированный набор из 5
    # doc_type — FABRIKANT_PKG_FILE_NAMES (fabrikant_* + tech_spec_request).
    # ВСЕ они намеренно исключены из CONTRACT_FAMILY_DOC_TYPES: это пакет для
    # тендерной процедуры на Фабрикант, публикуется ДО выбора поставщика —
    # ContractItem на этой стадии закупки ещё физически не существует, поэтому
    # items_list здесь по-прежнему строится из purchase_items (план), как и
    # раньше. Sanity-check ниже фейлит явно, если это когда-нибудь изменится
    # (новый doc_type в списке окажется договорным) — молчаливая подмена на
    # плановые данные для настоящего договорного документа недопустима.
    _fabrikant_pkg_doc_keys = {dk for dk, _, _ in FABRIKANT_PKG_FILE_NAMES}
    assert not (_fabrikant_pkg_doc_keys & CONTRACT_FAMILY_DOC_TYPES), (
        "render_fabrikant_package_files теперь рендерит договорной doc_type "
        f"({_fabrikant_pkg_doc_keys & CONTRACT_FAMILY_DOC_TYPES}) — items_list "
        "здесь построен из purchase_items (план), нужно переключить на "
        "_build_items_list_from_contract_items, иначе документ уйдёт с плановыми данными"
    )

    items_list = []
    for idx, (item, qty, total) in enumerate(_merge_identical_items(p.items or []), start=1):
        items_list.append({
            "num": idx,
            "name": item.item_name or "",
            "description": "",
            "type": item.item_type or "",
            "item_kind": (item.product.item_kind if item.product else None) or "товар",
            "quantity": float(qty) if qty else "",
            "unit": item.unit or "",
            "unit_price": _fmt_money(item.unit_price),
            "total_price": _fmt_money(total),
            "total": _fmt_money(total),
            "photo": "",
            # Поля для repair_framework (появятся позже, пока заглушки)
            "code": "",
            "norm_hours": "",
        })

    # Ставка НДС — только из введённого пользователем, без придуманного
    # значения по умолчанию (см. подробный комментарий у generate_document /
    # _require_vat_rate_for_doc). None = не указана, 0 = валидная ставка 0%.
    # Этот пакет из 5 документов рендерится «по-доброму» — сбой одного
    # шаблона не должен ронять остальные (см. try/except в цикле ниже),
    # поэтому здесь НЕ бросаем HTTPException на весь пакет; вместо этого
    # единственный шаблон, который реально печатает ставку
    # (fabrikant_contract_project.docx), отдельно проверяется прямо перед
    # рендером — см. чуть ниже по циклу.
    vat_app = bool(p.vat_applicable)
    vat_rate_val = p.vat_rate
    price_val = float(p.contract_price or 0)
    vat_amount_val = (
        price_val * vat_rate_val / (100 + vat_rate_val)
        if (vat_app and price_val and vat_rate_val is not None) else 0.0
    )
    if vat_app:
        if vat_rate_val is not None:
            vat_info_line = f"В том числе НДС {vat_rate_val}%: {_fmt_money_plain(vat_amount_val)} руб."
        else:
            vat_info_line = "НДС (ставка не указана)"
    else:
        # Основание — введённое человеком ИЛИ автоопределённое (самозанятый /
        # ГПХ с физлицом), см. _resolve_vat_exemption_basis. Пустое основание
        # для fabrikant_contract_project отдельно отбито ниже, прямо перед
        # рендером этого шаблона (см. try/except-цикл).
        art = _resolve_vat_exemption_basis(p)
        vat_info_line = "НДС не облагается" + (f" ({art})" if art else "")

    def _cd_parts():
        d = p.contract_date
        if not d:
            return "", "", ""
        if isinstance(d, str):
            try:
                from datetime import date as _d2
                d = _d2.fromisoformat(d)
            except ValueError:
                return "", "", ""
        months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        return str(d.day).zfill(2), months_ru[d.month - 1], str(d.year)

    cd_day, cd_month, cd_year = _cd_parts()

    def _g2(*sources, default=""):
        for s in sources:
            if s:
                return s
        return default

    cust_signatory_full_z = _cust_req.get('signatory') or ""
    _cust_z_last = _cust_req.get('signatory_last_name') or None
    _cust_z_first = _cust_req.get('signatory_first_name') or None
    _cust_z_middle = _cust_req.get('signatory_middle_name') or None
    _cust_z_position = _cust_req.get('signatory_position') or None
    cust_sig_z = _signatory_split(
        cust_signatory_full_z,
        last=_cust_z_last, first=_cust_z_first, middle=_cust_z_middle, position=_cust_z_position,
    )
    cust_signatory_basis_z = _g2(
        customer_ctr.signatory_basis if customer_ctr else None,
        "Устава",
    )
    c = p.contractor
    ctr_sig_z = _signatory_split(
        c.signatory if c else "",
        last=getattr(c, 'signatory_last_name', None) if c else None,
        first=getattr(c, 'signatory_first_name', None) if c else None,
        middle=getattr(c, 'signatory_middle_name', None) if c else None,
        position=getattr(c, 'signatory_position', None) if c else None,
    )

    # Fabrikant notice_number — platform_number (номер процедуры на ЭТП),
    # откат на external_id (наш internal requestId), если ещё не проставлен
    _notice_number = ""
    try:
        from app.models.platform_publication import PlatformPublication as _PlatPubZ
        _pub_q = await db.execute(
            select(_PlatPubZ.platform_number, _PlatPubZ.external_id)
            .where(
                _PlatPubZ.purchase_id == p.id,
                _PlatPubZ.platform == "fabrikant",
            )
            .order_by(_PlatPubZ.id.desc())
            .limit(1)
        )
        _pub_row_z = _pub_q.first()
        if _pub_row_z:
            _notice_number = _pub_row_z[0] or _pub_row_z[1] or ""
    except Exception:
        pass

    # applications_review_date
    if p.applications_review_date:
        _app_review_date = _fmt_date(p.applications_review_date)
    elif p.submission_deadline:
        from datetime import timedelta as _tds
        _next = p.submission_deadline.date() + _tds(days=1)
        while _next.weekday() >= 5:
            _next += _tds(days=1)
        _app_review_date = _next.strftime("%d.%m.%Y")
    else:
        _app_review_date = ""

    ci_ctx_z = await _build_contract_items_context(p, db)

    # ПРАВИЛО №6 (2026-09-07, группа D4): закрывающий документ — из JSONB
    # acceptance_docs (первый документ), не напрямую из legacy-скаляров.
    _acc = _acceptance_derived_scalars(p)

    context = {
        "purchase_number": p.purchase_number or "",
        "registry_number": p.registry_number or "",
        "purchase_method": {"single": "Единственный поставщик", "competitive": "Конкурсная процедура"}.get(p.purchase_method or "", p.purchase_method or ""),
        "subject": p.subject or "",
        "status": p.status or "",
        "responsible_person": resolved_responsible,
        "responsible_person_full": raw_responsible,
        "subsidy_name": subsidy.name if subsidy else "",
        "subsidy_year": subsidy.year if subsidy else "",
        "subsidy_budget": _fmt_money(subsidy.budget) if subsidy else "",
        "subsidy_agreement_number": (subsidy.agreement_number or "") if subsidy else "",
        "contractor_name": (c.name or "") if c else "",
        "contractor_inn": _clean_id(c.inn) if c else "",
        "contractor_kpp": _clean_id(c.kpp) if c else "",
        "contractor_address": (c.address or "") if c else "",
        "contractor_ogrn": (c.ogrn or "") if c else "",
        "contractor_phone": (c.phone or "") if c else "",
        "contractor_email": (c.email or "") if c else "",
        "contractor_signatory": (c.signatory or "") if c else "",
        "contractor_signatory_basis": (c.signatory_basis or "") if c else "",
        "contractor_settlement_account": (c.settlement_account or "") if c else "",
        "contractor_bank_name": (c.bank_name or "") if c else "",
        "contractor_bik": (c.bik or "") if c else "",
        "contractor_correspondent_account": (c.correspondent_account or "") if c else "",
        "contractor_signatory_position": _signatory_position(c.signatory) if c else "",
        "contractor_signatory_name": ctr_sig_z["name_full"],
        "contractor_signatory_name_genitive": ctr_sig_z["name_genitive"],
        "contractor_signatory_initials": ctr_sig_z["name_initials"],
        "contractor_ogrnip": (c.ogrn or "") if (c and (c.org_type or "").lower().startswith("ип")) else "",
        "contractor_full_name": (c.full_name or c.name or "") if c else "",
        "contractor_short_name": (c.name or "") if c else "",
        "feo_category_name": p.feo_category.name if p.feo_category else "",
        "feo_path": feo_path,
        "feo_level_1": feo_level_1,
        "feo_level_2": feo_level_2,
        "feo_level_3": feo_level_3,
        "total_nmcd": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price),
        "total_nmck": _fmt_money(p.total_nmck or p.nmck or p.planned_total_price),
        "nmck": _fmt_money(p.nmck or p.total_nmck),
        "contract_price": _fmt_money(p.contract_price),
        "economy": _fmt_money(p.economy),
        "contract_number": p.contract_number or "",
        "contract_date": _fmt_date(p.contract_date) or "__.__._____ г.",
        "contract_date_day": cd_day,
        "contract_date_month": cd_month,
        "contract_date_year": cd_year,
        "execution_term": _fmt_date(p.execution_term),
        "delivery_date": _fmt_date(p.delivery_date),
        "delivery_location": p.delivery_location or "",
        "country_origin": p.country_origin or "",
        "payment_doc_number": p.payment_doc_number or "",
        "payment_doc_date": _fmt_date(p.payment_doc_date),
        "payment_amount": _fmt_money(p.payment_amount),
        "items": items_list,
        "items_count": len(items_list),
        "item_names": p.subject or ", ".join(i["name"] for i in items_list if i["name"]),
        "approvers": [],
        "initiator_name": "",
        "initiator_role": "",
        "initiator_dept": "",
        "event_name": event.name if event else "",
        "contract_type": {"single": "Единственный поставщик"}.get(p.purchase_contract_type or "", ""),
        "today": _fmt_date(date.today()),
        "today_iso": date.today().isoformat(),
        "service_name": p.subject or "",
        "submission_deadline_date": p.submission_deadline.date().isoformat() if p.submission_deadline else "",
        "submission_deadline_time": p.submission_deadline.strftime("%H:%M") if p.submission_deadline else "",
        "submission_deadline_datetime": p.submission_deadline.strftime("%d.%m.%Y %H:%M") if p.submission_deadline else "",
        "subsidy_agreement_text": (subsidy.agreement_text if (subsidy and subsidy.agreement_text) else ""),
        "vat_applicable": vat_app,
        "vat_rate": vat_rate_val,
        "vat_amount_num": _fmt_money_plain(vat_amount_val),
        "vat_amount_words": _rubles_to_words(vat_amount_val),
        "vat_exemption_article": ("" if vat_app else art),
        "vat_info_line": vat_info_line,
        "contract_price_num": _fmt_money_plain(p.contract_price),
        "contract_price_words": _rubles_to_words(p.contract_price),
        "subject_kind": "goods",
        "period_type": p.service_period_type or "period",
        "service_start_date": _fmt_date(p.service_start_date) or _fmt_date(p.contract_date),
        "service_end_date": _fmt_date(p.service_end_date) or _fmt_date(p.execution_term),
        "service_date": _fmt_date(p.execution_term),
        "service_term": _format_service_term(p),
        "service_term_mode": p.service_term_mode or "",
        "service_term_days": p.service_term_days or "",
        "service_term_type": p.service_term_type or "",
        "service_deadline_date": _fmt_date(p.service_deadline_date),
        # Дата окончания срока действия договора (п. 8.1) — поле Purchase.contract_end_date
        "contract_end_date": _fmt_date(p.contract_end_date),
        "third_party_involved": bool(p.third_party_involved),
        "acceptance_doc_name": _acc["name"] or "",
        "acceptance_doc_number": _acc["number"] or "",
        "acceptance_doc_date": _fmt_date(_acc["date"]) or "",
        "acceptance_doc_amount": _fmt_money(_acc["amount"]) if _acc["amount"] else "",
        "receipts": [],
        "receipt_images": [],
        "receipts_small": [],
        "receipts_full": [],
        "receipt_pairs": [],
        "left_receipts": [],
        "right_receipts": [],
        "receipts_table": "",
        # Customer (Organisation)
        "customer_name": _g2(customer_org.name if customer_org else None, customer_ctr.name if customer_ctr else None),
        "customer_full_name": _g2(_cust_req.get('full_name'), customer_ctr.name if customer_ctr else None, customer_org.name if customer_org else None),
        "customer_short_name": _g2(customer_org.name if customer_org else None, customer_ctr.name if customer_ctr else None),
        "customer_address": _g2(_cust_req.get('address')),
        "customer_postal_address": _g2(customer_ctr.postal_address if customer_ctr else None, _cust_req.get('address')),
        "customer_inn": _clean_id(_g2(_cust_req.get('inn'))),
        "customer_kpp": _clean_id(_g2(_cust_req.get('kpp'))),
        "customer_ogrn": _g2(_cust_req.get('ogrn')),
        "customer_bank_name": _g2(customer_ctr.bank_name if customer_ctr else None),
        "customer_settlement_account": _g2(customer_ctr.settlement_account if customer_ctr else None),
        "customer_correspondent_account": _g2(customer_ctr.correspondent_account if customer_ctr else None),
        "customer_bik": _g2(customer_ctr.bik if customer_ctr else None),
        # Лицевой счёт Заказчика
        "customer_personal_account": _g2(customer_ctr.personal_account if customer_ctr else None),
        "customer_phone": _g2(customer_ctr.phone if customer_ctr else None),
        "customer_email": _g2(customer_ctr.email if customer_ctr else None),
        "customer_signatory": cust_signatory_full_z,
        "customer_signatory_position": cust_sig_z["position"],
        "customer_signatory_name": cust_sig_z["name_full"],
        "customer_signatory_name_genitive": cust_sig_z["name_genitive"],
        "customer_signatory_initials": cust_sig_z["name_initials"],
        # Инициалы впереди: «Е.В. Козеев» (для строки подписи)
        "customer_signatory_name_initials": _fio_to_initials_prefix(cust_sig_z["name_full"]),
        "customer_signatory_basis": cust_signatory_basis_z,
        "contract_city": (customer_org.contract_city or "Москва") if customer_org else "Москва",
        # Fabrikant-specific
        "notice_number": _notice_number,
        "payment_term_days": p.payment_term_days if (p.payment_term_days is not None) else 10,
        "applications_review_date": _app_review_date,
        # Phase 28 keys (best-effort)
        "subsidy_grantor_name": (subsidy.grantor_name or "").strip() if subsidy else "",
        "subsidy_ministry_name": (subsidy.ministry_name or "").strip() if subsidy else "",
        "subsidy_agreement_date": "",
        "advance_amount": _fmt_money(p.advance_amount) if p.advance_amount else "",
        "acceptance_term_days": p.acceptance_term_days if p.acceptance_term_days is not None else 5,
        "penalty_rate": str(p.penalty_rate) if p.penalty_rate is not None else "0.1",
        "warranty_period_days": p.warranty_period_days if p.warranty_period_days is not None else 15,
        "is_retroactive": bool(p.is_retroactive),
        # Phase 28 T3: условные блоки (поля в модели Purchase пока отсутствуют — T8)
        "delivery_by_supplier": bool(getattr(p, "delivery_by_supplier", True)),
        "has_stages": bool(getattr(p, "has_stages", False)),
        "subsidy_extra_clause_1": (subsidy.extra_contract_clause_1 or '').strip() if subsidy else '',
        "subsidy_extra_clause_2": (subsidy.extra_contract_clause_2 or '').strip() if subsidy else '',
        "commission_members": [],
        "commission_member_1_name": "",
        "commission_member_2_name": "",
        "commission_member_3_name": "",
        "contractor_passport_series": (c.passport_series or '') if c else '',
        "contractor_passport_number": (c.passport_number or '') if c else '',
        "contractor_passport_issuer": (c.passport_issuer or '') if c else '',
        "contractor_passport_issued_date": _fmt_date(c.passport_issued_date) if c and c.passport_issued_date else '',
        "contractor_snils": (c.snils or '') if c else '',
        "contractor_registration_address": (c.registration_address or c.address or '') if c else '',
        "contractor_birth_date": _fmt_date(c.birth_date) if c and c.birth_date else '',
        "contractor_ogrnip_date": _fmt_date(p.contractor_ogrnip_date) if p.contractor_ogrnip_date else "",
        "repair_request_number": (p.repair_request_number or "").strip() if hasattr(p, "repair_request_number") else "",
        "procurement_protocol_number": (p.procurement_protocol_number or "").strip(),
        "procurement_order_number": (p.procurement_order_number or "").strip(),
    }
    context.update(ci_ctx_z)
    context["initiator_name_gen"] = ""
    context["initiator_position_gen"] = ""
    context["responsible_name_gen"] = _to_gen_fio(resolved_responsible)
    context["responsible_position_gen"] = ""
    context["initiator_dept_gen"] = ""
    context["service_name_gen"] = _inflect_phrase_genitive(p.subject or "")
    context["contractor_signatory_line"] = (
        f"{c.signatory}, действует на основании {c.signatory_basis}"
        if c and c.signatory and c.signatory_basis
        else ((c.signatory or "") if c else "")
    )
    context["contractor_bank_details"] = (c.bank_name or "") if c else ""
    context["contractor_org_type"] = (c.org_type or "") if c else ""

    # ── Which templates to render ─────────────────────────────────────────────
    # tech_spec_request with fallback to contract_tz
    _tz_file, _tz_base = DOC_TYPES.get("tech_spec_request", ("tech_spec_request.docx", "ТЗ_запрос_цен"))
    _tz_path = os.path.join(TEMPLATES_DIR, _tz_file)
    if p.subsidy_id:
        _sub_tz = os.path.join(SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), "tech_spec_request.docx")
        if os.path.exists(_sub_tz):
            _tz_path = _sub_tz
    if not os.path.exists(_tz_path):
        _fb = DOC_TYPE_FALLBACK_FILES.get("tech_spec_request", "contract_tz.docx")
        _fb_path = os.path.join(TEMPLATES_DIR, _fb)
        if os.path.exists(_fb_path):
            _tz_path = _fb_path

    # (doc_key, archive_name used in ZIP) — legacy internal names, kept for ZIP endpoint
    _pkg_docs_legacy = [
        ("fabrikant_instruction",      "Инструкция.docx"),
        ("fabrikant_application_form", "Форма_заявки.docx"),
        ("fabrikant_documentation",    "Документация.docx"),
        ("fabrikant_contract_project", "Проект_договора.docx"),
        ("tech_spec_request",          "ТЗ.docx"),
    ]

    # ── Override file_type → doc_key mapping ─────────────────────────────────
    _override_map = {
        "fabrikant_instruction":      "fabrikant_instruction",
        "fabrikant_application_form": "fabrikant_application_form",
        "fabrikant_documentation":    "fabrikant_documentation",
        "fabrikant_contract_project": "fabrikant_contract_project",
        "tech_spec_request":          "fabrikant_tech_spec",
    }
    from app.models.purchase_file import PurchaseFile as _PF
    _override_keys = list(_override_map.values())
    _pf_res = await db.execute(
        select(_PF)
        .where(
            _PF.purchase_id == purchase_id,
            _PF.file_type.in_(_override_keys),
            _PF.is_active == True,
        )
        .order_by(_PF.id.desc())
    )
    _overrides: dict[str, _PF] = {}
    for _pf in _pf_res.scalars().all():
        if _pf.file_type not in _overrides:
            _overrides[_pf.file_type] = _pf

    # ── Render each doc ───────────────────────────────────────────────────────
    # rendered: (ascii_file_name, ru_title, bytes)
    rendered: list[tuple[str, str, bytes]] = []
    errors: list[str] = []

    for (doc_key, ascii_name, ru_title), (_doc_key2, legacy_arc) in zip(FABRIKANT_PKG_FILE_NAMES, _pkg_docs_legacy):
        override_ft = _override_map.get(doc_key)
        if override_ft and override_ft in _overrides:
            _pf_ov = _overrides[override_ft]
            orig_ext = os.path.splitext(_pf_ov.original_name or _pf_ov.filename or "")[1] or ".docx"
            ov_ascii_name = os.path.splitext(ascii_name)[0] + orig_ext
            if _pf_ov.filepath and os.path.exists(_pf_ov.filepath):
                with open(_pf_ov.filepath, "rb") as _fh:
                    rendered.append((ov_ascii_name, ru_title, _fh.read()))
                continue
            else:
                errors.append(f"{ascii_name}: файл override не найден на диске ({_pf_ov.filepath})")

        if doc_key == "tech_spec_request":
            tpl_path = _tz_path
        else:
            tpl_file, _ = DOC_TYPES.get(doc_key, (f"{doc_key}.docx", doc_key))
            tpl_path = os.path.join(TEMPLATES_DIR, tpl_file)
            if p.subsidy_id:
                _sub_override = os.path.join(SUBSIDY_TEMPLATES_DIR, "subsidies", str(p.subsidy_id), f"{doc_key}.docx")
                if os.path.exists(_sub_override):
                    tpl_path = _sub_override

        if not os.path.exists(tpl_path):
            errors.append(f"{ascii_name}: шаблон не найден ({tpl_path})")
            continue

        try:
            # fabrikant_contract_project.docx — единственный шаблон в этом
            # пакете, реально печатающий данные о НДС ({{vat_rate}} /
            # {{vat_exemption_article}}). Оба случая («ставка не указана» и
            # «основание освобождения не указано») — печатать выдуманное
            # значение нельзя, отказываем именно по этому документу (остальные
            # 4 рендерятся дальше как обычно, см. try/except-цикл).
            if doc_key == "fabrikant_contract_project" and vat_app and vat_rate_val is None:
                raise ValueError(
                    "Не указана ставка НДС: закупка отмечена как облагаемая НДС, "
                    "но поле «Ставка НДС» в карточке закупки пустое. Заполните "
                    "ставку (0, 10 или 20 — как у поставщика), либо снимите "
                    "отметку «Облагается НДС», если это верно."
                )
            if doc_key == "fabrikant_contract_project" and not vat_app and not _resolve_vat_exemption_basis(p):
                raise ValueError("Не указано основание освобождения от НДС. " + _vat_exemption_missing_hint(p))
            _tpl = _DxTpl(tpl_path)
            _tpl.render(context)
            _buf = BytesIO()
            _tpl.save(_buf)
            _rendered_bytes = _buf.getvalue()
            if doc_key == "tech_spec_request":
                _rendered_bytes = _strip_tech_spec_legend(_rendered_bytes)
            rendered.append((ascii_name, ru_title, _rendered_bytes))
        except Exception as _re:
            _tb = _traceback.format_exc()
            errors.append(f"{ascii_name}: {type(_re).__name__}: {_re}\n{_tb[:500]}")
            logger.warning("fabrikant-package render error for %s (purchase %s): %s", doc_key, purchase_id, _re)

    return rendered, errors
