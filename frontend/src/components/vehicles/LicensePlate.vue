<template>
  <!-- Fleet-style dark plate chip — always readonly display -->
  <span class="fleet-plate-chip">{{ modelValue || '—' }}</span>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
  readonly?: boolean  // kept for API compat — always treated as readonly
}>()
</script>

<style scoped>
.fleet-plate-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  background: #111521;
  border: 1px solid #2b3245;
  border-radius: 8px;
  padding: 4px 10px;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: .5px;
  color: #e9edf5;
  white-space: nowrap;
}
</style>
