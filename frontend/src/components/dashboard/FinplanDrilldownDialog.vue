<template>
  <v-dialog v-model="finplanDrilldown.show" max-width="1100" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-3">
        <v-icon icon="mdi-format-list-bulleted" class="mr-2" />
        <span>{{ finplanDrilldownTitle }} — {{ finplanDrilldown.period || 'все периоды' }}</span>
        <v-spacer />
        <v-chip size="small" variant="tonal" :color="finplanDrilldownChipColor">
          {{ finplanDrilldown.items.length }} закупок · Σ {{ finplanDrilldownTotal.toLocaleString('ru-RU') }} ₽
        </v-chip>
        <v-btn v-if="finplanDrilldown.category !== 'no_deadline'" size="small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel" @click="$emit('export-xlsx')" class="ml-2">
          Excel
        </v-btn>
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-2" @click="finplanDrilldown.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0">
        <v-progress-linear v-if="finplanDrilldown.loading" indeterminate />
        <v-table density="compact" v-else-if="finplanDrilldown.items.length">
          <thead>
            <tr>
              <th>№</th>
              <th>Предмет</th>
              <th>Контрагент</th>
              <th>Дата обязательства</th>
              <th>Статус</th>
              <th class="text-right">Сумма</th>
              <th class="text-right">Оплачено</th>
              <th class="text-right">Остаток</th>
              <th>Метки</th>
              <th>Понадобится</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in finplanDrilldown.items" :key="row.id"
                :style="{ cursor: 'pointer', opacity: row.is_likely_needed === false ? 0.55 : 1 }"
                @click="goToOrder(row.id)">
              <td><code>{{ row.purchase_number || row.id }}</code></td>
              <td>
                <div>{{ row.subject }}</div>
                <div v-if="row.stage_label" class="text-caption text-medium-emphasis">{{ row.stage_label }}</div>
              </td>
              <td>{{ row.contractor_name }}</td>
              <td>{{ formatDate(row.obligation_date || row.expected_date) }}</td>
              <td><v-chip size="x-small" variant="tonal">{{ statusLabelsFinplan[row.status] || row.status }}</v-chip></td>
              <td class="text-right font-weight-medium">{{ (row.amount || 0).toLocaleString('ru-RU') }} ₽</td>
              <td class="text-right">{{ (row.paid_amount || 0).toLocaleString('ru-RU') }} ₽</td>
              <td class="text-right">{{ (row.remaining || 0).toLocaleString('ru-RU') }} ₽</td>
              <td>
                <v-chip v-if="row.is_overdue" size="x-small" color="error" variant="tonal" class="mr-1">
                  Просрочено
                </v-chip>
                <v-chip v-if="row.missing_deadline" size="x-small" color="warning" variant="tonal" class="mr-1">
                  Нет срока
                </v-chip>
                <v-chip v-if="row.is_prepayment" size="x-small" color="info" variant="tonal">
                  Предоплата
                </v-chip>
              </td>
              <td @click.stop>
                <v-checkbox
                  :model-value="row.is_likely_needed !== false"
                  density="compact" hide-details
                  @update:model-value="patchIsLikelyNeeded(row, $event)"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
        <div v-else class="text-medium-emphasis text-center py-6">Нет закупок в этой группе</div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  mobile: boolean
  finplanDrilldown: {
    show: boolean
    loading: boolean
    period: string
    category: 'plan' | 'committed' | 'overdue' | 'no_deadline' | ''
    items: any[]
  }
  finplanDrilldownTitle: string
  finplanDrilldownTotal: number
  finplanDrilldownChipColor: string
  statusLabelsFinplan: Record<string, string>
  formatDate: (iso: string) => string
  goToOrder: (id: number) => void
  patchIsLikelyNeeded: (row: any, val: boolean) => void
}>()

defineEmits<{
  (e: 'export-xlsx'): void
}>()
</script>
