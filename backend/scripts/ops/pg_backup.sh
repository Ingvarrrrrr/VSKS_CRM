#!/bin/bash
# ЭТАЛОН для сервера (владелец, 26.10.2026) — живой скрипт на сервере сейчас
# /opt/backups/pg_backup.sh, его НЕ трогать руками; при изменении логики
# обновлять ОБА (этот — как образец в репозитории, сервер — отдельно по SSH,
# ПРАВИЛО №4/деплой-протокол).
#
# Фото каталога (product_photos) вынесены из основного daily-дампа —
# --exclude-table-data исключает их БАЙТЫ (схема таблицы в дампе остаётся,
# упадёт DDL — не реальные фото), чтобы ежедневный бэкап не раздувался. Фото
# бэкапятся ОТДЕЛЬНО, своим dump, с коротким retention (2 копии — фото
# восстанавливаемы повторным скачиванием/пережатием, в отличие от остальных
# данных).
#
# ВОССТАНОВЛЕНИЕ:
#   1) База (без фото):
#        docker exec -i vsks-crm-db-1 pg_restore -U vsks -d vsks_crm --clean --if-exists < daily/vsks_crm_YYYYMMDD_HHMM.dump
#   2) Фото (отдельно, --data-only — таблица product_photos из шага 1 уже пустая):
#        docker exec -i vsks-crm-db-1 pg_restore -U vsks -d vsks_crm --data-only --disable-triggers < photos/product_photos_YYYYMMDD_HHMM.dump
#
set -euo pipefail
TS=$(date +%Y%m%d_%H%M)

# --- 1) daily: вся база, без данных product_photos (схема есть, байт нет) ---
OUT=/opt/backups/daily/vsks_crm_$TS.dump
docker exec vsks-crm-db-1 pg_dump -U vsks -d vsks_crm -Fc --exclude-table-data=product_photos > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

# --- 2) photos: отдельный дамп только product_photos (--data-only, схема создаётся daily-дампом) ---
mkdir -p /opt/backups/photos
PHOTOS_OUT=/opt/backups/photos/product_photos_$TS.dump
docker exec vsks-crm-db-1 pg_dump -U vsks -d vsks_crm -Fc -t product_photos --data-only > "$PHOTOS_OUT.tmp" && mv "$PHOTOS_OUT.tmp" "$PHOTOS_OUT"

# --- 3) weekly: жёсткая ссылка на дневной дамп по воскресеньям ---
if [ "$(date +%u)" = "7" ]; then ln "$OUT" /opt/backups/weekly/ 2>/dev/null || cp "$OUT" /opt/backups/weekly/; fi

# --- 4) retention: daily 14, weekly 4, photos 2 ---
ls -1t /opt/backups/daily/*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f || true
ls -1t /opt/backups/weekly/*.dump 2>/dev/null | tail -n +5 | xargs -r rm -f || true
ls -1t /opt/backups/photos/*.dump 2>/dev/null | tail -n +3 | xargs -r rm -f || true

echo "[$(date "+%F %T")] ok $OUT $(stat -c%s "$OUT") bytes; photos $PHOTOS_OUT $(stat -c%s "$PHOTOS_OUT") bytes" >> /var/log/vsks-backup.log
