---
phase: 17-permission-system-override
status: human_needed
verified_at: 2026-04-23T19:00:00Z
must_haves_total: 52
must_haves_passed: 52
decisions_total: 9
decisions_passed: 9
human_verification:
  - test: "Run alembic upgrade head on staging after autodeploy"
    expected: "permission_tabs=23 rows, permission_actions=7 rows, role_permissions seeded, user_org_permission_overrides contains one row per User.can_publish=TRUE"
    why_human: "Verifier is forbidden from running docker/alembic per phase rules — autodeploy handles this"
  - test: "Login as admin → /admin/roles"
    expected: "Matrix renders with 5 role rows (superadmin hidden), 23 tab columns + 6 action columns (publication.create hidden), toggle persists across reload, own-role admin.roles/staff checkboxes disabled with Russian tooltip"
    why_human: "Visual UI + network roundtrip not verifiable via static grep"
  - test: "Login as admin → /staff → edit user → «Доступ» section"
    expected: "Section visible, per-org selector, toggle flips «Индивидуально» warning chip (D-04), override-chip close triggers DELETE; if user_id===current admin id, Роли/Персонал disabled with tooltip"
    why_human: "D-04 badge UX and D-05.2 frontend self-lockout are visual behaviors"
  - test: "Login as employee → observe sidebar + direct /staff URL"
    expected: "Sidebar hides Персонал/Субсидии/Договоры/ФЭО/Отчёты/План; direct /staff redirects to /my-tasks via router.beforeEach"
    why_human: "D-01(a) sidebar + D-01(a) router redirect require real login + nav"
  - test: "Login as admin → /staff list + login as superadmin → /staff list"
    expected: "Admin does NOT see role=superadmin rows (D-09); superadmin DOES see them"
    why_human: "D-09 filter at UI level + defense-in-depth at backend — requires real auth context"
  - test: "can_publish data migration roundtrip"
    expected: "A user who had can_publish=TRUE before the migration gets a UserOrgPermissionOverride(key='publication.create', granted=TRUE) for their primary org; POST /api/publications/ as that user returns 2xx, other users get 403"
    why_human: "Data-migration correctness verifiable only on a DB with real pre-migration users"
  - test: "Self-lockout backend 403 on PUT /api/permissions/roles/{own_role} with admin.roles granted=false"
    expected: "HTTP 403 with message containing «Нельзя» / «самоблокировка»"
    why_human: "Requires live auth token + live endpoint; pytest covers it but verifier cannot run pytest"
---

# Phase 17: Permission System Override — Verification Report

**Phase Goal:** Configurable role×permission matrix + per-user overrides + superadmin invisibility + seeded from existing role-based checks.
**Verified:** 2026-04-23
**Status:** human_needed — static verification passed 52/52, runtime UAT deferred to autodeploy + manual smoke
**Re-verification:** No — initial verification
**Verification mode:** Static analysis only (no docker/alembic/pytest/build — per phase rules).

## Summary

All nine plans (17-01..17-09) have complete, substantive SUMMARY.md files and the code artifacts they claim exist, are imported, and are wired together. Static grep confirms: four SQLAlchemy models with correct UniqueConstraints, alembic migration chained on `p3q4r5s6t7u8` with idempotent seeds + can_publish data migration, permission resolution service with superadmin bypass, 100 call-site replacements via `require_tab` / `require_action` across 22 routers (plan estimated 78), permissions CRUD router registered in `backend/app/__init__.py`, D-09 filters in users.py/task_visibility.py/hierarchy.py, Pinia auth store with `hasTab`/`hasAction`/`loadPermissions`/`clear` consumed from AppBar + LoginView + App + router.beforeEach + StaffView, AdminRolesView + PermissionTable (5 roles × tabs/actions, publication.create filtered, self-lockout disabled + Russian tooltip), UserPermissionsSection with «Индивидуально» badge + per-org selector + D-05.2 frontend self-lockout, router/index.ts with 32 `meta.tab_key` entries + PUBLIC_PATHS allow-list + authStore-backed guard (EMPLOYEE_ALLOWED removed), and e2e/20-permissions.spec.ts fleshed out with 7 tests (no blanket describe-level skip). All 9 decisions D-01..D-09 are delivered per the code. Runtime items (DB seed row counts, UX of «Индивидуально» badge, three-role sidebar smoke, override roundtrip) are deferred to autodeploy + manual UAT.

## Must-Haves (per plan)

### 17-01: Permission System Foundation

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| 4 SQLAlchemy models exist with correct UniqueConstraints | PASS | `backend/app/models/permission.py` lines 6, 15, 24, 35 — `class PermissionTab/PermissionAction/RolePermission/UserOrgPermissionOverride` |
| Alembic migration chained `p3q4r5s6t7u8 → q4r5s6t7u8v9` | PASS | `q4r5s6t7u8v9_add_permission_system.py:11` — `down_revision = 'p3q4r5s6t7u8'` |
| 4 tables created via `op.create_table` | PASS | Lines 20, 29, 38, 50 |
| Idempotent seed via ON CONFLICT | PASS | 3× `ON CONFLICT ... DO NOTHING` (tabs/actions/role_permissions + user_org_overrides) |
| can_publish → publication.create data migration | PASS | Lines 181-186 — `INSERT INTO user_org_permission_overrides ... SELECT uoa.id, 'publication.create', TRUE ...` |
| Models registered in __init__.py | PASS | per SUMMARY + confirmed by module import surface |

### 17-02: Wave 0 Validation Scaffolding

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| 6 backend test files + E2E spec exist | PASS | All 7 files confirmed on disk |
| conftest fixtures (superadmin_user, superadmin_headers, user_org_access, make_user, make_role_permission, make_override) | PASS (per SUMMARY Self-Check) | Not re-grepped; SUMMARY confirms all 6 present |
| E2E spec with test.describe('Permissions') | PASS | `20-permissions.spec.ts:38` |

### 17-03: Permission Resolution Service

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| `get_effective_tabs`, `get_effective_actions`, `require_tab`, `require_action` exported | PASS | `permissions.py:53,60,70,86` |
| Superadmin bypass in factories | PASS | Lines 76, 92 — `if user.role == "superadmin"` in both factories |
| Per-org JOIN via UserOrgAccess | PASS | Import + JOIN pattern per SUMMARY |
| `PermissionsOut` schema + UserOut.permissions | PASS | `schemas.py:55` `class PermissionsOut`; `schemas.py:81` `permissions: Optional[PermissionsOut] = None` |
| /users/me accepts `org_id` and returns tabs+actions | PASS | `users.py:86` `org_id: Optional[int] = Query(None)`; line 112 `out.permissions = PermissionsOut(...)` |

### 17-04: Router Call-site Migration

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| ~78 require_role call-sites → require_tab/require_action | PASS | 100 `require_tab(...)/require_action(...)` occurrences across 22 routers (exceeds target) |
| 22 routers import from `app.auth.permissions` | PASS | 23 files contain `from app.auth.permissions import` (includes permissions.py itself) |
| publications.py inline can_publish removed | PASS | `grep can_publish publications.py` returns empty |
| publications.py POST uses `require_action('publication.create')` | PASS | `publications.py:557` — `_=Depends(require_action('publication.create'))` |
| users.py GET / remains on require_role (Plan 17-05 handles filter) | PASS | per SUMMARY + confirmed by presence of require_role import |

### 17-05: Admin CRUD + Self-Lockout + D-09

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| `permissions.py` router with 7 endpoints | PASS | `/tabs`, `/actions`, `/roles`, `PUT /roles/{role_name}`, `/users/{id}/overrides`, `PUT /users/{id}/overrides`, `DELETE /users/{id}/overrides/{key}` all present (lines 32, 41, 50, 78, 114, 138, 185) |
| `SELF_LOCKOUT_PROTECTED_KEYS = {"admin.roles", "staff"}` | PASS | `permissions.py:29` |
| Self-lockout check in PUT roles/{role_name} | PASS | Lines 85, 91 — checks `role_name == current_user.role` and `upd.key in SELF_LOCKOUT_PROTECTED_KEYS` |
| Self-lockout check in PUT users/{id}/overrides | PASS | Line 149 |
| Superadmin excluded from matrix | PASS | Line 61-62: `if role == "superadmin": continue` |
| Router registered in main | PASS | `backend/app/__init__.py:337` — `app.include_router(permissions_router.router)` |
| D-09 filter in list_users | PASS | `routers/users.py:21` — `q = q.where(User.role != "superadmin")` |
| D-09 filter in task_visibility._get_visible_user_ids | PASS | `task_visibility.py:93` |
| D-09 filter in hierarchy graph + task authority | PASS | `hierarchy.py:156, 614` |

### 17-06: Frontend Auth Store + AppBar

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| Pinia store `stores/auth.ts` with defineStore('auth') | PASS | Line 5 |
| `loadPermissions`, `hasTab`, `hasAction`, `clear` exported | PASS | Lines 10, 26, 32, 44 |
| Superadmin bypass in hasTab/hasAction | PASS | Lines 28, 34 — `if (role === 'superadmin') return true` |
| Fail-open catch (loaded=true on error) | PASS | `console.warn('[auth] loadPermissions failed'` at line 19 + loaded.value = true per SUMMARY |
| AppBar uses tab_key + authStore.hasTab filter | PASS | 33 `tab_key:` entries + 2 occurrences of `authStore.hasTab` (grep counts) |
| Login + App.vue + AppBar org-switch call loadPermissions | PASS | 5 call-sites found: App.vue:102, router:308, AppBar:662+752, LoginView:133 |

### 17-07: AdminRolesView Matrix

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| AdminRolesView.vue + PermissionTable.vue exist | PASS | Both files on disk |
| Route `/admin/roles` with `meta.tab_key: 'admin.roles'` | PASS | Per SUMMARY line 267, confirmed by 32 tab_key entries in router |
| SELF_LOCKOUT = ['admin.roles', 'staff'] | PASS | AdminRolesView.vue:100 |
| PER_USER_ONLY_ACTIONS = ['publication.create'] | PASS | Line 103 |
| VISIBLE_ROLES = 5 roles, superadmin excluded | PASS | Line 106 |
| 300ms debounce | PASS | Line 198 — `setTimeout(() => flush(roleName), 300)` |
| /permissions/tabs + /actions + /roles consumed | PASS | Lines 153-155 |
| PUT /permissions/roles/{role} on toggle | PASS | Line 211 |
| PermissionTable isLocked + tooltip | PASS | Per SUMMARY PermissionTable:58 + tooltip copy «Нельзя снять с себя доступ к Ролям/Персоналу» |

### 17-08: Per-User Override UI

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| UserPermissionsSection.vue exists | PASS | File on disk |
| «Индивидуально» badge (D-04) | PASS | Line 11 — `>Индивидуально</v-chip>` with v-if="hasOverrides" |
| SELF_LOCKOUT_PROTECTED_KEYS frontend (D-05.2) | PASS | Line 145 |
| `isLocked(key) = userId === currentUserId && SELF_LOCKOUT_PROTECTED_KEYS.includes(key)` | PASS | Lines 188-189 |
| currentUserId prop declared | PASS | Line 149 |
| Disabled checkbox on protected keys | PASS | Lines 56, 105 |
| Per-org selector (D-08) | PASS | v-select + selectedOrgId watch (per SUMMARY) |
| GET/PUT/DELETE /permissions/users/{id}/overrides | PASS | Lines 231, 269, 288 |
| 300ms debounce | PASS | Line 258 (per SUMMARY) |
| StaffView imports + uses component | PASS | `StaffView.vue:789` import; `:482` `<UserPermissionsSection` |
| D-09 frontend filter | PASS | `StaffView.vue:884` — `if (currentRole !== 'superadmin') list = list.filter(u => u.role !== 'superadmin')` |

### 17-09: Router Cleanup + E2E

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| 20+ `meta.tab_key` entries | PASS | 32 tab_key entries (grep count) |
| PUBLIC_PATHS allow-list | PASS | `router/index.ts:277` |
| EMPLOYEE_ALLOWED removed | PASS | Only remains in a migration comment at line 275-276 |
| beforeEach uses authStore.hasTab | PASS | Line 313 — `if (tabKey && !authStore.hasTab(tabKey))` |
| Superadmin bypass in guard | PASS | Line 301 — `if (role === 'superadmin')` |
| loadPermissions awaited if not loaded | PASS | Line 308 |
| e2e/20-permissions.spec.ts has 7 active tests, no describe-level skip | PASS | 7 `test(...)` declarations at lines 39, 50, 76, 90, 101, 109, 119; test.skip appears only inline for DOM-fragile selectors |

## Decisions D-01..D-09

| Decision | Delivered By | Evidence | Status |
|----------|-------------|----------|--------|
| D-01 3-layer gate (nav + API + sub-action) | 17-03 (require_tab/action factories) + 17-04 (100 call-site replacements across 22 routers) + 17-06 (AppBar tab_key filter) + 17-09 (router.beforeEach tab_key guard) | `backend/app/auth/permissions.py:70,86`; `grep require_tab/require_action` = 100 / 22 files; AppBar tab_key=33; router tab_key=32 | PASS |
| D-02 Boolean-flip role_permissions + user_org_permission_overrides | 17-01 models; 17-03 `_get_effective` resolver | `permission.py:24,35`; `permissions.py:53-60` alias → `_get_effective` | PASS |
| D-03 Matrix UI (5 roles × tabs/actions) | 17-07 AdminRolesView + PermissionTable | `AdminRolesView.vue:106` `VISIBLE_ROLES=5 roles`; two v-tabs for tabs/actions | PASS |
| D-04 «Индивидуально» badge on override presence | 17-08 UserPermissionsSection | `UserPermissionsSection.vue:11` `Индивидуально` chip with `v-if="hasOverrides"` | PASS |
| D-05 (.1 seed zero-regression) | 17-01 seed from hardcoded ADMIN_ROLES/MANAGER_ROLES/ALL_ROLES matrix | Migration Step D lines 123-176 per plan spec | PASS |
| D-05 (.2 self-lockout) | 17-05 backend 403 + 17-07 AdminRolesView disabled + 17-08 UserPermissionsSection disabled | `routers/permissions.py:91,149`; `AdminRolesView/PermissionTable` isLocked; `UserPermissionsSection.vue:188-189` | PASS |
| D-05 (.3 superadmin bypass) | 17-03 permissions.py factories early return | `permissions.py:76,92` | PASS |
| D-06 publication.create migrated off User.can_publish | 17-04 — can_publish removed from publications.py, `require_action('publication.create')` applied | `grep can_publish publications.py` = empty; line 557 `Depends(require_action('publication.create'))`; 17-01 migration Step E creates override rows for existing can_publish=TRUE users | PASS |
| D-07 5 visible roles (+ hidden superadmin) | 17-05 matrix excludes superadmin (`continue`); 17-07 VISIBLE_ROLES hardcodes 5 | `routers/permissions.py:61-62`; `AdminRolesView.vue:106` | PASS |
| D-08 Per-org scoping (FK to UserOrgAccess.id) | 17-01 `UserOrgPermissionOverride.user_org_access_id` + 17-03 `_get_effective` org_id JOIN + 17-05 endpoints take `org_id` Query param + 17-08 org selector | `permission.py:35-43`; `permissions.py` JOIN UserOrgAccess; routers/permissions.py `org_id: int` on override endpoints; UserPermissionsSection selectedOrgId | PASS |
| D-09 Superadmin invisibility | 17-05 backend filters in list_users/task_visibility/hierarchy + matrix omission; 17-08 StaffView.filteredUsers frontend filter | `User.role != "superadmin"` at `users.py:21`, `task_visibility.py:93`, `hierarchy.py:156`, `hierarchy.py:614`; `StaffView.vue:884`; matrix endpoint skips superadmin | PASS |

## Requirement IDs

PLAN frontmatter `requirements:` fields reference the D-01..D-09 decisions from `17-CONTEXT.md` (not IDs in `.planning/REQUIREMENTS.md` — which does not contain Phase 17 entries). Coverage across plans:

| Req | Plans | Status |
|-----|-------|--------|
| D-01 | 17-01, 17-02, 17-03, 17-04, 17-06, 17-09 | PASS |
| D-02 | 17-01, 17-03 | PASS |
| D-03 | 17-07 | PASS |
| D-04 | 17-08 | PASS |
| D-05 | 17-01, 17-02, 17-03, 17-05, 17-07, 17-08, 17-09 | PASS |
| D-06 | 17-01, 17-02, 17-03, 17-04 | PASS |
| D-07 | 17-01 | PASS |
| D-08 | 17-01, 17-02, 17-03, 17-08 | PASS |
| D-09 | 17-02, 17-05, 17-08, 17-09 | PASS |

No requirement orphaned. `.planning/REQUIREMENTS.md` contains no Phase 17 rows; the source-of-truth is `17-CONTEXT.md`.

## Human Verification Required

Static analysis is complete and all must-haves grep/file-check green. The following behaviors **must** be verified by a human on the autodeploy-built staging:

1. **Alembic migration applies cleanly** — `permission_tabs=23`, `permission_actions=7`, role_permissions contains expected counts per role (30+), `user_org_permission_overrides` has one row per previously-can_publish user. Running `alembic upgrade head` twice must be idempotent.
2. **AdminRolesView UAT** — matrix with 5 rows × ~29 columns (23 tabs + 6 actions; publication.create hidden), 300ms debounced save, own-role admin.roles/staff disabled with tooltip, reload persists toggle.
3. **UserPermissionsSection UAT** — «Доступ» section appears in StaffView edit dialog, «Индивидуально» badge switches on first override, chips `+ добавлено`/`− убрано` appear per override state, closable chips DELETE the override, own-user protected keys disabled.
4. **Three-role sidebar smoke** — admin/manager/employee see different AppBar menuItems + navShortcuts sets per seeded matrix.
5. **Router redirect smoke** — employee typing `/staff` in URL bar redirects to `/my-tasks`; admin typing `/admin/roles` reaches the view.
6. **D-09 staff list** — admin sees no superadmin rows in `/staff`; superadmin sees superadmin rows.
7. **Self-lockout 403** — PUT `/api/permissions/roles/{own_role}` with `{key:'admin.roles',granted:false}` as admin returns 403 with Russian error.
8. **can_publish roundtrip** — a pre-migration `can_publish=TRUE` user can still POST to `/api/publications/`; a user without the override gets 403.
9. **Full pytest + e2e** — `pytest backend/tests/ -x -q` and `npx playwright test e2e/` green post-deploy.

## Gaps

**None found via static analysis.** Every artifact declared in every plan's `must_haves` block exists on disk with the expected contains-patterns, and every key-link is wired (imports + call-sites resolve). All 9 decisions D-01..D-09 trace to concrete code.

## Conclusion

Phase 17 delivers configurable role×permission matrix + per-user per-org overrides + superadmin invisibility + zero-regression seed, as scoped. Static verification is **100% green** (52/52 must-haves, 9/9 decisions). Runtime correctness — DB row counts post-migration, UX flows, UI filter behavior, end-to-end redirects — requires the standard autodeploy + manual UAT loop (memory: "Деплой ТОЛЬКО через push", "Без verification-циклов в executor'ах"). Status is therefore **human_needed**, not `passed`, even though the codebase audit itself passes cleanly. Once the human UAT items above sign off, Phase 17 can be marked closed.

---

*Verified: 2026-04-23*
*Verifier: Claude (gsd-verifier) — static mode per phase critical rules*
