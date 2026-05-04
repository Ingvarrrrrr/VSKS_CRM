# VSKS_CRM — Техническое описание для продолжения разработки

Дата составления: 2026-03-04
Ветка с актуальным кодом: `claude` (GitHub: `Ingvarrrrrr/VSKS_CRM`)

---

## 1. Назначение системы

CRM для управления государственными субсидиями в рамках постановления Правительства РФ.
Основные сущности: субсидии → закупки → контракты → контрагенты → платежи.
**NO LLM/AI внутри CRM** — только детерминированный код.

---

## 2. Технологический стек

| Слой | Технология |
|------|-----------|
| Backend | FastAPI 0.111 + SQLAlchemy 2.0 (async) + PostgreSQL 15 |
| Frontend | Vue 3 + Vuetify 3 + TypeScript + Vite |
| Авторизация | JWT (python-jose + passlib/bcrypt) |
| Инфраструктура | Docker Compose (5 сервисов) |
| Автоматизация | n8n (порт 5678) |
| Графики | ApexCharts |

---

## 3. Сервисы Docker

```
db        postgres:15       (внутренний, 5432)
backend   FastAPI            (8000)
frontend  Vite dev server    (3000, внутренний)
nginx     reverse proxy      (80 → frontend + /api/* → backend)
n8n       n8n                (5678)
```

**Volumes:**
- `pgdata` — данные PostgreSQL
- `uploads` — файлы закупок → `/app/uploads/{purchase_id}/`
- `n8n_data` — рабочие процессы n8n

**КРИТИЧНО: нет volume mount для кода backend/frontend.**
Любое изменение кода требует пересборки образа:
```bash
cd C:/Users/1/VSKS_CRM
docker compose build backend && docker compose up -d backend
docker compose build frontend && docker compose up -d frontend
```

---

## 4. Конфигурация и доступы

```
DB:       host=localhost, user=vsks, pass=vsks_secret_2024, db=vsks_crm
Admin:    login=admin / admin123
JWT:      SECRET_KEY=vsks-jwt-secret-key-change-in-production
API base: http://localhost:8000/api  (или через nginx: http://localhost:80/api)
```

Переменные окружения backend (docker-compose.yml):
```yaml
DATABASE_URL: postgresql+asyncpg://vsks:vsks_secret_2024@db:5432/vsks_crm
SECRET_KEY: vsks-jwt-secret-key-change-in-production
SUBSIDY_LIMIT: "26128070"
```

---

## 5. Структура файлов

### Backend (`backend/app/`)

```
__init__.py               — FastAPI app + include_router для всех роутеров
config.py                 — settings (SUBSIDY_LIMIT, SECRET_KEY и др.)
database.py               — async engine, get_db dependency
auth/
  jwt.py                  — get_current_user, require_role(*roles)
models/
  purchase.py             — Purchase (40+ колонок)
  purchase_item.py        — PurchaseItem (позиции закупки)
  purchase_file.py        — PurchaseFile (файловые вложения)
  subsidy.py              — Subsidy(id, name, year, budget)
  feo_category.py         — FeoCategory(id, parent_id, subsidy_id, level, name, code)
  contractor.py           — Contractor(id, name, inn, kpp, ...)
  contract.py             — Contract(id, number, contractor_id, max_amount, status, contract_type)
  product.py              — Product(id, name, price, description, photo_url, ...)
  payment.py              — Payment(id, contract_id, purchase_id, amount, payment_date)
  user.py                 — User(id, username, hashed_password, role, full_name)
routers/
  auth.py                 — POST /api/auth/login
  users.py                — CRUD пользователей
  purchases.py            — полный CRUD закупок + transition + export/excel
  purchase_files.py       — POST/GET/download/DELETE файлов закупки
  subsidies.py            — CRUD субсидий
  contractors.py          — CRUD контрагентов
  contracts.py            — CRUD контрактов
  payments.py             — CRUD платежей
  feo_categories.py       — CRUD + GET /tree
  dashboard.py            — GET / (дерево FEO) + GET /charts
  products.py             — GET /api/products/ (список товаров)
schemas/schemas.py        — все Pydantic схемы
```

### Frontend (`frontend/src/`)

```
api.ts                    — apiFetch<T>(path, options) + JWT из localStorage
router/index.ts           — маршруты: /orders, /orders/:id, /orders/:id/edit, /create-order, ...
views/
  LoginView.vue           — форма входа, сохраняет access_token + user_role в localStorage
  DashboardView.vue       — 4 KPI + 5 ApexCharts + BudgetDrillDownDialog
  OrdersView.vue          — v-data-table с expandable rows, фильтры, Excel-экспорт
  CreateOrderView.vue     — форма закупки (7 секций, мульти-позиции, файлы, переходы статусов)
  SubsidiesView.vue       — карточки + год-фильтр + панель FEO категорий
  ContractorsView.vue     — список контрагентов
  FeoCategoriesView.vue   — дерево категорий + диалог добавления
components/
  BudgetDrillDownDialog.vue — детализация бюджета по субсидиям (bar chart)
```

---

## 6. Модель данных (ключевые таблицы)

### purchases

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | |
| purchase_number | INTEGER | № п/п |
| registry_number | VARCHAR(100) | Авто: РЕЕ-{год}-{id:05d} |
| status | VARCHAR(20) | planned/confirmed/contracted/delivered/paid |
| subsidy_id | FK subsidies | |
| contractor_id | FK contractors | |
| feo_category_id | FK feo_categories | nullable |
| contract_id | FK contracts | nullable |
| purchase_method | VARCHAR(50) | 'single' / 'competitive' |
| item_name | VARCHAR(500) | устаревшее, заменено purchase_items |
| item_type | VARCHAR(20) | устаревшее |
| planned_quantity | NUMERIC(15,4) | устаревшее |
| unit | VARCHAR(50) | устаревшее |
| planned_unit_price | NUMERIC(15,2) | устаревшее |
| planned_total_price | NUMERIC(15,2) | используется в бюджетном чеке |
| total_nmck | NUMERIC(15,2) | = SUM(purchase_items.total_price) |
| nmck | NUMERIC(15,2) | НМЦК из формы |
| contract_number | VARCHAR(100) | Авто: {год}/{id}, редактируемый |
| contract_date | DATE | |
| contract_price | NUMERIC(15,2) | |
| economy | NUMERIC(15,2) | = nmck - contract_price |
| price_increase | NUMERIC(15,2) | |
| execution_term | DATE | |
| execution_term_changed | DATE | |
| country_origin | VARCHAR(100) | |
| acceptance_doc_name | VARCHAR(200) | |
| acceptance_doc_date | DATE | |
| acceptance_doc_number | VARCHAR(100) | |
| acceptance_doc_amount | NUMERIC(15,2) | |
| payment_doc_number | VARCHAR(100) | |
| payment_doc_date | DATE | |
| payment_amount | NUMERIC(15,2) | |
| payment_federal | NUMERIC(15,2) | |
| confirmed | BOOLEAN | устаревшее (NULL → default False) |
| final_unit_price | NUMERIC(15,2) | устаревшее |
| final_total_amount | NUMERIC(15,2) | устаревшее |
| delivery_payment_amount | NUMERIC(15,2) | устаревшее |

### purchase_items

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | |
| purchase_id | FK purchases CASCADE | |
| product_id | FK products nullable | |
| item_name | VARCHAR(500) NOT NULL | |
| item_type | VARCHAR(20) | товар/услуга/работа |
| quantity | NUMERIC(15,4) | |
| unit | VARCHAR(50) | |
| unit_price | NUMERIC(15,2) | |
| total_price | NUMERIC(15,2) | = quantity * unit_price |
| final_unit_price | NUMERIC(15,2) | |
| final_total | NUMERIC(15,2) | |

### purchase_files

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | |
| purchase_id | FK purchases CASCADE | |
| filename | VARCHAR(500) | оригинальное имя файла |
| filepath | VARCHAR(1000) | абс. путь: /app/uploads/{pid}/{filename} |
| mime_type | VARCHAR(100) | |
| size | INTEGER | байт |
| created_at | TIMESTAMP | DEFAULT NOW() |

**Примечание:** Таблица существовала до Phase 3 с другими колонками (`file_data bytea`, `file_size`, `original_name`, `uploaded_at`). Новые колонки добавлены через ALTER TABLE — старые остались, игнорировать их.

### subsidies

```
id, name, year, budget (NUMERIC), description
```

Актуальные данные (2026): 8+ субсидий, subsidy_id=7 (ФАДМ_2026) содержит 390 закупок на ~36.8М ₽ при бюджете 15.5М ₽ (исторические данные превышают лимит).

### feo_categories

```
id, parent_id (self-FK), subsidy_id, level (1-3), name, code, appendix, is_active
```

В дампе данных: уровни 1-2 существуют, большинство закупок имеют `feo_category_id=NULL`.

### products

```
id, name, price, description, photo_url, photo_link, clarification_link,
category, product_type, feo_category_id, is_reusable, is_active
```

Нет колонки `unit` в таблице products.

---

## 7. API Endpoints

### Авторизация
```
POST /api/auth/login          — { username, password } → { access_token, token_type, role, full_name }
```

### Закупки
```
GET    /api/purchases/         — список (без auth), фильтры: subsidy_id, status, contract_id, feo_category_id
GET    /api/purchases/{id}     — детальная (без auth)
POST   /api/purchases/         — создать (manager/admin), ?admin_override=true (только admin)
PUT    /api/purchases/{id}     — обновить (manager/admin), ?admin_override=true
DELETE /api/purchases/{id}     — удалить (admin)
POST   /api/purchases/{id}/transition?status=X  — смена статуса (manager/admin)
GET    /api/purchases/export/excel?subsidy_id=&status=  — скачать Excel
```

### Файлы закупки
```
POST   /api/purchases/{pid}/files                      — загрузить файл (multipart, auth required)
GET    /api/purchases/{pid}/files                      — список файлов (auth required)
GET    /api/purchases/{pid}/files/{fid}/download       — скачать (auth required)
DELETE /api/purchases/{pid}/files/{fid}                — удалить (auth required)
```

Разрешённые MIME: `application/pdf`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `image/jpeg`, `image/png`

### Остальные (без auth на GET)
```
GET/POST/PUT/DELETE /api/subsidies/
GET/POST/PUT/DELETE /api/contractors/
GET/POST/PUT/DELETE /api/contracts/
GET/POST/PUT/DELETE /api/payments/
GET/POST/PUT/DELETE /api/feo-categories/
GET                  /api/feo-categories/tree
GET                  /api/products/
GET                  /api/dashboard/
GET                  /api/dashboard/charts
```

---

## 8. Бизнес-логика

### Статусный workflow закупки
```
planned → confirmed → contracted → delivered → paid
```
- Переход вперёд: любой manager/admin
- Откат: только admin
- Обязательные поля для перехода:
  - → `contracted`: contract_number, contract_date
  - → `delivered`: acceptance_doc_name, acceptance_doc_date, acceptance_doc_number, acceptance_doc_amount
  - → `paid`: payment_doc_number, payment_doc_date, payment_amount

### Бюджетный контроль
- При POST/PUT: сумма всех `planned_total_price` по субсидии не должна превышать `subsidy.budget`
- При превышении: HTTP 422 с сообщением об остатке
- Обход: `?admin_override=true` (только role=admin)
- НМЦК закупки = SUM(purchase_items.total_price) → записывается в `purchases.total_nmck` и `planned_total_price`

### Авто-генерация номеров (при POST)
- `registry_number` = `РЕЕ-{year}-{id:05d}` (если не указан вручную)
- `contract_number` = `{year}/{id}` (если не указан вручную, редактируемый)
- Использует `db.flush()` для получения `id` до коммита

### Экономия
- `economy = nmck - contract_price` (вычисляется на фронтенде, сохраняется в БД)

---

## 9. Паттерны кода

### Backend (SQLAlchemy 2.0 async)
```python
# Запрос с eager loading
result = await db.execute(
    select(Purchase)
    .options(
        selectinload(Purchase.items).selectinload(PurchaseItem.product),
        selectinload(Purchase.files),
    )
    .where(Purchase.id == pid)
)
p = result.scalar_one_or_none()

# Массовое удаление
from sqlalchemy import delete
await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))

# case() — из sqlalchemy, НЕ func.case()
from sqlalchemy import case
case((Purchase.confirmed == True, Purchase.final_total_amount), else_=0)

# Зависимость роли
_ = Depends(require_role("admin", "manager"))

# flush для получения id до commit
db.add(obj)
await db.flush()  # obj.id теперь доступен
# ... используем obj.id ...
await db.commit()
```

### Pydantic v2
```python
class MySchema(BaseModel):
    model_config = {"from_attributes": True}

# Исключить поля при dump
data.model_dump(exclude={"items"}, exclude_unset=True)
```

### Frontend (api.ts)
```typescript
// apiFetch автоматически JSON.stringify object body + добавляет Bearer token
const data = await apiFetch<Purchase[]>('/purchases/')
await apiFetch('/purchases/', { method: 'POST', body: payload })

// Файловая загрузка — напрямую через fetch (не apiFetch), т.к. FormData
const fd = new FormData()
fd.append('file', file)
const token = localStorage.getItem('access_token')
const res = await fetch('/api/purchases/1/files', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` },
  body: fd,
})

// Скачивание файла с авторизацией
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
const blob = await res.blob()
const url2 = URL.createObjectURL(blob)
const a = document.createElement('a')
a.href = url2; a.download = filename; a.click()
URL.revokeObjectURL(url2)
```

### Хранение авторизации на фронтенде
```typescript
localStorage.getItem('access_token')  // JWT токен
localStorage.getItem('auth_token')     // альтернативный ключ (api.ts использует 'auth_token')
localStorage.getItem('user_role')      // 'admin' | 'manager' | 'viewer'
```

**Замечание:** В `api.ts` используется `localStorage.getItem('auth_token')`, а в file upload коде — `localStorage.getItem('access_token')`. Это расхождение существует в текущем коде.

---

## 10. Команды для разработки

```bash
# Пересобрать backend
cd C:/Users/1/VSKS_CRM
docker compose build backend && docker compose up -d backend

# Пересобрать frontend
docker compose build frontend && docker compose up -d frontend

# Логи
docker logs vsks_crm-backend-1 --tail 30
docker logs vsks_crm-frontend-1 --tail 20

# SQL в базе
docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm -c "SELECT ..."

# Перезапуск после изменений схемы БД
docker compose restart backend
```

---

## 11. Текущие данные

- 390 закупок (все subsidy_id=7, feo_category_id=NULL)
- 612 контрагентов
- 1520 товаров в таблице products
- 8+ субсидий (2025-2026)
- DB tables ready: purchase_items (390 записей), purchase_files (пустая), budget_history, wishes

---

## 12. Что сделано (Phases)

### Phase 1 — Форма закупки + статусный workflow ✓
- Расширена модель Purchase (40+ колонок)
- Статусный workflow planned → confirmed → contracted → delivered → paid
- Обязательные поля для каждого перехода (field guards)

### Phase 2 — Бюджетный контроль + FEO категории ✓
- `_check_budget()` в purchases.py
- Admin override (`?admin_override=true`)
- FeoCategoriesView — диалог добавления с выбором родителя и субсидии

### Phase 2.5 — Данные + UI фиксы ✓
- Загружен дамп ФАДМ_2026 (390 закупок)
- Dashboard: 4 KPI + 5 графиков + BudgetDrillDownDialog
- nginx: проброс Authorization заголовка

### Phase 3 — Мульти-позиции + файлы + UI ✓
- `purchase_items`: таблица позиций с FK на products, CASCADE delete
- `purchase_files`: загрузка файлов в /app/uploads/, список/скачать/удалить
- `total_nmck` = SUM(items.total_price)
- Авто-генерация registry_number и contract_number при создании
- CreateOrderView: таблица позиций с autocomplete из products (фото + описание)
- CreateOrderView: country_origin — v-combobox (РФ по умолчанию)
- CreateOrderView: валидация дат (дата договора ≤ срок исполнения)
- CreateOrderView: секция загрузки файлов (только в edit-режиме)
- OrdersView: expandable rows (список позиций), столбцы contract_number/contract_date/total_nmck
- Excel-экспорт закупок (`GET /api/purchases/export/excel`)
- Dashboard bar chart: высоты в px вместо % (фикс отображения)

### Phase 5 — FEO-дерево + Контрагенты (импорт Excel) ✓

- **SubsidiesView.vue** — FEO категории теперь отображаются как коллапсируемое дерево:
  - `FeoNode` extends `FeoCategory` (depth, hasChildren, children)
  - `expandedIds = ref<number[]>([])` (массив, не Set — для Vue 3 реактивности)
  - `feoTree` computed — строит вложенную структуру через `parent_id`
  - `flattenVisible()` — рекурсивно раскрывает только expanded ветви
  - `visibleFeoNodes` computed — то что рендерится
  - `toggleExpand(id)` — splice/push для мутации массива
  - Иконки: chevron-right/down, folder/folder-open/file-document-outline, цвет по уровню
  - Отступ = `node.depth * 24 + 8` px
  - CSS: `.feo-tree`, `.feo-tree-row`, `.feo-tree-row--clickable`, `.feo-tree-chevron`, `.feo-code`

- **ContractorsView.vue** — полный рефакторинг с Excel-импортом:
  - Кнопка "Импорт из Excel" → триггерит hidden `<input type="file" accept=".xlsx,.xls">`
  - `handleImport()` → FormData + raw fetch → `POST /api/contractors/import/excel`
  - Снэкбар результата: "Добавлено N, пропущено M"
  - Добавлено поле `bank_details` в форму
  - Стилизованный layout в стиле SubsidiesView (page-header, table-card)

- **contractors.py** — добавлен `POST /api/contractors/import/excel`:
  - openpyxl парсит .xlsx, определяет заголовки по ключевым словам (RU/EN)
  - Дедупликация по ИНН (пропускает уже существующие)
  - Возвращает `{ created: N, skipped: M }`

### Phase 4 — Генерация документов ✓ (инфраструктура готова, шаблоны — ожидают)
- `docxtpl==0.17.0` + `openpyxl==3.1.2` добавлены в `backend/requirements.txt`
- `backend/app/routers/documents.py` — endpoint `GET /api/purchases/{pid}/documents/{doc_type}`
  - Типы: `service_note`, `contract_tz`, `approval_sheet`
  - Возвращает `.docx` через StreamingResponse (Content-Disposition: attachment)
  - При отсутствии шаблона: HTTP 404 с инструкцией куда положить файл
- `backend/templates/` — volume-mounted из `./backend/templates` (горячая замена без rebuild!)
  - `README.md` — все переменные шаблона с примерами
- `docker-compose.yml` — добавлен volume `./backend/templates:/app/templates`
- `CreateOrderView.vue` — секция "Документы" (только isEdit): 3 кнопки → скачать .docx
- Контекст шаблона: все поля закупки, список позиций `items[]`, дата `today`

**Что осталось для полноценной работы:** положить `.docx` файлы в `backend/templates/`:
- `service_note.docx` — Служебная записка
- `contract_tz.docx` — ТЗ (общий шаблон; договор отдельно через contract.docx начиная с Phase 23)
- `approval_sheet.docx` — Лист согласования

---

## 13. Что планируется (следующие задачи)

### Остаток по рамочному договору
Для `purchase_method='competitive'` с `contract_id` — показывать остаток:
`остаток = contract.max_amount - SUM(purchases.planned_total_price WHERE contract_id = X)`

---

## 14. Известные проблемы и нюансы

1. **Нет volume mount** → каждое изменение кода = пересборка Docker образа
2. **`func.case(...)` не работает** → использовать `from sqlalchemy import case`
3. **`confirmed` может быть NULL в БД** → в схеме: `Optional[bool] = False`
4. **Закупки линкованы к субсидиям напрямую** (`Purchase.subsidy_id`), не через feo_categories
5. **Dashboard JOIN**: `Purchase.subsidy_id == Subsidy.id`
6. **После ALTER TABLE нужен restart backend** (SQLAlchemy кэширует prepared statements)
7. **Расхождение ключей в localStorage**: `api.ts` читает `auth_token`, file upload код читает `access_token`
8. **Старые колонки в purchase_files**: `file_data`, `file_size`, `original_name`, `uploaded_at` — существуют в БД, игнорируются кодом
9. **Данные ФАДМ_2026 превышают бюджет**: subsidy_id=7 имеет ~36.8М ₽ при бюджете 15.5М ₽, все новые закупки требуют admin_override
10. **products.unit не существует** в схеме БД (есть `price`, `description`, `category`, `photo_url`)

---

## 15. Nginx конфигурация

```nginx
# /nginx/nginx.conf
server {
    listen 80;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
        # ... стандартные заголовки
    }

    location / {
        proxy_pass http://frontend:3000;
    }
}
```

---

## 16. Быстрый старт для нового разработчика

```bash
# 1. Клонировать (ветка claude)
git clone https://github.com/Ingvarrrrrr/VSKS_CRM.git
cd VSKS_CRM
git checkout claude

# 2. Запустить
docker compose up -d

# 3. Проверить backend
curl http://localhost:8000/api/dashboard/charts

# 4. Получить JWT токен
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 5. Открыть приложение
# http://localhost:80
# Логин: admin / admin123
```
