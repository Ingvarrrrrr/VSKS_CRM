<!-- MonthlyFutureTreeDialog.vue — план abstract-noodling-pelican.md, п.8:
     «Ещё уйдёт помесячно до конца года» (карточки «Заключено договоров» и
     «Можно перераспределить») — дерево договор → его помесячные платежи до
     конца года, ВСЕГДА раскрытое целиком (владелец: «сразу раскрытое
     дерево»). Источник — GET /dashboard/metric-drill?metric=monthly_future|
     monthly_future_not_started (новый под-роутер dashboard_metric_drill.py,
     backend/app/services/monthly_future_payments.py — ОДНО место расчёта
     месяца/суммы платежа, Правило №6). Строки ответа — плоский список
     {contract_id, contract_number, contractor, parent_purchase_id,
     parent_subject, month, amount, source}, дерево строится ГРУППИРОВКОЙ уже
     готовых сумм по contract_id (не вторая формула, см. докстринг файла). -->
<template>
  <v-dialog :model-value="visible" max-width="900" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #1e3a5f, #312e81); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">Ещё уйдёт помесячно до конца года</div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ contracts.length }} {{ contractsWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="ma-3 text-caption">
        Итог дерева не сходится с карточкой на {{ formatCurrency(Math.abs(total - cardTotal)) }}
      </v-alert>

      <div class="drill-search">
        <v-text-field v-model="query" density="compact" variant="outlined" hide-details clearable
          prepend-inner-icon="mdi-magnify" label="Поиск…" class="drill-search__field" />
        <div v-if="searchActive" class="text-caption drill-search__summary">
          <template v-if="foundLeaves > 0">Найдено {{ foundLeaves }} из {{ totalLeaves }} · на сумму {{ formatCurrency(foundAmount) }}</template>
          <template v-else>ничего не найдено</template>
        </div>
      </div>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка графика платежей…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <v-alert v-else-if="filteredContracts.length === 0" type="info" variant="tonal" density="compact" class="ma-3">
          {{ contracts.length === 0 ? 'Нет платежей, которые ещё не начались' : 'Ничего не найдено по поиску' }}
        </v-alert>
        <v-list v-else density="compact">
          <template v-for="c in filteredContracts" :key="c.key">
            <v-list-subheader class="monthly-future-contract">
              <span class="font-weight-medium">Договор № {{ c.number || 'без номера' }}</span>
              <span v-if="c.contractor" class="text-caption text-medium-emphasis ml-2">{{ c.contractor }}</span>
              <span v-if="c.parent_subject && !(c.contractor && c.parent_subject.includes(c.contractor))" class="text-caption text-medium-emphasis ml-2">{{ c.parent_subject }}</span>
              <span class="ml-auto font-weight-bold text-primary">{{ formatCurrency(c.amount) }}</span>
            </v-list-subheader>
            <v-list-item v-for="m in c.months" :key="m.key" density="compact" class="monthly-future-month">
              <div class="d-flex align-center" style="width:100%">
                <span>{{ formatMonthLabel(m.month) }}</span>
                <span v-if="m.order_number" class="text-caption text-medium-emphasis ml-2">№ заказа {{ m.order_number }}</span>
                <span class="ml-auto font-weight-medium">{{ formatCurrency(m.amount) }}</span>
              </div>
            </v-list-item>
          </template>
        </v-list>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <div v-if="contracts.length" class="text-body-2 font-weight-medium">Итого: {{ formatCurrency(total) }}</div>
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { formatCurrency } from '@/composables/subsidies/format'
import { filterTree } from '@/composables/useDrillSearch'
import { searchWords } from '@/utils/textSearch'
import { textOfMonthlyFutureNode } from '@/components/drill/drillRowText'

const { mobile } = useDisplay()

interface MonthlyFutureRow {
  row_type: string
  contract_id: number | null
  contract_number: string | number | null
  contractor: string | null
  parent_purchase_id: number | null
  parent_subject: string | null
  month: string
  amount: number
  source?: string | null
  order_number?: string | number | null
  purchase_number?: string | number | null
  orders?: { purchase_number?: string | number | null }[]
}
interface MonthNode { key: string; month: string; amount: number; order_number: string | number | null }
interface ContractNode { key: string; contract_id: number | null; number: string | number | null; contractor: string | null; parent_subject: string | null; amount: number; months: MonthNode[] }

const props = defineProps<{
  visible: boolean
  subsidyId: number | null
  metric: 'monthly_future' | 'monthly_future_not_started'
  scope?: 'dashboard' | 'managed'
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const contracts = ref<ContractNode[]>([])
const total = ref(0)
const cardTotal = ref(0)

const mismatch = computed(() => Math.abs(total.value - cardTotal.value) > 0.01)

function pluralizeContracts(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'договоров'
  if (mod10 === 1) return 'договор'
  if (mod10 >= 2 && mod10 <= 4) return 'договора'
  return 'договоров'
}
const contractsWord = computed(() => pluralizeContracts(contracts.value.length))

function formatMonthLabel(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
}

function buildTree(rows: MonthlyFutureRow[]): ContractNode[] {
  const order: string[] = []
  const byKey = new Map<string, ContractNode>()
  // monthly_future отдаёт строки 'month' (заказ/платёж), monthly_future_not_started —
  // 'planned_item' (сумма строки 4 «Можно перераспределить» = Σ плановых позиций,
  // покрытых неначатыми заказами) с теми же contract_*/month — в дерево идут обе.
  rows.forEach((r, idx) => {
    if (r.row_type && r.row_type !== 'month' && r.row_type !== 'planned_item') return
    const key = String(r.contract_id ?? r.parent_purchase_id ?? r.contract_number ?? 'unknown')
    if (!byKey.has(key)) {
      byKey.set(key, {
        key: 'c-' + key, contract_id: r.contract_id, number: r.contract_number,
        contractor: r.contractor, parent_subject: r.parent_subject, amount: 0, months: [],
      })
      order.push(key)
    }
    const node = byKey.get(key)!
    node.amount += r.amount || 0
    const orderNumber = r.order_number ?? r.purchase_number ?? r.orders?.[0]?.purchase_number ?? null
    node.months.push({ key: 'c-' + key + '-m-' + r.month + '-' + idx, month: r.month, amount: r.amount || 0, order_number: orderNumber })
  })
  for (const c of byKey.values()) c.months.sort((a, b) => (a.month || '').localeCompare(b.month || ''))
  return order.map(k => byKey.get(k)!)
}

// ── Поиск (владелец, 15.10.2026) — то же дерево, фильтруется filterTree.ts
// (Правило №6, один фильтр дерева на проект), дерево ВСЕГДА раскрыто целиком
// (владелец: «сразу раскрытое дерево»), поэтому результат фильтра рендерится
// без отдельного Set развёрнутых ключей.
const query = ref('')
const searchWordsRef = computed(() => searchWords(query.value))
const searchActive = computed(() => searchWordsRef.value.length > 0)

interface TreeNode { key: string; month?: string; order_number?: string | number | null; children: TreeNode[] }
function toGenericTree(cs: ContractNode[]): TreeNode[] {
  return cs.map(c => ({
    key: c.key, contract_number: c.number, contractor: c.contractor, parent_subject: c.parent_subject, amount: c.amount,
    children: c.months.map(m => ({ key: m.key, month: m.month, order_number: m.order_number, amount: m.amount, children: [] })),
  } as any))
}

const filteredContracts = computed<ContractNode[]>(() => {
  if (!searchActive.value) return contracts.value
  const generic = toGenericTree(contracts.value)
  const { nodes } = filterTree(generic, n => (n as any).children, n => (n as any).key, textOfMonthlyFutureNode, query.value)
  return nodes.map(fn => {
    const n = fn.node as any
    return {
      key: n.key, contract_id: null, number: n.contract_number, contractor: n.contractor, parent_subject: n.parent_subject,
      amount: fn.children.reduce((s, c) => s + ((c.node as any).amount || 0), 0),
      months: fn.children.map(c => ({ key: (c.node as any).key, month: (c.node as any).month, amount: (c.node as any).amount, order_number: (c.node as any).order_number })),
    } as ContractNode
  })
})

const totalLeaves = computed(() => contracts.value.reduce((s, c) => s + c.months.length, 0))
const foundLeaves = computed(() => filteredContracts.value.reduce((s, c) => s + c.months.length, 0))
const foundAmount = computed(() => filteredContracts.value.reduce((s, c) => s + c.amount, 0))

async function load() {
  if (!props.subsidyId) {
    contracts.value = []
    total.value = 0
    cardTotal.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ metric: props.metric, scope: props.scope || 'managed', subsidy_ids: String(props.subsidyId) })
    const res = await apiFetch<{ metric: string; total: number; card_total: number; rows: MonthlyFutureRow[] }>(
      `/dashboard/metric-drill?${params.toString()}`,
    )
    contracts.value = buildTree(res.rows || [])
    total.value = res.total || 0
    cardTotal.value = res.card_total || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить график платежей' })
    contracts.value = []
    total.value = 0
    cardTotal.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.metric], () => { if (props.visible) { query.value = ''; load() } }, { immediate: true })
</script>

<style scoped>
.drill-search { padding: 8px 16px 0; }
.drill-search__field { max-width: 360px; }
.drill-search__summary { margin-top: 4px; color: rgba(0, 0, 0, 0.6); }
.monthly-future-contract { display: flex; align-items: center; background: rgba(30, 58, 95, 0.05); }
.monthly-future-month { padding-left: 32px; }
</style>
