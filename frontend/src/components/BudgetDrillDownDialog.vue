<template>
  <v-dialog v-model="dialog" max-width="1300" scrollable>
    <v-card style="min-height: 560px;">

      <!-- Header -->
      <v-card-title class="d-flex align-center pa-4" style="background: #1e3a5f; color: white; flex-shrink:0">
        <v-btn
          v-if="drillStack.length > 0"
          icon="mdi-arrow-left" variant="text" color="white"
          size="small" class="mr-2" @click="goBack"
        />
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">{{ dialogTitle }}</div>
          <div class="text-caption mt-1" style="opacity:0.7">{{ breadcrumb }}</div>
        </div>
        <v-btn icon="mdi-close" variant="text" color="white" @click="dialog = false" />
      </v-card-title>

      <!-- Summary strip -->
      <div class="summary-strip">
        <div v-for="c in summaryCards" :key="c.key" class="sum-card">
          <div class="sum-label">{{ c.label }}</div>
          <div class="sum-value" :style="{ color: c.color }">{{ fmtMoney(c.value) }}</div>
        </div>
      </div>

      <v-card-text class="pa-4" style="overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-circular indeterminate color="primary" size="48" />
        </div>

        <!-- Leaf purchases table -->
        <template v-else-if="isLeafPurchasesView">
          <div class="text-caption text-medium-emphasis mb-3">
            <v-icon icon="mdi-cart-outline" size="14" class="mr-1" />
            Закупки категории · {{ leafPurchases.length }} шт.
          </div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>№</th>
                <th>Предмет закупки</th>
                <th class="text-right">Сумма</th>
                <th>Контрагент</th>
                <th>Статус</th>
                <th>№ договора</th>
                <th>Дата договора</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="p in leafPurchases" :key="p.id"
                style="cursor:pointer"
                @click="handleLeafPurchaseClick(p.id)"
              >
                <td class="text-medium-emphasis">{{ p.purchase_number || p.id }}</td>
                <td style="max-width:240px;white-space:normal;font-size:13px">{{ p.subject || p.item_name || '—' }}</td>
                <td class="text-right font-weight-medium text-primary">{{ fmtMoney(purchaseEffectivePrice(p)) }}</td>
                <td class="text-caption text-medium-emphasis">{{ p.contractor_name || '—' }}</td>
                <td>
                  <v-chip size="x-small" :color="purchaseStatusColor(p.status)" variant="flat">
                    {{ purchaseStatusLabel(p.status) }}
                  </v-chip>
                </td>
                <td class="text-caption">{{ p.contract_number || '—' }}</td>
                <td class="text-caption">{{ fmtDate(p.contract_date) }}</td>
              </tr>
              <tr v-if="leafPurchases.length === 0">
                <td colspan="7" class="text-center py-6 text-medium-emphasis">Нет закупок в этой категории</td>
              </tr>
            </tbody>
          </v-table>
        </template>

        <div v-else-if="chartItems.length === 0" class="text-center py-12 text-medium-emphasis">
          <v-icon icon="mdi-chart-bar-stacked" size="48" class="mb-3" />
          <div>Нет данных для отображения</div>
        </div>

        <template v-else>
          <div class="text-caption text-medium-emphasis mb-3">
            <v-icon icon="mdi-cursor-pointer" size="14" class="mr-1" />
            {{ hint }}
          </div>

          <apexchart
            type="bar"
            :height="Math.max(280, chartItems.length * 68)"
            :options="chartOptions"
            :series="chartSeries"
          />
        </template>
      </v-card-text>

      <!-- Footer with Excel button -->
      <v-card-actions class="px-4 pb-3" style="border-top: 1px solid var(--crm-border); flex-shrink:0">
        <v-btn
          color="success" variant="tonal" size="small"
          prepend-icon="mdi-microsoft-excel"
          :loading="xlsxLoading"
          @click="exportXlsx"
        >Скачать Excel</v-btn>
        <v-spacer />
        <v-btn variant="text" size="small" @click="dialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useTheme } from 'vuetify'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const theme = useTheme()
const router = useRouter()
const isDark = computed(() => theme.global.name.value === 'dark')
const chartText  = computed(() => isDark.value ? '#E2E8F0' : '#374151')
const chartMuted = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
const chartGrid  = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : '#E2E8F0')

interface ChartItem {
  id: number
  name: string
  budget: number
  planned: number
  contracted: number
  paid: number
  _isSubsidy?: boolean
  _raw?: any
}

interface DrillEntry {
  subsidyId: number | null
  nodeId: number | null
}

const props = defineProps({
  modelValue: Boolean,
  metric: { type: String, default: 'budget' },
  subsidies: { type: Array as () => any[], default: () => [] },
  allPurchases: { type: Array as () => any[], default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const dialog = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ── State ──────────────────────────────────────────────────────────────────────
const drillStack     = ref<DrillEntry[]>([])   // navigation history
const curSubsidyId   = ref<number | null>(null)
const curNodeId      = ref<number | null>(null)
const curLeafNodeId  = ref<number | null>(null)  // set when at leaf-purchases level
const dashTree       = ref<any[]>([])            // dashboard categories roots
const loading        = ref(false)
const xlsxLoading    = ref(false)

// ── Load dashboard tree ─────────────────────────────────────────────────────
async function loadTree() {
  loading.value = true
  try {
    const data = await apiFetch<any>('/dashboard/')
    dashTree.value = data.categories || []
  } catch (e) {
    console.error('drill-down load error', e)
  } finally {
    loading.value = false
  }
}

// ── Flatten helpers ─────────────────────────────────────────────────────────
function flatAll(nodes: any[]): any[] {
  const result: any[] = []
  for (const n of nodes) {
    result.push(n)
    if (n.children?.length) result.push(...flatAll(n.children))
  }
  return result
}

function findNode(id: number): any | null {
  return flatAll(dashTree.value).find(n => n.id === id) ?? null
}

// ── Compute chart items at current drill level ──────────────────────────────
const chartItems = computed((): ChartItem[] => {
  if (drillStack.value.length === 0) {
    // Level 0 — show subsidies
    return (props.subsidies as any[]).map(s => ({
      id: s.id,
      name: s.name,
      budget: s.budget ?? 0,
      planned: s.planned ?? 0,
      contracted: s.contracted ?? 0,
      paid: s.paid ?? 0,
      _isSubsidy: true,
    }))
  }

  if (curNodeId.value === null) {
    // Drilled into a subsidy — show its level-1 FEO roots
    const sid = curSubsidyId.value
    return dashTree.value
      .filter(n => n.subsidy_id === sid)
      .map(nodeToItem)
  }

  // Drilled into a FEO category — show its children
  const node = findNode(curNodeId.value)
  if (!node?.children?.length) return []
  return node.children.map(nodeToItem)
})

function nodeToItem(n: any): ChartItem {
  return {
    id: n.id,
    name: n.name || n.code || `Кат. ${n.id}`,
    budget: 0,
    planned:    n.total_planned    ?? 0,
    contracted: n.total_confirmed  ?? 0,
    paid:       n.total_payment    ?? 0,
    _raw: n,
  }
}

// ── Navigation ──────────────────────────────────────────────────────────────
function handleBarClick(event: any, _ctx: any, config: any) {
  const idx = config?.dataPointIndex ?? -1
  if (idx < 0) return
  const item = chartItems.value[idx]
  if (!item) return

  if (item._isSubsidy) {
    drillStack.value.push({ subsidyId: curSubsidyId.value, nodeId: curNodeId.value })
    curSubsidyId.value = item.id
    curNodeId.value    = null
    if (!dashTree.value.length) loadTree()
    return
  }

  const raw = item._raw
  if (!raw?.children?.length) {
    // leaf node — show purchases of this feo_category_id
    drillStack.value.push({ subsidyId: curSubsidyId.value, nodeId: curNodeId.value })
    curNodeId.value    = raw.id
    curLeafNodeId.value = raw.id
    return
  }
  drillStack.value.push({ subsidyId: curSubsidyId.value, nodeId: curNodeId.value })
  curNodeId.value = raw.id
}

function goBack() {
  const prev = drillStack.value.pop()
  if (!prev) return
  curSubsidyId.value  = prev.subsidyId
  curNodeId.value     = prev.nodeId
  // if we were at leaf level, going back means leaving purchases view
  if (curLeafNodeId.value !== null) {
    curLeafNodeId.value = null
  }
}

// ── Chart config ────────────────────────────────────────────────────────────
// Бюджет=фиолетовый, НМЦД=индиго, Законтрактовано=оранжевый, Оплачено=зелёный
const SERIES_COLORS = ['#8B5CF6', '#6366F1', '#F59E0B', '#22C55E']

const chartSeries = computed(() => {
  const items = chartItems.value
  const hasBudget = items.some(i => i.budget > 0)
  const series: any[] = []
  if (hasBudget) {
    series.push({ name: 'Бюджет', data: items.map(i => Math.round(i.budget)) })
  }
  series.push({ name: 'НМЦД',            data: items.map(i => Math.round(i.planned)) })
  series.push({ name: 'Законтрактовано', data: items.map(i => Math.round(i.contracted)) })
  series.push({ name: 'Оплачено',        data: items.map(i => Math.round(i.paid)) })
  return series
})

const chartOptions = computed(() => ({
  chart: {
    type: 'bar',
    background: 'transparent',
    toolbar: { show: false },
    animations: { speed: 350 },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: { click: handleBarClick },
    selection: { enabled: false },
  },
  colors: SERIES_COLORS,
  plotOptions: {
    bar: {
      horizontal: true,
      barHeight: '55%',
      borderRadius: 3,
      borderRadiusApplication: 'end',
      dataLabels: { position: 'top' },
    },
  },
  dataLabels: {
    enabled: true,
    style: { fontSize: '10px', colors: [chartText.value] },
    formatter: (v: number) => v > 0 ? fmtShort(v) : '',
    offsetX: 6,
  },
  xaxis: {
    categories: chartItems.value.map(i => truncate(i.name, 40)),
    labels: {
      formatter: (v: number) => fmtShort(v),
      style: { fontSize: '11px', colors: chartMuted.value },
    },
  },
  yaxis: {
    labels: { style: { fontSize: '12px', colors: chartText.value } },
  },
  legend: { show: true, position: 'top', fontSize: '12px', labels: { colors: chartText.value } },
  grid:   { borderColor: chartGrid.value },
  tooltip: { theme: isDark.value ? 'dark' : 'light', y: { formatter: (v: number) => v.toLocaleString('ru-RU') + ' ₽' } },
  states: {
    active: { filter: { type: 'darken', value: 0.8 } },
    hover:  { filter: { type: 'lighten', value: 0.1 } },
  },
}))

// ── Summary cards ────────────────────────────────────────────────────────────
const summaryCards = computed(() => {
  const items = chartItems.value
  const tBudget     = items.reduce((s, i) => s + i.budget,     0)
  const tPlanned    = items.reduce((s, i) => s + i.planned,    0)
  const tContracted = items.reduce((s, i) => s + i.contracted, 0)
  const tPaid       = items.reduce((s, i) => s + i.paid,       0)
  const cards: any[] = []
  if (tBudget > 0) {
    cards.push({ key: 'budget',     label: 'Бюджет',          value: tBudget,     color: '#8B5CF6' })
  }
  cards.push(
    { key: 'planned',    label: 'НМЦД',           value: tPlanned,    color: '#6366F1' },
    { key: 'contracted', label: 'Законтрактовано', value: tContracted, color: '#F59E0B' },
    { key: 'paid',       label: 'Оплачено',        value: tPaid,       color: '#22C55E' },
  )
  return cards
})

// ── Breadcrumb / title ───────────────────────────────────────────────────────
const dialogTitle = computed(() => {
  if (drillStack.value.length === 0) return 'Бюджет по субсидиям'
  const sub = (props.subsidies as any[]).find(s => s.id === curSubsidyId.value)
  if (curNodeId.value === null) return sub?.name ?? 'Субсидия'
  return findNode(curNodeId.value)?.name ?? 'Категория'
})

const breadcrumb = computed(() => {
  const parts: string[] = ['Все субсидии']
  if (curSubsidyId.value !== null) {
    const sub = (props.subsidies as any[]).find(s => s.id === curSubsidyId.value)
    if (sub) parts.push(sub.name)
  }
  if (curNodeId.value !== null) {
    const nd = findNode(curNodeId.value)
    if (nd) parts.push(nd.name)
  }
  return parts.join(' → ')
})

const hint = computed(() => {
  if (drillStack.value.length === 0) return 'Нажмите на столбец субсидии для детализации по ФЭО категориям'
  if (isLeafPurchasesView.value) return 'Нажмите на строку для перехода к закупке'
  const hasChildren = chartItems.value.some(i => i._raw?.children?.length > 0)
  return hasChildren
    ? 'Нажмите на столбец категории для перехода на следующий уровень'
    : 'Нажмите на категорию для просмотра закупок'
})

// ── Leaf purchases view ───────────────────────────────────────────────────────
const isLeafPurchasesView = computed(() => curLeafNodeId.value !== null)

const leafPurchases = computed(() => {
  if (curLeafNodeId.value === null) return []
  return (props.allPurchases as any[]).filter(
    (p: any) => p.feo_category_id === curLeafNodeId.value
  )
})

const PURCHASE_STATUS_LABELS: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'В работе', work_in_progress: 'В работе',
  contracted: 'Договор', ordered: 'Заказано', delivered: 'Поставлено', paid: 'Оплачено',
}
const PURCHASE_STATUS_VUETIFY: Record<string, string> = {
  planned: 'grey', confirmed: 'primary', in_progress: 'teal', work_in_progress: 'teal',
  contracted: 'indigo', ordered: 'light-blue', delivered: 'deep-purple', paid: 'success',
  plan_schedule: 'warning',
}

function purchaseStatusLabel(s: string): string { return PURCHASE_STATUS_LABELS[s] || s }
function purchaseStatusColor(s: string): string { return PURCHASE_STATUS_VUETIFY[s] || 'grey' }

function purchaseEffectivePrice(p: any): number {
  const status = p.status
  if (status === 'paid')       return parseFloat(p.payment_amount || 0)
  if (status === 'delivered')  return parseFloat(p.acceptance_doc_amount || 0)
  if (status === 'ordered')    return parseFloat(p.contract_price || p.delivery_payment_amount || 0)
  if (status === 'contracted') {
    const isFramework = p.purchase_contract_type === 'framework_cumulative' ||
                        p.purchase_contract_type === 'framework_with_amount'
    if (isFramework) return parseFloat(p.acceptance_doc_amount || p.delivery_payment_amount || 0)
    return p.purchase_method === 'single'
      ? parseFloat(p.contract_price || 0)
      : parseFloat(p.delivery_payment_amount || 0)
  }
  return parseFloat(p.total_nmck || p.planned_total_price || 0)
}

function handleLeafPurchaseClick(id: number) {
  dialog.value = false
  router.push(`/orders/${id}/edit`)
}

function fmtDate(iso: string): string {
  if (!iso) return '—'
  const parts = iso.split('-')
  if (parts.length !== 3) return iso
  return `${parts[2]}.${parts[1]}.${parts[0]}`
}

// ── Excel export ──────────────────────────────────────────────────────────────
async function exportXlsx() {
  xlsxLoading.value = true
  try {
    const XLSX = await import('xlsx')
    let rows: any[]
    let sheetName: string

    if (isLeafPurchasesView.value) {
      // Export leaf purchases
      rows = leafPurchases.value.map((p: any) => ({
        '№': p.purchase_number || p.id,
        'Предмет закупки': p.subject || p.item_name || '',
        'Сумма': purchaseEffectivePrice(p),
        'Контрагент': p.contractor_name || '',
        'Статус': PURCHASE_STATUS_LABELS[p.status] || p.status,
        '№ договора': p.contract_number || '',
        'Дата договора': fmtDate(p.contract_date),
      }))
      const leafNode = findNode(curLeafNodeId.value!)
      sheetName = (leafNode?.name || 'Категория').slice(0, 31)
    } else {
      // Export categories at current chart level
      rows = chartItems.value.map(i => ({
        'Категория': i.name,
        'НМЦД': Math.round(i.planned),
        'Законтрактовано': Math.round(i.contracted),
        'Оплачено': Math.round(i.paid),
        ...(i.budget > 0 ? { 'Бюджет': Math.round(i.budget) } : {}),
      }))
      sheetName = dialogTitle.value.slice(0, 31)
    }

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
    const fname = `budget_drill_${new Date().toISOString().slice(0, 10)}.xlsx`
    XLSX.writeFile(wb, fname)
  } catch (e: any) {
    console.error('Excel export error', e)
  } finally {
    xlsxLoading.value = false
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtMoney(v: number): string {
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}
function fmtShort(v: number): string {
  if (!v) return ''
  if (Math.abs(v) >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'млрд'
  if (Math.abs(v) >= 1_000_000)     return (v / 1_000_000).toFixed(1) + 'млн'
  if (Math.abs(v) >= 1_000)         return (v / 1_000).toFixed(0) + 'тыс'
  return String(v)
}
function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
watch(() => props.modelValue, (v) => {
  if (v) {
    drillStack.value     = []
    curSubsidyId.value   = null
    curNodeId.value      = null
    curLeafNodeId.value  = null
    loadTree()
  }
})
</script>

<style scoped>
.summary-strip {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--crm-border-strong);
  background: var(--crm-surface-alt);
  flex-shrink: 0;
}
.sum-card {
  flex: 1;
  padding: 10px 16px;
  border-right: 1px solid var(--crm-border-strong);
  min-width: 0;
}
.sum-card:last-child { border-right: none; }
.sum-label { font-size: 11px; color: var(--crm-text-muted); }
.sum-value { font-size: 18px; font-weight: 700; line-height: 1.2; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
