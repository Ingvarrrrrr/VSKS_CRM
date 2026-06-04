<template>
  <div
    class="grad-avatar"
    :class="`grad-avatar--${size}`"
    :style="{ background: gradient }"
    :title="fullName"
  >
    {{ initials }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  fullName: string
  size?: 'xs' | 'sm' | 'md' | 'lg'
}>(), {
  size: 'md',
})

const initials = computed(() => {
  const parts = (props.fullName || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
})

// Stable gradient based on name hash
const gradient = computed(() => {
  const palettes: [string, string][] = [
    ['#6aa6ff', '#8b5cf6'],  // blue → purple
    ['#22c997', '#5dd0ff'],  // green → cyan
    ['#f6b34a', '#ff8a4a'],  // orange
    ['#ff5b6a', '#ff3b8b'],  // red → pink
    ['#8b5cf6', '#5dd0ff'],  // purple → cyan
    ['#22c997', '#f6b34a'],  // green → orange
  ]
  const hash = (props.fullName || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const [c1, c2] = palettes[hash % palettes.length]
  return `linear-gradient(135deg, ${c1}, ${c2})`
})
</script>

<style scoped>
.grad-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 28%;
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.5px;
  flex-shrink: 0;
  user-select: none;
}

.grad-avatar--xs { width: 24px; height: 24px; font-size: 10px; }
.grad-avatar--sm { width: 32px; height: 32px; font-size: 12px; }
.grad-avatar--md { width: 40px; height: 40px; font-size: 14px; }
.grad-avatar--lg { width: 56px; height: 56px; font-size: 18px; }
</style>
