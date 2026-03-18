<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold">Реестр договоров</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ filtered.length }} из {{ contracts.length }} записей
        </span>
      </div>
      <div class="d-flex gap-2">
        <v-btn v-if="isAdmin" variant="outlined" prepend-icon="mdi-database-import" @click="migrateDialog = true">
          Мигрировать из закупок
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Добавить</v-btn>
      </div>
    </div>

    <!-- ── Unified search bar ── -->
    <v-card class="mb-3" variant="flat" color="primary" rounded="lg">
      <v-card-text class="py-3 px-4">
        <div class="d-flex align-center gap-3">
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            placeholder="Поиск по номеру, контрагенту, субсидии, предмету, ИНН..."
            variant="outlined"
            density="compact"
            hide-details
            clearable
            bg-color="white"
            style="max-width:600px"
          />
          <v-btn-toggle v-model="searchScope" density="compact" variant="outlined" color="white" mandatory rounded="lg">
            <v-btn value="filtered" size="small" style="color:white">По фильтру</v-btn>
            <v-btn value="all" size="small" style="color:white">По всей БД</v-btn>
          </v-btn-toggle>
          <v-chip v-if="search" size="small" color="white" variant="tonal" class="text-caption">
            Найдено: {{ filtered.length }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- ── Filters (collapsible) ── -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ (мульти-выбор)</span>
          <v-spacer />
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить все
          </v-btn>
        </div>
        <div class="d-flex flex-wrap gap-2">

          <!-- Субсидия -->
          <v-autocomplete
            v-model="fSubsidy"
            :items="subsidies"
            item-title="name" item-value="id"
            label="Субсидия" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:280px"
          />

          <!-- Тип документа -->
          <v-autocomplete
            v-model="fType"
            :items="contractTypeItems"
            item-title="label" item-value="value"
            label="Тип документа" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Способ закупки -->
          <v-autocomplete
            v-model="fMethod"
            :items="purchaseMethodItems"
            item-title="label" item-value="value"
            label="Способ закупки" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:180px; max-width:240px"
          />

          <!-- Статус -->
          <v-autocomplete
            v-model="fStatus"
            :items="statusItems"
            item-title="label" item-value="value"
            label="Статус" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:140px; max-width:200px"
          />

          <!-- Контрагент -->
          <v-autocomplete
            v-model="fContractor"
            :items="contractors"
            item-title="name" item-value="id"
            label="Контрагент" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Дата от/до -->
          <v-text-field
            v-model="fDateFrom"
            label="Дата от" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />

        </div>
      </v-card-text>
    </v-card>

    <!-- ── Table ── -->
    <v-data-table
      :headers="headers"
      :items="filtered"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      items-per-page="50"
      :items-per-page-options="[25,50,100,-1]"
    >
      <template #item.number="{ item }">
        <span class="font-weight-medium">{{ item.number }}</span>
      </template>
      <template #item.date="{ item }">
        {{ fmtDate(item.date) }}
      </template>
      <template #item.end_date="{ item }">
        <span :style="item.end_date && isExpired(item.end_date) ? 'color:#DC2626' : ''">
          {{ fmtDate(item.end_date) }}
        </span>
      </template>
      <template #item.contract_type="{ item }">
        <v-chip size="x-small" :color="contractTypeColor(item.contract_type)" variant="tonal">
          {{ contractTypeLabel(item.contract_type) }}
        </v-chip>
      </template>
      <template #item.purchase_method="{ item }">
        <span class="text-caption">{{ item.purchase_method ? purchaseMethodLabel(item.purchase_method) : '—' }}</span>
      </template>
      <template #item.contractor_name="{ item }">
        <div>{{ item.contractor_name || '—' }}</div>
        <div v-if="item.contractor_inn" class="text-caption text-medium-emphasis">ИНН {{ item.contractor_inn }}</div>
      </template>
      <template #item.max_amount="{ item }">
        {{ item.max_amount ? formatMoney(item.max_amount) : '—' }}
      </template>
      <template #item.total_ordered="{ item }">
        <span :style="item.max_amount && Number(item.total_ordered) > Number(item.max_amount) ? 'color:#DC2626;font-weight:700' : ''">
          {{ item.total_ordered ? formatMoney(item.total_ordered) : '—' }}
        </span>
      </template>
      <template #item.total_paid="{ item }">
        <span style="color:#166534">{{ item.total_paid ? formatMoney(item.total_paid) : '—' }}</span>
      </template>
      <template #item.remaining="{ item }">
        <span :style="Number(item.remaining) < 0 ? 'color:#DC2626;font-weight:700' : 'color:#166534'">
          {{ item.remaining != null ? formatMoney(item.remaining) : '—' }}
        </span>
      </template>
      <template #item.status="{ item }">
        <v-chip size="x-small" :color="item.status === 'active' ? 'success' : 'grey'" variant="tonal">
          {{ statusLabel(item.status) }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <div class="d-flex gap-1">
          <v-btn icon="mdi-pencil" variant="text" size="small" @click="openEdit(item)" />
          <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDelete(item)" />
        </div>
      </template>
      <!-- Expanded: закупки по договору -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <div class="pa-3 bg-grey-lighten-5">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                Закупки по документу {{ item.number }}
              </div>
              <div v-if="!purchasesByContract[item.id]" class="text-caption text-medium-emphasis">
                <v-btn size="x-small" variant="text" @click="loadPurchasesForContract(item.id)">Загрузить</v-btn>
              </div>
              <div v-else-if="!purchasesByContract[item.id].length" class="text-caption text-medium-emphasis">Нет закупок</div>
              <v-table v-else density="compact">
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Предмет</th>
                    <th>Цена договора</th>
                    <th>Статус</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in purchasesByContract[item.id]" :key="p.id">
                    <td>{{ p.purchase_number || p.id }}</td>
                    <td>{{ p.subject || p.item_name }}</td>
                    <td>{{ p.contract_price ? formatMoney(p.contract_price) : '—' }}</td>
                    <td><v-chip size="x-small" variant="tonal">{{ p.status }}</v-chip></td>
                    <td><v-btn icon="mdi-open-in-new" variant="text" size="x-small" :to="`/orders/${p.id}/edit`" /></td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </td>
        </tr>
      </template>
    </v-data-table>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog.show" max-width="680">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          {{ dialog.id ? 'Редактировать документ' : 'Новый документ' }}
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.number" label="Номер *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.date" label="Дата" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.contract_type"
                :items="contractTypeItems" item-title="label" item-value="value"
                label="Тип документа *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.purchase_method"
                :items="purchaseMethodItems" item-title="label" item-value="value"
                label="Способ закупки" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="6">
              <v-autocomplete v-model="dialog.form.contractor_id"
                :items="contractors" item-title="name" item-value="id"
                label="Контрагент" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.subsidy_id"
                :items="subsidies" item-title="name" item-value="id"
                label="Субсидия" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12">
              <v-text-field v-model="dialog.form.subject" label="Предмет" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.max_amount" label="Предельная сумма, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.planned_monthly" label="Плановый ежемесячный платёж, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.start_date" label="Дата начала" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.end_date" label="Дата окончания" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.status"
                :items="statusItems" item-title="label" item-value="value"
                label="Статус" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="dialog.form.notes" label="Примечания" variant="outlined" density="compact" rows="2" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="dialog.saving" @click="saveContract">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="400">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Удалить запись?</v-card-title>
        <v-card-text class="px-4">
          Удалить <strong>{{ deleteDialog.item?.number }}</strong>? Закупки сохранятся.
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Migrate dialog -->
    <v-dialog v-model="migrateDialog" max-width="480">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Мигрировать из закупок</v-card-title>
        <v-card-text class="px-4">
          <p class="text-body-2 mb-3">
            Создаст записи реестра из всех закупок с заполненным номером договора. Уже существующие номера пропускаются.
          </p>
          <v-alert v-if="migrateResult" :type="migrateResult.created > 0 ? 'success' : 'info'" variant="tonal" density="compact">
            Создано: <strong>{{ migrateResult.created }}</strong>,
            пропущено: <strong>{{ migrateResult.skipped }}</strong>
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="migrateDialog = false">Закрыть</v-btn>
          <v-btn v-if="!migrateResult" color="primary" variant="tonal" :loading="migrating" @click="doMigrate">
            Запустить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { apiFetch } from '@/api'

const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

interface Contract {
  id: number
  number: string
  date?: string
  contract_type: string
  purchase_method?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  subsidy_id?: number
  subsidy_name?: string
  subject?: string
  max_amount?: number
  total_ordered?: number
  total_paid?: number
  remaining?: number
  start_date?: string
  end_date?: string
  status?: string
  notes?: string
  planned_monthly?: number
}
interface Subsidy { id: number; name: string; year: number }
interface Contractor { id: number; name: string; inn?: string }
interface Purchase { id: number; purchase_number?: number; subject?: string; item_name?: string; contract_price?: number; status: string }

const contracts = ref<Contract[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const expanded = ref<number[]>([])
const purchasesByContract = ref<Record<number, Purchase[]>>({})

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

// ── Filters (all multi-select, client-side) ────────────────────────────────
const search = ref('')
const searchScope = ref<'filtered' | 'all'>('filtered')
const fSubsidy    = ref<number[]>([])
const fType       = ref<string[]>([])
const fMethod     = ref<string[]>([])
const fStatus     = ref<string[]>([])
const fContractor = ref<number[]>([])
const fDateFrom   = ref('')
const fDateTo     = ref('')

const hasFilters = computed(() =>
  fSubsidy.value.length > 0 || fType.value.length > 0 || fMethod.value.length > 0 ||
  fStatus.value.length > 0 || fContractor.value.length > 0 || !!fDateFrom.value || !!fDateTo.value
)

const clearFilters = () => {
  fSubsidy.value = []; fType.value = []; fMethod.value = []
  fStatus.value = []; fContractor.value = []; fDateFrom.value = ''; fDateTo.value = ''
}

function matchesSearch(c: Contract, q: string): boolean {
  const lq = q.toLowerCase()
  return [c.number, c.contractor_name, c.contractor_inn, c.subsidy_name, c.subject, c.notes]
    .some(v => v?.toLowerCase().includes(lq))
}

const filtered = computed(() => {
  const q = search.value.trim()

  // "По всей БД" — ignore column filters, only apply search
  if (q && searchScope.value === 'all') {
    return contracts.value.filter(c => matchesSearch(c, q))
  }

  let list = contracts.value

  if (fSubsidy.value.length)    list = list.filter(c => c.subsidy_id != null && fSubsidy.value.includes(c.subsidy_id))
  if (fType.value.length)       list = list.filter(c => fType.value.includes(c.contract_type))
  if (fMethod.value.length)     list = list.filter(c => c.purchase_method != null && fMethod.value.includes(c.purchase_method))
  if (fStatus.value.length)     list = list.filter(c => c.status != null && fStatus.value.includes(c.status))
  if (fContractor.value.length) list = list.filter(c => c.contractor_id != null && fContractor.value.includes(c.contractor_id))
  if (fDateFrom.value)          list = list.filter(c => !c.date || c.date >= fDateFrom.value)
  if (fDateTo.value)            list = list.filter(c => !c.date || c.date <= fDateTo.value)
  if (q)                        list = list.filter(c => matchesSearch(c, q))

  return list
})

// ── Type / method / status lookup tables ──────────────────────────────────
const contractTypeItems = [
  { value: 'single',                label: 'Разовая поставка' },
  { value: 'framework_cumulative',  label: 'Рамочный (нарастающий итог)' },
  { value: 'framework_with_amount', label: 'Рамочный (с суммой)' },
  { value: 'invoice',               label: 'Счёт' },
  { value: 'invoice_contract',      label: 'Счёт-договор' },
  { value: 'advance_report',        label: 'Авансовый отчёт' },
]
const purchaseMethodItems = [
  { value: 'single',      label: 'Единственный поставщик' },
  { value: 'competitive', label: 'Конкурсная процедура' },
]
const statusItems = [
  { value: 'active', label: 'Активен' },
  { value: 'closed', label: 'Закрыт' },
]

const contractTypeLabel = (t?: string) => contractTypeItems.find(i => i.value === t)?.label || t || '—'
const purchaseMethodLabel = (m?: string) => purchaseMethodItems.find(i => i.value === m)?.label || m || '—'
const statusLabel = (s?: string) => statusItems.find(i => i.value === s)?.label || s || '—'
const contractTypeColor = (t?: string) => {
  if (t === 'single') return 'blue'
  if (t?.startsWith('framework')) return 'orange'
  if (t === 'invoice' || t === 'invoice_contract') return 'teal'
  if (t === 'advance_report') return 'purple'
  return 'grey'
}

const isExpired = (d: string) => new Date(d) < new Date()
const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('ru-RU') : '—'
const formatMoney = (v: number | string) =>
  Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ₽'

// ── Table headers ──────────────────────────────────────────────────────────
const headers = [
  { title: '', key: 'data-table-expand', width: 40, sortable: false },
  { title: '№ документа', key: 'number', minWidth: 120 },
  { title: 'Дата', key: 'date', width: 110 },
  { title: 'Тип', key: 'contract_type', width: 170 },
  { title: 'Способ', key: 'purchase_method', width: 130 },
  { title: 'Контрагент', key: 'contractor_name', minWidth: 160 },
  { title: 'Субсидия', key: 'subsidy_name', minWidth: 120 },
  { title: 'Предельная сумма', key: 'max_amount', align: 'end' as const, width: 140 },
  { title: 'Заказано', key: 'total_ordered', align: 'end' as const, width: 120 },
  { title: 'Оплачено', key: 'total_paid', align: 'end' as const, width: 120 },
  { title: 'Остаток', key: 'remaining', align: 'end' as const, width: 120 },
  { title: 'Срок', key: 'end_date', width: 110 },
  { title: 'Статус', key: 'status', width: 100 },
  { title: '', key: 'actions', sortable: false, width: 90 },
]

// ── Load data (all contracts, no server-side filter) ──────────────────────
const loadContracts = async () => {
  loading.value = true
  try {
    contracts.value = await apiFetch<Contract[]>('/contracts/')
  } catch {
    showSnack('Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') }
const loadContractors = async () => { contractors.value = await apiFetch<Contractor[]>('/contractors/') }

const loadPurchasesForContract = async (contractId: number) => {
  const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contractId}`)
  purchasesByContract.value = { ...purchasesByContract.value, [contractId]: items }
}

watch(expanded, (newVal) => {
  for (const id of newVal) {
    if (!purchasesByContract.value[id]) loadPurchasesForContract(id)
  }
})

// ── Dialog ─────────────────────────────────────────────────────────────────
const emptyForm = () => ({
  number: '', date: '', contract_type: 'single', purchase_method: null as string | null,
  contractor_id: null as number | null, subsidy_id: null as number | null,
  subject: '', max_amount: null as number | null, planned_monthly: null as number | null,
  start_date: '', end_date: '', status: 'active', notes: '',
})
const dialog = reactive({ show: false, saving: false, id: 0, form: emptyForm() })

const openCreate = () => { dialog.id = 0; Object.assign(dialog.form, emptyForm()); dialog.show = true }

const openEdit = (c: Contract) => {
  dialog.id = c.id
  Object.assign(dialog.form, {
    number: c.number || '', date: c.date || '', contract_type: c.contract_type || 'single',
    purchase_method: c.purchase_method || null, contractor_id: c.contractor_id || null,
    subsidy_id: c.subsidy_id || null, subject: c.subject || '',
    max_amount: c.max_amount || null, planned_monthly: c.planned_monthly || null,
    start_date: c.start_date || '', end_date: c.end_date || '',
    status: c.status || 'active', notes: c.notes || '',
  })
  dialog.show = true
}

const saveContract = async () => {
  dialog.saving = true
  try {
    const body = { ...dialog.form, date: dialog.form.date || null, start_date: dialog.form.start_date || null, end_date: dialog.form.end_date || null }
    if (dialog.id) {
      await apiFetch(`/contracts/${dialog.id}`, { method: 'PUT', body: JSON.stringify(body) })
      showSnack('Сохранено')
    } else {
      await apiFetch('/contracts/', { method: 'POST', body: JSON.stringify(body) })
      showSnack('Создано')
    }
    dialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    dialog.saving = false
  }
}

const deleteDialog = reactive({ show: false, deleting: false, item: null as Contract | null })
const confirmDelete = (c: Contract) => { deleteDialog.item = c; deleteDialog.show = true }
const doDelete = async () => {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/contracts/${deleteDialog.item.id}`, { method: 'DELETE' })
    showSnack('Удалено', 'warning')
    deleteDialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

// ── Migration ──────────────────────────────────────────────────────────────
const migrateDialog = ref(false)
const migrating = ref(false)
const migrateResult = ref<{ created: number; skipped: number } | null>(null)

watch(migrateDialog, (v) => { if (!v) migrateResult.value = null })

const doMigrate = async () => {
  migrating.value = true
  try {
    const res = await apiFetch<{ created: number; skipped: number }>('/contracts/migrate-from-purchases', { method: 'POST' })
    migrateResult.value = res
    if (res.created > 0) await loadContracts()
    showSnack(`Создано: ${res.created}`)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка миграции', 'error')
  } finally {
    migrating.value = false
  }
}

onMounted(() => { loadContracts(); loadSubsidies(); loadContractors() })
</script>
