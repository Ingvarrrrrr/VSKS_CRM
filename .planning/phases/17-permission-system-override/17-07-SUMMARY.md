---
phase: 17-permission-system-override
plan: 07
subsystem: ui
tags: [vue3, vuetify, admin-ui, permission-matrix, debounced-save, self-lockout, frontend]

# Dependency graph
requires:
  - phase: 17-05
    provides: GET /permissions/{tabs,actions,roles} + PUT /permissions/roles/{role} endpoints with self-lockout 403
  - phase: 17-06
    provides: Pinia auth store + tab_key-based navigation (used indirectly for sidebar visibility of /admin/roles)

provides:
  - frontend/src/views/AdminRolesView.vue — admin matrix editor at /admin/roles (5 roles × tabs/actions) with 300ms debounced PUT
  - frontend/src/components/PermissionTable.vue — reusable matrix table component with isLocked tooltip + Russian role labels
  - frontend/src/router/index.ts — new /admin/roles route with meta.tab_key='admin.roles'

affects:
  - 17-08 (UserPermissionsSection) — uses same /permissions endpoints for per-user overrides; publication.create intentionally deferred from this matrix to the user card
  - 17-09 (router guards) — /admin/roles protected via meta.tab_key, guard will deny non-admin before view mounts

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "300ms debounced PUT batching — per-role pending queue + timer, coalesces rapid toggle spam into one PUT with array of updates"
    - "Optimistic local matrix mutation on click + server revert via loadAll() on PUT error"
    - "Self-lockout visual: isLocked(role, key) = (role === currentRole && protectedKeys.includes(key)) → disabled checkbox + v-tooltip explanation"
    - "Per-user-only action filtering: PER_USER_ONLY_ACTIONS excluded from visibleActions computed (publication.create belongs in user card, not role matrix)"
    - "Vuetify v-table + scoped :deep() for compact matrix layout with wrapping column headers"

key-files:
  created:
    - frontend/src/views/AdminRolesView.vue
    - frontend/src/components/PermissionTable.vue
  modified:
    - frontend/src/router/index.ts

key-decisions:
  - "Drafts already existed in working tree from human pre-work — verified against PLAN must_haves and committed as-is (no rewrite needed)"
  - "AdminRolesView: save status shown via mutually-exclusive Сохранение/Сохранено ✓/error span with aria-live='polite' for a11y"
  - "PermissionTable uses v-tooltip :disabled guard — tooltip only activates for locked cells, preventing empty-text tooltip flash on normal checkboxes"
  - "currentRole sourced from localStorage.getItem('user_role') — consistent with existing router guard and AppBar patterns (no authStore dependency for this simple lookup)"
  - "PUT body format: array of { key, granted } objects — matches 17-05 endpoint signature; per-role coalescing keeps only the latest toggle for each key"
  - "Save error path: show saveError AND revert local state via loadAll() to guarantee UI matches server truth after failed PUT"
  - "Russian role labels (Владелец аккаунта / Администратор / Админ организации / Менеджер / Сотрудник) hardcoded in PermissionTable.roleLabel() — small fixed set, no i18n infra in project"

requirements-completed: [D-03, D-05]

# Metrics
duration: 10min
completed: 2026-04-23
---

# Phase 17 Plan 07: AdminRolesView Matrix Summary

**Admin matrix UI at /admin/roles — 5 roles × (tabs + actions) checkboxes with 300ms debounced PUT to /permissions/roles/{role}, self-lockout disabling for own role's staff/admin.roles, and publication.create filtered out (per-user only)**

## Performance

- **Duration:** ~10 min (drafts pre-existed; executor verified + committed)
- **Completed:** 2026-04-23
- **Tasks:** 1 auto + 1 checkpoint (auto-approved under workflow.auto_advance)
- **Files created:** 2 (AdminRolesView.vue, PermissionTable.vue)
- **Files modified:** 1 (router/index.ts)

## Accomplishments

- **AdminRolesView.vue (238 lines)** renders a Vuetify card with two v-tabs (Доступ к листам / Критичные действия), each containing a PermissionTable. Subtitle explicitly notes that Публикации is configured per-user. Loading, error, and save-status states all wired.
- **PermissionTable.vue (94 lines)** — reusable `<v-table>` with rows × columns × v-checkbox cells. Locked cells disabled + v-tooltip explains «Нельзя снять с себя доступ к Ролям/Персоналу». Russian role labels built-in.
- **Route /admin/roles** registered with `meta.tab_key: 'admin.roles'` — sidebar visibility and future router guard both key off this.
- **Debounce logic**: per-role pending queue + per-role 300ms timer; concurrent toggles for different roles flush independently, same-role same-key toggles coalesce to latest value.
- **Optimistic UI**: click immediately updates local Set; on PUT failure, `loadAll()` re-fetches server truth and clears the optimistic mutation.
- **Self-lockout** enforced client-side via `isLocked(role, key) = role === currentRole && protectedKeys.includes(key)` — matches backend 403 from 17-05 (defense in depth).
- **publication.create** filtered from visibleActions via `PER_USER_ONLY_ACTIONS = ['publication.create']` — action is present in backend `/permissions/actions` list but hidden from this matrix because its override surface is per-user only (see 17-08).

## Task Commits

1. **Task 1: AdminRolesView + PermissionTable + route** — `8ab8bf5` (feat)
2. **Task 2: UAT checkpoint** — auto-approved under `workflow.auto_advance: true` (visual QA deferred to manual post-deploy verification on https://vsks-crm.ru/admin/roles)

## Files Created/Modified

- `frontend/src/views/AdminRolesView.vue` — New admin matrix view. SELF_LOCKOUT, PER_USER_ONLY_ACTIONS, VISIBLE_ROLES constants; loadAll() parallel fetch; onCellChange + flush() debounced save; save status indicator.
- `frontend/src/components/PermissionTable.vue` — New reusable matrix component. colKey/colTitle/isLocked/roleLabel helpers; scoped styles for compact layout.
- `frontend/src/router/index.ts` — New route entry (lines 262-268) for `/admin/roles` → AdminRolesView.vue with `meta.tab_key: 'admin.roles'`.

## Decisions Made

- **Draft verification over rewrite** — human-drafted files in working tree matched all must_haves; committed as-is with atomic `feat(17-07): …` message.
- **Auto-approve UAT checkpoint** — `workflow.auto_advance: true` in config.json; Task 2 logged as auto-approved, manual visual verification deferred to post-deploy pass on vsks-crm.ru.
- **No router guard in this plan** — employee redirect to /my-tasks already exists via EMPLOYEE_ALLOWED list in router.beforeEach; tab_key-based guard for non-employee non-admin roles is 17-09 scope.
- **publication.create hidden, not greyed** — per W5, per-user-only actions should not appear at all in the role matrix to prevent admin confusion. User card (17-08) will be the sole surface for toggling this action.

## Deviations from Plan

None — plan executed exactly as written against pre-existing drafts. Every must_have truth verified:

- ✅ Route /admin/roles with meta.tab_key='admin.roles'
- ✅ 5 visible role rows (account_owner, admin, org_admin, manager, employee) — superadmin absent
- ✅ Checkbox click → 300ms debounce → PUT /api/permissions/roles/{role}
- ✅ Self-lockout: admin.roles + staff keys disabled on own role row with tooltip
- ✅ Reload re-fetches via onMounted(loadAll)
- ✅ publication.create NOT present in the role-matrix actions tab

## Issues Encountered

None.

## User Setup Required

None — once deployed, logs of admin-role user visiting /admin/roles will see the matrix. Backend endpoints from 17-05 already live.

## Known Stubs

None — all data flows through real API calls to backend endpoints seeded in Plans 17-01/17-05. If backend has empty `permission_tabs`/`permission_actions` tables (migration not applied), matrix renders empty state («Нет доступных вкладок/действий») gracefully.

## Next Phase Readiness

- **Plan 17-08 (UserPermissionsSection)**: Can use same `/permissions/tabs` + `/permissions/actions` fetch pattern; publication.create will appear there (not filtered). PermissionTable component could be reused if the per-user UI uses a similar matrix shape.
- **Plan 17-09 (Router guards)**: `/admin/roles` has `meta.tab_key = 'admin.roles'` ready for guard check via `authStore.hasTab(to.meta.tab_key)`.

## Self-Check: PASSED

- frontend/src/views/AdminRolesView.vue: FOUND
- frontend/src/components/PermissionTable.vue: FOUND
- frontend/src/router/index.ts /admin/roles entry: FOUND (line 264)
- SELF_LOCKOUT = ['admin.roles', 'staff']: FOUND (line 100)
- PER_USER_ONLY_ACTIONS = ['publication.create']: FOUND (line 103)
- VISIBLE_ROLES = ['account_owner', ...]: FOUND (line 106)
- 300ms debounce (`setTimeout(() => flush(roleName), 300)`): FOUND (line 198)
- isLocked check (role === currentRole && protectedKeys.includes(key)): FOUND (PermissionTable.vue:58)
- Tooltip copy «Нельзя снять с себя доступ к Ролям/Персоналу»: FOUND (PermissionTable.vue:16)
- Route `meta.tab_key: 'admin.roles'`: FOUND (router/index.ts:267)
- commit 8ab8bf5 (feat 17-07): FOUND

---
*Phase: 17-permission-system-override*
*Completed: 2026-04-23*
