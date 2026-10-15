<!-- DrillSearchField.vue — поле динамического поиска в шапке всплывающих
     окон-расшифровок (владелец, 15.10.2026). Используется вместе с
     useDrillSearch.ts (frontend/src/composables/useDrillSearch.ts) —
     v-model:query тут, фильтрация там, второй раз цикл поиска не пишем
     (Правило №6). Без debounce — фильтрация мгновенная, так же, как и в
     уже существующих полях поиска проекта. -->
<template>
  <div class="drill-search">
    <v-text-field
      v-model="model"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      prepend-inner-icon="mdi-magnify"
      label="Поиск…"
      class="drill-search__field"
    />
    <div v-if="active" class="text-caption drill-search__summary">
      <template v-if="foundCount > 0">
        Найдено {{ foundCount }} из {{ totalCount }}<template v-if="showAmount"> · на сумму {{ formattedAmount }}</template>
      </template>
      <template v-else>ничего не найдено</template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'

const props = withDefaults(defineProps<{
  modelValue: string
  active: boolean
  foundCount: number
  totalCount: number
  foundAmount?: number
  /** false — если для этого окна «на сумму» не осмысленно (строки без
   *  единой денежной величины). */
  showAmount?: boolean
}>(), {
  foundAmount: 0,
  showAmount: true,
})
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const model = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v ?? ''),
})
const formattedAmount = computed(() => formatCurrency(props.foundAmount || 0))
</script>

<style scoped>
.drill-search { padding: 8px 16px 0; }
.drill-search__field { max-width: 360px; background: rgba(255, 255, 255, 0.92); border-radius: 4px; }
.drill-search__summary { margin-top: 4px; color: rgba(0, 0, 0, 0.6); }
</style>
