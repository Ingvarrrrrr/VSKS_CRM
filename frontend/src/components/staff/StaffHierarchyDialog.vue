<template>
  <v-dialog v-model="dialog.show" max-width="500" :fullscreen="mobile">
    <v-card v-if="dialog.user">
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-account-supervisor" color="teal" class="mr-2" />
        Подчиненные: {{ dialog.user.full_name || dialog.user.username }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="dialog.show = false" />
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <div class="mb-3">
          <v-autocomplete
            v-model="dialog.newSubId"
            :items="dialog.availableUsers"
            item-title="display"
            item-value="id"
            label="Добавить подчиненного"
            variant="outlined" density="compact"
            hide-details
          />
          <v-btn size="small" color="teal" variant="tonal" class="mt-2"
            :disabled="!dialog.newSubId"
            :loading="dialog.adding"
            @click="$emit('add-subordinate')">
            Добавить
          </v-btn>
        </div>
        <v-divider class="mb-3" />
        <div class="text-body-2 font-weight-medium mb-2">Прямые подчиненные:</div>
        <div v-if="dialog.subordinates.length === 0" class="text-caption text-medium-emphasis">
          Нет подчиненных
        </div>
        <v-chip
          v-for="s in dialog.subordinates" :key="s.id"
          class="ma-1" size="small" :color="roleColor(s.role)" variant="tonal"
          closable @click:close="$emit('remove-subordinate', s.id)">
          {{ s.full_name || s.username }}
        </v-chip>
        <div v-if="dialog.allSubordinates.length > dialog.subordinates.length" class="mt-3">
          <div class="text-body-2 font-weight-medium mb-1">Все подчиненные (все уровни):</div>
          <v-chip
            v-for="s in allSubsNotDirect" :key="s.id"
            class="ma-1" size="x-small" color="grey" variant="tonal">
            {{ s.full_name || s.username }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { roleColor } from '@/composables/staff/staffLabels'

defineProps<{
  dialog: {
    show: boolean; user: any; subordinates: any[]; allSubordinates: any[]
    newSubId: number | null; adding: boolean; availableUsers: { id: number; display: string }[]
  }
  allSubsNotDirect: any[]
  mobile: boolean
}>()
defineEmits<{ (e: 'add-subordinate'): void; (e: 'remove-subordinate', id: number): void }>()
</script>
