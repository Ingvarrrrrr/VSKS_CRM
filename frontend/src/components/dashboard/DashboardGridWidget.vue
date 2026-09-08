<template>
  <div class="grid-widget" :class="{ 'grid-widget--editing': editing }">
    <div v-if="editing" class="widget-drag-handle">
      <v-icon icon="mdi-drag" size="16" /> {{ label }}
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  editing: boolean
  label: string
}>()
</script>
