-- Phase 21.06: per-item match confirmation flag
-- Apply manually on prod (idempotent):
--   docker exec -i vsks-crm-db-1 psql -U vsks -d vsks_crm < x1y2z3a4b5c6_add_match_confirmed.sql

ALTER TABLE purchase_items
    ADD COLUMN IF NOT EXISTS match_confirmed BOOLEAN NOT NULL DEFAULT TRUE;
