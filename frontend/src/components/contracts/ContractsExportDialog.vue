<template>
  <v-dialog v-model="exportDialog" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-file-excel-outline" color="success" class="mr-2" />Скачать реестр договоров
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <div class="text-body-2 mb-3">Выберите колонки для экспорта:</div>
        <v-checkbox v-for="col in exportColumns" :key="col.key"
          v-model="col.selected" :label="col.title" density="compact" hide-details />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-btn variant="text" size="small" @click="exportColumns.forEach((c: any) => c.selected = true)">Выбрать все</v-btn>
        <v-btn variant="text" size="small" @click="exportColumns.forEach((c: any) => c.selected = false)">Снять все</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="exportDialog = false">Отмена</v-btn>
        <v-btn color="success" variant="flat" prepend-icon="mdi-download" :loading="exportLoading" @click="onExport">Скачать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const exportDialog = defineModel<boolean>({ required: true })

defineProps<{
  exportColumns: { key: string; title: string; selected: boolean }[]
  exportLoading: boolean
  mobile: boolean
  onExport: () => void
}>()
</script>
