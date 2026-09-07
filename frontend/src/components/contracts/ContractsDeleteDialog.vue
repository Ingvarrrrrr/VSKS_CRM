<template>
  <v-dialog v-model="dialog.show" max-width="400">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Удалить запись?</v-card-title>
      <v-card-text class="px-4">
        Удалить <strong>{{ dialog.item?.number }}</strong>? Закупки сохранятся.
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="error" variant="tonal" :loading="dialog.deleting" @click="onDelete">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Contract } from '@/composables/contracts/contractsTypes'

defineProps<{
  dialog: { show: boolean; deleting: boolean; item: Contract | null }
  onDelete: () => void
}>()
</script>
