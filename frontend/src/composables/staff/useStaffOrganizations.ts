// useStaffOrganizations.ts — каталог организаций, «моя»/«назначаемые» организации,
// цвета организаций для дерева отделов. Дословный перенос из StaffView.vue.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

const ORG_COLORS = ['primary', 'purple', 'orange', 'teal', 'indigo', 'pink', 'brown']

export function useStaffOrganizations(currentRole: string) {
  // Владелец, 2026-09-01: `organizations` — общий каталог ВСЕХ организаций
  // (GET /organizations/, доступен любому залогиненному) для отображения имён
  // (color-lookup, диагностика headedOrgs и т.д.) и для НЕ-create-dialog
  // пикеров. НЕ путать с `assignableOrganizations` — узкий список «куда я
  // реально могу создать/добавить сотрудника» (GET /organizations/assignable),
  // нужен ТОЛЬКО для пикера в диалоге создания.
  // Раньше это был ОДИН и тот же ref: openCreateUser() перезаписывал общий
  // каталог узким assignable-списком, и после этого резолв имени организации
  // по id ломался для орг вне assignable-скоупа текущего редактора (баг
  // «Организация #28» — ХРО ВСКС не входила в assignable конкретного admin'а).
  const organizations = ref<any[]>([])
  const assignableOrganizations = ref<any[]>([])
  const currentOrgId = parseInt(localStorage.getItem('user_org_id') || '0') || null
  const currentOrgName = localStorage.getItem('user_org_name') || ''
  const isSuperadmin = computed(() => currentRole === 'superadmin')
  // SaaS-роли видят все орг → дать им выбор организации (account_owner Цыганов тоже).
  // Менеджер, управляющий >1 орг (напр. Маркодеева → ВСКС + Донецкое), тоже должен
  // выбирать целевую орг при добавлении сотрудника — иначе орг жёстко = его своя (баг).
  const canPickOrg = computed(() =>
    ['superadmin', 'account_owner'].includes(currentRole) || assignableOrganizations.value.length > 1
  )

  async function loadOrganizations() {
    try { organizations.value = await apiFetch<any[]>('/organizations/') } catch { organizations.value = [] }
  }

  // ── Org color map for dept nodes ──
  function orgColor(orgId: number | null | undefined): string {
    // Unify color logic: prefer Organization.color from DB (как в HierarchyView).
    // Если color задан админом через color-picker — возвращаем hex.
    // Иначе fallback на named Vuetify color по индексу.
    if (!orgId) return 'primary'
    const org = organizations.value.find((o: any) => o.id === orgId) as any
    if (org?.color && typeof org.color === 'string' && org.color.startsWith('#')) {
      return org.color
    }
    const idx = organizations.value.findIndex((o: any) => o.id === orgId)
    return ORG_COLORS[idx >= 0 ? idx % ORG_COLORS.length : 0]
  }

  // Helper: преобразует org color (hex или named) в CSS-color-value
  // для inline border-color / background стилей.
  function orgCssColor(orgId: number | null | undefined, alpha = 1): string {
    const c = orgColor(orgId)
    if (c.startsWith('#')) {
      // hex → используем как есть; для alpha добавляем суффикс
      if (alpha >= 1) return c
      // hex + alpha как rgba не получится напрямую — конвертируем
      const r = parseInt(c.slice(1, 3), 16)
      const g = parseInt(c.slice(3, 5), 16)
      const b = parseInt(c.slice(5, 7), 16)
      return `rgba(${r}, ${g}, ${b}, ${alpha})`
    }
    // Vuetify named theme color
    return alpha >= 1
      ? `rgb(var(--v-theme-${c}))`
      : `rgba(var(--v-theme-${c}), ${alpha})`
  }

  return {
    organizations, assignableOrganizations, currentOrgId, currentOrgName,
    isSuperadmin, canPickOrg, loadOrganizations, orgColor, orgCssColor,
  }
}
