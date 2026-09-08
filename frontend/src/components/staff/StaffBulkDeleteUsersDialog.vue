<template>
  <v-dialog v-model="show" max-width="440" persistent>
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить сотрудников?
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4 pa-4">
        <p class="mb-2">
          Вы собираетесь удалить <strong>{{ count }}</strong> сотрудников.
          Это действие <strong>нельзя отменить</strong>.
        </p>
        <p class="text-caption text-medium-emphasis">
          Все данные, задачи и права доступа удалённых сотрудников будут потеряны.
          В связанных закупках и задачах исполнитель/автор станет пустым.
        </p>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" :disabled="loading" @click="show = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" :loading="loading" @click="$emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{ count: number; loading: boolean }>()
defineEmits<{ (e: 'confirm'): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
