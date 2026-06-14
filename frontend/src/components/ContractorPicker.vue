<template>
  <div>
    <v-autocomplete
      :model-value="modelValue"
      :items="contractors"
      item-title="name"
      item-value="id"
      :label="label"
      variant="outlined"
      density="compact"
      clearable
      auto-select-first
      :custom-filter="contractorFilter"
      :loading="contractorSearchLoading"
      :menu-props="{ maxWidth: 500 }"
      :hint="hint"
      persistent-hint
      @update:model-value="onSelect"
      @update:search="onContractorSearch"
      @click:clear="$emit('clear')"
    >
      <template #item="{ item, props: itemProps }">
        <v-list-item v-bind="itemProps" :title="undefined">
          <template #title>
            <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
          </template>
          <template #subtitle>
            <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
          </template>
        </v-list-item>
      </template>
      <template #append-inner>
        <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
          title="Добавить контрагента" @click.stop="openAddContractor" />
      </template>
    </v-autocomplete>

    <!-- Add contractor dialog -->
    <v-dialog v-model="addContractorDialog" max-width="700" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-account-plus" class="mr-2" />Новый контрагент
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <!-- Import from file -->
          <div class="mb-4 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Данные:</strong> система автоматически извлечёт реквизиты из карточки контрагента
              </div>
            </v-alert>
            <FileDropZone v-model="addContractorFile" accept=".xlsx,.xls,.pdf,.docx,.doc"
              hint="Excel, Word, PDF — перетащите или нажмите" class="mb-2" />
            <v-btn v-if="addContractorFile" variant="tonal" color="primary" size="small" :loading="addContractorImporting"
              @click="importContractorFromFile">Заполнить поля из файла</v-btn>
          </div>
          <v-select v-model="addContractorForm.org_type" :items="['Юридическое лицо', 'ИП', 'Самозанятый', 'Физическое лицо']"
            label="Тип организации" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="addContractorForm.name" label="Наименование организации *" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Обязательное поле']" />
          <v-row dense>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.inn" label="ИНН" variant="outlined" density="compact" hide-details
                @update:model-value="onAddContractorInnChange">
                <template #append-inner>
                  <v-btn icon="mdi-database-search" size="x-small" variant="text" color="blue" :disabled="!addContractorForm.inn || addContractorForm.inn.length < 10" @click="lookupContractorInn" title="Заполнить из ЕГРЮЛ (nalog.ru)" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.kpp" label="КПП" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-textarea v-model="addContractorForm.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <div class="text-caption text-medium-emphasis mt-4 mb-1">Подписант</div>
          <v-text-field v-model="addContractorForm.signatory" label="Подписант (ФИО, должность)" variant="outlined" density="compact" class="mb-3" hide-details />
          <div class="text-caption text-medium-emphasis mt-3 mb-1">Контакты</div>
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="addContractorForm.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mt-3" hide-details />
          <div class="text-caption text-medium-emphasis mt-4 mb-1">Банковские реквизиты</div>
          <v-text-field v-model="addContractorForm.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-text-field v-model="addContractorForm.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.bik" label="БИК" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addContractorDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="addContractorSaving" :disabled="!addContractorForm.name.trim()" @click="saveNewContractor">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ЕГРЮЛ diff dialog -->
    <v-dialog v-model="egrulDiffDialog" max-width="640" persistent :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
          Данные из ЕГРЮЛ отличаются
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <p class="text-body-2 text-medium-emphasis mb-3">
            По каждому полю выберите — обновить значение или оставить текущее.
          </p>
          <v-table density="compact">
            <thead>
              <tr><th>Поле</th><th>Сейчас</th><th>Из ЕГРЮЛ</th><th style="width:90px">Обновить</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in egrulDiffItems" :key="d.key">
                <td class="text-caption font-weight-medium">{{ d.label }}</td>
                <td class="text-caption text-medium-emphasis" style="max-width:200px;word-break:break-word">{{ d.old }}</td>
                <td class="text-caption" style="color:#4caf50;max-width:200px;word-break:break-word">{{ d.new }}</td>
                <td>
                  <v-checkbox
                    :model-value="egrulDiffPending[d.key] !== undefined"
                    density="compact" hide-details
                    @update:model-value="(v) => v ? (egrulDiffPending[d.key] = d.new) : (delete egrulDiffPending[d.key])"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="egrulDiffDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" @click="applyEgrulDiff" :disabled="Object.keys(egrulDiffPending).length === 0">
            Применить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()
import { useContractorsStore } from '@/stores/contractors'
import FileDropZone from '@/components/FileDropZone.vue'

interface Contractor { id: number; name: string; inn?: string }

const props = defineProps<{
  modelValue: number | null
  label?: string
  hint?: string
  initialContractor?: Contractor | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: number | null): void
  (e: 'select', c: Contractor | null): void
  (e: 'clear'): void
}>()

const label = computed(() => props.label || 'Контрагент')
const hint = computed(() => props.hint || 'Поставщик/исполнитель. Поиск по названию или ИНН')

const contractorsStore = useContractorsStore()
const contractors = ref<Contractor[]>([])

watch(() => props.initialContractor, (c) => {
  if (c && c.id && !contractors.value.find(x => x.id === c.id)) contractors.value.push({ ...c })
}, { immediate: true })

const snack = ref({ show: false, text: '', color: 'success' })
function showSnack(text: string, color = 'success') { snack.value = { show: true, text, color } }

const contractorFilter = (value: string, query: string, item?: any): boolean => {
  const q = query.toLowerCase()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}
const contractorSearchLoading = computed(() => contractorsStore.searching)
let _searchTimeout: any = null
function onContractorSearch(query: string) {
  clearTimeout(_searchTimeout)
  if (!query || query.length < 2) return
  _searchTimeout = setTimeout(async () => {
    const list = await contractorsStore.search(query, 50)
    const existing = new Set(contractors.value.map(c => c.id))
    for (const c of list) if (!existing.has(c.id)) contractors.value.push(c as Contractor)
  }, 300)
}
function onSelect(id: number | null) {
  emit('update:modelValue', id)
  emit('select', contractors.value.find(c => c.id === id) || null)
}

const addContractorDialog = ref(false)
const addContractorForm = reactive({
  name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '',
  contact_person: '', signatory: '', org_type: '' as string,
  bank_name: '', bik: '', settlement_account: '', correspondent_account: '',
})
const addContractorSaving = ref(false)
const addContractorFile = ref<File | null>(null)
const addContractorImporting = ref(false)
const egrulDiffDialog = ref(false)
const egrulDiffItems = ref<{ key: string; label: string; old: string; new: string }[]>([])
const egrulDiffPending = ref<Record<string, string>>({})

function openAddContractor() {
  Object.assign(addContractorForm, { name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '', contact_person: '', signatory: '', org_type: 'Юридическое лицо', bank_name: '', bik: '', settlement_account: '', correspondent_account: '' })
  addContractorFile.value = null
  addContractorDialog.value = true
}

async function saveNewContractor() {
  if (!addContractorForm.name.trim()) return
  addContractorSaving.value = true
  try {
    const created = await apiFetch<Contractor>('/contractors/', { method: 'POST', body: { ...addContractorForm } })
    contractors.value.push(created)
    contractorsStore.putToCache(created)
    emit('update:modelValue', created.id)
    emit('select', created)
    addContractorDialog.value = false
    showSnack('Контрагент добавлен')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    addContractorSaving.value = false
  }
}

async function importContractorFromFile() {
  if (!addContractorFile.value) return
  addContractorImporting.value = true
  try {
    const fd = new FormData()
    fd.append('file', addContractorFile.value)
    const res = await fetch('/api/contractors/import/preview', { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` }, body: fd })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    const headers = data.headers || []
    const sample = data.sample?.[0] || []
    const hints: Record<string, string[]> = {
      name: ['назван', 'наимен', 'name', 'органи'], inn: ['инн', 'inn'], kpp: ['кпп', 'kpp'],
      ogrn: ['огрн', 'ogrn'], address: ['адрес', 'address'], phone: ['телефон', 'phone'],
      email: ['email', 'mail'], contact_person: ['контакт', 'лицо'], signatory: ['подписант', 'директор'],
      bank_name: ['банк', 'bank'], bik: ['бик', 'bik'], settlement_account: ['расч', 'р/с'],
      correspondent_account: ['корр', 'к/с'],
    }
    for (const [field, kws] of Object.entries(hints)) {
      for (let i = 0; i < headers.length; i++) {
        const h = (headers[i] || '').toLowerCase()
        if (kws.some(k => h.includes(k)) && sample[i]) {
          (addContractorForm as any)[field] = String(sample[i]).trim()
          break
        }
      }
    }
    showSnack('Данные подтянуты из файла', 'info')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка чтения файла', 'error')
  } finally {
    addContractorImporting.value = false
  }
}

async function lookupContractorInn() {
  const inn = addContractorForm.inn?.trim()
  if (!inn || inn.length < 10) return
  try {
    const data = await apiFetch<any>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
    const FIELDS = [
      { key: 'name', label: 'Наименование' },
      { key: 'full_name', label: 'Полное наименование' },
      { key: 'kpp', label: 'КПП' },
      { key: 'ogrn', label: 'ОГРН' },
      { key: 'address', label: 'Адрес' },
      { key: 'signatory', label: 'Подписант' },
      { key: 'phone', label: 'Телефон' },
      { key: 'email', label: 'Email' },
      { key: 'bank_name', label: 'Банк' },
      { key: 'bik', label: 'БИК' },
      { key: 'settlement_account', label: 'Расчётный счёт' },
      { key: 'correspondent_account', label: 'Корр. счёт' },
    ]
    const diffs: { key: string; label: string; old: string; new: string }[] = []
    const pending: Record<string, string> = {}
    for (const f of FIELDS) {
      const newVal = (data?.[f.key] || '').toString().trim()
      const curVal = ((addContractorForm as any)[f.key] || '').toString().trim()
      if (newVal && newVal !== curVal) {
        diffs.push({ key: f.key, label: f.label, old: curVal || '—', new: newVal })
        pending[f.key] = newVal
      }
    }
    if (diffs.length === 0) {
      showSnack('Данные ЕГРЮЛ совпадают с текущими', 'info')
      return
    }
    egrulDiffItems.value = diffs
    egrulDiffPending.value = pending
    egrulDiffDialog.value = true
  } catch (e: any) {
    if (e?.payload?.code === 'INN_NOT_FOUND') {
      showSnack(e.payload.message, 'warning')
    } else {
      showSnack(e?.message || 'Ошибка запроса к ФНС', 'error')
    }
  }
}

function applyEgrulDiff() {
  for (const k of Object.keys(egrulDiffPending.value)) {
    (addContractorForm as any)[k] = egrulDiffPending.value[k]
  }
  egrulDiffDialog.value = false
  showSnack('Данные обновлены из ЕГРЮЛ', 'success')
}

let _addContractorInnTimeout: any = null
function onAddContractorInnChange(val: string) {
  clearTimeout(_addContractorInnTimeout)
  const inn = (val || '').replace(/\D/g, '')
  if (inn.length === 10 || inn.length === 12) {
    _addContractorInnTimeout = setTimeout(() => lookupContractorInn(), 400)
  }
}
</script>
