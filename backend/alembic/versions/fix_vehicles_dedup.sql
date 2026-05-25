-- Phase 29.3 — merge vehicle duplicates by VIN + normalized plate
-- Idempotent: re-running does nothing once dups are gone.
-- Run: docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm < this_file.sql

BEGIN;

-- ============================================================
-- STEP 1. Build duplicate → canonical mapping (without touching vehicles yet)
-- ============================================================
DROP TABLE IF EXISTS _vehicle_dups;
CREATE TEMP TABLE _vehicle_dups (
    duplicate_id INT PRIMARY KEY,
    canonical_id INT NOT NULL
);

WITH all_pairs AS (
    SELECT
        v.id,
        FIRST_VALUE(v.id) OVER (
            PARTITION BY UPPER(REGEXP_REPLACE(v.plate, '\s+', '', 'g'))
            ORDER BY
                CASE WHEN v.vin IS NULL OR v.vin = '' THEN 1 ELSE 0 END,
                v.id
        ) AS canonical_id
    FROM vehicles v

    UNION ALL

    SELECT
        v.id,
        FIRST_VALUE(v.id) OVER (
            PARTITION BY UPPER(v.vin)
            ORDER BY v.id
        ) AS canonical_id
    FROM vehicles v
    WHERE v.vin IS NOT NULL AND v.vin <> ''
)
INSERT INTO _vehicle_dups (duplicate_id, canonical_id)
SELECT id, MIN(canonical_id)
FROM all_pairs
WHERE id <> canonical_id
GROUP BY id;

SELECT
    d.duplicate_id, d.canonical_id,
    vd.plate AS dup_plate, vd.vin AS dup_vin,
    vc.plate AS canon_plate, vc.vin AS canon_vin
FROM _vehicle_dups d
JOIN vehicles vd ON vd.id = d.duplicate_id
JOIN vehicles vc ON vc.id = d.canonical_id
ORDER BY d.canonical_id, d.duplicate_id;

-- ============================================================
-- STEP 2. Merge FK references from duplicate → canonical
-- ============================================================

DELETE FROM vehicle_odometer o
USING _vehicle_dups d
WHERE o.vehicle_id = d.duplicate_id
  AND EXISTS (
      SELECT 1 FROM vehicle_odometer o2
      WHERE o2.vehicle_id = d.canonical_id AND o2.date = o.date
  );

UPDATE vehicle_odometer
SET vehicle_id = d.canonical_id
FROM _vehicle_dups d
WHERE vehicle_odometer.vehicle_id = d.duplicate_id;

UPDATE vehicle_repairs           SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE vehicle_repairs.vehicle_id           = d.duplicate_id;
UPDATE vehicle_attachments       SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE vehicle_attachments.vehicle_id       = d.duplicate_id;
UPDATE vehicle_fines             SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE vehicle_fines.vehicle_id             = d.duplicate_id;
UPDATE vehicle_field_history     SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE vehicle_field_history.vehicle_id     = d.duplicate_id;
UPDATE vehicle_transfer_history  SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE vehicle_transfer_history.vehicle_id  = d.duplicate_id;
UPDATE fuel_logs                 SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE fuel_logs.vehicle_id                 = d.duplicate_id;
UPDATE trips                     SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE trips.vehicle_id                     = d.duplicate_id;
UPDATE checklists                SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE checklists.vehicle_id                = d.duplicate_id;
UPDATE incidents                 SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE incidents.vehicle_id                 = d.duplicate_id;
UPDATE fleet_documents           SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE fleet_documents.vehicle_id           = d.duplicate_id;
UPDATE purchases                 SET vehicle_id = d.canonical_id FROM _vehicle_dups d WHERE purchases.vehicle_id                 = d.duplicate_id;

-- ============================================================
-- STEP 3. Delete duplicates from vehicles
-- ============================================================
DELETE FROM vehicles WHERE id IN (SELECT duplicate_id FROM _vehicle_dups);

-- ============================================================
-- STEP 4. Normalize plate now that dups are gone
-- ============================================================
UPDATE vehicles
SET plate = UPPER(REGEXP_REPLACE(plate, '\s+', '', 'g'))
WHERE plate ~ '\s' OR plate <> UPPER(plate);

-- ============================================================
-- STEP 5. Partial unique index on VIN
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS vehicles_vin_unique_partial
    ON vehicles (UPPER(vin))
    WHERE vin IS NOT NULL AND vin <> '';

-- ============================================================
-- STEP 6. Verify
-- ============================================================
SELECT 'after_dedup_total'           AS check, COUNT(*)::text       AS value FROM vehicles
UNION ALL SELECT 'distinct_vin_nonempty',       COUNT(DISTINCT vin)::text     FROM vehicles WHERE vin IS NOT NULL AND vin <> ''
UNION ALL SELECT 'vin_dup_groups_remaining',    COUNT(*)::text                FROM (SELECT UPPER(vin) AS u FROM vehicles WHERE vin IS NOT NULL AND vin <> '' GROUP BY UPPER(vin) HAVING COUNT(*) > 1) t
UNION ALL SELECT 'plate_with_spaces_remaining', COUNT(*)::text                FROM vehicles WHERE plate ~ '\s';

SELECT 'state_breakdown' AS check, state, COUNT(*) AS cnt FROM vehicles GROUP BY state ORDER BY state NULLS LAST;

COMMIT;
