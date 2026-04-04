---
phase: 08-торговые-площадки
plan: "01"
subsystem: api
tags: [fastapi, pydantic, n8n, roseltorg, publications]

requires: []
provides:
  - PublishRequest schema с опциональным полем procedure_type
  - publish_purchase передаёт procedure_type в n8n payload для Росэлторг
affects:
  - frontend PublicationsView (POST /api/publications/purchases/{id})
  - n8n roseltorg-publish workflow (templateId маппинг)

tech-stack:
  added: []
  patterns:
    - "Optional fields in Pydantic schemas for backward compatibility"
    - "Enriching _build_publish_payload result before handing to background task"

key-files:
  created: []
  modified:
    - backend/app/schemas/schemas.py
    - backend/app/routers/publications.py

key-decisions:
  - "procedure_type оставлен Optional[str] без enum-валидации — значения templateId уточнятся после получения реального токена Росэлторг"
  - "Обогащение payload происходит в publish_purchase, а не внутри _build_publish_payload — сохраняет чистоту helper-функции"

patterns-established:
  - "Опциональные платформо-специфичные поля добавляются как Optional[str] = None в PublishRequest"

requirements-completed:
  - PUB-01
  - PUB-02

duration: 5min
completed: 2026-03-20
---

# Phase 08 Plan 01: Торговые площадки — procedure_type Summary

**PublishRequest Pydantic-схема расширена Optional[str] procedure_type, который передаётся в n8n payload для маппинга templateId Росэлторг**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-20T00:00:00Z
- **Completed:** 2026-03-20T00:05:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Добавлено опциональное поле `procedure_type: Optional[str] = None` в `PublishRequest`
- Обратная совместимость: Фабрикант запросы без procedure_type продолжают работать
- `publish_purchase` дополняет payload["procedure_type"] перед вызовом n8n background task
- Python синтаксис обоих файлов проверен `py_compile`

## Task Commits

1. **Task 1: Добавить procedure_type в PublishRequest схему** - `c73350e` (feat)
2. **Task 2: Передать procedure_type в n8n payload** - `cd8b33c` (feat)

## Files Created/Modified

- `backend/app/schemas/schemas.py` - procedure_type: Optional[str] = None в PublishRequest
- `backend/app/routers/publications.py` - if body.procedure_type: payload["procedure_type"] = body.procedure_type

## Decisions Made

- procedure_type оставлен без enum-валидации допустимых значений — templateId уточнятся после получения токена Росэлторг
- Обогащение payload выполняется в `publish_purchase` (не в `_build_publish_payload`), чтобы не смешивать платформо-специфичную логику с общим сбором данных закупки

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Backend готов принимать procedure_type от фронтенда
- n8n workflow может читать `procedure_type` из payload для маппинга на templateId
- Следующий шаг: обновить фронтенд (PublicationsView) для передачи выбранного типа процедуры при публикации на Росэлторг

---
*Phase: 08-торговые-площадки*
*Completed: 2026-03-20*
