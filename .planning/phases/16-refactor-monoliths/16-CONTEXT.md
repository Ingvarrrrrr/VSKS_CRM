# Phase 16: Refactor Monoliths - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Pure-refactor phase: разрезать 3 монолита (backend `purchases.py` 3233 строки, backend `tasks.py` 1698 строк, frontend `MyTasksView.vue` 2188 строк — суммарно 7119 строк) на тематические модули ≤ 800 строк. Границы HTTP-контрактов (URL, response shapes) и БД-схемы фиксируются; меняются только внутренние Python import-пути и размещение Vue-компонентов.

Out of scope: новая функциональность, миграции БД, переписывание на другой стек, извлечение `backend/app/services/` business-layer'а (это отдельная архитектурная фаза в будущем).

</domain>

<decisions>
## Implementation Decisions

### Extraction Order
- **D-01:** Backend сначала (purchases.py → tasks.py), frontend последним.
  - *Rationale:* E2E тесты (67 core + 3 phase-15) бьют по backend URL'ам; если внутренности URL не поменялись — E2E ловит frontend-breakage сразу. Параллельная работа по 3 монолитам делает blame diffusion.
- **D-02:** Внутри каждого монолита — от самых изолированных helpers к центральным CRUD.
  - *Rationale:* extract Excel-экспорта (чистый, без зависимостей) даёт безопасный первый commit и валидирует паттерн, до того как трогать transitions (200-строчная функция с 40+ branches).

### Backend Module Granularity (purchases.py → 6 модулей вместо 5)
- **D-03:** `purchases.py` — только CRUD (list, get, create, update, delete, bulk-delete). Целевой размер: ~600 строк.
- **D-04:** `purchase_transitions.py` — endpoint `POST /{pid}/transition` + `_assign_framework_seq` + field-guards (~250 строк).
- **D-05:** `purchase_budget.py` — `_check_budget` + FEO cap validation (~150 строк).
- **D-06:** `purchase_members.py` — `PATCH /{pid}/assign`, `POST /{pid}/consent`, `PATCH /{pid}/kanban-status`, `PATCH /{pid}/substatus`, `PATCH /{pid}/comment`, `_create_assignment_chat_room` (~350 строк).
- **D-07:** `purchase_export.py` — `GET /export/columns`, `GET /export/excel`, `GET /import/template`, `POST /import` (~400 строк).
- **D-08:** `purchase_items_import.py` — NEW (6-й модуль, не в ROADMAP). Excel items import + preview + mapped + smart + FEO-format + `_upsert_product_to_catalog` + `_ocr_pdf_to_rows` + `_legacy_*` helpers (~800 строк — ближе к верхней границе, но цельная тема).
  - *Rationale:* Currently ~720 строк (L1847-2582). Без выделения `purchases.py` даже после других extractions остаётся > 1000 строк.

### Backend Module Granularity (tasks.py → 5 модулей)
- **D-09:** `tasks.py` — только CRUD + list + get/subtasks + categories/departments (~450 строк).
- **D-10:** `task_visibility.py` — `_get_visible_user_ids` + hierarchy/chat-room participation visibility + `_enrich_tasks` (~200 строк).
- **D-11:** `task_badges.py` — `GET /badges` + `GET /org-summary` + `GET /init` (~300 строк).
- **D-12:** `task_delegation.py` — `POST /{id}/consent`, `GET /pending-consent`, `GET /consent-declines`, `POST /consent-declines/{id}/acknowledge` + `_create_task_chat_room` + `_set_assignees` (~350 строк).
- **D-13:** `task_comments.py` — `GET/POST/DELETE /{id}/comments` + broadcast + dismiss-field (~350 строк).

### Frontend Module Granularity (MyTasksView.vue → 1 orchestrator + 5 components)
- **D-14:** `MyTasksView.vue` — остаётся оркестратором: router, state bindings, api вызовы, tab switching. Target: ≤ 600 строк.
- **D-15:** `frontend/src/components/my-tasks/OrgSelector.vue` — карточки организаций + «Все организации» + счётчики.
- **D-16:** `frontend/src/components/my-tasks/TasksTable.vue` + `TasksKanban.vue` — вкладка «Задачи» (list + kanban view modes).
- **D-17:** `frontend/src/components/my-tasks/PurchasesTable.vue` + `PurchasesKanban.vue` — вкладка «Закупки» (list + kanban view modes).
- **D-18:** `frontend/src/components/my-tasks/OrgSummaryBar.vue` — header-счётчики + badges.
  - *Rationale on folder:* `/components/my-tasks/` подпапка — паттерн уже зафиксирован в Phase 14 (Radar components live co-located).

### Shared Helpers Location
- **D-19:** Shared helpers остаются в originating модуле; другие модули импортируют (`from app.routers.purchase_budget import _check_budget`).
  - *Rationale:* Нулевой архитектурный риск. Введение `backend/app/services/` business-layer'а — отдельная фаза (кандидат на Phase 17). Для refactor-only phase import-граф = достаточная изоляция.
- **D-20:** `_purchase_to_full`, `_item_to_out` → в `purchases.py` (центральный CRUD).
- **D-21:** `_get_visible_user_ids` → в `task_visibility.py`. На сегодня используется ТОЛЬКО внутри tasks.py (grep подтверждает), cross-file импорт не возникнет.

### Public API Preservation (STRICT)
- **D-22:** Все HTTP URL'ы FROZEN: `GET /api/purchases/`, `POST /api/purchases/{pid}/transition`, etc. — ни один не переименовать, ни сгруппировать, ни версионировать.
- **D-23:** Response schemas FROZEN (PurchaseOutFull, TaskOut и т.д.). Поля не добавлять, не удалять, не переупорядочивать.
- **D-24:** Все новые роутеры монтируются в `backend/app/__init__.py` (текущая точка регистрации 38 router'ов, L281-318) с одинаковыми `prefix` как у разделяемого роутера.
  - Напр., и `purchases.router`, и `purchase_transitions.router` имеют `prefix="/api/purchases"` → endpoint'ы на том же пути.

### Commit Granularity
- **D-25:** Каждый commit = «extract X from Y», атомарный, build-green. ROADMAP success criteria уже фиксирует это.
  - После каждого extract: (a) удалить код в Y, (b) добавить в X, (c) обновить imports, (d) `docker compose build backend` green, (e) `npx playwright test` на smoke-suite green, (f) commit.

### Testing Strategy (0-regression guarantee)
- **D-26:** Primary gate — **все E2E 67+3 тестов** pass до и после каждого commit-extract. `npx playwright test` обязателен локально перед каждым push.
- **D-27:** Добавить **1 smoke integration test на каждый новый router-модуль**: assert router mounts, happy-path 200-запрос возвращает тот же shape что до refactor'а. File: `backend/tests/test_routers_mounted.py` (один файл с параметризованными тестами).
- **D-28:** Frontend compat — `npm run build` zero-warn до и после. Визуальный snapshot MyTasksView до/после (ручной скриншот на этапе UAT, не автоматизировано).

### Claude's Discretion
- Внутренние имена private-helpers (`_foo` vs `_bar`) — планер решает.
- Порядок extraction внутри каждого монолита — планер приоритезирует (рекомендация: легкие/изолированные первыми).
- Точный split между `TasksTable.vue` и `TasksKanban.vue` (один компонент с prop `:mode` vs два отдельных) — планер решает на этапе frontend-research.
- Нужен ли `backend/app/routers/_shared.py` для 2-3 чисто утилитарных функций (форматтеры) — планер решает, если возникнет кросс-модульная дупликация.

### Folded Todos
_Нет. Оба todos из `todo match-phase 16` (Settings Page feature-toggles — UI, Rebuild nginx autodeploy — infra) по сути keyword-матчи, к refactor-фазе не относятся. Отмечены как reviewed в deferred ниже._

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope & State
- `.planning/ROADMAP.md` §Phase 16 — полный скоуп, non-goals, success criteria (строки ≤ 800/файл, E2E 67+3 pass, атомарные commits).
- `.planning/STATE.md` — `Roadmap Evolution` секция объясняет мотивацию Phase 16; `Pending from Feedback` для понимания, какие фичи могут «подрезать» рефакторингом.
- `C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/05_Gotchas.md` §«Архитектура — долг по модульности» — оригинальная фиксация проблемы + правило «один процесс — один модуль» начиная с Phase 13+.

### Backend monoliths (targets)
- `backend/app/routers/purchases.py` — 3233 строки, 88 функций; целевые extractions размечены в D-03..D-08.
- `backend/app/routers/tasks.py` — 1698 строк, 52 функции; extractions размечены в D-09..D-13.
- `backend/app/__init__.py` L281-318 — центральная точка регистрации 38 роутеров. ВСЕ новые роутеры МУСТ быть подключены здесь с корректным `prefix`.

### Backend patterns (existing split examples — reference)
- `backend/app/routers/purchase_files.py` — уже отдельный модуль, следовать его структуре (router + prefix + include).
- `backend/app/routers/purchase_events.py` — аналогично.
- `backend/app/routers/purchase_approvals.py` — аналогично.

### Frontend monolith (target)
- `frontend/src/views/MyTasksView.vue` — 2188 строк, ~137 top-level декларации в `<script setup>`; extractions размечены в D-14..D-18.

### Frontend patterns (existing split examples)
- `frontend/src/components/PurchaseItemsEditor.vue` — Phase 15 extraction, шаблон для «views → components экстракции».
- `frontend/src/components/RiskMetricCard.vue`, `AlertsTicker.vue` (Phase 14) — pattern для co-located components используемых одним view.

### E2E Test Suite (regression gate)
- `e2e/*.spec.ts` — 67 core + 3 phase-15 smoke = 70 tests. Обязательный gate для каждого commit-extract.
- `e2e/helpers.ts` — `dismissOrgPicker`, `login`, `waitForOverlays`, `collectApiErrors`. Использовать в smoke-тестах новых роутеров.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Router-split pattern уже в проекте:** `purchase_files.py`, `purchase_events.py`, `purchase_approvals.py` — 3 примера чистого extract'а из `purchases.py`. Planner должен следовать этому паттерну (router с префиксом, регистрация в `__init__.py`).
- **Phase 14 & 15 component extractions:** `PurchaseItemsEditor.vue`, `RiskMetricCard.vue`, `AlertsTicker.vue` — паттерн экстракции Vue-компонентов из монолита (использовать same props conventions, emit events вместо прямых api-вызовов).
- **E2E helpers** (`e2e/helpers.ts`) — готовые login/waitForOverlays/dismissOrgPicker для smoke-тестов новых роутеров.
- **Pytest fixtures** (если есть в `backend/tests/`) — для test_routers_mounted.py.

### Established Patterns
- **FastAPI APIRouter + app.include_router(prefix=…)** — каждый модуль = один `router = APIRouter(prefix="…")`, регистрация в `backend/app/__init__.py`.
- **Async SQLAlchemy 2.0 via `Depends(get_db)`** — все CRUD-хендлеры. Extractions не меняют этот паттерн.
- **`Depends(require_role(*ROLES))`** — auth gate на каждом endpoint. После split каждый новый роутер должен иметь те же role guards.
- **Vue `<script setup>` + composables** (`useChat`, `useRiskScores`, `useDashboardMode`) — шаблон: общий state в composable, компонент импортирует. При extraction MyTasksView подкомпоненты могут получить composable `useMyTasksState` (опционально, Claude's discretion).
- **Vuetify 3 в компонентах** — props типизируются, emit events через `defineEmits`.

### Integration Points
- **Backend `backend/app/__init__.py` L281-318** — точка, где новые роутеры монтируются. Grep: `app\.include_router`.
- **Frontend `router/index.ts`** — не трогается (URL `/my-tasks` остаётся прежним, меняется только внутренняя композиция view).
- **`frontend/src/api.ts`** — не трогается; endpoint-пути frozen.
- **n8n workflows** (`backend/app/routers/publications.py`, `routers/telegram_webhook.py`) — НЕ трогаются, они уже изолированы.

### Potential Pitfalls
- **Private helpers prefixed with `_`** часто используются в 2+ функциях одного файла. После extraction требуется либо экспортировать (убрать `_`), либо дублировать (плохо). План: экспортировать, оставив underscore prefix для визуального маркера «internal but importable».
- **Импорты `from app.routers.purchases import ...`** могут использоваться в других файлах (tests, scripts). Grep до extract'а: `grep -r "from app.routers.purchases"`. Все эти импорты ОБЯЗАН обновить тот же коммит.
- **FastAPI route registration order matters:** если `purchases.router` регистрируется до `purchase_transitions.router` и оба имеют `prefix="/api/purchases"`, то overlapping routes (`/{pid}/transition` vs `/{pid}`) должны быть разрешены. Решение: transition-роут более specific чем generic `/{pid}`, FastAPI matches longer prefix first. Тест: `test_routers_mounted.py` должен ловить конфликты.
- **`MyTasksView.vue` `<script setup>`** использует `<style scoped>`. При extraction компонентов нужно перенести relevant CSS в child components scoped styles (не loss, не duplicate).

</code_context>

<specifics>
## Specific Ideas

- «Экстракции делаем как Phase 15 — один extract = один commit, build green на каждом шаге. Никаких long-lived branches.»
- Правило «один процесс — один модуль» из 05_Gotchas — это философская основа phase. Планер должен интерпретировать его строго: если 2 endpoint'а отвечают на разные бизнес-вопросы (напр. budget-check vs member-assignment), они живут в разных файлах.
- Tests-first принцип: до начала extract'а запустить `npx playwright test` и зафиксировать baseline. Не начинать если хоть один red — сначала чинить.

</specifics>

<deferred>
## Deferred Ideas

### Reviewed Todos (not folded)
- **«Страница настроек — управление функционалом и уровнями доступа»** (`2026-04-04-settings-page-feature-toggles-access-levels.md`, score 0.9) — keyword-match на слова «frontend/views/vue», но по смыслу это новая UI-фича (feature toggles для админки), не рефакторинг. Отложено для отдельной фазы (возможно Phase 17 или backlog).
- **«Rebuild nginx in autodeploy for WebSocket support»** (`2026-04-05-...`, score 0.4) — инфраструктурный todo, к refactor-монолитов-phase не относится. Отложено в 04_TODO.

### Deferred (out of Phase 16 scope)
- **`backend/app/services/` business-layer.** Введение отдельного слоя между routers и models (DDD-style) — крупное архитектурное изменение. На Phase 16 оставляем helpers в router-модулях с import'ами; extraction в services — кандидат на Phase 17 (предложить в STATE.md после Phase 16 complete).
- **Unit-тесты для extracted helpers.** Добавлять только smoke integration tests для router-mount проверки (D-27). Полное unit-покрытие хелперов — отдельная фаза quality.
- **Cleanup `.backup.vue`, `AddProductDialogFixed2.vue`, `DashboardViewSimple.vue`, `CreateOrderViewSimple.vue`.** Уже зафиксировано в `04_TODO.md` §«Dead code cleanup». НЕ делать в Phase 16, чтобы не размывать scope («один процесс — один модуль», не «plus cleanup»).
- **localStorage унификация `auth_token` vs `access_token`.** Зафиксировано в 04_TODO и 05_Gotchas. Вне scope.
- **Многоэтапная декомпозиция OrdersView.vue, CreateOrderView.vue.** Эти view тоже крупные (CreateOrderView раньше был 1900+ строк до Phase 15-03), но не попали в 16 scope. Отдельная фаза 16.1 если будут расти вновь.

</deferred>

---

*Phase: 16-refactor-monoliths*
*Context gathered: 2026-04-19*
