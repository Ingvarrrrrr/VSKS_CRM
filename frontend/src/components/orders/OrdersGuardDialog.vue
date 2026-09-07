<template>
  <v-dialog v-model="dialog.show" max-width="480">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Не заполнены обязательные поля</v-card-title>
      <v-card-text class="px-6">
        <p class="mb-3 text-body-2 text-medium-emphasis">
          Для перехода в статус «{{ dialog.targetStatus === 'contracted' && dialog.isFramework ? 'Заказ' : STATUS_LABEL[dialog.targetStatus] }}» заполните:
        </p>
        <v-list density="compact">
          <v-list-item
            v-for="f in dialog.missing"
            :key="f"
            prepend-icon="mdi-alert-circle-outline"
            :title="f"
          />
        </v-list>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Закрыть</v-btn>
        <v-btn color="primary" :to="`/orders/${dialog.purchaseId}/edit`" @click="dialog.show = false">
          Открыть форму
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { STATUS_LABEL } from '@/composables/orders/ordersLabels'

defineProps<{
  dialog: { show: boolean; purchaseId: number; targetStatus: string; missing: string[]; isFramework: boolean }
}>()
</script>
