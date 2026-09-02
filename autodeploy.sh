#!/bin/bash
set -u  # fail on unset vars; keep going on non-zero so one step can't dead-lock the rest
LOG=/var/log/vsks-deploy.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "===== $(ts) deploy start =====" >> "$LOG"

# Serialize concurrent deploys. webhook.py запускает нас через Popen
# откреплённо и НЕ ждёт завершения — два push с разницей в пару минут
# порождают два ОДНОВРЕМЕННЫХ autodeploy.sh. Второй экземпляр раньше мог
# собрать docker-образ, пока первый ещё делал `git pull`, — Docker кешировал
# COPY . . / npm run build на ЕЩЁ НЕ обновлённом дереве, и в проде оседал
# бандл от предыдущего коммита (владелец видел это как «нужен hard refresh»).
# Лок-файл ВНЕ git-дерева (git clean -fd ниже чистит /opt/vsks-crm — если бы
# лок лежал внутри репозитория, clean мог бы удалить и пересоздать файл, а
# flock завязан на inode: новый файл = новый, независимый лок, взаимная
# исключительность сломается).
# Поведение при занятой блокировке: ЖДАТЬ, а не выходить сразу. Именно уход
# «на выход» и был бы той самой болезнью — самый свежий push потерялся бы.
# Раз сборка дольше, чем интервал между обычными push (десятки секунд –
# единицы минут), второй экземпляр просто встаёт в очередь и полноценно
# деплоит уже обновлённое дерево следующим шагом. Таймаут 30 минут — защита
# от вечного зависания, а не обычный режим работы.
LOCKFILE=/tmp/vsks-deploy.lock
exec 200>"$LOCKFILE"
echo "[$(ts)] waiting for deploy lock (held by another autodeploy.sh run, if any)..." >> "$LOG"
if ! flock -w 1800 200; then
    echo "[$(ts)] FAILED to acquire deploy lock within 30 min; another run appears stuck. Exiting without deploying." >> "$LOG"
    exit 1
fi
echo "[$(ts)] deploy lock acquired" >> "$LOG"

cd /opt/vsks-crm || { echo "[$(ts)] cd /opt/vsks-crm FAILED" >> "$LOG"; exit 1; }

# Track webhook.py hash before pull so we know whether to restart the webhook service
WEBHOOK_HASH_BEFORE=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)
# Track nginx config + docker-compose hash. nginx был отдельный TODO (websocket
# config-изменения не доходили до прода, т.к. autodeploy не пересобирал nginx).
# Rebuild ТОЛЬКО если nginx/* или docker-compose.yml поменялись — не хотим
# прерывать активные сессии браузера на каждом backend-only push.
NGINX_HASH_BEFORE=$(cat nginx/nginx.conf docker-compose.yml 2>/dev/null | sha256sum | cut -d' ' -f1)

git checkout -f claude >> "$LOG" 2>&1
git clean -fd >> "$LOG" 2>&1
git pull origin claude >> "$LOG" 2>&1

WEBHOOK_HASH_AFTER=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)
NGINX_HASH_AFTER=$(cat nginx/nginx.conf docker-compose.yml 2>/dev/null | sha256sum | cut -d' ' -f1)

# Текущий коммит — build-arg для фронта, чтобы Dockerfile детерминированно
# сбрасывал кеш шага сборки (COPY . . / npm run build) на каждый новый
# коммит, но не трогал кеш `npm ci` (см. frontend/Dockerfile).
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)

# Rebuild backend image (picks up code + model changes)
# Код возврата ОБЯЗАТЕЛЬНО проверяем: раньше упавшая сборка молча
# «проглатывалась», docker compose up -d поднимал СТАРЫЙ образ, а лог
# всё равно заканчивался строкой "deploy complete" — провал выглядел
# как успех (владелец получал 502 или требовал hard refresh без объяснений).
docker compose build backend >> "$LOG" 2>&1
BACKEND_BUILD_OK=$?
FRONTEND_BUILD_OK=0
NGINX_BUILD_OK=0

if [ "$BACKEND_BUILD_OK" -ne 0 ]; then
    echo "[$(ts)] !!!!! СБОРКА ОБРАЗА backend ПРОВАЛИЛАСЬ (exit $BACKEND_BUILD_OK) — деплой ПРЕРВАН ДО миграций и ДО перезапуска backend, на проде остаётся ПРЕДЫДУЩАЯ версия !!!!!" >> "$LOG"
else
    # Apply schema migrations BEFORE starting backend container.
    # Reason: if a migration adds a column, SQLAlchemy first request will
    # crash with UndefinedColumn → backend Exited → docker exec fails →
    # `|| true` swallows the error → site stays 502.
    # Use `docker compose run --rm` to spawn an ephemeral container on the
    # fresh image, apply schema, then exit. Only after that we start the
    # long-running backend container.
    echo "[$(ts)] applying schema migrations (pre-start)" >> "$LOG"
    docker compose run --rm --no-deps backend python /app/check_schema.py --apply >> "$LOG" 2>&1 || \
        echo "[$(ts)] WARN: check_schema.py --apply failed (see above)" >> "$LOG"

    # Now safe to start backend
    docker compose up -d backend >> "$LOG" 2>&1
    sleep 8

    # Rebuild & restart frontend. --build-arg GIT_SHA пробивает кеш шага сборки
    # приложения в frontend/Dockerfile на каждый коммит, npm ci остаётся кешированным.
    docker compose build --build-arg GIT_SHA="$GIT_SHA" frontend >> "$LOG" 2>&1
    FRONTEND_BUILD_OK=$?

    if [ "$FRONTEND_BUILD_OK" -ne 0 ]; then
        # backend к этому моменту УЖЕ пересобран и перезапущен на новом образе —
        # откатывать его не нужно, просто честно фиксируем в логе, что backend
        # обновился, а frontend остался на предыдущей версии.
        echo "[$(ts)] !!!!! СБОРКА ОБРАЗА frontend ПРОВАЛИЛАСЬ (exit $FRONTEND_BUILD_OK) — backend уже обновлён и работает, frontend остаётся на ПРЕДЫДУЩЕЙ версии, деплой считается неуспешным !!!!!" >> "$LOG"
    else
        docker compose up -d frontend >> "$LOG" 2>&1

        # Conditional nginx rebuild — только если nginx.conf или docker-compose.yml изменились.
        # Это закрывает старый TODO от 2026-04-05: websocket-fix в nginx.conf не применялся
        # на проде, т.к. autodeploy не трогал nginx-контейнер. Теперь ws/cache/proxy-tweaks
        # доходят, но мы не дёргаем nginx без нужды.
        if [ "$NGINX_HASH_BEFORE" != "$NGINX_HASH_AFTER" ]; then
            echo "[$(ts)] nginx config changed; rebuilding & restarting nginx" >> "$LOG"
            docker compose build nginx >> "$LOG" 2>&1
            NGINX_BUILD_OK=$?
            if [ "$NGINX_BUILD_OK" -ne 0 ]; then
                echo "[$(ts)] !!!!! СБОРКА ОБРАЗА nginx ПРОВАЛИЛАСЬ (exit $NGINX_BUILD_OK) — backend и frontend уже обновлены, nginx остаётся на ПРЕДЫДУЩЕЙ версии, деплой считается неуспешным !!!!!" >> "$LOG"
            else
                docker compose up -d --force-recreate nginx >> "$LOG" 2>&1
            fi
        fi

        docker image prune -f >> "$LOG" 2>&1
    fi
fi

# Always restart the webhook service at the end of a deploy. Two reasons:
#  (1) picks up any webhook.py changes (see WEBHOOK_HASH_BEFORE/AFTER above);
#  (2) clears any transient hang in the long-lived Python process — the root
#      cause of the 2026-04-19 outage was a stuck accept loop that `systemctl
#      status` reported as "active running" but that silently dropped every
#      connection. Cheaper to always restart than to run a separate healthcheck.
# Scheduled in the background with a 2s delay so the currently-running handler
# can finish responding to GitHub before we replace ourselves.
if [ "$WEBHOOK_HASH_BEFORE" != "$WEBHOOK_HASH_AFTER" ]; then
    echo "[$(ts)] webhook.py changed; restarting vsks-deploy.service" >> "$LOG"
else
    echo "[$(ts)] restarting vsks-deploy.service (routine hang prevention)" >> "$LOG"
fi
# Явно снимаем лок и закрываем fd ДО того, как уйти в фон: подпроцесс `&`
# наследует открытые дескрипторы, и если оставить fd 200 открытым, он держал
# бы лок ещё как минимум 2 секунды (sleep) — а то и дольше, пока
# systemctl restart не завершится. Из-за этого следующий деплой в очереди
# ждал бы без необходимости. Явный unlock+close делает освобождение лока
# синхронным с концом фактической работы деплоя, а не с концом этого скрипта.
flock -u 200
exec 200>&-

( sleep 2 && systemctl restart vsks-deploy.service ) &

# "deploy complete" печатаем ТОЛЬКО если все сборки (backend/frontend и,
# при необходимости, nginx) реально прошли успешно — иначе лог должен
# честно показывать провал, а не создавать иллюзию завершённого деплоя.
if [ "$BACKEND_BUILD_OK" -eq 0 ] && [ "$FRONTEND_BUILD_OK" -eq 0 ] && [ "$NGINX_BUILD_OK" -eq 0 ]; then
    echo "[$(ts)] deploy complete" >> "$LOG"
else
    echo "[$(ts)] deploy FAILED — см. выше, какой образ не собрался; vsks-deploy.service всё равно перезапущен, чтобы вебхук не завис" >> "$LOG"
    exit 1
fi
