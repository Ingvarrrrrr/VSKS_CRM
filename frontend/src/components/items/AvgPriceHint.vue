<template>
  <div v-if="stats && stats.avg_price != null" class="text-caption mt-1 d-inline-flex align-center ga-1" style="white-space:normal">
    <v-tooltip :text="fullLabel" location="top" max-width="320">
      <template #activator="{ props: tip }">
        <span v-bind="tip" class="text-medium-emphasis d-inline-flex align-center ga-1">
          <v-icon size="12">mdi-chart-line</v-icon>
          Средняя {{ basisLabel }}: {{ priceText }}
        </span>
      </template>
    </v-tooltip>
    <v-btn
      v-if="!readonly"
      size="x-small" variant="text" color="primary" density="compact"
      class="px-1" style="min-width:0;height:18px"
      @click="emit('apply')"
    >
      подставить
    </v-btn>
  </div>
</template>

<script setup lang="ts">
// AvgPriceHint.vue — подсказка средней цены у поля «Цена ед.» позиции
// заявки/закупки (план clever-bouncing-lantern.md, Часть 2, п.7). Чисто
// презентационный компонент (ПРАВИЛО №5 — новый UI в новом файле): данные
// считает useAvgPrice.ts (один экземпляр на весь редактор), текст — ОДИН
// форматтер utils/avgPrice.ts (ПРАВИЛО №6), этот компонент только их
// показывает и прокидывает клик «подставить» наверх. Нет средней — компонент
// рендерит пустоту (v-if выше), ничего не навязывает.
import { computed } from 'vue'
import { formatAvgPriceLabel, avgPriceBasisLabel, type AvgPriceStats } from '@/utils/avgPrice'

const props = defineProps<{
  stats?: AvgPriceStats | null
  readonly?: boolean
}>()
const emit = defineEmits<{ apply: [] }>()

const fullLabel = computed(() => formatAvgPriceLabel(props.stats))
const basisLabel = computed(() => avgPriceBasisLabel(props.stats))
const priceText = computed(() => {
  const v = props.stats?.avg_price
  if (v == null) return ''
  return Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
})
</script>
