<!--
  WishApprovalCeilingWarning.vue — крупное предупреждение согласующему ДО
  нажатия «Согласовать» (владелец, 19.10.2026, решение по жёсткому потолку
  субсидии, п.1): «После согласования план субсидии станет выше ФЭО на X —
  закупка встанет в «Плане закупок», пока не освободят деньги».

  ПРАВИЛО №6: число — ТО ЖЕ, что у плитки «Запланировано» (считается на
  бэкенде через subsidy_ceiling_state, см. useWishApprovalCeilingPreview.ts).
  Кнопка «Где взять деньги» — ТОТ ЖЕ компонент/диалог, что у плитки
  (useFundingSources), второй диалог не заводим.
-->
<template>
  <v-alert
    v-if="preview && preview.applicable && preview.over_amount > 0.005"
    type="warning"
    variant="tonal"
    density="comfortable"
    class="mb-3"
    icon="mdi-alert-octagon"
  >
    <div class="font-weight-bold mb-1">
      После согласования план субсидии «{{ preview.subsidy_name }}» станет выше ФЭО
      на {{ formatCurrency(preview.over_amount) }}
    </div>
    <div class="text-body-2 mb-2">
      Закупка встанет в «Плане закупок» и не сможет продвинуться дальше (в работу/договор),
      пока план не уменьшат или не найдут деньги.
    </div>
    <v-btn size="small" variant="flat" color="warning" prepend-icon="mdi-cash-sync" @click="openWhereToGetMoney">
      Где взять деньги
    </v-btn>
  </v-alert>
</template>

<script setup lang="ts">
import { formatCurrency } from '@/composables/subsidies/format'
import { useFundingSources } from '@/composables/subsidies/useFundingSources'
import type { WishApprovalCeilingPreview } from '@/composables/wishes/useWishApprovalCeilingPreview'

const props = defineProps<{ preview: WishApprovalCeilingPreview | null }>()

const funding = useFundingSources()

function openWhereToGetMoney() {
  if (!props.preview || !props.preview.subsidy_id) return
  // Цель — субсидия целиком (categoryId/plannedItemId не заданы), amount —
  // ТОЧНОЕ число превышения потолка (не «можно перераспределить» по
  // умолчанию, которое берёт backend при отсутствии amount — см. докстринг
  // app.services.plan_funding_sources._resolve_target).
  funding.openFundingSources({
    subsidyId: props.preview.subsidy_id,
    amount: props.preview.over_amount,
  })
}
</script>
