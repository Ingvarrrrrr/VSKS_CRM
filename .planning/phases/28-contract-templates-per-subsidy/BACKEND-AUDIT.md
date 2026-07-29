# Phase 28 — Backend Audit: Contract Templates Per-Subsidy

_Дата аудита: 2026-05-19_

---

## DOC_TYPES (документы)

Источник: `backend/app/routers/documents.py:276`

| Key | Файл шаблона | Русское название | Примечание |
|---|---|---|---|
| `service_note_delivery` | `service_note_delivery.docx` | СЗ на выдачу | — |
| `service_note_payment` | `service_note_payment.docx` | СЗ на оплату | — |
| `service_note_procurement` | `service_note_procurement.docx` | СЗ на закупку | fallback → `service_note.docx` |
| `service_note_advance` | `service_note_advance.docx` | СЗ на аванс | fallback → `service_note.docx` |
| `contract_tz` | `contract_tz.docx` | ТЗ (общий, legacy) | legacy — оставлен для обратной совместимости |
| `tech_spec` | `contract_tz.docx` | ТЗ (alias) | resolves to same contract_tz.docx |
| `tech_spec_request` | `tech_spec_request.docx` | ТЗ для запроса цен | fallback → `contract_tz.docx` |
| `tech_spec_contract` | `tech_spec_contract.docx` | ТЗ для договора | fallback → `contract_tz.docx` |
| `contract` | `contract.docx` | Договор (универсальный) | тип товар/услуга auto-detect |
| `approval_sheet` | `approval_sheet.docx` | Лист согласования | — |
| `order_purchase` | `order_purchase.docx` | Приказ на закупку | — |

Endpoint: `GET /api/purchases/{pid}/documents/{doc_type}` (documents.py:769)

Дополнительный fallback map `DOC_TYPE_FALLBACK_FILES` (documents.py:304):
```
service_note_procurement → service_note.docx
service_note_advance     → service_note.docx
tech_spec_request        → contract_tz.docx
tech_spec_contract       → contract_tz.docx
```

---

## SUPPORTED_DOC_TYPES (загружаемые через UI SubsidiesView)

Источник: `backend/app/routers/subsidies.py:453`

```python
SUPPORTED_DOC_TYPES = {
    "contract":                 "Договор",
    "contract_tz":              "ТЗ (общий шаблон)",
    "service_note_delivery":    "СЗ на выдачу",
    "service_note_payment":     "СЗ на оплату",
    "service_note_procurement": "СЗ на закупку",
    "service_note_advance":     "СЗ на аванс",
    "tech_spec_request":        "ТЗ для запроса цен",
    "tech_spec_contract":       "ТЗ для договора",
    "approval_sheet":           "Лист согласования",
    "order_purchase":           "Приказ на закупку",
}
```

**Разрыв с DOC_TYPES в documents.py:** `tech_spec` и `contract_tz` присутствуют в `DOC_TYPES` (documents.py) но `tech_spec` **отсутствует** в `SUPPORTED_DOC_TYPES`. Это намеренно — `tech_spec` — deprecated alias, UI его не показывает.

Эндпоинты управления шаблонами (subsidies.py):
- `GET  /api/subsidies/{id}/templates` — список с флагами `has_custom`/`has_global`
- `PUT  /api/subsidies/{id}/templates/{doc_type}` — upload
- `GET  /api/subsidies/{id}/templates/{doc_type}/download` — скачать
- `DELETE /api/subsidies/{id}/templates/{doc_type}` — удалить

Пути хранения:
- Глобальные: `/app/templates/{doc_type}.docx`
- Per-subsidy: `/app/uploads/templates/subsidies/{subsidy_id}/{doc_type}.docx`

---

## Context builders

### `generate_document(...)` — основная функция, один монолитный builder

Нет отдельной функции `_build_context`. Весь контекст собирается inline в `generate_document` (documents.py:1081–1556).

### `_build_acceptance_doc_context(p, doc_type, doc_indices_csv)` → dict (documents.py:380)

Для `service_note_payment` / `service_note_advance`:
- Читает `p.acceptance_docs` (JSONB — source of truth после Phase 26-H)
- Поддерживает фильтрацию по `doc_indices` (CSV индексов)
- Суммирует amount всех выбранных docs

Legacy fallback (все остальные doc_type ИЛИ если JSONB пустой):
- Читает `p.acceptance_doc_name`, `p.acceptance_doc_number`, `p.acceptance_doc_date`, `p.acceptance_doc_amount`

**Ключи контекста:**
```
acceptance_doc_name, acceptance_doc_number, acceptance_doc_date, acceptance_doc_amount
```

### `_build_contract_items_context(p, db)` → dict (documents.py:447)

**Ключи контекста:**
```
contract_items           — list[{num, name, quantity, unit, unit_price, total, total_numeric}]
contract_items_total     — форматированная сумма
contract_items_total_numeric — float
contract_item_count      — int
```
Primary path: `ContractItem` модель. Fallback (D-08): `purchase_items` если ContractItem пустые.

### Полный список ключей основного контекста (documents.py:1313–1556)

```
# Закупка
purchase_number, registry_number, purchase_method, subject, status, purchase_basis, responsible_person

# Субсидия
subsidy_name, subsidy_year, subsidy_budget, subsidy_agreement_text

# Контрагент — основные
contractor_name, contractor_inn, contractor_kpp, contractor_address, contractor_postal_address
contractor_ogrn, contractor_phone, contractor_email, contractor_org_type
contractor_short_name  (= c.name напрямую, без извлечения из кавычек — Phase 27.2-08)
contractor_full_name

# Контрагент — подписант
contractor_signatory, contractor_signatory_basis, contractor_signatory_line
contractor_signatory_position, contractor_signatory_name
contractor_signatory_name_genitive, contractor_signatory_initials
contractor_ogrnip  (только для ИП)

# Контрагент — банк
contractor_settlement_account, contractor_bank_name, contractor_bik
contractor_correspondent_account, contractor_bank_details

# FEO
feo_category_name, feo_path, feo_level_1, feo_level_2, feo_level_3

# Финансы
total_nmcd, total_nmck (deprecated alias), nmck
contract_price, contract_price_num, contract_price_words
economy, price_increase
vat_applicable, vat_rate, vat_amount_num, vat_amount_words, vat_exemption_article, vat_info_line

# Договор
contract_number, contract_date
contract_date_day, contract_date_month, contract_date_year
execution_term, execution_term_changed, delivery_date, country_origin
contract_type, contract_city  (всегда "Москва" — TODO per-org Phase 28?)
service_period_type, service_start_date, service_end_date, service_date
service_term, service_term_mode, service_term_days, service_term_type
service_term_type_name, service_deadline_date
submission_deadline_date, submission_deadline_time, submission_deadline_datetime
delivery_location, period_type

# Предмет
service_name, service_name_gen, service_subject, subject_kind ("goods"/"services" auto-detect)

# Акт приёмки (из _build_acceptance_doc_context)
acceptance_doc_name, acceptance_doc_number, acceptance_doc_date, acceptance_doc_amount

# Платёж
payment_doc_number, payment_doc_date, payment_amount, payment_federal

# Позиции (items loop)
items             — list[{num, name, description, type, item_kind, quantity, unit, unit_price, total_price, photo}]
items_count, item_names, item_categories

# Contract items (из _build_contract_items_context)
contract_items, contract_items_total, contract_items_total_numeric, contract_item_count

# Согласующие (approvers loop)
approvers         — list[{num, role_name, full_name, signature_img, decided_date, note, full_name_gen, role_name_gen}]

# Инициатор
initiator_name, initiator_name_gen
initiator_role, initiator_position_gen
initiator_dept, initiator_dept_gen

# Заказчик (Organization + linked Contractor)
customer_name, customer_full_name, customer_short_name, customer_address, customer_postal_address
customer_inn, customer_kpp, customer_ogrn
customer_bank_name, customer_settlement_account, customer_correspondent_account, customer_bik
customer_phone, customer_email
customer_signatory, customer_signatory_position, customer_signatory_name
customer_signatory_name_genitive, customer_signatory_initials, customer_signatory_basis

# Чеки (advance report only)
receipts, receipt_images, receipts_small, receipts_full
receipt_pairs, left_receipts, right_receipts, receipts_table

# Ответственный
responsible_person, responsible_name_gen, responsible_position_gen

# Мероприятие
event_name

# Служебные
today, today_iso, third_party_involved
```

### Кто читает `acceptance_doc_*` legacy vs JSONB `acceptance_docs`?

| Поле | Источник | Когда используется |
|---|---|---|
| `p.acceptance_docs` (JSONB) | source of truth после Phase 26-H | `service_note_payment`, `service_note_advance` |
| `p.acceptance_doc_name/number/date/amount` (plain columns) | legacy fallback | все остальные doc_type, или если JSONB пустой |

---

## Логика выбора шаблона

Алгоритм (documents.py:785–828):

1. `template_path = TEMPLATES_DIR + DOC_TYPES[doc_type][0]`  — глобальный шаблон
2. Если файл не существует → проверить `DOC_TYPE_FALLBACK_FILES[doc_type]` → взять legacy
3. Если ни одного нет → HTTP 404
4. После загрузки purchase: если `p.subsidy_id` → проверить `/app/uploads/templates/subsidies/{subsidy_id}/{doc_type}.docx`
   - Если существует → **override** `template_path` на кастомный per-subsidy шаблон

Файл: `documents.py:785–828`

Ошибки рендеринга (documents.py:1656–1678):
- Если кастомный шаблон упал с `TemplateSyntaxError` → **auto-fallback** на базовый `TEMPLATES_DIR/{doc_type}.docx` с предупреждением в лог.

### `_repair_docx_template(path)` — что чинит (subsidies.py:564)

Вызывается при **upload** шаблона через SubsidiesView. Чинит:
1. `{{ var русский_текст }}` → `{{ var }} русский_текст` — Word разрывает Jinja-теги на несколько XML runs
2. `{{русский_текст}}` → убирает маркеры, оставляет текст (нет ни одного ASCII-идентификатора)
3. `{% русский_текст %}` → убирает маркеры если не Jinja-keyword
4. `г. г.` doubled text fix после предыдущих правок
5. Итог: пересохраняет .docx. Затем вызывает `DocxTemplate.get_undeclared_template_variables()` для валидации.

### `_normalize_docx_template(path)` — что чинит (subsidies.py:~490)

Также вызывается при upload. Удаляет из XML:
- `<w:proofErr>` (spell/grammar check markers)
- `<w:bookmarkStart>` / `<w:bookmarkEnd>` (Word bookmarks)
- `<w:commentRangeStart/End>`, `<w:commentReference>` (комментарии)
- `<w:lastRenderedPageBreak>` (page break hints)

Зачем: эти теги разрывают контент Jinja-переменных на несколько XML runs → docxtpl не может их резолвить.

---

## БД — список субсидий

**SSH заблокирован (timeout)**, локальный контейнер не запущен → данные недоступны напрямую.

### Известно из `типовые документы/` (образцы договоров):

| Папка | Описание | Типы договоров |
|---|---|---|
| `ФАДМ/` | Федеральное агентство по делам молодёжи | услуги (большая/малая отчётность), поставка (разовый), ГПХ самозанятый ±РИД, ГПХ физ.лицо ±РИД, ремонт ТС |
| `Минпрос/` | Министерство просвещения | услуги (большая/малая/питание), поставка (разовый) |
| `Минтруд/` | Министерство труда | услуги (большая/малая/питание), поставка (разовый), ГПХ самозанятый ±РИД, ГПХ физ.лицо ±РИД |
| `Регионы/` | Региональные субсидии | поставка, СЗ на закупку (образец) |

**Для получения `id` субсидий** необходимо выполнить запрос на проде:
```sql
SELECT id, name, year, org_id FROM subsidies ORDER BY id;
```
→ Команда: `ssh root@85.239.53.155 "docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -c \"SELECT id, name, year, org_id FROM subsidies ORDER BY id\""`

---

## БД — custom-uploaded шаблоны

Шаблоны хранятся **на файловой системе**, не в БД. Нет таблицы `subsidy_templates`.

Хранилище: `/app/uploads/templates/subsidies/{subsidy_id}/{doc_type}.docx`
Список загруженных шаблонов определяется наличием файлов на диске (subsidies.py:479–484).

**Нет модели ORM** типа `SubsidyTemplate` — grep по `class.*Template` в `backend/app/models/` ничего не дал.

Для аудита загруженных шаблонов на проде:
```bash
find /app/uploads/templates/subsidies -name "*.docx" | sort
```

---

## Frontend

### CreateOrderView — кнопки документов (CreateOrderView.vue)

| Кнопка | `downloadDoc(...)` | Параметры |
|---|---|---|
| Скачать ТЗ → ТЗ для запроса цен | `downloadDoc('tech_spec_request')` | — |
| Скачать ТЗ → ТЗ для договора | `downloadDoc('tech_spec_contract')` | — |
| Договор | `downloadDoc('contract')` | — |
| Договор + ТЗ (merge) | `downloadDoc('contract', '?merge=tech_spec_contract', 'contract_merge')` | merge=tech_spec_contract |
| СЗ → На закупку | `openDocPicker('service_note_procurement')` | → `downloadDoc` с `initiator_id` |
| СЗ → На выдачу | `openDocPicker('service_note_delivery')` | → `downloadDoc` с `initiator_id` |
| СЗ → На оплату | `openDocPicker('service_note_payment')` | → acceptance doc picker → `downloadDoc` с `doc_indices` |
| СЗ → На аванс | `openDocPicker('service_note_advance')` | → acceptance doc picker → `downloadDoc` с `doc_indices` |
| Лист согласования | `openDocPicker('approval_sheet')` | → `downloadDoc` с `approver_ids` + `responsible_name` |

`order_purchase` (Приказ на закупку) — есть в `DOC_TYPES` и `SUPPORTED_DOC_TYPES`, но **нет кнопки** в `CreateOrderView.vue`. Видимо генерируется только как per-subsidy шаблон без прямой кнопки в UI.

### SubsidiesView — список doc_type в диалоге шаблонов

`subsidyTemplatesList` загружается с **сервера** через `GET /api/subsidies/{id}/templates` (SubsidiesView.vue:3889–3892). Список строится из `SUPPORTED_DOC_TYPES` на бэкенде — **не хардкод** во фронтенде. Пользователь видит именно те типы, что перечислены в `subsidies.py:SUPPORTED_DOC_TYPES`.

### Модель Purchase — есть ли поле формы договора?

**Нет** — ни `contract_form`, ни `template_key`, ни `template_kind`, ни `contract_template` в `backend/app/models/purchase.py` не существует. Выбор шаблона производится исключительно по `subsidy_id` закупки (файловая система per-subsidy).

---

## Рекомендации для Phase 28

### Что точно нужно добавить

#### 1. Новые `doc_type` ключи для вариантов договора

Из образцов в `типовые документы/`:

| Новый `doc_type` | Описание | Оба DOC_TYPES и SUPPORTED_DOC_TYPES |
|---|---|---|
| `contract_services_large` | Услуги — большая отчётность | оба |
| `contract_services_small` | Услуги — малая отчётность | оба |
| `contract_services_food` | Услуги — питание/малая отчётность | оба |
| `contract_goods_single` | Поставка — разовый договор | оба |
| `contract_gph_self_employed` | ГПХ с самозанятым (без РИД) | оба |
| `contract_gph_self_employed_rid` | ГПХ с самозанятым (+РИД) | оба |
| `contract_gph_individual` | ГПХ с физ. лицом (без РИД) | оба |
| `contract_gph_individual_rid` | ГПХ с физ. лицом (+РИД) | оба |
| `contract_repair_vehicle` | Договор на ремонт ТС | оба |

Альтернативный подход: добавить `contract_form` поле в `Purchase` (varchar: `services_large`/`services_small`/`goods`/`gph`/...) и выбирать шаблон по `{doc_type}_{contract_form}` — более гибко.

#### 2. Новые ключи переменных в контексте

Для договоров ГПХ с физ.лицом и самозанятым нужны:
```
contractor_passport_series, contractor_passport_number, contractor_passport_issued_by
contractor_passport_issued_date, contractor_registration_address
contractor_bank_account_type  ("расчётный" vs "карточный счёт")
```

Для РИД-договоров:
```
rid_description, rid_transfer_type
```

#### 3. UI-селектор формы договора

В `CreateOrderView.vue` добавить поле `form.contract_form` (v-select) с вариантами, зависящими от `subsidy.org` (ФАДМ / Минпрос / Минтруд). Кнопка «Договор» должна использовать выбранную форму для выбора шаблона.

Либо: кнопка «Договор» открывает меню со списком доступных для данной субсидии форм договора.

#### 4. Новое поле `Purchase.contract_form`

```python
contract_form = Column(String(50), nullable=True)
# 'services_large' | 'services_small' | 'services_food' | 'goods_single'
# | 'gph_self_employed' | 'gph_self_employed_rid'
# | 'gph_individual' | 'gph_individual_rid' | 'repair_vehicle'
```

Требуется Alembic-миграция.

### Что менять страшно (migration risk)

1. **DOC_TYPES dict в documents.py** — любой `doc_type` ключ который уже загружен в per-subsidy шаблоны на проде (файлы в `/app/uploads/templates/subsidies/*/`) нельзя переименовывать. Переименование = старые загруженные файлы больше не найдутся.

2. **`contract`** ключ — самый рискованный: используется как универсальный (subject_kind auto-detect). Не трогать.

3. **`contract_tz`** — legacy, оставить в SUPPORTED_DOC_TYPES для обратной совместимости с уже загруженными шаблонами.

4. **`tech_spec` alias** в DOC_TYPES — только в documents.py, не в SUPPORTED_DOC_TYPES. Безопасен: фронтенд его не показывает.

5. **SUBSIDY_TEMPLATES_DIR** = `/app/uploads/templates` — это Docker volume. Если переименовать папку или изменить схему, все загруженные шаблоны станут недоступны. Phase 28 должна добавлять новые ключи без удаления старых.

### Migration risk summary

| Изменение | Риск | Рекомендация |
|---|---|---|
| Добавить новые `doc_type` в оба словаря | Низкий | Просто добавить |
| Добавить `Purchase.contract_form` колонку | Средний | Alembic migration, nullable |
| Добавить новые ключи в контекст (`contractor_passport_*`) | Низкий | Только добавление |
| Переименовать существующий `doc_type` | ВЫСОКИЙ | ЗАПРЕЩЕНО без миграции файлов на диске |
| Удалить `contract_tz` из SUPPORTED_DOC_TYPES | Средний | Только если нет загруженных overrides |
| Менять логику `subject_kind` в `contract` | Средний | Протестировать шаблоны |

---

## Технические детали

- `backend/app/routers/documents.py` — 2000+ строк, DOC_TYPES:276, generate_document:769
- `backend/app/routers/subsidies.py` — SUPPORTED_DOC_TYPES:453, _repair:564, _normalize:~490
- `backend/app/routers/wish_documents.py` — отдельный роутер для wishes, **нет своих DOC_TYPES**, reuses `TEMPLATES_DIR` и formatters из documents.py
- `backend/app/models/purchase.py` — модель Purchase, нет поля contract_form
- `frontend/src/views/CreateOrderView.vue` — все кнопки документов
- `frontend/src/views/SubsidiesView.vue` — диалог шаблонов (subsidyTemplatesList загружается с бэка)
- `типовые документы/ФАДМ/`, `Минпрос/`, `Минтруд/`, `Регионы/` — образцы для Phase 28
