---
phase: 14-risk-radar-dashboard-neon-telemetry
plan: "01"
subsystem: frontend/composables + frontend/router + frontend/views
tags: [risk-radar, composables, router, typescript, localStorage]
dependency_graph:
  requires: []
  provides:
    - "Route /dashboard/radar (name: radar-dashboard, lazy-load)"
    - "useDashboardMode composable (DashboardMode type, mode/setMode/syncRouteWithMode)"
    - "useRiskScores composable (RiskScore/RiskSeverity types, 6-metric scoring, weighted overall)"
    - "RiskRadarView.vue stub (build placeholder for Plan 14-03)"
  affects:
    - "frontend/src/router/index.ts — one route added"
    - "Plans 14-02 and 14-03 — consume composable contracts defined here"
tech_stack:
  added: []
  patterns:
    - "Vue 3 composable with reactive refs + computed"
    - "localStorage per-user key pattern (dashboard-mode-{userId})"
    - "Promise.all with .catch(()=>[]) for tolerant multi-fetch"
    - "Client-side risk metric computation from existing API endpoints"
key_files:
  created:
    - frontend/src/composables/useDashboardMode.ts
    - frontend/src/composables/useRiskScores.ts
    - frontend/src/views/RiskRadarView.vue
  modified:
    - frontend/src/router/index.ts
decisions:
  - "Stub RiskRadarView.vue created (not planned) to unblock vite-plugin-pwa build resolution"
  - "apiFetch paths use '/dashboard/charts', '/contracts', '/wishes', '/purchases' (no /api prefix per api.ts convention)"
metrics:
  duration_seconds: 309
  completed_date: "2026-04-19"
  tasks_completed: 3
  files_modified: 4
---

# Phase 14 Plan 01: Infrastructure — Route + Composables Summary

JWT-auth router + per-user localStorage mode persistence + 6-metric client-side risk scoring composables with weighted overall score.

## Objective Achieved

Delivered the Phase 14 foundation: two composables and the router route that Plans 14-02 (components) and 14-03 (view assembly) depend on. No view code — contracts and wiring only.

## Exports Reference (for Plans 14-02 and 14-03)

### frontend/src/composables/useDashboardMode.ts

```typescript
export type DashboardMode = 'classic' | 'radar'

export interface UseDashboardModeReturn {
  mode: Ref<DashboardMode>
  setMode: (m: DashboardMode) => void
  syncRouteWithMode: () => void
}

export function useDashboardMode(): UseDashboardModeReturn
```

- localStorage key: `dashboard-mode-{userId}` where userId = `localStorage.getItem('user_id')`
- Fallback when user_id absent: `dashboard-mode-default`
- `setMode('radar')` → navigates to `/dashboard/radar`
- `setMode('classic')` → navigates to `/dashboard`
- `syncRouteWithMode()` — call from onMounted; only redirects when user is on `/dashboard` or `/dashboard/radar`

### frontend/src/composables/useRiskScores.ts

```typescript
export type RiskSeverity = 'ok' | 'warn' | 'high' | 'critical'
export type RiskMetricKey = 'budget_overrun' | 'contract_delays' | 'stalled_wishes' | 'framework_saturation' | 'feo_imbalance' | 'overdue_payments'

export interface RiskScore {
  key: RiskMetricKey
  label: string        // Russian label from META dict
  icon: string         // mdi-* icon from META dict
  score: number        // 0..100
  severity: RiskSeverity
  affectedCount: number
  description: string
}

export interface UseRiskScoresOptions {
  year: Ref<number | null>
  subsidyIds: Ref<number[]>
}

export interface UseRiskScoresReturn {
  scores: ComputedRef<RiskScore[]>       // always 6 entries, stable order
  overallScore: ComputedRef<number>
  overallSeverity: ComputedRef<RiskSeverity>
  loading: Ref<boolean>
  error: Ref<string | null>
  lastRefreshedAt: Ref<Date | null>
  refresh: () => Promise<void>
}

export function useRiskScores(opts: UseRiskScoresOptions): UseRiskScoresReturn
export function severityFromScore(score: number): RiskSeverity
```

**Severity thresholds:**
- `score >= 80` → `'critical'`
- `score >= 65` → `'high'`
- `score >= 40` → `'warn'`
- `score < 40` → `'ok'`

**Weights:**
- budget_overrun: 0.25
- contract_delays: 0.20
- stalled_wishes: 0.15
- framework_saturation: 0.20
- feo_imbalance: 0.10
- overdue_payments: 0.10

**API endpoints called (via apiFetch):**
- `/dashboard/charts` — required (hard fail if unavailable)
- `/contracts` — optional (.catch(()=>[]))
- `/wishes` — optional (.catch(()=>[]))
- `/purchases` — optional (.catch(()=>[]))

### frontend/src/router/index.ts (added route)

```typescript
{
  path: '/dashboard/radar',
  name: 'radar-dashboard',
  component: () => import('../views/RiskRadarView.vue'),
  meta: { requiresAuth: false, title: 'Risk Radar' }
}
```

- Employees blocked — path not in EMPLOYEE_ALLOWED, existing guard redirects to /my-tasks
- Inserted after `/dashboard`, before `/subsidies`

## localStorage Key Confirmed

Format: `dashboard-mode-{userId}` → e.g. `dashboard-mode-42`
Fallback: `dashboard-mode-default` (when user_id not in localStorage)
Values: `'classic'` | `'radar'`
Default: `'classic'`

## Commits

| Hash | Message |
|------|---------|
| `3724019` | feat(14-01): register /dashboard/radar route (lazy-load, employee guard) |
| `59bea33` | feat(14-01): create useDashboardMode composable (localStorage mode persistence) |
| `5b7c238` | feat(14-01): create useRiskScores composable (6-metric client-side risk scoring) |
| `f18761a` | feat(14-01): add RiskRadarView.vue stub to unblock build |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] Created RiskRadarView.vue stub to unblock vite-plugin-pwa build**
- **Found during:** Plan-level build verification
- **Issue:** `vite-plugin-pwa` resolves all lazy-import paths at build time (unlike standard Vite which defers lazy imports). The missing `RiskRadarView.vue` caused a hard build failure: "Could not resolve '../views/RiskRadarView.vue'". The plan expected "one warning" but PWA plugin makes it a fatal error.
- **Fix:** Created minimal stub `frontend/src/views/RiskRadarView.vue` with just a placeholder template and comment indicating Plan 14-03 will replace it.
- **Files modified:** `frontend/src/views/RiskRadarView.vue` (created)
- **Commit:** `f18761a`
- **Impact:** Plan 14-03 must overwrite this file with the full RiskRadarView implementation (not extend it).

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| `frontend/src/views/RiskRadarView.vue` | Entire view is placeholder | Unblocks build; Plan 14-03 replaces with full implementation |

## Self-Check: PASSED

- [x] `frontend/src/composables/useDashboardMode.ts` exists — FOUND
- [x] `frontend/src/composables/useRiskScores.ts` exists — FOUND
- [x] `frontend/src/router/index.ts` contains `/dashboard/radar` — FOUND
- [x] `frontend/src/views/RiskRadarView.vue` exists (stub) — FOUND
- [x] Commit `3724019` exists — FOUND
- [x] Commit `59bea33` exists — FOUND
- [x] Commit `5b7c238` exists — FOUND
- [x] Commit `f18761a` exists — FOUND
- [x] `npx tsc --noEmit --skipLibCheck` exit code 0 — PASSED
- [x] `npm run build` succeeds — PASSED
- [x] `DashboardView.vue` unchanged (D-01) — CONFIRMED
