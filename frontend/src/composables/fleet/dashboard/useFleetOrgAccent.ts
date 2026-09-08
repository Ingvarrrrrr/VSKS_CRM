// Список организаций и акцентный цвет дашборда автопарка (рамка/градиент по цвету орг).
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

export interface OrgItem { id: number; name: string; is_active: boolean; color?: string | null }

export function useFleetOrgAccent() {
  const orgsList = ref<OrgItem[]>([])
  const selectedOwners = ref<number[]>([])

  async function fetchOrgs() {
    try {
      const data = await apiFetch<OrgItem[]>('/auth/my-orgs')
      orgsList.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.error('[VehicleDash] my-orgs', e)
    }
  }

  const activeOrgColor = computed<string | null>(() => {
    if (selectedOwners.value?.length === 1) {
      const o = orgsList.value.find(x => x.id === selectedOwners.value[0])
      if (o?.color) return o.color
    }
    return orgsList.value[0]?.color || null
  })

  const dashboardAccentStyle = computed(() => activeOrgColor.value ? {
    '--org-accent': activeOrgColor.value,
    '--org-accent-soft': activeOrgColor.value + '22',
  } : {})

  return { orgsList, selectedOwners, fetchOrgs, activeOrgColor, dashboardAccentStyle }
}
