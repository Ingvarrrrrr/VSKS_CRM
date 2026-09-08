<template>
  <div class="d-flex align-center mb-4 flex-wrap" style="gap:8px">
    <v-select
      v-model="filterUserOrgId"
      v-if="organizations.length > 1"
      :items="organizations"
      item-title="name" item-value="id"
      label="Организация" variant="outlined" density="compact" clearable
      style="max-width:200px" hide-details
    />
    <v-select
      v-model="filterUserRole"
      :items="roleItems"
      item-title="label" item-value="value"
      label="Роль" variant="outlined" density="compact" clearable
      style="max-width:160px" hide-details
    />
    <v-text-field
      v-model="filterUserSearch"
      label="Поиск по ФИО / логину / ИНН"
      prepend-inner-icon="mdi-magnify"
      variant="outlined" density="compact" clearable hide-details
      style="max-width:280px"
    />
    <v-spacer />
    <v-btn v-if="isAdmin" variant="outlined" size="small" prepend-icon="mdi-download" @click="$emit('download-template')">
      Шаблон
    </v-btn>
    <v-btn v-if="isAdmin" color="success" variant="tonal" size="small" prepend-icon="mdi-file-excel-outline" @click="$emit('open-import')">
      Импорт из Excel
    </v-btn>
    <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="$emit('open-columns')">Колонки</v-btn>
    <RegistryExportButton
      title="Персонал"
      :get-columns="getExportColumns"
      :get-rows="getExportRows"
      :get-capture-el="getCaptureEl"
      @error="(msg: string) => $emit('error', msg)"
    />
    <v-btn-toggle
      v-if="!staffMobile"
      v-model="staffViewMode"
      mandatory
      density="compact"
      variant="outlined"
      divided
      class="ml-1"
    >
      <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
      <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
    </v-btn-toggle>
  </div>
</template>

<script setup lang="ts">
import RegistryExportButton from '@/components/RegistryExportButton.vue'

defineProps<{
  organizations: any[]
  roleItems: { value: string; label: string }[]
  isAdmin: boolean
  staffMobile: boolean
  getExportColumns: () => any[]
  getExportRows: () => any[]
  getCaptureEl: () => HTMLElement | null
}>()
defineEmits<{
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'open-columns'): void
  (e: 'error', msg: string): void
}>()
const filterUserOrgId = defineModel<number | null>('filterUserOrgId')
const filterUserRole = defineModel<string | null>('filterUserRole')
const filterUserSearch = defineModel<string>('filterUserSearch', { required: true })
const staffViewMode = defineModel<string>('staffViewMode', { required: true })
</script>
