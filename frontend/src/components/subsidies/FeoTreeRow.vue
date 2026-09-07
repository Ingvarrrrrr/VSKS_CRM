<template>
  <tr
    v-if="ctx.isNodeVisible(node) && !(ctx.plannedBase.value === 'requests' && ctx.isManualPosLeaf(node))"
    class="feo-tr"
    :data-feo-node-id="node.id"
    :class="[
      `feo-tr--l${node.level}`,
      ctx.dragOverId.value === node.id ? 'feo-drop-target' : '',
      ctx.dragNodeId.value === node.id ? 'feo-dragging' : '',
      kpi.kpiNodeClass(node),
    ]"
    :draggable="ctx.canEditFeo.value"
    @dragstart="ctx.canEditFeo.value && ctx.onDragStart($event, node)"
    @dragover.prevent="ctx.canEditFeo.value && ctx.onDragOver($event, node)"
    @dragleave="ctx.onDragLeave"
    @drop="ctx.canEditFeo.value && ctx.onDrop($event, node)"
    @dragend="ctx.onDragEnd"
  >
    <!-- Наименование -->
    <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
      <div class="feo-name-inner">
        <!-- Лист ФЭО: клик по папке/шеврону раскрывает ЕДИНУЮ панель «Плановые
             позиции» (expandedItemPanels/toggleItemPanel) — единственный источник
             детализации листа с 2026-08-07. -->
        <span class="feo-tree-chevron" @click="node.hasChildren ? ctx.toggleExpand(node.id) : ctx.toggleItemPanel(node)">
          <v-icon
            v-if="node.hasChildren"
            size="15"
            :icon="ctx.expandedIds.value.includes(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
            color="grey"
            class="mr-1 cursor-pointer"
          />
          <v-icon
            v-else
            size="15"
            :icon="ctx.expandedItemPanels.value.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
            color="grey"
            class="mr-1 cursor-pointer"
          />
        </span>
        <v-icon
          size="16"
          class="mr-1 flex-shrink-0 cursor-pointer"
          :icon="node.hasChildren
            ? (ctx.expandedIds.value.includes(node.id) ? 'mdi-folder-open' : 'mdi-folder')
            : (ctx.expandedItemPanels.value.has(node.id) ? 'mdi-folder-open' : 'mdi-folder')"
          :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
          @click="node.hasChildren ? ctx.toggleExpand(node.id) : ctx.toggleItemPanel(node)"
        />
        <span class="feo-name" :class="`feo-name--l${node.level}`">{{ node.name }}</span>
        <span v-if="node.code" class="feo-code ml-2">{{ node.code }}</span>
        <span v-if="node.appendix" class="feo-appendix ml-1">{{ node.appendix }}</span>
      </div>
      <v-tooltip v-if="node.description" location="bottom" open-delay="150" :max-width="420">
        <template #activator="{ props: tooltipProps }">
          <div v-bind="tooltipProps" class="feo-plan-note text-caption text-medium-emphasis text-truncate" style="max-width:100%">{{ node.description }}</div>
        </template>
        <span style="white-space:pre-line">{{ node.description }}</span>
      </v-tooltip>
    </td>

    <!-- Финансирование по ФЭО (inline edit) -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <template v-if="ctx.feoRollup(node).qty != null || ctx.feoRollup(node).amount != null">
        <div class="feo-plan-note text-right"
          :class="ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto ? 'text-medium-emphasis' : ''"
          :title="(ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto) ? 'Сумма по вложенным' : 'Количество и стоимость по документу ФЭО'"
        >
          <template v-if="ctx.feoRollup(node).qty != null && ctx.feoRollup(node).amount != null">
            {{ ctx.feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : '' }} × {{ ctx.feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
          </template>
          <template v-else-if="ctx.feoRollup(node).qty != null">
            {{ ctx.feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : ' шт' }}
          </template>
          <template v-else>
            {{ ctx.feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
          </template>
          <v-chip v-if="ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto" size="x-small" color="blue-grey" variant="tonal" class="ml-1">авто</v-chip>
        </div>
      </template>
      <div v-if="ctx.inlineBudgetId.value === node.id" class="d-flex align-center justify-end">
        <input
          ref="inlineInputEl"
          v-model="ctx.inlineBudgetVal.value"
          type="number"
          class="inline-input"
          @blur="ctx.saveInlineBudget(node)"
          @keydown.enter="ctx.saveInlineBudget(node)"
          @keydown.esc="ctx.cancelInlineBudget()"
        />
      </div>
      <div v-else-if="ctx.isAutoNode(node)" class="feo-amount-cell text-right" :class="{ 'feo-amount-cell--readonly': !ctx.canEditFeo.value }" @click="ctx.canEditFeo.value && ctx.startInlineBudget(node)"
        :title="ctx.canEditFeo.value ? 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план. Кликните, чтобы задать вручную' : 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план'"
      >
        <template v-if="ctx.feoEffectiveFor(node) > 0">
          <span class="feo-amount text-medium-emphasis">{{ formatCurrency(ctx.feoEffectiveFor(node)) }}</span>
          <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1">расчёт</v-chip>
        </template>
        <span v-else-if="ctx.canEditFeo.value" class="feo-set-hint">Задать</span>
        <span v-else class="feo-set-hint">—</span>
      </div>
      <div v-else class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !ctx.canEditFeo.value }" @click="ctx.canEditFeo.value && ctx.startInlineBudget(node)">
        <span v-if="ctx.feoBudgetFor(node) > 0" class="feo-amount"
          :style="ctx.feoChildrenBudgetDiff(node) > 0.005 ? 'color:#EF4444;font-weight:700' : ''"
        >{{ formatCurrency(ctx.feoBudgetFor(node)) }}</span>
        <span v-else-if="ctx.canEditFeo.value" class="feo-set-hint">Задать</span>
        <span v-else class="feo-set-hint">—</span>
      </div>
      <template v-if="node.hasChildren && node.budget != null && node.budget > 0">
        <div v-if="!ctx.hasManualChildFeo(node)"
          class="feo-plan-note text-medium-emphasis"
          title="Ни у одной дочерней строки не задано финансирование по ФЭО"
        >
          Подробное деление в ФЭО отсутствовало
        </div>
        <div v-else-if="ctx.feoChildrenBudgetDiff(node) > 0.005"
          class="feo-plan-note" style="color:#EF4444"
          :title="`Ручное ФЭО дочерних ${formatCurrency(ctx.manualChildFeoSum(node))} превышает финансирование этой строки ${formatCurrency(node.budget || 0)}. Ищите лишнюю сумму в дочерних строках.`"
        >
          заложено в ФЭО {{ formatCurrency(ctx.manualChildFeoSum(node)) }} — лишние {{ formatCurrency(ctx.feoChildrenBudgetDiff(node)) }}
        </div>
        <div v-else-if="ctx.feoChildrenBudgetDiff(node) < -0.005"
          class="feo-plan-note" style="color:#F59E0B"
          :title="`Ручное ФЭО дочерних ${formatCurrency(ctx.manualChildFeoSum(node))} меньше финансирования этой строки ${formatCurrency(node.budget || 0)}. Часть суммы не распределена по дочерним в ФЭО.`"
        >
          заложено в ФЭО {{ formatCurrency(ctx.manualChildFeoSum(node)) }} — не распределено {{ formatCurrency(-ctx.feoChildrenBudgetDiff(node)) }}
        </div>
        <div v-else class="feo-plan-note text-medium-emphasis">
          заложено в ФЭО {{ formatCurrency(ctx.manualChildFeoSum(node)) }}
        </div>
      </template>
    </td>

    <!-- Плановое количество -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <div v-if="ctx.isAutoQtyNode(node)" class="text-right">
        <div class="feo-amount">{{ ctx.feoQtyDisplayFor(node) > 0 ? ctx.feoQtyDisplayFor(node) : '—' }}{{ node.unit ? ` ${node.unit}` : '' }}</div>
        <div v-if="ctx.plannedQtyBase.value === 'all' && ctx.feoQtyRequestsFor(node) > 0"
          class="feo-plan-note text-medium-emphasis"
          :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${ctx.feoQtyRequestsFor(node)}`"
        >
          в т.ч. из заявок {{ ctx.feoQtyRequestsFor(node) }}
        </div>
        <v-chip size="x-small" color="blue-grey" variant="tonal"
          title="Количество автоматически считается из дочерних"
        >авто</v-chip>
      </div>
      <div v-else-if="ctx.inlineQtyId.value === node.id" class="d-flex align-center justify-end">
        <input
          ref="inlineQtyInputEl"
          v-model="ctx.inlineQtyVal.value"
          type="number"
          class="inline-input"
          @blur="ctx.saveInlineQty(node)"
          @keydown.enter="ctx.saveInlineQty(node)"
          @keydown.esc="ctx.cancelInlineQty()"
        />
      </div>
      <template v-else>
        <div class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !ctx.canEditFeo.value }" @click="ctx.canEditFeo.value && ctx.startInlineQty(node)">
          <span v-if="ctx.feoQtyDisplayFor(node) > 0" class="feo-amount">{{ ctx.feoQtyDisplayFor(node) }}{{ node.unit ? ` ${node.unit}` : '' }}</span>
          <span v-else class="feo-set-hint">—</span>
        </div>
        <div v-if="ctx.plannedQtyBase.value === 'all' && ctx.feoQtyRequestsFor(node) > 0"
          class="feo-plan-note text-medium-emphasis"
          :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${ctx.feoQtyRequestsFor(node)}`"
        >
          в т.ч. из заявок {{ ctx.feoQtyRequestsFor(node) }}
        </div>
        <template v-if="ctx.plannedQtyBase.value === 'all' && ctx.matchedReqFor(node).length">
          <div v-if="ctx.mergedQtyDiff(node) > 0"
            class="feo-plan-note" style="color:#F59E0B"
            :title="`Всего запланировано ${ctx.feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
          >
            на {{ ctx.mergedQtyDiff(node) }} превышает заложенный в ФЭО показатель ({{ Number(node.feo_quantity) || 0 }})
          </div>
          <div v-else-if="ctx.mergedQtyDiff(node) < 0"
            class="feo-plan-note text-medium-emphasis"
            :title="`Всего запланировано ${ctx.feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
          >
            не хватает {{ -ctx.mergedQtyDiff(node) }} до заложенного в ФЭО ({{ Number(node.feo_quantity) || 0 }})
          </div>
        </template>
      </template>
    </td>

    <!-- Плановая сумма: ручной план ФЭО и/или позиции заявок (по переключателю) -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <span v-if="ctx.feoPlannedDisplayFor(node) > 0" class="feo-amount"
        :style="(ctx.feoDisplayedFor(node) > 0 && ctx.feoPlannedDisplayFor(node) > ctx.feoDisplayedFor(node)) || ctx.feoHasOverspentDescendant(node) ? 'color:#EF4444;font-weight:700' : ''"
        :title="ctx.plannedSumBase.value === 'all' ? `Ручные ${formatCurrency(ctx.feoPlannedTotalFor(node))} + из заявок ${formatCurrency(ctx.feoPlannedRequestsFor(node))}` : ''"
      >{{ formatCurrency(ctx.feoPlannedDisplayFor(node)) }}</span>
      <span v-else class="feo-amount-empty">—</span>
      <!-- «В т.ч. на самом направлении N ₽» — часть плана узла с детьми, заложенная
           НЕПОСРЕДСТВЕННО на нём самом. Кликабельна — раскрывает ту же панель, что и
           иконка-список в «Действиях» (toggleItemPanel). -->
      <div v-if="ctx.feoOwnDirectionPlanFor(node) > 0"
        class="feo-plan-note text-medium-emphasis feo-plan-note--link"
        title="Часть плана этого направления, заложенная прямо на нём (не в подкатегориях). Клик открывает список этих плановых позиций"
        @click="ctx.toggleItemPanel(node)"
      >
        в т.ч. на самом направлении {{ formatCurrency(ctx.feoOwnDirectionPlanFor(node)) }}
      </div>
      <div v-if="ctx.feoDisplayedFor(node) > 0 && (node.budget != null || ctx.feoPlannedDisplayFor(node) > 0) && Math.abs(ctx.feoFinDiff(node)) > 0.005"
        class="feo-plan-note"
        :style="ctx.feoFinDiff(node) > 0 ? 'color:#16A34A' : 'color:#EF4444'"
        :title="`Финансирование по ФЭО (бюджет, заложенный в документе ФЭО): ${formatCurrency(ctx.feoDisplayedFor(node))}. Плановая сумма (сколько уже расписано по плану/заявкам): ${formatCurrency(ctx.feoPlannedDisplayFor(node))}`"
      >
        {{ ctx.feoFinDiff(node) > 0 ? `по плану можно добавить ещё ${formatCurrency(ctx.feoFinDiff(node))} до финансирования ФЭО (это остаток по плану, не по факту закупок)` : `надо убрать ${formatCurrency(-ctx.feoFinDiff(node))}, чтобы уложиться в ФЭО` }}
        <div v-if="ctx.feoRemainingWithPurchasesNote(node)"
          style="font-size:11px;color:#EF4444;font-weight:600;margin-top:2px"
        >
          {{ ctx.feoRemainingWithPurchasesNote(node) }}
        </div>
      </div>
      <div v-if="!ctx.feoIsOverBudget(node) && ctx.feoHasOverspentDescendant(node)"
        class="feo-plan-note" style="color:#EF4444"
        :title="ctx.feoOverspentDescendantTitle(node)"
      >
        {{ ctx.feoOverspentDescendantText(node) }}
      </div>
      <!-- Разбор «план · в закупках · свободно» -->
      <div v-if="ctx.feoResidualNoteFor(node)"
        class="feo-plan-note text-medium-emphasis"
        title="План: сумма плановых позиций этой категории. В закупках: сколько из них уже набрано заявками (привязанными к этим позициям). Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
      >
        план {{ formatCurrency(ctx.feoResidualNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(ctx.feoResidualNoteFor(node)!.consumed) }} ·
        <span v-if="ctx.feoResidualNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-ctx.feoResidualNoteFor(node)!.residual) }}</span>
        <span v-else>свободно {{ formatCurrency(ctx.feoResidualNoteFor(node)!.residual) }}</span>
        <div v-if="ctx.feoResidualNoteFor(node)!.residual < -0.005" style="font-size:11px;white-space:normal;margin-top:2px">
          <v-btn v-if="!ctx.comparisonData.value[node.id]"
            size="x-small" variant="text" color="orange-darken-3"
            :loading="ctx.loadingComparison.value.has(node.id)"
            @click.stop="ctx.ensureComparison(node.id)"
          >Показать, из-за чего</v-btn>
          <template v-else-if="ctx.factExcessReasonItems(node).length">
            <span style="color:#B45309">из-за: </span>
            <template v-for="(it, idx) in ctx.factExcessReasonItems(node)" :key="it.key">
              <span v-if="idx > 0" style="color:#B45309"> · </span>
              <a v-if="it.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
                :title="`Перейти в закупку ${it.purchases[0]!.label}`"
                @click.stop="ctx.router.push(`/orders/${it.purchases[0]!.id}`)"
              >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
              <v-menu v-else location="bottom start">
                <template #activator="{ props: excMenuProps }">
                  <a href="javascript:void(0)" class="feo-purchase-link" v-bind="excMenuProps" @click.stop
                  >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
                </template>
                <v-list density="compact">
                  <v-list-item v-for="p in it.purchases" :key="p.id" @click="ctx.router.push(`/orders/${p.id}`)">
                    <v-list-item-title>
                      {{ p.label }} · {{ formatCurrency(p.amount) }}
                      <span v-if="p.stopped" class="feo-stopped-marker ml-1">остановлена</span>
                    </v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-menu>
            </template>
            <span v-if="ctx.factExcessReasonRemainder(node) > 0.5" style="color:#B45309">
              и ещё {{ formatCurrency(ctx.factExcessReasonRemainder(node)) }} (гасится недобором по другим плановым позициям — расшифровка не покрывает эту часть один-в-один)
            </span>
          </template>
          <span v-else style="color:#B45309">
            точную причину разобрать не удалось — {{ formatCurrency(ctx.factExcessReasonRemainder(node)) }} без разбивки по позициям
          </span>
        </div>
      </div>
      <div v-else-if="ctx.plannedSumBase.value === 'all' && ctx.feoPlanConsumedNoteFor(node)"
        class="feo-plan-note text-medium-emphasis"
        title="План: та же сумма, что и в плановой сумме строки выше. В закупках: сколько из плана уже занято заявками — своими и заявками подкатегорий. Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
      >
        план {{ formatCurrency(ctx.feoPlanConsumedNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(ctx.feoPlanConsumedNoteFor(node)!.consumed) }} ·
        <span v-if="ctx.feoPlanConsumedNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-ctx.feoPlanConsumedNoteFor(node)!.residual) }}</span>
        <span v-else>свободно {{ formatCurrency(ctx.feoPlanConsumedNoteFor(node)!.residual) }}</span>
      </div>
      <!-- Прогноз «цена выше плановой» — ТОЛЬКО у конечной категории. -->
      <div v-if="!node.hasChildren && ctx.feoForecastWarningFor(node)"
        class="feo-plan-note" style="color:#F97316;font-weight:600"
        :title="`Если оставшуюся часть купить по нынешней средней цене заказанного, итоговая сумма составит ${formatCurrency(ctx.feoForecastWarningFor(node)!.forecast)} — выше плана ${formatCurrency(ctx.feoForecastWarningFor(node)!.planManual)}. Не блокирует, только предупреждение`"
      >
        если оставшееся купить по нынешней средней цене, выйдет {{ formatCurrency(ctx.feoForecastWarningFor(node)!.forecast) }} при плане {{ formatCurrency(ctx.feoForecastWarningFor(node)!.planManual) }}
      </div>
      <!-- Превышение плана над финансированием ФЭО — требует согласования цепочкой. -->
      <div v-if="ctx.excessFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
        <template v-if="ctx.excessApprovalFor(node)?.status === 'pending'">
          <v-chip size="x-small" color="orange" variant="flat">
            согласование ПРЕВЫШЕНИЯ ПЛАНА (не закупки) {{ formatCurrency(ctx.excessFor(node)!.amount) }} · на согласовании у: {{ ctx.excessPendingNames(node) || '—' }}
          </v-chip>
          <template v-if="ctx.excessMyPendingStep(node) && ctx.excessApprovalFor(node)?.can_decide">
            <v-btn size="x-small" variant="tonal" color="success"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.decidePlanExcess(node, 'approved')"
            >Одобрить</v-btn>
            <v-btn size="x-small" variant="tonal" color="error"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.openExcessRejectDialog(node)"
            >Отклонить</v-btn>
          </template>
          <div v-else-if="ctx.excessMyPendingStep(node) && !ctx.excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
            Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
          </div>
        </template>
        <template v-else-if="ctx.excessApprovalFor(node)?.status === 'approved'">
          <v-chip size="x-small" color="grey" variant="flat">
            превышение {{ formatCurrency(ctx.excessFor(node)!.amount) }} · согласовано · {{ ctx.excessResolvedByName(node) }}{{ ctx.excessResolvedDate(node) ? ' · ' + ctx.excessResolvedDate(node) : '' }}
          </v-chip>
        </template>
        <template v-else-if="ctx.excessApprovalFor(node)?.status === 'rejected'">
          <v-chip size="x-small" color="red" variant="flat">
            превышение отклонено{{ ctx.excessApprovalFor(node)?.comment ? ': ' + ctx.excessApprovalFor(node)!.comment : '' }}
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
        <template v-else>
          <v-chip size="x-small" color="red" variant="flat">
            превышение {{ formatCurrency(ctx.excessFor(node)!.amount) }} — требуется согласование
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
      </div>
      <!-- «Заметный сигнал превышения» — виновная закупка, из-за которой всё превысило. -->
      <div v-if="ctx.excessCulpritFor(node)" class="feo-excess-culprit">
        <v-icon size="16" icon="mdi-alert-decagram" class="mr-1" />
        {{ ctx.excessCulpritText(node) }}
        <v-btn v-if="ctx.excessCulpritFor(node)!.purchase_id" size="x-small" variant="flat" color="red"
          class="ml-1" @click.stop="ctx.router.push(`/orders/${ctx.excessCulpritFor(node)!.purchase_id}`)"
        >Открыть закупку</v-btn>
      </div>

      <!-- ВТОРАЯ, независимая плашка — «итог закупки/КП дороже плана» (excess_fact_over_plan). -->
      <div v-if="ctx.excessFactFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
        <template v-if="ctx.excessApprovalFor(node)?.status === 'pending'">
          <v-chip size="x-small" color="orange" variant="flat">
            согласование ПРЕВЫШЕНИЯ: итог закупки дороже плана на {{ formatCurrency(ctx.excessFactFor(node)!.amount) }} · на согласовании у: {{ ctx.excessPendingNames(node) || '—' }}
          </v-chip>
          <template v-if="ctx.excessMyPendingStep(node) && ctx.excessApprovalFor(node)?.can_decide">
            <v-btn size="x-small" variant="tonal" color="success"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.decidePlanExcess(node, 'approved')"
            >Одобрить</v-btn>
            <v-btn size="x-small" variant="tonal" color="error"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.openExcessRejectDialog(node)"
            >Отклонить</v-btn>
          </template>
          <div v-else-if="ctx.excessMyPendingStep(node) && !ctx.excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
            Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
          </div>
        </template>
        <template v-else-if="ctx.excessFactFor(node)!.approved">
          <v-chip size="x-small" color="grey" variant="flat">
            итог закупки дороже плана на {{ formatCurrency(ctx.excessFactFor(node)!.amount) }} · согласовано · {{ ctx.excessResolvedByName(node) }}{{ ctx.excessResolvedDate(node) ? ' · ' + ctx.excessResolvedDate(node) : '' }}
          </v-chip>
        </template>
        <template v-else-if="ctx.excessApprovalFor(node)?.status === 'rejected'">
          <v-chip size="x-small" color="red" variant="flat">
            превышение факта отклонено{{ ctx.excessApprovalFor(node)?.comment ? ': ' + ctx.excessApprovalFor(node)!.comment : '' }}
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
        <template v-else>
          <v-chip size="x-small" color="red" variant="flat">
            итог закупки дороже плана на {{ formatCurrency(ctx.excessFactFor(node)!.amount) }} — требуется согласование
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
      </div>

      <!-- ТРЕТЬЯ, независимая плашка — сумма плановых позиций категории превысила
           вручную заданный план (excessPlanFor). -->
      <div v-if="ctx.excessPlanFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
        <template v-if="ctx.excessApprovalFor(node)?.status === 'pending'">
          <v-chip size="x-small" color="orange" variant="flat">
            согласование ПРЕВЫШЕНИЯ: план превышает заданный вручную на {{ formatCurrency(ctx.excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(ctx.excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(ctx.excessPlanFor(node)!.manualEntered + ctx.excessPlanFor(node)!.amount) }}) · на согласовании у: {{ ctx.excessPendingNames(node) || '—' }}
          </v-chip>
          <template v-if="ctx.excessMyPendingStep(node) && ctx.excessApprovalFor(node)?.can_decide">
            <v-btn size="x-small" variant="tonal" color="success"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.decidePlanExcess(node, 'approved')"
            >Одобрить</v-btn>
            <v-btn size="x-small" variant="tonal" color="error"
              :loading="ctx.excessDecideLoading.value === node.id"
              @click.stop="ctx.openExcessRejectDialog(node)"
            >Отклонить</v-btn>
          </template>
          <div v-else-if="ctx.excessMyPendingStep(node) && !ctx.excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
            Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
          </div>
        </template>
        <template v-else-if="ctx.excessApprovalFor(node)?.status === 'rejected'">
          <v-chip size="x-small" color="red" variant="flat">
            превышение плана над ручным отклонено{{ ctx.excessApprovalFor(node)?.comment ? ': ' + ctx.excessApprovalFor(node)!.comment : '' }}
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
        <template v-else>
          <v-chip size="x-small" color="red" variant="flat">
            план превышает заданный вручную на {{ formatCurrency(ctx.excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(ctx.excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(ctx.excessPlanFor(node)!.manualEntered + ctx.excessPlanFor(node)!.amount) }})
          </v-chip>
          <v-btn size="x-small" variant="tonal" color="red"
            :loading="ctx.excessRequestLoading.value === node.id"
            @click.stop="ctx.requestPlanExcessApproval(node)"
          >Согласовать</v-btn>
        </template>
        <div v-if="ctx.excessPlanFor(node)!.items.length" class="d-flex align-center flex-wrap ga-1 mt-1" style="width:100%">
          <span style="font-size:11px;color:#B45309">Позиции-виновники:</span>
          <template v-for="item in ctx.excessPlanFor(node)!.items" :key="item.id">
            <span v-if="!item.purchases.length" class="feo-purchase-link" style="cursor:default;opacity:0.7"
              :title="`«${item.name}» (${formatCurrency(item.amount)}) — нет связанной закупки: позиция ещё не попала ни в одну закупку`"
            >{{ item.name }} ({{ formatCurrency(item.amount) }})</span>
            <a v-else-if="item.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
              @click.stop="ctx.router.push(`/orders/${item.purchases[0]!.id}`)"
            >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
            <v-menu v-else location="bottom start">
              <template #activator="{ props: purchMenuProps }">
                <a href="javascript:void(0)" class="feo-purchase-link" v-bind="purchMenuProps" @click.stop
                >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
              </template>
              <v-list density="compact">
                <v-list-item v-for="p in item.purchases" :key="p.id" @click="ctx.router.push(`/orders/${p.id}`)">
                  <v-list-item-title>
                    {{ ctx.excessPlanItemPurchaseTitle(p) }}
                    <span v-if="p.stopped_at" class="feo-stopped-marker ml-1">остановлена</span>
                  </v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </template>
        </div>
      </div>

      <!-- Постоянная пометка «превышение согласовано» — НЕ зависит от того, активно ли
           превышение прямо сейчас. -->
      <div v-if="ctx.excessPlanApprovalPermanent(node)" class="feo-plan-note mt-1">
        <v-chip size="x-small" color="grey" variant="tonal" prepend-icon="mdi-check-decagram">
          превышение согласовано: {{ formatCurrency(ctx.excessPlanApprovalPermanent(node)!.amount) }}{{ ctx.excessPlanApprovalPermanent(node)!.at ? ', ' + ctx.excessPlanApprovalPermanent(node)!.at : '' }}, {{ ctx.excessPlanApprovalPermanent(node)!.by }}<template v-if="ctx.excessPlanApprovalPermanent(node)!.planBefore != null && ctx.excessPlanApprovalPermanent(node)!.planAfter != null"> · план был {{ formatCurrency(ctx.excessPlanApprovalPermanent(node)!.planBefore!) }} → стал {{ formatCurrency(ctx.excessPlanApprovalPermanent(node)!.planAfter!) }}</template>
        </v-chip>
      </div>

      <!-- «Приравнять ФЭО к плану» — только org_admin и выше. -->
      <div v-if="canSaveVersion" class="mt-1">
        <v-btn size="x-small" variant="text" color="blue-grey" prepend-icon="mdi-equal"
          title="Установить финансирование по ФЭО этой категории равным её полной плановой сумме"
          @click.stop="ctx.openAlignBudgetConfirm(node)"
        >Приравнять ФЭО к плану</v-btn>
      </div>
    </td>

    <!-- «В плане-графике» -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <span :class="ctx.feoInPlanScheduleFor(node) > 0 ? 'feo-amount feo-amount--link' : 'feo-amount-empty'"
        :style="(ctx.feoDisplayedFor(node) > 0 && ctx.feoInPlanScheduleFor(node) > ctx.feoDisplayedFor(node)) || (ctx.feoPlannedDisplayFor(node) > 0 && ctx.feoInPlanScheduleFor(node) > ctx.feoPlannedDisplayFor(node)) ? 'color:#EF4444;font-weight:700' : ''"
        :title="ctx.feoInPlanScheduleFor(node) > 0 ? 'Открыть закупки по этой категории' : ''"
        @click="ctx.feoInPlanScheduleFor(node) > 0 && ctx.router.push(`/orders?feo_category_id=${node.id}`)"
      >
        {{ ctx.feoInPlanScheduleFor(node) > 0 ? formatCurrency(ctx.feoInPlanScheduleFor(node)) : '—' }}
      </span>
      <div v-if="ctx.feoFactFor(node) > 0 && Math.abs(ctx.feoInPlanScheduleFor(node) - ctx.feoFactFor(node)) > 0.005"
        class="feo-plan-note text-medium-emphasis"
        :title="`Из них уже есть договорная цена (договор/акт). Остальное — закупки, которые ещё в статусе «План закупок»`"
      >
        по договору {{ formatCurrency(ctx.feoFactFor(node)) }}
      </div>
    </td>

    <!-- Остаток = (Плановая сумма | Финансирование по ФЭО) − В плане-графике. -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <span v-if="ctx.feoResidualBaseFor(node) > 0 || ctx.feoInPlanScheduleFor(node) > 0"
        class="feo-amount"
        :style="ctx.feoResidualFor(node) < -0.005 ? 'color:#EF4444;font-weight:700' : 'color:#16A34A'"
        :title="`${ctx.residualBase.value === 'feo' ? 'ФЭО' : 'План'} ${formatCurrency(ctx.feoResidualBaseFor(node))} − В плане-графике ${formatCurrency(ctx.feoInPlanScheduleFor(node))}`"
      >
        {{ ctx.feoResidualFor(node) < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(ctx.feoResidualFor(node))) }}
      </span>
      <span v-else class="feo-amount-empty">—</span>
    </td>

    <!-- Действия -->
    <td class="feo-td feo-td-actions">
      <div class="feo-actions-wrap">
        <!-- Level 3: кнопка раскрытия позиций / spacer for alignment. У направления
             (node.hasChildren) кнопка тоже появляется, но ТОЛЬКО если у него есть
             СОБСТВЕННЫЕ плановые позиции (hasOwnPlannedAmountFor). -->
        <span class="feo-action-slot"><v-btn v-if="!node.hasChildren || ctx.hasOwnPlannedAmountFor(node)"
          :icon="ctx.expandedItemPanels.value.has(node.id) ? 'mdi-list-box' : 'mdi-list-box-outline'"
          variant="text" size="x-small"
          :color="ctx.expandedItemPanels.value.has(node.id) ? 'teal' : 'grey'"
          :title="node.hasChildren ? 'Состав плана: позиции, привязанные к самому направлению (не к его подкатегориям)' : 'Показать плановые / фактические позиции'"
          @click="ctx.toggleItemPanel(node)"
        /></span>
        <!-- Стрелки — друг под другом (B5: скрыты без feo_category.edit) -->
        <div v-if="ctx.canEditFeo.value" class="feo-actions-col">
          <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
            title="Переместить выше" @click.stop="ctx.reorderFeoNode(node, 'up')" />
          <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
            title="Переместить ниже" @click.stop="ctx.reorderFeoNode(node, 'down')" />
        </div>
        <!-- Значки: добавить/редактировать/удалить скрыты без feo_category.edit;
             «показать закупки» — чтение, остаётся всегда -->
        <div class="feo-actions-grid">
          <v-btn v-if="ctx.canEditFeo.value" icon="mdi-plus-circle-outline" variant="text" size="x-small" color="success"
            title="Добавить дочернюю" @click="ctx.openAddFeoDialog(node.id)" />
          <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
            title="Показать закупки по этой категории"
            @click.stop="ctx.router.push(`/orders?feo_category_id=${node.id}`)" />
          <v-btn v-if="ctx.canEditFeo.value" icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
            title="Редактировать" @click="ctx.startFeoEdit(node)" />
          <v-btn v-if="ctx.canEditFeo.value" icon="mdi-delete-outline" variant="text" size="x-small" color="error"
            title="Удалить" @click="ctx.confirmFeoDelete(node)" />
        </div>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
// Основная строка узла дерева ФЭО (наименование, финансирование, плановое
// кол-во/сумма, «в плане-графике», остаток, действия — со всеми плашками
// превышения плана) — вынесена из SubsidiesView.vue (волна 5c). Level 5 панель
// (плановые vs фактические) — соседний <tr>, см. FeoLevel5Panel.vue.
import { computed } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
import { formatCurrency } from '@/composables/subsidies/format'
import type { FeoNode } from '@/composables/subsidies/types'

const props = defineProps<{ node: FeoNode }>()
const node = props.node

const ctx = useSubsidyDetailCtx()
const kpi = useKpiDrilldown(ctx)

// Тот же гейт, что и в SubsidyEditDialog.vue/FeoTreeToolbar.vue (canSaveVersion) —
// вычисляется независимо здесь же (простая проверка роли из localStorage, не формула,
// дублирование не нарушает Правило №6).
const userRoleRaw = localStorage.getItem('user_role') || ''
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))
</script>
