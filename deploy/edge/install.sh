#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# deploy/edge/install.sh — переключение сервера с «единый nginx VSKS держит
# 80/443 для всех доменов» на «edge держит 80/443, GALA-nginx VSKS слушает
# только 127.0.0.1:8079». Выполняется ВЛАДЕЛЬЦЕМ на сервере (Claude Code на
# прод не ходит). Идемпотентен: повторный запуск `install.sh` синхронизирует
# /opt/edge-nginx/ с deploy/edge/ этого репозитория и, если edge уже живой
# и на 80/443, просто обновляет его конфиг (см. STEP 2/5) без полного цикла
# переключения портов GALA (тот выполняется только один раз — с этого
# момента GALA и так уже на 8079).
#
# ПРЕДПОСЫЛКИ (см. README.md — идти по нему при первом запуске):
#   1. /opt/vsks-crm уже содержит закоммиченные deploy/edge/* и обновлённые
#      nginx/nginx.conf + docker-compose.yml (порт GALA-nginx 127.0.0.1:8079)
#      — то есть `git pull` в /opt/vsks-crm СДЕЛАН ДО запуска этого скрипта.
#      Сам install.sh git НЕ трогает.
#   2. vsks-deploy.service (вебхук автодеплоя) остановлен ДО push в GitHub —
#      иначе автодеплой мог бы откликнуться на push раньше, чем ты запустишь
#      этот скрипт, и молча перезагрузить (`nginx -s reload`) уже
#      обрезанный nginx.conf на СТАРОМ контейнере, который всё ещё держит
#      80/443 — новый конфиг не содержит `listen 443` и других доменов
#      вообще, так что reload в этот момент оборвал бы TLS и все домены
#      соседей ДО того, как edge готов их принять. Этот скрипт останавливает
#      сервис ещё раз на всякий случай (STEP 1), но если вебхук успел
#      сработать один раз до этого — уже поздно, обращайся к rollback.
#   3. Docker + docker compose plugin установлены, /etc/letsencrypt на
#      хосте содержит (или НЕ содержит — тогда see STEP 4b) сертификат
#      /etc/letsencrypt/live/<DOMAIN>/{fullchain,privkey}.pem.
#
# ИСПОЛЬЗОВАНИЕ:
#   sudo bash deploy/edge/install.sh            # переключение (или resync)
#   sudo bash deploy/edge/install.sh rollback    # откат на прежнюю схему
#
# Переменные окружения (все опциональны, есть разумные дефолты):
#   VSKS_DIR        — где лежит репозиторий VSKS (default /opt/vsks-crm)
#   EDGE_LIVE        — куда устанавливается живой edge (default /opt/edge-nginx)
#   DOMAIN           — основной домен (default gaaala.duckdns.org)
#   VSKS_NETWORK     — имя docker-сети VSKS для n8n/adminer (default vsks-crm_default)
#   STAGING_HTTP_PORT / STAGING_HTTPS_PORT — запасные порты репетиции (default 8080/8443)
#   PRE_SPLIT_REF    — git-ref ДО разреза, источник файлов для rollback (default HEAD~1)
#   SKIP_SYSTEMD     — если "1", не трогает systemctl (используется локальным стендом)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

VSKS_DIR="${VSKS_DIR:-/opt/vsks-crm}"
EDGE_SRC="${EDGE_SRC:-$VSKS_DIR/deploy/edge}"
EDGE_LIVE="${EDGE_LIVE:-/opt/edge-nginx}"
DOMAIN="${DOMAIN:-gaaala.duckdns.org}"
VSKS_NETWORK="${VSKS_NETWORK:-vsks-crm_default}"
STAGING_HTTP_PORT="${STAGING_HTTP_PORT:-8080}"
STAGING_HTTPS_PORT="${STAGING_HTTPS_PORT:-8443}"
GALA_PORT="${GALA_PORT:-8079}"
PRE_SPLIT_REF="${PRE_SPLIT_REF:-HEAD~1}"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-0}"
STAGING_CONTAINER="edge-nginx-staging"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }
die() { echo "[$(ts)] !!!!! $* !!!!!" >&2; exit 1; }

# Домены и ожидаемые коды — ОДНА точка истины для проверок на всех этапах
# (staging-репетиция STEP 5 и финальная проверка STEP 6c используют один и
# тот же список, чтобы не разойтись). Формат: "host|path|ожидаемый_код".
# 401 для adminer — это ПРАВИЛЬНЫЙ ответ без креденшелов (доказывает,
# что запрос вообще дошёл до приложения и авторизация жива), а не ошибка.
# n8n отдаёт 200: у него СВОЯ страница входа, HTTP-авторизации на nginx нет —
# сверено с ответом через прежний общий nginx на проде 2026-09-05 (репетиция
# с ожиданием 401 отменила переключение, edge при этом вёл себя верно).
# DOMAIN_CHECKS_FILE (опционально) — переопределить список проверок файлом
# ("host|path|код" по одной на строку, # и пустые строки игнорируются) без
# правки самого скрипта. Используется, например, локальной репетицией на
# стенде, где какой-то путь заведомо недостижим по причине, не связанной с
# разрезом (see README/отчёт репетиции) — в бою переопределять не нужно.
DOMAIN_CHECKS=(
    "${DOMAIN}|/|200"
    "uniform.${DOMAIN}|/|200"
    "trading.${DOMAIN}|/|200"
    "sunduk.${DOMAIN}|/|200"
    "sizo.${DOMAIN}|/|200"
    "nemakh.${DOMAIN}|/|200"
    "n8n.${DOMAIN}|/|200"
    "adminer.${DOMAIN}|/|401"
    "halliem.${DOMAIN}|/|200"
)
if [ -n "${DOMAIN_CHECKS_FILE:-}" ]; then
    [ -f "$DOMAIN_CHECKS_FILE" ] || die "DOMAIN_CHECKS_FILE=$DOMAIN_CHECKS_FILE не найден"
    mapfile -t DOMAIN_CHECKS < <(grep -vE '^\s*(#|$)' "$DOMAIN_CHECKS_FILE")
fi

require_cmd() { command -v "$1" >/dev/null 2>&1 || die "требуется '$1', не найден в PATH"; }

systemd_stop() {
    [ "$SKIP_SYSTEMD" = "1" ] && { log "SKIP_SYSTEMD=1 — не трогаю vsks-deploy.service"; return 0; }
    # `systemctl cat`, а не grep по list-unit-files: на проде 2026-09-05
    # grep не нашёл существующий и включённый юнит, скрипт решил «локальный
    # стенд», и вебхук после переключения остался остановленным — автодеплой
    # был мёртв, пока не запустили руками.
    if systemctl cat vsks-deploy.service >/dev/null 2>&1; then
        log "останавливаю vsks-deploy.service (вебхук автодеплоя) — чтобы push/webhook не влез в середину переключения"
        systemctl stop vsks-deploy.service || log "WARN: не удалось остановить vsks-deploy.service (возможно уже остановлен)"
    else
        log "vsks-deploy.service не найден в systemd — пропускаю (локальный стенд?)"
    fi
}

systemd_start() {
    [ "$SKIP_SYSTEMD" = "1" ] && { log "SKIP_SYSTEMD=1 — не трогаю vsks-deploy.service"; return 0; }
    # `systemctl cat`, а не grep по list-unit-files: на проде 2026-09-05
    # grep не нашёл существующий и включённый юнит, скрипт решил «локальный
    # стенд», и вебхук после переключения остался остановленным — автодеплой
    # был мёртв, пока не запустили руками.
    if systemctl cat vsks-deploy.service >/dev/null 2>&1; then
        log "запускаю vsks-deploy.service обратно"
        systemctl start vsks-deploy.service || log "WARN: не удалось запустить vsks-deploy.service — запусти вручную"
    fi
}

check_one_domain() {
    # curl через указанный host:port (SNI/Host = $1), путь $2, порт $3
    # (https) — resolve-трюк: не трогаем /etc/hosts, не зависим от
    # реального DNS ни на стенде, ни на проде при staging-проверке на
    # запасных портах.
    local host="$1" path="$2" port="$3" code
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 \
        --resolve "${host}:${port}:127.0.0.1" \
        "https://${host}:${port}${path}" 2>/dev/null || echo "000")
    echo "$code"
}

run_domain_checks() {
    # $1 = порт (для staging — 8443, для боевого — 443). $2 = "skip-gala"
    # (опционально) — не проверять $DOMAIN на этом проходе. ПРИЧИНА: на
    # staging-репетиции (STEP 5) GALA-nginx ЕЩЁ НЕ существует на 127.0.0.1:
    # ${GALA_PORT} — он появляется там только в STEP 6a, который идёт
    # ПОСЛЕ репетиции (репетиция намеренно происходит ДО касания боевых
    # 80/443, а пересоздание GALA — уже часть боевого переключения). Значит
    # $DOMAIN на staging ВСЕГДА ответит 502 независимо от того, правильно
    # ли настроен edge — это НЕ баг edge, а факт порядка шагов, и проверять
    # его здесь означало бы либо ложно проваливать репетицию каждый раз,
    # либо (хуже) научиться игнорировать реальные проблемы. Соседи
    # (uniform/sunduk/sizo/nemakh/n8n/adminer/halliem) от состояния GALA
    # НЕ зависят вообще — их staging проверяет по-настоящему полноценно,
    # именно ради них и существует репетиция. Возвращает 0 если ВСЕ
    # проверенные домены ответили ожидаемым кодом, иначе печатает
    # расхождения и возвращает 1 (не падает сама — вызывающий решает).
    local port="$1" skip_gala="${2:-}" entry host path expected got fail=0
    for entry in "${DOMAIN_CHECKS[@]}"; do
        IFS='|' read -r host path expected <<< "$entry"
        if [ "$skip_gala" = "skip-gala" ] && [ "$host" = "$DOMAIN" ]; then
            log "  SKIP $host$path (GALA ещё не на 127.0.0.1:${GALA_PORT} на этом шаге — см. комментарий в run_domain_checks)"
            continue
        fi
        got=$(check_one_domain "$host" "$path" "$port")
        if [ "$got" = "$expected" ]; then
            log "  OK   $host$path → $got"
        else
            log "  FAIL $host$path → $got (ожидали $expected)"
            fail=1
        fi
    done
    return $fail
}

cmd_switch() {
    log "════ EDGE INSTALL: переключение 80/443 на edge-nginx ════"

    require_cmd docker
    require_cmd curl
    docker compose version >/dev/null 2>&1 || die "docker compose (plugin) не найден"

    [ -d "$VSKS_DIR" ] || die "VSKS_DIR=$VSKS_DIR не существует"
    [ -f "$EDGE_SRC/nginx.conf" ] || die "$EDGE_SRC/nginx.conf не найден — репозиторий не содержит новые файлы, сделай git pull в $VSKS_DIR перед запуском"
    [ -f "$EDGE_SRC/docker-compose.yml" ] || die "$EDGE_SRC/docker-compose.yml не найден"

    if ! docker network inspect "$VSKS_NETWORK" >/dev/null 2>&1; then
        die "сеть $VSKS_NETWORK не существует — VSKS ещё ни разу не поднимался (docker compose up -d в $VSKS_DIR), edge подключиться не сможет"
    fi

    # ── STEP 1: вебхук в сторону ────────────────────────────────────────
    systemd_stop

    # ── STEP 2: снимок ДОСПЛИТОВОГО состояния для rollback (делаем ДО
    #    любых live-изменений, один раз — повторный install.sh не
    #    перезаписывает уже сохранённый снимок, чтобы rollback всегда вёл
    #    к состоянию «перед первым переключением», а не к промежуточному) ──
    mkdir -p "$EDGE_LIVE/.rollback"
    if [ ! -f "$EDGE_LIVE/.rollback/nginx.conf" ]; then
        log "сохраняю доразрезное состояние ($PRE_SPLIT_REF) для rollback → $EDGE_LIVE/.rollback/"
        ( cd "$VSKS_DIR" && git show "${PRE_SPLIT_REF}:nginx/nginx.conf" ) > "$EDGE_LIVE/.rollback/nginx.conf" \
            || die "не удалось получить nginx/nginx.conf из $PRE_SPLIT_REF — задай PRE_SPLIT_REF=<нужный коммит> явно"
        ( cd "$VSKS_DIR" && git show "${PRE_SPLIT_REF}:docker-compose.yml" ) > "$EDGE_LIVE/.rollback/docker-compose.yml" \
            || die "не удалось получить docker-compose.yml из $PRE_SPLIT_REF"
        ( cd "$VSKS_DIR" && git rev-parse "$PRE_SPLIT_REF" ) > "$EDGE_LIVE/.rollback/ref.txt"
        log "снимок сохранён (коммит $(cat "$EDGE_LIVE/.rollback/ref.txt"))"
    else
        log "снимок для rollback уже существует ($(cat "$EDGE_LIVE/.rollback/ref.txt" 2>/dev/null || echo '?')) — не перезаписываю"
    fi

    # ── STEP 3: синхронизировать deploy/edge/ → живой каталог ───────────
    log "синхронизирую $EDGE_SRC → $EDGE_LIVE"
    mkdir -p "$EDGE_LIVE"
    cp -f "$EDGE_SRC/nginx.conf" "$EDGE_LIVE/nginx.conf"
    cp -f "$EDGE_SRC/docker-compose.yml" "$EDGE_LIVE/docker-compose.yml"
    [ -f "$EDGE_SRC/README.md" ] && cp -f "$EDGE_SRC/README.md" "$EDGE_LIVE/README.md" || true

    # ── STEP 4a: adminer htpasswd — переносим значение из .env VSKS, тот
    #    же пароль что был, просто источник истины теперь edge ──────────
    mkdir -p "$EDGE_LIVE/secrets"
    if [ -f "$VSKS_DIR/.env" ]; then
        ADMINER_HTPASSWD_VALUE=$(grep -m1 '^ADMINER_HTPASSWD=' "$VSKS_DIR/.env" 2>/dev/null | cut -d= -f2- || true)
    else
        ADMINER_HTPASSWD_VALUE=""
    fi
    if [ -n "${ADMINER_HTPASSWD_VALUE:-}" ]; then
        printf '%s\n' "$ADMINER_HTPASSWD_VALUE" > "$EDGE_LIVE/secrets/adminer.htpasswd"
        log "adminer.htpasswd записан из \$VSKS_DIR/.env (ADMINER_HTPASSWD)"
    else
        log "WARN: ADMINER_HTPASSWD не задан в $VSKS_DIR/.env — adminer будет честно отдавать 401 (неподходящий хеш), как и раньше при пустой переменной"
        RANDOM_PW=$(openssl rand -hex 20 2>/dev/null || echo "disabled-$(date +%s)")
        echo "disabled:$(openssl passwd -apr1 "$RANDOM_PW" 2>/dev/null || echo "*")" > "$EDGE_LIVE/secrets/adminer.htpasswd"
    fi

    # ── STEP 4b: сертификат — если реального ещё нет (свежий стенд/первая
    #    установка до setup-ssl.sh), self-signed placeholder — тем же
    #    способом, что nginx/entrypoint.sh VSKS уже делает для GALA, чтобы
    #    install.sh был тестируем БЕЗ реального LE-сертификата. На проде,
    #    где сертификат уже выпущен (см. постановку задачи), это ветка не
    #    сработает, только читает существующие файлы.
    #
    #    ЧЕРЕЗ ОДНОРАЗОВЫЙ КОНТЕЙНЕР, а не напрямую (`mkdir`/`openssl` этим
    #    же процессом) — сознательно: проверка/генерация должна видеть ТОТ
    #    ЖЕ `/etc/letsencrypt`, что видит Docker-демон при биндмаунте в
    #    edge/GALA (см. -v /etc/letsencrypt:/etc/letsencrypt в
    #    docker-compose.yml). На проде (Linux, install.sh от root) это
    #    один и тот же путь что для процесса, что для демона — разницы
    #    нет. На Docker Desktop (репетиция на стенде, см. отчёт) — ДВЕ
    #    разные файловые системы под одной строкой пути (процесс видит
    #    свою ОС, демон — свою внутреннюю VM), и прямой `mkdir` бил бы
    #    мимо. Контейнер убирает разницу структурно в обоих случаях.
    LIVE_CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
    docker run --rm -v /etc/letsencrypt:/etc/letsencrypt alpine:3 sh -c "
        set -e
        if [ -f '${LIVE_CERT_DIR}/fullchain.pem' ] && [ -f '${LIVE_CERT_DIR}/privkey.pem' ]; then
            echo '[cert] сертификат уже существует: ${LIVE_CERT_DIR}/fullchain.pem'
        else
            echo '[cert] LE cert не найден — генерирую self-signed placeholder (только для тестового/первого запуска)'
            apk add --no-cache openssl >/dev/null 2>&1
            mkdir -p '${LIVE_CERT_DIR}'
            openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
                -keyout '${LIVE_CERT_DIR}/privkey.pem' \
                -out '${LIVE_CERT_DIR}/fullchain.pem' \
                -subj '/CN=${DOMAIN}' -addext 'subjectAltName=DNS:${DOMAIN}' 2>/dev/null
        fi
    " | while IFS= read -r line; do log "$line"; done

    # ── STEP 5: репетиция на запасных портах — ПОЛНАЯ проверка ДО того,
    #    как тронут боевые 80/443. Отдельный `docker run` (не через
    #    docker-compose.yml, у которого порты 80/443 намертво прописаны) —
    #    сознательно: staging и боевой контейнер не должны конкурировать
    #    за порты, а деплой-артефакт (docker-compose.yml) должен остаться
    #    ЕДИНСТВЕННЫМ источником правды про боевые порты ──────────────────
    log "── STEP 5: репетиция на запасных портах ${STAGING_HTTP_PORT}/${STAGING_HTTPS_PORT} ──"
    docker rm -f "$STAGING_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$STAGING_CONTAINER" \
        -p "127.0.0.1:${STAGING_HTTP_PORT}:80" \
        -p "127.0.0.1:${STAGING_HTTPS_PORT}:443" \
        -v "$EDGE_LIVE/nginx.conf:/etc/nginx/nginx.conf:ro" \
        -v "$EDGE_LIVE/secrets:/etc/nginx/secrets:ro" \
        -v /etc/letsencrypt:/etc/letsencrypt:ro \
        --add-host host.docker.internal:host-gateway \
        --network "$VSKS_NETWORK" \
        nginx:alpine >/dev/null

    sleep 2
    if ! docker exec "$STAGING_CONTAINER" nginx -t >/dev/null 2>&1; then
        docker exec "$STAGING_CONTAINER" nginx -t || true
        docker rm -f "$STAGING_CONTAINER" >/dev/null 2>&1 || true
        die "nginx -t ПРОВАЛИЛСЯ на staging — переключение ОТМЕНЕНО, боевые 80/443 не тронуты"
    fi
    log "nginx -t на staging: OK"

    log "проверяю домены через staging (порт ${STAGING_HTTPS_PORT}, GALA пропущен — см. run_domain_checks):"
    if ! run_domain_checks "$STAGING_HTTPS_PORT" skip-gala; then
        docker logs --tail 50 "$STAGING_CONTAINER" || true
        docker rm -f "$STAGING_CONTAINER" >/dev/null 2>&1 || true
        die "ХОТЯ БЫ ОДИН домен не ответил ожидаемым кодом на staging — переключение ОТМЕНЕНО, боевые 80/443 не тронуты (см. расхождения выше)"
    fi
    log "все домены отвечают верно через staging — репетиция пройдена"
    docker rm -f "$STAGING_CONTAINER" >/dev/null 2>&1 || true

    # ── STEP 6: боевое переключение — минимальный простой ───────────────
    log "── STEP 6: боевое переключение ──"
    systemd_stop  # ещё раз — на случай если что-то успело перезапустить его между STEP 1 и сюда

    log "6a) пересоздаю nginx VSKS (GALA) — освобождает 80/443, поднимает 127.0.0.1:${GALA_PORT}"
    ( cd "$VSKS_DIR" && docker compose up -d --force-recreate --no-deps nginx )

    log "6b) СРАЗУ ЖЕ поднимаю edge на боевых 80/443"
    ( cd "$EDGE_LIVE" && docker compose up -d )

    log "6c) проверяю все домены через боевой edge (порт 443):"
    sleep 2
    if ! run_domain_checks 443; then
        log "!!!!! Не все домены отвечают ожидаемым кодом после переключения — смотри docker logs edge-nginx и docker compose -f $VSKS_DIR/docker-compose.yml logs nginx. Откат: bash $0 rollback !!!!!"
        systemd_start
        exit 1
    fi
    log "все домены отвечают верно на боевых портах — переключение завершено"

    systemd_start
    log "════ ГОТОВО. edge держит 80/443, GALA-nginx VSKS слушает 127.0.0.1:${GALA_PORT} ════"
    log "Когда убедишься, что всё стабильно (владелец решает когда) — сервис nginx можно оставить как есть, он больше не публикует порты наружу и не мешает: autodeploy.sh продолжит обновлять его штатно (roll_replica → nginx -t/-s reload), просто теперь это уже не риск для соседей."
}

cmd_rollback() {
    log "════ EDGE ROLLBACK: возврат nginx VSKS на 80/443 с прежним конфигом ════"
    require_cmd docker
    docker compose version >/dev/null 2>&1 || die "docker compose (plugin) не найден"

    [ -f "$EDGE_LIVE/.rollback/nginx.conf" ] || die "$EDGE_LIVE/.rollback/nginx.conf не найден — нечего восстанавливать (install.sh switch ни разу не запускался успешно, либо снимок вручную удалён)"
    [ -f "$EDGE_LIVE/.rollback/docker-compose.yml" ] || die "$EDGE_LIVE/.rollback/docker-compose.yml не найден"

    systemd_stop

    log "останавливаю edge (если запущен)"
    if [ -f "$EDGE_LIVE/docker-compose.yml" ]; then
        ( cd "$EDGE_LIVE" && docker compose down ) || log "WARN: edge compose down вернул ошибку (возможно уже остановлен)"
    fi
    docker rm -f edge-nginx "$STAGING_CONTAINER" >/dev/null 2>&1 || true

    log "восстанавливаю доразрезные nginx/nginx.conf и docker-compose.yml в $VSKS_DIR (коммит $(cat "$EDGE_LIVE/.rollback/ref.txt" 2>/dev/null || echo '?'))"
    log "⚠️  ЭТО ДЕЛАЕТ РАБОЧЕЕ ДЕРЕВО $VSKS_DIR ГРЯЗНЫМ (git diff покажет расхождение с HEAD) — так и задумано для аварийного отката,"
    log "    НО пока вебхук остановлен (см. выше) — следующий автодеплой (git checkout -f + git pull) вернёт файлы к HEAD, то есть СНОВА к split-схеме."
    log "    Держи vsks-deploy.service остановленным, пока владелец не решит: вернуться на edge (просто снова запустить install.sh) или закрепить откат (git revert коммита разреза)."
    cp -f "$EDGE_LIVE/.rollback/nginx.conf" "$VSKS_DIR/nginx/nginx.conf"
    cp -f "$EDGE_LIVE/.rollback/docker-compose.yml" "$VSKS_DIR/docker-compose.yml"

    log "пересоздаю nginx VSKS на 80/443 со старым конфигом"
    ( cd "$VSKS_DIR" && docker compose up -d --force-recreate --no-deps nginx )

    sleep 2
    log "проверяю домены на боевых портах (старая схема):"
    run_domain_checks 443 || log "WARN: не все домены ответили ожидаемо после отката — смотри docker compose -f $VSKS_DIR/docker-compose.yml logs nginx"

    log "webhook остаюсь ОСТАНОВЛЕННЫМ намеренно (см. предупреждение выше) — запусти вручную (systemctl start vsks-deploy.service), когда решишь, как поступать дальше"
    log "════ ROLLBACK ЗАВЕРШЁН ════"
}

case "${1:-switch}" in
    switch|"") cmd_switch ;;
    rollback) cmd_rollback ;;
    *) die "неизвестная команда '$1' (ожидалось: switch | rollback)" ;;
esac
