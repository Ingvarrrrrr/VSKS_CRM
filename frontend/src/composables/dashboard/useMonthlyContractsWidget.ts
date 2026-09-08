// Виджет «Ежемесячные договоры — остаток к заказу».
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { computed, type Ref } from 'vue'
import type { SubsidyRow } from './useDashboardData'

export function useMonthlyContractsWidget(
  allPurchases: Ref<any[]>,
  filteredSubsidies: Ref<SubsidyRow[]>,
) {
  const monthlyContractsRemaining = computed(() => {
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const today = new Date()
    return allPurchases.value
      .filter((p: any) => {
        if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
        return p.is_monthly_payment && p.monthly_payment_count && p.monthly_payment_amount
      })
      .map((p: any) => {
        const count = Number(p.monthly_payment_count)
        const perMonth = parseFloat(p.monthly_payment_amount)
        const total = count * perMonth
        const start = p.service_start_date ? new Date(p.service_start_date) : null
        let elapsed = 0
        if (start && !isNaN(start.getTime())) {
          const fullMonths = Math.min(
            Math.max(0, (today.getFullYear() - start.getFullYear()) * 12 + (today.getMonth() - start.getMonth())),
            count
          )
          const partialFraction = fullMonths < count ? today.getDate() / 30 : 0
          elapsed = (fullMonths + Math.min(partialFraction, 1)) * perMonth
        }
        const remaining = Math.max(0, total - elapsed)
        return {
          id: p.id,
          name: p.name || `Закупка #${p.id}`,
          total,
          remaining,
          elapsedPct: total > 0 ? Math.min(100, Math.round((total - remaining) / total * 100)) : 0,
        }
      })
      .filter(c => c.total > 0)
  })

  const totalMonthlyRemaining = computed(() =>
    monthlyContractsRemaining.value.reduce((s, c) => s + c.remaining, 0)
  )

  return { monthlyContractsRemaining, totalMonthlyRemaining }
}
