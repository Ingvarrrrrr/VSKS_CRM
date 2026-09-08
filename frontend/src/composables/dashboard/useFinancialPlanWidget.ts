// Виджет «Финансовый план» — график план/обязательства/долг по месяцам/кварталам
// + drill-down диалог со списком закупок группы + экспорт в Excel (прямой fetch,
// не apiFetch — сохранено как в оригинале, см. exportFinplanXlsx/exportFinplanDrilldownXlsx).
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, watch, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { PURCHASE_STATUS_ORDER, purchaseStatusLabel } from '@/constants/purchaseStatus'
import { formatCurrency, formatCurrencyShort } from './dashboardFormat'

interface ChartTheme {
  isDark: Ref<boolean>
  chartText: Ref<string>
  chartMuted: Ref<string>
  chartGrid: Ref<string>
}

// 'wishes'/'contracted'/'planned' здесь намеренно в развёрнутой формулировке документа
// финансового плана («Заявка», «Заключён договор», «Запланирован») — оставлены как есть;
// остальные (в т.ч. написание «План закупок») — из единого источника.
export const STATUS_LABELS_FINPLAN: Record<string, string> = {
  ...Object.fromEntries(PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusLabel(s)])),
  planned: 'Запланирован', wishes: 'Заявка',
  contracted: 'Заключён договор',
}

export function useFinancialPlanWidget(selectedSubsidyIds: Ref<number[]>, theme: ChartTheme) {
  const router = useRouter()
  const { isDark, chartText, chartMuted, chartGrid } = theme

  const finplanGranularity = ref<'month' | 'quarter'>('month')
  const finplanData = ref<any>(null)
  const finplanAllPeriods = ref<string[]>([])

  const finplanDrilldown = ref({
    show: false,
    loading: false,
    period: '' as string,
    category: '' as 'plan' | 'committed' | 'overdue' | 'no_deadline' | '',
    items: [] as any[],
  })

  async function openFinplanDrilldown(period: string, category: 'plan' | 'committed' | 'overdue' | 'no_deadline') {
    finplanDrilldown.value.show = true
    finplanDrilldown.value.loading = true
    finplanDrilldown.value.period = period
    finplanDrilldown.value.category = category
    finplanDrilldown.value.items = []
    try {
      const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
      const periodParam = period ? `&period=${period}` : ''
      const data = await apiFetch<any>(`/dashboard/financial-plan/details?category=${category}&granularity=${finplanGranularity.value}${periodParam}${sidParam}&scope=dashboard`)
      finplanDrilldown.value.items = data.items || []
    } catch (e) {
      finplanDrilldown.value.items = []
    } finally {
      finplanDrilldown.value.loading = false
    }
  }

  const finplanDrilldownTotal = computed(() =>
    finplanDrilldown.value.items.reduce((s: number, r: any) => s + (r.amount || 0), 0)
  )

  const finplanDrilldownTitle = computed(() => {
    const cat = finplanDrilldown.value.category
    if (cat === 'plan') return 'Плановые'
    if (cat === 'committed') return 'Принятые обязательства'
    if (cat === 'overdue') return 'Накопленный долг'
    if (cat === 'no_deadline') return 'Без срока исполнения'
    return 'Закупки'
  })

  const finplanDrilldownChipColor = computed(() => {
    const cat = finplanDrilldown.value.category
    if (cat === 'plan') return 'warning'
    if (cat === 'committed') return 'success'
    if (cat === 'overdue') return 'error'
    if (cat === 'no_deadline') return 'warning'
    return 'grey'
  })

  async function patchIsLikelyNeeded(row: any, val: boolean) {
    try {
      await apiFetch(`/purchases/${row.id}`, { method: 'PATCH', body: { is_likely_needed: val } })
      row.is_likely_needed = val
    } catch (e) {
      console.error('patchIsLikelyNeeded error', e)
    }
  }

  // no_deadline count for banner
  const finplanNoDeadlineCount = computed(() => {
    if (!finplanData.value) return 0
    const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
    return finplanData.value[key]?.no_deadline?.items_count ?? 0
  })

  // KPI текущего месяца
  const finplanCurrentMonthKpi = computed(() => {
    if (!finplanData.value) return null
    const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
    const data = finplanData.value[key]
    if (!data) return null
    const now = new Date()
    const period = finplanGranularity.value === 'month'
      ? `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      : `${now.getFullYear()}-Q${Math.ceil((now.getMonth() + 1) / 3)}`
    const planEntry = (data.plan || []).find((d: any) => d.period === period)
    const overdueEntry = (data.overdue || []).find((d: any) => d.period === period)
    return {
      period,
      plan: planEntry?.amount ?? 0,
      overdue: overdueEntry?.accumulated ?? 0,
    }
  })

  function goToOrder(id: number) {
    finplanDrilldown.value.show = false
    router.push(`/orders/${id}/edit`)
  }

  async function exportFinplanXlsx() {
    const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
    const token = localStorage.getItem('auth_token')
    const url = `/api/dashboard/financial-plan/export.xlsx?granularity=${finplanGranularity.value}${sidParam}&scope=dashboard`
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return
    const blob = await res.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `Финплан_${finplanGranularity.value}_${new Date().toISOString().slice(0, 10)}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  async function exportFinplanDrilldownXlsx() {
    const sidParam = selectedSubsidyIds.value.length === 1 ? `&subsidy_id=${selectedSubsidyIds.value[0]}` : ''
    const params = `period=${encodeURIComponent(finplanDrilldown.value.period)}&category=${finplanDrilldown.value.category}&granularity=${finplanGranularity.value}${sidParam}&scope=dashboard`
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/dashboard/financial-plan/details/export.xlsx?${params}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return
    const blob = await res.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `Финплан_${finplanDrilldown.value.period}_${finplanDrilldown.value.category}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  function formatDate(iso: string) {
    if (!iso) return ''
    const [y, m, d] = iso.split('-')
    return `${d}.${m}.${y}`
  }

  async function loadFinplan() {
    try {
      const sidParam = selectedSubsidyIds.value.length === 1 ? `?subsidy_id=${selectedSubsidyIds.value[0]}` : ''
      const finplanScopeParam = sidParam ? '&scope=dashboard' : '?scope=dashboard'
      finplanData.value = await apiFetch<any>(`/dashboard/financial-plan${sidParam}${finplanScopeParam}`)
    } catch {
      finplanData.value = null
    }
  }

  const finplanSeries = computed(() => {
    if (!finplanData.value) return []
    const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
    const data = finplanData.value[key]
    if (!data) return []
    const allPeriods = [...new Set([
      ...(data.feo_plan || []).map((d: any) => d.period),
      ...(data.plan || []).map((d: any) => d.period),
      ...(data.committed || []).map((d: any) => d.period),
      ...(data.overdue || []).map((d: any) => d.period),
    ])].sort()
    if (allPeriods.length === 0) return []
    finplanAllPeriods.value = allPeriods
    const feoMap = new Map((data.feo_plan || []).map((d: any) => [d.period, d.amount]))
    const planMap = new Map((data.plan || []).map((d: any) => [d.period, d.amount]))
    const commMap = new Map((data.committed || []).map((d: any) => [d.period, d.amount]))
    const overdueMap = new Map((data.overdue || []).map((d: any) => [d.period, d.accumulated ?? d.amount ?? 0]))
    const series: any[] = [
      { name: 'План (график ФЭО)', data: allPeriods.map(p => Math.round((feoMap.get(p) as number) ?? 0)) },
      { name: 'Принятые обязательства', data: allPeriods.map(p => Math.round((commMap.get(p) as number) ?? 0)) },
      { name: 'Плановые', data: allPeriods.map(p => Math.round((planMap.get(p) as number) ?? 0)) },
    ]
    const hasOverdue = (data.overdue || []).length > 0
    if (hasOverdue) {
      series.push({ name: 'Накопленный долг', data: allPeriods.map(p => Math.round((overdueMap.get(p) as number) ?? 0)) })
    }
    return series
  })

  const finplanOptions = computed(() => {
    if (!finplanData.value) return {}
    const key = finplanGranularity.value === 'month' ? 'by_month' : 'by_quarter'
    const data = finplanData.value[key]
    if (!data) return {}
    const allPeriods = [...new Set([
      ...(data.feo_plan || []).map((d: any) => d.period),
      ...(data.plan || []).map((d: any) => d.period),
      ...(data.committed || []).map((d: any) => d.period),
    ])].sort()
    return {
      chart: {
        type: 'bar', stacked: true, background: 'transparent', toolbar: { show: false },
        theme: { mode: isDark.value ? 'dark' : 'light' },
        events: {
          dataPointSelection: (_event: any, _ctx: any, config: any) => {
            const period = finplanAllPeriods.value[config.dataPointIndex]
            const seriesName = config.w.config.series[config.seriesIndex]?.name || ''
            // ФЭО-plan series has no drilldown — skip
            if (seriesName.includes('ФЭО')) return
            let category: 'plan' | 'committed' | 'overdue' | 'no_deadline' = 'plan'
            if (seriesName.toLowerCase().includes('принят')) category = 'committed'
            else if (seriesName.toLowerCase().includes('накопл') || seriesName.toLowerCase().includes('долг')) category = 'overdue'
            if (period) openFinplanDrilldown(period, category)
          },
        },
      },
      plotOptions: { bar: { horizontal: false, columnWidth: '60%' } },
      dataLabels: { enabled: false },
      xaxis: { categories: allPeriods, labels: { style: { colors: chartMuted.value, fontSize: '11px' } } },
      yaxis: { labels: { formatter: (v: number) => formatCurrencyShort(v), style: { colors: chartMuted.value, fontSize: '11px' } } },
      colors: ['#6366F1', '#15803D', '#F59E0B', '#EF4444'],
      legend: { position: 'top', fontSize: '12px', labels: { colors: chartText.value } },
      grid: { borderColor: chartGrid.value },
      tooltip: { theme: isDark.value ? 'dark' : 'light', y: { formatter: (v: number) => formatCurrency(v) } },
    }
  })

  // Reload finplan when subsidy filter changes
  watch(selectedSubsidyIds, () => { loadFinplan() })

  return {
    finplanGranularity, finplanData,
    finplanDrilldown, openFinplanDrilldown, finplanDrilldownTotal, finplanDrilldownTitle, finplanDrilldownChipColor,
    patchIsLikelyNeeded, finplanNoDeadlineCount, finplanCurrentMonthKpi, goToOrder,
    exportFinplanXlsx, exportFinplanDrilldownXlsx, formatDate,
    loadFinplan, finplanSeries, finplanOptions,
  }
}
