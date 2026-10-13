#!/bin/bash
# Чистит старые локальные теги образа фронта (вытянутые из GHCR), которые
# `docker image prune -f` не трогает, потому что они ПОМЕЧЕНЫ тегом
# (ghcr.io/.../vsks-crm-frontend:<sha-дерева-frontend>). За счёт тега
# каждый pull оседает на диске навсегда — 47 штук по ~214 МБ за 11 дней
# довели диск прода до 95%.
#
# Вынесено из autodeploy.sh отдельным файлом (ПРАВИЛО №5: этот скрипт уже
# разросся до ~500 строк разной деплой-логики — чистка образов - отдельная
# забота, ей тут делать нечего).
#
# Без `set -e`: ошибка чистки НЕ должна ронять деплой — вызывается ПОСЛЕ
# того, как деплой уже прошёл успешно (см. autodeploy.sh).
set -u

REPO="${1:-}"
KEEP="${2:-${KEEP:-3}}"
LOCAL_IMAGE="${3:-}"

log() { echo "[prune_old_images] $*"; }

# --- выбор кандидатов на удаление ---------------------------------------
# Чистая, тестируемая функция: НЕ трогает docker, только решает, что
# удалить. stdin — строки "<created_epoch> <tag>" (один тег на строку).
# Аргументы: keep, затем список защищённых тегов (не удалять никогда —
# используются контейнером или это текущий $FRONTEND_LOCAL_IMAGE).
# Правило: тег выживает, если он среди KEEP самых свежих (по дате) ИЛИ
# защищён — что бы ни было раньше. Остальные теги этого же репозитория —
# в stdout, по одному на строку, это и есть кандидаты на `docker rmi`.
pick_prune_candidates() {
    local keep="$1"; shift
    local -a protected=("$@")
    local sorted rank=0
    sorted=$(sort -rn -k1,1)  # свежие сверху
    while IFS=' ' read -r created tag; do
        [ -z "${tag:-}" ] && continue
        rank=$((rank + 1))
        local is_protected=0
        local p
        for p in "${protected[@]}"; do
            if [ "$tag" = "$p" ]; then
                is_protected=1
                break
            fi
        done
        if [ "$is_protected" -eq 1 ] || [ "$rank" -le "$keep" ]; then
            continue
        fi
        echo "$tag"
    done <<< "$sorted"
}

# Если скрипт просто source-нули (например для прогона pick_prune_candidates
# в тестах/сухом прогоне) — остановиться здесь и не трогать docker.
if [ "${PRUNE_OLD_IMAGES_SOURCE_ONLY:-0}" = "1" ]; then
    return 0 2>/dev/null || exit 0
fi

if [ -z "$REPO" ]; then
    log "usage: $0 <repo> [keep] [local_image_tag] — repo не передан, выход без действий"
    exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
    log "docker не найден в PATH, пропуск"
    exit 0
fi

# --- id образов, которые нельзя удалять ---------------------------------
# 1) образы, на которые ссылается любой контейнер (включая остановленные).
PROTECTED_IDS=$(docker ps -aq 2>/dev/null | xargs -r docker inspect -f '{{.Image}}' 2>/dev/null)

# 2) образ, на который сейчас указывает $FRONTEND_LOCAL_IMAGE (если передан).
if [ -n "$LOCAL_IMAGE" ]; then
    local_id=$(docker inspect -f '{{.Id}}' "$LOCAL_IMAGE" 2>/dev/null || true)
    [ -n "$local_id" ] && PROTECTED_IDS="$PROTECTED_IDS
$local_id"
fi

# --- теги этого репозитория + дата создания + id ------------------------
# docker images не отдаёт дату как epoch напрямую — берём RepoTags+ID из
# `docker images`, затем точную дату созданием образа через `docker inspect`
# (именно "дата создания образа", как требуется, а не время docker pull).
TAGS_LINES=$(docker images --no-trunc --format '{{.Tag}} {{.ID}}' "$REPO" 2>/dev/null)

to_delete=()
pairs_for_pick=""
protected_tags=()

if [ -n "$TAGS_LINES" ]; then
    while IFS=' ' read -r tag id; do
        [ -z "${tag:-}" ] || [ "$tag" = "<none>" ] && continue
        created=$(docker inspect -f '{{.Created}}' "$id" 2>/dev/null || true)
        [ -z "$created" ] && continue
        created_epoch=$(date -d "$created" +%s 2>/dev/null || echo 0)
        pairs_for_pick="$pairs_for_pick$created_epoch $tag
"
        if printf '%s\n' "$PROTECTED_IDS" | grep -qx "$id"; then
            protected_tags+=("$tag")
        fi
    done <<< "$TAGS_LINES"
fi

deleted_count=0
failed_count=0

if [ -n "$pairs_for_pick" ]; then
    while IFS= read -r del_tag; do
        [ -z "$del_tag" ] && continue
        if docker rmi "${REPO}:${del_tag}" >/dev/null 2>&1; then
            log "удалён ${REPO}:${del_tag}"
            deleted_count=$((deleted_count + 1))
        else
            log "НЕ удалён ${REPO}:${del_tag} (вероятно используется/не найден)"
            failed_count=$((failed_count + 1))
        fi
    done < <(printf '%s' "$pairs_for_pick" | pick_prune_candidates "$KEEP" "${protected_tags[@]}")
fi

# Кэш сборки (COPY/npm ci слои и т.п.) — НЕ полный prune: без него пакеты
# на сервере качаются ~30 кБ/с и сборка бэкенда растягивается на час+.
docker builder prune -f --keep-storage 2GB >/dev/null 2>&1

log "удалено тегов: $deleted_count, не удалено (ошибка): $failed_count, repo=$REPO keep=$KEEP"
df -h / 2>/dev/null | sed 's/^/[prune_old_images] /'
