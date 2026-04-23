---
phase: 17-permission-system-override
plan: 08
subsystem: ui
tags: [vue3, vuetify3, permissions, overrides, pinia, staff]

# Dependency graph
requires:
  - phase: 17-permission-system-override
    provides: "Plan 17-05 permissions router (GET/PUT/DELETE /api/permissions/users/{id}/overrides?org_id=N)"
  - phase: 17-permission-system-override
    provides: "Plan 17-06 auth store + /users/me?org_id effective permissions"
provides:
  - UserPermissionsSection.vue — reusable per-user per-org override editor
  - «Индивидуально» badge (D-04) when any override exists for the selected org
  - Frontend self-lockout (D-05.2) — disables admin.roles + staff toggles on own card with tooltip
  - Per-org editing structure (D-08) via org selector inside the section
  - D-09 frontend superadmin filter in StaffView.filteredUsers (defence-in-depth over Plan 17-05 backend filter)
affects: [17-09-regression-router-cleanup, 18-staff-directory]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Component-local debounce (300ms) on writes with Record<string, boolean> pending buffer"
    - "Override chip UI: success «+ добавлено» for grants, error «− убрано» for revocations, closable to DELETE the override"
    - "Role-default set computed from GET /permissions/roles response (tabs ∪ actions per role)"

key-files:
  created:
    - frontend/src/components/UserPermissionsSection.vue
  modified:
    - frontend/src/views/StaffView.vue

key-decisions:
  - "Used editDialog.userId (actual shape) instead of PLAN's editDialog.user_id — adapted per plan's 'field names vary' guidance"
  - "orgAccessList sourced from allOrgEntries (pre-hydrated ref with org_name from /users/{id}/salary) instead of rebuilding from extraOrgIds — avoids duplicate API call"
  - "Per-org role field in mapped orgAccessList falls back to editDialog.role (global) since allOrgEntries doesn't carry per-org role — acceptable because UserOrganization.role mirroring is handled server-side; the section only needs role for default-lookup display"
  - "D-09 filter wrapped the existing filteredUsers computed (not replaced) — preserves existing role/org filter semantics"

patterns-established:
  - "Self-lockout UX pattern: v-tooltip wrapping v-checkbox with :disabled + message 'Нельзя снять с себя доступ к Ролям/Персоналу'"
  - "Override-chip closable trigger → DELETE endpoint → reactive splice from overrides ref (no full reload)"

requirements-completed: [D-04, D-05, D-08, D-09]

# Metrics
duration: ~10min
completed: 2026-04-23
---

# Phase 17 Plan 08: Per-User Override UI Section Summary

**Added «Доступ» section to StaffView user edit dialog with per-org override editor, «Индивидуально» badge (D-04), frontend self-lockout (D-05.2), and defence-in-depth superadmin filter (D-09).**

## Performance

- **Duration:** ~10 min (execution only — component draft already existed)
- **Started:** 2026-04-23T18:04:43Z (same-wave parallel with 17-07)
- **Tasks:** 2 auto + 1 auto-approved checkpoint
- **Files modified:** 2

## Accomplishments

- Reusable `UserPermissionsSection.vue` component exposing per-org tabs + actions matrix with live override state
- «Индивидуально» badge swaps the role chip when any override is active for the selected org (D-04 exactly as specified in Любарец 2026-04-21 feedback)
- Own-user edit dialog blocks toggling `admin.roles` + `staff` — disabled checkboxes with tooltip, plus defensive early return in `toggle()` (D-05.2)
- StaffView user table hides `role='superadmin'` rows from non-superadmin viewers (D-09, mirroring backend filter in Plan 17-05)
- All three permission endpoints wired: GET on mount/org-switch, debounced PUT on toggle, DELETE on override-chip close

## Task Commits

1. **Task 1: UserPermissionsSection.vue component (D-04 + D-05.2 + D-08)** — `b930af8` (feat)
2. **Task 2: StaffView integration + D-09 filter** — `658cffc` (feat)
3. **Task 3: UAT checkpoint** — ⚡ auto-approved (workflow.auto_advance=true)

**Plan metadata commit:** TBD (final docs commit)

## Files Created/Modified

- `frontend/src/components/UserPermissionsSection.vue` (created, 309 lines) — per-org override editor with badge + self-lockout + override chips + debounced save
- `frontend/src/views/StaffView.vue` (modified, +16 lines) — added component import, `currentUserId` ref, D-09 filter guard, `<UserPermissionsSection>` slot in edit dialog after «Организации» block

## Decisions Made

- **Adapted field shape:** PLAN referenced `editDialog.user_id` + `editDialog.orgAccess` but actual StaffView uses `editDialog.userId` + pre-hydrated `allOrgEntries` ref. Used existing `allOrgEntries` (already populated via `/users/{id}/salary`) to avoid a second round-trip. Plan explicitly permits this: "Adapt field names based on the actual shape in StaffView."
- **Per-org role fallback:** `allOrgEntries` rows don't carry a `role` field, so the mapped `orgAccessList` sends `role: editDialog.role` (global) for each org. The component uses this value only for the "default lookup" rendering in the header chip when no overrides exist; actual effective-permission computation lives behind `/permissions/users/.../overrides` and is unaffected.
- **D-09 filter was additive, not a rewrite:** wrapped the existing role/org filter chain. Filter order: superadmin exclusion → role filter → org filter.

## Deviations from Plan

None. Task 1 draft (pre-existing in working tree before this executor ran) already satisfied all acceptance criteria (exact `Индивидуально` badge text, `SELF_LOCKOUT_PROTECTED_KEYS`, `isLocked`, `currentUserId` prop, `setTimeout(flush, 300)`, `overrideState` + `v-chip color="warning"`). Reviewed and committed as-is. Task 2 integration adapted field names per plan's explicit guidance — not a deviation, it's the documented flexibility clause.

## Issues Encountered

None. Per the phase's critical rules (no verification loops), `tsc --noEmit` and `vite build` were NOT run — the orchestrator will validate hooks once after the wave completes.

## Known Stubs

None. The `«Доступ»` section only renders when `editDialog.userId && allOrgEntries.length` — both guarantee real data is available. No placeholder/empty-array fallthrough to UI.

## User Setup Required

None.

## Self-Check: PASSED

**Files verified:**
- ✓ `frontend/src/components/UserPermissionsSection.vue` (exists, 309 lines, tracked in git)
- ✓ `frontend/src/views/StaffView.vue` (modified, +16 lines in commit 658cffc)

**Commits verified:**
- ✓ `b930af8` — feat(17-08): add UserPermissionsSection component for per-user overrides
- ✓ `658cffc` — feat(17-08): integrate «Доступ» section into StaffView + D-09 frontend filter

**Acceptance-criteria greps (all pass):**
- ✓ `import UserPermissionsSection` — StaffView.vue line 789
- ✓ `<UserPermissionsSection` — StaffView.vue line 482
- ✓ `:user-id="editDialog.userId"` + `:current-user-id="currentUserId"` + `:user-role="editDialog.role"` — StaffView.vue lines 484–486
- ✓ `u.role !== 'superadmin'` in filteredUsers — StaffView.vue line 884
- ✓ `Индивидуально` — UserPermissionsSection.vue line 11
- ✓ `SELF_LOCKOUT_PROTECTED_KEYS = ['admin.roles', 'staff']` — UserPermissionsSection.vue line 145
- ✓ `setTimeout(flush, 300)` — UserPermissionsSection.vue line 258
- ✓ `:disabled="isLocked(` — UserPermissionsSection.vue lines 56, 105 (tabs + actions)

## Next Phase Readiness

- Plan 17-08 delivers the last frontend feature of Phase 17. Plan 17-09 (regression/router cleanup) can now proceed.
- Admin matrix (Plan 17-07, parallel wave) delivers role-level editing; this plan delivers per-user-per-org editing. Both use the same backend endpoints from Plan 17-05.
- D-04 («Индивидуально»), D-05.2 (frontend self-lockout), D-08 (per-org), D-09 (superadmin hidden in staff list) all delivered from the UI side; backend counterparts sealed in 17-01/05.
- Ready for UAT smoke run (can be batched with 17-07 after wave completes).

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
