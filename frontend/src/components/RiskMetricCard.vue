<template>
  <div
    class="rr-metric-card"
    :data-severity="score.severity"
    role="button"
    tabindex="0"
    :aria-label="ariaLabel"
    :aria-pressed="false"
    @click="emit('click', score)"
    @keydown.enter.prevent="emit('click', score)"
    @keydown.space.prevent="emit('click', score)"
  >
    <div class="rr-metric-card__header">
      <v-icon :icon="score.icon" size="20" :color="accentColor" class="rr-metric-card__icon" />
      <span class="rr-metric-card__label">{{ score.label }}</span>
    </div>

    <div class="rr-metric-card__body">
      <div class="rr-metric-card__score" :style="{ color: accentColor }">
        {{ animatedScore }}
        <span class="rr-metric-card__score-suffix">/100</span>
      </div>
      <div class="rr-metric-card__bar">
        <div class="rr-metric-card__bar-fill" :style="barFillStyle" />
      </div>
      <div class="rr-metric-card__desc">{{ score.description }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useAnimatedNumber } from '../composables/useAnimatedNumber'
import type { RiskScore } from '../composables/useRiskScores'

interface Props {
  score: RiskScore
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'click', score: RiskScore): void
}>()

// Animate the score number (easeOutExpo via useAnimatedNumber).
const scoreTarget = toRef(() => props.score.score)
const animatedScore = useAnimatedNumber(scoreTarget, 800)

// Severity → label map (Russian, per UI-SPEC §Copywriting "Severity: *").
const SEVERITY_LABEL: Record<string, string> = {
  ok: 'Норма',
  warn: 'Внимание',
  high: 'Высокий',
  critical: 'Критический',
}

const accentColor = computed(() => `var(--rr-${props.score.severity})`)
const barFillStyle = computed(() => ({
  width: `${Math.max(0, Math.min(100, props.score.score))}%`,
  backgroundColor: `var(--rr-${props.score.severity})`,
}))
const ariaLabel = computed(() =>
  `${props.score.label}: ${props.score.score} из 100, уровень: ${SEVERITY_LABEL[props.score.severity] || props.score.severity}`
)
</script>

<style scoped>
.rr-metric-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 160px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  cursor: pointer;
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  outline: none;
}
.rr-metric-card:hover {
  transform: translateY(-3px);
}
.rr-metric-card:active {
  transform: translateY(-1px) scale(0.98);
  transition-duration: 0.1s;
}
.rr-metric-card:focus-visible {
  /* Preserve Vuetify focus ring; do not suppress via outline:none here. */
  box-shadow: 0 0 0 2px var(--v-theme-primary, #1976D2);
}

/* Severity-driven accent (border + glow on hover) */
.rr-metric-card[data-severity="ok"]:hover       { box-shadow: 0 12px 28px var(--rr-glow-ok);       border-color: var(--rr-ok); }
.rr-metric-card[data-severity="warn"]:hover     { box-shadow: 0 12px 28px var(--rr-glow-warn);     border-color: var(--rr-warn); }
.rr-metric-card[data-severity="high"]           { border-color: var(--rr-high); }
.rr-metric-card[data-severity="high"]:hover     { box-shadow: 0 12px 28px var(--rr-glow-high); }
.rr-metric-card[data-severity="critical"] {
  border-color: var(--rr-critical);
  animation: rr-critical-pulse 3s ease-in-out infinite;
}
.rr-metric-card[data-severity="critical"]:hover {
  box-shadow: 0 12px 28px var(--rr-glow-critical);
}

@keyframes rr-critical-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--rr-glow-critical); }
  50%      { box-shadow: 0 0 24px 4px var(--rr-glow-critical); }
}

/* Header: icon + uppercase label (Label typography role) */
.rr-metric-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rr-metric-card__icon { flex-shrink: 0; }
.rr-metric-card__label {
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--crm-text-muted);
}

.rr-metric-card__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
}

/* Score: Heading typography role (20px / 700) */
.rr-metric-card__score {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}
.rr-metric-card__score-suffix {
  font-size: 12px;
  font-weight: 400;
  color: var(--crm-text-muted);
}

/* Internal bar */
.rr-metric-card__bar {
  height: 8px;
  border-radius: 4px;
  background: var(--crm-border);
  overflow: hidden;
}
.rr-metric-card__bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}

/* Description: Body typography role (14px / 400) — trimmed visually */
.rr-metric-card__desc {
  font-size: 14px;
  font-weight: 400;
  line-height: 1.5;
  color: var(--crm-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
