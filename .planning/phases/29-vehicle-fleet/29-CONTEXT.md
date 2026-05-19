# Phase 29: Vehicle Fleet — Учёт автотранспорта - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Модуль учёта автотранспортного флота ВСКС и партнёрских организаций. Включает:

1. **Реестр ТС** — карточки 51+ машин (из xlsx-реестра Голичкова), CRUD, фильтры, импорт Excel.
2. **Карточка машины** — общая информация, фото, типизированные документы (СТС, ПТС, ОСАГО, КАСКО, ДК, Разрешение ТО, Прочее), история полей с автором/датой, ремонты с заказ-нарядами и фото.
3. **Пробег и топливо** — ежедневный одометр (абсолют), журнал заправок с чеками, нормы расхода (летняя/зимняя по Минтрансу), автоматический расчёт литров и стоимости.
4. **Путевые листы** — генерация .docx (3 формы: легковой ф.3 / грузовой ф.4-С / специальный) через docxtpl с автозаполнением водителя/маршрута/одометра.
5. **Водители** — `User.can_drive` flag + поля ВУ + медсправка; `ExternalDriver` сущность для наёмных водителей без аккаунта.
6. **Дашборд** — 8 виджетов с креативными визуализациями (анимация бензина в канистре, ТО-warning < 1000 км, виджет «в ремонте»), фильтры по регионам/организациям, draggable layout.
7. **Уведомления** — баннеры в карточке + auto-Task за 30 дней до окончания ОСАГО/медсправки/ВУ.
8. **Permissions** — новый tab `vehicles` + actions через Phase 17 матрицу.

**Out of scope (deferred):**
- Подмодули «Имущество / Оборудование» и «Имущество / Прочее» (заглушки в навигации, реализация — отдельные фазы).
- Интеграция с GPS-трекерами в реальном времени.
- Авто-распознавание ПТС/СТС/чеков заправки через OCR (через ручной upload в Phase 29; OCR — потенциально Phase 30+).
- Маршруты на карте (Yandex/2GIS) — отдельная фаза.

</domain>

<decisions>
## Implementation Decisions

### Workflow и навигация

- **D-01 Workflow:** полный GSD-цикл `/gsd:discuss-phase → /gsd:plan-phase → /gsd:execute-phase`. Не `fast/quick`.
- **D-02 Навигация:** новая вкладка AppBar **«Имущество»** (icon `mdi-warehouse`) → внутри tabs:
  - «Автотранспорт» — реализуется в этой фазе
  - «Оборудование» — заглушка (route `/property/equipment` → placeholder view)
  - «Прочее» — заглушка (route `/property/misc` → placeholder view)
  - Route группа: `/property/vehicles`, `/property/vehicles/:id`, `/property/vehicles/dashboard`.

### Глубина учёта

- **D-03 Учёт топлива и пробега:** полный — ежедневный одометр + норма расхода + журнал заправок с чеками + автоматический расчёт литров и стоимости + путевые листы (3 формы) + агрегация расхода денег по машине.

### Водители

- **D-04 User.can_drive flag:** чекбокс «Может водить ТС» в карточке сотрудника (StaffView) → раскрывает поля:
  - `license_series` (VARCHAR 10)
  - `license_number` (VARCHAR 20)
  - `license_categories` (VARCHAR 50, через запятую: A,B,C,D,CE,M,...)
  - `license_issued_at` (DATE)
  - `license_expires_at` (DATE)
  - `medical_cert_expires_at` (DATE, nullable)
  
  Список водителей в путёвке = `User WHERE can_drive=true` (видны из всех organizations).

- **D-15 Наёмные водители:** **`ExternalDriver` сущность** — новая таблица для водителей-не-сотрудников.
  - Колонки: `id, full_name, license_*, phone, org_id (nullable), notes`
  - В путёвке селект водителя = `User WHERE can_drive=true` ∪ `ExternalDriver` (объединённый список с префиксом «внешний»).
  - Накапливает историю — повторно используется при следующих путёвках.

### Permissions

- **D-05 Permissions:** новый tab `vehicles` в `permission_tabs` + actions:
  - `vehicle.edit` — редактирование карточки
  - `vehicle.delete` — удаление машины (только admin)
  - `vehicle.import` — импорт Excel
  - `vehicle.odometer.write` — ввод пробега (employee+ для своих машин)
  - `vehicle.repair.write` — добавление ремонтов
  - `vehicle.trip.create` — создание путевых листов
  - Default-матрица: admin/org_admin = R/W всё, manager = R/W свои org, employee = R-only + odometer.write для назначенных. Per-user overrides работают через Phase 17.

### Видимость (multi-tenancy)

- **D-06 Visibility:** `Vehicle.owner_org_id` (FK Organization) + `Vehicle.assigned_org_id` (FK Organization, nullable, «у кого в эксплуатации»).
  - Сотрудник видит ТС если `owner_org_id ∈ user.org_ids` ИЛИ `assigned_org_id ∈ user.org_ids`.
  - Admin и superadmin — видят всё.
  - Поле «У кого в эксплуатации» из xlsx-реестра при импорте мапится на `assigned_org_id` (по region → org lookup) либо в `assigned_text` (свободный текст для регионов без org-сущности).

### Storage

- **D-07 Storage:** PostgreSQL **bytea** для фото и сканов документов (паттерн Phase 3).
  - `VehicleAttachment(id, vehicle_id, kind ENUM, name, file_data bytea, mime, size, sha256, uploaded_at, uploaded_by)`.
  - SHA-256 дедупликация.
  - Бэкап — через `pg_dump` (volume не нужен).
  - `RepairAttachment` отдельная таблица с FK на VehicleRepair (для тематической изоляции ремонтных доков от документов ТС).

### Схема Vehicle

- **D-08 Mixed schema:** канонические колонки + bool слоты + JSONB props.

  **Колонки Vehicle:**
  ```
  id, owner_org_id (FK), assigned_org_id (FK nullable), assigned_text (VARCHAR 100, fallback),
  brand (VARCHAR 100), model (VARCHAR 100), color (VARCHAR 50),
  vin (VARCHAR 17, nullable), plate (VARCHAR 20),
  registered_at (DATE, nullable),
  type ENUM ('car_light', 'minivan', 'truck_van', 'truck_board', 'truck_tank', 'truck_metal', 'bus', 'special', 'quadbike', 'snowmobile', 'boat', 'boat_motor', 'trailer', 'other'),
  state ENUM ('working', 'broken', 'in_repair', 'needs_repair', 'destroyed', 'utilized'),
  insurance_until (DATE, nullable),
  fuel_type ENUM ('AI-92', 'AI-95', 'AI-98', 'AI-100', 'DT', 'GAS', 'other'),
  fuel_norm_summer FLOAT (л/100км, May-Sep), fuel_norm_winter FLOAT (Oct-Apr),
  has_tracker BOOL, akb_ok BOOL, has_radio BOOL, mirrors_ok BOOL,
  has_keys BOOL, has_first_aid_kit BOOL, has_spare_wheel BOOL, has_extinguisher BOOL,
  next_to_km INT (nullable, для ТО-warning),
  current_odometer_km INT (nullable, snapshot последней записи VehicleOdometer для быстрых фильтров),
  props JSONB (брендирование, ЛКП, неисправность, примечание, кастомные поля)
  ```

  **JSONB `props` ключи:** `branding`, `paint_condition`, `tires_type`, `defect_description`, `note`, `custom.*`.

### Импорт реестра

- **D-09 Import:** **seed на старте** (idempotent по VIN+plate) + UI «Импорт Excel» (паттерн OrdersView import dialog).
  - Seed скрипт: `backend/app/services/vehicles_seed.py` запускается из `lifespan` после `check_schema --apply`.
  - Idempotency key: `(vin, plate)` — `INSERT ... ON CONFLICT DO NOTHING`.
  - UI: `/property/vehicles` → кнопка «Импорт Excel» → FileDropZone → preview + commit. Mapping колонок xlsx → модель.

### История полей

- **D-10 History:** отдельная таблица `VehicleFieldHistory`.
  - Колонки: `id, vehicle_id, field_key (VARCHAR 50), old_value (TEXT), new_value (TEXT), changed_at, changed_by_user_id, comment (TEXT nullable)`.
  - Авто-запись через ORM event на PATCH полей (либо в `update_vehicle` endpoint).
  - UI: иконка `mdi-information-outline` рядом с каждым редактируемым полем → popover с timeline (старое → новое, когда, кто, опц. комментарий).

### Документы машины

- **D-11 Document slots:** типизированные слоты + «Прочее».
  - `VehicleAttachment.kind` ENUM: `'sts'`, `'pts'`, `'osago'`, `'kasko'`, `'dk'` (диагностическая карта), `'permit_to'`, `'photo'`, `'other'`.
  - Доп. поля для `osago`/`kasko`/`dk`: `policy_number`, `issued_at`, `expires_at` (отдельные колонки на `VehicleAttachment`).
  - UI: фиксированные слоты СТС/ПТС/ОСАГО/КАСКО/ДК/Разрешение ТО + список «Прочее» с inline name.
  - Каждый файл — кнопка «Скачать» + предпросмотр для image/pdf.

### Ремонты

- **D-12 Repairs:** `VehicleRepair` + `RepairAttachment` отдельные сущности.
  - `VehicleRepair(id, vehicle_id, date, description, cost_amount, performed_by_name, mileage_at_repair, status ENUM('planned'/'in_progress'/'done'/'cancelled'), purchase_id nullable FK)`.
  - `RepairAttachment(id, repair_id, kind ENUM('order_form'/'act'/'invoice'/'photo'/'other'), file_data bytea, mime, name)`.
  - UI: таб «Ремонты» в карточке ТС → timeline + accordion. Клик на ремонт → expand с приложениями и формой добавления.
  - Связь с Purchase: см. D-18.

### Пробег

- **D-13 Mileage:** `VehicleOdometer(id, vehicle_id, date, odometer_km, entered_by, note, source ENUM('manual'/'trip'/'fuel_log'))`.
  - UNIQUE constraint `(vehicle_id, date)`.
  - Абсолютные значения одометра (не delta).
  - `delta_km = odometer[N] - odometer[max_prev]` — вычисляется на чтении.
  - `fuel_used_l = delta_km * fuel_norm / 100` (норма выбирается по сезону: May-Sep summer, Oct-Apr winter — D-20).
  - Пропуски дат допустимы (delta считается с последней доступной записи).
  - UI: таб «Пробег» в карточке → таблица с inline-edit; календарь heatmap опционально.

### Путевые листы

- **D-14 Trip templates:** **3 раздельных `.docx` шаблона** в `backend/templates/`:
  - `trip_light.docx` — форма 3 (легковой / минивэн / квадроцикл)
  - `trip_truck.docx` — форма 4-С (грузовой бортовой / фургон / цистерна / цельнометаллический)
  - `trip_special.docx` — специальный (автобус / аварийно-спасательный / спецтехника)
  - Backend выбирает шаблон по `vehicle.type` (mapping в коде).
  - Шаблоны base. Кастомизация по орг — через Phase 19-стиль upload, **deferred (не в этой фазе)**.

### Дашборд

- **D-16 Dashboard:** 8 виджетов + draggable layout (grid-layout-plus как Phase 25/14) + кастомные креативные визуализации.
  - **KPI cards (4):** Машин всего | Стоимость бензина за период | Стоимость ремонтов за период | Общий пробег за период
  - **«Канистра»** — кастомный SVG-виджет с анимацией: уровень бензина = расход за выбранный период / бюджет на топливо; жидкость плещется при загрузке/смене периода.
  - **«Машины в ремонте»** — список с фото + статус + дата начала + ожидаемая дата окончания (из VehicleRepair WHERE status IN ('planned','in_progress')).
  - **«ТО скоро»** — список ТС где `(next_to_km - current_odometer_km) < 1000` ИЛИ `insurance_until < now() + 30 days` ИЛИ просрочка ВУ/медсправки водителя → подсветка красным.
  - **Bar:** Машины по организациям (toggle: владелец / эксплуатант).
  - **Line:** Расход топлива (period toggle: day/week/month/year + custom range).
  - **Donut:** Состояние флота (working/broken/in_repair/needs_repair).
  - **Table:** TOP-10 машин по расходам (бензин + ремонт) за период.
  - **Фильтры дашборда:** регион (assigned_text) + организация-владелец (multiselect) + период.
  - **Layout state:** localStorage `vehicle_dashboard_layout` per-user (как Phase 14 Analytics tab).

### Уведомления о просрочке

- **D-17 Alerts:** Баннер в карточке + auto-Task.
  - **Баннер в карточке ТС** — `v-alert` сверху если ОСАГО истекает в <30 дней или истёк, ТО до 1000 км или меньше, и т.п.
  - **KPI «Просрочено/Скоро»** на дашборде.
  - **Cron в lifespan** (либо daily startup task): создание `Task` с категорией «Автотранспорт» — «Продлить ОСАГО {гос.номер}», «Пройти ТО {гос.номер}», «Обновить медсправку для {водитель}» за 30 дней до окончания + дедлайн = expires_date.
  - Assigned to: `user_organizations` где is_vehicles_responsible (новый флаг на User или роль) → fallback на org_admin владельца ТС.
  - Идемпотентность: по тегу `[VEHICLE:{vehicle_id}:OSAGO_EXPIRY]` в `Task.system_tag` — не создавать дубль если такой Task ещё открыт.

### Интеграция с Purchase

- **D-18 Purchase ↔ Vehicle:** `Purchase.vehicle_id` (nullable FK→vehicles).
  - В `CreateOrderView`: если `subject` содержит ключевые слова («ремонт ТС», «заправка», «ТО», «страхование ТС», «запчасти», «шиномонтаж») → показывается селект «Автомобиль» (autocomplete по brand + plate).
  - В карточке ТС: таб «Связанные закупки» — выборка `Purchase WHERE vehicle_id=this` с группировкой по типу (ремонт / топливо / страхование / прочее).
  - Стоимость ремонта/топлива в дашборде берётся в первую очередь из linked Purchase (`contract_price` или `total_paid`), fallback на `VehicleRepair.cost_amount` / `FuelLog.total_amount`.
  - В `VehicleRepair` тоже nullable `purchase_id` (двусторонняя ссылка для удобства резолва).

### Формат путёвок

- **D-19 Trip output format:** `.docx` через `docxtpl`. Без PDF (как Phase 19/27.5/28). Пользователь печатает .docx сам через Word.

### Норма расхода топлива

- **D-20 Fuel norms по сезону:** 2 нормы на Vehicle (`fuel_norm_summer`, `fuel_norm_winter`).
  - **Сезон по дате одометра:** May-Sep = summer, Oct-Apr = winter (РФ Минтранс).
  - При расчёте `fuel_used_l` для delta — норма выбирается по дате конечного одометра.
  - Цена за литр — из последней записи `FuelLog` для этой машины (fallback на `FuelLog.price_per_liter` среднее по орг за последние 30 дней).

### Claude's Discretion

- Точный layout карточки ТС и порядок табов (Общее / Документы / Фото / Ремонты / Пробег / Заправки / Путёвки / История / Связанные закупки).
- Конкретная SVG-анимация «канистры» — пользователь хочет «крутую визуализацию», даём свободу.
- Цвета и иконки виджетов дашборда (соответствие dark/light mode).
- Точные ENUM-значения для type/state (могут уточняться при импорте xlsx).
- Конкретные шаблоны путёвок (формы 3/4-С — стандартные образцы Минтранса РФ берутся из открытых источников).
- Mapping регионов xlsx → org_id (полу-ручной — после импорта показывать диалог сопоставления).

</decisions>

<specifics>
## Specific Ideas

- **Дашборд должен быть «крутой» визуально** — пользователь явно подчеркнул креативные визуализации, не просто bar/line/KPI:
  - «Бензин должен плескаться в канистре» — SVG-анимация уровня жидкости с волной (как в Apple Watch Activity rings или Tesla battery UI).
  - «Машины у которых ТО скоро» должны «светиться» — pulsing glow effect на карточках ТС.
  - Виджет «в ремонте» — компактные карточки с фото машины + статус-бейдж.
- Фильтры дашборда — **обязательно переключение по регионам и организациям**.
- Реестр Голичкова — 51 строка с реальными машинами ВСКС, КАМАЗами, лодками, квадроциклами. Машины не только автомобили — модель должна поддерживать boat / boat_motor / trailer.
- Тип ТС определяет шаблон путевого листа — это критично (легковой ≠ грузовой по форме отчётности).
- ТО-warning через 1000 км — это **бизнес-критичный триггер**, не просто баннер. Пользователь явно сказал «должны светиться».

</specifics>

<canonical_refs>
## Canonical References

### Reference data
- `Доработки/реестр_транспорта_от_Голичкова_обновление_042026.xlsx` — Лист «Лист2», 51 ТС, 24 колонки. Источник правды для seed-импорта при первом запуске.

### Codebase patterns (downstream agents must read these)
- `backend/app/models/purchase_file.py` — паттерн bytea attachments для D-07/D-11/D-12 (file_data + mime + size + SHA-256 dedup).
- `backend/app/routers/purchase_files.py` — паттерн upload/download/list endpoints для VehicleAttachment + RepairAttachment.
- `backend/app/auth/permissions.py` — `require_tab()` + `require_action()` + `permission_tabs` seed pattern для D-05 (Phase 17).
- `backend/app/routers/documents.py` — паттерн docxtpl render + context builder для D-14/D-19 (путевые листы).
- `backend/app/services/check_schema.py` — паттерн `_ensure_*_table` + `--apply` lifespan вызов для миграций без alembic (Phase 27.1 D-08).
- `backend/app/routers/analytics.py` + `backend/app/services/field_registry.py` — паттерн dashboard widgets через Report Builder (Phase 25), reference для D-16 если решим вкладывать в pivot_engine.
- `frontend/src/views/OrdersView.vue` — паттерн list view + Excel import dialog + ColumnHeaderMenu (для `/property/vehicles`).
- `frontend/src/views/CreateOrderView.vue` — паттерн карточки с табами + загрузка файлов + docxtpl-генерация (для VehicleDetailView).
- `frontend/src/views/DashboardView.vue` + `frontend/src/components/widgets/` — паттерн draggable widgets + KPI cards + ApexCharts (Phase 14, для D-16).
- `frontend/src/components/PurchaseItemsEditor.vue` — паттерн встроенной таблицы с inline-edit (для VehicleOdometerTab, FuelLogTab).
- `frontend/src/views/StaffView.vue` — точка расширения D-04 (чекбокс can_drive + поля ВУ в editDialog).
- `backend/app/models/user.py` — место добавления can_drive + license_* колонок.

### Project-level context
- `.planning/PROJECT.md` — общий контекст проекта.
- `.planning/STATE.md` — текущее состояние (Phase 27.1 active, 12/19 phases done).
- `.planning/REQUIREMENTS.md` — общие требования проекта.
- `c:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/04_TODO.md` § «🚀 Новый раздел Имущество» — оригинальный brief F4 vehicle fleet.
- `c:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/05_Gotchas.md` — известные грабли: alembic сломан на проде (использовать check_schema паттерн), localStorage расхождение auth_token/access_token, bytea volume на проде, autodeploy webhook hardening.
- `c:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Lessons.md` — `{% tr %}` запрещён в docxtpl (Lesson 2026-05-15), pre-push grep дубликатов let/const, dict-detail HTTPException теряется в кастомном handler (b179c4f).

### Prior phase CONTEXT.md (reference patterns)
- `.planning/phases/27.1-contract-items/27.1-CONTEXT.md` — паттерн mixed model (FK + check_schema + idempotent backfill).
- `.planning/phases/25-report-builder/25-CONTEXT.md` — паттерн dashboard через Report Builder (если D-16 пойдёт через field_registry).
- `.planning/phases/19-document-templates/` — паттерн docxtpl с DOC_TYPES + загрузка шаблонов через UI (если будем поддерживать кастомные путёвки на будущее).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`backend/app/models/purchase_file.py` + `purchase_files.py` router** — почти 1:1 копируется как VehicleAttachment + RepairAttachment. SHA-256 dedup, bytea, mime detection, dedup 409 — всё готово.
- **`backend/app/auth/permissions.py`** — `require_tab('vehicles')` + `require_action('vehicle.edit')` готовы к использованию после Phase 17. Нужно только seed `vehicles` tab + actions через `perm_seed_*.sql`.
- **`backend/app/routers/documents.py`** — `_render_template_with_context` + `DocxTemplate(path).render(ctx)` готовы; добавляем `_build_trip_context(vehicle, driver, date, route, odometer_start, odometer_finish)` + выбор шаблона по `vehicle.type`.
- **`backend/app/services/check_schema.py`** — `_ensure_*_table` идемпотентный паттерн (Phase 27.1) — используем для всех новых таблиц (vehicles, vehicle_attachments, vehicle_repairs, repair_attachments, vehicle_field_history, vehicle_odometer, fuel_logs, trips, external_drivers).
- **`frontend/src/components/FileDropZone.vue`** — переиспользуется для upload фото/документов/чеков заправки.
- **`frontend/src/api.ts`** — JWT и apiFetch готовы.
- **`frontend/src/utils/qrDecode.ts`** (Phase 21) — потенциально для парсинга чеков заправки в будущем (deferred, не в этой фазе).
- **`frontend/src/views/DashboardView.vue` + draggable grid** — паттерн копируется для VehicleDashboardView.
- **ApexCharts** — установлен, line/bar/donut готовы.
- **grid-layout-plus** — установлен (Phase 25), используем для D-16 draggable layout.

### Established Patterns

- **Multi-tenancy через `org_id` + `user_organizations`** — для D-06 видимости (Phase 11/26-G).
- **Tasks с `system_tag`** — для D-17 идемпотентных авто-Tasks по просрочкам.
- **`Purchase.vehicle_id` nullable FK** — миграция через `check_schema._ensure_purchases_table` ALTER COLUMN.
- **`StaffView` editDialog с условными разворачивающимися секциями** — паттерн для D-04 чекбокса `can_drive` + поля ВУ (как уже сделано для `exclude_from_directory`).
- **`User.role` per-org override через `user_organizations.role`** — Phase 17.1, не затрагиваем.
- **`Sessions/YYYY-MM-DD_VSKS_CRM.md` autolog коммитов** — продолжаем для phase 29.

### Integration Points

- **AppBar.vue** — новый пункт «Имущество» (mdi-warehouse) с подменю Автотранспорт / Оборудование / Прочее. Видимость по permission `vehicles` tab.
- **Router (`frontend/src/router.ts`)** — новые routes: `/property/vehicles`, `/property/vehicles/:id`, `/property/vehicles/dashboard`, `/property/equipment` (placeholder), `/property/misc` (placeholder).
- **StaffView editDialog** — добавление блока «Может водить ТС» с раскрывающимися полями ВУ (D-04).
- **CreateOrderView** — условный селект «Автомобиль» если subject содержит ключевые слова ремонта/топлива/страхования ТС (D-18).
- **Покупки в карточке ТС** — таб «Связанные закупки» через `GET /api/purchases/?vehicle_id={id}` (новый query-param на existing endpoint).
- **`lifespan` в `backend/app/__init__.py`** — добавление daily-cron-like блока для D-17 alerts (создание Tasks за 30 дней до просрочки).
- **`__init__.py:include_router`** — новые routers: `vehicles.py`, `vehicle_attachments.py`, `vehicle_repairs.py`, `vehicle_odometer.py`, `fuel_logs.py`, `trips.py`, `external_drivers.py`, `vehicles_dashboard.py`. Регистрировать ПОСЛЕ catch-all `/{vehicle_id:int}` endpoint'ов (см. Gotcha FastAPI routing).

</code_context>

<deferred>
## Deferred Ideas

- **GPS-трекеры в реальном времени** — интеграция с n8n + Mapon/Wialon/Glonass-Soft API. Отдельная фаза 30+.
- **OCR ПТС/СТС/чеков заправки** — авто-распознавание полей при upload документа. Через ML модель или API (Yandex Vision / Tabula). Отдельная фаза 31+.
- **Маршруты на карте** — Yandex/2GIS embedded карта с маршрутом ТС за выбранный день. Отдельная фаза.
- **Имущество → Оборудование** — заглушка в навигации, реализация — отдельная фаза.
- **Имущество → Прочее** — заглушка в навигации, реализация — отдельная фаза.
- **PDF-экспорт путевых листов** — пока только .docx (D-19). При необходимости — отдельный мелкий PR через reportlab или libreoffice docker.
- **Кастомизация шаблонов путёвок по орг** — паттерн Phase 19 (DOC_TYPES + upload через UI). Сейчас 3 базовых .docx в репозитории.
- **Парсинг QR-кода чеков заправки → авто-FuelLog** — паттерн Phase 21-08 qrDecode. Отдельная мелкая фаза.
- **«Деньги ушли на топливо/ремонт» сводный отчёт через Phase 25 Report Builder** — новый field_registry source 'vehicle' + 'fuel_log' + 'vehicle_repair'. Делается опционально внутри Phase 29 (план 29-XX), либо отдельная мелкая интеграция.
- **Email уведомления о просрочке** — D-17 без email, только баннер + Task. Email — opt-in через настройки пользователя, отдельная фаза.
- **Роль «Ответственный за автопарк» (vehicles_responsible)** — пока флаг через `user_organizations.is_vehicles_responsible` или новый permission action. Полноценное «руководитель автопарка» с per-region scope — отдельная фаза.
- **Шиномонтажный календарь** — отдельная мелкая надстройка над VehicleRepair.

</deferred>

---

*Phase: 29-vehicle-fleet*
*Context gathered: 2026-05-19*
