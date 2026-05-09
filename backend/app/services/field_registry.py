from dataclasses import dataclass
from typing import Literal, Optional, List

FieldType = Literal['string', 'number', 'currency', 'date', 'datetime', 'boolean', 'enum']
FieldSource = Literal['purchase', 'purchase_item', 'contractor', 'subsidy', 'feo_category', 'payment', 'bank_payment', 'event', 'computed']
AggType = Literal['sum', 'avg', 'count', 'count_distinct', 'min', 'max', 'first']


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    type: FieldType
    source: FieldSource
    sql_expr: str  # SQL expression — например "purchases.contract_price" или CASE WHEN ...
    group: str  # категория для UI (e.g. "Идентификация", "Контрагент", "Финансы")
    format: Optional[str] = None  # 'rub', 'pct', 'date_dmy', etc.
    agg_default: Optional[AggType] = None
    drillable: bool = True  # можно ли использовать как dimension с drill-down
    is_dimension: bool = True
    is_measure: bool = False
    enum_values: Optional[List[str]] = None
    description: Optional[str] = None


# Полный registry
FIELDS: dict[str, FieldDef] = {
    # === ИДЕНТИФИКАЦИЯ ===
    'purchase_id': FieldDef('purchase_id', '№ закупки (id)', 'number', 'purchase', 'purchases.id', 'Идентификация', drillable=True),
    'purchase_number': FieldDef('purchase_number', 'Номер закупки', 'number', 'purchase', 'purchases.purchase_number', 'Идентификация'),
    'registry_number': FieldDef('registry_number', 'Реестровый номер', 'string', 'purchase', 'purchases.registry_number', 'Идентификация'),
    'order_number': FieldDef('order_number', 'Номер заказа', 'string', 'purchase', 'purchases.order_number', 'Идентификация'),

    # === ПРЕДМЕТ И КАТЕГОРИЗАЦИЯ ===
    'subject': FieldDef('subject', 'Предмет договора', 'string', 'purchase', 'purchases.subject', 'Предмет'),
    'item_name': FieldDef('item_name', 'Наименование товара/услуги', 'string', 'purchase', 'purchases.item_name', 'Предмет'),
    'item_type': FieldDef('item_type', 'Товар/Услуга', 'enum', 'purchase', 'purchases.item_type', 'Предмет', enum_values=['Товары', 'Услуги']),
    'description_mode': FieldDef('description_mode', 'Способ описания', 'enum', 'purchase', 'purchases.description_mode', 'Предмет'),

    # === КОНТРАГЕНТ ===
    'contractor_id': FieldDef('contractor_id', 'Контрагент (id)', 'number', 'contractor', 'contractors.id', 'Контрагент', drillable=True),
    'contractor_name': FieldDef('contractor_name', 'Контрагент', 'string', 'contractor', 'contractors.name', 'Контрагент'),
    'contractor_full_name': FieldDef('contractor_full_name', 'Полное наименование контрагента', 'string', 'contractor', 'contractors.full_name', 'Контрагент'),
    'contractor_inn': FieldDef('contractor_inn', 'ИНН контрагента', 'string', 'contractor', 'contractors.inn', 'Контрагент'),
    'contractor_kpp': FieldDef('contractor_kpp', 'КПП контрагента', 'string', 'contractor', 'contractors.kpp', 'Контрагент'),
    'contractor_ogrn': FieldDef('contractor_ogrn', 'ОГРН/ОГРНИП', 'string', 'contractor', 'contractors.ogrn', 'Контрагент'),
    'contractor_address': FieldDef('contractor_address', 'Адрес контрагента', 'string', 'contractor', 'contractors.address', 'Контрагент'),
    'contractor_org_type': FieldDef('contractor_org_type', 'Форма организации', 'enum', 'contractor', 'contractors.org_type', 'Контрагент', enum_values=['Юр.лицо', 'ИП', 'Самозанятый', 'Физ.лицо']),
    'contractor_bank_name': FieldDef('contractor_bank_name', 'Банк контрагента', 'string', 'contractor', 'contractors.bank_name', 'Контрагент'),
    'contractor_settlement_account': FieldDef('contractor_settlement_account', 'Расчётный счёт', 'string', 'contractor', 'contractors.settlement_account', 'Контрагент'),
    'contractor_bik': FieldDef('contractor_bik', 'БИК', 'string', 'contractor', 'contractors.bik', 'Контрагент'),
    'contractor_correspondent_account': FieldDef('contractor_correspondent_account', 'Корр. счёт', 'string', 'contractor', 'contractors.correspondent_account', 'Контрагент'),

    # === ДОГОВОР ===
    'contract_number': FieldDef('contract_number', 'Номер договора', 'string', 'purchase', 'purchases.contract_number', 'Договор'),
    'contract_date': FieldDef('contract_date', 'Дата договора', 'date', 'purchase', 'purchases.contract_date', 'Договор', format='date_dmy'),
    'contract_end_date': FieldDef('contract_end_date', 'Срок действия договора', 'date', 'purchase', 'purchases.contract_end_date', 'Договор'),
    'purchase_contract_type': FieldDef('purchase_contract_type', 'Тип договора', 'enum', 'purchase', 'purchases.purchase_contract_type', 'Договор', enum_values=['single', 'framework_cumulative', 'framework_with_amount']),

    # === ФЭО ===
    'subsidy_id': FieldDef('subsidy_id', 'Субсидия (id)', 'number', 'subsidy', 'subsidies.id', 'ФЭО', drillable=True),
    'subsidy_name': FieldDef('subsidy_name', 'Источник финансирования (субсидия)', 'string', 'subsidy', 'subsidies.name', 'ФЭО'),
    'subsidy_basis_doc_number': FieldDef('subsidy_basis_doc_number', 'Номер соглашения о субсидии', 'string', 'subsidy', 'subsidies.basis_doc_number', 'ФЭО'),
    'subsidy_basis_doc_date': FieldDef('subsidy_basis_doc_date', 'Дата соглашения о субсидии', 'date', 'subsidy', 'subsidies.basis_doc_date', 'ФЭО'),
    'subsidy_year': FieldDef('subsidy_year', 'Год субсидии', 'number', 'subsidy', 'subsidies.year', 'ФЭО'),
    'subsidy_budget': FieldDef('subsidy_budget', 'Объём субсидии', 'currency', 'subsidy', 'subsidies.budget', 'ФЭО', format='rub', is_measure=True, agg_default='sum'),
    'feo_category_id': FieldDef('feo_category_id', 'ФЭО категория (id)', 'number', 'feo_category', 'feo_categories.id', 'ФЭО', drillable=True),
    'feo_l1_name': FieldDef('feo_l1_name', 'Направление расходов по ФЭО (1 уровень)', 'string', 'computed', 'feo_l1.name', 'ФЭО'),
    'feo_l2_name': FieldDef('feo_l2_name', 'Тип расходов конкретизированный (2 уровень)', 'string', 'computed', 'feo_l2.name', 'ФЭО'),
    'feo_l3_name': FieldDef('feo_l3_name', 'Направление из приложений к ФЭО (3 уровень)', 'string', 'computed', 'feo_l3.name', 'ФЭО'),
    'feo_appendix': FieldDef('feo_appendix', 'Приложение ФЭО', 'string', 'feo_category', 'feo_categories.appendix', 'ФЭО'),
    'feo_planned_quantity': FieldDef('feo_planned_quantity', 'Количество из ФЭО', 'number', 'feo_category', 'feo_categories.planned_quantity', 'ФЭО', is_measure=True, agg_default='sum'),
    'feo_planned_amount': FieldDef('feo_planned_amount', 'Сумма из ФЭО', 'currency', 'feo_category', 'feo_categories.planned_amount', 'ФЭО', format='rub', is_measure=True, agg_default='sum'),

    # === ЦЕНЫ И КОЛИЧЕСТВО ===
    'planned_quantity': FieldDef('planned_quantity', 'Плановое количество', 'number', 'purchase', 'purchases.planned_quantity', 'Цены', is_measure=True, agg_default='sum'),
    'unit': FieldDef('unit', 'Ед. изм. (ОКЕИ)', 'string', 'purchase', 'purchases.unit', 'Цены'),
    'planned_unit_price': FieldDef('planned_unit_price', 'Плановая цена за единицу', 'currency', 'purchase', 'purchases.planned_unit_price', 'Цены', format='rub', is_measure=True, agg_default='avg'),
    'planned_total_price': FieldDef('planned_total_price', 'Плановая сумма', 'currency', 'purchase', 'purchases.planned_total_price', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'final_unit_price': FieldDef('final_unit_price', 'Итоговая цена за единицу', 'currency', 'purchase', 'purchases.final_unit_price', 'Цены', format='rub', is_measure=True, agg_default='avg'),
    'final_total_amount': FieldDef('final_total_amount', 'Итоговая сумма', 'currency', 'purchase', 'purchases.final_total_amount', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'contract_price': FieldDef('contract_price', 'Сумма по договору', 'currency', 'purchase', 'purchases.contract_price', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'nmck': FieldDef('nmck', 'НМЦК', 'currency', 'purchase', 'purchases.nmck', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'economy': FieldDef('economy', 'Экономия', 'currency', 'purchase', 'purchases.economy', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'delivery_payment_amount': FieldDef('delivery_payment_amount', 'Сумма к оплате по поставке', 'currency', 'purchase', 'purchases.delivery_payment_amount', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'acceptance_doc_amount': FieldDef('acceptance_doc_amount', 'Сумма по акту', 'currency', 'purchase', 'purchases.acceptance_doc_amount', 'Цены', format='rub', is_measure=True, agg_default='sum'),
    'payment_amount': FieldDef('payment_amount', 'Сумма оплачено', 'currency', 'purchase', 'purchases.payment_amount', 'Цены', format='rub', is_measure=True, agg_default='sum'),

    # === СТАТУСЫ ===
    'status': FieldDef('status', 'Статус', 'enum', 'purchase', 'purchases.status', 'Статусы', enum_values=['wishes', 'planned', 'confirmed', 'contracted', 'ordered', 'delivered', 'paid', 'cancelled']),
    'substatus': FieldDef('substatus', 'Подстатус', 'string', 'purchase', 'purchases.substatus', 'Статусы'),
    'confirmed': FieldDef('confirmed', 'Подтверждена', 'boolean', 'purchase', 'purchases.confirmed', 'Статусы'),
    'is_likely_needed': FieldDef('is_likely_needed', 'Скорее всего понадобится', 'boolean', 'purchase', 'purchases.is_likely_needed', 'Статусы'),
    'is_prepayment': FieldDef('is_prepayment', 'Предоплата', 'boolean', 'purchase', 'purchases.is_prepayment', 'Статусы'),
    'approval_status': FieldDef('approval_status', 'Статус согласования', 'enum', 'purchase', 'purchases.approval_status', 'Статусы', enum_values=['in_progress', 'approved', 'rejected']),

    # === МЕРОПРИЯТИЕ + РЕГИОН ===
    'event_id': FieldDef('event_id', 'Мероприятие (id)', 'number', 'event', 'events.id', 'Мероприятие', drillable=True),
    'event_name': FieldDef('event_name', 'Мероприятие', 'string', 'event', 'events.name', 'Мероприятие'),
    'region': FieldDef('region', 'Регион проведения мероприятия', 'string', 'purchase', 'purchases.region', 'Мероприятие'),

    # === ДАТЫ И ПЕРИОДЫ ===
    'execution_term': FieldDef('execution_term', 'Срок исполнения', 'date', 'purchase', 'purchases.execution_term', 'Сроки'),
    'delivery_date': FieldDef('delivery_date', 'Дата поставки', 'date', 'purchase', 'purchases.delivery_date', 'Сроки'),
    'service_start_date': FieldDef('service_start_date', 'Начало периода оказания', 'date', 'purchase', 'purchases.service_start_date', 'Сроки'),
    'service_end_date': FieldDef('service_end_date', 'Конец периода оказания', 'date', 'purchase', 'purchases.service_end_date', 'Сроки'),
    'service_deadline_date': FieldDef('service_deadline_date', 'Срок оказания услуг', 'date', 'purchase', 'purchases.service_deadline_date', 'Сроки'),
    'submission_deadline': FieldDef('submission_deadline', 'Дедлайн подачи', 'datetime', 'purchase', 'purchases.submission_deadline', 'Сроки'),
    'procurement_planned_date': FieldDef('procurement_planned_date', 'Планируемая дата закупки', 'date', 'purchase', 'purchases.procurement_planned_date', 'Сроки'),
    'prepayment_date': FieldDef('prepayment_date', 'Дата предоплаты', 'date', 'purchase', 'purchases.prepayment_date', 'Сроки'),
    'acceptance_doc_date': FieldDef('acceptance_doc_date', 'Дата акта/УПД', 'date', 'purchase', 'purchases.acceptance_doc_date', 'Сроки'),
    'acceptance_doc_number': FieldDef('acceptance_doc_number', 'Номер акта/УПД', 'string', 'purchase', 'purchases.acceptance_doc_number', 'Сроки'),
    'acceptance_doc_name': FieldDef('acceptance_doc_name', 'Тип закрывающего документа', 'string', 'purchase', 'purchases.acceptance_doc_name', 'Сроки'),
    'payment_doc_number': FieldDef('payment_doc_number', 'Номер ПП', 'string', 'purchase', 'purchases.payment_doc_number', 'Сроки'),
    'payment_doc_date': FieldDef('payment_doc_date', 'Дата ПП', 'date', 'purchase', 'purchases.payment_doc_date', 'Сроки'),

    # === ЛОКАЦИЯ И УСЛОВИЯ ===
    'delivery_location': FieldDef('delivery_location', 'Место оказания услуг / адрес доставки', 'string', 'purchase', 'purchases.delivery_location', 'Условия'),
    'delivery_address': FieldDef('delivery_address', 'Адрес доставки', 'string', 'purchase', 'purchases.delivery_address', 'Условия'),
    'country_origin': FieldDef('country_origin', 'Страна происхождения', 'string', 'purchase', 'purchases.country_origin', 'Условия'),
    'purchase_method': FieldDef('purchase_method', 'Способ закупки', 'enum', 'purchase', 'purchases.purchase_method', 'Условия', enum_values=['single', 'competitive']),
    'vat_applicable': FieldDef('vat_applicable', 'НДС применяется', 'boolean', 'purchase', 'purchases.vat_applicable', 'Условия'),
    'vat_rate': FieldDef('vat_rate', 'Ставка НДС', 'number', 'purchase', 'purchases.vat_rate', 'Условия'),
    'third_party_involved': FieldDef('third_party_involved', 'Третьи лица', 'boolean', 'purchase', 'purchases.third_party_involved', 'Условия'),
    'treasury_code': FieldDef('treasury_code', 'Казначейский / детализированный код', 'string', 'purchase', 'purchases.treasury_code', 'Условия'),

    # === COMPUTED MEASURES (CASE WHEN) ===
    'ordered_money': FieldDef('ordered_money', 'Заказано (₽)', 'currency', 'computed', "CASE WHEN purchases.status IN ('ordered','delivered','paid') THEN COALESCE(purchases.contract_price, purchases.planned_total_price, 0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'delivered_money': FieldDef('delivered_money', 'Поставлено (₽)', 'currency', 'computed', "CASE WHEN purchases.status IN ('delivered','paid') THEN COALESCE(purchases.acceptance_doc_amount, purchases.delivery_payment_amount, purchases.contract_price, purchases.planned_total_price, 0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'paid_money': FieldDef('paid_money', 'Оплачено (₽)', 'currency', 'computed', "CASE WHEN purchases.status='paid' THEN COALESCE(purchases.payment_amount, 0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'goods_amount': FieldDef('goods_amount', 'Сумма товаров (₽)', 'currency', 'computed', "CASE WHEN purchases.item_type='Товары' THEN COALESCE(purchases.planned_total_price, 0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'services_amount': FieldDef('services_amount', 'Сумма услуг (₽)', 'currency', 'computed', "CASE WHEN purchases.item_type='Услуги' THEN COALESCE(purchases.planned_total_price, 0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'wishes_unconfirmed_sum': FieldDef('wishes_unconfirmed_sum', 'Сумма желаний (не подтв.)', 'currency', 'computed', "CASE WHEN purchases.status='wishes' AND COALESCE(purchases.confirmed,false)=false THEN COALESCE(purchases.planned_total_price,0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),
    'confirmed_sum': FieldDef('confirmed_sum', 'Сумма подтверждённых', 'currency', 'computed', "CASE WHEN COALESCE(purchases.confirmed,false)=true THEN COALESCE(purchases.planned_total_price,0) ELSE 0 END", 'Computed', format='rub', is_measure=True, agg_default='sum', is_dimension=False),

    # === COMPUTED DIMENSIONS ===
    'quarter_of_obligation': FieldDef('quarter_of_obligation', 'Квартал обязательства', 'string', 'computed', "'Q' || EXTRACT(QUARTER FROM COALESCE(purchases.prepayment_date, purchases.service_deadline_date, purchases.service_end_date, purchases.execution_term))::text", 'Computed'),
    'year_of_obligation': FieldDef('year_of_obligation', 'Год обязательства', 'number', 'computed', "EXTRACT(YEAR FROM COALESCE(purchases.prepayment_date, purchases.service_deadline_date, purchases.service_end_date, purchases.execution_term))::int", 'Computed'),
    'month_of_obligation': FieldDef('month_of_obligation', 'Месяц обязательства', 'string', 'computed', "to_char(COALESCE(purchases.prepayment_date, purchases.service_deadline_date, purchases.service_end_date, purchases.execution_term), 'YYYY-MM')", 'Computed'),
    'quarter_of_payment': FieldDef('quarter_of_payment', 'Квартал оплаты', 'string', 'computed', "'Q' || EXTRACT(QUARTER FROM purchases.payment_doc_date)::text", 'Computed'),
    'year_of_payment': FieldDef('year_of_payment', 'Год оплаты', 'number', 'computed', "EXTRACT(YEAR FROM purchases.payment_doc_date)::int", 'Computed'),
    'month_of_payment': FieldDef('month_of_payment', 'Месяц оплаты', 'string', 'computed', "to_char(purchases.payment_doc_date, 'YYYY-MM')", 'Computed'),

    # === BANK PAYMENTS ===
    'bank_payment_number': FieldDef('bank_payment_number', 'Номер платёжки (банк)', 'string', 'bank_payment', 'bank_payments.payment_number', 'Банк'),
    'bank_payment_date': FieldDef('bank_payment_date', 'Дата платежа (банк)', 'date', 'bank_payment', 'bank_payments.payment_date', 'Банк'),
    'bank_purpose_text': FieldDef('bank_purpose_text', 'Назначение платежа', 'string', 'bank_payment', 'bank_payments.purpose_text', 'Банк'),
    'bank_kbk': FieldDef('bank_kbk', 'КБК', 'string', 'bank_payment', 'bank_payments.parsed_kbk', 'Банк'),
}


# Helpers
def get_field(key: str) -> 'Optional[FieldDef]':
    return FIELDS.get(key)


def list_fields() -> list:
    return list(FIELDS.values())


def list_groups() -> list:
    seen: list[str] = []
    for f in FIELDS.values():
        if f.group not in seen:
            seen.append(f.group)
    return seen


# Whitelist (для защиты от SQL-инъекций)
ALLOWED_KEYS = frozenset(FIELDS.keys())
ALLOWED_AGGS = frozenset(['sum', 'avg', 'count', 'count_distinct', 'min', 'max', 'first'])
