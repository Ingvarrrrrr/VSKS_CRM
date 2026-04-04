---
phase: 08-торговые-площадки
plan: "02"
subsystem: infra
tags: [n8n, roseltorg, fabrikant, workflow, publication, test-mode]

# Dependency graph
requires:
  - phase: publications-model
    provides: Publication model and /api/publications/{id}/status PATCH endpoint
provides:
  - n8n workflow for Росэлторг.Бизнес with token check and error callback
  - updated Fabrikant workflow with FABRIKANT_TEST_MODE test mode
affects:
  - 08-03 (SMTP КП email)
  - publications UI (SubsidiesView, BillingView)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - n8n workflow JSON with env variable access via $env
    - Token-check IF branch pattern before external API call
    - CRM PATCH callback via http://backend:8000 docker network

key-files:
  created:
    - n8n_workflows/roseltorg_publish.json
  modified:
    - n8n_workflows/fabrikant_publish.json

key-decisions:
  - "Use ROSELTORG_TOKEN env var in n8n — when empty, workflow short-circuits to error callback with descriptive message"
  - "FABRIKANT_TEST_MODE=true returns TEST-FAB-{timestamp} fakeId for UI flow testing without real SOAP"
  - "Production Росэлторг URL: https://rb.roseltorg.ru/api/v1/lots (per additional_context)"

patterns-established:
  - "n8n error-first: check prerequisites (token/mode) before external API, return descriptive error_text"
  - "CRM callback pattern: PATCH http://backend:8000/api/publications/{publicationId}/status"

requirements-completed: [PUB-03, PUB-04, PUB-05]

# Metrics
duration: 15min
completed: 2026-03-20
---

# Phase 08 Plan 02: Росэлторг + Фабрикант workflows Summary

**n8n workflow для Росэлторг с проверкой ROSELTORG_TOKEN и error callback, плюс Фабрикант с FABRIKANT_TEST_MODE=true возвращающим TEST-FAB-{timestamp} для UI flow тестирования**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-20T00:00:00Z
- **Completed:** 2026-03-20
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Создан roseltorg_publish.json: 11 nodes, webhook на roseltorg-publish, token check через IF, procedure_type маппинг на templateId, error callback с инструкцией по ROSELTORG_TOKEN
- Обновлён fabrikant_publish.json: node "Фабрикант API / Test Mode" — при FABRIKANT_TEST_MODE=true возвращает success + TEST-FAB-{timestamp}, при false — инструкцию по SOAP credentials
- Оба файла валидный JSON, готовы к импорту через n8n UI

## Task Commits

1. **Task 1: Создать roseltorg_publish.json** - `0c9c2ac` (feat)
2. **Task 2: Обновить fabrikant_publish.json** - `65c60d0` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `n8n_workflows/roseltorg_publish.json` — новый workflow для Росэлторг.Бизнес: Webhook → подготовка данных → проверка токена → API вызов → success/error callback в CRM
- `n8n_workflows/fabrikant_publish.json` — обновлён: node "Фабрикант API / Test Mode" с логикой FABRIKANT_TEST_MODE

## Decisions Made

- Использован production URL `https://rb.roseltorg.ru/api/v1/lots` (не /integration/v1) — согласно additional_context в плане
- При отсутствии токена workflow делает PATCH error callback (а не просто молча падает) — UX-friendly поведение
- FABRIKANT_TEST_MODE проверяется как строка `=== 'true'` для совместимости с n8n Variables (always string)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Python encoding issue при валидации JSON на Windows (cp1251 vs utf-8) — решено добавлением `encoding='utf-8'` в python вызов. JSON файлы валидны.

## User Setup Required

После выполнения этого плана требуется настройка в n8n UI:

1. **Импортировать** `n8n_workflows/roseltorg_publish.json` через n8n UI → Import Workflow
2. **Создать переменную** `ROSELTORG_TOKEN` (пустая строка) в n8n Settings → Variables
3. **Активировать** workflow roseltorg_publish (зелёный toggle)
4. **Обновить** fabrikant_publish.json через n8n UI (или re-import)
5. **Создать/обновить переменную** `FABRIKANT_TEST_MODE=true` в n8n Settings → Variables

## Next Phase Readiness

- Оба workflow готовы к импорту и тестированию через CRM UI (SubsidiesView публикация)
- Следующий план 08-03: SMTP КП email через Yandex 360 (требует app password для z@vsks.ru)
- Когда будет получен реальный ROSELTORG_TOKEN — сменить на настоящий и активировать workflow

---
*Phase: 08-торговые-площадки*
*Completed: 2026-03-20*
