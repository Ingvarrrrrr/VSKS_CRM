# -*- coding: utf-8 -*-
"""Phase 28 T5: приёмочные тесты шаблонов договоров.

48 кейсов (8 шаблонов × 6 комбо флагов).
Offline, синхронные, без БД и сети.

Логика перенесена из .tmp_p28_strict.py.
"""
import os
import re
import tempfile

import docx
import pytest
from docxtpl import DocxTemplate

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(__file__)
_TEMPLATES_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "templates"))

DOC_TYPES = [
    "contract_services_large",
    "contract_services_small",
    "contract_services_food",
    "contract_goods_single",
    "contract_gph_individual",
    "contract_gph_individual_rid",
    "contract_repair_vehicle",
    "contract_repair_framework",
]

COMBOS = [
    ("НДС20/ЮЛ",  {"vat_rate": 20, "vat_applicable": True,  "contractor_org_type": "ЮЛ"}),
    ("НДС5/ИП",   {"vat_rate": 5,  "vat_applicable": True,  "contractor_org_type": "ИП"}),
    ("безНДС/ИП", {"vat_rate": 0,  "vat_applicable": False, "contractor_org_type": "ИП"}),
    ("без3лиц",   {"third_party_involved": False}),
    ("ретро",     {"is_retroactive": True}),
    ("самовывоз", {"delivery_by_supplier": False, "has_stages": False}),
]

# ---------------------------------------------------------------------------
# Базовый контекст — все строковые значения заменены на уникальные сентинелы
# вида «КЛЮЧ». Это гарантирует, что проверка ловит реальные подстановки,
# а не совпадение с зашитой статикой в шаблоне.
# Сентинелы НЕ содержат < > & — иначе docxtpl портит XML.
# ---------------------------------------------------------------------------

_BASE_STRINGS = {
    "customer_inn": "customer_inn",
    "customer_kpp": "customer_kpp",
    "customer_ogrn": "customer_ogrn",
    "customer_full_name": "customer_full_name",
    "customer_short_name": "customer_short_name",
    "customer_address": "customer_address",
    "customer_bank_name": "customer_bank_name",
    "customer_settlement_account": "customer_settlement_account",
    "customer_correspondent_account": "customer_correspondent_account",
    "customer_bik": "customer_bik",
    "customer_personal_account": "customer_personal_account",
    "customer_signatory_position": "customer_signatory_position",
    "customer_signatory_initials": "customer_signatory_initials",
    "customer_signatory_name_initials": "customer_signatory_name_initials",
    "customer_signatory_name": "customer_signatory_name",
    "customer_signatory_basis": "customer_signatory_basis",
    "customer_email": "customer_email",
    "contract_number": "contract_number",
    "contract_date_day": "contract_date_day",
    "contract_date_month": "contract_date_month",
    "contract_date_year": "contract_date_year",
    "contract_city": "contract_city",
    "contractor_full_name": "contractor_full_name",
    "contractor_short_name": "contractor_short_name",
    "contractor_signatory_name": "contractor_signatory_name",
    "contractor_signatory_position": "contractor_signatory_position",
    "contractor_signatory_basis": "contractor_signatory_basis",
    "contractor_signatory_position_genitive": "contractor_signatory_position_genitive",
    "contractor_signatory_name_genitive": "contractor_signatory_name_genitive",
    "contractor_signatory_line": "contractor_signatory_line",
    "contractor_signatory_name_initials": "contractor_signatory_name_initials",
    "contractor_ogrnip": "contractor_ogrnip",
    "contractor_org_type": "contractor_org_type",
    "contractor_inn": "contractor_inn",
    "contractor_kpp": "contractor_kpp",
    "contractor_ogrn": "contractor_ogrn",
    "contractor_address": "contractor_address",
    "service_subject": "service_subject",
    "service_start_date": "service_start_date",
    "service_end_date": "service_end_date",
    "service_deadline_date": "service_deadline_date",
    "service_term": "service_term",
    "delivery_location": "delivery_location",
    "contract_price_num": "contract_price_num",
    "contract_price_words": "contract_price_words",
    "vat_exemption_article": "vat_exemption_article",
    "penalty_rate": "penalty_rate",
    "service_name": "service_name",
    "subsidy_agreement_text": "subsidy_agreement_text",
    "subsidy_agreement_number": "subsidy_agreement_number",
    "subsidy_agreement_date": "subsidy_agreement_date",
    "subsidy_grantor_name": "subsidy_grantor_name",
    "subsidy_ministry_name": "subsidy_ministry_name",
    "subsidy_extra_clause_1": "subsidy_extra_clause_1",
    "subsidy_extra_clause_2": "subsidy_extra_clause_2",
    "repair_request_number": "repair_request_number",
    "vehicle_body_number": "vehicle_body_number",
    "today": "today",
    "delivery_date": "delivery_date",
    "subject": "subject",
    "subject_kind": "subject_kind",
    "submission_deadline_datetime": "submission_deadline_datetime",
    "vat_amount_num": "vat_amount_num",
    "vat_amount_words": "vat_amount_words",
    "customer_postal_address": "customer_postal_address",
    "customer_phone": "customer_phone",
    "contractor_bank_name": "contractor_bank_name",
    "contractor_settlement_account": "contractor_settlement_account",
    "contractor_correspondent_account": "contractor_correspondent_account",
    "contractor_phone": "contractor_phone",
    "contractor_email": "contractor_email",
    "contractor_signatory_initials": "contractor_signatory_initials",
}

_ITEMS = [
    {
        "num": i,
        "name": "ПОЗИЦИЯ-СЕНТИНЕЛ-%d" % i,
        "quantity": i,
        "unit": "шт",
        "unit_price": "100,00",
        "total": "%d00,00" % i,
        "total_numeric": i * 100.0,
        "code": "КОД%d" % i,
        "norm_hours": "1,5",
    }
    for i in (1, 2, 3)
]


def _make_ctx(**override):
    """Собрать контекст со сентинелами, поверх применить override."""
    ctx = {}
    for k, v in _BASE_STRINGS.items():
        ctx[k] = "«%s»" % k.upper()[:26]
    # Нечисловые дефолты
    ctx.update(
        vat_applicable=True,
        third_party_involved=True,
        is_retroactive=False,
        vat_rate=20,
        warranty_period_days=15,
        acceptance_term_days=5,
        payment_term_days=10,
        service_term_days=30,
        items=_ITEMS,
        contract_items=_ITEMS,
        item={},
        contractor_org_type="ЮЛ",
        has_stages=True,
        delivery_by_supplier=True,
        commission_members=[],
    )
    ctx.update(override)
    return ctx


# ---------------------------------------------------------------------------
# Утилита рендера → plain text
# ---------------------------------------------------------------------------

def _render_text(template_path: str, ctx: dict) -> str:
    t = DocxTemplate(template_path)
    t.render(ctx)
    fd = tempfile.mktemp(suffix=".docx")
    t.save(fd)
    try:
        d = docx.Document(fd)
        parts = [p.text for p in d.paragraphs]
        for tb in d.tables:
            for row in tb.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts)
    finally:
        try:
            os.remove(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Словари для проверок
# ---------------------------------------------------------------------------

# Зашитые реквизиты ВСКС — не должны встречаться в тексте при сентинел-контексте
STATIC_FORBIDDEN = {
    "ИНН ВСКС": "7731178803",
    "ОГРН ВСКС": "1037739198672",
    "КПП ВСКС": "772901001",
    "Козеев": "Козеев",
    "Росмолодёжь-статик": "Федеральным агентством по делам молодежи",
    "№ соглашения 091": "091-10-2025-032",
    "№ соглашения МТ 149": "149-10-2025-043",
    "ВСКС-полное": "Всероссийский студенческий корпус спасателей",
}

_SERVICES = frozenset(
    ("contract_services_large", "contract_services_small", "contract_services_food")
)
_GPH = frozenset(("contract_gph_individual", "contract_gph_individual_rid"))

_R5_STAGE_MARKERS = [
    "В случае наличия этапов оказания Услуг",
    "или этапа оказания Услуг",
    "в т.ч. этапа оказания Услуг",
]

# Нерешённые альтернативы — всегда дефект
_UNRESOLVED_ALT = [
    "без привлечения третьих лиц / Услуги",
    "копеек) / в том числе НДС",
    "(включительно) / с момента заключения",
    "г. / в течение",
]


# ---------------------------------------------------------------------------
# Детекторы дефектов
# ---------------------------------------------------------------------------

def _text_defects(txt: str) -> list[str]:
    """Возвращает список описаний найденных дефектов текста."""
    errors = []

    def _snippets(pattern, label):
        found = re.findall(pattern, txt)
        if found:
            sample = found[0]
            errors.append(f"{label} — фрагмент: {' '.join(sample.split())[:120]!r}")

    _snippets(r".{40}\\g<\d+>.{20}", r"литерал \g<N> (regex не раскрыт)")
    _snippets(r".{50}«»", "пустая подстановка «»")
    _snippets(r".{0,40}№\s{1,}(?:от|г\.|\n|$).{0,20}", "«№» без значения")
    _snippets(r".{30}\b(?:в в|с с|по по|на на)\b.{30}", "двойной предлог")
    _snippets(r".{45}\(\s*\)", "пустые скобки ()")
    _snippets(r".{40}%%", "двойной %%")
    _snippets(r".{30}\{[\{%].{30}", "остаток Jinja {{ / {%")
    _snippets(r".{30}»«.{30}", "склейка маркеров »«")

    return errors


def _static_defects(txt: str) -> list[str]:
    errors = []
    for label, value in STATIC_FORBIDDEN.items():
        if value in txt:
            errors.append(f"зашитая статика {label!r}: {value!r} найдена в тексте")
    return errors


def _branch_defects(doc_name: str, ctx: dict, txt: str) -> list[str]:
    errors = []

    def must_have(s, rule):
        if s not in txt:
            errors.append(f"{rule}: ОТСУТСТВУЕТ обязательное «{s}»")

    def must_not(s, rule):
        if s in txt:
            errors.append(f"{rule}: ПРИСУТСТВУЕТ запрещённое «{s}»")

    # R2 — третьи лица (только договоры услуг)
    if doc_name in _SERVICES:
        if ctx.get("third_party_involved") is False:
            must_have("без привлечения третьих лиц", "R2-без3лиц")
            must_not("или с привлечением третьих лиц", "R2-без3лиц")
        else:
            must_have("или с привлечением третьих лиц", "R2-с3лиц")

    # R1 — НДС-ставка
    if ctx.get("vat_applicable") and ctx.get("vat_rate") == 20:
        must_not("НДС – 5%", "R1-НДС20")
        must_not("НДС 5%", "R1-НДС20")
    if ctx.get("vat_applicable") and ctx.get("vat_rate") == 5:
        must_not("НДС – 20%", "R1-НДС5")
        must_not("НДС 20%", "R1-НДС5")
    if not ctx.get("vat_applicable"):
        must_not("НДС – 20%", "R1-безНДС")
        must_not("НДС 20%", "R1-безНДС")
        must_not("НДС – 5%", "R1-безНДС")

    # R4 — доставка / самовывоз (только поставка товара)
    if doc_name == "contract_goods_single":
        if ctx.get("delivery_by_supplier") is False:
            must_have("выборки по месту нахождения Поставщика", "R4-самовывоз")
            must_not("Доставка товара осуществляется силами Поставщика", "R4-самовывоз")
        else:
            must_have("Доставка товара осуществляется силами Поставщика", "R4-доставка")
            must_not("выборки по месту нахождения Поставщика", "R4-доставка")

    # R6 — ретроактивность ст.425 (только услуги)
    if doc_name in _SERVICES:
        if ctx.get("is_retroactive") is False:
            must_not("425", "R6-не-ретро")
        else:
            must_have("425", "R6-ретро")

    # T4 — позиции сметы ремонта разворачиваются в таблицу
    if doc_name == "contract_repair_framework":
        must_have("ПОЗИЦИЯ-СЕНТИНЕЛ-1", "T4-смета-1")
        must_have("ПОЗИЦИЯ-СЕНТИНЕЛ-3", "T4-смета-3")

    # Устаревшая ставка НДС 18% — запрещена везде
    must_not("НДС, 18%", "устарел-НДС18")
    must_not("НДС 18%", "устарел-НДС18")
    must_not("НДС – 18%", "устарел-НДС18")

    # R5 — этапность ГПХ
    if doc_name in _GPH:
        if ctx.get("has_stages") is False:
            for marker in _R5_STAGE_MARKERS:
                must_not(marker, "R5-без-этапов")
        else:
            for marker in _R5_STAGE_MARKERS:
                must_have(marker, "R5-с-этапами")

    # Нерешённые альтернативы «/»
    for alt in _UNRESOLVED_ALT:
        if alt in txt:
            errors.append(f"нерешённая альтернатива через «/»: «{alt}»")

    return errors


# ---------------------------------------------------------------------------
# Параметризация
# ---------------------------------------------------------------------------

_PARAMS = [
    pytest.param(doc_type, combo_label, combo_override, id=f"{doc_type}::{combo_label}")
    for doc_type in DOC_TYPES
    for combo_label, combo_override in COMBOS
]


@pytest.mark.parametrize("doc_type,combo_label,combo_override", _PARAMS)
def test_contract_template(doc_type: str, combo_label: str, combo_override: dict):
    """Рендер шаблона с сентинел-контекстом + набор проверок качества.

    При падении сообщение показывает шаблон, комбо и конкретный дефект.
    """
    template_path = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    assert os.path.isfile(template_path), (
        f"Шаблон не найден: {template_path}"
    )

    ctx = _make_ctx(**combo_override)

    try:
        txt = _render_text(template_path, ctx)
    except Exception as exc:
        pytest.fail(
            f"[{doc_type} / {combo_label}] Рендер упал: {type(exc).__name__}: {exc}"
        )

    all_errors: list[str] = []
    all_errors.extend(_static_defects(txt))
    all_errors.extend(_text_defects(txt))
    all_errors.extend(_branch_defects(doc_type, ctx, txt))

    if all_errors:
        report = "\n".join(f"  • {e}" for e in all_errors)
        pytest.fail(
            f"[{doc_type} / {combo_label}] {len(all_errors)} дефект(а):\n{report}"
        )
