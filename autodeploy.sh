#!/bin/bash
set -u  # fail on unset vars; keep going on non-zero so one step can't dead-lock the rest
# На Linux (прод) эта переменная ничего не значит и никем не читается — но
# на Windows-стенде разработки (git-bash/MSYS), где этот скрипт гоняли для
# локальных проверок бесшовного деплоя, MSYS переписывает ЛЮБУЮ подстроку
# вида "/etc/..."/"/app/..." внутри аргументов командной строки (в т.ч.
# внутри одной строки `sh -c "..."`) в винда-путь и ломает вызов —
# нашли это эмпирически на командах вида `sh -c "/etc/nginx-src/
# entrypoint.sh && ..."`. Экспортируем безусловно: на проде no-op.
export MSYS_NO_PATHCONV=1
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

git checkout -f claude >> "$LOG" 2>&1
git clean -fd >> "$LOG" 2>&1
git pull origin claude >> "$LOG" 2>&1

WEBHOOK_HASH_AFTER=$(sha256sum webhook.py 2>/dev/null | cut -d' ' -f1)
# nginx.conf больше не проверяется отдельным hash-сравнением: nginx теперь
# ВСЕГДА получает `nginx -t && nginx -s reload` как часть обычного
# roll_replica ниже — это дёшево (graceful, доли секунды) и не требует
# отдельного отслеживания "а менялся ли nginx.conf в этом пуше". ВАЖНО: этот
# nginx по-прежнему держит 80/443 и обслуживает ВСЕ домены на сервере, не
# только VSKS (uniform/trading/sunduk/sizo/nemakh/n8n/adminer/halliem) —
# разрез на отдельный edge-nginx запланирован отдельным шагом (см.
# deploy/edge-nginx.conf), но пока НЕ применяется. Именно поэтому ниже
# контейнер nginx НИКОГДА не пересоздаётся (`--force-recreate`), только
# `nginx -t` + graceful `-s reload` — пересоздание уронило бы порты 80/443
# для всех проектов разом, не только VSKS.

# Текущий коммит — build-arg для фронта, чтобы Dockerfile детерминированно
# сбрасывал кеш шага сборки (COPY . . / npm run build) на каждый новый
# коммит, но не трогал кеш `npm ci` (см. frontend/Dockerfile).
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)

# ── Бесшовный деплой (2026-09-04, доработано после ревью транзитного
#    сценария; разрез edge/project nginx ОТЛОЖЕН — nginx пока держит 80/443
#    и все домены сервера, как раньше, см. комментарий выше) ─────────────
# backend и frontend — по ДВЕ реплики каждый (backend_a/backend_b,
# frontend_a/frontend_b — см. docker-compose.yml). Пересоздаём их ПООЧЕРЁДНО:
# пока одна реплика перезапускается, вторая продолжает отвечать, и nginx
# (upstream backend_pool/frontend_pool с proxy_next_upstream, см.
# nginx/nginx.conf) автоматически уводит запросы с недоступной реплики на
# живую. Раньше `docker compose up -d backend` пересоздавал ЕДИНСТВЕННЫЙ
# контейнер — на время миграций+инициализации (десятки секунд) сайт отдавал
# 502 всем.
#
# ⚠️ ЛОВУШКА ПЕРЕХОДНОГО ДЕПЛОЯ (найдена ревью до выката на прод, где сейчас
# ещё живут ОДИНОЧНЫЕ контейнеры "backend"/"frontend", а backend_b/
# frontend_a/frontend_b не существовали НИКОГДА): upstream{} резолвит имена
# серверов ОДИН РАЗ при `nginx -t`/старте/reload — обычным системным
# резолвером (не через `resolver` директиву, та только для динамических
# proxy_pass $var). Если во время самого первого прогона этой схемы
# попытаться сделать `nginx -t` сразу после того, как ожил только backend_a
# (а backend_b/frontend_a/frontend_b ещё не существуют вообще), nginx -t
# провалится с "host not found in upstream" — reload не произойдёт, и это
# полбеды (просто останемся на старом конфиге). БЕДА в другом: если при этом
# уже удалить старые одиночные "backend"/"frontend" контейнеры (например
# опрометчивым --remove-orphans на каждом шаге), nginx останется указывать
# в СТАРОМ (ещё не переключённом) конфиге на хост, которого больше нет —
# 502 на всё время, пока не появятся все четыре реплики. Поэтому:
#   1. ensure_exists() гарантирует, что ВСЕ ЧЕТЫРЕ реплики существуют
#      (не обязательно healthy — просто существуют, чтобы имя резолвилось)
#      ДО первой попытки nginx -t/reload в этом деплое.
#   2. --remove-orphans убран из roll_replica() и вызывается ОДИН раз, в
#      самом конце, ТОЛЬКО после того как nginx успешно перезагрузился на
#      новый конфиг (то есть старые контейнеры больше никому не нужны).
#      Используется --no-recreate — гарантия, что уже существующие и
#      корректные сервисы (включая сам nginx) НЕ пересоздаются походя.
wait_healthy() {
    # Ждёт, пока контейнер сервиса $1 не станет healthy (по докеровскому
    # healthcheck из docker-compose.yml — тот бьёт в реальный HTTP-эндпоинт,
    # а не просто проверяет "процесс запущен"). $2 — таймаут в секундах.
    local svc="$1" max_wait="$2" waited=0 cid status
    while [ "$waited" -lt "$max_wait" ]; do
        cid=$(docker compose ps -q "$svc" 2>/dev/null)
        if [ -n "$cid" ]; then
            status=$(docker inspect --format='{{.State.Health.Status}}' "$cid" 2>/dev/null)
            if [ "$status" = "healthy" ]; then
                return 0
            fi
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

ALL_REPLICAS="backend_a backend_b frontend_a frontend_b"

ensure_exists() {
    # Если контейнер сервиса $1 ещё НИ РАЗУ не существовал (переходный
    # деплой) — создаёт его (без ожидания healthy, только чтобы имя
    # появилось в Docker DNS и upstream{} мог его резолвить). В обычном
    # (стабильном) режиме все четыре реплики уже существуют — это no-op.
    # НЕ используется --no-deps: если создаётся backend_b, его собственный
    # depends_on (condition: service_healthy на backend_a, см.
    # docker-compose.yml) должен сработать по-настоящему — это и есть
    # гарантия "не мигрируем параллельно" даже для этого пути, не только
    # для порядка вызовов roll_replica ниже.
    local svc="$1"
    if [ -z "$(docker compose ps -q "$svc" 2>/dev/null)" ]; then
        echo "[$(ts)] $svc ещё не существовал (первый прогон схемы _a/_b) — создаю, чтобы nginx upstream мог его резолвить" >> "$LOG"
        docker compose up -d "$svc" >> "$LOG" 2>&1
    fi
}

NGINX_CONF_CONTAINER_PATH=/etc/nginx-src/nginx.conf

nginx_host_matches_container() {
    # ИНЦИДЕНТ 2026-09-04 (10 минут простоя на проде): раньше nginx.conf был
    # смонтирован ОДНИМ ФАЙЛОМ. `git checkout -f`/`git pull` не правят файл
    # на месте — заменяют его (новый inode на том же пути). У уже
    # запущенного контейнера bind-mount привязан к СТАРОМУ inode — контейнер
    # видел старый конфиг НАВСЕГДА, пока его не пересоздать, а `nginx -t`
    # внутри честно проверял (валидный!) старый файл. Деплой писал
    # "config valid, reload выполнен" — и это было правдой не про тот файл.
    # Теперь nginx.conf смонтирован КАТАЛОГОМ (./nginx:/etc/nginx-src:ro,
    # см. docker-compose.yml) — это структурно устраняет проблему (поиск
    # имени файла внутри примонтированного каталога всегда свежий). Но раз
    # цена ошибки — молчаливая стагнация прода, здесь ДОПОЛНИТЕЛЬНО, перед
    # КАЖДЫМ reload, сверяем sha256 хоста и того, что реально видит
    # контейнер — если они когда-нибудь разойдутся (баг Docker, другой
    # способ монтирования, что угодно), это будет ГРОМКО видно в логе, а не
    # тихо "reload выполнен" на устаревшем файле.
    local host_sha container_sha
    host_sha=$(sha256sum nginx/nginx.conf 2>/dev/null | cut -d' ' -f1)
    container_sha=$(docker compose exec -T nginx sh -c "sha256sum $NGINX_CONF_CONTAINER_PATH 2>/dev/null | cut -d' ' -f1" 2>/dev/null | tr -d '\r\n')
    if [ -z "$host_sha" ] || [ "$host_sha" != "$container_sha" ]; then
        echo "[$(ts)] !!!!! РАСХОЖДЕНИЕ bind-mount: хост nginx.conf sha256=${host_sha:-?}, контейнер видит sha256=${container_sha:-?} — reload НЕ выполняется вслепую !!!!!" >> "$LOG"
        return 1
    fi
    return 0
}

nginx_recover_stale_mount() {
    # Вызывается ТОЛЬКО если nginx_host_matches_container обнаружила
    # расхождение (в норме — при исправленном каталожном монтировании —
    # никогда не должна сработать). Единственный способ вернуть контейнеру
    # корректный bind-mount — пересоздать его; но пересоздавать с БИТЫМ
    # новым файлом нельзя (уронит порты 80/443 для всех доменов сразу,
    # без отката) — поэтому СНАЧАЛА независимая проверка нового файла в
    # одноразовом контейнере (никак не связанном с живым nginx), и только
    # при её успехе — recreate.
    echo "[$(ts)] пробую восстановиться: независимая проверка НОВОГО nginx.conf в одноразовом контейнере (живой nginx пока не тронут)" >> "$LOG"
    # ⚠️ ДЫРА, найденная ревью до выката (2026-09-04): первая версия этой
    # проверки монтировала ТОЛЬКО ./nginx — но nginx.conf ссылается на
    # внешние пути АБСОЛЮТНЫМИ путями (это НЕ вопрос синтаксиса — `nginx -t`
    # реально ОТКРЫВАЕТ эти файлы и падает, если их нет):
    #   /etc/letsencrypt/live/gaaala.duckdns.org/fullchain.pem  (ssl_certificate)
    #   /etc/letsencrypt/live/gaaala.duckdns.org/privkey.pem    (ssl_certificate_key)
    #   /etc/nginx/secrets/adminer.htpasswd     (auth_basic_user_file)
    #   /var/www/certbot                        (root, ACME challenge)
    # Проверено эмпирически (минимальные тестовые конфиги в изоляции):
    # ssl_certificate[_key] — ДЕЙСТВИТЕЛЬНО валятся без файла ("cannot load
    # certificate ... BIO_new_file() failed"); root и auth_basic_user_file —
    # НЕТ (root проверяется только при реальном запросе; auth_basic_user_file
    # читается лениво, не при -t). Значит обязательных внешних путей для -t
    # ровно два — оба под /etc/letsencrypt/live/gaaala.duckdns.org/.
    #
    # На проде nginx СЕЙЧАС (на момент этого фикса) ещё работает со старым
    # монтированием (одиночный файл) — значит именно ЭТА функция и есть
    # переходный путь на первом же деплое после выката, и должна отработать
    # правильно с первого раза.
    #
    # Решение — ВМЕСТО ручного `docker run` с вручную перечисленными
    # volume'ами (то, что и было дырой — легко забыть один) используем
    # `docker compose run --rm --no-deps nginx ...`: эфемерный контейнер
    # получает ВСЮ конфигурацию сервиса nginx из ЭТОГО ЖЕ docker-compose.yml
    # — те же volumes (./nginx:/etc/nginx-src:ro И /etc/letsencrypt:/etc/
    # letsencrypt), ТА ЖЕ docker-сеть проекта (это отдельная дыра, найденная
    # тут же: имена backend_a/backend_b в upstream{} резолвятся ТОЛЬКО
    # внутри сети compose-проекта — обычный `docker run` в неё не входит,
    # и -t валился бы на "host not found in upstream" даже с правильными
    # сертификатами). Раз источник — сам docker-compose.yml, эта проверка
    # не рассинхронизируется с реальным сервисом в будущем: правишь volumes
    # nginx один раз в docker-compose.yml, а не отдельно ещё и здесь.
    #
    # Команда переопределена на entrypoint.sh (готовит сертификат — тот же
    # скрипт, что и боевой контейнер) + `nginx -t`:
    #   • на проде сертификат уже есть → entrypoint.sh увидит "Cert уже
    #     существует", ничего не тронет, -t проверит РЕАЛЬНЫЙ сертификат;
    #   • на чистом локальном стенде без сертификата вовсе → entrypoint.sh
    #     создаст тот же self-signed placeholder, что создал бы боевой
    #     контейнер при первом старте — -t проверит его, а не упадёт вслепую.
    # Оба случая дают ЧЕСТНЫЙ ответ "запустился бы боевой nginx с этим
    # конфигом или нет" — а не ложный провал/успех из-за отсутствия внешних
    # файлов или сети, не имеющих отношения к тому, что реально проверяем
    # (сам nginx.conf). Запись в /etc/letsencrypt идёт ТОЛЬКО если
    # placeholder ещё не существует (entrypoint.sh сам это проверяет) — на
    # проде, где сертификат уже есть, эта проверка ничего не пишет, только
    # читает. `--no-deps` — не трогаем db/backend/frontend (уже подняты
    # предыдущими шагами roll_replica), `-T` — без псевдо-tty, безопасно в
    # неинтерактивном скрипте.
    #
    # `sh -c "..."` вокруг nginx-команды — не только ради Windows/git-bash
    # тестового стенда (там MSYS переписывает голый аргумент "/etc/..." в
    # виндовый путь и ломает вызов; внутри "sh -c '...'" этого не происходит,
    # т.к. путь — часть одной строки, а не отдельный argv с ведущим "/").
    # На проде (обычный Linux bash) эта обёртка ничего не меняет, но и не
    # вредит — дополнительный слой sh -c безопасен и делает вызов переносимым.
    if ! docker compose run --rm --no-deps -T nginx sh -c "/etc/nginx-src/entrypoint.sh && nginx -t -c /etc/nginx-src/nginx.conf" >> "$LOG" 2>&1; then
        echo "[$(ts)] !!!!! НОВЫЙ nginx.conf сам по себе невалиден (или недостающий внешний файл, на который он ссылается) — пересоздание ОТМЕНЕНО, живой nginx остаётся нетронутым на старом конфиге, деплой FAILED !!!!!" >> "$LOG"
        return 1
    fi
    echo "[$(ts)] новый конфиг валиден независимо — пересоздаю контейнер nginx (единственный способ снять расхождение)" >> "$LOG"
    docker compose up -d --force-recreate nginx >> "$LOG" 2>&1
    # Дать контейнеру пару секунд подняться перед проверкой (nginx:alpine
    # стартует за доли секунды, но сам docker-daemon событийно чуть отстаёт).
    sleep 3
    if docker compose exec -T nginx sh -c "nginx -t -c $NGINX_CONF_CONTAINER_PATH" >> "$LOG" 2>&1; then
        echo "[$(ts)] nginx пересоздан, обслуживает актуальный конфиг" >> "$LOG"
        return 0
    fi
    echo "[$(ts)] !!!!! nginx пересоздан, но -t после пересоздания всё равно проваливается — деплой FAILED, требуется ручное вмешательство !!!!!" >> "$LOG"
    return 1
}

nginx_reload_if_valid() {
    # Единая точка входа для перезагрузки nginx. Порядок ЖЁСТКО фиксирован:
    #   1. sha256 хоста vs то, что реально видит контейнер (см. выше) —
    #      если разошлось, восстановление через nginx_recover_stale_mount
    #      (проверка НОВОГО файла В ИЗОЛЯЦИИ, потом recreate) вместо reload.
    #   2. `nginx -t -c /etc/nginx-src/nginx.conf` — ЯВНО указываем путь:
    #      конфиг больше не лежит по дефолтному /etc/nginx/nginx.conf,
    #      и в любом случае явный путь гарантирует, что проверяем ИМЕННО
    #      тот файл, который поедет в reload (`-s reload` ниже без `-c`
    #      штатно находит уже запущенный master по pid-файлу и просит его
    #      перечитать СВОЙ, уже известный ему, путь — тот же самый).
    #   3. Только при успехе (1) и (2) — `nginx -s reload`.
    # При провале любого шага мастер-процесс nginx НИЧЕГО не делает и
    # продолжает обслуживать трафик на уже загруженном (старом, заведомо
    # рабочем) конфиге — ни одного деструктивного шага. NGINX_OK взводится
    # в 1, чтобы итоговый гейт в конце скрипта честно показал провал, даже
    # если обе реплики backend/frontend поднялись без проблем.
    if ! nginx_host_matches_container; then
        if nginx_recover_stale_mount; then
            return 0
        fi
        NGINX_OK=1
        return 1
    fi
    if docker compose exec -T nginx sh -c "nginx -t -c $NGINX_CONF_CONTAINER_PATH" >> "$LOG" 2>&1; then
        docker compose exec -T nginx nginx -s reload >> "$LOG" 2>&1
        echo "[$(ts)] nginx: конфиг валиден (хост и контейнер совпадают), reload выполнен" >> "$LOG"
        return 0
    else
        echo "[$(ts)] !!!!! nginx -t ПРОВАЛИЛСЯ — reload НЕ выполнен, nginx продолжает работать на ПРЕЖНЕМ конфиге (см. вывод nginx -t выше в логе), деплой считается неуспешным !!!!!" >> "$LOG"
        NGINX_OK=1
        return 1
    fi
}

roll_replica() {
    # Пересоздаёт ОДНУ реплику сервиса $1 (ждёт до $2 секунд её healthcheck).
    # Если она ожила — на всякий случай подстраховывает существование
    # ОСТАЛЬНЫХ трёх реплик (ensure_exists, см. комментарий про ловушку
    # переходного деплоя выше) и только тогда пробует nginx -t + reload,
    # чтобы nginx подхватил актуальный IP этой реплики (Docker пересоздаёт
    # контейнер → IP меняется) и снова балансировал между обеими репликами,
    # а не только полагался на proxy_next_upstream-фолбэк на вторую.
    local svc="$1" max_wait="$2" peer
    echo "[$(ts)] roll: recreating $svc" >> "$LOG"
    docker compose up -d --no-deps "$svc" >> "$LOG" 2>&1
    if ! wait_healthy "$svc" "$max_wait"; then
        echo "[$(ts)] !!!!! $svc НЕ прошёл healthcheck за ${max_wait}s — трафик продолжает идти через вторую реплику (nginx upstream fallback), деплой считается неуспешным, $svc НЕ включаем в ротацию (reload не делаем) !!!!!" >> "$LOG"
        return 1
    fi
    echo "[$(ts)] roll: $svc healthy" >> "$LOG"
    for peer in $ALL_REPLICAS; do
        ensure_exists "$peer"
    done
    nginx_reload_if_valid
    return 0
}

# Код возврата ОБЯЗАТЕЛЬНО проверяем: раньше упавшая сборка молча
# «проглатывалась», docker compose up -d поднимал СТАРЫЙ образ, а лог
# всё равно заканчивался строкой "deploy complete" — провал выглядел
# как успех (владелец получал 502 или требовал hard refresh без объяснений).
#
# Оба образа собираются здесь, ДО миграций и ДО касания любой реплики —
# раньше frontend собирался только после того, как backend уже был
# полностью прокатан. Причина переноса: ensure_exists() (переходный деплой)
# должен мочь создать ЛЮБУЮ из четырёх реплик, включая frontend_a/frontend_b,
# ещё во время roll_replica(backend_a) — а для этого их образ уже должен
# существовать, иначе `docker compose up -d frontend_a` внутри ensure_exists
# сама вынуждена будет собирать образ (неявно, без проверки кода возврата
# нашим скриптом). Собираем backend_a/frontend_a ОДИН раз каждый — вторая
# реплика пары использует тот же тег образа (см. `image:` в docker-compose.yml).
docker compose build backend_a >> "$LOG" 2>&1
BACKEND_BUILD_OK=$?
FRONTEND_BUILD_OK=1
if [ "$BACKEND_BUILD_OK" -eq 0 ]; then
    docker compose build --build-arg GIT_SHA="$GIT_SHA" frontend_a >> "$LOG" 2>&1
    FRONTEND_BUILD_OK=$?
fi
BACKEND_OK=1
FRONTEND_OK=1
NGINX_OK=0

if [ "$BACKEND_BUILD_OK" -ne 0 ]; then
    echo "[$(ts)] !!!!! СБОРКА ОБРАЗА backend ПРОВАЛИЛАСЬ (exit $BACKEND_BUILD_OK) — деплой ПРЕРВАН ДО миграций и ДО перезапуска чего-либо, на проде остаётся ПРЕДЫДУЩАЯ версия !!!!!" >> "$LOG"
elif [ "$FRONTEND_BUILD_OK" -ne 0 ]; then
    echo "[$(ts)] !!!!! СБОРКА ОБРАЗА frontend ПРОВАЛИЛАСЬ (exit $FRONTEND_BUILD_OK) — деплой ПРЕРВАН ДО миграций и ДО перезапуска чего-либо (оба образа собираются ДО каких-либо действий с контейнерами), на проде остаётся ПРЕДЫДУЩАЯ версия !!!!!" >> "$LOG"
else
    # Миграции — ОДИН РАЗ, ДО подъёма любой новой реплики (одноразовый шаг,
    # как уже было сделано для check_schema.py). Это не даёт alembic
    # выполниться параллельно в двух процессах: реплики пересоздаются строго
    # последовательно (roll_replica ниже), а на холодном старте с нуля
    # backend_b и так ждёт healthy backend_a (depends_on в docker-compose.yml).
    # Использует `docker compose run --rm` — эфемерный контейнер на свежем
    # образе, который выходит сразу после применения миграций.
    echo "[$(ts)] applying alembic migrations (pre-start, one-shot)" >> "$LOG"
    docker compose run --rm --no-deps backend_a python migrate.py >> "$LOG" 2>&1
    MIGRATE_OK=$?
    if [ "$MIGRATE_OK" -ne 0 ]; then
        echo "[$(ts)] !!!!! МИГРАЦИЯ БД ПРОВАЛИЛАСЬ (exit $MIGRATE_OK) — деплой ПРЕРВАН ДО перезапуска реплик, backend остаётся на ПРЕДЫДУЩЕЙ версии на обеих репликах !!!!!" >> "$LOG"
    else
        # Apply schema migrations BEFORE starting backend container.
        # Reason: if a migration adds a column, SQLAlchemy first request will
        # crash with UndefinedColumn → backend Exited → docker exec fails →
        # `|| true` swallows the error → site stays 502.
        echo "[$(ts)] applying schema drift fixes (check_schema.py, pre-start)" >> "$LOG"
        docker compose run --rm --no-deps backend_a python /app/check_schema.py --apply >> "$LOG" 2>&1 || \
            echo "[$(ts)] WARN: check_schema.py --apply failed (see above)" >> "$LOG"

        # Поочерёдно: backend_a, backend_b, frontend_a, frontend_b. В любой
        # момент времени внутри каждой пары минимум одна реплика жива —
        # клиент не видит недоступный backend/frontend благодаря
        # proxy_next_upstream в nginx. roll_replica сама следит, чтобы к
        # моменту nginx -t все четыре имени были резолвимы (см. ensure_exists
        # выше и комментарий про ловушку переходного деплоя).
        if roll_replica backend_a 120 && roll_replica backend_b 120; then
            BACKEND_OK=0
            if roll_replica frontend_a 60 && roll_replica frontend_b 60; then
                FRONTEND_OK=0
            fi
        fi

        if [ "$BACKEND_OK" -eq 0 ] && [ "$FRONTEND_OK" -eq 0 ]; then
            # Орфан-контейнеры (например одиночные "backend"/"frontend" из
            # схемы ДО этого деплоя) подчищаем ТОЛЬКО сейчас — после того как
            # nginx уже как минимум один раз успешно перезагрузился на конфиг,
            # который их больше не упоминает (см. roll_replica → nginx_reload_
            # if_valid). Раньше --remove-orphans стоял на каждом отдельном
            # roll_replica и мог снести старые контейнеры ДО того, как nginx
            # вообще узнал, что они больше не нужны — окно 502 длиной "пока не
            # появятся все четыре реплики". --no-recreate — гарантия, что уже
            # существующие сервисы (включая САМ nginx) этой командой не
            # пересоздаются, только удаляются настоящие орфаны.
            docker compose up -d --no-recreate --remove-orphans >> "$LOG" 2>&1
            docker image prune -f >> "$LOG" 2>&1
        fi
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

# "deploy complete" печатаем ТОЛЬКО если backend/frontend реально прокатились
# на ОБЕИХ репликах и (если менялся) nginx-конфиг применился — иначе лог
# должен честно показывать провал, а не создавать иллюзию завершённого деплоя.
if [ "$BACKEND_OK" -eq 0 ] && [ "$FRONTEND_OK" -eq 0 ] && [ "$NGINX_OK" -eq 0 ]; then
    echo "[$(ts)] deploy complete" >> "$LOG"
else
    echo "[$(ts)] deploy FAILED — см. выше, что именно не прошло; vsks-deploy.service всё равно перезапущен, чтобы вебхук не завис" >> "$LOG"
    exit 1
fi
