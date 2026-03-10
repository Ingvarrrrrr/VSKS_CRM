<template>
  <v-card class="memory-card" elevation="2" @click="$emit('edit', memory)">
    <v-card-item>
      <template #prepend>
        <v-icon 
          v-if="memory.is_pinned" 
          icon="mdi-pin" 
          color="amber" 
          size="20"
          class="mr-2"
        />
      </template>
      <v-card-title class="text-body-1 font-weight-bold">
        {{ memory.title }}
      </v-card-title>
      <v-card-subtitle v-if="memory.tags" class="d-flex flex-wrap gap-1 mt-1">
        <v-chip 
          v-for="tag in memory.tags.split(',')" 
          :key="tag" 
          size="x-small" 
          variant="tonal"
          class="mr-1"
        >
          {{ tag.trim() }}
        </v-chip>
      </v-card-subtitle>
    </v-card-item>

    <v-card-text v-if="memory.problem || memory.solution" class="pt-0">
      <div v-if="memory.problem" class="mb-2">
        <div class="text-caption text-grey mb-1">Проблема:</div>
        <div class="text-body-2 problem-text">{{ memory.problem }}</div>
      </div>
      <div v-if="memory.solution">
        <div class="text-caption text-grey mb-1">Решение:</div>
        <div class="text-body-2 solution-text">{{ memory.solution }}</div>
      </div>
    </v-card-text>

    <v-divider />

    <v-card-actions>
      <div class="text-caption text-grey">
        {{ formatDate(memory.updated_at) }}
      </div>
      <v-spacer />
      <v-btn icon="mdi-pencil" size="small" variant="text" @click.stop="$emit('edit', memory)" />
      <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click.stop="$emit('delete', memory)" />
    </v-card-actions>
  </v-card>
</template>

<script setup>
defineProps({
  memory: { type: Object, required: true }
})

defineEmits(['edit', 'delete'])

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

<style scoped>
.memory-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.memory-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0,0,0,0.15) !important;
}
.problem-text, .solution-text {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}
</style>
