<template>
  <v-dialog :model-value="modelValue" max-width="780" persistent scrollable :fullscreen="mobile"
    @update:model-value="emit('update:modelValue', $event)">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon :icon="contractorId ? 'mdi-pencil-outline' : 'mdi-plus-circle-outline'" color="primary" class="mr-2" />
        {{ contractorId ? 'Редактировать контрагента' : 'Добавить контрагента' }}
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4" style="max-height:75vh">
        <v-progress-linear v-if="loadingContractor" indeterminate color="primary" class="mb-3" />
        <v-alert
          v-if="existingContractor"
          type="info"
          density="compact"
          class="mb-2"
        >
          Контрагент с таким ИНН уже существует в базе:
          <strong>{{ existingContractor.name }}</strong>
          <template #append>
            <v-btn size="small" color="primary" variant="tonal" @click="openExistingContractor">
              Открыть карточку
            </v-btn>
          </template>
        </v-alert>
        <v-form ref="formRef">
          <div class="section-label">Загрузить из файла</div>
          <div class="mb-4 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Данные:</strong> система автоматически извлечёт реквизиты из карточки контрагента
              </div>
            </v-alert>
            <FileDropZone v-model="contractorCardFile" accept=".xlsx,.xls,.pdf,.docx,.doc"
              hint="Excel, Word, PDF — карточка реквизитов" class="mb-2" />
            <v-btn v-if="contractorCardFile" variant="tonal" color="primary" size="small" :loading="contractorCardImporting"
              @click="importFromCardFile">Заполнить поля из файла</v-btn>
          </div>

          <div class="section-label">Основные данные</div>
          <v-row dense class="mb-0">
            <v-col cols="4">
              <v-text-field v-model="form.inn" label="ИНН" variant="outlined" density="compact" hide-details
                @update:model-value="onInnChange" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.kpp" label="КПП" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="3">
              <v-text-field v-model="form.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-row dense class="mb-0 mt-2">
            <v-col cols="3">
              <v-text-field v-model="form.okpo" label="ОКПО" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.okved" label="ОКВЭД (осн.)" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.registration_date" label="Дата регистрации" type="date" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-btn
            variant="tonal" color="primary" size="small" class="mt-2 mb-2"
            prepend-icon="mdi-database-search-outline"
            :loading="fnsLoading"
            :disabled="!form.inn || form.inn.length < 10 || !!existingContractor"
            @click="lookupFns(true)"
          >
            Заполнить на основании ИНН из ЕГРЮЛ
          </v-btn>
          <v-alert v-if="fnsMessage" :type="fnsMessageType" variant="tonal" density="compact" class="mb-2 text-caption" closable @click:close="fnsMessage = ''">
            {{ fnsMessage }}
          </v-alert>
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
            label="Краткое наименование *"
            variant="outlined"
            density="compact"
            :rules="[v => !!v || 'Обязательное поле']"
            class="mb-2"
            hide-details="auto"
          />
          <v-text-field
            v-model="form.full_name"
            label="Полное наименование"
            variant="outlined"
            density="compact"
            class="mb-3"
            hide-details
          />
          <v-textarea v-model="form.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <v-textarea v-model="form.postal_address" label="Почтовый адрес" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

          <div class="section-label mt-4">Подписант</div>
          <v-row dense class="mb-3">
            <v-col cols="7">
              <v-text-field v-model="form.signatory" label="Подписант (ФИО)" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="5">
              <v-text-field v-model="form.signatory_position" label="Должность подписанта" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="form.signatory_basis" label="На основании чего действует" variant="outlined" density="compact" hide-details
            placeholder="Устава, доверенности №..." />

          <div class="section-label mt-4">Контакты</div>
          <v-row dense class="mb-3">
            <v-col cols="6">
              <v-text-field
                :model-value="formatPhoneRu(form.org_phone)"
                @update:model-value="form.org_phone = unformatPhone($event)"
                label="Телефон организации" variant="outlined" density="compact" hide-details
                placeholder="8-999-999-99-99"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="form.org_email" label="Email организации" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="form.website" label="Сайт организации" variant="outlined" density="compact" class="mt-2 mb-2" hide-details placeholder="https://..." />
          <v-text-field v-model="form.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                :model-value="formatPhoneRu(form.phone)"
                @update:model-value="form.phone = unformatPhone($event)"
                label="Телефон контактного лица" variant="outlined" density="compact" hide-details
                placeholder="8-999-999-99-99"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="form.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
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
          <v-row dense class="mt-2">
            <v-col cols="6">
              <v-text-field v-model="form.treasury_account" label="Казначейский счёт" variant="outlined" density="compact" hide-details maxlength="30" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="form.single_treasury_account" label="Единый казначейский счёт" variant="outlined" density="compact" hide-details maxlength="30" />
            </v-col>
          </v-row>
          <v-textarea v-model="form.bank_details" label="Банковские реквизиты (свободное поле)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

          <!-- ── Реквизиты физ.лица (ГПХ) — только для Физ.лицо ── -->
          <template v-if="form.org_type === 'Физ.лицо'">
            <div class="section-label mt-4">Реквизиты физ.лица (ГПХ)</div>
            <v-row dense class="mb-2">
              <v-col cols="4">
                <v-text-field
                  v-model="form.passport_series"
                  label="Серия паспорта"
                  variant="outlined"
                  density="compact"
                  hide-details
                  maxlength="4"
                  placeholder="1234"
                />
              </v-col>
              <v-col cols="8">
                <v-text-field
                  v-model="form.passport_number"
                  label="Номер паспорта"
                  variant="outlined"
                  density="compact"
                  hide-details
                  maxlength="6"
                  placeholder="567890"
                />
              </v-col>
            </v-row>
            <v-textarea
              v-model="form.passport_issuer"
              label="Кем выдан"
              variant="outlined"
              density="compact"
              rows="2"
              class="mb-2"
              hide-details
            />
            <v-row dense class="mb-2">
              <v-col cols="6">
                <v-text-field
                  v-model="form.passport_issued_date"
                  label="Дата выдачи паспорта"
                  type="date"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="form.birth_date"
                  label="Дата рождения"
                  type="date"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
              </v-col>
            </v-row>
            <v-text-field
              v-model="form.snils"
              label="СНИЛС"
              variant="outlined"
              density="compact"
              class="mb-2"
              hide-details
              maxlength="14"
              placeholder="000-000-000 00"
            />
            <v-textarea
              v-model="form.registration_address"
              label="Адрес регистрации"
              variant="outlined"
              density="compact"
              rows="2"
              class="mb-2"
              hide-details
            />
          </template>

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
        <v-btn variant="text" @click="close">Отмена</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!!existingContractor" @click="save">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── EGRUL diff confirm ── -->
  <v-dialog v-model="egrulDiffDialog" max-width="520" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 text-subtitle-1 font-weight-bold">
        <v-icon color="primary" class="mr-2">mdi-database-sync-outline</v-icon>
        Данные из ЕГРЮЛ отличаются
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <p class="text-body-2 text-medium-emphasis mb-3">Следующие поля изменились. Обновить?</p>
        <v-table density="compact">
          <thead>
            <tr>
              <th>Поле</th>
              <th>Сейчас</th>
              <th>Из ЕГРЮЛ</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in egrulDiffItems" :key="d.label">
              <td class="text-caption font-weight-medium">{{ d.label }}</td>
              <td class="text-caption text-medium-emphasis">{{ d.old }}</td>
              <td class="text-caption text-success">{{ d.new }}</td>
            </tr>
          </tbody>
        </v-table>
        <p class="text-caption text-medium-emphasis mt-3">Поля не из ЕГРЮЛ (контактное лицо, основание, реквизиты) останутся без изменений.</p>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="egrulDiffDialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" @click="applyEgrulDiff">Обновить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── Snackbar ── -->
  <v-snackbar v-model="snack.show" :color="snack.color" :timeout="4000" location="bottom right">
    {{ snack.text }}
  </v-snackbar>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'

const { mobile } = useDisplay()

interface ContractorFull {
  id: number
  name: string
  full_name?: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  org_phone?: string
  email?: string
  org_email?: string
  bank_details?: string
  signatory?: string
  signatory_basis?: string
  postal_address?: string
  ogrn?: string
  settlement_account?: string
  bank_name?: string
  bik?: string
  correspondent_account?: string
  product_categories?: string[]
  manual_product_categories?: string[]
  org_type?: string
  passport_series?: string
  passport_number?: string
  passport_issuer?: string
  passport_issued_date?: string
  snils?: string
  registration_address?: string
  birth_date?: string
  website?: string
  registration_date?: string
  okpo?: string
  okved?: string
  treasury_account?: string
  single_treasury_account?: string
  signatory_position?: string
}

const props = defineProps<{
  modelValue: boolean
  contractorId: number | null
  prefillInn?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'saved', contractor: ContractorFull): void
}>()

// ── State ─────────────────────────────────────────
const saving      = ref(false)
const fnsLoading  = ref(false)
const fnsMessage  = ref('')
const fnsMessageType = ref<'success' | 'info' | 'error' | 'warning'>('info')
const existingContractor = ref<{ id: number; name: string } | null>(null)
const loadingContractor = ref(false)
const formRef     = ref()
const editId      = ref<number | null>(null)

const snack = ref({ show: false, text: '', color: 'success' })
function showSnack(text: string, color = 'success') {
  snack.value = { show: true, text, color }
}

// Confirmation dialog for EGRUL diff
const egrulDiffDialog = ref(false)
const egrulDiffItems = ref<{ label: string; old: string; new: string }[]>([])
const egrulDiffPending = ref<Record<string, string>>({})

// Fields that come from EGRUL (overwrite always) vs fields we never touch from EGRUL
const EGRUL_FIELDS: { key: string; label: string }[] = [
  { key: 'name',      label: 'Краткое наименование' },
  { key: 'full_name', label: 'Полное наименование' },
  { key: 'kpp',       label: 'КПП' },
  { key: 'ogrn',      label: 'ОГРН' },
  { key: 'address',   label: 'Адрес' },
  { key: 'org_type',  label: 'Форма организации' },
  { key: 'signatory', label: 'Подписант' },
]

const contractorCardFile = ref<File | null>(null)
const contractorCardImporting = ref(false)

// ── Form ──────────────────────────────────────────
const emptyForm = () => ({
  name: '', full_name: '', inn: '', kpp: '', address: '',
  contact_person: '', phone: '', email: '', org_phone: '', org_email: '', bank_details: '',
  signatory: '', signatory_basis: '', postal_address: '',
  ogrn: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
  org_type: '' as string | null,
  manual_product_categories: [] as string[],
  passport_series: '', passport_number: '', passport_issuer: '',
  passport_issued_date: '', snils: '', registration_address: '', birth_date: '',
  website: '', registration_date: '', okpo: '', okved: '',
  treasury_account: '', single_treasury_account: '', signatory_position: '',
})
const form = ref(emptyForm())

// ── Categories ────────────────────────────────────
const allKnownCategories = ref<string[]>([])

async function loadCategories() {
  try {
    allKnownCategories.value = await apiFetch<string[]>('/contractors/product-categories')
  } catch { /* ignore */ }
}

const categoryOptions = computed(() => {
  return [...new Set(allKnownCategories.value)].sort()
})

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

/** Merge manual + auto categories, deduplicate */
function mergeCategories(manual: string[], auto: string[]): string[] {
  if (manual.includes('Все')) return ['Все']
  return [...new Set([...manual, ...auto])]
}

// ── INN / EGRUL lookup ────────────────────────────
let _innTimeout: any = null
function onInnChange(val: string) {
  clearTimeout(_innTimeout)
  existingContractor.value = null
  const inn = (val || '').replace(/\D/g, '')
  if (inn.length === 10 || inn.length === 12) {
    _innTimeout = setTimeout(() => lookupFns(), 400)
  }
}

async function lookupFns(forceEgrul = false) {
  const inn = form.value.inn?.trim()
  if (!inn || inn.length < 10) return
  fnsLoading.value = true
  fnsMessage.value = ''
  try {
    const url = forceEgrul ? `/contractors/lookup-inn/${inn}?force_egrul=1` : `/contractors/lookup-inn/${inn}`
    const data = await apiFetch<Record<string, any>>(url)
    const source = (data as any)._source === 'local' ? 'нашей БД' : 'ЕГРЮЛ'

    // If the lookup found an existing local contractor (not the one being edited) — show alert
    if ((data as any)._source === 'local' && (data as any).id && (data as any).id !== editId.value) {
      existingContractor.value = { id: (data as any).id, name: (data as any).name || '' }
      fnsMessage.value = ''
      fnsMessageType.value = 'info'
      return
    } else {
      existingContractor.value = null
    }

    // Build diff: compare EGRUL fields with current form values
    const diffs: { label: string; old: string; new: string }[] = []
    const pending: Record<string, string> = {}
    for (const { key, label } of EGRUL_FIELDS) {
      const incoming = (data[key] || '').toString().trim()
      const current = ((form.value as any)[key] || '').toString().trim()
      if (incoming && incoming !== current) {
        diffs.push({ label, old: current || '(пусто)', new: incoming })
        pending[key] = incoming
      }
    }

    if (diffs.length === 0) {
      fnsMessage.value = `Данные из ${source} совпадают с текущими — изменений нет`
      fnsMessageType.value = 'info'
      return
    }

    // Show confirmation dialog
    egrulDiffItems.value = diffs
    egrulDiffPending.value = pending
    egrulDiffDialog.value = true
    fnsMessage.value = `Получены данные из ${source}. Подтвердите обновление.`
    fnsMessageType.value = 'info'
  } catch (e: any) {
    if (e?.payload?.code === 'INN_NOT_FOUND') {
      fnsMessage.value = e.payload.message
      fnsMessageType.value = 'warning'
    } else {
      fnsMessage.value = e.message || 'Ошибка запроса к ФНС'
      fnsMessageType.value = 'error'
    }
  } finally {
    fnsLoading.value = false
  }
}

function applyEgrulDiff() {
  for (const [key, val] of Object.entries(egrulDiffPending.value)) {
    ;(form.value as any)[key] = val
  }
  fnsMessage.value = `Обновлено: ${egrulDiffItems.value.map(d => d.label).join(', ')}`
  fnsMessageType.value = 'success'
  egrulDiffDialog.value = false
}

// ── Import from card file ─────────────────────────
async function importFromCardFile() {
  if (!contractorCardFile.value) return
  contractorCardImporting.value = true
  try {
    const fd = new FormData()
    fd.append('file', contractorCardFile.value)
    const data = await apiFetch<any>('/contractors/parse-file', { method: 'POST', body: fd })
    const fieldLabels: Record<string, string> = {
      name: 'Наименование', inn: 'ИНН', kpp: 'КПП', ogrn: 'ОГРН',
      address: 'Адрес', phone: 'Телефон', email: 'Email',
      signatory: 'Подписант', bik: 'БИК', settlement_account: 'Р/С',
      correspondent_account: 'К/С', bank_name: 'Банк', org_type: 'Тип',
    }
    const filled: string[] = []
    for (const [field, label] of Object.entries(fieldLabels)) {
      if (data[field]) {
        (form.value as any)[field] = data[field]
        filled.push(label)
      }
    }
    fnsMessage.value = filled.length ? `Заполнено из файла: ${filled.join(', ')}` : 'Файл прочитан, но данные не распознаны'
    fnsMessageType.value = filled.length ? 'success' : 'warning'
    contractorCardFile.value = null
  } catch (e: any) {
    fnsMessage.value = e.message || 'Ошибка чтения файла'
    fnsMessageType.value = 'error'
  } finally {
    contractorCardImporting.value = false
  }
}

// ── Open existing contractor (from duplicate banner) ──
async function openExistingContractor() {
  if (!existingContractor.value) return
  const targetId = existingContractor.value.id
  existingContractor.value = null
  await fillFromContractorId(targetId)
}

// ── Load / fill ───────────────────────────────────
function fillForm(c: ContractorFull) {
  editId.value = c.id
  form.value = {
    name:                 c.name,
    full_name:            c.full_name            || '',
    inn:                  c.inn                  || '',
    kpp:                  c.kpp                  || '',
    address:              c.address              || '',
    contact_person:       c.contact_person       || '',
    phone:                c.phone                || '',
    org_phone:            c.org_phone            || '',
    email:                c.email                || '',
    org_email:            c.org_email            || '',
    bank_details:         c.bank_details         || '',
    signatory:            c.signatory            || '',
    signatory_basis:      c.signatory_basis      || '',
    postal_address:       c.postal_address       || '',
    ogrn:                 c.ogrn                 || '',
    settlement_account:   c.settlement_account   || '',
    bank_name:            c.bank_name            || '',
    bik:                  c.bik                  || '',
    correspondent_account: c.correspondent_account || '',
    org_type:             c.org_type             || '',
    manual_product_categories: mergeCategories(c.manual_product_categories || [], c.product_categories || []),
    passport_series:      c.passport_series      || '',
    passport_number:      c.passport_number      || '',
    passport_issuer:      c.passport_issuer      || '',
    passport_issued_date: c.passport_issued_date || '',
    snils:                c.snils                || '',
    registration_address: c.registration_address || '',
    birth_date:           c.birth_date           || '',
    website:              c.website              || '',
    registration_date:    c.registration_date    || '',
    okpo:                 c.okpo                 || '',
    okved:                c.okved                || '',
    treasury_account:     c.treasury_account     || '',
    single_treasury_account: c.single_treasury_account || '',
    signatory_position:   c.signatory_position   || '',
  }
}

async function fillFromContractorId(id: number) {
  loadingContractor.value = true
  existingContractor.value = null
  fnsMessage.value = ''
  try {
    const c = await apiFetch<ContractorFull>(`/contractors/${id}`)
    fillForm(c)
  } catch (e: any) {
    showSnack(e?.message || 'Не удалось загрузить контрагента', 'error')
    editId.value = null
    form.value = emptyForm()
  } finally {
    loadingContractor.value = false
  }
}

function resetForAdd() {
  editId.value = null
  form.value = emptyForm()
  fnsMessage.value = ''
  existingContractor.value = null
  contractorCardFile.value = null
  if (props.prefillInn) {
    form.value.inn = props.prefillInn
    onInnChange(props.prefillInn)
  }
}

// ── Open handling ─────────────────────────────────
async function onOpen() {
  loadCategories()
  contractorCardFile.value = null
  fnsMessage.value = ''
  existingContractor.value = null
  if (props.contractorId) {
    await fillFromContractorId(props.contractorId)
  } else {
    resetForAdd()
  }
}

watch(() => props.modelValue, (open) => {
  if (open) onOpen()
})

watch(() => props.contractorId, (id) => {
  if (props.modelValue && id) fillFromContractorId(id)
})

// ── Save ──────────────────────────────────────────
async function save() {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    let saved: ContractorFull
    if (editId.value) {
      saved = await apiFetch<ContractorFull>(`/contractors/${editId.value}`, {
        method: 'PUT',
        body: form.value as any,
      })
      showSnack('Контрагент обновлён')
    } else {
      saved = await apiFetch<ContractorFull>('/contractors/', {
        method: 'POST',
        body: form.value as any,
      })
      showSnack('Контрагент добавлен')
    }
    emit('saved', saved)
    emit('update:modelValue', false)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

function close() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
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
