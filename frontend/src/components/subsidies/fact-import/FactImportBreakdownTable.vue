<template>
  <v-card variant="outlined" class="mt-3">
    <v-card-text>
      <div class="text-subtitle-2 mb-2">Из чего сложились итоги</div>
      <!-- Задание 08.10.2026: владелец сверяет так — ставит в файле фильтр
           по статусу «Оплачено» и сравнивает с GALA. Поэтому на статус нужно
           видеть «войдут + пропущено = всего по файлу» в одной строке, не
           искать плитки и «Пропущено» отдельно. -->
      <div class="fibt-table-wrap">
        <table class="fibt-table text-body-2">
          <thead>
            <tr>
              <th rowspan="2" class="fibt-status-col">Статус</th>
              <th colspan="3" class="text-center fibt-group-included">Войдут в импорт</th>
              <th colspan="3" class="text-center fibt-group-skipped">Пропущено</th>
              <th colspan="2" class="text-center fibt-group-total">Всего по файлу</th>
            </tr>
            <tr>
              <th class="text-right fibt-group-included">Строк</th>
              <th class="text-right fibt-group-included">Договор</th>
              <th class="text-right fibt-group-included">Оплачено</th>
              <th class="text-right fibt-group-skipped">Строк</th>
              <th class="text-right fibt-group-skipped">Договор</th>
              <th class="text-right fibt-group-skipped">Оплачено</th>
              <th class="text-right fibt-group-total">Договор</th>
              <th class="text-right fibt-group-total">Оплачено</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in visibleStatuses" :key="b.code">
              <td>{{ b.label }}</td>
              <td class="text-right">{{ b.included.rows }}</td>
              <td class="text-right">{{ fmt(b.included.contract_amount) }}</td>
              <td class="text-right">{{ fmt(b.included.paid) }}</td>
              <td class="text-right">{{ b.skipped.rows }}</td>
              <td class="text-right">{{ fmt(b.skipped.contract_amount_raw) }}</td>
              <td class="text-right">{{ fmt(b.skipped.paid) }}</td>
              <td class="text-right">{{ fmt(b.included.contract_amount_raw + b.skipped.contract_amount_raw) }}</td>
              <td class="text-right">{{ fmt(b.included.paid + b.skipped.paid) }}</td>
            </tr>
            <tr v-if="totals.breakdown.included_existing.rows > 0">
              <td>Обновят существующие закупки</td>
              <td class="text-right">{{ totals.breakdown.included_existing.rows }}</td>
              <td class="text-right">—</td>
              <td class="text-right">{{ fmt(totals.breakdown.included_existing.paid) }}</td>
              <td class="text-right">—</td>
              <td class="text-right">—</td>
              <td class="text-right">—</td>
              <td class="text-right">—</td>
              <td class="text-right">{{ fmt(totals.breakdown.included_existing.paid) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="fibt-total">
              <td>Итого (= плитки выше)</td>
              <td class="text-right">{{ includedRowsTotal }}</td>
              <td class="text-right">{{ fmt(totals.contract_amount) }}</td>
              <td class="text-right">{{ fmt(totals.paid_amount) }}</td>
              <td class="text-right">{{ totals.skipped }}</td>
              <td class="text-right">{{ fmt(skippedContractTotal) }}</td>
              <td class="text-right">{{ fmt(skippedPaidTotal) }}</td>
              <td class="text-right">{{ fmt(totalFileContract) }}</td>
              <td class="text-right">{{ fmt(totalFilePaid) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- Задание 08.10.2026, п.4: сумма урезки «Договор больше плана» —
           разница between contract_amount_raw и contract_amount по
           включённым строкам (over_plan_choice='trim'), чтобы «Войдут.
           Договор» ≠ «Всего по файлу. Договор» не выглядело как ошибка. -->
      <div v-if="hasTrimmed" class="text-caption text-medium-emphasis mt-1">
        Урезано до плана по решению «Превышение»: {{ fmt(trimmedTotal) }}
      </div>

      <!-- Задание 07.10.2026 (п.4/п.10): «Пропущено» — отдельный блок с
           раскрытием по причине и номерами строк; клик по номеру — назад на
           шаг 3 к строке (goToRow, useRowJump). -->
      <div v-if="totals.skipped > 0" class="mt-3">
        <div class="text-body-2">
          Пропущено: {{ totals.skipped }} {{ rowsWord(totals.skipped) }}, договор
          {{ fmt(skippedContractTotal) }}, оплачено {{ fmt(skippedPaidTotal) }}
        </div>
        <v-expansion-panels class="mt-1" variant="accordion">
          <v-expansion-panel v-for="r in totals.breakdown.skipped_by_reason" :key="r.code">
            <v-expansion-panel-title class="text-caption">
              {{ reasonTitle(r) }}
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div class="d-flex flex-wrap ga-1">
                <v-chip v-for="rn in r.rows" :key="rn" size="x-small" variant="tonal"
                  class="fibt-row-chip" @click="$emit('go-to-row', rn)">
                  стр. {{ rn }}
                </v-chip>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// FactImportBreakdownTable — «Из чего сложились итоги» на шаге 5 мастера
// «Импорт факта» (ПРАВИЛО №5: вынесена из FactImportStepConfirm.vue, чтобы
// тот не разрастался). Чек-лист владельца 07.10.2026, п.4/п.6: «Оплачено»/
// «Договоров» на плитках не раскладывались — непонятно, откуда 2 718 488
// вместо 2 726 988 по фильтру файла. Данные — totals.breakdown, посчитанные
// бэкендом В ОДНОМ цикле с totals (preview.py, ПРАВИЛО №6) — здесь только
// отображение, сумма вторым способом не считается.
//
// Задание 08.10.2026: владелец сверяет по статусу, ставя фильтр в файле —
// по каждому статусу нужно видеть «войдут + пропущено = всего по файлу» в
// одной строке (шапка в два уровня), не складывать это в голове самому.
import { computed } from 'vue'
import type { FactImportBreakdownSkipReason, FactImportTotals } from '@/composables/subsidies/useFactImport'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{ totals: FactImportTotals }>()
defineEmits<{ 'go-to-row': [row: number] }>()

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

// Статусы, где нет ни одной строки ни «войдёт», ни «пропущено» — скрыты,
// владельцу незачем листать строки сплошь из нулей.
const visibleStatuses = computed(() =>
  props.totals.breakdown.by_status.filter(b => b.included.rows > 0 || b.skipped.rows > 0))

const includedRowsTotal = computed(() =>
  props.totals.breakdown.by_status.reduce((s, b) => s + b.included.rows, 0)
  + props.totals.breakdown.included_existing.rows)

const skippedContractTotal = computed(() =>
  props.totals.breakdown.by_status.reduce((s, b) => s + b.skipped.contract_amount_raw, 0))
const skippedPaidTotal = computed(() =>
  props.totals.breakdown.by_status.reduce((s, b) => s + b.skipped.paid, 0))

// «Всего по файлу» (п.1): договор ДО урезания (raw) включённых + пропущенных;
// оплачено — то же самое, плюс обновление существующих закупок (та же
// реальная оплата по субсидии, что и в плитке «Оплачено»).
const totalFileContract = computed(() =>
  props.totals.breakdown.by_status.reduce(
    (s, b) => s + b.included.contract_amount_raw + b.skipped.contract_amount_raw, 0))
const totalFilePaid = computed(() =>
  props.totals.breakdown.by_status.reduce((s, b) => s + b.included.paid + b.skipped.paid, 0)
  + props.totals.breakdown.included_existing.paid)

// п.4: разница contract_amount_raw/contract_amount у включённых строк — это
// ровно то, что «срезало» решение «Урезать до плана» в колонке «Превышение»
// (preview.py/commit.py, тот же over_plan_choice='trim', ПРАВИЛО №6 — тут
// просто показ разницы, не вторая формула урезания).
const trimmedTotal = computed(() =>
  props.totals.breakdown.by_status.reduce(
    (s, b) => s + (b.included.contract_amount_raw - b.included.contract_amount), 0))
const hasTrimmed = computed(() => trimmedTotal.value > 0.005)

function rowsWord(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'строк'
  if (mod10 === 1) return 'строка'
  if (mod10 >= 2 && mod10 <= 4) return 'строки'
  return 'строк'
}

// п.5: заголовок панели причины — с договором (если он не нулевой — у
// части причин, напр. no_status, договора нет вовсе) и оплатой.
function reasonTitle(r: FactImportBreakdownSkipReason): string {
  const parts = [`${r.rows.length} ${rowsWord(r.rows.length)}`]
  if (r.contract_amount_raw) parts.push(`договор ${fmt(r.contract_amount_raw)}`)
  parts.push(`оплачено ${fmt(r.paid)}`)
  return `${r.label} — ${parts.join(', ')}`
}
</script>

<style scoped>
/* п.6: таблица шире диалога на 1280 — скроллится горизонтально ВНУТРИ
   своего контейнера, не раздвигает диалог. */
.fibt-table-wrap { overflow-x: auto; max-width: 100%; }
.fibt-table { width: 100%; min-width: 760px; border-collapse: collapse; }
.fibt-table th, .fibt-table td { padding: 4px 8px; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); white-space: nowrap; }
.fibt-status-col { white-space: normal; text-align: left; }
.fibt-group-included { background: rgba(var(--v-theme-success), 0.06); }
.fibt-group-skipped { background: rgba(var(--v-theme-warning), 0.06); }
.fibt-group-total { background: rgba(var(--v-theme-on-surface), 0.04); }
.fibt-total td { font-weight: 600; border-top: 2px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-bottom: none; }
.fibt-row-chip { cursor: pointer; }
</style>
