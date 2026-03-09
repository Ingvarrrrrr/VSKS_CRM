<template>
  <div class="plan-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-calendar-check" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">План-график закупок</div>
          <div class="page-subtitle">Подтверждённые закупки · {{ selectedYear ?? 'все годы' }}</div>
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
        <span class="stat-label">Итого НМЦК</span>
        <span class="stat-val">{{ fmt(totalNmck) }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Законтрактовано</span>
        <span class="stat-val" style="color:#3B82F6">{{ fmt(totalContracted) }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Оплачено</span>
        <span class="stat-val" style="color:#22C55E">{{ fmt(totalPaid) }}</span>
      </div>
      <div class="stat-sep" />
      <div class="stat-item">
        <span class="stat-label">Экономия</span>
        <span class="stat-val" style="color:#8B5CF6">{{ fmt(totalEconomy) }}</span>
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
              <th class="th-money">НМЦК</th>
              <th class="th-method">Способ</th>
              <th class="th-contractor">Контрагент</th>
              <th class="th-money">Цена договора</th>
              <th class="th-money">Оплачено</th>
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
                <span v-if="p.nmck || p.total_nmck || p.planned_total_price">
                  {{ fmt(Number(p.nmck || p.total_nmck || p.planned_total_price)) }}
                </span>
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
                <span v-if="p.contract_price" style="color:#3B82F6">{{ fmt(Number(p.contract_price)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="th-money">
                <span v-if="p.payment_amount" style="color:#22C55E">{{ fmt(Number(p.payment_amount)) }}</span>
                <span v-else class="text-medium-emphasis">—</span>
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
              <td class="th-money font-weight-bold">{{ fmt(totalNmck) }}</td>
              <td />
              <td />
              <td class="th-money font-weight-bold" style="color:#3B82F6">{{ fmt(totalContracted) }}</td>
              <td class="th-money font-weight-bold" style="color:#22C55E">{{ fmt(totalPaid) }}</td>
              <td colspan="2" />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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
  status: string
}

interface SubsidyMeta { id: number; name: string; year: number }

const purchases   = ref<Purchase[]>([])
const subsidies   = ref<SubsidyMeta[]>([])
const loading     = ref(false)
const exporting   = ref(false)
const selectedYear    = ref<number | null>(null)
const filterSubsidyId = ref<number | null>(null)
const filterSearch    = ref('')
const filterStatuses  = ref<string[]>(['confirmed', 'contracted', 'delivered', 'paid'])

const statusOptions = [
  { value: 'confirmed',  label: 'Подтверждено', color: 'blue'   },
  { value: 'contracted', label: 'Законтрактовано', color: 'indigo' },
  { value: 'delivered',  label: 'Исполнено',    color: 'teal'   },
  { value: 'paid',       label: 'Оплачено',     color: 'green'  },
]

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

const totalNmck       = computed(() => filtered.value.reduce((s, p) => s + Number(p.nmck || p.total_nmck || p.planned_total_price || 0), 0))
const totalContracted = computed(() => filtered.value.reduce((s, p) => s + Number(p.contract_price || 0), 0))
const totalPaid       = computed(() => filtered.value.reduce((s, p) => s + Number(p.payment_amount || 0), 0))
const totalEconomy    = computed(() => filtered.value.reduce((s, p) => s + Number(p.economy || 0), 0))

const toggleStatus = (v: string) => {
  const idx = filterStatuses.value.indexOf(v)
  if (idx >= 0) filterStatuses.value = filterStatuses.value.filter(x => x !== v)
  else filterStatuses.value = [...filterStatuses.value, v]
}

const resetFilters = () => {
  filterSubsidyId.value = null
  filterSearch.value = ''
  filterStatuses.value = ['confirmed', 'contracted', 'delivered', 'paid']
}

const loadData = async () => {
  loading.value = true
  try {
    const [subs, charts] = await Promise.all([
      apiFetch<SubsidyMeta[]>('/subsidies/'),
      apiFetch<any>('/dashboard/charts'),
    ])
    subsidies.value = subs
    if (availableYears.value.length) selectedYear.value = availableYears.value[0]

    // Load all confirmed+ purchases
    purchases.value = await apiFetch<Purchase[]>('/purchases/')
  } finally {
    loading.value = false
  }
}

loadData()

const openOrder = (id: number) => router.push(`/orders/${id}/edit`)

// ─── Formatting ────────────────────────────────────────────────────────────────
const fmt = (v: number) =>
  v > 0 ? v.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽' : '—'

const fmtDate = (d?: string | null) => {
  if (!d) return '—'
  const dt = new Date(d)
  return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Планируется', confirmed: 'Подтверждено',
  contracted: 'Законтрактовано', delivered: 'Исполнено', paid: 'Оплачено',
}
const STATUS_COLORS: Record<string, string> = {
  planned: 'grey', confirmed: 'blue', contracted: 'indigo', delivered: 'teal', paid: 'green',
}
const statusLabel = (s: string) => STATUS_LABELS[s] ?? s
const statusColor = (s: string) => STATUS_COLORS[s] ?? 'grey'

const methodLabel = (m?: string | null) =>
  m === 'single' ? 'Единственный исполнитель' : m === 'competitive' ? 'Конкурсная процедура' : ''

// ─── Excel export ──────────────────────────────────────────────────────────────
const exportExcel = () => {
  exporting.value = true
  try {
    const headers = [
      '№ п/п', 'Реестровый №', 'Предмет закупки', 'Категория ФЭО', 'Субсидия',
      'НМЦК (руб.)', 'Способ закупки', 'Контрагент', '№ договора', 'Дата договора',
      'Цена договора (руб.)', 'Оплачено (руб.)', 'Экономия (руб.)', 'Срок исполнения', 'Статус',
    ]

    const rows = filtered.value.map((p, idx) => [
      idx + 1,
      p.registry_number ?? '',
      p.subject || p.item_name || '',
      p.feo_category_name ?? '',
      p.subsidy_name ?? '',
      Number(p.nmck || p.total_nmck || p.planned_total_price || 0),
      methodLabel(p.purchase_method),
      p.contractor_name ?? '',
      p.contract_number ?? '',
      p.contract_date ?? '',
      Number(p.contract_price || 0),
      Number(p.payment_amount || 0),
      Number(p.economy || 0),
      p.execution_term ?? '',
      statusLabel(p.status),
    ])

    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])

    // Column widths
    ws['!cols'] = [
      { wch: 5 }, { wch: 14 }, { wch: 40 }, { wch: 30 }, { wch: 20 },
      { wch: 16 }, { wch: 26 }, { wch: 28 }, { wch: 14 }, { wch: 14 },
      { wch: 16 }, { wch: 16 }, { wch: 14 }, { wch: 14 }, { wch: 18 },
    ]

    // Totals row
    const totalRow = [
      'ИТОГО', '', '', '', '',
      totalNmck.value, '', '', '', '',
      totalContracted.value, totalPaid.value, totalEconomy.value, '', '',
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
.page-title    { font-size: 26px; font-weight: 700; color: #111827; line-height: 1.2; }
.page-subtitle { font-size: 13px; color: #6B7280; margin-top: 2px; }

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
  background: #fff; border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 14px 24px; margin-bottom: 20px;
  flex-wrap: wrap; gap: 16px;
}
.stat-item  { display: flex; flex-direction: column; align-items: center; min-width: 100px; }
.stat-label { font-size: 11px; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
.stat-val   { font-size: 17px; font-weight: 700; color: #111827; }
.stat-sep   { width: 1px; height: 36px; background: rgba(0,0,0,0.08); flex-shrink: 0; }

/* ── Table card ── */
.plan-card {
  background: #fff; border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.07);
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow: hidden;
}

.plan-table-wrap { overflow-x: auto; }

.plan-table {
  width: 100%; border-collapse: collapse; font-size: 0.82rem;
}
.plan-table thead th {
  padding: 10px 10px; text-align: left;
  font-weight: 600; font-size: 0.7rem;
  text-transform: uppercase; letter-spacing: 0.05em;
  color: rgba(0,0,0,0.5); border-bottom: 2px solid rgba(0,0,0,0.08);
  white-space: nowrap; background: #FAFAFA; position: sticky; top: 0;
}
.plan-table td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
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

.plan-name { font-weight: 500; color: #111827; line-height: 1.3; }
.plan-reg  { font-size: 11px; color: #9CA3AF; margin-top: 2px; }

.plan-total {
  background: #F8FAFC;
  border-top: 2px solid rgba(0,0,0,0.1);
}
.plan-total td { padding: 10px 10px; font-size: 0.82rem; }

.empty-state {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 60px 0;
}
</style>
