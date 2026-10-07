<template>
  <v-checkbox
    :model-value="checked"
    :disabled="row.skip_forced"
    density="compact" hide-details
    @update:model-value="v => $emit('update:skip', row.row, !!v)"
  />
  <v-tooltip v-if="row.skip_reason" location="top" max-width="360">
    <template #activator="{ props: reasonProps }">
      <div v-bind="reasonProps" class="text-caption text-medium-emphasis fisrs-reason">
        {{ row.skip_reason.text }}
      </div>
    </template>
    <span>{{ row.skip_reason.text }}</span>
  </v-tooltip>
</template>

<script setup lang="ts">
// FactImportRowSkipCell — ячейка «Пропустить» шага 3 мастера «Импорт факта»
// (ПРАВИЛО №5: вынесена из FactImportStepRows.vue — тот файл разросся к
// ~350 строкам). Чек-лист владельца 07.10.2026, п.3/п.8: значение галочки —
// ОПТИМИСТИЧНОЕ (override пользователя, если задан, иначе r.skip с сервера) —
// меняется сразу по клику, не ждёт ответа предпросмотра; при r.skip_forced
// (причина не устранена — статус/ФОТ/позиция) галочка неактивна, под ней
// мелкий текст причины (row.skip_reason.text, ЕДИНСТВЕННЫЙ источник — тот
// же, что в preview.py, ПРАВИЛО №6), при наведении — тот же текст целиком
// во всплывающей подсказке. У НЕ-forced пропуска причина тоже показывается
// (owner: «у не-forced пропуска тоже показывать причину»).
import { computed } from 'vue'
import { useFactImport, type FactImportRow } from '@/composables/subsidies/useFactImport'

const props = defineProps<{ row: FactImportRow }>()
defineEmits<{ 'update:skip': [row: number, value: boolean] }>()

const { factImport } = useFactImport()

// Оптимистичное значение: override пользователя (decisions.row_overrides[row]
// .skip), если он уже задан (даже пока ответ предпросмотра ещё в пути —
// debounce 300мс, см. useFactImport.ts::queuePreviewRefresh), иначе то, что
// посчитал сервер (row.skip).
const checked = computed(() => {
  const override = factImport.decisions.row_overrides[String(props.row.row)]?.skip
  return override ?? props.row.skip
})
</script>

<style scoped>
.fisrs-reason {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: help;
  line-height: 1.2;
  max-width: 140px;
}
</style>
