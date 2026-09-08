// Виджет «Структура закупок — Товары / Услуги» (cumulative по этапам pipeline).
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { computed, type Ref } from 'vue'
import { purchaseEffectivePrice } from './dashboardFormat'
import { STATUS_LABELS, STATUS_COLORS } from './dashboardStatusMaps'
import type { SubsidyRow } from './useDashboardData'

const PIPELINE_ORDER = ['plan_schedule', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']

// Helper: split purchase amount by товары/услуги using item-level data
function purchaseTypeSplit(p: any): { goods: number, services: number } {
  const items: any[] = p.items || []
  if (items.length === 0) {
    const total = purchaseEffectivePrice(p)
    if (p.item_type === 'товар') return { goods: total, services: 0 }
    if (p.item_type === 'услуга' || p.item_type === 'работа') return { goods: 0, services: total }
    return { goods: total / 2, services: total / 2 }
  }
  let goods = 0, services = 0
  for (const item of items) {
    const amt = parseFloat(item.final_total || item.total_price || 0)
    if (item.item_type === 'товар') goods += amt
    else services += amt
  }
  return { goods, services }
}

export function useGoodsServicesWidget(
  allPurchases: Ref<any[]>,
  filteredSubsidies: Ref<SubsidyRow[]>,
  totalBudget: Ref<number>,
) {
  // Товары/услуги breakdown by pipeline stage (cumulative)
  const pipelineByType = computed(() => {
    const budget = totalBudget.value || 1
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const filtered = allPurchases.value.filter((p: any) =>
      subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
    )
    return PIPELINE_ORDER
      .map((status, idx) => {
        const stagesAtOrBeyond = PIPELINE_ORDER.slice(idx)
        const stagePurchases = filtered.filter((p: any) => stagesAtOrBeyond.includes(p.status))
        let goods = 0, services = 0
        for (const p of stagePurchases) {
          const split = purchaseTypeSplit(p)
          goods += split.goods
          services += split.services
        }
        const total = goods + services
        return {
          status,
          label: STATUS_LABELS[status] || status,
          color: STATUS_COLORS[status] || '#94A3B8',
          goods,
          services,
          total,
          goodsPct: budget > 0 ? Math.round(goods / budget * 100) : 0,
          servicesPct: budget > 0 ? Math.round(services / budget * 100) : 0,
        }
      })
  })

  return { pipelineByType }
}
