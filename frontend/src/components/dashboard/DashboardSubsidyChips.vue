<template>
  <div v-if="yearSubsidies.length > 0" class="subsidy-chips-bar">
    <v-chip
      v-for="s in yearSubsidies" :key="s.id"
      :color="selectedSubsidyIds.includes(s.id) ? 'primary' : undefined"
      :variant="selectedSubsidyIds.includes(s.id) ? 'flat' : 'outlined'"
      size="small"
      class="subsidy-chip"
      @click="$emit('toggle', s.id)"
    >
      {{ s.shortName || s.name }}
    </v-chip>
    <v-chip
      v-if="selectedSubsidyIds.length > 0"
      variant="text" size="small" class="subsidy-chip"
      prepend-icon="mdi-close-circle-outline"
      @click="$emit('clear')"
    >Все</v-chip>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  yearSubsidies: any[]
  selectedSubsidyIds: number[]
}>()

defineEmits<{
  (e: 'toggle', id: number): void
  (e: 'clear'): void
}>()
</script>
