---
phase: 14
plan: 02
subsystem: frontend/components
tags: [risk-radar, neon-telemetry, vue3, accessibility, css-tokens]
dependency_graph:
  requires:
    - useAnimatedNumber.ts (frontend/src/composables/)
    - useRiskScores.ts types (frontend/src/composables/) — type-only import, 14-01 provides
  provides:
    - RiskMetricCard.vue — single risk card component
    - AlertsTicker.vue — horizontal scrolling alerts strip
  affects:
    - 14-03-PLAN.md (RiskRadarView.vue composes both components)
tech_stack:
  added: []
  patterns:
    - Vue 3 SFC with script setup lang=ts
    - CSS custom property tokens (--rr-* + --crm-*) for theme-agnostic styling
    - data-severity attribute for CSS state-driven styling (avoids class concatenation)
    - doubledItems + translateX(-50%) CSS trick for seamless marquee loop
    - useAnimatedNumber composable for easeOutExpo score animation
key_files:
  created:
    - frontend/src/components/RiskMetricCard.vue
    - frontend/src/components/AlertsTicker.vue
  modified: []
decisions:
  - "Inline type stub for RiskScore not needed — type import kept as-is; TypeScript will resolve once 14-01 lands"
  - "toRef(() => props.score.score) for derived ref to useAnimatedNumber — avoids extra computed"
  - "doubledItems trick (duplicate array + translate -50%) for seamless CSS marquee without JS timers"
  - "HTML entity &#9888; for warning triangle icon in ticker (avoids v-icon overhead in marquee)"
metrics:
  duration: "~2 minutes"
  completed_date: "2026-04-19"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 14 Plan 02: Presentational Components (RiskMetricCard + AlertsTicker) Summary

Two pure presentational Vue 3 SFCs built for the Risk Radar dashboard — RiskMetricCard renders a single severity-scored metric card with neon token styling and animated score count-up; AlertsTicker renders a seamlessly looping CSS marquee of critical-threshold items, hidden via v-if when empty.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create RiskMetricCard.vue | 17ec9c8 | frontend/src/components/RiskMetricCard.vue |
| 2 | Create AlertsTicker.vue | e06fdc9 | frontend/src/components/AlertsTicker.vue |

## Component Contracts

### RiskMetricCard.vue

**Props interface:**
```typescript
interface Props {
  score: RiskScore  // from '../composables/useRiskScores'
}
// RiskScore shape (per 14-01 contract):
// { key: RiskMetricKey, label: string, icon: string, score: number,
//   severity: RiskSeverity, affectedCount: number, description: string }
```

**Events:**
```typescript
defineEmits<{
  (e: 'click', score: RiskScore): void
}>()
```

**Behavior:**
- Score animated via `useAnimatedNumber(toRef(() => props.score.score), 800)` — easeOutExpo 800ms
- `data-severity` attribute drives all CSS severity state (border, glow, pulse animation)
- `rr-critical-pulse` keyframe runs `3s ease-in-out infinite` when `data-severity="critical"`
- Hover: `translateY(-3px)` + `box-shadow: 0 12px 28px var(--rr-glow-{severity})`
- Active: `translateY(-1px) scale(0.98)` with 0.1s transition
- ARIA: `role="button"`, `tabindex="0"`, `:aria-label`, `aria-pressed="false"`
- Keyboard: `@keydown.enter.prevent` + `@keydown.space.prevent` both emit `click`

### AlertsTicker.vue

**Props interface:**
```typescript
interface Props {
  items: RiskScore[]
  visible?: boolean      // default: true
  durationSec?: number   // default: 30
}
```

**Events:**
```typescript
defineEmits<{
  (e: 'item-click', item: RiskScore): void
}>()
```

**Behavior:**
- `v-if="visible && items.length > 0"` — full DOM removal when hidden (not v-show)
- `doubledItems = [...items, ...items]` + `translateX(-50%)` — seamless loop without JS
- `animationDuration` set from `durationSec` prop via inline style on track
- Hover pauses animation (`animation-play-state: paused`) for readability
- `prefers-reduced-motion: reduce` → `animation: none`
- Items rendered as `<button type="button">` — keyboard focusable by default
- ARIA: `role="marquee"`, `aria-live="off"`, `aria-label="Критические предупреждения"`

## CSS Custom Properties Read from Parent Context

Both components read these tokens defined by RiskRadarView.vue (Plan 14-03):

| Token | Purpose |
|-------|---------|
| `--rr-ok` | Severity color for ok level |
| `--rr-warn` | Severity color for warn level |
| `--rr-high` | Severity color for high level |
| `--rr-critical` | Severity color for critical level |
| `--rr-glow-ok` | Box-shadow glow for ok cards |
| `--rr-glow-warn` | Box-shadow glow for warn cards |
| `--rr-glow-high` | Box-shadow glow for high cards |
| `--rr-glow-critical` | Box-shadow glow for critical cards |
| `--crm-surface` | Card background (existing global token) |
| `--crm-border` | Card border + bar track background |
| `--crm-text` | Primary text color |
| `--crm-text-muted` | Secondary/label text color |

## Deviations from Plan

None — plan executed exactly as written.

The only minor adaptation: `toRef(() => props.score.score)` used for the computed getter form (Vue 3.3+) instead of `toRef(props, 'score').value.score` — functionally identical, avoids the extra object destructure.

## Known Stubs

None. Both components are pure presentational — they render whatever data is passed in via props. No hardcoded data, no placeholder text, no empty arrays wired to props.

## Self-Check: PASSED

- FOUND: frontend/src/components/RiskMetricCard.vue
- FOUND: frontend/src/components/AlertsTicker.vue
- FOUND: .planning/phases/14-risk-radar-dashboard-neon-telemetry/14-02-SUMMARY.md
- FOUND commit: 17ec9c8 (RiskMetricCard.vue)
- FOUND commit: e06fdc9 (AlertsTicker.vue)
