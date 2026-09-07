<template>
  <!-- ── Level 5 панель: Плановые vs Фактические ──
       Условие расширено (!node.hasChildren || hasOwnPlannedAmountFor(node)) — у
       направления панель раскрывается, только если есть чем её наполнить. -->
  <tr v-if="(!node.hasChildren || ctx.hasOwnPlannedAmountFor(node)) && ctx.expandedItemPanels.value.has(node.id)" :data-feo-panel-for="node.id">
    <td colspan="7" style="padding:0">
      <div style="padding:10px 0 12px 0">
        <div class="d-flex align-center mb-2" style="gap:8px">
          <v-btn v-if="ctx.displayPlannedRowsFor(node).length > 1" size="x-small" variant="text" color="teal"
            :prepend-icon="ctx.anyPlannedExpandedFor(node) ? 'mdi-arrow-collapse-vertical' : 'mdi-arrow-expand-vertical'"
            @click="ctx.toggleAllPlannedItemsForCategory(node)"
          >{{ ctx.anyPlannedExpandedFor(node) ? 'Свернуть всё' : 'Развернуть всё' }}</v-btn>
          <v-spacer />
          <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-plus"
            @click="ctx.openAddPlannedItem(node.id)">
            Добавить плановую
          </v-btn>
        </div>

        <div v-if="ctx.loadingComparison.value.has(node.id)" class="d-flex align-center" style="gap:8px;padding:8px 0">
          <v-progress-circular indeterminate size="16" color="teal" />
          <span class="text-caption">Загрузка...</span>
        </div>

        <table v-else-if="ctx.comparisonData.value[node.id]" style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
          <thead>
            <tr>
              <th :style="[feoResize.resizeStyle('name'), { paddingLeft: `${ctx.plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;text-align:left;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE" title="Плановая позиция. Закупки, привязанные к ней (как выставили в закупку / как в договоре — по стадии), — в раскрывающемся блоке под строкой плана.">
                Позиция плана
              </th>
              <th :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Плановая цена за единицу</th>
              <th :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Кол-во плана</th>
              <th :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Сумма плана</th>
              <th style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Тип</th>
              <th :style="feoResize.resizeStyle('spent')" style="border-bottom:1px solid #BFDBFE"></th>
              <th :style="feoResize.resizeStyle('residual')" style="border-bottom:1px solid #BFDBFE"></th>
              <th style="width:112px;min-width:112px;max-width:112px;padding:4px 2px;border-bottom:1px solid #BFDBFE"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(planned, pIdx) in ctx.displayPlannedRowsFor(node)" :key="`p-${planned.id}`">
              <tr style="border-bottom:1px solid #E5E7EB">
                <td :style="[feoResize.resizeStyle('name'), { paddingLeft: `${ctx.plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;color:#0c4a6e">
                  <div class="d-flex align-center" style="gap:2px">
                    <v-btn
                      :icon="ctx.expandedPlannedItems.value.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      variant="text" density="compact" size="x-small" color="teal"
                      title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                      @click="ctx.togglePlannedItemFolder(planned.id)"
                    />
                    <span>{{ planned.name }}</span>
                    <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                      title="Это плановая позиция — она запланирована, а не выставлена в закупку и не приехала по факту"
                    >план</v-chip>
                    <v-chip v-if="node.hasChildren" size="x-small" color="grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                      title="Позиция привязана к направлению, а не к конечной категории. Её можно перенести вниз, в подходящую категорию — суммы при этом не изменятся."
                    >на направлении целиком</v-chip>
                    <v-chip v-if="!planned.isManual && planned.is_feo_breakdown" size="x-small" color="green" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                      title="По ФЭО — жёсткая построчная разбивка ФЭО, покупать будут именно это, отчётность строгая"
                    >по ФЭО</v-chip>
                    <v-chip v-if="!planned.isManual && planned.is_internal_plan" size="x-small" color="amber-darken-3" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                      title="Внутренний план — в ФЭО была более широкая категория (или позиции не было вовсе), состав определили сами"
                    >внутренний план</v-chip>
                  </div>
                  <div v-if="planned.isManual" class="feo-plan-note text-medium-emphasis">
                    <v-icon icon="mdi-pencil-ruler" size="11" class="mr-1" />ручной план ФЭО — подробного деления в ФЭО не было
                  </div>
                  <div v-if="planned.amount != null" class="text-medium-emphasis" style="font-size:10px;line-height:1.3;white-space:normal">
                    {{ ctx.planBreakdownText(node.id, planned) }}
                  </div>
                </td>
                <td :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#64748b">
                  <span v-if="planned.unit_price != null">{{ formatCurrency(Number(planned.unit_price)) }}</span>
                  <span v-else-if="planned.amount != null" class="text-medium-emphasis" style="font-size:10px;line-height:1.3">{{ UNIT_PRICE_NOT_FIXED_HINT }}</span>
                </td>
                <td :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#64748b">
                  <span v-if="planned.quantity">{{ parseFloat(String(planned.quantity)) }} {{ planned.unit || '' }}</span>
                </td>
                <td :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#64748b">
                  <span v-if="planned.amount">{{ formatCurrency(planned.amount) }}</span>
                </td>
                <td style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#64748b">
                  <span
                    v-if="planned.item_type_inherited"
                    class="text-medium-emphasis"
                    title="Тип взят из позиций закупок — у самой плановой позиции он не задан"
                  >{{ planned.item_type_effective }}</span>
                  <span v-else>{{ planned.item_type_effective || '—' }}</span>
                </td>
                <td :style="feoResize.resizeStyle('spent')"></td>
                <td :style="feoResize.resizeStyle('residual')"></td>
                <td style="width:112px;min-width:112px;max-width:112px;padding:2px;text-align:center">
                  <div class="d-flex align-center flex-wrap justify-center" style="gap:0">
                    <template v-if="!planned.isManual">
                      <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                        :disabled="pIdx === 0"
                        :loading="ctx.reorderingPlannedItemId.value === planned.id"
                        title="Переместить выше"
                        @click.stop="ctx.reorderPlannedItem(node, pIdx, 'up')"
                      />
                      <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                        :disabled="pIdx === ctx.displayPlannedRowsFor(node).length - 1"
                        :loading="ctx.reorderingPlannedItemId.value === planned.id"
                        title="Переместить ниже"
                        @click.stop="ctx.reorderPlannedItem(node, pIdx, 'down')"
                      />
                    </template>
                  </div>
                  <v-btn
                    size="x-small" variant="text" color="teal" class="text-none"
                    :prepend-icon="ctx.expandedPlannedItems.value.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                    title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                    @click="ctx.togglePlannedItemFolder(planned.id)"
                  >План vs факт</v-btn>
                  <template v-if="!planned.isManual">
                    <v-menu v-if="node.hasChildren" location="bottom end">
                      <template #activator="{ props: moveMenuProps }">
                        <v-btn v-bind="moveMenuProps" icon="mdi-arrow-down-bold-box-outline"
                          size="x-small" variant="text" color="orange-darken-1"
                          :loading="ctx.movingPlannedItemId.value === planned.id"
                          title="Перенести позицию вниз, в подходящую конечную категорию — суммы не изменятся"
                        />
                      </template>
                      <v-list density="compact" max-height="320" style="overflow-y:auto">
                        <v-list-subheader>Перенести в категорию</v-list-subheader>
                        <v-list-item v-for="d in ctx.descendantCategoriesFor(node)" :key="d.id"
                          :title="d.name"
                          :style="{ paddingLeft: `${8 + (d.depth - node.depth - 1) * 16}px` }"
                          @click="ctx.movePlannedItemToCategory(planned, d.id)"
                        />
                      </v-list>
                    </v-menu>
                    <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                      title="Редактировать плановую позицию"
                      @click="ctx.openEditPlannedItem(planned)"
                    />
                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                      title="Удалить плановую позицию"
                      :loading="ctx.deletingPlannedItemId.value === planned.id"
                      @click="ctx.deletePlannedItem(planned)"
                    />
                  </template>
                  <template v-else>
                    <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                      title="Редактировать план категории — количество, цена за единицу, единица измерения"
                      @click="ctx.openEditCategoryPlan(node)"
                    />
                    <v-btn icon="mdi-playlist-plus" size="x-small" variant="text" color="teal"
                      title="Завести плановую позицию — именованный товар/услуга вместо строки категории; количество и цена берутся из плана листа, факты привяжутся к ней автоматически"
                      @click="ctx.openConvertManualPlanToItem(node)"
                    />
                  </template>
                </td>
              </tr>
              <tr v-if="ctx.expandedPlannedItems.value.has(planned.id)">
                <td colspan="8" style="padding:0">
                  <div style="margin:10px 8px 12px 32px;padding:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px">
                  <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                    <thead>
                      <tr>
                        <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" :title="ctx.factStageHeaderFor(node.id, planned.id) === 'Позиция закупки' ? 'Закупки этой плановой позиции сейчас на разных стадиях — стадия каждой подписана на её строке' : ''">
                          {{ ctx.factStageHeaderFor(node.id, planned.id) }}
                        </th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Цена</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма</th>
                        <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" title="Реальные закупки, привязанные к этой плановой позиции — что действительно куплено или заказано">ФАКТ (из закупок)</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Цена (факт)</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:90px">Кол-во (факт)</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:110px">Сумма (факт)</th>
                        <th style="padding:4px 8px;text-align:right;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:100px">Разница</th>
                        <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:120px">Контрагент</th>
                        <th style="padding:4px 8px;text-align:center;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4;width:80px">Статус</th>
                        <th style="padding:4px 2px;width:80px;border-bottom:1px solid #99F6E4"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="!ctx.factForPlanned(node.id, planned.id).length">
                        <td colspan="12" style="padding:8px 8px;color:#94a3b8;font-style:italic">Закупок по этой плановой позиции пока нет</td>
                      </tr>
                      <template v-for="actual in ctx.factForPlanned(node.id, planned.id)" :key="`pa-${actual.purchase_item_id}`">
                        <tr
                          :class="ctx.kpiItemRowClass(actual)"
                          :data-item-id="actual.purchase_item_id" data-item-group="planned"
                          style="border-bottom:1px solid #E2E8F0">
                          <td style="padding:4px 8px;color:#0c4a6e">
                            {{ leftGroupInfo(actual).name }}
                            <v-chip size="x-small" :color="ctx.stageChipColorFor(actual.purchase_status)" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                              :title="ctx.stageChipTitleFor(actual.purchase_status)"
                            >{{ ctx.stageChipLabelFor(actual.purchase_status) }}</v-chip>
                          </td>
                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).unitPrice != null ? formatCurrency(leftGroupInfo(actual).unitPrice!) : '—' }}</td>
                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).quantity != null ? `${parseFloat(String(leftGroupInfo(actual).quantity))} ${leftGroupInfo(actual).unit || ''}` : '—' }}</td>
                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).total != null ? formatCurrency(leftGroupInfo(actual).total!) : '—' }}</td>
                          <td style="padding:4px 8px 4px 24px;color:#166534">
                            <div class="d-flex align-center" style="gap:6px">
                              <v-btn v-if="(actual.stages?.length || 0) >= 2"
                                :icon="ctx.expandedStageRows.value.has(`pa-${actual.purchase_item_id}`) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                variant="text" density="compact" size="x-small" color="teal"
                                title="Показать стадии уточнения позиции"
                                @click.stop="ctx.toggleStageRow(`pa-${actual.purchase_item_id}`)"
                              />
                              <v-avatar v-if="actual.product_photo" size="24" rounded class="flex-shrink-0" style="cursor:pointer"
                                @click.stop="ctx.photoPreview.value = { src: actual.product_photo!, title: actual.item_name }">
                                <v-img :src="actual.product_photo" cover />
                              </v-avatar>
                              <div>{{ actual.item_name }}</div>
                              <v-chip v-if="ctx.isExcessCulpritActual(node, actual)" size="x-small" color="red" variant="flat" class="ml-1"
                                style="font-size:9px;height:16px" :title="ctx.excessCulpritChipTooltip(node)"
                              ><v-icon icon="mdi-alert-decagram" size="10" class="mr-1" />из-за неё превышение</v-chip>
                            </div>
                            <a
                              href="javascript:void(0)"
                              class="feo-purchase-link"
                              :title="`Перейти в закупку #${actual.purchase_id}`"
                              @click.stop="ctx.router.push(`/orders/${actual.purchase_id}`)"
                            >
                              <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                              {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                            </a>
                            <a v-if="actual.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                              title="Перейти к заявкам"
                              @click.stop="ctx.router.push('/wishes')"
                            >
                              <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ actual.wish_id }}
                            </a>
                            <div v-if="actual.stopped_at" class="feo-stopped-marker mt-1">
                              <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ ctx.feoStoppedLine(actual) }}
                            </div>
                          </td>
                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.fact_amount != null && actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ actual.fact_amount != null && actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                          <td style="padding:4px 8px;text-align:right;font-weight:500">
                            <template v-if="actual.fact_amount != null">
                              <span :title="actual.fact_allocated ? 'Распределено пропорционально между позициями закупки' : ''">{{ formatCurrency(actual.fact_amount) }}</span>
                              <v-chip v-if="!actual.fact_confirmed" size="x-small" variant="tonal" color="warning" class="ml-1" style="font-size:9px;height:16px"
                                title="Сумма по договору — закрывающими документами (актом приёмки) ещё не подтверждена"
                              >по договору</v-chip>
                            </template>
                            <span v-else class="text-medium-emphasis" style="font-style:italic;font-weight:400">{{ purchaseStatusLabel(actual.purchase_status) }}</span>
                          </td>
                          <td style="padding:4px 8px"></td>
                          <td style="padding:4px 8px;color:#64748b;font-size:11px">{{ actual.contractor_name || '—' }}</td>
                          <td style="padding:4px 8px;text-align:center;color:#94a3b8;font-size:10px">
                            {{ purchaseStatusLabel(actual.purchase_status) }}
                          </td>
                          <td style="padding:2px;text-align:center;white-space:nowrap">
                            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                              title="Редактировать позицию закупки"
                              @click="ctx.openReqItemEditFromActual(node, actual)"
                            />
                            <v-btn icon="mdi-link-off" size="x-small" variant="text" color="grey"
                              title="Снять сопоставление"
                              @click="() => { ctx.mapTarget.value = actual; ctx.mapCategoryId.value = node.id; ctx.applyMapping(null) }"
                            />
                          </td>
                        </tr>
                        <template v-if="ctx.expandedStageRows.value.has(`pa-${actual.purchase_item_id}`)">
                        <tr v-for="sr in ctx.stagesWithDiff(actual.stages)" :key="`pa-stage-${actual.purchase_item_id}-${sr.stage.key}`"
                          style="border-bottom:1px solid #E2E8F0">
                          <td style="padding:2px 8px 2px 40px;color:#94a3b8;font-size:10px">{{ sr.stage.label }}</td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px" :style="sr.nameChanged ? 'color:#4F46E5' : ''">{{ sr.stage.name }}</td>
                          <td style="padding:2px 8px;text-align:right;color:#64748b">
                            {{ sr.stage.unit_price != null ? formatCurrency(sr.stage.unit_price) : '—' }}
                            <div v-if="sr.priceDeltaLabel" style="font-size:10px" :style="`color:${sr.priceDeltaColor}`">{{ sr.priceDeltaLabel }}</div>
                          </td>
                          <td style="padding:2px 8px;text-align:right;color:#64748b">
                            {{ sr.stage.quantity != null ? `${parseFloat(String(sr.stage.quantity))} ${sr.stage.unit || ''}` : '—' }}
                            <div v-if="sr.qtyDeltaLabel" style="font-size:10px" :style="`color:${sr.qtyDeltaColor}`">{{ sr.qtyDeltaLabel }}</div>
                          </td>
                          <td style="padding:2px 8px;text-align:right;color:#64748b">{{ sr.stage.total != null ? formatCurrency(sr.stage.total) : '—' }}</td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px"></td>
                          <td style="padding:2px 8px"></td>
                        </tr>
                        </template>
                      </template>
                    </tbody>
                  </table>
                  </div>
                </td>
              </tr>
            </template>

            <tr v-if="!ctx.displayPlannedRowsFor(node).length && !ctx.comparisonData.value[node.id]!.actual.length">
              <td colspan="8" style="padding:12px 8px;text-align:center;color:#9ca3af;font-style:italic">
                Нет плановых позиций. Добавьте вручную или загрузите из Excel.
              </td>
            </tr>
          </tbody>
          <tfoot v-if="ctx.displayPlannedRowsFor(node).length || ctx.comparisonData.value[node.id]!.actual.length">
            <tr style="background:rgba(34,197,94,0.08);font-weight:600;border-top:2px solid rgba(34,197,94,0.3)">
              <td :style="{ paddingLeft: `${ctx.plannedItemIndentPx(node)}px` }" style="padding-top:4px;padding-right:8px;padding-bottom:4px" class="text-success">ИТОГО</td>
              <td style="padding:4px 8px"></td>
              <td style="padding:4px 8px"></td>
              <td style="padding:4px 8px;text-align:right">
                {{ formatCurrency(ctx.comparisonPlanTotal(node)) }}
              </td>
              <td style="padding:4px 8px"></td>
            </tr>
          </tfoot>
        </table>

      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
// Level 5 дерева ФЭО — панель «Плановые позиции vs Фактические». Вынесена из
// SubsidiesView.vue (волна 5c); соседний <tr> с основной строкой узла — см.
// FeoTreeRow.vue. Формулы/состояние — composables/subsidies/useFeoLevel5.ts
// (Правило №6), здесь только вёрстка.
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import { leftGroupInfo } from '@/composables/subsidies/feoCategoryUtils'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import type { FeoNode } from '@/composables/subsidies/types'

const props = defineProps<{ node: FeoNode }>()
const node = props.node

const ctx = useSubsidyDetailCtx()
// useResizableColumns() НЕ singleton — создаёт новый colWidths при каждом вызове
// (см. её докстринг). Единственный экземпляр 'feo-table' живёт в SubsidiesView.vue
// и приходит через ctx.feoResize — иначе у каждого узла была бы своя, не связанная
// с основной таблицей ширина колонок (см. комментарий в FeoTreeTable.vue).
const feoResize = ctx.feoResize
</script>
