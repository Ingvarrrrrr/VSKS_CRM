// Виджет «Закупки по этапам» (pipeline) + два его drill-down диалога:
// - stageFeoDrillVisible/Title/Statuses → StageFeoDrillDialog (FEO-иерархический drill)
// - statusDrillDialog/Status/Statuses → StatusDrillDialog (плоский список закупок статуса)
// Также содержит статус-pie вычисления (filteredStatusCounts..statusPieOptions,
// onPieSliceClick) — ПЕРЕНЕСЕНЫ КАК ЕСТЬ: в исходном DashboardView.vue они уже были
// мёртвым кодом (StatusPieWithWishes импортирован, но нигде не используется в
// шаблоне; ни один из статус-pie computed'ов там тоже не рендерился). Оставлено
// без изменений поведения, отмечено в отчёте о рефакторинге.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref, computed, type Ref } from 'vue'
import { purchaseEffectivePrice } from './dashboardFormat'
import { STATUS_LABELS, STATUS_COLORS } from './dashboardStatusMaps'
import type { SubsidyRow } from './useDashboardData'

// Pipeline stages (purchase lifecycle funnel)
const PIPELINE_ORDER = ['plan_schedule', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']

export function usePipelineWidget(
  allPurchases: Ref<any[]>,
  filteredSubsidies: Ref<SubsidyRow[]>,
  totalBudget: Ref<number>,
) {
  // Status pie drill-down
  const statusDrillDialog = ref(false)
  const statusDrillStatus = ref('')
  // Если задан — drill cumulative (пр. pipeline бар Заказано → ordered+delivered+paid).
  // Если пуст — drill exact по statusDrillStatus (pie chart по статусам).
  const statusDrillStatuses = ref<string[]>([])

  // FEO-иерархический drill для pipeline-этапов
  const stageFeoDrillVisible = ref(false)
  const stageFeoDrillTitle = ref('')
  const stageFeoDrillStatuses = ref<string[]>([])

  const statusDrillPurchases = computed(() => {
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const cumulative = statusDrillStatuses.value
    const exact = statusDrillStatus.value
    return allPurchases.value.filter((p: any) => {
      if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) return false
      if (cumulative.length > 0) return cumulative.includes(p.status)
      return p.status === exact
    })
  })

  // Excel export для status drill-down (клиентский — использует список из computed).
  async function exportStatusDrillXlsx() {
    try {
      const XLSX = await import('xlsx')
      const rows = statusDrillPurchases.value.map((p: any) => ({
        '№': p.purchase_number || p.id,
        'Предмет закупки': p.subject || p.item_name || '',
        'Сумма': purchaseEffectivePrice(p),
        'Субсидия': p.subsidy_name || '',
        'Статус': STATUS_LABELS[p.status] || p.status,
        'Контрагент': p.contractor_name || '',
        '№ договора': p.contract_number || '',
        'Дата договора': p.contract_date || '',
      }))
      const ws = XLSX.utils.json_to_sheet(rows)
      const wb = XLSX.utils.book_new()
      const sheetName = (STATUS_LABELS[statusDrillStatus.value] || statusDrillStatus.value || 'Закупки').slice(0, 31)
      XLSX.utils.book_append_sheet(wb, ws, sheetName)
      const fname = `dashboard_${statusDrillStatus.value}_${new Date().toISOString().slice(0, 10)}.xlsx`
      XLSX.writeFile(wb, fname)
    } catch (e: any) {
      // ДЕФЕКТ (сохранён как есть): showSnack здесь не определена и не импортирована
      // в исходном DashboardView.vue — вызов бросил бы ReferenceError, если бы
      // catch когда-нибудь сработал. Не исправлено намеренно (задача — перенос
      // без изменения поведения), см. отчёт о рефакторинге.
      showSnack(e?.message || 'Не удалось сформировать Excel', 'error')
    }
  }

  // Status amounts for tooltip
  const filteredStatusAmounts = computed(() => {
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const amounts: Record<string, number> = {}
    for (const p of allPurchases.value) {
      if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) continue
      amounts[p.status] = (amounts[p.status] || 0) + purchaseEffectivePrice(p)
    }
    return amounts
  })

  const pipelineStages = computed(() => {
    const budget = totalBudget.value || 1
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const filtered = allPurchases.value.filter((p: any) =>
      subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
    )
    return PIPELINE_ORDER
      .map((status, idx) => {
        const stagesAtOrBeyond = PIPELINE_ORDER.slice(idx)
        const amount = filtered
          .filter((p: any) => stagesAtOrBeyond.includes(p.status))
          .reduce((sum: number, p: any) => sum + purchaseEffectivePrice(p), 0)
        return {
          status,
          label: STATUS_LABELS[status] || status,
          color: STATUS_COLORS[status] || '#94A3B8',
          amount,
          pct: Math.round(amount / budget * 100),
        }
      })
  })

  // «Поставлено, не оплачено» = SUM(delivered) − SUM(paid). Drill открывает status='delivered'.
  const deliveredNotPaid = computed(() => {
    const subsidyIds = filteredSubsidies.value.map((s: any) => s.id)
    const filtered = allPurchases.value.filter((p: any) =>
      subsidyIds.length === 0 || subsidyIds.includes(p.subsidy_id)
    )
    const delivered = filtered.filter((p: any) => p.status === 'delivered')
      .reduce((sum: number, p: any) => sum + purchaseEffectivePrice(p), 0)
    const budget = totalBudget.value || 1
    return {
      amount: delivered,
      pct: Math.round(delivered / budget * 100),
    }
  })

  function onPipelineClick(status: string) {
    // Cumulative: Заказано → ordered+delivered+paid и т.д.
    const idx = PIPELINE_ORDER.indexOf(status)
    const statuses = idx >= 0 ? PIPELINE_ORDER.slice(idx) : [status]
    const label = STATUS_LABELS[status] || status
    // Открываем FEO-иерархический drill (Субсидия → ФЭО 1 → ФЭО 2 → ... → закупки)
    stageFeoDrillTitle.value = `${label} (и далее) — drill по ФЭО`
    stageFeoDrillStatuses.value = statuses
    stageFeoDrillVisible.value = true
  }

  // Точный фильтр для метрики «Поставлено, не оплачено».
  function onDeliveredNotPaidClick() {
    statusDrillStatuses.value = []   // exact mode
    statusDrillStatus.value = 'delivered'
    statusDrillDialog.value = true
  }

  // ── Status pie (мёртвый код, см. заголовок файла) ──────────────────
  const filteredStatusCounts = computed(() => {
    const subsidyIds = filteredSubsidies.value.map(s => s.id)
    const counts: Record<string, number> = {}
    for (const p of allPurchases.value) {
      if (subsidyIds.length > 0 && !subsidyIds.includes(p.subsidy_id)) continue
      counts[p.status] = (counts[p.status] || 0) + 1
    }
    return counts
  })

  const statusPieReady = computed(() =>
    Object.keys(filteredStatusCounts.value).length > 0 &&
    Object.values(filteredStatusCounts.value).some(v => v > 0)
  )

  // Sorted entries so chart is stable
  const statusPieEntries = computed(() => {
    const ORDER = ['planned', 'in_progress', 'work_in_progress', 'contracted', 'delivered', 'paid']
    return Object.entries(filteredStatusCounts.value)
      .filter(([, v]) => v > 0)
      .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
  })

  const statusPieSeries = computed(() => statusPieEntries.value.map(([, v]) => v))
  const statusPieLabels = computed(() => statusPieEntries.value.map(([k]) => STATUS_LABELS[k] || k))
  const statusPieColors = computed(() => statusPieEntries.value.map(([k]) => STATUS_COLORS[k] || '#94A3B8'))
  const statusPieKey    = computed(() => statusPieEntries.value.map(e => e[0]).join('-'))

  // For custom StatusPieWithWishes component
  const statusPieForComponent = computed(() =>
    statusPieEntries.value
      .filter(([k]) => k !== 'wishes')
      .map(([k, v]) => ({
        status: k,
        count: v,
        color: STATUS_COLORS[k] || '#94A3B8',
        label: STATUS_LABELS[k] || k,
      }))
  )
  const wishesAmountForPie = computed(() => filteredStatusAmounts.value['wishes'] || 0)
  function onPieSliceClick(status: string) {
    statusDrillStatuses.value = []   // exact mode
    statusDrillStatus.value = status
    statusDrillDialog.value = true
  }

  return {
    statusDrillDialog, statusDrillStatus, statusDrillStatuses, statusDrillPurchases,
    exportStatusDrillXlsx, filteredStatusAmounts,
    stageFeoDrillVisible, stageFeoDrillTitle, stageFeoDrillStatuses,
    pipelineStages, deliveredNotPaid, onPipelineClick, onDeliveredNotPaidClick,
    // мёртвый код (см. заголовок)
    filteredStatusCounts, statusPieReady, statusPieEntries, statusPieSeries,
    statusPieLabels, statusPieColors, statusPieKey, statusPieForComponent,
    wishesAmountForPie, onPieSliceClick,
  }
}
