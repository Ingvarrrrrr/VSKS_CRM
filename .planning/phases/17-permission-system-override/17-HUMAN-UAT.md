---
status: partial
phase: 17-permission-system-override
source: [17-VERIFICATION.md]
started: 2026-04-23T18:20:00Z
updated: 2026-04-23T18:20:00Z
---

## Current Test

[awaiting human testing on prod after autodeploy]

## Tests

### 1. Alembic migration applies cleanly
expected: `docker exec vsks-crm-backend-1 sh -c "cd /app && alembic upgrade head"` завершается успешно. После миграции: `permission_tabs=23`, `permission_actions=7`, `role_permissions` ≥30 строк на роль, `user_org_permission_overrides` содержит одну строку на каждого бывшего `can_publish=TRUE` пользователя. Повторный `alembic upgrade head` — идемпотентен (нет ошибок).
result: [pending]

### 2. AdminRolesView — матрица ролей
expected: `/admin/roles` открывается под admin'ом. Видны 5 строк (account_owner / admin / org_admin / manager / employee; superadmin скрыт). ~29 колонок (23 tabs + 6 actions, `publication.create` скрыт). Клик по чекбоксу → через ~300мс появляется «Сохранено ✓». Чекбоксы `admin.roles` / `staff` для собственной роли disabled с тултипом «Нельзя снять с себя доступ к Ролям/Персоналу». Reload страницы — состояние сохраняется.
result: [pending]

### 3. UserPermissionsSection — карточка пользователя
expected: в StaffView открыть edit dialog любого пользователя → секция «Доступ» видна после «Организации». Org-селектор показывает все org'и пользователя. Клик по чекбоксу → создаётся override → бейдж карточки переключается с роли на «Индивидуально». Chip `+ добавлено` или `− убрано` появляется рядом с переключённым правом. Клик по крестику chip'а — удаляет override (DELETE). Для собственного аккаунта чекбоксы `admin.roles`/`staff` disabled.
result: [pending]

### 4. Three-role sidebar smoke
expected: логин под admin → в AppBar видны все menuItems включая «Роли». Логин под manager → нет «Роли»/«Персонал». Логин под employee → видны только те вкладки, что по seed'у role_permissions для employee (Мои задачи, Чат, etc).
result: [pending]

### 5. Router redirect smoke
expected: залогиненный employee пишет `/staff` в адресной строке → редирект на `/my-tasks` (нет доступа). Admin пишет `/admin/roles` → открывается страница матрицы. Unauthenticated пользователь с любого защищённого пути → редирект на `/login`.
result: [pending]

### 6. D-09 superadmin invisibility
expected: логин под admin (не superadmin) → в `/staff` НЕ видны строки с ролью `superadmin`. Логин под superadmin → видны. API: `GET /api/users/` под admin не возвращает superadmin'ов, под superadmin — возвращает.
result: [pending]

### 7. Self-lockout 403 на backend
expected: как admin вызвать `PUT /api/permissions/roles/admin` с `[{key:'admin.roles', granted:false}]` → 403 с русским error message. То же для `staff`. `{key:'admin.roles', granted:true}` → 200 (включение разрешено, выключение — нет).
result: [pending]

### 8. can_publish roundtrip
expected: пользователь, у которого до миграции был `can_publish=TRUE`, после миграции всё ещё может `POST /api/publications/` (через override `publication.create=true`). Пользователь без такого override получает 403. Admin может в UserPermissionsSection добавить/убрать `publication.create` → изменение применяется сразу после reload.
result: [pending]

### 9. Full pytest + e2e зелёные post-deploy
expected: `docker exec vsks-crm-backend-1 sh -c "cd /app && pytest -x -q"` — все тесты зелёные (включая 6 новых тест-модулей из 17-02). `npx playwright test e2e/20-permissions.spec.ts` на `BASE_URL=http://85.239.53.155` — 7 тестов pass. Regression: e2e/*.spec.ts без новых failures.
result: [pending]

## Summary

total: 9
passed: 0
issues: 0
pending: 9
skipped: 0
blocked: 0

## Gaps

_(появятся при прогонке — сейчас пусто)_
