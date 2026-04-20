---
phase: 16
plan: "03"
subsystem: backend/routers
tags: [refactor, purchases, import, extraction]
dependency_graph:
  requires: [16-02]
  provides: [purchase_items_import router]
  affects: [purchases.py, __init__.py]
tech_stack:
  added: []
  patterns: [router extraction, APIRouter prefix]
key_files:
  created:
    - backend/app/routers/purchase_items_import.py
  modified:
    - backend/app/routers/purchases.py
    - backend/app/__init__.py
decisions:
  - Keep same URL prefix /api/purchases for import endpoints — no API breaking change
metrics:
  duration: "~45 minutes (recovery from timeout)"
  completed: "2026-04-19"
  tasks: 4
  files: 3
---

# Phase 16 Plan 03: Extract purchase_items_import Router Summary

Extracted all items-import endpoints from the `purchases.py` monolith (2787 lines) into a dedicated `purchase_items_import.py` router (1267 lines), reducing `purchases.py` to 1556 lines.

## What Was Built

- `backend/app/routers/purchase_items_import.py` — new dedicated router (1267 lines) handling:
  - `GET /api/purchases/items/import/template` — blank xlsx template download
  - `POST /api/purchases/{pid}/items/import` — bulk import from Excel (legacy)
  - `POST /api/purchases/items/import-preview` — parse file, return headers/samples for mapping
  - `POST /api/purchases/{pid}/items/import-mapped` — import with user-specified column mapping
  - `POST /api/purchases/{pid}/items/import-smart` — AI-assisted import (markitdown + fallback)
  - `GET /api/purchases/import/feo-format/template` — FEO-format template download
  - `POST /api/purchases/import/feo-format` — import from FEO 57-column format
- OCR helpers and product-catalog upsert helper live in this module
- `purchases.py` reduced by ~1231 lines (import endpoints removed)
- `__init__.py` registered `purchase_items_import` router after `purchase_export`

## Verification

- 17/17 tests pass: `python -m pytest tests/test_routers_mounted.py -q`
- Backend startup: clean (no traceback in docker logs)
- Commit: `3d744c6` — `refactor(16-03): extract purchase_items_import from purchases`

## Deviations from Plan

None — plan executed exactly as written. (Previous agent timed out before committing; recovery agent completed registration in `__init__.py` and committed.)

## Known Stubs

None.

## Self-Check: PASSED

- `backend/app/routers/purchase_items_import.py` — FOUND (1267 lines)
- `backend/app/routers/purchases.py` — FOUND (1556 lines)
- `backend/app/__init__.py` — 2 hits for `purchase_items_import` — FOUND
- Commit `3d744c6` — FOUND
- 17 pytest tests — PASSED
