<!-- Плашка «Оплачено больше, чем поставлено» (владелец, 07.10.2026, прод
     id=74 «ЛНР»: карточки «Поставлено» 3 381 872,26 / «Поставлено, не
     оплачено» 0,00 / «Оплачено» 3 385 009,26 — оплачено больше поставленного,
     причина — РЕЕ-2026-03421, work_in_progress, оплата по отметке 3 137,
     договора нет). Новый файл (Правило №5 — SubsidyKpiCards.vue уже > 500
     строк) по образцу ContractsDrillDialog.vue. GET /api/dashboard/
     paid-over-delivered-drill (backend/app/routers/dashboard_paid_over_
     delivered_drill.py) — фронт ничего не считает, только показывает готовые
     поля (Правило №6): total/card_total/prepayment_total/purchases_count/
     rows[excess/is_prepayment/reason]. -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #991b1b, #7c2d12); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">Оплачено больше, чем поставлено</div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ purchasesCount }} {{ purchasesWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-alert type="error" variant="tonal" density="compact" class="ma-3 text-caption">
        Сверх поставленного: {{ formatCurrency(total) }}
        <template v-if="prepaymentTotal > 0.5"> — из них авансом: {{ formatCurrency(prepaymentTotal) }}</template>
      </v-alert>
      <!-- Σ excess по закупкам МОЖЕТ отличаться от (Оплачено − Поставлено)
           карточек субсидии целиком — переплата одной закупки не гасит
           недоплату другой (см. docstring paid_over_delivered.py). Если
           список пуст, а разность карточек > 0 — это тоже сигнал. -->
      <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="ma-3 text-caption">
        Σ по списку закупок ({{ formatCurrency(total) }}) отличается от карточки, посчитанной по этой же
        формуле ({{ formatCurrency(cardTotal) }}) — обновите страницу, если число не совпадает.
      </v-alert>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="error" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка закупок…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <div v-else style="overflow-x:auto">
          <v-table density="compact" style="min-width:900px">
            <thead>
              <tr>
                <th class="px-4">№ / РЕЕ</th>
                <th class="px-4">Предмет</th>
                <th class="px-4">Статус</th>
                <th class="text-right px-4">Поставлено</th>
                <th class="text-right px-4">Оплачено</th>
                <th class="text-right px-4">Сверх</th>
                <th class="px-4">Причина</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.purchase_id" class="paid-over-delivered-row" @click="emit('row-click', r.purchase_id)">
                <td class="px-4 py-2" style="font-size:13px">{{ r.registry_number || r.purchase_number || r.purchase_id }}</td>
                <td class="px-4 text-caption" style="max-width:260px; white-space:normal">{{ r.subject || '—' }}</td>
                <td class="px-4 text-caption">{{ r.status_label }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.delivered) }}</td>
                <td class="text-right px-4">{{ formatCurrency(r.paid) }}</td>
                <td class="text-right px-4 font-weight-medium text-error">{{ formatCurrency(r.excess) }}</td>
                <td class="px-4 text-caption">
                  <v-chip v-if="r.is_prepayment" size="x-small" color="orange" variant="tonal" class="mr-1">аванс</v-chip>
                  {{ r.reason }}
                </td>
              </tr>
              <tr v-if="rows.length === 0">
                <td colspan="7" class="text-center py-6 text-medium-emphasis">Нет закупок с переплатой</td>
              </tr>
            </tbody>
            <tfoot v-if="rows.length">
              <tr>
                <td colspan="5" class="px-4 text-right font-weight-medium">Итого: {{ purchasesCount }} {{ purchasesWord }}</td>
                <td class="text-right px-4 font-weight-bold text-error">{{ formatCurrency(total) }}</td>
                <td class="px-4" />
              </tr>
            </tfoot>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { formatCurrency } from '@/composables/subsidies/format'

const { mobile } = useDisplay()

interface PaidOverDeliveredRow {
  purchase_id: number
  subsidy_id: number | null
  registry_number: string | null
  purchase_number: number | string | null
  subject: string
  status: string
  status_label: string
  is_prepayment: boolean
  delivered: number
  paid: number
  excess: number
  reason: string
}

const props = withDefaults(defineProps<{
  visible: boolean
  subsidyId?: number | null
  // Главный дашборд (DashboardView.vue, scope=dashboard): несколько субсидий
  // (фильтр) или вовсе без фильтра (вся видимость scope) — subsidyId здесь не
  // годится (одна субсидия). Страница «Субсидии» (SubsidyKpiCards.vue,
  // scope=managed) продолжает передавать subsidyId как раньше.
  subsidyIds?: number[] | null
  scope?: 'dashboard' | 'managed'
}>(), {
  subsidyId: null,
  subsidyIds: null,
  scope: 'managed',
})
const emit = defineEmits<{ (e: 'close'): void; (e: 'row-click', purchaseId: number): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const rows = ref<PaidOverDeliveredRow[]>([])
const total = ref(0)
const cardTotal = ref(0)
const prepaymentTotal = ref(0)
const purchasesCount = ref(0)

const mismatch = computed(() => Math.abs(total.value - cardTotal.value) > 0.005)

function pluralizePurchases(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'закупок'
  if (mod10 === 1) return 'закупка'
  if (mod10 >= 2 && mod10 <= 4) return 'закупки'
  return 'закупок'
}
const purchasesWord = computed(() => pluralizePurchases(purchasesCount.value))

async function load() {
  // scope=managed (страница субсидии) требует конкретную субсидию; scope=
  // dashboard допускает «без фильтра» (все видимые) — subsidyIds=[] в этом
  // случае осознанно означает «не сужать», не «пустой список id».
  if (props.scope === 'managed' && !props.subsidyId) {
    rows.value = []
    total.value = 0
    cardTotal.value = 0
    prepaymentTotal.value = 0
    purchasesCount.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const ids = (props.subsidyIds && props.subsidyIds.length > 0)
      ? props.subsidyIds
      : (props.subsidyId ? [props.subsidyId] : [])
    const params = new URLSearchParams({ scope: props.scope })
    if (ids.length > 0) params.set('subsidy_ids', ids.join(','))
    const res = await apiFetch<{
      total: number; card_total: number; prepayment_total: number
      purchases_count: number; rows: PaidOverDeliveredRow[]
    }>(`/dashboard/paid-over-delivered-drill?${params.toString()}`)
    rows.value = res.rows || []
    total.value = res.total || 0
    cardTotal.value = res.card_total || 0
    prepaymentTotal.value = res.prepayment_total || 0
    purchasesCount.value = res.purchases_count || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить список закупок' })
    rows.value = []
    total.value = 0
    cardTotal.value = 0
    prepaymentTotal.value = 0
    purchasesCount.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.subsidyIds], () => { if (props.visible) load() }, { immediate: true, deep: true })
</script>

<style scoped>
.paid-over-delivered-row { cursor: pointer; }
.paid-over-delivered-row:hover { background: rgba(239, 68, 68, 0.06); }
</style>
