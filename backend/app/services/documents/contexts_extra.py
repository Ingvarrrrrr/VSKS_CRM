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
from app.services.documents.formatting import (
    _fmt_date, _clean_id, _fio_to_initials_prefix, _signatory_position,
    _normalize_signatory_position, _extract_city_from_address,
)
from app.services.documents.morphology import (
    _to_gen_fio, _to_gen_phrase, _inflect_phrase_genitive,
    _to_dat_fio, _to_dat_fio_initials, _to_dat_position,
)
from app.services.documents.contexts import _signatory_split
from app.services.documents.contract_terms import warranty_period_text
from app.services.contractor_pii import contractor_pii_doc_fields
from app.services.documents.contexts_org_people import (
    responsible_case_context, _to_gen_org_name, _to_dat_org_name,
)

logger = logging.getLogger(__name__)


def add_phase28_context(context: dict, subsidy, c, p: Purchase, can_view_pii: bool = True) -> None:
    """Phase 28: расширенные ключи для типовых договоров.

    `can_view_pii` (владелец, 2026-10-08): без права на раздел «Договоры»
    паспорт/СНИЛС/адрес регистрации/дату рождения контрагента-физлица сюда
    не кладём — см. app.services.contractor_pii.contractor_pii_doc_fields
    (ПРАВИЛО №6, единственный расчёт этих ключей, тот же вызывается из
    fabrikant_package.py). Документ всё равно формируется, просто с
    пустыми этими полями.

    Все ключи NULL-safe (пустая строка / ноль / пустой список при отсутствии
    данных). Любая ошибка здесь ТОЛЬКО логируется — не должна ронять генерацию
    документа (см. оригинальный try/except).
    """
    try:
        # Реквизиты субсидии-грантодателя (для рамочных и региональных договоров)
        # Phase 28: grantor_name / ministry_name берём из новых полей модели Subsidy
        context["subsidy_grantor_name"] = (subsidy.grantor_name or "").strip() if subsidy else ""
        context["subsidy_ministry_name"] = (subsidy.ministry_name or "").strip() if subsidy else ""
        # subsidy_agreement_number/date — см. add_subsidy_agreement_context
        # (ПРАВИЛО №6, вызывается из add_misc_purchase_context ниже по generate.py).

        # Реквизиты физ.лица (ГПХ) — читаем из контрагента, с PII-гейтом
        context.update(contractor_pii_doc_fields(c, can_view_pii, _fmt_date))

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
        # Владелец (жалоба п.10, 2026-09-17): единица измерения (дни/месяцы/годы) +
        # человекочитаемый текст «1 год»/«12 месяцев»/«30 дней» для новых шаблонов —
        # единственный расчёт в contract_terms.warranty_period_text (ПРАВИЛО №6).
        context["warranty_period_text"]        = warranty_period_text(
            context["warranty_period_days"], getattr(p, "warranty_period_unit", None)
        )
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
    # responsible_name_gen/_dat + сокращённые инициалы — единственный расчёт
    # (ПРАВИЛО №6), см. contexts_org_people.responsible_case_context — тот же
    # вызывается из fabrikant_package.py, второй копии не заводим.
    context.update(responsible_case_context(resolved_responsible))
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
        # Владелец (16.10.2026): {{customer_name}} убран — единственные ключи
        # краткого/полного названия Заказчика — customer_short_name и
        # customer_full_name, строго по своему полю карточки, БЕЗ фолбэка
        # одного на другое (пусто — значит пусто в карточке).
        # customer_full_name — ТОЛЬКО поле «Полное наименование» (org_requisites,
        # контрагент — источник истины при org.contractor_id).
        "customer_full_name":    _cust_req.get('full_name') or "",
        # customer_short_name — ТОЛЬКО поле «Краткое наименование»: organizations.name
        # (column_property, читает Contractor.name напрямую — app/models/
        # organization.py) либо, если org не передана — contractor.name.
        "customer_short_name":   _g(customer_org.name if customer_org else None,
                                    customer_ctr.name if customer_ctr else None),
        # Падежи названия Заказчика (владелец, 20.10.2026) — единственный
        # разбор _to_case_position, см. contexts_org_people._to_case_org_name.
        "customer_full_name_genitive":  _to_gen_org_name(_cust_req.get('full_name') or ""),
        "customer_full_name_dative":    _to_dat_org_name(_cust_req.get('full_name') or ""),
        "customer_short_name_genitive": _to_gen_org_name(_g(customer_org.name if customer_org else None,
                                                             customer_ctr.name if customer_ctr else None)),
        "customer_short_name_dative":   _to_dat_org_name(_g(customer_org.name if customer_org else None,
                                                             customer_ctr.name if customer_ctr else None)),
        "customer_address":      _g(_cust_req.get('address')),
        # Город из юридического адреса (владелец, 20.10.2026) — см.
        # formatting._extract_city_from_address. НЕ contract_city (ниже) —
        # разные показатели, contract_city не трогаем.
        "customer_city":         _extract_city_from_address(_cust_req.get('address') or ""),
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
        "customer_signatory_position_genitive": _to_gen_phrase(cust_sig["position"]),
        # Дательный падеж (владелец, 15.10.2026: «Председателю Совета…
        # Артеевой Анне Игоревне») — тот же единственный расчёт склонения
        # (ПРАВИЛО №6), см. morphology._to_dat_position/_to_dat_fio/_to_dat_fio_initials.
        "customer_signatory_position_dative":   _to_dat_position(cust_sig["position"]),
        "customer_signatory_name_dative":       _to_dat_fio(cust_sig["name_full"]),
        "customer_signatory_initials_dative":   _to_dat_fio_initials(cust_sig["name_full"]),
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


def add_subsidy_agreement_context(context: dict, subsidy) -> None:
    """Номер и дата соглашения о субсидии — единственный расчёт (ПРАВИЛО №6),
    вызывается из add_misc_purchase_context (основная генерация) и
    fabrikant_package.py, вторую копию не заводить.

    Владелец (14.10.2026): в карточке субсидии вводится только
    Subsidy.basis_doc_number/basis_doc_date («Номер документа-основания») —
    отдельного поля для номера/даты соглашения в UI нет. Subsidy.agreement_number
    остаётся как устаревший fallback (поля ввода для него нет, но колонка
    в БД может быть заполнена старыми данными/импортом).
    """
    context["subsidy_agreement_number"] = (
        (subsidy.basis_doc_number or subsidy.agreement_number or "") if subsidy else ""
    )
    context["subsidy_agreement_date"] = (
        _fmt_date(subsidy.basis_doc_date) if (subsidy and subsidy.basis_doc_date) else ""
    )
    context["procurement_regulation_date"] = (
        _fmt_date(subsidy.procurement_regulation_date)
        if (subsidy and getattr(subsidy, 'procurement_regulation_date', None)) else ""
    )


def add_misc_purchase_context(context: dict, p: Purchase, subsidy) -> None:
    # subsidy_agreement_number/date — см. add_subsidy_agreement_context выше.
    add_subsidy_agreement_context(context, subsidy)

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


def add_prepayment_context(context: dict, p: Purchase) -> None:
    """Владелец (05.10.2026, план «Шаблоны договоров», п.3): признак и дата
    предоплаты — пункт об оплате печатает вариант с суммой аванса (уже есть
    в контексте как advance_amount, см. add_phase28_context выше) при
    is_prepayment=True, иначе вариант со сроком оплаты (payment_term_days,
    см. add_misc_purchase_context). ПРАВИЛО №6: один расчёт — вызывается из
    generate.py и fabrikant_package.py, не копируется вторым литералом.
    """
    context["is_prepayment"] = bool(getattr(p, "is_prepayment", False))
    context["prepayment_date"] = _fmt_date(p.prepayment_date) if getattr(p, "prepayment_date", None) else ""


def _day_count_to_words(n) -> str:
    """int/numeric-строка дней → числительное словами ("7" → "семь").
    Пусто/None/не число → "". Переиспользует formatting._chunk_to_words —
    второй механизм прописи чисел не заводим (ПРАВИЛО №6)."""
    if n is None or n == "":
        return ""
    try:
        from app.services.documents.formatting import _chunk_to_words
        return _chunk_to_words(int(n))
    except (TypeError, ValueError):
        return ""


def add_day_words_context(context: dict, p: Purchase) -> None:
    """Владелец (05.10.2026, живая генерация договора): шаблоны печатают срок
    цифрой и цифрой же в скобках — «в течение {{ payment_term_days }}
    ({{ payment_term_days }}) рабочих дней» — вместо прописи между ними.
    Нашли grep'ом по backend/templates/*.docx (word/document.xml,
    `\\{\\{ x \\}\\} \\(\\{\\{ x \\}\\}\\)`): payment_term_days (contract_services,
    contract_services_food, contract_repair_framework, contract_goods_single),
    service_term_days и acceptance_term_days (contract_goods_single).
    ПРАВИЛО №6: один расчёт — вызывается из generate.py и fabrikant_package.py.

    Дефект (05.10.2026): acceptance_term_days/payment_term_days печатаются
    цифрой с умолчанием (5 / 10 при None — см. add_phase28_context и
    add_misc_purchase_context выше), а пропись считалась от сырого p.* (None
    → ""). Пропись ДОЛЖНА совпадать с тем, что уже напечатано цифрой — читаем
    из context[...] (эта функция вызывается ПОСЛЕ add_phase28_context /
    add_misc_purchase_context / build_base_context_part2 — там эти ключи уже
    положены в контекст с тем же умолчанием), не из p напрямую.
    """
    context["payment_term_days_words"] = _day_count_to_words(context.get("payment_term_days"))
    context["service_term_days_words"] = _day_count_to_words(context.get("service_term_days"))
    context["acceptance_term_days_words"] = _day_count_to_words(context.get("acceptance_term_days"))


def contractor_org_type_for_docs(c) -> str:
    """Тип контрагента для шаблонов (ОГРН/ОГРНИП, преамбула «в лице ИП…»).

    Владелец (05.10.2026): в локальной БД у большинства контрагентов
    org_type пустой — ИП с пустым org_type печатался как юрлицо (ОГРН
    вместо ОГРНИП). ПРАВИЛО №6: единственный расчёт, вызывается из
    contexts_build.py (build_base_context_part2) и fabrikant_package.py —
    раньше там было по копии `(c.org_type or "") if c else ""`.

    Непустой org_type — как есть (strip). Пустой + ИНН из 12 цифр — 'ИП'
    (10 цифр — ИНН юрлица, 12 — ИП/физлицо). Иначе пустой — "" (как раньше,
    например пустой org_type + пустой ИНН). 'Самозанятый' не трогаем — это
    непустой org_type, возвращается как есть.
    """
    if not c:
        return ""
    org_type = (c.org_type or "").strip()
    if org_type:
        return org_type
    inn_digits = _re_dept.sub(r"\D", "", c.inn or "")
    if len(inn_digits) == 12:
        return "ИП"
    return ""


def add_contractor_signatory_context(context: dict, c) -> None:
    # Phase 23: расширенные поля подписанта Исполнителя (name_genitive, initials, ogrnip)
    ctr_sig = _signatory_split(
        c.signatory if c else "",
        last=getattr(c, 'signatory_last_name', None) if c else None,
        first=getattr(c, 'signatory_first_name', None) if c else None,
        middle=getattr(c, 'signatory_middle_name', None) if c else None,
        position=getattr(c, 'signatory_position', None) if c else None,
    )
    # Владелец (14.10.2026): должность подписанта Исполнителя — из заполненного
    # Contractor.signatory_position, если есть; угадывание по строке signatory
    # (_signatory_position, по умолчанию «Директор») — только фолбэк, когда
    # поле не заполнено. Раньше угадывание побеждало всегда даже при
    # заполненном signatory_position (contexts_build.py/fabrikant_package.py —
    # обе копии читали только эвристику).
    _ctr_signatory_position = _normalize_signatory_position(
        getattr(c, 'signatory_position', None) or _signatory_position(c.signatory) if c else ""
    )
    context.update({
        "contractor_signatory_name":          ctr_sig["name_full"],
        "contractor_signatory_name_genitive": ctr_sig["name_genitive"],
        "contractor_signatory_initials":      ctr_sig["name_initials"],
        # Инициалы впереди: «П.П. Сидоров» — тот же приём, что и для Заказчика
        # (customer_signatory_name_initials), см. add_customer_context выше.
        "contractor_signatory_name_initials": _fio_to_initials_prefix(ctr_sig["name_full"]),
        "contractor_signatory_position":          _ctr_signatory_position,
        "contractor_signatory_position_genitive": _to_gen_phrase(_ctr_signatory_position),
        # Дательный падеж — см. комментарий у customer_signatory_*_dative выше
        # (ПРАВИЛО №6, тот же единственный расчёт склонения).
        "contractor_signatory_position_dative":   _to_dat_position(_ctr_signatory_position),
        "contractor_signatory_name_dative":       _to_dat_fio(ctr_sig["name_full"]),
        "contractor_signatory_initials_dative":   _to_dat_fio_initials(ctr_sig["name_full"]),
        "contractor_ogrnip":                  (c.ogrn or "") if (c and (c.org_type or "").lower().startswith("ип")) else "",
        # Владелец (16.10.2026): полное наименование — ТОЛЬКО поле «Полное
        # наименование» контрагента, без фолбэка на краткое (contractor_name
        # убран — он дублировал contractor_short_name).
        "contractor_full_name":               (c.full_name or "") if c else "",
    })
