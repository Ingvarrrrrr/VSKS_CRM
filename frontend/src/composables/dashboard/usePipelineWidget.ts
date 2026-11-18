// Виджет «Закупки по этапам» (pipeline) + два его drill-down диалога:
// - stageFeoDrillVisible/Title/Statuses → StageFeoDrillDialog (FEO-иерархический drill)
// - statusDrillDialog/Status/Statuses → StatusDrillDialog (плоский список закупок статуса)
// Единый источник истины: этапы берут данные из effectiveWidgets и totalPlanSchedule
// (без расхождений с KPI-карточками, с учётом рамочных договоров и плана ФЭО).
import { ref, computed, type Ref } from 'vue'
import { purchaseEffectivePrice } from './dashboardFormat'
import { STATUS_LABELS, STATUS_COLORS } from './dashboardStatusMaps'
import type { SubsidyRow, WidgetsData } from './useDashboardData'
import { useToast } from '@/composables/useToast'
import { KPI_STAGE_CUMULATIVE_STATUSES } from '@/utils/itemTypeKind'

export interface PipelineStageItem {
  status: string
  label: string
  color: string
  amount: number
  pct: number
}

export function usePipelineWidget(
  allPurchases: Ref<any[]>,
  filteredSubsidies: Ref<SubsidyRow[]>,
  totalBudget: Ref<number>,
  effectiveWidgets: Ref<WidgetsData | null>,
  totalPlanSchedule: Ref<number>,
) {
  const toast = useToast()

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
  const stageFeoDrillTypeKind = ref<'goods' | 'services' | 'unspecified' | null>(null)
  const stageFeoDrillStageKey = ref<string | null>(null)

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

  // Excel export для status drill-down
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
      toast.addToast(e?.payload?.message || e?.message || 'Не удалось сформировать Excel', 'error')
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

  // ── Единый источник истины для воронки этапов ──────────────────────────
  const pipelineStages = computed<PipelineStageItem[]>(() => {
    const budget = totalBudget.value || 1
    const w = effectiveWidgets.value

    const defs: { status: string; label: string; color: string; amount: number }[] = [
      {
        status: 'plan_schedule',
        label: 'План закупок',
        color: '#F59E0B',
        amount: totalPlanSchedule.value,
      },
      {
        status: 'work',
        label: 'Ведётся работа',
        color: '#8B5CF6', // контрастный фиолетовый
        amount: w?.work.amount ?? 0,
      },
      {
        status: 'contracts',
        label: 'Заключён договор',
        color: '#6366F1',
        amount: w?.contracts.amount ?? 0,
      },
      {
        status: 'ordered',
        label: 'Заказано',
        color: '#3B82F6',
        amount: w?.ordered.amount ?? 0,
      },
      {
        status: 'delivered',
        label: 'Поставлено',
        color: '#06B6D4',
        amount: w?.delivered.amount ?? 0,
      },
      {
        status: 'paid',
        label: 'Оплачено',
        color: '#059669',
        amount: w?.paid.amount ?? 0,
      },
    ]

    return defs.map(d => ({
      ...d,
      pct: Math.round((d.amount / budget) * 100),
    }))
  })

  // «Поставлено, не оплачено» = effectiveWidgets.delivered_unpaid
  const deliveredNotPaid = computed(() => {
    const budget = totalBudget.value || 1
    const amount = effectiveWidgets.value?.delivered_unpaid.amount ?? 0
    return {
      amount,
      pct: Math.round((amount / budget) * 100),
    }
  })

  function onPipelineClick(status: string) {
    const statuses = KPI_STAGE_CUMULATIVE_STATUSES[status] || [status]
    const stageLabels: Record<string, string> = {
      plan_schedule: 'План закупок',
      work: 'Ведётся работа',
      contracts: 'Заключён договор',
      ordered: 'Заказано',
      delivered: 'Поставлено',
      paid: 'Оплачено',
      delivered_unpaid: 'Поставлено, не оплачено',
    }
    const label = stageLabels[status] || STATUS_LABELS[status] || status
    stageFeoDrillTypeKind.value = null
    stageFeoDrillStageKey.value = null
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

  // ── Status pie (мёртвый код) ──────────────────
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
    statusDrillStatuses.value = []
    statusDrillStatus.value = status
    statusDrillDialog.value = true
  }

  return {
    statusDrillDialog, statusDrillStatus, statusDrillStatuses, statusDrillPurchases,
    exportStatusDrillXlsx, filteredStatusAmounts,
    stageFeoDrillVisible, stageFeoDrillTitle, stageFeoDrillStatuses, stageFeoDrillTypeKind, stageFeoDrillStageKey,
    pipelineStages, deliveredNotPaid, onPipelineClick, onDeliveredNotPaidClick,
    filteredStatusCounts, statusPieReady, statusPieEntries, statusPieSeries,
    statusPieLabels, statusPieColors, statusPieKey, statusPieForComponent,
    wishesAmountForPie, onPieSliceClick,
  }
}
