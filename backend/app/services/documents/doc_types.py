"""Константы doc_type: пути к шаблонам, метки, наборы типов документов.

Ноль логики — только справочные данные, поэтому у модуля нет зависимостей
от остальных services/documents/*. TEMPLATE_VARIABLES вынесен в отдельный
template_variables.py (204 строки) и реэкспортируется отсюда."""


from .template_variables import TEMPLATE_VARIABLES  # noqa: F401 — реэкспорт


TEMPLATES_DIR = "/app/templates"
SUBSIDY_TEMPLATES_DIR = "/app/uploads/templates"


# Phase 26-ggg: sentinel-маркер для post-render таблицы чеков.
# Пользователь ставит {{ receipts_table }} в шаблон одним параграфом;
# context подставляет эту строку; postprocess находит её и заменяет
# параграф на настоящую docx-таблицу с PNG чеков в каждой ячейке.
RECEIPTS_TABLE_MARKER = "[[RECEIPTS_TABLE_2COL]]"


DOC_TYPES = {
    "service_note_delivery": ("service_note_delivery.docx", "Служебная_записка_выдача"),
    "service_note_payment":  ("service_note_payment.docx",  "Служебная_записка_оплата"),
    # Phase 19.05: dedicated SZ for procurement (distinct from generic service_note)
    "service_note_procurement": ("service_note_procurement.docx", "Служебная_записка_закупка"),
    # Phase 19.07: СЗ на аванс
    "service_note_advance":  ("service_note_advance.docx",  "Служебная_записка_аванс"),
    # Legacy — kept for backwards compat with existing uploaded subsidy overrides.
    "contract_tz":           ("contract_tz.docx",           "Договор_с_ТЗ"),
    # tech_spec falls back to contract_tz.docx — separation kept for future
    # when a dedicated tech_spec template is uploaded, but both resolve to
    # the same file today so there is no confusing "empty ТЗ slot" in UI.
    "tech_spec":             ("contract_tz.docx",           "Техническое_задание"),
    # Phase 19.05: split ТЗ into request-of-prices and contract-appendix variants.
    # Default template file is a copy of contract_tz.docx; admins upload
    # per-subsidy overrides via SubsidiesView.
    "tech_spec_request":     ("tech_spec_request.docx",     "ТЗ_запрос_цен"),
    "tech_spec_contract":    ("tech_spec_contract.docx",    "ТЗ_к_договору"),
    "contract":              ("contract.docx",              "Договор"),
    # Phase 23.1: contract_services / contract_goods merged into universal contract.docx
    # (removed — subject_kind auto-detected from purchase_items.product.item_kind)
    "approval_sheet":        ("approval_sheet.docx",        "Лист_согласования"),
    "order_purchase":        ("order_purchase.docx",        "Приказ_о_закупке"),
    # Phase 28: typed contract forms per-subsidy
    # Форма «услуги» объединена в один файл (contract_services.docx) — большая/малая
    # отчётность теперь не отдельные шаблоны договора, а отдельная методичка
    # (methodology_large / methodology_small), приклеиваемая к готовому договору.
    "contract_services":             ("contract_services.docx",            "Договор_услуг"),
    # Алиасы на новый объединённый файл — НЕ удалять: у уже существующих закупок
    # doc_type мог быть сохранён/запрошен под старым именем, без алиаса — 404.
    "contract_services_large":      ("contract_services.docx",      "Договор_услуги_крупный"),
    "contract_services_small":      ("contract_services.docx",      "Договор_услуги_малый"),
    "contract_services_food":       ("contract_services_food.docx",       "Договор_услуги_питание"),
    "methodology_large":             ("methodology_large.docx",            "Методические_рекомендации_большие"),
    "methodology_small":             ("methodology_small.docx",            "Методические_рекомендации_малые"),
    "contract_goods_single":        ("contract_goods_single.docx",        "Договор_поставка_единственный"),
    "contract_gph_individual":      ("contract_gph_individual.docx",      "Договор_ГПХ_физлицо"),
    "contract_gph_individual_rid":  ("contract_gph_individual_rid.docx",  "Договор_ГПХ_физлицо_РИД"),
    "contract_repair_vehicle":      ("contract_repair_vehicle.docx",      "Договор_ремонт_ТС"),
    "contract_repair_framework":    ("contract_repair_framework.docx",    "Договор_ремонт_рамочный"),
    # Fabrikant ЭТП package — four template types for запрос цен на Фабрикант
    "fabrikant_instruction":        ("fabrikant_instruction.docx",        "Фабрикант_инструкция"),
    "fabrikant_application_form":   ("fabrikant_application_form.docx",   "Фабрикант_форма_заявки"),
    "fabrikant_documentation":      ("fabrikant_documentation.docx",      "Фабрикант_документация"),
    "fabrikant_contract_project":   ("fabrikant_contract_project.docx",   "Фабрикант_проект_договора"),
}


# Требование владельца («Плановые не равно Договор»): для этих типов документ
# печатает ТОЛЬКО позиции и суммы "Как в договоре" (ContractItem) — без
# молчаливого отката на плановые purchase_items / НМЦК. Лист согласования
# входит сюда же: он визирует именно то, что уйдёт в договор.
#
# НЕ включены намеренно:
#   - tech_spec_request — ТЗ для ЗАПРОСА цен, по смыслу плановый документ;
#   - service_note_* — служебные записки оформляются ДО заключения договора;
#   - fabrikant_* — пакет документов для тендерной процедуры на Фабрикант,
#     публикуется ДО выбора поставщика, договора ещё не существует;
#   - order_purchase — приказ о закупке, тоже предшествует договору.
# tech_spec_request и tech_spec_contract сейчас оба резолвятся в один файл
# contract_tz.docx (см. DOC_TYPE_FALLBACK_FILES), но теперь ведут себя
# по-разному — это ожидаемо и намеренно.
CONTRACT_FAMILY_DOC_TYPES = {
    "contract_services",
    # Алиасы — держим в семье тоже, чтобы гейт «Плановые не равно Договор»
    # срабатывал одинаково, если старый doc_type всё же запрошен.
    "contract_services_large",
    "contract_services_small",
    "contract_services_food",
    "contract_goods_single",
    "contract_gph_individual",
    "contract_gph_individual_rid",
    "contract_repair_vehicle",
    "contract_repair_framework",
    "contract",
    "contract_tz",
    "tech_spec_contract",
    "approval_sheet",
}


# Семь типовых форм договора (+ 2 legacy-алиаса на contract_services) — только
# к НИМ приклеивается методичка (Purchase.methodology), см. generate_document
# ниже. 'contract' (старый универсальный шаблон), 'approval_sheet',
# 'contract_tz', 'tech_spec_contract' — не подписываемый контрагентом текст
# договора, методичка к ним не приклеивается.
CONTRACT_TYPED_FORM_DOC_TYPES = {
    "contract_services",
    "contract_services_large",
    "contract_services_small",
    "contract_services_food",
    "contract_goods_single",
    "contract_gph_individual",
    "contract_gph_individual_rid",
    "contract_repair_vehicle",
    "contract_repair_framework",
}


# Phase 19.05: fallback map — if a dedicated template file is missing,
# fall back to the legacy file so the endpoint still works before admins
# upload per-subsidy overrides.
DOC_TYPE_FALLBACK_FILES = {
    "service_note_procurement": "service_note.docx",
    # Phase 19.07: fall back to generic service_note until a dedicated
    # advance template is uploaded (per-subsidy or globally).
    "service_note_advance":     "service_note.docx",
    "tech_spec_request":        "contract_tz.docx",
    "tech_spec_contract":       "contract_tz.docx",
    # Phase 28: new typed contract forms fall back to universal contract.docx
    # until per-subsidy templates are uploaded. Prevents 404 for old purchases.
    "contract_services_large":     "contract.docx",
    "contract_services_small":     "contract.docx",
    "contract_services_food":      "contract.docx",
    "contract_goods_single":       "contract.docx",
    "contract_gph_individual":     "contract.docx",
    "contract_gph_individual_rid": "contract.docx",
    "contract_repair_vehicle":     "contract.docx",
    "contract_repair_framework":   "contract.docx",
}


_BASIS_LABELS = {
    "plan_schedule": "план закупок",
    "service_note": "служебная записка",
}


# Способ закупки (Purchase.purchase_method) → человекочитаемая подпись.
# Значения см. frontend/src/views/CreateOrderView.vue (v-select purchase_method)
# и ContractsView.vue (purchaseMethodItems): в системе только 3 кода.
# Неизвестный код — не пустая строка, а сам код (см. order_purchase, п.2).
_PURCHASE_METHOD_LABELS = {
    "single": "Единственный поставщик",
    "competitive": "Конкурсная процедура",
    "advance": "Авансовый отчёт",
}


# Уточняющая форма конкурентной процедуры (Purchase.competitive_form).
# Владелец: «"Запрос цен" — это вариант конкурсной процедуры, так же как и
# Аукцион — он же редукцион, а также Конкурс» — НЕ отдельный способ закупки,
# применимо только когда purchase_method == 'competitive'.
_COMPETITIVE_FORM_LABELS = {
    "price_request": "Запрос цен",
    "auction": "Аукцион (редукцион)",
    "tender": "Конкурс",
}


# Приказ о закупке и лист согласования визируют способ закупки как отдельный
# распорядительный пункт — без него документ юридически бессмысленный
# («2. Определить способ закупки: .»). Владелец подтвердил для приказа
# уверенно, для листа согласования — «наверное тоже надо» (менее строго).
PURCHASE_METHOD_REQUIRED_DOC_TYPES = {"order_purchase", "approval_sheet"}


# doc_type, чьи .docx-шаблоны реально печатают ставку НДС ({{vat_rate}} и/или
# {{vat_info_line}}) — установлено сканом backend/templates/*.docx на предмет
# этих плейсхолдеров (2026-09-04). Остальные doc_type (contract_tz,
# contract_gph_individual[_rid], contract_repair_vehicle, order_purchase,
# service_note_delivery/procurement/advance, tech_spec_request и т.д.) ставку
# НДС в тексте не показывают вовсе — для них требовать заполненную ставку
# было бы избыточным блоком, никак не защищающим от реальной ошибки в тексте.
VAT_RATE_PRINTED_DOC_TYPES = {
    "contract",
    "contract_services",
    "contract_services_large",
    "contract_services_small",
    "contract_services_food",
    "contract_goods_single",
    "contract_repair_framework",
    "tech_spec_contract",
    "approval_sheet",
    "service_note_payment",
}


# Тексты оснований освобождения от НДС, подставляемые автоматически, когда
# основание системе уже известно из данных закупки — владелец (2026-09-04):
# «самозанятые не облагаются НДС и ГПХ, у остальных должно быть [заполнено]».
# Единственное место с этими текстами — держим их здесь константами, не
# размазывая по коду (см. _resolve_vat_exemption_basis).
VAT_EXEMPTION_ARTICLE_NPD = (
    "ч. 9 ст. 2 Федерального закона от 27.11.2018 № 422-ФЗ "
    "(исполнитель применяет специальный налоговый режим "
    "«Налог на профессиональный доход»)"
)
VAT_EXEMPTION_ARTICLE_GPH_INDIVIDUAL = (
    "ст. 143 НК РФ (физическое лицо, с которым заключён договор ГПХ, "
    "не признаётся налогоплательщиком НДС)"
)


# contract_form (Purchase.contract_form, см. app/models/purchase.py) — формы
# договора с физическим лицом, для которых основание освобождения от НДС
# определено самим фактом такого договора и не требует ввода вручную.
_GPH_INDIVIDUAL_CONTRACT_FORMS = {"gph_individual", "gph_individual_rid"}


FEO_PATH_UNRESOLVED_LABEL = "Категория ФЭО не определена (позиция договора без привязки к плановой)"


# ── Fabrikant package ZIP endpoint ───────────────────────────────────────────

# File names for Fabrikant document package (видны пользователю в кабинете
# площадки в разделе документов извещения, поэтому названы по-русски)
FABRIKANT_PKG_FILE_NAMES = [
    ("fabrikant_instruction",      "Инструкция по заполнению заявки.docx", "Инструкция по заполнению заявки"),
    ("fabrikant_application_form", "Заявка (форма).docx",                  "Заявка (форма)"),
    ("fabrikant_documentation",    "Документация к закупке.docx",          "Документация к закупке"),
    ("fabrikant_contract_project", "Проект договора.docx",                 "Проект договора"),
    ("tech_spec_request",          "Техническое задание.docx",             "Техническое задание"),
]
