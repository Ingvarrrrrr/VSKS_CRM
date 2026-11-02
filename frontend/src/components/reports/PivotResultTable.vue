<template>
  <v-table density="compact" hover>
    <thead>
      <tr>
        <th v-for="d in rowDims" :key="'rd_' + d.key">{{ d.label }}</th>
        <th v-for="d in colDims" :key="'cd_' + d.key">{{ d.label }}</th>
        <th v-for="m in measures" :key="'m_' + m.key" class="text-right">{{ m.label }}</th>
        <th v-for="cc in calcColumns" :key="'cc_' + JSON.stringify(cc)" class="text-right">{{ calcLabel(cc) }}</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="(row, idx) in rows"
        :key="idx"
        :style="clickableRows ? 'cursor: pointer' : undefined"
        @click="clickableRows && $emit('row-click', row)"
      >
        <td v-for="d in rowDims" :key="'rd_' + d.key">{{ row[d.key] ?? '' }}</td>
        <td v-for="d in colDims" :key="'cd_' + d.key">{{ row[d.key] ?? '' }}</td>
        <td v-for="m in measures" :key="'m_' + m.key" class="text-right">{{ fmtNumber(row[m.key]) }}</td>
        <td v-for="cc in calcColumns" :key="'cc_' + JSON.stringify(cc)" class="text-right">{{ fmtCalc(row, cc) }}</td>
      </tr>
      <tr v-if="totals" class="bg-blue-lighten-4 font-weight-bold">
        <td :colspan="rowDims.length + colDims.length">Итого</td>
        <td v-for="m in measures" :key="'tm_' + m.key" class="text-right">{{ fmtNumber(totals[m.key]) }}</td>
        <td v-for="cc in calcColumns" :key="'tcc_' + JSON.stringify(cc)"></td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
/**
 * Таблица результата сводной (pivot) — один источник для превью в
 * PivotBuilderView.vue и для запуска сохранённой сводной в ReportRunView.vue
 * (ПРАВИЛО №6: одна вёрстка/форматирование, не две копии).
 * Форматирование чисел/расчётных колонок — из utils/pivotDisplay.ts.
 */
import { fmtNumber, fmtCalc, calcLabel, type PivotCalcColSpec } from '@/utils/pivotDisplay'

interface Dim { key: string; label: string }
interface Measure { key: string; label: string }

withDefaults(
  defineProps<{
    rowDims: Dim[]
    colDims: Dim[]
    measures: Measure[]
    calcColumns: PivotCalcColSpec[]
    rows: any[]
    totals?: Record<string, any> | null
    clickableRows?: boolean
  }>(),
  { totals: null, clickableRows: false },
)

defineEmits<{ (e: 'row-click', row: any): void }>()
</script>
