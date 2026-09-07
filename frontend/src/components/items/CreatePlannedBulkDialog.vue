<template>
  <!-- Общая кнопка «Создать в плане закупок» (владелец 2026-08-06) — создаёт плановые
       позиции (Ур.5 FeoPlannedItem) сразу для ВСЕХ позиций, у которых заполнена категория
       ФЭО, но нет привязки к плановой позиции, каждую в своей категории. Presentational —
       parent owns needPlanRows/progress/failures and the actual create loop.
       Extracted from PurchaseItemsEditor.vue. -->
  <v-dialog v-model="open" max-width="640" :persistent="loading">
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
        <v-table density="compact">
          <thead>
            <tr>
              <th>Наименование</th>
              <th>Кол-во</th>
              <th>Сумма</th>
              <th>Категория ФЭО</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.uid">
              <td>
                {{ row.name }}
                <v-tooltip v-if="row.duplicateOf" location="top" :text="`Уже есть: «${row.duplicateOf.name}» — будет создана отдельная позиция`">
                  <template #activator="{ props: tip }">
                    <v-icon v-bind="tip" icon="mdi-alert-outline" size="16" color="warning" class="ml-1" />
                  </template>
                </v-tooltip>
              </td>
              <td>{{ row.quantity ?? '—' }} {{ row.unit }}</td>
              <td>{{ fmtRub(row.amount) }}</td>
              <td>{{ row.categoryName }}</td>
            </tr>
          </tbody>
        </v-table>
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
        <v-btn color="primary" variant="flat" :loading="loading" :disabled="rows.length === 0" @click="emit('confirm')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { fmtRub } from '@/utils/numberFormat'

interface PlanCreateRow {
  uid: string | number
  name: string
  quantity: number | null
  unit: string
  amount: number | null
  categoryName: string
  duplicateOf: { id: number; name: string } | null
}

const open = defineModel<boolean>({ default: false })

defineProps<{
  loading?: boolean
  rows: PlanCreateRow[]
  noCategoryCount: number
  progress: { done: number; total: number }
  failures: string[]
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>
