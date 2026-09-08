// staffLabels.ts — роли, аватарки, мелкие форматтеры вкладки «Персонал».
// Дословный перенос из StaffView.vue.

export const ROLE_LABELS: Record<string, string> = {
  superadmin: 'Суперадмин',
  account_owner: 'Хозяин аккаунта',
  admin: 'Администратор аккаунта',
  org_admin: 'Администратор организации',
  manager: 'Менеджер',
  employee: 'Сотрудник',
}

// Глобальная роль: org_admin СЮДА НЕ входит — «Администратор организации» это
// только per-org роль (UserOrgAccess.role), не глобальная. Глобально доступны
// Сотрудник / Менеджер / Администратор аккаунта (управляет всем аккаунтом).
export function getRoleItems(currentRole: string) {
  const items = [
    { value: 'manager', label: 'Менеджер' },
    { value: 'employee', label: 'Сотрудник' },
  ]
  // «Администратор аккаунта» и «Хозяин аккаунта» доступны любому, кто управляет
  // сотрудниками (org_admin и выше). Запрос 14.07: в аккаунте может не быть ни одного
  // admin/account_owner — если опции прятать, роль некому выдать в принципе.
  if (['superadmin', 'account_owner', 'admin', 'org_admin'].includes(currentRole)) {
    items.unshift({ value: 'admin', label: 'Администратор аккаунта' })
    items.unshift({ value: 'account_owner', label: 'Хозяин аккаунта' })
  }
  return items
}

export const roleColor = (r: string) => ({
  superadmin: 'purple', account_owner: 'deep-orange', admin: 'error', org_admin: 'orange-darken-2', manager: 'blue', employee: 'teal',
}[r] || 'grey')

export const AVATARS = [
  { id: 'man',     icon: 'mdi-face-man',             color: '#4CAF50', label: 'Парень' },
  { id: 'woman',   icon: 'mdi-face-woman',           color: '#E91E63', label: 'Девушка' },
  { id: 'cowboy',  icon: 'mdi-account-cowboy-hat',    color: '#FF9800', label: 'Ковбой' },
  { id: 'ninja',   icon: 'mdi-ninja',                color: '#607D8B', label: 'Ниндзя' },
  { id: 'robot',   icon: 'mdi-robot',                color: '#2196F3', label: 'Робот' },
  { id: 'cool',    icon: 'mdi-emoticon-cool-outline', color: '#9C27B0', label: 'Крутой' },
  { id: 'alien',   icon: 'mdi-alien',                color: '#00BCD4', label: 'Пришелец' },
  { id: 'pirate',  icon: 'mdi-pirate',               color: '#795548', label: 'Пират' },
]

export function getAvatar(id?: string | null) {
  return AVATARS.find(a => a.id === id) || AVATARS[0]
}
export function randomAvatarId() {
  return AVATARS[Math.floor(Math.random() * AVATARS.length)].id
}

// 29-15: helpers — days until expiry (null if date invalid/empty)
export function driverLicenseExpiryDays(dateStr: string | null): number | null {
  if (!dateStr) return null
  const exp = new Date(dateStr)
  if (isNaN(exp.getTime())) return null
  const diff = Math.ceil((exp.getTime() - Date.now()) / 86400000)
  return diff
}
export function driverMedicalExpiryDays(dateStr: string | null): number | null {
  return driverLicenseExpiryDays(dateStr)
}

export function normalizeDepartment(val: string | null | undefined): string | null {
  if (!val || typeof val !== 'string') return null
  return val.trim().split(/\s+/).map(w =>
    w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
  ).join(' ')
}
