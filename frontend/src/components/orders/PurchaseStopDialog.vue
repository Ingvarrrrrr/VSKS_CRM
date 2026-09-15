<template>
  <v-dialog :model-value="modelValue" max-width="520" :fullscreen="mobile" @update:model-value="v => emit('update:modelValue', v)">
    <v-card v-if="purchase">
      <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
        <v-icon :color="mode === 'stop' ? 'error' : 'success'">
          {{ mode === 'stop' ? 'mdi-alert-octagon' : 'mdi-play-circle' }}
        </v-icon>
        {{ mode === 'stop' ? 'Остановить закупку' : 'Возобновить закупку' }}
      </v-card-title>
      <v-card-text class="pa-4">
        <template v-if="mode === 'stop'">
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
            Закупка №{{ purchase.purchase_number || purchase.id }} будет остановлена и уйдёт из
            плана закупок. Данные не удаляются — остановку можно отменить кнопкой «Возобновить».
          </v-alert>
          <v-textarea
            :model-value="reason"
            label="Причина остановки (необязательно)"
            variant="outlined"
            density="compact"
            rows="3"
            @update:model-value="v => emit('update:reason', v)"
          />
        </template>
        <template v-else>
          <v-alert type="info" variant="tonal" density="compact">
            Закупка №{{ purchase.purchase_number || purchase.id }} снова станет активной и
            вернётся в план закупок.
          </v-alert>
        </template>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn
          variant="flat"
          :color="mode === 'stop' ? 'error' : 'success'"
          :loading="loading"
          @click="emit('confirm')"
        >
          {{ mode === 'stop' ? 'Остановить' : 'Возобновить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Общий диалог остановки/возобновления закупки (владелец, 2026-09-15) — по
// образцу STOP DIALOG в WishActionDialogs.vue, но один компонент на ДВЕ
// закупочные точки входа (список «Закупки» и карточка закупки), не копия
// разметки в каждый view (ПРАВИЛО №6). Логика вызова API — в
// composables/orders/usePurchaseStop.ts, этот компонент только форма.
import { useDisplay } from 'vuetify'
import type { Purchase } from '@/composables/orders/ordersTypes'

defineProps<{
  modelValue: boolean
  mode: 'stop' | 'resume'
  purchase: Purchase | null
  reason: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:reason', v: string): void
  (e: 'confirm'): void
}>()

const { mobile } = useDisplay()
</script>
