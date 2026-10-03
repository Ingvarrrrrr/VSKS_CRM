<template>
  <v-alert type="success" variant="tonal" class="mb-3">
    Импорт завершён. Закупок создано: <strong>{{ factImport.commitResult?.purchases_created ?? 0 }}</strong>,
    платежей: <strong>{{ factImport.commitResult?.payments_created ?? 0 }}</strong>,
    новых контрагентов: <strong>{{ factImport.commitResult?.contractors_created ?? 0 }}</strong><template v-if="factImport.commitResult?.existing_matches_linked">,
    оставлено существующих закупок: <strong>{{ factImport.commitResult.existing_matches_linked }}</strong></template>.
  </v-alert>
  <div class="fisrep-table-wrap">
    <v-table density="compact">
      <thead>
        <tr><th>№ закупки</th><th>Поставщик</th><th>Статус</th><th>Договор</th><th>Оплачено</th><th>Чего не хватает</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in factImport.runDetail?.report ?? []" :key="r.purchase_id">
          <td>
            <router-link :to="`/orders/${r.purchase_id}`">{{ r.registry_number || r.purchase_id }}</router-link>
          </td>
          <template v-if="r.existing_match">
            <td colspan="5" class="text-caption">
              оставлена существующая {{ r.registry_number || `#${r.purchase_id}` }} — привязано
              {{ r.items_linked ?? 0 }} позиций, создано {{ r.planned_items_created ?? 0 }} плановых
            </td>
          </template>
          <template v-else>
            <td>{{ r.supplier || '—' }}</td>
            <td>{{ statusLabel(r.status) }}</td>
            <td>{{ fmt(r.contract_amount) }}</td>
            <td>{{ fmt(r.paid_amount) }}</td>
            <td>
              <v-chip v-for="(m, i) in r.missing" :key="i" size="x-small" color="warning" variant="tonal" class="mr-1 mb-1">
                {{ m }}
              </v-chip>
              <span v-if="!r.missing?.length" class="text-caption text-medium-emphasis">—</span>
            </td>
          </template>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { useFactImport } from '@/composables/subsidies/useFactImport'
// ПРАВИЛО №6: подпись статуса закупки и формат суммы — общие источники.
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import { formatMoney } from '@/utils/formatMoney'
const { factImport } = useFactImport()
function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}
function statusLabel(s?: string | null): string {
  return purchaseStatusLabel(s) || 'План закупок'
}
</script>

<style scoped>
.fisrep-table-wrap { max-height: 55vh; overflow: auto; border: 1px solid #eee; border-radius: 6px; }
</style>
