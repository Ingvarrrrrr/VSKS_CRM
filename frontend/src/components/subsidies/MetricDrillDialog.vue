<!-- MetricDrillDialog.vue — план abstract-noodling-pelican.md, п.8: «из чего
     сложилось число» для карточек, расшифровка которых — НЕ список закупок
     одной стадии (StageFeoDrillDialog) и НЕ дерево ФЭО (FeoCardDrillDialog), а
     построчный список другой природы — GET /dashboard/metric-drill (новый
     под-роутер dashboard_metric_drill.py, пишет параллельный исполнитель).
     Новый файл (Правило №5 — по образцу ContractsDrillDialog.vue/
     PaidOverDeliveredDrillDialog.vue). Фронт ничего не считает (Правило №6):
     total/card_total/rows — готовые поля ответа, «Итого» строки = total,
     расхождение с карточкой (|total − card_total| > 0.01) — красная строка,
     без собственной формулы.

     row_type: 'budget' (строка «Бюджет ФЭО», первой, жирным — только у
     balance_marked/balance_confirmed), 'planned_item' (подпись «плановая
     позиция»), 'purchase' (№ закупки — ссылка-переход, как в
     StageFeoDrillDialog/ContractsDrillDialog). Строка-заголовок окна — словами
     владельца (METRIC_TITLES ниже), не internal-имена метрик. -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #1e3a5f, #312e81); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">{{ title }}</div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ rows.length }} {{ rowsWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="ma-3 text-caption">
        Итог списка не сходится с карточкой на {{ formatCurrency(Math.abs(total - cardTotal)) }}
      </v-alert>

      <DrillSearchField v-model="search.query.value" :active="search.isActive.value"
        :found-count="search.foundCount.value" :total-count="search.totalCount.value"
        :found-amount="search.foundAmount.value" />

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка расшифровки…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <div v-else style="overflow-x:auto">
          <v-table density="compact" style="min-width:900px">
            <thead>
              <tr>
                <th class="px-4">№ закупки / позиция</th>
                <th class="px-4">Предмет</th>
                <th class="px-4">Поставщик</th>
                <th class="px-4">Направление ФЭО</th>
                <th class="px-4">Статус</th>
                <th class="text-right px-4">Сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in search.filtered.value" :key="rowKey(r, idx)"
                :class="{ 'metric-drill-row-clickable': r.row_type === 'purchase' && r.purchase_id }"
                @click="r.row_type === 'purchase' && r.purchase_id ? emit('row-click', r.purchase_id) : null">
                <td class="px-4 py-2" :class="{ 'font-weight-bold': r.row_type === 'budget' }">
                  <template v-if="r.row_type === 'budget'">Бюджет ФЭО</template>
                  <template v-else-if="r.row_type === 'planned_item'">
                    <div style="font-size:13px">{{ r.name || '—' }}</div>
                    <div class="text-caption text-medium-emphasis">плановая позиция</div>
                  </template>
                  <template v-else>{{ r.purchase_number || r.purchase_id || '—' }}</template>
                </td>
                <td class="px-4 py-2" style="max-width:260px;white-space:normal;font-size:13px">{{ r.subject || '—' }}</td>
                <td class="px-4 text-caption">{{ r.supplier || r.contractor || '—' }}</td>
                <td class="px-4 text-caption" style="max-width:220px;white-space:normal">{{ r.category_path || '—' }}</td>
                <td class="px-4 text-caption">{{ r.status || '—' }}</td>
                <td class="text-right px-4 font-weight-medium" :class="r.row_type === 'budget' ? 'font-weight-bold' : 'text-primary'">
                  {{ formatCurrency(r.amount) }}
                </td>
              </tr>
              <tr v-if="search.filtered.value.length === 0">
                <td colspan="6" class="text-center py-6 text-medium-emphasis">
                  {{ rows.length === 0 ? 'Нет данных' : 'Ничего не найдено по поиску' }}
                </td>
              </tr>
            </tbody>
            <tfoot v-if="rows.length">
              <tr>
                <td colspan="5" class="px-4 text-right font-weight-medium">Итого</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
              </tr>
              <tr v-if="mismatch">
                <td colspan="5" class="px-4 text-right text-error">не сходится с карточкой на</td>
                <td class="text-right px-4 font-weight-bold text-error">{{ formatCurrency(Math.abs(total - cardTotal)) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
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
import { useDrillSearch } from '@/composables/useDrillSearch'
import { textOfMetricDrillRow } from '@/components/drill/drillRowText'
import DrillSearchField from '@/components/drill/DrillSearchField.vue'
import type { MetricDrillMetric } from '@/composables/subsidies/useCardDrills'

const { mobile } = useDisplay()

interface MetricDrillRow {
  row_type: 'purchase' | 'planned_item' | 'budget' | 'month'
  purchase_id: number | null
  purchase_number: string | number | null
  subject: string | null
  supplier: string | null
  contractor?: string | null
  status: string | null
  subsidy_id: number | null
  subsidy_name: string | null
  category_path: string | null
  amount: number
  items_text?: string | null
  planned_item_id?: number | null
  name?: string | null
  contribution?: number | null
  committed?: number | null
}

const props = withDefaults(defineProps<{
  visible: boolean
  subsidyId: number | null
  metric: MetricDrillMetric
  kind?: 'goods' | 'services' | null
  scope?: 'dashboard' | 'managed'
}>(), {
  kind: null,
  scope: 'managed',
})
const emit = defineEmits<{ (e: 'close'): void; (e: 'row-click', purchaseId: number): void }>()

// Заголовки окна словами владельца (план п.8) — не internal-имена метрик.
const METRIC_TITLES: Record<MetricDrillMetric, string> = {
  monthly_future: 'Ещё уйдёт помесячно до конца года',
  monthly_future_not_started: 'Ещё уйдёт помесячно до конца года',
  not_committed_nice: 'Хотелось бы, можно отказаться — плановые позиции',
  not_committed_likely: 'Скорее всего понадобится — плановые позиции',
  paid_declared: 'Оплачено по отметке — закупки',
  paid_confirmed: 'Подтверждено выпиской — закупки',
  balance_marked: 'Остаток субсидии по отметке',
  balance_confirmed: 'Остаток субсидии по выписке',
  economy: 'Экономия по закупкам',
}
const KIND_SUFFIX: Record<'goods' | 'services', string> = { goods: ' — товары', services: ' — услуги' }
const title = computed(() => METRIC_TITLES[props.metric] + (props.kind ? KIND_SUFFIX[props.kind] : ''))

const loading = ref(false)
const error = ref<string | null>(null)
const rows = ref<MetricDrillRow[]>([])
const total = ref(0)
const cardTotal = ref(0)

const mismatch = computed(() => Math.abs(total.value - cardTotal.value) > 0.01)

const search = useDrillSearch(rows, textOfMetricDrillRow, r => r.amount)

function pluralizeRows(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'строк'
  if (mod10 === 1) return 'строка'
  if (mod10 >= 2 && mod10 <= 4) return 'строки'
  return 'строк'
}
const rowsWord = computed(() => pluralizeRows(rows.value.length))

function rowKey(r: MetricDrillRow, idx: number): string {
  return `${r.row_type}-${r.purchase_id ?? r.planned_item_id ?? idx}-${idx}`
}

async function load() {
  if (!props.subsidyId) {
    rows.value = []
    total.value = 0
    cardTotal.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ metric: props.metric, scope: props.scope, subsidy_ids: String(props.subsidyId) })
    if (props.kind) params.set('kind', props.kind)
    const res = await apiFetch<{ metric: string; total: number; card_total: number; rows: MetricDrillRow[] }>(
      `/dashboard/metric-drill?${params.toString()}`,
    )
    rows.value = res.rows || []
    total.value = res.total || 0
    cardTotal.value = res.card_total || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить расшифровку' })
    rows.value = []
    total.value = 0
    cardTotal.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.metric, props.kind], () => { if (props.visible) { search.reset(); load() } }, { immediate: true })
</script>

<style scoped>
.metric-drill-row-clickable { cursor: pointer; }
.metric-drill-row-clickable:hover { background: rgba(0, 0, 0, 0.04); }
</style>
