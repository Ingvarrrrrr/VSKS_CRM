import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { OrgItem } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Список организаций для пикеров «Владелец» / «Эксплуатант» карточки ТС.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleOrgsList() {
  const orgsList = ref<OrgItem[]>([])

  // /organizations/ требует superadmin — обычному admin отдаёт пустой список,
  // и v-autocomplete тогда показывает "сырой" id вместо названия организации
  // (баг подтверждён на карточке ТС: «Владелец» = «1»). Используем /auth/my-orgs
  // — тот же обход, что и в VehicleListView.vue::loadOrgs(): admin получает
  // свои организации через UserOrgAccess, superadmin — все. Ответ — массив
  // объектов [{id,name,is_active}], не {items:[]}.
  async function loadOrgs() {
    try {
      const data = await apiFetch<OrgItem[] | { items: OrgItem[] }>('/auth/my-orgs')
      orgsList.value = Array.isArray(data) ? data : (data?.items ?? [])
    } catch {}
  }

  return { orgsList, loadOrgs }
}
