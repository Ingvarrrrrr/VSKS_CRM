<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
      <div>
        <h1 class="text-h5 font-weight-bold">
          Реестр платежей
          <span v-if="importId" class="text-medium-emphasis font-weight-regular">· Импорт #{{ importId }}</span>
        </h1>
        <span class="text-body-2 text-medium-emphasis">{{ totalCount }} записей</span>
      </div>
      <v-btn prepend-icon="mdi-view-column" variant="outlined" color="primary" @click="colPickerOpen = true">
        Колонки
      </v-btn>
    </div>

    <!-- Stale parsed alert: записи где parsed_contract_number совпадает с номером субсидии -->
    <v-alert
      v-if="hasStaleParsed"
      type="warning"
      variant="tonal"
      closable
      density="compact"
      class="mb-3"
      @click:close="staleParsedDismissed = true"
    >
      В реестре есть записи где номер субсидии попал в колонку «Договор (авто)».
      Откройте импорт → нажмите «Перепарсить» для исправления.
    </v-alert>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ</span>
          <v-spacer />
          <!-- Import badge -->
          <v-chip
            v-if="importId"
            size="small"
            color="blue"
            variant="tonal"
            closable
            @click:close="clearImport"
          >Фильтр: Импорт #{{ importId }}</v-chip>
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить
          </v-btn>
        </div>
        <div class="d-flex flex-wrap gap-2 align-end">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по любому полю"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:220px; max-width:340px"
          />
          <v-select
            v-model="filterSubsidyId"
            :items="subsidiesList"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:180px; max-width:260px"
          />
          <v-text-field
            v-model="fDateFrom"
            label="Дата от"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до"
            type="date"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:145px; max-width:145px"
          />
          <v-select
            v-model="fStatus"
            :items="statusOptions"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fMatched"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Сматчено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
          />
          <v-select
            v-model="fConfirmed"
            :items="yesNoOptions"
            item-title="label"
            item-value="value"
            label="Подтверждено"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:165px; max-width:200px"
          />
          <v-text-field
            v-model="fInn"
            label="ИНН получателя"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="min-width:160px; max-width:200px"
            @keyup.enter="applyFilters"
          />
          <v-btn color="primary" variant="elevated" @click="applyFilters" :loading="loading">
            Применить
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <v-data-table
      :headers="activeHeaders"
      :items="searchedItems"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      fixed-header
      height="calc(100vh - 320px)"
      :items-per-page="50"
      :items-per-page-options="[25, 50, 100]"
      :page="page"
      @update:page="page = $event"
    >
      <!-- Index -->
      <template #item.index="{ index }">
        <span class="text-medium-emphasis">{{ (page - 1) * 50 + index + 1 }}</span>
      </template>

      <!-- Date -->
      <template #item.payment_date="{ item }">
        {{ fmtDate(item.payment_date) }}
      </template>

      <!-- Payer -->
      <template #item.payer_name="{ item }">
        <div class="text-body-2">
          {{ item.payer_name_resolved || item.payer_name || '—' }}
        </div>
        <div v-if="item.payer_name_resolved && item.payer_name_resolved !== item.payer_name" class="text-caption text-medium-emphasis" :title="item.payer_name || ''">
          ({{ item.payer_name }})
        </div>
      </template>

      <!-- Payee -->
      <template #item.payee_name="{ item }">
        <div class="text-body-2">
          {{ item.payee_name_resolved || item.payee_name || '—' }}
        </div>
        <div v-if="item.payee_inn" class="text-caption text-medium-emphasis">ИНН {{ item.payee_inn }}</div>
      </template>

      <!-- Amount -->
      <template #item.amount="{ item }">
        <span class="font-weight-medium">{{ formatMoney(item.amount) }}</span>
      </template>

      <!-- Status chip -->
      <template #item.status="{ item }">
        <v-chip size="x-small" :color="statusColor(item.status)" variant="tonal">
          {{ item.status || '—' }}
        </v-chip>
      </template>

      <!-- Parsed contract / advance report / agreement -->
      <template #item.parsed_contract_number="{ item }">
        <span class="text-caption">{{ docDisplay(item) }}</span>
      </template>

      <!-- Matched chip -->
      <template #item.matched="{ item }">
        <v-chip
          v-if="item.matched_contract_id"
          size="x-small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-check"
        >Да</v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">Нет</v-chip>
      </template>

      <!-- Confirmed chip (key = matched_confirmed) -->
      <template #item.matched_confirmed="{ item }">
        <v-chip
          v-if="item.matched_confirmed"
          size="x-small"
          color="blue"
          variant="tonal"
          prepend-icon="mdi-check-decagram"
        >Да</v-chip>
        <v-chip v-else size="x-small" color="grey" variant="tonal">Нет</v-chip>
      </template>

      <!-- Basis doc date -->
      <template #item.basis_doc_date="{ item }">
        <span class="text-caption">{{ fmtDate(item.basis_doc_date) }}</span>
      </template>

      <!-- Parsed contract date -->
      <template #item.parsed_contract_date="{ item }">
        <span class="text-caption">{{ fmtDate(item.parsed_contract_date) }}</span>
      </template>

      <!-- Created at -->
      <template #item.created_at="{ item }">
        <span class="text-caption">{{ fmtDate(item.created_at) }}</span>
      </template>

      <!-- Purpose text (wrap) -->
      <template #item.purpose_text="{ item }">
        <div class="text-caption" style="max-width:280px">
          {{ item.purpose_text || '—' }}
        </div>
      </template>

      <!-- Basis doc text (wrap) -->
      <template #item.basis_doc_text="{ item }">
        <div class="text-caption" style="max-width:220px">
          {{ item.basis_doc_text || '—' }}
        </div>
      </template>

      <!-- Actions -->
      <template #item.actions="{ item }">
        <div class="d-flex gap-1 align-center">
          <!-- Confirm button (only if matched) -->
          <v-btn
            v-if="can('payment.confirm')"
            icon
            size="x-small"
            variant="text"
            color="success"
            :disabled="!item.matched_contract_id"
            :title="item.matched_contract_id ? 'Подтвердить' : 'Сначала привяжите договор'"
            @click.stop="openConfirm(item)"
          >
            <v-icon>mdi-check</v-icon>
          </v-btn>

          <!-- Match/re-link button -->
          <v-btn
            icon
            size="x-small"
            variant="text"
            color="primary"
            title="Привязать договор"
            @click.stop="openMatch(item)"
          >
            <v-icon>mdi-link-variant</v-icon>
          </v-btn>

          <!-- Unbind button -->
          <v-btn
            v-if="can('payment.unbind') && item.matched_confirmed"
            icon
            size="x-small"
            variant="text"
            color="warning"
            title="Откатить подтверждение"
            :loading="unbindingId === item.id"
            @click.stop="unbind(item)"
          >
            <v-icon>mdi-undo</v-icon>
          </v-btn>
        </div>
      </template>

      <!-- Expanded row -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <div class="pa-3 bg-grey-lighten-5">
              <div class="d-flex flex-wrap gap-x-8 gap-y-1 text-body-2 mb-2">
                <span><b>Назначение платежа:</b> {{ item.purpose_text || '—' }}</span>
              </div>
              <div class="d-flex flex-wrap gap-x-8 gap-y-1 text-caption text-medium-emphasis">
                <span v-if="item.kbk"><b>КБК:</b> {{ item.kbk }}</span>
                <span v-if="item.payer_kpp"><b>КПП плательщика:</b> {{ item.payer_kpp }}</span>
                <span v-if="item.payee_kpp"><b>КПП получателя:</b> {{ item.payee_kpp }}</span>
              </div>
            </div>
          </td>
        </tr>
      </template>

      <!-- No data -->
      <template #no-data>
        <div class="text-center py-8 text-medium-emphasis">
          <v-icon size="48" class="mb-2">mdi-bank-outline</v-icon>
          <div>Платежи не найдены</div>
          <div class="text-caption">Измените параметры фильтра</div>
        </div>
      </template>
    </v-data-table>

    <!-- Column picker dialog -->
    <v-dialog v-model="colPickerOpen" max-width="640">
      <v-card>
        <v-card-title class="text-body-1 font-weight-bold px-4 pt-3 pb-1">Видимые колонки и ширина</v-card-title>
        <v-divider />
        <v-card-text class="pa-0" style="max-height:500px; overflow-y:auto">
          <v-list density="compact" class="py-1">
            <v-list-item
              v-for="col in allColumns"
              :key="col.key"
              class="px-3"
              @click="toggleColumn(col.key)"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="visibleColumnKeys.includes(col.key)"
                  density="compact"
                  @click.stop="toggleColumn(col.key)"
                />
              </template>
              <template #default>
                <div class="d-flex align-center gap-3 w-100">
                  <span class="text-body-2 flex-grow-1">{{ col.title || col.key }}</span>
                  <v-text-field
                    v-if="col.key !== 'data-table-expand'"
                    :model-value="colWidths[col.key] ?? (_colMetaDefaults[col.key]?.width ?? '')"
                    type="number"
                    min="40"
                    max="600"
                    label="px"
                    variant="plain"
                    density="compact"
                    hide-details
                    style="max-width:70px"
                    @click.stop
                    @update:model-value="(v: any) => saveColWidth(col.key, Number(v))"
                  />
                </div>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-3 py-2">
          <v-btn size="small" variant="text" @click="resetColumns">Сбросить колонки</v-btn>
          <v-btn size="small" variant="text" color="warning" @click="colWidths = {}; localStorage.removeItem(LS_WIDTHS_KEY)">Сбросить ширины</v-btn>
          <v-spacer />
          <v-btn size="small" color="primary" variant="elevated" @click="colPickerOpen = false">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Match dialog -->
    <PaymentMatchDialog
      v-model="matchDialog"
      :bank-payment-id="selectedPaymentId"
      @updated="onUpdated"
    />

    <!-- Unbind confirm dialog -->
    <v-dialog v-model="unbindDialog" max-width="420">
      <v-card>
        <v-card-title>Откатить подтверждение?</v-card-title>
        <v-card-text>
          Платёжные записи, созданные при подтверждении, будут удалены. Статусы закупок пересчитаются автоматически.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="unbindDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="elevated" :loading="unbindLoading" @click="doUnbind">Откатить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import PaymentMatchDialog from '@/components/PaymentMatchDialog.vue'

// ── Route & auth ───────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { success, error } = useToast()

function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

// ── Import filter from query ────────────────────────────────────────────────
const importId = computed<number | null>(() => {
  const v = route.query.import_id
  return v ? Number(v) : null
})

function clearImport() {
  const q = { ...route.query }
  delete q.import_id
  router.replace({ query: q })
}

// ── Filter state ────────────────────────────────────────────────────────────
const fDateFrom = ref<string>('')
const fDateTo = ref<string>('')
const fStatus = ref<string | null>(null)
const fMatched = ref<string | null>(null)
const fConfirmed = ref<string | null>(null)
const fInn = ref<string>('')

const statusOptions = [
  { label: 'ИСПОЛНЕН', value: 'ИСПОЛНЕН' },
  { label: 'АННУЛИРОВАН', value: 'АННУЛИРОВАН' },
  { label: 'Прочие', value: 'OTHER' },
]
const yesNoOptions = [
  { label: 'Только сматченные', value: 'true' },
  { label: 'Только не сматченные', value: 'false' },
]

// ── Global search + subsidy filter ─────────────────────────────────────────
const searchQuery = ref('')
const filterSubsidyId = ref<number | null>(null)

interface SubsidyItem { id: number; name: string }
const subsidiesList = ref<SubsidyItem[]>([])

async function loadSubsidies() {
  try {
    const data = await apiFetch<any[]>('/subsidies/')
    subsidiesList.value = (data || []).map((s: any) => ({ id: s.id, name: s.name }))
  } catch {}
}

const searchedItems = computed(() => {
  let items = payments.value as any[]
  if (filterSubsidyId.value) {
    items = items.filter(i => i.matched_subsidy_id === filterSubsidyId.value)
  }
  if (!searchQuery.value.trim()) return items
  const q = searchQuery.value.toLowerCase()
  return items.filter((item: any) => {
    const haystack = [
      item.payer_name, item.payer_name_resolved, item.payer_inn,
      item.payee_name, item.payee_name_resolved, item.payee_inn,
      item.purpose_text, item.basis_doc_text, item.basis_doc_number,
      item.parsed_contract_number, item.payment_number, item.subsidy_code,
    ].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(q)
  })
})

const hasFilters = computed(() =>
  fDateFrom.value || fDateTo.value || fStatus.value || fMatched.value || fConfirmed.value || fInn.value
)

function clearFilters() {
  fDateFrom.value = ''
  fDateTo.value = ''
  fStatus.value = null
  fMatched.value = null
  fConfirmed.value = null
  fInn.value = ''
  searchQuery.value = ''
  filterSubsidyId.value = null
  applyFilters()
}

// ── Table state ─────────────────────────────────────────────────────────────
interface BankPayment {
  id: number
  import_id: number | null
  payment_date: string | null
  payment_number: string | null
  amount: number | null
  // Плательщик
  payer_name: string | null
  payer_name_resolved: string | null
  payer_inn: string | null
  payer_kpp: string | null
  payer_account: string | null
  payer_bank: string | null
  payer_bik: string | null
  payer_settlement_account: string | null
  payer_corr_account: string | null
  // Получатель
  payee_name: string | null
  payee_name_resolved: string | null
  payee_inn: string | null
  payee_kpp: string | null
  payee_account: string | null
  payee_bank: string | null
  payee_bik: string | null
  payee_settlement_account: string | null
  payee_corr_account: string | null
  // Парсинг
  parsed_contract_number: string | null
  parsed_contract_date: string | null
  parsed_kbk: string | null
  parsed_documents: Record<string, Array<{ number: string; date: string | null }>> | null
  status: string | null
  purpose_text: string | null
  basis_doc_text: string | null
  basis_doc_number: string | null
  basis_doc_date: string | null
  subsidy_code: string | null
  kbk: string | null
  execution_datetime: string | null
  // Match
  matched_contract_id: number | null
  matched_contractor_id: number | null
  matched_purchase_id: number | null
  matched_subsidy_id: number | null
  matched_confirmed: boolean
  created_at: string | null
}

const payments = ref<BankPayment[]>([])
const loading = ref(false)
const totalCount = ref(0)
const page = ref(1)
const expanded = ref<number[]>([])

// Stale parsed detection: записи где parsed_contract_number совпадает с basis_doc_number (номер субсидии)
const staleParsedDismissed = ref(false)
const hasStaleParsed = computed(() =>
  !staleParsedDismissed.value &&
  payments.value.some(
    p => p.parsed_contract_number && p.basis_doc_number &&
      p.parsed_contract_number === p.basis_doc_number
  )
)

// ── Column picker ─────────────────────────────────────────────────────────────
const LS_KEY = 'payment_registry_columns'

const DEFAULT_VISIBLE_KEYS = [
  'data-table-expand', 'index', 'payment_number', 'payment_date', 'payer_name', 'payee_name',
  'amount', 'status', 'parsed_contract_number', 'matched', 'matched_confirmed',
  'actions',
]

const allColumns = [
  { title: '', key: 'data-table-expand' },
  { title: '№', key: 'index' },
  // Метаданные документа
  { title: 'Номер документа', key: 'payment_number' },
  { title: 'Дата документа', key: 'payment_date' },
  { title: 'Дата исполнения операции', key: 'execution_datetime' },
  { title: 'Статус документа', key: 'status' },
  { title: 'Сумма', key: 'amount' },
  // Плательщик
  { title: 'ИНН плательщика', key: 'payer_inn' },
  { title: 'КПП плательщика', key: 'payer_kpp' },
  { title: 'Плательщик', key: 'payer_name' },
  { title: 'Плательщик (raw)', key: 'payer_name_raw' },
  { title: 'Лицевой счёт плательщика', key: 'payer_account' },
  { title: 'Банк плательщика', key: 'payer_bank' },
  { title: 'БИК плательщика', key: 'payer_bik' },
  { title: 'Расчётный счёт плательщика', key: 'payer_settlement_account' },
  { title: 'Корр. счёт плательщика', key: 'payer_corr_account' },
  // Получатель
  { title: 'ИНН получателя', key: 'payee_inn' },
  { title: 'КПП получателя', key: 'payee_kpp' },
  { title: 'Получатель', key: 'payee_name' },
  { title: 'Получатель (raw)', key: 'payee_name_raw' },
  { title: 'Лицевой счёт получателя', key: 'payee_account' },
  { title: 'Банк получателя', key: 'payee_bank' },
  { title: 'БИК получателя', key: 'payee_bik' },
  { title: 'Расчётный счёт получателя', key: 'payee_settlement_account' },
  { title: 'Корр. счёт получателя', key: 'payee_corr_account' },
  // Назначение и парсинг
  { title: 'Назначение платежа', key: 'purpose_text' },
  { title: 'Документ-основание (raw)', key: 'basis_doc_text' },
  { title: '№ документа-основания', key: 'basis_doc_number' },
  { title: 'Дата документа-основания', key: 'basis_doc_date' },
  { title: 'Шифр субсидии', key: 'subsidy_code' },
  { title: 'Договор/Авансовый/Соглашение (авто)', key: 'parsed_contract_number' },
  { title: 'Дата договора (авто)', key: 'parsed_contract_date' },
  { title: 'КБК', key: 'parsed_kbk' },
  // Match
  { title: 'Match: Контрагент', key: 'matched_contractor_id' },
  { title: 'Match: Субсидия', key: 'matched_subsidy_id' },
  { title: 'Match: Договор', key: 'matched_contract_id' },
  { title: 'Match: Закупка', key: 'matched_purchase_id' },
  { title: 'Сматчен', key: 'matched' },
  { title: 'Подтверждён', key: 'matched_confirmed' },
  // Audit
  { title: 'Создано', key: 'created_at' },
  { title: 'Действия', key: 'actions' },
]

function _loadVisibleKeys(): string[] {
  try {
    const stored = localStorage.getItem(LS_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) return parsed as string[]
    }
  } catch {}
  return [...DEFAULT_VISIBLE_KEYS]
}

const visibleColumnKeys = ref<string[]>(_loadVisibleKeys())
const colPickerOpen = ref(false)

function toggleColumn(key: string) {
  const idx = visibleColumnKeys.value.indexOf(key)
  if (idx >= 0) {
    // Don't allow hiding the last column or fixed system columns
    if (visibleColumnKeys.value.length <= 2) return
    visibleColumnKeys.value = visibleColumnKeys.value.filter(k => k !== key)
  } else {
    visibleColumnKeys.value = [...visibleColumnKeys.value, key]
  }
  localStorage.setItem(LS_KEY, JSON.stringify(visibleColumnKeys.value))
}

function resetColumns() {
  visibleColumnKeys.value = [...DEFAULT_VISIBLE_KEYS]
  localStorage.setItem(LS_KEY, JSON.stringify(visibleColumnKeys.value))
}

// Map from key to column definition including width/sortable
const _colMetaDefaults: Record<string, { width?: number; sortable?: boolean }> = {
  index:                      { sortable: false, width: 50 },
  payment_number:              { width: 130 },
  payment_date:                { width: 100 },
  execution_datetime:          { width: 150 },
  // Плательщик
  payer_name:                  { sortable: false, width: 180 },
  payer_name_raw:              { sortable: false, width: 180 },
  payer_inn:                   { width: 130 },
  payer_kpp:                   { width: 110 },
  payer_account:               { width: 160 },
  payer_bank:                  { sortable: false, width: 180 },
  payer_bik:                   { width: 110 },
  payer_settlement_account:    { width: 180 },
  payer_corr_account:          { width: 180 },
  // Получатель
  payee_name:                  { sortable: false, width: 180 },
  payee_name_raw:              { sortable: false, width: 180 },
  payee_inn:                   { width: 130 },
  payee_kpp:                   { width: 110 },
  payee_account:               { width: 160 },
  payee_bank:                  { sortable: false, width: 180 },
  payee_bik:                   { width: 110 },
  payee_settlement_account:    { width: 180 },
  payee_corr_account:          { width: 180 },
  // Прочее
  amount:                      { width: 130 },
  status:                      { width: 130 },
  purpose_text:                { sortable: false, width: 280 },
  basis_doc_text:              { sortable: false, width: 220 },
  basis_doc_number:            { width: 160 },
  basis_doc_date:              { width: 130 },
  subsidy_code:                { width: 130 },
  parsed_contract_number:      { width: 200 },
  parsed_contract_date:        { width: 130 },
  parsed_kbk:                  { width: 120 },
  matched:                     { width: 90, sortable: false },
  matched_confirmed:           { width: 110, sortable: false },
  matched_contractor_id:       { width: 120 },
  matched_contract_id:         { width: 120 },
  matched_purchase_id:         { width: 120 },
  matched_subsidy_id:          { width: 120 },
  created_at:                  { width: 150 },
  actions:                     { sortable: false, width: 110 },
  'data-table-expand':         { width: 48 },
}

// LS_COL_WIDTHS_KEY — хранит ширины колонок в пикселях
const LS_WIDTHS_KEY = 'payment_registry_col_widths'

function _loadColWidths(): Record<string, number> {
  try {
    const s = localStorage.getItem(LS_WIDTHS_KEY)
    if (s) return JSON.parse(s) as Record<string, number>
  } catch {}
  return {}
}
const colWidths = ref<Record<string, number>>(_loadColWidths())

function saveColWidth(key: string, w: number) {
  colWidths.value = { ...colWidths.value, [key]: w }
  localStorage.setItem(LS_WIDTHS_KEY, JSON.stringify(colWidths.value))
}

const activeHeaders = computed(() => {
  return allColumns
    .filter(c => visibleColumnKeys.value.includes(c.key))
    .map(c => {
      const meta = _colMetaDefaults[c.key] || {}
      const w = colWidths.value[c.key] ?? meta.width
      return {
        title: c.title,
        key: c.key,
        sortable: meta.sortable,
        width: w ? `${w}px` : undefined,
      }
    })
})

// ── Load data ───────────────────────────────────────────────────────────────
async function loadPayments() {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (fDateFrom.value) params.set('date_from', fDateFrom.value)
    if (fDateTo.value) params.set('date_to', fDateTo.value)
    if (fStatus.value) params.set('status', fStatus.value)
    if (fMatched.value !== null && fMatched.value !== '') params.set('matched', fMatched.value)
    if (fConfirmed.value !== null && fConfirmed.value !== '') params.set('confirmed', fConfirmed.value)
    if (fInn.value) params.set('payee_inn', fInn.value)
    if (importId.value) params.set('import_id', String(importId.value))

    const data = await apiFetch<any>(`/payments/registry?${params}`)
    const raw: BankPayment[] = Array.isArray(data) ? data : (data as any).items ?? []
    payments.value = raw
    totalCount.value = (data as any).total ?? raw.length
  } catch (e: any) {
    error('Не удалось загрузить реестр: ' + (e.detail || ''))
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadPayments()
}

// ── Watch import_id changes in URL ──────────────────────────────────────────
watch(importId, () => {
  applyFilters()
})

// ── Match dialog ─────────────────────────────────────────────────────────────
const matchDialog = ref(false)
const selectedPaymentId = ref<number | null>(null)

function openMatch(item: BankPayment) {
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function openConfirm(item: BankPayment) {
  // Open match dialog with pre-loaded contract for confirmation flow
  selectedPaymentId.value = item.id
  matchDialog.value = true
}

function onUpdated() {
  loadPayments()
}

// ── Unbind ───────────────────────────────────────────────────────────────────
const unbindDialog = ref(false)
const unbindingId = ref<number | null>(null)
const unbindLoading = ref(false)

function unbind(item: BankPayment) {
  unbindingId.value = item.id
  unbindDialog.value = true
}

async function doUnbind() {
  if (!unbindingId.value) return
  unbindLoading.value = true
  try {
    await apiFetch(`/payments/registry/${unbindingId.value}/unbind`, { method: 'POST' })
    success('Подтверждение откатено')
    unbindDialog.value = false
    loadPayments()
  } catch (e: any) {
    error('Ошибка при откате: ' + (e.detail || ''))
  } finally {
    unbindLoading.value = false
    unbindingId.value = null
  }
}

// ── Doc display: тип + номер ──────────────────────────────────────────────────
function docDisplay(item: any): string {
  const pd = item.parsed_documents || {}
  const contracts = pd.contracts || []
  const advance = pd.advance_reports || []
  const agreements = pd.agreements || []

  if (contracts.length) return `Договор ${contracts[0].number}`
  if (advance.length) return `Авансовый отчёт ${advance[0].number}`
  if (agreements.length) return `Соглашение ${agreements[0].number}`
  // fallback: просто parsed_contract_number без типа
  return item.parsed_contract_number || '—'
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU')
}

function formatMoney(v: number | null | undefined) {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(v)
}

function statusColor(s: string | null) {
  if (!s) return 'grey'
  if (s === 'ИСПОЛНЕН') return 'success'
  if (s === 'АННУЛИРОВАН') return 'error'
  return 'warning'
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadPayments()
  loadSubsidies()
})
</script>

<style scoped>
/* Phase 22.5: перенос текста в ячейках таблицы */
:deep(.v-data-table td) {
  white-space: normal !important;
  word-break: break-word;
  vertical-align: top;
  padding-top: 8px;
  padding-bottom: 8px;
}
</style>
