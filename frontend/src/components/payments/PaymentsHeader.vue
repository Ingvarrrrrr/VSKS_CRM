<template>
  <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
    <div>
      <h1 class="text-h5 font-weight-bold">
        Реестр платежей
        <span v-if="importId" class="text-medium-emphasis font-weight-regular">· Импорт #{{ importId }}</span>
      </h1>
      <span class="text-body-2 text-medium-emphasis">{{ totalCount }} записей</span>
    </div>
    <div class="d-flex ga-2 align-center">
      <v-btn prepend-icon="mdi-table-check" variant="outlined" color="warning" @click="emit('open-reconciliation')">
        Сверка платежей
      </v-btn>
      <v-btn prepend-icon="mdi-view-column" variant="outlined" color="primary" @click="showColumnPicker = true">
        Колонки
      </v-btn>
      <RegistryExportButton
        title="Реестр платежей"
        :get-columns="getColumns"
        :get-rows="getRows"
        :get-capture-el="getCaptureEl"
        @error="(msg) => emit('error', msg)"
      />
      <v-btn-toggle
        v-if="!prMobile"
        v-model="prViewMode"
        mandatory
        density="comfortable"
        variant="outlined"
        divided
      >
        <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
      </v-btn-toggle>
    </div>
  </div>
</template>

<script setup lang="ts">
import RegistryExportButton from '@/components/RegistryExportButton.vue'

const showColumnPicker = defineModel<boolean>('showColumnPicker', { required: true })
const prViewMode = defineModel<'table' | 'cards'>('prViewMode', { required: true })

defineProps<{
  totalCount: number
  importId: number | null
  prMobile: boolean
  getColumns: () => any[]
  getRows: () => any[]
  getCaptureEl: () => HTMLElement | null
}>()

const emit = defineEmits<{
  'open-reconciliation': []
  error: [msg: string]
}>()
</script>
