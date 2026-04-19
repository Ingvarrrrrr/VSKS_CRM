<template>
  <div
    v-if="visible && items.length > 0"
    class="rr-ticker"
    role="marquee"
    aria-live="off"
    aria-label="Критические предупреждения"
  >
    <div class="rr-ticker__track" :style="trackStyle">
      <!-- Double the list so the scroll loops seamlessly -->
      <template v-for="(item, idx) in doubledItems" :key="`${item.key}-${idx}`">
        <button
          type="button"
          class="rr-ticker__item"
          :data-severity="item.severity"
          @click="emit('item-click', item)"
        >
          <span class="rr-ticker__icon" aria-hidden="true">&#9888;</span>
          <span class="rr-ticker__label">{{ item.label }}:</span>
          <span class="rr-ticker__desc">{{ item.description }}</span>
        </button>
        <span class="rr-ticker__sep" aria-hidden="true">&middot;</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RiskScore } from '../composables/useRiskScores'

interface Props {
  items: RiskScore[]
  visible?: boolean
  /** Seconds for full scroll cycle. Default 30s per UI-SPEC. */
  durationSec?: number
}
const props = withDefaults(defineProps<Props>(), {
  visible: true,
  durationSec: 30,
})
const emit = defineEmits<{
  (e: 'item-click', item: RiskScore): void
}>()

const doubledItems = computed(() => [...props.items, ...props.items])

const trackStyle = computed(() => ({
  animationDuration: `${props.durationSec}s`,
}))
</script>

<style scoped>
.rr-ticker {
  position: relative;
  height: 36px;
  overflow: hidden;
  border-top: 1px solid var(--rr-critical);
  background: color-mix(in srgb, var(--rr-critical) 15%, transparent);
  border-radius: 6px;
}

/* Light theme: softer tint per UI-SPEC */
:deep(.v-theme--light) .rr-ticker,
.rr-ticker[data-theme="light"] {
  background: color-mix(in srgb, var(--rr-high) 8%, transparent);
  border-top-color: var(--rr-high);
}

.rr-ticker__track {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  height: 100%;
  padding-left: 16px;
  white-space: nowrap;
  animation: rr-ticker-scroll linear infinite;
}

@keyframes rr-ticker-scroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

.rr-ticker:hover .rr-ticker__track {
  animation-play-state: paused;
}

.rr-ticker__item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  padding: 0 4px;
  color: var(--crm-text);
  cursor: pointer;
  font-size: 14px;
  font-weight: 400;
  line-height: 1.4;
}
.rr-ticker__item:hover .rr-ticker__label,
.rr-ticker__item:focus-visible .rr-ticker__label {
  text-decoration: underline;
}

.rr-ticker__icon { flex-shrink: 0; }
.rr-ticker__label { font-weight: 400; }
.rr-ticker__desc { color: var(--crm-text-muted); }
.rr-ticker__sep { color: var(--crm-text-muted); user-select: none; }

/* Severity accent on icon (text color) */
.rr-ticker__item[data-severity="warn"]     .rr-ticker__icon { color: var(--rr-warn); }
.rr-ticker__item[data-severity="high"]     .rr-ticker__icon { color: var(--rr-high); }
.rr-ticker__item[data-severity="critical"] .rr-ticker__icon { color: var(--rr-critical); }

/* Respect user motion preference */
@media (prefers-reduced-motion: reduce) {
  .rr-ticker__track { animation: none; }
}
</style>
