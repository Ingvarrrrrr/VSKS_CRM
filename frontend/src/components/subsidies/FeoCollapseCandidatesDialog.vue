<template>
  <!-- Диалог предпросмотра массового сворачивания категорий-дублей в плановые
       позиции (владелец, задача 3) — открывается кнопкой «Свернуть категории-
       дубли (N)» в FeoTreeToolbar.vue. Состояние/API — useFeoCategoryCollapse.ts
       (Правило №6, единственный источник, тот же список кандидатов, что и у
       кнопки в FeoTreeRow.vue). -->
  <v-dialog v-model="feoCollapse.bulkDialogOpen.value" max-width="860" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1">
        Свернуть категории-дубли в плановые позиции
      </v-card-title>
      <v-card-subtitle class="text-caption">
        Категория без подкатегорий и ровно с одной плановой позицией с тем же именем —
        позиция переедет в родительскую категорию, сама категория исчезнет.
      </v-card-subtitle>
      <v-card-text>
        <div v-if="feoCollapse.candidatesLoading.value" class="d-flex align-center" style="gap:8px;padding:8px 0">
          <v-progress-circular indeterminate size="16" color="blue-grey" />
          <span class="text-caption">Загрузка кандидатов…</span>
        </div>
        <div v-else-if="!feoCollapse.candidates.value.length" class="text-center text-medium-emphasis py-6">
          Кандидатов на сворачивание нет
        </div>
        <div v-else class="fcc-scroll">
          <table class="fcc-table">
            <thead>
              <tr>
                <th style="width:28px"></th>
                <th>Категория</th>
                <th>Родитель</th>
                <th>Плановая позиция</th>
                <th class="text-right">ФЭО категории</th>
                <th class="text-right">Сумма позиции</th>
                <th>Причина блокировки</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in feoCollapse.candidates.value" :key="c.category_id" :class="{ 'fcc-row--blocked': !!c.blocked_reason }">
                <td>
                  <v-checkbox-btn
                    density="compact" color="blue-grey-darken-1"
                    :model-value="feoCollapse.bulkSelectedIds.value.has(c.category_id)"
                    :disabled="!!c.blocked_reason"
                    @update:model-value="feoCollapse.toggleBulkSelected(c.category_id)"
                  />
                </td>
                <td>
                  {{ c.name }}
                  <v-chip v-if="c.is_name_duplicate" size="x-small" color="teal" variant="tonal" class="ml-1">имя совпадает</v-chip>
                </td>
                <td>{{ c.parent_name || '—' }}</td>
                <td>{{ c.planned_item_name }}</td>
                <td class="text-right">{{ c.category_feo_amount != null ? formatCurrency(c.category_feo_amount) : '—' }}</td>
                <td class="text-right">{{ c.item_amount != null ? formatCurrency(c.item_amount) : '—' }}</td>
                <td class="text-caption text-error">{{ c.blocked_reason || '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="feoCollapse.bulkSubmitting.value" class="mt-3">
          <div class="text-caption text-medium-emphasis mb-1">
            Свёрнуто {{ feoCollapse.bulkProgressDone.value }} из {{ feoCollapse.bulkProgressTotal.value }}
          </div>
          <v-progress-linear
            :model-value="bulkProgressPercent"
            color="blue-grey-darken-1" height="6" rounded
          />
        </div>
        <div v-if="failedResults.length" class="mt-3">
          <div class="text-caption font-weight-medium text-error mb-1">Не удалось свернуть ({{ failedResults.length }}):</div>
          <div v-for="r in failedResults" :key="r.category_id" class="text-caption text-error">
            #{{ r.category_id }} — {{ r.error || 'ошибка' }}
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="feoCollapse.bulkSubmitting.value" @click="feoCollapse.closeBulkDialog()">Отмена</v-btn>
        <v-btn color="blue-grey-darken-1" variant="flat"
          :loading="feoCollapse.bulkSubmitting.value"
          :disabled="!feoCollapse.bulkSelectedIds.value.size || feoCollapse.bulkSubmitting.value"
          @click="onSubmit"
        >Свернуть выбранные ({{ feoCollapse.bulkSelectedIds.value.size }})</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Таблица кандидатов + подтверждение массового сворачивания — вынесена
// отдельным компонентом (Правило №5, FeoTreeToolbar.vue и так плотный).
import { computed } from 'vue'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'

const ctx = useSubsidyDetailCtx()
const feoCollapse = useFeoCategoryCollapse()

const failedResults = computed(() => feoCollapse.bulkResults.value.filter(r => !r.ok))
const bulkProgressPercent = computed(() => {
  const total = feoCollapse.bulkProgressTotal.value
  return total > 0 ? (feoCollapse.bulkProgressDone.value / total) * 100 : 0
})

async function onSubmit() {
  const ok = await feoCollapse.submitBulkCollapse()
  if (ok && ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
}
</script>

<style scoped>
.fcc-scroll { max-height: 420px; overflow-y: auto; }
.fcc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.fcc-table th {
  position: sticky; top: 0; background: #F8FAFC;
  text-align: left; padding: 6px 8px; border-bottom: 1px solid #E2E8F0;
  color: #64748b; font-weight: 600; z-index: 1;
}
.fcc-table td { padding: 6px 8px; border-bottom: 1px solid #F1F5F9; vertical-align: middle; }
.fcc-row--blocked { opacity: 0.6; }
</style>
