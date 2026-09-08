<template>
  <!-- Актуализация цены (владелец, сессия 2026-08-29: «цена может быть уже
       неактуальна, надо показывать дату актуализации и уметь её обновить») -->
  <v-dialog v-model="dialog.show" max-width="560" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        Актуализация цены
        <div v-if="dialog.product" class="text-caption text-medium-emphasis mt-1" style="white-space:normal">
          {{ dialog.product.name }}
        </div>
      </v-card-title>
      <v-card-text class="px-6">
        <v-alert v-if="dialog.product?.price_freshness" type="info" variant="tonal" density="compact" class="mb-3">
          Текущий статус: {{ dialog.product.price_freshness.label }}
        </v-alert>
        <v-row dense>
          <v-col cols="12" sm="6">
            <v-text-field v-model.number="form.price" label="Цена, ₽ *" type="number"
              variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field v-model="form.collected_at" label="Дата актуализации" type="date"
              variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-select v-model="form.source" :items="priceSourceOptions"
              label="Источник *" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field v-model="form.source_ref" label="Номер/ссылка"
              placeholder="напр. 123-ОК или Запрос КП №7"
              variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12">
            <ContractorPicker v-model="form.contractor_id" label="Контрагент (поставщик)" />
          </v-col>
          <v-col cols="12">
            <v-textarea v-model="form.note" label="Примечание" rows="2" auto-grow
              variant="outlined" density="compact" />
          </v-col>
        </v-row>

        <v-divider class="my-3" />
        <div class="d-flex align-center justify-space-between mb-2">
          <span class="text-subtitle-2">История актуализаций</span>
          <v-progress-circular v-if="dialog.historyLoading" indeterminate size="16" width="2" />
        </div>
        <div v-if="!dialog.historyLoading && !dialog.history.length" class="text-caption text-medium-emphasis">
          Актуализаций ещё не было.
        </div>
        <v-table v-else density="compact">
          <thead>
            <tr><th>Дата</th><th>Цена</th><th>Источник</th><th>Кто</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in dialog.history" :key="h.id">
              <td>{{ formatDateDDMMYYYY(h.collected_at || h.created_at) || '—' }}</td>
              <td>{{ Number(h.price).toLocaleString('ru-RU') }} ₽</td>
              <td>{{ PRICE_SOURCE_LABELS[h.source] || h.source }}{{ h.source_ref ? ` · ${h.source_ref}` : '' }}</td>
              <td>{{ h.created_by || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="dialog.saving" :disabled="!form.price || !form.source" @click="$emit('save')">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import ContractorPicker from '@/components/ContractorPicker.vue'
import { PRICE_SOURCE_LABELS, formatDateDDMMYYYY } from '@/composables/usePriceFreshness'
import type { Product, PriceHistoryEntry } from '@/composables/products/productsTypes'

defineProps<{
  dialog: {
    show: boolean; product: Product | null; history: PriceHistoryEntry[]
    historyLoading: boolean; saving: boolean
  }
  form: {
    price: number | null; collected_at: string; source: string
    source_ref: string; contractor_id: number | null; note: string
  }
  priceSourceOptions: { value: string; title: string }[]
  mobile: boolean
}>()
defineEmits<{ (e: 'save'): void }>()
</script>
