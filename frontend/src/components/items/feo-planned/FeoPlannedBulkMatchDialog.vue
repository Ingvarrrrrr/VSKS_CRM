<template>
  <!-- «Привязать к плану» (владелец, 2026-09-16, дефект 2) — общий диалог для закупки
       И заявки (PurchaseItemsEditor.vue вызывает его один раз, требование C — один
       компонент, один композабл). Список «позиция → предложенная плановая», галочки:
       100% совпадение отмечено и подписано, частичное — предложено, но не отмечено.
       Владелец (29.09, п.1, экран 2560px): max-width 720 узкий, чипы «точное
       совпадение» обрезались — ширина теперь от экрана (95vw/1600, fullscreen на
       mobile), таблица вместо d-flex строк, ничего не обрезается (white-space:normal). -->
  <v-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    width="95vw"
    max-width="1600"
    :fullscreen="mobile"
    persistent
  >
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
          <div v-else class="bulk-match-table-wrap">
            <v-table density="compact" class="bulk-match-table">
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th>Позиция закупки</th>
                  <th>Тип</th>
                  <th>Предложенная плановая позиция</th>
                  <th style="width:170px">Совпадение</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in rows" :key="row.uid">
                  <td>
                    <v-checkbox
                      :model-value="row.checked"
                      :disabled="!row.candidate"
                      density="compact" hide-details
                      @update:model-value="$emit('toggle', i)"
                    />
                  </td>
                  <td class="wrap-cell">
                    <div class="text-body-2 font-weight-medium">{{ row.name }}</div>
                  </td>
                  <td class="wrap-cell">
                    <div class="text-body-2">{{ row.itemType || '—' }}</div>
                    <div v-if="row.candidate" class="text-caption"
                      :class="row.candidate.itemType && row.itemType && row.candidate.itemType !== row.itemType ? 'text-error' : 'text-medium-emphasis'">
                      в плане: {{ row.candidate.itemType || (row.candidate.kind === 'planned_item' ? 'не указан' : 'категория целиком') }}
                    </div>
                  </td>
                  <td class="wrap-cell">
                    <template v-if="row.candidate">
                      <div class="text-body-2">{{ row.candidate.name }}</div>
                      <div v-if="row.candidate.path" class="text-caption text-medium-emphasis">{{ row.candidate.path }}</div>
                      <div v-if="row.candidate.residual != null" class="text-caption text-medium-emphasis">остаток {{ fmt(row.candidate.residual) }}</div>
                    </template>
                    <span v-else class="text-caption text-medium-emphasis">Похожих плановых позиций не найдено</span>
                  </td>
                  <td>
                    <v-chip v-if="row.isExact" size="small" color="success" variant="tonal" class="match-chip">точное совпадение</v-chip>
                    <v-chip v-else-if="row.candidate" size="small" color="amber" variant="tonal" class="match-chip">
                      предложено, {{ Math.round(row.candidate.score * 100) }}%
                    </v-chip>
                  </td>
                </tr>
              </tbody>
            </v-table>
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
import { useDisplay } from 'vuetify'
import type { BulkMatchRow } from '@/composables/items/feoPlanned/useFeoPlannedBulkMatch'

const { mobile } = useDisplay()

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
.bulk-match-table-wrap {
  overflow-x: auto;
}
.bulk-match-table :deep(th),
.bulk-match-table :deep(td) {
  white-space: normal;
  word-break: break-word;
  vertical-align: top;
  padding-top: 8px;
  padding-bottom: 8px;
}
.match-chip {
  flex-shrink: 0;
  white-space: nowrap;
  min-width: max-content;
}
</style>
