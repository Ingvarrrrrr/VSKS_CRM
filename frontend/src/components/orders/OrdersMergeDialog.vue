<template>
  <v-dialog v-model="show" max-width="640" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon start color="indigo">mdi-call-merge</v-icon>
        Объединение закупок
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>

      <v-card-text class="pa-4 pt-0">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Позиции, файлы и платежи выбранных закупок будут перенесены в одну целевую закупку.
          Исходные номера закупок и номера заявок будут зафиксированы в комментарии и журнале изменений.
        </v-alert>

        <div class="text-subtitle-2 mb-2 font-weight-bold">Целевая закупка (останется в реестре):</div>
        <v-select
          v-model="targetId"
          :items="orderOptions"
          item-title="title"
          item-value="id"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
        />

        <div class="text-subtitle-2 mb-2 font-weight-bold">Состав объединения ({{ selected.length }}):</div>
        <v-list density="compact" class="border rounded mb-3 bg-grey-lighten-5">
          <v-list-item v-for="order in selected" :key="order.id" class="py-1">
            <template #prepend>
              <v-chip
                :color="order.id === targetId ? 'indigo' : 'grey'"
                size="x-small"
                variant="flat"
                class="mr-2"
              >
                {{ order.id === targetId ? 'Целевая' : 'Вливается' }}
              </v-chip>
            </template>
            <v-list-item-title class="text-body-2 font-weight-medium">
              {{ order.registry_number || `#${order.id}` }}
              <span class="text-caption text-medium-emphasis ml-2">{{ order.contractor_name || 'Без контрагента' }}</span>
            </v-list-item-title>
            <template #append>
              <div class="d-flex align-center gap-2">
                <v-chip v-if="(order as any).wish_id" size="x-small" color="deep-orange" variant="tonal">
                  Заявка #{{ (order as any).wish_id }}
                </v-chip>
                <span class="font-weight-bold text-body-2">{{ formatMoney(order.planned_total_price || order.contract_price || 0) }}</span>
              </div>
            </template>
          </v-list-item>
        </v-list>

        <div class="d-flex justify-space-between align-center px-1 py-2 font-weight-bold">
          <span>Итоговая сумма объединённой закупки:</span>
          <span class="text-primary text-h6">{{ formatMoney(totalSum) }}</span>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" :disabled="loading" @click="show = false">Отмена</v-btn>
        <v-btn
          color="indigo"
          variant="flat"
          :loading="loading"
          :disabled="!targetId || selected.length < 2"
          @click="doMerge"
        >
          Объединить закупки
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import type { Purchase } from '@/composables/orders/ordersTypes'
import type { ToastType } from '@/composables/useToast'

const props = defineProps<{
  showSnack: (text: string, color?: ToastType) => void
  onMerged: () => void
}>()

const show = ref(false)
const loading = ref(false)
const selected = ref<Purchase[]>([])
const targetId = ref<number | null>(null)

const orderOptions = computed(() =>
  selected.value.map(o => ({
    id: o.id,
    title: `${o.registry_number || `#${o.id}`} — ${o.contractor_name || 'без контрагента'} (${formatMoney(o.planned_total_price || o.contract_price || 0)})`,
  }))
)

const totalSum = computed(() =>
  selected.value.reduce((sum, o) => sum + (o.planned_total_price || o.contract_price || 0), 0)
)

function open(orders: Purchase[]) {
  selected.value = [...orders]
  targetId.value = orders[0]?.id ?? null
  show.value = true
}

async function doMerge() {
  if (!targetId.value || selected.value.length < 2) return
  const sourceIds = selected.value.map(o => o.id).filter(id => id !== targetId.value)
  loading.value = true
  try {
    const res = await apiFetch<any>('/purchases/merge', {
      method: 'POST',
      body: JSON.stringify({
        target_purchase_id: targetId.value,
        source_purchase_ids: sourceIds,
      }),
    })
    show.value = false
    props.showSnack(res?.message || 'Закупки успешно объединены', 'success')
    props.onMerged()
  } catch (e: any) {
    const msg = e?.payload?.message || e?.detail || e?.message || 'Ошибка объединения закупок'
    props.showSnack(msg, 'error')
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>
