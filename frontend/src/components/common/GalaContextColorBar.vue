<template>
  <div class="gala-color-bar">
    <!-- Mode selector: Ячейка / Строка -->
    <div v-if="allowRowToggle" class="gala-color-bar-mode">
      <button
        type="button"
        class="gala-mode-btn"
        :class="{ 'gala-mode-btn--active': localMode === 'cell' }"
        @click="setMode('cell')"
      >
        Ячейка
      </button>
      <button
        type="button"
        class="gala-mode-btn"
        :class="{ 'gala-mode-btn--active': localMode === 'row' }"
        @click="setMode('row')"
      >
        Строка
      </button>
    </div>

    <!-- Palette swatches -->
    <div class="gala-palette-row">
      <button
        v-for="item in MARK_COLOR_PALETTE"
        :key="item.key"
        type="button"
        class="gala-palette-swatch"
        :class="{ 'gala-palette-swatch--active': currentColor === item.key }"
        :style="{ backgroundColor: item.swatch }"
        :title="`${item.label} (${localMode === 'row' ? 'строка' : 'ячейка'})`"
        @click="$emit('select-color', item.key, localMode)"
      />

      <!-- Clear color button -->
      <button
        type="button"
        class="gala-palette-clear"
        title="Сбросить цвет"
        @click="$emit('clear-color', localMode)"
      >
        <v-icon size="14">mdi-close</v-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { MARK_COLOR_PALETTE, type MarkColor } from '@/composables/useCellMarks'

const props = withDefaults(
  defineProps<{
    mode?: 'cell' | 'row'
    allowRowToggle?: boolean
    currentColor?: MarkColor | null
  }>(),
  {
    mode: 'cell',
    allowRowToggle: true,
    currentColor: null,
  }
)

const emit = defineEmits<{
  'select-color': [color: MarkColor, mode: 'cell' | 'row']
  'clear-color': [mode: 'cell' | 'row']
  'update:mode': [mode: 'cell' | 'row']
}>()

const localMode = ref<'cell' | 'row'>(props.mode)

watch(
  () => props.mode,
  m => {
    localMode.value = m
  }
)

function setMode(m: 'cell' | 'row') {
  localMode.value = m
  emit('update:mode', m)
}
</script>

<style scoped>
.gala-color-bar {
  padding: 6px 8px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-radius: 6px;
  margin-bottom: 4px;
}

.gala-color-bar-mode {
  display: flex;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 4px;
  padding: 2px;
  margin-bottom: 6px;
  gap: 2px;
}

.gala-mode-btn {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 3px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  cursor: pointer;
  transition: all 0.15s ease;
}

.gala-mode-btn--active {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.gala-palette-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.gala-palette-swatch {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.12s ease, border-color 0.12s ease;
  padding: 0;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}

.gala-palette-swatch:hover {
  transform: scale(1.18);
}

.gala-palette-swatch--active {
  border-color: rgb(var(--v-theme-on-surface));
  transform: scale(1.12);
}

.gala-palette-clear {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.35);
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: all 0.15s ease;
}

.gala-palette-clear:hover {
  border-color: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.08);
}
</style>
