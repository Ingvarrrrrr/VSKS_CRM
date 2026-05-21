<template>
  <span class="status-pill" :class="`status-pill--${variant}`">
    <i v-if="dot" class="status-pill__dot"></i>
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'ok' | 'warn' | 'alert' | 'info' | 'muted'
  label?: string
  dot?: boolean   // show pulsing dot indicator
}>(), {
  variant: 'muted',
  label: '',
  dot: false,
})
</script>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.status-pill__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  background: currentColor;
  animation: pill-pulse 1.8s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pill-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

.status-pill--ok    { background: rgba(34,  201, 151, 0.18); color: #22c997; }
.status-pill--warn  { background: rgba(246, 179, 74,  0.18); color: #f6b34a; }
.status-pill--alert { background: rgba(255, 91,  106, 0.18); color: #ff5b6a; }
.status-pill--info  { background: rgba(93,  208, 255, 0.18); color: #5dd0ff; }
.status-pill--muted { background: rgba(138, 147, 168, 0.18); color: #8a93a8; }
</style>
