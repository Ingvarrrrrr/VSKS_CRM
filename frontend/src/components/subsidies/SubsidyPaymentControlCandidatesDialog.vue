<template>
  <v-dialog v-model="dialog" max-width="640" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-magnify</v-icon>
        Найти закупку по платёжке
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <div v-if="loading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="!items.length" class="text-caption text-medium-emphasis py-4">
          Подходящих закупок не найдено
        </div>
        <v-list v-else density="compact">
          <v-list-item
            v-for="c in items"
            :key="c.purchase_id"
            class="mb-2 rounded border"
            :active="selectedId === c.purchase_id"
            @click="selectedId = c.purchase_id"
          >
            <template #prepend>
              <v-radio :model-value="selectedId === c.purchase_id" density="compact" />
            </template>
            <v-list-item-title class="font-weight-medium">
              {{ c.registry_number || `Закупка #${c.purchase_id}` }} — {{ c.subject || '—' }}
            </v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              {{ c.contractor_name || 'Контрагент не указан' }}
              · договор {{ formatCurrency(c.contract_price || 0) }}
              <template v-if="c.paid_by_statement != null"> · уже оплачено по выписке {{ formatCurrency(c.paid_by_statement) }}</template>
            </v-list-item-subtitle>
            <div v-if="c.reason" class="text-caption text-medium-emphasis mt-1">{{ c.reason }}</div>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!selectedId" :loading="attaching" @click="onAttach">
          Привязать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Найти закупку» из вкладки «Платёжки» (строка registry_only). Один
// источник действий — useSubsidyPaymentControl.ts (ПРАВИЛО №6): и кандидаты,
// и сама привязка идут через тот же composable, что грузит сверку.
import { ref, watch } from 'vue'
import { useSubsidyPaymentControl, type PaymentControlCandidate } from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

const props = defineProps<{
  subsidyId: number
  bankPaymentId: number | null
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()
const emit = defineEmits<{ (e: 'attached'): void }>()

const dialog = defineModel<boolean>({ default: false })
const toast = useToast()

const items = ref<PaymentControlCandidate[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)
const attaching = ref(false)

async function load() {
  if (!props.bankPaymentId) return
  loading.value = true
  items.value = []
  selectedId.value = null
  try {
    items.value = await props.control.fetchCandidates(props.subsidyId, props.bankPaymentId)
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось загрузить кандидатов' }), 'error')
  } finally {
    loading.value = false
  }
}

async function onAttach() {
  if (!props.bankPaymentId || !selectedId.value) return
  attaching.value = true
  try {
    const res = await props.control.attachPurchase(props.subsidyId, props.bankPaymentId, selectedId.value)
    for (const w of (res.warnings || [])) toast.addToast(w, 'warning')
    toast.success('Закупка привязана к платёжке')
    dialog.value = false
    emit('attached')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось привязать закупку' }), 'error')
  } finally {
    attaching.value = false
  }
}

watch(dialog, (v) => { if (v) load() })
</script>
