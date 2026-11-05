<template>
  <div>
    <!-- Панель управления над таблицей + цветовая легенда -->
    <div class="d-flex flex-wrap align-center gap-2 mb-2">
      <v-text-field
        v-model="search"
        placeholder="Поиск по № / контрагенту / ИНН / назначению…"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        style="max-width: 360px"
      />
      <v-btn
        v-if="activeFilterCount > 0"
        variant="tonal"
        color="warning"
        density="compact"
        prepend-icon="mdi-filter-off"
        @click="clearAllFilters"
      >
        Сбросить фильтры ({{ activeFilterCount }})
      </v-btn>
      <v-spacer />
      <div class="d-flex align-center gap-3 text-caption text-medium-emphasis">
        <span>Показано: <b>{{ filteredRows.length }}</b> / {{ rows.length }}</span>
        <v-divider vertical class="my-1" />
        <span>Итог: <b class="text-body-2 text-high-emphasis">{{ formatCurrency(filteredTotal) }}</b></span>
      </div>
    </div>

    <!-- Интерактивная легенда цветов (клик фильтрует строки) -->
    <div class="d-flex flex-wrap align-center gap-2 mb-3 text-caption">
      <span class="text-medium-emphasis mr-1">Подсветка строк (кликните на платёж, чтобы сматчить с 1 или несколькими закупками):</span>
      <v-chip
        size="small"
        :variant="colorFilter === 'all' ? 'flat' : 'outlined'"
        color="primary"
        class="cursor-pointer"
        @click="colorFilter = 'all'"
      >
        Все ({{ rows.length }})
      </v-chip>
      <v-chip
        size="small"
        :variant="colorFilter === 'goods' ? 'flat' : 'tonal'"
        class="cursor-pointer legend-chip-goods"
        @click="colorFilter = colorFilter === 'goods' ? 'all' : 'goods'"
      >
        <span class="legend-dot legend-dot-goods mr-1" />
        Зелёный — Товары ({{ goodsMatchedCount }})
      </v-chip>
      <v-chip
        size="small"
        :variant="colorFilter === 'services' ? 'flat' : 'tonal'"
        class="cursor-pointer legend-chip-services"
        @click="colorFilter = colorFilter === 'services' ? 'all' : 'services'"
      >
        <span class="legend-dot legend-dot-services mr-1" />
        Песочный — Услуги ({{ servicesMatchedCount }})
      </v-chip>
      <v-chip
        size="small"
        :variant="colorFilter === 'unmatched' ? 'flat' : 'outlined'"
        color="error"
        class="cursor-pointer"
        @click="colorFilter = colorFilter === 'unmatched' ? 'all' : 'unmatched'"
      >
        Без закупки ({{ unmatchedProcurementCount }})
      </v-chip>
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
              <th style="min-width: 90px">
                <ColumnHeaderMenu
                  col-key="payment_number"
                  title="№"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'payment_number')"
                  :model-value="colFilters['payment_number'] ?? null"
                  :sort-by="getSortBy('payment_number')"
                  @update:model-value="v => setFilter('payment_number', v)"
                  @sort="dir => applySort('payment_number', dir)"
                />
              </th>
              <th style="min-width: 120px">
                <ColumnHeaderMenu
                  col-key="payment_date"
                  title="Дата"
                  col-type="date"
                  :hide-action="false"
                  :model-value="colFilters['payment_date'] ?? null"
                  :sort-by="getSortBy('payment_date')"
                  @update:model-value="v => setFilter('payment_date', v)"
                  @sort="dir => applySort('payment_date', dir)"
                />
              </th>
              <th style="min-width: 120px">
                <ColumnHeaderMenu
                  col-key="status"
                  title="Статус"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'status')"
                  :model-value="colFilters['status'] ?? null"
                  :sort-by="getSortBy('status')"
                  @update:model-value="v => setFilter('status', v)"
                  @sort="dir => applySort('status', dir)"
                />
              </th>
              <th style="min-width: 180px">
                <ColumnHeaderMenu
                  col-key="payee_name"
                  title="Получатель"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'payee_name')"
                  :model-value="colFilters['payee_name'] ?? null"
                  :sort-by="getSortBy('payee_name')"
                  @update:model-value="v => setFilter('payee_name', v)"
                  @sort="dir => applySort('payee_name', dir)"
                />
              </th>
              <th style="min-width: 120px">
                <ColumnHeaderMenu
                  col-key="payee_inn"
                  title="ИНН"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'payee_inn')"
                  :model-value="colFilters['payee_inn'] ?? null"
                  :sort-by="getSortBy('payee_inn')"
                  @update:model-value="v => setFilter('payee_inn', v)"
                  @sort="dir => applySort('payee_inn', dir)"
                />
              </th>
              <th style="min-width: 180px">
                <ColumnHeaderMenu
                  col-key="basis_doc_display"
                  title="Документ-основание"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'basis_doc_display')"
                  :model-value="colFilters['basis_doc_display'] ?? null"
                  :sort-by="getSortBy('basis_doc_display')"
                  @update:model-value="v => setFilter('basis_doc_display', v)"
                  @sort="dir => applySort('basis_doc_display', dir)"
                />
              </th>
              <th style="min-width: 130px" class="text-right">
                <ColumnHeaderMenu
                  col-key="amount"
                  title="Сумма"
                  col-type="number"
                  align="end"
                  :hide-action="false"
                  :model-value="colFilters['amount'] ?? null"
                  :sort-by="getSortBy('amount')"
                  @update:model-value="v => setFilter('amount', v)"
                  @sort="dir => applySort('amount', dir)"
                />
              </th>
              <th style="min-width: 240px">
                <ColumnHeaderMenu
                  col-key="purpose_text"
                  title="Назначение"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'purpose_text')"
                  :model-value="colFilters['purpose_text'] ?? null"
                  :sort-by="getSortBy('purpose_text')"
                  @update:model-value="v => setFilter('purpose_text', v)"
                  @sort="dir => applySort('purpose_text', dir)"
                />
              </th>
              <th style="min-width: 160px">
                <ColumnHeaderMenu
                  col-key="expense_name"
                  title="Статья"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'expense_name')"
                  :model-value="colFilters['expense_name'] ?? null"
                  :sort-by="getSortBy('expense_name')"
                  @update:model-value="v => setFilter('expense_name', v)"
                  @sort="dir => applySort('expense_name', dir)"
                />
              </th>
              <th style="min-width: 130px">
                <ColumnHeaderMenu
                  col-key="expense_code_short"
                  title="Краткий код"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'expense_code_short')"
                  :model-value="colFilters['expense_code_short'] ?? null"
                  :sort-by="getSortBy('expense_code_short')"
                  @update:model-value="v => setFilter('expense_code_short', v)"
                  @sort="dir => applySort('expense_code_short', dir)"
                />
              </th>
              <th style="min-width: 140px">
                <ColumnHeaderMenu
                  col-key="attached"
                  title="Закупка"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'attached')"
                  :model-value="colFilters['attached'] ?? null"
                  :sort-by="getSortBy('attached')"
                  @update:model-value="v => setFilter('attached', v)"
                  @sort="dir => applySort('attached', dir)"
                />
              </th>
              <th style="min-width: 160px">
                <ColumnHeaderMenu
                  col-key="import_file_name"
                  title="Файл выгрузки"
                  col-type="enum"
                  :hide-action="false"
                  :items="uniqValues(rows, 'import_file_name')"
                  :model-value="colFilters['import_file_name'] ?? null"
                  :sort-by="getSortBy('import_file_name')"
                  @update:model-value="v => setFilter('import_file_name', v)"
                  @sort="dir => applySort('import_file_name', dir)"
                />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in filteredRows"
              :key="r.id"
              :id="`statement-row-${r.payment_number}`"
              :class="statementRowClass(r)"
              class="statement-clickable-row"
              title="Нажмите, чтобы сопоставить платёж с одной или несколькими закупками"
              @click="emit('match', r.id)"
            >
              <td class="text-no-wrap font-weight-medium">{{ r.payment_number || '—' }}</td>
              <td class="text-no-wrap">{{ fmtDate(r.payment_date) }}</td>
              <td class="text-caption">{{ statusLabel(r.status) }}</td>
              <td style="max-width:200px" class="text-truncate" :title="r.payee_name || ''">{{ r.payee_name || '—' }}</td>
              <td class="text-no-wrap font-mono">{{ r.payee_inn || '—' }}</td>
              <td style="max-width:220px" class="text-truncate" :title="getRowValue(r, 'basis_doc_display') || ''">{{ getRowValue(r, 'basis_doc_display') || '—' }}</td>
              <td class="text-right text-no-wrap font-weight-medium">{{ formatCurrency(r.amount) }}</td>
              <td style="max-width:280px" @click.stop>
                <PaymentPurposeCell :text="r.purpose_text" />
              </td>
              <td class="text-caption" style="max-width:180px">{{ r.expense_name || r.expense_code || '—' }}</td>
              <td class="text-caption font-weight-medium font-mono">{{ getRowValue(r, 'expense_code_short') || '—' }}</td>
              <td style="min-width:190px" @click.stop>
                <template v-if="r.attached && r.attached.length">
                  <div class="d-flex align-center gap-1 flex-wrap mb-1">
                    <span
                      class="matched-kind-badge"
                      :class="rowMatchedKind(r) === 'goods' ? 'badge-goods' : 'badge-services'"
                    >
                      {{ rowMatchedKind(r) === 'goods' ? 'Товар' : 'Услуга' }}
                    </span>
                    <v-btn
                      size="x-small"
                      variant="text"
                      color="primary"
                      density="compact"
                      prepend-icon="mdi-link-edit"
                      @click.stop="emit('match', r.id)"
                    >
                      Изменить
                    </v-btn>
                  </div>
                  <div v-for="a in r.attached" :key="a.purchase_id" class="d-flex align-center gap-1 flex-wrap">
                    <a :href="`/orders/${a.purchase_id}/edit`" target="_blank" @click.stop>
                      <v-chip size="x-small" color="success" variant="tonal">{{ a.registry_number || '#' + a.purchase_id }}</v-chip>
                    </a>
                    <span v-if="a.sheet_ref" class="text-caption text-medium-emphasis">{{ a.sheet_ref }}</span>
                  </div>
                </template>
                <div v-else class="d-flex align-center gap-1">
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    :color="r.is_procurement ? 'primary' : 'grey'"
                    prepend-icon="mdi-link-plus"
                    @click.stop="emit('match', r.id)"
                  >
                    Сматчить
                  </v-btn>
                </div>
              </td>
              <td class="text-caption text-medium-emphasis text-truncate" style="max-width:160px" :title="r.import_file_name || ''">{{ r.import_file_name || '—' }}</td>
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
// Вкладка «Выписка» окна сверки — таблица строк банковской выписки текущей
// субсидии с фильтрами и сортировкой через ColumnHeaderMenu (единый стандарт Excel).
import { computed, ref, watch, nextTick } from 'vue'
import { useSubsidyStatement, type StatementRow } from '@/composables/subsidies/useSubsidyStatement'
import { formatCurrency } from '@/composables/subsidies/format'
import PaymentPurposeCell from '@/components/subsidies/PaymentPurposeCell.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import type { FilterValue } from '@/composables/useColumnConfig'

const props = defineProps<{
  subsidyId: number | null | undefined
  // Номер п/п — проскроллить и подсветить при открытии
  highlightNumber?: string | null
}>()

const emit = defineEmits<{
  (e: 'match', bankPaymentId: number): void
}>()

const statement = useSubsidyStatement()
const rows = computed(() => statement.rows.value)
const loading = statement.loading
const loadError = statement.loadError

const search = ref('')
const colorFilter = ref<'all' | 'goods' | 'services' | 'unmatched'>('all')
const colFilters = ref<Record<string, FilterValue>>({})
const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)

function rowMatchedKind(r: StatementRow): 'goods' | 'services' | null {
  if (!r.attached || !r.attached.length) return null
  if (r.matched_kind === 'goods' || r.matched_kind === 'services') return r.matched_kind
  for (const a of r.attached) {
    const it = (a.item_type || '').toLowerCase().trim()
    if (it === 'товар' || it === 'товары' || it === 'goods') return 'goods'
    if (it === 'услуга' || it === 'услуги' || it === 'работа' || it === 'services') return 'services'
  }
  const ec = String(r.expense_code || r.expense_code_short || '').trim()
  if (ec.startsWith('03') || ec.startsWith('300')) return 'goods'
  return 'services'
}

function statementRowClass(r: StatementRow): string {
  const kind = rowMatchedKind(r)
  if (kind === 'goods') return 'row-matched-goods'
  if (kind === 'services') return 'row-matched-services'
  return ''
}

const goodsMatchedCount = computed(() => rows.value.filter(r => rowMatchedKind(r) === 'goods').length)
const servicesMatchedCount = computed(() => rows.value.filter(r => rowMatchedKind(r) === 'services').length)
const unmatchedProcurementCount = computed(() => rows.value.filter(r => (!r.attached || !r.attached.length) && r.is_procurement).length)

defineExpose({
  reload: () => statement.load(props.subsidyId),
})

function setFilter(key: string, val: FilterValue | null) {
  if (!val) {
    const copy = { ...colFilters.value }
    delete copy[key]
    colFilters.value = copy
  } else {
    colFilters.value = { ...colFilters.value, [key]: val }
  }
}

function clearAllFilters() {
  colFilters.value = {}
  search.value = ''
  colorFilter.value = 'all'
  localSort.value = null
}

const activeFilterCount = computed(() => {
  let count = Object.keys(colFilters.value).length
  if (search.value?.trim()) count++
  if (colorFilter.value !== 'all') count++
  return count
})

function getSortBy(k: string): 'asc' | 'desc' | null {
  return localSort.value?.key === k ? localSort.value.order : null
}

function applySort(k: string, dir: 'asc' | 'desc' | null) {
  localSort.value = dir ? { key: k, order: dir } : null
}

function statusLabel(s: string | null | undefined): string {
  const low = (s || '').toLowerCase().trim()
  if (low === 'executed' || low === 'исполнен') return 'исполнен'
  return s || '—'
}

function getRowValue(r: StatementRow, key: string): any {
  if (key === 'basis_doc_display') {
    return r.basis_doc_text || (r.basis_doc_number ? `№ ${r.basis_doc_number}${r.basis_doc_date ? ' от ' + fmtDate(r.basis_doc_date) : ''}` : null)
  }
  if (key === 'expense_code_short') {
    return r.expense_code_short || (r.expense_code ? r.expense_code.slice(0, 4) : null)
  }
  if (key === 'attached') {
    return (r.attached && r.attached.length > 0) ? 'Привязан' : 'Не привязан'
  }
  if (key === 'status') {
    return statusLabel(r.status)
  }
  return (r as any)[key] ?? null
}

function uniqValues(items: StatementRow[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  items.forEach(r => {
    const v = getRowValue(r, key)
    if (v !== null && v !== undefined && v !== '') {
      set.add(v)
    }
  })
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? ''), 'ru', { numeric: true }))
}

function matchesColumnFilters(r: StatementRow): boolean {
  for (const [key, f] of Object.entries(colFilters.value)) {
    const v = getRowValue(r, key)
    if (f.type === 'text') {
      if (!f.q) continue
      const rawQ = String(f.q).trim()
      if (!rawQ) continue
      const tokens = rawQ.split(/[,;\s|]+/).map(t => t.trim().toLowerCase()).filter(Boolean)
      const valStr = String(v ?? '').toLowerCase()
      if (tokens.length > 1) {
        if (!tokens.some(t => valStr.includes(t))) return false
      } else if (tokens.length === 1) {
        if (!valStr.includes(tokens[0])) return false
      }
    } else if (f.type === 'enum') {
      if (!f.values || f.values.length === 0) continue
      const strValues = f.values.map((x: any) => x === null || x === undefined ? '' : String(x))
      const valStr = v === null || v === undefined ? '' : String(v)
      if (!f.values.includes(v) && !strValues.includes(valStr)) return false
    } else if (f.type === 'number') {
      const n = typeof v === 'number' ? v : parseFloat(v)
      if (f.min != null && !(n >= f.min)) return false
      if (f.max != null && !(n <= f.max)) return false
    } else if (f.type === 'date') {
      if (!v) { if (f.from || f.to) return false; continue }
      const d = String(v).slice(0, 10)
      if (f.from && d < f.from) return false
      if (f.to && d > f.to) return false
    }
  }
  return true
}

const filteredRows = computed(() => {
  let list = rows.value.filter(matchesColumnFilters)
  if (colorFilter.value === 'goods') {
    list = list.filter(r => rowMatchedKind(r) === 'goods')
  } else if (colorFilter.value === 'services') {
    list = list.filter(r => rowMatchedKind(r) === 'services')
  } else if (colorFilter.value === 'unmatched') {
    list = list.filter(r => (!r.attached || !r.attached.length) && r.is_procurement)
  }
  const q = search.value?.trim().toLowerCase()
  if (q) {
    const tokens = q.split(/[,;\s|]+/).map(t => t.trim()).filter(Boolean)
    list = list.filter(r => {
      const matchTarget = [
        r.payment_number || '',
        r.payee_name || '',
        r.payee_inn || '',
        r.expense_code || '',
        getRowValue(r, 'expense_code_short') || '',
        r.purpose_text || '',
        r.import_file_name || '',
      ].join(' ').toLowerCase()
      return tokens.some(t => matchTarget.includes(t))
    })
  }
  if (localSort.value) {
    const { key, order } = localSort.value
    list = [...list].sort((a, b) => {
      const av = getRowValue(a, key)
      const bv = getRowValue(b, key)
      if (typeof av === 'number' && typeof bv === 'number') {
        return order === 'asc' ? av - bv : bv - av
      }
      const cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'ru', { numeric: true })
      return order === 'asc' ? cmp : -cmp
    })
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
  colFilters.value = {}
  search.value = num
  await nextTick()
  const el = document.getElementById(`statement-row-${num}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})
</script>

<style scoped>
.statement-table-scroll {
  overflow-x: auto;
}
.statement-table {
  min-width: 960px;
}
.statement-table th {
  vertical-align: middle;
}
.statement-table td {
  vertical-align: middle;
}
.font-mono {
  font-family: monospace;
}
.statement-clickable-row {
  cursor: pointer;
  transition: filter 0.12s ease;
}
.statement-clickable-row:hover {
  filter: brightness(0.96);
}
/* Зелёная заливка для сопоставленных товаров */
.row-matched-goods,
.row-matched-goods > td {
  background-color: #dcfce7 !important;
}
.row-matched-goods > td:first-child {
  border-left: 4px solid #16a34a !important;
}
/* Песочная заливка для сопоставленных услуг */
.row-matched-services,
.row-matched-services > td {
  background-color: #f9ecc9 !important;
}
.row-matched-services > td:first-child {
  border-left: 4px solid #d97706 !important;
}
.matched-kind-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
}
.badge-goods {
  background-color: #16a34a;
  color: #fff;
}
.badge-services {
  background-color: #b45309;
  color: #fff;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.legend-dot-goods {
  background-color: #16a34a;
}
.legend-dot-services {
  background-color: #d97706;
}
.legend-chip-goods {
  background-color: #dcfce7 !important;
  color: #14532d !important;
  border: 1px solid #86efac !important;
}
.legend-chip-services {
  background-color: #f9ecc9 !important;
  color: #78350f !important;
  border: 1px solid #fcd34d !important;
}
</style>
