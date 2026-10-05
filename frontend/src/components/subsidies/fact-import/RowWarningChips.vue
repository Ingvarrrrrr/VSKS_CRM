<template>
  <div class="d-flex flex-wrap ga-1 align-center mt-1">
    <v-chip v-for="row in visibleRows" :key="row" size="x-small" variant="tonal" color="warning"
      class="rwc-chip" @click="onChipClick(row)">
      стр. {{ row }}
    </v-chip>
    <span v-if="hiddenCount > 0" class="text-caption text-medium-emphasis">ещё {{ hiddenCount }}</span>
    <v-btn v-if="showIsolateButton" size="x-small" variant="text" color="primary" class="ml-1"
      @click="$emit('update:isolated', !isolated)">
      {{ isolated ? 'Показать все' : 'Показать только эти строки' }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
// RowWarningChips — ЕДИНЫЙ компонент чипов «стр. N» под сводным
// предупреждением мастера «Импорт факта» (ПРАВИЛО №5/№6: один механизм на
// весь мастер, не копия в каждом v-alert). Клик по чипу кладёт номер строки в
// общее состояние useRowJump — сам переход/подсветку делает активный шаг
// (у него есть доступ к своим фильтрам и DOM таблицы/карточек).
import { computed } from 'vue'
import { useRowJump } from '@/composables/subsidies/useRowJump'

const props = defineProps<{
  rows: number[]
  isolated?: boolean
  /** Показывать кнопку «Показать только эти строки» — не нужна там, где
   *  сводных предупреждений с разным набором строк несколько и переключатель
   *  неоднозначен (сейчас используется везде, кроме такого случая). */
  showIsolateButton?: boolean
}>()
defineEmits<{ 'update:isolated': [value: boolean] }>()

const { jumpToRow } = useRowJump()

const LIMIT = 15
const sortedRows = computed(() => [...props.rows].sort((a, b) => a - b))
const visibleRows = computed(() => sortedRows.value.slice(0, LIMIT))
const hiddenCount = computed(() => Math.max(0, sortedRows.value.length - LIMIT))

function onChipClick(row: number) {
  jumpToRow(row)
}
</script>

<style scoped>
.rwc-chip { cursor: pointer; }
</style>
