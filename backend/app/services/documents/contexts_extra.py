"""generate_document: остальные ключи контекста после основного context={...}
литерала — Phase 28 расширенные поля, родительный падеж, Заказчик
(org_requisites), Fabrikant-ключи, прочие поля закупки, расширенный
подписант Исполнителя.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
Each function mutates `context` in place, in the same order the original
inline code ran, including the original's own exception handling where
present (Phase 28 block swallows all exceptions and only logs a warning —
preserved here unchanged).
"""
import logging
import re as _re_dept

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.services.documents.formatting import _fmt_date, _clean_id, _fio_to_initials_prefix
from app.services.documents.morphology import _to_gen_fio, _to_gen_phrase, _inflect_phrase_genitive
from app.services.documents.contexts import _signatory_split

logger = logging.getLogger(__name__)


def add_phase28_context(context: dict, subsidy, c, p: Purchase) -> None:
    """Phase 28: расширенные ключи для типовых договоров.

    Все ключи NULL-safe (пустая строка / ноль / пустой список при отсутствии
    данных). Любая ошибка здесь ТОЛЬКО логируется — не должна ронять генерацию
    документа (см. оригинальный try/except).
    """
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
        from app.services.documents.formatting import _fmt_money
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
        logging.getLogger(__name__).warning("Phase 28 context keys failed: %s", _e28)


def add_genitive_forms(context: dict, p: Purchase, resolved_responsible: str) -> None:
    # Phase 26-V: родительный падеж для инициатора и ответственного
    context["initiator_name_gen"] = _to_gen_fio(context.get("initiator_name", ""))
    context["initiator_position_gen"] = _to_gen_phrase(context.get("initiator_role", ""))
    context["responsible_name_gen"] = _to_gen_fio(resolved_responsible)
    context["responsible_position_gen"] = _to_gen_phrase(p.responsible_position or "" if hasattr(p, "responsible_position") else "")

    # Phase 27.2-10: дедуп тавтологии "отдел Отдела ..." + gent для отдела
    # Если в должности уже есть корень "отдел*" — убираем leading "Отдел*" из имени отдела.
    # Пример: «Заместитель начальника отдела» + «Отдела МТО» → «МТО».
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


def add_customer_context(context: dict, customer_org, customer_ctr) -> None:
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


async def add_fabrikant_context(context: dict, db: AsyncSession, p: Purchase) -> None:
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


def add_misc_purchase_context(context: dict, p: Purchase, subsidy) -> None:
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


def add_contractor_signatory_context(context: dict, c) -> None:
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
