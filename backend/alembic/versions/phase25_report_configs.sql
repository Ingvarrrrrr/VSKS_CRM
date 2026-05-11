-- Phase 25: create report_configs table (ручное применение)
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS report_configs (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(1000),
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    parameters_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_shared BOOLEAN NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_report_configs_org_name_kind ON report_configs(org_id, name, kind);
CREATE INDEX IF NOT EXISTS ix_report_configs_org_id ON report_configs(org_id);
