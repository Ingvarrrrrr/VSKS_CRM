<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Организации</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orgs.length }} организаций</span>
      </div>
      <v-spacer />
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
      <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
    </div>

    <v-data-table
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

    <!-- Edit org dialog -->
    <v-dialog v-model="editOrgDialog" max-width="640" scrollable>
      <v-card class="org-dialog-card">
        <v-card-title class="pa-4">Реквизиты организации</v-card-title>
        <v-card-text class="pa-4 pt-0" style="max-height:75vh">
          <v-alert
            v-if="editOrgItem.contractor_id"
            type="info" density="compact" variant="tonal" class="mb-3"
            icon="mdi-link-variant"
          >
            <div class="d-flex align-center flex-wrap" style="gap:8px">
              <span class="text-caption">
                Данные автоматически берутся из карточки контрагента.
                Редактируйте реквизиты в разделе «Контрагенты».
              </span>
              <v-btn
                size="x-small" variant="tonal" color="primary"
                prepend-icon="mdi-open-in-new"
                @click="goToContractor(editOrgItem.contractor_id)"
              >
                Открыть контрагента
              </v-btn>
            </div>
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
            v-model="editOrgItem.signatory" label="Подписант (ФИО, должность)"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!editOrgItem.contractor_id"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editOrgDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="editOrgSaving" @click="saveOrg">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- EGRUL diff confirm -->
    <v-dialog v-model="egrulDiffDialog" max-width="520" persistent>
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

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>

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
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

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
  { key: 'signatory', label: 'Подписант' },
]

const router = useRouter()
const orgs = ref<Org[]>([])
const loading = ref(false)
const search = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoad() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadOrgs(), 300)
}
const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

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
  signatory: '',
  contractor_id: null as number | null,
})
const egrulLoading = ref(false)
const egrulMessage = ref('')
const egrulMessageType = ref<'success' | 'info' | 'error'>('info')

const egrulDiffDialog = ref(false)
const egrulDiffItems = ref<{ label: string; old: string; new: string }[]>([])
const egrulDiffPending = ref<Record<string, string>>({})

async function enrichFromEgrul() {
  const inn = editOrgItem.value.inn?.trim()
  if (!inn || inn.length < 10) return
  egrulLoading.value = true
  egrulMessage.value = ''
  try {
    const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
    const mapped: Record<string, string> = {
      name: data.name || '',
      full_name: data.full_name || '',
      kpp: data.kpp || '',
      ogrn: data.ogrn || '',
      address: data.address || '',
      signatory: data.signatory || '',
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

async function openEditOrg(org: Org) {
  editOrgItem.value = {
    id: org.id,
    name: org.name || '',
    full_name: org.full_name || '',
    inn: org.inn || '',
    kpp: org.kpp || '',
    ogrn: org.ogrn || '',
    address: org.address || '',
    signatory: org.signatory || '',
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
      fill('signatory', data.signatory)
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
  editOrgSaving.value = true
  try {
    await apiFetch(`/organizations/${editOrgItem.value.id}`, {
      method: 'PUT',
      body: {
        name: editOrgItem.value.name,
        full_name: editOrgItem.value.full_name || null,
        inn: editOrgItem.value.inn || null,
        kpp: editOrgItem.value.kpp || null,
        ogrn: editOrgItem.value.ogrn || null,
        address: editOrgItem.value.address || null,
        signatory: editOrgItem.value.signatory || null,
        contractor_id: editOrgItem.value.contractor_id ?? null,
      }
    })
    editOrgDialog.value = false
    await loadOrgs()
    showSnack('Реквизиты сохранены')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
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

onMounted(loadOrgs)
</script>

<style scoped>
/* Phase 17.1-03 — fix label truncation for «Краткое название» and similar long labels
   inside the narrow Organization edit dialog */
.org-dialog-card :deep(.v-field-label) {
  white-space: nowrap;
  overflow: visible;
}
</style>
