#!/bin/bash
# ЭТАЛОН для сервера (владелец, 27.10.2026) — живой скрипт на сервере сейчас
# /opt/backups/pg_backup.sh, его НЕ трогать руками; при изменении логики
# обновлять ОБА (этот — как образец в репозитории, сервер — отдельно по SSH,
# ПРАВИЛО №4/деплой-протокол).
#
# Фото каталога (product_photos) вынесены из основного daily-дампа —
# --exclude-table-data исключает их БАЙТЫ (схема таблицы в дампе остаётся,
# упадёт DDL — не реальные фото), чтобы ежедневный бэкап не раздувался.
# Фото — РАЗ В НЕДЕЛЮ (по воскресеньям), хранится ОДНА копия: дамп ~2,5 ГБ,
# «слишком жирно и всё равно не разобраться где что» (решение владельца
# 27.10.2026). Вне воскресенья фото-дамп делается только если в
# /opt/backups/photos вообще нет ни одной копии (после чистки/на новом
# сервере копия появится в ближайшую ночь, а не через неделю).
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

# --- 2) photos: раз в неделю (воскресенье) или если копий вообще нет ---
mkdir -p /opt/backups/photos
PHOTOS_OUT=/opt/backups/photos/product_photos_$TS.dump
PHOTOS_DONE=0
if [ "$(date +%u)" = "7" ] || [ -z "$(ls -1 /opt/backups/photos/*.dump 2>/dev/null)" ]; then
  docker exec vsks-crm-db-1 pg_dump -U vsks -d vsks_crm -Fc -t product_photos --data-only > "$PHOTOS_OUT.tmp" && mv "$PHOTOS_OUT.tmp" "$PHOTOS_OUT"
  PHOTOS_DONE=1
fi

# --- 3) weekly: жёсткая ссылка на дневной дамп по воскресеньям ---
if [ "$(date +%u)" = "7" ]; then ln "$OUT" /opt/backups/weekly/ 2>/dev/null || cp "$OUT" /opt/backups/weekly/; fi

# --- 4) retention: daily 14, weekly 4, photos 1 (успешный дамп уже лежит — старые можно убрать) ---
ls -1t /opt/backups/daily/*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f || true
ls -1t /opt/backups/weekly/*.dump 2>/dev/null | tail -n +5 | xargs -r rm -f || true
ls -1t /opt/backups/photos/*.dump 2>/dev/null | tail -n +2 | xargs -r rm -f || true

if [ "$PHOTOS_DONE" = "1" ]; then
  echo "[$(date "+%F %T")] ok $OUT $(stat -c%s "$OUT") bytes; photos $PHOTOS_OUT $(stat -c%s "$PHOTOS_OUT") bytes" >> /var/log/vsks-backup.log
else
  echo "[$(date "+%F %T")] ok $OUT $(stat -c%s "$OUT") bytes; photos skipped (weekly)" >> /var/log/vsks-backup.log
fi
