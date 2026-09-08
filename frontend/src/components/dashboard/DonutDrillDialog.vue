<template>
  <v-dialog v-model="show" max-width="500" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-5 d-flex align-center gap-2">
        <v-icon :color="['success','primary','warning','grey'][drillDownSegment ?? 0]"
          :icon="['mdi-cash-check','mdi-file-sign','mdi-clock-outline','mdi-cash-remove'][drillDownSegment ?? 0]" />
        {{ drillDownSegment !== null ? segmentLabels[drillDownSegment] : '' }}
      </v-card-title>
      <v-card-subtitle class="px-5 pb-1 text-caption text-medium-emphasis">Разбивка по субсидиям</v-card-subtitle>
      <v-card-text class="pa-0">
        <v-table density="compact">
          <thead>
            <tr>
              <th class="px-5">Субсидия</th>
              <th class="text-right px-5">Сумма</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in drillDownRows" :key="row.name">
              <td class="px-5 py-2">{{ row.name }}</td>
              <td class="text-right px-5 font-weight-medium text-primary">{{ formatCurrency(row.value) }}</td>
            </tr>
            <tr v-if="drillDownRows.length === 0">
              <td colspan="2" class="text-center py-6 text-medium-emphasis">Нет данных</td>
            </tr>
          </tbody>
          <tfoot v-if="drillDownRows.length > 1">
            <tr style="border-top: 2px solid var(--crm-border-strong)">
              <td class="px-5 py-2 font-weight-bold">Итого</td>
              <td class="text-right px-5 font-weight-bold text-primary">
                {{ formatCurrency(drillDownRows.reduce((s, r) => s + r.value, 0)) }}
              </td>
            </tr>
          </tfoot>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  mobile: boolean
  drillDownSegment: number | null
  drillDownRows: { name: string; value: number }[]
  segmentLabels: string[]
  formatCurrency: (v: number) => string
}>()

const show = defineModel<boolean>({ required: true })
</script>
