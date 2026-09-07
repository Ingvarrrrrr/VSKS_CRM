<template>
  <template v-for="row in ctx.reqItemRowsFor(owner)" :key="`req-${owner.id}-${row.key}`">
    <tr
      class="feo-tr feo-req-row"
      :class="ctx.kpiReqRowClass(row)"
      :data-item-ids="row.group ? row.group.items.map(i => i.id).join(',') : ''"
      data-item-group="owner-virtual"
      :style="row.group ? 'background:rgba(20,184,166,0.04)' : 'background:rgba(20,184,166,0.10)'"
    >
      <td class="feo-td feo-td-name" :style="{ paddingLeft: ctx.reqRowIndent(owner, row) }">
        <div class="feo-name-inner">
          <template v-if="!row.group">
            <v-icon size="14" class="mr-1 flex-shrink-0"
              :icon="row.level === 1 ? 'mdi-shape-outline' : 'mdi-tag-outline'"
              :color="row.level === 1 ? '#0D9488' : '#64748B'" />
            <span :style="row.level === 1 ? 'font-weight:600;font-size:12px' : 'font-weight:500;font-size:12px;color:#475569'">{{ row.header }}</span>
            <span class="feo-code ml-2">{{ row.count }} поз.</span>
          </template>
          <template v-else>
            <span style="width:16px;display:inline-block" />
            <v-icon size="16" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
            <v-avatar v-if="row.group.items.find(i => i.product_photo)" size="28" rounded class="mr-1 flex-shrink-0" style="cursor:pointer"
              @click.stop="ctx.photoPreview.value = { src: row.group.items.find(i => i.product_photo)!.product_photo!, title: row.group.name }">
              <v-img :src="row.group.items.find(i => i.product_photo)!.product_photo!" cover />
            </v-avatar>
            <span class="feo-status-strip mr-1">
              <v-icon v-for="gs in ctx.groupStatuses(row.group).slice(0, 3)" :key="gs.status"
                :icon="purchaseStatusIcon(gs.status)" :color="purchaseStatusColor(gs.status)" size="13"
                :title="`${gs.label} — ${gs.count} поз.`" class="mr-1" />
            </span>
            <span class="feo-name feo-name--l3">{{ row.group.name }}</span>
            <span v-if="row.group.items.length > 1" class="feo-code ml-2"
              title="Слито из нескольких позиций заявок">{{ row.group.items.length }} поз. в заявках</span>
          </template>
        </div>
      </td>
      <!-- Финансирование по ФЭО: не задавалось -->
      <td class="feo-td feo-td-num">
        <span v-if="row.group" class="feo-amount-empty"
          title="Эта позиция не задавалась в ФЭО — заведена через заявку">—</span>
      </td>
      <!-- Плановое кол-во: снимок ТЗ (planned_quantity), НЕ текущее кол-во. -->
      <td class="feo-td feo-td-num">
        <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ row.group ? ctx.groupPlannedQty(row.group) : row.sumQty }}{{ row.group?.unit ? ` ${row.group.unit}` : '' }}</span>
        <div v-if="row.group" class="feo-plan-note text-medium-emphasis">из заявок</div>
      </td>
      <!-- Плановая сумма: снимок ТЗ (planned_total), не съезжает при правке итоговой цены -->
      <td class="feo-td feo-td-num">
        <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ formatCurrency(row.group ? ctx.groupPlannedTotal(row.group) : row.sum) }}</span>
        <div v-if="row.group && row.group.items.length === 1 && (row.group.items[0]!.planned_unit_price ?? row.group.items[0]!.unit_price)"
          class="feo-plan-note text-medium-emphasis">{{ formatCurrency(row.group.items[0]!.planned_unit_price ?? row.group.items[0]!.unit_price) }}/ед.</div>
      </td>
      <!-- Фактическая сумма: реальный факт (ContractItem/contract_price), а не заглушка. -->
      <td class="feo-td feo-td-num">
        <span v-if="row.group && ctx.groupFactTotal(row.group) != null" class="feo-amount" style="font-size:12px">{{ formatCurrency(ctx.groupFactTotal(row.group)!) }}</span>
        <span v-else-if="row.group" class="feo-amount-empty" title="Итог закупки/договора ещё не известен">—</span>
      </td>
      <td class="feo-td feo-td-num"><span v-if="row.group" class="feo-amount-empty">—</span></td>
      <td class="feo-td feo-td-actions">
        <div v-if="row.group" class="d-flex align-center justify-end">
          <v-btn
            :icon="ctx.expandedReqItemPanels.value.has(ctx.reqPanelKey(owner, row.group)) ? 'mdi-list-box' : 'mdi-list-box-outline'"
            variant="text" size="x-small"
            :color="ctx.expandedReqItemPanels.value.has(ctx.reqPanelKey(owner, row.group)) ? 'teal' : 'grey'"
            title="Источники: план vs факт по этой позиции"
            @click="ctx.toggleReqItemPanel(owner, row.group)"
          />
          <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
            :title="ctx.virtGroupPurchaseIds(row.group).length === 1 ? 'Открыть закупку' : 'Несколько закупок — открыть источники'"
            @click.stop="ctx.virtCart(owner, row.group)" />
          <v-btn icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
            :title="row.group.items.length === 1 ? 'Редактировать позицию закупки' : 'Несколько позиций — открыть источники'"
            @click="ctx.virtEdit(owner, row.group)" />
          <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error"
            :title="row.group.items.length === 1 ? 'Удалить позицию из закупки' : 'Несколько позиций — открыть источники'"
            @click="ctx.virtDelete(owner, row.group)" />
        </div>
      </td>
    </tr>

    <!-- Панель источников: план vs факт по каждой позиции заявки -->
    <tr v-if="row.group && ctx.expandedReqItemPanels.value.has(ctx.reqPanelKey(owner, row.group))">
      <td colspan="7" style="padding:0;background:rgba(20,184,166,0.08)">
        <div :style="{ padding: '8px 12px 10px', marginLeft: ctx.reqRowIndent(owner, row) }">
          <div class="d-flex align-center mb-1" style="gap:6px">
            <v-icon icon="mdi-compare-horizontal" size="14" color="teal" />
            <span style="font-size:11px;font-weight:600" class="text-teal-darken-2">Позиции: план vs факт</span>
          </div>
          <div v-if="ctx.loadingComparison.value.has(owner.id)" class="d-flex align-center" style="gap:8px;padding:4px 0">
            <v-progress-circular indeterminate size="14" color="teal" />
            <span class="text-caption">Загрузка...</span>
          </div>
          <table v-else style="width:100%;border-collapse:collapse;font-size:11px;background:#fff">
            <thead>
              <tr style="background:#CCFBF1">
                <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600">Название (из ТЗ)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Кол-во (из ТЗ)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Цена (из ТЗ)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:110px">Сумма (из ТЗ)</th>
                <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600">ФАКТ (из закупок)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Кол-во (факт)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:90px">Цена (факт)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:110px">Сумма (факт)</th>
                <th style="padding:3px 8px;text-align:right;color:#0f766e;font-weight:600;width:100px">Разница</th>
                <th style="padding:3px 8px;text-align:left;color:#0f766e;font-weight:600;width:120px">Контрагент</th>
                <th style="padding:3px 8px;text-align:center;color:#0f766e;font-weight:600;width:80px">Статус</th>
                <th style="padding:3px 2px;width:80px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in row.group.items" :key="`src-${it.id}`" :class="ctx.kpiItemRowClass(it)" :data-item-id="it.id" data-item-group="owner-virtual-source" style="border-bottom:1px solid #E0F2FE">
                <td style="padding:4px 8px;color:#0c4a6e">
                  <div class="d-flex align-center" style="gap:6px">
                    <v-avatar v-if="it.product_photo" size="28" rounded class="flex-shrink-0" style="cursor:pointer"
                      @click.stop="ctx.photoPreview.value = { src: it.product_photo!, title: it.item_name }">
                      <v-img :src="it.product_photo" cover />
                    </v-avatar>
                    <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="purchaseStatusLabel(it.purchase_status)" />
                    <div>{{ it.item_name }}</div>
                  </div>
                  <div class="d-flex align-center flex-wrap" style="gap:8px">
                    <a href="javascript:void(0)" class="feo-purchase-link"
                      :title="`Перейти в закупку #${it.purchase_id}`"
                      @click.stop="ctx.router.push(`/orders/${it.purchase_id}`)"
                    >
                      <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                      {{ it.registry_number || (it.purchase_number != null ? `№ ${it.purchase_number}` : `Закупка #${it.purchase_id}`) }}
                    </a>
                    <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                      title="Перейти к заявкам"
                      @click.stop="ctx.router.push('/wishes')"
                    >
                      <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}
                    </a>
                  </div>
                  <div v-if="ctx.reqItemPlanned(owner.id, it.id)" class="feo-plan-note text-medium-emphasis">
                    сопоставлено с плановой «{{ ctx.reqItemPlanned(owner.id, it.id)?.name }}»
                  </div>
                </td>
                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.planned_quantity ?? it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</td>
                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ (it.planned_unit_price ?? it.unit_price) ? formatCurrency(it.planned_unit_price ?? it.unit_price) : '—' }}</td>
                <td style="padding:4px 8px;text-align:right;font-weight:500">{{ formatCurrency(it.planned_total ?? it.total_price) }}</td>
                <td style="padding:4px 8px;color:#9ca3af;font-style:italic">{{ it.fact_amount != null ? '' : 'ещё не поставлено' }}</td>
                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null ? `${it.fact_quantity ?? it.planned_quantity ?? it.quantity}${it.unit ? ` ${it.unit}` : ''}` : '' }}</td>
                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null && it.fact_unit_price != null ? formatCurrency(it.fact_unit_price) : '' }}</td>
                <td style="padding:4px 8px;text-align:right;font-weight:500">{{ it.fact_amount != null ? formatCurrency(it.fact_amount) : '' }}</td>
                <td style="padding:4px 8px;text-align:right" :style="ctx.getDiffStyle(it.planned_total ?? it.total_price, [it])">{{ formatCurrency(ctx.calcDiff(it.planned_total ?? it.total_price, [it])) }}</td>
                <td style="padding:4px 8px;color:#9ca3af">—</td>
                <td style="padding:4px 8px;text-align:center">
                  <v-chip size="x-small" color="blue" variant="tonal" :prepend-icon="purchaseStatusIcon(it.purchase_status)">
                    {{ purchaseStatusLabel(it.purchase_status) }}
                  </v-chip>
                </td>
                <td style="padding:2px;text-align:center;white-space:nowrap">
                  <v-btn icon="mdi-cart-outline" size="x-small" variant="text" color="blue"
                    title="Открыть закупку"
                    @click.stop="ctx.router.push(`/orders/${it.purchase_id}`)" />
                  <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                    title="Изменить можно только в заявке"
                    @click.stop="ctx.router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
                  ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
                  <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
                    title="Сменить категорию ФЭО позиции"
                    @click.stop="ctx.openWishItemFeoEdit(owner, it)" />
                  <template v-if="!it.wish_id">
                    <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                      title="Редактировать позицию закупки"
                      @click="ctx.openReqItemEdit(owner, it)" />
                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                      title="Удалить позицию из закупки"
                      @click="ctx.confirmReqItemDelete(owner, it)" />
                  </template>
                  <v-btn v-if="!ctx.reqItemPlanned(owner.id, it.id) && ctx.reqItemActual(owner.id, it.id)"
                    icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                    title="Сопоставить с плановой позицией"
                    @click="ctx.mapReqItem(owner, it)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  </template>
</template>

<script setup lang="ts">
// Позиции «из заявок» как узлы дерева ФЭО (после поддерева владельца, режим
// «слияние по имени/группировка») — вынесены из SubsidiesView.vue (волна 5c).
// Формулы/состояние — composables/subsidies/useFeoReqItems.ts (Правило №6),
// здесь только вёрстка. Режим «по закупкам» (papки без слияния) — соседний
// компонент FeoByPurchasesRows.vue.
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import { purchaseStatusIcon, purchaseStatusColor, purchaseStatusLabel } from '@/constants/purchaseStatus'
import type { FeoNode } from '@/composables/subsidies/types'

const props = defineProps<{ owner: FeoNode }>()
const owner = props.owner

const ctx = useSubsidyDetailCtx()
</script>
