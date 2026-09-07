<template>
  <!-- Save Filter Preset Dialog -->
  <v-dialog v-model="dialog.show" max-width="380">
    <v-card>
      <v-card-title class="pa-4">Сохранить фильтр</v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-text-field
          v-model="dialog.name"
          label="Название пресета"
          variant="outlined" density="compact" autofocus
          placeholder="Например: ФАДМ 2026 неоплачено"
          @keyup.enter="onConfirm"
        />
        <div class="text-caption text-medium-emphasis mt-1">
          <span v-if="filters.subsidyId">Субсидия: {{ subsidies.find(s=>s.id===filters.subsidyId)?.name }}</span>
          <span v-if="filters.status" class="ml-2">Статус: {{ STATUS_LABEL[filters.status] }}</span>
          <span v-if="filters.search" class="ml-2">Поиск: "{{ filters.search }}"</span>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!dialog.name.trim()" @click="onConfirm">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { STATUS_LABEL } from '@/composables/orders/ordersLabels'
import type { OrdersFiltersState } from '@/composables/orders/useOrdersFilters'
import type { Subsidy } from '@/composables/orders/ordersTypes'

defineProps<{
  dialog: { show: boolean; name: string }
  filters: OrdersFiltersState
  subsidies: Subsidy[]
  onConfirm: () => void
}>()
</script>
