<template>
  <!-- Общий переключатель РАСКРЫТИЯ комментариев ФЭО — ОДИН на всю субсидию
       (правка 2026-09-14, жалоба владельца: раньше прятал саму иконку —
       «должна быть видна постоянно», переключатель обязан только разворачивать
       /сворачивать все ветки разом). UI-точка одна физическая: рисуется только
       в самой первой видимой строке дерева (см. isFirstVisibleRow ниже), а не
       в каждой строке. Строка ВСЕГДА видима независимо от текущего значения. -->
  <tr v-if="isFirstVisibleRow" class="feo-comments-visibility-bar">
    <td colspan="7" style="padding:4px 8px">
      <div class="d-flex align-center" style="gap:6px">
        <v-icon icon="mdi-comment-text-multiple-outline" size="14" color="grey-darken-1" />
        <span class="text-caption text-medium-emphasis">Комментарии к плану ФЭО:</span>
        <v-switch
          :model-value="feoComments.isVisibleCached(subsidyId)"
          density="compact" hide-details color="teal" style="flex:0 0 auto"
          :label="feoComments.isVisibleCached(subsidyId) ? 'все развёрнуты' : 'все свёрнуты'"
          @update:model-value="onToggleCommentsVisible"
        />
        <span class="text-caption text-medium-emphasis">— разворачивает/сворачивает сразу все ветки; иконка комментария видна всегда</span>
      </div>
    </td>
  </tr>

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
        <!-- Один клик — одно раскрытие (жалоба владельца 2026-09-14, вторая волна:
             «пусть если это на направлении лежит, то разворачивается вместе с
             папкой, а не отдельным нажатием»). Для направления, у которого есть
             И подразделы, И собственные плановые позиции, toggleNodeExpansion
             переключает ОБА состояния согласованно за один клик — раскрыл: видно
             подразделы и панель позиций, свернул: скрыто и то и другое. Для
             направления без подразделов — прежнее поведение (шеврон открывает
             панель позиций листа). Для направления без собственных позиций —
             тоже прежнее (только подразделы). См. toggleNodeExpansion в
             <script setup> — единственное место, решающее «что открыть по
             клику»; бейдж/строка состава ниже вызывают её же, не полдела. -->
        <!-- Чекбокс «выбрать категорию/поддерево целиком» (владелец, задача 1) —
             только в режиме выбора для «Создать закупку на основе плана».
             Состояние/клик — usePlanToRequest.ts::subtreeSelectionState/
             selectCategorySubtree (Правило №6, тот же общий Set выбора, что и
             построчные чекбоксы FeoLevel5Panel.vue). Правка 2026-09-20: жалоба
             владельца — на категориях вроде «Экипировка»/«Комплект специальной
             одежды для добровольцев» чекбокс показывал indeterminate («квадрат
             с минусом»), и это не читалось как галочка вовсе. Крупнее (density
             default, control-size 22px — уже был в CSS), с явной подписью
             «категория целиком» и tooltip со счётом «выбрано k из N» — тот же
             subtreeSelection (задача 1б, total/selectedCount из
             computeSelectionState), второй подсчёт не заводим. N=0 — disabled
             (в категории нет позиций с остатком, кликать нечего). -->
        <v-tooltip v-if="planToRequest.active.value" location="top" open-delay="200">
          <template #activator="{ props: cbTooltipProps }">
            <span v-bind="cbTooltipProps" class="feo-tree-select-wrap" @click.stop>
              <v-checkbox-btn
                class="feo-tree-select-checkbox"
                density="default" color="orange-darken-1"
                :model-value="subtreeSelection.all"
                :indeterminate="!subtreeSelection.all && subtreeSelection.some"
                :disabled="subtreeSelection.total === 0"
                @update:model-value="(v: boolean | null) => planToRequest.selectCategorySubtree(node, ctx.feoCategories.value, !!v)"
              />
              <span class="feo-tree-select-label">{{ subtreeSelectionLabel }}</span>
            </span>
          </template>
          <span>{{ subtreeSelectionTooltip }}</span>
        </v-tooltip>
        <!-- Шеврон/папка — увеличенная кликабельная область (владелец, задача 3):
             раньше цель клика была ровно с иконку (15/16px), мимо легко было
             промахнуться. Обёрнуты в span 28×28 с паддингом — попадание проще,
             сама строка выше не становится (высоту задаёт колонка «Действия» с
             её сеткой кнопок). -->
        <span class="feo-tree-chevron" @click="toggleNodeExpansion(node)">
          <v-icon
            v-if="node.hasChildren"
            size="22"
            :icon="ctx.expandedIds.value.includes(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
            color="grey"
            class="cursor-pointer"
          />
          <v-icon
            v-else
            size="22"
            :icon="ctx.expandedItemPanels.value.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
            color="grey"
            class="cursor-pointer"
          />
        </span>
        <span class="feo-tree-folder" @click="toggleNodeExpansion(node)">
          <v-icon
            size="20"
            class="cursor-pointer"
            :icon="node.hasChildren
              ? (ctx.expandedIds.value.includes(node.id) ? 'mdi-folder-open' : 'mdi-folder')
              : (ctx.expandedItemPanels.value.has(node.id) ? 'mdi-folder-open' : 'mdi-folder')"
            :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
          />
        </span>
        <span class="feo-name" :class="`feo-name--l${node.level}`">{{ node.name }}</span>
        <span v-if="node.code" class="feo-code ml-2">{{ node.code }}</span>
        <span v-if="node.appendix" class="feo-appendix ml-1">{{ node.appendix }}</span>
      </div>
      <!-- Заметный индикатор собственных плановых позиций направления (не в
           подкатегориях) — виден ДО раскрытия чего-либо. Кликабелен, но делает
           РОВНО то же, что шеврон/папка (toggleNodeExpansion) — раньше открывал
           только панель позиций отдельно от подразделов, владелец справедливо
           указал, что это два действия там, где должно быть одно («это тоже
           входит в состав направления»). НА СВОЕЙ СТРОКЕ (не внутри
           .feo-name-inner) — тот флекс-ряд и так тесный; втиснутый туда бейдж с
           суммой отжимал у .feo-name всю ширину до нуля и валил колонку в
           800+px переносом по одному символу (найдено живой проверкой на
           стенде, категория 4792 — ИСПРАВЛЕНО переносом бейджа сюда). -->
      <div v-if="feoOwnItemsBadgeText" class="feo-name-badge-row">
        <span class="feo-own-badge"
          :class="{ 'feo-own-badge--active': ctx.expandedItemPanels.value.has(node.id) }"
          title="На этом направлении есть свои плановые позиции — раскрываются вместе с подразделами по клику на папку/шеврон"
          @click.stop="toggleNodeExpansion(node)"
        >
          <v-icon size="12" icon="mdi-clipboard-text-outline" class="mr-1" />{{ feoOwnItemsBadgeText }}
        </span>
      </div>
      <v-tooltip v-if="node.description" location="bottom" open-delay="150" :max-width="420">
        <template #activator="{ props: tooltipProps }">
          <div v-bind="tooltipProps" class="feo-plan-note text-caption text-medium-emphasis text-truncate" style="max-width:100%">{{ node.description }}</div>
        </template>
        <span style="white-space:pre-line">{{ node.description }}</span>
      </v-tooltip>
    </td>

    <!-- Кол-во и финансирование по ФЭО (inline edit) -->
    <td class="feo-td feo-td-num" style="vertical-align:top">
      <!-- Только Кол-во и Сумма по документу ФЭО (задача владельца, п.15б —
           раньше здесь стояло «qty × цена за ед.», читавшееся как цена за
           единицу, которой в этой колонке быть не должно). feoRollup(node).amount
           теперь ВСЕГДА готовые деньги (qty × unit_price), не голая цена за
           единицу (node.feo_amount) — см. подробный комментарий в
           useFeoTreeAmounts.ts у feoRollup. Блок целиком скрыт, если сумму не
           из чего посчитать (задано только количество ИЛИ только цена за ед.,
           но не оба) — показывать один из этих двух чисел под подписью «Сумма»
           нельзя, а 0 трактуется как «не задано» так же, как и node.budget. -->
      <div v-if="ctx.feoRollup(node).amount != null" class="feo-plan-note text-right"
        :class="ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto ? 'text-medium-emphasis' : ''"
        :title="(ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto) ? 'Сумма по вложенным' : 'Количество и сумма (кол-во × цена за ед.) по документу ФЭО'"
      >
        <div v-if="ctx.feoRollup(node).qty != null">Кол-во: {{ ctx.feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : '' }}</div>
        <div>Сумма: {{ formatCurrency(ctx.feoRollup(node).amount!) }}</div>
        <v-chip v-if="ctx.feoRollup(node).qtyAuto || ctx.feoRollup(node).amountAuto" size="x-small" color="blue-grey" variant="tonal" class="ml-1">авто</v-chip>
      </div>
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
        <!-- «Не задано» явным выбором в поле ввода (задача владельца, п.8) — не
             только стирать вручную. mousedown.prevent, чтобы клик не сначала
             отправил blur со старым значением, а сразу обнулил и сохранил. -->
        <v-btn
          icon="mdi-close-circle-outline" variant="text" size="x-small" color="grey" class="ml-1"
          title="Не задано (очистить финансирование по ФЭО)"
          @mousedown.prevent="() => { ctx.inlineBudgetVal.value = ''; ctx.saveInlineBudget(node) }"
        />
      </div>
      <div v-else-if="ctx.isAutoNode(node)" class="feo-amount-cell text-right" :class="{ 'feo-amount-cell--readonly': !ctx.canEditFeo.value }" @click="ctx.canEditFeo.value && ctx.startInlineBudget(node)"
        :title="ctx.canEditFeo.value ? 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план. Кликните, чтобы задать вручную' : 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план'"
      >
        <template v-if="ctx.feoEffectiveFor(node) > 0">
          <span class="feo-amount text-medium-emphasis">{{ formatCurrency(ctx.feoEffectiveFor(node)) }}</span>
          <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1">расчёт</v-chip>
        </template>
        <span v-else class="feo-set-hint">Не задано</span>
      </div>
      <div v-else class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !ctx.canEditFeo.value }" @click="ctx.canEditFeo.value && ctx.startInlineBudget(node)">
        <span v-if="ctx.feoBudgetFor(node) > 0" class="feo-amount"
          :style="ctx.feoChildrenBudgetDiff(node) > 0.005 ? 'color:#EF4444;font-weight:700' : ''"
        >{{ formatCurrency(ctx.feoBudgetFor(node)) }}</span>
        <span v-else class="feo-set-hint">Не задано</span>
      </div>
      <template v-if="node.hasChildren && node.budget != null && node.budget > 0">
        <!-- Задача владельца, п.17: старый текст «Подробное деление в ФЭО
             отсутствовало» стоял вплотную к сумме выше и читался как отрицание
             этой же суммы («сумма есть, а деления нет — как так»). На деле оба
             факта верны и не спорят друг с другом: сумма задана на саму группу
             целиком, а по вложенным строкам её никто не расписывал — условие
             показа (!hasManualChildFeo) не менялось, объяснено в title. -->
        <div v-if="!ctx.hasManualChildFeo(node)"
          class="feo-plan-note text-medium-emphasis"
          style="white-space:normal"
          :title="`Эта подпись появляется только когда у направления задано своё финансирование по ФЭО (сумма выше) и при этом ни у одной вложенной категории собственного ФЭО нет — делить тогда нечего, вся сумма относится к группе целиком. Задайте ФЭО хотя бы одной дочерней категории — здесь появится разбор «заложено / лишние / не распределено».`"
        >
          сумма {{ formatCurrency(node.budget || 0) }} задана на всю группу целиком — это нормально, по подкатегориям она не расписывалась
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
      <!-- Раздел C0 (план ancient-prancing-music.md, 2026-09-21): «товары/услуги» —
           переключатель kpiTypeSplit (useKpiPrefs.ts, общий с карточками KPI и
           вторым экземпляром переключателя в FeoTreeToolbar.vue). Поля узла —
           см. feoTreeAmounts2.feoTypeSplitFor (useFeoTreeAmounts.ts), null —
           нечего показать (все доли нулевые). -->
      <div v-if="kpiPrefs.kpiTypeSplit.value === 'split' && feoTreeAmounts2.feoTypeSplitFor(node)"
        class="feo-plan-note feo-type-split-note text-medium-emphasis"
      >
        товары {{ formatCurrency(feoTreeAmounts2.feoTypeSplitFor(node)!.goods) }} · услуги {{ formatCurrency(feoTreeAmounts2.feoTypeSplitFor(node)!.services) }}<span v-if="feoTreeAmounts2.feoTypeSplitFor(node)!.unspecified > 0.005"> · без типа {{ formatCurrency(feoTreeAmounts2.feoTypeSplitFor(node)!.unspecified) }}</span>
      </div>
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
      <!-- Раздел C0: «товары/услуги» плановой суммы — та же схема, что и у
           колонки «Количество и финансирование по ФЭО» выше (feoTreeAmounts2.
           planTypeSplitFor, поля plan_goods/plan_services/plan_unspecified узла). -->
      <div v-if="kpiPrefs.kpiTypeSplit.value === 'split' && feoTreeAmounts2.planTypeSplitFor(node)"
        class="feo-plan-note feo-type-split-note text-medium-emphasis"
      >
        товары {{ formatCurrency(feoTreeAmounts2.planTypeSplitFor(node)!.goods) }} · услуги {{ formatCurrency(feoTreeAmounts2.planTypeSplitFor(node)!.services) }}<span v-if="feoTreeAmounts2.planTypeSplitFor(node)!.unspecified > 0.005"> · без типа {{ formatCurrency(feoTreeAmounts2.planTypeSplitFor(node)!.unspecified) }}</span>
      </div>
      <!-- Состав суммы направления: сколько заложено по подкатегориям и сколько —
           прямо на самом направлении (жалоба владельца 2026-09-14 — число 831 972
           не читалось как сложение). Показывается ТОЛЬКО когда есть обе части
           (см. feoDirectionCompositionText). Кликабельна — вызывает
           toggleNodeExpansion, то же единое раскрытие, что и шеврон/папка/бейдж. -->
      <div v-if="feoDirectionCompositionText"
        class="feo-plan-note text-medium-emphasis feo-plan-note--link"
        title="Часть плана этого направления, заложенная прямо на нём (не в подкатегориях). Клик раскрывает направление целиком — подразделы и эти позиции"
        @click="toggleNodeExpansion(node)"
      >
        {{ feoDirectionCompositionText }}
      </div>
      <!-- Направление без плана по подкатегориям, но с собственными позициями —
           прежняя короткая подпись остаётся (обе части не нужны, показывать
           «состав» не из чего складывать). -->
      <div v-else-if="ctx.feoOwnDirectionPlanFor(node) > 0"
        class="feo-plan-note text-medium-emphasis feo-plan-note--link"
        title="Часть плана этого направления, заложенная прямо на нём (не в подкатегориях). Клик раскрывает направление целиком — подразделы и эти позиции"
        @click="toggleNodeExpansion(node)"
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

      <!-- ЧЕТВЁРТАЯ/ПЯТАЯ, независимые плашки — превышение ПО ТИПУ (товары/
           услуги), раздел E плана ancient-prancing-music.md (владелец,
           21.09.2026): «план по товарам/услугам выше ФЭО по товарам/услугам»
           и «закупки по товарам/услугам выше плана по товарам/услугам» — на
           уровне ЭТОЙ категории (уровень субсидии целиком — SubsidyKpiCards.vue,
           другой агент). Величины/approval — useFeoTreeExcess.ts::typeExcessFor
           (единственный источник, НЕЗАВИСИМ от excessFor/excessFactFor/
           excessPlanFor выше — те держат СТАРЫЕ три вида; одобрение по одному
           виду/типу не гасит остальные). v-for по typeExcessKindDefs — общий
           массив 4 видов с SubsidyKpiCards.vue (Правило №6, не дублируем). -->
      <template v-for="tk in feoTreeExcess.typeExcessKindDefs" :key="tk.kind">
        <div v-if="feoTreeExcess.typeExcessFor(node, tk.kind)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
          <template v-if="feoTreeExcess.typeExcessFor(node, tk.kind)!.approval?.status === 'pending'">
            <v-chip size="x-small" color="orange" variant="flat">
              согласование: {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(node, tk.kind)!.amount) }} · на согласовании у: {{ feoTreeExcess.typeExcessPendingNames(node.id, tk.kind) || '—' }}
            </v-chip>
            <template v-if="feoTreeExcess.typeExcessMyPendingStep(node.id, tk.kind) && feoTreeExcess.typeExcessFor(node, tk.kind)!.approval?.can_decide">
              <v-btn size="x-small" variant="tonal" color="success"
                :loading="feoTreeExcess.typeExcessDecideLoading.value === feoTreeExcess.typeExcessKey(node.id, tk.kind)"
                @click.stop="feoTreeExcess.decideTypeExcess(node.id, tk.kind, 'approved')"
              >Одобрить</v-btn>
              <v-btn size="x-small" variant="tonal" color="error"
                :loading="feoTreeExcess.typeExcessDecideLoading.value === feoTreeExcess.typeExcessKey(node.id, tk.kind)"
                @click.stop="feoTreeExcess.decideTypeExcess(node.id, tk.kind, 'rejected')"
              >Отклонить</v-btn>
            </template>
            <div v-else-if="feoTreeExcess.typeExcessMyPendingStep(node.id, tk.kind) && !feoTreeExcess.typeExcessFor(node, tk.kind)!.approval?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
            </div>
          </template>
          <template v-else-if="feoTreeExcess.typeExcessFor(node, tk.kind)!.approved">
            <v-chip size="x-small" color="grey" variant="flat">
              {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(node, tk.kind)!.amount) }} · согласовано · {{ feoTreeExcess.typeExcessResolvedByName(node.id, tk.kind) }}{{ feoTreeExcess.typeExcessResolvedDate(node.id, tk.kind) ? ' · ' + feoTreeExcess.typeExcessResolvedDate(node.id, tk.kind) : '' }}
            </v-chip>
          </template>
          <template v-else-if="feoTreeExcess.typeExcessFor(node, tk.kind)!.approval?.status === 'rejected'">
            <v-chip size="x-small" color="red" variant="flat">
              {{ tk.label }} — отклонено{{ feoTreeExcess.typeExcessFor(node, tk.kind)!.approval?.comment ? ': ' + feoTreeExcess.typeExcessFor(node, tk.kind)!.approval!.comment : '' }}
            </v-chip>
            <v-btn size="x-small" variant="tonal" color="red"
              :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(node.id, tk.kind)"
              @click.stop="feoTreeExcess.requestTypeExcessApproval(node, tk.kind)"
            >Согласовать</v-btn>
          </template>
          <template v-else>
            <v-chip size="x-small" color="red" variant="flat">
              {{ tk.label }} на {{ formatCurrency(feoTreeExcess.typeExcessFor(node, tk.kind)!.amount) }} — требуется согласование
            </v-chip>
            <v-btn size="x-small" variant="tonal" color="red"
              :loading="feoTreeExcess.typeExcessRequestLoading.value === feoTreeExcess.typeExcessKey(node.id, tk.kind)"
              @click.stop="feoTreeExcess.requestTypeExcessApproval(node, tk.kind)"
            >Согласовать</v-btn>
          </template>
        </div>
      </template>

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
      <!-- Раздел C0: остаток по типам = ФЭО по типу − план по типу (формула
           фиксирована — не следует переключателю «от плановой/от ФЭО»
           residualBase у общей колонки, см. докстринг remainingTypeSplitFor). -->
      <div v-if="kpiPrefs.kpiTypeSplit.value === 'split'" class="feo-plan-note feo-type-split-note text-medium-emphasis">
        товары {{ feoTreeAmounts2.remainingTypeSplitFor(node).goods < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(feoTreeAmounts2.remainingTypeSplitFor(node).goods)) }}
        · услуги {{ feoTreeAmounts2.remainingTypeSplitFor(node).services < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(feoTreeAmounts2.remainingTypeSplitFor(node).services)) }}
      </div>
    </td>

    <!-- Действия -->
    <td class="feo-td feo-td-actions">
      <div class="feo-actions-wrap">
        <!-- Level 3: кнопка раскрытия позиций / spacer for alignment. У направления
             (node.hasChildren) кнопка тоже появляется, но ТОЛЬКО если у него есть
             СОБСТВЕННЫЕ плановые позиции (hasOwnPlannedAmountFor). Клик — то же
             единое toggleNodeExpansion, что и у шеврона/папки/бейджа (для узла с
             подразделами она теперь тоже раскрывает подразделы, не только
             позиции — второго действия для одного направления быть не должно). -->
        <!-- Владелец 21.09.2026: «на любом уровне ФЭО можно добавить плановую
             позицию» — раньше у направления без собственных позиций кнопки не
             было вовсе, и первую позицию на направление добавить было неоткуда
             (панель с «Добавить плановую» открыть нечем). Кнопка есть у всех
             узлов и открывает именно панель собственных позиций (пустую — с
             кнопкой «Добавить плановую»); раскрытие подкатегорий — за шевроном/папкой. -->
        <span class="feo-action-slot"><v-btn
          :icon="ctx.expandedItemPanels.value.has(node.id) ? 'mdi-list-box' : 'mdi-list-box-outline'"
          variant="text" size="x-small"
          :color="ctx.expandedItemPanels.value.has(node.id) ? 'teal' : 'grey'"
          :title="node.hasChildren ? 'Позиции самого направления (не подкатегорий): показать / добавить плановую' : 'Показать плановые / фактические позиции'"
          @click="node.hasChildren ? ctx.toggleItemPanel(node) : toggleNodeExpansion(node)"
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
          <!-- «Сделать плановой позицией» (владелец, задача 3) — у категории без
               подкатегорий и ровно с одной плановой позицией, обычно дублирующей
               её же имя. collapseCandidate — единственный источник и для этой
               кнопки, и для счётчика/диалога массового сворачивания в
               FeoTreeToolbar.vue (Правило №6, useFeoCategoryCollapse.ts). -->
          <v-btn v-if="ctx.canEditFeo.value && collapseCandidate" icon="mdi-arrow-collapse-up" variant="text" size="x-small"
            :color="collapseCandidate.blocked_reason ? 'grey' : 'blue-grey-darken-1'"
            :disabled="!!collapseCandidate.blocked_reason"
            :loading="feoCollapse.singleCollapsing.value === node.id"
            :title="collapseCandidate.blocked_reason
              ? `Нельзя свернуть: ${collapseCandidate.blocked_reason}`
              : `Сделать плановой позицией: «${collapseCandidate.planned_item_name}» переедет в родительскую категорию, сама категория «${node.name}» исчезнет, деньги ФЭО категории перейдут на позицию`"
            @click="onCollapseToItem"
          />
          <v-btn v-if="ctx.canEditFeo.value" icon="mdi-delete-outline" variant="text" size="x-small" color="error"
            title="Удалить" @click="ctx.confirmFeoDelete(node)" />
          <!-- Комментарии к категории (владелец, Волна 4, п.16) — раскрывает
               ветку комментариев в отдельной строке ниже (см. FeoCommentThread.vue
               ниже). Правка 2026-09-14: иконка видна ВСЕГДА (общий переключатель
               наверху таблицы больше не прячет её — он лишь массово раскрывает/
               сворачивает ветки, см. докстринг isFirstVisibleRow строки выше).
               Правка 2026-09-15 (жалоба владельца — «раскрыть всё» открывало
               пустые карточки «Комментариев пока нет»): счётчик рядом с иконкой
               ВИДЕН ДО раскрытия — по нему сразу понятно, есть ли комментарии и
               сколько, не только по цвету/заливке самой иконки. Клик по иконке
               работает КАК РАНЬШЕ — просто переключает commentsExpanded
               локально, и открывает ветку даже если comment count = 0 (иначе
               некуда было бы написать первый комментарий).
               НЕ v-badge — в первом прогоне живой проверки на стенде (2026-09-15)
               v-badge оказался ДОСТАТОЧНО КРУПНЫМ, чтобы полностью накрыть
               x-small-иконку в тесной колонке «Действия» и перехватывать клик
               мимо кнопки (поймано Playwright: "intercepts pointer events" — это
               не строгость теста, а реальный клик мимо цели у живого
               пользователя). Свой маленький уголковый бейдж вместо этого:
               pointer-events:none, чтобы клик всегда доходил до кнопки под ним. -->
          <span class="feo-comment-icon-wrap">
            <v-btn
              :icon="categoryCommentCount > 0 ? 'mdi-comment-text' : 'mdi-comment-text-outline'"
              variant="text" size="x-small" :color="commentsExpanded ? 'teal' : 'grey-darken-1'"
              title="Комментарии к этой категории"
              @click.stop="commentsExpanded = !commentsExpanded"
            />
            <span v-if="categoryCommentCount > 0" class="feo-comment-count-badge">{{ categoryCommentCount }}</span>
          </span>
        </div>
      </div>
    </td>
  </tr>

  <!-- Разделяющая подпись перед панелью собственных позиций направления
       (владелец, 2026-09-14, вторая волна): теперь один клик по папке
       раскрывает СРАЗУ и подразделы, и панель позиций самого направления —
       они окажутся под одной строкой одновременно, и без подписи было бы
       непонятно, что мини-таблица ниже относится к самому направлению
       («Стенды»/«Ростов»), а не к первой попавшейся подкатегории. Рисуется
       ЗДЕСЬ (в FeoTreeRow.vue, не в FeoLevel5Panel.vue) — FeoTreeTable.vue
       рендерит <FeoTreeRow>, затем <FeoLevel5Panel> как соседний <tr> для
       того же узла (Правило №6, второй компонент не трогаем): любой <tr>,
       добавленный в конец шаблона ЭТОГО компонента, гарантированно окажется
       ПЕРЕД панелью в DOM. Сами подкатегории — отдельные строки со своими
       именами и увеличенным отступом сразу после панели, вторая подпись
       перед ними не нужна: они и так самоочевидно другие строки. -->
  <tr v-if="node.hasChildren && ctx.expandedItemPanels.value.has(node.id)">
    <td colspan="7" :style="{ padding: `2px 8px 0 ${node.depth * 20 + 32}px` }">
      <span class="feo-own-items-caption">
        <v-icon size="12" icon="mdi-clipboard-text-outline" class="mr-1" />Плановые позиции самого направления «{{ node.name }}» — не входят в подкатегории ниже
      </span>
    </td>
  </tr>

  <!-- Ветка комментариев категории — раскрывающийся блок под строкой (не
       колонка), как и панель «Плановые vs факт» в FeoLevel5Panel.vue соседом.
       Правка 2026-09-14: больше не гейтится общим переключателем видимости
       (тот теперь управляет только начальным раскрытием, см. commentsExpanded
       ниже) — только собственным состоянием раскрытия этой ветки. -->
  <tr v-if="commentsExpanded">
    <td colspan="7" style="padding:0">
      <div style="margin:6px 8px 10px 32px;padding:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px">
        <FeoCommentThread :feo-category-id="node.id" :subsidy-id="subsidyId" />
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
// Основная строка узла дерева ФЭО (наименование, финансирование, плановое
// кол-во/сумма, «в плане-графике», остаток, действия — со всеми плашками
// превышения плана) — вынесена из SubsidiesView.vue (волна 5c). Level 5 панель
// (плановые vs фактические) — соседний <tr>, см. FeoLevel5Panel.vue.
import { computed, ref, onMounted, toRef, watch } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
import { formatCurrency } from '@/composables/subsidies/format'
import { useFeoComments } from '@/composables/subsidies/useFeoComments'
import { usePlanToRequest, RESIDUAL_SELECTION_TOOLTIP } from '@/composables/subsidies/usePlanToRequest'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import { useToast } from '@/composables/useToast'
import type { FeoNode } from '@/composables/subsidies/types'
import FeoCommentThread from './FeoCommentThread.vue'
// Раздел C0/E (план ancient-prancing-music.md, 2026-09-21): переключатель
// «целиком / товары-услуги» (useKpiPrefs.ts — пишет параллельный агент, см.
// задание волны: карточки KPI и второй экземпляр переключателя в
// FeoTreeToolbar.vue читают тот же общий pref) + превышения по типу
// (useFeoTreeExcess.ts, singleton уже построен SubsidiesView.vue — здесь
// переиспользуется БЕЗ ctx, тот же приём, что и useFeoLevel5Api() в
// FeoLevel5Panel.vue). ⚠️ useKpiPrefs.ts на момент написания этого файла ещё
// не существовал (пишет другой агент параллельно) — импорт по согласованному
// пути, npx vue-tsc --noEmit перепроверить, когда файл появится.
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import { useFeoTreeExcess } from '@/composables/subsidies/useFeoTreeExcess'
import { useFeoTreeAmounts } from '@/composables/subsidies/useFeoTreeAmounts'

const props = defineProps<{ node: FeoNode }>()
// ФИКС (найден QA стека отмены, доп. волна 2026-09-14): `const node = props.node`
// захватывал ОБЪЕКТ props.node ОДИН РАЗ при монтировании компонента — v-for в
// FeoTreeTable.vue переиспользует уже смонтированный экземпляр по :key="node.id"
// (id не меняется при правке ПОЛЕЙ категории), поэтому <script setup> не
// перезапускается, а `node` в шаблоне навсегда оставался ссылкой на СТАРЫЙ
// объект — правка направления (имя/бюджет/т.д.) сохранялась на сервере
// (проверено сетевым логом и повторным GET), но строка дерева не обновлялась
// без полной перезагрузки страницы. toRef(props, 'node') — реактивная ссылка
// НА ТЕКУЩЕЕ значение props.node; шаблон Vue автоматически разворачивает
// топ-level ref (node.name работает как раньше, без node.value.*) — единственное
// исключение — node.id внутри <script setup> (isFirstVisibleRow ниже), там
// разворачивание ручное. Баг был и до стека отмены (обычная правка направления
// через диалог тоже не обновляла дерево без Ctrl+F5) — не только для undo/redo.
const node = toRef(props, 'node')

const ctx = useSubsidyDetailCtx()
const kpi = useKpiDrilldown(ctx)
// Раздел C0/E — см. докстринг у импортов выше. Оба уже построены как singleton
// (SubsidiesView.vue вызывает их с ctx при монтировании дерева раньше первой
// строки) — вызов без аргумента возвращает тот же объект.
const kpiPrefs = useKpiPrefs()
const feoTreeExcess = useFeoTreeExcess()
const feoTreeAmounts2 = useFeoTreeAmounts()

// Выбор категории/поддерева целиком (задача 1) — состояние чекбокса перед
// шевроном читает usePlanToRequest.ts::subtreeSelectionState (единственный
// источник, тот же Set выбора, что и построчные чекбоксы FeoLevel5Panel.vue).
const planToRequest = usePlanToRequest()
const subtreeSelection = computed(() => planToRequest.subtreeSelectionState(node.value, ctx.feoCategories.value))
// Подпись чекбокса категории (правка 2026-09-21, СЖАТО после приёмки: полный
// текст «Выбрано k из N незакупленных» рвал колонку «Наименование» по буквам —
// теперь компактный чип «k из N» (N=0 → просто «0»), полный текст ушёл в
// tooltip ниже. Тот же subtreeSelection, второй источник счёта не заводим
// (Правило №6).
const subtreeSelectionLabel = computed(() => {
  const s = subtreeSelection.value
  if (s.total === 0) return '0'
  return `${s.selectedCount} из ${s.total}`
})
// Tooltip чекбокса категории — счёт + тот же explain-текст, что и у кнопки
// «Вся смета» (usePlanToRequest.ts::RESIDUAL_SELECTION_TOOLTIP, единственный
// источник объяснения, второй не заводим — Правило №6).
const subtreeSelectionTooltip = computed(() => {
  const s = subtreeSelection.value
  if (s.total === 0) return 'В этой категории нет незакупленных плановых позиций. ' + RESIDUAL_SELECTION_TOOLTIP
  return `Выбрано ${s.selectedCount} из ${s.total} незакупленных. ` + RESIDUAL_SELECTION_TOOLTIP
})

// Сворачивание категории-дубля в плановую позицию (задача 3) — тот же список
// кандидатов, что считает счётчик/диалог в FeoTreeToolbar.vue (Правило №6).
const feoCollapse = useFeoCategoryCollapse()
const collapseCandidate = computed(() => (node.value.hasChildren ? undefined : feoCollapse.candidateFor(node.value.id)))
function onCollapseToItem() {
  const cand = collapseCandidate.value
  if (!cand || cand.blocked_reason) return
  // Подтверждение — v-dialog (FeoCollapseConfirmDialog.vue, рендерится один раз
  // в FeoTreeToolbar.vue), не window.confirm() (координатор, приёмка в браузере).
  feoCollapse.openSingleCollapseDialog(node.value.id, node.value.name, cand.planned_item_name)
}

// Тот же гейт, что и в SubsidyEditDialog.vue/FeoTreeToolbar.vue (canSaveVersion) —
// вычисляется независимо здесь же (простая проверка роли из localStorage, не формула,
// дублирование не нарушает Правило №6).
const userRoleRaw = localStorage.getItem('user_role') || ''
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))

// Комментарии к плану ФЭО (владелец, Волна 4, п.16) — переиспользуем ОДИН
// FeoCommentThread.vue (та же копия, что и у плановых позиций в
// FeoLevel5Panel.vue, см. её докстринг) + один общий переключатель видимости
// на всю субсидию, рисуемый ровно в первой видимой строке дерева.
const feoComments = useFeoComments()
const toast = useToast()
const commentsExpanded = ref(false)
const subsidyId = computed(() => ctx.selectedId.value)

// «Первая видимая строка» — единственное место, где рисуется общий
// переключатель (см. шаблон выше): ctx.visibleFeoNodes — тот же поток узлов,
// что рендерит FeoTreeTable.vue через v-for (Правило №6, ничего не пересчитываем
// заново), просто сверяем id первого элемента с id текущего узла.
const isFirstVisibleRow = computed(() => ctx.visibleFeoNodes.value[0]?.id === node.value.id)

// Счётчик комментариев ЭТОЙ категории (владелец, 2026-09-15) — читает
// уже загруженный общесубсидийный кэш (см. loadCounts в onMounted ниже),
// единственный источник и для бейджа, и для решения «раскрывать ли ветку
// при массовом раскрытии» (watch на expandAllSignal ниже).
const categoryCommentCount = computed(() => feoComments.categoryCommentCount(subsidyId.value, node.value.id))

// Состав плановой суммы направления (жалоба владельца 2026-09-14: «не понял,
// как суммировалось 831 972, вижу только подкатегории на 550 000») — явно
// показываем оба слагаемых, из которых складывается число в колонке выше,
// а не только «довесок» на самом направлении. Показываем ТОЛЬКО когда обе
// части реально есть — своя сумма (feoOwnDirectionPlanFor) И план по
// подкатегориям (feoChildrenPlanManualFor); суммы читаем из
// useFeoTreeAmounts.ts (Правило №6, здесь ничего не пересчитывается).
const feoDirectionCompositionText = computed(() => {
  const n = node.value
  if (!n.hasChildren) return null
  const own = ctx.feoOwnDirectionPlanFor(n)
  const children = ctx.feoChildrenPlanManualFor(n)
  if (own <= 0.005 || children <= 0.005) return null
  const count = ctx.feoChildrenWithPlanCountFor(n)
  const byWord = count === 1 ? 'подкатегории' : 'подкатегориям'
  return `состав: ${formatCurrency(children)} по ${count} ${byWord} + ${formatCurrency(own)} на самом направлении`
})

// КОРЕНЬ жалобы владельца (2026-09-14, уточнение по п.6): у направления с
// подразделами шеврон/папка раскрывают ТОЛЬКО подразделы (ctx.toggleExpand) —
// панель собственных плановых позиций (ctx.toggleItemPanel/expandedItemPanels)
// у такого узла до сих пор открывалась ЕДИНСТВЕННО крошечной иконкой в самом
// конце строки, в колонке «Действия», и НИЧЕМ не анонсировалась заранее — по
// строке было не видно, что на направлении вообще что-то лежит. Ровно это
// владелец описал как «позиции исчезли из поля видимости»: они не удалялись
// (категория 4792 — «Стенды» 0 ₽ и «Ростов» 281 972 ₽ по-прежнему активны),
// их просто неоткуда было увидеть. Этот бейдж — ЗАМЕТНЫЙ (не мелкая серая
// пометка) счётчик прямо у названия направления, который: (1) виден ДО любого
// раскрытия, (2) кликабелен и открывает ту же панель, что и иконка в
// «Действиях» (Правило №6 — общий toggleItemPanel/expandedItemPanels, свой
// переключатель не заводим). Условие показа — то же самое hasOwnPlannedAmountFor,
// что уже управляет иконкой в «Действиях» (см. докстринг там же).
// СУММОЙ, не количеством: реальный список FeoPlannedItem направления (тот,
// что покажет панель) грузится лениво — только по клику (ensureComparison /
// toggleItemPanel в useFeoLevel5.ts), поэтому ДО раскрытия точного числа
// позиций у нас нет. feoOwnDirectionPlanFor(node) — тот же надёжный источник,
// что уже используется для «в т.ч. на самом направлении» и для «состава
// суммы» выше (Правило №6) — его и показываем, чтобы не выдумывать цифру.
const feoOwnItemsBadgeText = computed(() => {
  const n = node.value
  if (!n.hasChildren || !ctx.hasOwnPlannedAmountFor(n)) return null
  const own = ctx.feoOwnDirectionPlanFor(n)
  if (own > 0.005) return `на направлении: ${formatCurrency(own)}`
  return 'на направлении есть позиции'
})

// ЕДИНСТВЕННОЕ место, решающее «что открыть по клику» — жалоба владельца
// 2026-09-14 (вторая волна): «пусть если это на направлении лежит, то
// разворачивается вместе с папкой, а не отдельным нажатием. Зачем оно
// отдельно, это тоже входит в состав "Канцелярские и бытовые расходы..."».
// Раньше шеврон/папка вызывали ctx.toggleExpand ТОЛЬКО подразделов, а панель
// собственных позиций (ctx.toggleItemPanel) была отдельным действием, до
// которого добирались лишь бейджем/иконкой в «Действиях» — два независимых
// переключателя для одного направления. Теперь везде (шеврон, папка, бейдж,
// строка состава суммы, иконка в «Действиях») зовут ЭТУ функцию:
// - лист (без подразделов) — как раньше, просто toggleItemPanel;
// - направление без своих позиций — как раньше, просто toggleExpand;
// - направление С ОБЕИМИ частями — оба состояния переключаются СОГЛАСОВАННО
//   за один клик: раскрыл — открылись подразделы И панель позиций; свернул —
//   закрылось и то, и другое. Целевое состояние берём из expandedIds (что
//   сейчас видно по подразделам) и приводим expandedItemPanels к нему же —
//   так функция самовосстанавливает согласованность, даже если панель была
//   открыта раньше каким-то другим путём (например, снэпшотом KPI-дриллдауна).
function toggleNodeExpansion(node: FeoNode) {
  if (!node.hasChildren) {
    ctx.toggleItemPanel(node)
    return
  }
  if (!ctx.hasOwnPlannedAmountFor(node)) {
    ctx.toggleExpand(node.id)
    return
  }
  const willExpand = !ctx.expandedIds.value.includes(node.id)
  ctx.toggleExpand(node.id)
  const panelOpen = ctx.expandedItemPanels.value.has(node.id)
  if (willExpand !== panelOpen) ctx.toggleItemPanel(node)
}

// Правка 2026-09-14 (жалоба владельца): раньше этот флаг только прятал иконку;
// теперь на старте ветки её раскрытие подстраивается ПОД ТЕКУЩЕЕ положение
// общего переключателя (так свежесмонтированная строка — например, только что
// раскрытая подкатегория — выглядит согласованно с уже видимыми ветками), а
// дальше живёт своим независимым commentsExpanded (клик по иконке ничего не
// шлёт на сервер и не трогает feoComments.expandAllSignal).
onMounted(async () => {
  if (subsidyId.value == null) return
  // loadCounts — дедуп на уровне composable (module-level singleton
  // countsPromises): сколько бы строк дерева ни смонтировалось одновременно,
  // сетевой запрос на субсидию уйдёт РОВНО ОДИН (жалоба владельца 2026-09-15
  // про десятки запросов при «развернуть все»). Не await — не блокируем
  // готовность строки её результатом, значение подтянется реактивно.
  void feoComments.loadCounts(subsidyId.value)
  const visible = await feoComments.loadVisibility(subsidyId.value)
  // Жалоба владельца 2026-09-15: «если комментариев нет, то и поле показываться
  // не должно» — начальное раскрытие следует за общим переключателем ТОЛЬКО у
  // веток, где комментарии реально есть; пустые остаются свёрнутыми, даже если
  // переключатель сейчас в положении «все развёрнуты».
  commentsExpanded.value = visible && categoryCommentCount.value > 0
})

// Синхронизация с общим переключателем (см. broadcastExpandAll в
// useFeoComments.ts) — реагируем на version, а не на пару (subsidyId, expanded),
// чтобы повторное «включили те же значения» тоже применилось. После этого
// события commentsExpanded снова свободно живёт локально до следующего
// broadcast — обычный клик по иконке ветки его не трогает.
watch(() => feoComments.expandAllSignal.version, () => {
  if (feoComments.expandAllSignal.version === 0) return
  if (feoComments.expandAllSignal.subsidyId !== subsidyId.value) return
  const expanded = feoComments.expandAllSignal.expanded
  // Массовое «развернуть» открывает ТОЛЬКО ветки с реальными комментариями
  // (жалоба владельца, см. задачу) — пустые не трогаем вовсе, они остаются в
  // текущем состоянии (обычно свёрнуты). Массовое «свернуть» по-прежнему
  // закрывает ВСЕ ветки безусловно, включая те, что были раскрыты вручную
  // индивидуальным кликом по иконке.
  commentsExpanded.value = expanded ? categoryCommentCount.value > 0 : false
})

async function onToggleCommentsVisible(val: boolean | null) {
  if (subsidyId.value == null) return
  const next = !!val
  try {
    await feoComments.setVisibility(subsidyId.value, next)
    feoComments.broadcastExpandAll(subsidyId.value, next)
  } catch (e: any) {
    toast.addToast(e?.payload?.message || e?.detail || e?.message || 'Не удалось изменить видимость комментариев', 'error')
  }
}
</script>
