<template>
  <div class="d-flex flex-wrap ga-2 mb-3 align-center">
    <v-select
      v-model="statusFilter" :items="statusFilterOptions" label="Статус" variant="outlined" density="compact"
      clearable style="min-width:200px" hide-details />
    <v-checkbox v-model="onlyNeedsDecision" label="Нужно решение" density="compact" hide-details />
    <v-checkbox v-model="onlyWarnings" label="Предупреждения" density="compact" hide-details />
    <v-checkbox v-model="showSkipped" label="Показывать пропущенные" density="compact" hide-details />
    <v-chip v-if="isolatedRows" size="small" variant="tonal" color="primary" closable @click:close="isolatedRows = null">
      показаны только отобранные строки
    </v-chip>
    <v-spacer />
    <v-switch
      v-model="factImport.decisions.include_payroll" label="Включить ФОТ" color="teal"
      density="compact" hide-details @update:model-value="onIncludePayrollChange" />
  </div>

  <!-- Сводные предупреждения мастера (жалоба владельца 05.10.2026: не говорят,
       какие строки, нельзя кликнуть, неверное склонение «в 1 строках») — текст
       через rowsInPhrase (ПРАВИЛО №6, utils/pluralize.ts), под текстом чипы
       строк (RowWarningChips.vue, клик → useRowJump → секция «переход к
       строке» ниже). -->
  <v-alert v-if="contractRows.length" type="warning" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(contractRows.length) }} заполнено «Законтрактовано», но статус «В работе» — отметьте
    галочкой, если договор уже подписан. Пример: статус «на стадии заключения договора», законтрактовано
    = весь план — отмечена → закупка «Заключён» на эту сумму, не отмечена → «В работе» без суммы договора.
    <v-btn size="x-small" variant="tonal" class="ml-2" @click="onMarkAllContracts">Отметить все</v-btn>
    <RowWarningChips :rows="contractRows" show-isolate-button :isolated="isIsolatedTo(contractRows)"
      @update:isolated="v => setIsolated(v, contractRows)" />
  </v-alert>
  <v-alert v-if="statusRows.length" type="error" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(statusRows.length) }} статус не распознан — выберите его в колонке «Статус».
    <RowWarningChips :rows="statusRows" show-isolate-button :isolated="isIsolatedTo(statusRows)"
      @update:isolated="v => setIsolated(v, statusRows)" />
  </v-alert>
  <v-alert v-if="notFoundRows.length" type="warning" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(notFoundRows.length) }} плановая позиция не найдена или сопоставление неоднозначно —
    выберите её в колонке «Сопоставление».
    <RowWarningChips :rows="notFoundRows" show-isolate-button :isolated="isIsolatedTo(notFoundRows)"
      @update:isolated="v => setIsolated(v, notFoundRows)" />
  </v-alert>
  <v-alert v-if="overPlanRows.length" type="warning" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(overPlanRows.length) }} факт превышает план — выберите решение в колонке «Превышение».
    <RowWarningChips :rows="overPlanRows" show-isolate-button :isolated="isIsolatedTo(overPlanRows)"
      @update:isolated="v => setIsolated(v, overPlanRows)" />
  </v-alert>
  <v-alert v-if="alreadyPurchasedRows.length" type="info" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(alreadyPurchasedRows.length) }} позиция уже закуплена ранее — проверьте, что закупка не задвоится.
    <RowWarningChips :rows="alreadyPurchasedRows" show-isolate-button :isolated="isIsolatedTo(alreadyPurchasedRows)"
      @update:isolated="v => setIsolated(v, alreadyPurchasedRows)" />
  </v-alert>
  <v-alert v-if="normalizedStatusRows.length" type="info" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(normalizedStatusRows.length) }} статус из файла автоматически приведён к одному из принятых —
    проверьте соответствие в колонке «Статус».
    <RowWarningChips :rows="normalizedStatusRows" show-isolate-button :isolated="isIsolatedTo(normalizedStatusRows)"
      @update:isolated="v => setIsolated(v, normalizedStatusRows)" />
  </v-alert>
  <v-alert v-if="payrollRows.length" type="info" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(payrollRows.length) }} отмечены как ФОТ — попадут в импорт только при включённом переключателе
    «Включить ФОТ».
    <RowWarningChips :rows="payrollRows" show-isolate-button :isolated="isIsolatedTo(payrollRows)"
      @update:isolated="v => setIsolated(v, payrollRows)" />
  </v-alert>

  <!-- 🔵 правка 3: оверлей на серию кликов (debounce ~500мс, см.
       queuePreviewRefresh в useFactImport.ts) — таблица остаётся видимой и
       кликабельной, не мигает полным factImport.loading на каждую галочку. -->
  <div class="fisr-table-wrap" ref="tableWrapRef">
    <div v-if="factImport.previewRefreshing" class="fisr-overlay">
      <v-progress-circular indeterminate size="28" color="teal" />
    </div>
    <!-- Жалоба владельца 07.10.2026 (п.4): шапка «уезжала» при прокрутке —
         прокручивался ВНЕШНИЙ div (.fisr-table-wrap), а не внутренний
         .v-table__wrapper самого v-table. fixed-header+height здесь (образец
         PaymentsTable.vue:12-13) — Vuetify сам держит прокрутку и шапку
         внутри .v-table__wrapper; внешний div больше не скроллится сам
         (см. стили ниже), useRowJump.scrollToRowEl ниже целится именно в
         .v-table__wrapper. -->
    <v-table density="compact" class="fisr-table" fixed-header height="55vh">
      <thead>
        <tr>
          <th>Стр.</th><th class="fisr-col-plan">Плановая позиция</th><th>Статус</th>
          <th class="fisr-col-match">Сопоставление</th><th>План</th><th>Договор</th>
          <th class="fisr-col-over">Превышение</th><th>Оплачено</th><th>Поставщик</th><th>Пропустить</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in filteredRows" :key="r.row" :data-row-anchor="r.row"
          :class="{ 'fisr-row--decision': r.needs_contract_decision, 'fisr-row--needs-status': r.needs_status, 'fisr-row--skip': r.skip, 'row-jump-flash': rowJumpState.highlightedRow === r.row }">
          <td>{{ r.row }}</td>
          <td class="fisr-col-plan">
            <div class="text-caption text-medium-emphasis">{{ r.path.join(' › ') }}</div>
            <div>{{ r.name }}</div>
            <v-tooltip v-if="r.warnings?.length" location="bottom" max-width="420">
              <template #activator="{ props: warnProps }">
                <div v-bind="warnProps" class="text-caption text-warning fisr-warnings">
                  <v-icon icon="mdi-alert-outline" size="12" /> {{ r.warnings.join('; ') }}
                </div>
              </template>
              <span>{{ r.warnings.join('; ') }}</span>
            </v-tooltip>
          </td>
          <td>
            <!-- Ровно 6 статусов GALA — список ТОЛЬКО с бэкенда
                 (preview.statuses), свой справочник фронт не хранит. -->
            <v-select
              :model-value="rowStatusCode(r)"
              :items="statusSelectOptions"
              density="compact" variant="outlined" hide-details style="min-width:128px"
              class="fisr-wrap-select"
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
            <!-- «Договор заключён» — про статус «В работе» + законтрактовано,
                 логически относится к статусу строки, перенесена сюда из
                 колонки «Превышение» (чек-лист 07.10.2026, п.2). -->
            <v-checkbox v-if="r.needs_contract_decision"
              :model-value="isContractConfirmed(r.row)" label="Договор заключён" density="compact" hide-details
              @update:model-value="v => onContractConfirmed(r.row, !!v)" />
          </td>
          <td class="fisr-col-match">
            <FactImportRowMatchCell :row="r" @open-picker="openPicker" @set-planned-item="onSetPlannedItem" />
          </td>
          <td>{{ fmt(r.plan.amount) }}</td>
          <td>{{ fmt(r.fact.amount ?? r.contracted) }}</td>
          <td class="fisr-col-over">
            <template v-if="isOverPlan(r)">
              <div class="text-caption text-medium-emphasis">
                больше плана на {{ fmt(overPlanDiff(r)) }}
              </div>
              <v-select
                :model-value="overPlanChoice(r.row)" :items="overPlanOptions" density="compact" hide-details
                variant="outlined" style="max-width:140px" class="fisr-wrap-select"
                @update:model-value="v => onOverPlanChoice(r.row, v)" />
            </template>
            <template v-else>—</template>
          </td>
          <td>{{ fmt(r.paid) }}</td>
          <td>{{ r.supplier || '—' }}</td>
          <td>
            <FactImportRowSkipCell :row="r" @update:skip="onRowSkip" />
          </td>
        </tr>
      </tbody>
    </v-table>
  </div>

  <FactImportRowPlanPicker v-model="pickerOpen" :row="pickerRow" :subsidy-id="subsidyId" @update:model-value="onPickerClose" />
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useFactImport, type FactImportRow, type FactImportOverPlanChoice } from '@/composables/subsidies/useFactImport'
import { useRowJump } from '@/composables/subsidies/useRowJump'
import FactImportRowPlanPicker from './FactImportRowPlanPicker.vue'
import FactImportRowMatchCell from './FactImportRowMatchCell.vue'
import FactImportRowSkipCell from './FactImportRowSkipCell.vue'
import RowWarningChips from './RowWarningChips.vue'
import { formatMoney } from '@/utils/formatMoney'
import { rowsInPhrase } from '@/utils/pluralize'

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
// «Показать только эти строки» (один из сводных предупреждений выше) —
// держит набор строк одного предупреждения; второй клик на той же кнопке или
// крестик чипа над таблицей снимает изоляцию.
const isolatedRows = ref<number[] | null>(null)

// 🔵 правка 3: статусы — ровно 6 из preview.statuses (код→подпись с бэка),
// не собственный список фронта (ПРАВИЛО №6).
const statusSelectOptions = computed(() =>
  (factImport.preview?.statuses || []).map(s => ({ title: s.label, value: s.code })))
const statusFilterOptions = computed(() => statusSelectOptions.value)

function rowStatusCode(r: FactImportRow): string {
  return factImport.decisions.row_overrides[String(r.row)]?.status ?? r.status
}

const filteredRows = computed(() => visibleRows.value.filter(r => {
  if (isolatedRows.value && !isolatedRows.value.includes(r.row)) return false
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

// Наборы строк под каждое сводное предупреждение (ПРАВИЛО №6 — одно условие,
// один источник: то же needs_contract_decision/needs_status/match.state/
// isOverPlan/statusNormalizedHint/is_payroll, которыми уже помечена каждая
// строка в таблице ниже, здесь просто собраны в список номеров для чипов).
const contractRows = computed(() => visibleRows.value.filter(r => r.needs_contract_decision).map(r => r.row))
const statusRows = computed(() => visibleRows.value.filter(r => r.needs_status).map(r => r.row))
const notFoundRows = computed(() =>
  visibleRows.value.filter(r => r.match.state === 'not_found' || r.match.state === 'ambiguous').map(r => r.row))
const overPlanRows = computed(() => visibleRows.value.filter(isOverPlan).map(r => r.row))
const alreadyPurchasedRows = computed(() =>
  visibleRows.value.filter(r => r.match.state === 'already_purchased').map(r => r.row))
const normalizedStatusRows = computed(() =>
  visibleRows.value.filter(r => !!statusNormalizedHint(r)).map(r => r.row))
const payrollRows = computed(() => visibleRows.value.filter(r => r.is_payroll).map(r => r.row))

function isIsolatedTo(rows: number[]): boolean {
  if (!isolatedRows.value) return false
  if (isolatedRows.value.length !== rows.length) return false
  const set = new Set(rows)
  return isolatedRows.value.every(r => set.has(r))
}
function setIsolated(on: boolean, rows: number[]) {
  isolatedRows.value = on ? [...rows] : null
}

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
// Короткие подписи (2-я приёмка 07.10.2026: «Заключён д…»/«Урезать д…» —
// обрезались в узкой колонке «Превышение») — полный смысл решения не
// меняется, только текст короче + выбранное значение теперь переносится
// (см. .fisr-wrap-select ниже), а не режется многоточием.
const overPlanOptions: { title: string; value: FactImportOverPlanChoice }[] = [
  { title: 'С пометкой', value: 'keep_over' },
  { title: 'Урезать до плана', value: 'trim' },
  { title: 'Пропустить', value: 'skip' },
]
function overPlanChoice(row: number): FactImportOverPlanChoice {
  return factImport.decisions.over_plan[String(row)] || 'keep_over'
}
// Подпись над селектом решения (чек-лист 07.10.2026, п.2) — «на сколько
// больше плана», тот же источник чисел, что и isOverPlan выше (ПРАВИЛО №6).
function overPlanDiff(r: FactImportRow): number {
  const fact = r.fact.amount ?? r.contracted ?? 0
  return fact - (r.plan.amount ?? 0)
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

// Переход «к строке» (useRowJump.ts, ЕДИНЫЙ механизм мастера) — чип в одном
// из предупреждений выше кладёт номер строки в общее состояние; этот шаг (он
// активен — виден на экране) сам снимает СВОИ фильтры, которые могли бы
// скрыть строку, и скроллит к <tr data-row-anchor="N"> внутри .fisr-table-wrap.
const { state: rowJumpState, clearPendingRow, scrollToRowEl } = useRowJump()
const tableWrapRef = ref<HTMLElement | null>(null)
watch(() => rowJumpState.pendingRow, (row) => {
  if (row == null) return
  statusFilter.value = null
  onlyNeedsDecision.value = false
  onlyWarnings.value = false
  showSkipped.value = true
  if (isolatedRows.value && !isolatedRows.value.includes(row)) isolatedRows.value = null
  nextTick(() => {
    // Задание 07.10.2026 (п.7): .v-table__wrapper — тот элемент, который
    // Vuetify реально прокручивает при fixed-header+height (внешний
    // .fisr-table-wrap больше не скроллится сам, см. стили ниже).
    const scrollEl = tableWrapRef.value?.querySelector<HTMLElement>('.v-table__wrapper') ?? tableWrapRef.value
    scrollToRowEl(scrollEl, row)
    clearPendingRow()
  })
})
</script>

<style scoped>
/* Задание 07.10.2026 (п.7): внешний div больше НЕ скроллится сам — v-table
   с fixed-header+height держит прокрутку внутри своего .v-table__wrapper
   (образец PaymentsTable.vue:12-13); position:relative остаётся только для
   оверлея .fisr-overlay поверх таблицы. */
.fisr-table-wrap { position: relative; border: 1px solid #eee; border-radius: 6px; }
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

/* Жалоба владельца 07.10.2026: колонка «Плановая позиция» раздувалась
   длинными предупреждениями и уводила «Превышение»/«Пропустить» за правый
   край без видимой прокрутки — ширины колонок ограничены, предупреждения
   зажаты в 2 строки (полный текст — в tooltip, см. template). Шапка теперь
   держится fixed-header самого v-table, свой sticky не нужен. */
.fisr-table :deep(th), .fisr-table :deep(td) {
  padding: 4px 6px !important;
}
/* 2-я приёмка 07.10.2026 (браузер, 1280×800): сумма прежних min-width
   (статус 160 + плановая 200 + сопоставление 190 + превышение 170 + остальные
   колонки) уводила «Пропустить» за правый край контейнера (1304px при
   1232px доступных) — таблица скроллилась по горизонтали внутри самой себя.
   Ширины урезаны так, чтобы 10 колонок умещались на 1280px без внутренней
   прокрутки (см. .fisr-wrap-select ниже — выбранное значение селектов
   переносится, а не обрезается многоточием при таких узких колонках). */
.fisr-col-plan { max-width: 190px; min-width: 150px; }
.fisr-col-match { min-width: 140px; max-width: 170px; }
.fisr-col-over { min-width: 130px; }
.fisr-warnings {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: help;
}
/* Подписи решений («Урезать до плана» и т.п.) переносятся вместо обрезки
   многоточием в узких колонках «Статус»/«Превышение». */
.fisr-wrap-select :deep(.v-select__selection-text) {
  white-space: normal;
  overflow: visible;
  text-overflow: unset;
  line-height: 1.2;
}
.fisr-wrap-select :deep(.v-field__input) {
  min-height: 36px;
  height: auto;
  flex-wrap: wrap;
}
</style>
