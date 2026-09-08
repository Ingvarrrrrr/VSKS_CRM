<template>
  <v-dialog v-model="show" max-width="500">
    <v-card>
      <v-card-title>Импорт отделов из Excel</v-card-title>
      <v-card-text>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-download" class="mb-3" @click="$emit('download-template')">Скачать шаблон</v-btn>
        <v-file-input v-model="deptImportFile" label="Выберите файл .xlsx" accept=".xlsx,.xls" variant="outlined" density="compact" />
        <v-alert v-if="deptImportResult" :type="deptImportResult.errors?.length ? 'warning' : 'success'" variant="tonal" class="mt-2">
          Создано отделов: {{ deptImportResult.created_departments }}, сотрудников: {{ deptImportResult.created_members }}
          <div v-for="err in deptImportResult.errors?.slice(0, 5)" :key="err.row" class="text-caption">Строка {{ err.row }}: {{ err.error }}</div>
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Закрыть</v-btn>
        <v-btn color="primary" :loading="deptImporting" :disabled="!deptImportFile" @click="$emit('import')">Импортировать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  deptImportResult: any
  deptImporting: boolean
}>()
defineEmits<{ (e: 'download-template'): void; (e: 'import'): void }>()
const show = defineModel<boolean>('show', { required: true })
const deptImportFile = defineModel<File | null>('deptImportFile', { required: true })
</script>
