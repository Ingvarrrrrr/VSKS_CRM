<template>
  <div class="plan-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-calendar-check" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">План-график закупок</div>
          <div class="page-subtitle">Закупки план-графика · {{ selectedYear ?? 'все годы' }}</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-chip-group v-if="availableYears.length" v-model="selectedYear" mandatory class="year-chips mr-3">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
        <v-btn
          color="success" prepend-icon="mdi-file-excel" variant="flat"
          :loading="exporting" :disabled="filtered.length === 0"
          @click="exportExcel"
        >
          Скачать Excel
        </v-btn>
      </div>
    </div>

    <!-- ── Filters ── -->
    <div class="filters-bar">
      <v-select
        v-model="filterSubsidyId"
        :items="[{ id: null, name: 'Все субсидии' }, ...subsidies]"
        item-title="name" item-value="id"
        label="Субсидия" variant="outlined" density="compact"
        hide-details clearable style="max-width:280px"
      />
      <v-text-field
        v-model="filterSearch"
        prepend-inner-icon="mdi-magnify"
        placeholder="Поиск по наименованию..."
        variant="outlined" density="compact"
        hide-details clearable style="max-width:260px"
      />
      <div class="status-chips">
        <v-chip
          v-for="s in statusOptions" :key="s.value"
          :color="filterStatuses.includes(s.value) ? s.color : 'default'"
          :variant="filterStatuses.includes(s.value) ? 'flat' : 'outlined'"
          size="small" class="mr-1 cursor-pointer"
          @click="toggleStatus(s.value)"
        >{{ s.label }}</v-chip>
      </div>
      <v-btn variant="text" size="small" color="grey" @click="resetFilters">Сбросить</v-btn>
    </div>

    <!-- ── Stats bar ── -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-label">Позиций</span>
        <span class="stat-val">{{ filtered.length }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Итого план</span>
        <span class="stat-val">{{ fmt(totalPlan) }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Итого расчёт</span>
        <span class="stat-val" style="color:var(--color-contracted)">{{ fmt(totalCalc) }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Остаток</span>
        <span class="stat-val" :style="{ color: totalPlan - totalCalc >= 0 ? 'var(--color-savings)' : 'var(--color-paid)' }">
          {{ fmtSigned(totalPlan - totalCalc) }}
        </span>
      </div>
    </div>

    <!-- ── Table ── -->
    <div class="plan-card">
      <v-progress-linear v-if="loading" indeterminate color="primary" />

      <div v-if="!loading && filtered.length === 0" class="empty-state">
        <v-icon icon="mdi-calendar-blank" size="56" color="grey-lighten-2" />
        <div class="text-medium-emphasis mt-3">Нет закупок по выбранным фильтрам</div>
      </div>

      <div v-else class="plan-table-wrap">
        <table class="plan-table">
          <thead>
            <tr>
              <th class="th-num">№</th>
              <th class="th-name">Предмет закупки</th>
              <th class="th-feo">Категория ФЭО</th>
              <th class="th-sub">Субсидия</th>
              <th class="th-money">НМЦД</th>
              <th class="th-money">Сумма (расчёт)</th>
              <th class="th-method">Способ</th>
              <th class="th-contractor">Контрагент</th>
              <th class="th-money">Цена договора</th>
              <th class="th-money">Оплачено</th>
              <th class="th-date">Плановая дата</th>
              <th class="th-date">Срок</th>
              <th class="th-status">Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, idx) in filtered" :key="p.id" class="plan-tr" @click="openOrder(p.id)">
              <td class="th-num text-medium-emphasis">{{ idx + 1 }}</td>
              <td class="th-name">
                <div class="plan-name">{{ p.subject || p.item_name || '—' }}</div>
                <div v-if="p.registry_number" class="plan-reg">{{ p.registry_number }}</div>
              </td>
              <td class="th-feo text-caption text-medium-emphasis">{{ p.feo_category_name || '—' }}</td>
              <td class="th-sub text-caption">{{ p.subsidy_name || '—' }}</td>
              <td class="th-money">
                <span v-if="planAmount(p) > 0">{{ fmt(planAmount(p)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-money">
                <span v-if="calcAmount(p) > 0" style="color:var(--color-contracted)">{{ fmt(calcAmount(p)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-method">
                <v-chip v-if="p.purchase_method" size="x-small"
                  :color="p.purchase_method === 'single' ? 'blue-grey' : 'purple'" variant="tonal">
                  {{ p.purchase_method === 'single' ? 'ЕИ' : 'КП' }}
                </v-chip>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-contractor text-caption">{{ p.contractor_name || '—' }}</td>
              <td class="th-money">
                <span v-if="p.contract_price" style="color:var(--color-contracted)">{{ fmt(Number(p.contract_price)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-money">
                <span v-if="p.payment_amount" style="color:var(--color-paid)">{{ fmt(Number(p.payment_amount)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-date text-caption" :class="{ 'text-warning': isPastPlanned(p.procurement_planned_date) }">
                {{ fmtDate(p.procurement_planned_date) }}
              </td>
              <td class="th-date text-caption">{{ fmtDate(p.execution_term) }}</td>
              <td class="th-status">
                <v-chip size="x-small" :color="statusColor(p.status)" variant="flat">
                  {{ statusLabel(p.status) }}
                </v-chip>
              </td>
            </tr>
          </tbody>
          <!-- Footer totals -->
          <tfoot v-if="filtered.length > 0">
            <tr class="plan-total">
              <td colspan="4" class="font-weight-bold pl-3">ИТОГО ({{ filtered.length }} позиций)</td>
              <td class="th-money font-weight-bold">{{ fmt(totalPlan) }}</td>
              <td class="th-money font-weight-bold" style="color:var(--color-contracted)">{{ fmt(totalCalc) }}</td>
              <td />
              <td />
              <td class="th-money font-weight-bold" style="color:var(--color-contracted)">{{ fmt(totalContracted) }}</td>
              <td class="th-money font-weight-bold" style="color:var(--color-paid)">{{ fmt(totalPaid) }}</td>
              <td colspan="3" />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>

    <!-- ── Версии план-графика (только при выборе одной субсидии) ── -->
    <div v-if="filterSubsidyId !== null" class="plan-card mt-5">
      <div class="versions-header">
        <div class="versions-title">
          <v-icon icon="mdi-history" size="20" color="primary" class="mr-2" />
          Версии план-графика
        </div>
        <div class="versions-summary" v-if="versionsList.length > 0">
          Остаток: <strong>{{ fmtSigned(versionsRemainder) }}</strong>
        </div>
        <v-btn
          color="primary" size="small" variant="flat" prepend-icon="mdi-content-save"
          :loading="saveVersionLoading" @click="openSaveVersionDialog"
        >
          Зафиксировать версию
        </v-btn>
      </div>

      <v-progress-linear v-if="versionsLoading" indeterminate color="primary" />

      <div v-if="!versionsLoading && versionsList.length === 0" class="empty-state" style="padding:32px 0">
        <v-icon icon="mdi-clock-outline" size="40" color="grey-lighten-2" />
        <div class="text-medium-emphasis mt-2 text-caption">Версии не зафиксированы</div>
      </div>

      <div v-if="!versionsLoading && versionsList.length > 0" class="versions-table-wrap">
        <table class="plan-table">
          <thead>
            <tr>
              <th style="width:60px">№</th>
              <th style="width:110px">Дата</th>
              <th>Автор</th>
              <th>Примечание</th>
              <th class="th-money">Итого план</th>
              <th class="th-money">Итого расчёт</th>
              <th style="width:80px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="v in versionsList" :key="v.id" class="plan-tr">
              <td class="text-medium-emphasis text-caption">{{ v.version_number }}</td>
              <td class="text-caption">{{ fmtDate(v.created_at) }}</td>
              <td class="text-caption">{{ v.created_by_name || '—' }}</td>
              <td class="text-caption">{{ v.note || '—' }}</td>
              <td class="th-money text-caption">{{ fmt(Number(v.total_planned) || 0) }}</td>
              <td class="th-money text-caption" style="color:var(--color-contracted)">
                {{ fmt(Number(v.total_effective ?? v.total_planned) || 0) }}
              </td>
              <td>
                <v-btn
                  icon="mdi-file-excel" size="x-small" variant="text" color="success"
                  :title="`Скачать Excel версии ${v.version_number}`"
                  @click.stop="downloadVersionExcel(v.id)"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Dialog: зафиксировать версию ── -->
    <v-dialog v-model="showSaveVersionDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-5">Зафиксировать версию план-графика</v-card-title>
        <v-card-text class="px-5 pb-2">
          <v-textarea
            v-model="saveVersionNote"
            label="Примечание (необязательно)"
            variant="outlined" density="compact"
            rows="3" auto-grow hide-details
          />
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showSaveVersionDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="saveVersionLoading" @click="saveVersion">
            Зафиксировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ── -->
    <v-snackbar v-model="snack.show" :color="snack.color" timeout="4000">
      {{ snack.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import * as XLSX from 'xlsx'

const router = useRouter()

interface Purchase {
  id: number
  purchase_number?: number | null
  registry_number?: string | null
  subject?: string | null
  item_name?: string | null
  item_type?: string | null
  feo_category_name?: string | null
  subsidy_name?: string | null
  subsidy_id?: number | null
  contractor_name?: string | null
  nmck?: number | null
  total_nmck?: number | null
  planned_total_price?: number | null
  contract_price?: number | null
  payment_amount?: number | null
  economy?: number | null
  purchase_method?: string | null
  execution_term?: string | null
  contract_number?: string | null
  contract_date?: string | null
  procurement_planned_date?: string | null
  status: string
  etp_url?: string | null
}

interface SubsidyMeta { id: number; name: string; year: number }

interface PlanGraphVersion {
  id: number
  version_number: number
  created_at: string
  created_by_name?: string | null
  note?: string | null
  total_planned?: number | null
  total_effective?: number | null
}

const purchases   = ref<Purchase[]>([])
const subsidies   = ref<SubsidyMeta[]>([])
const loading     = ref(false)
const exporting   = ref(false)
const selectedYear    = ref<number | null>(null)
const filterSubsidyId = ref<number | null>(null)
const filterSearch    = ref('')
const filterStatuses  = ref<string[]>([
  'plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid',
])

const statusOptions = [
  { value: 'plan_schedule',   label: 'План-график',     color: 'blue'   },
  { value: 'confirmed',       label: 'Подтверждено',    color: 'cyan'   },
  { value: 'work_in_progress',label: 'В работе',        color: 'orange' },
  { value: 'contracted',      label: 'Договор',         color: 'indigo' },
  { value: 'ordered',         label: 'Заказано',        color: 'teal'   },
  { value: 'delivered',       label: 'Поставлено',      color: 'green'  },
  { value: 'paid',            label: 'Оплачено',        color: 'success'},
]

// ── Versions block ──
const versionsList         = ref<PlanGraphVersion[]>([])
const versionsLoading      = ref(false)
const showSaveVersionDialog = ref(false)
const saveVersionNote      = ref('')
const saveVersionLoading   = ref(false)
const snack = ref({ show: false, text: '', color: 'info' })

const availableYears = computed(() => {
  const years = new Set<number>()
  for (const s of subsidies.value) years.add(s.year)
  return [...years].sort((a, b) => b - a)
})

const yearSubsidyIds = computed(() => {
  if (!selectedYear.value) return null
  return new Set(subsidies.value.filter(s => s.year === selectedYear.value).map(s => s.id))
})

const filtered = computed(() => {
  const q = filterSearch.value.toLowerCase()
  return purchases.value.filter(p => {
    if (!filterStatuses.value.includes(p.status)) return false
    if (filterSubsidyId.value && p.subsidy_id !== filterSubsidyId.value) return false
    if (yearSubsidyIds.value && p.subsidy_id && !yearSubsidyIds.value.has(p.subsidy_id)) return false
    if (q) {
      const name = (p.subject || p.item_name || '').toLowerCase()
      if (!name.includes(q)) return false
    }
    return true
  })
})

// ── Amount helpers ──
const planAmount = (p: Purchase) =>
  Number(p.nmck) || Number(p.total_nmck) || Number(p.planned_total_price) || 0

const calcAmount = (p: Purchase) => {
  if (p.status === 'delivered' || p.status === 'paid') {
    return Number(p.payment_amount) || Number(p.contract_price) || planAmount(p)
  }
  return planAmount(p)
}

const totalPlan       = computed(() => filtered.value.reduce((s, p) => s + planAmount(p), 0))
const totalCalc       = computed(() => filtered.value.reduce((s, p) => s + calcAmount(p), 0))
const totalContracted = computed(() => filtered.value.reduce((s, p) => s + Number(p.contract_price || 0), 0))
const totalPaid       = computed(() => filtered.value.reduce((s, p) => s + Number(p.payment_amount || 0), 0))

// ── Versions summary ──
const versionsRemainder = computed(() => {
  if (versionsList.value.length === 0) return 0
  const sorted = [...versionsList.value].sort((a, b) => a.version_number - b.version_number)
  const first = sorted[0]
  const last  = sorted[sorted.length - 1]
  const firstPlan = Number(first.total_planned) || 0
  const lastCalc  = Number(last.total_effective ?? last.total_planned) || 0
  return firstPlan - lastCalc
})

const toggleStatus = (v: string) => {
  const idx = filterStatuses.value.indexOf(v)
  if (idx >= 0) filterStatuses.value = filterStatuses.value.filter(x => x !== v)
  else filterStatuses.value = [...filterStatuses.value, v]
}

const resetFilters = () => {
  filterSubsidyId.value = null
  filterSearch.value = ''
  filterStatuses.value = [
    'plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid',
  ]
}

const loadData = async () => {
  loading.value = true
  try {
    const [subs] = await Promise.all([
      apiFetch<SubsidyMeta[]>('/subsidies/'),
    ])
    subsidies.value = subs
    if (availableYears.value.length) selectedYear.value = availableYears.value[0]

    purchases.value = await apiFetch<Purchase[]>('/purchases/?scope=plan')
  } finally {
    loading.value = false
  }
}

loadData()

// ── Versions loading ──
const loadVersions = async () => {
  if (filterSubsidyId.value === null) { versionsList.value = []; return }
  versionsLoading.value = true
  try {
    versionsList.value = await apiFetch<PlanGraphVersion[]>(`/subsidies/${filterSubsidyId.value}/plan-graph/versions`)
  } catch {
    versionsList.value = []
  } finally {
    versionsLoading.value = false
  }
}

watch(filterSubsidyId, () => { loadVersions() })

const openSaveVersionDialog = () => {
  saveVersionNote.value = ''
  showSaveVersionDialog.value = true
}

const saveVersion = async () => {
  if (filterSubsidyId.value === null) return
  saveVersionLoading.value = true
  try {
    await apiFetch(`/subsidies/${filterSubsidyId.value}/plan-graph/versions`, {
      method: 'POST',
      body: JSON.stringify({ note: saveVersionNote.value || null }),
    })
    showSaveVersionDialog.value = false
    snack.value = { show: true, text: 'Версия план-графика зафиксирована', color: 'success' }
    await loadVersions()
  } catch (e: any) {
    snack.value = { show: true, text: e?.payload?.message || e?.message || 'Ошибка сохранения', color: 'error' }
  } finally {
    saveVersionLoading.value = false
  }
}

const downloadVersionExcel = async (vid: number) => {
  if (filterSubsidyId.value === null) return
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/subsidies/${filterSubsidyId.value}/plan-graph/versions/${vid}/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('Ошибка экспорта')
    const blob = await res.blob()
    const cd = res.headers.get('content-disposition') || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const filename = m ? m[1] : `version-${vid}.xlsx`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    snack.value = { show: true, text: e?.message || 'Ошибка экспорта', color: 'error' }
  }
}

const openOrder = (id: number) => router.push(`/orders/${id}/edit`)

// ─── Formatting ────────────────────────────────────────────────────────────────
const fmt = (v: number) =>
  v > 0 ? v.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽' : '—'

const fmtSigned = (v: number) => v.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'

const fmtDate = (d?: string | null) => {
  if (!d) return '—'
  const dt = new Date(d)
  return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const isPastPlanned = (d?: string | null) => {
  if (!d) return false
  return new Date(d) < new Date()
}

const STATUS_LABELS: Record<string, string> = {
  planned:          'Планируется',
  plan_schedule:    'План-график',
  confirmed:        'Подтверждено',
  work_in_progress: 'В работе',
  contracted:       'Договор',
  ordered:          'Заказано',
  delivered:        'Поставлено',
  paid:             'Оплачено',
}
const STATUS_COLORS: Record<string, string> = {
  planned:          'grey',
  plan_schedule:    'blue',
  confirmed:        'cyan',
  work_in_progress: 'orange',
  contracted:       'indigo',
  ordered:          'teal',
  delivered:        'green',
  paid:             'success',
}
const statusLabel = (s: string) => STATUS_LABELS[s] ?? s
const statusColor = (s: string) => STATUS_COLORS[s] ?? 'grey'

const methodLabel = (m?: string | null) =>
  m === 'single' ? 'Единственный поставщик' : m === 'competitive' ? 'Конкурсная процедура' : ''

// ─── Excel export ──────────────────────────────────────────────────────────────
const exportExcel = () => {
  exporting.value = true
  try {
    const headers = [
      '№ п/п', 'Реестровый №', 'Предмет закупки', 'Категория ФЭО', 'Субсидия',
      'НМЦД (руб.)', 'Сумма (план, руб.)', 'Сумма (расчёт, руб.)', 'Способ закупки',
      'Контрагент', '№ договора', 'Дата договора',
      'Цена договора (руб.)', 'Оплачено (руб.)',
      'Плановая дата закупки', 'Срок исполнения', 'Статус', 'Ссылка ЭТП',
    ]

    const rows = filtered.value.map((p, idx) => [
      idx + 1,
      p.registry_number ?? '',
      p.subject || p.item_name || '',
      p.feo_category_name ?? '',
      p.subsidy_name ?? '',
      Number(p.nmck || p.total_nmck || p.planned_total_price || 0),
      planAmount(p),
      calcAmount(p),
      methodLabel(p.purchase_method),
      p.contractor_name ?? '',
      p.contract_number ?? '',
      p.contract_date ?? '',
      Number(p.contract_price || 0),
      Number(p.payment_amount || 0),
      p.procurement_planned_date ?? '',
      p.execution_term ?? '',
      statusLabel(p.status),
      p.etp_url ?? '',
    ])

    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])

    // Column widths
    ws['!cols'] = [
      { wch: 5 }, { wch: 14 }, { wch: 40 }, { wch: 30 }, { wch: 20 },
      { wch: 16 }, { wch: 18 }, { wch: 18 }, { wch: 26 }, { wch: 28 },
      { wch: 14 }, { wch: 14 }, { wch: 16 }, { wch: 16 },
      { wch: 14 }, { wch: 14 }, { wch: 18 }, { wch: 40 },
    ]

    // Totals row
    const totalRow = [
      'ИТОГО', '', '', '', '',
      totalPlan.value, totalPlan.value, totalCalc.value, '', '', '', '',
      totalContracted.value, totalPaid.value, '', '', '', '',
    ]
    XLSX.utils.sheet_add_aoa(ws, [totalRow], { origin: -1 })

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'План-график')

    const year = selectedYear.value ?? 'все'
    XLSX.writeFile(wb, `план_график_${year}.xlsx`)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.plan-page {
  padding: 20px 24px;
  max-width: 1800px;
}

/* ── Header ── */
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px; flex-wrap: wrap; gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; gap: 8px; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Filters ── */
.filters-bar {
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap; margin-bottom: 16px;
}
.status-chips { display: flex; flex-wrap: wrap; }
.cursor-pointer { cursor: pointer; }

/* ── Stats bar ── */
.stats-bar {
  display: flex; align-items: center; gap: 0;
  background: var(--crm-surface); border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 14px 24px; margin-bottom: 20px;
  flex-wrap: wrap; gap: 16px;
}
.stat-item  { display: flex; flex-direction: column; align-items: center; min-width: 100px; }
.stat-label { font-size: 11px; color: var(--crm-text-faint); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
.stat-val   { font-size: 17px; font-weight: 700; color: var(--crm-text); }
.stat-sep   { width: 1px; height: 36px; background: var(--crm-border); flex-shrink: 0; }

/* ── Table card ── */
.plan-card {
  background: var(--crm-surface); border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  overflow: hidden;
}

.plan-table-wrap, .versions-table-wrap { overflow-x: auto; }

.plan-table {
  width: 100%; border-collapse: collapse; font-size: 0.82rem;
}
.plan-table thead th {
  padding: 10px 10px; text-align: left;
  font-weight: 600; font-size: 0.7rem;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--crm-text-muted); border-bottom: 2px solid var(--crm-border-strong);
  white-space: nowrap; background: var(--crm-table-header); position: sticky; top: 0;
}
.plan-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
}
.plan-tr { cursor: pointer; transition: background 0.1s; }
.plan-tr:hover { background: rgba(59,130,246,0.04); }

.th-num        { width: 40px; text-align: center; }
.th-name       { min-width: 200px; max-width: 320px; }
.th-feo        { min-width: 140px; max-width: 200px; }
.th-sub        { min-width: 100px; max-width: 160px; }
.th-money      { width: 120px; text-align: right; white-space: nowrap; }
.th-method     { width: 60px; text-align: center; }
.th-contractor { min-width: 120px; max-width: 180px; }
.th-date       { width: 90px; white-space: nowrap; }
.th-status     { width: 110px; }

.plan-name { font-weight: 500; color: var(--crm-text); line-height: 1.3; }
.plan-reg  { font-size: 11px; color: var(--crm-text-faint); margin-top: 2px; }

.plan-total {
  background: var(--crm-surface-alt);
  border-top: 2px solid var(--crm-border-strong);
}
.plan-total td { padding: 10px 10px; font-size: 0.82rem; }

.empty-state {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 60px 0;
}

/* ── Versions block ── */
.versions-header {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 20px; border-bottom: 1px solid var(--crm-border);
  flex-wrap: wrap;
}
.versions-title {
  display: flex; align-items: center;
  font-weight: 600; font-size: 0.95rem; color: var(--crm-text);
}
.versions-summary {
  font-size: 0.85rem; color: var(--crm-text-muted);
  margin-left: auto;
}
</style>
