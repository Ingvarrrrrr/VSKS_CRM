# Phase 16: Refactor Monoliths - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-19
**Phase:** 16-refactor-monoliths
**Mode:** AUTO (harness auto-mode active) — Claude auto-selected all gray areas and recommended defaults without AskUserQuestion prompts. Log преследует цель дать пользователю возможность ревьюить каждый выбор позже.
**Areas discussed:** Extraction Order, Backend Module Granularity (purchases), Backend Module Granularity (tasks), Frontend Module Granularity, Shared Helpers Location, Public API Strictness, Frontend Components Folder, Commit Granularity, Testing Strategy

---

## Extraction Order

| Option | Description | Selected |
|--------|-------------|----------|
| Backend first (purchases → tasks), frontend last | Backend URL'ы — контрактная граница, E2E тесты ловят нарушения. Frontend после, проверяется визуально + E2E | ✓ |
| Frontend first, backend second | Легче увидеть UI-regressions, но bigger blast radius если URL меняются | |
| Parallel all 3 | Fastest в сумме, но blame diffusion при регрессиях | |

**User's choice:** `[auto]` Backend first
**Notes:** E2E gate работает с backend; frontend check полностью покрывается E2E + визуальным snapshot.

---

## Backend Module Granularity — purchases.py

| Option | Description | Selected |
|--------|-------------|----------|
| 5 модулей (по ROADMAP) | purchases + transitions + budget + members + export | |
| 6 модулей (ROADMAP + items_import отдельно) | Добавить `purchase_items_import.py` для ~720 строк Excel import кода | ✓ |
| 4 модуля (merge members+transitions) | Более плоская декомпозиция | |

**User's choice:** `[auto]` 6 модулей
**Notes:** ROADMAP list'ит 5, но Excel items import (L1847-2582) ~720 строк — без него `purchases.py` после split'а всё равно >1000 строк. Items import — cohesive тема (preview/mapped/smart + FEO-format + _upsert_product_to_catalog + _ocr_* + _legacy_*).

---

## Backend Module Granularity — tasks.py

| Option | Description | Selected |
|--------|-------------|----------|
| 5 модулей (по ROADMAP) | tasks + visibility + badges + delegation + comments | ✓ |
| 4 модуля (merge delegation+comments в "collaboration") | Меньше файлов | |
| 6 модулей (split reports в отдельный) | Reports в `task_reports.py` | |

**User's choice:** `[auto]` 5 модулей (по ROADMAP)
**Notes:** Reports (`/report/by-department`) — один endpoint, ~90 строк; оставляем в `tasks.py` core как исторически связанный.

---

## Frontend Module Granularity — MyTasksView.vue

| Option | Description | Selected |
|--------|-------------|----------|
| Orchestrator + 5 co-located components | По ROADMAP: MyTasksView (state/api) + OrgSelector + TasksTable + TasksKanban + PurchasesTable + PurchasesKanban + OrgSummaryBar | ✓ |
| Orchestrator + 3 комбинированных компонента (Tasks/Purchases/OrgHeader) | Каждый с prop `:mode='kanban'\|'list'` внутри | |
| Полная перепись на Pinia store + slim view | Слишком большой scope | |

**User's choice:** `[auto]` Orchestrator + 5 co-located components
**Notes:** TasksTable + TasksKanban как 2 компонента — planner решает на этапе frontend-research (single component с `:mode` prop vs 2 компонента с shared composable). Помечено как Claude's Discretion в CONTEXT.md.

---

## Shared Helpers Location

| Option | Description | Selected |
|--------|-------------|----------|
| Keep in originating module, import from there | `_check_budget` в `purchase_budget.py`, `purchases.py` импортирует | ✓ |
| New `backend/app/routers/_shared.py` | Утилитарные функции в общий файл | |
| New `backend/app/services/` business-layer | DDD-style layer между routers и models | |

**User's choice:** `[auto]` Keep in originating module
**Notes:** Минимальный архитектурный риск для refactor-only phase. `services/` layer — серьёзное архитектурное изменение, кандидат на отдельную Phase 17 (зафиксировано в deferred ideas CONTEXT.md).

---

## Public API Preservation Strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Strict (URLs + response shapes frozen) | Меняются только Python import paths | ✓ |
| Opportunistic (rename URLs where logical) | Напр. `/api/purchases/{pid}/transition` → `/api/purchase-transitions/{pid}` | |
| Internal imports only | Не трогать даже import paths | |

**User's choice:** `[auto]` Strict
**Notes:** Ровно совпадает с ROADMAP non-goal «Изменения API контрактов (имена endpoints/URL-ов остаются)».

---

## Frontend Components Folder Structure

| Option | Description | Selected |
|--------|-------------|----------|
| `/components/my-tasks/` подпапка | Co-located с parent view | ✓ |
| `/components/tasks/` + `/components/orgs/` | Сегментировано по доменам | |
| Flat `/components/` с префиксом `MyTasks*` | Напр. `MyTasksOrgSelector.vue` | |

**User's choice:** `[auto]` `/components/my-tasks/` subfolder
**Notes:** Паттерн зафиксирован в Phase 14 (RiskMetricCard, AlertsTicker — планировалось как co-located, но лежат flat; confirm на planning и, если нужно, nest'нуть Radar тоже отдельным тикетом).

---

## Commit Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic «extract X from Y» per commit | Одна extraction = один commit, build green | ✓ (pre-locked in ROADMAP) |
| One commit per file split into modules | Все extractions из purchases.py в одном commit | |
| One commit per phase (backend/frontend) | Крупнозернистые коммиты | |

**User's choice:** Pre-locked в ROADMAP success criteria §5.
**Notes:** ROADMAP уже зафиксировал правило. Здесь просто подтверждено.

---

## Testing Strategy (0-regression)

| Option | Description | Selected |
|--------|-------------|----------|
| E2E full suite as gate + 1 smoke per router | 67+3 E2E + `test_routers_mounted.py` с параметризованными mount-тестами | ✓ |
| E2E only | 67+3 тестов как единственный gate | |
| E2E + full unit test coverage на helpers | Крупное расширение покрытия (out of scope) | |

**User's choice:** `[auto]` E2E + 1 smoke per new router
**Notes:** Smoke integration tests — минимальная страховка что роутеры смонтировались (`app.include_router` не забыт). Full unit coverage — отдельная quality-фаза.

---

## Claude's Discretion

- Точные имена private-helpers (`_foo` vs `_bar`).
- Порядок extraction внутри каждого монолита (рекомендация: лёгкие/изолированные первыми — export, затем budget, затем members, напоследок transitions).
- Split `TasksTable.vue` vs `TasksKanban.vue` — один компонент с `:mode` prop vs два компонента с shared composable. Решается на этапе frontend-research в plan-phase.
- Нужен ли `_shared.py` для 2-3 чисто утилитарных функций (форматтеры) — если при extraction возникнет реальная дупликация.

## Deferred Ideas

- `backend/app/services/` business-layer (кандидат на Phase 17)
- Full unit-coverage extracted helpers (отдельная quality phase)
- Cleanup `.backup.vue`, dead dialogs (уже в 04_TODO §Dead code cleanup)
- localStorage `auth_token` vs `access_token` унификация (в 04_TODO + 05_Gotchas)
- Дополнительные view-монолиты (OrdersView, CreateOrderView) — Phase 16.1 если вырастут снова

## Reviewed Todos (not folded)

- «Страница настроек — управление функционалом и уровнями доступа» (2026-04-04) — UI feature, не refactor
- «Rebuild nginx in autodeploy for WebSocket support» (2026-04-05) — infra, не refactor
