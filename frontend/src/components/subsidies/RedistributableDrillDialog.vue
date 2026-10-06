<!-- Доп. задача (владелец, 06.10.2026, после sleepy-fluttering-walrus.md п.1):
     расшифровка строк «Товары»/«Услуги» карточки «Можно перераспределить» по
     клику — список плановых позиций, из которых сложилась сумма. Новый файл
     (Правило №5 — SubsidyMoneyCards.vue/SubsidyKpiCards.vue не дописываются).
     GET /api/dashboard/redistributable-drill (backend/app/routers/
     dashboard_redistributable_drill.py) — фронт ничего не считает, только
     показывает готовые поля (Правило №6): total/card_total/rows[...]. По
     образцу ContractsDrillDialog.vue (тот же api-клиент, describeApiError,
     индикатор загрузки, Excel). -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #0f766e, #134e4a); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">
            Можно перераспределить · {{ kind === 'goods' ? 'товары' : 'услуги' }}
          </div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ rows.length }} {{ rowsWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="ma-3 text-caption">
        Итог списка не совпадает с карточкой: {{ formatCurrency(cardTotal) }}
      </v-alert>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка позиций…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <div v-else style="overflow-x:auto">
          <v-table density="compact" style="min-width:900px">
            <thead>
              <tr>
                <th class="px-4">Позиция плана</th>
                <th class="px-4">Направление ФЭО</th>
                <th class="px-4">Нужность</th>
                <th class="text-right px-4">План</th>
                <th class="text-right px-4">Законтрактовано</th>
                <th class="text-right px-4">Остаток</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.planned_item_id">
                <td class="px-4 py-2" style="max-width:260px; white-space:normal">{{ r.name }}</td>
                <td class="px-4 text-caption category-path-cell" :title="fullPathTooltip(r.category_path)">
                  {{ lastCategorySegment(r.category_path) }}
                </td>
                <td class="px-4 text-caption">{{ needLevelLabel(r) }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.contribution) }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.committed) }}</td>
                <td class="text-right px-4 font-weight-medium" :class="r.raw < -0.5 ? 'text-error' : 'text-primary'">
                  {{ formatCurrency(r.raw) }}
                </td>
              </tr>
              <tr v-if="rows.length === 0">
                <td colspan="6" class="text-center py-6 text-medium-emphasis">Нет позиций с остатком</td>
              </tr>
            </tbody>
            <tfoot v-if="rows.length">
              <tr>
                <td colspan="5" class="px-4 text-right font-weight-medium">Итого:</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
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

interface RedistributableDrillRow {
  planned_item_id: number
  name: string
  feo_category_id: number | null
  category_path: string
  kind: 'goods' | 'services' | 'unspecified'
  need_level: 'nice_to_have' | 'likely'
  contribution: number
  committed: number
  raw: number
  contracted_not_ordered: boolean
  subsidy_id: number
  subsidy_name?: string | null
}

const props = withDefaults(defineProps<{
  visible: boolean
  subsidyId: number | null
  kind: 'goods' | 'services'
  scope?: 'dashboard' | 'managed'
}>(), {
  scope: 'managed',
})
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const xlsxLoading = ref(false)
const rows = ref<RedistributableDrillRow[]>([])
const total = ref(0)
const cardTotal = ref(0)

const mismatch = computed(() => Math.abs(total.value - cardTotal.value) > 0.005)

function pluralizeRows(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'позиций'
  if (mod10 === 1) return 'позиция'
  if (mod10 >= 2 && mod10 <= 4) return 'позиции'
  return 'позиций'
}
const rowsWord = computed(() => pluralizeRows(rows.value.length))

// Координатор, 06.10.2026 (доп. правка после первой приёмки): столбец
// «Направление ФЭО» показывает только последнее (самое глубокое) звено пути
// в одну строку с обрезкой по ширине — полный путь целиком уходит в title
// (всплывающая подсказка браузера). Схлопываем подряд идущие одинаковые
// звенья ТОЛЬКО в подсказке (путь вида «Техническое оснащение › Техническое
// оснащение» — у category_path бэкенда так бывает, когда категория и её
// родитель названы одинаково) — сам category_path (и Excel-экспорт ниже) не
// трогаем, это ТОЛЬКО представление для title.
function lastCategorySegment(path: string): string {
  if (!path) return '—'
  const parts = path.split(' › ')
  return parts[parts.length - 1] || '—'
}
function fullPathTooltip(path: string): string {
  if (!path) return ''
  const parts = path.split(' › ')
  const collapsed: string[] = []
  for (const part of parts) {
    if (collapsed.length === 0 || collapsed[collapsed.length - 1] !== part) collapsed.push(part)
  }
  return collapsed.join(' › ')
}

function needLevelLabel(r: RedistributableDrillRow): string {
  // Договор заключён (дочерний заказ рамочного договора, status='contracted')
  // перевешивает хотелось бы/скорее всего — владелец: отдельная подпись
  // (app.services.redistributable_raw.not_committed_raw_rows).
  if (r.contracted_not_ordered) return 'договор заключён, не заказано'
  return r.need_level === 'nice_to_have' ? 'хотелось бы' : 'скорее всего'
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
    const params = new URLSearchParams({
      scope: props.scope, subsidy_ids: String(props.subsidyId), kind: props.kind,
    })
    const res = await apiFetch<{ total: number; card_total: number; rows: RedistributableDrillRow[] }>(
      `/dashboard/redistributable-drill?${params.toString()}`,
    )
    rows.value = res.rows || []
    total.value = res.total || 0
    cardTotal.value = res.card_total || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить список позиций' })
    rows.value = []
    total.value = 0
    cardTotal.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.kind], () => { if (props.visible) load() }, { immediate: true })

async function exportXlsx() {
  xlsxLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const data = rows.value.map(r => ({
      'Позиция плана': r.name,
      'Направление ФЭО': r.category_path || '',
      'Нужность': needLevelLabel(r),
      'План': r.contribution,
      'Законтрактовано': r.committed,
      'Остаток': r.raw,
    }))
    const ws = XLSX.utils.json_to_sheet(data)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Перераспределить')
    const fname = `redistributable_${props.kind}_${props.subsidyId || 'subsidy'}_${new Date().toISOString().slice(0, 10)}.xlsx`
    XLSX.writeFile(wb, fname)
  } catch (e) {
    console.error('xlsx export failed', e)
  } finally {
    xlsxLoading.value = false
  }
}
</script>

<style scoped>
/* Координатор, 06.10.2026: столбец «Направление ФЭО» — одна строка, только
   последнее звено пути, обрезка по ширине (полный путь — в title). */
.category-path-cell {
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
}
</style>
