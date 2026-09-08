<template>
  <v-dialog v-model="show" max-width="400">
    <v-card class="dialog-card">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-pencil" color="primary" class="mr-2" />
        Должность сотрудника
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="text-body-2 font-weight-medium mb-3">{{ editMemberTarget?.name }}</div>
        <v-text-field v-model="editMemberForm.position" label="Должность в отделе"
          variant="outlined" density="compact" placeholder="Менеджер, Специалист, Ведущий инженер..."
          hide-details />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" @click="$emit('save')">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  editMemberTarget: any
  editMemberForm: { position: string }
}>()
defineEmits<{ (e: 'save'): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
