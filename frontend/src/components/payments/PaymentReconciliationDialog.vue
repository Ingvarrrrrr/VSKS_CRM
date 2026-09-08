<template>
  <!-- 27.4-21: Reconciliation dialog -->
  <v-dialog v-model="dialogOpen" max-width="1100" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="warning">mdi-table-check</v-icon>
        Сверка платежей: реестр vs закупки
        <span v-if="importId" class="text-caption text-medium-emphasis ml-2">Импорт #{{ importId }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="dialogOpen = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <div v-if="loading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate color="warning" />
        </div>
        <div v-else-if="reconciliation">
          <div class="d-flex ga-2 mb-3">
            <v-chip color="success" variant="tonal" size="small" prepend-icon="mdi-check">
              Совпало: {{ reconciliation.match_count }}
            </v-chip>
            <v-chip color="error" variant="tonal" size="small" prepend-icon="mdi-currency-rub">
              Расходятся суммы: {{ reconciliation.mismatch_count }}
            </v-chip>
            <v-chip color="error" variant="tonal" size="small" prepend-icon="mdi-alert">
              Только в реестре: {{ reconciliation.registry_only_count }}
            </v-chip>
            <v-chip color="warning" variant="tonal" size="small" prepend-icon="mdi-help">
              Только в закупках: {{ reconciliation.purchases_only_count }}
            </v-chip>
            <v-chip color="orange" variant="tonal" size="small" prepend-icon="mdi-account-alert">
              Заявлено, не подтверждено: {{ reconciliation.declared_unconfirmed_count }}
            </v-chip>
            <v-spacer />
            <v-chip size="small" variant="tonal">
              Показано: {{ filteredRows.length }} / {{ reconciliation.total }}
            </v-chip>
          </div>

          <!-- 27.4-22: filter -->
          <v-text-field
            v-model="filterQuery"
            placeholder="Фильтр по получателю / номеру / статусу..."
            prepend-inner-icon="mdi-magnify"
            density="compact" variant="outlined" hide-details clearable
            class="mb-3" />

          <v-table density="compact">
            <thead>
              <tr>
                <th>№ платежа</th>
                <th class="text-right">Реестр (₽)</th>
                <th class="text-right">Привязано (₽)</th>
                <th class="text-right">Δ (₽)</th>
                <th>Получатель</th>
                <th>Закупки</th>
                <th>Статус</th>
                <th style="width:140px">Действие</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in filteredRows" :key="r.payment_number"
                  :class="reconciliationRowClass(r.status)">
                <td><b>{{ r.payment_number }}</b></td>
                <td class="text-right">{{ formatMoney(r.registry_amount) }}</td>
                <td class="text-right">{{ formatMoney(r.purchases_amount) }}</td>
                <td class="text-right" :class="r.amount_diff > 0.02 ? 'text-error font-weight-bold' : ''">
                  {{ r.amount_diff > 0.02 ? formatMoney(r.amount_diff) : '—' }}
                </td>
                <td class="text-caption">{{ (r.registry_payees || []).join(', ') || '—' }}</td>
                <td>
                  <a v-for="pid in (r.linked_purchase_ids || [])" :key="pid"
                     :href="`/orders/${pid}/edit`" target="_blank" class="mr-1">
                    <v-chip size="x-small" color="primary" variant="tonal">#{{ pid }}</v-chip>
                  </a>
                  <span v-if="!(r.linked_purchase_ids || []).length" class="text-medium-emphasis">—</span>
                </td>
                <td>
                  <v-chip :color="reconciliationStatusColor(r.status)" size="x-small" variant="flat">
                    {{ reconciliationStatusLabel(r.status) }}
                  </v-chip>
                </td>
                <td>
                  <v-btn v-if="(r.registry_ids?.length === 1) && r.status !== 'match'"
                         size="x-small" variant="tonal" color="primary"
                         prepend-icon="mdi-link-variant"
                         @click="emit('match', r.registry_ids[0])">
                    Привязать
                  </v-btn>
                  <v-menu v-else-if="(r.registry_ids?.length || 0) > 1">
                    <template #activator="{ props: ap }">
                      <v-btn v-bind="ap" size="x-small" variant="tonal" color="primary"
                             prepend-icon="mdi-link-variant" append-icon="mdi-menu-down">
                        Привязать ({{ r.registry_ids.length }})
                      </v-btn>
                    </template>
                    <v-list density="compact">
                      <v-list-item v-for="bpId in r.registry_ids" :key="bpId"
                                   :title="`Платёж #${bpId}`"
                                   @click="emit('match', bpId)" />
                    </v-list>
                  </v-menu>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialogOpen = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { formatMoney } from '@/composables/payments/paymentsFormat'

const dialogOpen = defineModel<boolean>({ required: true })
const filterQuery = defineModel<string>('filter', { required: true })

defineProps<{
  loading: boolean
  reconciliation: any
  filteredRows: any[]
  importId: number | null
  mobile: boolean
  reconciliationRowClass: (status: string) => string
  reconciliationStatusColor: (status: string) => string
  reconciliationStatusLabel: (status: string) => string
}>()

const emit = defineEmits<{
  match: [bpId: number]
}>()
</script>
