<template>
  <!-- Жалоба владельца (сессия 2026-08-19): «создаю новую позицию 10 шт — она молча
       привязывается к существующей 14 шт». POST /feo-planned-items/ теперь отдаёт 409
       planned_item_duplicate_name вместо тихого return existing_item — этот диалог
       показывает ОБА набора чисел (что уже есть / что вводит человек) и даёт выбор:
       привязаться к существующей плановой позиции или создать отдельную (allow_duplicate_name). -->
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="460" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1">Такая позиция уже есть в плане</v-card-title>
      <v-card-text>
        <div class="mb-3">{{ duplicateInfo?.message }}</div>
        <v-table density="compact" class="mb-2">
          <thead>
            <tr><th></th><th>Кол-во</th><th class="text-right">Сумма</th></tr>
          </thead>
          <tbody>
            <tr>
              <td class="text-medium-emphasis">Уже в плане</td>
              <td>{{ duplicateInfo?.existingQuantity ?? '—' }} {{ duplicateInfo?.existingUnit || '' }}</td>
              <td class="text-right">{{ fmt(duplicateInfo?.existingAmount ?? null) }}</td>
            </tr>
            <tr>
              <td class="text-medium-emphasis">Вы вводите</td>
              <td>{{ duplicateInfo?.newQuantity ?? '—' }} {{ duplicateInfo?.newUnit || '' }}</td>
              <td class="text-right">{{ fmt(duplicateInfo?.newAmount ?? null) }}</td>
            </tr>
          </tbody>
        </v-table>
        <!-- Жалоба владельца (добор 2026-08-19): «Привязать к существующей» была
             активна, даже когда в найденной позиции остатка не было — новые числа
             молча садились поверх уже выбранных. -->
        <div v-if="attachBlockedReason" class="feo-planned-shortfall-note">{{ attachBlockedReason }}</div>
      </v-card-text>
      <v-card-actions class="flex-wrap">
        <v-spacer />
        <v-btn variant="text" :disabled="saving" @click="$emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn
          variant="outlined"
          color="primary"
          :disabled="saving || attachDisabled"
          :title="attachBlockedReason || undefined"
          @click="$emit('attach')"
        >Привязать к существующей</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" @click="$emit('create-duplicate')">Создать отдельную</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { DuplicateInfo } from '@/composables/items/feoPlanned/useFeoPlannedCreate'

defineProps<{
  modelValue: boolean
  duplicateInfo: DuplicateInfo | null
  attachBlockedReason: string | null
  attachDisabled: boolean
  saving: boolean
  fmt: (v: number | null | undefined) => string
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  attach: []
  'create-duplicate': []
}>()
</script>
