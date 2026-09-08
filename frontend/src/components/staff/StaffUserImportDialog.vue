<template>
  <v-dialog v-model="dialog.show" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-file-excel-outline" color="success" class="mr-2" />
        Импорт пользователей из Excel
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-btn variant="text" color="primary" size="small" prepend-icon="mdi-download" class="mb-4"
          @click="$emit('download-template')">
          Скачать шаблон
        </v-btn>
        <v-file-input
          v-model="dialog.file"
          label="Выберите Excel файл"
          accept=".xlsx,.xls"
          variant="outlined" density="compact"
          prepend-icon="mdi-file-upload-outline"
          :disabled="dialog.loading"
        />
        <v-alert v-if="dialog.result" :type="dialog.result.errors?.length ? 'warning' : 'success'" class="mt-3" density="compact">
          Создано: {{ dialog.result.created }}, пропущено: {{ dialog.result.skipped }}
          <div v-if="dialog.result.errors?.length" class="mt-2">
            <div v-for="(e, i) in dialog.result.errors" :key="i" class="text-body-2">
              Строка {{ e.row }}: {{ e.error }}
            </div>
          </div>
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Закрыть</v-btn>
        <v-btn color="success" variant="flat"
          :loading="dialog.loading"
          :disabled="!dialog.file"
          @click="$emit('import')">
          Импортировать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  dialog: { show: boolean; file: File | null; loading: boolean; result: { created: number; skipped: number; errors: { row: number; error: string }[] } | null }
  mobile: boolean
}>()
defineEmits<{ (e: 'download-template'): void; (e: 'import'): void }>()
</script>
