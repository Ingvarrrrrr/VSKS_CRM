<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <!-- Header with breadcrumb -->
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #1e3a5f, #312e81); color: white;">
        <v-btn v-if="path.length > 0" icon="mdi-arrow-left"
          variant="text" color="white" size="small" class="mr-2" @click="goBack" />
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">{{ title }}</div>
          <div class="text-caption mt-1" style="opacity:0.75">{{ breadcrumb }}</div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">
          {{ stageItems.length }} закуп.
        </v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert v-if="!uniformDepth && path.length === 0" type="info"
        variant="tonal" density="compact" class="ma-3 text-caption">
        FEO-структура выбранных субсидий неоднородна — drill доступен внутри каждой ветки отдельно.
      </v-alert>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-circular indeterminate color="primary" size="42" />
        </div>

        <!-- Categories level: show children with aggregated amount -->
        <v-table v-else-if="!isLeafLevel" density="compact">
          <thead>
            <tr>
              <th class="px-4">{{ levelHeader }}</th>
              <th class="text-right px-4">Закупок</th>
              <th class="text-right px-4">Сумма этапа</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in currentRows" :key="row.key"
              style="cursor:pointer" @click="drillInto(row)">
              <td class="px-4 py-2" style="max-width:600px">
                <v-icon icon="mdi-folder-outline" size="16" class="mr-1" color="grey" />
                {{ row.name }}
                <span v-if="row.kind === 'leaf'" class="text-caption text-medium-emphasis ml-1">
                  (последний уровень)
                </span>
              </td>
              <td class="text-right px-4 text-caption">{{ row.count }}</td>
              <td class="text-right px-4 font-weight-medium text-primary">
                {{ fmtMoney(row.amount) }}
              </td>
            </tr>
            <tr v-if="currentRows.length === 0">
              <td colspan="3" class="text-center py-6 text-medium-emphasis">
                Нет данных на этом уровне
              </td>
            </tr>
          </tbody>
        </v-table>

        <!-- Leaf level: show purchases -->
        <v-table v-else density="compact">
          <thead>
            <tr>
              <th class="px-4">№</th>
              <th class="px-4">Предмет</th>
              <th class="text-right px-4">Сумма</th>
              <th class="px-4">Контрагент</th>
              <th class="px-4">Статус</th>
              <th class="px-4">№ договора</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in leafPurchases" :key="p.id"
              style="cursor:pointer" @click="emit('row-click', p.id)">
              <td class="px-4 text-medium-emphasis">{{ p.purchase_number || p.id }}</td>
              <td class="px-4 py-2" style="max-width:300px;white-space:normal;font-size:13px">
                {{ p.subject || p.item_name || '—' }}
              </td>
              <td class="text-right px-4 font-weight-medium text-primary">
                {{ fmtMoney(effectivePrice(p)) }}
              </td>
              <td class="px-4 text-caption text-medium-emphasis">{{ p.contractor_name || '—' }}</td>
              <td class="px-4">
                <v-chip size="x-small" variant="flat" :color="statusColorMap[p.status] || 'grey'">
                  {{ statusLabelMap[p.status] || p.status }}
                </v-chip>
              </td>
              <td class="px-4 text-caption">{{ p.contract_number || '—' }}</td>
            </tr>
            <tr v-if="leafPurchases.length === 0">
              <td colspan="6" class="text-center py-6 text-medium-emphasis">Нет закупок</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-btn color="success" variant="tonal" prepend-icon="mdi-microsoft-excel"
          :loading="xlsxLoading" @click="exportXlsx">
          Скачать Excel
        </v-btn>
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'

interface Props {
  visible: boolean
  title: string
  /** Cumulative set of statuses (e.g. ['ordered','delivered','paid']) */
  stageStatuses: string[]
  /** Purchases ALREADY filtered by current org/year (full list) */
  allPurchases: any[]
  /** Subsidies ids in current dashboard filter (empty = all) */
  subsidyIds: number[]
  /** Subsidies metadata for displaying name */
  subsidies: any[]
  effectivePrice: (p: any) => number
  statusLabelMap?: Record<string, string>
  statusColorMap?: Record<string, string>
}

const props = withDefaults(defineProps<Props>(), {
  statusLabelMap: () => ({}),
  statusColorMap: () => ({}),
})
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'row-click', id: number): void
}>()

// ── State ────────────────────────────────────────────────────────────────────
type PathEntry =
  | { kind: 'subsidy'; subsidyId: number; name: string }
  | { kind: 'node'; subsidyId: number; nodeId: number; name: string }

const path = ref<PathEntry[]>([])
const tree = ref<any[]>([])      // categories from /dashboard/
const loading = ref(false)
const xlsxLoading = ref(false)

watch(() => props.visible, (v) => {
  if (v) {
    path.value = []
    if (tree.value.length === 0) loadTree()
  }
})

async function loadTree() {
  loading.value = true
  try {
    const data = await apiFetch<any>('/dashboard/')
    tree.value = data.categories || []
  } catch {
    tree.value = []
  } finally {
    loading.value = false
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function flatAll(nodes: any[]): any[] {
  const out: any[] = []
  for (const n of nodes) {
    out.push(n)
    if (n.children?.length) out.push(...flatAll(n.children))
  }
  return out
}

function findNode(id: number): any | null {
  return flatAll(tree.value).find(n => n.id === id) ?? null
}

function maxDepth(nodes: any[]): number {
  if (!nodes.length) return 0
  let max = 1
  for (const n of nodes) {
    const d = n.children?.length ? 1 + maxDepth(n.children) : 1
    if (d > max) max = d
  }
  return max
}

const stageItems = computed(() => {
  const ss = new Set(props.stageStatuses)
  const subs = new Set(props.subsidyIds)
  return props.allPurchases.filter(p => {
    if (subs.size > 0 && !subs.has(p.subsidy_id)) return false
    return ss.has(p.status)
  })
})

// Uniform depth check: max FEO depth должна совпадать у всех выбранных субсидий
const uniformDepth = computed(() => {
  const subs = props.subsidyIds.length > 0
    ? props.subsidyIds
    : Array.from(new Set(props.subsidies.map((s: any) => s.id)))
  if (subs.length <= 1) return true
  const depths = subs.map(sid => {
    const roots = tree.value.filter(n => n.subsidy_id === sid)
    return maxDepth(roots)
  })
  return depths.every(d => d === depths[0])
})

const breadcrumb = computed(() => {
  if (path.value.length === 0) return 'Все субсидии'
  return ['Все субсидии', ...path.value.map(p => p.name)].join(' → ')
})

const levelHeader = computed(() => {
  if (path.value.length === 0) return 'Субсидия'
  return 'Категория ФЭО'
})

// ── Current level rows ──────────────────────────────────────────────────────
function nodeAndAllDescendants(node: any): number[] {
  const ids: number[] = [node.id]
  if (node.children?.length) {
    for (const c of node.children) ids.push(...nodeAndAllDescendants(c))
  }
  return ids
}

function aggregatePurchases(catIds: Set<number>): { count: number; amount: number; purchases: any[] } {
  const matching = stageItems.value.filter(p => catIds.has(p.feo_category_id))
  let amount = 0
  for (const p of matching) amount += props.effectivePrice(p)
  return { count: matching.length, amount, purchases: matching }
}

const currentRows = computed(() => {
  if (loading.value) return []

  // Level 0 — subsidies
  if (path.value.length === 0) {
    const subs = props.subsidyIds.length > 0
      ? props.subsidies.filter((s: any) => props.subsidyIds.includes(s.id))
      : props.subsidies

    return subs.map((s: any) => {
      const subTreeIds = new Set(
        flatAll(tree.value.filter(n => n.subsidy_id === s.id)).map(n => n.id)
      )
      // Закупки этой субсидии без feo_category — тоже считаем здесь
      const filteredPurchases = stageItems.value.filter(p =>
        p.subsidy_id === s.id && (subTreeIds.has(p.feo_category_id) || !p.feo_category_id)
      )
      const amount = filteredPurchases.reduce((sum, p) => sum + props.effectivePrice(p), 0)
      const roots = tree.value.filter(n => n.subsidy_id === s.id)
      return {
        key: `s-${s.id}`,
        name: s.shortName || s.name,
        count: filteredPurchases.length,
        amount,
        kind: roots.length === 0 ? 'leaf' : 'subsidy',
        subsidyId: s.id,
      }
    })
  }

  // Inside a subsidy — show its FEO roots
  const last = path.value[path.value.length - 1]
  if (last.kind === 'subsidy') {
    const roots = tree.value.filter(n => n.subsidy_id === last.subsidyId)
    if (roots.length === 0) {
      // No FEO tree — treat as leaf with no children → show purchases
      return []
    }
    return roots.map(n => {
      const ids = new Set(nodeAndAllDescendants(n))
      const agg = aggregatePurchases(ids)
      return {
        key: `n-${n.id}`,
        name: n.name || n.code || `Кат. ${n.id}`,
        count: agg.count,
        amount: agg.amount,
        kind: n.children?.length ? 'node' : 'leaf',
        nodeId: n.id,
        subsidyId: last.subsidyId,
      }
    })
  }

  // Inside a category node — show its children
  const node = findNode(last.nodeId)
  if (!node?.children?.length) return []
  return node.children.map((n: any) => {
    const ids = new Set(nodeAndAllDescendants(n))
    const agg = aggregatePurchases(ids)
    return {
      key: `n-${n.id}`,
      name: n.name || n.code || `Кат. ${n.id}`,
      count: agg.count,
      amount: agg.amount,
      kind: n.children?.length ? 'node' : 'leaf',
      nodeId: n.id,
      subsidyId: last.subsidyId,
    }
  })
})

const isLeafLevel = computed(() => {
  if (path.value.length === 0) return false
  const last = path.value[path.value.length - 1]
  if (last.kind === 'subsidy') {
    const roots = tree.value.filter(n => n.subsidy_id === last.subsidyId)
    return roots.length === 0
  }
  const node = findNode(last.nodeId)
  return !node?.children?.length
})

const leafPurchases = computed(() => {
  const last = path.value[path.value.length - 1]
  if (!last) return []

  if (last.kind === 'subsidy') {
    return stageItems.value.filter(p => p.subsidy_id === last.subsidyId)
  }
  const node = findNode(last.nodeId)
  if (!node) return []
  const ids = new Set(nodeAndAllDescendants(node))
  return stageItems.value.filter(p => ids.has(p.feo_category_id))
})

// ── Navigation ───────────────────────────────────────────────────────────────
function drillInto(row: any) {
  if (path.value.length === 0) {
    path.value.push({ kind: 'subsidy', subsidyId: row.subsidyId, name: row.name })
    return
  }
  // Drill into a node (even if leaf — that opens purchases view)
  path.value.push({ kind: 'node', subsidyId: row.subsidyId, nodeId: row.nodeId, name: row.name })
}

function goBack() {
  path.value.pop()
}

// ── Excel ────────────────────────────────────────────────────────────────────
function fmtMoney(n: number): string {
  if (!n) return '0 ₽'
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} млн ₽`
  if (n >= 1e3) return `${Math.round(n / 1e3)} тыс ₽`
  return `${Math.round(n)} ₽`
}

async function exportXlsx() {
  xlsxLoading.value = true
  try {
    const XLSX = await import('xlsx')
    let rows: any[]
    let sheetName = 'Закупки'
    if (isLeafLevel.value) {
      rows = leafPurchases.value.map(p => ({
        '№': p.purchase_number || p.id,
        'Предмет': p.subject || p.item_name || '',
        'Сумма': props.effectivePrice(p),
        'Контрагент': p.contractor_name || '',
        'Статус': props.statusLabelMap[p.status] || p.status,
        '№ договора': p.contract_number || '',
        'Дата договора': p.contract_date || '',
        'Субсидия': p.subsidy_name || '',
      }))
      sheetName = (path.value[path.value.length - 1]?.name || 'Закупки').slice(0, 31)
    } else {
      rows = currentRows.value.map((r: any) => ({
        [levelHeader.value]: r.name,
        'Закупок': r.count,
        'Сумма этапа': r.amount,
      }))
      sheetName = (path.value[path.value.length - 1]?.name || 'Уровень').slice(0, 31)
    }
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
    const fname = `pipeline_${(props.title || 'drill').replace(/[^a-z0-9_-]/gi, '_').slice(0, 30)}_${new Date().toISOString().slice(0, 10)}.xlsx`
    XLSX.writeFile(wb, fname)
  } catch (e) {
    console.error('xlsx export failed', e)
  } finally {
    xlsxLoading.value = false
  }
}
</script>
