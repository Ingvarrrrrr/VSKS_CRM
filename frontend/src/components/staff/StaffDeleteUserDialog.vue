<template>
  <v-dialog v-model="dialog.show" :max-width="dialog.warning ? 480 : 340">
    <v-card>
      <v-card-title class="pa-4">Убрать сотрудника из организации?</v-card-title>
      <v-card-text>
        {{ dialog.user?.full_name || dialog.user?.username }}
        <div class="text-caption text-medium-emphasis mt-1">
          Сотрудник будет откреплён от этой организации. Аккаунт удалится полностью, только если это его единственная организация (с отдельным подтверждением).
        </div>
        <v-alert v-if="dialog.warning" type="warning" variant="tonal" density="compact" class="mt-3 text-body-2">
          {{ dialog.warning }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" :loading="dialog.deleting" @click="$emit('confirm')">
          {{ dialog.warning ? 'Удалить безвозвратно' : 'Удалить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  dialog: { show: boolean; user: any; deleting: boolean; warning: string }
}>()
defineEmits<{ (e: 'confirm'): void }>()
</script>
