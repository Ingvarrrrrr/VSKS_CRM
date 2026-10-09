<template>
  <div class="fismc-cell">
    <template v-if="row.match.state === 'found' || row.match.state === 'already_purchased'">
      <v-chip size="x-small" :color="row.match.state === 'found' ? 'success' : 'grey'" variant="tonal" class="mb-1">
        <v-icon v-if="row.match.state === 'found'" icon="mdi-check" size="12" />
        {{ row.match.state === 'found' ? 'найдено' : 'уже закуплено' }}
      </v-chip>
      <div class="text-caption fismc-wrap">
        {{ row.match.planned_item_name || '(без имени)' }}
        <span v-if="row.match.planned_item_amount != null" class="text-medium-emphasis">
          ({{ formatMoney(row.match.planned_item_amount) }})
        </span>
      </div>
      <v-btn size="x-small" variant="text" color="primary" class="mt-1 fismc-btn" @click="$emit('open-picker', row)">
        Изменить…
      </v-btn>
    </template>
    <template v-else>
      <!-- 🔵 Правка (план lazy-swimming-hollerith.md, п.4): состояние
           no_item_name («Плановая позиция» пуста у строки-категории с
           данными) — своя подпись словами владельца, остальная вёрстка
           (кандидаты + «Выбрать плановую позицию…») общая с ambiguous/
           not_found, второй компонент не завели. -->
      <v-chip
        size="x-small"
        :color="row.match.state === 'ambiguous' || row.match.state === 'no_item_name' ? 'warning' : 'error'"
        variant="tonal" class="mb-1"
      >
        {{ row.match.state === 'ambiguous' ? 'неоднозначно'
          : row.match.state === 'no_item_name' ? 'нет названия позиции'
          : 'не найдено' }}
      </v-chip>
      <!-- Задание 07.10.2026 (п.1/п.2): у ambiguous — строка «уже у строки N»,
           клик переносит к той строке (useRowJump, ПРАВИЛО №5/№6 — тот же
           механизм, что у сводных предупреждений). -->
      <div v-if="row.match.state === 'ambiguous' && row.match.competing_rows?.length" class="text-caption fismc-wrap mb-1">
        уже у
        <a v-for="(rn, i) in row.match.competing_rows" :key="rn" href="#" class="fismc-row-link"
           @click.prevent="jumpToRow(rn)">
          строки {{ rn }}<template v-if="i < row.match.competing_rows!.length - 1">, </template>
        </a>
      </div>
      <div class="d-flex flex-column ga-1">
        <v-btn v-for="c in row.match.candidates.slice(0, 3)" :key="c.id" size="x-small" variant="outlined"
          class="fismc-btn" @click="$emit('set-planned-item', row.row, c.id)">
          {{ c.name }} ({{ formatMoney(c.amount) }})
        </v-btn>
        <v-btn size="x-small" variant="text" color="primary" class="fismc-btn" @click="$emit('open-picker', row)">
          Выбрать плановую позицию…
        </v-btn>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// FactImportRowMatchCell — ячейка «Сопоставление» шага 3 мастера «Импорт
// факта» (ПРАВИЛО №5: вынесена из FactImportStepRows.vue, чтобы тот не
// разрастался). Выбор плановой позиции у КАЖДОЙ строки — чек-лист
// владельца 07.10.2026, п.3: found/already_purchased теперь тоже можно
// сменить («Изменить…»), не только исправить not_found/ambiguous.
// ПРАВИЛО №6: формат денег — общий formatMoney, пикер — переиспользуемый
// FactImportRowPlanPicker (открывается тем же событием open-picker, что и
// раньше в FactImportStepRows.vue), переход к строке — общий useRowJump.
//
// Жалоба владельца 07.10.2026 (п.1): кандидаты заглавными, nowrap, без
// overflow — наезжали на соседние колонки. Текст кнопок теперь обычным
// регистром (text-none), переносится (white-space:normal, height:auto),
// занимает всю ширину ячейки, выровнен влево (см. .fismc-btn ниже).
import type { FactImportRow } from '@/composables/subsidies/useFactImport'
import { formatMoney } from '@/utils/formatMoney'
import { useRowJump } from '@/composables/subsidies/useRowJump'

defineProps<{ row: FactImportRow }>()
defineEmits<{
  'open-picker': [row: FactImportRow]
  'set-planned-item': [row: number, id: number]
}>()

const { jumpToRow } = useRowJump()
</script>

<style scoped>
.fismc-cell { overflow-wrap: anywhere; }
.fismc-wrap { white-space: normal; overflow-wrap: anywhere; }
.fismc-row-link { color: rgb(var(--v-theme-primary)); text-decoration: underline; }
.fismc-btn {
  text-transform: none !important;
  white-space: normal !important;
  height: auto !important;
  min-height: 24px;
  width: 100%;
  justify-content: flex-start !important;
  text-align: left;
  display: block;
}
.fismc-btn :deep(.v-btn__content) {
  white-space: normal;
  text-align: left;
  display: block;
  line-height: 1.3;
}
</style>
