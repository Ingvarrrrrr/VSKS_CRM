<template>
  <!-- «Привязать к плану» (владелец, 2026-09-16, дефект 2) — общий диалог для закупки
       И заявки (PurchaseItemsEditor.vue вызывает его один раз, требование C — один
       компонент, один композабл). Список «позиция → предложенная плановая», галочки:
       100% совпадение отмечено и подписано, частичное — предложено, но не отмечено. -->
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="720" persistent>
    <v-card :loading="loading">
      <v-card-title class="text-subtitle-1">Привязать к плану ({{ rows.length }})</v-card-title>
      <v-card-text>
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate color="primary" />
          <div class="text-caption text-medium-emphasis mt-2">Подбираем плановые позиции…</div>
        </div>
        <template v-else>
          <div v-if="!rows.length" class="text-body-2 text-medium-emphasis py-4">
            Нет непривязанных позиций.
          </div>
          <div v-for="(row, i) in rows" :key="row.uid" class="bulk-match-row d-flex align-start ga-2 py-2">
            <v-checkbox
              :model-value="row.checked"
              :disabled="!row.candidate"
              density="compact" hide-details
              @update:model-value="$emit('toggle', i)"
            />
            <div class="flex-grow-1">
              <div class="text-body-2 font-weight-medium">{{ row.name }}</div>
              <div v-if="row.candidate" class="text-caption text-medium-emphasis">
                → {{ row.candidate.name }}
                <span v-if="row.candidate.path"> · {{ row.candidate.path }}</span>
                <span v-if="row.candidate.residual != null"> · остаток {{ fmt(row.candidate.residual) }}</span>
              </div>
              <div v-else class="text-caption text-medium-emphasis">Похожих плановых позиций не найдено</div>
            </div>
            <v-chip v-if="row.isExact" size="small" color="success" variant="tonal">точное совпадение</v-chip>
            <v-chip v-else-if="row.candidate" size="small" color="amber" variant="tonal">
              предложено, {{ Math.round(row.candidate.score * 100) }}%
            </v-chip>
          </div>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="loading" @click="$emit('cancel')">Отмена</v-btn>
        <v-btn
          color="primary" variant="flat"
          :disabled="loading || !rows.some(r => r.checked)"
          @click="$emit('confirm')"
        >
          Привязать отмеченные
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { BulkMatchRow } from '@/composables/items/feoPlanned/useFeoPlannedBulkMatch'

defineProps<{
  modelValue: boolean
  rows: BulkMatchRow[]
  loading?: boolean
  fmt: (v: number | null | undefined) => string
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  toggle: [i: number]
  confirm: []
  cancel: []
}>()
</script>

<style scoped>
.bulk-match-row + .bulk-match-row {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
