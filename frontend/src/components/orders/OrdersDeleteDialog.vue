<template>
  <v-dialog v-model="dialog.show" max-width="420">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
        <v-icon icon="mdi-alert-circle-outline" color="error" />
        Удалить закупки
      </v-card-title>
      <v-card-text class="px-6">
        <template v-if="dialog.bulk">
          Удалить <strong>{{ selectedCount }}</strong> выбранных закупок? Действие нельзя отменить.
        </template>
        <template v-else>
          Удалить закупку <strong>{{ dialog.single?.subject || dialog.single?.item_name || `#${dialog.single?.id}` }}</strong>? Действие нельзя отменить.
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="error" :loading="dialog.deleting" @click="onDelete">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Purchase } from '@/composables/orders/ordersTypes'

defineProps<{
  dialog: { show: boolean; single: Purchase | null; bulk: boolean; deleting: boolean }
  selectedCount: number
  onDelete: () => void
}>()
</script>
