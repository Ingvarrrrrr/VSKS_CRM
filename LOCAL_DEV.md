# VSKS_CRM — Локальная разработка

**Цель**: править → проверить локально → push в `claude` → autodeploy на прод. Не пушить непроверенный код.

---

## Первый запуск (один раз)

### 1. Запустить Docker Desktop

Иконка в системном трее → ждать пока «Engine running» (зелёная точка).

### 2. Установить зависимости frontend (один раз)

```powershell
cd frontend
npm install
```

(~2 минуты, скачивает ~600 МБ пакетов в `frontend/node_modules/`)

### 3. Стартовать БД + backend через Docker

```powershell
cd c:\Users\1\Desktop\Cursor\VSKS_CRM
docker compose up -d db backend
```

Первый билд backend ~3 минуты (apt-get install OCR-пакетов + pip install). Следующие запуски — секунды.

**Проверка**:
```powershell
docker ps --filter "name=vsks" --format "table {{.Names}}\t{{.Status}}"
# vsks_crm-db-1        Up (healthy)
# vsks_crm-backend_a-1   Up

curl http://localhost:8000/docs
# Должна открыться Swagger UI
```

### 4. Стартовать frontend (Vite hot-reload)

В отдельном терминале:
```powershell
cd c:\Users\1\Desktop\Cursor\VSKS_CRM\frontend
npm run dev
```

Откроется http://localhost:3002. Любые правки `.vue`/`.ts` — авто-перезагрузка в браузере за 200 мс.

### 5. Создать тестового пользователя

```powershell
docker exec -it vsks_crm-db-1 psql -U vsks -d vsks_crm -c "
INSERT INTO users (username, hashed_password, full_name, role)
VALUES ('admin', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYxe0qZW0/oF7Wi', 'Local Admin', 'admin')
ON CONFLICT (username) DO NOTHING;
"
# Пароль: admin123 (стандартный bcrypt hash)
```

Залогиниться на http://localhost:3002: `admin` / `admin123`.

---

## Повседневный workflow

### Запуск

```powershell
# В первом терминале (backend):
docker compose up -d db backend
docker logs vsks_crm-backend_a-1 -f
# Ctrl+C — выйти из логов (backend продолжит работать)

# Во втором терминале (frontend):
cd frontend && npm run dev
```

### Внесение правок

| Что изменено | Что делать |
|---|---|
| `frontend/src/**/*.vue` | Ничего — Vite hot-reload |
| `frontend/src/**/*.ts` | Ничего — Vite hot-reload |
| `backend/app/**/*.py` | `docker compose restart backend` (5 сек) |
| `backend/app/models/**/*.py` | `docker compose restart backend` (схема через check_schema --apply на старте) |
| `backend/requirements.txt` | `docker compose build backend && docker compose up -d backend` (~2 мин) |
| `backend/Dockerfile` | `docker compose build backend --no-cache && docker compose up -d backend` |
| `docker-compose.yml` | `docker compose up -d` |

### Smoke test перед push

```powershell
# 1. Backend жив?
curl http://localhost:8000/api/dashboard/charts
# Ожидаем 401 (auth required) — backend OK

# 2. Frontend собирается?
cd frontend && npm run build
# Ошибки TS/build → не пушить, чинить

# 3. Открыть http://localhost:3002 → ту вкладку которую меняли → проверить:
#    - Console F12: нет красных runtime errors
#    - Network: запросы 200/401, не 500
#    - Сам функционал работает как ожидалось

# 4. Если изменения backend — посмотреть docker logs
docker logs vsks_crm-backend_a-1 --tail 30
# Не должно быть Tracebacks при штатной работе
```

### Push в прод

```powershell
git add -A
git commit -m "fix(NN): описание"
git push origin claude
# Autodeploy подхватит через 30 сек, пересборка ~3-5 мин
```

Выкладка бесшовная: у backend и frontend по две реплики (`_a` и `_b`) за
upstream nginx, и меняются они по очереди — пока одна пересоздаётся, вторая
отвечает. Пользователи 502 не видят. Проверено замером: полный цикл выкладки
при непрерывном опросе — 448 запросов, 0 отказов; на прежней схеме то же окно
давало 30 отказов из 42.

Из этого следуют два правила:

- **Миграции обязаны быть обратно совместимыми.** Во время выкладки реплики
  какое-то время работают на РАЗНЫХ версиях кода против уже смигрированной
  базы. Удалять или переименовывать колонку и в том же заходе перестраивать
  код под неё нельзя — сначала добавить, выложить, потом убрать старое.
- **nginx больше не пересоздаётся** — только graceful reload и только после
  успешной `nginx -t`. Битый конфиг не выкладывается: деплой честно падает
  в FAILED, а nginx продолжает работать на прежнем конфиге. Помнить, что этот
  nginx обслуживает и чужие проекты на сервере.

### Stop

```powershell
# В терминале frontend: Ctrl+C
# Backend остаётся в Docker, можно оставить — не жрёт CPU когда idle

# Если совсем выключить (например на ночь):
docker compose down
# pgdata volume сохраняется — данные не теряются
```

---

## Импорт реальных данных с прода (опционально)

**ВНИМАНИЕ**: содержит реальные данные пользователей. Не коммитить дампы в git.

```powershell
# 1. Сделать дамп на проде
ssh root@85.239.53.155 "docker exec vsks-crm-db-1 pg_dump -U vsks -d vsks_crm --clean --if-exists --no-owner" > prod-dump.sql

# 2. Загрузить локально (очистит локальную БД)
Get-Content prod-dump.sql | docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm

# 3. Удалить дамп
Remove-Item prod-dump.sql
```

Теперь локальная БД содержит точную копию прода — баги на конкретных закупках/ТС/пользователях можно воспроизводить локально.

---

## Известные нюансы

1. **PWA service worker** — Vite dev mode (npm run dev) НЕ регистрирует SW. Это хорошо — нет workbox-кеша при разработке (Lesson 2026-05-07).

2. **localhost:80 nginx** — НЕ запускаем для локалки. Frontend через Vite (3002), backend через Docker (8000), прокси `/api` уже настроен в vite.config.ts.

3. **WebSocket** — `ws://localhost:8000/api/ws/chat` доступен напрямую (тестировать через DevTools Network → WS).

4. **Telegram polling** — backend пытается опрашивать Telegram bot API. Если нет `TELEGRAM_BOT_TOKEN` в env — `Telegram polling started` не появится в логах (norm).

5. **VAPID keys** — push notifications не работают без `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` в `.env`. Для локалки не критично.

6. **Email через SMTP** — закомментировать SMTP_* в `.env` или поставить mock. Иначе при попытке отправки уведомлений будет ошибка к smtp.yandex.ru.

---

## Команды-шпаргалка

```powershell
# Логи backend в реальном времени
docker logs vsks_crm-backend_a-1 -f

# Backend быстрый restart после правки Python
docker compose restart backend

# Влезть в БД
docker exec -it vsks_crm-db-1 psql -U vsks -d vsks_crm

# Полный wipe (потеря данных!)
docker compose down -v
# затем заново шаги 3-5 из «Первый запуск»

# Что занимает место
docker system df
```

---

*Создано: 2026-05-20 после инцидента с QueuePool exhaustion (Phase 29.2). Цель: больше не пушить в прод непроверенный код.*
