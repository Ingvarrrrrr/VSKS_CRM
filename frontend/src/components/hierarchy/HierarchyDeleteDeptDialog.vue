<template>
  <v-dialog v-model="show" max-width="380">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-delete-alert" color="error" class="mr-2" />
        Удалить отдел
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        Удалить отдел <strong>«{{ name }}»</strong>?
        Все сотрудники станут «Вне отдела».
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" @click="emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{ name: string }>()
const emit = defineEmits<{ confirm: [] }>()
const show = defineModel<boolean>({ default: false })
</script>
