-- =============================================================================
-- fix_vehicles_dedup.sql
-- Дедупликация записей в таблице vehicles.
-- Идемпотентен: повторный запуск ничего лишнего не делает.
--
-- Группы дубликатов:
--   VIN X8956584480AD4033 → ids {11, 14, 312, 314}  (4 копии, Митсубиси Делика)
--   VIN X8956584490AD4082 → ids {13, 313}
--   VIN VF77DNFRCCJ641603 → ids {23, 335}
--   VIN XTT316300P1015643 → ids {8, 305}
--   VIN XTT316300P1023047 → ids {9, 306}
--   VIN XTT390995P1205016 → ids {10, 308}
--   VIN XTC43101M0039560  → ids {15, 315}
--   plate К618ВС797       → ids {16, 316} (без VIN)
--   plate Н429ВВ977       → ids {17, 317} (без VIN)
--
-- Canonical = наименьший id, имеющий непустой VIN.
-- Для пар без VIN canonical = наименьший id после нормализации plate.
--
-- Применение:
--   docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm < backend/alembic/versions/fix_vehicles_dedup.sql
-- =============================================================================

BEGIN;

-- ============================================================
-- ШАГ 1: Нормализация plate — убрать пробелы, привести к UPPER
-- ============================================================
-- Идемпотентно: если пробелов уже нет и plate уже UPPER — UPDATE ничего не поменяет.
UPDATE vehicles
SET plate = UPPER(REGEXP_REPLACE(plate, '\s+', '', 'g'))
WHERE plate ~ '\s' OR plate <> UPPER(plate);


-- ============================================================
-- ШАГ 2: Построить mapping дубликатов → canonical
-- ============================================================
-- Используем временную таблицу (живёт только в рамках сессии/транзакции).
-- Идемпотентно: DROP IF EXISTS перед созданием.

DROP TABLE IF EXISTS _vehicle_dups;

CREATE TEMP TABLE _vehicle_dups AS
WITH

-- 2а. Группы по VIN (только непустые VIN)
vin_groups AS (
    SELECT
        id,
        -- canonical = наименьший id в группе с непустым VIN
        MIN(id) OVER (PARTITION BY UPPER(TRIM(vin))) AS canonical_id
    FROM vehicles
    WHERE vin IS NOT NULL AND TRIM(vin) <> ''
),

-- 2б. Группы по нормализованной plate (только ТС без VIN)
plate_groups AS (
    SELECT
        id,
        -- canonical = наименьший id в группе с одинаковым plate
        MIN(id) OVER (PARTITION BY UPPER(TRIM(plate))) AS canonical_id
    FROM vehicles
    WHERE vin IS NULL OR TRIM(vin) = ''
),

all_groups AS (
    SELECT id, canonical_id FROM vin_groups
    UNION ALL
    SELECT id, canonical_id FROM plate_groups
)

-- Оставляем только дубликаты (id != canonical)
SELECT DISTINCT id AS duplicate_id, canonical_id
FROM all_groups
WHERE id <> canonical_id;


-- Отладочный SELECT — покажет, что будет удалено
SELECT
    d.duplicate_id,
    d.canonical_id,
    v_dup.plate  AS dup_plate,
    v_dup.vin    AS dup_vin,
    v_can.plate  AS can_plate,
    v_can.vin    AS can_vin
FROM _vehicle_dups d
JOIN vehicles v_dup ON v_dup.id = d.duplicate_id
JOIN vehicles v_can ON v_can.id = d.canonical_id
ORDER BY d.canonical_id, d.duplicate_id;


-- ============================================================
-- ШАГ 3: Перевести FK со всех дочерних таблиц на canonical
-- ============================================================

-- 3.1 checklists
UPDATE checklists
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = checklists.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.2 fleet_documents
UPDATE fleet_documents
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = fleet_documents.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.3 fuel_logs
UPDATE fuel_logs
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = fuel_logs.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.4 incidents
UPDATE incidents
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = incidents.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.5 purchases (nullable FK — SET NULL при удалении, но всё равно мёрджим)
UPDATE purchases
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = purchases.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.6 trips (путевые листы)
UPDATE trips
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = trips.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.7 vehicle_attachments
UPDATE vehicle_attachments
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_attachments.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.8 vehicle_fines
UPDATE vehicle_fines
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_fines.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.9 vehicle_field_history
UPDATE vehicle_field_history
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_field_history.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.10 vehicle_odometer
-- ВНИМАНИЕ: UNIQUE(vehicle_id, date) — возможен конфликт если у дубля и canonical
--   одинаковые даты одометра. Удаляем строки дубля, которые конфликтуют с canonical.
DELETE FROM vehicle_odometer AS vod
WHERE vod.vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups)
  AND EXISTS (
      SELECT 1
      FROM vehicle_odometer voc
      JOIN _vehicle_dups d ON d.duplicate_id = vod.vehicle_id
      WHERE voc.vehicle_id = d.canonical_id
        AND voc.date = vod.date
  );

UPDATE vehicle_odometer
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_odometer.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.11 vehicle_repairs
UPDATE vehicle_repairs
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_repairs.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);

-- 3.12 vehicle_transfer_history
UPDATE vehicle_transfer_history
SET vehicle_id = (SELECT canonical_id FROM _vehicle_dups WHERE duplicate_id = vehicle_transfer_history.vehicle_id)
WHERE vehicle_id IN (SELECT duplicate_id FROM _vehicle_dups);


-- ============================================================
-- ШАГ 4: Удалить дубликаты из vehicles
-- ============================================================
-- ON DELETE CASCADE обеспечивает очистку дочерних таблиц (если какая-то FK-запись
-- всё ещё осталась — каскад подчистит; но после шага 3 их быть не должно).

DELETE FROM vehicles
WHERE id IN (SELECT duplicate_id FROM _vehicle_dups);


-- ============================================================
-- ШАГ 5: Partial unique index на VIN (предотвращает новые дубли)
-- ============================================================
-- IF NOT EXISTS — идемпотентно.
CREATE UNIQUE INDEX IF NOT EXISTS vehicles_vin_unique_partial
    ON vehicles (UPPER(vin))
    WHERE vin IS NOT NULL AND vin <> '';


-- ============================================================
-- ШАГ 6: Проверка — должно быть 0 дублей
-- ============================================================
SELECT 'vin_duplicates_remaining'   AS check_name, COUNT(*) AS cnt
FROM (
    SELECT vin
    FROM vehicles
    WHERE vin IS NOT NULL AND TRIM(vin) <> ''
    GROUP BY vin
    HAVING COUNT(*) > 1
) t

UNION ALL

SELECT 'plate_duplicates_remaining' AS check_name, COUNT(*) AS cnt
FROM (
    SELECT plate
    FROM vehicles
    GROUP BY plate
    HAVING COUNT(*) > 1
) t

UNION ALL

SELECT 'total_vehicles_after' AS check_name, COUNT(*) AS cnt
FROM vehicles;


-- ============================================================
-- Всё ок → коммитим
-- ============================================================
COMMIT;
