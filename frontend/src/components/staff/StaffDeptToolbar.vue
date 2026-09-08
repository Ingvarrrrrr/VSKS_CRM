<template>
  <div class="d-flex align-center mb-4 flex-wrap dept-toolbar" style="gap:8px">
    <v-select
      v-model="filterDeptOrgId"
      v-if="organizations.length > 1"
      :items="organizations"
      item-title="name" item-value="id"
      label="Организация" variant="outlined" density="compact" clearable
      style="max-width:200px" hide-details
    />
    <v-select
      v-model="filterSubsidyId"
      :items="subsidies"
      item-title="name" item-value="id"
      label="Субсидия" variant="outlined" density="compact" clearable
      style="max-width:260px" hide-details
    />
    <v-autocomplete
      v-model="filterDeptUserId"
      :items="users.map(u => ({ title: u.full_name || u.username, value: u.id }))"
      item-title="title" item-value="value"
      label="Сотрудник" variant="outlined" density="compact" clearable
      style="max-width:220px" hide-details
    />
    <v-spacer />
    <RegistryExportButton
      title="Отделы"
      :get-columns="getDeptExportColumns"
      :get-rows="getDeptExportRows"
      :get-capture-el="getCaptureEl"
      @error="(msg: string) => $emit('error', msg)"
    />
    <v-btn variant="outlined" size="small" prepend-icon="mdi-download" @click="$emit('download-template')">
      Шаблон
    </v-btn>
    <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-file-excel-outline" @click="$emit('open-import')">
      Импорт Excel
    </v-btn>
    <v-btn color="primary" size="small" prepend-icon="mdi-plus" @click="$emit('create-dept')">
      Добавить отдел
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import RegistryExportButton from '@/components/RegistryExportButton.vue'

defineProps<{
  organizations: any[]
  subsidies: any[]
  users: any[]
  getDeptExportColumns: () => any[]
  getDeptExportRows: () => any[]
  getCaptureEl: () => HTMLElement | null
}>()
defineEmits<{
  (e: 'error', msg: string): void
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'create-dept'): void
}>()
const filterDeptOrgId = defineModel<number | null>('filterDeptOrgId')
const filterSubsidyId = defineModel<number | null>('filterSubsidyId')
const filterDeptUserId = defineModel<number | null>('filterDeptUserId')
</script>
