---
phase: 14-risk-radar-dashboard-neon-telemetry
plan: "03"
subsystem: frontend/views
tags: [risk-radar, neon-telemetry, vue3, apexcharts, css-tokens, theming]
dependency_graph:
  requires:
    - "frontend/src/composables/useRiskScores.ts (Plan 14-01)"
    - "frontend/src/composables/useDashboardMode.ts (Plan 14-01)"
    - "frontend/src/components/RiskMetricCard.vue (Plan 14-02)"
    - "frontend/src/components/AlertsTicker.vue (Plan 14-02)"
  provides:
    - "RiskRadarView.vue — full Risk Radar dashboard page"
    - "--rr-* CSS tokens scoped to .risk-radar (both themes)"
    - "D-02 enforcement: onMounted setMode('radar') + syncRouteWithMode()"
  affects:
    - "Plan 14-04 (verifier/auditor): visual verification of the complete view"
tech_stack:
  added: []
  patterns:
    - "ApexCharts polarArea + radialBar with isDark-reactive color dictionaries"
    - "CSS custom property tokens under .risk-radar with [data-theme] override for light"
    - "Subsidy/year filter state copied verbatim from DashboardView (no shared composable per UI-SPEC §5)"
    - "hasShownCriticalToast flag to fire toast once on initial load only"
    - "Locally scoped gradient-text @keyframes to avoid DashboardView dependency"
key_files:
  created: []
  modified:
    - frontend/src/views/RiskRadarView.vue
decisions:
  - "Script and template scaffolded in Task 1 then replaced in Task 2 per plan — atomic commits for each task"
  - "severityFromScore not imported in view (unused — useRiskScores already exposes severity on each RiskScore object)"
  - "toggleMode ref kept separate from useDashboardMode's mode ref to avoid circular watch — toggleMode watch calls setMode() which navigates"
metrics:
  duration_seconds: 480
  completed_date: "2026-04-19"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 1
---

# Phase 14 Plan 03: RiskRadarView Assembly Summary

Full Risk Radar view assembled — 532-line SFC wires Plans 14-01 composables and 14-02 components into a complete Neon Telemetry dashboard page at `/dashboard/radar`.

## Objective Achieved

`frontend/src/views/RiskRadarView.vue` stub from Plan 14-01 replaced with the full implementation per UI-SPEC.md. The view renders:

- Header with gradient "Risk Radar" title, year chip group, subsidy multi-select, refresh button, and Classic/Radar toggle chip group
- Quick subsidy chips bar (identical CSS class pattern to DashboardView)
- Main 2-column grid: 340px radar panel (polarArea chart + radialBar gauge + timestamp) + 2×3 `RiskMetricCard` grid
- `AlertsTicker` strip (v-if hidden when no scores ≥ 40)
- Error and empty states with spec copywriting
- Theme-adaptive `--rr-*` CSS tokens (dark = neon, light = muted per D-04)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Scaffold RiskRadarView.vue — script, state, fetch wiring | 72adc56 | frontend/src/views/RiskRadarView.vue |
| 2 | Build template, charts, and theme-adaptive scoped CSS | 3379ba6 | frontend/src/views/RiskRadarView.vue |

## File Metrics

- **Lines:** 532 (within spec 450–550)
- **Sections:** `<template>` (116 lines), `<script setup lang="ts">` (248 lines), `<style scoped>` (168 lines)

## Acceptance Criteria Verification

### Task 1 (Script)

| Check | Result |
|-------|--------|
| `import { useRiskScores` | PASS |
| `import { useDashboardMode` | PASS |
| `import RiskMetricCard` | PASS |
| `import AlertsTicker` | PASS |
| `setMode('radar')` in onMounted | PASS |
| `syncRouteWithMode()` in onMounted | PASS |
| `useTheme()` from vuetify | PASS |
| `toast.error(` with "Обнаружены критические риски" | PASS |
| `router.push('/contracts?filter=expiring')` | PASS |
| `router.push('/wishes?filter=stalled')` | PASS |
| `router.push('/contracts?filter=saturated')` | PASS |
| `router.push('/orders?filter=overdue_payment')` | PASS |
| `router.push('/dashboard?drill=')` | PASS |
| filter refs: selectedYear, selectedSubsidyIds, allSubsidies, availableYears, yearSubsidies | PASS |
| `loadSubsidiesCatalog` calls `apiFetch<any>('/dashboard/charts')` | PASS |

### Task 2 (Template + Charts + CSS)

| Check | Result |
|-------|--------|
| Root `<div class="risk-radar" :data-theme="..." role="main">` | PASS |
| `<apexchart type="polarArea"` | PASS |
| `<apexchart type="radialBar"` | PASS |
| `<RiskMetricCard v-for="s in scores"` | PASS |
| `<AlertsTicker :items="tickerItems" :visible="tickerVisible"` | PASS |
| Toggle chips 'classic' and 'radar' | PASS |
| All 8 copywriting literals | PASS |
| Dark hex: #22D3EE, #FBBF24, #F97316, #F43F5E | PASS |
| Light hex: #0891B2, #B45309, #C2410C, #BE123C | PASS |
| `.risk-radar[data-theme="light"]` override block | PASS |
| Breakpoints 1279.98/959.98/767.98/479.98 | PASS |
| `theme: { mode: isDark.value` in chart options | PASS |
| Tooltip `Math.round(val)` + `/100` | PASS |
| `v-for="n in 6"` + `v-skeleton-loader` | PASS |
| `npm run build` exits 0 | PASS |
| `git diff DashboardView.vue` exits 0 (D-01) | PASS |

## Build Verification

```
✓ built in 26.44s
dist/assets/RiskRadarView-BY9RROo3.js    16.33 kB │ gzip:  6.34 kB
dist/assets/RiskRadarView-CZPoYGt7.css   7.56 kB  │ gzip:  1.93 kB
```

No errors. Chunk size warnings are pre-existing (main bundle already exceeded 500kB before Phase 14).

## D-01 Compliance (Critical)

`git diff --exit-code frontend/src/views/DashboardView.vue` → exit code 0.
DashboardView.vue byte-for-byte unchanged throughout Plan 14-03.

## CSS Token Coverage

All 8 `--rr-*` tokens defined in both themes:

| Token | Dark | Light |
|-------|------|-------|
| `--rr-ok` | `#22D3EE` | `#0891B2` |
| `--rr-warn` | `#FBBF24` | `#B45309` |
| `--rr-high` | `#F97316` | `#C2410C` |
| `--rr-critical` | `#F43F5E` | `#BE123C` |
| `--rr-glow-ok` | `rgba(34,211,238,0.25)` | `rgba(8,145,178,0.12)` |
| `--rr-glow-warn` | `rgba(251,191,36,0.25)` | `rgba(180,83,9,0.12)` |
| `--rr-glow-high` | `rgba(249,115,22,0.30)` | `rgba(194,65,12,0.12)` |
| `--rr-glow-critical` | `rgba(244,63,94,0.35)` | `rgba(190,18,60,0.15)` |
| `--rr-panel-bg` | `rgba(30,41,59,0.85)` | `rgba(248,250,252,0.92)` |

RiskMetricCard and AlertsTicker (both children) inherit these tokens from `.risk-radar` container — D-03 satisfied.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Removed unused `severityFromScore` import**
- **Found during:** Task 1 implementation
- **Issue:** Plan 14-03 template code included `import { useRiskScores, severityFromScore, type RiskScore }` but `severityFromScore` is never called in the view — severity is already computed on each `RiskScore` object by `useRiskScores`. Keeping the import would produce a TypeScript "imported but unused" lint warning.
- **Fix:** Removed `severityFromScore` from the import — kept only `{ useRiskScores, type RiskScore }`.
- **Files modified:** `frontend/src/views/RiskRadarView.vue`
- **Impact:** Zero — the composable still exports it for consumers that need it directly.

## Manual Test Instructions for Plan 14-04

To verify the complete view visually after deployment:

1. Navigate to `/dashboard/radar` — should render full layout (not the old stub chip "Coming in Plan 14-03")
2. Verify header: `mdi-radar` icon + gradient "Risk Radar" title + subtitle "ВСКС · Мониторинг рисков · {year}"
3. Verify 6 skeleton cards appear briefly during load, then 6 RiskMetricCard components render
4. Verify polar area chart (6 colored slices) and radial bar gauge appear in left panel
5. Switch Vuetify theme to light → all --rr-* colors should shift to muted palette (cyan → darker cyan, etc.)
6. Click "Классик" chip → should navigate to `/dashboard`
7. Navigate back to `/dashboard/radar` → "Радар" chip should be active
8. Click a metric card → should navigate to the drill-down route (e.g. `/contracts?filter=expiring`)
9. Click refresh button → spinner appears, data refetches
10. If any score ≥ 80: toast "Обнаружены критические риски: ..." should appear once
11. If any score ≥ 40: AlertsTicker strip appears at bottom with scrolling items

## Known Stubs

None. All data sources are wired to live API via `useRiskScores` composable. No hardcoded placeholder values flow to UI.

## Self-Check: PASSED

- [x] `frontend/src/views/RiskRadarView.vue` exists — FOUND (532 lines)
- [x] Commit `72adc56` exists — FOUND
- [x] Commit `3379ba6` exists — FOUND
- [x] `npm run build` exits 0 — PASSED
- [x] `git diff DashboardView.vue` exits 0 — PASSED (D-01)
- [x] All TypeScript — no errors in RiskRadarView.vue
