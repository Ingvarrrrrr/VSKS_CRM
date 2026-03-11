# Переменные шаблонов документов

## Основные поля закупки

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `purchase_number` | номер закупки | 1 |
| `registry_number` | реестровый номер | 12345 |
| `today` | текущая дата | 11.03.2026 |
| `total_nmck` | НМЦК (сумма позиций) | 100000 |
| `contract_price` | цена договора | 95000 |
| `economy` | экономия | 5000 |
| `purchase_method` | способ закупки | Единственный исполнитель |
| `execution_term` | срок исполнения | до 31.12.2026 |
| `status` | статус закупки | planned/confirmed/in_progress/contracted/delivered/paid |
| `country_origin` | страна происхождения | Россия |

## Договор

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `contract_number` | номер договора | 123 |
| `contract_date` | дата договора | 01.03.2026 |

## Субсидия

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `subsidy_name` | название субсидии | ФАДМ |
| `subsidy_year` | год субсидии | 2026 |

## Контрагент

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `contractor_name` | наименование | ООО "Ромашка" |
| `contractor_inn` | ИНН | 1234567890 |
| `contractor_kpp` | КПП | 123401001 |
| `contractor_ogrn` | ОГРН | 1234567890123 |
| `contractor_address` | юридический адрес | г. Москва, ул. Примерная, д.1 |
| `contractor_postal_address` | почтовый адрес | г. Москва, а/я 123 |
| `contractor_phone` | телефон | +7 (495) 123-45-67 |
| `contractor_email` | email | info@example.com |
| `contractor_signatory` | ФИО подписанта | Иванов И.И. |
| `contractor_signatory_basis` | должность подписанта | Генеральный директор |
| `contractor_bank_name` | наименование банка | ПАО Сбербанк |
| `contractor_bik` | БИК | 044525225 |
| `contractor_correspondent_account` | корр. счёт | 30101810400000000225 |
| `contractor_settlement_account` | расчётный счёт | 40703810138060100002 |
| `contractor_bank_details` | банковские реквизиты (строка) | ПАО Сбербанк, БИК 044525225 |

## Позиции (items) - для таблиц

| Переменная | Описание |
|-----------|----------|
| `items` | массив позиций |
| `item.num` | номер по порядку |
| `item.name` | наименование |
| `item.description` | описание |
| `item.type` | тип (товар/услуга/работа) |
| `item.quantity` | количество |
| `item.unit` | единица измерения |
| `item.unit_price` | цена за единицу |
| `item.total_price` | сумма |
| `item.photo` | фото (URL) |

## Согласующие (approvers) - для листа согласования

| Переменная | Описание |
|-----------|----------|
| `approvers` | массив согласующих |
| `a.num` | номер по порядку |
| `a.role_name` | должность |
| `a.full_name` | ФИО |

## Пример цикла в Word таблице

```
{%tr for item in items %}
{{item.num}} | {{item.name}} | {{item.quantity}} | {{item.unit}} | {{item.unit_price}} | {{item.total_price}}
{%tr endfor %}
```

## Пример использования в документе

```
Договор № {{contract_number}} от {{contract_date}}
Заказчик: {{contractor_name}}, ИНН {{contractor_inn}}
Сумма: {{contract_price}} руб.
```
