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
          color="secondary"
          prepend-icon="mdi-download"
          class="mr-2"
          @click="downloadTemplate"
        >
          Шаблон
        </v-btn>
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
      <v-autocomplete
        v-model="filterCategory"
        :items="allProductCategories"
        label="Категория товаров"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 260px"
      />
      <v-btn
        v-if="filterCategory || search"
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
            <th style="min-width:160px">Категории товаров</th>
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
          <tr v-for="c in filtered" :key="c.id" class="contractor-row" :class="{ 'contractor-row--selected': selectedIds.has(c.id) }" style="cursor:pointer" @click="openEdit(c)">
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
              <template v-if="c.product_categories.length > 0">
                <v-chip
                  v-if="c.product_categories.includes('Все')"
                  size="x-small"
                  color="blue"
                  variant="tonal"
                  class="mr-1 mb-1"
                >Все категории</v-chip>
                <template v-else>
                  <v-chip
                    v-for="cat in c.product_categories.slice(0, 2)"
                    :key="cat"
                    size="x-small"
                    color="teal"
                    variant="tonal"
                    class="mr-1 mb-1"
                  >{{ cat }}</v-chip>
                  <v-chip
                    v-if="c.product_categories.length > 2"
                    size="x-small"
                    color="grey"
                    variant="tonal"
                    class="cursor-pointer"
                    @click="openCategoriesDialog(c)"
                  >+{{ c.product_categories.length - 2 }}</v-chip>
                </template>
              </template>
              <span v-else class="text-medium-emphasis text-caption">—</span>
            </td>
            <td class="text-right" @click.stop>
              <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDelete(c)" />
            </td>
          </tr>
        </tbody>
      </v-table>
    </div>

    <!-- ── Categories dialog ── -->
    <v-dialog v-model="categoriesDialog" max-width="480" scrollable>
      <v-card>
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-tag-multiple-outline" color="teal" class="mr-2" />
          Категории товаров: {{ categoriesDialogContractor?.name }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="categoriesDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-chip
            v-for="cat in categoriesDialogContractor?.product_categories ?? []"
            :key="cat"
            color="teal"
            variant="tonal"
            class="mr-2 mb-2"
          >{{ cat }}</v-chip>
          <div v-if="!categoriesDialogContractor?.product_categories?.length" class="text-center text-medium-emphasis pa-4">
            Категории не указаны (нет закупок с товарами из каталога)
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
            <v-select
              v-model="form.org_type"
              :items="['Юр.лицо', 'ИП', 'Самозанятый', 'Физ.лицо']"
              label="Форма организации"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              class="mb-3"
            />
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

            <div class="section-label mt-4">Категории товаров</div>
            <v-combobox
              v-model="form.manual_product_categories"
              :items="categoryOptions"
              label="Категории товаров / услуг"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
              clearable
              hide-details
              hint="Введите категорию и нажмите Enter. Выберите «Все» для всех категорий."
              persistent-hint
              :disabled="form.manual_product_categories?.includes('Все')"
            />
            <v-checkbox
              v-model="allCategoriesToggle"
              label="Все категории"
              density="compact"
              hide-details
              color="teal"
              class="mt-1"
            />
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
    <v-dialog v-model="bulkDeleteDialog" max-width="440" persistent>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить контрагентов?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <p class="mb-3">
            Вы собираетесь удалить <strong>{{ selectedIds.size }}</strong> контрагентов.
            Это действие <strong>нельзя отменить</strong>.
          </p>
          <p v-if="selectedIds.size > 5" class="text-caption text-medium-emphasis mb-3">
            Для подтверждения введите количество удаляемых записей:
          </p>
          <v-text-field
            v-if="selectedIds.size > 5"
            v-model="bulkDeleteConfirmCount"
            :placeholder="`Введите ${selectedIds.size}`"
            variant="outlined"
            density="compact"
            hide-details
            autofocus
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="bulkDeleteDialog = false; bulkDeleteConfirmCount = ''">Отмена</v-btn>
          <v-btn
            color="error"
            :loading="saving"
            :disabled="selectedIds.size > 5 && bulkDeleteConfirmCount !== String(selectedIds.size)"
            @click="doBulkDelete"
          >Удалить</v-btn>
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

    <!-- ── Import hint dialog ── -->
    <v-dialog v-model="importHintDialog" max-width="580" persistent>
      <v-card>
        <v-card-title class="text-h6 pa-4">Импорт контрагентов из Excel</v-card-title>
        <v-card-text class="pt-0">
          <p class="mb-3">Загрузите файл <strong>.xlsx</strong>. Первая строка — заголовки.</p>
          <v-table density="compact" class="mb-3">
            <thead>
              <tr>
                <th>Колонка</th>
                <th style="width:110px">Обязательна</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Наименование</td><td><v-chip size="x-small" color="error">обяз.</v-chip></td></tr>
              <tr><td>ИНН</td><td><v-chip size="x-small" color="error">обяз., уникальный</v-chip></td></tr>
              <tr><td>КПП</td><td></td></tr>
              <tr><td>ОГРН</td><td></td></tr>
              <tr><td>Адрес местонахождения</td><td></td></tr>
              <tr><td>Почтовый адрес</td><td></td></tr>
              <tr><td>Подписант</td><td></td></tr>
              <tr><td>Основание</td><td></td></tr>
              <tr><td>Контактное лицо</td><td></td></tr>
              <tr><td>Телефон</td><td></td></tr>
              <tr><td>Email</td><td></td></tr>
              <tr><td>Расчётный счёт</td><td></td></tr>
              <tr><td>Банк</td><td></td></tr>
              <tr><td>БИК</td><td></td></tr>
              <tr><td>Корр. счёт</td><td></td></tr>
              <tr><td>Банковские реквизиты</td><td></td></tr>
            </tbody>
          </v-table>
          <p class="text-caption text-medium-emphasis">
            Колонки распознаются по частичному совпадению названия. Строки с дублирующимся ИНН пропускаются.
            Скачайте шаблон — там уже правильные заголовки и пример строки.
          </p>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn variant="text" prepend-icon="mdi-download" @click="downloadTemplate">Шаблон</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="importHintDialog = false">Отмена</v-btn>
          <v-btn color="success" variant="tonal" prepend-icon="mdi-microsoft-excel" @click="confirmImport">
            Выбрать файл
          </v-btn>
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
  product_categories: string[]
  manual_product_categories?: string[]
  org_type?: string
}

const contractors = ref<ContractorWithStats[]>([])
const loading     = ref(false)
const saving      = ref(false)
const importing   = ref(false)
const search      = ref('')
const filterCategory = ref<string | null>(null)
const dialog      = ref(false)
const deleteDialog     = ref(false)
const bulkDeleteDialog = ref(false)
const bulkDeleteConfirmCount = ref('')
const editId      = ref<number | null>(null)
const deleteTarget  = ref<ContractorWithStats | null>(null)
const formRef     = ref()
const excelInput  = ref<HTMLInputElement>()
const importHintDialog = ref(false)
const selectedIds = ref(new Set<number>())

// Categories dialog
const categoriesDialog = ref(false)
const categoriesDialogContractor = ref<ContractorWithStats | null>(null)

const snack = ref({ show: false, text: '', color: 'success' })

const emptyForm = () => ({
  name: '', inn: '', kpp: '', address: '',
  contact_person: '', phone: '', email: '', bank_details: '',
  signatory: '', signatory_basis: '', postal_address: '',
  ogrn: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
  org_type: '' as string | null,
  manual_product_categories: [] as string[],
})
const form = ref(emptyForm())

const allProductCategories = computed(() => {
  const cats = new Set<string>()
  contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') cats.add(p) }))
  return [...cats].sort()
})

// All known categories (from products + manual) — loaded from backend
const allKnownCategories = ref<string[]>([])

async function loadCategories() {
  try {
    allKnownCategories.value = await apiFetch<string[]>('/contractors/product-categories')
  } catch { /* ignore */ }
}

// Options for category combobox: backend list + any currently in form (user-typed new ones)
const categoryOptions = computed(() => {
  const set = new Set(allKnownCategories.value)
  // Add categories from loaded contractors too
  contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') set.add(p) }))
  return [...set].sort()
})

// "All categories" toggle
const allCategoriesToggle = computed({
  get: () => form.value.manual_product_categories?.includes('Все') ?? false,
  set: (val: boolean) => {
    if (val) {
      form.value.manual_product_categories = ['Все']
    } else {
      form.value.manual_product_categories = []
    }
  },
})

const filtered = computed(() => {
  let list = contractors.value
  const q = search.value?.toLowerCase() ?? ''
  if (q) list = list.filter(c => c.name.toLowerCase().includes(q) || (c.inn || '').includes(q))
  if (filterCategory.value) {
    const cat = filterCategory.value
    list = list.filter(c => c.product_categories.includes('Все') || c.product_categories.includes(cat))
  }
  return list
})

function clearFilters() {
  search.value = ''
  filterCategory.value = null
}

// ── Load ──────────────────────────────────────────
async function loadContractors() {
  loading.value = true
  try {
    contractors.value = await apiFetch<ContractorWithStats[]>('/contractors/with-stats')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

// ── Categories dialog ──────────────────────────────
function openCategoriesDialog(c: ContractorWithStats) {
  categoriesDialogContractor.value = c
  categoriesDialog.value = true
}


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
    manual_product_categories: mergeCategories(c.manual_product_categories || [], c.product_categories || []),
  }
  dialog.value = true
}

/** Merge manual + auto categories, deduplicate */
function mergeCategories(manual: string[], auto: string[]): string[] {
  if (manual.includes('Все')) return ['Все']
  return [...new Set([...manual, ...auto])]
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
    loadCategories()
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
    const res = await apiFetch<{ deleted: number; skipped_linked: number; skipped_not_found: number }>('/contractors/bulk', {
      method: 'DELETE',
      body: { ids } as any,
    })
    selectedIds.value = new Set()
    bulkDeleteDialog.value = false
    bulkDeleteConfirmCount.value = ''
    let msg = `Удалено: ${res.deleted}`
    if (res.skipped_linked) msg += `, пропущено (есть закупки): ${res.skipped_linked}`
    if (res.skipped_not_found) msg += `, не найдено: ${res.skipped_not_found}`
    showSnack(msg, res.skipped_linked ? 'warning' : 'success')
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
  importHintDialog.value = true
}

function confirmImport() {
  importHintDialog.value = false
  excelInput.value?.click()
}

async function downloadTemplate() {
  const token = localStorage.getItem('auth_token') || ''
  const res = await fetch('/api/contractors/import/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Ошибка скачивания шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'contractors_template.xlsx'; a.click()
  URL.revokeObjectURL(url)
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

onMounted(() => { loadContractors(); loadCategories() })
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
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Filters ── */
.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.search-count {
  font-size: 13px;
  color: var(--crm-text-muted);
  white-space: nowrap;
  margin-left: auto;
}

/* ── Table ── */
.table-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  overflow: hidden;
}
.contractors-table thead th {
  font-size: 11px !important;
  font-weight: 600 !important;
  color: var(--crm-text-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--crm-table-header);
  padding: 10px 14px !important;
  white-space: nowrap;
}
.contractors-table tbody td {
  padding: 10px 14px !important;
  vertical-align: top;
}
.contractor-row:hover td { background: var(--crm-surface-alt); }
.contractor-row--selected td { background: var(--crm-surface-hover); }
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
  color: var(--crm-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--crm-border);
}
</style>
