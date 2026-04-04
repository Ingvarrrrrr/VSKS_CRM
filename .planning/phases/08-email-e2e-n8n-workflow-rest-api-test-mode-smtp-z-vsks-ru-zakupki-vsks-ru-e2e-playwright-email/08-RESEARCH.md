# Phase 8: Торговые площадки + КП email + E2E — Research

**Researched:** 2026-03-20
**Domain:** n8n workflow integration (Росэлторг REST API, Фабрикант SOAP stub), SMTP email, Playwright E2E
**Confidence:** HIGH (all critical code read directly from repo)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Тип процедуры Росэлторг: сотрудник выбирает в диалоге (Запрос котировок / Запрос предложений / Конкурс / Аукцион)
- Нет токена Росэлторг → статус error с текстом: "Требуется Bearer Token Росэлторг — настройте в параметрах n8n (переменная ROSELTORG_TOKEN)"
- Фабрикант: FABRIKANT_TEST_MODE=true → workflow возвращает success с фиктивным externalId
- SMTP настройки уже в SystemSetting (z@vsks.ru, smtp.yandex.ru) — тест через POST /api/settings/smtp/test на zakupki@vsks.ru
- E2E акцент на ошибочных сценариях: нет токена Росэлторг → error виден в UI; Фабрикант test mode → published+externalId; SMTP test endpoint → 200

### Claude's Discretion

- Точный маппинг procedure_type → templateId в n8n
- Формат polling в E2E тестах
- Структура JSON roseltorg_publish.json workflow

### Deferred Ideas (OUT OF SCOPE)

- Полная интеграция с реальным API Росэлторг (production) — после получения Bearer Token
- Фабрикант SOAP интеграция — после получения credentials
- ЕИС (zakupki.gov.ru) — явно out of scope
</user_constraints>

---

## Summary

Фаза строится поверх готовой инфраструктуры публикаций. Backend (`publications.py`) уже полностью готов: POST/GET/PATCH endpoints, `_build_publish_payload()`, фоновый вызов n8n, callback PATCH `/api/publications/{id}/status`. Frontend (`CreateOrderView.vue`) уже имеет секцию публикаций, диалог, polling. Шаблон Фабрикант workflow (`fabrikant_publish.json`) — полный образец для копирования. SMTP backend (`settings.py`, `commercial_requests.py`) полностью готов.

Работа этой фазы сводится к четырём изменениям: (1) добавить dropdown `procedure_type` в диалог публикации для Росэлторг, (2) передать `procedure_type` в payload и расширить `PublishRequest` схему, (3) создать `roseltorg_publish.json` n8n workflow (копия Фабрикант с REST вместо SOAP), (4) улучшить Фабрикант workflow для test mode, (5) написать E2E тесты `12-publications.spec.ts`.

**Primary recommendation:** Копировать `fabrikant_publish.json` как основу для `roseltorg_publish.json`. Добавить один `v-select` в существующий диалог публикации. Весь сложный backend код уже написан — изменения минимальны.

---

## Standard Stack

### Core (все уже в проекте)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| n8n | running at :5678 | Workflow automation, webhook → HTTP | Уже развёрнут в docker-compose |
| httpx | installed | Async HTTP call из FastAPI background task | Уже используется в publications.py |
| Vuetify v-select | 3.x | Dropdown procedure_type в диалоге | Уже используется везде в проекте |
| Playwright | installed (e2e/) | E2E тесты | Уже настроен, 63 теста |
| smtplib | stdlib | SMTP отправка | Уже используется в settings.py и commercial_requests.py |

### n8n Nodes для roseltorg_publish.json
| Node type | Purpose |
|-----------|---------|
| `n8n-nodes-base.webhook` | Принять POST от CRM (path: `roseltorg-publish`) |
| `n8n-nodes-base.code` | Подготовить данные + маппинг procedure_type → templateId |
| `n8n-nodes-base.if` | Проверить ROSELTORG_TOKEN пустой? |
| `n8n-nodes-base.httpRequest` | POST на Росэлторг API (заглушка URL) |
| `n8n-nodes-base.if` | Проверить success из ответа |
| `n8n-nodes-base.httpRequest` x2 | PATCH callback → CRM success / error |
| `n8n-nodes-base.respondToWebhook` | Ответить 200 ok в CRM |

---

## Architecture Patterns

### Паттерн публикации (уже реализован, не менять)

```
CRM POST /api/publications/purchases/{id}
  → создаёт PlatformPublication(status="publishing")
  → background_task: POST n8n_webhook(payload + publication_id)
  → n8n обрабатывает
  → n8n PATCH /api/publications/{pub_id}/status  ← callback
  → CRM обновляет status, external_id, error_text
  → Vue polling каждые 2с (max 30с через 15 attempts)
```

### Изменение PublishRequest (минимальное)

Текущий `PublishRequest` в `schemas.py`:
```python
class PublishRequest(BaseModel):
    platform: str  # fabrikant / roseltorg_rb
```

Нужно добавить опциональное поле (обратная совместимость Фабрикант):
```python
class PublishRequest(BaseModel):
    platform: str
    procedure_type: Optional[str] = None  # только для roseltorg_rb
```

### Передача procedure_type через backend в n8n

В `publications.py` функция `publish_purchase`:
- Добавить `procedure_type: Optional[str]` в body
- Передать в `_build_publish_payload()` или добавить к payload после его построения:
```python
payload = await _build_publish_payload(purchase_id, db)
if body.procedure_type:
    payload["procedure_type"] = body.procedure_type
```

### Vue диалог — добавить dropdown для Росэлторг

В `CreateOrderView.vue` диалог публикации (lines ~1227-1267):

Текущий диалог показывает список площадок и кнопку "Опубликовать" для каждой.
Нужно: при клике "Опубликовать" на Росэлторг — показать sub-dialog ИЛИ добавить `v-select` прямо в диалог, который показывается только когда выбрана площадка `roseltorg_rb`.

**Рекомендуемый паттерн:** Промежуточный шаг в диалоге — локальный `ref selectedPlatform`, при выборе Росэлторг показываем v-select с `procedure_type`, затем кнопка "Подтвердить". Это менее инвазивно чем отдельный диалог.

```vue
<!-- Добавить в publishDialog, после списка площадок -->
<v-expand-transition>
  <div v-if="pendingPlatform === 'roseltorg_rb'" class="px-4 pb-2">
    <v-select
      v-model="roseltorgProcedureType"
      :items="ROSELTORG_PROCEDURE_TYPES"
      item-title="title"
      item-value="value"
      label="Тип процедуры"
      variant="outlined"
      density="compact"
      hide-details
    />
    <v-btn color="deep-purple" class="mt-2" @click="doPublish('roseltorg_rb', roseltorgProcedureType)">
      Опубликовать
    </v-btn>
  </div>
</v-expand-transition>
```

```typescript
const ROSELTORG_PROCEDURE_TYPES = [
  { value: 'request_quotations',  title: 'Запрос котировок' },
  { value: 'request_proposals',   title: 'Запрос предложений' },
  { value: 'competition',         title: 'Конкурс' },
  { value: 'auction',             title: 'Аукцион' },
]
const pendingPlatform = ref<string | null>(null)
const roseltorgProcedureType = ref<string | null>(null)
```

Изменить `doPublish(platform)` → `doPublish(platform, procedureType?)`:
```typescript
async function doPublish(platform: string, procedureType?: string) {
  const body: any = { platform }
  if (procedureType) body.procedure_type = procedureType
  // ... rest unchanged
}
```

### n8n roseltorg_publish.json — структура

Основа — копия `fabrikant_publish.json`. Ключевые отличия:

**Node 1 (webhook):** path = `"roseltorg-publish"`

**Node 2 (Code — prepare + token check):**
```javascript
const data = $input.first().json.body || $input.first().json;
const token = $env.ROSELTORG_TOKEN || '';
const procedureType = data.procedure_type || 'request_quotations';

// procedure_type → templateId mapping
const TEMPLATE_IDS = {
  request_quotations: 'QUOTATION',
  request_proposals:  'PROPOSAL',
  competition:        'COMPETITION',
  auction:            'AUCTION',
};
const templateId = TEMPLATE_IDS[procedureType] || 'QUOTATION';

return [{ json: {
  publicationId: data.publication_id,
  hasToken: !!token,
  token,
  templateId,
  procedureType,
  purchase: data,
}}];
```

**Node 3 (IF — token check):** `$json.hasToken === true`
- TRUE branch → Node 4 (HTTP Request к Росэлторг)
- FALSE branch → Node 6 (callback error с сообщением о токене)

**Node 4 (HTTP Request — Росэлторг API заглушка):**
```
Method: POST
URL: https://rb.roseltorg.ru/api/v1/lots  (заглушка — реальный URL после получения token)
Headers: Authorization: Bearer {{ $json.token }}
Body: { templateId, lotName, startPrice, ... }
```
На данном этапе без реального токена — этот branch недостижим (token всегда пустой).

**Node 5 (IF — success check):** `$json.success === true`

**Node 6 (callback error — нет токена):**
- error_text: "Требуется Bearer Token Росэлторг — настройте в параметрах n8n (переменная ROSELTORG_TOKEN)"
- PATCH /api/publications/{{ $json.publicationId }}/status с status=error

**Callback nodes — идентичны Фабрикант:** PATCH к `http://backend:8000/api/publications/{{ $json.publicationId }}/status`

### Фабрикант workflow — test mode улучшение

Изменить Node `"Вызов Фабрикант API (настроить!)"` — добавить логику test mode:

```javascript
const { publicationId, fabrikantPayload } = $input.first().json;
const testMode = $env.FABRIKANT_TEST_MODE === 'true';

if (testMode) {
  return [{ json: {
    publicationId,
    success: true,
    externalId: 'TEST-' + Date.now(),
    externalUrl: 'https://fabrikant.ru/test-lot',
  }}];
}

return [{ json: {
  publicationId,
  success: false,
  error: 'API Фабрикант не настроен. Получите SOAP credentials на fabrikant.ru/integration-api',
}}];
```

### E2E тест структура (12-publications.spec.ts)

Паттерн из существующих тестов (05-orders.spec.ts):
```typescript
test.beforeAll → login(page)
```

Три главных теста:

**Test 1: Фабрикант test mode → published**
```
1. GET /api/purchases → взять первый purchase.id
2. POST /api/publications/purchases/{id} body={platform:"fabrikant"}
3. Подождать PATCH callback (mock: вызвать PATCH напрямую со status="published", external_id="TEST-123")
4. GET /api/publications/purchases/{id} → проверить status="published", external_id присутствует
5. Открыть страницу закупки в браузере → проверить chip "Опубликовано" виден
```

**Test 2: Росэлторг — нет токена → error виден в UI**
```
1. POST /api/publications/purchases/{id} body={platform:"roseltorg_rb", procedure_type:"request_quotations"}
2. Вызвать PATCH callback напрямую: status="error", error_text="Требуется Bearer Token..."
3. GET /api/publications/purchases/{id} → проверить status="error"
4. Открыть страницу закупки → проверить error_text виден в таблице публикаций
```

**Test 3: SMTP test endpoint → 200**
```
1. POST /api/settings/smtp/test?to_email=zakupki@vsks.ru
2. Проверить response.ok === true (200)
3. (Если SMTP не настроен на тестовой машине → проверить 400 с понятным сообщением)
```

**Mock callback approach:** Т.к. n8n не запущен в E2E среде (или токены не настроены), тесты напрямую вызывают `PATCH /api/publications/{pub_id}/status` вместо ожидания реального callback от n8n. Это корректный подход — тестируем CRM логику, не n8n.

```typescript
// Паттерн mock callback
const pub = await request.post(`${baseURL}/api/publications/purchases/${purchaseId}`, {
  data: { platform: 'fabrikant' },
  headers: { Authorization: `Bearer ${token}` }
});
const pubData = await pub.json();

// Mock n8n callback
await request.patch(`${baseURL}/api/publications/${pubData.id}/status`, {
  data: { status: 'published', external_id: 'TEST-001' }
});
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| n8n workflow structure | Новую структуру с нуля | Копировать `fabrikant_publish.json` | Структура connection graph нетривиальна, шаблон уже проверен |
| SMTP test | Новый SMTP endpoint | `POST /api/settings/smtp/test?to_email=` | Уже реализован в settings.py:88 |
| КП email | SMTP логику | `POST /api/commercial-requests/send` | Уже реализован в commercial_requests.py:152 |
| Publication polling | Отдельный websocket | Существующий `pollPublication()` в CreateOrderView.vue | Уже работает, 2с интервал, 15 попыток |
| Auth token в E2E | Ручной логин | `login(page)` из `e2e/helpers.ts` | Уже реализован |

---

## Common Pitfalls

### Pitfall 1: n8n Variables vs процесс
**What goes wrong:** `$env.ROSELTORG_TOKEN` в n8n Code node — переменная читается из n8n Settings → Variables, не из docker-compose env.
**How to avoid:** В n8n UI: Settings → Variables → добавить `ROSELTORG_TOKEN` (пустое значение). Тогда `$env.ROSELTORG_TOKEN` вернёт `""` и ветка no-token сработает. Если переменная не создана — `$env.ROSELTORG_TOKEN` может бросить ошибку вместо пустой строки.
**Warning signs:** n8n workflow падает с "Cannot read property of undefined" вместо попадания в error branch.

### Pitfall 2: n8n webhook URL регистрация
**What goes wrong:** Новый workflow с path `"roseltorg-publish"` не активируется — webhook URL не регистрируется пока workflow не "Activated" (toggle в UI).
**How to avoid:** После импорта JSON в n8n — обязательно активировать workflow (зелёный toggle).

### Pitfall 3: Backend URL в n8n callback
**What goes wrong:** n8n использует `http://backend:8000` (docker internal). При локальной разработке без docker — URL недоступен.
**How to avoid:** В тестах не ждать n8n callback — вызывать PATCH напрямую из теста. В production — backend доступен как `backend:8000` внутри docker network.

### Pitfall 4: PublishRequest обратная совместимость
**What goes wrong:** Добавление `procedure_type` в PublishRequest ломает существующие запросы к Фабрикант если поле обязательное.
**How to avoid:** `procedure_type: Optional[str] = None` — обязательно опциональное.

### Pitfall 5: SMTP test endpoint требует Admin роль
**What goes wrong:** `POST /api/settings/smtp/test` требует `ADMIN_ROLES` (см. settings.py:93). E2E тест логинится как admin → ok. Но если тест пробует другую роль — 403.
**How to avoid:** E2E тест SMTP всегда запускать от admin. Тест КП (commercial-requests/send) требует `MANAGER_ROLES` — подходит admin тоже.

### Pitfall 6: E2E purchase_id зависит от данных
**What goes wrong:** Тест хардкодит `purchase_id=1` — в тестовой БД может не быть.
**How to avoid:** Тест делает `GET /api/purchases?limit=1` и берёт первый id из ответа.

### Pitfall 7: Фабрикант test mode — переменная в n8n
**What goes wrong:** `FABRIKANT_TEST_MODE` не создана в n8n Variables → `$env.FABRIKANT_TEST_MODE` вернёт undefined → `undefined === 'true'` = false → режим test mode не включится.
**How to avoid:** Создать переменную `FABRIKANT_TEST_MODE = true` в n8n Settings → Variables.

---

## Code Examples

### n8n: Token check node (Росэлторг)
```javascript
// Source: логика из fabrikant_publish.json + context решения
const data = $input.first().json.body || $input.first().json;
const token = $env.ROSELTORG_TOKEN || '';

const TEMPLATE_IDS = {
  'request_quotations': 'QUOTATION_REQUEST',
  'request_proposals':  'PROPOSAL_REQUEST',
  'competition':        'OPEN_COMPETITION',
  'auction':            'OPEN_AUCTION',
};

const procedureType = data.procedure_type || 'request_quotations';
const templateId = TEMPLATE_IDS[procedureType] || 'QUOTATION_REQUEST';

return [{
  json: {
    publicationId: data.publication_id,
    hasToken: !!token,
    token,
    templateId,
    procedureType,
    purchase: data,
    roseltorgPayload: {
      templateId,
      lotName: data.subject || 'Закупка #' + data.purchase_id,
      startPrice: data.nmck,
      currency: 'RUB',
      items: (data.items || []).map(i => ({
        name: i.item_name,
        quantity: i.quantity,
        unit: i.unit,
        unitPrice: i.unit_price,
      })),
    }
  }
}];
```

### n8n: Error callback (нет токена)
```javascript
// Source: паттерн из fabrikant_publish.json callback-error node
// Этот node достигается через FALSE branch из IF(hasToken)
const { publicationId } = $input.first().json;
return [{
  json: {
    publicationId,
    status: 'error',
    error_text: 'Требуется Bearer Token Росэлторг — настройте в параметрах n8n (переменная ROSELTORG_TOKEN)',
  }
}];
```

### Vue: procedure_type в doPublish
```typescript
// Source: существующий doPublish в CreateOrderView.vue:2522
async function doPublish(platform: string, procedureType?: string | null) {
  publishingPlatform.value = platform
  try {
    const body: Record<string, any> = { platform }
    if (procedureType) body.procedure_type = procedureType
    const pub = await apiFetch<Publication>(`/publications/purchases/${purchaseId.value}`, {
      method: 'POST',
      body,
    })
    publications.value.unshift(pub)
    showSnack(`Отправлено на публикацию: ${PLATFORM_LABELS[platform]}`)
    publishDialog.value = false
    pendingPlatform.value = null
    roseltorgProcedureType.value = null
    pollPublication(pub.id)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка при отправке на публикацию', 'error')
  } finally {
    publishingPlatform.value = null
  }
}
```

### E2E: Mock n8n callback pattern
```typescript
// Source: паттерн из e2e/05-orders.spec.ts + helpers.ts
import { test, expect, request as playwrightRequest } from '@playwright/test';
import { login, collectApiErrors } from './helpers';

const BASE_URL = process.env.BASE_URL || 'http://localhost';

test('Публикация Фабрикант test mode → published', async ({ page, request }) => {
  await login(page);

  // Получить первый purchase_id
  const orders = await request.get(`${BASE_URL}/api/purchases?limit=1`, {
    headers: { Authorization: `Bearer ${await getToken(page)}` }
  });
  const [purchase] = await orders.json();

  // Публикация
  const pubResp = await request.post(
    `${BASE_URL}/api/publications/purchases/${purchase.id}`,
    { data: { platform: 'fabrikant' }, headers: { Authorization: `Bearer ${await getToken(page)}` } }
  );
  expect(pubResp.status()).toBe(200);
  const pub = await pubResp.json();

  // Mock callback от n8n
  const callbackResp = await request.patch(
    `${BASE_URL}/api/publications/${pub.id}/status`,
    { data: { status: 'published', external_id: 'TEST-FABRIKANT-001', external_url: 'https://fabrikant.ru/test' } }
  );
  expect(callbackResp.status()).toBe(200);

  // Проверить в UI
  await page.goto(`/create-order/${purchase.id}`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  const publishedChip = page.locator('.v-chip').filter({ hasText: /Опубликовано/i });
  expect(await publishedChip.isVisible()).toBe(true);
});
```

---

## What Already Exists (Don't Re-implement)

| Component | Location | Status |
|-----------|----------|--------|
| POST /api/publications/purchases/{id} | publications.py:111 | READY |
| GET /api/publications/purchases/{id} | publications.py:97 | READY |
| PATCH /api/publications/{id}/status | publications.py:148 | READY |
| `_build_publish_payload()` | publications.py:31 | READY — добавить procedure_type |
| Секция публикаций в UI | CreateOrderView.vue:1159 | READY — добавить dropdown |
| Диалог публикации | CreateOrderView.vue:1227 | READY — добавить step для Росэлторг |
| `pollPublication()` | CreateOrderView.vue:2545 | READY — не трогать |
| SMTP test endpoint | settings.py:88 | READY |
| КП email send | commercial_requests.py:152 | READY |
| Фабрикант workflow | n8n_workflows/fabrikant_publish.json | READY — добавить test mode |
| E2E infrastructure | e2e/ + playwright.config.ts | READY — добавить 12-publications.spec.ts |

---

## Key Integration Points (что менять)

### Backend (минимальные изменения)

1. **`schemas.py`**: добавить `procedure_type: Optional[str] = None` в `PublishRequest`
2. **`publications.py`**: в `publish_purchase` — добавить `procedure_type` к payload если задан

### Frontend (одно место)

3. **`CreateOrderView.vue`**: диалог публикации (lines ~1227-1267)
   - Добавить `pendingPlatform`, `roseltorgProcedureType` refs
   - При клике "Опубликовать" на Росэлторг → показать v-select типа процедуры
   - Изменить `doPublish(platform)` → `doPublish(platform, procedureType?)`

### n8n (новые файлы)

4. **`n8n_workflows/roseltorg_publish.json`** — новый файл (копия Фабрикант с отличиями)
5. **`n8n_workflows/fabrikant_publish.json`** — обновить: добавить FABRIKANT_TEST_MODE logic

### E2E (новый файл)

6. **`e2e/12-publications.spec.ts`** — 4-5 тестов с mock callback

---

## Open Questions

1. **templateId реального Росэлторг API**
   - Что знаем: Росэлторг.Бизнес (rb.roseltorg.ru) имеет REST API для публикации
   - Неясно: точные значения templateId (QUOTATION_REQUEST, PROPOSAL_REQUEST и т.д.)
   - Рекомендация: использовать читаемые константы (QUOTATION_REQUEST и т.д.) — реальные значения уточнить при получении Bearer Token. На данном этапе branch с реальным API недостижим (нет токена).

2. **SMTP настройки на локальной тестовой машине**
   - Что знаем: на сервере (85.239.53.155) z@vsks.ru настроен в SystemSetting
   - Неясно: настроен ли SMTP на localhost для E2E тестов
   - Рекомендация: SMTP E2E тест должен gracefully обрабатывать 400 "SMTP не настроен" на локальном окружении. Проверять только что endpoint отвечает (200 или 400 с понятным сообщением, не 500).

3. **n8n Variables API**
   - Что знаем: `$env.VAR_NAME` читает из n8n Settings → Variables
   - Неясно: Требуется ли создавать переменные вручную через n8n UI или они создаются при импорте workflow
   - Рекомендация: В документации к фазе указать что нужно создать Variables вручную в n8n UI.

---

## Sources

### Primary (HIGH confidence — прочитан исходный код)
- `backend/app/routers/publications.py` — полная структура публикаций, `_build_publish_payload()`
- `backend/app/schemas/schemas.py:457-478` — PublishRequest, PublicationOut, PublicationStatusUpdate
- `backend/app/routers/settings.py` — SMTP endpoints, SystemSetting pattern
- `backend/app/routers/commercial_requests.py:152-205` — send_kp_emails SMTP logic
- `frontend/src/views/CreateOrderView.vue:2484-2552` — AVAILABLE_PLATFORMS, doPublish, pollPublication
- `frontend/src/views/CreateOrderView.vue:1159-1267` — UI секция публикации + диалог
- `n8n_workflows/fabrikant_publish.json` — полная структура workflow (шаблон)
- `e2e/helpers.ts` — login, collectApiErrors, clickButton, waitForOverlays
- `e2e/05-orders.spec.ts` — паттерн тестов

### Secondary (MEDIUM confidence)
- `.planning/phases/08-*/08-CONTEXT.md` — решения пользователя
- `.planning/STATE.md` — текущий статус проекта

---

## Metadata

**Confidence breakdown:**
- Backend changes: HIGH — код прочитан, изменения минимальны и очевидны
- n8n workflow structure: HIGH — шаблон прочитан полностью
- Vue dropdown pattern: HIGH — Vuetify v-select уже используется в проекте
- templateId значения Росэлторг: LOW — реальный API не изучался (нет токена, не актуально)
- E2E mock approach: HIGH — PATCH /status endpoint прочитан, pattern с прямым вызовом корректен

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (стабильный стек)
