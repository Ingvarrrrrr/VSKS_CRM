<!-- Быстрые действия — путевой лист / сохранить / удалить. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-lightning-bolt" size="small" class="mr-2" />
      Быстрые действия
    </v-card-title>
    <v-card-text class="d-flex flex-column gap-2">
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-clipboard-edit-outline"
        block
        @click="$emit('new-waybill')"
      >
        Создать путевой лист
      </v-btn>
      <v-btn
        color="success"
        variant="tonal"
        prepend-icon="mdi-content-save"
        block
        :loading="saving"
        :disabled="!isDirty"
        @click="$emit('save')"
      >
        Сохранить изменения
      </v-btn>
      <v-btn
        v-if="isAdminOrAbove"
        color="error"
        variant="outlined"
        prepend-icon="mdi-delete"
        block
        @click="$emit('delete')"
      >
        Удалить ТС
      </v-btn>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
defineProps<{
  saving: boolean
  isDirty: boolean
  isAdminOrAbove: boolean
}>()

defineEmits<{
  (e: 'new-waybill'): void
  (e: 'save'): void
  (e: 'delete'): void
}>()
</script>
