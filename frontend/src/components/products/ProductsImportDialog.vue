<template>
  <v-dialog v-model="dialog.show" max-width="540" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Импорт товаров из Excel</v-card-title>
      <v-card-text class="px-6">
        <!-- Step 1: upload -->
        <template v-if="dialog.step === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Форматы:</strong> Excel (.xlsx, .xls)<br>
              <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
              <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
            </div>
          </v-alert>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Загрузите файл .xlsx. Обязательная колонка:<br>
            <strong>Наименование</strong> (или «Название», «Товар»).<br>
            Необязательные: Описание, Категория, Вид, Цена (или «Стоимость»),
            Ссылка 1…3, Цена ссылки 1…3,
            Фото (URL), Многоразовое, Активен, Категория ФЭО.
          </p>
          <v-file-input
            v-model="dialog.fileList"
            label="Файл Excel (.xlsx)"
            accept=".xlsx,.xls"
            variant="outlined" density="compact"
            prepend-icon="mdi-file-excel"
            show-size
            @update:model-value="dialog.file = Array.isArray($event) ? ($event[0] ?? null) : ($event ?? null)"
          />
        </template>

        <!-- Step 2: results -->
        <template v-else>
          <v-alert v-if="dialog.result && !dialog.result.headers_found?.name" type="error" variant="tonal" class="mb-3">
            Колонка <strong>«Наименование»</strong> не найдена в файле!<br>
            Все строки пропущены. Проверьте заголовки в первой строке Excel.
            <div v-if="dialog.result.headers_raw?.length" class="mt-2 text-caption">
              Найденные заголовки: <strong>{{ dialog.result.headers_raw.filter((h: any) => h).join(', ') }}</strong>
            </div>
          </v-alert>
          <v-alert v-else-if="dialog.result" :type="dialog.result.created > 0 ? 'success' : 'warning'" variant="tonal" class="mb-3">
            Создано: <strong>{{ dialog.result.created }}</strong> &nbsp;
            Пропущено: <strong>{{ dialog.result.skipped }}</strong>
          </v-alert>
          <div v-if="dialog.result?.headers_found && Object.keys(dialog.result.headers_found).length" class="mb-3">
            <div class="text-caption text-medium-emphasis">Распознанные колонки:
              <span v-for="(header, field) in dialog.result.headers_found" :key="field" class="mr-2">
                <v-chip size="x-small" color="primary" variant="tonal">{{ header }}</v-chip>
              </span>
            </div>
          </div>
          <div v-if="dialog.result?.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ dialog.result.errors.length }}):</div>
            <v-list density="compact" class="bg-error-lighten-5 rounded">
              <v-list-item v-for="e in dialog.result.errors" :key="e.row"
                :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
            </v-list>
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="$emit('close')">{{ dialog.step === 2 ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="dialog.step === 1" color="primary" :loading="dialog.loading"
          :disabled="!dialog.file" @click="$emit('import')">Загрузить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  dialog: {
    show: boolean; step: number; file: File | null; fileList: File[]
    loading: boolean; result: any
  }
  mobile: boolean
}>()
defineEmits<{
  (e: 'close'): void
  (e: 'import'): void
}>()
</script>
