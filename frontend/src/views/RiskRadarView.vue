<template>
  <div class="risk-radar" :data-theme="isDark ? 'dark' : 'light'" role="main">

    <!-- ── Header ── -->
    <div class="rr-header">
      <div class="rr-header-left">
        <v-icon icon="mdi-radar" size="34" color="primary" class="mr-3" />
        <div>
          <div class="rr-title gradient-text">Risk Radar</div>
          <div class="rr-subtitle">GALA · Мониторинг рисков · {{ selectedYear }}</div>
        </div>
      </div>
      <div class="rr-header-right">
        <v-chip-group v-model="selectedYear" mandatory class="year-chips">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
        <v-select
          v-model="selectedSubsidyIds"
          :items="allSubsidies.filter(s => s.year === selectedYear)"
          item-title="name" item-value="id"
          label="Субсидии"
          variant="outlined" multiple chips clearable density="compact"
          style="min-width: 220px; max-width: 340px;"
          hide-details class="ml-3"
        />
        <v-btn
          icon="mdi-refresh" variant="tonal" color="primary"
          :loading="loading" @click="refresh" size="small" class="ml-3"
          title="Обновить данные" aria-label="Обновить данные Risk Radar"
        />
        <v-btn
          icon="mdi-information-outline" variant="tonal" color="primary"
          size="small" class="ml-3"
          title="Как считаются риски"
          @click="formulasDialogOpen = true"
        />
        <v-chip-group
          v-model="toggleMode"
          mandatory class="ml-3"
          selected-class="text-primary"
        >
          <v-chip value="classic" size="small" variant="outlined" prepend-icon="mdi-view-dashboard" style="min-height: 44px">
            Классик
          </v-chip>
          <v-chip value="radar" size="small" variant="outlined" prepend-icon="mdi-radar" style="min-height: 44px">
            Радар
          </v-chip>
        </v-chip-group>
      </div>
    </div>

    <!-- ── Quick subsidy chips (same pattern as DashboardView) ── -->
    <div v-if="yearSubsidies.length > 0" class="subsidy-chips-bar">
      <v-chip
        v-for="s in yearSubsidies" :key="s.id"
        :color="selectedSubsidyIds.includes(s.id) ? 'primary' : undefined"
        :variant="selectedSubsidyIds.includes(s.id) ? 'flat' : 'outlined'"
        size="small"
        class="subsidy-chip"
        @click="toggleSubsidyChip(s.id)"
      >{{ s.shortName || s.name }}</v-chip>
      <v-chip
        v-if="selectedSubsidyIds.length > 0"
        variant="text" size="small" class="subsidy-chip"
        prepend-icon="mdi-close-circle-outline"
        @click="selectedSubsidyIds = []"
      >Все</v-chip>
    </div>

    <!-- ── Body states ── -->
    <div v-if="error" class="rr-error">
      <v-alert type="error" variant="outlined" icon="mdi-alert-circle-outline" class="rr-alert">
        <div class="text-subtitle-1" style="font-weight:700">Не удалось загрузить данные</div>
        <div class="text-body-2">Проверьте соединение и попробуйте снова. Нажмите ⟳ для повторной загрузки.</div>
      </v-alert>
    </div>

    <div v-else-if="!loading && scores.length === 0" class="rr-empty">
      <div class="text-h6" style="font-weight:700">Нет данных для анализа рисков</div>
      <div class="text-body-2">Выберите субсидию и год, чтобы увидеть оценку рисков.</div>
    </div>

    <template v-else>
      <!-- ── Main grid: radar panel + metric cards ── -->
      <div class="rr-main-grid">

        <!-- Radar panel (left) -->
        <div class="rr-panel" :aria-label="chartAriaLabel">
          <div class="rr-panel__chart">
            <apexchart
              v-if="!loading"
              type="polarArea"
              height="280"
              :options="polarOptions"
              :series="polarSeries"
            />
            <v-progress-circular v-else indeterminate size="32" color="primary" />
          </div>

          <div class="rr-panel__gauge">
            <apexchart
              v-if="!loading"
              type="radialBar"
              height="140"
              :options="gaugeOptions"
              :series="gaugeSeries"
            />
          </div>

          <div class="rr-panel__meta">
            <span class="rr-panel__meta-label">Обновлено</span>
            <span class="rr-panel__meta-value">{{ refreshedAtText }}</span>
          </div>
        </div>

        <!-- Metric cards (right, 2×3 grid) -->
        <div class="rr-metric-grid">
          <template v-if="loading">
            <v-skeleton-loader v-for="n in 6" :key="'rr-skel-'+n" type="card" height="160" class="rounded-lg" />
          </template>
          <template v-else>
            <RiskMetricCard
              v-for="s in scores" :key="s.key"
              :score="s"
              @click="handleCardClick(s)"
            />
          </template>
        </div>
      </div>

      <!-- ── Alerts ticker ── -->
      <AlertsTicker
        :items="tickerItems"
        :visible="tickerVisible"
        @item-click="handleCardClick"
      />
    </template>

  </div>

  <!-- ── Formulas info dialog ── -->
  <v-dialog v-model="formulasDialogOpen" max-width="720">
    <v-card>
      <v-card-title class="text-h6 pa-4 pb-2">Как считаются риски</v-card-title>
      <v-card-text class="pa-4">
        <p class="text-body-2 mb-4">
          Все метрики — от 0 до 100. 0–39 — норма, 40–64 — внимание, 65–79 — высокий, 80–100 — критический. Общий риск — взвешенное среднее.
        </p>
        <div class="formulas-table-wrapper">
          <table class="formulas-table">
            <thead>
              <tr>
                <th>Метрика</th>
                <th>Источник данных</th>
                <th>Формула</th>
                <th>Вес</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Превышение бюджета</td>
                <td><code>/api/dashboard/charts</code> → subsidy_stats</td>
                <td>Σ max(0, total_planned − budget) / Σ budget × 100 (≤ 100)</td>
                <td>0.25</td>
              </tr>
              <tr>
                <td>Просрочки договоров</td>
                <td><code>/api/contracts</code></td>
                <td>count(status ≠ completed AND end_date ≤ сегодня + 14 дн) / всего × 100</td>
                <td>0.20</td>
              </tr>
              <tr>
                <td>Зависшие заявки</td>
                <td><code>/api/wishes</code></td>
                <td>count(status = approved AND возраст > 14 дн) / всего approved × 100</td>
                <td>0.15</td>
              </tr>
              <tr>
                <td>Насыщение рамочных</td>
                <td><code>/api/contracts</code> (framework)</td>
                <td>max(current_amount / max_amount × 100) — худший случай</td>
                <td>0.20</td>
              </tr>
              <tr>
                <td>Дисбаланс ФЭО</td>
                <td><code>/api/dashboard/charts</code> → subsidy_stats</td>
                <td>std_dev(утилизация%) / mean(утилизация%) × 100 — коэфф. вариации</td>
                <td>0.10</td>
              </tr>
              <tr>
                <td>Просрочки оплат</td>
                <td><code>/api/purchases</code></td>
                <td>count(status = contracted AND contract_date &lt; сегодня − 30 дн) / всего contracted × 100</td>
                <td>0.10</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="mt-4">
          <div class="text-subtitle-2 mb-2">Пороги уровней</div>
          <div class="thresholds-list">
            <span class="threshold-item threshold-ok">0–39: Норма</span>
            <span class="threshold-item threshold-warn">40–64: Внимание</span>
            <span class="threshold-item threshold-high">65–79: Высокий</span>
            <span class="threshold-item threshold-critical">80–100: Критический</span>
          </div>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="tonal" @click="formulasDialogOpen = false">Понятно</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '../api'
import { useRiskScores, type RiskScore } from '../composables/useRiskScores'
import { useDashboardMode } from '../composables/useDashboardMode'
import { useToast } from '../composables/useToast'
import RiskMetricCard from '../components/RiskMetricCard.vue'
import AlertsTicker from '../components/AlertsTicker.vue'

// ─── Theme (D-03, D-04) ────────────────────────────────────────────
const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)

// ─── Formulas dialog ───────────────────────────────────────────────
const formulasDialogOpen = ref(false)

// ─── Dashboard mode persistence (D-02) ─────────────────────────────
const { setMode, syncRouteWithMode } = useDashboardMode()
const toggleMode = ref<'classic' | 'radar'>('radar')
watch(toggleMode, (v) => {
  if (v === 'classic' || v === 'radar') setMode(v)
})

// ─── Router (for card drill-downs) ─────────────────────────────────
const router = useRouter()

// ─── Subsidy / year filter state (pattern copied from DashboardView) ─
interface SubsidyRow {
  id: number
  name: string
  shortName?: string
  year: number
  budget: number
}
const selectedYear = ref<number>(new Date().getFullYear())
const selectedSubsidyIds = ref<number[]>([])
const allSubsidies = ref<SubsidyRow[]>([])
const availableYears = computed(() =>
  [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
)
const yearSubsidies = computed<SubsidyRow[]>(() =>
  allSubsidies.value.filter(s => s.year === selectedYear.value)
)

function toggleSubsidyChip(id: number) {
  const idx = selectedSubsidyIds.value.indexOf(id)
  if (idx >= 0) selectedSubsidyIds.value = selectedSubsidyIds.value.filter(x => x !== id)
  else selectedSubsidyIds.value = [...selectedSubsidyIds.value, id]
}

// Reset subsidy selection when year changes.
watch(selectedYear, () => { selectedSubsidyIds.value = [] })

// ─── Risk scores composable ────────────────────────────────────────
const yearForScores = computed(() => selectedYear.value)
const { scores, overallScore, overallSeverity, loading, error, lastRefreshedAt, refresh } =
  useRiskScores({ year: yearForScores, subsidyIds: selectedSubsidyIds })

// ─── Critical-risk toast (fire once on initial load) ───────────────
const toast = useToast()
let hasShownCriticalToast = false
watch(() => loading.value, (val, prev) => {
  if (prev && !val && !hasShownCriticalToast) {
    const critical = scores.value.filter(s => s.severity === 'critical')
    if (critical.length > 0) {
      toast.error(
        `Обнаружены критические риски: ${critical.map(s => s.label).join(', ')}`,
        6000
      )
      hasShownCriticalToast = true
    }
  }
})

// ─── Load subsidies list (for filter dropdown) ─────────────────────
async function loadSubsidiesCatalog() {
  try {
    const charts = await apiFetch<any>('/dashboard/charts')
    allSubsidies.value = (charts?.subsidy_stats || []).map((s: any) => ({
      id: s.id,
      name: s.name,
      shortName: s.name?.length > 24 ? s.name.slice(0, 22) + '…' : s.name,
      year: s.year,
      budget: s.budget,
    }))
    // Auto-select most recent year if current is not present
    const years = [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a)
    if (years.length > 0 && !years.includes(selectedYear.value)) {
      selectedYear.value = years[0]
    }
  } catch {
    /* error surfaced via useRiskScores below */
  }
}

// ─── Drill-down navigation map ─────────────────────────────────────
function handleCardClick(s: RiskScore) {
  switch (s.key) {
    case 'budget_overrun':
    case 'feo_imbalance':
      // UI-SPEC: open BudgetDrillDownDialog; since that dialog requires parent-level state
      // and MVP allows pass-through nav, route to dashboard with a query that the dashboard
      // already understands — executor may upgrade to dialog in a follow-up phase.
      router.push('/dashboard?drill=' + s.key)
      break
    case 'contract_delays':
      router.push('/contracts?filter=expiring')
      break
    case 'stalled_wishes':
      router.push('/wishes?filter=stalled')
      break
    case 'framework_saturation':
      router.push('/contracts?filter=saturated')
      break
    case 'overdue_payments':
      router.push('/orders?filter=overdue_payment')
      break
  }
}

// ─── Alerts ticker items — derived from scores ≥ warn ──────────────
const tickerItems = computed<RiskScore[]>(() =>
  scores.value.filter(s => s.score >= 40)
)
const tickerVisible = computed(() => tickerItems.value.length > 0)

// ─── ApexCharts options (polar area + radial bar) ────────────────
const polarSeries = computed(() => scores.value.map(s => Math.round(s.score)))
const polarOptions = computed(() => ({
  chart: {
    type: 'polarArea' as const,
    background: 'transparent',
    animations: { easing: 'easeinout', speed: 600 },
    toolbar: { show: false },
  },
  labels: scores.value.map(s => {
    // Short labels for chart (UI-SPEC §Chart Specifications)
    const SHORT: Record<string, string> = {
      budget_overrun: 'Бюджет',
      contract_delays: 'Договоры',
      stalled_wishes: 'Заявки',
      framework_saturation: 'Рамочные',
      feo_imbalance: 'ФЭО',
      overdue_payments: 'Оплаты',
    }
    return SHORT[s.key] || s.label
  }),
  colors: scores.value.map(s => {
    // Resolve CSS var to real color for ApexCharts (it needs a concrete value at render time)
    // Use Tailwind palette hex per UI-SPEC §Color — dark/light variants.
    const DARK: Record<string, string> = {
      ok: '#22D3EE', warn: '#FBBF24', high: '#F97316', critical: '#F43F5E',
    }
    const LIGHT: Record<string, string> = {
      ok: '#0891B2', warn: '#B45309', high: '#C2410C', critical: '#BE123C',
    }
    return (isDark.value ? DARK : LIGHT)[s.severity]
  }),
  stroke: { colors: [isDark.value ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'], width: 1 },
  fill: { opacity: isDark.value ? 0.7 : 0.6 },
  yaxis: { max: 100, show: false },
  legend: { show: false },
  plotOptions: {
    polarArea: {
      rings: { strokeWidth: 1 },
      spokes: { strokeWidth: 1 },
    },
  },
  theme: { mode: isDark.value ? 'dark' : 'light' as 'dark' | 'light' },
  tooltip: {
    y: {
      formatter: (val: number, opts: any) => {
        const label = opts?.w?.globals?.labels?.[opts.seriesIndex] ?? ''
        return `${label}: ${Math.round(val)}/100`
      },
    },
  },
}))

const gaugeSeries = computed(() => [overallScore.value])
const gaugeOptions = computed(() => {
  const DARK: Record<string, string> = { ok: '#22D3EE', warn: '#FBBF24', high: '#F97316', critical: '#F43F5E' }
  const LIGHT: Record<string, string> = { ok: '#0891B2', warn: '#B45309', high: '#C2410C', critical: '#BE123C' }
  const color = (isDark.value ? DARK : LIGHT)[overallSeverity.value]
  return {
    chart: { type: 'radialBar' as const, background: 'transparent', toolbar: { show: false } },
    plotOptions: {
      radialBar: {
        hollow: { size: '60%' },
        dataLabels: {
          name: { offsetY: -4, fontSize: '12px', fontWeight: 400 },
          value: { fontSize: '20px', fontWeight: 700 },
        },
      },
    },
    labels: ['Общий риск'],
    colors: [color],
    theme: { mode: isDark.value ? 'dark' : 'light' as 'dark' | 'light' },
  }
})

// Formatted refreshed timestamp
const refreshedAtText = computed(() =>
  lastRefreshedAt.value ? lastRefreshedAt.value.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '—'
)

// Chart aria-label (UI-SPEC §Accessibility → Keyboard Navigation)
const chartAriaLabel = computed(() => {
  if (!scores.value.length) return 'Радар рисков'
  const top = [...scores.value].sort((a, b) => b.score - a.score)[0]
  return `Радар рисков. 6 метрик. Наивысший: ${top.label} ${top.score}/100`
})

// ─── Lifecycle ─────────────────────────────────────────────────────
onMounted(async () => {
  // D-02: record that radar is the active mode for this user
  setMode('radar')
  syncRouteWithMode()
  await loadSubsidiesCatalog()
  await refresh()
})

// Expose for potential parent inspection
defineExpose({ scores, overallScore, overallSeverity, lastRefreshedAt })
</script>

<style scoped>
/* ───── Design tokens (D-03, D-04: both themes first-class) ───── */
.risk-radar {
  /* Defaults = dark values (page usually opens dark per project default). */
  --rr-ok: #22D3EE;
  --rr-warn: #FBBF24;
  --rr-high: #F97316;
  --rr-critical: #F43F5E;
  --rr-glow-ok: rgba(34, 211, 238, 0.25);
  --rr-glow-warn: rgba(251, 191, 36, 0.25);
  --rr-glow-high: rgba(249, 115, 22, 0.30);
  --rr-glow-critical: rgba(244, 63, 94, 0.35);
  --rr-panel-bg: rgba(30, 41, 59, 0.85);

  padding: 20px 24px;
  max-width: 1600px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
}

/* Light theme override (D-04: muted palette, not neon glow) */
.risk-radar[data-theme="light"] {
  --rr-ok: #0891B2;
  --rr-warn: #B45309;
  --rr-high: #C2410C;
  --rr-critical: #BE123C;
  --rr-glow-ok: rgba(8, 145, 178, 0.12);
  --rr-glow-warn: rgba(180, 83, 9, 0.12);
  --rr-glow-high: rgba(194, 65, 12, 0.12);
  --rr-glow-critical: rgba(190, 18, 60, 0.15);
  --rr-panel-bg: rgba(248, 250, 252, 0.92);
}

/* ───── Header ───── */
.rr-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.rr-header-left {
  display: flex;
  align-items: center;
}
.rr-header-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.rr-title {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
}
.rr-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: var(--crm-text-muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* ───── Subsidy chips bar (reuses class names from DashboardView for consistent look) ───── */
.subsidy-chips-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 0;
}

/* ───── Main grid ───── */
.rr-main-grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  align-items: start;
}

/* ───── Radar panel ───── */
.rr-panel {
  background: var(--rr-panel-bg);
  border: 1px solid var(--crm-border);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  backdrop-filter: blur(8px);
}
.rr-panel__chart {
  width: 280px;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rr-panel__gauge {
  width: 100%;
  display: flex;
  justify-content: center;
}
.rr-panel__meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--crm-text-muted);
}
.rr-panel__meta-label {
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* ───── Metric grid ───── */
.rr-metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

/* ───── Breakpoints (UI-SPEC §Responsive Breakpoints) ───── */
@media (max-width: 1279.98px) {
  .rr-main-grid { grid-template-columns: 300px 1fr; }
  .rr-metric-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 959.98px) {
  .rr-main-grid { grid-template-columns: 1fr; }
  .rr-metric-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 767.98px) {
  .rr-panel__chart { width: 240px; height: 240px; }
  .rr-metric-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 479.98px) {
  .rr-panel__chart { display: none; }
  .rr-metric-grid { grid-template-columns: 1fr; }
}

/* ───── State containers ───── */
.rr-error, .rr-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 8px;
  text-align: center;
}

/* ───── gradient-text reuses DashboardView animation — redeclare local copy to avoid global coupling ───── */
.gradient-text {
  background: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 50%, #22D3EE 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: rr-gradient-shift 8s ease infinite;
}
@keyframes rr-gradient-shift {
  0%,100% { background-position: 0% 50%; }
  50%     { background-position: 100% 50%; }
}

/* ───── Formulas dialog ───── */
.formulas-table-wrapper {
  overflow-x: auto;
}
.formulas-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.formulas-table th,
.formulas-table td {
  padding: 8px 10px;
  border: 1px solid rgba(128, 128, 128, 0.2);
  text-align: left;
  vertical-align: top;
  line-height: 1.4;
}
.formulas-table th {
  font-weight: 600;
  background: rgba(128, 128, 128, 0.08);
}
.formulas-table code {
  font-size: 11px;
  background: rgba(128, 128, 128, 0.12);
  padding: 1px 4px;
  border-radius: 3px;
}
.thresholds-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.threshold-item {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}
.threshold-ok       { background: rgba(8, 145, 178, 0.15); color: #0891B2; }
.threshold-warn     { background: rgba(180, 83, 9, 0.15);  color: #B45309; }
.threshold-high     { background: rgba(194, 65, 12, 0.15); color: #C2410C; }
.threshold-critical { background: rgba(190, 18, 60, 0.15); color: #BE123C; }
</style>
