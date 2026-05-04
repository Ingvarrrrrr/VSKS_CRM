---
phase: 18
plan: 18-03
title: Navigation — AppBar пункт «Справочник» + route /directory
wave: 3
depends_on: [18-02]
autonomous: true
files_modified:
  - frontend/src/router/index.ts
  - frontend/src/components/AppBar.vue
requirements: []
---

# 18-03: Navigation — Route + AppBar entry

<objective>
1. Добавить route `/directory` → `StaffDirectoryView` с `meta.tab_key='staff_directory'`.
2. Добавить пункт «Справочник» в AppBar (sidebar menu) с иконкой `mdi-account-multiple-outline`, видим если `authStore.hasTab('staff_directory')`.
3. (Опционально) Добавить mobile bottom-nav entry если такая навигация существует и логично место в ней.
</objective>

<must_haves>
- Route `/directory` с `meta.tab_key='staff_directory'` зарегистрирован
- Lazy import `() => import('@/views/StaffDirectoryView.vue')`
- В AppBar появился пункт «Справочник» с проверкой `authStore.hasTab('staff_directory')`
- Кликабельный, навигирует на `/directory`
- При role с разрешением — пункт виден; при отсутствии разрешения — скрыт
- Build `cd frontend && npm run build` чистый
</must_haves>

<tasks>

<task id="18-03-01" title="Route /directory">
<read_first>
- frontend/src/router/index.ts — паттерн добавления route с `meta.tab_key` (например `/staff` для StaffView), middleware/guard `router.beforeEach` который проверяет `authStore.hasTab(meta.tab_key)`
</read_first>

<action>
В `frontend/src/router/index.ts` в массив routes добавить:

```ts
{
  path: '/directory',
  name: 'staff-directory',
  component: () => import('@/views/StaffDirectoryView.vue'),
  meta: { tab_key: 'staff_directory', requiresAuth: true },
}
```

Расположить рядом с `/staff` route для логической группировки.
</action>

<acceptance_criteria>
- `grep -n "'/directory'" frontend/src/router/index.ts` возвращает 1 совпадение
- `grep -n "StaffDirectoryView" frontend/src/router/index.ts` возвращает 1 совпадение
- `grep -n "tab_key: 'staff_directory'" frontend/src/router/index.ts` возвращает 1 совпадение
</acceptance_criteria>
</task>

<task id="18-03-02" title="AppBar пункт «Справочник»">
<read_first>
- frontend/src/components/AppBar.vue — массив menu items, паттерн entry с `tab_key`, использование `authStore.hasTab()`
- frontend/src/stores/auth.ts — `hasTab(key: string): boolean` сигнатура
</read_first>

<action>
В `frontend/src/components/AppBar.vue` в массив menu items добавить новый entry рядом с пунктом «Персонал» (`/staff`):

```ts
{
  title: 'Справочник',
  icon: 'mdi-account-multiple-outline',
  to: '/directory',
  tab_key: 'staff_directory',
}
```

Если в шаблоне используется `v-if="authStore.hasTab(item.tab_key)"` — пункт автоматически появится для пользователей с разрешением.

Если есть mobile bottom navigation (`BottomNav.vue` или подобное) — **НЕ** добавлять там по умолчанию (4 кнопки внизу обычно достаточно). Можно добавить если спецификация bottom-nav это разрешает.
</action>

<acceptance_criteria>
- `grep -n "Справочник" frontend/src/components/AppBar.vue` возвращает 1+ совпадение
- `grep -n "mdi-account-multiple-outline" frontend/src/components/AppBar.vue` возвращает 1+ совпадение
- `grep -n "to: '/directory'" frontend/src/components/AppBar.vue` возвращает 1 совпадение
- `cd frontend && npm run build` завершается успешно
</acceptance_criteria>
</task>

</tasks>

<verification>
- После autodeploy: войти как admin/manager/employee — пункт «Справочник» виден в sidebar, click открывает /directory
- Войти как роль без разрешения staff_directory (если такие были после seed — все по умолчанию TRUE, так что неприменимо) — пункт скрыт.
- Прямой переход на /directory работает (не редиректит на 403/404).
</verification>
