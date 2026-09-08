// Вкладка «Аналитика» — ленивая загрузка при первом переключении на неё
// + перезагрузка при смене фильтра субсидий, пока вкладка активна.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { PURCHASE_STATUS_ORDER, purchaseStatusColor, purchaseMethodLabel } from '@/constants/purchaseStatus'
import { safeDiv } from '@/utils/numberFormat'
import { formatCurrencyShort } from './dashboardFormat'

export interface AnalyticsData {
  funnel: { status: string; count: number; total: number }[]
  monthly_payments: { year: number; month: number; total: number }[]
  top_contractors: { name: string; count: number; total: number }[]
  upcoming_deliveries: { count: number; total: number }
  // Σ(план − договор) — агрегат дашборда, отдельный показатель от ручного
  // поля закупки purchases.economy («Экономия»). Не путать и не сводить —
  // ПРАВИЛО №6 (один показатель — одно имя).
  plan_contract_delta: number
  overdue_count: number
  upcoming_deadlines: { id: number; name: string; purchase_number?: number; execution_term: string; status: string }[]
  method_distribution: Record<string, number>
  plan_fact: { subsidy: string; plan: number; contracted: number; paid: number }[]
}

// Подписи здесь намеренно в грамматическом согласовании с «закупка» (женский род:
// «Заказана», «Поставлена», «Оплачена») — оставлены как есть, унифицирован только цвет.
export const A_STATUS_LABELS: Record<string, string> = {
  wishes:           'Пожелания',
  plan_schedule:    'План закупок',
  work_in_progress: 'Ведётся работа',
  contracted:       'Законтрактована',
  ordered:          'Заказана',
  delivered:        'Поставлена',
  paid:             'Оплачена',
  planned:          'Планирование',
  in_progress:      'Ведётся работа',
}
export const A_STATUS_COLORS: Record<string, string> = {
  ...Object.fromEntries(PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusColor(s)])),
  planned: purchaseStatusColor('plan_schedule'),
  in_progress: purchaseStatusColor('work_in_progress'),
}
// Единый источник подписи способа закупки: frontend/src/constants/purchaseStatus.ts (Правило №6)
export const A_METHOD_LABELS: Record<string, string> = {
  single: purchaseMethodLabel('single'), competitive: purchaseMethodLabel('competitive'),
  quote_request: purchaseMethodLabel('quote_request'), unknown: 'Не указано',
}
export const A_METHOD_COLORS: Record<string, string> = {
  single: 'blue', competitive: 'teal', quote_request: 'purple', unknown: 'grey',
}
export const A_MONTH_NAMES = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']

export function useAnalyticsTab(activeTab: Ref<string>, selectedSubsidyIds: Ref<number[]>) {
  const analyticsData = ref<AnalyticsData | null>(null)
  const analyticsLoading = ref(false)

  const analyticsTotalPurchases = computed(() =>
    analyticsData.value ? analyticsData.value.funnel.reduce((s, i) => s + i.count, 0) : 0
  )
  const analyticsTotalPaid = computed(() => {
    if (!analyticsData.value) return '—'
    const total = analyticsData.value.monthly_payments.reduce((s, i) => s + i.total, 0)
    return formatCurrencyShort(total)
  })
  const analyticsMaxFunnel = computed(() =>
    analyticsData.value ? Math.max(...analyticsData.value.funnel.map(i => i.total), 1) : 1
  )
  const analyticsFunnelPct = (count: number) => safeDiv(count, analyticsMaxFunnel.value) * 100
  const analyticsMaxContractor = computed(() =>
    analyticsData.value?.top_contractors?.length ? analyticsData.value.top_contractors[0].total : 1
  )
  const analyticsTopPct = (total: number) => safeDiv(total, analyticsMaxContractor.value) * 100
  const analyticsMaxMonthly = computed(() =>
    // Math.max(...totals, 1) — floor на 1 даже когда список не пуст, но все месяцы
    // «оплачено 0» (иначе Math.max вернул бы 0 и analyticsBarHeight делил бы на
    // ноль — владелец, 2026-09-04: деление на ноль не должно ломать интерфейс).
    analyticsData.value?.monthly_payments?.length ? Math.max(...analyticsData.value.monthly_payments.map(m => m.total), 1) : 1
  )
  const analyticsBarHeight = (total: number) => Math.max(safeDiv(total, analyticsMaxMonthly.value) * 100, 4)

  function analyticsFormatDate(d: string): string {
    if (!d) return ''
    const [y, m, day] = d.split('-')
    return `${day}.${m}.${y}`
  }
  function analyticsDeadlineColor(d: string): string {
    const diff = (new Date(d).getTime() - Date.now()) / 86400000
    if (diff <= 7) return 'error'
    if (diff <= 14) return 'warning'
    return 'success'
  }

  async function loadAnalytics() {
    analyticsLoading.value = true
    try {
      const ids = selectedSubsidyIds.value
      const qs = ids.length > 0 ? `?subsidy_ids=${ids.join(',')}` : ''
      analyticsData.value = await apiFetch<AnalyticsData>(`/dashboard/analytics${qs}${qs ? '&' : '?'}scope=dashboard`)
    } finally {
      analyticsLoading.value = false
    }
  }

  // Load analytics on tab switch (lazy)
  watch(activeTab, (tab) => {
    if (tab === 'analytics') {
      loadAnalytics()
    }
  })

  // Reload analytics when subsidy filter changes while on analytics tab
  watch(selectedSubsidyIds, () => {
    if (activeTab.value === 'analytics') {
      loadAnalytics()
    }
  })

  return {
    analyticsData, analyticsLoading,
    analyticsTotalPurchases, analyticsTotalPaid, analyticsFunnelPct,
    analyticsTopPct, analyticsBarHeight, analyticsFormatDate, analyticsDeadlineColor,
    loadAnalytics,
  }
}
