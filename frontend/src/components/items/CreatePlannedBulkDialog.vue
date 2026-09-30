<template>
  <!-- Общая кнопка «Создать в плане закупок» (владелец 2026-08-06) — создаёт плановые
       позиции (Ур.5 FeoPlannedItem) сразу для ВСЕХ позиций, у которых заполнена категория
       ФЭО, но нет привязки к плановой позиции, каждую в своей категории. Presentational —
       parent owns needPlanRows/progress/failures and the actual create loop.
       Extracted from PurchaseItemsEditor.vue. -->
  <!-- Владелец (29.09, п.2, экран 2560px): max-width 640 узкий, наименования и
       заголовки обрезались/не переносились, колонка «Тип» не влезала целиком —
       ширина теперь от экрана (95vw/1600, fullscreen на mobile), текст переносится. -->
  <v-dialog v-model="open" width="95vw" max-width="1600" :fullscreen="mobile" :persistent="loading">
    <v-card>
      <v-card-title class="text-subtitle-1">
        Создать в плане закупок ({{ rows.length }})
      </v-card-title>
      <v-card-text>
        <div v-if="noCategoryCount > 0" class="text-caption mb-2" style="color:#EF4444">
          У {{ noCategoryCount }} {{ noCategoryCount === 1 ? 'позиции' : 'позиций' }} не выбрана категория ФЭО — для них плановые позиции не создаются.
        </div>
        <!-- Дефект 2 (владелец, 2026-08-20): решение владельца — каждая строка получает
             СВОЮ плановую позицию, одноимённые не объединяются. Честно предупреждаем,
             если в категории уже есть плановая с тем же именем — это НЕ блокирует
             создание и НЕ меняет поведение, только предупреждает, чтобы не было сюрприза. -->
        <div v-if="rows.some(r => r.duplicateOf)" class="text-caption mb-2" style="color:#B45309">
          У части позиций (отмечены ниже) в этой категории уже есть плановая позиция с таким же названием — будет создана ОТДЕЛЬНАЯ, не объединяются.
        </div>
        <!-- Жалоба владельца (29.09, п.3): «Тип» отсутствовал в этом диалоге —
             каждая плановая позиция обязана нести признак товар/услуга/работа.
             «Всем: …» сверху — быстрый групповой выбор, per-row select — точечная
             правка (setRowItemType/setAllItemType в useItemsBulkFeo.ts). -->
        <div class="d-flex align-center ga-2 mb-2 flex-wrap">
          <span class="text-caption text-medium-emphasis">Всем:</span>
          <v-btn
            v-for="opt in ITEM_TYPE_OPTIONS"
            :key="opt.value"
            size="x-small"
            variant="tonal"
            color="primary"
            @click="emit('set-all-type', opt.value)"
          >{{ opt.title }}</v-btn>
        </div>
        <div class="bulk-create-table-wrap">
          <v-table density="compact" class="bulk-create-table">
            <thead>
              <tr>
                <th>Наименование</th>
                <th>Кол-во</th>
                <th>Сумма</th>
                <th>Категория ФЭО</th>
                <th style="width:160px">Тип</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.uid" :id="`plan-bulk-type-row-${row.uid}`">
                <td class="wrap-cell">
                  {{ row.name }}
                  <v-tooltip v-if="row.duplicateOf" location="top" :text="`Уже есть: «${row.duplicateOf.name}» — будет создана отдельная позиция`">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" icon="mdi-alert-outline" size="16" color="warning" class="ml-1" />
                    </template>
                  </v-tooltip>
                </td>
                <td class="wrap-cell">{{ row.quantity ?? '—' }} {{ row.unit }}</td>
                <td class="wrap-cell">{{ fmtRub(row.amount) }}</td>
                <td class="wrap-cell">{{ row.categoryName }}</td>
                <td style="min-width:150px">
                  <v-select
                    :model-value="row.itemType"
                    :items="ITEM_TYPE_OPTIONS"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :error="!row.itemType"
                    placeholder="Не указан"
                    @update:model-value="(v: string | null) => emit('set-row-type', row.idx, v)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
        <div v-if="missingTypeCount > 0" class="text-caption mt-1" style="color:#EF4444">
          Не указан тип: {{ missingTypeCount }}
          <a href="#" class="ml-1" @click.prevent="emit('show-missing-type')">показать</a>
        </div>
        <div v-if="loading || progress.total > 0" class="mt-3 d-flex align-center ga-2">
          <v-progress-circular v-if="loading" indeterminate size="18" width="2" color="primary" />
          <span class="text-caption">Создано {{ progress.done }} из {{ progress.total }}</span>
        </div>
        <div v-if="failures.length" class="mt-2 text-caption" style="color:#EF4444">
          <div>Не удалось создать/привязать:</div>
          <div v-for="(f, i) in failures" :key="i">{{ f }}</div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="loading" @click="emit('cancel')">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="loading" :disabled="rows.length === 0 || missingTypeCount > 0" @click="emit('confirm')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import { fmtRub } from '@/utils/numberFormat'
import { ITEM_TYPE_OPTIONS } from '@/composables/items/feoPlanned/useFeoPlannedCreate'

const { mobile } = useDisplay()

interface PlanCreateRow {
  idx: number
  uid: string | number
  name: string
  quantity: number | null
  unit: string
  amount: number | null
  categoryName: string
  duplicateOf: { id: number; name: string } | null
  itemType: string | null
}

const open = defineModel<boolean>({ default: false })

const props = defineProps<{
  loading?: boolean
  rows: PlanCreateRow[]
  noCategoryCount: number
  progress: { done: number; total: number }
  failures: string[]
}>()

// Жалоба владельца (29.09, п.3) — кнопка «Создать» недоступна, пока хоть у одной
// строки нет типа (тот же гейт, что и createPlannedBulkDisabled в
// useItemsBulkFeo.ts — дублируется здесь только для локального disabled на
// кнопке/подсветки строк, источник данных общий — props.rows).
const missingTypeCount = computed(() => props.rows.filter(r => !r.itemType).length)

const emit = defineEmits<{
  confirm: []
  cancel: []
  'set-row-type': [idx: number, value: string | null]
  'set-all-type': [value: string | null]
  'show-missing-type': []
}>()
</script>

<style scoped>
.bulk-create-table-wrap {
  overflow-x: auto;
}
.bulk-create-table :deep(th),
.bulk-create-table :deep(td) {
  white-space: normal;
  word-break: break-word;
  vertical-align: top;
}
.wrap-cell {
  min-width: 160px;
}
</style>
