<template>
  <v-dialog v-model="show" max-width="360" scrollable>
    <v-card>
      <v-card-title class="text-h6 pt-4 px-5 d-flex align-center justify-space-between">
        Порядок столбцов
        <v-btn variant="text" size="small" prepend-icon="mdi-restore" @click="$emit('reset')">Сбросить</v-btn>
      </v-card-title>
      <v-card-subtitle class="px-5 pb-2 text-caption text-medium-emphasis">
        Перетащите строки, чтобы изменить порядок
      </v-card-subtitle>
      <v-card-text class="px-3 py-0">
        <v-list density="compact">
          <v-list-item
            v-for="(key, idx) in colOrder"
            :key="key"
            :draggable="true"
            @dragstart="$emit('drag-start', idx)"
            @dragover="$emit('drag-over', $event, idx)"
            @dragend="$emit('drag-end')"
            :style="dragSrcIdx === idx ? 'opacity:0.4' : ''"
            class="col-drag-item px-2"
            rounded="sm"
          >
            <template #prepend>
              <v-icon icon="mdi-drag-vertical" color="grey" size="20" class="mr-1" style="cursor:grab" />
            </template>
            <v-list-item-title class="text-body-2">
              {{ allColumns.find(c => c.key === key)?.title || key }}
            </v-list-item-title>
            <template #append>
              <v-btn icon="mdi-chevron-up" variant="text" size="x-small" :disabled="idx === 0" @click="$emit('move', idx, -1)" />
              <v-btn icon="mdi-chevron-down" variant="text" size="x-small" :disabled="idx === colOrder.length - 1" @click="$emit('move', idx, 1)" />
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn color="primary" @click="show = false">Готово</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  colOrder: string[]
  dragSrcIdx: number | null
  allColumns: { key: string; title: string }[]
}>()
defineEmits<{
  (e: 'reset'): void
  (e: 'drag-start', idx: number): void
  (e: 'drag-over', event: DragEvent, idx: number): void
  (e: 'drag-end'): void
  (e: 'move', idx: number, dir: -1 | 1): void
}>()

const show = defineModel<boolean>('modelValue', { required: true })
</script>

<style scoped>
.col-drag-item { cursor: default; user-select: none; }
.col-drag-item:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
</style>
