# Доступные переменные для шаблонов договоров

Полный справочник Jinja2-переменных, которые подставляет `backend/app/routers/documents.py`
при генерации любого документа из закупки. Используйте `{{переменная}}` в шаблоне Word (.docx).

---

## 📑 Договор (общее)

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{contract_number}}` | Номер договора | 2026/15 | purchases.contract_number |
| `{{contract_date}}` | Дата договора | 28.04.2026 | purchases.contract_date |
| `{{contract_date_day}}` | День (с ведущим нулём) | 28 | purchases.contract_date |
| `{{contract_date_month}}` | Месяц прописью | апреля | purchases.contract_date |
| `{{contract_date_year}}` | Год | 2026 | purchases.contract_date |
| `{{contract_city}}` | Город заключения | Москва | фиксированное (по умолчанию Москва) |
| `{{contract_price}}` | Цена договора (с ₽) | 130 000,00 ₽ | purchases.contract_price |
| `{{contract_price_num}}` | Цена (без символа валюты) | 130 000,00 | purchases.contract_price |
| `{{contract_price_words}}` | Цена прописью | сто тридцать тысяч рублей 00 копеек | purchases.contract_price |
| `{{execution_term}}` | Срок исполнения (дата) | 28.02.2026 | purchases.execution_term |
| `{{contract_type}}` | Тип договора | Единственный поставщик | purchases.purchase_contract_type |

---

## 🏛 Заказчик (Customer) — Phase 23

Источник: `Organization`, которой принадлежит субсидия закупки (`subsidy.org_id`).
Банковские реквизиты берутся из связанного `Contractor` через `organization.contractor_id`.

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{customer_name}}` | Краткое наименование | ВСКС | organizations.name |
| `{{customer_full_name}}` | Полное наименование | Автономная некоммерческая организация... | organizations.full_name |
| `{{customer_short_name}}` | В кавычках из названия | ВСКС | извлекается из full_name/name |
| `{{customer_inn}}` | ИНН | 7700000001 | organizations.inn |
| `{{customer_kpp}}` | КПП | 770001001 | organizations.kpp |
| `{{customer_ogrn}}` | ОГРН | 1027700000001 | organizations.ogrn |
| `{{customer_address}}` | Юридический адрес | г. Москва, ул. Ленина, д. 1 | organizations.address или contractor.address |
| `{{customer_postal_address}}` | Почтовый адрес | 123456, г. Москва... | contractor.postal_address |
| `{{customer_bank_name}}` | Наименование банка | ПАО Сбербанк | contractor.bank_name (linked) |
| `{{customer_bik}}` | БИК банка | 044525225 | contractor.bik (linked) |
| `{{customer_settlement_account}}` | Расчётный счёт | 40701810000000000001 | contractor.settlement_account (linked) |
| `{{customer_correspondent_account}}` | Корреспондентский счёт | 30101810000000000225 | contractor.correspondent_account (linked) |
| `{{customer_phone}}` | Телефон | +7 (495) 000-00-00 | contractor.phone (linked) |
| `{{customer_email}}` | E-mail | info@vsks.ru | contractor.email (linked) |
| `{{customer_signatory}}` | Подписант (строка целиком) | Президент Козеев Евгений Викторович | organizations.signatory |
| `{{customer_signatory_position}}` | Должность подписанта | Президент | из signatory (до ФИО) |
| `{{customer_signatory_name}}` | ФИО подписанта | Козеев Евгений Викторович | из signatory |
| `{{customer_signatory_name_genitive}}` | ФИО в родительном падеже | Козеева Евгения Викторовича | автоматическое склонение (приближённое) |
| `{{customer_signatory_initials}}` | Е.В. Козеев | Козеев Е.В. | из signatory |
| `{{customer_signatory_basis}}` | Основание полномочий | Устава | contractor.signatory_basis (linked) |

> **Как заполнять:** реквизиты Заказчика редактируются в карточке Организации (Иерархия → клик на организацию)
> и в карточке связанного Контрагента (поле «contractor_id» в организации).

---

## 🏢 Исполнитель (Contractor)

Источник: `Contractor`, привязанный к закупке (`purchase.contractor_id`).

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{contractor_name}}` | Наименование | ООО «Ромашка» | contractors.name |
| `{{contractor_full_name}}` | Полное наименование | Общество с ограниченной... | contractors.full_name |
| `{{contractor_short_name}}` | В кавычках | Ромашка | извлекается из name |
| `{{contractor_org_type}}` | Тип организации | Юр.лицо / ИП / Самозанятый | contractors.org_type |
| `{{contractor_inn}}` | ИНН | 7700000002 | contractors.inn |
| `{{contractor_kpp}}` | КПП | 770001002 | contractors.kpp |
| `{{contractor_ogrn}}` | ОГРН | 1027700000002 | contractors.ogrn |
| `{{contractor_ogrnip}}` | ОГРНИП (только для ИП) | 304770000000001 | contractors.ogrn (если org_type=ИП) |
| `{{contractor_address}}` | Юридический адрес | г. Москва, ул. Садовая, д. 5 | contractors.address |
| `{{contractor_postal_address}}` | Почтовый адрес | 123456, г. Москва... | contractors.postal_address |
| `{{contractor_phone}}` | Телефон | +7 (495) 111-11-11 | contractors.phone |
| `{{contractor_email}}` | E-mail | info@romashka.ru | contractors.email |
| `{{contractor_signatory}}` | Подписант (строка) | Директор Сидоров Пётр Павлович | contractors.signatory |
| `{{contractor_signatory_basis}}` | Основание полномочий | Устава | contractors.signatory_basis |
| `{{contractor_signatory_position}}` | Должность | Директор | из signatory |
| `{{contractor_signatory_name}}` | ФИО подписанта | Сидоров Пётр Павлович | из signatory (Phase 23) |
| `{{contractor_signatory_name_genitive}}` | ФИО в родительном | Сидорова Петра Павловича | автоматическое склонение (Phase 23) |
| `{{contractor_signatory_initials}}` | Инициалы + фамилия | Сидоров П.П. | из signatory (Phase 23) |
| `{{contractor_signatory_line}}` | ФИО + основание (строка) | Сидоров П.П., действует на основании Устава | составное поле |
| `{{contractor_bank_name}}` | Банк | ПАО Сбербанк | contractors.bank_name |
| `{{contractor_bik}}` | БИК | 044525225 | contractors.bik |
| `{{contractor_settlement_account}}` | Расчётный счёт | 40702810000000000002 | contractors.settlement_account |
| `{{contractor_correspondent_account}}` | Корр. счёт | 30101810000000000225 | contractors.correspondent_account |

---

## 💰 Цена и НДС

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{vat_applicable}}` | НДС применяется? | true / false | purchases.vat_applicable |
| `{{vat_rate}}` | Ставка НДС, % | 20 | purchases.vat_rate |
| `{{vat_amount_num}}` | Сумма НДС (цифрами) | 21 666,67 | вычисляется: price × rate / (100+rate) |
| `{{vat_amount_words}}` | Сумма НДС прописью | двадцать одна тысяча... | вычисляется |
| `{{vat_exemption_article}}` | Статья освобождения от НДС | п.2 ст.346.11 НК РФ | purchases.vat_exemption_article |
| `{{vat_info_line}}` | Готовая строка НДС | В том числе НДС 20%: 21 666,67 руб. | составное поле |
| `{{total_nmcd}}` | НМЦД | 135 000,00 ₽ | purchases.total_nmck / nmck / planned_total_price |
| `{{economy}}` | Экономия | 5 000,00 ₽ | purchases.economy |

**Условный блок НДС в шаблоне:**
```
{% if vat_applicable %}
В том числе НДС {{vat_rate}}%: {{vat_amount_num}} ({{vat_amount_words}}) руб.
{% else %}
НДС не облагается на основании {{vat_exemption_article}}.
{% endif %}
```

---

## 📅 Сроки

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{service_term}}` | Готовая строка срока | с 01.05.2026 по 31.05.2026 | вычисляется по mode |
| `{{service_term_mode}}` | Режим срока | range / duration / deadline | purchases.service_term_mode |
| `{{service_term_days}}` | Количество дней (duration) | 30 | purchases.service_term_days |
| `{{service_term_type}}` | Тип дней | calendar / working | purchases.service_term_type |
| `{{service_term_type_name}}` | Тип дней по-русски | календарных / рабочих | из service_term_type |
| `{{service_start_date}}` | Дата начала | 01.05.2026 | purchases.service_start_date |
| `{{service_end_date}}` | Дата окончания | 31.05.2026 | purchases.service_end_date |
| `{{service_deadline_date}}` | Крайняя дата (deadline) | 30.06.2026 | purchases.service_deadline_date |
| `{{submission_deadline_date}}` | Дата завершения приёма заявок | 2026-04-25 | purchases.submission_deadline |
| `{{submission_deadline_time}}` | Время завершения приёма | 18:00 | purchases.submission_deadline |
| `{{submission_deadline_datetime}}` | Дата+время | 25.04.2026 18:00 | purchases.submission_deadline |

**Три режима `service_term` (используется в поле «Срок оказания Услуг»):**
```
range:    "с 01.05.2026 по 31.05.2026"
duration: "в течение 30 календарных дней после заключения договора"
deadline: "до 30.06.2026 включительно"
```

---

## ✅ Условия исполнения

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{third_party_involved}}` | Привлечение третьих лиц | true / false | purchases.third_party_involved |
| `{{subsidy_agreement_text}}` | Текст соглашения Минтруда | Соглашения № 149-2023... | subsidies.agreement_text |
| `{{delivery_location}}` | Место оказания услуг | г. Москва, ул. Ленина, д. 1 | purchases.delivery_location |

**Условный блок третьих лиц:**
```
{% if third_party_involved %}
с привлечением третьих лиц
{% else %}
своими силами, без привлечения третьих лиц
{% endif %}
```

**Условный блок тип организации (ИП vs. Юр.лицо):**
```
{%- if contractor_org_type == 'ИП' %}
ИП {{contractor_short_name}}, ОГРНИП {{contractor_ogrnip}}
{%- else %}
{{contractor_full_name}} ({{contractor_short_name}}), в лице {{contractor_signatory_position}}...
{%- endif %}
```

---

## 📦 Позиции закупки (таблица)

Используйте в строке таблицы Word с `{%tr for item in items %}` (docxtpl).

| Переменная | Описание | Пример |
|---|---|---|
| `{{item.num}}` | Порядковый номер строки | 1 |
| `{{item.name}}` | Наименование товара/услуги | Ежедневник А5 |
| `{{item.description}}` | Описание из карточки продукта | Ежедневник датированный... |
| `{{item.type}}` | Тип (товар/услуга) | товар |
| `{{item.quantity}}` | Количество | 50 |
| `{{item.unit}}` | Единица измерения | шт. |
| `{{item.unit_price}}` | Цена за единицу | 500,00 ₽ |
| `{{item.total_price}}` | Сумма строки | 25 000,00 ₽ |
| `{{item.photo}}` | Фото товара (картинка inline) | [изображение] |
| `{{items_count}}` | Общее количество позиций | 3 |
| `{{item_names}}` | Перечень названий через запятую | Ежедневник А5, Ручка Parker |

**Шаблон строки таблицы Word:**
```
{%tr for item in items %}
{{item.num}} | {{item.name}} | {{item.quantity}} | {{item.unit}} | {{item.unit_price}} | {{item.total_price}}
{%tr endfor %}
```

---

## 🏷 Закупка (общее)

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{purchase_number}}` | Номер закупки | 42 | purchases.purchase_number |
| `{{registry_number}}` | Реестровый номер | РЕЕ-2026-00042 | purchases.registry_number |
| `{{purchase_method}}` | Способ закупки | Единственный поставщик | purchases.purchase_method |
| `{{subject}}` | Предмет закупки | Оказание полиграфических услуг | purchases.subject |
| `{{service_name}}` | Синоним subject | — | purchases.subject |
| `{{service_name_gen}}` | Предмет в родительном падеже (для «Прошу осуществить закупку ...») | канцелярских принадлежностей | inflect(subject) |
| `{{purchase_basis}}` | Основание | план-график | purchases.purchase_basis |
| `{{responsible_person}}` | Ответственный исполнитель | Иванов А.А. | purchases.responsible_person |
| `{{subsidy_name}}` | Субсидия | ФАДМ_2026 | subsidies.name |
| `{{subsidy_year}}` | Год субсидии | 2026 | subsidies.year |
| `{{subsidy_budget}}` | Бюджет субсидии | 15 500 000,00 ₽ | subsidies.budget |
| `{{event_name}}` | Название мероприятия | Всероссийский форум | events.name |
| `{{feo_category_name}}` | Категория ФЭО | Полиграфия | feo_categories.name |
| `{{feo_path}}` | Путь ФЭО (root→leaf) | Расходы → Полиграфия | вычисляется |

---

## ⚙️ Технические

| Переменная | Описание | Пример | Источник |
|---|---|---|---|
| `{{today}}` | Сегодняшняя дата | 04.05.2026 | date.today() |
| `{{today_iso}}` | ISO-дата | 2026-05-04 | date.today() |

---

## 💡 Как использовать шаблоны

### Встроенные шаблоны

| Файл | doc_type | Документ |
|---|---|---|
| `contract_services.docx` | `contract_services` | Договор оказания услуг (Phase 23) |
| `contract.docx` | `contract` | Договор поставки |
| `contract_tz.docx` | `contract_tz` | ТЗ (общий шаблон; договор отдельно через contract.docx) |
| `approval_sheet.docx` | `approval_sheet` | Лист согласования |
| `service_note_procurement.docx` | `service_note_procurement` | СЗ на закупку |
| `tech_spec_request.docx` | `tech_spec_request` | ТЗ для запроса цен |
| `tech_spec_contract.docx` | `tech_spec_contract` | ТЗ для договора |
| `order_purchase.docx` | `order_purchase` | Приказ о закупке |

### Кастомный шаблон для субсидии

1. Скачайте `contract_services.docx` или любой другой шаблон.
2. Откройте в MS Word, замените текст на `{{переменная}}` или используйте `{% if/else %}` для условий.
3. Загрузите шаблон через «Субсидии → [субсидия] → Шаблоны документов».
4. При генерации документа из закупки переменные подставятся автоматически.

### Источники данных

| Данные | Откуда |
|---|---|
| **Заказчик** | Организация субсидии закупки → её Контрагент-обёртка (FK по contractor_id) |
| **Исполнитель** | Контрагент закупки (purchases.contractor_id) |
| **Цена/Срок/НДС** | Поля закупки (секция «Параметры договора (для документа)» в карточке закупки) |
| **Реквизиты Заказчика** | Редактируются в карточке Организации (Иерархия → клик на организацию) |

### Частые ошибки

| Ошибка | Причина | Решение |
|---|---|---|
| «Ошибка генерации» | Русский текст внутри `{{ }}` | Вынести за скобки: `{{ contract_date }} г.` |
| Переменная не подставляется | Word разбил текст на части | Удалить и набрать переменную заново одним блоком |
| Пустое значение | Поле не заполнено в закупке | Заполнить в карточке закупки |
| `{{customer_bank_name}}` пустой | Нет linked Contractor у организации | Привязать контрагента в карточке организации |

---

> Документация движка шаблонов: https://docxtpl.readthedocs.io
> Регенерация шаблона: `py backend/templates/make_contract_services.py`
