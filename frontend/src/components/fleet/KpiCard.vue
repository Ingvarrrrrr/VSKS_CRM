<template>
  <div
    class="kpi-card"
    :class="[`kpi-card--${variant}`, { 'kpi-card--clickable': clickable, 'kpi-card--active': active }]"
    @click="clickable && $emit('click')"
  >
    <div class="kpi-card__label">{{ label }}</div>
    <div class="kpi-card__value">
      {{ value }}
      <span v-if="trend" class="kpi-card__trend" :class="`kpi-card__trend--${trendType}`">{{ trend }}</span>
    </div>
    <div v-if="sub" class="kpi-card__sub">{{ sub }}</div>
    <div v-if="barPct !== null" class="kpi-card__bar">
      <i :style="{ width: `${barPct}%`, background: barGradient }"></i>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  value: string | number
  sub?: string
  trend?: string        // e.g. '+2 за неделю', '-1', '+3'
  trendType?: 'ok' | 'warn' | 'alert'
  variant?: 'default' | 'ok' | 'warn' | 'alert' | 'info'
  barPct?: number | null
  clickable?: boolean
  active?: boolean
}>(), {
  trendType: 'ok',
  variant: 'default',
  barPct: null,
  clickable: false,
  active: false,
})

defineEmits<{
  (e: 'click'): void
}>()

const barGradient = computed(() => {
  switch (props.variant) {
    case 'ok':    return 'linear-gradient(90deg, #22c997, #5dd0ff)'
    case 'warn':  return 'linear-gradient(90deg, #f6b34a, #ff8a4a)'
    case 'alert': return 'linear-gradient(90deg, #ff5b6a, #ff3b8b)'
    case 'info':  return 'linear-gradient(90deg, #5dd0ff, #6aa6ff)'
    default:      return 'linear-gradient(90deg, #6aa6ff, #8b5cf6)'
  }
})
</script>

<style scoped>
.kpi-card {
  background: var(--panel, #141823);
  border: 1px solid var(--line, #222838);
  border-radius: 14px;
  padding: 18px 20px;
  color: var(--text, #e9edf5);
  position: relative;
  transition: border-color 0.15s, transform 0.15s;
}

.kpi-card--clickable { cursor: pointer; user-select: none; }
.kpi-card--clickable:hover {
  border-color: var(--accent, #6aa6ff);
  transform: translateY(-2px);
}
.kpi-card--clickable:active {
  transform: translateY(0);
  filter: brightness(0.95);
}

/* Active state — выбран как активный фильтр */
.kpi-card--active {
  border-color: var(--accent, #6aa6ff);
  border-width: 2px;
  padding: 17px 19px;  /* компенсация +1px бордера */
  background:
    linear-gradient(180deg, rgba(106, 166, 255, 0.18), rgba(106, 166, 255, 0.06)),
    var(--panel, #141823);
  box-shadow:
    0 0 0 3px rgba(106, 166, 255, 0.15),
    0 8px 24px -10px rgba(106, 166, 255, 0.4);
  transform: translateY(-1px);
}
.kpi-card--active.kpi-card--ok {
  border-color: #22c997;
  background:
    linear-gradient(180deg, rgba(34, 201, 151, 0.18), rgba(34, 201, 151, 0.05)),
    var(--panel, #141823);
  box-shadow: 0 0 0 3px rgba(34, 201, 151, 0.15), 0 8px 24px -10px rgba(34, 201, 151, 0.4);
}
.kpi-card--active.kpi-card--warn {
  border-color: #f6b34a;
  background:
    linear-gradient(180deg, rgba(246, 179, 74, 0.18), rgba(246, 179, 74, 0.05)),
    var(--panel, #141823);
  box-shadow: 0 0 0 3px rgba(246, 179, 74, 0.15), 0 8px 24px -10px rgba(246, 179, 74, 0.4);
}
.kpi-card--active.kpi-card--alert {
  border-color: #ff5b6a;
  background:
    linear-gradient(180deg, rgba(255, 91, 106, 0.18), rgba(255, 91, 106, 0.05)),
    var(--panel, #141823);
  box-shadow: 0 0 0 3px rgba(255, 91, 106, 0.15), 0 8px 24px -10px rgba(255, 91, 106, 0.4);
}
/* Active checkmark indicator в правом верхнем углу */
.kpi-card--active::after {
  content: '✓';
  position: absolute;
  top: 8px;
  right: 10px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
  background: var(--accent, #6aa6ff);
  color: #0a0d14;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
}
.kpi-card--active.kpi-card--ok::after { background: #22c997; }
.kpi-card--active.kpi-card--warn::after { background: #f6b34a; }
.kpi-card--active.kpi-card--alert::after { background: #ff5b6a; }

.kpi-card__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--muted, #8a93a8);
  font-weight: 600;
}

.kpi-card__value {
  font-size: 32px;
  font-weight: 800;
  line-height: 1.2;
  margin-top: 6px;
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.kpi-card__trend {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-family: inherit;
  font-weight: 700;
}
.kpi-card__trend--ok    { background: rgba(34, 201, 151, 0.18); color: #22c997; }
.kpi-card__trend--warn  { background: rgba(246, 179, 74, 0.18);  color: #f6b34a; }
.kpi-card__trend--alert { background: rgba(255, 91, 106, 0.18);  color: #ff5b6a; }

.kpi-card__sub {
  font-size: 12px;
  color: var(--muted, #8a93a8);
  margin-top: 4px;
}

.kpi-card__bar {
  height: 4px;
  border-radius: 4px;
  background: var(--bg-2, #0f131c);
  margin-top: 12px;
  overflow: hidden;
}
.kpi-card__bar i {
  display: block;
  height: 100%;
  transition: width 0.4s ease;
}

/* Light theme overrides */
:deep(.v-theme--light) .kpi-card,
.v-theme--light .kpi-card {
  background: #ffffff;
  border-color: #e2e6f0;
  color: #1a1d23;
}
:deep(.v-theme--light) .kpi-card__label,
.v-theme--light .kpi-card__label { color: #6b7280; }
:deep(.v-theme--light) .kpi-card__sub,
.v-theme--light .kpi-card__sub   { color: #6b7280; }
:deep(.v-theme--light) .kpi-card__bar,
.v-theme--light .kpi-card__bar   { background: #f1f4fa; }
</style>
