---
phase: 06-analytics-budget-history
verified: 2026-04-03T00:00:00Z
status: gaps_found
score: 4/5 must-haves verified
gaps:
  - truth: "BUDGET-09 is reflected as complete in REQUIREMENTS.md"
    status: partial
    reason: "BudgetHistoryDialog.vue is fully implemented and wired in SubsidiesView.vue, but REQUIREMENTS.md still shows BUDGET-09 as unchecked (- [ ]). Implementation exists; checklist was not updated."
    artifacts:
      - path: ".planning/REQUIREMENTS.md"
        issue: "Line 41: '- [ ] **BUDGET-09**' — should be '[x]' after implementation in 06-03"
    missing:
      - "Change '- [ ] **BUDGET-09**' to '- [x] **BUDGET-09**' in .planning/REQUIREMENTS.md line 41"
human_verification:
  - test: "Open SubsidiesView in browser, click the history (mdi-history) button on any subsidy card"
    expected: "BudgetHistoryDialog opens showing either 'Изменений ещё не было' (if no rows) or a v-timeline of history entries"
    why_human: "Visual rendering and click-to-open flow cannot be verified programmatically"
  - test: "Edit a subsidy's budget value, save, then open its history dialog"
    expected: "A new timeline entry appears with the old and new budget values, user name, and timestamp"
    why_human: "Write-hook correctness requires a live DB write+read cycle to confirm end-to-end"
  - test: "Open BudgetDrillDownDialog from the dashboard, click a subsidy bar, then click a FEO category bar"
    expected: "Drill-down navigates through all 3 levels (subsidies → FEO roots → FEO children) without errors"
    why_human: "Chart click events and navigation state transitions require a live browser session"
---

# Phase 6: Analytics & Budget History — Verification Report

**Phase Goal:** Surface budget change history from the existing `budget_history` table and add FEO drill-down analytics.
**Verified:** 2026-04-03
**Status:** gaps_found (1 minor gap: REQUIREMENTS.md checklist not updated for BUDGET-09)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every save of a purchase that changes `planned_total_price` writes a row to `budget_history` with correct `old_value`, `new_value`, `changed_by`, `changed_at` | ✓ VERIFIED | `purchases.py` lines 700, 788–803: `old_planned_total_price` captured before setattr loop; hook fires only when `_old != _new`; all required fields populated |
| 2 | Every change to a subsidy's `limit` (budget) also writes to `budget_history` | ✓ VERIFIED | `subsidies.py` lines 176, 183–193: `old_budget` captured before setattr loop; hook fires only when `old_budget != db_subsidy.budget`; entity_type="subsidy" |
| 3 | `GET /api/subsidies/{id}/history` returns paginated history records in descending chronological order | ✓ VERIFIED | `subsidies.py` lines 541–579: endpoint exists, `order_by(changed_at.desc())`, returns `{total, items}`, supports `offset`/`limit` via Query params |
| 4 | The subsidy detail view shows a budget history timeline/modal listing all changes with timestamps and user attribution | ✓ VERIFIED | `BudgetHistoryDialog.vue` fully implemented with v-timeline, empty state, load-more pagination, `open()` exposed; wired into `SubsidiesView.vue` with mdi-history button, `historyDialogRef`, `openHistoryDialog()` |
| 5 | The existing BudgetDrillDownDialog in the dashboard loads FEO drill-down data correctly for all three levels without errors | ✓ VERIFIED | `BudgetDrillDownDialog.vue` lines 95–154: `drillStack` state machine handles all 3 levels; `apiFetch('/dashboard/')` call on open; `children` traversal for FEO levels; dashboard router mounted at `/api/dashboard` in `__init__.py` line 288; `dashboard.py` returns nested `children` arrays |

**Score:** 4/5 truths fully verified (1 has implementation present but REQUIREMENTS.md checklist not updated)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/models/budget_history.py` | BudgetHistory SQLAlchemy model | ✓ VERIFIED | Contains `__tablename__ = "budget_history"`, all 10 columns including `subsidy_id`, `entity_type`, `old_value`, `new_value`, `changed_by_name`, `changed_at` |
| `backend/app/models/__init__.py` | Model registration for create_all | ✓ VERIFIED | Line 35: `from app.models.budget_history import BudgetHistory` present |
| `backend/app/routers/purchases.py` | Write hooks in update_purchase and create_purchase | ✓ VERIFIED | Line 700: `old_planned_total_price` captured; lines 669–681: create hook with flush; lines 788–803: update hook with change-guard |
| `backend/app/routers/subsidies.py` | Write hook in update_subsidy + GET /history endpoint | ✓ VERIFIED | Lines 176, 183–193: subsidy write hook; lines 541–579: paginated history endpoint |
| `backend/app/schemas/schemas.py` | BudgetHistoryItemOut Pydantic schema | ✓ VERIFIED | Lines 810–821: schema with all 8 required fields, `from_attributes=True` |
| `frontend/src/components/BudgetHistoryDialog.vue` | Budget history timeline dialog component | ✓ VERIFIED | Full component: v-timeline, empty state ("Изменений ещё не было"), load-more button, `open()` exposed via `defineExpose`, apiFetch to `/subsidies/{id}/history` |
| `frontend/src/views/SubsidiesView.vue` | History button wiring + dialog registration | ✓ VERIFIED | Import, `historyDialogRef`, `openHistoryDialog()`, mdi-history button, `<BudgetHistoryDialog ref="historyDialogRef" />` all present |
| `frontend/src/components/BudgetDrillDownDialog.vue` | FEO drill-down dialog with 3-level navigation | ✓ VERIFIED | `drillStack`, `children` traversal, `apiFetch('/dashboard/')`, all 3 level handlers implemented |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `purchases.py` update_purchase | `budget_history` table | `db.add(BudgetHistory(...))` before `await db.commit()` | ✓ WIRED | Lines 793–803; guarded by `_old != _new` |
| `purchases.py` create_purchase | `budget_history` table | `await db.flush()` + `db.add(BudgetHistory(...))` | ✓ WIRED | Lines 628, 669–681; `p.id` available after flush at line 628 |
| `subsidies.py` update_subsidy | `budget_history` table | `db.add(BudgetHistory(...))` before `await db.commit()` | ✓ WIRED | Lines 185–193; guarded by `old_budget != db_subsidy.budget` |
| `GET /api/subsidies/{id}/history` | `budget_history` table | `select(BudgetHistoryModel).where(subsidy_id).order_by(changed_at.desc())` | ✓ WIRED | Lines 552–562; correct query and response structure |
| `SubsidiesView.vue` | `BudgetHistoryDialog.vue` | `historyDialogRef.value?.open(s.id, s.name)` | ✓ WIRED | `openHistoryDialog()` calls `.open()` on the ref |
| `BudgetHistoryDialog.vue` | `GET /api/subsidies/{id}/history` | `apiFetch('/subsidies/${id}/history?offset=...&limit=...')` | ✓ WIRED | Line 97 in component |
| `BudgetDrillDownDialog.vue` | `GET /api/dashboard/` | `apiFetch('/dashboard/')` + `drillStack` local tree traversal | ✓ WIRED | Lines 102–111 (load), lines 129–154 (3-level computed) |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| BUDGET-07 | 06-01 | Write records to `budget_history` on subsidy limit or purchase price change | ✓ SATISFIED | Write hooks in purchases.py and subsidies.py confirmed; REQUIREMENTS.md marked `[x]` |
| BUDGET-08 | 06-02 | `GET /api/subsidies/{id}/history` paginated endpoint | ✓ SATISFIED | Endpoint at subsidies.py line 541; REQUIREMENTS.md marked `[x]` |
| BUDGET-09 | 06-03 | Subsidy detail view timeline/modal showing budget history | ✗ BLOCKED (minor) | Implementation complete (BudgetHistoryDialog.vue fully wired), but REQUIREMENTS.md line 41 still shows `- [ ]` instead of `- [x]`. Code satisfies the requirement; tracking artifact is stale. |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `purchases.py` (create hook) | 670 | `if p.subsidy_id and p.planned_total_price:` — skips writing if `planned_total_price` is falsy (0 or None at creation) | ℹ️ Info | Creates no history row when a purchase is saved with zero planned price; by design per plan spec |
| `BudgetDrillDownDialog.vue` | 185 | `if (!raw?.children?.length) return` — silently no-ops on leaf click | ℹ️ Info | Expected behavior (leaf nodes have no children to drill into) |

No blocking anti-patterns found.

---

## Human Verification Required

### 1. History button opens dialog

**Test:** Open SubsidiesView in the browser. Each subsidy card should have a grey mdi-history icon button next to the edit/delete buttons.
**Expected:** Clicking the icon opens BudgetHistoryDialog. If no history rows exist, shows "Изменений ещё не было". If rows exist, shows a v-timeline of entries.
**Why human:** Visual rendering and DOM click events cannot be verified via grep.

### 2. Write hook produces visible history entry

**Test:** Edit a subsidy's budget (limit) field to a different value and save. Reopen the history dialog for that subsidy.
**Expected:** A new timeline entry appears with entity_type "Лимит субсидии", the old and new values, user name, and timestamp. Similarly, edit a purchase's НМЦД — its history dialog should show the change.
**Why human:** Requires a live DB write + API read cycle.

### 3. BudgetDrillDownDialog 3-level drill-down

**Test:** From the dashboard, click "Детализация" (or equivalent button) to open BudgetDrillDownDialog. Click a subsidy bar (level 0 → level 1). Click a FEO category bar (level 1 → level 2). Use the back button to return.
**Expected:** All three levels render chart data without console errors. Back button returns to the previous level correctly.
**Why human:** Chart click events and drillStack state transitions require a live browser session.

---

## Gaps Summary

One minor tracking gap exists: **BUDGET-09** in `REQUIREMENTS.md` remains unchecked (`- [ ]`) even though the full implementation — `BudgetHistoryDialog.vue` + wiring in `SubsidiesView.vue` — was delivered by plan 06-03. The code satisfies the requirement; only the checklist entry needs to be updated to `- [x]`.

All automated checks for the five success criteria pass. The phase goal — surfacing budget history from the `budget_history` table and adding FEO drill-down analytics — is functionally achieved in the codebase.

---

_Verified: 2026-04-03_
_Verifier: Claude (gsd-verifier)_
