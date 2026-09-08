<template>
  <v-dialog v-model="show" max-width="480">
    <v-card>
      <v-card-title>Дополнительное право на задачи</v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-3">
          Начальник отдела <strong>автоматически</strong> может редактировать задачи своих сотрудников. Здесь вы можете дать такое право <strong>дополнительно</strong> любому другому пользователю.
        </v-alert>
        <v-select v-model="delegateForm.delegate_user_id" :items="userDropdownItems" item-title="text" item-value="value"
          label="Кто получает право редактировать *" variant="outlined" density="compact" class="mb-3"
          hint="Выберите пользователя, которому даете право" persistent-hint />
        <v-select v-model="delegateForm.target_user_id" :items="userDropdownItems" item-title="text" item-value="value"
          label="Чьи задачи можно будет редактировать *" variant="outlined" density="compact"
          hint="Выберите сотрудника организации" persistent-hint />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" :disabled="!delegateForm.delegate_user_id || !delegateForm.target_user_id" @click="$emit('add')">Добавить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  delegateForm: { target_user_id: number | null; delegate_user_id: number | null }
  userDropdownItems: { text: string; value: number }[]
}>()
defineEmits<{ (e: 'add'): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
