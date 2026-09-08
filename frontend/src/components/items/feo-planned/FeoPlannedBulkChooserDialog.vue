<template>
  <!-- Диалог выбора СПОСОБА создания (владелец, сессия 2026-08-17): «Создать в плане
       закупок» на «шапочном» экземпляре (см. проп bulkItems) больше не создаёт молча
       одну позицию на имя первого товара и всю НМЦД — сначала спрашивает, как именно.
       POST /feo-planned-items/bulk — одна атомарная транзакция на все выбранные строки. -->
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="640" :persistent="bulkCreating">
    <v-card>
      <v-card-title class="text-subtitle-1">Создать в плане закупок</v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-3">Категория: {{ categoryName }}</div>
        <v-radio-group :model-value="mode" @update:model-value="(v: string | null) => $emit('update:mode', v as 'per_item' | 'single' | 'manual')" hide-details density="compact" class="mb-3">
          <v-radio value="per_item">
            <template #label>
              <span>По плановой позиции на <b>каждый товар</b> — {{ bulkPerItemCandidates.length }}
                {{ bulkPerItemCandidates.length === 1 ? 'позиция' : 'позиций' }}, каждая на свою сумму</span>
            </template>
          </v-radio>
          <v-radio value="single">
            <template #label>
              <span>Одна <b>общая</b> позиция на всю закупку — сумма {{ fmt(bulkTotalAmount) }}</span>
            </template>
          </v-radio>
          <v-radio value="manual">
            <template #label>
              <span>Выбрать позиции <b>вручную</b></span>
            </template>
          </v-radio>
        </v-radio-group>

        <v-text-field
          v-if="mode === 'single'"
          :model-value="singleName"
          @update:model-value="$emit('update:singleName', $event)"
          label="Наименование *"
          variant="outlined"
          density="compact"
          hide-details="auto"
          class="mb-3"
          autofocus
        />

        <div v-if="mode === 'manual'" class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Отметьте позиции для создания:</div>
          <div v-for="row in bulkItems" :key="'manual-' + row.idx" class="d-flex align-center ga-1">
            <v-checkbox
              :model-value="manualChecked.includes(row.idx)"
              density="compact"
              hide-details
              class="flex-shrink-0"
              @update:model-value="(v: boolean | null) => $emit('toggle-manual', row.idx, !!v)"
            />
            <span class="text-body-2">
              {{ row.name }}
              <span class="text-caption text-medium-emphasis">— {{ fmt(row.amount) }}</span>
              <span v-if="row.linked" class="text-caption text-medium-emphasis"> (уже привязана к плановой позиции — по умолчанию не отмечена)</span>
            </span>
          </div>
        </div>

        <div class="text-caption text-medium-emphasis mb-1">Будет создано:</div>
        <v-table density="compact">
          <thead>
            <tr><th>Наименование</th><th>Кол-во</th><th class="text-right">Сумма</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in bulkPreviewRows" :key="'prev-' + (row.idx ?? 'single') + '-' + i">
              <td>{{ row.name || '—' }}</td>
              <td>{{ row.quantity ?? '—' }} {{ row.unit || '' }}</td>
              <td class="text-right">{{ fmt(row.amount) }}</td>
            </tr>
            <tr v-if="bulkPreviewRows.length === 0">
              <td colspan="3" class="text-medium-emphasis">Нечего создавать — отметьте хотя бы одну позицию</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="font-weight-bold">ИТОГО</td>
              <td></td>
              <td class="text-right font-weight-bold">{{ fmt(bulkPreviewTotal) }}</td>
            </tr>
          </tfoot>
        </v-table>
        <div v-if="mode === 'per_item' && bulkSkippedLinkedCount > 0" class="text-caption text-medium-emphasis mt-1">
          {{ bulkSkippedLinkedCount }} {{ bulkSkippedLinkedCount === 1 ? 'позиция уже привязана' : 'позиций уже привязаны' }} к плановой позиции — пропущены.
        </div>
        <div v-if="bulkCreating" class="mt-2 d-flex align-center ga-2">
          <v-progress-circular indeterminate size="18" width="2" color="primary" />
          <span class="text-caption">Создание…</span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="bulkCreating" @click="$emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="bulkCreating"
          :disabled="bulkPreviewRows.length === 0 || (mode === 'single' && !singleName.trim())"
          @click="$emit('create')"
        >
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { BulkItem, BulkPreviewRow } from '@/composables/items/feoPlanned/useFeoPlannedBulk'

defineProps<{
  modelValue: boolean
  categoryName: string
  mode: 'per_item' | 'single' | 'manual'
  singleName: string
  bulkItems?: BulkItem[]
  manualChecked: number[]
  bulkTotalAmount: number
  bulkPerItemCandidates: BulkItem[]
  bulkSkippedLinkedCount: number
  bulkPreviewRows: BulkPreviewRow[]
  bulkPreviewTotal: number
  bulkCreating: boolean
  fmt: (v: number | null | undefined) => string
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  'update:mode': [value: 'per_item' | 'single' | 'manual']
  'update:singleName': [value: string]
  'toggle-manual': [idx: number, checked: boolean]
  create: []
}>()
</script>
