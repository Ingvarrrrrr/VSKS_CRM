"""Purchase import — column maps and label→code lookup tables.

Split out of `services/purchase_import_parser.py` (refactor, 2026-09):
these module-level constants are used exclusively by
`purchase_import_parser_group._parse_and_group` (via the facade) and by
nothing else in the codebase — moved here verbatim, byte-for-byte, to keep
that file under the modularity guideline (ПРАВИЛО №5).

ПРАВИЛО №6 note: these are label→code lookup tables for parsing free-form
Excel cell text (Russian labels from the dropdown, legacy technical keys,
abbreviations, typos/aliases seen in real user files). They are NOT 1:1
duplicates of `services/dictionaries.py` (which holds the reverse,
code→label maps used for display): the keys here are lower-cased Russian
labels/aliases (many with no equivalent in dictionaries.py, e.g. "еи", "ед",
"кп", "зк", "рамочный накопительный", "подтверждено"), the values are the
same internal status/type codes. Do not merge — the two serve different
directions and the alias set here is import-specific.
"""
from typing import Dict

# ---------------------------------------------------------------------------
# Import helpers & COLUMN_MAP
# ---------------------------------------------------------------------------

# Full column map: lower-stripped header → internal field name.
# New template keys + old keys for backward compat.
_COLUMN_MAP: Dict[str, str] = {
    # --- New template: «Закупки» sheet ---
    "тип договора":                                              "contract_type_raw",
    "тип договора (разовый/рамочный)":                          "contract_type_raw",
    "номер закупки":                                             "purchase_group_num",
    "номер закупки (группа)":                                   "purchase_group_num",
    "номер заказа внутри закупки":                              "order_number",
    "номер заказа внутри закупки или период оказания услуг":   "order_number",
    "номер заказа":                                              "order_number",
    "предмет договора (общий)":                                 "subject",
    "предмет договора":                                         "subject",
    "наименование товара":                                       "item_name",
    "максимальная цена договора":                               "contract_price",
    "максимальная цена договора (предел рамочного)":           "contract_price",
    "наименование позиции":         "item_name",
    "наименование позиции *":       "item_name",
    "тип (товар/услуга/работа)":    "item_type",
    "тип":                          "item_type",
    # New 5-level FEO columns
    "фэо ур.1":                     "feo_l1",
    "фэо ур.2":                     "feo_l2",
    "фэо ур.3":                     "feo_l3",
    "фэо ур.4":                     "feo_l4",
    "фэо ур.5":                     "feo_l5",
    # Old single-path FEO column (backward compat)
    "категория фэо (полный путь) *": "feo_path",
    "категория фэо (полный путь)":  "feo_path",
    "категория фэо *":              "feo_path",
    "категория фэо":                "feo_category_name",
    "мероприятие":                  "event_name",
    "контрагент":                   "contractor_name",
    "инн контрагента *":            "contractor_inn",
    "инн контрагента":              "contractor_inn",
    "способ закупки (еи/кп)":       "purchase_method",
    "способ закупки":               "purchase_method",
    "реестровый №":                 "registry_number",
    "реестровый номер":             "registry_number",
    "реестр. №":                    "registry_number",
    "№ договора *":                 "contract_number",
    "№ договора":                   "contract_number",
    "дата договора *":              "contract_date",
    "дата договора":                "contract_date",
    "цена договора (итого)":        "contract_price",
    "цена договора":                "contract_price",
    "срок исполнения":              "execution_term",
    "статус":                       "status",
    "этап закупки":                 "status",   # новый заголовок (обратная совместимость через оба)
    "этап":                         "status",
    "подстатус (для «ведётся работа»)": "substatus",
    "подстатус":                    "substatus",
    "тип позиции (товар/услуга)":   "item_type",
    "основание для оплаты":         "payment_basis_type",
    "количество (план) *":          "plan_qty",
    "количество (план)":            "plan_qty",
    "ед. изм.":                     "unit",
    "ед. изм":                      "unit",
    "цена за ед. (план) *":         "plan_unit_price",
    "цена за ед. (план)":           "plan_unit_price",
    "сумма план":                   "plan_total",
    "кол-во факт":                  "fact_qty",
    "цена за ед. (факт)":           "fact_unit_price",
    "сумма факт *":                 "fact_total",
    "сумма факт":                   "fact_total",
    "страна происхождения":         "country_origin",
    "ставка ндс":                   "vat_rate",
    "год":                          "year",
    # --- Inline payment columns (new template) ---
    "номер платёжного документа":   "payment_doc_number",
    "номер платежного документа":   "payment_doc_number",
    "дата платёжного документа":    "payment_doc_date",
    "дата платежного документа":    "payment_doc_date",
    "назначение платежа":           "payment_purpose",
    # --- Removed columns from old template (keep for backward compat) ---
    "№ пп *":                       "payment_doc_number",
    "№ пп":                         "payment_doc_number",
    "дата платежа *":               "payment_doc_date",
    "дата платежа":                 "payment_doc_date",
    "сумма оплаты *":               "payment_amount",
    "сумма оплаты":                 "payment_amount",
    "в т.ч. федеральный бюджет":   "payment_federal",
    "в т.ч. фед. бюджет":          "payment_federal",
    # --- Old 17-col backward compat ---
    "наименование":                 "item_name",
    "предмет закупки":              "item_name",
    "субсидия":                     "subsidy_name",
    "инн":                          "contractor_inn",
    "нмцк":                         "nmck",
    "сумма":                        "nmck",
    "цена":                         "nmck",
    "способ":                       "purchase_method",
    "номер договора":               "contract_number",
    "пп №":                         "payment_doc_number",
    "пп номер":                     "payment_doc_number",
    "пп дата":                      "payment_doc_date",
    "оплачено":                     "payment_amount",
    "ссылка этп":                   "etp_url",
    "этп":                          "etp_url",
    # --- New template extended columns ---
    "срок исполнения (изменён)":    "execution_term_changed",
    "срок (изменён)":               "execution_term_changed",
    "дата доставки":                "delivery_date",
    "основание закупки":            "purchase_basis",
    "основание":                    "purchase_basis",
    "ответственное лицо":           "responsible_person",
    "ответственный":                "responsible_person",
    "ндс применяется":              "vat_applicable",
    "статья нк рф":                 "vat_exemption_article",
    "статья нк":                    "vat_exemption_article",
    "закрывающий документ: наименование": "acceptance_doc_name",
    "закрывающий документ: наим":   "acceptance_doc_name",
    "наименование закрывающего документа": "acceptance_doc_name",
    "закрывающий документ: №":      "acceptance_doc_number",
    "закрывающий документ: номер":  "acceptance_doc_number",
    "номер закрывающего документа": "acceptance_doc_number",
    "закрывающий документ: дата":   "acceptance_doc_date",
    "дата закрывающего документа":  "acceptance_doc_date",
    "закрывающий документ: сумма":  "acceptance_doc_amount",
    "сумма закрывающего документа": "acceptance_doc_amount",
    "предоплата":                   "is_prepayment",
    "ежемесячный платёж":           "is_monthly_payment",
    "ежемесячный платеж":           "is_monthly_payment",
    "процедура этп":                "etp_url",
    "№ п/п":                        "purchase_number",
    # --- New extended columns (plan §3) ---
    "регион":                                               "region",
    "регион проведения мероприятия":                        "region",
    "регион мероприятия":                                   "region",
    "регион поставки":                                      "delivery_region",
    "регион поставки (субъект рф)":                         "delivery_region",
    "субъект рф (место поставки)":                          "delivery_region",
    "субъект рф":                                           "delivery_region",
    "место оказания услуг / доставки":                      "delivery_location",
    "место оказания услуг":                                 "delivery_location",
    "место доставки":                                       "delivery_location",
    "адрес доставки":                                       "delivery_address",
    "экономия по результатам конкурентных закупок":         "economy",
    "экономия":                                             "economy",
    "срок действия договора":                               "contract_end_date",
    "квартал принятия обязательств":                        "commitment_quarter",
    "планируемый месяц платежа":                            "planned_payment_month",
    "дата окончания приёма заявок":                         "submission_deadline",
    "режим ндс":                                            "vat_mode",
    "подпись этапа":                                        "stage_label",
}

# «Платежи» sheet column map
_PAYMENTS_COLUMN_MAP: Dict[str, str] = {
    "№ договора":           "contract_number",
    "№ пп":                 "document_number",
    "дата платежа":         "payment_date",
    "сумма":                "amount",
    "назначение платежа":   "payment_purpose",
}

_STATUS_MAP = {
    # Русские лейблы из выпадающего списка (новый шаблон)
    "желания сотрудников": "wishes",
    "план закупок":         "plan_schedule",
    "ведётся работа":      "work_in_progress",
    "заключён договор":    "contracted",
    "поставлено":          "delivered",
    "оплачено":            "paid",
    # Технические ключи (backward compat)
    "wishes": "wishes", "желания": "wishes", "planned": "wishes", "планируется": "wishes", "план": "wishes",
    "plan_schedule": "plan_schedule",
    "confirmed": "work_in_progress", "подтверждено": "work_in_progress",
    "work_in_progress": "work_in_progress", "в работе": "work_in_progress", "in_progress": "work_in_progress",
    "contracted": "contracted", "законтрактовано": "contracted",
    "ordered": "ordered", "заказано": "ordered",
    "delivered": "delivered", "исполнено": "delivered",
    "поставлено, но не оплачено": "delivered", "поставлено, не оплачено": "delivered",
    "paid": "paid",
}

_SUBSTATUS_MAP = {
    # Русские лейблы из выпадающего списка
    "формирование тз":             "tz_forming",
    "сбор кп":                     "kp_collecting",
    "размещено на площадке":       "on_platform",
    "переговоры с поставщиком":    "contractor_negotiations",
    "подписание договора":         "contract_signing",
    # Технические ключи
    "tz_forming": "tz_forming",
    "kp_collecting": "kp_collecting",
    "on_platform": "on_platform",
    "contractor_negotiations": "contractor_negotiations",
    "contract_signing": "contract_signing",
}

_CONTRACT_TYPE_MAP = {
    # Русские лейблы из выпадающего списка
    "разовая поставка":              "single",
    "рамочный (нарастающий итог)":  "framework_cumulative",
    "рамочный (с указанием суммы)": "framework_with_amount",
    # Короткие псевдонимы (backward compat)
    "рамочный":           "framework_cumulative",
    "разовый":            "single",
    "рамочный накопительный": "framework_cumulative",
    # Технические ключи
    "single":               "single",
    "framework_cumulative": "framework_cumulative",
    "framework_with_amount":"framework_with_amount",
}

_ITEM_TYPE_MAP = {
    # Русские лейблы из выпадающего списка
    "товар":    "товар",
    "услуга":   "услуга",
    "работа":   "работа",
    # Множественное число (из файла пользователя «Товары», «Услуги»)
    "товары":   "товар",
    "услуги":   "услуга",
    "работы":   "работа",
}

_PAYMENT_BASIS_MAP = {
    # Русские лейблы из выпадающего списка
    "договор":      "contract",
    "счёт":         "invoice",
    "счёт-договор": "invoice_contract",
    # Технические ключи
    "contract":          "contract",
    "invoice":           "invoice",
    "invoice_contract":  "invoice_contract",
}

_METHOD_MAP = {
    # Русские лейблы из выпадающего списка
    "единственный поставщик":   "single",
    "единственный исполнитель": "single",
    "единый поставщик":         "single",
    "конкурентная процедура":   "competitive",
    "конкурсная процедура":     "competitive",
    "запрос котировок":         "quote_request",
    # Аббревиатуры (backward compat)
    "еи":  "single",
    "ед":  "single",
    "кп":  "competitive",
    "зк":  "quote_request",
    # Технические ключи
    "single":        "single",
    "competitive":   "competitive",
    "quote_request": "quote_request",
}

# Required fields for new-format validation (field_name, display_label)
_REQUIRED_FIELDS = [
    ("item_name",       "Наименование товара"),
    ("feo_l1",          "ФЭО Ур.1"),
    ("contractor_inn",  "ИНН контрагента"),
    ("contract_number", "№ договора"),
    ("contract_date",   "Дата договора"),
    ("plan_qty",        "Количество (план)"),
    ("plan_unit_price", "Цена за ед. (план)"),
    ("fact_total",      "Сумма факт"),
]

# Marker fields that distinguish new template from old legacy template
_NEW_TEMPLATE_MARKER_FIELDS = {"feo_l1", "plan_qty", "plan_unit_price", "fact_total"}
# Old-template marker (single path column)
_OLD_TEMPLATE_MARKER_FIELDS = {"feo_path", "feo_category_name"}
