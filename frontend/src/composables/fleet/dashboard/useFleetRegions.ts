// География эксплуатации ТС на дашборде автопарка: список регионов, топ-5 + «Прочее».
// Перенесено без изменений из VehicleDashboardView.vue при разбиении на модули (ПРАВИЛО №5).
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

export interface RegionItem {
  region: string
  count: number
  shtab_label: string
  by_state: Record<string, number>
}

export function useFleetRegions() {
  const regionItems = ref<RegionItem[]>([])
  const loadingRegions = ref(false)

  const availableRegions = computed(() => regionItems.value.map(r => r.region).filter(Boolean))

  const MAX_REG_COUNT = computed(() => Math.max(...regionItems.value.map(r => r.count), 1))

  // Tiles constants
  const REG_TILES_LIMIT = 12   // show first N tiles before "show more"
  const REG_DOT_MAX = 4        // max dots per status before "+N" overflow label

  const showAllRegions = ref(false)

  // Phase 29.3-R3: топ-5 регионов + 6-я строка «Прочее» (collapsible, persistent state — не сворачивается auto)
  const REG_TOP_LIMIT = 5
  const showOtherRegions = ref(false)

  const sortedRegions = computed(() => [...regionItems.value].sort((a, b) => b.count - a.count))
  const topRegions = computed(() => sortedRegions.value.slice(0, REG_TOP_LIMIT))
  const otherRegions = computed(() => sortedRegions.value.slice(REG_TOP_LIMIT))
  const otherRegionsTotalCount = computed(() => otherRegions.value.reduce((sum, r) => sum + r.count, 0))

  // Sorted by count desc, capped if not showAll (kept for legacy tiles)
  const visibleRegionItems = computed(() => {
    return showAllRegions.value ? sortedRegions.value : sortedRegions.value.slice(0, REG_TILES_LIMIT)
  })

  function regSegments(reg: RegionItem) {
    const bs = reg.by_state || {}
    const working = bs['working'] || 0
    const inRepair = (bs['in_repair'] || 0) + (bs['needs_repair'] || 0)
    const broken = (bs['broken'] || 0) + (bs['destroyed'] || 0) + (bs['not_running'] || 0)
    const other = (bs['utilized'] || 0) + (bs['transferred'] || 0) + (bs['decommissioned'] || 0)
    const max = MAX_REG_COUNT.value
    const total = reg.count
    const total_w = Math.round((total / max) * 96)
    const working_w = Math.round((working / max) * 96)
    const in_repair_w = Math.round((inRepair / max) * 96)
    const broken_w = Math.round((broken / max) * 96)
    // pct values are relative to total bar width (100%)
    const working_pct = total > 0 ? Math.round((working / total) * 100) : 0
    const in_repair_pct = total > 0 ? Math.round((inRepair / total) * 100) : 0
    const broken_pct = total > 0 ? 100 - working_pct - in_repair_pct : 0
    return { working, inRepair, broken, other, total_w, working_w, in_repair_w, broken_w, working_pct, in_repair_pct, broken_pct }
  }

  async function fetchRegions() {
    loadingRegions.value = true
    try {
      const data = await apiFetch<{ items: RegionItem[]; mock_demo: boolean }>('/vehicles-dashboard/by-region')
      regionItems.value = data.items || []
    } catch (e) {
      console.error('[VehicleDash] regions', e)
    } finally {
      loadingRegions.value = false
    }
  }

  return {
    regionItems, loadingRegions, availableRegions, MAX_REG_COUNT,
    REG_TILES_LIMIT, REG_DOT_MAX, showAllRegions, REG_TOP_LIMIT, showOtherRegions,
    sortedRegions, topRegions, otherRegions, otherRegionsTotalCount, visibleRegionItems,
    regSegments, fetchRegions,
  }
}
