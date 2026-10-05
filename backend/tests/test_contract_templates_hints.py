# -*- coding: utf-8 -*-
"""Quick-задача 2026-10-05: «Шаблоны договоров — подсказки, выдуманные
примеры, реквизиты исполнителя, оплата». Offline, без БД и сети.

Проверяет (ревью 2026-10-05 расширило список до 19 файлов):
  (а) ни в одном рабочем шаблоне (7 форм договора + order_purchase +
      contract.docx + contract_tz.docx + tech_spec_request/contract +
      5 служебных записок + 2 методички) нет литералов ВСКС/реальных
      реквизитов (ИНН, ОГРН, казначейский счёт, ОКПО, БИК/к/с Сбербанка,
      адрес, телефон, Козеев);
  (а2) та же проверка — для ТЕКСТОВ самих подсказок (word/comments.xml),
      не только document.xml;
  (б) у каждого тега {{ }}/{% %} в document.xml есть Word-комментарий —
      для 7 форм + order_purchase (build.py) и для файлов вне сборки
      (build/patch_offbuild.py::attach_hints, тот же comments_ru.py);
  (в) рендер docxtpl на выдуманном контексте при is_prepayment True/False
      печатает РОВНО один пункт оплаты, реквизиты исполнителя (ИНН
      ООО «Ромашка») попадают в текст.

Не запускает backend/templates/build/build.py — проверяет уже собранные
файлы в backend/templates/ (как они лежат в репозитории после --install).
"""
import os
import re
import sys
import tempfile
import types
import zipfile

import docx
import pytest
from docxtpl import DocxTemplate

_THIS_DIR = os.path.dirname(__file__)
_TEMPLATES_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "templates"))
_BACKEND_DIR = os.path.normpath(os.path.join(_THIS_DIR, ".."))


def _ensure_backend_package_importable() -> None:
    """build/*.py всегда импортируют друг друга как `backend.templates.
    build.X` (абсолютный путь от корня репо — так же работает сам
    build.py, вставляющий REPO_ROOT в sys.path). Локально (py запущен из
    корня репо) это резолвится само; в контейнере backend_b рабочая папка
    /app УЖЕ ЕСТЬ содержимое backend/ (никакой папки `backend` на диске
    нет вовсе) — импорт `backend.templates...` падает с ModuleNotFoundError.
    Регистрируем `backend` как namespace-пакет, чьё __path__ указывает на
    текущую backend-директорию (локально — .../backend, в контейнере —
    /app) — тогда `backend.templates.build.rules_comments` резолвится
    одинаково в обоих окружениях без правок самого build/*.py."""
    if "backend" in sys.modules:
        return
    pkg = types.ModuleType("backend")
    pkg.__path__ = [_BACKEND_DIR]
    sys.modules["backend"] = pkg

# Семь форм договора + приказ — к ним подключены комментарии Word
# (см. backend/templates/build/build.py::_COMMENT_DOC_TYPES).
COMMENTED_FILES = [
    "contract_services.docx",
    "contract_services_food.docx",
    "contract_goods_single.docx",
    "contract_gph_individual.docx",
    "contract_gph_individual_rid.docx",
    "contract_repair_vehicle.docx",
    "contract_repair_framework.docx",
    "order_purchase.docx",
    # Ревью 2026-10-05: contract.docx/contract_tz.docx/tech_spec_* — живые
    # doc_type (doc_types.py), а не черновики — подсказки навешиваются
    # build/patch_offbuild.py::attach_hints тем же comments_ru.py. То же
    # самое для 5 служебных записок (SERVICE_NOTE_FILES ниже).
    "contract.docx",
    "contract_tz.docx",
    "tech_spec_request.docx",
    "tech_spec_contract.docx",
]

SERVICE_NOTE_FILES = [
    "service_note.docx",
    "service_note_advance.docx",
    "service_note_delivery.docx",
    "service_note_payment.docx",
    "service_note_procurement.docx",
]

COMMENTED_FILES = COMMENTED_FILES + SERVICE_NOTE_FILES

# Методички приклеиваются к готовому договору «как есть» (docxcompose, без
# Jinja) — подсказок к тегам там нет (в них и тегов нет), но текст внутри
# должен быть нейтрализован (build/rules_methodology.py).
METHODOLOGY_FILES = ["methodology_large.docx", "methodology_small.docx"]

ALL_WORKING_FILES = COMMENTED_FILES + METHODOLOGY_FILES

# Реальные данные ВСКС — ни в одном рабочем шаблоне их не должно быть
# (владелец 05.10.2026: «в шаблонах выдуманные организации, ФИО и контакты»).
# 17777419 — реальный ОКПО ВСКС; 81054537000 — подстрока реального ЕКС
# 40102810545370000003 (уже входит отдельной строкой, добавлена явно по
# ревью); 044525225/30101810400000000225 — реальный БИК и к/с Сбербанка,
# используемые раньше как «выдуманный» пример в подсказках (исправлено).
FORBIDDEN_LITERALS = [
    "ВСКС",
    "Всероссийск",
    "7731178803",
    "7704190720",
    "40102810545370000003",
    "40703810138060100002",
    "568-00-11",
    "17777419",
    "81054537000",
    "044525225",
    "30101810400000000225",
    "Вернадского",
    "Козеев",
]

_TAG_RE = re.compile(r"\{\{.*?\}\}|\{%-?.*?-?%\}")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document_xml_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


# ---------------------------------------------------------------------------
# (а) нет литералов ВСКС
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", ALL_WORKING_FILES)
def test_no_vsks_literals(filename):
    path = os.path.join(_TEMPLATES_DIR, filename)
    assert os.path.exists(path), f"{filename} отсутствует в {_TEMPLATES_DIR}"
    text = _document_xml_text(path)
    found = [lit for lit in FORBIDDEN_LITERALS if lit in text]
    assert not found, f"{filename}: найдены реальные данные ВСКС: {found}"


# ---------------------------------------------------------------------------
# (а2) тексты подсказок (word/comments.xml) — тоже без реальных данных
# (ревью 2026-10-05: БИК/к/с Сбербанка были «выдуманным» примером в тексте
# самой подсказки — document.xml чист, а подсказка внутри Word-комментария
# содержала реальные реквизиты).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", COMMENTED_FILES)
def test_comment_hints_no_vsks_literals(filename):
    path = os.path.join(_TEMPLATES_DIR, filename)
    assert os.path.exists(path), f"{filename} отсутствует в {_TEMPLATES_DIR}"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "word/comments.xml" not in names:
            pytest.skip(f"{filename}: нет word/comments.xml")
        xml = z.read("word/comments.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml)
    found = [lit for lit in FORBIDDEN_LITERALS if lit in text]
    assert not found, f"{filename}: в текстах подсказок (comments.xml) найдены реальные данные ВСКС: {found}"


# ---------------------------------------------------------------------------
# (б) у каждого тега есть Word-комментарий
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", COMMENTED_FILES)
def test_every_tag_has_comment(filename):
    """Источник истины для «есть ли у тега подсказка» — сама функция
    rules_comments.apply_comments() (ПРАВИЛО №6: не пересчитывать
    покрытие regex'ом по сырому XML второй раз, спросить у реального
    механизма сборки, который build.py уже гоняет на --install)."""
    import docx as docx_module
    _ensure_backend_package_importable()
    from backend.templates.build import rules_comments

    path = os.path.join(_TEMPLATES_DIR, filename)
    assert os.path.exists(path), f"{filename} отсутствует в {_TEMPLATES_DIR}"

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    assert "word/comments.xml" in names, (
        f"{filename}: нет word/comments.xml — комментарии не подключены"
    )

    doc = docx_module.Document(path)
    _n_comments, uncovered = rules_comments.apply_comments(doc)

    assert not uncovered, (
        f"{filename}: теги без подсказки (Word-комментария) в comments_ru.py: {uncovered}"
    )


# ---------------------------------------------------------------------------
# (в) рендер на выдуманном контексте — предоплата/постоплата, реквизиты
# ---------------------------------------------------------------------------

_ITEMS = [
    {
        "num": 1, "name": "Позиция 1", "quantity": 1, "unit": "шт",
        "unit_price": "100,00", "total": "100,00", "total_numeric": 100.0,
        "code": "К1", "norm_hours": "1,0",
    },
]

# Выдуманные данные — заказчик АНО «Пример» / Петров П.П., исполнитель
# ООО «Ромашка» / Иванов И.И. (владелец, 05.10.2026).
_FAKE_CTX_BASE = {
    "customer_full_name": "Автономная некоммерческая организация «Пример»",
    "customer_short_name": "АНО «Пример»",
    "customer_inn": "7700000001",
    "customer_kpp": "770001001",
    "customer_ogrn": "1027700000001",
    "customer_address": "г. Москва, ул. Примерная, д. 1",
    "customer_postal_address": "г. Москва, ул. Примерная, д. 1",
    "customer_bank_name": "ПАО «Пример-Банк»",
    "customer_settlement_account": "40703810400000000099",
    "customer_correspondent_account": "30101810400000000099",
    "customer_bik": "044500099",
    "customer_personal_account": "71234Ц56789",
    "customer_phone": "+7 (900) 000-00-00",
    "customer_email": "info@example.ru",
    "customer_signatory_position": "Президент",
    "customer_signatory_name": "Петров Пётр Петрович",
    "customer_signatory_name_genitive": "Петрова Петра Петровича",
    "customer_signatory_name_initials": "П.П. Петров",
    "customer_signatory_initials": "Петров П.П.",
    "customer_signatory_basis": "Устава",
    "contract_city": "Москва",
    "contractor_full_name": "Общество с ограниченной ответственностью «Ромашка»",
    "contractor_short_name": "ООО «Ромашка»",
    "contractor_inn": "7700000000",
    "contractor_kpp": "770000001",
    "contractor_ogrn": "1157746000000",
    "contractor_ogrnip": "304770000000001",
    "contractor_org_type": "ЮЛ",
    "contractor_address": "г. Москва, ул. Ромашковая, д. 2",
    "contractor_postal_address": "г. Москва, ул. Ромашковая, д. 2",
    "contractor_phone": "+7 (495) 123-45-67",
    "contractor_email": "info@romashka.ru",
    "contractor_bank_name": "ПАО «Банк Ромашка»",
    "contractor_settlement_account": "40702810000000000001",
    "contractor_bik": "044525225",
    "contractor_correspondent_account": "30101810400000000225",
    "contractor_signatory_position": "Директор",
    "contractor_signatory_name": "Иванов Иван Иванович",
    "contractor_signatory_name_genitive": "Иванова Ивана Ивановича",
    "contractor_signatory_initials": "Иванов И.И.",
    "contractor_signatory_basis": "Устава",
    "contract_number": "2026/42",
    "contract_date_day": "15",
    "contract_date_month": "января",
    "contract_date_year": "2026",
    "contract_price_num": "130 000,00",
    "contract_price_words": "сто тридцать тысяч рублей 00 копеек",
    "payment_term_days": 7,
    "payment_term_days_words": "семь",
    "service_term_days": 7,
    "service_term_days_words": "семь",
    "acceptance_term_days": 7,
    "acceptance_term_days_words": "семь",
    "advance_amount": "50 000,00",
    "prepayment_date": "10.01.2026",
    "delivery_location": "г. Москва, ул. Примерная, д. 1",
    "delivery_date": "20.01.2026",
    "service_subject": "Оказание услуг связи",
    "service_start_date": "15.01.2026",
    "service_end_date": "28.02.2026",
    "service_date": "20.01.2026",
    "service_name": "Оказание услуг связи",
    "vat_applicable": True,
    "vat_rate": 20,
    "vat_amount_num": "21 666,67",
    "vat_amount_words": "двадцать одна тысяча шестьсот шестьдесят шесть рублей 67 копеек",
    "vat_exemption_article": "ст. 149 НК РФ",
    "third_party_involved": True,
    "is_retroactive": False,
    "has_stages": True,
    "delivery_by_supplier": True,
    "penalty_rate": "0,1",
    "subsidy_ministry_name": "Министерство примерной защиты Российской Федерации",
    "subsidy_grantor_name": "Федеральное агентство по примерным делам",
    "subsidy_agreement_number": "000-10-2026-001",
    "subsidy_agreement_date": "01.01.2026",
    "items": _ITEMS,
    "contract_items": _ITEMS,
    "item": {},
    "commission_members": [],
}


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


_PREPAYMENT_DOC_TYPES = [
    "contract_goods_single",
    "contract_services",
    "contract_services_food",
    "contract_repair_framework",
]


@pytest.mark.parametrize("doc_type", _PREPAYMENT_DOC_TYPES)
@pytest.mark.parametrize("is_prepayment", [True, False])
def test_prepayment_toggle_prints_exactly_one_clause(doc_type, is_prepayment):
    path = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    ctx = dict(_FAKE_CTX_BASE, is_prepayment=is_prepayment)
    txt = _render_text(path, ctx)

    if doc_type == "contract_goods_single":
        prepay_marker = "100% предоплаты"
        postpay_marker = "без авансирования"
    elif doc_type == "contract_repair_framework":
        prepay_marker = "в форме предоплаты"
        postpay_marker = "в форме безналичного перечисления"
    else:
        prepay_marker = "с предоплатой"
        postpay_marker = "без авансирования"

    has_prepay = prepay_marker in txt
    has_postpay = postpay_marker in txt

    assert has_prepay != has_postpay, (
        f"{doc_type} (is_prepayment={is_prepayment}): должен печататься "
        f"РОВНО один вариант оплаты, prepay={has_prepay} postpay={has_postpay}"
    )
    if is_prepayment:
        assert has_prepay, f"{doc_type}: при is_prepayment=True должен печататься вариант предоплаты"
    else:
        assert has_postpay, f"{doc_type}: при is_prepayment=False должен печататься вариант постоплаты"

    # Реквизиты исполнителя — ИНН ООО «Ромашка» обязан попасть в текст.
    assert "7700000000" in txt, f"{doc_type}: ИНН контрагента (Ромашки) не найден в тексте"
    assert "Ромашка" in txt, f"{doc_type}: наименование контрагента не найдено в тексте"

    # Ревью 2026-10-05 (живая генерация закупки 20655): «…Услуги течение 7
    # (7) с даты подписания…» — потеряны «в» и «рабочих дней», прописью не
    # подставлялась. Срок оплаты должен печататься ПОЛНОЙ фразой с
    # прописью в скобках, в ОБОИХ вариантах оплаты.
    expected = "в течение 7 (семь) рабочих дней"
    assert expected in txt, (
        f"{doc_type} (is_prepayment={is_prepayment}): не найдена полная фраза "
        f"{expected!r} — пропущено «в»/«рабочих дней» или не подставлена пропись. "
        f"Текст: {txt!r}"
    )


@pytest.mark.parametrize("doc_type", [
    "contract_services", "contract_services_food", "contract_goods_single",
    "contract_gph_individual", "contract_gph_individual_rid",
    "contract_repair_vehicle", "contract_repair_framework",
])
def test_contractor_requisites_render_no_blank_labels(doc_type):
    """Реквизиты исполнителя заполняются — пустых глухих лейблов
    («Наименование:», «ИНН/КПП», «р/с:» без значения) после рендера не
    остаётся."""
    path = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    ctx = dict(_FAKE_CTX_BASE, is_prepayment=False)
    txt = _render_text(path, ctx)

    assert "7700000000" in txt
    assert "Ромашка" in txt
    # Голый лейбл без значения сразу за ним на следующей строке — признак
    # незаполненного поля.
    for blank_pair in ("Наименование:\nАдрес", "ИНН/КПП\n", "р/с:\n"):
        assert blank_pair not in txt, f"{doc_type}: похоже на незаполненный лейбл {blank_pair!r}"


# Ревью 2026-10-05 (живая генерация закупки 20655, ООО «ТЕХНИЧЕСКИЙ ЦЕНТР
# ПОЖАРНОЙ БЕЗОПАСНОСТИ»): блок реквизитов исполнителя печатал ОГРН (пусто)
# И ОГРНИП (пусто) ОДНОВРЕМЕННО, плюс дублировал ИНН отдельной строкой.
# contract_gph_individual(_rid) этого блока вовсе не содержат (физлицо),
# contract_repair_framework использует свою структуру без ОГРНИП —
# проверяем только там, где блок «ИНН/КПП»+«ОГРН»+«ИНН»+«ОГРНИП» реально есть.
_OGRN_BLOCK_DOC_TYPES = [
    "contract_services", "contract_services_food", "contract_goods_single",
    "contract_repair_vehicle",
]


@pytest.mark.parametrize("doc_type", _OGRN_BLOCK_DOC_TYPES)
@pytest.mark.parametrize("org_type", ["ЮЛ", "ИП"])
def test_contractor_ogrn_ogrnip_exclusive(doc_type, org_type):
    """Юрлицо печатает ИНН/КПП+ОГРН, ИП печатает ИНН+ОГРНИП — НИКОГДА оба
    одновременно, и без дублирования значения ИНН в обеих ветках сразу."""
    path = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    ctx = dict(_FAKE_CTX_BASE, is_prepayment=False, contractor_org_type=org_type)
    txt = _render_text(path, ctx)

    ogrn_value = _FAKE_CTX_BASE["contractor_ogrn"]
    ogrnip_value = _FAKE_CTX_BASE["contractor_ogrnip"]

    if org_type == "ЮЛ":
        assert ogrn_value in txt, f"{doc_type}/{org_type}: ОГРН исполнителя не найден"
        assert ogrnip_value not in txt, (
            f"{doc_type}/{org_type}: ОГРНИП НЕ должен печататься у юрлица, "
            f"но {ogrnip_value!r} найден в тексте"
        )
    else:
        assert ogrnip_value in txt, f"{doc_type}/{org_type}: ОГРНИП исполнителя не найден"
        assert ogrn_value not in txt, (
            f"{doc_type}/{org_type}: ОГРН НЕ должен печататься у ИП, "
            f"но {ogrn_value!r} найден в тексте"
        )


# ---------------------------------------------------------------------------
# Ревью 2026-10-06 (живая генерация, данные стенда с пустыми полями):
# «предоставившим субсидию ()» и «в течение  () календарных дней» — пустые
# subsidy_ministry_name/subsidy_grantor_name и сроки-в-днях (service_term_days
# и его _words-пропись) печатали голые скобки. Рендерим с этими полями
# пустыми и ищем «()» / «(  )» (скобки с пробелами внутри) в тексте.
# ---------------------------------------------------------------------------

_EMPTY_PARENS_RE = re.compile(r"\(\s*\)")

_SEVEN_FORMS = [
    "contract_services", "contract_services_food", "contract_goods_single",
    "contract_gph_individual", "contract_gph_individual_rid",
    "contract_repair_vehicle", "contract_repair_framework",
]


@pytest.mark.parametrize("doc_type", _SEVEN_FORMS)
def test_empty_optional_fields_no_bare_parens(doc_type):
    path = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    ctx = dict(_FAKE_CTX_BASE, is_prepayment=False)
    ctx.update(
        subsidy_ministry_name="",
        subsidy_grantor_name="",
        service_term_days="",
        service_term_days_words="",
        payment_term_days="",
        payment_term_days_words="",
        acceptance_term_days="",
        acceptance_term_days_words="",
    )
    txt = _render_text(path, ctx)

    found = _EMPTY_PARENS_RE.findall(txt)
    assert not found, (
        f"{doc_type}: при пустых subsidy_ministry_name/subsidy_grantor_name/"
        f"*_term_days(_words) в тексте остались голые скобки «()»/«(  )»: "
        f"{found}. Текст: {txt!r}"
    )
