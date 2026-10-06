<!-- Квик-план 06.10.2026 (sleepy-fluttering-walrus.md, п.2): расшифровка карточки
     «Заключено договоров» по клику — список ДОГОВОРОВ (не позиций закупок, как
     у StageFeoDrillDialog в режиме typeKind). Новый файл (Правило №5 —
     SubsidyKpiCards.vue уже > 500 строк). GET /api/dashboard/contracts-drill
     (backend/app/routers/dashboard_contracts_drill.py, уже готов) — фронт
     ничего не считает, только показывает готовые поля (Правило №6): total/
     card_total/contracts_count/rows[contract_amount/ordered_amount/remaining].
     card_total — то же число, что и карточка (contracted_total_by_subsidy) —
     жёлтое предупреждение при расхождении, сам фронт ничего не пересчитывает. -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #1e3a5f, #312e81); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">Заключено договоров</div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ contractsCount }} {{ contractsWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="ma-3 text-caption">
        Итог списка не совпадает с карточкой: {{ formatCurrency(cardTotal) }}
      </v-alert>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка договоров…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <div v-else style="overflow-x:auto">
          <v-table density="compact" style="min-width:860px">
            <thead>
              <tr>
                <th class="px-4">Договор</th>
                <th class="px-4">Контрагент</th>
                <th class="px-4">Тип</th>
                <th class="text-right px-4">Сумма договора</th>
                <th class="text-right px-4">Заказано</th>
                <th class="text-right px-4">Остаток</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.contract_id ?? 'u-' + r.subject + r.contract_amount">
                <td class="px-4 py-2" style="max-width:280px">
                  <div v-if="r.number" style="font-size:13px">{{ r.number }}</div>
                  <div v-if="r.subject && r.subject !== r.number" class="text-caption text-medium-emphasis" style="white-space:normal">{{ r.subject }}</div>
                </td>
                <td class="px-4 text-caption">{{ r.contractor_name || '—' }}</td>
                <td class="px-4 text-caption">{{ r.contract_type_label }}</td>
                <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(r.contract_amount) }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.ordered_amount) }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.remaining) }}</td>
              </tr>
              <tr v-if="rows.length === 0">
                <td colspan="6" class="text-center py-6 text-medium-emphasis">Нет договоров</td>
              </tr>
            </tbody>
            <tfoot v-if="rows.length">
              <tr>
                <td colspan="3" class="px-4 text-right font-weight-medium">Итого: {{ contractsCount }} {{ contractsWord }}</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
                <td class="px-4" />
                <td class="px-4" />
              </tr>
            </tfoot>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-btn color="success" variant="tonal" prepend-icon="mdi-microsoft-excel"
          :loading="xlsxLoading" :disabled="loading || !rows.length" @click="exportXlsx">
          Скачать Excel
        </v-btn>
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

const { mobile } = useDisplay()

interface ContractDrillRow {
  contract_id: number | null
  number: string | number | null
  subject: string | null
  contract_type: string | null
  contract_type_label: string
  contractor_id: number | null
  contractor_name: string | null
  subsidy_id: number
  subsidy_name?: string | null
  contract_amount: number
  ordered_amount: number
  remaining: number
}

const props = withDefaults(defineProps<{
  visible: boolean
  subsidyId: number | null
  scope?: 'dashboard' | 'managed'
}>(), {
  scope: 'managed',
})
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const xlsxLoading = ref(false)
const rows = ref<ContractDrillRow[]>([])
const total = ref(0)
const cardTotal = ref(0)
const contractsCount = ref(0)

const mismatch = computed(() => Math.abs(total.value - cardTotal.value) > 0.005)

// Склонение «договор/договора/договоров» (11-14 — всегда «договоров»,
// иначе по последней цифре: 1 → договор, 2-4 → договора, 0/5-9 → договоров).
function pluralizeContracts(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'договоров'
  if (mod10 === 1) return 'договор'
  if (mod10 >= 2 && mod10 <= 4) return 'договора'
  return 'договоров'
}
const contractsWord = computed(() => pluralizeContracts(contractsCount.value))

async function load() {
  if (!props.subsidyId) {
    rows.value = []
    total.value = 0
    cardTotal.value = 0
    contractsCount.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ scope: props.scope, subsidy_ids: String(props.subsidyId) })
    const res = await apiFetch<{ total: number; card_total: number; contracts_count: number; rows: ContractDrillRow[] }>(
      `/dashboard/contracts-drill?${params.toString()}`,
    )
    rows.value = res.rows || []
    total.value = res.total || 0
    cardTotal.value = res.card_total || 0
    contractsCount.value = res.contracts_count || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить список договоров' })
    rows.value = []
    total.value = 0
    cardTotal.value = 0
    contractsCount.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId], () => { if (props.visible) load() }, { immediate: true })

async function exportXlsx() {
  xlsxLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const data = rows.value.map(r => ({
      'Договор': r.number || '',
      'Предмет': r.subject || '',
      'Контрагент': r.contractor_name || '',
      'Тип': r.contract_type_label,
      'Сумма договора': r.contract_amount,
      'Заказано': r.ordered_amount,
      'Остаток': r.remaining,
    }))
    const ws = XLSX.utils.json_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Договоры')
    const fname = `contracts_${props.subsidyId || 'subsidy'}_${new Date().toISOString().slice(0, 10)}.xlsx`
    XLSX.writeFile(wb, fname)
  } catch (e) {
    console.error('xlsx export failed', e)
  } finally {
    xlsxLoading.value = false
  }
}
</script>
