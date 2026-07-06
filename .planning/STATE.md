---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Фидбек-кластер 2026-06-24 pushed (UAT pending)
last_updated: "2026-06-24T00:00:00.000Z"
progress:
  total_phases: 21
  completed_phases: 13
  total_plans: 95
  completed_plans: 90
  percent: 80
---

# STATE.md — VSKS_CRM

## Current Position

Режим: LOCAL-dev → push в `claude` (autodeploy). Итеративный фидбек тестировщика.
Last push: `8c340b0` (фидбек-кластер 22-24 июня, 35 файлов) + `30792a1` (mobile nav).
Next action: UAT фидбек-кластера на проде (см. 04_TODO) + pending фазы (29 / 27.1.x / 26-I / 25).

## 2026-06-24 — Фидбек-кластер 22-24 июня PUSHED ✅

Один пакет `8c340b0` (+2538/−486, 35 файлов) → autodeploy. 5 задач от тестировщика Лягина:
- **Филиппов в Сотрудниках** — `users.py` `or_()`-union (org_id + user_organizations + user_org_access).
- **По-уровневая пропагация ФЭО** — `FeoCascadeSelect` эмитит узел на КАЖДОМ уровне; UI-only `feo_node_id` отдельно от листового `feo_category_id`; пропагация позиции на все выбранные строки (3 view).
- **Ширина expand-row** — per-item атрибуты в full-width sub-row, каскад горизонтальный (no-scroll).
- **Поиск по графу иерархии** — pill-поиск (#fb923c), подсветка + вьющаяся стрелка `matchPointer()` + `fitView`; тёмная тема (убран `bg-color="white"`), кнопки blue/purple.
- **Экспорт реестров** — generic `report_excel/pdf` + `exports.py` (`/api/exports/*`), `useRegistryExport.ts` + `RegistryExportButton.vue` в 8 реестрах; фикс 401 (токен `auth_token`).

Проверки: vue-tsc EXIT=0, Python AST OK, пересборка фронта, рестарт backend. Pre-push: новых миграций/колонок нет → 502-риска нет.

## 2026-05-19 — Phase 29 EXECUTED ✅ Vehicle Fleet (21/21 plans, 25 коммитов)

## 2026-05-19 — Phase 29 EXECUTED ✅ Vehicle Fleet (21/21 plans, 25 коммитов)

`gsd-executor` (Sonnet) × 21 параллельных/sequential волн → все 21 плана выполнены, **25 atomic commits** (`ac982c9..be45939`) pushed → autodeploy.

**Wave summary:**
- **W0 (sequential):** 29-01 `ac982c9` (9 моделей) → 29-02 `0462ab6` (check_schema 9 таблиц + ALTER) → 29-03 `463c62b` (permissions seed)
- **W1 (×7 parallel + finalize):** 29-04 `96ffd27` vehicles CRUD, 29-05 `93dd185` attachments, 29-06 `7a97968` repairs, 29-07 `dadb8fb` odometer+fuel, 29-08 `b0838e6` trips+stubs, 29-09 `1a81c7a` external_drivers, 29-10 `9474b8f` dashboard endpoints + `7cd0fdc` register 9 routers
- **W1.5 (×3 parallel):** 29-11 `cb047dd` seed xlsx Голичкова, 29-12 `c86815d` import router, 29-13 `8892624` alerts cron (TaskStatus enum compliance verified)
- **W2 (×3 parallel):** 29-14 `3511447` AppBar+router, 29-15 `4edf179` StaffView can_drive, 29-16 `cb22b08` VehicleListView
- **W3:** 29-17 `aa44b91` VehicleDetailView shell + FieldHistoryPopover
- **W3.5 (×8 parallel + wire):** 29-18a `7e1afa4` Documents, 29-18b `fb813ec` Photos, 29-18c `d21682c` Repairs, 29-18d `bcc087f` Odometer, 29-18e `6169afb` FuelLog, 29-18f `40b42d5` Trips, 29-18g `eb63a9d` RelatedPurchases, 29-18h `51ca5f5` History + `6544b56` wire-up
- **W4 (×3 parallel + main):** 29-19a `bf29179` FuelCanister SVG, 29-19b `7af1e83` MaintenanceWarning pulse-glow, 29-19c `2a9ee5c` VehiclesInRepair + 29-19d `6c75d66` VehicleDashboardView main
- **W5 (×2 parallel):** 29-20 `f867196` real .docx templates (smoke-render passed) + `be45939` SUMMARY, 29-21 `418d5d1` Purchase.vehicle_id integration

**D-01..D-20 — all 20 decisions delivered.**

**Architectural notes:**
- TaskStatus enum compliance: 29-13 использует только `[todo, in_progress, review]` для open status check (no phantom `planned`)
- ENUMs хранятся как VARCHAR (не PG ENUM types) — DO blocks не понадобились
- system_tag column добавлен в Task (ALTER) — для идемпотентных авто-Tasks
- 3 stub trip docx templates от 29-08 заменены реальными Минтранс formами в 29-20 (smoke-render всех 3 прошёл)
- Plate как unique key seed (VIN часто «отсутствует» в xlsx Голичкова)
- ENUM mapping для VehicleType учитывает все 14 типов из xlsx (car_light/minivan/truck_*/special/bus/quadbike/snowmobile/boat/boat_motor/trailer/other)
- 11 dashboard виджетов (4 KPI + 3 custom + 4 ApexCharts) в grid-layout-plus с per-user localStorage

**UAT pending Phase 29 (требует пользователь на проде):**
1. AppBar «Имущество» (mdi-warehouse) видна → submenu Автотранспорт/Оборудование/Прочее
2. `/property/vehicles` → 51 ТС из реестра Голичкова после seed-on-boot
3. Импорт Excel: preview → region→org dialog → commit
4. VehicleDetailView 9 tabs: Общее/Документы/Фото/Ремонты/Пробег/Заправки/Путёвки/История/Связанные закупки
5. SVG канистра «плещется», карточки с просрочкой ТО «светятся» pulse-glow
6. Путевые листы скачиваются для 3 типов ТС (легковой/грузовой/специальный)
7. StaffView чекбокс «Может водить ТС» раскрывает 6 полей ВУ + медсправка
8. CreateOrderView показывает селект «Автомобиль» если subject содержит ремонт/заправка/ОСАГО keywords
9. Auto-Tasks за 30 дней до OSAGO/ТО/license/medical expiry создаются в lifespan cron



# STATE.md — VSKS_CRM

## Current Position

Phase: 29 (Vehicle Fleet)
Plan: 21 plans created (29-01..29-21), PASS WITH NOTES (7 warning, 0 blocker)
Next action: `/gsd:execute-phase 29` (Wave 0 → 1/1.5 → 2 → 3 → 3.5 → 4 → 5). Параллельно UAT 27.1.x, 26-I, 25 (16 пунктов Report Builder).
Resume file: None
Plan review: .planning/phases/29-vehicle-fleet/PLAN-REVIEW.md (avg 11.71/12)
Baseline rollback Phase 26-E: `ae1cddd` (git revert --no-edit ae1cddd..HEAD && git push)

## 2026-05-19 — Phase 29 planned ✅ Vehicle Fleet (21 plans)

`gsd-pattern-mapper` (Haiku) + `gsd-phase-researcher` (Sonnet) → 35/45 patterns mapped + 12 R-items resolved.
`gsd-planner` (Opus) → 21 PLAN.md files, 7 волн (0/1/1.5/2/3/3.5/4/5).
`gsd-plan-checker` (Opus) → PASS WITH NOTES, avg score 11.71/12.

**Coverage:** D-01..D-20 — все 20 решений покрыты ≥1 планом. 35/35 файлов из PATTERNS.md ассигнованы планам. 12/12 R-items из RESEARCH.md отражены в task'ах.

**Wave plan (зависимости):**

- W0 (sequential): 29-01 (models) → 29-02 (check_schema) → 29-03 (permissions)
- W1 (7 параллельно): 29-04..29-10 (CRUD routers)
- W1.5 (3 параллельно): 29-11 (seed), 29-12 (import), 29-13 (alerts cron)
- W2 (3 параллельно): 29-14 (AppBar+router), 29-15 (StaffView can_drive), 29-16 (VehicleListView)
- W3: 29-17 (VehicleDetailView shell)
- W3.5: 29-18 (8 tab components)
- W4: 29-19 (VehicleDashboardView + canister + pulse-glow)
- W5: 29-20 (real .docx templates), 29-21 (Purchase ?vehicle_id integration)

**Warnings to address during execution:**

- W1-W3 (29-13): TaskStatus enum strings — открыть `backend/app/models/task.py` ДО выполнения 29-13, зафиксировать exact enum values
- W6 (29-19): «8 виджетов» в D-16 раскрыты до 11 (4 KPI = 1 «виджет» в decision, но 4 карточки на UI)
- W7 (29-18): размер плана — может потребоваться разбить на 29-18a/18b если context budget превышен

## 2026-05-14 — Phase 26-I ✅ Фидбек 14 мая по фазе 26 (12 коммитов)

`de78162..47c9abf` → push в `claude`. 5 параллельных Sonnet-агентов, непересекающиеся scope. Подробности в `VAULT_for_LLM/Projects/VSKS_CRM/Sessions/2026-05-14_VSKS_CRM.md`.

**Кластеры:**

- **1a/1b** ColumnHeaderMenu стрелка справа + фильтр purchase_type на реальных ключах БД
- **2** Накопительный договор без max_amount → счётчик (без отрицательного остатка)
- **3** Диалог шаблонных переменных 1100px + nowrap
- **4** Combobox типов закр. документов — удаление кастомных через крестик
- **5** ContractorsView «Открыть карточку» работает (nextTick + GET fallback)
- **7a-g** Multi-dept big pack: per-row position, DnD move с remove-from-old, cascade DELETE org-membership, org-color border, UserAvatar с photo_url + square, DepartmentsView UNION фильтр

**Архитектурные решения:**

- `PATCH /api/users/{uid}/org-memberships/{row_id}` — per-row position update (не bulk по org)
- `DELETE /api/users/{uid}/organizations/{org_id}` cascade: user_organizations + department_members
- DepartmentsView `/departments/tree` UNION (DepartmentMember ∪ UserOrganization.dept_id)
- Новый `UserAvatar.vue` с prop `square`

## 2026-05-14 — Phase 27 context gathered ✅ + Phase 27.1 inserted

Discuss-phase 27 завершён, 19 решений D-01..D-19 + 3 Claude's Discretion. Ключевое: введён промежуточный слой `contract_items` (Phase 27.1, ВСТАВЛЕНА В ROADMAP ПЕРЕД 27) на основании фидбека «три стадии: ТЗ/Договор/Поставка». Phase 27 теперь зависит от Phase 27.1 через `delivery_items.contract_item_id` FK.

**Артефакты:**

- `.planning/phases/27-delivery-items-manual-matching/27-CONTEXT.md` — 19 решений
- `.planning/phases/27-delivery-items-manual-matching/27-DISCUSSION-LOG.md` — аудит Q&A (21 вопрос)
- `.planning/todos/pending/2026-05-13-three-stages-tz-contract-delivery.md` — folded в Phase 27.1
- `.planning/ROADMAP.md` — Phase 27.1 stub добавлен

**Ключевые решения:**

- D-01 lazy trigger «Заполнить позиции», D-03 импорт как PurchaseItemsEditor (Excel/CSV/JSON/QR-фото), без OCR PDF
- D-04/05 strict валидация сумм: SUM(delivery_items) == acceptance_doc.amount + SUM(acceptance_docs) ≤ contract_price
- D-08 fuzzy-match difflib 0.7 → auto-link match_confirmed=false (Phase 21 паттерн)
- D-11 Phase 27.1 contract_items ВСТАВЛЕНА ПЕРЕД 27
- D-12/15 новый source 'delivery_items' в field_registry, сводная «Закупка × Товар × (План/Договор/Поставка)»
- D-16 legacy acceptance_doc_* → миграция в JSONB[0] + deprecated alias
- D-18 PaymentMatcher subset-sum комбинаторный матчинг (Phase 22 extension)
- D-19 «протокол закупки» (Росэлторг/Фабрикант API + manual upload) → contract_items

## 2026-05-13 — Phase 26-E/F/G/H ✅ UX/Permissions/SZ fixes batch (22 коммита)

`900a369..4200e0a` → push в `claude`. Полный разбор в `VAULT_for_LLM/Projects/VSKS_CRM/Sessions/2026-05-13_VSKS_CRM.md`.

Ключевые изменения:

- **26-E**: Excel-like ColumnHeaderMenu (54 слота на 4 list-view, ~440 LOC)
- **26-F**: рамочный остаток, шаблонные переменные UI, закрывающие документы UX
- **26-G**: должность per-org, дедуп ИНН, /users/in-my-orgs
- **26-H**: PATCH coerce ISO-дат, JSONB flag_modified, убран опасный SubsidyApprover.id fallback, membership-check СЗ, «за другого» только руководитель

**Архитектурные решения:**

- `_coerce_patch_value`: ISO-строки → date/datetime, '' → None (asyncpg не принимает str для Date-колонок)
- `flag_modified(obj, 'acceptance_docs')`: обязателен для JSONB мутаций в SQLAlchemy
- Initiator resolve: SubsidyApprover.user_id → SimpleNamespace из User (уровень SubsidyApprover.id УБРАН как опасный)
- Membership-check: инициатор обязан состоять в org субсидии

## 2026-05-11 — Phase 25 ✅ Report Builder (UI-конфигуратор сводных и дашбордов)

11 коммитов (`558dcc9..0b16f75`) → push в `claude`. Полная реализация UI-конструктора отчётов: 3 типа (реестр / сводная / дашборд) с drill-down, Excel и PDF экспортом.

### Backend (ядро)

- **field_registry.py** — 95 полей с label/type/source/sql_expr/agg_default/is_dimension/is_measure (источник правды для всех UI)
- **pivot_engine.py** — SQL group_by с whitelist ALLOWED_KEYS/ALLOWED_AGGS (защита от инъекций); LEFT JOIN purchases→contractors/subsidies/feo (3 уровня FEO через aliased); execute_query (list+pivot) + execute_drill
- **calc_columns.py** — share_of_total / cumulative_sum / delta_to_plan post-processing
- **composite_columns.py** — template-рендеринг `{field|format}` с fallback + group_rows (subtotals + grand_total)
- **report_excel.py** — openpyxl 3 типа: list (group_header + subtotals + grand_total), pivot (multi-row header + totals), dashboard (N листов по виджету)
- **report_pdf.py** — reportlab + DejaVuSans (fallback CID) + reportlab.graphics.charts.VerticalBarChart
- **routers/analytics.py** — `/fields` `/query` `/drill` `/export.xlsx` `/export.pdf`
- **routers/report_configs.py** — CRUD per-org + `/run` с params
- **models/report_config.py** — таблица `report_configs(id, org_id, kind, name, config_json, parameters_json)`
- **permission action `report_config.edit`** (default admin + org_admin)

### Frontend (3 builder'а + 4 supporting view)

- **ListBuilderView** (Тип A — реестр) — drag поля, composite-колонки `{contract_number} от {contract_date|dmy}`, константы «Россия», format units (₽/тыс.₽/млн.₽), группировка с subtotals; превью live (debounce 350ms)
- **PivotBuilderView** (Тип B — сводная) — drop-зоны Строки/Колонки/Значения/Фильтры; aggs; calc-columns (% от итога/нарастающий/Δ); drill-click→диалог→`/orders/{id}`
- **DashboardBuilderView** (Тип C — дашборд) — grid-layout-plus + WidgetRenderer (KPI/bar/line/area/pie/donut/table) + параметры
- **ReportRunView** — запуск шаблона с параметрами
- **Reports{Lists,Pivots,Dashboards}ListView** — индекс сохранённых отчётов

### Миграции

- **Purchase.region** (String 200, nullable) — через `check_schema.py --apply` auto-add
- **report_configs** таблица — через `Base.metadata.create_all` (alembic chain сломан)
- **89 субъектов РФ** — `frontend/src/constants/russian_regions.ts` + spec values
- **fonts-dejavu** в Dockerfile (для PDF кириллицы)

### Pending UAT (16 пунктов в `.planning/phases/25-report-builder/STATE.md`)

Ключевые: воспроизвести в UI 3 эталонных листа Excel пользователя — «Сумма_заключенных_договоров» (329 строк), «Контрактование закупок» (Товары/Услуги × Квартал × SUM), «Это для отчёта по мероприятиям» (группировка по event_id + composite).

### Manual step (alembic сломан)

Применить permission seed на проде:

```bash
docker cp backend/alembic/versions/phase25_seed_report_config_action.sql vsks-crm-db-1:/tmp/
docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -f /tmp/phase25_seed_report_config_action.sql
```

## 2026-05-07 — Phase 24 + drill-down + реформа авансовых

Push `c5ed69a` (последний из 24 коммитов): этапы рамочного, FEO-drill в pipeline, реформа авансовых отчётов в 3 фазы (reimbursement_user → per-item contractor → multi_contractor_label).

Detailed log: `/c/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Sessions/2026-05-07_VSKS_CRM.md`.

### Инциденты

- 2× OOM build на проде после крупных frontend refactor'ов (`81a5267`, `307290f`) → revert + атомарные правки. Lesson зафиксирован.
- alembic chain сломан, `check_schema.py --apply` авто-добавляет колонки на старте контейнера.

### Bundle deployment chain (для контроля OOM)

`8ea172f→DpY8cZqE→OOM→DWu4YuSF→B6MSF_sA→CWprrQSO→DFqZxfNU→BjOYCtYV→D1ECJ3n0→BlpoywjK→BoMULp2O→BQnejltI→Drz-nu6d`

## 2026-05-05 — Triage 3 (фидбек 5 мая, docx)

Push `89514eb` — 9 правок одним коммитом, applied/verified на проде:

1. **check_schema asyncpg multi-statement bug** — DROP+ADD одним `text()` падал PostgresSyntaxError; теперь два отдельных execute. Cascade FK `payments.purchase_id` стоял NO ACTION с момента a273f8c (4+ дня) — фикс применён вручную SQL + код корректен на следующий деплой.
2. **`/departments/{id}/members` UNION** — раньше показывал только из `department_members`; теперь UNION с `user_organizations.dept_id` → Цыганов виден в depts 3, 17, 18 (подтверждено API). `add_member` больше НЕ удаляет другие отделы той же org (раньше «one dept per org» сносил multi-dept).
3. **PATCH `/purchases/{pid}`** — НОВЫЙ endpoint. Phase 26 autosave стрелял PATCH, но его не было → 405 → autosaveState='error' silently. Поэтому пропадал контрагент в #525. PATCHABLE whitelist + partial body.
4. **Тогл «Адрес доставки/Место оказания услуг»** в карточке закупки (v-btn-toggle над AddressAutocomplete). Новое поле `purchases.delivery_location_kind` + schema/PATCHABLE.
5. **Receipt block для advance method** — раньше был только в `formMode='advance_report'` (/advance-reports). Теперь и для обычной закупки с `purchase_method='advance'`. loadReceipts() расширен.
6. **Transitions для авансового** — `FIELD_LABELS` подменяются: `contract_date` → «Дата документа основания (чек/УПД)», `contract_number` → «№». Хинт без служебных слов.
7. **`lookup-inn` НЕ дефолтит «Юридическое лицо»** для 12-знач ИНН без ОГРН → None, пользователь сам выбирает.
8. **AddressAutocomplete defaults** — «По месту нахождения подрядчика» (вместо «На территории Исполнителя») + ownOrgAddress prop + customerAddress.
9. **focusout-handler** — flush autosave немедленно при blur поля (помимо debounce 1500ms). Document capture-phase listener.

UAT pending: пользователь проверяет на проде (Ctrl+F5 → /orders, /dashboard). Ошибок в логах backend кроме тестовой PATCH с FK violation — нет.

Recently closed:

- Phase 22 — Импорт банковских выписок (RESTORED 2026-05-07). Восстановлен через `git revert dd0ff00..fc6fbd1` + полный рефакторинг парсера/матчера. Новая архитектура: 4-шаговый matcher (contractor→subsidy→contract→purchase); универсальный header parser (merged cells + 2 строки); АВАНСОВЫЙ ОТЧЁТ + СЧФ + УПД + ТТН в regex; basis_doc_number/date на Subsidy; SHA-256 source_row_hash (UniqueConstraint по 5 полям); _json_safe() для asyncpg JSONB datetime; PWA NetworkFirst 3s + skipWaiting+clientsClaim+activate cleanup; гибридный column picker (3 таба: Основные/В этом файле/Все возможные). Commits: 8cbfa4a..8fd5bbc.
- Phase 21 — Авансовые отчёты + чеки + ФНС (deployed 2026-04-26)
- Phase 17 — Permission System Override (9/9 planов, commits 1622167, f733aca + per-plan commits; 9 decisions D-01..D-09 delivered)
- Phase 13 — Заявки v3 канбан + split purchase kanban (7/7 планов, commits 9ae0202, c2312f8, f40546c, d1b3cb9, fcbed67)
- Phase 16 — Refactor monoliths (15/15, 16-15-UAT pass)
- Phase 15 — PurchaseItemsEditor extraction (5/5)

- **Milestone:** v1.0
- **Last Completed Phase:** 17 → 16 → 13 (в порядке закрытия)
- **Profile:** balanced (Opus plans, Sonnet executes)

## Status

- ✅ Complete (18): Phases 1–9, 10, 11, 13, 14, 15, 16, 17, 21, 22
- ⏳ Not started (2): Phase 12 (4 плана ready), Phase 18 Staff Directory (TBD)
- Post-phase feedback work: ✅ Delivered (Голичков-3, Суперадмин-1, Суперадмин-2, Суперадмин-3)

## Recent Activity (April–May 2026)

- 2026-05-07: **Phase 22 RESTORED — Bank Statements Import (рефакторинг парсера + bulletproof Subsidy save + PWA cache strategy)**. `git revert dd0ff00..fc6fbd1` восстановил каркас (8 коммитов). Затем: (1) Refactor parser/matcher — удалён multi-row split cols 62-81, расширен regex (+АВАНСОВЫЙ ОТЧЁТ / АКТ / СЧЁТ / СЧФ / УПД / ТТН / РЕЕСТР), basis_doc_number+date на Subsidy, 4-шаговый matcher. (2) UniqueConstraint заменён на SHA-256 source_row_hash. (3) openpyxl read_only=False для merged_cells.ranges, _find_first_data_row. (4) _json_safe() для asyncpg JSONB datetime/date/Decimal. (5) ALTER TABLE в lifespan (не в endpoint). (6) PWA workbox `/api/*` NetworkFirst 3s + skipWaiting+clientsClaim+activate cache cleanup — root cause «basis_doc не сохраняется» был в SW cache (stale GET после PUT). (7) Гибридный column picker 3 таба. Ключевые коммиты: `ca129fa`, `174e2fc`, `6015d87`, `a568257`, `290e404`, `aa6f52c`, `db5c4ab`, `4d4633a`, `64996b6`, `8fd5bbc`.

- 2026-05-04: **Карточка сотрудника — 3 фикса** (`4df1a86`). (1) Фото сотрудника в editDialog StaffView: вертикальный прямоугольник 4:5 (160×200 превью, 240×300 storage), border-radius 12px, новые admin endpoints `GET/PUT/DELETE /users/{user_id}/photo` (require_tab('staff')); `ProfilePhotoUpload.vue` расширен props `format='circle'|'rectangle'` + `userId?` (AppBar остаётся круглым). (2) Кнопка `mdi-delete` у каждой строки `allOrgEntries` в editDialog → новый `DELETE /api/users/{uid}/org-memberships/{row_id}` (по PK строки `user_organizations`, mirror в `department_members`, снимает `user.org_id` если строк к этой org не осталось). `GET /users/{uid}/salary` теперь отдаёт `id` + `dept_id`. (3) `GET /api/hierarchy/graph` `members_map` = UNION(`department_members`, `user_organizations.dept_id`) — Цыганов в 4 отделах ВСКС теперь появляется в каждом на канвасе. UAT: открыть карточку Цыганова, удалить лишние строки, загрузить фото; проверить что на канвасе HierarchyView сотрудник появляется во всех своих отделах.
- 2026-05-04: **Approval workflow integration** — 3 коммита (`5d2414f`, `7f50475`, `fdb11c2`). (1) `SubsidiesView` диалог approver получил `<v-autocomplete>` сотрудников — выбор `user_id` обязателен, `full_name` авто-подставляется; старые записи без user_id блокируются на сохранении с warning. (2) `purchase_approvals.start_approval` теперь создаёт `Task(category="Согласование", purchase_id, due_date=approval_deadline)` + `TaskAssignee` + `ChatRoom` через `_create_assignment_chat_room` + system-message «📋 Запущено согласование» для каждого approver_user; `decide_approval` закрывает Task (approve→done, reject→cancelled), `reset_approvals` отменяет все pending. (3) `purchases.update_purchase` + `create_purchase` — `contract_price` авто-пересчёт расширен: `(is_single_contract OR is_advance) and items_sum` — раньше авансовые отчёты с `purchase_method='advance'` не пересчитывали contract_price; рамочные не затронуты. Backfill закупки #573 — открыть+сохранить.
- 2026-04-27: **Phase 22 CLOSED** — Bank Statements Import. 8/8 планов, 8 коммитов (`0ec6c22..6af20a8`) push'нуты в `claude`. Backend: 2 новые таблицы (`bank_statement_imports`, `bank_payments`), парсер xlsx (header-based mapping для разноколоночных выгрузок, 20-групп multi-row split в ScrollerHash формате, regex для contract_number/КБК/parsed_date), matching service (ИНН+contract_number), 7 endpoints, permission seed (`payment_registry` tab + 3 actions). Frontend: /payments/import (DropZone + журнал), /payments/registry + PaymentMatchDialog (ручной матчинг + confirm), PaymentsBlock в CreateOrderView (показывает N платежей закупки + источник). Auto-paid при SUM≥contract_price/planned_total_price И matched_confirmed=true. Pending: применить 2 SQL миграции на проде (alembic chain сломан).
- 2026-04-23: **Phase 17 CLOSED** — Permission System Override, 9/9 planов. 17-09: router guards migrated to `meta.tab_key` + `authStore.hasTab()` (32 routes, commit 1622167); E2E spec 20-permissions.spec.ts unskipped with 7 tests (commit f733aca). EMPLOYEE_ALLOWED removed. All 9 decisions D-01..D-09 delivered. Ready for `/gsd:verify-work 17`.
- 2026-04-23: Purchase Split Kanban — DnD-редистрибуция позиций в существующей закупке, N дочерних закупок, блокируется после статуса «Договор» (не-админам). commits: 40b9d98, 17ec94b, 6a13456, 06ef867, 60379f7, fbb6169. Bugfix цепочка: id-propagation → column width/wrap → ref-state DnD.
- 2026-04-23: Wishes edit dialog — product_id persistence в WishItem schema + 3-layer name-fallback (openEditDialog, openKanbanDialog, approve_distribution) + assignee action banners по ролям.
- 2026-04-23: Knowledge graph updated — targeted AST-refresh для 14 файлов Phase 13/15/Split scope, pruned 83 VAULT ghost nodes. Final: 1645 nodes / 4843 edges / 234 communities.
- 2026-04-23: STATE.md + ROADMAP.md sync с реальностью — Phase 7 PARTIAL→✅, Phase 13 ✅, Phase 16 "в работе"→✅.
- 2026-04-23: Phase 17 context gathered — 9 решений (D-01..D-09) через опросник. Scope = 3 уровня (nav + API + sub-actions). Override = boolean flip. Admin UI = матрица роль×вкладка. Badge = «Индивидуально». Per-org structure (role per-org + overrides per-org). Superadmin полностью невидим для не-superadmin (SaaS-сотрудник).
- 2026-04-19: Phase 16 context gathered — CONTEXT.md + DISCUSSION-LOG.md for Refactor Monoliths (faaa12d). Auto-mode picked 6 gray-area defaults: backend-first order, 6 modules for purchases.py (added items_import), 5 for tasks.py, orchestrator+5 components for MyTasksView, helpers stay in originating modules, strict URL preservation, E2E + smoke gates.
- 2026-04-19: Autodeploy hardened (2d04e4e) — ThreadingHTTPServer в webhook.py, always-restart в autodeploy.sh, /healthz endpoint. Root cause предыдущего падения: single-threaded HTTPServer завис в accept loop, systemd репортил active, но всё таймаутило. 2 дня push'ей были silently dropped.
- 2026-04-19: Phase 11 reopened+fixed — 4 UX бага на /my-tasks под employee: закупки без org/member фильтра (ce90039), flash unfiltered tasks + "Все организации" не кликалось + счётчик header считал done/cancelled (f3cf2cc).
- 2026-04-19: Phase 15 closed — PurchaseItemsEditor extracted (15-01), dead OrderProductsTable removed (15-02), wired into CreateOrderView -1425 lines (15-03), wired into WishesView -100 lines (15-04), E2E smoke spec 3/3 pass on deploy (15-05). Заявка ↔ Новый заказ parity achieved.
- 2026-04-19: Phase 14.1 post-MVP fixes — Radar nav entry (b911e75), Classic/Radar toggle in DashboardView (4a43c30), formulas info dialog (5c87c47). QA PASS WITH NOTES.
- 2026-04-19: Phase 14 UI-SPEC approved (revision 1/2, typography fix) — CONTEXT.md + DISCUSSION-LOG.md + UI-SPEC.md ready for planning
- 2026-04-19: Phase 14 context gathered (Risk Radar Neon Telemetry Dashboard)
- 2026-04-17: Superadmin-3 feedback, Wishes v2 (items+FEO+subsidy), persistent templates volume
- 2026-04-16: Superadmin-2 feedback fixes (org-aware task loading, archive column, subsidy filter)
- 2026-04-15: Golichkov-3 + Superadmin-1 feedback fixes (hierarchy filtering, can_publish, document access)
- 2026-04-14: Draggable dashboard, visual enhancements, document import
- 2026-04-12: Pipeline funnel, dashboard cards, FEO fixes

## Decisions

- Direct API for Фабрикант/Росэлторг (n8n removed)
- PostgreSQL bytea for file storage (no filesystem)
- Autodeploy: git push → webhook → docker compose build backend + frontend
- [Phase 14]: AlertsTicker uses doubledItems+translateX(-50%) for seamless CSS marquee loop without JS timers
- [Phase 14]: Stub RiskRadarView.vue created to unblock vite-plugin-pwa build (Plan 14-03 replaces it)
- [Phase 14]: RiskRadarView uses isDark-reactive hex dictionaries for ApexCharts colors (CSS vars not readable by SVG engine)
- [Phase 15]: OrderProductsTable.vue confirmed dead (only .backup.vue referenced it) — deleted to clean frontend/src/components before PurchaseItemsEditor lands
- [Phase 15]: PurchaseItemsEditor.vue: purchaseId-aware import branching — null path uses client-side row assembly from preview, set path calls pid-bound API; imap-* CSS migrated to component scoped styles; emit('items-changed') replaces direct syncContractPriceIfSingle call
- [Phase 15]: WishesView :readonly=false since dialog guard at call-site ensures only draft wishes are editable
- [Phase 15]: wishForm.items typed as any[] to accept EditorItem superset; saveWish strips helper fields with destructure map
- [Phase 15]: FEO column Branch 3 (no per-row FEO in old items table) — no #row-extra slot; feo_planned_item_id flows via v-model
- [Phase 15]: quickProductEditDialog deleted as dead code (Plan 15-03) — caller button removed with items table; PurchaseItemsEditor has own internal handler
- [Phase 16]: httpx 0.27.0 already present in requirements.txt — kept existing version
- [Phase 16]: ASGITransport (in-process) pattern for FastAPI pytest — no port conflicts, < 10s execution
- [Phase 16-05]: Extracted _create_assignment_chat_room + 5 endpoints into purchase_members.py; cleaned 3 unused imports from purchases.py
- [Phase 16-refactor-monoliths]: tasks.py at 641 lines (not 500): create/update consent logic is dense — splitting requires new service layer (16-12 candidate)
- [Phase 16-refactor-monoliths]: OrgSummaryBar includes consent banners (D-18 badges scope) enabling required line reduction
- [Phase 16-refactor-monoliths]: visibleOrgSummary computed moved to OrgSelector child — child owns its own filter logic
- [Phase 16-refactor-monoliths]: TasksTable+TasksKanban are pure-presentation components; handleUpdateTaskStatus in MyTasksView handles PATCH persistence via update-status emit
- [Phase 13-v3-drag-drop-n]: AdvancedProductSelector delegates product creation to AddProductDialog — validation applied in AddProductDialog, not inline
- [Phase 13-v3-drag-drop-n]: Category payload uses .trim() instead of || null since field is now required (matches DB NOT NULL from plan 13-01)
- [Phase 13-v3-drag-drop-n]: Backfill NULL products.category to 'Прочее' before NOT NULL constraint (D-03); downgrade reverts constraint only
- [Phase 13-v3-drag-drop-n]: ProductCreate.category required via Pydantic Field(..., min_length=1) — empty string also rejected at API layer
- [Phase 13-v3-drag-drop-n]: 409 for approved-wish edit (not 403): resource state conflict. 404 for cross-wish PATCH: item not in that wish. Explicit db.rollback() in approve-distribution for atomicity. product relationship added to WishItem for category resolution.
- [Phase 17-permission-system-override]: FK user_org_access_id (not user_id+org_id pair) per D-08 — UserOrgAccess already enforces uniqueness
- [Phase 17-permission-system-override]: publication.create NOT seeded into role_permissions — per-user override via can_publish migration (Step E)
- [Phase 17]: Wave 0 test scaffolding uses deferred imports in fixtures to prevent collection errors while Plan 17-01 models exist on disk but DB migration not yet run
- [Phase 17]: require_tab/require_action import directly from app.auth.permissions at call-sites (no jwt.py re-export needed)
- [Phase 17]: Split effective key set into tabs vs actions using PermissionTab/PermissionAction dictionary tables at /me endpoint
- [Phase 17]: Pinia auth store (stores/auth.ts) uses tab_key filter via authStore.hasTab() replacing hardcoded roles arrays in AppBar.vue; fail-open pattern on loadPermissions errors
- [Phase 17]: D-09 superadmin filter applied in 4 user-listing locations: list_users, _get_visible_user_ids, hierarchy graph, task authority; all other select(User) sites annotated superadmin-bypass-ok
- [Phase 17]: permissions.router prefix /api/permissions in constructor; org_id as Query(...) param in override endpoints; self-lockout returns 403 on admin.roles+staff keys for own role
- [Phase 17-permission-system-override]: purchases.py bulk_delete → require_tab('purchases') — no separate delete action seeded for purchases
- [Phase 17-permission-system-override]: publications.py can_publish inline check already absent; declarative require_action('publication.create') added on POST endpoint per D-06
- [Phase 17-permission-system-override]: users.py GET /users/ stays require_role(*ALL_ROLES) — 17-05 handles superadmin filter there
- [Phase 17]: [Phase 17-07]: AdminRolesView uses 300ms debounced per-role PUT with optimistic UI and server-truth revert on error; publication.create filtered out of matrix via PER_USER_ONLY_ACTIONS (per-user only, handled in 17-08)
- [Phase 17-permission-system-override]: Plan 17-08: «Доступ» section uses allOrgEntries (not rebuilt orgAccessList) and editDialog.userId (actual shape) per PLAN's adaptation clause
- [Phase 17-permission-system-override]: Plan 17-09: EMPLOYEE_ALLOWED removed outright (no fallback) — authStore.loaded fail-opens on API failure (17-06) + 17-01 seed grants employee defaults; double-gating would regress
- [Phase 17-permission-system-override]: Plan 17-09: Sub-routes share parent tab_key (/hierarchy→staff, /suppliers→contractors, /orders/*→purchases, service-notes/advance-reports sub-paths) — matches RESEARCH Open-Question 2
- [Phase 17-permission-system-override]: Plan 17-09: E2E uses inline loginAs(page,user,pwd) helper — existing helpers.ts login() is hardcoded to admin/admin123; keeps plan scope to two declared files
- [Phase 27.1]: ContractItem uses _ensure_*_table pattern (not alembic) + non-fatal lifespan startup
- [Phase 27.1]: Backfill uses NOT EXISTS guard; framework head excluded by purchase_contract_type check (D-07)
- [Phase 27.1-contract-items]: contract_items.router registered BEFORE purchases.router in __init__.py (line 505 vs 506) to prevent catch-all /{purchase_id} from intercepting /contract-items path
- [Phase 27.1-contract-items]: D-06 strict 422 guard CONTRACT_ITEMS_REQUIRED placed AFTER field guards, BEFORE p.status=target_status in purchase_transitions.py
- [Phase 27.1-03]: openSmartImportDialog() used as real contract import proxy (W-1 resolved via grep)
- [Phase 27.1-03]: replaceAllContractItems called unconditionally when canShowContractColumns (W-2 compliance)

## Blockers

_нет активных блокеров_

### Closed 2026-04-19

- **INTERNAL_ERROR на /dashboard/radar** → оказалось не backend N+1, а frontend: ApexCharts получал negative `<circle r>` из unclamped `feoImbalance` score + `mode="out-in"` в `<transition>` не давал новой view монтироваться. Закрыто в `e9efc8d` + `c313c57`. Детали в 05_Gotchas.
- **PydanticSerializationError для WishItem** на `/api/wishes/` → `WishOut.items` был нетипизированным `list`. Pydantic не знал схему. Закрыто в `5c592d8` (items: List[WishItemOut]).
- **Автодеплой висел 2 дня** → webhook.py однопоточный HTTPServer в silent-hang. Закрыто в `2d04e4e` (ThreadingHTTPServer + always-restart + /healthz).
- **4 UX-бага Любарца на /my-tasks** → Phase 11 incomplete. Закрыто в `ce90039` (backend: employee + PurchaseMember + ?org_id) и `f3cf2cc` (frontend: org picker, flash, counter).

## Roadmap Evolution

- Phase 13 added: Заявки v3 — авторасспределение позиций по закупкам, drag-drop, автосоздание N закупок, служебная записка
- Phase 14 added: Risk Radar — альтернативный визуал Dashboard (Neon Telemetry стиль) с toggle classic/radar, без модификации DashboardView.vue
- Phase 16 added (2026-04-19): Refactor Monoliths — декомпозиция purchases.py (3200), tasks.py (1639), MyTasksView.vue (2155) в тематические модули ≤800 строк по принципу «один процесс — один модуль». Директория `.planning/phases/16-refactor-monoliths/`.
- Phase 17 added (2026-04-21): Permission System — конфигурируемая матрица ролей + индивидуальные override'ы (галочки в карточке пользователя → роль `Индивидуально`). Триггер: Любарец видит «Персонал» но редактировать не может. Директория TBD.
- Phase 18 added (2026-04-21): Staff Directory — read-only справочник коллег (ФИО, должность, телефон, email) фильтрованный по своим организациям, отдельно от админской вкладки «Персонал». Директория TBD.
- Phase 31 added (2026-07-06): Feedback Backlog UX — 6 пунктов из «Pending from Feedback»: DnD закрывающих документов, diff-подсветка изменений, Undo/Redo (Ctrl+Z/Y), синхронизация договор↔закупка, пересмотр бюджетной логики План vs ФЭО, фикс слетающих шаблонов (лист согласования ФАДМ_26). Директория `.planning/phases/31-feedback-backlog-ux-dnd-diff-undo-redo-vs/`.

## Pending from Feedback

- Drag & Drop для закрывающих документов
- Подсветка изменений (diff-tracking) в карточке задачи/закупки
- Автосохранение + Undo/Redo (Ctrl+Z/Y)
- Синхронизация договор ↔ закупка
- Бюджетная логика: Плановая vs ФЭО (пересмотр)
- Шаблоны слетают (лист согласования ФАДМ_26)
