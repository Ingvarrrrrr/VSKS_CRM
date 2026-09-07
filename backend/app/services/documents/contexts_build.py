"""generate_document: main docxtpl context dict construction (stage "build
contract family / specific context" from the wave 3f split plan).

Split into two parts purely to stay under the 150-line-per-function budget —
together they reproduce the single `context = {...}` literal from the
original app/routers/documents.py::generate_document byte-for-byte (same
keys, same values, same order of evaluation for anything with side effects).
Part 2 needs `db` because it awaits _resolve_user_position/_resolve_user_dept
for the initiator role/department — matching the original inline awaits.
"""
from datetime import date

from app.models.purchase import Purchase
from app.services.documents.doc_types import _BASIS_LABELS, _PURCHASE_METHOD_LABELS
from app.services.documents.formatting import (
    _fmt_date, _clean_id, _fmt_money, _fmt_money_plain, _rubles_to_words, _signatory_position,
)
from app.services.documents.templates import _purchase_method_label
from app.services.documents.contexts import (
    _build_acceptance_doc_context,
    _resolve_user_position,
    _resolve_user_dept,
    _format_service_term,
)
from app.services.documents.morphology import _inflect_phrase_genitive
from app.services.documents.stages_amounts import resolve_vat_exemption_article


def build_base_context_part1(
    p: Purchase, subsidy, c, doc_indices, doc_type,
    feo_path, feo_level_1, feo_level_2, feo_level_3,
    resolved_responsible, resolved_responsible_full,
    items_list, item_categories_str,
    amounts: dict,
) -> dict:
    items_sum_val = amounts["items_sum_val"]
    doc_amount_val = amounts["doc_amount_val"]

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
    }
    return context


async def build_base_context_part2(
    context: dict, p: Purchase, subsidy, db,
    approvers_list, initiator, event,
    cd_day, cd_month, cd_year,
    c, subject_kind,
    amounts: dict,
) -> None:
    """Extends `context` in place with the rest of the original dict literal."""
    doc_amount_val = amounts["doc_amount_val"]
    vat_app = amounts["vat_app"]
    vat_rate_val = amounts["vat_rate_val"]
    vat_amount_val = amounts["vat_amount_val"]
    vat_info_line = amounts["vat_info_line"]
    amount_is_planned = amounts["amount_is_planned"]
    is_advance = amounts["is_advance"]
    # Preserved-bug call site — see stages_amounts.resolve_vat_exemption_article()
    # docstring: raises UnboundLocalError('art') when vat_app=False and
    # is_advance=True, exactly like the original inline ternary did.
    art = resolve_vat_exemption_article(p, vat_app, is_advance)

    context.update({
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
    })
