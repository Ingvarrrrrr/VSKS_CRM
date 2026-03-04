# Шаблоны документов

Поместите .docx файлы с именами:

| Файл | Документ |
|------|----------|
| `service_note.docx` | Служебная записка |
| `contract_tz.docx` | Договор + ТЗ |
| `approval_sheet.docx` | Лист согласования |

## Синтаксис шаблона (Jinja2)

Создайте .docx в Word и используйте переменные в фигурных скобках.

### Доступные переменные

| Переменная | Значение | Пример |
|-----------|---------|--------|
| `{{purchase_number}}` | № п/п | 42 |
| `{{registry_number}}` | Реестровый номер | РЕЕ-2026-00042 |
| `{{purchase_method}}` | Способ закупки | Единственный исполнитель |
| `{{status}}` | Статус | contracted |
| `{{subsidy_name}}` | Наименование субсидии | ФАДМ_2026 |
| `{{subsidy_year}}` | Год субсидии | 2026 |
| `{{subsidy_budget}}` | Бюджет субсидии | 15 500 000,00 ₽ |
| `{{contractor_name}}` | Наименование контрагента | ООО "Ромашка" |
| `{{contractor_inn}}` | ИНН | 7700000000 |
| `{{contractor_kpp}}` | КПП | 770000000 |
| `{{contractor_address}}` | Адрес | г. Москва, ул. ... |
| `{{feo_category_name}}` | Категория ФЭО | Компьютерное оборудование |
| `{{total_nmck}}` | НМЦК итого | 135 000,00 ₽ |
| `{{contract_price}}` | Цена договора | 130 000,00 ₽ |
| `{{economy}}` | Экономия | 5 000,00 ₽ |
| `{{price_increase}}` | Увеличение цены | |
| `{{contract_number}}` | Номер договора | 2026/42 |
| `{{contract_date}}` | Дата договора | 15.01.2026 |
| `{{execution_term}}` | Срок исполнения | 28.02.2026 |
| `{{execution_term_changed}}` | Изменённый срок | |
| `{{country_origin}}` | Страна происхождения | Российская Федерация |
| `{{acceptance_doc_name}}` | Наименование акта | Акт приёмки-передачи |
| `{{acceptance_doc_number}}` | № акта | 12 |
| `{{acceptance_doc_date}}` | Дата акта | 01.03.2026 |
| `{{acceptance_doc_amount}}` | Сумма акта | 130 000,00 ₽ |
| `{{payment_doc_number}}` | № платёжного поручения | 345 |
| `{{payment_doc_date}}` | Дата ПП | 05.03.2026 |
| `{{payment_amount}}` | Сумма платежа | 130 000,00 ₽ |
| `{{payment_federal}}` | в т.ч. федеральный бюджет | 130 000,00 ₽ |
| `{{today}}` | Сегодняшняя дата | 04.03.2026 |
| `{{items_count}}` | Количество позиций | 3 |

### Таблица позиций (цикл)

```
{% for item in items %}
{{ item.num }} | {{ item.name }} | {{ item.type }} | {{ item.quantity }} | {{ item.unit }} | {{ item.unit_price }} | {{ item.total_price }}
{% endfor %}
```

### Пример использования в Word

В тексте документа пишите: `{{contractor_name}}`
В ячейке таблицы: `{{contract_number}}`

Документация docxtpl: https://docxtpl.readthedocs.io
