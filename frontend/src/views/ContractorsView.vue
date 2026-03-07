<template>
  <div class="contractors-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-account-group" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">Контрагенты</div>
          <div class="page-subtitle">Список поставщиков и исполнителей</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-btn
          variant="tonal"
          color="success"
          prepend-icon="mdi-microsoft-excel"
          class="mr-2"
          :loading="importing"
          @click="triggerImport"
        >
          Импорт из Excel
        </v-btn>
        <input
          ref="excelInput"
          type="file"
          accept=".xlsx,.xls"
          style="display:none"
          @change="handleImport"
        />
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openAdd">
          Добавить контрагента
        </v-btn>
      </div>
    </div>

    <!-- ── Filters ── -->
    <div class="filters-bar mb-4">
      <v-text-field
        v-model="search"
        prepend-inner-icon="mdi-magnify"
        label="Поиск по названию или ИНН"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 320px"
        clearable
      />
      <v-select
        v-model="filterSubsidyId"
        :items="subsidies"
        item-title="name"
        item-value="id"
        label="Субсидия"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 200px"
      />
      <v-select
        v-model="filterCategoryId"
        :items="feoCategories"
        item-title="label"
        item-value="id"
        label="Категория ФЭО"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 260px"
      />
      <v-btn
        v-if="filterSubsidyId || filterCategoryId || search"
        variant="text"
        size="small"
        color="grey"
        @click="clearFilters"
      >Сбросить</v-btn>
      <span class="search-count">{{ filtered.length }} из {{ contractors.length }}</span>
    </div>

    <!-- ── Bulk actions ── -->
    <div v-if="selectedIds.size > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedIds.size }}</span>
      <v-spacer />
      <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранных
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedIds = new Set()">Снять выделение</v-btn>
    </div>

    <!-- ── Loading ── -->
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <!-- ── Table ── -->
    <div class="table-card">
      <v-table class="contractors-table">
        <thead>
          <tr>
            <th style="width:48px">
              <v-checkbox
                :model-value="filtered.length > 0 && selectedIds.size === filtered.length"
                :indeterminate="selectedIds.size > 0 && selectedIds.size < filtered.length"
                density="compact"
                hide-details
                @update:model-value="toggleAll"
              />
            </th>
            <th>Наименование</th>
            <th>ИНН</th>
            <th>КПП</th>
            <th>Адрес</th>
            <th>Телефон / Email</th>
            <th>Контактное лицо</th>
            <th style="min-width:120px">Закупки</th>
            <th class="text-right">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!loading && filtered.length === 0">
            <td colspan="9" class="text-center py-10 text-medium-emphasis">
              <v-icon icon="mdi-account-off-outline" size="40" color="grey-lighten-2" class="d-block mx-auto mb-2" />
              Контрагенты не найдены
            </td>
          </tr>
          <tr v-for="c in filtered" :key="c.id" class="contractor-row" :class="{ 'contractor-row--selected': selectedIds.has(c.id) }">
            <td>
              <v-checkbox
                :model-value="selectedIds.has(c.id)"
                density="compact"
                hide-details
                @update:model-value="toggleOne(c.id)"
              />
            </td>
            <td class="font-weight-medium">{{ c.name }}</td>
            <td class="text-mono">{{ c.inn || '—' }}</td>
            <td class="text-mono">{{ c.kpp || '—' }}</td>
            <td class="text-sm">{{ c.address || '—' }}</td>
            <td>
              <div class="text-sm">{{ c.phone || '—' }}</div>
              <div class="text-caption text-medium-emphasis">{{ c.email || '' }}</div>
            </td>
            <td class="text-sm">{{ c.contact_person || '—' }}</td>
            <td>
              <v-chip
                v-if="c.purchase_count > 0"
                size="small"
                color="primary"
                variant="tonal"
                class="cursor-pointer"
                @click="openPurchasesDialog(c)"
              >
                {{ c.purchase_count }} закуп.
              </v-chip>
              <span v-else class="text-medium-emphasis text-caption">—</span>
            </td>
            <td class="text-right">
              <v-btn icon="mdi-pencil" variant="text" size="small" class="mr-1" @click="openEdit(c)" />
              <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDelete(c)" />
            </td>
          </tr>
        </tbody>
      </v-table>
    </div>

    <!-- ── Purchases dialog ── -->
    <v-dialog v-model="purchasesDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-clipboard-list" color="primary" class="mr-2" />
          Закупки: {{ purchasesDialogContractor?.name }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="purchasesDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height:460px; padding:0">
          <v-progress-linear v-if="purchasesLoading" indeterminate color="primary" />
          <v-table v-if="purchasesList.length > 0" density="compact">
            <thead>
              <tr>
                <th>ID</th>
                <th>Предмет</th>
                <th>Субсидия</th>
                <th>Категория ФЭО</th>
                <th>Сумма</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in purchasesList" :key="p.id">
                <td class="text-caption text-medium-emphasis">{{ p.id }}</td>
                <td class="text-sm" style="max-width:200px; white-space:normal">{{ p.subject }}</td>
                <td class="text-caption">{{ p.subsidy_name }}</td>
                <td class="text-caption">{{ p.feo_category_name }}</td>
                <td class="text-sm text-no-wrap">{{ p.planned_total_price ? p.planned_total_price.toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
                <td>
                  <v-chip size="x-small" :color="statusColor(p.status)" variant="flat">
                    {{ statusLabel(p.status) }}
                  </v-chip>
                </td>
              </tr>
            </tbody>
          </v-table>
          <div v-else-if="!purchasesLoading" class="text-center pa-8 text-medium-emphasis">
            Закупки не найдены
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- ── Add / Edit Dialog ── -->
    <v-dialog v-model="dialog" max-width="780" persistent scrollable>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon :icon="editId ? 'mdi-pencil-outline' : 'mdi-plus-circle-outline'" color="primary" class="mr-2" />
          {{ editId ? 'Редактировать контрагента' : 'Добавить контрагента' }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="dialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4" style="max-height:75vh">
          <v-form ref="formRef">
            <div class="section-label">Основные данные</div>
            <v-text-field
              v-model="form.name"
              label="Наименование организации *"
              variant="outlined"
              density="compact"
              :rules="[v => !!v || 'Обязательное поле']"
              class="mb-3"
              hide-details="auto"
            />
            <v-row dense>
              <v-col cols="4">
                <v-text-field v-model="form.inn" label="ИНН" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="4">
                <v-text-field v-model="form.kpp" label="КПП" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="4">
                <v-text-field v-model="form.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>
            <v-textarea v-model="form.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
            <v-textarea v-model="form.postal_address" label="Почтовый адрес" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

            <div class="section-label mt-4">Подписант</div>
            <v-text-field v-model="form.signatory" label="Подписант (ФИО, должность)" variant="outlined" density="compact" class="mb-3" hide-details />
            <v-text-field v-model="form.signatory_basis" label="На основании чего действует" variant="outlined" density="compact" hide-details
              placeholder="Устава, доверенности №..." />

            <div class="section-label mt-4">Контакты</div>
            <v-text-field v-model="form.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mb-3" hide-details />
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="form.phone" label="Телефон" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="form.email" label="Email" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>

            <div class="section-label mt-4">Банковские реквизиты</div>
            <v-text-field v-model="form.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details maxlength="20" />
            <v-text-field v-model="form.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details
              placeholder="в ПАО «Сбербанк»..." />
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="form.bik" label="БИК" variant="outlined" density="compact" hide-details maxlength="9" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="form.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details maxlength="20" />
              </v-col>
            </v-row>
            <v-textarea v-model="form.bank_details" label="Банковские реквизиты (свободное поле)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          </v-form>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Bulk delete confirm ── -->
    <v-dialog v-model="bulkDeleteDialog" max-width="420">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить контрагентов?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Удалить <strong>{{ selectedIds.size }}</strong> выбранных контрагентов? Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="bulkDeleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="saving" @click="doBulkDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Delete confirm ── -->
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить контрагента?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Удалить <strong>{{ deleteTarget?.name }}</strong>? Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="saving" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ── -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="4000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface ContractorWithStats {
  id: number
  name: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  email?: string
  bank_details?: string
  signatory?: string
  signatory_basis?: string
  postal_address?: string
  ogrn?: string
  settlement_account?: string
  bank_name?: string
  bik?: string
  correspondent_account?: string
  purchase_count: number
  subsidy_ids: number[]
  feo_category_ids: number[]
}

interface Subsidy { id: number; name: string }
interface FeoCategory { id: number; name: string; level: number; code?: string }
interface PurchaseSummary {
  id: number; subject: string; status: string
  planned_total_price?: number; subsidy_name: string; feo_category_name: string
}

const contractors = ref<ContractorWithStats[]>([])
const subsidies   = ref<Subsidy[]>([])
const feoCategories = ref<{ id: number; label: string; feo_ids?: number[] }[]>([])
const loading     = ref(false)
const saving      = ref(false)
const importing   = ref(false)
const search      = ref('')
const filterSubsidyId  = ref<number | null>(null)
const filterCategoryId = ref<number | null>(null)
const dialog      = ref(false)
const deleteDialog     = ref(false)
const bulkDeleteDialog = ref(false)
const editId      = ref<number | null>(null)
const deleteTarget  = ref<ContractorWithStats | null>(null)
const formRef     = ref()
const excelInput  = ref<HTMLInputElement>()
const selectedIds = ref(new Set<number>())

// Purchases dialog
const purchasesDialog = ref(false)
const purchasesLoading = ref(false)
const purchasesDialogContractor = ref<ContractorWithStats | null>(null)
const purchasesList = ref<PurchaseSummary[]>([])

const snack = ref({ show: false, text: '', color: 'success' })

const emptyForm = () => ({
  name: '', inn: '', kpp: '', address: '',
  contact_person: '', phone: '', email: '', bank_details: '',
  signatory: '', signatory_basis: '', postal_address: '',
  ogrn: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
})
const form = ref(emptyForm())

const filtered = computed(() => {
  let list = contractors.value
  const q = search.value?.toLowerCase() ?? ''
  if (q) list = list.filter(c => c.name.toLowerCase().includes(q) || (c.inn || '').includes(q))
  if (filterSubsidyId.value) {
    const sid = filterSubsidyId.value
    list = list.filter(c => c.subsidy_ids.includes(sid))
  }
  if (filterCategoryId.value) {
    const cid = filterCategoryId.value
    list = list.filter(c => c.feo_category_ids.includes(cid))
  }
  return list
})

function clearFilters() {
  search.value = ''
  filterSubsidyId.value = null
  filterCategoryId.value = null
}

// ── Load ──────────────────────────────────────────
async function loadContractors() {
  loading.value = true
  try {
    const [conts, subs, cats] = await Promise.all([
      apiFetch<ContractorWithStats[]>('/contractors/with-stats'),
      apiFetch<Subsidy[]>('/subsidies/'),
      apiFetch<FeoCategory[]>('/feo-categories/'),
    ])
    contractors.value = conts
    subsidies.value = subs
    // Build flat list for filter — show all levels with indentation
    feoCategories.value = cats.map(c => ({
      id: c.id,
      label: `${'·'.repeat(c.level - 1)} [${c.code || c.level}] ${c.name}`,
    }))
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

// ── Purchases dialog ───────────────────────────────
async function openPurchasesDialog(c: ContractorWithStats) {
  purchasesDialogContractor.value = c
  purchasesList.value = []
  purchasesDialog.value = true
  purchasesLoading.value = true
  try {
    purchasesList.value = await apiFetch<PurchaseSummary[]>(`/contractors/${c.id}/purchases`)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки закупок', 'error')
  } finally {
    purchasesLoading.value = false
  }
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Плановая', confirmed: 'Подтверждена', contracted: 'Законтрактована',
  delivered: 'Доставлена', paid: 'Оплачена',
}
const STATUS_COLORS: Record<string, string> = {
  planned: 'grey', confirmed: 'blue', contracted: 'orange', delivered: 'teal', paid: 'green',
}
function statusLabel(s: string) { return STATUS_LABELS[s] || s }
function statusColor(s: string) { return STATUS_COLORS[s] || 'grey' }

// ── Add / Edit ────────────────────────────────────
function openAdd() {
  editId.value = null
  form.value = emptyForm()
  dialog.value = true
}

function openEdit(c: ContractorWithStats) {
  editId.value = c.id
  form.value = {
    name:                 c.name,
    inn:                  c.inn                  || '',
    kpp:                  c.kpp                  || '',
    address:              c.address              || '',
    contact_person:       c.contact_person       || '',
    phone:                c.phone                || '',
    email:                c.email                || '',
    bank_details:         c.bank_details         || '',
    signatory:            c.signatory            || '',
    signatory_basis:      c.signatory_basis      || '',
    postal_address:       c.postal_address       || '',
    ogrn:                 c.ogrn                 || '',
    settlement_account:   c.settlement_account   || '',
    bank_name:            c.bank_name            || '',
    bik:                  c.bik                  || '',
    correspondent_account: c.correspondent_account || '',
  }
  dialog.value = true
}

async function save() {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    if (editId.value) {
      await apiFetch<ContractorWithStats>(`/contractors/${editId.value}`, {
        method: 'PUT',
        body: form.value as any,
      })
      showSnack('Контрагент обновлён')
    } else {
      await apiFetch<ContractorWithStats>('/contractors/', {
        method: 'POST',
        body: form.value as any,
      })
      showSnack('Контрагент добавлен')
    }
    dialog.value = false
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

// ── Selection ─────────────────────────────────────
function toggleOne(id: number) {
  const s = new Set(selectedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedIds.value = s
}

function toggleAll(val: boolean) {
  selectedIds.value = val ? new Set(filtered.value.map(c => c.id)) : new Set()
}

function confirmBulkDelete() {
  bulkDeleteDialog.value = true
}

async function doBulkDelete() {
  saving.value = true
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map(id => apiFetch(`/contractors/${id}`, { method: 'DELETE' })))
    selectedIds.value = new Set()
    bulkDeleteDialog.value = false
    showSnack(`Удалено контрагентов: ${ids.length}`, 'warning')
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка удаления', 'error')
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────
function confirmDelete(c: ContractorWithStats) {
  deleteTarget.value = c
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await apiFetch(`/contractors/${deleteTarget.value.id}`, { method: 'DELETE' })
    deleteDialog.value = false
    showSnack('Контрагент удалён', 'warning')
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка удаления', 'error')
  } finally {
    saving.value = false
  }
}

// ── Excel import ──────────────────────────────────
function triggerImport() {
  excelInput.value?.click()
}

async function handleImport(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  ;(event.target as HTMLInputElement).value = ''

  importing.value = true
  try {
    const token = localStorage.getItem('auth_token') || ''
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/contractors/import/excel', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      const text = await res.text()
      let detail = text
      try { detail = JSON.parse(text).detail } catch {}
      throw new Error(detail)
    }
    const data = await res.json()
    showSnack(`Импорт завершён: добавлено ${data.created}, пропущено ${data.skipped}`, 'success')
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    importing.value = false
  }
}

// ── Helpers ───────────────────────────────────────
function showSnack(text: string, color = 'success') {
  snack.value = { show: true, text, color }
}

onMounted(loadContractors)
</script>

<style scoped>
.contractors-page {
  padding: 20px 24px;
  max-width: 1600px;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: #111827; line-height: 1.2; }
.page-subtitle { font-size: 13px; color: #6B7280; margin-top: 2px; }

/* ── Filters ── */
.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.search-count {
  font-size: 13px;
  color: #6B7280;
  white-space: nowrap;
  margin-left: auto;
}

/* ── Table ── */
.table-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow: hidden;
}
.contractors-table thead th {
  font-size: 11px !important;
  font-weight: 600 !important;
  color: #6B7280 !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: #F9FAFB;
  padding: 10px 14px !important;
  white-space: nowrap;
}
.contractors-table tbody td {
  padding: 10px 14px !important;
  vertical-align: top;
}
.contractor-row:hover td { background: #F9FAFB; }
.contractor-row--selected td { background: #EFF6FF; }
.text-mono { font-family: monospace; font-size: 13px; }
.text-sm   { font-size: 13px; }
.cursor-pointer { cursor: pointer; }

/* ── Dialogs ── */
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 16px !important;
  font-weight: 600 !important;
  padding: 16px 20px !important;
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #F3F4F6;
}
</style>
