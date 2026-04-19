# Phase 14: Risk Radar Dashboard (Neon Telemetry) - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Альтернативное визуальное представление текущего Dashboard в стиле Neon Telemetry — "mission control" — где данные поданы как приоритизированный набор рисков (budget overruns, contract/payment delays, stalled wishes, framework-contract saturation). Читает те же данные, что и classic DashboardView.vue, но агрегирует и визуализирует их иначе.

**В scope:**
- Новая view `RiskRadarView.vue` с Neon Telemetry визуалом
- Toggle-переключатель между classic Dashboard и Risk Radar
- Обе реализации (classic + radar) поддерживают dark и light Vuetify темы
- Сохранение выбора режима между сессиями (per-user localStorage)

**Вне scope:**
- Модификация существующего [DashboardView.vue](frontend/src/views/DashboardView.vue) (2142 строки) — остаётся как есть
- Модификация `/api/dashboard/charts` (можно добавлять новые endpoints, но не ломать существующие)
- Новые бизнес-метрики, не выводимые из текущих данных (это были бы новые фазы)
- Мобильная адаптация Risk Radar (если базовый web-responsive достаточен)

</domain>

<decisions>
## Implementation Decisions

### Dashboard coexistence
- **D-01:** Classic [DashboardView.vue](frontend/src/views/DashboardView.vue) НЕ модифицируется. Risk Radar создаётся как независимая view (`RiskRadarView.vue`), без изменения existing Dashboard логики/layout/стилей.
- **D-02:** Пользователь может переключаться между Classic Dashboard и Risk Radar в любой момент. Выбор запоминается (localStorage ключ per-user), при следующем входе открывается последний использованный режим.

### Theming
- **D-03:** Обе реализации (Classic + Risk Radar) работают в обеих Vuetify темах — dark и light. Переключение темы Vuetify работает одинаково на обеих view.
- **D-04:** Neon Telemetry эффекты (glow, акцентные цвета) адаптируются под тему: в dark — полноценный neon с glow, в light — приглушённая палитра с сохранением узнаваемого radar-стиля. Компонент НЕ форсирует свою тему поверх Vuetify.

### Claude's Discretion
Следующие решения принимает Claude во время research и planning, согласно philosophy (implementation choices — работа разработчика):

- **Toggle UI placement** — где именно переключатель (AppBar chip group / in-page tabs / standalone button). Выбрать так, чтобы было единообразно и не ломало Vuetify tabs в существующем Dashboard.
- **Route strategy** — новый `/dashboard/radar` vs query param `?mode=radar` vs single `/dashboard` с внутренним switcher. Выбрать вариант с минимальной миграцией для existing deep links.
- **Risk metrics набор** — какие именно риски показываем (бюджет превышен, контракт просрочен, платёж не прошёл, заявка зависла в approved, framework-contract saturation, FEO overcommit). Начать с 4–6 наиболее критичных для VSKS_CRM.
- **Risk score formulas** — как считаем уровень критичности (normalized 0–100, thresholds, weighted by amount). Опираться на существующие данные `/api/dashboard/charts`, `/api/purchases`, `/api/contracts`, `/api/wishes`.
- **Визуальная композиция** — центральный radar/polar chart + телеметрийные панели VS grid с отдельными risk-карточками VS heatmap субсидий. Выбрать то, что лучше читается с 5 секунд взгляда.
- **Палитра Neon** — конкретные hex-коды акцентов (cyan/magenta/amber/lime или cyan/violet/amber). Палитра должна сочетаться с existing glassmorphism (Wiza-стиль) и иметь 3–4 уровня severity.
- **Визуальные эффекты** — dot-grid фон, radar sweep анимация, glow на critical, pulse для active alerts, scan-line overlay. Использовать сдержанно — данные > украшения.
- **API strategy** — reuse `/api/dashboard/charts` + клиентский composable `useRiskScores()` (быстрее стартует, нет backend-миграций) VS новый `/api/dashboard/risks` endpoint (чище разделение). Решение принять в research-фазе после оценки сложности клиентского расчёта.
- **Interactions** — hover tooltip, click drill-down в список проблемных закупок, alerts ticker снизу, auto-refresh. Минимальный набор для MVP.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project specs
- [.planning/ROADMAP.md](.planning/ROADMAP.md) — Phase 14 entry (line ~296) + предыдущие фазы для понимания эволюции Dashboard
- [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md) — BUDGET-01..09, CONTRACT-01..07, WISHES-01..07 — источники данных для risk metrics

### Existing Dashboard implementation (read-only reference)
- [frontend/src/views/DashboardView.vue](frontend/src/views/DashboardView.vue) — classic view, 2142 строки. Изучить chart options, API usage, KPI структуру, grid-layout-plus паттерн, but НЕ модифицировать.
- [frontend/src/views/AnalyticsView.vue](frontend/src/views/AnalyticsView.vue) — аналогичный паттерн tab, 331 строка.
- [frontend/src/components/BudgetDrillDownDialog.vue](frontend/src/components/BudgetDrillDownDialog.vue) — готовый drill-down UX, переиспользуем.
- [frontend/src/components/BudgetHistoryDialog.vue](frontend/src/components/BudgetHistoryDialog.vue) — event-log паттерн для alerts-ticker.
- [frontend/src/components/StatusPieWithWishes.vue](frontend/src/components/StatusPieWithWishes.vue) — ApexCharts donut с Vue reactivity.

### Frontend stack references
- [frontend/src/main.ts](frontend/src/main.ts) — регистрация `VueApexCharts` (уже подключено, используем `<apexchart>`).
- [frontend/src/router/index.ts](frontend/src/router/index.ts) — соглашения route registration, employee guards, meta.title.
- [frontend/src/api.ts](frontend/src/api.ts) — apiFetch + JWT паттерн для любых новых API вызовов.

### Backend data sources (для risk metric расчёта)
- [backend/app/routers/dashboard.py](backend/app/routers/dashboard.py) — существующий агрегатор KPI/charts, источник данных классического Dashboard.
- [backend/app/routers/purchases.py](backend/app/routers/purchases.py) — Purchase model + статусы, `_check_budget()` логика, transition дата.
- [backend/app/routers/contracts.py](backend/app/routers/contracts.py) — framework-limited утилизация, ceiling checks.
- [backend/app/routers/wishes.py](backend/app/routers/wishes.py) — lifecycle статусы (draft/submitted/approved/rejected/converted) для "stalled wish" detection.

### Design language / prior feedback
- [.planning/STATE.md](.planning/STATE.md) — фиксация: "Risk Radar — альтернативный визуал Dashboard (Neon Telemetry стиль) с toggle classic/radar, без модификации DashboardView.vue".
- [.planning/phases/](.planning/phases/) — предыдущие CONTEXT.md для соблюдения established design language (glassmorphism, gradient text, dot-grid — Wiza-стиль, 2026-04-14).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`<apexchart>` компонент** (via vue3-apexcharts, [main.ts](frontend/src/main.ts)) — уже зарегистрирован глобально. Поддерживает donut, radialBar, radar, polar, area, bar, heatmap.
- **grid-layout-plus** (GridLayout/GridItem) — Risk Radar может тоже быть draggable/resizable как Summary tab классического Dashboard. Layout сохраняется в localStorage per-user.
- **useAnimatedNumber.ts** (easeOutExpo) — для плавной анимации risk-скоров.
- **Toast system** (useToast + [ToastContainer.vue](frontend/src/components/ToastContainer.vue)) — для алертов при критических рисках.
- **Glassmorphism стили** (AppBar glass blur, KPI glow hover) — established design language для Neon Telemetry fit-in.

### Established Patterns
- **API paradigm:** `apiFetch<T>('/api/...')` из [api.ts](frontend/src/api.ts), JWT автоматически подтягивается.
- **Subsidy year/multi-select filtering:** ВСЕ dashboard-виджеты принимают `selectedYear` + `selectedSubsidyIds` — Risk Radar должен следовать этому паттерну (читай лог DashboardView header, строки 14–28).
- **Dark/light Vuetify theming:** используется стандартный `useTheme()`. Компоненты реагируют на `theme.global.current.value.dark` (boolean). SCSS переменные через `v-theme`.
- **grid-layout-plus persistence:** localStorage ключ `dashboard-layout-${user_id}`. Для Risk Radar — отдельный ключ типа `risk-radar-layout-${user_id}`.
- **Tab UX:** `v-tabs` + `v-window` паттерн (как Summary/Analytics в DashboardView строка 72–79). Применим для in-page toggle, если выберется этот вариант.

### Integration Points
- **[frontend/src/router/index.ts](frontend/src/router/index.ts):** добавить маршрут для Risk Radar (`/dashboard/radar` рекомендуется, lazy-load как ContractsView/StaffView). Учесть `EMPLOYEE_ALLOWED` guard — Risk Radar нужно employee доступ или нет? (Claude: по умолчанию — только non-employee, как classic Dashboard.)
- **[frontend/src/components/AppBar.vue](frontend/src/components/AppBar.vue):** сюда попадает toggle "Classic / Radar" (если выберется AppBar размещение) — учесть existing AppBar glass-blur стиль.
- **Backend:** если выбран путь `/api/dashboard/risks` endpoint — добавляется в [backend/app/routers/dashboard.py](backend/app/routers/dashboard.py) рядом с `charts`. Миграций БД не требуется (metrics вычисляются из уже существующих таблиц).
- **Vuetify theme config:** если Risk Radar требует специфических CSS переменных для neon-палитры в каждой теме, добавляются в Vuetify theme config (не хардкодить hex в компонентах).

</code_context>

<specifics>
## Specific Ideas

- **"Mission control" feel** — Risk Radar должен чувствоваться как telemetry panel в cockpit/ops dashboard. Пользователь должен за 5 секунд увидеть: всё ли ок, или что-то горит.
- **Toggle должен быть явным и быстрым** — не "зарыт" в настройках. Пользователь переключается между режимами как между tabs.
- **Обе темы — first-class citizens** — не делать Risk Radar "только dark, light — второсортный". Light версия должна быть такой же убедительной.
- **Не трогать DashboardView.vue** — это существующий 2142-строчный view с draggable widgets, который работает. Любой бойлерплейт (subsidy selector, year chips) копируется/выносится в shared composable, не модифицируется in-place.

</specifics>

<deferred>
## Deferred Ideas

- **Drill-down от риска к конкретной закупке** — если реализация потребует больше 1 плана, вынести в Phase 14.1.
- **Web Push уведомления при появлении critical risk** — отдельная phase (инфра есть из Phase 10, но требует отдельной бизнес-логики триггеров).
- **Исторический тренд риск-скоров** (radar сравнивает текущее состояние с прошлым месяцем) — v2, требует хранения snapshot'ов.
- **Customizable risk weights per-user** — v2, пользователь настраивает вес каждого риска.
- **Risk Radar для мобильного** (оптимизированный layout под 375px) — отдельная задача, решается после базовой desktop версии.
- **Экспорт Risk Radar в PDF/PNG** для отчётов — v2.

</deferred>

---

*Phase: 14-risk-radar-dashboard-neon-telemetry*
*Context gathered: 2026-04-19*
