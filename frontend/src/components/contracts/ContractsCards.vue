<template>
  <div>
    <v-row dense>
      <v-col v-for="c in pagedCards" :key="c.id" cols="12" sm="6" lg="4">
        <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="emit('edit', c)">
          <!-- Владелец, 2026-09-02: та же плашка, что и в табличном виде — см. ContractsTable #item.subject -->
          <div v-if="c.approval_state === 'pending'" class="contract-approval-pending-banner ma-2 mb-0">
            <v-icon icon="mdi-shield-alert-outline" size="18" class="mr-1" />
            <span class="contract-approval-pending-banner__title">ТРЕБУЕТСЯ СОГЛАСОВАНИЕ</span>
            <span class="contract-approval-pending-banner__meta">Ждёт согласования по цепочке руководителей</span>
          </div>
          <v-card-item class="pb-1">
            <v-card-title class="text-body-2 d-flex align-center ga-2 flex-wrap">
              <span class="font-weight-bold">{{ c.number || ('#' + c.id) }}</span>
              <v-chip :color="contractTypeColor(c.contract_type)" size="x-small" variant="tonal">{{ contractTypeLabel(c.contract_type) }}</v-chip>
              <v-chip v-if="c.status" :color="c.status === 'active' ? 'success' : 'grey'" size="x-small" variant="tonal">{{ statusLabel(c.status) }}</v-chip>
            </v-card-title>
          </v-card-item>
          <v-card-text class="py-1 flex-grow-1">
            <div v-if="c.subject" class="text-caption text-medium-emphasis mb-1" style="overflow-wrap:anywhere">{{ c.subject.length > 80 ? c.subject.slice(0, 80) + '...' : c.subject }}</div>
            <div class="text-caption text-medium-emphasis">Контрагент</div>
            <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">{{ c.contractor_name || '—' }}</div>
            <div class="text-caption text-medium-emphasis">Субсидия</div>
            <div class="mb-1 d-flex flex-wrap ga-1">
              <v-chip v-if="c.subsidy_name" size="x-small" color="primary" variant="tonal">{{ c.subsidy_name }}</v-chip>
              <v-chip v-for="es in (c.extra_subsidies || [])" :key="es.subsidy_id" size="x-small" color="secondary" variant="tonal">{{ es.subsidy_name }}</v-chip>
              <span v-if="!c.subsidy_name && !(c.extra_subsidies?.length)" class="text-body-2 text-medium-emphasis">—</span>
            </div>
            <div class="d-flex flex-wrap ga-3 mt-2">
              <div>
                <div class="text-caption text-medium-emphasis">Предельная сумма</div>
                <div class="text-body-2 font-weight-bold">{{ c.max_amount ? formatMoney(c.max_amount) : '—' }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Заказано</div>
                <div class="text-body-2" :style="c.max_amount && Number(c.total_ordered) > Number(c.max_amount) ? 'color:var(--color-loss);font-weight:700' : ''">{{ c.total_ordered ? formatMoney(c.total_ordered) : '—' }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Оплачено</div>
                <div class="text-body-2" style="color:var(--color-profit)">{{ c.total_paid ? formatMoney(c.total_paid) : '—' }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Остаток</div>
                <div class="text-body-2" :style="Number(c.remaining_ordered) < 0 ? 'color:var(--color-loss);font-weight:700' : ''">{{ c.remaining_ordered != null ? formatMoney(c.remaining_ordered) : '—' }}</div>
              </div>
            </div>
            <div class="d-flex justify-space-between mt-2">
              <div>
                <div class="text-caption text-medium-emphasis">Дата</div>
                <div class="text-body-2">{{ fmtDate(c.date) }}</div>
              </div>
              <div class="text-right">
                <div class="text-caption text-medium-emphasis">Срок</div>
                <div class="text-body-2" :style="c.end_date && isExpired(c.end_date) ? 'color:#DC2626' : ''">{{ fmtDate(c.end_date) }}</div>
              </div>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="py-1" @click.stop>
            <v-spacer />
            <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="emit('confirm-delete', c)" />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <div v-if="!pagedCards.length" class="text-center py-10">
      <v-icon icon="mdi-file-document-outline" size="48" color="grey-lighten-1" class="mb-3" />
      <div class="text-medium-emphasis">Договоры не найдены</div>
    </div>
    <v-pagination v-if="cardsTotalPages > 1" v-model="cardsPage" :length="cardsTotalPages" density="compact" total-visible="7" class="d-flex justify-center mt-4" />
  </div>
</template>

<script setup lang="ts">
import type { Contract } from '@/composables/contracts/contractsTypes'
import { contractTypeColor, contractTypeLabel, statusLabel, fmtDate, isExpired, formatMoney } from '@/composables/contracts/contractsLabels'

defineProps<{
  pagedCards: Contract[]
  cardsTotalPages: number
  isAdmin: boolean
}>()

const cardsPage = defineModel<number>('cardsPage', { required: true })

const emit = defineEmits<{
  edit: [item: Contract]
  'confirm-delete': [item: Contract]
}>()
</script>

<style scoped>
.contract-approval-pending-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(15, 23, 42, 0.92);
  color: #fff;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.contract-approval-pending-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.contract-approval-pending-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.85;
}
</style>
