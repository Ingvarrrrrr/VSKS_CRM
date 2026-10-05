<template>
  <v-dialog v-model="dialog" max-width="1200" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-table-check</v-icon>
        Сверка «выписка ↔ закупки»
        <span v-if="data?.as_of" class="text-caption text-medium-emphasis ml-2">на {{ fmtDate(data.as_of) }}</span>
        <v-spacer />
        <v-btn icon="mdi-refresh" variant="text" :loading="control.loading.value" @click="control.reload()" />
        <v-btn
          icon="mdi-file-excel"
          variant="text"
          :loading="control.exporting.value"
          title="Выгрузить в Excel"
          @click="onExport"
        />
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
          <!-- Контрольный итог (квик-план 06.10, statement-control): привязано
               N из M платёжек, сумма A из B ₽, не хватает C ₽ (K платёжек);
               номера непривязанных — кликабельны, переводят на вкладку
               «Выписка» и прокручивают/подсвечивают строку. -->
          <v-sheet
            v-if="data.totals.statement_count != null"
            rounded="lg"
            :color="unattachedCount > 0 ? 'orange-lighten-5' : 'green-lighten-5'"
            class="pa-3 mb-3"
          >
            <div class="text-body-2">
              <b>Привязано {{ data.totals.attached_count ?? 0 }} из {{ data.totals.statement_count }} платёжек</b>
              · {{ formatCurrency((data.totals.reconciled_total || 0) - (data.totals.unattached_total || 0)) }} из {{ formatCurrency(data.totals.reconciled_total || 0) }} ₽
              <template v-if="unattachedCount > 0">
                · <span class="text-error font-weight-bold">не хватает {{ formatCurrency(data.totals.unattached_total || 0) }} ₽ ({{ unattachedCount }} платёжек)</span>
              </template>
            </div>
            <div v-if="unattachedNumbers.length" class="d-flex flex-wrap gap-1 mt-2">
              <v-chip
                v-for="num in unattachedNumbers"
                :key="num"
                size="x-small"
                color="error"
                variant="tonal"
                class="cursor-pointer"
                @click="goToStatementNumber(num)"
              >{{ num }}</v-chip>
            </div>
          </v-sheet>

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
            <v-tab value="statement">Выписка</v-tab>
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
                :subsidy-id="props.subsidyId!"
                :control="control"
                @find="onFind"
                @create="onCreate"
              />
            </v-window-item>

            <v-window-item value="statement">
              <SubsidyStatementTab :subsidy-id="props.subsidyId" :highlight-number="highlightStatementNumber" />
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
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'
import SubsidyPaymentControlArticlesTab from '@/components/subsidies/SubsidyPaymentControlArticlesTab.vue'
import SubsidyPaymentControlRowsTab from '@/components/subsidies/SubsidyPaymentControlRowsTab.vue'
import SubsidyPaymentControlCandidatesDialog from '@/components/subsidies/SubsidyPaymentControlCandidatesDialog.vue'
import SubsidyPaymentControlCreatePurchaseDialog from '@/components/subsidies/SubsidyPaymentControlCreatePurchaseDialog.vue'
import SubsidyStatementTab from '@/components/subsidies/SubsidyStatementTab.vue'

const props = defineProps<{
  subsidyId: number | null | undefined
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()

const dialog = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()
const control = props.control
const data = computed(() => control.data.value)

const tab = ref('articles')
const toast = useToast()

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

// Контрольный итог (квик-план 06.10) — номера непривязанных платёжек, клик по
// чипу переводит на вкладку «Выписка» и подсвечивает/прокручивает строку там
// (не дублируем список строк здесь — один источник, SubsidyStatementTab.vue).
const unattachedCount = computed(() => data.value?.totals.unattached_count ?? 0)
const unattachedNumbers = computed(() => data.value?.totals.unattached_numbers ?? [])
const highlightStatementNumber = ref<string | null>(null)
function goToStatementNumber(num: string) {
  tab.value = 'statement'
  highlightStatementNumber.value = num
}

async function onExport() {
  if (!props.subsidyId) return
  try {
    await control.exportXlsx(props.subsidyId)
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось выгрузить сверку' }), 'error')
  }
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
