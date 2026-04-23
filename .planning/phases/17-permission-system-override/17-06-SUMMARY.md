---
phase: 17-permission-system-override
plan: 06
subsystem: ui
tags: [pinia, vue3, vuetify, auth-store, permission-system, sidebar, frontend]

# Dependency graph
requires:
  - phase: 17-03
    provides: /users/me endpoint returning permissions.tabs + permissions.actions for given org_id
  - phase: 17-05
    provides: backend permissions router + schemas (PermissionsOut on UserOut)

provides:
  - frontend/src/stores/auth.ts — Pinia store with effectiveTabs, effectiveActions, loadPermissions, hasTab, hasAction, clear
  - AppBar.vue menuItems and navShortcuts filtered by authStore.hasTab(tab_key) instead of .roles.includes(role)
  - Login flow calls authStore.loadPermissions after token stored
  - App.vue mount calls authStore.loadPermissions if auth_token present
  - Org-switch (both single and multi-org) calls authStore.loadPermissions before page reload
  - Logout calls authStore.clear()

affects:
  - 17-07 (AdminRolesView — will use useAuthStore and rely on admin.roles tab_key)
  - 17-08 (UserPermissionsSection — reads overrides via same store)
  - 17-09 (router guards — will check authStore.loaded + authStore.hasTab)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pinia store with setup() syntax — effectiveTabs/effectiveActions as ref<Set<string>>, superadmin bypass in hasTab/hasAction"
    - "fail-open pattern: loadPermissions catch block sets loaded=true, empty sets — router guards never block forever"
    - "tab_key string per route entry, filter via authStore.hasTab() in computed"

key-files:
  created:
    - frontend/src/stores/auth.ts
  modified:
    - frontend/src/main.ts
    - frontend/src/components/AppBar.vue
    - frontend/src/views/LoginView.vue
    - frontend/src/App.vue

key-decisions:
  - "Task 1 files (stores/auth.ts, main.ts, LoginView.vue, App.vue) were included in the 17-05 parallel executor commit c520cbc — no duplication needed"
  - "menuItems converted from computed+roles filter to static _allMenuItems array (24 entries with tab_key) + computed filter via authStore.hasTab"
  - "ADMIN_ROLES/MANAGER_ROLES/ALL_ROLES constants retained in AppBar.vue — isEmployee computed still uses userRoleRaw for Quick Access subsidies section visibility"
  - "pinia already present in package.json ^3.0.4 — no dependency change needed"
  - "applyOrgSelection (superadmin multi-org) passes primaryOrgId = data.org_ids[0] to loadPermissions before page reload"
  - "Роли menu item added (tab_key: admin.roles, route: /admin/roles) as placeholder for Plan 17-07"

patterns-established:
  - "useAuthStore pattern: import { useAuthStore } from '../stores/auth' (or './stores/auth' from App.vue)"
  - "All org-switch call-sites wrap loadPermissions in try/catch with authStore.loaded = true in catch (fail-open)"

requirements-completed: [D-01]

# Metrics
duration: 25min
completed: 2026-04-23
---

# Phase 17 Plan 06: Frontend Auth Store + AppBar Tab-Key Migration Summary

**Pinia auth store (stores/auth.ts) wired into AppBar sidebar filter via hasTab(tab_key) replacing hardcoded .roles.includes(role), with loadPermissions called at login, mount, and org-switch**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-23T10:30:00Z
- **Completed:** 2026-04-23T11:00:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created `frontend/src/stores/auth.ts` — Pinia store with `effectiveTabs`, `effectiveActions`, `loadPermissions(orgId?)`, `hasTab(key)`, `hasAction(key)`, `clear()`. Superadmin bypass hardcoded in hasTab/hasAction. Fail-open on network error (loaded=true, empty sets).
- Verified `frontend/src/main.ts` registration order: `app.use(pinia)` before `app.use(router)` and before `app.mount()`.
- Wired `authStore.loadPermissions` in `LoginView.vue` (after token stored, before `window.location.href='/'`) and in `App.vue` (in `onMounted` after `/api/auth/me` succeeds, if auth_token present). Both wrapped in try/catch fail-open.
- Migrated `AppBar.vue`: `allNavShortcuts` (9 entries) and `_allMenuItems` (24 entries, includes new 'Роли' entry for 17-07) now use `tab_key` strings. Filters use `authStore.hasTab(n.tab_key)` / `authStore.hasTab(i.tab_key)`.
- Added `authStore.clear()` to `logout()` function in AppBar.vue.
- Added `authStore.loadPermissions(newOrgId)` to both `switchOrgSingle` and `applyOrgSelection` org-switch handlers with try/catch fail-open before page reload.

## Task Commits

1. **Task 1: Create Pinia auth store + wire login/app mount** - `c520cbc` (feat — included by 17-05 parallel executor)
2. **Task 2: Migrate AppBar.vue menuItems + shortcuts to tab_key filter** - `e1d1441` (feat)

## Files Created/Modified

- `frontend/src/stores/auth.ts` — New Pinia auth store: defineStore('auth'), effectiveTabs/effectiveActions as ref<Set<string>>, loadPermissions calls /users/me, hasTab/hasAction with superadmin bypass
- `frontend/src/main.ts` — Named `pinia` variable, `app.use(pinia)` confirmed before `app.use(router)` and `app.mount()`
- `frontend/src/components/AppBar.vue` — allNavShortcuts and _allMenuItems migrated to tab_key; filter computed uses authStore.hasTab; org-switch handlers call loadPermissions; logout calls authStore.clear()
- `frontend/src/views/LoginView.vue` — useAuthStore imported, authStore.loadPermissions called after login token stored with try/catch fail-open
- `frontend/src/App.vue` — useAuthStore imported, authStore.loadPermissions called in onMounted after /api/auth/me succeeds with try/catch fail-open

## Decisions Made

- Task 1 files were committed by the 17-05 parallel executor (c520cbc) — executor detected the files already matched expected output and proceeded to Task 2 without duplicate commits.
- `ADMIN_ROLES`/`MANAGER_ROLES`/`ALL_ROLES` constants kept in AppBar.vue — `isEmployee` computed uses `userRoleRaw` for the Quick Access subsidies section visibility control (unrelated to menu filtering).
- `_allMenuItems` static array (not computed) — 24 entries including 'Роли' (admin.roles) placeholder for Plan 17-07.
- `applyOrgSelection` (superadmin multi-org picker) uses `data.org_ids?.[0]` as the org_id for loadPermissions since superadmin may have multiple orgs selected.

## Deviations from Plan

None — plan executed as written. The only notable event was that the 17-05 parallel executor had already committed Task 1 files (stores/auth.ts, main.ts, LoginView.vue, App.vue) as part of its own commit. All files matched the expected implementation exactly.

## Issues Encountered

- `git commit` returned `index.lock` error on first attempt — another git process (17-05 executor) was in mid-commit. Resolved automatically: lock file disappeared, re-run succeeded. The 17-05 executor had actually committed Task 1 files as part of its work.

## User Setup Required

None — no external service configuration required. Permissions load from existing `/api/users/me` endpoint with `?org_id=` param.

## Known Stubs

None — `loadPermissions` makes a real API call to `/users/me?org_id=...`. When `permissions.tabs` is empty (backend not yet seeded or user has no org), `hasTab()` returns empty set but superadmin bypass ensures superadmin always sees everything. Non-superadmin users will see an empty sidebar until Plan 17-01 seed migration is applied.

## Next Phase Readiness

- Plan 17-07 (AdminRolesView): `useAuthStore` is available; `admin.roles` tab_key entry is in menuItems; route `/admin/roles` just needs the view component.
- Plan 17-08 (UserPermissionsSection): uses same store pattern.
- Plan 17-09 (Router guards): `authStore.loaded` ref is available to block navigation until permissions loaded.
- Foundation complete: sidebar visibility is now dynamic, driven by backend permission matrix seeded in 17-01.

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
