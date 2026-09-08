<template>
  <v-dialog v-model="show" max-width="440">
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
        <v-icon icon="mdi-delete-alert" color="error" />
        Удалить ТС?
      </v-card-title>
      <v-card-text class="px-5">
        Действие необратимо. Будут удалены все связанные документы, ремонты, пробег и история.
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" :loading="deleting" @click="$emit('confirm')">
          Удалить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  deleting: boolean
}>()

defineEmits<{
  (e: 'confirm'): void
}>()

const show = defineModel<boolean>({ default: false })
</script>
