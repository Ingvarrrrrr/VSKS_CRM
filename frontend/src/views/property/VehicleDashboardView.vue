<template>
  <div class="veh-dashboard" :key="route.fullPath">

    <!-- ── Header ── -->
    <div class="veh-dash-header">
      <div class="veh-dash-header-left">
        <v-icon icon="mdi-car-multiple" size="32" color="primary" class="mr-3" />
        <div>
          <div class="veh-dash-title gradient-text">Дашборд автотранспорта</div>
          <div class="veh-dash-subtitle text-medium-emphasis text-caption">
            {{ periodLabel }}
          </div>
        </div>
      </div>
      <div class="veh-dash-header-right">
        <!-- Period selector -->
        <v-chip-group v-model="periodPreset" mandatory class="period-chips">
          <v-chip v-for="p in PERIOD_PRESETS" :key="p.value" :value="p.value"
            filter variant="elevated" color="primary" size="small">
            {{ p.label }}
          </v-chip>
        </v-chip-group>

        <!-- Custom date range -->
        <v-menu v-if="periodPreset === 'custom'" :close-on-content-click="false" location="bottom end">
          <template #activator="{ props: mProps }">
            <v-btn v-bind="mProps" variant="outlined" size="small" class="ml-2" prepend-icon="mdi-calendar-range">
              {{ customFrom || '...' }} — {{ customTo || '...' }}
            </v-btn>
          </template>
          <v-card min-width="280" class="pa-3">
            <v-text-field v-model="customFrom" label="От" type="date" density="compact" variant="outlined" class="mb-2" />
            <v-text-field v-model="customTo" label="До" type="date" density="compact" variant="outlined" />
            <div class="d-flex justify-end mt-2">
              <v-btn size="small" color="primary" @click="onCustomRangeApply">Применить</v-btn>
            </div>
          </v-card>
        </v-menu>

        <!-- Org filter -->
        <v-autocomplete
          v-model="selectedOrgIds"
          :items="orgOptions"
          item-title="name"
          item-value="id"
          label="Организации"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
          style="min-width: 180px; max-width: 280px;"
          class="ml-3"
        />

        <!-- Edit / Reset -->
        <v-btn
          :icon="isEditing ? 'mdi-lock-open' : 'mdi-cursor-move'"
          :variant="isEditing ? 'flat' : 'tonal'"
          :color="isEditing ? 'warning' : 'default'"
          size="small" class="ml-3"
          :title="isEditing ? 'Завершить' : 'Настроить layout'"
          @click="toggleEditing"
        />
        <v-btn
          v-if="isEditing"
          icon="mdi-restore"
          variant="tonal"
          color="error"
          size="small"
          class="ml-1"
          title="Сбросить layout"
          @click="resetLayout"
        />
        <v-btn
          icon="mdi-refresh"
          variant="tonal"
          color="primary"
          :loading="anyLoading"
          size="small"
          class="ml-3"
          @click="fetchAll"
        />
      </div>
    </div>

    <!-- Edit mode banner -->
    <div v-if="isEditing" class="edit-mode-banner">
      <v-icon icon="mdi-cursor-move" size="18" class="mr-2" />
      Режим редактирования — перетаскивайте и изменяйте размер виджетов
      <v-btn size="small" variant="tonal" color="white" class="ml-4" @click="toggleEditing">Готово</v-btn>
    </div>

    <!-- ── Grid Layout ── -->
    <GridLayout
      v-model:layout="layout"
      :col-num="12"
      :row-height="30"
      :is-draggable="isEditing"
      :is-resizable="isEditing"
      :margin="[10, 10]"
      :vertical-compact="true"
      :use-css-transforms="true"
      @layout-updated="onLayoutUpdated"
    >
      <!-- ── KPI: Машин всего ── -->
      <GridItem v-bind="getLayoutItem('kpi-vehicles')" key="kpi-vehicles">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Машины
          </div>
          <VehicleKpiCard
            title="Машин всего"
            :value="kpi.total_vehicles"
            icon="mdi-car-multiple"
            color="primary"
          />
        </div>
      </GridItem>

      <!-- ── KPI: Стоимость бензина ── -->
      <GridItem v-bind="getLayoutItem('kpi-fuel')" key="kpi-fuel">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Бензин
          </div>
          <VehicleKpiCard
            title="Бензин за период"
            :value="kpi.fuel_total_cost"
            unit="₽"
            icon="mdi-gas-station"
            color="orange"
          />
        </div>
      </GridItem>

      <!-- ── KPI: Стоимость ремонтов ── -->
      <GridItem v-bind="getLayoutItem('kpi-repairs')" key="kpi-repairs">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Ремонты
          </div>
          <VehicleKpiCard
            title="Ремонты за период"
            :value="kpi.repairs_total_cost"
            unit="₽"
            icon="mdi-wrench"
            color="error"
          />
        </div>
      </GridItem>

      <!-- ── KPI: Пробег ── -->
      <GridItem v-bind="getLayoutItem('kpi-mileage')" key="kpi-mileage">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Пробег
          </div>
          <VehicleKpiCard
            title="Пробег за период"
            :value="kpi.total_mileage_km"
            unit="км"
            icon="mdi-counter"
            color="success"
          />
        </div>
      </GridItem>

      <!-- ── Канистра ── -->
      <GridItem v-bind="getLayoutItem('canister')" key="canister">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Канистра
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="text-subtitle-2 pb-1 pt-3 px-3">
              <v-icon icon="mdi-gas-station" size="18" color="orange" class="mr-1" />
              Топливный бюджет
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 d-flex align-center justify-center pa-2">
              <FuelCanisterWidget
                :level="canister.level"
                :liters="canister.spent_l"
                :budget="canister.fuel_budget"
                :period-label="canister.period_label"
              />
            </v-card-text>
          </v-card>
        </div>
      </GridItem>

      <!-- ── В ремонте ── -->
      <GridItem v-bind="getLayoutItem('in_repair')" key="in_repair">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> В ремонте
          </div>
          <VehiclesInRepairWidget />
        </div>
      </GridItem>

      <!-- ── ТО / Предупреждения ── -->
      <GridItem v-bind="getLayoutItem('to_warning')" key="to_warning">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Предупреждения
          </div>
          <MaintenanceWarningWidget />
        </div>
      </GridItem>

      <!-- ── Bar: Машины по организациям ── -->
      <GridItem v-bind="getLayoutItem('bar_org')" key="bar_org">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> По орг.
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="d-flex align-center gap-2 pb-1 pt-3 px-3 text-subtitle-2">
              <v-icon icon="mdi-office-building" size="18" color="primary" class="mr-1" />
              Машины по организациям
              <v-spacer />
              <v-btn-toggle v-model="barOrgMode" mandatory density="compact" variant="outlined" rounded="sm">
                <v-btn value="owner" size="x-small">Владелец</v-btn>
                <v-btn value="assigned" size="x-small">Эксплуатант</v-btn>
              </v-btn-toggle>
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 pa-2">
              <div v-if="loadingByOrg" class="d-flex justify-center align-center h-100 py-6">
                <v-progress-circular indeterminate color="primary" />
              </div>
              <div v-else-if="byOrgError" class="pa-2">
                <v-alert type="error" density="compact" variant="tonal">{{ byOrgError }}</v-alert>
              </div>
              <apexchart
                v-else
                type="bar"
                height="220"
                :options="barOrgOptions"
                :series="barOrgSeries"
              />
            </v-card-text>
          </v-card>
        </div>
      </GridItem>

      <!-- ── Donut: Состояние флота ── -->
      <GridItem v-bind="getLayoutItem('donut_state')" key="donut_state">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Состояние
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="pb-1 pt-3 px-3 text-subtitle-2">
              <v-icon icon="mdi-chart-donut" size="18" color="purple" class="mr-1" />
              Состояние флота
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 pa-1">
              <div v-if="loadingDonut" class="d-flex justify-center align-center h-100 py-6">
                <v-progress-circular indeterminate color="purple" />
              </div>
              <div v-else-if="donutError" class="pa-2">
                <v-alert type="error" density="compact" variant="tonal">{{ donutError }}</v-alert>
              </div>
              <apexchart
                v-else
                type="donut"
                height="220"
                :options="donutOptions"
                :series="donutSeries"
              />
            </v-card-text>
          </v-card>
        </div>
      </GridItem>

      <!-- ── Line: Расход топлива ── -->
      <GridItem v-bind="getLayoutItem('line_fuel')" key="line_fuel">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Расход
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="pb-1 pt-3 px-3 text-subtitle-2">
              <v-icon icon="mdi-chart-line" size="18" color="orange" class="mr-1" />
              Расход топлива
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 pa-1">
              <div v-if="loadingLine" class="d-flex justify-center align-center h-100 py-6">
                <v-progress-circular indeterminate color="orange" />
              </div>
              <div v-else-if="lineError" class="pa-2">
                <v-alert type="error" density="compact" variant="tonal">{{ lineError }}</v-alert>
              </div>
              <apexchart
                v-else
                type="line"
                height="220"
                :options="lineOptions"
                :series="lineSeries"
              />
            </v-card-text>
          </v-card>
        </div>
      </GridItem>

      <!-- ── Table: Все ТС ── -->
      <GridItem v-bind="getLayoutItem('all_vehicles')" key="all_vehicles">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> Все ТС
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="pb-1 pt-3 px-3 text-subtitle-2 d-flex align-center gap-2">
              <v-icon icon="mdi-car-multiple" size="18" color="primary" class="mr-1" />
              Все транспортные средства
              <v-spacer />
              <v-text-field
                v-model="allVehiclesSearch"
                density="compact"
                variant="outlined"
                placeholder="Поиск..."
                hide-details
                prepend-inner-icon="mdi-magnify"
                clearable
                style="max-width: 220px;"
              />
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 pa-0 overflow-y-auto">
              <div v-if="loadingAll" class="d-flex justify-center align-center py-6">
                <v-progress-circular indeterminate color="primary" />
              </div>
              <v-alert v-else-if="allVehiclesError" type="error" density="compact" variant="tonal" class="ma-3">
                {{ allVehiclesError }}
              </v-alert>
              <v-data-table
                v-else
                :items="allVehicles"
                :headers="allVehiclesHeaders"
                :search="allVehiclesSearch"
                density="compact"
                :items-per-page="15"
                class="all-vehicles-table clickable-rows"
                @click:row="(_: unknown, { item }: { item: AllVehicleRow }) => router.push(`/property/vehicles/${item.vehicle_id}`)"
              >
                <template #item.plate="{ item }">
                  <v-chip size="x-small" variant="tonal" color="primary">{{ item.plate }}</v-chip>
                </template>
                <template #item.state="{ item }">
                  <v-chip size="x-small" :color="ALL_VEH_STATE_COLORS[item.state] || 'default'" variant="tonal">
                    {{ ALL_VEH_STATE_LABELS[item.state] || item.state }}
                  </v-chip>
                </template>
                <template #item.fuel_cost="{ item }">
                  {{ fmtCurrency(item.fuel_cost) }}
                </template>
                <template #item.repair_cost="{ item }">
                  {{ fmtCurrency(item.repair_cost) }}
                </template>
                <template #item.mileage_km="{ item }">
                  {{ item.mileage_km.toLocaleString('ru-RU') }} км
                </template>
                <template #item.insurance_until="{ item }">
                  <span :class="item.insurance_overdue ? 'text-error font-weight-bold' : ''">
                    {{ item.insurance_until || '—' }}
                    <v-icon v-if="item.insurance_overdue" icon="mdi-alert" size="14" color="error" class="ml-1" />
                  </span>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </div>
      </GridItem>

      <!-- ── Table: TOP-10 по расходам ── -->
      <GridItem v-bind="getLayoutItem('top10_table')" key="top10_table">
        <div class="grid-widget" :class="{ 'grid-widget--editing': isEditing }">
          <div v-if="isEditing" class="widget-drag-handle">
            <v-icon icon="mdi-drag" size="14" /> TOP-10
          </div>
          <v-card class="h-100 d-flex flex-column" elevation="2">
            <v-card-title class="pb-1 pt-3 px-3 text-subtitle-2">
              <v-icon icon="mdi-trophy" size="18" color="amber" class="mr-1" />
              TOP-10 машин по расходам
            </v-card-title>
            <v-divider />
            <v-card-text class="flex-grow-1 pa-0 overflow-y-auto">
              <div v-if="loadingTop10" class="d-flex justify-center align-center py-6">
                <v-progress-circular indeterminate color="amber" />
              </div>
              <div v-else-if="top10Error" class="pa-3">
                <v-alert type="error" density="compact" variant="tonal">{{ top10Error }}</v-alert>
              </div>
              <v-data-table
                v-else
                :items="top10"
                :headers="top10Headers"
                density="compact"
                :items-per-page="10"
                hide-default-footer
                class="top10-table clickable-rows"
                @click:row="(_: unknown, { item }: { item: Top10Row }) => drill('top_expenses', String(item.vehicle_id))"
              >
                <template #item.total_cost="{ item }">
                  {{ fmtCurrency(item.total_cost) }}
                </template>
                <template #item.fuel_cost="{ item }">
                  {{ fmtCurrency(item.fuel_cost) }}
                </template>
                <template #item.repair_cost="{ item }">
                  {{ fmtCurrency(item.repair_cost) }}
                </template>
                <template #item.brand_model="{ item }">
                  <span class="font-weight-medium">{{ item.brand_model }}</span>
                  <v-chip size="x-small" variant="tonal" class="ml-1">{{ item.plate }}</v-chip>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </div>
      </GridItem>
    </GridLayout>

    <!-- ── Drill-down dialog ── -->
    <VehicleDrillDialog
      v-model="drillOpen"
      :dimension="drillDimension"
      :value="drillValue"
      :date-from="getDateRange().from"
      :date-to="getDateRange().to"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { useVehicleDashboardLayout } from '@/composables/useVehicleDashboardLayout'
import FuelCanisterWidget from '@/components/vehicles/FuelCanisterWidget.vue'
import VehiclesInRepairWidget from '@/components/vehicles/VehiclesInRepairWidget.vue'
import MaintenanceWarningWidget from '@/components/vehicles/MaintenanceWarningWidget.vue'
import VehicleKpiCard from '@/components/vehicles/VehicleKpiCard.vue'
import VehicleDrillDialog from '@/components/vehicles/VehicleDrillDialog.vue'
import { apiFetch } from '@/api'

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const isDark = computed(() => theme.global.name.value === 'dark')

// ── Dark-aware chart colors ──────────────────────────────────────────────────
const chartText = computed(() => isDark.value ? '#CBD5E1' : '#374151')
const chartMuted = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
const chartGrid = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : '#E2E8F0')

// ── Layout ───────────────────────────────────────────────────────────────────
const { layout, isEditing, toggleEditing, resetLayout, onLayoutUpdated, getLayoutItem } = useVehicleDashboardLayout()

// ── Drill-down dialog ────────────────────────────────────────────────────────
const drillOpen = ref(false)
const drillDimension = ref('')
const drillValue = ref('')

function drill(dimension: string, value: string) {
  drillDimension.value = dimension
  drillValue.value = value
  drillOpen.value = true
}

// ── Period ───────────────────────────────────────────────────────────────────
const PERIOD_PRESETS = [
  { value: 'day',   label: 'День' },
  { value: 'week',  label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'year',  label: 'Год' },
  { value: 'custom', label: 'Период' },
] as const

type PeriodPreset = typeof PERIOD_PRESETS[number]['value']

const periodPreset = ref<PeriodPreset>('month')
const customFrom = ref<string>('')
const customTo = ref<string>('')

function getTodayISO() {
  return new Date().toISOString().slice(0, 10)
}

function getDateRange(): { from: string; to: string } {
  const today = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  if (periodPreset.value === 'custom') {
    return { from: customFrom.value || iso(today), to: customTo.value || iso(today) }
  }
  if (periodPreset.value === 'day') {
    return { from: iso(today), to: iso(today) }
  }
  if (periodPreset.value === 'week') {
    const from = new Date(today)
    from.setDate(today.getDate() - 6)
    return { from: iso(from), to: iso(today) }
  }
  if (periodPreset.value === 'year') {
    return { from: `${today.getFullYear()}-01-01`, to: `${today.getFullYear()}-12-31` }
  }
  // month
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
  const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  return { from: iso(firstDay), to: iso(lastDay) }
}

const periodLabel = computed(() => {
  const { from, to } = getDateRange()
  return `${from} — ${to}`
})

function onCustomRangeApply() {
  fetchAll()
}

// ── Filters ──────────────────────────────────────────────────────────────────
const selectedOrgIds = ref<number[]>([])

interface OrgOption { id: number; name: string }
const orgOptions = ref<OrgOption[]>([])

async function loadOrgOptions() {
  try {
    const data = await apiFetch<OrgOption[]>('/organizations/?limit=500')
    orgOptions.value = Array.isArray(data) ? data : []
  } catch {
    // non-critical
  }
}

function buildQS(extra: Record<string, string> = {}): string {
  const { from, to } = getDateRange()
  const params = new URLSearchParams({
    date_from: from,
    date_to: to,
    ...extra,
  })
  if (selectedOrgIds.value.length > 0) {
    params.set('owner_org_ids', selectedOrgIds.value.join(','))
  }
  return '?' + params.toString()
}

// ── KPI ──────────────────────────────────────────────────────────────────────
interface KpiData {
  total_vehicles: number
  fuel_total_cost: number
  repairs_total_cost: number
  total_mileage_km: number
}

const kpi = ref<KpiData>({
  total_vehicles: 0,
  fuel_total_cost: 0,
  repairs_total_cost: 0,
  total_mileage_km: 0,
})
const loadingKpi = ref(false)

async function fetchKpi() {
  loadingKpi.value = true
  try {
    const data = await apiFetch<KpiData>('/vehicles-dashboard/kpi' + buildQS())
    kpi.value = data
  } catch (e: unknown) {
    console.error('[VehicleDashboard] KPI fetch error', e)
  } finally {
    loadingKpi.value = false
  }
}

// ── Canister ─────────────────────────────────────────────────────────────────
interface CanisterData {
  spent_l: number
  spent_amount: number
  fuel_budget: number
  level: number
  period_label: string
}

const canister = ref<CanisterData>({
  spent_l: 0,
  spent_amount: 0,
  fuel_budget: 0,
  level: 0.5,
  period_label: '—',
})
const loadingCanister = ref(false)

async function fetchCanister() {
  loadingCanister.value = true
  try {
    const data = await apiFetch<CanisterData>('/vehicles-dashboard/fuel-canister' + buildQS())
    canister.value = data
  } catch (e: unknown) {
    console.error('[VehicleDashboard] canister fetch error', e)
  } finally {
    loadingCanister.value = false
  }
}

// ── By-Org Bar ────────────────────────────────────────────────────────────────
interface ByOrgRow { org_id: number; org_name: string; count: number }
const barOrgMode = ref<'owner' | 'assigned'>('owner')
const byOrgData = ref<ByOrgRow[]>([])
const loadingByOrg = ref(false)
const byOrgError = ref<string | null>(null)

async function fetchByOrg() {
  loadingByOrg.value = true
  byOrgError.value = null
  try {
    const data = await apiFetch<ByOrgRow[]>(`/vehicles-dashboard/by-org?mode=${barOrgMode.value}`)
    byOrgData.value = data
  } catch (e: unknown) {
    byOrgError.value = e instanceof Error ? e.message : `Ошибка загрузки`
  } finally {
    loadingByOrg.value = false
  }
}

const barOrgSeries = computed(() => [{
  name: 'Машин',
  data: byOrgData.value.map(r => r.count),
}])

const barOrgOptions = computed(() => ({
  chart: {
    type: 'bar',
    background: 'transparent',
    toolbar: { show: false },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_event: unknown, _ctx: unknown, opts: { dataPointIndex: number }) => {
        const label = byOrgData.value[opts.dataPointIndex]?.org_name
        if (label) drill('bar_org', label)
      },
    },
  },
  plotOptions: { bar: { borderRadius: 4, horizontal: false } },
  xaxis: {
    categories: byOrgData.value.map(r => r.org_name),
    labels: {
      style: { colors: chartText.value, fontSize: '11px' },
      rotate: -30,
      hideOverlappingLabels: true,
    },
  },
  yaxis: { labels: { style: { colors: chartMuted.value } } },
  grid: { borderColor: chartGrid.value },
  colors: ['#3B82F6'],
  tooltip: { theme: isDark.value ? 'dark' : 'light' },
  dataLabels: { enabled: false },
  states: { active: { filter: { type: 'darken', value: 0.8 } } },
}))

watch(barOrgMode, fetchByOrg)

// ── State Donut ───────────────────────────────────────────────────────────────
interface DonutRow { state: string; label: string; count: number; color: string }
const donutData = ref<DonutRow[]>([])
const loadingDonut = ref(false)
const donutError = ref<string | null>(null)

async function fetchDonut() {
  loadingDonut.value = true
  donutError.value = null
  try {
    const data = await apiFetch<DonutRow[]>('/vehicles-dashboard/state-donut')
    donutData.value = data
  } catch (e: unknown) {
    donutError.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loadingDonut.value = false
  }
}

const donutSeries = computed(() => donutData.value.map(r => r.count))
const donutOptions = computed(() => ({
  chart: {
    type: 'donut',
    background: 'transparent',
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_event: unknown, _ctx: unknown, opts: { dataPointIndex: number }) => {
        const label = donutData.value[opts.dataPointIndex]?.label
        if (label) drill('donut_state', label)
      },
    },
  },
  labels: donutData.value.map(r => r.label),
  colors: donutData.value.map(r => r.color),
  legend: { position: 'bottom', fontSize: '11px', labels: { colors: chartText.value } },
  dataLabels: { enabled: true, style: { fontSize: '11px' } },
  tooltip: { theme: isDark.value ? 'dark' : 'light' },
}))

// ── Line: Fuel by period ──────────────────────────────────────────────────────
interface FuelLineRow { period: string; total_liters: number; total_amount: number }
const lineData = ref<FuelLineRow[]>([])
const loadingLine = ref(false)
const lineError = ref<string | null>(null)

function granularityFromPreset(): string {
  if (periodPreset.value === 'day') return 'day'
  if (periodPreset.value === 'week') return 'day'
  if (periodPreset.value === 'month') return 'day'
  if (periodPreset.value === 'year') return 'month'
  return 'day'
}

async function fetchLine() {
  loadingLine.value = true
  lineError.value = null
  try {
    const { from, to } = getDateRange()
    const gran = granularityFromPreset()
    const data = await apiFetch<FuelLineRow[]>(
      `/vehicles-dashboard/fuel-by-period?granularity=${gran}&date_from=${from}&date_to=${to}`
    )
    lineData.value = data
  } catch (e: unknown) {
    lineError.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loadingLine.value = false
  }
}

const lineSeries = computed(() => [{
  name: 'Сумма (₽)',
  data: lineData.value.map(r => r.total_amount),
}])

const lineOptions = computed(() => ({
  chart: {
    type: 'line',
    background: 'transparent',
    toolbar: { show: false },
    theme: { mode: isDark.value ? 'dark' : 'light' },
    events: {
      dataPointSelection: (_event: unknown, _ctx: unknown, opts: { dataPointIndex: number }) => {
        const label = lineData.value[opts.dataPointIndex]?.period
        if (label) drill('line_fuel', label)
      },
    },
  },
  stroke: { curve: 'smooth', width: 2 },
  xaxis: {
    categories: lineData.value.map(r => r.period),
    labels: { style: { colors: chartText.value, fontSize: '10px' }, rotate: -30 },
  },
  yaxis: { labels: { style: { colors: chartMuted.value } } },
  grid: { borderColor: chartGrid.value },
  colors: ['#F97316'],
  tooltip: {
    theme: isDark.value ? 'dark' : 'light',
    y: { formatter: (v: number) => fmtCurrency(v) },
  },
  dataLabels: { enabled: false },
  markers: { size: 3 },
}))

// ── TOP-10 ────────────────────────────────────────────────────────────────────
interface Top10Row {
  vehicle_id: number
  plate: string
  brand_model: string
  fuel_cost: number
  repair_cost: number
  total_cost: number
}

const top10 = ref<Top10Row[]>([])
const loadingTop10 = ref(false)
const top10Error = ref<string | null>(null)

const top10Headers = [
  { title: '#', key: 'index', width: 40 },
  { title: 'Машина', key: 'brand_model' },
  { title: 'Топливо', key: 'fuel_cost', align: 'end' as const },
  { title: 'Ремонты', key: 'repair_cost', align: 'end' as const },
  { title: 'Итого', key: 'total_cost', align: 'end' as const },
]

async function fetchTop10() {
  loadingTop10.value = true
  top10Error.value = null
  try {
    const { from, to } = getDateRange()
    const data = await apiFetch<Top10Row[]>(
      `/vehicles-dashboard/top-expenses?limit=10&date_from=${from}&date_to=${to}`
    )
    top10.value = data
  } catch (e: unknown) {
    top10Error.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loadingTop10.value = false
  }
}

// ── All vehicles summary table ────────────────────────────────────────────────
interface AllVehicleRow {
  vehicle_id: number
  plate: string
  brand_model: string
  state: string
  owner_org_name: string
  fuel_cost: number
  repair_cost: number
  mileage_km: number
  insurance_overdue: boolean
  insurance_until: string | null
}

const allVehicles = ref<AllVehicleRow[]>([])
const loadingAll = ref(false)
const allVehiclesError = ref<string | null>(null)
const allVehiclesSearch = ref('')

const allVehiclesHeaders = [
  { title: 'Гос.№', key: 'plate', width: 110 },
  { title: 'Марка/Модель', key: 'brand_model' },
  { title: 'Состояние', key: 'state', width: 140 },
  { title: 'Владелец', key: 'owner_org_name' },
  { title: 'Бензин ₽', key: 'fuel_cost', align: 'end' as const, width: 110 },
  { title: 'Ремонты ₽', key: 'repair_cost', align: 'end' as const, width: 110 },
  { title: 'Пробег км', key: 'mileage_km', align: 'end' as const, width: 100 },
  { title: 'ОСАГО', key: 'insurance_until', width: 130 },
]

const ALL_VEH_STATE_LABELS: Record<string, string> = {
  working: 'Работает', broken: 'Сломан', in_repair: 'В ремонте',
  needs_repair: 'Треб. ремонта', destroyed: 'Уничтожен', utilized: 'Утилизирован',
}
const ALL_VEH_STATE_COLORS: Record<string, string> = {
  working: 'success', broken: 'error', in_repair: 'warning',
  needs_repair: 'orange', destroyed: 'grey', utilized: 'purple',
}

async function fetchAllVehicles() {
  loadingAll.value = true
  allVehiclesError.value = null
  try {
    const data = await apiFetch<AllVehicleRow[]>('/vehicles-dashboard/all-vehicles-summary' + buildQS())
    allVehicles.value = data
  } catch (e: unknown) {
    allVehiclesError.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loadingAll.value = false
  }
}

// ── Aggregate loading state ───────────────────────────────────────────────────
const anyLoading = computed(() =>
  loadingKpi.value || loadingCanister.value || loadingByOrg.value ||
  loadingDonut.value || loadingLine.value || loadingTop10.value || loadingAll.value
)

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtCurrency(v: number): string {
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

// ── Fetch all ────────────────────────────────────────────────────────────────
function fetchAll() {
  fetchKpi()
  fetchCanister()
  fetchByOrg()
  fetchDonut()
  fetchLine()
  fetchTop10()
  fetchAllVehicles()
}

// ── Debounced watch on filters ────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null

watch([periodPreset, selectedOrgIds], () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchAll, 300)
}, { deep: true })

onMounted(() => {
  loadOrgOptions()
  fetchAll()
})
</script>

<style scoped>
.veh-dashboard {
  padding: 16px;
  min-height: 100vh;
}

.veh-dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.veh-dash-header-left {
  display: flex;
  align-items: center;
}

.veh-dash-header-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0;
}

.veh-dash-title {
  font-size: 1.4rem;
  font-weight: 700;
  line-height: 1.2;
}

.gradient-text {
  background: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.veh-dash-subtitle {
  margin-top: 2px;
}

.period-chips {
  flex-wrap: nowrap;
}

.edit-mode-banner {
  background: linear-gradient(90deg, #F59E0B, #D97706);
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 12px;
}

/* Grid widget wrapper */
.grid-widget {
  width: 100%;
  height: 100%;
  position: relative;
  border-radius: 10px;
  overflow: hidden;
}

.grid-widget--editing {
  outline: 2px dashed rgba(245, 158, 11, 0.5);
  outline-offset: -2px;
}

.widget-drag-handle {
  position: absolute;
  top: 4px;
  right: 6px;
  z-index: 10;
  background: rgba(245, 158, 11, 0.85);
  color: white;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 3px;
  cursor: grab;
  pointer-events: none;
}

.top10-table :deep(th),
.all-vehicles-table :deep(th) {
  font-size: 12px !important;
}

.top10-table :deep(td),
.all-vehicles-table :deep(td) {
  font-size: 12px !important;
}

.clickable-rows :deep(tr) {
  cursor: pointer;
}

.clickable-rows :deep(tr:hover td) {
  background: rgba(59, 130, 246, 0.06);
}

:deep(.vgl-item) {
  touch-action: none;
}

:deep(.apexcharts-canvas) {
  background: transparent !important;
}
</style>
