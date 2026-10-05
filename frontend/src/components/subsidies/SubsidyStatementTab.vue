<template>
  <div>
    <div class="d-flex flex-wrap align-center gap-2 mb-3">
      <v-select
        v-model="statusFilter"
        :items="statusOptions"
        label="Статус"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:200px"
      />
      <v-select
        v-model="procurementFilter"
        :items="procurementOptions"
        label="Закупочные"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:200px"
      />
      <v-select
        v-model="attachedFilter"
        :items="attachedOptions"
        label="Привязка"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:200px"
      />
      <v-text-field
        v-model="search"
        placeholder="Поиск по № / получателю / ИНН"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        style="max-width:260px"
      />
      <v-spacer />
      <span class="text-caption text-medium-emphasis">Показано: {{ filteredRows.length }} / {{ rows.length }}</span>
    </div>

    <div v-if="loading" class="d-flex justify-center py-8">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <v-alert v-else-if="loadError" type="error" variant="tonal" density="compact">{{ loadError }}</v-alert>
    <template v-else>
      <div class="statement-table-scroll">
        <v-table density="compact" class="statement-table">
          <thead>
            <tr>
              <th>№</th>
              <th>Дата</th>
              <th>Статус</th>
              <th>Получатель</th>
              <th>ИНН</th>
              <th class="text-right">Сумма</th>
              <th>Назначение</th>
              <th>Статья</th>
              <th>Закупка</th>
              <th>Файл выгрузки</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filteredRows" :key="r.id" :id="`statement-row-${r.payment_number}`">
              <td class="text-no-wrap">{{ r.payment_number || '—' }}</td>
              <td class="text-no-wrap">{{ fmtDate(r.payment_date) }}</td>
              <td class="text-caption">{{ statusLabel(r.status) }}</td>
              <td style="max-width:180px">{{ r.payee_name || '—' }}</td>
              <td class="text-no-wrap">{{ r.payee_inn || '—' }}</td>
              <td class="text-right text-no-wrap">{{ formatCurrency(r.amount) }}</td>
              <td style="max-width:240px">
                <PaymentPurposeCell :text="r.purpose_text" />
              </td>
              <td class="text-caption">{{ r.expense_name || r.expense_code || '—' }}</td>
              <td style="min-width:160px">
                <template v-if="r.attached && r.attached.length">
                  <div v-for="a in r.attached" :key="a.purchase_id" class="d-flex align-center gap-1 flex-wrap">
                    <a :href="`/orders/${a.purchase_id}/edit`" target="_blank">
                      <v-chip size="x-small" color="success" variant="tonal">{{ a.registry_number || '#' + a.purchase_id }}</v-chip>
                    </a>
                    <span v-if="a.sheet_ref" class="text-caption text-medium-emphasis">{{ a.sheet_ref }}</span>
                  </div>
                </template>
                <span v-else-if="r.is_procurement" class="text-error text-caption">—</span>
                <span v-else class="text-caption text-medium-emphasis">—</span>
              </td>
              <td class="text-caption text-medium-emphasis" style="max-width:140px">{{ r.import_file_name || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
      <div v-if="!filteredRows.length" class="text-caption text-medium-emphasis text-center py-6">
        Нет строк выписки по заданным фильтрам
      </div>
      <div v-else class="text-body-2 mt-2">
        <b>Итог по отфильтрованному:</b> {{ formatCurrency(filteredTotal) }} ({{ filteredRows.length }})
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Вкладка «Выписка» окна сверки (квик-план 06.10, statement-control) —
// таблица строк выписки ТОЛЬКО текущей субсидии, колонки как в выгрузке
// Scroller. Фильтры: статус/закупочность/привязка/поиск. Источник данных —
// useSubsidyStatement.ts (отдельный GET /statement, не payment-control).
import { computed, ref, watch, nextTick } from 'vue'
import { useSubsidyStatement, type StatementRow } from '@/composables/subsidies/useSubsidyStatement'
import { formatCurrency } from '@/composables/subsidies/format'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'

const props = defineProps<{
  subsidyId: number | null | undefined
  // Номер п/п — проскроллить и подсветить при открытии (переход с чипа
  // «непривязанные» из контрольного итога, см. SubsidyPaymentControlDialog.vue).
  highlightNumber?: string | null
}>()

const statement = useSubsidyStatement()
const rows = computed(() => statement.rows.value)
const loading = statement.loading
const loadError = statement.loadError

const statusFilter = ref<'all' | 'executed' | 'other'>('all')
const procurementFilter = ref<'all' | 'procurement' | 'other'>('all')
const attachedFilter = ref<'all' | 'attached' | 'unattached'>('all')
const search = ref('')

const statusOptions = [
  { title: 'Все', value: 'all' },
  { title: 'Исполнен', value: 'executed' },
  { title: 'Прочие', value: 'other' },
]
const procurementOptions = [
  { title: 'Все', value: 'all' },
  { title: 'Закупочные', value: 'procurement' },
  { title: 'Не закупочные', value: 'other' },
]
const attachedOptions = [
  { title: 'Все', value: 'all' },
  { title: 'Привязан', value: 'attached' },
  { title: 'Не привязан', value: 'unattached' },
]

function statusLabel(s: string): string {
  if (s === 'executed' || s === 'исполнен') return 'исполнен'
  return s || '—'
}

function isExecuted(r: StatementRow): boolean {
  return r.status === 'executed' || r.status === 'исполнен'
}

const filteredRows = computed(() => {
  let list = rows.value
  if (statusFilter.value === 'executed') list = list.filter(isExecuted)
  else if (statusFilter.value === 'other') list = list.filter(r => !isExecuted(r))
  if (procurementFilter.value === 'procurement') list = list.filter(r => r.is_procurement)
  else if (procurementFilter.value === 'other') list = list.filter(r => !r.is_procurement)
  if (attachedFilter.value === 'attached') list = list.filter(r => r.attached && r.attached.length > 0)
  else if (attachedFilter.value === 'unattached') list = list.filter(r => !r.attached || !r.attached.length)
  const q = search.value.trim().toLowerCase()
  if (q) {
    list = list.filter(r =>
      (r.payment_number || '').toLowerCase().includes(q) ||
      (r.payee_name || '').toLowerCase().includes(q) ||
      (r.payee_inn || '').toLowerCase().includes(q),
    )
  }
  return list
})

const filteredTotal = computed(() => filteredRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0))

function fmtDate(d: string | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

watch(() => props.subsidyId, (id) => statement.load(id), { immediate: true })

watch(() => props.highlightNumber, async (num) => {
  if (!num) return
  attachedFilter.value = 'all'
  statusFilter.value = 'all'
  procurementFilter.value = 'all'
  search.value = num
  await nextTick()
  const el = document.getElementById(`statement-row-${num}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})
</script>

<style scoped>
/* PWA: таблица шире экрана — своя горизонтальная прокрутка, не раздвигает страницу. */
.statement-table-scroll {
  overflow-x: auto;
}
.statement-table {
  min-width: 960px;
}
</style>
