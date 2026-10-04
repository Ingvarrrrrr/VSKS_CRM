<template>
  <!-- «Что ещё заказать» (владелец, 04.10.2026) — плановые позиции субсидии,
       у которых остаток «не заказано» > 0,5 ₽, сгруппированные по «нужности»
       и внутри — по товарам/услугам. Кнопка открытия — FeoTreeToolbar.vue.
       Состояние/данные — usePlanToOrderDialog.ts (Правило №6). -->
  <v-dialog :model-value="p.show.value" max-width="760" :fullscreen="mobile" scrollable
    @update:model-value="(v: boolean) => { if (!v) p.closePlanToOrderDialog() }">
    <v-card>
      <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-cart-outline" color="deep-purple" class="mr-2" />
        <span>Что ещё заказать{{ p.subsidyName.value ? ` — ${p.subsidyName.value}` : '' }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="p.closePlanToOrderDialog()" />
      </v-card-title>
      <v-card-text class="px-4 pb-4" style="max-height:72vh">
        <div v-if="p.loading.value" class="d-flex align-center justify-center py-8">
          <v-progress-circular indeterminate color="deep-purple" class="mr-2" />
          <span class="text-body-2 text-medium-emphasis">Загрузка плановых позиций…</span>
        </div>
        <v-alert v-else-if="p.error.value" type="error" variant="tonal" density="compact">
          {{ p.error.value }}
          <template #append>
            <v-btn size="small" variant="text" color="error" @click="p.reload()">Повторить</v-btn>
          </template>
        </v-alert>
        <div v-else-if="!p.groups.value.length && p.unlinkedAmount.value == null" class="text-body-2 text-medium-emphasis py-6 text-center">
          Нечего заказывать — все плановые позиции с остатком уже выбраны закупками.
        </div>
        <template v-else>
          <div class="text-caption text-medium-emphasis mb-3">
            Итого без договоров: <b>{{ formatCurrency(p.grandTotalAmount.value) }}</b>
          </div>
          <div v-for="group in p.groups.value" :key="group.needLevel" class="plan-to-order-group mb-4">
            <div class="d-flex align-center plan-to-order-group__title">
              <v-chip
                size="small" variant="tonal"
                :color="group.needLevel === 'nice_to_have' ? 'deep-orange' : 'blue-grey'"
              >{{ group.label }}</v-chip>
              <span class="text-caption text-medium-emphasis ml-2">{{ formatCurrency(group.totalAmount) }}</span>
            </div>
            <div v-for="kindGroup in group.kinds" :key="kindGroup.kind" class="plan-to-order-kind mt-2">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-1">
                {{ kindGroup.label }} · {{ formatCurrency(kindGroup.totalAmount) }}
              </div>
              <div class="plan-to-order-table-wrap">
                <table class="plan-to-order-table">
                  <thead>
                    <tr>
                      <th>Позиция</th>
                      <th>Направление ФЭО</th>
                      <th class="text-right">Без договоров</th>
                      <th>Тип</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in kindGroup.rows" :key="row.key" class="plan-to-order-row" @click="goTo(row)">
                      <td>{{ row.name }}</td>
                      <td class="text-medium-emphasis plan-to-order-path" :title="row.path">{{ lastPathSegment(row.path) }}</td>
                      <td class="text-right">
                        <div>{{ formatCurrency(row.residualAmount) }}</div>
                        <div v-if="row.residualQuantity" class="text-caption text-medium-emphasis">
                          {{ row.residualQuantity }} {{ row.unit || '' }}
                        </div>
                      </td>
                      <td>{{ KIND_LABELS[row.itemKind] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <!-- Строка сверки (владелец 04.10.2026) — остаток разницы между итогом
               карточки и Σ строк (заявки без плановой позиции и т.п.), см.
               docstring unlinkedAmount в usePlanToOrderDialog.ts — не новая
               формула, просто остаток, который строками не объяснён. -->
          <div v-if="p.unlinkedAmount.value != null" class="text-caption text-medium-emphasis plan-to-order-unlinked">
            Не привязано к позициям (заявки без плановой позиции и т.п.): {{ formatCurrency(p.unlinkedAmount.value) }}
          </div>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { usePlanToOrderDialog, type PlanToOrderRow } from '@/composables/subsidies/usePlanToOrderDialog'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import { KIND_LABELS } from '@/utils/itemTypeKind'

const { mobile } = useDisplay()
const p = usePlanToOrderDialog()
const ctx = useSubsidyDetailCtx()

// Клик по строке — закрыть окно и подсветить позицию в дереве ФЭО тем же
// механизмом, что и поиск по субсидии (useFeoTreeSearch.ts::goToFeoSearchResult,
// Правило №6 — второй scroll/highlight не заводим). kind='plan_position'/
// 'feo_article' (план введён прямо на листе дерева, без отдельной
// FeoPlannedItem) — это категория целиком, см. FeoSearchResult.kind='category'.
// Колонка «Направление ФЭО» (владелец 04.10.2026) — путь по дереву занимал по
// 4 строки на каждую позицию; показываем только последний сегмент (сама
// позиция/лист), полный путь — в title (tooltip при наведении), разделитель
// пути — тот же '›', что строит backend build_category_path.
function lastPathSegment(path: string): string {
  const parts = path.split('›').map(s => s.trim()).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : path
}

async function goTo(row: PlanToOrderRow) {
  p.closePlanToOrderDialog()
  const isPlannedItem = row.kind === 'planned_item'
  await ctx.goToFeoSearchResult({
    key: row.key,
    kind: isPlannedItem ? 'planned_item' : 'category',
    id: isPlannedItem ? row.id : row.categoryId,
    name: row.name,
    path: row.path,
    categoryId: row.categoryId,
  })
}
</script>

<style scoped>
.plan-to-order-group__title { gap: 4px; }
.plan-to-order-table-wrap { overflow-x: auto; }
.plan-to-order-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.plan-to-order-table th {
  text-align: left;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.6);
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  padding: 4px 6px;
  white-space: nowrap;
}
.plan-to-order-table td {
  padding: 4px 6px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  vertical-align: top;
}
.plan-to-order-row { cursor: pointer; }
.plan-to-order-row:hover { background: rgba(103, 58, 183, 0.06); }
/* «Направление ФЭО» — компактно, последний сегмент пути, полный путь в title
   (владелец 04.10.2026: было по 4 строки на каждую позицию). */
.plan-to-order-path {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plan-to-order-unlinked { margin-top: 4px; }
</style>
