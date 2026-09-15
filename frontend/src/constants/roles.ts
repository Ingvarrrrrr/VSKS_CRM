/**
 * Единый источник перечней ролей для фронтенда (ПРАВИЛО №6, 2026-09-15).
 *
 * Модель уровней допуска (шесть ролей, по возрастанию):
 * employee < manager < org_admin (одна организация) < admin (весь аккаунт)
 * < account_owner (email-recovery) < superadmin (SaaS).
 *
 * Источник истины на бэкенде: backend/app/auth/jwt.py (ADMIN_ROLES/MANAGER_ROLES/
 * OWNER_ROLES/ROLES) — держать оба списка синхронными вручную, схема ролей меняется
 * редко. НЕ заводить третий список с этим же набором значений в другом файле —
 * импортировать отсюда.
 *
 * Раньше ADMIN_ROLES/MANAGER_ROLES были продублированы (и местами расходились —
 * забывали account_owner) в: useWishesContext.ts, AppBar.vue, usePurchaseSplit.ts,
 * OrdersView.vue, ContractsView.vue, CreateOrderView.vue, SubsidyEventsPanel.vue,
 * TaskEditDialog.vue.
 */

// org_admin и выше (включая account_owner/superadmin) — «админ хотя бы своей организации».
export const ADMIN_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin'] as const

// manager и выше.
export const MANAGER_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager'] as const

// Только два верхних SaaS-уровня (account_owner/superadmin) — сознательно ýже
// ADMIN_ROLES, не путать друг с другом.
export const SAAS_ROLES = ['superadmin', 'account_owner'] as const

// Все роли, по возрастанию уровня допуска.
export const ALL_ROLES = ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee'] as const

export type UserRole = typeof ALL_ROLES[number]
