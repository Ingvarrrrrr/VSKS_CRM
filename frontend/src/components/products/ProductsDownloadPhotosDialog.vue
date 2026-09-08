<template>
  <v-dialog v-model="dialog.show" max-width="480" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        <v-icon icon="mdi-image-sync" class="mr-2" />Скачать фото по ссылкам
      </v-card-title>
      <v-card-text class="px-6">
        <template v-if="!dialog.result">
          <p class="text-body-2 text-medium-emphasis">
            Для всех товаров, у которых есть ссылка на фото (но нет локальной копии),
            будет скачана фотография и сохранена в базе данных.
          </p>
          <v-alert v-if="dialog.loading" type="info" variant="tonal" class="mt-3">
            <v-progress-circular indeterminate size="16" width="2" class="mr-2" />
            Скачивание... может занять несколько минут
          </v-alert>
        </template>
        <template v-else>
          <v-alert type="success" variant="tonal" class="mb-3">
            Обновлено: <strong>{{ dialog.result.updated }}</strong> &nbsp;
            Пропущено: <strong>{{ dialog.result.skipped }}</strong>
          </v-alert>
          <div v-if="dialog.result.errors?.length" class="mt-2">
            <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ dialog.result.errors.length }}):</div>
            <v-list density="compact" class="rounded" style="max-height:160px;overflow-y:auto">
              <v-list-item v-for="e in dialog.result.errors" :key="e.id"
                :subtitle="`#${e.id} ${e.name}: ${e.error}`" />
            </v-list>
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false; dialog.result = null">Закрыть</v-btn>
        <v-btn v-if="!dialog.result" color="teal" :loading="dialog.loading"
          prepend-icon="mdi-download" @click="$emit('download')">Скачать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  dialog: {
    show: boolean; loading: boolean
    result: { updated: number; skipped: number; errors: { id: number; name: string; error: string }[] } | null
  }
  mobile: boolean
}>()
defineEmits<{ (e: 'download'): void }>()
</script>
