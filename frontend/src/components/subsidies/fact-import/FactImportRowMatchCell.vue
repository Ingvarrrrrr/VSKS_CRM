<template>
  <template v-if="row.match.state === 'found' || row.match.state === 'already_purchased'">
    <v-chip size="x-small" :color="row.match.state === 'found' ? 'success' : 'grey'" variant="tonal" class="mb-1">
      <v-icon v-if="row.match.state === 'found'" icon="mdi-check" size="12" />
      {{ row.match.state === 'found' ? 'найдено' : 'уже закуплено' }}
    </v-chip>
    <div class="text-caption">
      {{ row.match.planned_item_name || '(без имени)' }}
      <span v-if="row.match.planned_item_amount != null" class="text-medium-emphasis">
        ({{ formatMoney(row.match.planned_item_amount) }})
      </span>
    </div>
    <v-btn size="x-small" variant="text" color="primary" class="mt-1" @click="$emit('open-picker', row)">
      Изменить…
    </v-btn>
  </template>
  <template v-else>
    <v-chip size="x-small" :color="row.match.state === 'ambiguous' ? 'warning' : 'error'" variant="tonal" class="mb-1">
      {{ row.match.state === 'ambiguous' ? 'неоднозначно' : 'не найдено' }}
    </v-chip>
    <div class="d-flex flex-column ga-1">
      <v-btn v-for="c in row.match.candidates.slice(0, 3)" :key="c.id" size="x-small" variant="outlined"
        @click="$emit('set-planned-item', row.row, c.id)">
        {{ c.name }} ({{ formatMoney(c.amount) }})
      </v-btn>
      <v-btn size="x-small" variant="text" color="primary" @click="$emit('open-picker', row)">
        Выбрать плановую позицию…
      </v-btn>
    </div>
  </template>
</template>

<script setup lang="ts">
// FactImportRowMatchCell — ячейка «Сопоставление» шага 3 мастера «Импорт
// факта» (ПРАВИЛО №5: вынесена из FactImportStepRows.vue, чтобы тот не
// разрастался). Выбор плановой позиции у КАЖДОЙ строки — чек-лист
// владельца 07.10.2026, п.3: found/already_purchased теперь тоже можно
// сменить («Изменить…»), не только исправить not_found/ambiguous.
// ПРАВИЛО №6: формат денег — общий formatMoney, пикер — переиспользуемый
// FactImportRowPlanPicker (открывается тем же событием open-picker, что и
// раньше в FactImportStepRows.vue).
import type { FactImportRow } from '@/composables/subsidies/useFactImport'
import { formatMoney } from '@/utils/formatMoney'

defineProps<{ row: FactImportRow }>()
defineEmits<{
  'open-picker': [row: FactImportRow]
  'set-planned-item': [row: number, id: number]
}>()
</script>
