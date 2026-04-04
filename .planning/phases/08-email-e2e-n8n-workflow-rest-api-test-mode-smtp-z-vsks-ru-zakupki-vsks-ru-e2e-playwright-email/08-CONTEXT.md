# Phase 8: Торговые площадки + КП email + E2E - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Публикация закупок на торговые площадки (Росэлторг.Бизнес, Фабрикант) через n8n workflow, рассылка КП по email с z@vsks.ru, E2E Playwright тесты на публикацию и email. Реальные API Росэлторга/Фабрикант подключаются позже (нет credentials) — сейчас demo env + test mode.

</domain>

<decisions>
## Implementation Decisions

### Тип процедуры Росэлторг (templateId)
- Сотрудник выбирает тип процедуры вручную в диалоге публикации — не автоматически
- В диалог публикации на Росэлторг добавить dropdown: Запрос котировок / Запрос предложений / Конкурс / Аукцион
- Выбранный тип передаётся в n8n payload как `procedure_type` → маппится на templateId в workflow

### Поведение при отсутствии токена Росэлторг
- Публикация создаётся, n8n сразу возвращает status=error
- error_text = "Требуется Bearer Token Росэлторг — настройте в параметрах n8n (переменная ROSELTORG_TOKEN)"
- Видно в UI в секции публикаций карточки закупки

### Фабрикант — test mode
- n8n переменная `FABRIKANT_TEST_MODE=true` → workflow возвращает success с фиктивным externalId
- Позволяет проверить весь flow UI (publishing → published) без реального API
- error_text при FABRIKANT_TEST_MODE=false: инструкция как получить SOAP credentials на fabrikant.ru

### SMTP рассылка КП
- Настройки SMTP уже сохранены в SystemSetting таблице на сервере (z@vsks.ru, smtp.yandex.ru)
- Тест: отправить тестовое письмо на zakupki@vsks.ru через `POST /api/settings/smtp/test`
- КП рассылка: через существующий endpoint `POST /api/commercial-requests/send`

### E2E тесты — scope
- Тестировать **ошибочные сценарии** с понятными сообщениями:
  - Нет токена Росэлторг → статус error, текст ошибки виден в UI
  - Фабрикант test mode → статус published, externalId присвоен
  - КП email → SMTP test endpoint возвращает 200
- UI видимость: секция публикаций есть в карточке закупки, кнопки кликабельны
- Mock n8n callback: после POST публикации — вызвать PATCH /api/publications/{id}/status напрямую

### Claude's Discretion
- Точный маппинг procedure_type → templateId в n8n (технически, Claude разберётся)
- Формат polling в E2E тестах
- Структура JSON roseltorg_publish.json workflow

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/routers/publications.py`: готовый POST/GET/PATCH, `_build_publish_payload()` собирает все поля закупки
- `backend/app/routers/commercial_requests.py` (lines 152-205): `send_kp_emails()` — готовая SMTP рассылка
- `backend/app/routers/settings.py`: `POST /api/settings/smtp/test` — тест email
- `frontend/src/views/CreateOrderView.vue` (lines 1131-1239): UI секция публикации + диалог + polling
- `n8n_workflows/fabrikant_publish.json`: шаблон workflow для копирования структуры
- `e2e/` + `playwright.config.ts`: готовая инфраструктура тестов

### Established Patterns
- n8n webhook → n8n обрабатывает → PATCH callback в CRM (уже в Фабрикант workflow)
- Статусы публикации: pending → publishing → published/error
- Polling в Vue: каждые 2с, 30с максимум (реализован в CreateOrderView.vue)
- SMTP настройки из SystemSetting таблицы (не из .env)

### Integration Points
- Диалог публикации (CreateOrderView.vue ~line 1198): добавить dropdown выбора типа процедуры для Росэлторг
- `_build_publish_payload()`: добавить `procedure_type` в payload
- n8n Variables: `ROSELTORG_TOKEN`, `FABRIKANT_TEST_MODE`
- Новый файл: `n8n_workflows/roseltorg_publish.json`

</code_context>

<specifics>
## Specific Ideas

- Диалог публикации на Росэлторг должен показывать dropdown типа процедуры: Запрос котировок / Запрос предложений / Конкурс / Аукцион
- E2E акцент на ошибках: тест должен проверять что ошибки описательны и видны пользователю
- Фабрикант test mode — способ проверить весь flow до получения реальных credentials

</specifics>

<deferred>
## Deferred Ideas

- Полная интеграция с реальным API Росэлторг (production) — после получения Bearer Token
- Фабрикант SOAP интеграция — после получения credentials на fabrikant.ru/integration-api
- ЕИС (zakupki.gov.ru) интеграция — явно out of scope (в PROJECT.md)

</deferred>

---

*Phase: 08-торговые-площадки*
*Context gathered: 2026-03-20*
