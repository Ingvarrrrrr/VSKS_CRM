<template>
  <div class="d-flex flex-wrap ga-2 mb-3 align-center">
    <v-select
      v-model="statusFilter" :items="statusFilterOptions" label="Статус" variant="outlined" density="compact"
      clearable style="max-width:200px" hide-details />
    <v-checkbox v-model="onlyNeedsDecision" label="Нужно решение" density="compact" hide-details />
    <v-checkbox v-model="onlyWarnings" label="Предупреждения" density="compact" hide-details />
    <v-checkbox v-model="showSkipped" label="Показывать пропущенные" density="compact" hide-details />
    <v-spacer />
    <v-switch
      v-model="factImport.decisions.include_payroll" label="Включить ФОТ" color="teal"
      density="compact" hide-details @update:model-value="onIncludePayrollChange" />
  </div>

  <v-alert v-if="needsContractCount > 0" type="warning" variant="tonal" density="compact" class="mb-2">
    В {{ needsContractCount }} строках заполнено «Законтрактовано», но статус «В работе» — отметьте
    галочкой, если договор уже подписан. Пример: статус «на стадии заключения договора», законтрактовано
    = весь план — отмечена → закупка «Заключён» на эту сумму, не отмечена → «В работе» без суммы договора.
    <v-btn size="x-small" variant="tonal" class="ml-2" @click="onMarkAllContracts">Отметить все</v-btn>
  </v-alert>
  <v-alert v-if="needsStatusCount > 0" type="error" variant="tonal" density="compact" class="mb-2">
    В {{ needsStatusCount }} строках статус не распознан — выберите его в колонке «Статус».
  </v-alert>

  <!-- 🔵 правка 3: оверлей на серию кликов (debounce ~500мс, см.
       queuePreviewRefresh в useFactImport.ts) — таблица остаётся видимой и
       кликабельной, не мигает полным factImport.loading на каждую галочку. -->
  <div class="fisr-table-wrap">
    <div v-if="factImport.previewRefreshing" class="fisr-overlay">
      <v-progress-circular indeterminate size="28" color="teal" />
    </div>
    <v-table density="compact">
      <thead>
        <tr>
          <th>Стр.</th><th>Плановая позиция</th><th>Статус</th>
          <th>План</th><th>Договор</th><th>Оплачено</th><th>Поставщик</th>
          <th>Сопоставление</th><th>Превышение</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in filteredRows" :key="r.row"
          :class="{ 'fisr-row--decision': r.needs_contract_decision, 'fisr-row--needs-status': r.needs_status, 'fisr-row--skip': r.skip }">
          <td>{{ r.row }}</td>
          <td>
            <div class="text-caption text-medium-emphasis">{{ r.path.join(' › ') }}</div>
            <div>{{ r.name }}</div>
            <div v-if="r.warnings?.length" class="text-caption text-warning">
              <v-icon icon="mdi-alert-outline" size="12" /> {{ r.warnings.join('; ') }}
            </div>
          </td>
          <td>
            <!-- Ровно 6 статусов GALA — список ТОЛЬКО с бэкенда
                 (preview.statuses), свой справочник фронт не хранит. -->
            <v-select
              :model-value="rowStatusCode(r)"
              :items="statusSelectOptions"
              density="compact" variant="outlined" hide-details style="min-width:170px"
              :color="r.needs_status ? 'error' : undefined"
              @update:model-value="v => onSetRowStatus(r.row, v)"
            />
            <v-tooltip v-if="statusNormalizedHint(r)" location="top">
              <template #activator="{ props: hintProps }">
                <v-chip v-bind="hintProps" size="x-small" color="blue-grey" variant="tonal" class="mt-1">
                  приведён
                </v-chip>
              </template>
              <span>{{ statusNormalizedHint(r) }}</span>
            </v-tooltip>
          </td>
          <td>{{ fmt(r.plan.amount) }}</td>
          <td>{{ fmt(r.fact.amount ?? r.contracted) }}</td>
          <td>{{ fmt(r.paid) }}</td>
          <td>{{ r.supplier || '—' }}</td>
          <td>
            <v-chip v-if="r.match.state === 'found'" size="x-small" color="success" variant="tonal">
              <v-icon icon="mdi-check" size="12" /> найдено
            </v-chip>
            <template v-else-if="r.match.state === 'already_purchased'">
              <v-chip size="x-small" color="grey" variant="tonal">уже закуплено</v-chip>
            </template>
            <template v-else>
              <v-chip size="x-small" :color="r.match.state === 'ambiguous' ? 'warning' : 'error'" variant="tonal" class="mb-1">
                {{ r.match.state === 'ambiguous' ? 'неоднозначно' : 'не найдено' }}
              </v-chip>
              <div class="d-flex flex-column ga-1">
                <v-btn v-for="c in r.match.candidates.slice(0, 3)" :key="c.id" size="x-small" variant="outlined"
                  @click="onSetPlannedItem(r.row, c.id)">
                  {{ c.name }} ({{ fmt(c.amount) }})
                </v-btn>
                <v-btn size="x-small" variant="text" color="primary" @click="openPicker(r)">Выбрать/создать…</v-btn>
              </div>
            </template>
          </td>
          <td>
            <v-checkbox v-if="r.needs_contract_decision"
              :model-value="isContractConfirmed(r.row)" label="Договор заключён" density="compact" hide-details
              @update:model-value="v => onContractConfirmed(r.row, !!v)" />
            <v-select v-if="isOverPlan(r)"
              :model-value="overPlanChoice(r.row)" :items="overPlanOptions" density="compact" hide-details
              variant="outlined" style="max-width:180px"
              @update:model-value="v => onOverPlanChoice(r.row, v)" />
          </td>
          <td>
            <v-checkbox :model-value="r.skip" density="compact" hide-details label="Пропустить"
              @update:model-value="v => onRowSkip(r.row, !!v)" />
          </td>
        </tr>
      </tbody>
    </v-table>
  </div>

  <FactImportRowPlanPicker v-model="pickerOpen" :row="pickerRow" :subsidy-id="subsidyId" @update:model-value="onPickerClose" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFactImport, type FactImportRow, type FactImportOverPlanChoice } from '@/composables/subsidies/useFactImport'
import FactImportRowPlanPicker from './FactImportRowPlanPicker.vue'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{ subsidyId: number | null }>()
const subsidyId = computed(() => props.subsidyId)

const {
  factImport, visibleRows, loadPreview, queuePreviewRefresh,
  setRowSkip, setRowPlannedItem, setContractConfirmed, markAllContractsConfirmed, setOverPlanChoice,
  setRowStatus, statusNormalizedHint,
} = useFactImport()

const statusFilter = ref<string | null>(null)
const onlyNeedsDecision = ref(false)
const onlyWarnings = ref(false)
const showSkipped = ref(true)

// 🔵 правка 3: статусы — ровно 6 из preview.statuses (код→подпись с бэка),
// не собственный список фронта (ПРАВИЛО №6).
const statusSelectOptions = computed(() =>
  (factImport.preview?.statuses || []).map(s => ({ title: s.label, value: s.code })))
const statusFilterOptions = computed(() => statusSelectOptions.value)

function rowStatusCode(r: FactImportRow): string {
  return factImport.decisions.row_overrides[String(r.row)]?.status ?? r.status
}

const filteredRows = computed(() => visibleRows.value.filter(r => {
  if (statusFilter.value && rowStatusCode(r) !== statusFilter.value) return false
  // «Нужно решение» — статус не распознан (needs_status) ИЛИ нужно решить
  // договор/превышение/сопоставление; найденная и не спорная строка скрыта.
  if (onlyNeedsDecision.value) {
    const needsAny = r.needs_status || r.needs_contract_decision || isOverPlan(r) || r.match.state !== 'found'
    if (!needsAny) return false
  }
  if (onlyWarnings.value && !(r.warnings?.length)) return false
  if (!showSkipped.value && r.skip) return false
  return true
}))

const needsContractCount = computed(() => visibleRows.value.filter(r => r.needs_contract_decision).length)
const needsStatusCount = computed(() => visibleRows.value.filter(r => r.needs_status).length)

// Решения по строке (пропуск/галочка договора/превышение/статус) меняют то,
// что покажет сервер (сумма группы, needs_contract_decision и т.п.) —
// каждое решение планирует повторный предпросмотр ЧЕРЕЗ ДЕБАУНС (🔵 правка 3,
// владелец: «серия галочек не должна слать файл на каждый клик») —
// queuePreviewRefresh схлопывает быстрые клики в один запрос ~500мс после
// последнего. Открытие/закрытие диалога выбора плана (пикер) — отдельное
// редкое действие, там оставлен немедленный loadPreview().
function onRowSkip(row: number, skip: boolean) { setRowSkip(row, skip); queuePreviewRefresh() }
function onSetPlannedItem(row: number, id: number) { setRowPlannedItem(row, id); queuePreviewRefresh() }
function onContractConfirmed(row: number, v: boolean) { setContractConfirmed(row, v); queuePreviewRefresh() }
function onOverPlanChoice(row: number, v: FactImportOverPlanChoice) { setOverPlanChoice(row, v); queuePreviewRefresh() }
function onMarkAllContracts() { markAllContractsConfirmed(); queuePreviewRefresh() }
function onSetRowStatus(row: number, code: string) { setRowStatus(row, code); queuePreviewRefresh() }

function isContractConfirmed(row: number): boolean {
  return factImport.decisions.contract_confirmed_rows.includes(row)
}

function isOverPlan(r: FactImportRow): boolean {
  const fact = r.fact.amount ?? r.contracted ?? 0
  return !!(r.plan.amount != null && fact > r.plan.amount)
}
const overPlanOptions: { title: string; value: FactImportOverPlanChoice }[] = [
  { title: 'Оставить с пометкой', value: 'keep_over' },
  { title: 'Урезать до плана', value: 'trim' },
  { title: 'Пропустить', value: 'skip' },
]
function overPlanChoice(row: number): FactImportOverPlanChoice {
  return factImport.decisions.over_plan[String(row)] || 'keep_over'
}

// ПРАВИЛО №6: формат суммы — общий хелпер, не своя копия Intl.NumberFormat.
function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

const pickerOpen = ref(false)
const pickerRow = ref<FactImportRow | null>(null)
function openPicker(r: FactImportRow) {
  pickerRow.value = r
  pickerOpen.value = true
}
function onPickerClose(open: boolean) {
  if (!open) void loadPreview()
}

function onIncludePayrollChange() {
  queuePreviewRefresh()
}
</script>

<style scoped>
.fisr-table-wrap { position: relative; max-height: 50vh; overflow: auto; border: 1px solid #eee; border-radius: 6px; }
.fisr-overlay {
  position: absolute;
  inset: 0;
  display: flex; justify-content: center; align-items: center;
  background: rgba(255,255,255,0.55);
  z-index: 2;
}
.fisr-row--decision { background: #fff8e1; }
.fisr-row--needs-status { background: #ffebee; }
.fisr-row--skip { opacity: 0.5; }
</style>
