import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { apiFetch } from '../api'

// ─── Public types ───────────────────────────────────────────────────

export type RiskSeverity = 'ok' | 'warn' | 'high' | 'critical'

export type RiskMetricKey =
  | 'budget_overrun'
  | 'contract_delays'
  | 'stalled_wishes'
  | 'framework_saturation'
  | 'feo_imbalance'
  | 'overdue_payments'

export interface RiskScore {
  key: RiskMetricKey
  label: string       // Russian label, per UI-SPEC Copywriting
  icon: string        // mdi-* icon name, per UI-SPEC Risk Metrics table
  score: number       // 0..100, rounded integer
  severity: RiskSeverity
  affectedCount: number   // "N элементов требуют внимания" — raw count driving the score
  description: string     // short human-readable description for tooltip/ticker
}

export interface UseRiskScoresOptions {
  /** Year filter, e.g. 2026. Omit or null = all years. */
  year: Ref<number | null>
  /** Subsidy ID filter; empty array = all subsidies. */
  subsidyIds: Ref<number[]>
}

export interface UseRiskScoresReturn {
  scores: ComputedRef<RiskScore[]>        // always 6 entries, stable order matching RiskMetricKey union
  overallScore: ComputedRef<number>       // 0..100 weighted
  overallSeverity: ComputedRef<RiskSeverity>
  loading: Ref<boolean>
  error: Ref<string | null>
  lastRefreshedAt: Ref<Date | null>
  refresh: () => Promise<void>
}

// ─── Severity helper (exported for components) ──────────────────────

export function severityFromScore(score: number): RiskSeverity {
  if (score >= 80) return 'critical'
  if (score >= 65) return 'high'
  if (score >= 40) return 'warn'
  return 'ok'
}

// ─── Weights per UI-SPEC §Overall Risk Score ───────────────────────
const WEIGHTS: Record<RiskMetricKey, number> = {
  budget_overrun: 0.25,
  contract_delays: 0.20,
  stalled_wishes: 0.15,
  framework_saturation: 0.20,
  feo_imbalance: 0.10,
  overdue_payments: 0.10,
}

// ─── Labels and icons per UI-SPEC ───────────────────────────────────
const META: Record<RiskMetricKey, { label: string; icon: string }> = {
  budget_overrun:       { label: 'Превышение бюджета',  icon: 'mdi-cash-remove' },
  contract_delays:      { label: 'Просрочки договоров', icon: 'mdi-file-clock' },
  stalled_wishes:       { label: 'Зависшие заявки',     icon: 'mdi-star-remove' },
  framework_saturation: { label: 'Насыщение рамочных',  icon: 'mdi-chart-bell-curve' },
  feo_imbalance:        { label: 'Дисбаланс ФЭО',        icon: 'mdi-scale-unbalanced' },
  overdue_payments:     { label: 'Просрочки оплат',     icon: 'mdi-credit-card-remove' },
}

const ORDERED_KEYS: RiskMetricKey[] = [
  'budget_overrun', 'contract_delays', 'stalled_wishes',
  'framework_saturation', 'feo_imbalance', 'overdue_payments'
]

// ─── Raw response types ─────────────────────────────────────────────

interface SubsidyStat {
  id: number
  name: string
  year: number
  budget: number
  total_planned: number
  total_confirmed: number
  feo_budget_total: number
}
interface ChartsResponse {
  status_counts: Record<string, number>
  subsidy_stats: SubsidyStat[]
}
interface ContractRow {
  id: number
  end_date?: string | null
  status?: string | null
  contract_type?: string | null
  max_amount?: number | null
  current_amount?: number | null
}
interface WishRow {
  id: number
  status: string
  created_at: string
  approved_at?: string | null
}
interface PurchaseRow {
  id: number
  status: string
  subsidy_id?: number | null
  contract_date?: string | null
}

// ─── Composable ─────────────────────────────────────────────────────

export function useRiskScores(opts: UseRiskScoresOptions): UseRiskScoresReturn {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastRefreshedAt = ref<Date | null>(null)

  const rawCharts = ref<ChartsResponse | null>(null)
  const rawContracts = ref<ContractRow[]>([])
  const rawWishes = ref<WishRow[]>([])
  const rawPurchases = ref<PurchaseRow[]>([])

  // ---- Metric formulas ----

  function budgetOverrun(subsidies: SubsidyStat[]): { score: number; count: number; desc: string } {
    if (!subsidies.length) return { score: 0, count: 0, desc: 'Нет субсидий' }
    const budgetTotal = subsidies.reduce((a, s) => a + (s.budget || 0), 0)
    if (budgetTotal <= 0) return { score: 0, count: 0, desc: 'Бюджет не задан' }
    let overrun = 0
    let count = 0
    for (const s of subsidies) {
      const diff = (s.total_planned || 0) - (s.budget || 0)
      if (diff > 0) { overrun += diff; count += 1 }
    }
    const score = Math.min(100, Math.round((overrun / budgetTotal) * 100))
    return { score, count, desc: `${count} субсидий с превышением` }
  }

  function contractDelays(contracts: ContractRow[]): { score: number; count: number; desc: string } {
    const total = contracts.length
    if (!total) return { score: 0, count: 0, desc: 'Нет договоров' }
    const now = Date.now()
    const horizon = now + 14 * 24 * 60 * 60 * 1000
    let count = 0
    for (const c of contracts) {
      if (c.status === 'completed') continue
      if (!c.end_date) continue
      const end = new Date(c.end_date).getTime()
      if (!Number.isFinite(end)) continue
      if (end < horizon) count += 1
    }
    const score = Math.min(100, Math.round((count / total) * 100))
    return { score, count, desc: `${count} договоров истекают ≤14 дней` }
  }

  function stalledWishes(wishes: WishRow[]): { score: number; count: number; desc: string } {
    const approved = wishes.filter(w => w.status === 'approved')
    if (!approved.length) return { score: 0, count: 0, desc: 'Нет одобренных заявок' }
    const now = Date.now()
    const threshold = 14 * 24 * 60 * 60 * 1000
    let stalled = 0
    for (const w of approved) {
      const anchor = w.approved_at || w.created_at
      const t = anchor ? new Date(anchor).getTime() : NaN
      if (Number.isFinite(t) && (now - t) > threshold) stalled += 1
    }
    const score = Math.min(100, Math.round((stalled / approved.length) * 100))
    return { score, count: stalled, desc: `${stalled} заявок старше 14 дней` }
  }

  function frameworkSaturation(contracts: ContractRow[]): { score: number; count: number; desc: string } {
    const framework = contracts.filter(c =>
      c.contract_type === 'framework_cumulative' || c.contract_type === 'framework_with_amount'
    )
    if (!framework.length) return { score: 0, count: 0, desc: 'Нет рамочных договоров' }
    let worst = 0
    let saturated = 0
    for (const c of framework) {
      const max = c.max_amount || 0
      const curr = c.current_amount || 0
      if (max <= 0) continue
      const pct = Math.min(100, (curr / max) * 100)
      if (pct > worst) worst = pct
      if (pct >= 80) saturated += 1
    }
    return {
      score: Math.round(worst),
      count: saturated,
      desc: `Макс. заполненность: ${Math.round(worst)}% · ${saturated} рамочных ≥80%`
    }
  }

  function feoImbalance(subsidies: SubsidyStat[]): { score: number; count: number; desc: string } {
    const withBudget = subsidies.filter(s => (s.budget || 0) > 0)
    if (withBudget.length < 2) return { score: 0, count: 0, desc: 'Недостаточно данных' }
    const utils = withBudget.map(s => ((s.total_confirmed || 0) / s.budget) * 100)
    const mean = utils.reduce((a, v) => a + v, 0) / utils.length
    if (mean <= 0) return { score: 0, count: 0, desc: 'Нулевая утилизация' }
    const variance = utils.reduce((a, v) => a + (v - mean) * (v - mean), 0) / utils.length
    const stdDev = Math.sqrt(variance)
    // Coefficient of variation as percent, capped at 100
    const cv = (stdDev / mean) * 100
    const score = Math.min(100, Math.round(cv))
    return { score, count: withBudget.length, desc: `CV утилизации: ${score}%` }
  }

  function overduePayments(purchases: PurchaseRow[]): { score: number; count: number; desc: string } {
    const contracted = purchases.filter(p => p.status === 'contracted')
    if (!contracted.length) return { score: 0, count: 0, desc: 'Нет законтрактованных' }
    const now = Date.now()
    const threshold = 30 * 24 * 60 * 60 * 1000
    let overdue = 0
    for (const p of contracted) {
      if (!p.contract_date) continue
      const t = new Date(p.contract_date).getTime()
      if (Number.isFinite(t) && (now - t) > threshold) overdue += 1
    }
    const score = Math.min(100, Math.round((overdue / contracted.length) * 100))
    return { score, count: overdue, desc: `${overdue} закупок без оплаты >30 дней` }
  }

  // ---- Fetch ----

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [charts, contracts, wishes, purchases] = await Promise.all([
        apiFetch<ChartsResponse>('/dashboard/charts'),
        apiFetch<ContractRow[]>('/contracts').catch(() => [] as ContractRow[]),
        apiFetch<WishRow[]>('/wishes').catch(() => [] as WishRow[]),
        apiFetch<PurchaseRow[]>('/purchases').catch(() => [] as PurchaseRow[]),
      ])
      rawCharts.value = charts
      rawContracts.value = Array.isArray(contracts) ? contracts : []
      rawWishes.value = Array.isArray(wishes) ? wishes : []
      rawPurchases.value = Array.isArray(purchases) ? purchases : []
      lastRefreshedAt.value = new Date()
    } catch (e: any) {
      error.value = e?.message || 'Не удалось загрузить данные'
    } finally {
      loading.value = false
    }
  }

  // ---- Derived (reactive filtering by year + subsidyIds) ----

  const filteredSubsidies = computed<SubsidyStat[]>(() => {
    const stats = rawCharts.value?.subsidy_stats || []
    const y = opts.year.value
    const ids = opts.subsidyIds.value
    return stats.filter(s => {
      if (y !== null && s.year !== y) return false
      if (ids.length > 0 && !ids.includes(s.id)) return false
      return true
    })
  })

  const filteredPurchases = computed<PurchaseRow[]>(() => {
    const ids = opts.subsidyIds.value
    if (ids.length === 0) return rawPurchases.value
    return rawPurchases.value.filter(p => p.subsidy_id != null && ids.includes(p.subsidy_id))
  })

  const scores = computed<RiskScore[]>(() => {
    const results: Record<RiskMetricKey, { score: number; count: number; desc: string }> = {
      budget_overrun: budgetOverrun(filteredSubsidies.value),
      contract_delays: contractDelays(rawContracts.value),
      stalled_wishes: stalledWishes(rawWishes.value),
      framework_saturation: frameworkSaturation(rawContracts.value),
      feo_imbalance: feoImbalance(filteredSubsidies.value),
      overdue_payments: overduePayments(filteredPurchases.value),
    }
    return ORDERED_KEYS.map(k => ({
      key: k,
      label: META[k].label,
      icon: META[k].icon,
      score: results[k].score,
      severity: severityFromScore(results[k].score),
      affectedCount: results[k].count,
      description: results[k].desc,
    }))
  })

  const overallScore = computed<number>(() => {
    const arr = scores.value
    if (!arr.length) return 0
    let total = 0
    for (const s of arr) total += s.score * WEIGHTS[s.key]
    return Math.round(total)
  })

  const overallSeverity = computed<RiskSeverity>(() => severityFromScore(overallScore.value))

  return {
    scores, overallScore, overallSeverity,
    loading, error, lastRefreshedAt, refresh,
  }
}
