<template>
  <div class="fdocs" :class="{ 'fdocs--light': !isDark }">

    <!-- ── Topbar ── -->
    <div class="fdocs-topbar">
      <div>
        <div class="fdocs-crumbs">
          Автопарк <span class="fdocs-crumbs__sep">/</span> <b>Документы</b>
        </div>
        <h1 class="fdocs-h1">Документы парка</h1>
        <p class="fdocs-lead">ОСАГО, СТС, ПТС, техосмотр, тахографы и договоры КП по всем ТС</p>
      </div>
      <div class="fdocs-topbar__actions">
        <button class="fdocs-btn" @click="showCalendar = true">
          <v-icon size="14" icon="mdi-calendar-month" />
          Календарь
        </button>
        <button class="fdocs-btn" @click="onExport">
          <v-icon size="14" icon="mdi-file-excel" />
          Экспорт XLSX
        </button>
        <button class="fdocs-btn fdocs-btn--primary" @click="openUploadDialog">
          <v-icon size="14" icon="mdi-upload" />
          Загрузить
        </button>
      </div>
    </div>

    <!-- ── KPI Cards ── -->
    <section class="fdocs-kpis">
      <KpiCard
        label="Всего документов"
        :value="summary.total"
        :sub="`по ${summary.total} записям реестра`"
        variant="default"
        :bar-pct="100"
        clickable
        @click="setStatusFilter('')"
      />
      <KpiCard
        label="Действующие"
        :value="summary.valid"
        :sub="summary.total ? `${Math.round(summary.valid / summary.total * 100)}% от общего` : ''"
        variant="ok"
        :bar-pct="summary.total ? Math.round(summary.valid / summary.total * 100) : 0"
        clickable
        @click="setStatusFilter('valid')"
      />
      <KpiCard
        label="Истекают <60 дн."
        :value="summary.expiring_soon"
        sub="требуется продление"
        variant="warn"
        :bar-pct="summary.total ? Math.round(summary.expiring_soon / summary.total * 100) : 0"
        clickable
        @click="setStatusFilter('expiring')"
      />
      <KpiCard
        label="Просрочены"
        :value="summary.expired"
        sub="требуются немедленно"
        variant="alert"
        :bar-pct="summary.total ? Math.round(summary.expired / summary.total * 100) : 0"
        clickable
        @click="setStatusFilter('expired')"
      />
      <KpiCard
        label="Без документа"
        :value="summary.missing"
        sub="отсутствуют в реестре"
        variant="default"
        :bar-pct="0"
        clickable
        @click="setStatusFilter('missing')"
      />
      <KpiCard
        label="КП (договоров)"
        :value="summary.by_type.purchase_contract ?? 0"
        sub="договоры купли-продажи"
        variant="info"
        :bar-pct="0"
        clickable
        @click="setTypeFilter('purchase_contract')"
      />
    </section>

    <!-- ── Two-column: Urgent + By type ── -->
    <section class="fdocs-two-col">
      <!-- Urgent -->
      <div class="fdocs-panel">
        <h3 class="fdocs-panel__title">
          <v-icon size="16" icon="mdi-fire" style="color: var(--alert-color, #ff5b6a)" />
          Требуют действия
          <span class="fdocs-panel__title-sub">топ-7 по срочности</span>
        </h3>
        <div v-if="urgentLoading" class="fdocs-panel__empty">Загрузка…</div>
        <div v-else-if="urgentItems.length === 0" class="fdocs-panel__empty">Нет срочных документов</div>
        <div v-else class="fdocs-urgent">
          <div
            v-for="doc in urgentItems"
            :key="doc.id"
            class="fdocs-urg-item"
            :class="urgentClass(doc)"
          >
            <div class="fdocs-urg-item__ic">
              <span v-if="docStatus(doc) === 'expired'">!</span>
              <span v-else>⚠</span>
            </div>
            <div class="fdocs-urg-item__body">
              <div class="fdocs-urg-item__nm">
                {{ doc.vehicle_plate || '—' }}
                <span v-if="doc.vehicle_model" class="fdocs-urg-item__model">· {{ doc.vehicle_model }}</span>
              </div>
              <div class="fdocs-urg-item__ds">{{ docTypeLabel(doc.type) }} — {{ urgentDescription(doc) }}</div>
            </div>
            <div class="fdocs-urg-item__right">
              <b>{{ urgentDaysLabel(doc) }}</b>
            </div>
          </div>
        </div>
      </div>

      <!-- By type -->
      <div class="fdocs-panel">
        <h3 class="fdocs-panel__title">По типам документов</h3>
        <div class="fdocs-types">
          <div
            v-for="dt in DOC_TYPES"
            :key="dt.key"
            class="fdocs-type-row"
          >
            <div class="fdocs-type-row__icon" :style="{ background: dt.iconBg, color: dt.iconColor }">
              <v-icon size="18" :icon="dt.icon" />
            </div>
            <div class="fdocs-type-row__info">
              <div class="fdocs-type-row__nm">{{ dt.label }}</div>
              <div class="fdocs-type-row__ds">{{ dt.desc }}</div>
            </div>
            <div class="fdocs-type-row__stats">
              <div>
                <b class="fdocs-type-row__ok">{{ summary.by_type[dt.key] ?? 0 }}</b>
                <span>всего</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Filters ── -->
    <div class="fdocs-filters">
      <!-- Status chips -->
      <button
        v-for="sc in STATUS_CHIPS"
        :key="sc.value"
        class="fdocs-chip"
        :class="{ 'fdocs-chip--active': activeStatus === sc.value }"
        @click="setStatusFilter(sc.value)"
      >
        <span v-if="sc.dot" class="fdocs-chip__dot" :class="`fdocs-chip__dot--${sc.dot}`"></span>
        {{ sc.label }}
      </button>

      <div class="fdocs-filters__sep"></div>

      <!-- Type chips -->
      <button
        v-for="dt in DOC_TYPES"
        :key="dt.key"
        class="fdocs-chip"
        :class="{ 'fdocs-chip--active': activeType === dt.key }"
        @click="setTypeFilter(dt.key)"
      >
        {{ dt.label }}
      </button>

      <div class="fdocs-filters__spacer"></div>

      <!-- Search -->
      <div class="fdocs-search">
        <v-icon size="14" icon="mdi-magnify" />
        <input
          v-model="searchQuery"
          class="fdocs-search__input"
          placeholder="Поиск по госномеру, номеру документа…"
        />
        <button v-if="searchQuery" class="fdocs-search__clear" @click="searchQuery = ''">
          <v-icon size="12" icon="mdi-close" />
        </button>
      </div>
    </div>

    <!-- ── Registry Table ── -->
    <section class="fdocs-reg-box">
      <div class="fdocs-reg-box__head">
        <h3>Реестр документов</h3>
        <small>сортировка: по сроку действия ↑</small>
      </div>

      <div v-if="loading" class="fdocs-reg-box__loading">
        <v-progress-circular indeterminate size="24" />
        Загрузка…
      </div>

      <table v-else class="fdocs-table">
        <thead>
          <tr>
            <th>ТС</th>
            <th>Эксплуатант</th>
            <th>Тип документа</th>
            <th>Номер</th>
            <th>Действует до</th>
            <th>Статус</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredDocs.length === 0">
            <td colspan="7" class="fdocs-table__empty">Документы не найдены</td>
          </tr>
          <tr v-for="doc in filteredDocs" :key="doc.id">
            <!-- ТС -->
            <td>
              <div class="fdocs-veh">
                <VehicleTypeIcon :type="doc.vehicle_type" :size="32" />
                <div class="fdocs-veh__info">
                  <LicensePlate :model-value="doc.vehicle_plate || '—'" size="sm" />
                  <div class="fdocs-veh__model">{{ doc.vehicle_model || '' }}</div>
                </div>
              </div>
            </td>
            <!-- Эксплуатант -->
            <td>
              <span v-if="doc.operator_org_name" class="fdocs-operator">{{ doc.operator_org_name }}</span>
              <span v-else style="opacity:0.4">—</span>
            </td>
            <!-- Тип -->
            <td>
              <div class="fdocs-doc-type">
                <v-icon size="15" :icon="docTypeIcon(doc.type)" style="opacity:0.7" />
                <b>{{ docTypeLabel(doc.type) }}</b>
              </div>
            </td>
            <!-- Номер -->
            <td>
              <span class="fdocs-mono">{{ doc.number || '—' }}</span>
            </td>
            <!-- Действует до -->
            <td>
              <template v-if="doc.type === 'purchase_contract'">
                <b>{{ formatDate(doc.issued_at) }}</b>
                <div class="fdocs-table__sub">дата выдачи</div>
              </template>
              <template v-else-if="doc.expires_at">
                <b>{{ formatDate(doc.expires_at) }}</b>
                <div class="fdocs-table__sub">{{ expiresRelative(doc.expires_at) }}</div>
              </template>
              <template v-else>
                <span style="opacity:0.4">—</span>
              </template>
            </td>
            <!-- Статус -->
            <td>
              <StatusPill :variant="docStatusVariant(doc)" :dot="docStatus(doc) !== 'muted'">
                {{ docStatusLabel(doc) }}
              </StatusPill>
            </td>
            <!-- Actions -->
            <td>
              <div class="fdocs-actions">
                <button class="fdocs-actions__btn" title="Редактировать" @click="openEditDialog(doc)">
                  <v-icon size="14" icon="mdi-pencil" />
                </button>
                <button
                  v-if="doc.has_file"
                  class="fdocs-actions__btn"
                  title="Скачать файл"
                  @click="downloadFile(doc.id)"
                >
                  <v-icon size="14" icon="mdi-open-in-new" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="fdocs-reg-box__footer">
        <div>Показано {{ filteredDocs.length }} из {{ docs.length }} · последнее обновление {{ lastUpdated }}</div>
        <div>Напоминания за <b>30 / 14 / 7 дней</b></div>
      </div>
    </section>

    <!-- ── Upload/Edit Dialog ── -->
    <v-dialog v-model="dialogOpen" max-width="560" persistent :fullscreen="mobile">
      <v-card class="fdocs-dialog">
        <v-card-title class="fdocs-dialog__title">
          {{ editingDoc ? 'Редактировать документ' : 'Загрузить документ' }}
          <v-spacer />
          <v-btn icon flat @click="closeDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text class="fdocs-dialog__body">
          <v-form ref="formRef" @submit.prevent="submitForm">

            <!-- Vehicle -->
            <v-autocomplete
              v-model="form.vehicle_id"
              :items="vehicleOptions"
              item-title="label"
              item-value="id"
              label="Транспортное средство *"
              :rules="[v => !!v || 'Обязательно']"
              variant="outlined"
              density="compact"
              clearable
              class="mb-3"
            />

            <!-- Type -->
            <v-select
              v-model="form.type"
              :items="DOC_TYPE_SELECT"
              item-title="label"
              item-value="value"
              label="Тип документа *"
              :rules="[v => !!v || 'Обязательно']"
              variant="outlined"
              density="compact"
              class="mb-3"
              @update:model-value="onTypeChange"
            />

            <!-- Number -->
            <v-text-field
              v-model="form.number"
              label="Номер документа"
              variant="outlined"
              density="compact"
              class="mb-3"
            />

            <!-- Dates row -->
            <div class="fdocs-dialog__row2">
              <v-text-field
                v-model="form.issued_at"
                label="Дата выдачи"
                type="date"
                variant="outlined"
                density="compact"
                class="mb-3"
              />
              <v-text-field
                v-model="form.expires_at"
                label="Действует до"
                type="date"
                variant="outlined"
                density="compact"
                :disabled="form.type === 'purchase_contract'"
                class="mb-3"
              />
            </div>

            <!-- Purchase contract fields -->
            <template v-if="form.type === 'purchase_contract'">
              <v-text-field
                v-model="form.counterparty"
                label="Контрагент (продавец/покупатель)"
                variant="outlined"
                density="compact"
                class="mb-3"
              />
              <v-text-field
                v-model.number="form.amount_rub"
                label="Сумма, ₽"
                type="number"
                variant="outlined"
                density="compact"
                class="mb-3"
              />
            </template>

            <!-- File upload -->
            <v-file-input
              v-model="form.file"
              label="Файл документа (PDF, JPG, PNG)"
              accept=".pdf,.jpg,.jpeg,.png"
              variant="outlined"
              density="compact"
              prepend-icon=""
              prepend-inner-icon="mdi-paperclip"
              class="mb-3"
            />

            <!-- Notes -->
            <v-textarea
              v-model="form.notes"
              label="Примечания"
              variant="outlined"
              density="compact"
              rows="2"
              auto-grow
              class="mb-1"
            />
          </v-form>
        </v-card-text>
        <v-card-actions class="fdocs-dialog__actions">
          <v-btn variant="text" @click="closeDialog">Отмена</v-btn>
          <v-spacer />
          <v-btn
            v-if="editingDoc"
            color="error"
            variant="text"
            :loading="submitting"
            @click="deleteDoc"
          >Удалить</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="submitting"
            @click="submitForm"
          >{{ editingDoc ? 'Сохранить' : 'Загрузить' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Calendar stub dialog -->
    <v-dialog v-model="showCalendar" max-width="400">
      <v-card>
        <v-card-title>Календарь сроков</v-card-title>
        <v-card-text>Раздел в разработке</v-card-text>
        <v-card-actions>
          <v-spacer /><v-btn @click="showCalendar = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useTheme, useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import KpiCard from '@/components/fleet/KpiCard.vue'
import StatusPill from '@/components/fleet/StatusPill.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

const { mobile } = useDisplay()

// ── Theme ─────────────────────────────────────────────────────────────────────
const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)

// ── Constants ─────────────────────────────────────────────────────────────────
const DOC_TYPES = [
  { key: 'osago',            label: 'ОСАГО',      desc: 'обязательное страхование',    icon: 'mdi-shield-car',          iconBg: 'rgba(34,201,151,.12)',  iconColor: '#22c997' },
  { key: 'sts',              label: 'СТС',         desc: 'свидетельство регистрации',   icon: 'mdi-card-text',           iconBg: 'rgba(106,166,255,.12)', iconColor: '#6aa6ff' },
  { key: 'pts',              label: 'ПТС',         desc: 'паспорт транспортного средства', icon: 'mdi-credit-card',      iconBg: 'rgba(139,92,246,.12)', iconColor: '#8b5cf6' },
  { key: 'to',               label: 'Техосмотр',   desc: 'диагностическая карта',       icon: 'mdi-clipboard-check',     iconBg: 'rgba(246,179,74,.12)', iconColor: '#f6b34a' },
  { key: 'tachograph',       label: 'Тахограф',    desc: 'карта тахографа водителя',    icon: 'mdi-clock-outline',       iconBg: 'rgba(93,208,255,.12)', iconColor: '#5dd0ff' },
  { key: 'fpg',              label: 'ФПГ',         desc: 'пропуск, разрешение',         icon: 'mdi-badge-account',       iconBg: 'rgba(255,91,106,.12)', iconColor: '#ff5b6a' },
  { key: 'purchase_contract', label: 'Договор КП', desc: 'договор купли-продажи',      icon: 'mdi-handshake',           iconBg: 'rgba(106,166,255,.08)', iconColor: '#6aa6ff' },
] as const

type DocTypeKey = typeof DOC_TYPES[number]['key']

const DOC_TYPE_SELECT = DOC_TYPES.map(d => ({ value: d.key, label: d.label }))

const STATUS_CHIPS = [
  { value: '',          label: 'Все',        dot: null },
  { value: 'valid',     label: 'Действующие', dot: 'ok' },
  { value: 'expiring',  label: 'Истекают',   dot: 'warn' },
  { value: 'expired',   label: 'Просрочены', dot: 'alert' },
  { value: 'missing',   label: 'Без документа', dot: null },
]

// ── Interfaces ────────────────────────────────────────────────────────────────
interface FleetDocument {
  id: number
  vehicle_id: number
  vehicle_plate?: string
  vehicle_model?: string
  vehicle_type?: string
  operator_org_name?: string   // Phase 29.3-R3 (Д-2) — Эксплуатант
  type: string
  number?: string
  issued_at?: string
  expires_at?: string
  status?: string          // 'valid' | 'expiring' | 'expired' | 'missing'
  counterparty?: string
  amount_rub?: number
  notes?: string
  has_file?: boolean
}

interface DocSummary {
  total: number
  valid: number
  expiring_soon: number
  expired: number
  missing: number
  by_type: Record<string, number>
}

interface VehicleOption {
  id: number
  label: string
}

// ── State ─────────────────────────────────────────────────────────────────────
const loading = ref(false)
const urgentLoading = ref(false)
const docs = ref<FleetDocument[]>([])
const urgentItems = ref<FleetDocument[]>([])
const summary = ref<DocSummary>({
  total: 0, valid: 0, expiring_soon: 0, expired: 0, missing: 0, by_type: {},
})
const vehicleOptions = ref<VehicleOption[]>([])
const lastUpdated = ref('—')

const activeStatus = ref('')
const activeType = ref<string>('')
const searchQuery = ref('')
const showCalendar = ref(false)

// ── Dialog state ──────────────────────────────────────────────────────────────
const dialogOpen = ref(false)
const editingDoc = ref<FleetDocument | null>(null)
const submitting = ref(false)
const formRef = ref<any>(null)

const emptyForm = () => ({
  vehicle_id: null as number | null,
  type: '' as string,
  number: '',
  issued_at: '',
  expires_at: '',
  counterparty: '',
  amount_rub: null as number | null,
  notes: '',
  file: null as File | null | File[],
})
const form = ref(emptyForm())

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchSummary() {
  try {
    summary.value = await apiFetch<DocSummary>('/fleet-documents/summary')
  } catch (e) {
    console.error('[FleetDocs] summary', e)
  }
}

async function fetchDocs() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (activeStatus.value) params.set('status', activeStatus.value)
    if (activeType.value) params.set('type', activeType.value)
    if (searchQuery.value) params.set('q', searchQuery.value)
    params.set('limit', '200')
    docs.value = await apiFetch<FleetDocument[]>(`/fleet-documents/?${params}`)
    lastUpdated.value = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date())
  } catch (e) {
    console.error('[FleetDocs] list', e)
  } finally {
    loading.value = false
  }
}

async function fetchUrgent() {
  urgentLoading.value = true
  try {
    const params = new URLSearchParams({ status: 'expired', limit: '4' })
    const expired = await apiFetch<FleetDocument[]>(`/fleet-documents/?${params}`)
    const params2 = new URLSearchParams({ status: 'expiring', limit: '3' })
    const expiring = await apiFetch<FleetDocument[]>(`/fleet-documents/?${params2}`)
    urgentItems.value = [...expired.slice(0, 4), ...expiring.slice(0, 3)].slice(0, 7)
  } catch (e) {
    console.error('[FleetDocs] urgent', e)
  } finally {
    urgentLoading.value = false
  }
}

async function fetchVehicles() {
  try {
    const data = await apiFetch<{ id: number; plate: string; model?: string }[]>('/vehicles?limit=500')
    vehicleOptions.value = (Array.isArray(data) ? data : (data as any).items || []).map((v: any) => ({
      id: v.id,
      label: [v.plate, v.model].filter(Boolean).join(' · '),
    }))
  } catch (e) {
    console.error('[FleetDocs] vehicles', e)
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────
const filteredDocs = computed(() => {
  let list = docs.value
  // Phase 29.3-R3 (Д-4): client-side фильтр расширен на brand/model/vin (паттерн из /api/vehicles)
  // Backend уже делает аналогичный ILIKE через ?q= — client-side это дублирование для отзывчивости
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(d =>
      (d.vehicle_plate || '').toLowerCase().includes(q) ||
      (d.vehicle_model || '').toLowerCase().includes(q) ||
      (d.number || '').toLowerCase().includes(q)
    )
  }
  return list
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function docTypeLabel(type: string): string {
  return DOC_TYPES.find(d => d.key === type)?.label ?? type
}

function docTypeIcon(type: string): string {
  return DOC_TYPES.find(d => d.key === type)?.icon ?? 'mdi-file-document-outline'
}

function docStatus(doc: FleetDocument): string {
  if (doc.type === 'purchase_contract') return 'muted'
  if (doc.status) return doc.status
  if (!doc.expires_at) return 'missing'
  const now = Date.now()
  const exp = new Date(doc.expires_at).getTime()
  const days = (exp - now) / 86400000
  if (days < 0) return 'expired'
  if (days < 60) return 'expiring'
  return 'valid'
}

function docStatusVariant(doc: FleetDocument): 'ok' | 'warn' | 'alert' | 'muted' | 'info' {
  const s = docStatus(doc)
  if (s === 'valid') return 'ok'
  if (s === 'expiring') return 'warn'
  if (s === 'expired') return 'alert'
  if (s === 'missing') return 'alert'
  return 'muted'
}

function docStatusLabel(doc: FleetDocument): string {
  const s = docStatus(doc)
  if (s === 'valid') return 'Действует'
  if (s === 'expiring') return 'Истекает'
  if (s === 'expired') return 'Просрочен'
  if (s === 'missing') return 'Отсутствует'
  return 'Договор'
}

function urgentClass(doc: FleetDocument): string {
  const s = docStatus(doc)
  if (s === 'expired') return 'fdocs-urg-item--alert'
  return 'fdocs-urg-item--warn'
}

function urgentDescription(doc: FleetDocument): string {
  if (!doc.expires_at) return 'отсутствует'
  const exp = new Date(doc.expires_at)
  return `до ${formatDate(doc.expires_at)}`
}

function urgentDaysLabel(doc: FleetDocument): string {
  if (!doc.expires_at) return 'нет данных'
  const days = Math.round((new Date(doc.expires_at).getTime() - Date.now()) / 86400000)
  if (days < 0) return `${days} дн.`
  return `${days} дн.`
}

function formatDate(val?: string | null): string {
  if (!val) return '—'
  try {
    return new Intl.DateTimeFormat('ru-RU').format(new Date(val))
  } catch {
    return val
  }
}

function expiresRelative(val?: string | null): string {
  if (!val) return ''
  const days = Math.round((new Date(val).getTime() - Date.now()) / 86400000)
  if (days < 0) return `${Math.abs(days)} дн. назад`
  if (days === 0) return 'сегодня'
  return `через ${days} дн.`
}

function formatRub(val: number): string {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(val)
}

// ── Filters ───────────────────────────────────────────────────────────────────
function setStatusFilter(val: string) {
  activeStatus.value = activeStatus.value === val ? '' : val
  fetchDocs()
}

function setTypeFilter(val: string) {
  activeType.value = activeType.value === val ? '' : val
  fetchDocs()
}

// ── Dialog ────────────────────────────────────────────────────────────────────
function openUploadDialog() {
  editingDoc.value = null
  form.value = emptyForm()
  dialogOpen.value = true
}

function openEditDialog(doc: FleetDocument) {
  editingDoc.value = doc
  form.value = {
    vehicle_id: doc.vehicle_id,
    type: doc.type,
    number: doc.number || '',
    issued_at: doc.issued_at || '',
    expires_at: doc.expires_at || '',
    counterparty: doc.counterparty || '',
    amount_rub: doc.amount_rub ?? null,
    notes: doc.notes || '',
    file: null,
  }
  dialogOpen.value = true
}

function closeDialog() {
  dialogOpen.value = false
  editingDoc.value = null
}

function onTypeChange() {
  if (form.value.type === 'purchase_contract') {
    form.value.expires_at = ''
  }
}

async function submitForm() {
  if (!formRef.value) return
  const { valid } = await formRef.value.validate()
  if (!valid) return

  submitting.value = true
  try {
    const fileArr = Array.isArray(form.value.file) ? form.value.file : [form.value.file]
    const hasFile = fileArr.length > 0 && fileArr[0] instanceof File

    const payload = new FormData()
    payload.append('vehicle_id', String(form.value.vehicle_id))
    payload.append('type', form.value.type)
    if (form.value.number) payload.append('number', form.value.number)
    if (form.value.issued_at) payload.append('issued_at', form.value.issued_at)
    if (form.value.expires_at && form.value.type !== 'purchase_contract') payload.append('expires_at', form.value.expires_at)
    if (form.value.type === 'purchase_contract') {
      if (form.value.counterparty) payload.append('counterparty', form.value.counterparty)
      if (form.value.amount_rub != null) payload.append('amount_rub', String(form.value.amount_rub))
    }
    if (form.value.notes) payload.append('notes', form.value.notes)
    if (hasFile) payload.append('file', fileArr[0] as File)

    if (editingDoc.value) {
      await apiFetch(`/fleet-documents/${editingDoc.value.id}`, { method: 'PATCH', body: payload })
    } else {
      await apiFetch('/fleet-documents/', { method: 'POST', body: payload })
    }

    closeDialog()
    await Promise.all([fetchSummary(), fetchDocs(), fetchUrgent()])
  } catch (e: any) {
    const msg = e?.payload?.message || e?.message || 'Ошибка при сохранении'
    console.error('[FleetDocs] submit', e)
    window.dispatchEvent(new CustomEvent('api-error', { detail: { message: msg } }))
  } finally {
    submitting.value = false
  }
}

async function deleteDoc() {
  if (!editingDoc.value) return
  submitting.value = true
  try {
    await apiFetch(`/fleet-documents/${editingDoc.value.id}`, { method: 'DELETE' })
    closeDialog()
    await Promise.all([fetchSummary(), fetchDocs(), fetchUrgent()])
  } catch (e: any) {
    console.error('[FleetDocs] delete', e)
  } finally {
    submitting.value = false
  }
}

async function downloadFile(id: number) {
  try {
    const token = localStorage.getItem('auth_token')
    const url = `/api/fleet-documents/${id}/file`
    const a = document.createElement('a')
    a.href = url
    a.target = '_blank'
    a.click()
  } catch (e) {
    console.error('[FleetDocs] download', e)
  }
}

async function onExport() {
  const params = new URLSearchParams()
  if (activeStatus.value) params.set('status', activeStatus.value)
  if (activeType.value) params.set('type', activeType.value)
  if (searchQuery.value) params.set('q', searchQuery.value)
  window.open(`/api/fleet-documents/export?${params}`, '_blank')
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([fetchSummary(), fetchDocs(), fetchUrgent(), fetchVehicles()])
})
</script>

<style scoped>
/* ── Root ── */
.fdocs {
  min-height: 100vh;
  padding: 22px 28px 60px;
  color: var(--text, #e9edf5);
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 14px;
}

/* ── Topbar ── */
.fdocs-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
  flex-wrap: wrap;
}
.fdocs-crumbs {
  color: var(--muted, #8a93a8);
  font-size: 13px;
  margin-bottom: 4px;
}
.fdocs-crumbs__sep { opacity: 0.5; margin: 0 4px; }
.fdocs-h1 {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.4px;
}
.fdocs-lead {
  color: var(--muted, #8a93a8);
  margin: 0;
  font-size: 13px;
}
.fdocs-topbar__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 20px;
}

/* ── Buttons ── */
.fdocs-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  border-radius: 10px;
  border: 1px solid var(--line-2, #2b3245);
  background: var(--panel, #141823);
  color: var(--text, #e9edf5);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.fdocs-btn:hover { background: var(--panel-2, #1a1f2c); }
.fdocs-btn--primary {
  background: linear-gradient(180deg, #5a96ff, #4a85f0);
  border-color: #3a74dc;
  color: #fff;
  box-shadow: 0 8px 22px -10px rgba(106,166,255,.5);
}
.fdocs-btn--primary:hover { background: linear-gradient(180deg, #6aa6ff, #5a94f8); }

/* ── KPI grid ── */
.fdocs-kpis {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}
@media (max-width: 1400px) { .fdocs-kpis { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 900px)  { .fdocs-kpis { grid-template-columns: repeat(2, 1fr); } }

/* ── Two-col ── */
.fdocs-two-col {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 18px;
  margin-bottom: 22px;
}
@media (max-width: 960px) { .fdocs-two-col { grid-template-columns: 1fr; } }

/* ── Panel ── */
.fdocs-panel {
  background: linear-gradient(180deg, var(--panel, #141823), var(--bg-2, #0f131c));
  border: 1px solid var(--line, #222838);
  border-radius: 16px;
  padding: 18px;
}
.fdocs-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 700;
}
.fdocs-panel__title-sub {
  color: var(--muted, #8a93a8);
  font-weight: 500;
  font-size: 12px;
  margin-left: auto;
}
.fdocs-panel__empty {
  color: var(--muted, #8a93a8);
  font-size: 13px;
  text-align: center;
  padding: 20px 0;
}

/* ── Urgent items ── */
.fdocs-urgent { display: grid; gap: 8px; }
.fdocs-urg-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--line, #222838);
  border-radius: 12px;
  background: rgba(255,255,255,.02);
}
.fdocs-urg-item--alert {
  border-color: rgba(255,91,106,.3);
  background: rgba(255,91,106,.04);
}
.fdocs-urg-item--warn {
  border-color: rgba(246,179,74,.3);
  background: rgba(246,179,74,.04);
}
.fdocs-urg-item__ic {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 14px;
}
.fdocs-urg-item--alert .fdocs-urg-item__ic { background: rgba(255,91,106,.18); color: #ff5b6a; }
.fdocs-urg-item--warn  .fdocs-urg-item__ic { background: rgba(246,179,74,.18); color: #f6b34a; }
.fdocs-urg-item__nm { font-weight: 700; font-size: 13px; }
.fdocs-urg-item__model { color: var(--muted, #8a93a8); font-weight: 400; font-size: 12px; }
.fdocs-urg-item__ds { color: var(--muted, #8a93a8); font-size: 12px; margin-top: 1px; }
.fdocs-urg-item__right { text-align: right; font-size: 11.5px; font-weight: 700; white-space: nowrap; color: var(--muted, #8a93a8); }
.fdocs-urg-item--alert .fdocs-urg-item__right b { color: #ff5b6a; display: block; font-size: 13px; }
.fdocs-urg-item--warn  .fdocs-urg-item__right b { color: #f6b34a; display: block; font-size: 13px; }

/* ── Type rows ── */
.fdocs-types { display: grid; gap: 12px; }
.fdocs-type-row { display: flex; align-items: center; gap: 14px; }
.fdocs-type-row__icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.fdocs-type-row__info { flex: 1; min-width: 0; }
.fdocs-type-row__nm { font-weight: 700; font-size: 13px; }
.fdocs-type-row__ds { color: var(--muted, #8a93a8); font-size: 11.5px; margin-top: 2px; }
.fdocs-type-row__stats { display: flex; gap: 10px; text-align: right; flex-shrink: 0; }
.fdocs-type-row__stats div { font-size: 11px; color: var(--muted, #8a93a8); font-weight: 600; }
.fdocs-type-row__ok { display: block; font-size: 14px; font-weight: 800; color: #22c997; }

/* ── Filters ── */
.fdocs-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 18px;
}
.fdocs-filters__sep {
  width: 1px;
  height: 20px;
  background: var(--line, #222838);
  margin: 0 4px;
}
.fdocs-filters__spacer { flex: 1; }

.fdocs-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--line-2, #2b3245);
  border-radius: 999px;
  background: var(--panel, #141823);
  color: var(--muted, #8a93a8);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.fdocs-chip:hover { border-color: var(--accent, #6aa6ff); color: var(--text, #e9edf5); }
.fdocs-chip--active {
  background: rgba(106,166,255,.12);
  border-color: rgba(106,166,255,.4);
  color: #cfe1ff;
}
.fdocs-chip__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.fdocs-chip__dot--ok    { background: #22c997; }
.fdocs-chip__dot--warn  { background: #f6b34a; }
.fdocs-chip__dot--alert { background: #ff5b6a; }

.fdocs-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--panel, #141823);
  border: 1px solid var(--line, #222838);
  padding: 7px 11px;
  border-radius: 8px;
  color: var(--muted, #8a93a8);
}
.fdocs-search__input {
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--text, #e9edf5);
  font-size: 12.5px;
  width: 240px;
  font-family: inherit;
}
.fdocs-search__input::placeholder { color: var(--muted, #8a93a8); }
.fdocs-search__clear {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted, #8a93a8);
  padding: 0;
  display: flex;
  align-items: center;
}

/* ── Registry ── */
.fdocs-reg-box {
  background: linear-gradient(180deg, var(--panel, #141823), var(--bg-2, #0f131c));
  border: 1px solid var(--line, #222838);
  border-radius: 16px;
  overflow: hidden;
}
.fdocs-reg-box__head {
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--line, #222838);
}
.fdocs-reg-box__head h3 { margin: 0; font-size: 15px; font-weight: 700; }
.fdocs-reg-box__head small { color: var(--muted, #8a93a8); margin-left: auto; font-size: 12px; }
.fdocs-reg-box__loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 32px 20px;
  color: var(--muted, #8a93a8);
  justify-content: center;
}
.fdocs-reg-box__footer {
  padding: 14px 20px;
  color: var(--muted, #8a93a8);
  font-size: 12px;
  border-top: 1px solid var(--line, #222838);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.fdocs-reg-box__footer b { color: var(--text, #e9edf5); }

/* ── Table ── */
.fdocs-table {
  width: 100%;
  border-collapse: collapse;
}
.fdocs-table thead th {
  text-align: left;
  padding: 12px 20px;
  font-size: 11px;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--muted, #8a93a8);
  font-weight: 700;
  border-bottom: 1px solid var(--line, #222838);
  background: rgba(255,255,255,.02);
  white-space: nowrap;
}
.fdocs-table tbody td {
  padding: 12px 20px;
  border-bottom: 1px solid var(--line, #222838);
  font-size: 13px;
  vertical-align: middle;
}
.fdocs-table tbody tr:last-child td { border-bottom: 0; }
.fdocs-table tbody tr:hover { background: rgba(255,255,255,.02); }
.fdocs-table__empty {
  text-align: center;
  color: var(--muted, #8a93a8);
  padding: 32px !important;
}
.fdocs-table__sub { font-size: 11px; color: var(--muted, #8a93a8); margin-top: 1px; }

/* ── Vehicle cell ── */
.fdocs-veh {
  display: flex;
  align-items: center;
  gap: 10px;
}
.fdocs-veh__info { display: flex; flex-direction: column; gap: 3px; }
.fdocs-veh__model { font-size: 11px; color: var(--muted, #8a93a8); margin-top: 1px; }

/* ── Doc type cell ── */
.fdocs-doc-type { display: flex; align-items: center; gap: 6px; }

/* ── Mono ── */
.fdocs-mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--muted, #8a93a8);
}

/* ── Contract cell ── */
.fdocs-contract { display: flex; flex-direction: column; gap: 2px; }
.fdocs-contract__cp { font-size: 12px; font-weight: 600; }
.fdocs-contract__amount { font-size: 12px; color: var(--ok, #22c997); font-weight: 700; font-family: 'JetBrains Mono', monospace; }

/* ── Actions ── */
.fdocs-actions { display: flex; gap: 4px; }
.fdocs-actions__btn {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--line, #222838);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted, #8a93a8);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.fdocs-actions__btn:hover { color: var(--text, #e9edf5); background: var(--panel-2, #1a1f2c); }

/* ── Dialog ── */
.fdocs-dialog__title {
  display: flex;
  align-items: center;
  font-size: 15px;
  font-weight: 700;
  padding: 16px 20px 8px;
}
.fdocs-dialog__body { padding: 8px 20px 0; }
.fdocs-dialog__row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.fdocs-dialog__actions { padding: 8px 20px 16px; }

/* ── Light theme ── */
.fdocs--light .fdocs-btn {
  background: #f5f7fb;
  border-color: #e2e6f0;
  color: #1a1d23;
}
.fdocs--light .fdocs-btn:hover { background: #eaecf5; }
.fdocs--light .fdocs-chip {
  background: #f5f7fb;
  border-color: #e2e6f0;
  color: #6b7280;
}
.fdocs--light .fdocs-chip--active {
  background: rgba(74,133,240,.12);
  border-color: rgba(74,133,240,.4);
  color: #1a56db;
}
.fdocs--light .fdocs-search {
  background: #f5f7fb;
  border-color: #e2e6f0;
  color: #6b7280;
}
.fdocs--light .fdocs-search__input { color: #1a1d23; }
.fdocs--light .fdocs-panel,
.fdocs--light .fdocs-reg-box {
  background: #ffffff;
  border-color: #e2e6f0;
}
.fdocs--light .fdocs-table thead th {
  background: #f8f9fc;
  color: #6b7280;
  border-color: #e2e6f0;
}
.fdocs--light .fdocs-table tbody td { border-color: #e2e6f0; color: #1a1d23; }
.fdocs--light .fdocs-table tbody tr:hover { background: rgba(0,0,0,.02); }
.fdocs--light .fdocs-reg-box__head,
.fdocs--light .fdocs-reg-box__footer { border-color: #e2e6f0; }
.fdocs--light .fdocs-urg-item { border-color: #e2e6f0; background: rgba(0,0,0,.01); }
.fdocs--light .fdocs-urg-item--alert { border-color: rgba(255,91,106,.3); }
.fdocs--light .fdocs-urg-item--warn  { border-color: rgba(246,179,74,.3); }
.fdocs--light .fdocs-filters__sep { background: #e2e6f0; }
.fdocs--light .fdocs-actions__btn { background: #f5f7fb; border-color: #e2e6f0; color: #6b7280; }
.fdocs--light .fdocs-actions__btn:hover { background: #eaecf5; color: #1a1d23; }
</style>
