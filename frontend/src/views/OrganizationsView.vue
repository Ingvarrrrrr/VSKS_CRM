<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Организации</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orgs.length }} организаций</span>
      </div>
      <v-spacer />
      <v-btn
        v-if="canCreateOrg"
        color="primary"
        prepend-icon="mdi-domain-plus"
        @click="openCreateOrg"
      >
        Добавить организацию
      </v-btn>
      <v-text-field
        v-model="search"
        placeholder="Поиск по названию или ИНН..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 320px"
        @update:model-value="debouncedLoad"
      />
      <v-btn-toggle
        v-if="!mobile"
        v-model="viewMode"
        mandatory
        density="compact"
        variant="outlined"
        divided
        class="ml-1"
      >
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
      <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
      <RegistryExportButton
        title="Организации"
        :get-columns="() => visibleHeaders.filter(h => !['actions','avatar','data-table-expand','data-table-select'].includes(h.key) && !!h.title).map(h => ({ key: h.key, title: h.title, align: h.align }))"
        :get-rows="() => orgs"
        :get-capture-el="() => registryArea"
        @error="(msg) => showSnack(msg, 'error')"
      />
    </div>

    <div ref="registryArea">
    <v-data-table
        v-if="effectiveView === 'table'"
        v-resizable-columns="'organizations'"
        :headers="visibleHeaders"
        :items="orgs"
        :loading="loading"
        :search="search"
        density="comfortable"
        item-value="id"
      >
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            {{ item.is_active ? 'Активна' : 'Деактивирована' }}
          </v-chip>
        </template>
        <template v-slot:item.created_at="{ item }">
          <span class="text-caption">{{ formatDate(item.created_at) }}</span>
        </template>
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn
              icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
              title="Редактировать реквизиты"
              @click="openEditOrg(item)"
            />
            <v-btn
              :icon="item.is_active ? 'mdi-toggle-switch' : 'mdi-toggle-switch-off'"
              :color="item.is_active ? 'success' : 'grey'"
              size="x-small" variant="text"
              :title="item.is_active ? 'Деактивировать' : 'Активировать'"
              @click="toggleActive(item)"
            />
            <v-btn
              icon="mdi-delete-outline" size="x-small" variant="text" color="error"
              @click="confirmDelete(item)"
            />
          </div>
        </template>
      </v-data-table>
    <div v-else>
      <v-row dense>
        <v-col
          v-for="org in pagedCards"
          :key="org.id"
          cols="12" sm="6" lg="4"
        >
          <v-card hover class="h-100">
            <v-card-item>
              <v-card-title class="text-body-1 font-weight-bold" style="white-space:normal; word-break:break-word; line-height:1.25">{{ org.name }}</v-card-title>
              <v-card-subtitle v-if="org.full_name && org.full_name !== org.name" class="text-caption" style="white-space:normal; word-break:break-word; line-height:1.2">
                {{ org.full_name }}
              </v-card-subtitle>
            </v-card-item>
            <v-card-text class="pt-0">
              <div class="d-flex flex-wrap align-center" style="gap:6px">
                <v-chip
                  :color="org.is_active ? 'success' : 'error'"
                  size="x-small"
                  variant="tonal"
                >
                  {{ org.is_active ? 'Активна' : 'Деактивирована' }}
                </v-chip>
                <span v-if="org.inn" class="text-caption text-medium-emphasis">ИНН: {{ org.inn }}</span>
              </div>
              <div class="text-caption text-medium-emphasis mt-2">
                <v-icon size="x-small" class="mr-1">mdi-account-multiple-outline</v-icon>
                Пользователей: {{ org.user_count }}
              </div>
              <div class="text-caption text-medium-emphasis mt-1">
                Создана: {{ formatDate(org.created_at) }}
              </div>
            </v-card-text>
            <v-card-actions @click.stop>
              <v-btn
                icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                title="Редактировать реквизиты"
                @click="openEditOrg(org)"
              />
              <v-btn
                :icon="org.is_active ? 'mdi-toggle-switch' : 'mdi-toggle-switch-off'"
                :color="org.is_active ? 'success' : 'grey'"
                size="x-small" variant="text"
                :title="org.is_active ? 'Деактивировать' : 'Активировать'"
                @click="toggleActive(org)"
              />
              <v-btn
                icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                @click="confirmDelete(org)"
              />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!pagedCards.length" class="text-center py-10 text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-domain-off</v-icon>
        <div>Организации не найдены</div>
      </div>
      <v-pagination
        v-if="cardsTotalPages > 1"
        v-model="cardsPage"
        :length="cardsTotalPages"
        density="compact"
        total-visible="7"
        class="d-flex justify-center mt-4"
      />
    </div>
    </div>

    <!-- Edit org dialog -->
    <v-dialog v-model="editOrgDialog" max-width="640" scrollable :fullscreen="mobile">
      <v-card class="org-dialog-card">
        <v-card-title class="pa-4">{{ editOrgItem.id ? 'Реквизиты организации' : 'Новая организация' }}</v-card-title>
        <v-card-text class="pa-4 pt-0" style="max-height:75vh">
          <v-alert
            v-if="editOrgItem.contractor_id"
            type="info" density="compact" variant="tonal" class="mb-3"
            icon="mdi-link-variant"
          >
            <div class="d-flex align-center flex-wrap" style="gap:8px">
              <span class="text-caption">
                Полные реквизиты хранятся в карточке контрагента.
              </span>
              <v-btn
                size="x-small" variant="flat" color="primary"
                prepend-icon="mdi-pencil-outline"
                @click="openContractorEdit(editOrgItem.contractor_id!)"
              >
                Редактировать реквизиты
              </v-btn>
              <v-btn
                size="x-small" variant="text" color="primary"
                prepend-icon="mdi-open-in-new"
                @click="goToContractor(editOrgItem.contractor_id!)"
              >
                Открыть контрагента
              </v-btn>
            </div>
          </v-alert>
          <v-alert
            v-if="!editOrgItem.contractor_id"
            type="info" density="compact" variant="tonal" class="mb-3"
            icon="mdi-information-outline"
          >
            <span class="text-caption">Укажите ИНН — будет создана карточка контрагента с полными реквизитами.</span>
          </v-alert>

          <v-text-field
            v-model="editOrgItem.name" label="Краткое название *"
            variant="outlined" density="compact" class="mb-2"
          />
          <v-text-field
            v-model="editOrgItem.full_name" label="Полное наименование"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!editOrgItem.contractor_id"
            :hint="editOrgItem.contractor_id ? 'Поле берётся из контрагента' : ''"
            :persistent-hint="!!editOrgItem.contractor_id"
          />

          <div class="d-flex gap-2 align-start mb-1">
            <v-text-field
              v-model="editOrgItem.inn" label="ИНН"
              variant="outlined" density="compact" style="flex:1"
              hint="10 (юр.лицо) или 12 (ИП) цифр" persistent-hint
              :readonly="!!editOrgItem.contractor_id"
            />
            <v-text-field
              v-model="editOrgItem.kpp" label="КПП"
              variant="outlined" density="compact" style="max-width:130px" hide-details
              :readonly="!!editOrgItem.contractor_id"
            />
            <v-text-field
              v-model="editOrgItem.ogrn" label="ОГРН"
              variant="outlined" density="compact" style="max-width:150px" hide-details
              :readonly="!!editOrgItem.contractor_id"
            />
          </div>

          <v-btn
            v-if="!editOrgItem.contractor_id"
            variant="tonal" color="primary" size="small" class="mt-3 mb-2"
            prepend-icon="mdi-database-search-outline"
            :loading="egrulLoading"
            :disabled="!editOrgItem.inn || editOrgItem.inn.length < 10"
            @click="enrichFromEgrul"
          >
            Заполнить на основании ИНН из ЕГРЮЛ
          </v-btn>

          <v-alert v-if="egrulMessage" :type="egrulMessageType" density="compact" variant="tonal" class="mb-3 text-caption" closable @click:close="egrulMessage = ''">
            {{ egrulMessage }}
          </v-alert>

          <v-text-field
            v-model="editOrgItem.address" label="Адрес"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!editOrgItem.contractor_id"
          />
          <v-text-field
            v-model="editOrgItem.signatory_position" label="Должность подписанта"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!editOrgItem.contractor_id"
          />
          <v-row dense class="mb-2">
            <v-col cols="4">
              <v-text-field v-model="editOrgItem.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details :readonly="!!editOrgItem.contractor_id" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="editOrgItem.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details :readonly="!!editOrgItem.contractor_id" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="editOrgItem.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details :readonly="!!editOrgItem.contractor_id" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editOrgDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="editOrgSaving" @click="saveOrg">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- EGRUL diff confirm -->
    <v-dialog v-model="egrulDiffDialog" max-width="520" persistent :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 text-subtitle-1 font-weight-bold">
          <v-icon color="primary" class="mr-2">mdi-database-sync-outline</v-icon>
          Данные из ЕГРЮЛ отличаются
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <p class="text-body-2 text-medium-emphasis mb-3">Следующие поля изменятся. Обновить?</p>
          <v-table density="compact">
            <thead><tr><th>Поле</th><th>Сейчас</th><th>Из ЕГРЮЛ</th></tr></thead>
            <tbody>
              <tr v-for="d in egrulDiffItems" :key="d.label">
                <td class="text-caption font-weight-medium">{{ d.label }}</td>
                <td class="text-caption text-medium-emphasis">{{ d.old }}</td>
                <td class="text-caption" style="color:var(--v-theme-success,#4caf50)">{{ d.new }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="egrulDiffDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" @click="applyEgrulDiff">Обновить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ContractorEditDialog — редактирование реквизитов контрагента из карточки org -->
    <ContractorEditDialog
      v-model="contractorEditDialog"
      :contractor-id="contractorEditId"
      @saved="onContractorSaved"
    />

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="360">
      <v-card>
        <v-card-title class="pa-4">Удалить организацию?</v-card-title>
        <v-card-text>
          <strong>{{ deleteDialog.item?.name }}</strong><br>
          <span class="text-caption text-error">Будут удалены все данные организации: субсидии, закупки, пользователи.</span>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { useCardView } from '@/composables/useCardView'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import ContractorEditDialog from '@/components/ContractorEditDialog.vue'
import { useToast, type ToastType } from '@/composables/useToast'

interface Org {
  id: number
  name: string
  full_name?: string
  inn?: string
  kpp?: string
  ogrn?: string
  address?: string
  signatory?: string
  is_active: boolean
  created_at: string
  user_count: number
  contractor_id?: number | null
}

const EGRUL_FIELDS = [
  { key: 'name', label: 'Краткое название' },
  { key: 'full_name', label: 'Полное наименование' },
  { key: 'kpp', label: 'КПП' },
  { key: 'ogrn', label: 'ОГРН' },
  { key: 'address', label: 'Адрес' },
  { key: 'signatory_last_name', label: 'Фамилия подписанта' },
  { key: 'signatory_first_name', label: 'Имя подписанта' },
  { key: 'signatory_middle_name', label: 'Отчество подписанта' },
  { key: 'signatory_position', label: 'Должность подписанта' },
]

const router = useRouter()
const route = useRoute()
// Создавать организации могут только владельцы контура (superadmin / account_owner) —
// бэкенд POST /organizations требует OWNER_ROLES.
const canCreateOrg = computed(() =>
  ['superadmin', 'account_owner'].includes(localStorage.getItem('user_role') || '')
)
const registryArea = ref<HTMLElement | null>(null)
const orgs = ref<Org[]>([])
const loading = ref(false)
const search = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoad() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadOrgs(), 300)
}
const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const deleteDialog = reactive({ show: false, item: null as Org | null, deleting: false })

const editOrgDialog = ref(false)
const editOrgSaving = ref(false)
const editOrgItem = ref({
  id: 0,
  name: '',
  full_name: '',
  inn: '',
  kpp: '',
  ogrn: '',
  address: '',
  signatory_last_name: '',
  signatory_first_name: '',
  signatory_middle_name: '',
  signatory_position: '',
  contractor_id: null as number | null,
})
const egrulLoading = ref(false)
const egrulMessage = ref('')
const egrulMessageType = ref<'success' | 'info' | 'error'>('info')

const egrulDiffDialog = ref(false)
const egrulDiffItems = ref<{ label: string; old: string; new: string }[]>([])
const egrulDiffPending = ref<Record<string, string>>({})

// ContractorEditDialog — открытие из карточки организации
const contractorEditDialog = ref(false)
const contractorEditId = ref<number | null>(null)

function openContractorEdit(contractorId: number) {
  contractorEditId.value = contractorId
  contractorEditDialog.value = true
}

async function onContractorSaved() {
  contractorEditDialog.value = false
  await loadOrgs()
  showSnack('Реквизиты контрагента обновлены')
}

async function enrichFromEgrul() {
  const inn = editOrgItem.value.inn?.trim()
  if (!inn || inn.length < 10) return
  egrulLoading.value = true
  egrulMessage.value = ''
  try {
    const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
    if (data._source === 'npd') {
      egrulMessage.value = data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`
      egrulMessageType.value = 'warning'
      return
    }
    const mapped: Record<string, string> = {
      name: data.name || '',
      full_name: data.full_name || '',
      kpp: data.kpp || '',
      ogrn: data.ogrn || '',
      address: data.address || '',
      signatory_last_name: data.signatory_last_name || '',
      signatory_first_name: data.signatory_first_name || '',
      signatory_middle_name: data.signatory_middle_name || '',
      signatory_position: data.signatory_position || '',
    }
    const diffs: { label: string; old: string; new: string }[] = []
    for (const f of EGRUL_FIELDS) {
      const newVal = mapped[f.key] || ''
      const curVal = (editOrgItem.value as any)[f.key] || ''
      if (newVal && newVal !== curVal) {
        diffs.push({ label: f.label, old: curVal, new: newVal })
      }
    }
    if (diffs.length === 0) {
      egrulMessage.value = 'Данные из ЕГРЮЛ совпадают с текущими'
      egrulMessageType.value = 'info'
    } else {
      egrulDiffItems.value = diffs
      egrulDiffPending.value = mapped
      egrulDiffDialog.value = true
    }
  } catch (e: any) {
    if (e?.payload?.code === 'INN_NOT_FOUND') {
      egrulMessage.value = e.payload.message
      egrulMessageType.value = 'warning'
    } else {
      egrulMessage.value = e?.message || 'Ошибка запроса к ФНС'
      egrulMessageType.value = 'error'
    }
  } finally {
    egrulLoading.value = false
  }
}

function applyEgrulDiff() {
  for (const f of EGRUL_FIELDS) {
    const val = egrulDiffPending.value[f.key]
    if (val) (editOrgItem.value as any)[f.key] = val
  }
  egrulDiffDialog.value = false
  egrulMessage.value = 'Данные обновлены из ЕГРЮЛ'
  egrulMessageType.value = 'success'
}

function openCreateOrg() {
  editOrgItem.value = {
    id: 0,
    name: '',
    full_name: '',
    inn: '',
    kpp: '',
    ogrn: '',
    address: '',
    signatory_last_name: '',
    signatory_first_name: '',
    signatory_middle_name: '',
    signatory_position: '',
    contractor_id: null,
  }
  egrulMessage.value = ''
  editOrgDialog.value = true
}

async function openEditOrg(org: Org) {
  editOrgItem.value = {
    id: org.id,
    name: org.name || '',
    full_name: org.full_name || '',
    inn: org.inn || '',
    kpp: org.kpp || '',
    ogrn: org.ogrn || '',
    address: org.address || '',
    signatory_last_name: (org as any).signatory_last_name || '',
    signatory_first_name: (org as any).signatory_first_name || '',
    signatory_middle_name: (org as any).signatory_middle_name || '',
    signatory_position: (org as any).signatory_position || '',
    contractor_id: org.contractor_id ?? null,
  }
  egrulMessage.value = ''
  editOrgDialog.value = true

  // Phase 17.1-03: if org is not yet linked to a contractor but has an INN —
  // prefill empty fields from the matching Contractor (if any).
  if (!org.contractor_id && org.inn) {
    try {
      const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${org.inn.trim()}`)
      // Only fill fields that are still empty — never overwrite existing values.
      const fill = (key: keyof typeof editOrgItem.value, value: any) => {
        if (!((editOrgItem.value as any)[key] || '').toString().trim() && value) {
          ;(editOrgItem.value as any)[key] = value
        }
      }
      fill('full_name', data.full_name)
      fill('kpp', data.kpp)
      fill('ogrn', data.ogrn)
      fill('address', data.address)
      fill('signatory_last_name', data.signatory_last_name)
      fill('signatory_first_name', data.signatory_first_name)
      fill('signatory_middle_name', data.signatory_middle_name)
      fill('signatory_position', data.signatory_position)
    } catch {
      // silent — prefill is best-effort
    }
  }
}

function goToContractor(contractorId: number) {
  editOrgDialog.value = false
  router.push({ path: '/contractors', query: { id: String(contractorId) } })
}

async function saveOrg() {
  if (!editOrgItem.value.name?.trim()) {
    showSnack('Укажите краткое название организации', 'error')
    return
  }
  const isCreate = !editOrgItem.value.id
  editOrgSaving.value = true
  try {
    const body = {
      name: editOrgItem.value.name,
      full_name: editOrgItem.value.full_name || null,
      inn: editOrgItem.value.inn || null,
      kpp: editOrgItem.value.kpp || null,
      ogrn: editOrgItem.value.ogrn || null,
      address: editOrgItem.value.address || null,
      signatory_last_name: editOrgItem.value.signatory_last_name || null,
      signatory_first_name: editOrgItem.value.signatory_first_name || null,
      signatory_middle_name: editOrgItem.value.signatory_middle_name || null,
      signatory_position: editOrgItem.value.signatory_position || null,
      contractor_id: editOrgItem.value.contractor_id ?? null,
    }
    if (isCreate) {
      await apiFetch(`/organizations/`, { method: 'POST', body })
    } else {
      await apiFetch(`/organizations/${editOrgItem.value.id}`, { method: 'PUT', body })
    }
    editOrgDialog.value = false
    await loadOrgs()
    showSnack(isCreate ? 'Организация создана' : 'Реквизиты сохранены')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка сохранения', 'error')
  } finally {
    editOrgSaving.value = false
  }
}

const allColumns: ColumnDef[] = [
  { title: 'ID', key: 'id', width: 60 },
  { title: 'Название', key: 'name' },
  { title: 'ИНН', key: 'inn', width: 120 },
  { title: 'Пользователи', key: 'user_count', width: 120 },
  { title: 'Статус', key: 'is_active', width: 140 },
  { title: 'Создана', key: 'created_at', width: 160 },
  { title: '', key: 'actions', width: 80, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('organizations', allColumns)
const showColumnPicker = ref(false)

const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedCards,
} = useCardView({
  storageKey: 'organizations_view_mode',
  source: () => orgs.value,
  search: () => search.value,
  searchFields: (o: Org) => [o.name, o.full_name, o.inn],
  pageSize: 24,
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('ru-RU')
}

async function loadOrgs() {
  loading.value = true
  try {
    orgs.value = await apiFetch<Org[]>('/organizations/')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

async function toggleActive(org: Org) {
  try {
    const res = await apiFetch<{ id: number; is_active: boolean }>(`/organizations/${org.id}/toggle-active`, { method: 'PATCH' })
    const idx = orgs.value.findIndex(o => o.id === org.id)
    if (idx >= 0) orgs.value[idx].is_active = res.is_active
    showSnack(res.is_active ? 'Организация активирована' : 'Организация деактивирована')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

function confirmDelete(org: Org) {
  deleteDialog.item = org
  deleteDialog.show = true
}

async function doDelete() {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/organizations/${deleteDialog.item.id}`, { method: 'DELETE' })
    orgs.value = orgs.value.filter(o => o.id !== deleteDialog.item!.id)
    deleteDialog.show = false
    showSnack('Организация удалена')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

onMounted(async () => {
  await loadOrgs()
  // Открыть форму создания, если перешли сюда с ?create=1 (напр. из «Персонала»)
  if (route.query.create && canCreateOrg.value) {
    openCreateOrg()
    router.replace({ query: {} })
  }
})
</script>

<style scoped>
/* Phase 17.1-03 — fix label truncation for «Краткое название» and similar long labels
   inside the narrow Organization edit dialog */
.org-dialog-card :deep(.v-field-label) {
  white-space: nowrap;
  overflow: visible;
}
</style>
