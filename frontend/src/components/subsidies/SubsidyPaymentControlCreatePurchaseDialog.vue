<template>
  <v-dialog v-model="dialog" max-width="560">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-cart-plus</v-icon>
        Создать закупку по платёжке
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Закупка будет внесена без заявки, с пометкой «внесена по платёжке
          {{ row?.payment_number || '—' }}», одной обобщённой позицией — позиции
          уточните потом вручную.
        </v-alert>
        <div class="text-body-2 mb-3" v-if="row">
          <div><b>Получатель:</b> {{ row.payee_name || '—' }}</div>
          <div><b>Сумма:</b> {{ formatCurrency(row.amount) }}</div>
          <div v-if="row.purpose_text" class="text-caption text-medium-emphasis mt-1">{{ row.purpose_text }}</div>
        </div>
        <div class="text-subtitle-2 mb-1">Направление ФЭО (необязательно)</div>
        <FeoTreeSelect
          v-model="feoCategoryId"
          :nodes="feoTreeNodes"
          :leaves="[]"
          root-label="Без выбора — «Не определена»"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="creating" @click="onCreate">
          Создать закупку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Создать закупку по платёжке» из вкладки «Платёжки» (строка
// registry_only). Категория ФЭО — переиспользован штатный пикер
// FeoTreeSelect.vue + useFeoTreeNodes.ts (ПРАВИЛО №6: не плодим второй пикер
// дерева ФЭО), без выбора создание пойдёт в штатную папку «Не определена»
// (бэкенд, get_or_create_unallocated).
import { computed, ref, watch } from 'vue'
import { useSubsidyPaymentControl, type PaymentControlRow } from '@/composables/subsidies/useSubsidyPaymentControl'
import { useFeoTreeNodes } from '@/composables/useFeoTreeNodes'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'

const props = defineProps<{
  subsidyId: number
  row: PaymentControlRow | null
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()
const emit = defineEmits<{ (e: 'created'): void }>()

const dialog = defineModel<boolean>({ default: false })
const toast = useToast()

const feoCategoryId = ref<number | null>(null)
const creating = ref(false)

const { feoTreeNodes } = useFeoTreeNodes(
  computed(() => props.subsidyId),
  feoCategoryId,
)

async function onCreate() {
  if (!props.row) return
  const bpId = props.row.bank_payment_ids[0]
  if (!bpId) return
  creating.value = true
  try {
    const res = await props.control.createPurchaseFromPayment(props.subsidyId, bpId, feoCategoryId.value)
    for (const w of (res.warnings || [])) toast.addToast(w, 'warning')
    toast.success(`Закупка ${res.registry_number || '#' + res.purchase_id} создана по платёжке`, {
      actionText: 'Открыть',
      onAction: () => window.open(`/orders/${res.purchase_id}/edit`, '_blank'),
    })
    dialog.value = false
    emit('created')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось создать закупку по платёжке' }), 'error')
  } finally {
    creating.value = false
  }
}

watch(dialog, (v) => { if (v) feoCategoryId.value = null })
</script>
