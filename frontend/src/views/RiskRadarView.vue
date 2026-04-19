<template>
  <div class="risk-radar" :data-theme="isDark ? 'dark' : 'light'">
    <!-- Placeholder — Task 2 replaces this stub with the full layout -->
    <div v-if="loading" class="rr-loading">
      <v-progress-circular indeterminate size="32" />
    </div>
    <div v-else-if="error" class="rr-error">
      <v-alert type="error" variant="outlined" icon="mdi-alert-circle-outline">
        <div class="text-subtitle-1">Не удалось загрузить данные</div>
        <div class="text-body-2">Проверьте соединение и попробуйте снова. Нажмите ⟳ для повторной загрузки.</div>
      </v-alert>
    </div>
    <div v-else>
      <!-- Scores computed: {{ overallScore }} — rendering is wired in Task 2 -->
    </div>
  </div>
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

// ─── Lifecycle ─────────────────────────────────────────────────────
onMounted(async () => {
  // D-02: record that radar is the active mode for this user
  setMode('radar')
  syncRouteWithMode()
  await loadSubsidiesCatalog()
  await refresh()
})

// Expose for template (Task 2)
defineExpose({ scores, overallScore, overallSeverity, lastRefreshedAt })
</script>

<style scoped>
/* Token definitions land in Task 2. Minimal placeholder so file is renderable. */
.risk-radar {
  padding: 20px 24px;
  max-width: 1600px;
  margin: 0 auto;
}
.rr-loading, .rr-error {
  padding: 48px;
  display: flex;
  justify-content: center;
}
</style>
