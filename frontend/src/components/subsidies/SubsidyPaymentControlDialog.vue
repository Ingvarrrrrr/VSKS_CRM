<template>
  <v-dialog v-model="dialog" max-width="1200" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-table-check</v-icon>
        Сверка «выписка ↔ закупки»
        <span v-if="data?.as_of" class="text-caption text-medium-emphasis ml-2">на {{ fmtDate(data.as_of) }}</span>
        <v-spacer />
        <v-btn icon="mdi-refresh" variant="text" :loading="control.loading.value" @click="control.reload()" />
        <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <div v-if="control.loading.value && !data" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <v-alert v-else-if="control.loadError.value" type="error" variant="tonal" density="compact">
          {{ control.loadError.value }}
        </v-alert>

        <template v-else-if="data">
          <!-- Контрольные суммы -->
          <v-sheet rounded="lg" border class="pa-3 mb-4">
            <div class="d-flex flex-wrap gap-x-6 gap-y-2 text-body-2">
              <span><b>Исполнено по выписке всего:</b> {{ formatCurrency(data.totals.executed_total) }} ({{ data.totals.executed_count }})</span>
              <span><b>Сверяется с закупками:</b> {{ formatCurrency(data.totals.reconciled_total) }}</span>
              <span><b>Найдено в закупках:</b> {{ formatCurrency(data.totals.found_in_purchases) }}</span>
              <span :class="data.totals.difference ? 'text-error font-weight-bold' : ''">
                <b>Разница:</b> {{ formatCurrency(data.totals.difference) }}
              </span>
              <span class="text-medium-emphasis"><b>Не сверяется:</b> {{ formatCurrency(data.totals.not_reconciled_total) }}</span>
              <span class="text-medium-emphasis"><b>Не исполнены (справочно):</b> {{ formatCurrency(data.totals.not_executed_total) }} ({{ data.totals.not_executed_count }})</span>
            </div>
          </v-sheet>

          <v-tabs v-model="tab" class="mb-3">
            <v-tab value="articles">Статьи</v-tab>
            <v-tab value="rows">Платёжки</v-tab>
            <v-tab value="not_executed">Не исполнены</v-tab>
          </v-tabs>

          <v-window v-model="tab">
            <v-window-item value="articles">
              <SubsidyPaymentControlArticlesTab
                :subsidy-id="props.subsidyId!"
                :control="control"
                @saved="control.reload()"
              />
            </v-window-item>

            <v-window-item value="rows">
              <SubsidyPaymentControlRowsTab
                :rows="data.rows"
                :articles="data.articles"
                @find="onFind"
                @create="onCreate"
              />
            </v-window-item>

            <v-window-item value="not_executed">
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Дата</th>
                    <th>Получатель</th>
                    <th class="text-right">Сумма</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ne in data.not_executed" :key="ne.id">
                    <td>{{ ne.payment_number || '—' }}</td>
                    <td>{{ fmtDate(ne.payment_date) }}</td>
                    <td>{{ ne.payee_name || '—' }}</td>
                    <td class="text-right">{{ formatCurrency(ne.amount) }}</td>
                    <td>{{ ne.status }}</td>
                  </tr>
                </tbody>
              </v-table>
              <div v-if="!data.not_executed.length" class="text-caption text-medium-emphasis text-center py-6">
                Неисполненных записей нет
              </div>
            </v-window-item>
          </v-window>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <SubsidyPaymentControlCandidatesDialog
    v-if="props.subsidyId"
    v-model="candidatesDialog"
    :subsidy-id="props.subsidyId"
    :bank-payment-id="candidatesBpId"
    :control="control"
    @attached="control.reload()"
  />

  <SubsidyPaymentControlCreatePurchaseDialog
    v-if="props.subsidyId"
    v-model="createDialog"
    :subsidy-id="props.subsidyId"
    :row="createRow"
    :control="control"
    @created="control.reload()"
  />
</template>

<script setup lang="ts">
// Диалог сверки «выписка ↔ закупки» по субсидии — открывается из баннера
// (SubsidyPaymentControlBanner.vue), который держит общий composable
// useSubsidyPaymentControl.ts (ПРАВИЛО №6: один источник данных на баннер и
// диалог, не отдельный fetch здесь). Полноэкранный на мобиле.
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useSubsidyPaymentControl, type PaymentControlRow } from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import SubsidyPaymentControlArticlesTab from '@/components/subsidies/SubsidyPaymentControlArticlesTab.vue'
import SubsidyPaymentControlRowsTab from '@/components/subsidies/SubsidyPaymentControlRowsTab.vue'
import SubsidyPaymentControlCandidatesDialog from '@/components/subsidies/SubsidyPaymentControlCandidatesDialog.vue'
import SubsidyPaymentControlCreatePurchaseDialog from '@/components/subsidies/SubsidyPaymentControlCreatePurchaseDialog.vue'

const props = defineProps<{
  subsidyId: number | null | undefined
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()

const dialog = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()
const control = props.control
const data = computed(() => control.data.value)

const tab = ref('articles')

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

const candidatesDialog = ref(false)
const candidatesBpId = ref<number | null>(null)
function onFind(row: PaymentControlRow) {
  candidatesBpId.value = row.bank_payment_ids[0] ?? null
  candidatesDialog.value = true
}

const createDialog = ref(false)
const createRow = ref<PaymentControlRow | null>(null)
function onCreate(row: PaymentControlRow) {
  createRow.value = row
  createDialog.value = true
}
</script>
