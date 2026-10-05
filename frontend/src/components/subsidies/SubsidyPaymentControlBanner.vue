<template>
  <v-alert
    v-if="control.data.value && control.data.value.alarm"
    type="error"
    variant="tonal"
    density="comfortable"
    class="mb-4"
    icon="mdi-alert-decagram"
  >
    <div class="text-body-2">
      По выписке (на {{ fmtDate(control.data.value.as_of) }}) оплачено
      {{ formatCurrency(control.data.value.totals.reconciled_total) }},
      в закупках найдено {{ formatCurrency(control.data.value.totals.found_in_purchases) }}
      — разница {{ formatCurrency(control.data.value.totals.difference) }}:
      {{ control.data.value.counts.registry_only }} платёжек без закупки,
      {{ control.data.value.counts.amount_mismatch }} с расхождением суммы,
      {{ control.data.value.counts.duplicate }} возможных дублей<template v-if="control.data.value.totals.from_payment_unrefined_count">,
      {{ control.data.value.totals.from_payment_unrefined_count }} закупок по платёжкам — позиции не уточнены</template>.
    </div>
    <v-btn size="small" color="error" variant="flat" class="mt-2" prepend-icon="mdi-table-check" @click="dialog = true">
      Открыть сверку
    </v-btn>
  </v-alert>

  <div
    v-else-if="control.data.value && control.data.value.totals.executed_count > 0"
    class="d-flex align-center mb-4 pa-2 rounded"
    style="background: rgba(76, 175, 80, 0.08)"
  >
    <v-icon color="success" size="18" class="mr-2">mdi-check-circle</v-icon>
    <span class="text-caption text-medium-emphasis">
      Выписка сходится с закупками на {{ fmtDate(control.data.value.as_of) }}
    </span>
    <v-btn size="x-small" variant="text" color="success" class="ml-2" @click="dialog = true">сверка</v-btn>
  </div>

  <div v-else-if="control.data.value" class="text-caption text-medium-emphasis mb-4">
    Выписка по этой субсидии не загружена или не отнесена к ней (проверьте номер соглашения)
  </div>

  <SubsidyPaymentControlDialog
    v-model="dialog"
    :subsidy-id="props.subsidyId"
    :control="control"
  />
</template>

<script setup lang="ts">
// Баннер «выписка ↔ закупки» на странице «Субсидии» — рядом с
// PaidConfirmationsPanel (см. views/SubsidiesView.vue). Источник данных —
// общий composable useSubsidyPaymentControl.ts (ПРАВИЛО №6): и баннер, и
// диалог сверки читают один и тот же control.data, не дублируют fetch.
import { ref, watch } from 'vue'
import { useSubsidyPaymentControl } from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import SubsidyPaymentControlDialog from '@/components/subsidies/SubsidyPaymentControlDialog.vue'

const props = defineProps<{ subsidyId: number | null | undefined }>()

const control = useSubsidyPaymentControl()
const dialog = ref(false)

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

watch(() => props.subsidyId, (id) => control.load(id), { immediate: true })
</script>
