<template>
  <!-- Bulk actions bar -->
  <div v-if="isAdmin && selectedUsers.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
    <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
    <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedUsers.length }}</span>
    <v-spacer />
    <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="$emit('bulk-delete')">
      Удалить выбранных
    </v-btn>
    <v-btn variant="text" size="small" @click="$emit('clear-selection')">Снять выделение</v-btn>
  </div>

  <!-- B6: кнопка дубликатов по ИНН -->
  <v-alert
    v-if="isAdmin && duplicateInnGroups.length > 0"
    type="warning"
    variant="tonal"
    density="compact"
    class="mb-3"
    icon="mdi-account-multiple-outline"
  >
    <div class="d-flex align-center flex-wrap" style="gap:8px">
      <span class="text-body-2">Найдены дубликаты по ИНН: <strong>{{ duplicateInnGroups.length }}</strong> группы</span>
      <v-btn size="x-small" variant="tonal" color="warning" @click="$emit('open-inn-dup')">
        Просмотреть
      </v-btn>
    </div>
  </v-alert>
</template>

<script setup lang="ts">
defineProps<{
  isAdmin: boolean
  selectedUsers: any[]
  duplicateInnGroups: { inn: string; group: any[] }[]
}>()
defineEmits<{
  (e: 'bulk-delete'): void
  (e: 'clear-selection'): void
  (e: 'open-inn-dup'): void
}>()
</script>
