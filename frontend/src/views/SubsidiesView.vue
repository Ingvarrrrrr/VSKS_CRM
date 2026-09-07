<template>
  <div class="subsidies-page">

    <!-- ── Header ── -->
    <SubsidyListHeader v-model:add-open="showAddDialog" :registry-area="registryArea" />

    <!-- ── Loading ── -->
    <div v-if="loading" class="d-flex justify-center py-16">
      <v-progress-circular indeterminate color="primary" size="52" />
    </div>

    <template v-else>
      <!-- ── Empty ── -->
      <div v-if="filteredSubsidies.length === 0" class="empty-state">
        <v-icon icon="mdi-cash-off" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-3">Нет субсидий за {{ selectedYear }} год</div>
        <v-btn class="mt-4" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="showAddDialog = true">
          Добавить субсидию
        </v-btn>
      </div>

      <template v-else>
       <div ref="registryArea">
        <SubsidyListTable v-if="effectiveView === 'table'" />
        <SubsidyCardsGrid v-else />
       </div>

        <!-- ── Summary bar ── -->
        <SubsidySummaryBar />

        <!-- ── Detail panel ── -->
        <div v-if="selectedSubsidy" class="detail-panel">
          <div class="detail-header">
            <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
            <span class="detail-title">{{ selectedSubsidy.name }} — направления ФЭО</span>
            <v-chip v-if="selectedSubsidy.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
            <v-btn
              v-if="canApproveSubsidy(selectedSubsidy)"
              size="small" variant="tonal" color="success" prepend-icon="mdi-check-decagram"
              class="ml-3"
              :loading="approvingSubsidyId === selectedSubsidy.id"
              @click="approveSubsidy(selectedSubsidy)"
            >Утвердить</v-btn>
            <v-btn icon="mdi-close" size="x-small" variant="text" class="ml-auto" @click="selectedId = null" />
          </div>

          <!-- KPI mini-cards for selected subsidy -->
          <SubsidyKpiCards />

          <!-- FEO categories -->
          <div v-if="loadingFeo" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <div v-else>
            <FeoTreeToolbar />

            <div v-if="feoCategories.length === 0" class="feo-empty">
              <v-icon icon="mdi-folder-off" size="40" color="grey-lighten-2" />
              <div class="text-caption text-medium-emphasis mt-2">Нет категорий ФЭО</div>
            </div>

            <!-- FEO table with D&D, inline edit, total row -->
            <div v-else ref="feoTableArea" class="feo-table-wrap">
              <table class="feo-table">
                <thead>
                  <tr>
                    <th class="feo-th feo-th-name" :style="feoResize.resizeStyle('name')">
                      Наименование
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'name')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('budget')">
                      <div>Количество и<br>финансирование по ФЭО</div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'budget')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('qty')">
                      <div>ПЛАНОВОЕ<br>КОЛ-ВО</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="plannedQtyBase === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции заявок в плане закупок"
                          @click.stop="plannedQtyBase = 'all'"
                        >все</span>
                        <span
                          :class="plannedQtyBase === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только ручной план ФЭО"
                          @click.stop="plannedQtyBase = 'manual'"
                        >ручные</span>
                        <span
                          :class="plannedQtyBase === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только позиции заявок со статусом «План закупок» и дальше"
                          @click.stop="plannedQtyBase = 'requests'"
                        >из заявок</span>
                        <span
                          :class="plannedQtyBase === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                          @click.stop="plannedQtyBase = 'purchases'"
                        >по закупкам</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'qty')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('planned')">
                      <div>ПЛАНОВАЯ<br>СУММА</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="plannedSumBase === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции заявок в плане закупок"
                          @click.stop="plannedSumBase = 'all'"
                        >все</span>
                        <span
                          :class="plannedSumBase === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только ручной план: кол-во × стоимость за ед."
                          @click.stop="plannedSumBase = 'manual'"
                        >ручные</span>
                        <span
                          :class="plannedSumBase === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Только позиции заявок со статусом «План закупок» и дальше"
                          @click.stop="plannedSumBase = 'requests'"
                        >из заявок</span>
                        <span
                          :class="plannedSumBase === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                          @click.stop="plannedSumBase = 'purchases'"
                        >по закупкам</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'planned')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('spent')"
                      title="Сумма всех позиций закупок этой категории во всех статусах плана закупок (включая «План закупок»), в отличие от договорного факта"
                    >
                      В плане-графике
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'spent')"></span>
                    </th>
                    <th class="feo-th feo-th-num" :style="feoResize.resizeStyle('residual')">
                      <div>ОСТАТОК</div>
                      <div class="feo-residual-toggle">
                        <span
                          :class="residualBase === 'plan' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Остаток = Плановая сумма − В плане-графике"
                          @click.stop="residualBase = 'plan'"
                        >от плановой</span>
                        <span
                          :class="residualBase === 'feo' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                          title="Остаток = Финансирование по ФЭО − В плане-графике"
                          @click.stop="residualBase = 'feo'"
                        >от ФЭО</span>
                      </div>
                      <span class="col-resize-handle" @mousedown="feoResize.onResizeStart($event, 'residual')"></span>
                    </th>
                    <th class="feo-th feo-th-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="node in visibleFeoNodes" :key="node.id">
                    <tr
                      v-if="isNodeVisible(node) && !(plannedBase === 'requests' && isManualPosLeaf(node))"
                      class="feo-tr"
                      :data-feo-node-id="node.id"
                      :class="[
                        `feo-tr--l${node.level}`,
                        dragOverId === node.id ? 'feo-drop-target' : '',
                        dragNodeId === node.id ? 'feo-dragging' : '',
                        kpi.kpiNodeClass(node),
                      ]"
                      :draggable="canEditFeo"
                      @dragstart="canEditFeo && onDragStart($event, node)"
                      @dragover.prevent="canEditFeo && onDragOver($event, node)"
                      @dragleave="onDragLeave"
                      @drop="canEditFeo && onDrop($event, node)"
                      @dragend="onDragEnd"
                    >
                      <!-- Наименование -->
                      <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
                        <div class="feo-name-inner">
                          <!-- Лист ФЭО: клик по папке/шеврону раскрывает ЕДИНУЮ панель «Плановые
                               позиции» (expandedItemPanels/toggleItemPanel) — единственный источник
                               детализации листа с 2026-08-07 (устранение тройного рендера одной и
                               той же позиции, см. ШАГ 1 плана дедупликации дерева ФЭО). Раньше здесь
                               был отдельный toggleReqItems (hasReqItems), дававший второй независимый
                               список тех же позиций закупок — убран целиком. -->
                          <span class="feo-tree-chevron" @click="node.hasChildren ? toggleExpand(node.id) : toggleItemPanel(node)">
                            <v-icon
                              v-if="node.hasChildren"
                              size="15"
                              :icon="expandedIds.includes(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                              color="grey"
                              class="mr-1 cursor-pointer"
                            />
                            <v-icon
                              v-else
                              size="15"
                              :icon="expandedItemPanels.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                              color="grey"
                              class="mr-1 cursor-pointer"
                            />
                          </span>
                          <v-icon
                            size="16"
                            class="mr-1 flex-shrink-0 cursor-pointer"
                            :icon="node.hasChildren
                              ? (expandedIds.includes(node.id) ? 'mdi-folder-open' : 'mdi-folder')
                              : (expandedItemPanels.has(node.id) ? 'mdi-folder-open' : 'mdi-folder')"
                            :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
                            @click="node.hasChildren ? toggleExpand(node.id) : toggleItemPanel(node)"
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
                      <!-- vertical-align:top (жалоба владельца 2026-08-17, разбор превышения): .feo-td
                           по умолчанию vertical-align:middle — когда «Плановая сумма» справа выросла
                           расшифровкой «из-за: …» на несколько строк, соседние числовые колонки
                           центрировались по всей высоте строки и визуально ЗАЛЕЗАЛИ на середину текста
                           расшифровки. top — сироты не всплывают в середину. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <template v-if="feoRollup(node).qty != null || feoRollup(node).amount != null">
                          <div class="feo-plan-note text-right"
                            :class="feoRollup(node).qtyAuto || feoRollup(node).amountAuto ? 'text-medium-emphasis' : ''"
                            :title="(feoRollup(node).qtyAuto || feoRollup(node).amountAuto) ? 'Сумма по вложенным' : 'Количество и стоимость по документу ФЭО'"
                          >
                            <template v-if="feoRollup(node).qty != null && feoRollup(node).amount != null">
                              {{ feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : '' }} × {{ feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
                            </template>
                            <template v-else-if="feoRollup(node).qty != null">
                              {{ feoRollup(node).qty }}{{ node.feo_unit ? ` ${node.feo_unit}` : ' шт' }}
                            </template>
                            <template v-else>
                              {{ feoRollup(node).amount?.toLocaleString('ru-RU') }} ₽
                            </template>
                            <v-chip v-if="feoRollup(node).qtyAuto || feoRollup(node).amountAuto" size="x-small" color="blue-grey" variant="tonal" class="ml-1">авто</v-chip>
                          </div>
                        </template>
                        <div v-if="inlineBudgetId === node.id" class="d-flex align-center justify-end">
                          <input
                            ref="inlineInputEl"
                            v-model="inlineBudgetVal"
                            type="number"
                            class="inline-input"
                            @blur="saveInlineBudget(node)"
                            @keydown.enter="saveInlineBudget(node)"
                            @keydown.esc="inlineBudgetId = null"
                          />
                        </div>
                        <div v-else-if="isAutoNode(node)" class="feo-amount-cell text-right" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineBudget(node)"
                          :title="canEditFeo ? 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план. Кликните, чтобы задать вручную' : 'Расчёт: ручное ФЭО дочерних; без ФЭО — факт (поставлено/оплачено), иначе план'"
                        >
                          <template v-if="feoEffectiveFor(node) > 0">
                            <span class="feo-amount text-medium-emphasis">{{ formatCurrency(feoEffectiveFor(node)) }}</span>
                            <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1">расчёт</v-chip>
                          </template>
                          <span v-else-if="canEditFeo" class="feo-set-hint">Задать</span>
                          <span v-else class="feo-set-hint">—</span>
                        </div>
                        <div v-else class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineBudget(node)">
                          <span v-if="feoBudgetFor(node) > 0" class="feo-amount"
                            :style="feoChildrenBudgetDiff(node) > 0.005 ? 'color:#EF4444;font-weight:700' : ''"
                          >{{ formatCurrency(feoBudgetFor(node)) }}</span>
                          <span v-else-if="canEditFeo" class="feo-set-hint">Задать</span>
                          <span v-else class="feo-set-hint">—</span>
                        </div>
                        <template v-if="node.hasChildren && node.budget != null && node.budget > 0">
                          <div v-if="!hasManualChildFeo(node)"
                            class="feo-plan-note text-medium-emphasis"
                            title="Ни у одной дочерней строки не задано финансирование по ФЭО"
                          >
                            Подробное деление в ФЭО отсутствовало
                          </div>
                          <div v-else-if="feoChildrenBudgetDiff(node) > 0.005"
                            class="feo-plan-note" style="color:#EF4444"
                            :title="`Ручное ФЭО дочерних ${formatCurrency(manualChildFeoSum(node))} превышает финансирование этой строки ${formatCurrency(node.budget || 0)}. Ищите лишнюю сумму в дочерних строках.`"
                          >
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }} — лишние {{ formatCurrency(feoChildrenBudgetDiff(node)) }}
                          </div>
                          <div v-else-if="feoChildrenBudgetDiff(node) < -0.005"
                            class="feo-plan-note" style="color:#F59E0B"
                            :title="`Ручное ФЭО дочерних ${formatCurrency(manualChildFeoSum(node))} меньше финансирования этой строки ${formatCurrency(node.budget || 0)}. Часть суммы не распределена по дочерним в ФЭО.`"
                          >
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }} — не распределено {{ formatCurrency(-feoChildrenBudgetDiff(node)) }}
                          </div>
                          <div v-else class="feo-plan-note text-medium-emphasis">
                            заложено в ФЭО {{ formatCurrency(manualChildFeoSum(node)) }}
                          </div>
                        </template>
                      </td>

                      <!-- Плановое количество -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <div v-if="isAutoQtyNode(node)" class="text-right">
                          <div class="feo-amount">{{ feoQtyDisplayFor(node) > 0 ? feoQtyDisplayFor(node) : '—' }}{{ node.unit ? ` ${node.unit}` : '' }}</div>
                          <div v-if="plannedQtyBase === 'all' && feoQtyRequestsFor(node) > 0"
                            class="feo-plan-note text-medium-emphasis"
                            :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${feoQtyRequestsFor(node)}`"
                          >
                            в т.ч. из заявок {{ feoQtyRequestsFor(node) }}
                          </div>
                          <v-chip size="x-small" color="blue-grey" variant="tonal"
                            title="Количество автоматически считается из дочерних"
                          >авто</v-chip>
                        </div>
                        <div v-else-if="inlineQtyId === node.id" class="d-flex align-center justify-end">
                          <input
                            ref="inlineQtyInputEl"
                            v-model="inlineQtyVal"
                            type="number"
                            class="inline-input"
                            @blur="saveInlineQty(node)"
                            @keydown.enter="saveInlineQty(node)"
                            @keydown.esc="inlineQtyId = null"
                          />
                        </div>
                        <template v-else>
                          <!-- feo-amount-cell — display:inline-flex (см. стили ниже, нужен для строки
                               «сумма/чип» в других колонках) — блочные пояснения feo-plan-note ниже
                               ВЫНЕСЕНЫ из него сиблингами (как в колонке «Финансирование по ФЭО»,
                               см. td выше), иначе inline-flex склеивает их с суммой в одну строку без
                               пробела («204 услугав т.ч. из заявок 2», баг вёрстки 2026-08-07). -->
                          <div class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineQty(node)">
                            <span v-if="feoQtyDisplayFor(node) > 0" class="feo-amount">{{ feoQtyDisplayFor(node) }}{{ node.unit ? ` ${node.unit}` : '' }}</span>
                            <span v-else class="feo-set-hint">—</span>
                          </div>
                          <div v-if="plannedQtyBase === 'all' && feoQtyRequestsFor(node) > 0"
                            class="feo-plan-note text-medium-emphasis"
                            :title="`Количество из позиций заявок в статусе «План закупок» и дальше: ${feoQtyRequestsFor(node)}`"
                          >
                            в т.ч. из заявок {{ feoQtyRequestsFor(node) }}
                          </div>
                          <template v-if="plannedQtyBase === 'all' && matchedReqFor(node).length">
                            <div v-if="mergedQtyDiff(node) > 0"
                              class="feo-plan-note" style="color:#F59E0B"
                              :title="`Всего запланировано ${feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
                            >
                              на {{ mergedQtyDiff(node) }} превышает заложенный в ФЭО показатель ({{ Number(node.feo_quantity) || 0 }})
                            </div>
                            <div v-else-if="mergedQtyDiff(node) < 0"
                              class="feo-plan-note text-medium-emphasis"
                              :title="`Всего запланировано ${feoQtyDisplayFor(node)}, в ФЭО заложено ${Number(node.feo_quantity) || 0}`"
                            >
                              не хватает {{ -mergedQtyDiff(node) }} до заложенного в ФЭО ({{ Number(node.feo_quantity) || 0 }})
                            </div>
                          </template>
                        </template>
                      </td>

                      <!-- Плановая сумма: ручной план ФЭО и/или позиции заявок (по переключателю) -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span v-if="feoPlannedDisplayFor(node) > 0" class="feo-amount"
                          :style="(feoDisplayedFor(node) > 0 && feoPlannedDisplayFor(node) > feoDisplayedFor(node)) || feoHasOverspentDescendant(node) ? 'color:#EF4444;font-weight:700' : ''"
                          :title="plannedSumBase === 'all' ? `Ручные ${formatCurrency(feoPlannedTotalFor(node))} + из заявок ${formatCurrency(feoPlannedRequestsFor(node))}` : ''"
                        >{{ formatCurrency(feoPlannedDisplayFor(node)) }}</span>
                        <span v-else class="feo-amount-empty">—</span>
                        <!-- Заметка «в т.ч. из заявок N ₽» под плановой суммой УБРАНА (жалоба
                             владельца 2026-08-13): совпадает по величине с «в закупках» из строки
                             разбора ниже (feoResidualNoteFor/feoPlanConsumedNoteFor), но стояла прямо
                             под планом и читалась как его часть — «выбрано 695 656, что уже больше
                             561». Та же заметка в колонке «Плановое количество» (feoQtyRequestsFor,
                             см. ниже по файлу) НЕ трогается — она про количество, путаницы там не
                             было. Заметка «в т.ч. из заявок {{ matchedReqTotal }}» (matchedReqFor,
                             сопоставление по ИМЕНИ) была убрана раньше, 2026-08-07, — см. ШАГ 1
                             плана дедупликации. -->
                        <!-- «В т.ч. на самом направлении N ₽» (жалоба владельца 2026-08-13:
                             «48 441,80 — нигде нет такой суммы», «что это за фантом») — часть плана
                             узла с детьми, заложенная НЕПОСРЕДСТВЕННО на нём самом (плановые позиции,
                             привязанные к направлению, а не к его подкатегориям), см.
                             feoOwnDirectionPlanFor(). Кликабельна — раскрывает ту же панель, что и
                             иконка-список в «Действиях» (toggleItemPanel), см. feo-action-slot ниже. -->
                        <div v-if="feoOwnDirectionPlanFor(node) > 0"
                          class="feo-plan-note text-medium-emphasis feo-plan-note--link"
                          title="Часть плана этого направления, заложенная прямо на нём (не в подкатегориях). Клик открывает список этих плановых позиций"
                          @click="toggleItemPanel(node)"
                        >
                          в т.ч. на самом направлении {{ formatCurrency(feoOwnDirectionPlanFor(node)) }}
                        </div>
                        <!-- Жалоба владельца 2026-08-17: «можно добавить N ₽ до финансирования ФЭО» считало
                             N как ФЭО минус ПЛАН (560 000 − 351 844 = 208 156), хотя в закупках уже размещено
                             432 162 — реально до потолка ФЭО остаётся 127 838 (560 000 − 432 162), меньше почти
                             в 2 раза. Первая строка теперь явно называет себя «остатком по ПЛАНУ», вторая
                             (feoRemainingWithPurchasesNote) появляется, только когда «в закупках» уже больше
                             плана — тогда именно она честная, а не первая. -->
                        <div v-if="feoDisplayedFor(node) > 0 && (node.budget != null || feoPlannedDisplayFor(node) > 0) && Math.abs(feoFinDiff(node)) > 0.005"
                          class="feo-plan-note"
                          :style="feoFinDiff(node) > 0 ? 'color:#16A34A' : 'color:#EF4444'"
                          :title="`Финансирование по ФЭО (бюджет, заложенный в документе ФЭО): ${formatCurrency(feoDisplayedFor(node))}. Плановая сумма (сколько уже расписано по плану/заявкам): ${formatCurrency(feoPlannedDisplayFor(node))}`"
                        >
                          {{ feoFinDiff(node) > 0 ? `по плану можно добавить ещё ${formatCurrency(feoFinDiff(node))} до финансирования ФЭО (это остаток по плану, не по факту закупок)` : `надо убрать ${formatCurrency(-feoFinDiff(node))}, чтобы уложиться в ФЭО` }}
                          <div v-if="feoRemainingWithPurchasesNote(node)"
                            style="font-size:11px;color:#EF4444;font-weight:600;margin-top:2px"
                          >
                            {{ feoRemainingWithPurchasesNote(node) }}
                          </div>
                        </div>
                        <div v-if="!feoIsOverBudget(node) && feoHasOverspentDescendant(node)"
                          class="feo-plan-note" style="color:#EF4444"
                          :title="feoOverspentDescendantTitle(node)"
                        >
                          {{ feoOverspentDescendantText(node) }}
                        </div>
                        <!-- Разбор «план · в закупках · свободно» (жалоба владельца 2026-08-13:
                             «план 513 244 — это откуда? Выбрано 695 — откуда?»). Оба источника
                             (feoResidualNoteFor — лист со своими Ур.5-позициями; feoPlanConsumedNoteFor —
                             остальные узлы, включая направления) теперь берут «план» из ТОГО ЖЕ
                             planTreeByCat.plan_manual, что и шапка строки (не считают свою отдельную
                             формулу), и «в закупках» = привязанные + непривязанные позиции заявок —
                             см. комментарии у функций ниже по файлу. -->
                        <div v-if="feoResidualNoteFor(node)"
                          class="feo-plan-note text-medium-emphasis"
                          title="План: сумма плановых позиций этой категории. В закупках: сколько из них уже набрано заявками (привязанными к этим позициям). Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
                        >
                          план {{ formatCurrency(feoResidualNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(feoResidualNoteFor(node)!.consumed) }} ·
                          <span v-if="feoResidualNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-feoResidualNoteFor(node)!.residual) }}</span>
                          <span v-else>свободно {{ formatCurrency(feoResidualNoteFor(node)!.residual) }}</span>
                          <!-- Расшифровка «больше плана на X» (жалоба владельца 2026-08-13: «откуда 5 121,60,
                               если в позициях плана этого нет?»; продолжение 2026-08-17: «где это превышение
                               80 318? где оно?» — см. factExcessReasonItems, считает ОБА источника: перерасход
                               внутри плановых позиций И закупки без действующей плановой привязки/с мёртвой
                               привязкой). Данные (comparisonData[node.id]) грузятся лениво — если панель плана
                               ещё не раскрывали, вместо расшифровки кнопка «Показать, из-за чего», которая сама
                               догружает сравнение (ensureComparison, тот же запрос, что и обычное раскрытие
                               панели) — точечно для ЭТОГО узла, не для всего дерева разом. -->
                          <div v-if="feoResidualNoteFor(node)!.residual < -0.005" style="font-size:11px;white-space:normal;margin-top:2px">
                            <v-btn v-if="!comparisonData[node.id]"
                              size="x-small" variant="text" color="orange-darken-3"
                              :loading="loadingComparison.has(node.id)"
                              @click.stop="ensureComparison(node.id)"
                            >Показать, из-за чего</v-btn>
                            <template v-else-if="factExcessReasonItems(node).length">
                              <span style="color:#B45309">из-за: </span>
                              <template v-for="(it, idx) in factExcessReasonItems(node)" :key="it.key">
                                <span v-if="idx > 0" style="color:#B45309"> · </span>
                                <a v-if="it.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
                                  :title="`Перейти в закупку ${it.purchases[0].label}`"
                                  @click.stop="router.push(`/orders/${it.purchases[0].id}`)"
                                >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
                                <v-menu v-else location="bottom start">
                                  <template #activator="{ props: excMenuProps }">
                                    <a href="javascript:void(0)" class="feo-purchase-link" v-bind="excMenuProps" @click.stop
                                    >{{ it.name }} +{{ formatCurrency(it.amount) }}</a>
                                  </template>
                                  <v-list density="compact">
                                    <v-list-item v-for="p in it.purchases" :key="p.id" @click="router.push(`/orders/${p.id}`)">
                                      <v-list-item-title>
                                        {{ p.label }} · {{ formatCurrency(p.amount) }}
                                        <span v-if="p.stopped" class="feo-stopped-marker ml-1">остановлена</span>
                                      </v-list-item-title>
                                    </v-list-item>
                                  </v-list>
                                </v-menu>
                              </template>
                              <!-- Сумма расшифровки обязана сходиться с самим числом превышения (владелец,
                                   2026-08-17) — если не сходится (недобор по другим плановым позициям съедает
                                   часть), честно показываем остаток строкой, а не молчим про разницу. -->
                              <span v-if="factExcessReasonRemainder(node) > 0.5" style="color:#B45309">
                                и ещё {{ formatCurrency(factExcessReasonRemainder(node)) }} (гасится недобором по другим плановым позициям — расшифровка не покрывает эту часть один-в-один)
                              </span>
                            </template>
                            <span v-else style="color:#B45309">
                              точную причину разобрать не удалось — {{ formatCurrency(factExcessReasonRemainder(node)) }} без разбивки по позициям
                            </span>
                          </div>
                        </div>
                        <div v-else-if="plannedSumBase === 'all' && feoPlanConsumedNoteFor(node)"
                          class="feo-plan-note text-medium-emphasis"
                          title="План: та же сумма, что и в плановой сумме строки выше. В закупках: сколько из плана уже занято заявками — своими и заявками подкатегорий. Свободно: план минус то, что в закупках — если в закупках больше плана, показано превышение"
                        >
                          план {{ formatCurrency(feoPlanConsumedNoteFor(node)!.planned) }} · в закупках {{ formatCurrency(feoPlanConsumedNoteFor(node)!.consumed) }} ·
                          <span v-if="feoPlanConsumedNoteFor(node)!.residual < -0.005" style="color:#EF4444;font-weight:700">больше плана на {{ formatCurrency(-feoPlanConsumedNoteFor(node)!.residual) }}</span>
                          <span v-else>свободно {{ formatCurrency(feoPlanConsumedNoteFor(node)!.residual) }}</span>
                        </div>
                        <!-- Прогноз «цена выше плановой» — ТОЛЬКО у конечной категории (жалоба
                             владельца 2026-08-13: «вишенкой откуда-то выяснилось, что цена выше
                             плановой и прогноз 1 257 342» — у направления с детьми это план плюс
                             перерасходы детей, число не значит ничего осмысленного). -->
                        <div v-if="!node.hasChildren && feoForecastWarningFor(node)"
                          class="feo-plan-note" style="color:#F97316;font-weight:600"
                          :title="`Если оставшуюся часть купить по нынешней средней цене заказанного, итоговая сумма составит ${formatCurrency(feoForecastWarningFor(node)!.forecast)} — выше плана ${formatCurrency(feoForecastWarningFor(node)!.planManual)}. Не блокирует, только предупреждение`"
                        >
                          если оставшееся купить по нынешней средней цене, выйдет {{ formatCurrency(feoForecastWarningFor(node)!.forecast) }} при плане {{ formatCurrency(feoForecastWarningFor(node)!.planManual) }}
                        </div>
                        <!-- Превышение плана над финансированием ФЭО — требует согласования цепочкой
                             (задача владельца 2026-08-05), см. excessFor()/requestPlanExcessApproval().
                             Детали запроса (шаги, ФИО текущего согласующего, комментарий отказа) —
                             из planExcessApprovals (GET /api/plan-excess?subsidy_id=), см. loadPlanExcessApprovals(). -->
                        <div v-if="excessFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ ПЛАНА (не закупки) {{ formatCurrency(excessFor(node)!.amount) }} · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'approved'">
                            <v-chip size="x-small" color="grey" variant="flat">
                              превышение {{ formatCurrency(excessFor(node)!.amount) }} · согласовано · {{ excessResolvedByName(node) }}{{ excessResolvedDate(node) ? ' · ' + excessResolvedDate(node) : '' }}
                            </v-chip>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение {{ formatCurrency(excessFor(node)!.amount) }} — требуется согласование
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                        </div>
                        <!-- «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено
                             из отката e0db76a): владелец — «в случае превышения должна отображаться
                             данная закупка и показать, что из-за неё всё превысило». Раньше плашка выше
                             называла ТОЛЬКО сумму — виновник нигде не был виден. Крупно, адресно, с
                             прямой ссылкой на закупку. -->
                        <div v-if="excessCulpritFor(node)" class="feo-excess-culprit">
                          <v-icon size="16" icon="mdi-alert-decagram" class="mr-1" />
                          {{ excessCulpritText(node) }}
                          <v-btn v-if="excessCulpritFor(node)!.purchase_id" size="x-small" variant="flat" color="red"
                            class="ml-1" @click.stop="router.push(`/orders/${excessCulpritFor(node)!.purchase_id}`)"
                          >Открыть закупку</v-btn>
                        </div>

                        <!-- Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.5): ВТОРАЯ,
                             независимая плашка — «итог закупки/КП дороже плана» (excess_fact_over_plan),
                             отдельно от превышения плана над финансированием ФЭО выше. Тот же механизм
                             согласования (см. excessFactFor()/requestPlanExcessApproval()). -->
                        <div v-if="excessFactFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ: итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessFactFor(node)!.approved">
                            <v-chip size="x-small" color="grey" variant="flat">
                              итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} · согласовано · {{ excessResolvedByName(node) }}{{ excessResolvedDate(node) ? ' · ' + excessResolvedDate(node) : '' }}
                            </v-chip>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение факта отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              итог закупки дороже плана на {{ formatCurrency(excessFactFor(node)!.amount) }} — требуется согласование
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                        </div>

                        <!-- Замечание владельца п.2 (2026-08-12): ТРЕТЬЯ, независимая плашка — сумма
                             плановых позиций категории превысила вручную заданный план (excessPlanFor).
                             Тот же механизм согласования — см. excessPlanFor()/requestPlanExcessApproval(). -->
                        <div v-if="excessPlanFor(node)" class="feo-plan-note d-flex align-center flex-wrap ga-1 mt-1">
                          <template v-if="excessApprovalFor(node)?.status === 'pending'">
                            <v-chip size="x-small" color="orange" variant="flat">
                              согласование ПРЕВЫШЕНИЯ: план превышает заданный вручную на {{ formatCurrency(excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(excessPlanFor(node)!.manualEntered + excessPlanFor(node)!.amount) }}) · на согласовании у: {{ excessPendingNames(node) || '—' }}
                            </v-chip>
                            <template v-if="excessMyPendingStep(node) && excessApprovalFor(node)?.can_decide">
                              <v-btn size="x-small" variant="tonal" color="success"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="decidePlanExcess(node, 'approved')"
                              >Одобрить</v-btn>
                              <v-btn size="x-small" variant="tonal" color="error"
                                :loading="excessDecideLoading === node.id"
                                @click.stop="openExcessRejectDialog(node)"
                              >Отклонить</v-btn>
                            </template>
                            <div v-else-if="excessMyPendingStep(node) && !excessApprovalFor(node)?.can_decide" class="feo-plan-note text-medium-emphasis" style="width:100%">
                              Решение по превышению принимают только уполномоченные (владелец/финансист). Обратитесь к ним — согласовывать может не любой назначенный.
                            </div>
                          </template>
                          <template v-else-if="excessApprovalFor(node)?.status === 'rejected'">
                            <v-chip size="x-small" color="red" variant="flat">
                              превышение плана над ручным отклонено{{ excessApprovalFor(node)?.comment ? ': ' + excessApprovalFor(node)!.comment : '' }}
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <template v-else>
                            <v-chip size="x-small" color="red" variant="flat">
                              план превышает заданный вручную на {{ formatCurrency(excessPlanFor(node)!.amount) }} (задано {{ formatCurrency(excessPlanFor(node)!.manualEntered) }}, стало {{ formatCurrency(excessPlanFor(node)!.manualEntered + excessPlanFor(node)!.amount) }})
                            </v-chip>
                            <v-btn size="x-small" variant="tonal" color="red"
                              :loading="excessRequestLoading === node.id"
                              @click.stop="requestPlanExcessApproval(node)"
                            >Согласовать</v-btn>
                          </template>
                          <!-- План zany-fluttering-mountain.md, п.2: вместо текстовой строки —
                               кликабельные чипы по позициям. Одна связанная закупка → сразу
                               открыть (router.push, тот же приём, что и у excessCulpritFor
                               выше/virtCart); несколько — v-menu со списком «номер · статус ·
                               сумма», остановленные помечены; закупок нет — чип без действия,
                               с подсказкой почему (см. excessPlanItemPurchaseTitle). -->
                          <div v-if="excessPlanFor(node)!.items.length" class="d-flex align-center flex-wrap ga-1 mt-1" style="width:100%">
                            <span style="font-size:11px;color:#B45309">Позиции-виновники:</span>
                            <template v-for="item in excessPlanFor(node)!.items" :key="item.id">
                              <span v-if="!item.purchases.length" class="feo-purchase-link" style="cursor:default;opacity:0.7"
                                :title="`«${item.name}» (${formatCurrency(item.amount)}) — нет связанной закупки: позиция ещё не попала ни в одну закупку`"
                              >{{ item.name }} ({{ formatCurrency(item.amount) }})</span>
                              <a v-else-if="item.purchases.length === 1" href="javascript:void(0)" class="feo-purchase-link"
                                @click.stop="router.push(`/orders/${item.purchases[0].id}`)"
                              >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
                              <v-menu v-else location="bottom start">
                                <template #activator="{ props: purchMenuProps }">
                                  <a href="javascript:void(0)" class="feo-purchase-link" v-bind="purchMenuProps" @click.stop
                                  >{{ item.name }} ({{ formatCurrency(item.amount) }})</a>
                                </template>
                                <v-list density="compact">
                                  <v-list-item v-for="p in item.purchases" :key="p.id" @click="router.push(`/orders/${p.id}`)">
                                    <v-list-item-title>
                                      {{ excessPlanItemPurchaseTitle(p) }}
                                      <span v-if="p.stopped_at" class="feo-stopped-marker ml-1">остановлена</span>
                                    </v-list-item-title>
                                  </v-list-item>
                                </v-list>
                              </v-menu>
                            </template>
                          </div>
                        </div>

                        <!-- Замечание владельца п.4: «если согласовали превышение — так и остаётся,
                             надо чтобы висело предупреждение, что согласовали» — постоянная спокойная
                             пометка, НЕ зависит от того, активно ли превышение прямо сейчас. План
                             zany-fluttering-mountain.md, п.3: дополнено «план был X → стал Y» из
                             excess_approval_plan_before/after (может отсутствовать у старых запросов). -->
                        <div v-if="excessPlanApprovalPermanent(node)" class="feo-plan-note mt-1">
                          <v-chip size="x-small" color="grey" variant="tonal" prepend-icon="mdi-check-decagram">
                            превышение согласовано: {{ formatCurrency(excessPlanApprovalPermanent(node)!.amount) }}{{ excessPlanApprovalPermanent(node)!.at ? ', ' + excessPlanApprovalPermanent(node)!.at : '' }}, {{ excessPlanApprovalPermanent(node)!.by }}<template v-if="excessPlanApprovalPermanent(node)!.planBefore != null && excessPlanApprovalPermanent(node)!.planAfter != null"> · план был {{ formatCurrency(excessPlanApprovalPermanent(node)!.planBefore!) }} → стал {{ formatCurrency(excessPlanApprovalPermanent(node)!.planAfter!) }}</template>
                          </v-chip>
                        </div>

                        <!-- Замечание владельца п.3: «Приравнять ФЭО к плану» — только org_admin и выше
                             (canSaveVersion — переиспользован без изменений, см. её объявление ниже). -->
                        <div v-if="canSaveVersion" class="mt-1">
                          <v-btn size="x-small" variant="text" color="blue-grey" prepend-icon="mdi-equal"
                            title="Установить финансирование по ФЭО этой категории равным её полной плановой сумме"
                            @click.stop="openAlignBudgetConfirm(node)"
                          >Приравнять ФЭО к плану</v-btn>
                        </div>
                      </td>

                      <!-- «В плане-графике» — решение владельца 2026-08-18 (жалоба на категории 3710:
                           строка дерева показывала три несводимые шкалы одновременно — план 351 844,
                           «фактическая» 54 318 (договорный факт), остаток 351 844 (плюс ещё заметка ниже
                           «в закупках 432 162»). Владелец потребовал «фактическая должна получаться
                           432 162» — свели колонку к той же шкале, что и заметка «в закупках» под
                           «Плановой суммой» (feoInPlanScheduleFor — сумма всех статусов плана закупок,
                           второй источник не изобретаем). feoFactFor (plan_tree.fact, договорный факт
                           work_in_progress…paid) НЕ удалён и не изменён — остался подписью «по договору»
                           ниже и по-прежнему единственный источник плашки превышения факта. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span :class="feoInPlanScheduleFor(node) > 0 ? 'feo-amount feo-amount--link' : 'feo-amount-empty'"
                          :style="(feoDisplayedFor(node) > 0 && feoInPlanScheduleFor(node) > feoDisplayedFor(node)) || (feoPlannedDisplayFor(node) > 0 && feoInPlanScheduleFor(node) > feoPlannedDisplayFor(node)) ? 'color:#EF4444;font-weight:700' : ''"
                          :title="feoInPlanScheduleFor(node) > 0 ? 'Открыть закупки по этой категории' : ''"
                          @click="feoInPlanScheduleFor(node) > 0 && router.push(`/orders?feo_category_id=${node.id}`)"
                        >
                          {{ feoInPlanScheduleFor(node) > 0 ? formatCurrency(feoInPlanScheduleFor(node)) : '—' }}
                        </span>
                        <!-- Договорный факт — подпись, не отдельная метрика (правило «одна подпись = одна
                             метрика»): показываем только когда он есть и реально отличается от «в плане-графике». -->
                        <div v-if="feoFactFor(node) > 0 && Math.abs(feoInPlanScheduleFor(node) - feoFactFor(node)) > 0.005"
                          class="feo-plan-note text-medium-emphasis"
                          :title="`Из них уже есть договорная цена (договор/акт). Остальное — закупки, которые ещё в статусе «План закупок»`"
                        >
                          по договору {{ formatCurrency(feoFactFor(node)) }}
                        </div>
                      </td>

                      <!-- Остаток = (Плановая сумма | Финансирование по ФЭО) − В плане-графике.
                           Решение владельца 2026-08-18: та же шкала, что и колонка «В плане-графике»
                           и заметка «в закупках» — см. feoResidualFor/feoInPlanScheduleFor. -->
                      <td class="feo-td feo-td-num" style="vertical-align:top">
                        <span v-if="feoResidualBaseFor(node) > 0 || feoInPlanScheduleFor(node) > 0"
                          class="feo-amount"
                          :style="feoResidualFor(node) < -0.005 ? 'color:#EF4444;font-weight:700' : 'color:#16A34A'"
                          :title="`${residualBase === 'feo' ? 'ФЭО' : 'План'} ${formatCurrency(feoResidualBaseFor(node))} − В плане-графике ${formatCurrency(feoInPlanScheduleFor(node))}`"
                        >
                          {{ feoResidualFor(node) < 0 ? '−' : '' }}{{ formatCurrency(Math.abs(feoResidualFor(node))) }}
                        </span>
                        <span v-else class="feo-amount-empty">—</span>
                      </td>

                      <!-- Действия -->
                      <td class="feo-td feo-td-actions">
                        <div class="feo-actions-wrap">
                          <!-- Level 3: кнопка раскрытия позиций / spacer for alignment.
                               Задача владельца «направление со временем может наполниться»
                               (2026-08-12): у направления (node.hasChildren) кнопка тоже
                               появляется, но ТОЛЬКО если у него есть СОБСТВЕННЫЕ плановые
                               позиции (hasOwnPlannedAmountFor) — иначе раскрывать нечего,
                               ничего не меняется для обычных направлений без своего плана. -->
                          <span class="feo-action-slot"><v-btn v-if="!node.hasChildren || hasOwnPlannedAmountFor(node)"
                            :icon="expandedItemPanels.has(node.id) ? 'mdi-list-box' : 'mdi-list-box-outline'"
                            variant="text" size="x-small"
                            :color="expandedItemPanels.has(node.id) ? 'teal' : 'grey'"
                            :title="node.hasChildren ? 'Состав плана: позиции, привязанные к самому направлению (не к его подкатегориям)' : 'Показать плановые / фактические позиции'"
                            @click="toggleItemPanel(node)"
                          /></span>
                          <!-- Стрелки — друг под другом (B5: скрыты без feo_category.edit) -->
                          <div v-if="canEditFeo" class="feo-actions-col">
                            <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                              title="Переместить выше" @click.stop="reorderFeoNode(node, 'up')" />
                            <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                              title="Переместить ниже" @click.stop="reorderFeoNode(node, 'down')" />
                          </div>
                          <!-- Значки: добавить/редактировать/удалить скрыты без feo_category.edit;
                               «показать закупки» — чтение, остаётся всегда -->
                          <div class="feo-actions-grid">
                            <v-btn v-if="canEditFeo" icon="mdi-plus-circle-outline" variant="text" size="x-small" color="success"
                              title="Добавить дочернюю" @click="openAddFeoDialog(node.id)" />
                            <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                              title="Показать закупки по этой категории"
                              @click.stop="router.push(`/orders?feo_category_id=${node.id}`)" />
                            <v-btn v-if="canEditFeo" icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
                              title="Редактировать" @click="startFeoEdit(node)" />
                            <v-btn v-if="canEditFeo" icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                              title="Удалить" @click="confirmFeoDelete(node)" />
                          </div>
                        </div>
                      </td>
                    </tr>

                    <!-- ── Level 5 панель: Плановые vs Фактические ──
                         Условие расширено (!node.hasChildren || hasOwnPlannedAmountFor(node)) —
                         см. комментарий у hasOwnPlannedAmountFor выше: у направления панель
                         раскрывается, только если есть чем её наполнить. -->
                    <tr v-if="(!node.hasChildren || hasOwnPlannedAmountFor(node)) && expandedItemPanels.has(node.id)" :key="`items-${node.id}`" :data-feo-panel-for="node.id">
                      <!-- Правка владельца (2026-08-12): отступ 0 0 0 60px убран — он сдвигал ВСЮ
                           вложенную таблицу плановых позиций вправо и ломал вертикальное выравнивание
                           её колонок с колонками основной таблицы (feo-table). Визуальная вложенность
                           теперь только padding-left ВНУТРИ первой ячейки «Позиция плана» ниже.
                           colspan="7" (было 6) — вложенная таблица теперь имеет ту же раскладку из
                           7 колонок, что и основная (см. feoResize выше); чтобы её auto-колонки делили
                           РОВНО ТУ ЖЕ полную ширину контейнера, что и основная таблица, ячейка обязана
                           захватывать ВСЕ 7 колонок основной строки, а не 6. -->
                      <td colspan="7" style="padding:0">
                        <!-- padding-left:0 (было 12px) — тот же замер в браузере показал, что этот
                             левый паддинг сдвигал ВСЮ вложенную таблицу плановых позиций на 12px
                             вправо от колонок основной таблицы feo-table.
                             padding-right:0 (было 12px, правка 2026-08-12) — тот же принцип: правый
                             паддинг урезал ширину вложенной таблицы на 12px относительно основной,
                             из-за чего table-layout:fixed делил остаток на 3px меньше на каждую
                             auto-колонку и budget/qty/planned чуть съезжали влево от одноимённых
                             колонок основной таблицы. Только top/bottom оставлены. -->
                        <div style="padding:10px 0 12px 0">
                          <!-- Требование владельца (план zany-fluttering-mountain.md, возвращено из отката
                               e0db76a): при раскрытии категории СРАЗУ видны её плановые позиции — БЕЗ
                               промежуточного заголовка-обёртки «Позиции: план vs факт», это уже просто
                               продолжение дерева. Кнопка добавления плановой позиции осталась, без title. -->
                          <div class="d-flex align-center mb-2" style="gap:8px">
                            <!-- Замечание владельца 1 (2026-08-12): «по одной сворачивать неудобно,
                                 надо развернуть все сразу, посмотреть, как что покупалось, и свернуть
                                 все сразу» — переключатель раскрытия «План vs факт» у ВСЕХ плановых
                                 позиций именно этой категории, см. toggleAllPlannedItemsForCategory. -->
                            <v-btn v-if="displayPlannedRowsFor(node).length > 1" size="x-small" variant="text" color="teal"
                              :prepend-icon="anyPlannedExpandedFor(node) ? 'mdi-arrow-collapse-vertical' : 'mdi-arrow-expand-vertical'"
                              @click="toggleAllPlannedItemsForCategory(node)"
                            >{{ anyPlannedExpandedFor(node) ? 'Свернуть всё' : 'Развернуть всё' }}</v-btn>
                            <v-spacer />
                            <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-plus"
                              @click="openAddPlannedItem(node.id)">
                              Добавить плановую
                            </v-btn>
                          </div>

                          <!-- Спиннер загрузки -->
                          <div v-if="loadingComparison.has(node.id)" class="d-flex align-center" style="gap:8px;padding:8px 0">
                            <v-progress-circular indeterminate size="16" color="teal" />
                            <span class="text-caption">Загрузка...</span>
                          </div>

                          <!-- Таблица сравнения -->
                          <!-- table-layout:fixed (правка 2026-08-12, вместе с откатом фиксированных 180px
                               выше): без него браузер считает ширину auto-колонок ПО СОДЕРЖИМОМУ (обычный
                               table-layout:auto), а не делит остаток поровну как в основной .feo-table
                               (там table-layout:fixed задан классом). Из-за этого «Позиция плана» (длинный
                               текст) раздувалась на сотни px, а budget/qty/planned вообще не совпадали с
                               основной таблицей, несмотря на одинаковые resizeStyle(key). -->
                          <table v-else-if="comparisonData[node.id]" style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                            <thead>
                              <!-- Требование владельца (2026-08-12): в рамках одной плановой позиции может быть
                                   несколько разных закупок — одна строка на уровне плана физически не может
                                   описать факт по всем сразу (либо врёт, либо пустует). Поэтому фактические
                                   колонки убраны с ЭТОГО уровня целиком: тут только план (синий), весь факт —
                                   уровнем ниже, в раскрывающемся блоке «План vs факт» под каждой плановой
                                   позицией (см. ниже, вёрстка не тронута). Строка-группировка «ПОЗИЦИИ ПЛАНА» /
                                   «ПЛАН VS ФАКТ» убрана — делить больше нечего, вся таблица теперь про план. -->
                              <!-- Правка владельца (2026-08-12): колонки этой (вложенной) таблицы выровнены
                                   ПОД одноимёнными колонками ОСНОВНОЙ таблицы дерева ФЭО (feo-table) — тем же
                                   feoResize.resizeStyle(key), тот же порядок ключей: name → budget → qty → planned.
                                   «Цена плана» стоит под budget («Количество и финансирование по ФЭО» — там тоже
                                   деньги), поэтому она ЛЕВЕЕ «Кол-во плана» (qty) — так требует вертикальное
                                   выравнивание, не смысловой порядок колонок.
                                   Правка владельца (2026-08-12, откат фиксированных 180px): чтобы авто-колонки
                                   (name/qty/planned/residual, ширина 0 = делят остаток) делили ОДИНАКОВЫЙ
                                   остаток в обеих таблицах, у вложенной таблицы теперь РОВНО ТЕ ЖЕ 7 колонок,
                                   что у основной — добавлены пустые spent/residual (те же ключи, те же
                                   fixed/auto свойства), а колонка кнопок зафиксирована в 112px — как
                                   .feo-th-actions у основной (там тоже fixed, не auto). Иначе набор и число
                                   auto-колонок в двух таблицах отличались бы, и остаток делился бы по-разному. -->
                              <!-- Замечание владельца 3 (2026-08-12): «слишком сливающиеся подложки» —
                                   фон шапки/строк убран (белый), синий остался только в тексте заголовков
                                   и тонкой нижней границе шапки. -->
                              <tr>
                                <th :style="[feoResize.resizeStyle('name'), { paddingLeft: `${plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;text-align:left;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE" title="Плановая позиция. Закупки, привязанные к ней (как выставили в закупку / как в договоре — по стадии), — в раскрывающемся блоке под строкой плана.">
                                  Позиция плана
                                </th>
                                <th :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Плановая цена за единицу</th>
                                <th :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Кол-во плана</th>
                                <th :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Сумма плана</th>
                                <!-- «Тип» (блок 1, план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/
                                     работа плановой позиции. Колонка ДОПОЛНИТЕЛЬНАЯ, фиксированной ширины (не
                                     через feoResize) — сознательно нарушает описанный выше «ровно те же 7
                                     колонок» подсчёт остатка совместно с основной таблицей; смирились с этим
                                     ради нового признака, вертикальное совпадение auto-колонок левее (name/
                                     budget/qty/planned) не страдает. -->
                                <th style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Тип</th>
                                <th :style="feoResize.resizeStyle('spent')" style="border-bottom:1px solid #BFDBFE"></th>
                                <th :style="feoResize.resizeStyle('residual')" style="border-bottom:1px solid #BFDBFE"></th>
                                <th style="width:112px;min-width:112px;max-width:112px;padding:4px 2px;border-bottom:1px solid #BFDBFE"></th>
                              </tr>
                            </thead>
                            <tbody>
                              <!-- Плановые позиции Ур.5: строка плана свёрнута по умолчанию, шеврон + чип
                                   «заявок: N на сумму M» раскрывают привязанные позиции заявок ВНУТРИ неё
                                   (feo_planned_item_id = planned.id) — переиспользует вёрстку строки позиции
                                   заявки (аватар/ссылка на закупку/снять сопоставление), но с увеличенным
                                   левым отступом первой ячейки, чтобы визуально вложить её под план.
                                   Источник строк — displayPlannedRowsFor(node): реальные FeoPlannedItem,
                                   ИЛИ (если их нет) одна синтетическая «ручной план ФЭО» с id = -node.id —
                                   единая иерархия ШАГ 1 (2026-08-07), псевдо-строка была отдельным блоком
                                   ниже, теперь та же вёрстка, что и у реальной плановой позиции. -->
                              <template v-for="(planned, pIdx) in displayPlannedRowsFor(node)" :key="`p-${planned.id}`">
                                <tr style="border-bottom:1px solid #E5E7EB">
                                  <td :style="[feoResize.resizeStyle('name'), { paddingLeft: `${plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;color:#0c4a6e">
                                    <div class="d-flex align-center" style="gap:2px">
                                      <!-- Правка владельца (жалоба по скриншоту): раскрытие теперь доступно ВСЕГДА —
                                           даже без единой привязанной закупки, чтобы блок «План vs факт» не пропадал
                                           бесследно и не вводил в заблуждение. Раньше (2026-08-10) шеврон скрывался
                                           при пустом factForPlanned; теперь пустой случай рисует заглушку внутри. -->
                                      <v-btn
                                        :icon="expandedPlannedItems.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                        variant="text" density="compact" size="x-small" color="teal"
                                        title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                                        @click="togglePlannedItemFolder(planned.id)"
                                      />
                                      <span>{{ planned.name }}</span>
                                      <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="Это плановая позиция — она запланирована, а не выставлена в закупку и не приехала по факту"
                                      >план</v-chip>
                                      <!-- Спокойная пометка владельца (2026-08-12, повод — «Бинт марлевый» на
                                           «Окружных»): панель сейчас открыта для направления (node.hasChildren) —
                                           ЛЮБАЯ плановая позиция в ней по построению привязана ПРЯМО к нему
                                           (comparisonData грузится по feo_category_id=node.id, без детей),
                                           а не к какой-то из его конечных категорий. Не тревожный красный —
                                           нейтральный серый, суммы при переносе вниз не меняются. -->
                                      <v-chip v-if="node.hasChildren" size="x-small" color="grey" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                        title="Позиция привязана к направлению, а не к конечной категории. Её можно перенести вниз, в подходящую категорию — суммы при этом не изменятся."
                                      >на направлении целиком</v-chip>
                                      <!-- Происхождение (владелец, 2026-09-01) — компактные пометки, не мешающие
                                           читать строку: жёсткая разбивка ФЭО против внутреннего плана (см.
                                           докстринг is_feo_breakdown/is_internal_plan в feo_planned_item.py). Обе
                                           могут стоять одновременно — независимые галочки, не переключатель. -->
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
                                    <!-- Разбор плана (требование владельца 2026-08-09): сколько уже разобрано
                                         этой плановой позиции — и в штуках, и в деньгах, остаток тем же образом.
                                         Штуки — только если у плана вообще задано количество (planned.quantity),
                                         иначе у плана нет множителя количества и писать «из N шт» нечего. -->
                                    <div v-if="planned.amount != null" class="text-medium-emphasis" style="font-size:10px;line-height:1.3;white-space:normal">
                                      {{ planBreakdownText(node.id, planned) }}
                                    </div>
                                  </td>
                                  <!-- Правка владельца (2026-08-12): «Цена плана» — под колонкой budget
                                       («Количество и финансирование по ФЭО») основной таблицы, поэтому она
                                       ЛЕВЕЕ «Кол-во плана» (qty) ниже — порядок задан выравниванием колонок. -->
                                  <td :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#64748b">
                                    <!-- Правка 2026-09-03: раньше здесь ДЕЛИЛИ amount/quantity — выдуманное
                                         частное, а не реальная цена (planned.unit_price вообще не читался).
                                         Теперь — только честное поле; пусто, но сумма плана задана → серая
                                         подпись вместо подставного числа. -->
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
                                  <!-- spent/residual — пустые заглушки, только чтобы раскладка колонок совпадала
                                       со основной таблицей (см. правку выше у feoResize/th этой таблицы). -->
                                  <td :style="feoResize.resizeStyle('spent')"></td>
                                  <td :style="feoResize.resizeStyle('residual')"></td>
                                  <!-- Требование владельца (2026-08-12): факт (colspan-заглушка, «Разница»,
                                       «Контрагент», «Статус» — factForPlanned/calcDiff/getDiffStyle/isFactActual)
                                       убран с уровня строки плановой позиции целиком — одна строка не может
                                       описать несколько разных закупок под одной плановой позицией; весь факт
                                       теперь только в раскрывающемся блоке ниже (шеврон слева от названия).
                                       Кнопка «План vs факт» (жалоба владельца 2026-08-12 — раскрытие было не
                                       видно, только маленький шеврон у названия) дублирует togglePlannedItemFolder
                                       текстовой ссылкой; видна на КАЖДОЙ строке, включая синтетическую
                                       (planned.isManual), поэтому вынесена ИЗ ветки v-if/v-else ниже.
                                       width:112px — как у .feo-th-actions основной таблицы (fixed, не auto),
                                       чтобы остаток между auto-колонками делился одинаково в обеих таблицах. -->
                                  <td style="width:112px;min-width:112px;max-width:112px;padding:2px;text-align:center">
                                    <div class="d-flex align-center flex-wrap justify-center" style="gap:0">
                                      <!-- Замечание владельца 2 (2026-08-12): «должна быть возможность менять
                                           плановые позиции местами внутри категории» — те же стрелки, что уже
                                           есть у категорий ФЭО в дереве (reorderFeoNode), только для плановых
                                           позиций (reorderPlannedItem, PUT /feo-planned-items/{id} с sort_order).
                                           Не показываются у синтетической строки (planned.isManual) — она одна
                                           и переставлять её не с чем (displayPlannedRowsFor никогда не мешает
                                           ручную строку с реальными). -->
                                      <template v-if="!planned.isManual">
                                        <v-btn icon="mdi-chevron-up" variant="text" size="x-small" color="grey-darken-1"
                                          :disabled="pIdx === 0"
                                          :loading="reorderingPlannedItemId === planned.id"
                                          title="Переместить выше"
                                          @click.stop="reorderPlannedItem(node, pIdx, 'up')"
                                        />
                                        <v-btn icon="mdi-chevron-down" variant="text" size="x-small" color="grey-darken-1"
                                          :disabled="pIdx === displayPlannedRowsFor(node).length - 1"
                                          :loading="reorderingPlannedItemId === planned.id"
                                          title="Переместить ниже"
                                          @click.stop="reorderPlannedItem(node, pIdx, 'down')"
                                        />
                                      </template>
                                    </div>
                                    <v-btn
                                      size="x-small" variant="text" color="teal" class="text-none"
                                      :prepend-icon="expandedPlannedItems.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                      title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                                      @click="togglePlannedItemFolder(planned.id)"
                                    >План vs факт</v-btn>
                                    <template v-if="!planned.isManual">
                                      <!-- Требование владельца, п.2/п.3 (2026-08-12): позицию, висящую прямо на
                                           направлении («на направлении целиком», см. чип выше), можно перенести
                                           вниз, в подходящую конечную категорию — суммы при этом не меняются
                                           (перенос просто меняет feo_category_id, деньги как считались в плане
                                           направления, так и продолжат считаться, просто уже на новом узле).
                                           Кнопка видна ТОЛЬКО в панели направления (node.hasChildren) — у обычной
                                           конечной категории переносить пока некуда конкретным местом, ничего не
                                           меняем в её поведении. -->
                                      <v-menu v-if="node.hasChildren" location="bottom end">
                                        <template #activator="{ props: moveMenuProps }">
                                          <v-btn v-bind="moveMenuProps" icon="mdi-arrow-down-bold-box-outline"
                                            size="x-small" variant="text" color="orange-darken-1"
                                            :loading="movingPlannedItemId === planned.id"
                                            title="Перенести позицию вниз, в подходящую конечную категорию — суммы не изменятся"
                                          />
                                        </template>
                                        <v-list density="compact" max-height="320" style="overflow-y:auto">
                                          <v-list-subheader>Перенести в категорию</v-list-subheader>
                                          <v-list-item v-for="d in descendantCategoriesFor(node)" :key="d.id"
                                            :title="d.name"
                                            :style="{ paddingLeft: `${8 + (d.depth - node.depth - 1) * 16}px` }"
                                            @click="movePlannedItemToCategory(planned, d.id)"
                                          />
                                        </v-list>
                                      </v-menu>
                                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                        title="Редактировать плановую позицию"
                                        @click="openEditPlannedItem(planned)"
                                      />
                                      <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                        title="Удалить плановую позицию"
                                        :loading="deletingPlannedItemId === planned.id"
                                        @click="deletePlannedItem(planned)"
                                      />
                                    </template>
                                    <template v-else>
                                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="blue"
                                        title="Редактировать план категории — количество, цена за единицу, единица измерения"
                                        @click="openEditCategoryPlan(node)"
                                      />
                                      <v-btn icon="mdi-playlist-plus" size="x-small" variant="text" color="teal"
                                        title="Завести плановую позицию — именованный товар/услуга вместо строки категории; количество и цена берутся из плана листа, факты привяжутся к ней автоматически"
                                        @click="openConvertManualPlanToItem(node)"
                                      />
                                    </template>
                                  </td>
                                </tr>
                                <!-- Раскрывающийся блок плановой позиции: под одной плановой позицией может
                                     висеть несколько закупок («покупаю по одной машине в каждой закупке»).
                                     Правка владельца (жалоба по скриншоту): раскрытие теперь доступно ВСЕГДА,
                                     даже без единой закупки — иначе блок «План vs факт» пропадал бесследно и
                                     вводил в заблуждение (было видно только у позиций С закупками). Пустой
                                     случай рисует ту же шапку и одну строку-заглушку вместо строк actual —
                                     фактические ячейки НЕ заполняются плановыми числами (правка 2026-08-10
                                     остаётся в силе, тут просто видимость блока, не логика чисел). Своя
                                     вложенная таблица со своей шапкой (см. factStageHeaderFor/leftGroupInfo) —
                                     ровно одна стадия, если все закупки позиции на ней, иначе нейтральный
                                     заголовок и стадия подписана на каждой строке (пометка «как выставили»/
                                     «как в договоре» уже есть на строке). -->
                                <tr v-if="expandedPlannedItems.has(planned.id)">
                                  <!-- colspan="8" (было 7, до колонки «Тип» — 5) — у вложенной таблицы плановых
                                       позиций теперь 8 колонок (добавлены пустые spent/residual + «Тип», см.
                                       выше), эта ячейка должна закрывать всю строку целиком, а не оставлять
                                       колонки «дыркой» справа. -->
                                  <!-- Замечание владельца 3+4 (2026-08-12): вложенный блок «План vs факт» —
                                       собственная светло-серая заливка + рамка + заметный отступ сверху/слева
                                       (визуальная вложенность внутрь плановой позиции), ЧТОБЫ читался как
                                       отдельная от плана сущность. table-layout:fixed добавлен на ВНУТРЕННЮЮ
                                       таблицу (у неё его не было — вот почему в МИНПРОСе блок садился по
                                       ширине содержимого вместо 100% строки, см. разбор в отчёте задачи;
                                       у обёртки-td теперь padding:0, вся раскладка — во внутреннем div). -->
                                  <td colspan="8" style="padding:0">
                                    <div style="margin:10px 8px 12px 32px;padding:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px">
                                    <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                                      <thead>
                                        <!-- Замечание владельца 5 (2026-08-12): порядок «цена → количество → сумма»,
                                             как в «Позициях плана» — было «кол-во → цена», переставлено местами
                                             в ОБЕИХ группах (план-сторона и факт-сторона). Подписи не менялись. -->
                                        <tr>
                                          <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" :title="factStageHeaderFor(node.id, planned.id) === 'Позиция закупки' ? 'Закупки этой плановой позиции сейчас на разных стадиях — стадия каждой подписана на её строке' : ''">
                                            {{ factStageHeaderFor(node.id, planned.id) }}
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
                                        <tr v-if="!factForPlanned(node.id, planned.id).length">
                                          <td colspan="12" style="padding:8px 8px;color:#94a3b8;font-style:italic">Закупок по этой плановой позиции пока нет</td>
                                        </tr>
                                        <template v-for="actual in factForPlanned(node.id, planned.id)" :key="`pa-${actual.purchase_item_id}`">
                                        <tr
                                          :class="kpiItemRowClass(actual)"
                                          :data-item-id="actual.purchase_item_id" data-item-group="planned"
                                          style="border-bottom:1px solid #E2E8F0">
                                          <td style="padding:4px 8px;color:#0c4a6e">
                                            {{ leftGroupInfo(actual).name }}
                                            <v-chip size="x-small" :color="stageChipColorFor(actual.purchase_status)" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                              :title="stageChipTitleFor(actual.purchase_status)"
                                            >{{ stageChipLabelFor(actual.purchase_status) }}</v-chip>
                                          </td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).unitPrice != null ? formatCurrency(leftGroupInfo(actual).unitPrice!) : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).quantity != null ? `${parseFloat(String(leftGroupInfo(actual).quantity))} ${leftGroupInfo(actual).unit || ''}` : '—' }}</td>
                                          <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).total != null ? formatCurrency(leftGroupInfo(actual).total!) : '—' }}</td>
                                          <td style="padding:4px 8px 4px 24px;color:#166534">
                                            <div class="d-flex align-center" style="gap:6px">
                                              <v-btn v-if="(actual.stages?.length || 0) >= 2"
                                                :icon="expandedStageRows.has(`pa-${actual.purchase_item_id}`) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                                variant="text" density="compact" size="x-small" color="teal"
                                                title="Показать стадии уточнения позиции"
                                                @click.stop="toggleStageRow(`pa-${actual.purchase_item_id}`)"
                                              />
                                              <v-avatar v-if="actual.product_photo" size="24" rounded class="flex-shrink-0" style="cursor:pointer"
                                                @click.stop="photoPreview = { src: actual.product_photo!, title: actual.item_name }">
                                                <v-img :src="actual.product_photo" cover />
                                              </v-avatar>
                                              <div>{{ actual.item_name }}</div>
                                              <v-chip v-if="isExcessCulpritActual(node, actual)" size="x-small" color="red" variant="flat" class="ml-1"
                                                style="font-size:9px;height:16px" :title="excessCulpritChipTooltip(node)"
                                              ><v-icon icon="mdi-alert-decagram" size="10" class="mr-1" />из-за неё превышение</v-chip>
                                            </div>
                                            <a
                                              href="javascript:void(0)"
                                              class="feo-purchase-link"
                                              :title="`Перейти в закупку #${actual.purchase_id}`"
                                              @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                            >
                                              <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                              {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                            </a>
                                            <a v-if="actual.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                              title="Перейти к заявкам"
                                              @click.stop="router.push('/wishes')"
                                            >
                                              <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ actual.wish_id }}
                                            </a>
                                            <!-- Владелец, 2026-08-13: остановка закупки — см. FeoActualItem.stopped_at -->
                                            <div v-if="actual.stopped_at" class="feo-stopped-marker mt-1">
                                              <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(actual) }}
                                            </div>
                                          </td>
                                          <!-- Правка владельца (2026-08-12): «Кол-во (факт)»/«Цена (факт)» раньше
                                               брались из actual.quantity/unit_price — это поля позиции закупки,
                                               заполненные на ЛЮБОЙ стадии (даже «план закупок», без единой поставки).
                                               Тот же признак факта, что уже работает у «Сумма (факт)»:
                                               fact_amount != null — до появления факта прочерк, как и у суммы. -->
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
                                          <!-- Правка владельца (2026-08-12): галочка mdi-check-circle стояла безусловно
                                               (строка и так вложена под своей плановой позицией — «сопоставлено» и
                                               так очевидно, галочка ничего не сообщала). Вместо неё — стадия закупки
                                               текстом, тем же purchaseStatusLabel, что и в других местах файла. -->
                                          <td style="padding:4px 8px;text-align:center;color:#94a3b8;font-size:10px">
                                            {{ purchaseStatusLabel(actual.purchase_status) }}
                                          </td>
                                          <td style="padding:2px;text-align:center;white-space:nowrap">
                                            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                                              title="Редактировать позицию закупки"
                                              @click="openReqItemEditFromActual(node, actual)"
                                            />
                                            <!-- Баг найден при приёмке (2026-08-11): mapTarget/mapCategoryId — refs,
                                                 в шаблоне уже auto-unwrap; `mapTarget.value = actual` пытался создать
                                                 свойство "value" на РАЗВЁРНУТОМ значении (объекте/числе), а не на самом
                                                 ref — падало TypeError «Cannot create property 'value' on number»,
                                                 и applyMapping(null) вообще не успевал выполниться (обрыв на строке
                                                 выше). «Снять сопоставление» из вложенной таблицы плановой позиции
                                                 был полностью нерабочим. Исправлено на прямое присваивание — компилятор
                                                 Vue сам генерирует `x.value = y` для присваивания top-level ref. -->
                                            <v-btn icon="mdi-link-off" size="x-small" variant="text" color="grey"
                                              title="Снять сопоставление"
                                              @click="() => { mapTarget = actual; mapCategoryId = node.id; applyMapping(null) }"
                                            />
                                          </td>
                                        </tr>
                                        <!-- Подстроки стадий уточнения (справочно, НЕ входят в comparisonPlanTotal/comparisonFactTotal) -->
                                        <template v-if="expandedStageRows.has(`pa-${actual.purchase_item_id}`)">
                                        <tr v-for="sr in stagesWithDiff(actual.stages)" :key="`pa-stage-${actual.purchase_item_id}-${sr.stage.key}`"
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

                              <!-- Правка владельца (2026-08-11): «Плановые из закупок» как самостоятельный
                                   блок УБРАН — позиция в стадии «План закупок» это уже начало жизни строки
                                   плана, а не отдельная параллельная сущность (баг «пикап Great Wall POER»:
                                   рисовалась ЗДЕСЬ и одновременно план ФЭО отдельной строкой — ИТОГО складывал
                                   план с закупкой, 16 000 000 вместо 8 000 000). Такие позиции (привязанные —
                                   feo_planned_item_id, непривязанные — на синтетическую «ручной план ФЭО»)
                                   теперь нарисованы ВНУТРИ раскрывающегося блока плановой строки выше —
                                   см. factForPlanned (расширен до ЛЮБОЙ стадии закупки, не только FACT_STATUSES). -->

                              <!-- «Не привязаны к плану — требуется действие»: позиции закупок ЛЮБОЙ
                                   стадии (правка 2026-08-11 — раньше только FACT_STATUSES, теперь
                                   unplannedActualFor смотрит на allActualFor, иначе позиции в статусе
                                   «План закупок» без привязки молча пропадали бы после удаления блока
                                   «Плановые из закупок») без feo_planned_item_id. Показывается ТОЛЬКО
                                   когда есть куда «не привязаться» осмысленно: у листа либо вообще нет
                                   плановой строки (ни реальных FeoPlannedItem, ни ручного плана —
                                   тогда те же самые позиции стали бы фактом синтетической «ручной план
                                   ФЭО» строки, см. factForPlanned(catId, -node.id) — hasManualPseudoRow
                                   ниже это и проверяет), либо реальные плановые позиции есть, но именно
                                   эта закупка ни к одной не привязана.
                                   Правка (регресс вёрстки, найдено при разборе задачи): этот блок — 12
                                   реальных колонок (те же, что у вложенной таблицы «План vs факт» выше —
                                   см. её thead), а НЕ 7 колонок основной таблицы плановых позиций. Раньше
                                   его строки были ПРЯМЫМИ детьми <tbody> внешней 7-колоночной таблицы —
                                   table-layout:fixed считал колонки по МАКСИМУМУ ячеек среди ВСЕХ строк
                                   таблицы (а не только thead), находил тут 12 и делил остаток между 4+8=12
                                   auto-колонками вместо 4, отчего «Позиция плана»/«Кол-во плана»/«Сумма
                                   плана» в шапке резко сужались и текст/подписи наезжали друг на друга —
                                   именно это было на скриншоте по МИНПРОС (у категорий без непривязанных
                                   закупок, как «Внедорожник» у ЦентрПоиск, эффекта не было, поэтому баг
                                   был на вид «плавающий»). Оборачиваем в colspan="7"+свою таблицу — тот
                                   же приём, что уже применён у «План vs факт» (td colspan=7 → div → own
                                   table), тогда обе таблицы снова независимы по колонкам. -->
                              <tr v-if="unplannedActualFor(node).length">
                                <td colspan="7" style="padding:0">
                                  <div style="margin:8px 8px 4px 8px;padding:8px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.35);border-radius:6px">
                                  <table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px">
                                    <tbody>
                                    <tr style="background:rgba(245,158,11,0.14)">
                                      <td colspan="12" style="padding:4px 8px;font-weight:600;color:#B45309;font-size:11px">
                                        <v-icon icon="mdi-alert-circle-outline" size="14" color="warning" class="mr-1" />
                                        <!-- Владелец (2026-08-31): отличать от плашки в самой закупке
                                             («позиция закупки пока не привязана — человек в процессе»).
                                             Здесь — про план: строка висит непривязанной и не попадает
                                             в общий объём, пока её не привяжут. -->
                                        В плане есть непривязанные позиции — не учитываются в общем объёме, нужно привязать
                                      </td>
                                    </tr>
                              <template v-for="actual in unplannedActualFor(node)" :key="`a-${actual.purchase_item_id}`">
                              <tr
                                :data-item-id="actual.purchase_item_id" data-item-group="unplanned"
                                style="border-bottom:1px solid var(--crm-border);background:rgba(245,158,11,0.06)">
                                <td style="padding:4px 8px;color:#0c4a6e">
                                  {{ leftGroupInfo(actual).name }}
                                  <v-chip size="x-small" :color="stageChipColorFor(actual.purchase_status)" variant="tonal" class="ml-1" style="font-size:9px;height:16px"
                                    :title="stageChipTitleFor(actual.purchase_status)"
                                  >{{ stageChipLabelFor(actual.purchase_status) }}</v-chip>
                                </td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).quantity != null ? `${parseFloat(String(leftGroupInfo(actual).quantity))} ${leftGroupInfo(actual).unit || ''}` : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).unitPrice != null ? formatCurrency(leftGroupInfo(actual).unitPrice!) : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;color:#64748b">{{ leftGroupInfo(actual).total != null ? formatCurrency(leftGroupInfo(actual).total!) : '—' }}</td>
                                <td style="padding:4px 8px" class="text-orange-darken-2">
                                  <div class="d-flex align-center" style="gap:6px">
                                    <v-btn v-if="(actual.stages?.length || 0) >= 2"
                                      :icon="expandedStageRows.has(`a-${actual.purchase_item_id}`) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                                      variant="text" density="compact" size="x-small" color="teal"
                                      title="Показать стадии уточнения позиции"
                                      @click.stop="toggleStageRow(`a-${actual.purchase_item_id}`)"
                                    />
                                    <v-avatar v-if="actual.product_photo" size="28" rounded class="flex-shrink-0" style="cursor:pointer"
                                      @click.stop="photoPreview = { src: actual.product_photo!, title: actual.item_name }">
                                      <v-img :src="actual.product_photo" cover />
                                    </v-avatar>
                                    <div>{{ actual.item_name }}</div>
                                    <v-chip v-if="isExcessCulpritActual(node, actual)" size="x-small" color="red" variant="flat" class="ml-1"
                                      style="font-size:9px;height:16px" :title="excessCulpritChipTooltip(node)"
                                    ><v-icon icon="mdi-alert-decagram" size="10" class="mr-1" />из-за неё превышение</v-chip>
                                    <!-- Жалоба владельца 2026-08-17 (категория 3710): позиции с feo_planned_item_id,
                                         указывающим на УЖЕ УДАЛЁННУЮ плановую позицию, раньше пропадали с экрана
                                         молча (см. правку unplannedActualFor/isOrphanedActual) — теперь показаны
                                         здесь же, с пометкой ПОЧЕМУ они тут, а не просто «не привязаны». -->
                                    <v-chip v-if="isOrphanedActual(actual)" size="x-small" color="deep-orange" variant="flat" class="ml-1"
                                      style="font-size:9px;height:16px"
                                      title="feo_planned_item_id заполнен, но такой плановой позиции больше нет среди плановых позиций категории — она была удалена. Привязка мертва, позиция не засчитана в план. Заведите новую плановую позицию (кнопка справа) или сопоставьте с существующей."
                                    ><v-icon icon="mdi-link-off" size="10" class="mr-1" />привязана к удалённой плановой позиции</v-chip>
                                  </div>
                                  <a
                                    href="javascript:void(0)"
                                    class="feo-purchase-link"
                                    :title="`Перейти в закупку #${actual.purchase_id}`"
                                    @click.stop="router.push(`/orders/${actual.purchase_id}`)"
                                  >
                                    <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                    {{ actual.registry_number || (actual.purchase_number != null ? `№ ${actual.purchase_number}` : `Закупка #${actual.purchase_id}`) }}
                                  </a>
                                  <a v-if="actual.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                    title="Перейти к заявкам"
                                    @click.stop="router.push('/wishes')"
                                  >
                                    <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ actual.wish_id }}
                                  </a>
                                  <!-- Владелец, 2026-08-13: остановка закупки — см. FeoActualItem.stopped_at -->
                                  <div v-if="actual.stopped_at" class="feo-stopped-marker mt-1">
                                    <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(actual) }}
                                  </div>
                                </td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.quantity ? `${parseFloat(String(actual.quantity))} ${actual.unit || ''}` : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right" class="text-medium-emphasis">{{ actual.unit_price ? formatCurrency(actual.unit_price) : '—' }}</td>
                                <td style="padding:4px 8px;text-align:right;font-weight:500" class="text-orange-darken-2">
                                  <template v-if="actual.fact_amount != null">
                                    <span :title="actual.fact_allocated ? 'Распределено пропорционально между позициями закупки' : ''">{{ formatCurrency(actual.fact_amount) }}</span>
                                    <v-chip v-if="!actual.fact_confirmed" size="x-small" variant="tonal" color="warning" class="ml-1" style="font-size:9px;height:16px"
                                      title="Сумма по договору — закрывающими документами (актом приёмки) ещё не подтверждена"
                                    >по договору</v-chip>
                                  </template>
                                  <span v-else class="text-medium-emphasis" style="font-style:italic;font-weight:400">{{ purchaseStatusLabel(actual.purchase_status) }}</span>
                                </td>
                                <!-- calcDiff(0,[actual]) считает вклад в diff ТОЛЬКО для committed/delivered
                                     статусов (см. DIFF_COMMITTED_STATUSES) — для позиции в «План закупок»
                                     это дало бы враньё «0», хотя вся сумма ей не покрыта планом; здесь
                                     нет строки плана вовсе, поэтому просто минус вся сумма позиции. -->
                                <td style="padding:4px 8px;text-align:right;color:#DC2626">{{ formatCurrency(-(Number(actual.fact_amount ?? actual.total_price ?? 0))) }}</td>
                                <td style="padding:4px 8px;font-size:11px" class="text-medium-emphasis">{{ actual.contractor_name || '—' }}</td>
                                <td style="padding:4px 8px;text-align:center">
                                  <v-icon icon="mdi-alert-circle-outline" size="16" color="warning"
                                    :title="isOrphanedActual(actual)
                                      ? 'Закупка привязана к плановой позиции, которой больше нет (удалена) — в графу «план» она не засчитана. Заведите новую плановую позицию кнопкой справа, либо сопоставьте с существующей.'
                                      : 'Закупка не привязана ни к одной плановой позиции — в графу «план» она не засчитана. Нажмите кнопку-ссылку справа «Сопоставить с плановой».'" />
                                </td>
                                <td style="padding:2px;text-align:center;white-space:nowrap">
                                  <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                                    title="Редактировать позицию закупки"
                                    @click="openReqItemEditFromActual(node, actual)"
                                  />
                                  <!-- Задача владельца 2026-08-17: «раз причина в том, что плановой позиции
                                       нет — предложи создать её из данных этой позиции закупки и сразу
                                       привязать». Переиспользует showAddPlannedDialog/plannedItemForm/
                                       savePlannedItem (тот же диалог, что «Добавить плановую» и
                                       openConvertManualPlanToItem выше) — второй диалог не пишем. -->
                                  <v-btn icon="mdi-plus-box-outline" size="x-small" variant="text" color="deep-orange"
                                    title="Завести плановую позицию по этой закупке и сразу привязать"
                                    @click="openCreatePlannedFromActual(node, actual)"
                                  />
                                  <v-btn icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                                    title="Сопоставить с плановой"
                                    @click="openMapDialog(actual, node.id)"
                                  />
                                </td>
                              </tr>
                              <!-- Подстроки стадий уточнения (справочно, НЕ входят в comparisonPlanTotal/comparisonFactTotal) -->
                              <template v-if="expandedStageRows.has(`a-${actual.purchase_item_id}`)">
                              <tr v-for="sr in stagesWithDiff(actual.stages)" :key="`a-stage-${actual.purchase_item_id}-${sr.stage.key}`"
                                style="border-bottom:1px solid var(--crm-border);background:rgba(245,158,11,0.1)">
                                <td style="padding:2px 8px 2px 40px;color:#94a3b8;font-size:10px">{{ sr.stage.label }}</td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px"></td>
                                <td style="padding:2px 8px" :style="sr.nameChanged ? 'color:#4F46E5' : ''">{{ sr.stage.name }}</td>
                                <td style="padding:2px 8px;text-align:right;color:#64748b">
                                  {{ sr.stage.quantity != null ? `${parseFloat(String(sr.stage.quantity))} ${sr.stage.unit || ''}` : '—' }}
                                  <div v-if="sr.qtyDeltaLabel" style="font-size:10px" :style="`color:${sr.qtyDeltaColor}`">{{ sr.qtyDeltaLabel }}</div>
                                </td>
                                <td style="padding:2px 8px;text-align:right;color:#64748b">
                                  {{ sr.stage.unit_price != null ? formatCurrency(sr.stage.unit_price) : '—' }}
                                  <div v-if="sr.priceDeltaLabel" style="font-size:10px" :style="`color:${sr.priceDeltaColor}`">{{ sr.priceDeltaLabel }}</div>
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

                              <!-- Ручной план ФЭО (сама категория) — до 2026-08-07 был отдельным блоком
                                   строк здесь; теперь это ОДНА строка внутри цикла displayPlannedRowsFor
                                   выше (id = -node.id, planned.isManual), переиспользующая ту же вёрстку,
                                   что и реальная плановая позиция — не отдельный рендер. -->

                              <!-- «Одноимённые позиции из заявок» (сопоставление по ИМЕНИ, matchedReqFor)
                                   УБРАНЫ ЦЕЛИКОМ 2026-08-07 (ШАГ 1 плана дедупликации дерева ФЭО): это был
                                   ТРЕТИЙ независимый рендер тех же самых позиций закупок (см. Таблицу B —
                                   reqOwnersAfter/reqItemRowsFor — и «actualFactFor» выше в этой же панели),
                                   плюс сопоставление по названию давало ложные совпадения (позиция другой
                                   категории с тем же именем показывалась здесь). Единственный источник
                                   факта листа теперь — comparisonData[node.id].actual (см. factForPlanned/
                                   unplannedActualFor). -->

                              <!-- Пусто -->
                              <tr v-if="!displayPlannedRowsFor(node).length && !comparisonData[node.id].actual.length">
                                <td colspan="8" style="padding:12px 8px;text-align:center;color:#9ca3af;font-style:italic">
                                  Нет плановых позиций. Добавьте вручную или загрузите из Excel.
                                </td>
                              </tr>
                            </tbody>
                            <!-- Итоговая строка -->
                            <tfoot v-if="displayPlannedRowsFor(node).length || comparisonData[node.id].actual.length">
                              <!-- Требование владельца (2026-08-12): ИТОГО на уровне плана — только план,
                                   фактическая сумма/разница отсюда убраны вместе с остальными факт-колонками
                                   этого уровня (см. thead выше); факт по-прежнему суммируется в раскрывающихся
                                   блоках под каждой плановой позицией. -->
                              <tr style="background:rgba(34,197,94,0.08);font-weight:600;border-top:2px solid rgba(34,197,94,0.3)">
                                <td :style="{ paddingLeft: `${plannedItemIndentPx(node)}px` }" style="padding-top:4px;padding-right:8px;padding-bottom:4px" class="text-success">ИТОГО</td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px"></td>
                                <td style="padding:4px 8px;text-align:right">
                                  {{ formatCurrency(comparisonPlanTotal(node)) }}
                                </td>
                                <td style="padding:4px 8px"></td>
                              </tr>
                            </tfoot>
                          </table>

                        </div>
                      </td>
                    </tr>

                    <!-- ── Позиции «из заявок» как позиции ФЭО (после поддерева владельца) ── -->
                    <template v-for="owner in (reqOwnersAfter[node.id] || [])" :key="`reqblk-${owner.id}`">
                      <template v-if="plannedBase !== 'purchases'">
                        <template v-for="row in reqItemRowsFor(owner)" :key="`req-${owner.id}-${row.key}`">
                          <tr
                            class="feo-tr feo-req-row"
                            :class="kpiReqRowClass(row)"
                            :data-item-ids="row.group ? row.group.items.map(i => i.id).join(',') : ''"
                            data-item-group="owner-virtual"
                            :style="row.group ? 'background:rgba(20,184,166,0.04)' : 'background:rgba(20,184,166,0.10)'"
                          >
                            <td class="feo-td feo-td-name" :style="{ paddingLeft: reqRowIndent(owner, row) }">
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
                                    @click.stop="photoPreview = { src: row.group.items.find(i => i.product_photo)!.product_photo!, title: row.group.name }">
                                    <v-img :src="row.group.items.find(i => i.product_photo)!.product_photo!" cover />
                                  </v-avatar>
                                  <span class="feo-status-strip mr-1">
                                    <v-icon v-for="gs in groupStatuses(row.group).slice(0, 3)" :key="gs.status"
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
                            <!-- Плановое кол-во: снимок ТЗ (planned_quantity), НЕ текущее кол-во —
                                 см. задачу владельца «план ≠ факт» (Шаг 5, п.1). -->
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ row.group ? groupPlannedQty(row.group) : row.sumQty }}{{ row.group?.unit ? ` ${row.group.unit}` : '' }}</span>
                              <div v-if="row.group" class="feo-plan-note text-medium-emphasis">из заявок</div>
                            </td>
                            <!-- Плановая сумма: снимок ТЗ (planned_total), не съезжает при правке итоговой цены -->
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" :class="!row.group ? 'text-medium-emphasis' : ''" style="font-size:12px">{{ formatCurrency(row.group ? groupPlannedTotal(row.group) : row.sum) }}</span>
                              <div v-if="row.group && row.group.items.length === 1 && (row.group.items[0].planned_unit_price ?? row.group.items[0].unit_price)"
                                class="feo-plan-note text-medium-emphasis">{{ formatCurrency(row.group.items[0].planned_unit_price ?? row.group.items[0].unit_price) }}/ед.</div>
                            </td>
                            <!-- Фактическая сумма: реальный факт (ContractItem/contract_price), а не заглушка —
                                 см. задачу владельца «план ≠ факт» (Шаг 5, п.1). «—» только когда факта ещё нет. -->
                            <td class="feo-td feo-td-num">
                              <span v-if="row.group && groupFactTotal(row.group) != null" class="feo-amount" style="font-size:12px">{{ formatCurrency(groupFactTotal(row.group)!) }}</span>
                              <span v-else-if="row.group" class="feo-amount-empty" title="Итог закупки/договора ещё не известен">—</span>
                            </td>
                            <td class="feo-td feo-td-num"><span v-if="row.group" class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-actions">
                              <div v-if="row.group" class="d-flex align-center justify-end">
                                <v-btn
                                  :icon="expandedReqItemPanels.has(reqPanelKey(owner, row.group)) ? 'mdi-list-box' : 'mdi-list-box-outline'"
                                  variant="text" size="x-small"
                                  :color="expandedReqItemPanels.has(reqPanelKey(owner, row.group)) ? 'teal' : 'grey'"
                                  title="Источники: план vs факт по этой позиции"
                                  @click="toggleReqItemPanel(owner, row.group)"
                                />
                                <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                                  :title="virtGroupPurchaseIds(row.group).length === 1 ? 'Открыть закупку' : 'Несколько закупок — открыть источники'"
                                  @click.stop="virtCart(owner, row.group)" />
                                <v-btn icon="mdi-pencil-outline" variant="text" size="x-small" color="primary"
                                  :title="row.group.items.length === 1 ? 'Редактировать позицию закупки' : 'Несколько позиций — открыть источники'"
                                  @click="virtEdit(owner, row.group)" />
                                <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                                  :title="row.group.items.length === 1 ? 'Удалить позицию из закупки' : 'Несколько позиций — открыть источники'"
                                  @click="virtDelete(owner, row.group)" />
                              </div>
                            </td>
                          </tr>

                          <!-- Панель источников: план vs факт по каждой позиции заявки -->
                          <tr v-if="row.group && expandedReqItemPanels.has(reqPanelKey(owner, row.group))">
                            <td colspan="7" style="padding:0;background:rgba(20,184,166,0.08)">
                              <div :style="{ padding: '8px 12px 10px', marginLeft: reqRowIndent(owner, row) }">
                                <div class="d-flex align-center mb-1" style="gap:6px">
                                  <v-icon icon="mdi-compare-horizontal" size="14" color="teal" />
                                  <span style="font-size:11px;font-weight:600" class="text-teal-darken-2">Позиции: план vs факт</span>
                                </div>
                                <div v-if="loadingComparison.has(owner.id)" class="d-flex align-center" style="gap:8px;padding:4px 0">
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
                                    <tr v-for="it in row.group.items" :key="`src-${it.id}`" :class="kpiItemRowClass(it)" :data-item-id="it.id" data-item-group="owner-virtual-source" style="border-bottom:1px solid #E0F2FE">
                                      <td style="padding:4px 8px;color:#0c4a6e">
                                        <div class="d-flex align-center" style="gap:6px">
                                          <v-avatar v-if="it.product_photo" size="28" rounded class="flex-shrink-0" style="cursor:pointer"
                                            @click.stop="photoPreview = { src: it.product_photo!, title: it.item_name }">
                                            <v-img :src="it.product_photo" cover />
                                          </v-avatar>
                                          <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="purchaseStatusLabel(it.purchase_status)" />
                                          <div>{{ it.item_name }}</div>
                                        </div>
                                        <div class="d-flex align-center flex-wrap" style="gap:8px">
                                          <a href="javascript:void(0)" class="feo-purchase-link"
                                            :title="`Перейти в закупку #${it.purchase_id}`"
                                            @click.stop="router.push(`/orders/${it.purchase_id}`)"
                                          >
                                            <v-icon icon="mdi-link-variant" size="11" class="mr-1" />
                                            {{ it.registry_number || (it.purchase_number != null ? `№ ${it.purchase_number}` : `Закупка #${it.purchase_id}`) }}
                                          </a>
                                          <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                            title="Перейти к заявкам"
                                            @click.stop="router.push('/wishes')"
                                          >
                                            <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}
                                          </a>
                                        </div>
                                        <div v-if="reqItemPlanned(owner.id, it.id)" class="feo-plan-note text-medium-emphasis">
                                          сопоставлено с плановой «{{ reqItemPlanned(owner.id, it.id)?.name }}»
                                        </div>
                                      </td>
                                      <!-- Снимок ТЗ (planned_*), заморожен с момента объявления закупки — не текущее
                                           кол-во/цена, см. задачу владельца «план ≠ факт» (Шаг 5, п.1/2). -->
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.planned_quantity ?? it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ (it.planned_unit_price ?? it.unit_price) ? formatCurrency(it.planned_unit_price ?? it.unit_price) : '—' }}</td>
                                      <td style="padding:4px 8px;text-align:right;font-weight:500">{{ formatCurrency(it.planned_total ?? it.total_price) }}</td>
                                      <!-- ФАКТ: реальные данные (ContractItem/contract_price), «ещё не поставлено»
                                           только когда факта действительно нет — Шаг 5, п.3. -->
                                      <td style="padding:4px 8px;color:#9ca3af;font-style:italic">{{ it.fact_amount != null ? '' : 'ещё не поставлено' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null ? `${it.fact_quantity ?? it.planned_quantity ?? it.quantity}${it.unit ? ` ${it.unit}` : ''}` : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;color:#64748b">{{ it.fact_amount != null && it.fact_unit_price != null ? formatCurrency(it.fact_unit_price) : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right;font-weight:500">{{ it.fact_amount != null ? formatCurrency(it.fact_amount) : '' }}</td>
                                      <td style="padding:4px 8px;text-align:right" :style="getDiffStyle(it.planned_total ?? it.total_price, [it])">{{ formatCurrency(calcDiff(it.planned_total ?? it.total_price, [it])) }}</td>
                                      <td style="padding:4px 8px;color:#9ca3af">—</td>
                                      <td style="padding:4px 8px;text-align:center">
                                        <v-chip size="x-small" color="blue" variant="tonal" :prepend-icon="purchaseStatusIcon(it.purchase_status)">
                                          {{ purchaseStatusLabel(it.purchase_status) }}
                                        </v-chip>
                                      </td>
                                      <td style="padding:2px;text-align:center;white-space:nowrap">
                                        <v-btn icon="mdi-cart-outline" size="x-small" variant="text" color="blue"
                                          title="Открыть закупку"
                                          @click.stop="router.push(`/orders/${it.purchase_id}`)" />
                                        <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                          title="Изменить можно только в заявке"
                                          @click.stop="router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
                                        ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
                                        <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
                                          title="Сменить категорию ФЭО позиции"
                                          @click.stop="openWishItemFeoEdit(owner, it)" />
                                        <template v-if="!it.wish_id">
                                          <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                                            title="Редактировать позицию закупки"
                                            @click="openReqItemEdit(owner, it)" />
                                          <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                            title="Удалить позицию из закупки"
                                            @click="confirmReqItemDelete(owner, it)" />
                                        </template>
                                        <v-btn v-if="!reqItemPlanned(owner.id, it.id) && reqItemActual(owner.id, it.id)"
                                          icon="mdi-link-variant" size="x-small" variant="text" color="teal"
                                          title="Сопоставить с плановой позицией"
                                          @click="mapReqItem(owner, it)"
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
                      <template v-else>
                        <!-- Режим «по закупкам»: папки по purchase_id без слияния -->
                        <template v-for="f in purchaseFoldersFor(owner)" :key="`pf-${owner.id}-${f.purchase_id}`">
                          <tr class="feo-tr feo-req-row" :class="kpiFolderClass(f)" style="background:rgba(20,184,166,0.10)">
                            <td class="feo-td feo-td-name" :style="{ paddingLeft: ((owner.depth + 1) * 20 + 8) + 'px' }">
                              <div class="feo-name-inner">
                                <span class="feo-tree-chevron" style="cursor:pointer" @click.stop="togglePurchaseFolder(f.purchase_id)">
                                  <v-icon size="16">{{ expandedPurchases.has(f.purchase_id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                                </span>
                                <v-icon size="15" color="#0D9488" class="mr-1">{{ expandedPurchases.has(f.purchase_id) ? 'mdi-folder-open-outline' : 'mdi-folder-outline' }}</v-icon>
                                <span>{{ purchaseFolderTitle(f) }}</span>
                                <v-chip size="x-small" variant="tonal" color="blue" class="ml-2" :prepend-icon="purchaseStatusIcon(f.purchase_status)">{{ purchaseStatusLabel(f.purchase_status) }}</v-chip>
                                <span class="feo-code ml-2">{{ f.items.length }} поз.</span>
                                <a v-if="f.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
                                  title="Перейти к заявкам"
                                  @click.stop="router.push('/wishes')"
                                >
                                  <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ f.wish_id }}
                                </a>
                                <!-- Владелец, 2026-08-13: остановка закупки (сейчас всегда скрыт — backend
                                     ещё не отдаёт stopped_at в этой выборке, см. FeoPurchaseFolder.stopped_at) -->
                                <span v-if="f.stopped_at" class="feo-stopped-marker ml-2">
                                  <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ feoStoppedLine(f) }}
                                </span>
                              </div>
                            </td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" style="font-size:12px">{{ f.qty }}{{ f.unit ? ` ${f.unit}` : '' }}</span>
                            </td>
                            <td class="feo-td feo-td-num">
                              <span class="feo-amount" style="font-size:12px">{{ formatCurrency(f.total) }}</span>
                            </td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                            <td class="feo-td feo-td-actions">
                              <div class="d-flex align-center justify-end">
                                <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
                                  title="Открыть закупку"
                                  @click.stop="router.push(`/orders/${f.purchase_id}`)" />
                              </div>
                            </td>
                          </tr>
                          <template v-if="expandedPurchases.has(f.purchase_id)">
                            <tr v-for="it in f.items" :key="`pfi-${owner.id}-${it.id}`" class="feo-tr feo-req-row" :class="kpiItemRowClass(it)" :data-item-id="it.id" data-item-group="owner-purchase-folder" style="background:rgba(20,184,166,0.04)">
                              <td class="feo-td feo-td-name" :style="{ paddingLeft: ((owner.depth + 2) * 20 + 8) + 'px' }">
                                <div class="feo-name-inner">
                                  <span style="width:16px;display:inline-block" />
                                  <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
                                  <v-avatar v-if="it.product_photo" size="28" rounded class="mr-1 flex-shrink-0" style="cursor:pointer"
                                    @click.stop="photoPreview = { src: it.product_photo!, title: it.item_name }">
                                    <v-img :src="it.product_photo" cover />
                                  </v-avatar>
                                  <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="purchaseStatusLabel(it.purchase_status)" />
                                  <span class="feo-name feo-name--l3">{{ it.item_name }}</span>
                                </div>
                              </td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-num">
                                <span class="feo-amount" style="font-size:12px">{{ it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</span>
                              </td>
                              <td class="feo-td feo-td-num">
                                <span class="feo-amount" style="font-size:12px">{{ formatCurrency(it.total_price) }}</span>
                                <div v-if="it.unit_price" class="feo-plan-note text-medium-emphasis">{{ formatCurrency(it.unit_price) }}/ед.</div>
                              </td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-num"><span class="feo-amount-empty">—</span></td>
                              <td class="feo-td feo-td-actions">
                                <div class="d-flex align-center justify-end">
                                  <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
                                    title="Изменить можно только в заявке"
                                    @click.stop="router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
                                  ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
                                  <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
                                    title="Сменить категорию ФЭО позиции"
                                    @click.stop="openWishItemFeoEdit(owner, it)" />
                                  <template v-if="!it.wish_id">
                                    <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                                      title="Редактировать позицию закупки"
                                      @click="openReqItemEdit(owner, it)" />
                                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                                      title="Удалить позицию из закупки"
                                      @click="confirmReqItemDelete(owner, it)" />
                                  </template>
                                </div>
                              </td>
                            </tr>
                          </template>
                        </template>
                      </template>
                    </template>
                  </template>

                  <!-- Drop zone: переместить на верхний уровень -->
                  <tr v-if="dragNodeId"
                    class="feo-tr feo-drop-root"
                    :class="{ 'feo-drop-target': dragOverId === -1 }"
                    @dragover.prevent="dragOverId = -1"
                    @dragleave="dragOverId = null"
                    @drop.prevent="onDropToRoot"
                  >
                    <td colspan="6" class="feo-td text-center text-caption text-medium-emphasis" style="padding:12px">
                      <v-icon icon="mdi-arrow-up-bold" size="16" class="mr-1" />
                      Переместить на верхний уровень (корень)
                    </td>
                  </tr>

                  <!-- Без категории ФЭО: закупки субсидии, у которых ни сама закупка, ни одна
                       позиция не привязаны к категории — деньги есть (KPI их видит), но в дереве
                       ФЭО не отображаются, т.к. дерево строится по категориям. Справочная строка,
                       НЕ входит в ИТОГО ниже. -->
                  <tr v-if="unassignedFeo.amount > 0 || unassignedFeo.purchase_count > 0"
                    class="feo-tr feo-tr--unassigned"
                    style="cursor:pointer"
                    title="Перейти в реестр закупок субсидии"
                    @click="goToUnassignedFeoPurchases"
                  >
                    <td class="feo-td feo-td-name" style="padding-left:8px">
                      <v-icon icon="mdi-help-circle-outline" size="16" color="#F59E0B" class="mr-1" />
                      <span style="color:#F59E0B;font-weight:600">Без категории ФЭО</span>
                      <div class="feo-plan-note text-medium-emphasis font-weight-regular">
                        {{ unassignedFeo.purchase_count }} {{ unassignedFeo.purchase_count === 1 ? 'закупка не привязана' : 'закупок не привязаны' }}
                        к категориям — распределите, иначе деньги не видны в плане
                      </div>
                    </td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num" style="color:#F59E0B;font-weight:600">{{ formatCurrency(unassignedFeo.amount) }}</td>
                    <td class="feo-td feo-td-num">—</td>
                    <td class="feo-td feo-td-num">—</td>
                  </tr>

                  <!-- Итого -->
                  <tr class="feo-tr feo-tr--total">
                    <td class="feo-td feo-td-name font-weight-bold" style="padding-left:8px">ИТОГО</td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      <span title="Сумма верхних категорий: ручное ФЭО, без него — факт (поставлено/оплачено), иначе план">
                        {{ formatCurrency(totalFeoEffective) }}
                      </span>
                      <div v-if="totalFeoBudget !== null" class="feo-plan-note text-medium-emphasis font-weight-regular"
                        title="Ручной бюджет субсидии"
                      >
                        бюджет {{ formatCurrency(totalFeoBudget) }}
                      </div>
                      <div v-if="totalFeoBudget !== null && totalFeoDiff > 0.005"
                        class="feo-plan-note font-weight-regular" style="color:#EF4444"
                        :title="`Сумма категорий ${formatCurrency(totalFeoEffective)} превышает бюджет субсидии ${formatCurrency(totalFeoBudget)}`"
                      >
                        лишние {{ formatCurrency(totalFeoDiff) }}
                      </div>
                      <div v-else-if="totalFeoBudget !== null && totalFeoDiff < -0.005"
                        class="feo-plan-note font-weight-regular" style="color:#F59E0B"
                        :title="`Сумма категорий ${formatCurrency(totalFeoEffective)} меньше бюджета субсидии ${formatCurrency(totalFeoBudget)}`"
                      >
                        не распределено {{ formatCurrency(-totalFeoDiff) }}
                      </div>
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoQtyDisplayFor(r), 0) > 0 ? feoTree.reduce((acc, r) => acc + feoQtyDisplayFor(r), 0) : '—' }}
                    </td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ feoTree.reduce((acc, r) => acc + feoPlannedDisplayFor(r), 0) > 0 ? formatCurrency(feoTree.reduce((acc, r) => acc + feoPlannedDisplayFor(r), 0)) : '—' }}
                    </td>
                    <!-- Футер обязан считаться по той же шкале, что и колонка «В плане-графике» в строках
                         (решение владельца 2026-08-18), иначе ИТОГО противоречит телу таблицы. -->
                    <td class="feo-td feo-td-num font-weight-bold">{{ formatCurrency(totalFeoInPlanSchedule) }}</td>
                    <td class="feo-td feo-td-num font-weight-bold">
                      {{ formatCurrency(feoTree.reduce((acc, r) => acc + feoResidualBaseFor(r), 0) - totalFeoInPlanSchedule) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <SubsidyEventsPanel ref="eventsPanelRef" :subsidy-id="selectedId" />
        </div>

      </template>
    </template>

    <SubsidyEditDialog ref="subsidyEditDialogRef" v-model:add-open="showAddDialog" v-model:edit-open="showEditDialog" />
    <SubsidyDeleteDialog ref="subsidyDeleteDialogRef" v-model="showDeleteDialog" @deleted="loadAll" />
    <FeoCategoryDialog ref="feoCategoryDialogRef" v-model:add-open="showAddFeoDialog" v-model:edit-open="showEditFeoDialog" />
    <FeoCategoryDeleteDialog ref="feoCategoryDeleteDialogRef" v-model="showDeleteFeoDialog" />

    <!-- ── «Приравнять ФЭО к плану» — подтверждение с текущими числами (замечание владельца п.3, 2026-08-12) ── -->
    <v-dialog v-model="alignBudgetDialog.show" max-width="440">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-equal" color="primary" class="mr-2" />
          Приравнять ФЭО к плану?
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="alignBudgetDialog.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="mb-2">«{{ alignBudgetDialog.node?.name }}»</div>
          <div>ФЭО категории станет {{ formatCurrency(alignBudgetDialog.newBudget) }} вместо {{ formatCurrency(alignBudgetDialog.oldBudget) }}</div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="alignBudgetDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="alignBudgetLoading === alignBudgetDialog.node?.id" @click="confirmAlignBudgetToPlan">Приравнять</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Отклонить превышение плана ФЭО — обязательный комментарий (задача владельца 2026-08-05) ── -->
    <v-dialog v-model="excessRejectDialog.show" max-width="440">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-close-circle-outline" color="error" class="mr-2" />
          Отклонить превышение плана
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="excessRejectDialog.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="mb-2">«{{ excessRejectDialog.node?.name }}»</div>
          <v-textarea v-model="excessRejectDialog.comment" label="Причина отклонения" density="comfortable"
            variant="outlined" rows="3" autofocus hide-details="auto" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="excessRejectDialog.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="excessDecideLoading === excessRejectDialog.node?.id" @click="submitExcessReject">Отклонить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Редактирование позиции закупки (из дерева ФЭО) ── -->
    <v-dialog v-model="reqItemEdit.show" :max-width="reqItemEditDialogWidth" :fullscreen="mobile">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
          Редактировать позицию
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="reqItemEdit.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="reqItemEdit.form.item_name" label="Название позиции" density="comfortable"
            variant="outlined" class="mb-2" hide-details="auto" />
          <div class="d-flex ga-2 mb-2">
            <v-text-field v-model.number="reqItemEdit.form.quantity" label="Кол-во" type="number" min="0"
              density="comfortable" variant="outlined" hide-details="auto" style="max-width: 130px" />
            <v-text-field v-model="reqItemEdit.form.unit" label="Ед." density="comfortable" variant="outlined"
              hide-details="auto" style="max-width: 100px" />
            <v-text-field v-model.number="reqItemEdit.form.unit_price" label="Цена за ед., ₽" type="number" min="0"
              density="comfortable" variant="outlined" hide-details="auto" />
          </div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            Сумма: <b>{{ formatCurrency((Number(reqItemEdit.form.quantity) || 0) * (Number(reqItemEdit.form.unit_price) || 0)) }}</b>
          </div>
          <FeoTreeSelect
            v-model="reqItemEdit.form.feo_category_id"
            :nodes="reqItemEditFeoNodes"
            :leaves="reqItemEditFeoLeaves"
            label="Категория ФЭО"
          />
          <div class="text-caption text-medium-emphasis mt-1 mb-2">
            Перенос в другую категорию не тратит новых денег — так перерасход и разбирается
          </div>
          <!-- Владелец (2026-08-18): выбор ПЛАНОВОЙ ПОЗИЦИИ внутри выбранной категории —
               без него позиция при переносе в новую категорию находит план только точным
               совпадением имени, иначе молча заводит новую плановую позицию рядом с уже
               подходящей (прод-инцидент «Огнетушитель ОУ-2»). -->
          <FeoPlannedItemsSelect
            v-if="reqItemEdit.form.feo_category_id"
            :model-value="reqItemEditPlanSelection"
            :category-id="reqItemEdit.form.feo_category_id"
            :nodes="reqItemEditFeoNodes"
            :items="reqItemEditPlannedResiduals"
            :amount="reqItemEditPlanAmount"
            :loading="reqItemEditPlannedLoading"
            :prefill="reqItemEditPlanPrefill"
            :purchase-id="reqItemEdit.purchaseId"
            @update:model-value="onReqItemEditPlanSelect"
            @planned-item-created="reloadReqItemEditPlanned"
            @planned-item-deleted="reloadReqItemEditPlanned"
          />
          <div class="text-caption text-medium-emphasis mt-1">
            Можно привязать к существующей плановой позиции или создать новую — если не
            выбирать, система подберёт сама по точному совпадению названия.
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="reqItemEdit.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="reqItemEdit.saving" @click="saveReqItemEdit">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Удаление позиции закупки (из дерева ФЭО) ── -->
    <v-dialog v-model="reqItemDelete.show" max-width="480">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-delete-outline" color="error" class="mr-2" />
          Удалить позицию
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Удалить позицию «<b>{{ reqItemDelete.name }}</b>» из закупки?
          <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
            Позиция будет удалена из закупки, суммы закупки пересчитаются.
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="reqItemDelete.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="reqItemDelete.deleting" @click="doReqItemDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Позиция из заявки: точечное удаление запрещено — объясняем и даём легальный путь ── -->
    <v-dialog v-model="wishBlockedDelete.show" max-width="520">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-information-outline" color="primary" class="mr-2" />
          Позиция создана заявкой №{{ wishBlockedDelete.wishId }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Позиция «<b>{{ wishBlockedDelete.name }}</b>» ({{ wishBlockedDelete.quantity }} {{ wishBlockedDelete.unit || 'шт' }}, {{ formatCurrency(wishBlockedDelete.sum) }} ₽)
          пришла из заявки №{{ wishBlockedDelete.wishId }}.
          <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
            Позиции согласованной заявки нельзя убирать из плана по одной: заявка меняется целиком и уходит на повторное согласование.
          </v-alert>
          <div class="mt-3">
            Чтобы убрать её из плана-графика — откройте заявку и отредактируйте состав. При сохранении она вернётся на согласование и уйдёт из плана автоматически.
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="wishBlockedDelete.show = false">Отмена</v-btn>
          <v-btn color="primary" @click="openWishFromBlockedDelete">Открыть заявку</v-btn>
          <v-btn v-if="isSaas" color="warning" :loading="wishBlockedDelete.reverting" @click="revertWishBlockedDeleteToDraft">Вернуть заявку в черновик</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Смена категории ФЭО у wish-позиции ── -->
    <v-dialog v-model="wishItemFeoEdit.show" max-width="520">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-swap-horizontal" color="primary" class="mr-2" />
          Сменить категорию ФЭО
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="wishItemFeoEdit.show = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="text-body-2 text-medium-emphasis mb-3">
            Позиция: <b>{{ wishItemFeoEdit.itemName }}</b>
          </div>
          <v-select
            v-model="wishItemFeoEdit.selectedCatId"
            :items="leafFeoCategories"
            item-title="name"
            item-value="id"
            label="Категория ФЭО"
            density="comfortable"
            variant="outlined"
            clearable
            hide-details="auto"
            class="mb-3"
          />
          <div class="mt-1">
            <v-btn
              size="small"
              variant="tonal"
              color="orange"
              prepend-icon="mdi-package-variant"
              :loading="wishItemFeoEdit.unallocatedLoading"
              @click="pickWishItemUnallocated"
            >
              ❓ Не определена
            </v-btn>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="wishItemFeoEdit.show = false">Отмена</v-btn>
          <v-btn color="primary" :loading="wishItemFeoEdit.saving" :disabled="wishItemFeoEdit.selectedCatId == null" @click="saveWishItemFeo">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <SubsidyApproversDialog />
    <SubsidyMembersDialog ref="subsidyMembersDialogRef" />
    <SubsidyCopyApproversDialog />
    <SubsidyApproverFormDialog />
    <SubsidyTemplatesDialog />
    <SubsidyCopyTemplatesDialog />
    <SubsidyContractorOverrideDialog ref="contractorOverrideDialogRef" />

    <FeoImportWizard />

    <PlannedItemEditDialog />
    <CategoryPlanEditDialog />
    <PlannedItemMapDialog />
    <PlannedItemAddDialog />

    <BudgetHistoryDialog ref="historyDialogRef" />

    <PlanGraphVersionHistoryDialog />
    <PlanGraphExportVersionsDialog />
    <PlanGraphSnapshotDialog />
    <PlanGraphSaveVersionDialog />

    <ProductPhotoPreviewDialog />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive, nextTick } from 'vue'
import { useDisplay } from 'vuetify'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useResizableColumns } from '@/composables/useResizableColumns'
import { useToast, type ToastType } from '@/composables/useToast'
import BudgetHistoryDialog from '@/components/BudgetHistoryDialog.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useAuthStore } from '@/stores/auth'
// Владелец (2026-08-18, прод-инцидент — «Огнетушитель ОУ-2» перенесён в новую
// категорию, автоподбор не нашёл точное совпадение имени и молча завёл вторую
// плановую позицию рядом с уже подходящей): диалог «Редактировать позицию»
// теперь даёт выбрать плановую позицию явно, тот же компонент, что в
// CreateOrderView.vue/WishesView.vue — см. reqItemEdit ниже.
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { numOrNull } from '@/utils/numberFormat'
import { PURCHASE_STATUS_META, PURCHASE_STATUS_ORDER, purchaseStatusLabel, purchaseStatusIcon, purchaseStatusColor } from '@/constants/purchaseStatus'
import { formatCurrency, formatCurrencyRound } from '@/composables/subsidies/format'
import SubsidyListHeader from '@/components/subsidies/SubsidyListHeader.vue'
import SubsidyListTable from '@/components/subsidies/SubsidyListTable.vue'
import SubsidyCardsGrid from '@/components/subsidies/SubsidyCardsGrid.vue'
import SubsidySummaryBar from '@/components/subsidies/SubsidySummaryBar.vue'
import SubsidyKpiCards from '@/components/subsidies/SubsidyKpiCards.vue'
import FeoTreeToolbar from '@/components/subsidies/FeoTreeToolbar.vue'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'
import { useKpiDrilldown } from '@/composables/subsidies/useKpiDrilldown'
import SubsidyEventsPanel from '@/components/subsidies/SubsidyEventsPanel.vue'
import SubsidyEditDialog from '@/components/subsidies/SubsidyEditDialog.vue'
import SubsidyDeleteDialog from '@/components/subsidies/SubsidyDeleteDialog.vue'
import FeoCategoryDialog from '@/components/subsidies/FeoCategoryDialog.vue'
import FeoCategoryDeleteDialog from '@/components/subsidies/FeoCategoryDeleteDialog.vue'
import SubsidyApproversDialog from '@/components/subsidies/SubsidyApproversDialog.vue'
import SubsidyApproverFormDialog from '@/components/subsidies/SubsidyApproverFormDialog.vue'
import SubsidyCopyApproversDialog from '@/components/subsidies/SubsidyCopyApproversDialog.vue'
import SubsidyMembersDialog from '@/components/subsidies/SubsidyMembersDialog.vue'
import SubsidyTemplatesDialog from '@/components/subsidies/SubsidyTemplatesDialog.vue'
import SubsidyCopyTemplatesDialog from '@/components/subsidies/SubsidyCopyTemplatesDialog.vue'
import SubsidyContractorOverrideDialog from '@/components/subsidies/SubsidyContractorOverrideDialog.vue'
import ProductPhotoPreviewDialog from '@/components/subsidies/ProductPhotoPreviewDialog.vue'
import PlanGraphVersionHistoryDialog from '@/components/subsidies/PlanGraphVersionHistoryDialog.vue'
import PlanGraphExportVersionsDialog from '@/components/subsidies/PlanGraphExportVersionsDialog.vue'
import PlanGraphSnapshotDialog from '@/components/subsidies/PlanGraphSnapshotDialog.vue'
import PlanGraphSaveVersionDialog from '@/components/subsidies/PlanGraphSaveVersionDialog.vue'
import PlannedItemAddDialog from '@/components/subsidies/PlannedItemAddDialog.vue'
import PlannedItemEditDialog from '@/components/subsidies/PlannedItemEditDialog.vue'
import CategoryPlanEditDialog from '@/components/subsidies/CategoryPlanEditDialog.vue'
import PlannedItemMapDialog from '@/components/subsidies/PlannedItemMapDialog.vue'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'
import FeoImportWizard from '@/components/subsidies/FeoImportWizard.vue'
import { provideSubsidyDetail } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'
// Относительный путь (не '@/...'), т.к. tsconfig.app.json не содержит paths-маппинга
// для алиаса '@' (Vite резолвит его сам через vite.config.ts, но чистый tsc/vue-tsc —
// нет) — с алиасом эти типы стабильно не резолвились бы во ВСЁМ файле (тысячи мест
// используют их как аннотации), заваливая проверку implicit-any лавиной. У новых
// компонентов (components/subsidies/*) та же проблема не бьёт так же сильно — там
// использований единицы, поэтому там оставлен алиас '@/...' как и everywhere else.
import type { SubsidyRow, FeoCategory, FeoNode, FeoPlannedItem, FeoStage, FeoActualItem, FeoReqItem, PlannedBase } from '../composables/subsidies/types'
import { collectSubtreeIds, leftGroupInfo } from '@/composables/subsidies/feoCategoryUtils'

const { globalSubsidyId } = useGlobalSubsidy()

// ── Persist настроек отображения дерева ФЭО (localStorage) — по образцу CARD_ORDER_KEY
// (см. ниже ~subsidyOrder). Без этого переключатель «план»/группировка/раскрытые узлы
// сбрасывались при каждой загрузке страницы — «на разных компьютерах по-разному»
// (задача владельца ШАГ 1, 2026-08-07). Загружается ОДИН раз при инициализации модуля;
// используется как фолбэк для начальных значений refs, объявленных ниже по файлу.
const FEO_DISPLAY_PREFS_KEY = 'subsidies_feo_display_prefs'
interface FeoDisplayPrefs {
  plannedBase?: 'all' | 'manual' | 'requests' | 'purchases'
  feoItemsGroupBy?: 'none' | 'category' | 'category_type'
  expandedIds?: number[]
  expandedReqItems?: number[]
  expandedItemPanels?: number[]
  expandedPlannedItems?: number[]
  // Возвращено из отката e0db76a (план zany-fluttering-mountain.md, п.4): строка плана
  // раскрыта по умолчанию, если под ней есть закупка (см. applyDefaultPlannedExpansion) —
  // но явное решение пользователя СВЕРНУТЬ строку обязано пережить перезагрузку и не быть
  // перезаписано дефолтом. Раз "развёрнуто" теперь может появиться и БЕЗ клика пользователя,
  // самого expandedPlannedItems недостаточно, чтобы отличить «дефолт» от «пользователь
  // свернул» (оба случая — id отсутствует в массиве). collapsedPlannedItems — id, которые
  // пользователь ЯВНО свернул кликом по шеврону (см. togglePlannedItemFolder) —
  // единственный признак с приоритетом над дефолтом.
  collapsedPlannedItems?: number[]
}
function loadFeoDisplayPrefs(): FeoDisplayPrefs {
  try {
    const raw = localStorage.getItem(FEO_DISPLAY_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}
const feoDisplayPrefs = loadFeoDisplayPrefs()

// Правка владельца (2026-08-12, откат явных 180px — регресс): фиксированные
// name/qty/planned/spent=180px сузили feo-table в узкую полосу по центру экрана
// (авто-колонки с width:0 растягивали таблицу на всю ширину, фиксированные — нет).
// Возвращены авто-ширины (0) для name/qty/planned/residual — budget/spent остаются
// зафиксированы под деньги (180px), как и раньше. Совпадение колонок вложенной
// таблицы плановых позиций с основной (см. предыдущую правку выше и баг
// «name~470px vs 187px») теперь достигается НЕ фиксацией ширин, а тем, что у
// вложенной таблицы РОВНО ТОТ ЖЕ набор из 7 колонок, что и у основной —
// name/budget/qty/planned/spent/residual (spent/residual — пустые заглушки) +
// колонка кнопок шириной 112px (как .feo-th-actions у основной). При одинаковом
// наборе фиксированных/авто-колонок и одинаковой полной ширине контейнера
// (colspan захватывает ВСЕ 7 колонок основной таблицы, а не 6) table-layout:fixed
// делит остаток одинаково в обеих таблицах — колонки совпадают по построению.
const feoResize = useResizableColumns('feo-table', {
  name: 0, budget: 180, qty: 0, planned: 0, spent: 180, residual: 0,
})

const router = useRouter()
const route  = useRoute()

// Владелец (2026-08-29): «превышение согласовывают только владельцы/финансисты,
// у начальника отдела таких прав быть не может». Раньше здесь стоял фронтовый
// canDecidePlanExcess = can('plan_excess.decide') поверх «я назначен в шаге»
// (excessMyPendingStep) — но can() читал НАСЛЕДУЮЩИЙ список прав с /api/users/me
// (get_effective_actions), а реальный гейт POST /decide — НЕнаследующий
// has_org_key. org_admin без гранта ВИДЕЛ кнопку «Одобрить» и получал 403 при
// клике. Убрано — единственный источник истины теперь can_decide в ответе
// GET /api/plan-excess (см. excessApprovalFor(node)?.can_decide ниже,
// backend/app/routers/plan_excess.py _can_decide_plan_excess).

// SubsidyRow/SubsidyMember/FeoCategory/FeoNode — см. composables/subsidies/types.ts
// (единственный источник; раньше дублировались тут и во всех вынесенных
// диалогах компонентах, Правило №6).

// ── State ─────────────────────────────────────────
const registryArea = ref<HTMLElement | null>(null)
const feoTableArea = ref<HTMLElement | null>(null)
const loading    = ref(false)
// saving/savingFeo (диалоги субсидии/категории ФЭО) — теперь внутри
// SubsidyEditDialog.vue/SubsidyDeleteDialog.vue/FeoCategoryDialog.vue/
// FeoCategoryDeleteDialog.vue, каждый со своим независимым состоянием.
const loadingFeo = ref(false)

const allSubsidies    = ref<SubsidyRow[]>([])
const feoCategories   = ref<FeoCategory[]>([])
const purchaseTotals  = ref<Record<number, number>>({})
// НЕпривязанные (feo_planned_item_id IS NULL) — используются в feoPlannedRequestsFor/feoQtyRequestsFor,
// чтобы не задваивать ручной план листа (Ур.5) позициями заявок, которые его уже расходуют.
const plannedPurchaseTotals = ref<Record<number, number>>({})
const plannedPurchaseQty = ref<Record<number, number>>({})
// Привязанные (feo_planned_item_id IS NOT NULL) — «выбрано заявками» из плана; см.
// feoPlannedConsumedFor/feoQtyConsumedFor и заметку под «Плановой суммой».
const plannedPurchaseTotalsLinked = ref<Record<number, number>>({})
const plannedPurchaseQtyLinked = ref<Record<number, number>>({})
// «Сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановой сумме элемента
// безусловно, поверх план/заказ. См. feoPlannedOverFor/feoQtyOverFor. Итоговая «Плановая
// сумма»/«Плановое количество» (feoPlannedDisplayRaw/feoQtyDisplayRaw) больше НЕ считается
// на фронте — читается готовой из GET /api/feo-categories/plan-tree (planTreeByCat), см.
// app.services.feo_plan.compute_feo_plan_tree (единый источник, сессия 2026-08-05).
const plannedPurchaseTotalsOver = ref<Record<number, number>>({})
const plannedPurchaseQtyOver = ref<Record<number, number>>({})
// Прогнозное предупреждение «цена выше плановой» (сессия 2026-08-05, формула v2 —
// backend app.services.feo_plan.compute_feo_plan_tree). Только для информирования,
// НИКАКИХ блокировок — см. feoForecastWarningFor и предупреждение под «Плановой суммой».
const plannedPurchaseForecast = ref<Record<number, { forecast: number; forecast_over: number; plan_manual: number }>>({})
// Единая формула «Плановой суммы»/«Планового количества» узла — числа готовые с бэкенда
// (сессия 2026-08-05, задача «формула только на бэкенде»: раньше фронт пересчитывал сам,
// MAX(план, выбрано) + сверх_плана — СТАРАЯ формула, расходилась с KPI «Запланировано»
// на дашборде/в списке субсидий, который считает НОВУЮ формулу «заказ замещает план»,
// app.services.feo_plan.compute_feo_plan_tree). См. GET /api/feo-categories/plan-tree.
// excess_amount/excess_pending/excess_approved — согласование превышения плана
// над финансированием ФЭО узла (задача владельца 2026-08-05, «блокировать пока
// не согласовано» — см. backend app.services.feo_plan.compute_feo_plan_tree /
// app.routers.plan_excess). excessFor(node) ниже читает их из этой же карты.
// plan_manual/ordered_sum/residual/consumed — те же поля, что в GET /feo-categories/plan-tree
// (см. compute_feo_plan_tree), нужны feoResidualNoteFor ниже, чтобы заметка под «Плановой
// суммой» брала план из ТОГО ЖЕ источника, что и сама колонка (баг «заметка показывает
// не тот план», сессия 2026-08-05) — не из feoResiduals (Ур.5-детализация, другая сущность).
// Виновник превышения плана над ФЭО (задача владельца, план zany-fluttering-mountain.md
// п.«Заметный сигнал превышения», возвращено из отката e0db76a) — см. backend/app/services/
// feo_plan.py::find_excess_culprit за методом определения; null, пока превышения нет либо
// оно согласовано (сервер считает виновника только для узлов с неснятым excess_amount).
interface ExcessCulprit {
  purchase_id: number | null
  purchase_number: string | number | null
  item_name: string | null
  amount_before: number
  amount_at_crossing: number
  cumulative_after: number
}
// План zany-fluttering-mountain.md, п.4/п.2 (фронт): «позиции-виновники» превышения
// плана над вручную заданной суммой (excess_plan_items) — раньше приходили как голое
// {name, amount} без возможности перейти в закупку. Теперь каждая позиция несёт свой
// id и список связанных закупок (переиспользует planned_item_consumption на бэкенде,
// см. app/services/feo_plan.py); клик по позиции с одной закупкой ведёт прямо туда,
// с несколькими — открывает список (см. excessPlanCulpritClick/шаблон ниже).
interface ExcessPlanItemPurchase {
  id: number
  registry_number: string | number | null
  purchase_number: string | number | null
  status: string | null
  status_label: string | null
  amount: number
  stopped_at: string | null
}
interface ExcessPlanItem {
  id: number
  name: string
  amount: number
  purchases: ExcessPlanItemPurchase[]
}
const planTreeByCat = ref<Record<number, {
  display: number; display_quantity: number
  excess_amount?: number; excess_pending?: boolean; excess_approved?: boolean
  plan_manual?: number; ordered_sum?: number; residual?: number; consumed?: number
  // qty_plan — количественный двойник plan_manual/plan (замещение «заказ вместо плана»,
  // если набрано полностью, иначе собственный plan_manual-по-количеству), см.
  // backend/app/services/feo_plan.py::compute_feo_plan_tree. Нужен фолбэком в feoQtyFor
  // для мигрированных листьев (план в FeoPlannedItem, planned_quantity узла = null).
  qty_plan?: number
  // Задача владельца «план ≠ факт» (сессия 2026-08-06): факт узла (fact/fact_quantity)
  // и второй, независимый вид превышения — «итог закупки/КП дороже плана»
  // (excess_fact_over_plan/excess_fact_pending/excess_fact_approved), см. excessFactFor().
  plan?: number; fact?: number; fact_quantity?: number
  excess_fact_over_plan?: number; excess_fact_pending?: boolean; excess_fact_approved?: boolean
  // «Заметный сигнал превышения» — то же excess_amount под понятным именем + виновник
  // (закупка, из-за которой узел вышел за ФЭО), см. ExcessCulprit выше.
  excess_over_feo?: number; excess_culprit?: ExcessCulprit | null
  // over — полная плановая сумма узла ПОВЕРХ node["plan"] (см. backend
  // align_budget_to_plan: new_budget = plan + over), нужен фронту только чтобы
  // показать «станет N ₽» в подтверждении «Приравнять ФЭО к плану» ДО вызова —
  // реальный расчёт всё равно делает бэкенд.
  over?: number
  // Замечания владельца п.2/п.4 (2026-08-12, «план ≠ факт», продолжение) —
  // ТРЕТИЙ вид превышения (Σ плановых позиций > вручную заданного плана) и
  // постоянная пометка «превышение согласовано», см. excessPlanFor()/
  // excessPlanApprovalPermanent() ниже.
  manual_plan_entered?: number
  excess_plan_over_manual?: number
  excess_plan_approved?: boolean
  excess_plan_pending?: boolean
  excess_plan_items?: ExcessPlanItem[]
  excess_approval_amount?: number | null
  excess_approval_at?: string | null
  excess_approval_by_name?: string | null
  // План zany-fluttering-mountain.md, п.3: «план был X → стал Y» в постоянной плашке
  // «превышение согласовано» — снимок plan_excess_approvals.plan_before/plan_after на
  // МОМЕНТ создания запроса согласования (не пересчитывается задним числом), см.
  // excessPlanApprovalPermanent() ниже.
  excess_approval_plan_before?: number | null
  excess_approval_plan_after?: number | null
  // План zany-fluttering-mountain.md, п.1/п.5: способ расчёта плана категории —
  // переключатель в диалоге создания/редактирования, см. feoForm.planSource/
  // feoEditForm.planSource ниже.
  plan_source?: 'planned_items' | 'manual_sum'
  manual_plan_amount?: number | null
}>>({})
// Детали запросов согласования превышения плана ФЭО — GET /api/plan-excess?subsidy_id=
// (backend/app/routers/plan_excess.py). Карта feo_category_id → ПОСЛЕДНИЙ (по created_at,
// список от бэкенда уже отсортирован) запрос: шаги с ФИО согласующих, статус, комментарий
// отказа. planTreeByCat.excess_pending/excess_approved читает ТУ ЖЕ таблицу на бэкенде
// (см. app.services.feo_plan.compute_feo_plan_tree), поэтому статусы согласованы между
// собой — этот объект добавляет детали (кто именно, комментарий), которых в plan-tree нет.
interface PlanExcessStep {
  id: number; approval_id: number; user_id: number | null; order_num: number
  role_name: string | null; full_name: string | null; status: string
  comment: string | null; decided_at: string | null; decided_by_user_id: number | null
}
interface PlanExcessApprovalDto {
  id: number; feo_category_id: number; subsidy_id: number
  excess_amount: number; plan_amount: number | null; budget_amount: number | null
  status: string; mode: string; requested_by_id: number | null
  created_at: string | null; resolved_at: string | null; comment: string | null
  steps: PlanExcessStep[]
  self_approval?: boolean; warning?: string | null
  // Правка 2026-08-29: сервер сам считает, реально ли пройдёт POST /decide для
  // текущего пользователя (та же проверка has_org_key + «свой шаг» + запрет
  // самосогласования, что и в гейте /decide — см. backend/app/routers/plan_excess.py
  // _can_decide_plan_excess). Раньше кнопки судили по наследующему списку прав
  // с /api/users/me (canDecidePlanExcess/can('plan_excess.decide')) — org_admin
  // без гранта ВИДЕЛ кнопку «Одобрить» и получал 403 при клике.
  can_decide?: boolean
}
const planExcessApprovals = ref<Record<number, PlanExcessApprovalDto>>({})
// Закупки субсидии без категории ФЭО (ни у самой закупки, ни у одной позиции) — деньги
// есть (влияют на KPI «Ведётся работа»/«Запланировано» по субсидии), но в дереве ФЭО
// их не видно, т.к. дерево строится по категориям (сессия 2026-08-05). Отдельный
// ключ "unassigned" в GET /api/feo-categories/plan-tree, справочный, НЕ входит в
// ИТОГО дерева / feoPlannedDisplayFor / comparisonPlanTotal.
const unassignedFeo = ref<{ amount: number; purchase_count: number; purchase_ids: number[] }>({
  amount: 0, purchase_count: 0, purchase_ids: [],
})
// GET /plan-tree отдаёт "unassigned" как ДОПОЛНИТЕЛЬНЫЙ ключ рядом с числовыми id категорий
// (см. backend/app/routers/feo_categories.py) — вычленяем его в unassignedFeo, а
// planTreeByCat остаётся чистым Record<number, ...>, как и раньше (по нему никто не
// итерируется, только node.id → значение, так что нечисловой ключ и без выделения
// был бы безвреден, но так типобезопаснее).
function splitPlanTree(raw: Record<string, any>) {
  const { unassigned, ...rest } = raw || {}
  unassignedFeo.value = unassigned && typeof unassigned === 'object'
    ? { amount: Number(unassigned.amount || 0), purchase_count: Number(unassigned.purchase_count || 0), purchase_ids: unassigned.purchase_ids || [] }
    : { amount: 0, purchase_count: 0, purchase_ids: [] }
  return rest as Record<number, {
    display: number; display_quantity: number
    excess_amount?: number; excess_pending?: boolean; excess_approved?: boolean
    plan_manual?: number; ordered_sum?: number; residual?: number; consumed?: number
    qty_plan?: number
    plan?: number; fact?: number; fact_quantity?: number
    excess_fact_over_plan?: number; excess_fact_pending?: boolean; excess_fact_approved?: boolean
    excess_over_feo?: number; excess_culprit?: ExcessCulprit | null
  }>
}
function goToUnassignedFeoPurchases() {
  if (!selectedId.value) return
  router.push(`/orders?subsidy_id=${selectedId.value}`)
}
const excessRequestLoading = ref<number | null>(null)
const excessDecideLoading = ref<number | null>(null)
const excessRejectDialog = ref<{ show: boolean; node: FeoNode | null; comment: string }>({
  show: false, node: null, comment: '',
})
const expandedIds     = ref<number[]>(feoDisplayPrefs.expandedIds || [])
const selectedId      = ref<number | null>(null)
// Состояние списка субсидий (год/режим таблица-карточки/карточки/пагинация) —
// вынесено в useSubsidyList.ts (волна 5b, SubsidyListHeader/Table/CardsGrid/
// SummaryBar.vue). Этому файлу из него нужны только selectedYear (авто-выбор
// последнего года при загрузке, ниже по файлу), filteredSubsidies/effectiveView
// (условия v-if в шаблоне выше) и mobile (диалог reqItemEdit, :fullscreen="mobile").
const { selectedYear, filteredSubsidies, effectiveView, mobile } = useSubsidyList({ allSubsidies })

// Объявлен здесь (не ниже, у других computed из блока «панель субсидии»), потому что
// reqItemEditSubsidyId (см. useFeoLeaves для диалога правки позиции) читает
// selectedSubsidy.value синхронно при вызове composable'а — до его собственной
// декларации это ReferenceError "Cannot access 'selectedSubsidy' before initialization".
const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

// 12-04: Residuals state
const feoResiduals = ref<Record<number, {
  feo_item_id: number
  name: string
  category_id: number
  planned_amount: number
  used_amount: number
  wish_used_amount: number
  residual: number
  linked_purchase_ids: number[]
}>>({})
const residualsLoading = ref(false)

// Плановые позиции (Ур.5) сгруппированы по листовой категории ФЭО — для заметки
// «план N · выбрано заявками M · остаток K» под «Плановой суммой» (см. feoResidualNoteFor).
// Переиспользует уже загруженный feoResiduals, ничего заново не считает.
const feoResidualsByCat = computed<Record<number, { planned: number; consumed: number; residual: number }>>(() => {
  const result: Record<number, { planned: number; consumed: number; residual: number }> = {}
  for (const item of Object.values(feoResiduals.value)) {
    const catId = item.category_id
    if (catId == null) continue
    const acc = (result[catId] ||= { planned: 0, consumed: 0, residual: 0 })
    acc.planned += Number(item.planned_amount || 0)
    // Заявки не расходуют план (владелец, 2026-08-17) — в consumed идут только
    // позиции закупок; wish_used_amount всегда 0, но поле оставлено в типе ради контракта ответа.
    acc.consumed += Number(item.used_amount || 0)
    acc.residual += Number(item.residual || 0)
  }
  return result
})
// БАГ 4 (сессия 2026-08-05): раньше значения брались из feoResidualsByCat — суммы
// ТОЛЬКО по Ур.5-записям (FeoPlannedItem) этой категории. У категории могли одновременно
// быть: (а) собственный план на уровне листа (planned_quantity × planned_amount, напр.
// 8 000 000 ₽) и (б) одна мелкая Ур.5-детализация (напр. «вавава» на 333 ₽) — заметка
// показывала «план 333 ₽», хотя колонка «Плановая сумма» рядом честно показывала
// 8 000 000 ₽ (из planTreeByCat/display). Теперь ЗНАЧЕНИЯ берутся из planTreeByCat —
// того же источника, что и колонка (plan_manual); feoResidualsByCat используется
// ТОЛЬКО как признак «у категории есть Ур.5-детализация», не как источник чисел —
// иначе эта заметка задваивала бы feoPlanConsumedNoteFor (см. v-else-if в шаблоне).
//
// БАГ (жалоба владельца 2026-08-13, конечная категория «Расходные материалы для
// проведения окружных полуфиналов…»): «Выбрано заявками 0 — это блядь что значит?»
// — consumed раньше читался из t.ordered_sum/t.consumed (planTreeByCat) — это
// backend-поле own_ordered/ordered, СЧИТАЕТ ТОЛЬКО заявки, ПРИВЯЗАННЫЕ к плановым
// позициям этой категории (feo_planned_item_id). У этой категории все 9 закупленных
// позиций на 118 365,60 ₽ заведены БЕЗ привязки (обычные позиции с тем же
// feo_category_id) — ordered_sum по ним 0, хотя по плану уже фактически набрано.
// Тот же приём, что и в feoPlanConsumedNoteFor: consumed = непривязанные
// (feoPlannedRequestsFor, карта plannedPurchaseTotals) + привязанные
// (feoPlannedConsumedFor, карта plannedPurchaseTotalsLinked) — «в закупках» считает
// ВСЕ заявки по категории, а не только те, что явно привязаны к Ур.5-позиции.
function feoResidualNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
  if (node.hasChildren) return null
  if (!feoResidualsByCat.value[node.id]) return null
  const t = planTreeByCat.value[node.id]
  if (!t) return null
  const planned = Number(t.plan_manual ?? 0)
  const consumed = feoInPlanScheduleFor(node)
  const residual = planned - consumed
  if (planned <= 0 && consumed <= 0) return null
  return { planned, consumed, residual }
}

// Версии план-графика (История/Экспорт редакций/Снимок/Сохранить редакцию) —
// состояние вынесено в usePlanGraphVersions.ts (см. openVersionHistory/
// openExportVersionsDialog/openSaveVersionDialog ниже).

const showAddDialog      = ref(false)
const showEditDialog     = ref(false)
const showDeleteDialog   = ref(false)
const showAddFeoDialog   = ref(false)
const showEditFeoDialog  = ref(false)
const showDeleteFeoDialog = ref(false)

// Budget history dialog ref
const historyDialogRef = ref<InstanceType<typeof BudgetHistoryDialog> | null>(null)

// Согласующие/участники/шаблоны/удаление субсидии и категорий ФЭО — состояние и
// CRUD вынесены в components/subsidies/* + composables/subsidies/useSubsidyApprovers.ts
// и useSubsidyTemplates.ts. approvingSubsidyId остаётся здесь — используется
// approveSubsidy()/canApproveSubsidy() вне этой волны рефакторинга.
const approvingSubsidyId = ref<number | null>(null)

// FEO search
const feoSearch = ref('')

// FEO inline budget edit
const inlineBudgetId = ref<number | null>(null)
const inlineBudgetVal = ref('')
const inlineInputEl = ref<HTMLInputElement | null>(null)

// FEO inline planned_quantity edit
const inlineQtyId = ref<number | null>(null)
const inlineQtyVal = ref('')
const inlineQtyInputEl = ref<HTMLInputElement | null>(null)

// FEO inline planned_amount edit
const inlineAmtId = ref<number | null>(null)
const inlineAmtVal = ref('')
const inlineAmtInputEl = ref<HTMLInputElement | null>(null)

// FEO Drag & Drop
const dragNodeId = ref<number | null>(null)
const dragOverId = ref<number | null>(null)

// feoWarnKindLabel/feoWarnSubtitle/feoImport/feoImportTargetSubsidy/
// FEO_TARGET_FIELDS/feoDragMapping/feoIgnoredCols/feoDragOverTarget/
// feoResultPanels/feoToggleResultPanel/feoUnmatchedNeedsMapping/
// feoHasSuggestions/feoRemapPlannedCount/feoAcceptAllSuggestions/
// feoStep4MainLabel/feoPluralRu/feoLoadSummary/feoCurrentSheet/
// feoCurrentHeaders/feoMappingValid/feoUnmappedCount/feoIsMapped/feoIsIgnored/
// feoIsTargetFilled/feoGetColumnLabel/feoGetSamples/feoOnDragStart/
// feoOnDropToTarget/feoOnDropToUnresolved/feoUnmapTarget/feoIgnoreColumn/
// feoAutoMap — вынесены в useFeoImport.ts (см. const { feoImport } =
// useFeoImport() ниже — тот же реактивный объект остаётся feoImport.show для
// кнопки «Импорт» в тулбаре выше).

// ── FEO Level 5: Плановые позиции vs Фактические ──
// FeoPlannedItem/FeoStage/FeoActualItem — см. composables/subsidies/types.ts
// (Правило №6 — один источник, используют и PlannedItem*Dialog.vue).
const expandedItemPanels = ref<Set<number>>(new Set(feoDisplayPrefs.expandedItemPanels || []))
const comparisonData = ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>({})
const loadingComparison = ref<Set<number>>(new Set())

// Photo preview overlay
const photoPreview = ref<{ src: string; title: string } | null>(null)

// showMapDialog/mapTarget/mapCategoryId/mappingInProgress, showAddPlannedDialog/
// addPlannedCategoryId/savingPlannedItem/convertFromCategoryPlanId/
// createPlannedFromActualId/plannedItemForm/addPlannedProductId/
// addPlannedProductPhoto/addPlannedMatchConfirmed/addPlannedPriceMeta/
// PLANNED_PRICE_SOURCE_LABELS/formatRuDateShort/addPlannedPriceCaption/
// plannedItemAmountIsComputed/recalcPlannedAmountFromUnitPrice/
// applyPlannedProductHint/onPlannedItemProductPick/onPlannedItemProductClear —
// вынесены в usePlannedItems.ts.
async function toggleItemPanel(node: FeoNode) {
  const id = node.id
  if (expandedItemPanels.value.has(id)) {
    expandedItemPanels.value.delete(id)
    return
  }
  expandedItemPanels.value.add(id)
  if (comparisonData.value[id]) return
  loadingComparison.value.add(id)
  try {
    const subsId = selectedId.value
    const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
      `/feo-planned-items/comparison?feo_category_id=${id}${subsId ? `&subsidy_id=${subsId}` : ''}`
    )
    comparisonData.value[id] = res
    applyDefaultPlannedExpansion(id)
  } catch {
    comparisonData.value[id] = { planned: [], actual: [] }
  } finally {
    loadingComparison.value.delete(id)
  }
}

async function refreshComparison(categoryId: number) {
  const subsId = selectedId.value
  const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
    `/feo-planned-items/comparison?feo_category_id=${categoryId}${subsId ? `&subsidy_id=${subsId}` : ''}`
  )
  comparisonData.value[categoryId] = res
  applyDefaultPlannedExpansion(categoryId)
}

// ── Позиции «из заявок» в дереве ФЭО (раскрытие листа-папки) ──
// FeoReqItem — теперь в composables/subsidies/types.ts (нужен и useKpiDrilldown.ts,
// волна 5b) — единственный источник, импортирован сверху (Правило №6).
interface FeoReqRow {
  key: string
  header: string
  level: number
  count: number
  sumQty: number
  sum: number
  group: FeoVirtualGroup | null
  items: FeoReqItem[]
}
const plannedItemsByCat = ref<Record<number, FeoReqItem[]>>({})
const plannedItemsLoaded = ref(false)
const expandedReqItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedReqItems || []))
const feoItemsGroupBy = ref<'none' | 'category' | 'category_type'>(feoDisplayPrefs.feoItemsGroupBy || 'none')

interface FeoPurchaseFolder {
  purchase_id: number
  purchase_number: number | null
  registry_number: string | null
  purchase_status: string
  wish_id: number | null
  qty: number
  unit: string | null
  total: number
  items: FeoReqItem[]
  // Владелец, 2026-08-13: остановка закупки — переносится из items[0] при
  // группировке (см. purchaseFoldersFor), см. комментарий у FeoReqItem.stopped_at.
  stopped_at?: string | null
  stopped_by_name?: string | null
}
const expandedPurchases = ref<Set<number>>(new Set())
function togglePurchaseFolder(pid: number) {
  if (expandedPurchases.value.has(pid)) expandedPurchases.value.delete(pid)
  else expandedPurchases.value.add(pid)
}

// Раскрытие позиций закупок, привязанных к конкретной плановой позиции (Ур.5) в панели
// «план vs факт». Персистится в FEO_DISPLAY_PREFS_KEY наравне с остальными настройками
// дерева (требование владельца 2026-08-09) — см. saveFeoDisplayPrefs/watch ниже.
// Возвращено из отката e0db76a (план zany-fluttering-mountain.md, п.4): владелец решил,
// что закупки под плановой строкой «нет вовсе», если её не видно без клика — раскрыто ПО
// УМОЛЧАНИЮ, когда под строкой есть хотя бы одна закупка (см. applyDefaultPlannedExpansion).
// Явное решение пользователя свернуть строку (collapsedPlannedItems, см. интерфейс
// FeoDisplayPrefs) имеет приоритет над этим правилом — именно поэтому toggle ниже пишет
// в ОБА множества.
const expandedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.expandedPlannedItems || []))
const collapsedPlannedItems = ref<Set<number>>(new Set(feoDisplayPrefs.collapsedPlannedItems || []))
function togglePlannedItemFolder(plannedId: number) {
  if (expandedPlannedItems.value.has(plannedId)) {
    expandedPlannedItems.value.delete(plannedId)
    collapsedPlannedItems.value.add(plannedId)
  } else {
    expandedPlannedItems.value.add(plannedId)
    collapsedPlannedItems.value.delete(plannedId)
  }
}

// Применяет правило «раскрыто по умолчанию, если под плановой позицией есть закупка» —
// вызывается сразу после того, как comparisonData[catId] загрузился (единственный момент,
// когда factForPlanned() вообще может быть непустым), см. toggleItemPanel/refreshComparison/
// ensureComparison. Пропускает id из collapsedPlannedItems (пользователь явно свернул —
// его выбор приоритетнее) и id, уже присутствующие в expandedPlannedItems (нечего делать).
function applyDefaultPlannedExpansion(catId: number) {
  const data = comparisonData.value[catId]
  if (!data) return
  const cat = feoCategories.value.find(c => c.id === catId)
  const plannedIds: number[] = data.planned.length
    ? data.planned.map(p => p.id)
    : (cat && (cat.planned_quantity != null || cat.planned_amount != null)) ? [-catId] : []
  for (const pid of plannedIds) {
    if (collapsedPlannedItems.value.has(pid)) continue
    if (expandedPlannedItems.value.has(pid)) continue
    if (factForPlanned(catId, pid).length > 0) {
      expandedPlannedItems.value.add(pid)
    }
  }
}

// Замечание владельца 1 (2026-08-12): «по одной сворачивать неудобно, надо развернуть
// все сразу, посмотреть, как что покупалось, и свернуть все сразу». Кнопка-переключатель
// в шапке раскрытой категории — использует ТЕ ЖЕ expandedPlannedItems/collapsedPlannedItems
// (persist через FEO_DISPLAY_PREFS_KEY уже работает, см. watch ниже), ничего нового не заводит.
function anyPlannedExpandedFor(node: FeoNode): boolean {
  return displayPlannedRowsFor(node).some(p => expandedPlannedItems.value.has(p.id))
}
function toggleAllPlannedItemsForCategory(node: FeoNode) {
  const ids = displayPlannedRowsFor(node).map(p => p.id)
  const collapse = ids.some(id => expandedPlannedItems.value.has(id))
  for (const id of ids) {
    if (collapse) {
      expandedPlannedItems.value.delete(id)
      collapsedPlannedItems.value.add(id)
    } else {
      expandedPlannedItems.value.add(id)
      collapsedPlannedItems.value.delete(id)
    }
  }
}

// Разворот строки позиции закупки в подстроки стадий уточнения (ФЭО/План/Закупка/Договор/Приёмка).
// Ключ — строка вида `<префикс-типа-строки>-<purchase_item_id | it.id>`, префикс совпадает с
// префиксом :key соответствующей <tr v-for> ниже, чтобы не пересекаться между типами строк.
const expandedStageRows = ref<Set<string>>(new Set())
function toggleStageRow(key: string) {
  if (expandedStageRows.value.has(key)) expandedStageRows.value.delete(key)
  else expandedStageRows.value.add(key)
}

// hasReqItems/toggleReqItems (переключатель Таблицы B на САМОМ листе) убраны 2026-08-07 —
// после ШАГ 1 плана дедупликации у листа единственный источник детализации это
// expandedItemPanels/toggleItemPanel (Таблица A), см. шеврон/папку в имени узла выше.
// expandedReqItems осталась — она всё ещё используется reqExpandedFor() для владельцев
// (hasChildren-категорий), там Таблица B легитимна (см. reqOwnersAfter).

// ── Слияние: позиции из заявок ↔ ручные дочерние позиции ФЭО ──
// Миграция плана категории → плановые позиции (сессия 2026-08-12): у мигрированного
// листа planned_quantity/planned_amount оба null, хотя план есть (живёт в активных
// плановых позициях) — без фолбэка isManualPosLeaf вернула бы false, и «строгая
// фильтрация ручные/из заявок» (v-if в шапке дерева, plannedBase==='requests')
// перестала бы прятать мигрированный лист, как прятала до миграции. Фолбэк —
// planTreeByCat.plan_manual > 0, тот же сигнал «есть план в позициях», что и в
// feoPlannedTotalFor выше (там же объяснение поля).
function isManualPosLeaf(node: FeoNode): boolean {
  if (node.hasChildren) return false
  if (node.planned_quantity != null || node.planned_amount != null) return true
  const t = planTreeByCat.value[node.id]
  return !!(t && Number(t.plan_manual || 0) > 0)
}

// Задача владельца «направление со временем может наполниться, соответственно
// должно считаться и оно» (сессия 2026-08-12, повод — «Бинт марлевый» 48 441,80 ₽
// привязан прямо к «Окружным», а это направление с 5 подкатегориями, не лист —
// панель «Плановые позиции» раньше раскрывалась ТОЛЬКО у листа, состав был не
// посмотреть). Раскрывать панель у узла с детьми имеет смысл, только если у него
// САМОГО есть активные FeoPlannedItem (иначе раскрывать нечего — там всегда пусто).
//
// Выбор способа определения «есть свои позиции» БЕЗ похода в сеть за comparisonData
// для каждого узла подряд (это раскрывало бы GET .../comparison на КАЖДУЮ группу
// дерева сразу при рендере — дорого и не нужно, панель и так грузится ЛЕНИВО по
// клику): бэкенд (compute_feo_plan_tree, app/services/feo_plan.py, ветка с детьми)
// теперь считает plan_manual направления как «Σ plan_manual детей + Σ amount
// СОБСТВЕННЫХ активных плановых позиций узла» (own_amt). Раз оба числа уже лежат в
// planTreeByCat (bulk-загружен один раз в loadFeo для ВСЕХ категорий сразу),
// «plan_manual узла минус Σ plan_manual его НЕПОСРЕДСТВЕННЫХ детей» и есть own_amt —
// без единого дополнительного запроса. Для многоуровневых направлений это тоже
// корректно: plan_manual каждого ребёнка уже рекурсивно включает ЕГО own_amt, поэтому
// разница с суммой прямых детей даёт own_amt именно ЭТОГО узла, а не всей ветки.
//
// Если бэкенд-правка ещё не выкатилась (plan_manual группы = Σ детей без own_amt,
// как было раньше) — diff всегда 0, и кнопка раскрытия у направления не появится,
// даже если своя позиция физически есть. Это ожидаемо и безопасно (см. поручение) —
// как только бэкенд посчитает own_amt, число само перестанет быть нулевым без правок
// фронта.
function hasOwnPlannedAmountFor(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  const t = planTreeByCat.value[node.id]
  if (t) {
    const childrenPlanManual = (node.children || []).reduce(
      (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
    )
    const ownAmt = Number(t.plan_manual || 0) - childrenPlanManual
    if (ownAmt > 0.005) return true
  }
  // Фолбэк на приёмке (2026-08-12): на живых данных бэкенд-процесс ещё не перезапущен
  // с правкой own_amt (см. комментарий выше — файл поменялся, работающий сервер нет),
  // поэтому diff по plan_manual выше пока всегда 0, хотя «Бинт марлевый» физически
  // висит на категории 3677. Используем УЖЕ загруженный bulk-массив plannedItemsByCat
  // (`/feo-categories/planned-purchase-items`, грузится один раз на всю субсидию в
  // loadFeo/refreshReqData, БЕЗ дополнительного запроса на этот узел) — если у узла
  // есть СОБСТВЕННЫЕ позиции закупок (те же, что попадают в панель через
  // unplannedActualFor/displayPlannedRowsFor), считаем, что раскрывать есть что.
  // Не идеальный признак (пропустит совсем ручной FeoPlannedItem без единой закупки
  // за ним), но не требует похода в сеть и покрывает боевой сценарий задачи.
  return (plannedItemsByCat.value[node.id]?.length || 0) > 0
}

// Числовой двойник hasOwnPlannedAmountFor выше — не просто «есть ли своя сумма», а
// СКОЛЬКО её (жалоба владельца 2026-08-13: «48 441,80 — нигде нет такой суммы»,
// «внутри какой панели, я нигде не вижу этой хуйни, что это за фантом» — план
// направления после бэкенд-правки own_amt уже включает свою часть в шапке строки, но
// нигде не показан отдельным числом). Та же формула («plan_manual узла минус Σ
// plan_manual его непосредственных детей» = own_amt этого узла, см. комментарий у
// hasOwnPlannedAmountFor), только возвращает сумму, а не boolean — используется в
// строке «в т.ч. на самом направлении N ₽» под «Плановой суммой» направления.
function feoOwnDirectionPlanFor(node: FeoNode): number {
  if (!node.hasChildren) return 0
  const t = planTreeByCat.value[node.id]
  if (!t) return 0
  const childrenPlanManual = (node.children || []).reduce(
    (sum, ch) => sum + Number(planTreeByCat.value[ch.id]?.plan_manual || 0), 0
  )
  const own = Number(t.plan_manual || 0) - childrenPlanManual
  return own > 0.005 ? own : 0
}

interface FeoVirtualGroup {
  name: string
  unit: string | null
  qty: number
  total: number
  category: string
  product_type: string
  items: FeoReqItem[]
}

function normName(s: string | null | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

const mergedReqByCat = computed(() => {
  const matched: Record<number, FeoReqItem[]> = {}
  const virtualByCat: Record<number, FeoVirtualGroup[]> = {}
  // Позиции, привязанные к плановой позиции (feo_planned_item_id) — расходуют план Ур.5,
  // а не складываются с ним поверх. Ключ — feo_planned_item_id. Исключены из matched/
  // virtualByCat, иначе matchedReqTotal() и feoPlannedDisplayFor() задвоят план.
  const linkedByPlanned: Record<number, FeoReqItem[]> = {}
  const byId: Record<number, FeoNode> = {}
  for (const n of flattenAll(feoTree.value)) byId[n.id] = n
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const catId = Number(catIdStr)
    const node = byId[catId]
    const leafByName: Record<string, number> = {}
    for (const ch of node?.children || []) {
      if (!ch.hasChildren) leafByName[normName(ch.name)] = ch.id
    }
    const groups = new Map<string, FeoVirtualGroup>()
    for (const it of items || []) {
      if (it.feo_planned_item_id != null) {
        ;(linkedByPlanned[it.feo_planned_item_id] ||= []).push(it)
        continue
      }
      const key = normName(it.item_name)
      const childId = leafByName[key]
      if (childId != null) {
        ;(matched[childId] ||= []).push(it)
        continue
      }
      let g = groups.get(key)
      if (!g) {
        g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
        groups.set(key, g)
      }
      g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
      g.total += Number(it.total_price || 0)
      if (!g.unit && it.unit) g.unit = it.unit
      g.items.push(it)
    }
    const list = [...groups.values()]
    if (list.length) virtualByCat[catId] = list
  }
  return { matched, virtualByCat, linkedByPlanned }
})

// Все позиции заявок сгруппированные по cat (без исключения matched) — для режима 'requests'
const allReqGroupsByCat = computed<Record<number, FeoVirtualGroup[]>>(() => {
  const result: Record<number, FeoVirtualGroup[]> = {}
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const catId = Number(catIdStr)
    const groups = new Map<string, FeoVirtualGroup>()
    for (const it of items || []) {
      const key = normName(it.item_name)
      let g = groups.get(key)
      if (!g) {
        g = { name: it.item_name, unit: it.unit, qty: 0, total: 0, category: it.category, product_type: it.product_type, items: [] }
        groups.set(key, g)
      }
      g.qty = Math.round((g.qty + Number(it.quantity || 0)) * 10000) / 10000
      g.total += Number(it.total_price || 0)
      if (!g.unit && it.unit) g.unit = it.unit
      g.items.push(it)
    }
    const list = [...groups.values()]
    if (list.length) result[catId] = list
  }
  return result
})

const purchaseFoldersByCat = computed<Record<number, FeoPurchaseFolder[]>>(() => {
  const res: Record<number, FeoPurchaseFolder[]> = {}
  for (const [catIdStr, items] of Object.entries(plannedItemsByCat.value)) {
    const byPid = new Map<number, FeoPurchaseFolder>()
    for (const it of items || []) {
      let f = byPid.get(it.purchase_id)
      if (!f) {
        f = { purchase_id: it.purchase_id, purchase_number: it.purchase_number, registry_number: it.registry_number, purchase_status: it.purchase_status, wish_id: it.wish_id, qty: 0, unit: it.unit, total: 0, items: [], stopped_at: it.stopped_at, stopped_by_name: it.stopped_by_name }
        byPid.set(it.purchase_id, f)
      }
      f.qty = Math.round((f.qty + Number(it.quantity || 0)) * 10000) / 10000
      f.total += Number(it.total_price || 0)
      if (f.unit !== it.unit) f.unit = null
      f.items.push(it)
    }
    const list = [...byPid.values()].sort((a, b) => (a.registry_number || String(a.purchase_number ?? a.purchase_id)).localeCompare(b.registry_number || String(b.purchase_number ?? b.purchase_id), 'ru'))
    if (list.length) res[Number(catIdStr)] = list
  }
  return res
})
function purchaseFoldersFor(node: FeoNode): FeoPurchaseFolder[] {
  return purchaseFoldersByCat.value[node.id] || []
}
// Владелец, 2026-08-13: «закупка остановлена {ФИО}, {дата}» — используется в
// маркере ЗАКУПКА ОСТАНОВЛЕНА у позиций/папок закупок (см. FeoActualItem/
// FeoReqItem/FeoPurchaseFolder.stopped_at — сейчас всегда undefined, т.к.
// /feo-planned-items/comparison и /feo-categories/planned-purchase-items ещё не
// отдают эти поля; функция готова, сработает как только бэкенд их добавит).
function feoStoppedLine(row: { stopped_by_name?: string | null; stopped_at?: string | null }): string {
  const who = row.stopped_by_name || 'неизвестно кем'
  const when = row.stopped_at ? new Date(row.stopped_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
  return `остановлена ${who}${when ? ', ' + when : ''}`
}
function purchaseFolderTitle(f: FeoPurchaseFolder): string {
  return 'Закупка ' + (f.registry_number || (f.purchase_number != null ? '№ ' + f.purchase_number : '#' + f.purchase_id))
}

function matchedReqFor(node: FeoNode): FeoReqItem[] {
  return mergedReqByCat.value.matched[node.id] || []
}
function virtualGroupsFor(node: FeoNode): FeoVirtualGroup[] {
  if (plannedBase.value === 'requests') return allReqGroupsByCat.value[node.id] || []
  return mergedReqByCat.value.virtualByCat[node.id] || []
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.1): строка виртуальной
// позиции «из заявок» обязана показывать ЗАМОРОЖЕННЫЙ снимок ТЗ (planned_quantity/
// planned_total), а не текущее quantity/total_price позиции закупки (которое задним
// числом подменяется ценой по итогам закупки) — иначе плановая сумма «съезжает» вслед
// за правкой цены. it.planned_quantity/planned_total уже приходят с бэкенда с фолбэком
// на текущие значения для старых записей без снимка (см. GET /feo-categories/planned-purchase-items) —
// доп. `?? it.quantity`/`?? it.total_price` здесь — вторая линия защиты на случай отсутствия поля.
function groupPlannedQty(g: FeoVirtualGroup): number {
  return Math.round(g.items.reduce((s, it) => s + Number(it.planned_quantity ?? it.quantity ?? 0), 0) * 10000) / 10000
}
function groupPlannedTotal(g: FeoVirtualGroup): number {
  return g.items.reduce((s, it) => s + Number(it.planned_total ?? it.total_price ?? 0), 0)
}
// Фактическая сумма группы: сумма fact_amount по позициям, у которых факт уже известен
// (ContractItem/contract_price, см. purchase_item_fact_amount). null — ни у одной
// позиции группы факта ещё нет (план_schedule или нет договорных данных).
function groupFactTotal(g: FeoVirtualGroup): number | null {
  const withFact = g.items.filter(it => it.fact_amount != null)
  if (!withFact.length) return null
  return withFact.reduce((s, it) => s + Number(it.fact_amount || 0), 0)
}
function matchedReqQty(node: FeoNode): number {
  return Math.round(matchedReqFor(node).reduce((s, x) => s + Number(x.quantity || 0), 0) * 10000) / 10000
}
function matchedReqTotal(node: FeoNode): number {
  return matchedReqFor(node).reduce((s, x) => s + Number(x.total_price || 0), 0)
}
// Финансирование задано вручную → детальное разбиение в ФЭО, ручные план-значения приоритетнее заявок
function mergedManualPriority(node: FeoNode): boolean {
  return feoBudgetFor(node) > 0
}

// Раскрыт ли узел для показа виртуальных позиций из заявок
function reqExpandedFor(node: FeoNode): boolean {
  return node.hasChildren ? expandedIds.value.includes(node.id) : expandedReqItems.value.has(node.id)
}

// Карта: после какой строки дерева (последний узел поддерева) рисовать виртуальные позиции владельца
function ownerReqRowCount(n: FeoNode): number {
  if (plannedBase.value === 'manual') return 0
  return plannedBase.value === 'purchases' ? purchaseFoldersFor(n).length : virtualGroupsFor(n).length
}

// ШАГ 1 плана дедупликации дерева ФЭО (2026-08-07): ЛИСТЬЯ (!n.hasChildren) исключены —
// их plannedItemsByCat-позиции (эта же «Таблица B») сгруппированы РОВНО тем же ключом
// coalesce(feo_category_id, purchase.feo_category_id), что и comparisonData[leaf.id].actual
// (см. Таблицу A выше, expandedItemPanels) — то есть это ФИЗИЧЕСКИ ТЕ ЖЕ позиции закупок,
// просто пришедшие с другого эндпоинта. Для листа Таблица A уже показывает их все —
// повторный показ здесь был вторым независимым рендером (баг «Great Wall POER» ×2-3).
// Для владельцев (hasChildren) содержимое другое — позиции, заведённые прямо на
// родительскую категорию, а не на конкретный лист — оставлено без изменений.
const reqOwnersAfter = computed<Record<number, FeoNode[]>>(() => {
  const map: Record<number, FeoNode[]> = {}
  const all = visibleFeoNodes.value
  for (let i = all.length - 1; i >= 0; i--) {
    const n = all[i]
    if (!n.hasChildren || !ownerReqRowCount(n) || !reqExpandedFor(n) || !isNodeVisible(n)) continue
    let j = i
    while (j + 1 < all.length && all[j + 1].depth > n.depth) j++
    ;(map[all[j].id] ||= []).push(n)
  }
  return map
})

function reqItemRowsFor(node: FeoNode): FeoReqRow[] {
  const groupsList = virtualGroupsFor(node)
  const mode = feoItemsGroupBy.value
  const groupRowOf = (g: FeoVirtualGroup): FeoReqRow =>
    ({ key: `g-${normName(g.name)}`, header: '', level: 0, count: g.items.length, sumQty: g.qty, sum: g.total, group: g, items: g.items })
  if (mode === 'none') {
    return [...groupsList].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(groupRowOf)
  }
  const sorted = [...groupsList].sort((a, b) =>
    a.category.localeCompare(b.category, 'ru')
    || a.product_type.localeCompare(b.product_type, 'ru')
    || a.name.localeCompare(b.name, 'ru'))
  const rows: FeoReqRow[] = []
  let curCat: string | null = null
  let curType: string | null = null
  const headerRow = (key: string, header: string, level: number, grp: FeoVirtualGroup[]): FeoReqRow => ({
    key, header, level,
    count: grp.reduce((s, x) => s + x.items.length, 0),
    sumQty: Math.round(grp.reduce((s, x) => s + x.qty, 0) * 10000) / 10000,
    sum: grp.reduce((s, x) => s + x.total, 0),
    group: null,
    items: grp.flatMap(x => x.items),
  })
  for (const g of sorted) {
    if (g.category !== curCat) {
      curCat = g.category
      curType = null
      rows.push(headerRow(`c-${curCat}`, curCat, 1, sorted.filter(x => x.category === curCat)))
    }
    if (mode === 'category_type' && g.product_type !== curType) {
      curType = g.product_type
      rows.push(headerRow(`c-${curCat}-t-${curType}`, curType, 2,
        sorted.filter(x => x.category === curCat && x.product_type === curType)))
    }
    rows.push(groupRowOf(g))
  }
  return rows
}

function reqRowIndent(node: FeoNode, row: FeoReqRow): string {
  const extra = row.group
    ? (feoItemsGroupBy.value === 'none' ? 0 : feoItemsGroupBy.value === 'category' ? 1 : 2)
    : row.level - 1
  return `${(node.depth + 1 + extra) * 20 + 8}px`
}

// ── Панель источников виртуальной позиции «план vs факт» + правка/удаление ──
const expandedReqItemPanels = ref<Set<string>>(new Set())

function reqPanelKey(node: FeoNode, g: FeoVirtualGroup): string {
  return `${node.id}|${normName(g.name)}`
}

async function ensureComparison(catId: number) {
  if (comparisonData.value[catId]) return
  loadingComparison.value.add(catId)
  try {
    const subsId = selectedId.value
    comparisonData.value[catId] = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
      `/feo-planned-items/comparison?feo_category_id=${catId}${subsId ? `&subsidy_id=${subsId}` : ''}`
    )
    applyDefaultPlannedExpansion(catId)
  } catch {
    comparisonData.value[catId] = { planned: [], actual: [] }
  } finally {
    loadingComparison.value.delete(catId)
  }
}

function toggleReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
  const key = reqPanelKey(node, g)
  if (expandedReqItemPanels.value.has(key)) {
    expandedReqItemPanels.value.delete(key)
    return
  }
  expandedReqItemPanels.value.add(key)
  ensureComparison(node.id)
}

function openReqItemPanel(node: FeoNode, g: FeoVirtualGroup) {
  expandedReqItemPanels.value.add(reqPanelKey(node, g))
  ensureComparison(node.id)
}

// Кнопки виртуальной позиции: одна цель → сразу действие, несколько → раскрыть панель источников
function virtGroupPurchaseIds(g: FeoVirtualGroup): number[] {
  return [...new Set(g.items.map(i => i.purchase_id))]
}

function virtCart(node: FeoNode, g: FeoVirtualGroup) {
  const ids = virtGroupPurchaseIds(g)
  if (ids.length === 1) router.push(`/orders/${ids[0]}`)
  else openReqItemPanel(node, g)
}

function virtEdit(node: FeoNode, g: FeoVirtualGroup) {
  if (g.items.length === 1) openReqItemEdit(node, g.items[0])
  else openReqItemPanel(node, g)
}

function virtDelete(node: FeoNode, g: FeoVirtualGroup) {
  if (g.items.length === 1) confirmReqItemDelete(node, g.items[0])
  else openReqItemPanel(node, g)
}

function reqItemActual(catId: number, itemId: number): FeoActualItem | null {
  return comparisonData.value[catId]?.actual.find(a => a.purchase_item_id === itemId) || null
}

// Стадии позиции «из заявок» (matchedReqFor) — сама FeoReqItem их не содержит, но одна и та же
// позиция закупки, как правило, приходит и в comparisonData.actual (см. reqItemActual), где
// бэкенд уже проставил stages.
function stagesForReqItem(catId: number, itemId: number): FeoStage[] {
  return reqItemActual(catId, itemId)?.stages || []
}

function reqItemPlanned(catId: number, itemId: number): FeoPlannedItem | null {
  const a = reqItemActual(catId, itemId)
  if (!a?.feo_planned_item_id) return null
  return comparisonData.value[catId]?.planned.find(p => p.id === a.feo_planned_item_id) || null
}

function mapReqItem(node: FeoNode, item: FeoReqItem) {
  const a = reqItemActual(node.id, item.id)
  if (a) openMapDialog(a, node.id)
}

// Обновление данных «из заявок» без сброса раскрытых папок
async function refreshReqData(catId?: number) {
  if (!selectedId.value) return
  const [totals, items, planTree] = await Promise.all([
    apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${selectedId.value}`),
    apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${selectedId.value}`),
    apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${selectedId.value}`),
  ])
  planTreeByCat.value = splitPlanTree(planTree)
  loadPlanExcessApprovals(selectedId.value)
  const sums: Record<number, number> = {}
  const qtys: Record<number, number> = {}
  const sumsLinked: Record<number, number> = {}
  const qtysLinked: Record<number, number> = {}
  const sumsOver: Record<number, number> = {}
  const qtysOver: Record<number, number> = {}
  const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
  for (const [k, v] of Object.entries(totals)) {
    const totalLinked = Number(v?.total_linked || 0)
    const qtyLinked = Number(v?.qty_linked || 0)
    const totalOver = Number(v?.total_over || 0)
    const qtyOver = Number(v?.qty_over || 0)
    sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
    qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
    sumsLinked[Number(k)] = totalLinked
    qtysLinked[Number(k)] = qtyLinked
    sumsOver[Number(k)] = totalOver
    qtysOver[Number(k)] = qtyOver
    forecasts[Number(k)] = {
      forecast: Number(v?.forecast || 0),
      forecast_over: Number(v?.forecast_over || 0),
      plan_manual: Number(v?.plan_manual || 0),
    }
  }
  plannedPurchaseTotals.value = sums
  plannedPurchaseQty.value = qtys
  plannedPurchaseTotalsLinked.value = sumsLinked
  plannedPurchaseQtyLinked.value = qtysLinked
  plannedPurchaseTotalsOver.value = sumsOver
  plannedPurchaseQtyOver.value = qtysOver
  plannedPurchaseForecast.value = forecasts
  plannedItemsByCat.value = items
  plannedItemsLoaded.value = true
  if (catId != null) {
    delete comparisonData.value[catId]
    await ensureComparison(catId)
  }
}

const reqItemEdit = reactive({
  show: false, saving: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null,
  form: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null, feo_category_id: null as number | null },
  // Снимок значений на момент открытия диалога (правка 2026-08-18): saveReqItemEdit
  // шлёт в PATCH только реально изменённые поля — иначе при заморозке ТЗ
  // (TZ_FROZEN_STATUSES) правка ОДНОЙ ТОЛЬКО категории отбивается 409 из-за
  // молча переотправленных qty/price, которых пользователь не трогал.
  original: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null },
})

// Жалоба владельца (2026-08-18): диалог правки позиции всегда был зашит в
// max-width 520 — на мониторе 27" название категории/позиции не влезает, а
// внутри уже дерево ФЭО + список плановых позиций, которым тесно. В файле нет
// общего паттерна адаптивной ширины диалогов (остальные — фикс max-width +
// :fullscreen="mobile"), поэтому заводим свой computed по брейкпоинтам
// Vuetify. mobile (<mobileBreakpoint) уже держит fullscreen как было.
const { smAndDown: reqItemEditSmAndDown, mdAndDown: reqItemEditMdAndDown } = useDisplay()
const reqItemEditDialogWidth = computed(() => {
  if (reqItemEditSmAndDown.value) return 720   // планшет/маленький ноутбук
  if (reqItemEditMdAndDown.value) return 900   // обычный десктоп
  return 1100                                   // крупный монитор (lg/xl и выше)
})

// selectedSubsidy объявлен выше (сразу после allSubsidies/selectedId) — useFeoLeaves
// ниже читает reqItemEditSubsidyId.value синхронно при вызове (immediate-watch внутри
// композабла), поэтому computed(), от которого он зависит, обязан быть создан ДО этой
// строки, иначе ReferenceError "Cannot access before initialization" (было до 2026-08-12).
//
// Дерево категорий ФЭО для пикера в диалоге правки позиции (Правка владельца
// 2026-08-12: «перенести позицию в другую категорию — так превышение и
// разбирается»). Переиспользует useFeoLeaves (тот же composable, что
// PurchaseItemsEditor использует под FeoTreeSelect) — реагирует на subsidyId,
// сам подгружает узлы/листья при открытии диалога/смене субсидии.
const reqItemEditSubsidyId = computed(() => selectedSubsidy.value?.id ?? null)
const { feoLeaves: reqItemEditFeoLeaves, feoNodes: reqItemEditFeoNodes } = useFeoLeaves({ subsidyId: reqItemEditSubsidyId })

// Плановые позиции категории для диалога правки (владелец, 2026-08-18) — тот же
// источник (/feo-categories/plan-positions) и composable, что CreateOrderView.vue
// использует для того же компонента (purchasePlannedResiduals) — здесь своя копия,
// т.к. reqItemEdit — отдельный, независимый от формы создания закупки диалог.
// plannedItemsByCat в этом файле — ДРУГОЕ (реальные позиции закупок категории из
// /feo-categories/planned-purchase-items, «Таблица B»), не годится как items для
// FeoPlannedItemsSelect (там нужны сами плановые строки с planned_amount/residual).
// excludePurchaseId — своя закупка не занимает свой же план (иначе двойное вычитание).
const {
  plannedResiduals: reqItemEditPlannedResiduals,
  plannedLoading: reqItemEditPlannedLoading,
  reloadPlanned: reloadReqItemEditPlanned,
} = useFeoPlannedResiduals({
  subsidyId: reqItemEditSubsidyId,
  excludePurchaseId: computed(() => reqItemEdit.purchaseId),
})
// Составной выбор { kind, id } | null — зеркалит feoPlanSelection в CreateOrderView.vue.
// touched различает «не трогал» (PATCH без feo_planned_item_id — прежний автоподбор)
// от «явно выбрал/снял выбор» (PATCH шлёт feo_planned_item_id, в т.ч. null).
const reqItemEditPlanSelection = ref<FeoPlanSelection | null>(null)
const reqItemEditPlanTouched = ref(false)
function onReqItemEditPlanSelect(val: FeoPlanSelection | null) {
  reqItemEditPlanTouched.value = true
  // Строки kind='plan_position'/'feo_article' — план самого листа категории ФЭО
  // (FeoCategory.planned_quantity/amount), а не отдельная FeoPlannedItem — им нечего
  // положить в feo_planned_item_id (id там — id категории, не плановой позиции).
  // Выбор такой строки означает «план — на уровне категории», что эквивалентно
  // отсутствию привязки к конкретной FeoPlannedItem — отправляем null тем же путём,
  // что и снятие выбора.
  reqItemEditPlanSelection.value = val && val.kind === 'planned_item' ? val : null
}
// Сумма редактируемой позиции — компонент честно покажет, хватает ли остатка плана.
const reqItemEditPlanAmount = computed(() =>
  (Number(reqItemEdit.form.quantity) || 0) * (Number(reqItemEdit.form.unit_price) || 0)
)
// Предзаполнение диалога «Создать в плане закупок» данными уже введённой позиции.
const reqItemEditPlanPrefill = computed(() => ({
  name: reqItemEdit.form.item_name,
  quantity: reqItemEdit.form.quantity,
  unit: reqItemEdit.form.unit,
  amount: reqItemEditPlanAmount.value,
}))

// Принцип владельца (2026-08-18): «после того как заявка попала в План
// закупок, дальше редактирование и перераспределение между плановыми
// позициями — только в Закупках». Раньше здесь был ранний выход в /wishes
// для item.wish_id — тупик: заявка, уже ушедшая в закупку, там заблокирована
// (TZ_FROZEN_STATUSES), и пользователь упирался в баннер «редактирование
// запрещено», хотя позиция реально существует в закупке и правится через
// PATCH /purchases/{id}/items/{id} (см. saveReqItemEdit ниже). Диалог теперь
// открывается всегда; блокировки (заморозка ТЗ, превышение плана) отрабатывает
// сам PATCH своим 409, который saveReqItemEdit уже распаковывает.
function openReqItemEdit(node: FeoNode, item: FeoReqItem) {
  reqItemEdit.catId = node.id
  reqItemEdit.purchaseId = item.purchase_id
  reqItemEdit.itemId = item.id
  reqItemEdit.form = { item_name: item.item_name, quantity: item.quantity, unit: item.unit || '', unit_price: item.unit_price, feo_category_id: node.id }
  reqItemEdit.original = {
    item_name: reqItemEdit.form.item_name, quantity: reqItemEdit.form.quantity,
    unit: reqItemEdit.form.unit, unit_price: reqItemEdit.form.unit_price,
  }
  // Текущая привязка к плановой позиции — начальное состояние пикера ниже; сброс
  // touched — открытие диалога не считается правкой, пока пользователь не кликнет.
  reqItemEditPlanSelection.value = item.feo_planned_item_id != null
    ? { kind: 'planned_item', id: item.feo_planned_item_id }
    : null
  reqItemEditPlanTouched.value = false
  reqItemEdit.show = true
}

// Карандаш в строках факта панели «план vs факт» (все три блока) правит ПОЗИЦИЮ
// ЗАКУПКИ, а не план — задача владельца (2026-08-09, пункт 2). Переиспользует
// готовый диалог reqItemEdit/saveReqItemEdit выше вместо второго диалога:
// адаптер собирает совместимый FeoReqItem из FeoActualItem (те же данные под
// другими именами полей — purchase_item_id → id). Блокировки уже отработаны
// внутри переиспользуемых функций, второй раз их тут не пишем: заморозка ТЗ
// (TZ_FROZEN_STATUSES) и превышение плана (assert_tz_not_over_plan) → 409 от
// PATCH /purchases/{id}/items/{id} (backend/app/routers/purchases.py),
// распаковывается в saveReqItemEdit через e.payload.message/e.detail.
function openReqItemEditFromActual(node: FeoNode, actual: FeoActualItem) {
  openReqItemEdit(node, {
    id: actual.purchase_item_id,
    item_name: actual.item_name,
    quantity: actual.quantity ?? 0,
    unit: actual.unit,
    unit_price: actual.unit_price ?? 0,
    total_price: actual.total_price ?? 0,
    purchase_id: actual.purchase_id,
    purchase_number: actual.purchase_number,
    registry_number: actual.registry_number,
    purchase_status: actual.purchase_status || '',
    wish_id: actual.wish_id ?? null,
    category: '', product_type: '',
    feo_planned_item_id: actual.feo_planned_item_id ?? null,
  })
}

async function saveReqItemEdit() {
  if (!reqItemEdit.itemId || !reqItemEdit.purchaseId) return
  reqItemEdit.saving = true
  try {
    // Шлём ТОЛЬКО реально изменённые поля (правка 2026-08-18) — сверяем со
    // снимком, сделанным при открытии диалога (reqItemEdit.original). Раньше
    // тело PATCH всегда несло item_name/quantity/unit/unit_price целиком, даже
    // нетронутыми — при заморозке ТЗ (TZ_FROZEN_STATUSES) это отбивало 409
    // правку ОДНОЙ ТОЛЬКО категории, хотя её менять можно.
    const body: Record<string, any> = {}
    if (reqItemEdit.form.item_name !== reqItemEdit.original.item_name) {
      body.item_name = reqItemEdit.form.item_name
    }
    // quantity/unit_price приходят из v-model.number — при очистке поля Vue даёт
    // '' (не null), сырое сравнение с original (числом/null) ловит ложные "изменения"
    // ('' !== null) и шлёт '' на сервер → 422. Сравниваем и шлём нормализованные
    // через numOrNull (2026-09-04, тот же хелпер, что и в savePlannedItem/FEO-форме):
    // '' → null, 0 сохраняется как число.
    const normQuantity = numOrNull(reqItemEdit.form.quantity)
    if (normQuantity !== numOrNull(reqItemEdit.original.quantity)) {
      body.quantity = normQuantity
    }
    if ((reqItemEdit.form.unit || '') !== (reqItemEdit.original.unit || '')) {
      body.unit = reqItemEdit.form.unit || null
    }
    const normUnitPrice = numOrNull(reqItemEdit.form.unit_price)
    if (normUnitPrice !== numOrNull(reqItemEdit.original.unit_price)) {
      body.unit_price = normUnitPrice
    }
    // Категорию отправляем ТОЛЬКО если пользователь её реально сменил (catId —
    // категория, под которой позиция открыта в дереве, т.е. текущая) — не
    // переписывать лишнего при обычном редактировании имени/цены.
    const categoryChanged = reqItemEdit.form.feo_category_id != null && reqItemEdit.form.feo_category_id !== reqItemEdit.catId
    if (categoryChanged) body.feo_category_id = reqItemEdit.form.feo_category_id
    // Явный выбор плановой позиции (владелец, 2026-08-18) — шлём поле ТОЛЬКО если
    // пользователь реально кликнул в пикере (reqItemEditPlanTouched), иначе бэкенд
    // не должен отличить «не трогал» от «выбрал и снял» — молчание сохраняет прежний
    // автоподбор по точному совпадению имени (см. backend patch_purchase_item).
    if (reqItemEditPlanTouched.value) {
      body.feo_planned_item_id = reqItemEditPlanSelection.value?.id ?? null
    }
    if (Object.keys(body).length === 0) {
      reqItemEdit.show = false
      showSnack('Изменений нет')
      return
    }
    const _patchRes = await apiFetch<any>(`/purchases/${reqItemEdit.purchaseId}/items/${reqItemEdit.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    reqItemEdit.show = false
    await refreshReqData(reqItemEdit.catId ?? undefined)
    if (categoryChanged && reqItemEdit.form.feo_category_id != null) {
      delete comparisonData.value[reqItemEdit.form.feo_category_id]
      await ensureComparison(reqItemEdit.form.feo_category_id)
    }
    // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    // см. app.services.feo_plan.assert_no_unapproved_excess. excess_warnings —
    // тот же паттерн, что и у заявок (WishesView.vue).
    if (_patchRes?.excess_warnings?.length) {
      showSnack(_patchRes.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack('Позиция обновлена')
    }
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось сохранить позицию', 'error')
  } finally {
    reqItemEdit.saving = false
  }
}

const reqItemDelete = reactive({
  show: false, deleting: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null, name: '',
})

// Позиция «из заявки»: точечно удалить её из плана нельзя — заявка уже согласована,
// и убрать одну строку в обход цепочки согласующих значит сломать инвариант
// «изменил заявку → она уходит на повторное согласование» (см. backend/app/routers/purchases.py).
// Вместо слепого перехода в заявку — объясняем, куда идти и что произойдёт.
const wishBlockedDelete = reactive({
  show: false, reverting: false,
  wishId: null as number | null, catId: null as number | null,
  name: '', quantity: null as number | null, unit: '' as string | null, sum: 0,
})

function confirmReqItemDelete(node: FeoNode, item: FeoReqItem) {
  if (item.wish_id) {
    wishBlockedDelete.wishId = item.wish_id
    wishBlockedDelete.catId = node.id
    wishBlockedDelete.name = item.item_name
    wishBlockedDelete.quantity = item.quantity
    wishBlockedDelete.unit = item.unit
    wishBlockedDelete.sum = item.total_price
    wishBlockedDelete.show = true
    return
  }
  reqItemDelete.catId = node.id
  reqItemDelete.purchaseId = item.purchase_id
  reqItemDelete.itemId = item.id
  reqItemDelete.name = item.item_name
  reqItemDelete.show = true
}

async function doReqItemDelete() {
  if (!reqItemDelete.itemId || !reqItemDelete.purchaseId) return
  reqItemDelete.deleting = true
  try {
    await apiFetch(`/purchases/${reqItemDelete.purchaseId}/items/${reqItemDelete.itemId}`, { method: 'DELETE' })
    reqItemDelete.show = false
    await refreshReqData(reqItemDelete.catId ?? undefined)
    showSnack('Позиция удалена из закупки')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось удалить позицию', 'error')
  } finally {
    reqItemDelete.deleting = false
  }
}

function openWishFromBlockedDelete() {
  wishBlockedDelete.show = false
  router.push({ path: '/wishes', query: { open: String(wishBlockedDelete.wishId) } })
}

// Только для SaaS-ролей: принудительно вернуть заявку в черновик — эндпоинт сам
// убирает всю заявку (не одну позицию) из плана-графика.
async function revertWishBlockedDeleteToDraft() {
  if (!wishBlockedDelete.wishId) return
  wishBlockedDelete.reverting = true
  try {
    const res = await apiFetch<{ convert_warning?: string | null }>(`/wishes/${wishBlockedDelete.wishId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: 'draft' }),
    })
    wishBlockedDelete.show = false
    if (res?.convert_warning) {
      showSnack(`Заявка №${wishBlockedDelete.wishId} возвращена в черновик. ${res.convert_warning}`, 'warning')
    } else {
      showSnack(`Заявка №${wishBlockedDelete.wishId} возвращена в черновик и убрана из плана`)
    }
    await refreshReqData(wishBlockedDelete.catId ?? undefined)
    await loadResiduals()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось вернуть заявку в черновик', 'error')
  } finally {
    wishBlockedDelete.reverting = false
  }
}

// ── Смена ФЭО-категории у wish-позиции ──────────────────────────────────────
const wishItemFeoEdit = reactive({
  show: false,
  saving: false,
  unallocatedLoading: false,
  purchaseId: null as number | null,
  itemId: null as number | null,
  itemName: '',
  catId: null as number | null,   // текущий catId для refreshReqData
  selectedCatId: null as number | null,
})

// Только листовые категории текущей субсидии
const leafFeoCategories = computed(() =>
  feoCategories.value.filter(c => !feoCategories.value.some(x => x.parent_id === c.id))
)

function openWishItemFeoEdit(node: FeoNode, item: FeoReqItem) {
  wishItemFeoEdit.catId = node.id
  wishItemFeoEdit.purchaseId = item.purchase_id
  wishItemFeoEdit.itemId = item.id
  wishItemFeoEdit.itemName = item.item_name
  wishItemFeoEdit.selectedCatId = null
  wishItemFeoEdit.show = true
}

async function saveWishItemFeo() {
  if (!wishItemFeoEdit.itemId || !wishItemFeoEdit.purchaseId || wishItemFeoEdit.selectedCatId == null) return
  wishItemFeoEdit.saving = true
  try {
    const _feoRes = await apiFetch<any>(`/purchases/${wishItemFeoEdit.purchaseId}/items/${wishItemFeoEdit.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify({ feo_category_id: wishItemFeoEdit.selectedCatId }),
    })
    wishItemFeoEdit.show = false
    await refreshReqData(wishItemFeoEdit.catId ?? undefined)
    // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» — см. saveReqItemEdit выше.
    if (_feoRes?.excess_warnings?.length) {
      showSnack(_feoRes.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack('Категория ФЭО обновлена')
    }
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось сменить категорию ФЭО', 'error')
  } finally {
    wishItemFeoEdit.saving = false
  }
}

async function pickWishItemUnallocated() {
  if (!selectedId.value) return
  wishItemFeoEdit.unallocatedLoading = true
  try {
    const cat = await apiFetch<{ id: number; name: string }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify({ subsidy_id: selectedId.value }),
    })
    // Добавить в feoCategories если ещё нет
    if (!feoCategories.value.find(c => c.id === cat.id)) {
      feoCategories.value = [...feoCategories.value, {
        id: cat.id, name: cat.name, parent_id: null, level: 0,
        subsidy_id: selectedId.value!, code: null, appendix: null,
        is_active: true, budget: null, planned_quantity: null, planned_amount: null, unit: null,
      }]
    }
    wishItemFeoEdit.selectedCatId = cat.id
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения «Не определена»', 'error')
  } finally {
    wishItemFeoEdit.unallocatedLoading = false
  }
}
// ─────────────────────────────────────────────────────────────────────────────

// openMapDialog/applyMapping/openAddPlannedItem/openConvertManualPlanToItem/
// openCreatePlannedFromActual/savePlannedItem/clearCategoryManualPlan —
// вынесены в usePlannedItems.ts (см. const plannedItems = usePlannedItems(...)
// ниже — те же имена остаются доступны и дереву ФЭО, и provideSubsidyDetail).

// Баг владельца (2026-08-17): «убрал огнетушитель — сумма не пересчиталась,
// превышение осталось». Причина — эта функция звала ТОЛЬКО refreshComparison
// (перечитывает состав панели «План vs факт» для одной категории), а числа узла/
// родителей в шапке дерева (feoPlannedDisplayFor/excessFor и т.д.) читаются из
// planTreeByCat — его обновляет ТОЛЬКО refreshReqData (см. movePlannedItemToCategory
// выше, который уже делает это правильно). Без refreshReqData() дерево показывало
// старые plan_manual/display/excess_amount до полной перезагрузки страницы.
const deletingPlannedItemId = ref<number | null>(null)
async function deletePlannedItem(item: FeoPlannedItem) {
  deletingPlannedItemId.value = item.id
  try {
    await apiFetch(`/feo-planned-items/${item.id}`, { method: 'DELETE' })
    await Promise.all([refreshComparison(item.feo_category_id), refreshReqData()])
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось удалить плановую позицию', 'error')
  } finally {
    deletingPlannedItemId.value = null
  }
}

// Все категории, лежащие НИЖЕ данного узла в дереве (сам узел не включён) — источник
// списка «Куда перенести» для плановой позиции направления (см. кнопку
// mdi-arrow-down-bold-box-outline в панели выше). flattenAll(node.children) уже
// используется в файле для того же обхода дерева (см. её объявление выше).
function descendantCategoriesFor(node: FeoNode): FeoNode[] {
  return flattenAll(node.children || [])
}

// Требование владельца, п.2/п.3 (2026-08-12): «Её можно перенести вниз, в подходящую
// категорию — суммы при этом не изменятся» — перенос плановой позиции, привязанной
// прямо к направлению, в одну из его конечных (или промежуточных) категорий.
// PUT /feo-planned-items/{id} — та же ПОЛНАЯ замена, что и у saveEditPlannedItem/
// reorderPlannedItem выше (неполный payload обнулил бы остальные поля позиции),
// меняется только feo_category_id. unit_price (правка 2026-09-03, найдено при
// ревизии всех PUT feo-planned-items без unit_price) обязан идти тем же явным
// образом, что и amount/quantity — иначе перенос молча обнулял цену за единицу.
const movingPlannedItemId = ref<number | null>(null)
async function movePlannedItemToCategory(item: FeoPlannedItem, targetCategoryId: number) {
  if (item.feo_category_id === targetCategoryId) return
  const sourceCategoryId = item.feo_category_id
  movingPlannedItemId.value = item.id
  try {
    await apiFetch(`/feo-planned-items/${item.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        feo_category_id: targetCategoryId,
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
        amount: item.amount,
        unit_price: item.unit_price ?? null,
        notes: item.notes,
        is_active: item.is_active,
        payment_mode: item.payment_mode ?? 'one_time',
        planned_date: item.planned_date ?? null,
        monthly_start_date: item.monthly_start_date ?? null,
        months_count: item.months_count ?? null,
        monthly_amount: item.monthly_amount ?? null,
        sort_order: item.sort_order ?? null,
        item_type: item.item_type ?? null,
      }),
    })
    // Затронуты ДВА узла (старый и новый) плюс их суммы по всей ветке вверх —
    // refreshComparison точечно обновляет составы обеих панелей, refreshReqData
    // перечитывает planTreeByCat (plan_manual/display), от которого зависит и
    // «Плановая сумма» в шапке дерева, и hasOwnPlannedAmountFor (раскрытие панели
    // направления) для обоих узлов.
    await Promise.all([refreshComparison(sourceCategoryId), refreshComparison(targetCategoryId)])
    await refreshReqData()
    showSnack('Позиция перенесена')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Ошибка переноса', 'error')
  } finally {
    movingPlannedItemId.value = null
  }
}

// Замечание владельца 2 (2026-08-12): «должна быть возможность менять плановые позиции
// местами внутри категории». Бэкенд готов — FeoPlannedItem.sort_order (nulls last),
// PUT /feo-planned-items/{id} принимает sort_order как ОБЫЧНОЕ поле полного payload'а
// (тот же роутер, что update_planned_item — НЕ отдельный /reorder-эндпоинт, как у
// категорий ФЭО, см. reorderFeoNode выше). PUT там — ПОЛНАЯ замена (см. её же
// докстринг/паттерн saveEditPlannedItem/clearCategoryManualPlan) — неполный payload
// обнулил бы amount/quantity/notes и т.д., поэтому отправляем ВСЕ поля позиции как есть.
// unit_price (правка 2026-09-03) — тем же payload'ом, иначе перестановка стрелками
// молча обнуляла цену за единицу существующей позиции (та же ловушка, что и у
// остальных PUT в этом файле — см. коммент у FeoPlannedItem.unit_price выше).
const reorderingPlannedItemId = ref<number | null>(null)
async function savePlannedItemSortOrder(item: FeoPlannedItem, newOrder: number) {
  await apiFetch(`/feo-planned-items/${item.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      feo_category_id: item.feo_category_id,
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      amount: item.amount,
      unit_price: item.unit_price ?? null,
      notes: item.notes,
      is_active: item.is_active,
      payment_mode: item.payment_mode ?? 'one_time',
      planned_date: item.planned_date ?? null,
      monthly_start_date: item.monthly_start_date ?? null,
      months_count: item.months_count ?? null,
      monthly_amount: item.monthly_amount ?? null,
      sort_order: newOrder,
      item_type: item.item_type ?? null,
    }),
  })
}

async function reorderPlannedItem(node: FeoNode, pIdx: number, direction: 'up' | 'down') {
  const rows = displayPlannedRowsFor(node)
  const a = rows[pIdx]
  const targetIdx = direction === 'up' ? pIdx - 1 : pIdx + 1
  if (!a || a.isManual || targetIdx < 0 || targetIdx >= rows.length) return
  const b = rows[targetIdx]
  if (!b || b.isManual) return
  reorderingPlannedItemId.value = a.id
  try {
    // sort_order пуст у части/всех (старые данные, до этой правки) — при первом
    // перемещении проставляем базовую нумерацию по текущему видимому порядку (1,2,3…),
    // чтобы дальше поведение было предсказуемым (требование владельца).
    const needsBaseline = rows.some(p => p.sort_order == null)
    const orders = needsBaseline ? rows.map((_, i) => i + 1) : rows.map(p => Number(p.sort_order))
    if (needsBaseline) {
      for (let i = 0; i < rows.length; i++) {
        if (i === pIdx || i === targetIdx) continue
        if (Number(rows[i].sort_order) === orders[i]) continue
        await savePlannedItemSortOrder(rows[i], orders[i])
      }
    }
    await savePlannedItemSortOrder(a, orders[targetIdx])
    await savePlannedItemSortOrder(b, orders[pIdx])
    await refreshComparison(node.id)
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось изменить порядок плановых позиций', 'error')
  } finally {
    reorderingPlannedItemId.value = null
  }
}

// ── Diff helpers ──────────────────────────────────────────────────────────
// Формула владельца (2026-08-05): «Остаток считается на основании "плановая сумма" минус
// заказано, и если поставлено, то "плановая сумма" − "поставлено"». Применяется ко всем типам
// строк панели (не только к плановым позициям Ур.5): если среди актуалов есть хотя бы одна
// поставленная/оплаченная — вычитаем сумму поставленного, иначе — сумму заказанного.
// fact_amount берём из API, если он отдан; иначе (напр. для «одноимённых из заявок», у которых
// нет fact_amount) — падаем на total_price позиции.
// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5): «заказано»-уровень (комитированный,
// но ещё не подтверждённый актом факт) расширен с одного статуса 'ordered' до всей тройки
// work_in_progress/contracted/ordered (см. FACT_PRICED_STATUSES в backend/app/services/feo_plan.py) —
// иначе позиция в статусе «Ведётся работа»/«Договор» с уже известной ценой по итогам закупки
// (fact_amount) не давала вклада в factSum и «Разница» ошибочно показывала полный план вместо
// план-факт.
type DiffActual = { total_price?: number | string | null; fact_amount?: number | string | null; purchase_status?: string | null }
const DIFF_COMMITTED_STATUSES = ['work_in_progress', 'contracted', 'ordered']
function calcDiff(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): number {
  const amountOf = (a: DiffActual) => Number(a.fact_amount ?? a.total_price ?? 0)
  const delivered = actuals.filter(a => ['delivered', 'paid'].includes(a.purchase_status || ''))
  const committed = actuals.filter(a => DIFF_COMMITTED_STATUSES.includes(a.purchase_status || ''))
  const factSum = delivered.length
    ? delivered.reduce((s, a) => s + amountOf(a), 0)
    : committed.reduce((s, a) => s + amountOf(a), 0)
  return Number(plannedAmount || 0) - factSum
}
function getDiffStyle(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): string {
  const diff = calcDiff(plannedAmount, actuals)
  return diff >= 0 ? 'color:#166534;font-weight:600' : 'color:#DC2626;font-weight:600'
}

// ── Подстроки стадий (разворот позиции закупки на ФЭО/План/Закупка/Договор/Приёмка) ──
// Совпадение соседних стадий — норма (уточнили наименование, но купили ровно то же кол-во/цену),
// подсвечиваем ТОЛЬКО расхождение, чтобы не плодить визуальный шум там, где всё сошлось.
interface FeoStageRow {
  stage: FeoStage
  nameChanged: boolean
  qtyDeltaLabel: string | null
  qtyDeltaColor: string
  priceDeltaLabel: string | null
  priceDeltaColor: string
}
function stagesWithDiff(stages: FeoStage[] | undefined): FeoStageRow[] {
  const list = stages || []
  return list.map((stage, i) => {
    const prev = i > 0 ? list[i - 1] : null
    let nameChanged = false
    let qtyDeltaLabel: string | null = null
    let qtyDeltaColor = ''
    let priceDeltaLabel: string | null = null
    let priceDeltaColor = ''
    if (prev) {
      nameChanged = normName(stage.name) !== normName(prev.name)
      const qtyDelta = Math.round((Number(stage.quantity || 0) - Number(prev.quantity || 0)) * 10000) / 10000
      if (Math.abs(qtyDelta) >= 0.0001) {
        qtyDeltaColor = qtyDelta < 0 ? '#DC2626' : '#EA580C'
        qtyDeltaLabel = `${qtyDelta > 0 ? '+' : '−'}${Math.abs(qtyDelta)}${stage.unit ? ' ' + stage.unit : ''}`
      }
      const priceDelta = Number(stage.unit_price || 0) - Number(prev.unit_price || 0)
      if (Math.abs(priceDelta) >= 0.005) {
        priceDeltaColor = priceDelta < 0 ? '#DC2626' : '#EA580C'
        priceDeltaLabel = `${priceDelta > 0 ? '+' : '−'}${formatCurrencyRound(Math.abs(priceDelta))}`
      }
    }
    return { stage, nameChanged, qtyDeltaLabel, qtyDeltaColor, priceDeltaLabel, priceDeltaColor }
  })
}

// editPlannedDialog/editAmountIsComputed/recalcEditAmountFromUnitPrice/
// editPriceCaption/openEditPlannedItem/saveEditPlannedItem/CATEGORY_UNIT_OPTIONS/
// isNumericLikeUnit/editCategoryPlanDialog/isCategoryUnitSuspicious/
// editCategoryPlanSum/openEditCategoryPlan/saveEditCategoryPlan — вынесены в
// usePlannedItems.ts.

// Contractor override state (showOverrideDialog/overrideForm/...) — вынесено
// в SubsidyContractorOverrideDialog.vue целиком (видимость внутренняя, парент
// вызывает через ref.open()).
// Events (Мероприятия) state — вынесено в SubsidyEventsPanel.vue.
const userRoleRaw = localStorage.getItem('user_role') || ''
// 12-05: admin or account_owner can save a version
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))
// B5 (2026-09-01): право на запись в дерево категорий ФЭО (backend-гейт —
// feo_category.edit, см. backend/app/routers/feo_categories.py). Экспорт и
// просмотр остаются доступны без этого права — прячем только
// create/edit/delete/import/reorder/drag редактора дерева ниже.
const authStore = useAuthStore()
const canEditFeo = computed(() => authStore.hasAction('feo_category.edit'))
// SaaS-роли (как в WishesView.vue) — им доступен force-возврат заявки в черновик из диалога блокировки удаления
const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRoleRaw))
// Как в WishesView.vue — id текущего пользователя, чтобы определить «это назначенный
// согласующий превышения плана ФЭО или нет» (см. excessMyPendingStep/decidePlanExcess).
const currentUserId = Number(localStorage.getItem('user_id') || '0')

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// По умолчанию уведомление НЕ исчезает само (duration=0): результат действия
// пользователя должен быть прочитан, а не пропасть за 3-4 секунды.
const toast = useToast()

// form/editForm/contractors/editInitialContractor (диалог субсидии) и
// feoForm/feoEditForm/feoPlanPairError/feoAddPlanPairError/feoEditPlanPairError/
// feoEditManualPlanSet/feoEditPlanSourceSwitchWarning (диалог категории ФЭО) —
// вынесены в SubsidyEditDialog.vue / FeoCategoryDialog.vue соответственно.

// ── Computed ──────────────────────────────────────
// availableYears/CARD_ORDER_KEY/cardDrag*/subsidyOrder/onCardDrag*/onCardDrop/
// filteredSubsidies/useCardView/subsidyTableHeaders/getSubsidyExportColumns+Rows/
// totals — вынесены в useSubsidyList.ts (волна 5b, см. `const { selectedYear,
// filteredSubsidies, effectiveView, mobile } = useSubsidyList(...)` выше).

const selectedBudget = computed(() => {
  if (!selectedSubsidy.value) return 0
  // Живой расчёт по дереву ФЭО; ручное поле budget — только как fallback (решение 15.07)
  if (feoTree.value.length) return totalFeoEffective.value
  return selectedSubsidy.value.feo_budget_total || selectedSubsidy.value.budget || 0
})

// «Запланировано» панели ФЭО = плановая сумма дерева (ручные позиции ФЭО + из заявок в плане закупок),
// а не только закупки — план вносится и импортом/созданием позиций прямо в ФЭО
const selectedPlannedTotal = computed(() => {
  if (feoTree.value.length) {
    return feoTree.value.reduce((acc, r) => acc + feoPlannedTotalFor(r) + feoPlannedRequestsFor(r), 0)
  }
  return selectedSubsidy.value?.planned || 0
})

// ── FEO tree ──────────────────────────────────────
// ФИКС (замер на проде 2026-08-13, жалоба владельца: «Приобретение футболок…» смещено
// относительно «Призового фонда…», дети «Окружных»/«Финала» не на одной линии, хотя в БД
// у всех level=3 и один и тот же parent_id — данные ровные, врала отрисовка). Раньше
// глубина ребёнка бралась из node.depth родителя ПРЯМО В ЭТОМ ЖЕ ПРОХОДЕ по плоскому
// cats.forEach — если ребёнок в массиве (порядок = sort_order/id) шёл РАНЬШЕ своего
// родителя, у родителя на тот момент ещё не была проставлена его собственная глубина
// (он сам ещё не был привязан к своему родителю в этом же проходе), и ребёнок получал
// depth на 1 меньше правильного. Отсюда «часть строк ровные, часть съехала» — зависело
// от порядка в массиве, а не от structure. Теперь связи (children/hasChildren/roots)
// строятся отдельным первым проходом, а depth — вторым проходом, обходом уже готового
// дерева от корней, поэтому не зависит от порядка элементов в исходном списке.
const feoTree = computed<FeoNode[]>(() => {
  const cats = feoCategories.value
  const byId: Record<number, FeoNode> = {}
  cats.forEach(c => { byId[c.id] = { ...c, depth: 0, hasChildren: false, children: [] } })
  const roots: FeoNode[] = []
  cats.forEach(c => {
    const node = byId[c.id]
    if (c.parent_id && byId[c.parent_id]) {
      byId[c.parent_id].children.push(node)
      byId[c.parent_id].hasChildren = true
    } else {
      roots.push(node)
    }
  })
  // visited защищает от циклов в битых данных (узел, ссылающийся сам на себя или
  // образующий петлю через parent_id) — такой узел просто не будет посещён повторно,
  // обход не зависает.
  const visited = new Set<number>()
  const assignDepth = (node: FeoNode, depth: number) => {
    if (visited.has(node.id)) return
    visited.add(node.id)
    node.depth = depth
    node.children.forEach(child => assignDepth(child, depth + 1))
  }
  roots.forEach(r => assignDepth(r, 0))
  return roots
})

function flattenAll(nodes: FeoNode[]): FeoNode[] {
  return nodes.flatMap(n => [n, ...flattenAll(n.children)])
}

function isNodeVisible(node: FeoNode): boolean {
  if (feoSearch.value) return true  // при поиске все найденные видны
  if (!node.parent_id) return true
  const checkParent = (pid: number): boolean => {
    if (!expandedIds.value.includes(pid)) return false
    const p = feoCategories.value.find(c => c.id === pid)
    return !p?.parent_id || checkParent(p.parent_id)
  }
  return checkParent(node.parent_id)
}

const visibleFeoNodes = computed(() => {
  const q = feoSearch.value.toLowerCase()
  const all = flattenAll(feoTree.value)
  if (q) return all.filter(n => n.name.toLowerCase().includes(q) || (n.code ?? '').toLowerCase().includes(q))
  // Баг (2026-08-12): фильтр по видимости предков раньше стоял только на guard'е
  // ОСНОВНОЙ строки узла в шаблоне (v-if="isNodeVisible(node) && ..."). Остальные
  // блоки того же v-for (панель плановых позиций, служебки, папки закупок) такого
  // guard'а не имели — при сворачивании родительской категории её строка пропадала,
  // а эти блоки дочерних узлов оставались висеть на экране. Фильтруем здесь, в
  // источнике списка, чтобы ни один блок цикла не рендерился для скрытого узла —
  // isNodeVisible сама учитывает expandedIds (и остаётся true при активном поиске).
  return all.filter(isNodeVisible)
})

// Решение 14.07: итог по субсидии НЕ суммируется из дерева — сравнение всегда
// с ручным бюджетом субсидии (Subsidy.budget)
const totalFeoBudget = computed(() => {
  const b = selectedSubsidy.value?.budget
  return b != null && Number(b) > 0 ? Number(b) : null
})

// Расчётная справка: Σ effective по корням дерева
const totalFeoEffective = computed(() => feoTree.value.reduce((a, r) => a + feoEffectiveFor(r), 0))

// Расхождение итога: расчёт по дереву vs ручной бюджет субсидии
const totalFeoDiff = computed(() =>
  totalFeoBudget.value != null ? totalFeoEffective.value - totalFeoBudget.value : 0
)

const totalFeoPurchased = computed(() => feoTree.value.reduce((a, r) => a + feoPurchasedFor(r), 0))

// Итог по той же шкале, что и колонка «В плане-графике» в строках дерева (решение
// владельца 2026-08-18) — footer «ИТОГО» обязан считаться через feoInPlanScheduleFor,
// иначе строки показывают сумму по плану закупок, а ИТОГО — старую (только delivered/paid).
const totalFeoInPlanSchedule = computed(() => feoTree.value.reduce((a, r) => a + feoInPlanScheduleFor(r), 0))

// Animated KPI targets for the detail panel (9 cards) — вынесены в
// SubsidyKpiCards.vue вместе с шаблоном карточек (волна 5b); selectedBudget/
// selectedPlannedTotal остаются здесь (нужны формулам дерева ФЭО выше) и
// экспортированы через ctx (см. provideSubsidyDetail ниже).

// ── KPI drill-down ── activeKpi/onKpiCardClick/resetKpi/applyKpiExpansion/
// kpiNodeClass и все identification-computed'ы (kpiItemIds/kpiNodeIds/...) —
// вынесены в composables/subsidies/useKpiDrilldown.ts (волна 5b, SubsidyKpiCards.vue).
// `kpi` — тот же module-singleton экземпляр, что и в SubsidyKpiCards.vue (см.
// объявление `const kpi = useKpiDrilldown(...)` в самом низу этого файла рядом с
// provideSubsidyDetail — используется здесь ТОЛЬКО в функциях/watch, вызываемых
// из шаблона или реактивности, т.е. уже после того, как весь скрипт отработает
// и kpi будет присвоен; никакого obращения к kpi до его объявления не происходит).
//
// Три маленькие функции подсветки строк дерева остаются здесь — им нужны
// локальные типы FeoReqRow/FeoPurchaseFolder, которых нет (и не должно быть) в
// useKpiDrilldown.ts; они читают набор id оттуда напрямую (kpi.kpiItemIds), не
// дублируя его (Правило №6).
// Класс строки виртуальной позиции/заголовка группы (reqItemRowsFor)
function kpiReqRowClass(row: FeoReqRow): string {
  if (!kpi.activeKpi.value) return ''
  const hit = row.items.some(it => kpi.kpiItemIds.value.has(it.id))
  if (!hit) return 'feo-kpi-dim'
  return row.group ? 'feo-kpi-hl' : 'feo-kpi-path'
}

// Класс строки одиночной позиции закупки (msrc / панель источников / товар в папке-закупке).
// Принимает и FeoReqItem (id), и FeoActualItem (purchase_item_id — та же строка purchase_items,
// просто другой эндпоинт/интерфейс, см. комментарий у FeoActualItem) — обе используют один и тот
// же набор id, kpiItemIds. Добавлено для строк «План vs факт» внутри панели плановой позиции
// (регресс 2026-08-13: раньше у этих строк не было kpi-класса вовсе, см. правку у kpiPlannedOwnerCatIds).
function kpiItemRowClass(it: FeoReqItem | FeoActualItem): string {
  if (!kpi.activeKpi.value) return ''
  const id = 'id' in it ? it.id : it.purchase_item_id
  return kpi.kpiItemIds.value.has(id) ? 'feo-kpi-hl' : 'feo-kpi-dim'
}

// Класс строки папки-закупки (режим «по закупкам»)
function kpiFolderClass(f: FeoPurchaseFolder): string {
  if (!kpi.activeKpi.value) return ''
  return f.items.some(it => kpi.kpiItemIds.value.has(it.id)) ? 'feo-kpi-path' : 'feo-kpi-dim'
}

// Уникальные статусы товаров виртуальной группы, отсортированные по жизненному циклу закупки
function groupStatuses(g: FeoVirtualGroup): { status: string; count: number; label: string }[] {
  const counts = new Map<string, number>()
  for (const it of g.items) counts.set(it.purchase_status, (counts.get(it.purchase_status) || 0) + 1)
  return PURCHASE_STATUS_ORDER
    .filter(s => counts.has(s))
    .map(s => ({ status: s, count: counts.get(s)!, label: PURCHASE_STATUS_META[s]?.label ?? s }))
}

// Финансирование ФЭО: ТОЛЬКО ручное значение (решение 14.07 — без авто-суммирования из детей)
function feoBudgetFor(node: FeoNode): number {
  return node.budget != null ? Number(node.budget) : 0
}

// Расчётное значение узла: ручное ФЭО, если задано; иначе факт (поставлено/оплачено),
// если появился; иначе плановая сумма. Группа без ручного — Σ по детям.
function feoEffectiveFor(node: FeoNode): number {
  if (node.budget != null) return Number(node.budget)
  if (!node.hasChildren) {
    const fact = purchaseTotals.value[node.id] || 0
    return fact > 0 ? fact : feoPlannedTotalFor(node)
  }
  return node.children.reduce((acc, child) => acc + feoEffectiveFor(child), 0)
}

// Σ ручного ФЭО в поддеревьях прямых детей. Факт/план НЕ подставляются;
// budget 0 или NULL = «не задано» (в UI оба показываются как «Задать»)
function manualChildFeoSum(node: FeoNode): number {
  const walk = (n: FeoNode): number =>
    Number(n.budget) > 0 ? Number(n.budget) : n.children.reduce((a, c) => a + walk(c), 0)
  return node.children.reduce((a, c) => a + walk(c), 0)
}

function hasManualChildFeo(node: FeoNode): boolean {
  const walk = (n: FeoNode): boolean => Number(n.budget) > 0 || n.children.some(walk)
  return node.children.some(walk)
}

function isAutoNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.budget == null
}

/** Rollup-хелпер: возвращает qty/amount для узла с признаком «авто» (из потомков). */
function feoRollup(node: FeoNode): { qty: number | null; qtyAuto: boolean; amount: number | null; amountAuto: boolean } {
  const ownQty = node.feo_quantity != null ? Number(node.feo_quantity) : null
  const ownAmt = node.feo_amount != null ? Number(node.feo_amount) : null
  if (ownQty != null || ownAmt != null) {
    return { qty: ownQty, qtyAuto: false, amount: ownAmt, amountAuto: false }
  }
  if (!node.hasChildren) return { qty: null, qtyAuto: false, amount: null, amountAuto: false }
  // Суммируем по прямым и косвенным детям рекурсивно
  let sumQty = 0; let hasQty = false
  let sumAmt = 0; let hasAmt = false
  const walkChildren = (children: FeoNode[]) => {
    for (const c of children) {
      const r = feoRollup(c)
      if (r.qty != null) { sumQty += r.qty; hasQty = true }
      if (r.amount != null) { sumAmt += r.amount; hasAmt = true }
    }
  }
  walkChildren(node.children)
  return {
    qty: hasQty ? sumQty : null, qtyAuto: hasQty,
    amount: hasAmt ? sumAmt : null, amountAuto: hasAmt,
  }
}

// Фактически запланированные расходы:
// - листовая категория (нет детей) → берём закупки, привязанные напрямую к ней
// - родительская категория → ТОЛЬКО сумма детей (закупки напрямую на уровне 1/2 не считаются)
// ⚠️ Старая шкала «Остатка» (только delivered/paid) — решением владельца 2026-08-18 строка
// дерева ФЭО больше НЕ использует эту функцию (заменена на feoInPlanScheduleFor), но саму
// функцию не удаляем: проверено грепом, используется в других местах (напр. плашка факта).
function feoPurchasedFor(node: FeoNode): number {
  if (!node.hasChildren) {
    return purchaseTotals.value[node.id] || 0
  }
  return node.children.reduce((acc, child) => acc + feoPurchasedFor(child), 0)
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5): «Фактическая сумма» дерева ФЭО
// читает готовое число fact из GET /feo-categories/plan-tree (compute_feo_plan_tree — единая
// формула факта, уже питающая плашку «итог закупки дороже плана», см. excessFactFor()).
// Учитывает ContractItem/contract_price с «Ведётся работа» (не только delivered/paid, как
// feoPurchasedFor() выше — тот оставлен нетронутым для «Остатка» и прочих мест, не входящих
// в явное поручение). planTreeByCat уже содержит fact для каждого узла, включая роллап по
// родителям (бэкенд суммирует по дереву сам — фронт не пересчитывает).
function feoFactFor(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.fact || 0
}

// База остатка: от плановой суммы или от финансирования по ФЭО
const residualBase = ref<'plan' | 'feo'>('plan')

// Режим колонок «Плановая сумма»/«Плановое кол-во» — единый синхронный переключатель.
// Тип PlannedBase — в composables/subsidies/types.ts (общий с useKpiDrilldown.ts).
const plannedBase = ref<PlannedBase>(feoDisplayPrefs.plannedBase || 'all')
const plannedSumBase = plannedBase
const plannedQtyBase = plannedBase

watch(plannedBase, () => {
  if (kpi.activeKpi.value && plannedItemsLoaded.value) kpi.applyKpiExpansion()
})

// Сохранение настроек отображения дерева ФЭО (см. FEO_DISPLAY_PREFS_KEY/feoDisplayPrefs
// в начале файла) — единая точка на все семь настроек, deep:true нужен, т.к. expandedIds/
// expandedReqItems/expandedItemPanels/expandedPlannedItems/collapsedPlannedItems мутируются
// на месте (push/add/delete), а не переприсваиваются.
function saveFeoDisplayPrefs() {
  try {
    localStorage.setItem(FEO_DISPLAY_PREFS_KEY, JSON.stringify({
      plannedBase: plannedBase.value,
      feoItemsGroupBy: feoItemsGroupBy.value,
      expandedIds: expandedIds.value,
      expandedReqItems: [...expandedReqItems.value],
      expandedItemPanels: [...expandedItemPanels.value],
      expandedPlannedItems: [...expandedPlannedItems.value],
      collapsedPlannedItems: [...collapsedPlannedItems.value],
    } satisfies FeoDisplayPrefs))
  } catch {
    // localStorage недоступен (приватный режим и т.п.) — не критично, просто не персистим
  }
}
watch(
  [plannedBase, feoItemsGroupBy, expandedIds, expandedReqItems, expandedItemPanels, expandedPlannedItems, collapsedPlannedItems],
  saveFeoDisplayPrefs,
  { deep: true },
)

function feoResidualBaseFor(node: FeoNode): number {
  return residualBase.value === 'feo' ? feoEffectiveFor(node) : feoPlannedDisplayFor(node)
}

// Остаток = (Плановая сумма | Финансирование по ФЭО) − В плане-графике.
// Решение владельца 2026-08-18: раньше вычитался feoPurchasedFor (только delivered/paid),
// из-за чего «Остаток» жил на третьей шкале, отдельной от «В плане-графике»/заметки
// «в закупках» — сводим все три числа строки к одной шкале.
function feoResidualFor(node: FeoNode): number {
  return feoResidualBaseFor(node) - feoInPlanScheduleFor(node)
}

// Отображаемое финансирование по ФЭО: ручное значение, для групп без ручного — серый расчёт
function feoDisplayedFor(node: FeoNode): number {
  if (node.budget != null) return Number(node.budget)
  return node.hasChildren ? feoEffectiveFor(node) : 0
}

// Финансирование vs Плановая сумма (в текущем режиме): >0 — можно добавить (зелёная), <0 — надо убрать (красная)
function feoFinDiff(node: FeoNode): number {
  return feoDisplayedFor(node) - feoPlannedDisplayFor(node)
}

// Жалоба владельца 2026-08-17 (категория 3710, «Расходные материалы для проведения
// окружных полуфиналов…»): «можно добавить 208 156 ₽ до финансирования ФЭО» вводит в
// заблуждение — это ФЭО минус ПЛАН (560 000 − 351 844), но в закупках уже 432 162 ₽ (план
// уже превышен закупками), и реально до потолка ФЭО остаётся 560 000 − 432 162 = 127 838 ₽,
// почти вдвое меньше. Вторая строка появляется ТОЛЬКО когда «в закупках» уже больше плана
// (иначе она дублировала бы первую строку той же цифрой, см. feedback_no_duplicate_metrics_
// same_label в Lessons) — берёт consumed из ТОЙ ЖЕ заметки «план · в закупках · свободно»
// (feoResidualNoteFor/feoPlanConsumedNoteFor), что уже нарисована строкой ниже под этим же
// узлом — второй источник чисел не изобретаем.
function feoRemainingWithPurchasesNote(node: FeoNode): string | null {
  // Решение владельца 2026-08-18: при базе «от ФЭО» ровно это число (feoDisplayedFor − consumed)
  // уже стоит в колонке «ОСТАТОК» — не дублируем ту же величину второй строкой под «Плановой суммой».
  if (residualBase.value === 'feo') return null
  if (feoFinDiff(node) <= 0.005) return null
  const note = feoResidualNoteFor(node) || feoPlanConsumedNoteFor(node)
  if (!note || note.residual >= -0.005) return null
  const remaining = feoDisplayedFor(node) - note.consumed
  return `с учётом уже размещённых закупок (${formatCurrency(note.consumed)}) до потолка ФЭО реально остаётся ${formatCurrency(remaining)}`
}

// «Собственный» перерасход узла — ровно то же условие, по которому строка
// "надо убрать N" уже красится ниже в шаблоне (feoDisplayedFor(node) > 0 — лимит вообще задан).
// Без этой проверки feoFinDiff() ложно уходит в минус у любого листа без лимита ФЭО
// (feoDisplayedFor = 0, а плановая сумма положительная — это НЕ перерасход, лимита просто нет).
function feoIsOverBudget(node: FeoNode): boolean {
  return feoDisplayedFor(node) > 0 && feoFinDiff(node) < -0.005
}

// Согласование превышения плана над финансированием ФЭО (задача владельца
// 2026-08-05: «если где-то превысил план ФЭО, значит где-то надо снимать —
// действия заблокированы, пока план закупок не загонять обратно в размеры ФЭО,
// либо согласовать превышение цепочкой»). excess_amount/excess_pending/
// excess_approved приходят готовыми с бэкенда в planTreeByCat (см.
// app.services.feo_plan.compute_feo_plan_tree) — фронт ничего не пересчитывает.
function excessFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_amount || 0)
  if (amount <= 0.005) return null
  return { amount, pending: !!t?.excess_pending, approved: !!t?.excess_approved }
}

// «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено из отката
// e0db76a) — виновная закупка, из-за которой узел вышел за финансирование ФЭО. Приходит
// готовой с бэкенда (см. app.services.feo_plan.find_excess_culprit, GET /api/feo-categories/
// plan-tree) — сервер заполняет её ТОЛЬКО пока excess_amount не согласован, поэтому
// дополнительно проверять excessApprovalFor тут не нужно: approved-случай уже отдаёт
// culprit=null сам по себе.
function excessCulpritFor(node: FeoNode): ExcessCulprit | null {
  return planTreeByCat.value[node.id]?.excess_culprit ?? null
}

// Текст виновника — «закупка № РЕЕ-2026-00889 «Great Wall POER» добавила 4 000 000 ₽,
// после неё выбрано 12 000 000 ₽ при ФЭО 8 000 000 ₽», либо без номера закупки, если
// виновник — синтетическое «плановое значение категории» (ручной план листа без
// разбивки на плановые позиции, см. find_excess_culprit).
function excessCulpritText(node: FeoNode): string {
  const c = excessCulpritFor(node)
  if (!c) return ''
  const source = c.purchase_number != null
    ? `закупка № ${c.purchase_number}${c.item_name ? ` «${c.item_name}»` : ''}`
    : (c.item_name || 'плановое значение категории')
  const budget = node.budget != null ? formatCurrency(node.budget) : '—'
  return `из-за чего: ${source} — добавила ${formatCurrency(c.amount_at_crossing)}, после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
}

// Правка владельца (2026-08-12): виновник превышения (excess_culprit) уже виден
// плашкой над деревом, но НЕ на самой строке позиции в панели «план vs факт» —
// найти её среди десятков строк было неочевидно. Сопоставляем по purchase_id +
// item_name (у ExcessCulprit нет purchase_item_id — сервер отдаёт только эти два
// поля, см. find_excess_culprit); ничего не пересчитываем, только сверяем то,
// что уже пришло с бэкенда.
function isExcessCulpritActual(node: FeoNode, actual: FeoActualItem): boolean {
  const c = excessCulpritFor(node)
  if (!c || c.purchase_id == null) return false
  return c.purchase_id === actual.purchase_id && (c.item_name || '') === (actual.item_name || '')
}

function excessCulpritChipTooltip(node: FeoNode): string {
  const c = excessCulpritFor(node)
  if (!c) return ''
  const budget = node.budget != null ? formatCurrency(node.budget) : '—'
  return `Добавила ${formatCurrency(c.amount_at_crossing)} — после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.5): ВТОРОЙ, независимый
// вид превышения — «итог закупки/КП (факт) дороже плана», отличный от excessFor()
// («план дороже финансирования ФЭО»). Оба поля приходят готовыми в той же карте
// planTreeByCat (compute_feo_plan_tree — см. backend/app/services/feo_plan.py) и
// закрываются ОДНИМ и тем же механизмом согласования (POST /plan-excess {feo_category_id}
// сам решает, какое из двух превышений согласовывать — см. request_plan_excess_approval),
// поэтому кнопка и вся инфраструктура approvalFor/pendingNames/decidePlanExcess ниже
// переиспользуются без изменений.
function excessFactFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_fact_over_plan || 0)
  if (amount <= 0.005) return null
  return { amount, pending: !!t?.excess_fact_pending, approved: !!t?.excess_fact_approved }
}

// Замечание владельца п.2 (2026-08-12, сессия «план ≠ факт», продолжение): ТРЕТИЙ,
// независимый вид превышения — Σ всех активных плановых позиций категории больше
// вручную заданного плана (excess_plan_over_manual/manual_plan_entered/excess_plan_items
// приходят готовыми в planTreeByCat, см. app.services.feo_plan.compute_feo_plan_tree).
// Тот же механизм согласования (POST /plan-excess сам выбирает, какое из трёх
// превышений согласовывать по приоритету — см. requestPlanExcessApproval выше,
// backend app.routers.plan_excess.request_plan_excess_approval), поэтому вся
// инфраструктура excessApprovalFor/excessPendingNames/excessMyPendingStep/
// decidePlanExcess переиспользуется без изменений.
function excessPlanFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean; manualEntered: number; items: ExcessPlanItem[] } | null {
  const t = planTreeByCat.value[node.id]
  const amount = Number(t?.excess_plan_over_manual || 0)
  if (amount <= 0.005) return null
  return {
    amount,
    pending: !!t?.excess_plan_pending,
    approved: !!t?.excess_plan_approved,
    manualEntered: Number(t?.manual_plan_entered || 0),
    items: t?.excess_plan_items || [],
  }
}

// Клик по чипу «позиция-виновник» (план zany-fluttering-mountain.md, п.2): одна связанная
// закупка → сразу открыть её (тот же приём router.push, что и у excessCulpritFor/
// virtCart выше — ничего нового не изобретаем); несколько — открывается v-menu со
// списком прямо в шаблоне (см. .feo-excess-plan-item-chip), сюда доходит только
// однозначный случай.
function excessPlanItemPurchaseTitle(p: ExcessPlanItemPurchase): string {
  const num = p.registry_number || (p.purchase_number != null ? `№ ${p.purchase_number}` : `#${p.id}`)
  const status = p.status_label || p.status || '—'
  return `${num} · ${status} · ${formatCurrency(p.amount)}`
}

// Замечание владельца п.4: «если согласовали превышение — так и остаётся, надо чтобы
// висело предупреждение, что согласовали» — спокойная ПОСТОЯННАЯ пометка, читает
// excess_approval_amount/at/by_name (данные ПОСЛЕДНЕГО approved-запроса по категории,
// см. compute_feo_plan_tree) НЕЗАВИСИМО от того, есть ли активное превышение прямо
// сейчас (excessPlanFor может уже вернуть null, если план снова уложился в ручной,
// пометка о прошлом согласовании всё равно должна остаться видна).
function excessPlanApprovalPermanent(node: FeoNode): { amount: number; at: string; by: string; planBefore: number | null; planAfter: number | null } | null {
  const t = planTreeByCat.value[node.id]
  if (t?.excess_approval_amount == null) return null
  return {
    amount: Number(t.excess_approval_amount),
    at: t.excess_approval_at ? new Date(t.excess_approval_at).toLocaleDateString('ru-RU') : '',
    by: t.excess_approval_by_name || '—',
    // План zany-fluttering-mountain.md, п.3: снимок «план был X → стал Y» на момент
    // согласования (plan_excess_approvals.plan_before/plan_after) — может быть null у
    // старых запросов, созданных до миграции; тогда фронт просто не показывает стрелку.
    planBefore: t.excess_approval_plan_before != null ? Number(t.excess_approval_plan_before) : null,
    planAfter: t.excess_approval_plan_after != null ? Number(t.excess_approval_plan_after) : null,
  }
}

// Детали запроса согласования превышения по узлу — см. planExcessApprovals/loadPlanExcessApprovals.
function excessApprovalFor(node: FeoNode): PlanExcessApprovalDto | null {
  return planExcessApprovals.value[node.id] || null
}

// ФИО, у кого сейчас на согласовании: sequential — первый pending-шаг по order_num,
// parallel — все pending-шаги сразу (см. backend _notify_pending_plan_excess_approvers,
// та же логика различия sequential/parallel).
function excessPendingNames(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr || appr.status !== 'pending') return ''
  const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
  const pendingSteps = appr.mode === 'parallel'
    ? sorted.filter(s => s.status === 'pending')
    : sorted.filter(s => s.status === 'pending').slice(0, 1)
  return pendingSteps.map(s => s.full_name || s.role_name || `пользователь #${s.user_id}`).join(', ')
}

// Шаг, который может решить ИМЕННО текущий пользователь: назначенный согласующий
// текущего шага, либо любая SaaS-роль (см. backend decide_plan_excess_step: !_is_saas
// и role not in MANAGER_ROLES блокируют чужой шаг, иначе — можно).
function excessMyPendingStep(node: FeoNode): PlanExcessStep | null {
  const appr = excessApprovalFor(node)
  if (!appr || appr.status !== 'pending') return null
  const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
  if (appr.mode === 'parallel') {
    return sorted.find(s => s.status === 'pending' && (s.user_id === currentUserId || isSaas.value)) || null
  }
  const first = sorted.find(s => s.status === 'pending')
  if (first && (first.user_id === currentUserId || isSaas.value)) return first
  return null
}

// Кто согласовал (последний решённый шаг approved) — для бейджа «превышение согласовано».
function excessResolvedByName(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr) return ''
  const decided = [...appr.steps]
    .filter(s => s.status === 'approved' && s.decided_at)
    .sort((a, b) => new Date(b.decided_at!).getTime() - new Date(a.decided_at!).getTime())
  return decided[0]?.full_name || decided[0]?.role_name || '—'
}

function excessResolvedDate(node: FeoNode): string {
  const appr = excessApprovalFor(node)
  if (!appr?.resolved_at) return ''
  return new Date(appr.resolved_at).toLocaleDateString('ru-RU')
}

// Загрузка запросов согласования превышения плана ФЭО по субсидии — GET /api/plan-excess.
// Список уже отсортирован бэкендом по created_at desc, поэтому первое вхождение
// на категорию — последний (актуальный) запрос.
async function loadPlanExcessApprovals(subsidyId: number) {
  try {
    const rows = await apiFetch<PlanExcessApprovalDto[]>(`/plan-excess?subsidy_id=${subsidyId}`)
    const map: Record<number, PlanExcessApprovalDto> = {}
    for (const r of rows) {
      if (!(r.feo_category_id in map)) map[r.feo_category_id] = r
    }
    planExcessApprovals.value = map
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось загрузить согласования превышения плана', 'error')
  }
}

async function requestPlanExcessApproval(node: FeoNode) {
  excessRequestLoading.value = node.id
  try {
    const res = await apiFetch<PlanExcessApprovalDto>('/plan-excess', {
      method: 'POST',
      body: JSON.stringify({ feo_category_id: node.id }),
    })
    if (res.self_approval && res.warning) {
      showSnack(res.warning, 'warning')
    } else if (res.warning) {
      showSnack(`Запрос отправлен. ${res.warning}`, 'warning')
    } else {
      showSnack('Запрос на согласование превышения плана отправлен', 'success')
    }
    if (selectedId.value) await refreshReqData()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось запросить согласование превышения', 'error')
  } finally {
    excessRequestLoading.value = null
  }
}

function openExcessRejectDialog(node: FeoNode) {
  excessRejectDialog.value = { show: true, node, comment: '' }
}

async function decidePlanExcess(node: FeoNode, decision: 'approved' | 'rejected', comment?: string) {
  const appr = excessApprovalFor(node)
  const step = excessMyPendingStep(node)
  if (!appr || !step) {
    showSnack('Шаг согласования не найден — обновите страницу', 'error')
    return
  }
  excessDecideLoading.value = node.id
  try {
    await apiFetch(`/plan-excess/${appr.id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, step_id: step.id, comment: comment || null }),
    })
    showSnack(decision === 'approved' ? 'Превышение согласовано' : 'Превышение отклонено', decision === 'approved' ? 'success' : 'warning')
    if (selectedId.value) await refreshReqData()
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
  } finally {
    excessDecideLoading.value = null
  }
}

async function submitExcessReject() {
  const node = excessRejectDialog.value.node
  if (!node) return
  if (!excessRejectDialog.value.comment.trim()) {
    showSnack('Укажите причину отклонения', 'error')
    return
  }
  await decidePlanExcess(node, 'rejected', excessRejectDialog.value.comment.trim())
  excessRejectDialog.value.show = false
}

// Для каждого узла — потомки (любой глубины), у которых feoIsOverBudget === true.
// Мемоизировано Map'ом за один обход дерева, а не пересчитывается в шаблоне на каждый узел —
// дерево ФЭО большое, feoNodeClass/рендер строки вызываются в цикле по всем видимым узлам.
interface FeoOverspentInfo { names: string[]; count: number }
const feoOverspentDescendantMap = computed<Map<number, FeoOverspentInfo>>(() => {
  const map = new Map<number, FeoOverspentInfo>()
  function walk(node: FeoNode): string[] {
    let names: string[] = []
    for (const child of node.children) {
      if (feoIsOverBudget(child)) names.push(child.name)
      names = names.concat(walk(child))
    }
    map.set(node.id, { names, count: names.length })
    return names
  }
  for (const root of feoTree.value) walk(root)
  return map
})

// Есть ли хотя бы один потомок (на любой глубине), превышающий СВОЙ лимит ФЭО
function feoHasOverspentDescendant(node: FeoNode): boolean {
  return (feoOverspentDescendantMap.value.get(node.id)?.count ?? 0) > 0
}

// Текст комментария у родителя: если превышающая подкатегория одна — называем её,
// иначе общая формулировка (по требованию пользователя)
function feoOverspentDescendantText(node: FeoNode): string {
  const info = feoOverspentDescendantMap.value.get(node.id)
  if (!info || info.count === 0) return ''
  if (info.count === 1) return `подкатегория «${info.names[0]}» превышает лимит`
  return 'одна из подкатегорий превышает лимит'
}

// Тултип: до трёх имён превышающих подкатегорий + «и ещё N», чтобы было видно, куда идти
function feoOverspentDescendantTitle(node: FeoNode): string {
  const info = feoOverspentDescendantMap.value.get(node.id)
  if (!info || info.count === 0) return ''
  const shown = info.names.slice(0, 3)
  const suffix = info.count > 3 ? ` и ещё ${info.count - 3}` : ''
  const verb = info.count === 1 ? 'Превышает' : 'Превышают'
  return `${verb} лимит ФЭО: ${shown.join(', ')}${suffix}`
}

// Ручное ФЭО дочерних vs собственная ручная сумма узла (без подмены фактом/планом)
function feoChildrenBudgetDiff(node: FeoNode): number {
  if (!node.hasChildren || node.budget == null || node.budget <= 0) return 0
  if (!hasManualChildFeo(node)) return 0
  return manualChildFeoSum(node) - node.budget
}

// Факт по требованию владельца (2026-08-05): появляется с «Заказано» (по договору, актом ещё
// не подтверждено — см. fact_confirmed), уточняется закрывающими документами при «Поставлено»/
// «Оплачено». До «Заказано» это ещё ПЛАН, а не факт.
// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 3/5): порог опущен с «Заказано» до
// «Ведётся работа» (см. FACT_PRICED_STATUSES в backend/app/services/feo_plan.py) — факт (цена
// по итогам КП/торгов) должен попадать в панель «план vs факт» ещё ДО подписания договора,
// иначе позиция в статусе «Ведётся работа»/«Договор» с уже известным fact_amount ошибочно
// показывала текущую (замороженную ТЗ) сумму вместо факта — панель и дерево ФЭО расходились.
// isFactActual/FACT_STATUSES остаются нужны для ИТОГО/факт-колонок и для guard'а «Разница»
// (нужен именно подтверждённый факт); для вложения строк ПОД плановой позицией с 2026-08-11
// используется расширенный allActualFor/factForPlanned — см. ниже.
const FACT_STATUSES = ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
function isFactActual(a: { purchase_status?: string | null }): boolean {
  return FACT_STATUSES.includes(a.purchase_status || '')
}

// Позиция «из заявки» в плановой стадии (до договора): источник истины — заявка,
// поэтому название/кол-во/цену тут править нельзя (бэкенд отдаёт 409). Прячем карандаш/удаление.
const WISH_PLAN_LOCKED_STATUSES = ['wishes', 'plan_schedule', 'work_in_progress']
function isWishLocked(it: { wish_id?: number | null; purchase_status?: string | null }): boolean {
  return !!it.wish_id && WISH_PLAN_LOCKED_STATUSES.includes(it.purchase_status || '')
}

function actualFactFor(catId: number) {
  return (comparisonData.value[catId]?.actual || []).filter(a => isFactActual(a))
}

// Все позиции закупок категории, ЛЮБОЙ стадии (включая «План закупок» — по нашей модели это
// уже начало жизни позиции, не отдельная параллельная сущность). Правка владельца 2026-08-11
// («пикап» Great Wall POER на стадии «План закупок» рисовался ОТДЕЛЬНОЙ строкой рядом с планом
// вместо вложения под неё, ИТОГО складывал план с закупкой) — единственный источник вложенных
// строк под плановой позицией теперь этот, а не actualFactFor (тот остаётся только для
// ИТОГО/факт-колонок, где нужен именно подтверждённый факт, см. comparisonFactTotal).
function allActualFor(catId: number) {
  return comparisonData.value[catId]?.actual || []
}

// Фолбэк владельца (2026-08-12): «плановая позиция была создана из заявки — названия сейчас
// совпадают, значит должны разворачиваться в план БЕЗ факта». У части плановых позиций
// (проверено в БД, категория 3710) ни одна позиция закупки не получила feo_planned_item_id —
// привязка не проставлена (ручной ввод/миграция пропустили её), хотя закупка с тем же
// названием реально существует в той же категории. Считаем ОДИН РАЗ на всю категорию (не в
// factForPlanned/unplannedActualFor по отдельности!) — единый источник для обеих функций
// ниже, иначе одна и та же позиция закупки задвоится: попадёт и под план (по имени), и в
// «Не привязаны к плану» (по !feo_planned_item_id). Жадный «первое совпадение выигрывает»
// (usedIds) — на случай двух плановых позиций с одинаковым именем в одной категории, чтобы
// одна непривязанная позиция не досталась сразу обеим. Плановые позиции, у которых УЖЕ есть
// хоть одна привязанная (bound) позиция, в фолбэке не участвуют — там factForPlanned и так
// находит факт напрямую.
const fallbackAbsorbedByCategory = computed((): Record<number, Map<number, number>> => {
  const result: Record<number, Map<number, number>> = {}
  for (const key of Object.keys(comparisonData.value)) {
    const catId = Number(key)
    const data = comparisonData.value[catId]
    const map = new Map<number, number>()
    const usedIds = new Set<number>()
    for (const planned of data.planned || []) {
      const hasBound = (data.actual || []).some(a => a.feo_planned_item_id === planned.id)
      if (hasBound) continue
      const targetName = normName(planned.name)
      if (!targetName) continue
      for (const a of data.actual || []) {
        if (a.feo_planned_item_id) continue
        if (usedIds.has(a.purchase_item_id)) continue
        if (normName(a.item_name) !== targetName) continue
        map.set(a.purchase_item_id, planned.id)
        usedIds.add(a.purchase_item_id)
      }
    }
    result[catId] = map
  }
  return result
})

// plannedId < 0 — синтетическая «ручная плановая позиция» (см. displayPlannedRowsFor):
// когда у категории нет ни одной реальной FeoPlannedItem, а план задан прямо на листе
// (node.planned_quantity/planned_amount), лист получает ОДНУ псевдо-строку с id = -node.id,
// и её «факт» — это ВСЕ позиции категории без привязки к плановой (им и привязываться не к
// чему — детального деления в ФЭО не было). ШАГ 1 плана дедупликации дерева ФЭО (2026-08-07):
// раньше эти же позиции рисовались ВТОРОЙ раз через matchedReqFor (сопоставление по ИМЕНИ) —
// убрано целиком, единственный источник теперь этот. С 2026-08-11 — allActualFor (любая
// стадия), а не actualFactFor: закупка на стадии «План закупок» тоже обязана лечь ПОД свою
// плановую строку, а не рисоваться рядом отдельным блоком (см. снесённый actualPlanStageFor).
// С 2026-08-12 (plannedId >= 0) — если привязанных позиций нет вовсе, фолбэк на
// fallbackAbsorbedByCategory (см. выше, комментарий там).
function factForPlanned(catId: number, plannedId: number) {
  if (plannedId < 0) return allActualFor(catId).filter(a => !a.feo_planned_item_id)
  const bound = allActualFor(catId).filter(a => a.feo_planned_item_id === plannedId)
  if (bound.length) return bound
  const absorbed = fallbackAbsorbedByCategory.value[catId]
  if (!absorbed) return bound
  return allActualFor(catId).filter(a => absorbed.get(a.purchase_item_id) === plannedId)
}

function factForPlannedTotal(catId: number, plannedId: number): number {
  // fact_amount — реальный факт (ContractItem/contract_price); total_price (ТЗ) —
  // фолбэк только пока факта ещё нет (см. calcDiff::amountOf — тот же приоритет).
  return factForPlanned(catId, plannedId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
}

// Расшифровка «больше плана на X» у заметки «план … · в закупках … · больше плана на …»
// (жалоба владельца 2026-08-13: «в закупках 118 365,60 — больше плана на 5 121,60, откуда,
// если в позициях плана этого нет?»; продолжение — 2026-08-17, категория 3710: «где это
// превышение 80 318? где оно?»). Это заметка feoResidualNoteFor ниже по шаблону (строка
// «план X · в закупках Y · больше плана на Z»), НЕ плашка у «Фактической суммы» (та про
// контрактный факт, отдельная и обычно ещё пустая, пока закупка не дошла до договора/
// поставки — «в закупках» здесь про заявки/ТЗ).
//
// Превышение складывается из ДВУХ независимых источников — расследование 2026-08-17
// показало, что раньше учитывался только первый, из-за чего у категории 3710 расшифровка
// молчала (пусто), хотя число «больше плана на 80 318» было честным:
//  1) перерасход ВНУТРИ существующей плановой позиции — сумма закупок, привязанных к ней
//     (factForPlanned), больше её planned.amount. Арифметика — та же, что у
//     planBreakdownText (factForPlannedTotal − planned.amount), берём только положительные.
//  2) позиции закупок БЕЗ действующей плановой позиции — unplannedActualFor(node) (и вовсе
//     непривязанные, и с мёртвой привязкой на удалённую плановую позицию, см. её правку
//     выше) — такая позиция ничей план не убавляет, целиком уходит в превышение категории
//     (пример владельца: огнетушитель 54 318 ₽ + каска 26 000 ₽ = ровно 80 318 ₽, обе с
//     feo_planned_item_id на уже удалённые плановые позиции 809/1409).
// Каждый пункт несёт список закупок-источников (обычно один, но плановая позиция может
// быть покрыта несколькими закупками сразу) — шаблон рисует по ним кликабельные ссылки/меню
// (тот же приём, что excessPlanFor().items выше по файлу — v-menu при >1 закупке).
//
// ⚠️ comparisonData[node.id] грузится ТОЛЬКО когда панель плановых позиций категории
// раскрыта, либо когда явно нажали «Показать, из-за чего» (см. ensureComparison в шаблоне) —
// читаем здесь готовое значение ref'а, ничего сами не запрашиваем.
interface ExcessReasonPurchase { id: number; label: string; amount: number; stopped: boolean }
interface ExcessReasonItem { key: string; name: string; amount: number; purchases: ExcessReasonPurchase[] }
function purchaseLabelFor(a: { registry_number?: string | null; purchase_number?: number | null; purchase_id: number }): string {
  return a.registry_number || (a.purchase_number != null ? `№ ${a.purchase_number}` : `#${a.purchase_id}`)
}
function factExcessReasonItems(node: FeoNode): ExcessReasonItem[] {
  const catId = node.id
  const data = comparisonData.value[catId]
  if (!data) return []
  const items: ExcessReasonItem[] = []
  // Источник 1 — перерасход внутри существующих плановых позиций.
  for (const p of data.planned || []) {
    const amount = factForPlannedTotal(catId, p.id) - Number(p.amount ?? 0)
    if (amount <= 0.005) continue
    const facts = factForPlanned(catId, p.id)
    items.push({
      key: `p-${p.id}`,
      name: p.name,
      amount,
      purchases: facts.map(a => ({
        id: a.purchase_id,
        label: purchaseLabelFor(a),
        amount: Number(a.fact_amount ?? a.total_price ?? 0),
        stopped: !!a.stopped_at,
      })),
    })
  }
  // Источник 2 — закупки без действующей плановой позиции (непривязанные ИЛИ с мёртвой
  // привязкой на удалённую плановую позицию) — unplannedActualFor уже ловит оба случая.
  for (const a of unplannedActualFor(node)) {
    const amount = Number(a.fact_amount ?? a.total_price ?? 0)
    if (amount <= 0.005) continue
    items.push({
      key: `a-${a.purchase_item_id}`,
      name: a.item_name,
      amount,
      purchases: [{ id: a.purchase_id, label: purchaseLabelFor(a), amount, stopped: !!a.stopped_at }],
    })
  }
  return items.sort((a, b) => b.amount - a.amount)
}
// Расшифровка обязана сходиться с самим числом превышения (требование владельца
// 2026-08-17: «если не сходится — показывай остаток строкой, а не молчи»). Расхождение
// возможно: источник 1 берёт только плановые позиции, которые САМИ перерасходованы —
// недобор по другим плановым позициям категории эту сумму не компенсирует здесь, хотя
// компенсирует итоговый residual категории (там план минус ВЕСЬ consumed целиком).
function factExcessReasonRemainder(node: FeoNode): number {
  const note = feoResidualNoteFor(node)
  if (!note) return 0
  const total = -note.residual
  const shown = factExcessReasonItems(node).reduce((s, it) => s + it.amount, 0)
  return total - shown
}

// ── Левая группа колонок панели «план vs факт» ──
// leftGroupInfo/FeoLeftGroupInfo — см. composables/subsidies/feoCategoryUtils.ts
// (функция чистая, используется и деревом ФЭО здесь, и PlannedItemAddDialog.vue —
// один источник, не две копии, Правило №6).

// ── Шапка вложенной таблицы закупок плановой позиции — ровно одна стадия ──────
// Требование владельца (2026-08-09), дословно: «если ещё на стадии закупки, то просто
// "как выставили в закупку", не надо туда дополнять "как в договоре"; когда переместится
// на стадию договора, то тогда эта надпись меняется на "как в договоре", не нужно
// дополнять непонятными сущностями». Все закупки этой плановой позиции на одной стадии →
// шапка называет ровно её; стадии разные → нейтральное «Позиция закупки», стадия —
// на каждой строке (чип уже есть).
//
// Правка владельца (2026-08-12, разбор задвоения плановой позиции без факта): раньше
// шапка различала только 2 состояния (leftGroupInfo.isContract), из-за чего заявка
// (wishes/plan_schedule) и «Ведётся работа» получали одну и ту же надпись «Как выставили
// в закупку». Дословно от владельца: «плановая позиция была создана из заявки, названия
// сейчас совпадают [→ "Как называется в заявке"]. Перейдёт в работу — статус сменится
// "как называется в закупке" [work_in_progress], далее в договоре [contracted/ordered/
// delivered/paid → "Как в договоре"]». PURCHASE_STATUS_META — единственный источник
// статусов (constants/purchaseStatus.ts), см. импорт в начале файла.
function stageHeaderLabelFor(status: string | null | undefined): string {
  if (status === 'wishes' || status === 'plan_schedule') return 'Как называется в заявке'
  if (status === 'work_in_progress') return 'Как называется в закупке'
  if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Как в договоре'
  return 'Позиция закупки'
}
// Краткий вариант stageHeaderLabelFor для чипа НА СТРОКЕ (не в шапке колонки).
// Баг владельца (2026-08-13): у «Бинт марлевый Навтекс» в статусе «План закупок»
// чип писал «как выставили», хотя ничего ещё не выставлено в закупку — это
// название из заявки. Чип раньше жил на своей отдельной двоичной логике
// (leftGroupInfo.isContract ? 'как в договоре' : 'как выставили'), не совпадающей
// со стадийной функцией шапки. Переиспользуем stageHeaderLabelFor, никакой новой
// логики стадий не изобретаем.
function stageChipLabelFor(status: string | null | undefined): string {
  const full = stageHeaderLabelFor(status)
  if (full === 'Как называется в заявке') return 'как в заявке'
  if (full === 'Как называется в закупке') return 'как в закупке'
  if (full === 'Как в договоре') return 'как в договоре'
  return 'как выставили'
}
// Хвост той же правки (2026-08-13): :title и :color рядом с чипом остались на старой
// двоичной логике (leftGroupInfo.isContract) — у позиции «Ведётся работа» чип уже писал
// «как в закупке» (stageChipLabelFor выше), а подсказка при наведении всё ещё говорила
// про заявку/ТЗ. Считаем обе от той же стадии (actual.purchase_status), что и текст чипа.
function stageChipTitleFor(status: string | null | undefined): string {
  if (status === 'wishes' || status === 'plan_schedule') return 'Наименование, количество и цена — как их завели в заявке; в закупку ещё не выставлено'
  if (status === 'work_in_progress') return 'Наименование, количество и цена — как выставлено в закупке'
  if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Наименование, количество и цена — из договора с подрядчиком'
  return 'Как товар завели в заявке/ТЗ — до заключения договора'
}
function stageChipColorFor(status: string | null | undefined): string {
  return (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') ? 'indigo' : 'blue-grey'
}
function factStageHeaderFor(catId: number, plannedId: number): string {
  const facts = factForPlanned(catId, plannedId)
  if (!facts.length) return 'Позиция закупки'
  const labels = new Set(facts.map(a => stageHeaderLabelFor(a.purchase_status)))
  if (labels.size > 1) return 'Позиция закупки'
  return [...labels][0]
}

// ── Разбор плана на строке плановой позиции («сколько уже разобрано») ─────────
// Требование владельца (2026-08-09): под одной плановой позицией может висеть НЕСКОЛЬКО
// закупок («покупаю по одной машине в каждой закупке») — на строке плана нужно видеть,
// сколько уже взято и сколько осталось, И в штуках, И в деньгах. Деньги считаются той же
// формулой, что и factForPlannedTotal (fact_amount, фолбэк total_price) — второй источник
// приоритета не изобретаем. Штуки — Σ actual.quantity (реальное количество позиции закупки,
// та же колонка «Кол-во (факт)» вложенной таблицы) против planned.quantity; если у плана
// количество не задано — про штуки не пишем вообще (у плана тогда нет множителя количества).
// Правка владельца (2026-08-11): facts (factForPlanned) теперь включает ЛЮБУЮ стадию закупки,
// в т.ч. «План закупок» — слово «закуплено» для неё враньё (ничего ещё не куплено, только
// выставлено в закупку). Нейтральное «в закупках» верно для всех стадий одинаково.
function planBreakdownText(catId: number, planned: FeoPlannedItem & { isManual?: boolean }): string {
  const facts = factForPlanned(catId, planned.id)
  const amountTotal = Number(planned.amount ?? 0)
  const amountTaken = factForPlannedTotal(catId, planned.id)
  const amountRemaining = amountTotal - amountTaken
  const unit = planned.unit || 'шт'
  if (planned.quantity != null) {
    const qtyTotal = Math.round(Number(planned.quantity) * 10000) / 10000
    const qtyTaken = Math.round(facts.reduce((s, a) => s + Number(a.quantity ?? 0), 0) * 10000) / 10000
    const qtyRemaining = Math.round((qtyTotal - qtyTaken) * 10000) / 10000
    return `в закупках ${qtyTaken} из ${qtyTotal} ${unit} · на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${qtyRemaining} ${unit} и ${formatCurrency(amountRemaining)}`
  }
  return `в закупках на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${formatCurrency(amountRemaining)}`
}

// Строки «Плановые позиции» листа для панели «план vs факт»: реальные FeoPlannedItem
// категории, ИЛИ — если их нет, а план задан прямо на листе — одна псевдо-строка
// «ручной план ФЭО» (id = -node.id, отрицательный, никогда не совпадает с реальным id).
// Переиспользует вёрстку обычной плановой строки (см. таблицу ниже) вместо отдельного блока.
//
// ⚠️ Семантика поля `amount` РАЗНАЯ у двух источников и это специально не унифицировано
// в БД (баг с проды 2026-08-07): `FeoPlannedItem.amount` (реальная плановая позиция,
// приходит от бэкенда как есть) — это уже ИТОГОВАЯ СУММА строки. А `FeoCategory.planned_amount`
// (ручной план на листе, поля «Плановое кол-во»/«Финансирование по ФЭО» в дереве) — это ЦЕНА
// ЗА ЕДИНИЦУ (см. feoPlannedTotalFor/feoAmtFor выше, которые считают qty × planned_amount).
// Вся остальная вёрстка панели (строки 1057/1060/1069-1070 ниже, calcDiff, comparisonPlanTotal)
// трактует `planned.amount` как СУММУ — поэтому здесь для синтетической строки amount ОБЯЗАН
// быть посчитан как planned_quantity × planned_amount, а не взят «как есть» из planned_amount
// (иначе «Сумма (план)» делится на количество ещё раз при выводе цены за единицу).
function displayPlannedRowsFor(node: FeoNode): (FeoPlannedItem & { isManual?: boolean })[] {
  const real = comparisonData.value[node.id]?.planned || []
  if (real.length) return real
  if (node.planned_quantity == null && node.planned_amount == null) return []
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
  // И количество, И цена ОБЯЗАНЫ быть заданы и положительны, чтобы сумму вообще можно
  // было посчитать — иначе null (неизвестно), а не «додумывать» недостающий множитель
  // за 1. Проверено на приёмке 2026-08-07: значение «количество не задано → считать 1»
  // ЗАВОДИТ РАСХОЖДЕНИЕ с «Плановой суммой» шапки дерева (feoPlannedTotalFor на фронте
  // и plan_manual в backend/app/services/feo_plan.py::_visit — оба явно требуют
  // `qty > 0 and amt > 0`, иначе план листа = 0/«не задано»). Панель обязана
  // ЗЕРКАЛИТЬ эту же формулу, а не изобретать свою — их расхождение и есть баг.
  const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
  return [{
    id: -node.id,
    feo_category_id: node.id,
    name: node.name,
    quantity: qty,
    unit: node.unit || null,
    amount,
    // Тот же qty/unitPrice, что уже проверены выше для amount — здесь это НЕ
    // деление задним числом (как было раньше в колонке «Плановая цена за
    // единицу», см. правку 2026-09-03), а честная цена, из которой amount и
    // посчитан. amount == null (условие не выполнено) → и unit_price null.
    unit_price: amount != null ? unitPrice : null,
    notes: null,
    is_active: true,
    isManual: true,
  }]
}

// «Не привязаны к плану — требуется действие»: позиции категории (ЛЮБОЙ стадии закупки —
// правка 2026-08-11, было actualFactFor/FACT_STATUSES, см. allActualFor) без
// feo_planned_item_id. НЕ показываются только в одном случае — когда те же самые позиции
// уже отрисованы как факт синтетической строки «ручной план ФЭО» (displayPlannedRowsFor
// возвращает псевдо-строку id=-node.id именно тогда, когда реальных плановых позиций нет,
// а план на листе задан вручную — см. factForPlanned(catId, -node.id) выше). Если у листа
// НЕТ ни реальных плановых позиций, ни ручного плана — абсорбировать эти позиции некуда,
// они обязаны показаться здесь как «требует действия» (иначе позиции пропадают из дерева
// молча — так и было до фикса: 15+ позиций категории без плана исчезали совсем).
// С 2026-08-12 — дополнительно исключены позиции, поглощённые фолбэком по имени
// (fallbackAbsorbedByCategory, см. factForPlanned) — те уже показаны ПОД своей плановой
// строкой, повторно рисовать их тут значило бы задвоить одну и ту же закупку на экране.
//
// БАГ (жалоба владельца 2026-08-17, категория 3710 «Расходные материалы для проведения
// окружных полуфиналов…»): «где превышение 80 318? где его увидеть?» — две позиции закупок
// (огнетушитель 54 318 ₽, каска 26 000 ₽) имели feo_planned_item_id, указывающий на
// плановые позиции, которые к этому моменту УДАЛЕНЫ (id 809/1409 больше нет среди
// comparisonData[catId].planned). Из-за этого они проваливались МИМО обеих веток: у
// factForPlanned нет плановой строки с таким id, чтобы их подставить, а этот фильтр
// (`!a.feo_planned_item_id`) их тоже отбрасывал — feo_planned_item_id формально заполнен,
// просто ссылка мертва. Позиции исчезали с экрана совсем — не факт, не план, ничего.
// Теперь ловим ОБА случая: (1) привязки вовсе нет — прежнее поведение; (2) привязка ЕСТЬ,
// но указанной плановой позиции больше не существует в текущем списке категории — «мёртвая»
// привязка. Мёртвая привязка показывается ВСЕГДА (даже при hasManualPseudoRow — абсорбировать
// в синтетическую строку её всё равно нельзя, там участвуют только позиции без
// feo_planned_item_id вовсе, см. factForPlanned(catId, -node.id)). Различение — isOrphanedActual
// ниже, шаблон рисует по нему отдельную пометку «привязана к удалённой плановой позиции».
function unplannedActualFor(node: FeoNode) {
  const catId = node.id
  const hasManualPseudoRow = !(comparisonData.value[catId]?.planned || []).length
    && (node.planned_quantity != null || node.planned_amount != null)
  const absorbed = fallbackAbsorbedByCategory.value[catId]
  const plannedIds = new Set((comparisonData.value[catId]?.planned || []).map(p => p.id))
  return allActualFor(catId).filter(a => {
    if (a.feo_planned_item_id != null) {
      // Мёртвая привязка — не зависит от hasManualPseudoRow/fallback, показываем всегда.
      return !plannedIds.has(a.feo_planned_item_id)
    }
    if (hasManualPseudoRow) return false
    return !(absorbed && absorbed.has(a.purchase_item_id))
  })
}

// Различает две причины попадания в «Не привязаны к плану»: мёртвая привязка (позиция
// формально привязана к feo_planned_item_id, но та плановая позиция удалена) vs позиция
// вообще никогда не была привязана. Внутри unplannedActualFor(node) — единственный
// источник истины, что считается «мёртвым», эта функция ничего не решает заново.
function isOrphanedActual(actual: FeoActualItem): boolean {
  return actual.feo_planned_item_id != null
}

// Dev-ассерт (ШАГ 1 плана дедупликации, 2026-08-07; расширен 2026-08-11 после удаления
// блока «Плановые из закупок»): панель «план vs факт» листа обязана показывать каждую
// PurchaseItem категории РОВНО один раз — либо под своей плановой позицией/синтетической
// строкой (factForPlanned, любая стадия), либо в «Не привязаны» (unplannedActualFor).
// Группы по построению не пересекаются (feo_planned_item_id делит позиции на
// привязанные/непривязанные, hasManualPseudoRow решает, кто абсорбирует непривязанные) —
// если дубль или пропажа всё же появились, это регресс, обязан быть виден в консоли сразу,
// а не найден на проде (см. feedback_no_false_absence_claims в Lessons — позиции не должны
// пропадать молча).
function devCheckNoDuplicateItems(catId: number) {
  if (!import.meta.env.DEV) return
  const node = flattenAll(feoTree.value).find(n => n.id === catId)
  if (!node || node.hasChildren) return
  const ids: number[] = []
  for (const planned of displayPlannedRowsFor(node)) {
    for (const a of factForPlanned(catId, planned.id)) ids.push(a.purchase_item_id)
  }
  for (const a of unplannedActualFor(node)) ids.push(a.purchase_item_id)
  const seen = new Set<number>()
  const dups = new Set<number>()
  for (const id of ids) {
    if (seen.has(id)) dups.add(id)
    seen.add(id)
  }
  if (dups.size) {
    console.warn(`[ФЭО дерево] Дубли PurchaseItem.id в панели «${node.name}» (категория ${catId}):`, [...dups])
  }
  const missing = allActualFor(catId).filter(a => !seen.has(a.purchase_item_id))
  if (missing.length) {
    console.warn(`[ФЭО дерево] Позиции закупок пропали из панели «${node.name}» (категория ${catId}):`, missing.map(a => a.purchase_item_id))
  }
}
watch(comparisonData, (data) => {
  for (const catId of Object.keys(data).map(Number)) devCheckNoDuplicateItems(catId)
}, { deep: true })

// ⚠️ БАГ с прода (2026-08-07): раньше суммировал ТОЛЬКО comparisonData.value[catId].planned —
// это реальные FeoPlannedItem с бэкенда. У категории с РУЧНЫМ планом листа (planned_quantity/
// planned_amount на FeoCategory) и без единой реальной FeoPlannedItem реальный список планового
// пуст, и строка ИТОГО панели не учитывала ручной план вообще, расходясь с «Плановой суммой»
// в шапке дерева (feoPlannedTotalFor/planTreeByCat). Теперь берём displayPlannedRowsFor(node) —
// тот же источник строк, что рисует сама таблица (реальные позиции ИЛИ синтетическая
// «ручной план ФЭО» с уже посчитанной суммой qty × unitPrice, см. displayPlannedRowsFor выше).
// ⚠️ ВТОРОЙ БАГ с прода (2026-08-11, «пикап» Great Wall POER, категория 903): раньше СВЕРХУ
// ещё добавлялась сумма непривязанных позиций закупки в плановой стадии (planStage,
// через actualPlanStageFor) — план и сама закупка складывались (ИТОГО 16 000 000 вместо
// 8 000 000). Плановая часть ИТОГО обязана быть РОВНО суммой плановых строк — позиции
// закупок (любой стадии) теперь либо вложены ПОД своей плановой строкой (не добавляют
// ничего к сумме — она уже посчитана в planned.amount), либо, если не привязаны и плана нет
// вовсе, повисают в «Не привязаны» и намеренно НЕ участвуют ни в плановом, ни в фактическом
// ИТОГО (это и есть смысл пометки «требуется действие»).
function comparisonPlanTotal(node: FeoNode): number {
  return displayPlannedRowsFor(node).reduce((s, p) => s + Number(p.amount || 0), 0)
}

// Требование владельца (2026-08-12): таблица плановых позиций должна выглядеть вложенной
// в свою категорию — так же, как «Внедорожник» вложен в «Транспорт и технику». 20px — это
// сам шаг вложенности дерева (paddingLeft строки категории в основном дереве =
// node.depth * 20 + 8px, см. feo-td-name выше), к нему прибавлен один уровень (+20) плюс
// поправка +5px компенсирующая разницу ширины иконок ПЕРЕД текстом: в строке дерева их
// две — шеврон + папка (~39px), а в строке плановой позиции — одна маленькая (~14px);
// без этой поправки визуальный левый край текста «съедает» уступ и вложенность не видна
// на глаз, хотя padding формально уже глубже. Итог замерян в браузере (getBoundingClientRect
// по текстовым узлам): «Транспорт и техника» → «Внедорожник» → «Great Wall POER» идут
// лесенкой с шагом ≈20px. Привязано к depth, а не константе, чтобы уступ был одинаковым
// на любом уровне вложенности дерева.
function plannedItemIndentPx(node: FeoNode): number {
  return node.depth * 20 + 53
}

// Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.6): ИТОГО «факт» панели
// обязано суммировать РЕАЛЬНЫЙ факт (fact_amount — ContractItem/contract_price), а не
// текущую total_price позиции — та с момента заморозки ТЗ (Шаг 2) держит плановую цену
// и была бы неотличима от плана в самой строке, где как раз нужно показать факт.
function comparisonFactTotal(catId: number): number {
  return actualFactFor(catId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
}

function toggleExpand(id: number) {
  const idx = expandedIds.value.indexOf(id)
  if (idx >= 0) {
    expandedIds.value.splice(idx, 1)
  } else {
    expandedIds.value.push(id)
  }
}

// ── Inline budget edit ───────────────────────────
async function startInlineBudget(node: FeoNode) {
  inlineBudgetId.value = node.id
  inlineBudgetVal.value = node.budget != null ? String(node.budget) : ''
  _pendingBudgetSave = { nodeId: node.id, node }
  await nextTick()
  const el = Array.isArray(inlineInputEl.value) ? inlineInputEl.value[0] : inlineInputEl.value
  el?.focus?.()
}

let _pendingBudgetSave: { nodeId: number; node: FeoNode } | null = null

async function saveInlineBudget(node: FeoNode) {
  // Save nodeId before clearing — blur may fire after re-render
  const nodeId = _pendingBudgetSave?.nodeId ?? inlineBudgetId.value
  if (!nodeId) return
  const savedNode = _pendingBudgetSave?.node ?? node
  _pendingBudgetSave = null
  inlineBudgetId.value = null
  const raw = String(inlineBudgetVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: val, planned_quantity: savedNode.planned_quantity ?? null,
        planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.budget = val
    savedNode.budget = val
    feoCategories.value = [...feoCategories.value]
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

// ── Planned quantity helpers ─────────────────────
// Зеркало фолбэка feoPlannedTotalFor выше (миграция плана → плановые позиции): у
// мигрированного листа planned_quantity null, но план есть в плановых позициях —
// берём qty_plan из planTreeByCat вместо 0.
function feoQtyFor(node: FeoNode): number {
  if (!node.hasChildren) {
    if (node.planned_quantity != null) return Number(node.planned_quantity)
    const t = planTreeByCat.value[node.id]
    if (t && t.qty_plan != null) return Number(t.qty_plan)
    return 0
  }
  if (node.planned_quantity != null) return Number(node.planned_quantity)
  return node.children.reduce((acc, child) => acc + feoQtyFor(child), 0)
}

function isAutoQtyNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.planned_quantity == null
}

// ── Плановое количество из заявок (статусы план закупок и дальше), БЕЗ привязанных к
// плановой позиции (feo_planned_item_id) — те расходуют ручной план листа, а не
// складываются с ним поверх. Карта plannedPurchaseQty уже нетто (qty − qty_linked).
function feoQtyRequestsFor(node: FeoNode): number {
  const own = plannedPurchaseQty.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyRequestsFor(child), 0)
}

// Количество «выбрано заявками» из ручного плана — зеркало feoQtyRequestsFor по карте
// ПРИВЯЗАННЫХ позиций. Нужно, чтобы режимы 'purchases'/'requests' (показывающие ВСЕ
// позиции заявок, не нетто) не потеряли привязанную часть после нетто-правки выше.
function feoQtyConsumedFor(node: FeoNode): number {
  const own = plannedPurchaseQtyLinked.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyConsumedFor(child), 0)
}

// Количество «сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановому
// количеству элемента безусловно, поверх план/заказ. Зеркало feoPlannedOverFor (см. ниже)
// для количеств.
function feoQtyOverFor(node: FeoNode): number {
  const own = plannedPurchaseQtyOver.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoQtyOverFor(child), 0)
}

// Единая формула «Планового количества» узла — считается на бэкенде (сессия
// 2026-08-05, задача «формула только на бэкенде»: раньше здесь была СВОЯ формула
// MAX(план, выбрано) + сверх_плана, которая расходилась с KPI «Запланировано» на
// дашборде/в списке субсидий — тот считает НОВУЮ формулу «заказ замещает план»
// (app.services.feo_plan.compute_feo_plan_tree). Теперь читаем готовое число из
// GET /api/feo-categories/plan-tree (planTreeByCat) — фронт ничего не пересчитывает.
function feoQtyDisplayRaw(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.display_quantity || 0
}

// Отображаемое «Плановое количество» по режиму собственного переключателя
function feoQtyDisplayFor(node: FeoNode): number {
  if (plannedQtyBase.value === 'manual') return feoQtyFor(node)
  // 'purchases'/'requests' — режимы «показать всё из заявок»: +Consumed/+Over возвращают
  // привязанную и сверхплановую часть, вычтенные из feoQtyRequestsFor (иначе переключатель
  // занизит объём).
  if (plannedQtyBase.value === 'purchases') return feoQtyFor(node) + feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node)
  if (plannedQtyBase.value === 'requests') {
    // одноимённые из заявок привязаны к родителю — у слитого листа добавляем их явно
    return feoQtyRequestsFor(node) + feoQtyConsumedFor(node) + feoQtyOverFor(node) + (!node.hasChildren ? matchedReqQty(node) : 0)
  }
  // 'all' (по умолчанию): готовое число с бэкенда — см. feoQtyDisplayRaw. До 2026-08-07 здесь
  // была ветка «слитая позиция: ручной план + matchedReqQty(node)» — складывала ручное
  // количество узла с количеством позиций заявок, сматченных с ним ПО ИМЕНИ (см. matchedReqFor),
  // то есть задваивала счётчик тем же способом, каким уже была исправлена «Плановая сумма»
  // (см. feoPlannedDisplayFor выше, задача «план ≠ факт», сессия 2026-08-06). В 'all' фронт
  // обязан ТОЛЬКО читать готовое число с бэкенда.
  return feoQtyDisplayRaw(node)
}

// Отклонение слитого кол-ва от заложенного в ФЭО показателя (кол-во по документу ФЭО)
function mergedQtyDiff(node: FeoNode): number {
  if (!mergedManualPriority(node) || node.feo_quantity == null) return 0
  const total = feoQtyFor(node) + matchedReqQty(node) + feoQtyRequestsFor(node)
  return Math.round((total - Number(node.feo_quantity)) * 10000) / 10000
}

// ── Planned amount helpers ───────────────────────
function feoAmtFor(node: FeoNode): number {
  if (!node.hasChildren) return node.planned_amount != null ? Number(node.planned_amount) : 0
  if (node.planned_amount != null) return Number(node.planned_amount)
  return node.children.reduce((acc, child) => acc + feoAmtFor(child), 0)
}

// ── Computed planned total: кол-во × стоимость за ед. ───
// Parent = sum of children's planned totals (never qty × unitPrice of parent)
// Leaf = own planned_quantity × own planned_amount
// Миграция плана категории → именованные плановые позиции (FeoPlannedItem, сессия
// 2026-08-12): у мигрированного листа planned_quantity/planned_amount оба null (план
// живёт в активных плановых позициях), поэтому qty×unitPrice ниже даёт 0. Фолбэк —
// planTreeByCat.value[node.id]?.plan_manual, точный двойник этой функции на бэкенде
// (см. app.services.feo_plan.compute_feo_plan_tree: qty×amt, если поля заданы, иначе
// Σ сумм активных плановых позиций). Если дерево плана ещё не загружено — старая
// локальная формула как запасной вариант (даст 0 для мигрированного листа, как раньше).
function feoPlannedTotalFor(node: FeoNode): number {
  if (node.hasChildren) {
    return node.children.reduce((acc, child) => acc + feoPlannedTotalFor(child), 0)
  }
  // Leaf: qty × unit_price (both must be set on THIS node, not inherited)
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : 0
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : 0
  if (qty > 0 && unitPrice > 0) return qty * unitPrice
  if (node.planned_quantity == null && node.planned_amount == null) {
    const t = planTreeByCat.value[node.id]
    if (t && t.plan_manual != null) return Number(t.plan_manual)
  }
  return 0
}

// ── Плановая сумма из заявок (статусы план закупок и дальше), БЕЗ позиций, привязанных
// к плановой позиции (feo_planned_item_id) — они РАСХОДУЮТ ручной план листа (Ур.5),
// а не складываются с ним поверх (иначе план задваивается — см. feoPlannedConsumedFor).
// Лист — из карты бэкенда (уже нетто: total − total_linked); группа — собственные
// позиции (привязанные прямо к группе) + сумма детей.
function feoPlannedRequestsFor(node: FeoNode): number {
  const own = plannedPurchaseTotals.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedRequestsFor(child), 0)
}

// Сумма «выбрано заявками» из ручного плана — зеркало feoPlannedRequestsFor по карте
// ПРИВЯЗАННЫХ позиций. Нужна для заметки под «Плановой суммой» и чтобы режимы
// 'purchases'/'requests' (показывающие ВСЕ позиции заявок целиком) не потеряли
// привязанную часть после нетто-правки feoPlannedRequestsFor выше.
function feoPlannedConsumedFor(node: FeoNode): number {
  const own = plannedPurchaseTotalsLinked.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedConsumedFor(child), 0)
}

// «В плане-графике» — решение владельца 2026-08-18 (категория 3710: три несводимые шкалы
// в строке дерева читались как противоречие). Это ровно та же величина, что уже показывает
// заметка «в закупках» под «Плановой суммой» (feoResidualNoteFor/feoPlanConsumedNoteFor
// считают consumed этой же суммой) — второй источник чисел не изобретаем, оба места сведены
// к этому хелперу.
function feoInPlanScheduleFor(node: FeoNode): number {
  return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node)
}

// Сумма «сверх плана» (over_plan=true, НЕпривязанные) — прибавляется к плановой сумме
// элемента безусловно, поверх план/заказ (см. feoPlannedDisplayRaw ниже).
// Лист — из карты бэкенда (уже нетто относительно linked); группа — собственные
// сверхплановые позиции (прямо на группе) + сумма детей.
function feoPlannedOverFor(node: FeoNode): number {
  const own = plannedPurchaseTotalsOver.value[node.id] || 0
  if (!node.hasChildren) return own
  return own + node.children.reduce((acc, child) => acc + feoPlannedOverFor(child), 0)
}

// Единая формула «Плановой суммы» узла — считается на бэкенде (сессия 2026-08-05,
// задача «формула только на бэкенде»). Раньше здесь была СВОЯ формула
// MAX(план, выбрано) + сверх_плана — расходилась с KPI «Запланировано» на дашборде/
// в списке субсидий, который считает через _calculate_feo_planned_tree_bulk НОВУЮ
// формулу «заказ замещает план, когда количество набрано полностью»
// (app.services.feo_plan.compute_feo_plan_tree) — два разных числа на одном экране.
// Теперь читаем готовое число из GET /api/feo-categories/plan-tree (planTreeByCat) —
// единственный источник правды, фронт ничего не пересчитывает и не обходит детей сам.
function feoPlannedDisplayRaw(node: FeoNode): number {
  return planTreeByCat.value[node.id]?.display || 0
}

// Отображаемая «Плановая сумма» по режиму переключателя.
// Нетто-исключение привязанных применяется ТОЛЬКО в ветке 'all' (последний return —
// единственный режим, где «Плановая сумма» это цельный лимит листа, который заявка не
// должна задваивать). 'purchases' и 'requests' — режимы «показать всё из заявок», там
// +feoPlannedConsumedFor(node)/+feoPlannedOverFor(node) восстанавливают привязанную и
// сверхплановую часть до полного объёма (feoPlannedRequestsFor теперь исключает обе).
function feoPlannedDisplayFor(node: FeoNode): number {
  if (plannedSumBase.value === 'manual') return feoPlannedTotalFor(node)
  if (plannedSumBase.value === 'purchases') return feoPlannedTotalFor(node) + feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node)
  if (plannedSumBase.value === 'requests') {
    // одноимённые из заявок привязаны к родителю — у слитого листа добавляем их явно
    return feoPlannedRequestsFor(node) + feoPlannedConsumedFor(node) + feoPlannedOverFor(node) + (!node.hasChildren ? matchedReqTotal(node) : 0)
  }
  // 'all' (по умолчанию): готовое число с бэкенда — см. feoPlannedDisplayRaw.
  // Задача владельца «план ≠ факт» (сессия 2026-08-06, Шаг 5, п.4): раньше здесь была
  // ветка «слитая позиция: ручной план + matchedReqTotal(node)», которая СКЛАДЫВАЛА
  // ручной план узла с суммой позиций заявок, сматченных с ним ПО ИМЕНИ — источник
  // задвоения (пример владельца: ручной план 8 000 000 + заявка 8 380 000 = 16 760 000,
  // хотя заявка ЯВЛЯЕТСЯ этим планом, а не чем-то поверх него). В режиме 'all' фронт
  // обязан ТОЛЬКО читать готовое число с бэкенда (compute_feo_plan_tree уже правильно
  // засчитывает факт/план по каждой позиции ровно один раз — см. feo_plan.py).
  return feoPlannedDisplayRaw(node)
}

// Заметка под «Плановой суммой»: план N ₽ · в закупках M ₽ · свободно K ₽ (см. ЗАДАЧА
// сессии 2026-08-05). Свободно = plan_manual − consumed (может уйти в минус — тогда
// шаблон пишет «больше плана на X»). Показывается ТОЛЬКО в режиме 'all' (единственный
// режим, где действует новая формула MAX) и только когда есть хоть какие-то числа —
// пустые узлы (ни плана, ни заявок) заметку не показывают.
//
// БАГ (жалоба владельца 2026-08-13, «Окружные»): «план 513 244 — это откуда?» — раньше
// planned = feoPlannedTotalFor(node), а та для узла с детьми считает ТОЛЬКО сумму
// планов детей, без собственной плановой позиции узла — расходилась с шапкой строки
// (feoPlannedDisplayFor/planTreeByCat.plan_manual, который = дети + own_amt, см.
// feoOwnDirectionPlanFor). Теперь planned читается из ТОГО ЖЕ planTreeByCat.plan_manual,
// что и шапка — те же 561 685,80, а не 513 244. feoPlannedTotalFor(node) остаётся ТОЛЬКО
// запасным вариантом на случай, когда дерево плана (planTreeByCat) ещё не загружено.
//
// БАГ 2: «выбрано 695 656 — откуда?» / у конечной категории «выбрано заявками 0,00»
// при факте 118 365,60 закупками — раньше consumed = feoPlannedRequestsFor(node), это
// ТОЛЬКО непривязанные к Ур.5 позиции заявок (plannedPurchaseTotals). Если у категории
// все позиции привязаны (feo_planned_item_id задан), consumed был 0, хотя по плану уже
// набрано. Складываем непривязанные (feoPlannedRequestsFor) с привязанными
// (feoPlannedConsumedFor, карта plannedPurchaseTotalsLinked) — «в закупках» теперь
// считает ВСЁ, что стоит за планом, вне зависимости от привязки.
function feoPlanConsumedNoteFor(node: FeoNode): { planned: number; consumed: number; residual: number } | null {
  const t = planTreeByCat.value[node.id]
  const planned = (t && t.plan_manual != null) ? Number(t.plan_manual) : feoPlannedTotalFor(node)
  const consumed = feoInPlanScheduleFor(node)
  if (planned <= 0 && consumed <= 0) return null
  return { planned, consumed, residual: planned - consumed }
}

// Прогнозное предупреждение «цена выше плановой» (ЗАДАЧА 2/3 сессии 2026-08-05).
// Данные считаются на бэкенде (app.services.feo_plan.compute_feo_plan_tree, поля
// forecast/forecast_over/plan_manual в GET /feo-categories/planned-purchase-totals,
// см. plannedPurchaseForecast) — фронт только читает готовое число, НИКАКИХ
// вычислений и блокировок. Только информирование: если по факту заказанного темпу
// цен итоговая сумма грозит превысить план — оранжевая заметка под «Плановой суммой».
function feoForecastWarningFor(node: FeoNode): { forecast: number; forecastOver: number; planManual: number } | null {
  const v = plannedPurchaseForecast.value[node.id]
  if (!v || !(v.forecast_over > 0)) return null
  return { forecast: v.forecast, forecastOver: v.forecast_over, planManual: v.plan_manual }
}

function isAutoAmtNode(node: FeoNode): boolean {
  if (!node.hasChildren) return false
  return node.planned_amount == null
}

let _pendingAmtSave: { nodeId: number; node: FeoNode } | null = null

async function startInlineAmt(node: FeoNode) {
  inlineAmtId.value = node.id
  inlineAmtVal.value = node.planned_amount != null ? String(node.planned_amount) : ''
  _pendingAmtSave = { nodeId: node.id, node }
  await nextTick()
  const elA = Array.isArray(inlineAmtInputEl.value) ? inlineAmtInputEl.value[0] : inlineAmtInputEl.value
  elA?.focus?.()
}

async function saveInlineAmt(node: FeoNode) {
  const nodeId = _pendingAmtSave?.nodeId ?? inlineAmtId.value
  if (!nodeId) return
  const savedNode = _pendingAmtSave?.node ?? node
  _pendingAmtSave = null
  inlineAmtId.value = null
  const raw = String(inlineAmtVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: savedNode.planned_quantity ?? null,
        planned_amount: val ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.planned_amount = val ?? null
    savedNode.planned_amount = val ?? null
    feoCategories.value = [...feoCategories.value]
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

let _pendingQtySave: { nodeId: number; node: FeoNode } | null = null

async function startInlineQty(node: FeoNode) {
  inlineQtyId.value = node.id
  inlineQtyVal.value = node.planned_quantity != null ? String(node.planned_quantity) : ''
  _pendingQtySave = { nodeId: node.id, node }
  await nextTick()
  const elQ = Array.isArray(inlineQtyInputEl.value) ? inlineQtyInputEl.value[0] : inlineQtyInputEl.value
  elQ?.focus?.()
}

async function saveInlineQty(node: FeoNode) {
  const nodeId = _pendingQtySave?.nodeId ?? inlineQtyId.value
  if (!nodeId) return
  const savedNode = _pendingQtySave?.node ?? node
  _pendingQtySave = null
  inlineQtyId.value = null
  const raw = String(inlineQtyVal.value ?? '').trim()
  const val = raw === '' ? null : parseFloat(raw)
  try {
    await apiFetch(`/feo-categories/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
        is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: val,
        planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
    })
    const cat = feoCategories.value.find(c => c.id === nodeId)
    if (cat) cat.planned_quantity = val
    savedNode.planned_quantity = val
    feoCategories.value = [...feoCategories.value]
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

// ── Drag & Drop ──────────────────────────────────
function onDragStart(e: DragEvent, node: FeoNode) {
  dragNodeId.value = node.id
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(node.id))
}

function onDragOver(e: DragEvent, node: FeoNode) {
  if (!dragNodeId.value || dragNodeId.value === node.id) return
  const subtree = collectSubtreeIds(feoCategories.value, dragNodeId.value)
  if (subtree.includes(node.id)) return
  dragOverId.value = node.id
}

function onDragLeave() { dragOverId.value = null }

async function onDrop(e: DragEvent, targetNode: FeoNode) {
  e.preventDefault()
  if (!dragNodeId.value || dragNodeId.value === targetNode.id) return
  const srcId = dragNodeId.value
  const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode) return
  const subtree = collectSubtreeIds(feoCategories.value, srcId)
  if (subtree.includes(targetNode.id)) { showSnack('Нельзя переместить в собственное поддерево', 'error'); return }
  if (srcNode.parent_id === targetNode.id) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: targetNode.id }),
    })
    showSnack('Категория перемещена')
    if (res?.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
}

async function onDropToRoot(e: DragEvent) {
  e.preventDefault()
  if (!dragNodeId.value) return
  const srcId = dragNodeId.value
  const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode || !srcNode.parent_id) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: null }),
    })
    showSnack('Категория перемещена на верхний уровень')
    if (res?.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
}

function onDragEnd() { dragNodeId.value = null; dragOverId.value = null }

// ── Data load ─────────────────────────────────────
// Phase 26-ZZ: bulk-load контрагентов убран. Локальный contractors массив
// наполняется через ContractorPicker и ad-hoc fetch при edit.
async function loadAll() {
  loading.value = true
  try {
    const charts = await apiFetch<any>('/dashboard/charts?scope=managed')
    allSubsidies.value = charts.subsidy_stats.map((s: any) => ({
      id: s.id, name: s.name, year: s.year, budget: s.budget,
      calculated_budget: s.calculated_budget ?? 0,
      planned: s.planned_tree ?? s.total_planned, paid: s.total_paid, contracted: s.total_confirmed,
      plan_schedule: s.total_plan_schedule ?? 0,
      ordered: s.total_ordered ?? 0,
      feo_budget_total: s.feo_budget_total ?? 0,
      feo_filled: s.feo_filled ?? false,
      contractor_id: s.contractor_id ?? null,
      contractor_name: s.contractor_name ?? null,
      contractor_inn: s.contractor_inn ?? null,
      // Phase 31-05: canonical budget fields (D-17)
      remaining: s.remaining ?? null,
      planned_amount: s.planned_amount ?? null,
      budget_discrepancy: s.budget_discrepancy ?? null,
      // Phase 32: dashboard KPI fields
      work: s.total_work ?? 0,
      contracts: s.total_contracts ?? 0,
      delivered: s.total_delivered ?? 0,
      delivered_unpaid: s.total_delivered_unpaid ?? 0,
      // Владелец (2026-08-30): предупреждение о подходе к потолку субсидии
      ceiling_warn_percent: s.ceiling_warn_percent ?? 90,
      ceiling_total: s.ceiling_total ?? 0,
      ceiling_committed_total: s.ceiling_committed_total ?? 0,
      ceiling_committed_percent: s.ceiling_committed_percent ?? 0,
      ceiling_near_warning: s.ceiling_near_warning ?? false,
      ceiling_exceeded: s.ceiling_exceeded ?? false,
      status: 'approved', // fallback, перезаписывается ниже реальным значением
    }))
    // C4: dashboard/charts не отдаёт status/created_by/approved_by/approved_at
    // (это отдельная сводка бюджетов). Статус черновика подтягиваем отдельным
    // вызовом уже существующего списочного эндпоинта и мёрджим по id — без
    // изменений на бэкенде. Ошибка здесь не должна ломать страницу (fallback
    // 'approved' — чипы просто не появятся).
    try {
      const statusRows = await apiFetch<Array<{ id: number; status?: string; created_by?: number | null; approved_by?: number | null; approved_at?: string | null }>>('/subsidies/')
      const byId = new Map(statusRows.map(r => [r.id, r]))
      for (const row of allSubsidies.value) {
        const found = byId.get(row.id)
        if (found) {
          row.status = found.status ?? 'approved'
          row.created_by = found.created_by ?? null
          row.approved_by = found.approved_by ?? null
          row.approved_at = found.approved_at ?? null
        }
      }
    } catch (e) {
      console.warn('[subsidies] status load failed:', e)
    }
    const years = [...new Set(allSubsidies.value.map((s: SubsidyRow) => s.year))].sort((a, b) => b - a)
    if (years.length) selectedYear.value = years[0]  // always reset to most recent year

    // Handle ?sid=X navigation from Quick Access
    const sidParam = route.query.sid
    if (sidParam) {
      const targetId = Number(sidParam)
      const target = allSubsidies.value.find(s => s.id === targetId)
      if (target) {
        selectedYear.value = target.year
        selectedId.value = targetId
        loadFeo(targetId)
      }
    }
  } catch (e) {
    showSnack('Ошибка загрузки данных', 'error')
  } finally {
    loading.value = false
  }
}

// exportFeoPdf — вынесена в FeoTreeToolbar.vue (волна 5b, кнопка «Экспорт → PDF»
// тулбара дерева ФЭО, использовалась только там).
// exportFeoToExcel — вынесена в usePlanGraphVersions.ts (использовалась только
// runVersionsExport, тоже там).

async function downloadFeoTemplate(subsidyId?: number, subsidyName?: string) {
  const token = localStorage.getItem('auth_token')
  const qs = subsidyId ? `?subsidy_id=${subsidyId}` : ''
  const res = await fetch(`/api/feo-categories/import/template${qs}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const safeName = subsidyName ? subsidyName.replace(/[\\/:*?"<>|]/g, '_').trim() : ''
  const fname = safeName
    ? `Шаблон_импорта_направлений_ФЭО_${safeName}.xlsx`
    : 'Шаблон_импорта_направлений_ФЭО.xlsx'
  const a = document.createElement('a'); a.href = url; a.download = fname; a.click()
  URL.revokeObjectURL(url)
}

// doFeoImport/doFeoMappedImport/closeFeoImport — вынесены в useFeoImport.ts.
async function loadFeo(subsidyId: number) {
  loadingFeo.value = true
  feoCategories.value = []
  purchaseTotals.value = {}
  plannedPurchaseTotals.value = {}
  plannedPurchaseQty.value = {}
  plannedPurchaseTotalsLinked.value = {}
  plannedPurchaseQtyLinked.value = {}
  plannedPurchaseTotalsOver.value = {}
  plannedPurchaseQtyOver.value = {}
  plannedPurchaseForecast.value = {}
  planTreeByCat.value = {}
  planExcessApprovals.value = {}
  unassignedFeo.value = { amount: 0, purchase_count: 0, purchase_ids: [] }
  plannedItemsByCat.value = {}
  plannedItemsLoaded.value = false
  // expandedReqItems больше НЕ сбрасывается здесь безусловно (было `= new Set()`) — это
  // ломало persist раскрытых узлов при перезагрузке страницы (см. FEO_DISPLAY_PREFS_KEY):
  // loadFeo вызывается сразу при выборе субсидии, и сброс стирал восстановленное из
  // localStorage состояние раньше, чем пользователь успевал его увидеть. Устаревшие id
  // от другой субсидии безвредны — hasReqItems/virtualGroupsFor для несуществующего в
  // текущей субсидии узла просто вернут пусто.
  try {
    const [cats, totals, plannedTotals, plannedItems, planTree] = await Promise.all([
      apiFetch<FeoCategory[]>(`/feo-categories/?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, number>>(`/feo-categories/purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, { total: number; qty: number; total_linked?: number; qty_linked?: number; total_over?: number; qty_over?: number; forecast?: number; forecast_over?: number; plan_manual?: number }>>(`/feo-categories/planned-purchase-totals?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, FeoReqItem[]>>(`/feo-categories/planned-purchase-items?subsidy_id=${subsidyId}`),
      apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${subsidyId}`),
    ])
    feoCategories.value = cats
    purchaseTotals.value = totals
    planTreeByCat.value = splitPlanTree(planTree)
    loadPlanExcessApprovals(subsidyId)
    plannedItemsByCat.value = plannedItems
    plannedItemsLoaded.value = true
    const sums: Record<number, number> = {}
    const qtys: Record<number, number> = {}
    const sumsLinked: Record<number, number> = {}
    const qtysLinked: Record<number, number> = {}
    const sumsOver: Record<number, number> = {}
    const qtysOver: Record<number, number> = {}
    const forecasts: Record<number, { forecast: number; forecast_over: number; plan_manual: number }> = {}
    for (const [k, v] of Object.entries(plannedTotals)) {
      const totalLinked = Number(v?.total_linked || 0)
      const qtyLinked = Number(v?.qty_linked || 0)
      const totalOver = Number(v?.total_over || 0)
      const qtyOver = Number(v?.qty_over || 0)
      sums[Number(k)] = Number(v?.total || 0) - totalLinked - totalOver
      qtys[Number(k)] = Number(v?.qty || 0) - qtyLinked - qtyOver
      sumsLinked[Number(k)] = totalLinked
      qtysLinked[Number(k)] = qtyLinked
      sumsOver[Number(k)] = totalOver
      qtysOver[Number(k)] = qtyOver
      forecasts[Number(k)] = {
        forecast: Number(v?.forecast || 0),
        forecast_over: Number(v?.forecast_over || 0),
        plan_manual: Number(v?.plan_manual || 0),
      }
    }
    plannedPurchaseTotals.value = sums
    plannedPurchaseQty.value = qtys
    plannedPurchaseTotalsLinked.value = sumsLinked
    plannedPurchaseQtyLinked.value = qtysLinked
    plannedPurchaseTotalsOver.value = sumsOver
    plannedPurchaseQtyOver.value = qtysOver
    plannedPurchaseForecast.value = forecasts
    // Восстановленные из localStorage раскрытые панели «план vs факт» (expandedItemPanels)
    // не тянут свои данные сами — toggleItemPanel грузит их только по клику. Подгружаем
    // явно, иначе после перезагрузки страницы раскрытая панель будет пустой до повторного клика.
    for (const id of expandedItemPanels.value) {
      if (feoCategories.value.some(c => c.id === id)) refreshComparison(id)
    }
  } catch {
    showSnack('Ошибка загрузки категорий ФЭО', 'error')
  } finally {
    loadingFeo.value = false
  }
}

async function reorderFeoNode(node: any, direction: 'up' | 'down') {
  if (!selectedId.value) return
  try {
    const res = await apiFetch<any>(`/feo-categories/${node.id}/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ direction }),
    })
    if (res?.moved === false) {
      showSnack(direction === 'up' ? 'Уже первая в списке' : 'Уже последняя в списке', 'info')
      return
    }
    await loadFeo(selectedId.value)
    syncFeoFilled()
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Не удалось переместить', 'error')
  }
}

// Замечание владельца п.3 (2026-08-12): «Приравнять ФЭО к плану» — POST
// /feo-categories/{id}/align-budget-to-plan (бэкенд уже готов, включая жёсткий
// потолок субсидии — assert внутри самого эндпоинта, фронт ничего не проверяет
// заранее). Доступ — org_admin и выше: переиспользуем canSaveVersion (тот же
// набор ролей, что backend ADMIN_ROLES = superadmin/account_owner/admin/org_admin,
// см. её объявление ниже) — НЕ придумываем новую проверку, чтобы не потерять
// org_admin, как это уже бывало в проекте (см. Lessons).
const alignBudgetLoading = ref<number | null>(null)
const alignBudgetDialog = ref<{ show: boolean; node: FeoNode | null; newBudget: number; oldBudget: number }>({
  show: false, node: null, newBudget: 0, oldBudget: 0,
})
function openAlignBudgetConfirm(node: FeoNode) {
  const t = planTreeByCat.value[node.id]
  const newBudget = Number(t?.plan || 0) + Number(t?.over || 0)
  alignBudgetDialog.value = { show: true, node, newBudget, oldBudget: Number(node.budget || 0) }
}
async function confirmAlignBudgetToPlan() {
  const node = alignBudgetDialog.value.node
  if (!node) return
  alignBudgetLoading.value = node.id
  try {
    await apiFetch(`/feo-categories/${node.id}/align-budget-to-plan`, { method: 'POST' })
    alignBudgetDialog.value.show = false
    showSnack('Финансирование по ФЭО приравнено к плану', 'success')
    if (selectedId.value) await loadFeo(selectedId.value)
  } catch (e: any) {
    // Ошибку показываем распакованной (в т.ч. отказ по общему потолку субсидии,
    // код PLAN_OVER_SUBSIDY_CEILING) — showSnack по умолчанию без автозакрытия.
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось приравнять ФЭО к плану', 'error')
  } finally {
    alignBudgetLoading.value = null
  }
}

// ── Actions ───────────────────────────────────────
// 12-04: load FEO residuals for selected subsidy
async function loadResiduals() {
  if (!selectedId.value) return
  residualsLoading.value = true
  try {
    const data = await apiFetch<any[]>(`/feo-planned-items/residuals?subsidy_id=${selectedId.value}`)
    const byItemId: Record<number, any> = {}
    for (const item of data) {
      byItemId[item.feo_item_id] = item
    }
    feoResiduals.value = byItemId
  } catch (e) {
    console.error('Failed to load residuals', e)
  } finally {
    residualsLoading.value = false
  }
}

// loadVersionHistory/openVersionHistory/viewVersionSnapshot/downloadVersionExcel/
// formatEditionDate/openExportVersionsDialog/toggleExportId/runVersionsExport/
// downloadCompareExcel/flattenedSnapshotTree/getReconStatus/getActualUsed/
// getActualResidual/snapshotTotalActual/openSaveVersionDialog/saveVersion —
// вынесены в usePlanGraphVersions.ts.

// exportPlanGraphExcel/exportPlanGraphDocx/uploadTemplate — вынесены в
// FeoTreeToolbar.vue (волна 5b, использовались только кнопками её тулбара).

function toggleSelect(id: number) {
  if (selectedId.value === id) { selectedId.value = null; globalSubsidyId.value = null; return }
  selectedId.value = id
  globalSubsidyId.value = id
  loadFeo(id)
  loadEvents(id)
  loadResiduals()  // 12-04
}

// Sync: global → local
watch(globalSubsidyId, (id: number | null) => {
  if (id !== null && id !== selectedId.value) {
    selectedId.value = id
    loadFeo(id)
    loadEvents(id)
    loadResiduals()  // 12-04
  } else if (id === null) {
    selectedId.value = null
    feoResiduals.value = {}  // 12-04
  }
})

// startEdit/confirmDelete — тонкие прокси в SubsidyEditDialog.vue/
// SubsidyDeleteDialog.vue: сама форма, апи-вызовы и состояние диалога теперь
// там, а вызовы из списка субсидий (@click.stop="startEdit(item)"/"confirmDelete(item)")
// остаются текстуально теми же.
async function startEdit(s: SubsidyRow) {
  await subsidyEditDialogRef.value?.startEdit(s)
}

async function confirmDelete(s: SubsidyRow) {
  await subsidyDeleteDialogRef.value?.open(s)
}

// openAddFeoDialog/startFeoEdit/confirmFeoDelete — тонкие прокси в
// FeoCategoryDialog.vue/FeoCategoryDeleteDialog.vue. addFeoCategory/updateFeoCategory/
// deleteFeoCategory/openAddPlannedItemFromCategoryEdit/convertCategoryEditPlanToItem
// переехали туда же вместе с формами feoForm/feoEditForm.
function openAddFeoDialog(parentId: number | null) {
  feoCategoryDialogRef.value?.openAdd(parentId)
}

// Update calculated_budget on the card after FEO budget changes (using tree logic)
function syncFeoFilled() {
  if (!selectedId.value) return
  // Справочный расчёт по дереву: ручное ФЭО, без него — факт, иначе план
  const total = feoTree.value.reduce((sum, root) => sum + feoEffectiveFor(root), 0)
  const s = allSubsidies.value.find(x => x.id === selectedId.value)
  if (s) {
    s.feo_filled = total > 0
    s.feo_budget_total = total
    s.calculated_budget = total
  }
}

function startFeoEdit(node: FeoNode) {
  feoCategoryDialogRef.value?.openEdit(node)
}

function confirmFeoDelete(node: FeoCategory) {
  feoCategoryDeleteDialogRef.value?.open(node)
}

// ── Budget history ────────────────────────────────
function openHistoryDialog(s: any) {
  historyDialogRef.value?.open(s.id, s.name)
}

// ── C4: Draft subsidies — approve + members ────────
// Кнопка видна только для черновика и только тому, у кого есть право
// subsidy.edit — тот же hasAction(), которым уже проверяется canEditFeo
// (feo_category.edit) в этом файле. Сервер (POST /approve) перепроверяет
// require_action('subsidy.edit') сам — фронт лишь скрывает лишнее.
function canApproveSubsidy(s: SubsidyRow | null): boolean {
  if (!s) return false
  return s.status === 'draft' && authStore.hasAction('subsidy.edit')
}

async function approveSubsidy(s: SubsidyRow) {
  approvingSubsidyId.value = s.id
  try {
    const updated = await apiFetch<{ status?: string; approved_by?: number | null; approved_at?: string | null }>(
      `/subsidies/${s.id}/approve`, { method: 'POST' }
    )
    const idx = allSubsidies.value.findIndex(x => x.id === s.id)
    if (idx >= 0) {
      allSubsidies.value[idx] = {
        ...allSubsidies.value[idx],
        status: updated.status ?? 'approved',
        approved_by: updated.approved_by ?? null,
        approved_at: updated.approved_at ?? null,
      }
    }
    showSnack('Субсидия утверждена')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка утверждения субсидии', 'error')
  } finally {
    approvingSubsidyId.value = null
  }
}

// openMembersDialog — тонкий прокси в SubsidyMembersDialog.vue (loadMemberUsers/
// addSubsidyMember/removeSubsidyMember переехали туда же). openApproversDialog/
// openTemplateDialog теперь берутся напрямую из useSubsidyApprovers()/
// useSubsidyTemplates() (см. константы composables ниже, вызов деструктуризацией).
async function openMembersDialog(s: SubsidyRow) {
  await subsidyMembersDialogRef.value?.open(s)
}

// ── Helpers ───────────────────────────────────────
// pct/progressColor/cardDelta — вынесены в useSubsidyList.ts (использовались только
// в карточках списка, волна 5b). formatCurrencyRound/formatCurrencyShort — в
// composables/subsidies/format.ts (импортированы сверху, Правило №6).

function showSnack(
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) {
  toast.addToast(text, color, opts)
}

// ── Contractor override ─────────────────────────
// openContractorOverride — тонкий прокси в SubsidyContractorOverrideDialog.vue
// (saveContractorOverride/overrideForm переехали туда же).
async function openContractorOverride(s: SubsidyRow) {
  await contractorOverrideDialogRef.value?.open(s)
}

// ── Events (Мероприятия) — состояние и loadEvents делегированы
// SubsidyEventsPanel.vue через ref (addEvent/saveEditEvent/deleteEvent/
// downloadReport переехали туда же); watcher'ы globalSubsidyId/toggleSelect
// ниже по файлу продолжают вызывать loadEvents(id) текстуально без изменений.
async function loadEvents(subsidyId: number) {
  await eventsPanelRef.value?.reload(subsidyId)
}

// ── Ссылки на диалоги, вынесенные в components/subsidies/*: родитель дальше
// не хранит их форм/состояния, только дёргает исключённые наружу open()-методы
// (см. startEdit/confirmDelete/startFeoEdit/confirmFeoDelete/openMembersDialog/
// openContractorOverride/loadEvents выше и openAddFeoDialog чуть выше) —
// вызовы из внешнего списка субсидий/дерева ФЭО остаются текстуально теми же.
const eventsPanelRef = ref<InstanceType<typeof SubsidyEventsPanel> | null>(null)
const subsidyEditDialogRef = ref<InstanceType<typeof SubsidyEditDialog> | null>(null)
const subsidyDeleteDialogRef = ref<InstanceType<typeof SubsidyDeleteDialog> | null>(null)
const feoCategoryDialogRef = ref<InstanceType<typeof FeoCategoryDialog> | null>(null)
const feoCategoryDeleteDialogRef = ref<InstanceType<typeof FeoCategoryDeleteDialog> | null>(null)
const subsidyMembersDialogRef = ref<InstanceType<typeof SubsidyMembersDialog> | null>(null)
const contractorOverrideDialogRef = ref<InstanceType<typeof SubsidyContractorOverrideDialog> | null>(null)

// Шаблоны документов — module-level singleton (см. её докстринг): паренту нужен
// только loadTemplateVars() для onMounted; openTemplateDialog/contractTemplates
// (список субсидий) и openApproversDialog (useSubsidyApprovers.ts) теперь берутся
// напрямую в SubsidyListTable.vue/SubsidyCardsGrid.vue, openVersionHistory/
// openExportVersionsDialog/openSaveVersionDialog (usePlanGraphVersions.ts) — в
// FeoTreeToolbar.vue, feoImport (useFeoImport.ts) — тоже там (волна 5b).
const { loadTemplateVars } = useSubsidyTemplates()
// Плановые позиции (usePlannedItems.ts, тот же singleton-паттерн) — паренту
// нужны open*-функции: тройка openAddPlannedItem/openConvertManualPlanToItem/
// openMapDialog вызывается прямо из дерева ФЭО (шаблон выше) и уходит в ctx
// ниже для FeoCategoryDialog.vue; openCreatePlannedFromActual/openEditPlannedItem/
// openEditCategoryPlan — тоже из дерева. Само состояние читают/пишут вынесенные
// диалоги PlannedItem*Dialog.vue/CategoryPlanEditDialog.vue.
const {
  openAddPlannedItem, openConvertManualPlanToItem, openCreatePlannedFromActual,
  openEditPlannedItem, openEditCategoryPlan, openMapDialog,
  // mapTarget/mapCategoryId/applyMapping — нужны напрямую дереву ФЭО для кнопки
  // «Снять сопоставление» (см. её докстринг в шаблоне выше: прямое присваивание
  // top-level ref без диалога, applyMapping(null) вызывается без открытия
  // showMapDialog).
  mapTarget, mapCategoryId, applyMapping,
} = usePlannedItems({ selectedId, feoCategories, loadFeo, comparisonData, refreshComparison, ensureComparison, refreshReqData, factForPlanned })

// Контекст детали субсидии для вынесенных диалогов/компонентов (provide/inject,
// см. composables/subsidies/useSubsidyDetail.ts) — единственная точка, откуда они
// читают/пишут состояние, оставшееся в родителе (список субсидий, дерево ФЭО).
// Волна 5b расширила его полями списка субсидий (toggleSelect/canApproveSubsidy/…)
// и «сырыми» ссылками дерева, нужными useKpiDrilldown.ts (см. ниже) — не второй
// контекст, а расширение существующего (Правило №6).
const subsidyDetailCtx = {
  router,
  allSubsidies,
  loadAll,
  selectedId,
  selectedSubsidy,
  feoCategories,
  feoTree,
  flattenAll,
  loadFeo,
  syncFeoFilled,
  openAddPlannedItem,
  openConvertManualPlanToItem,
  getFeoPlanManual: (categoryId: number) => Number(planTreeByCat.value[categoryId]?.plan_manual || 0),
  comparisonData,
  refreshComparison,
  ensureComparison,
  refreshReqData,
  factForPlanned,
  photoPreview,
  canEditFeo,
  downloadFeoTemplate,
  toggleSelect,
  canApproveSubsidy,
  approveSubsidy,
  approvingSubsidyId,
  startEdit,
  confirmDelete,
  openMembersDialog,
  openHistoryDialog,
  openContractorOverride,
  openAddFeoDialog,
  feoTableArea,
  feoItemsGroupBy,
  plannedBase,
  selectedBudget,
  selectedPlannedTotal,
  plannedItemsByCat,
  plannedItemsLoaded,
  mergedReqByCat,
  purchaseFoldersByCat,
  expandedIds,
  expandedReqItems,
  expandedItemPanels,
  expandedPurchases,
  expandedPlannedItems,
  collapsedPlannedItems,
  feoSearch,
  loadingComparison,
  feoFinDiff,
  feoPlannedTotalFor,
}
provideSubsidyDetail(subsidyDetailCtx)

// kpiNodeClass/activeKpi нужны функциям подсветки строк дерева выше по файлу
// (kpiReqRowClass/kpiItemRowClass/kpiFolderClass) и шаблону (kpi.kpiNodeClass(node))
// — тот же module-singleton экземпляр, что получит SubsidyKpiCards.vue, вызвав
// useKpiDrilldown(useSubsidyDetailCtx()) (см. докстринг композабла).
const kpi = useKpiDrilldown(subsidyDetailCtx)

onMounted(() => {
  loadAll()
  loadTemplateVars()
})
</script>

<style scoped>
/* ── Layout ── */
/* Ширина страницы не ограничивается (жалоба владельца 2026-08-12: «какого хуя
   половина окна не задействована»): раньше стоял max-width: 1600px, и на широком
   мониторе правая половина экрана пустовала, хотя таблица ФЭО как раз просит
   ширины — у неё шесть числовых колонок плюс раскрывающиеся панели плана и факта. */
.subsidies-page {
  padding: 20px 24px;
  width: 100%;
  box-sizing: border-box;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Empty state ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: var(--crm-text-faint);
}

/* ── Subsidies grid ── */
.subsidies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.subsidy-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 2px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 18px 20px;
  cursor: grab;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s, opacity 0.15s;
  position: relative;
}
.subsidy-card:active {
  cursor: grabbing;
}
.subsidy-card--dragging {
  opacity: 0.4;
}
.subsidy-card--drag-over {
  outline: 2px dashed rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.subsidy-card::after {
  content: 'Нажмите для подробностей';
  position: absolute;
  bottom: 6px;
  right: 12px;
  font-size: 10px;
  color: var(--crm-text-faint);
  opacity: 0;
  transition: opacity 0.15s;
}
.subsidy-card:hover::after {
  opacity: 1;
}
.subsidy-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px var(--crm-shadow-hover);
  border-color: rgba(var(--v-theme-primary), 0.3);
}
.subsidy-card--active {
  border-color: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.12), 0 4px 16px var(--crm-shadow-hover);
}

/* Шапка карточки: название — крупные полупрозрачные буквы в одну строку (фон),
   кнопки управления поверх них */
.sc-title-band {
  margin-bottom: 8px;
  display: flex; flex-direction: column; align-items: center;
}
.sc-actions { display: flex; gap: 2px; align-items: center; justify-content: center; }
.sc-name {
  font-weight: 800; color: var(--crm-text-muted);
  line-height: 1.15; text-align: center;
  white-space: nowrap; overflow: hidden;
  width: 100%; user-select: none;
}
.sc-delta-chip { height: auto !important; max-width: 100%; }
.sc-delta-chip :deep(.v-chip__content) { white-space: normal; line-height: 1.35; padding-top: 3px; padding-bottom: 3px; }
.sc-budget      { font-size: 22px; font-weight: 700; color: var(--crm-text); }
.sc-budget-label{ font-size: 11px; color: var(--crm-text-faint); margin-bottom: 12px; }

.sc-mini-row { display: flex; gap: 20px; }
.sc-mini-label { font-size: 11px; color: var(--crm-text-faint); margin-bottom: 2px; }
.sc-mini-val   { font-size: 13px; font-weight: 600; }

.sc-contractor { font-size: 12px; color: var(--crm-text-faint); display: flex; align-items: center; margin-top: 6px; }
.sc-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.sc-pct { font-size: 11px; color: var(--crm-text-faint); }
.sc-feo-badge { display: flex; align-items: center; font-size: 11px; font-weight: 600; border-radius: 10px; padding: 1px 7px; }
.sc-feo-badge--ok  { color: #16a34a; background: #dcfce7; }
.sc-feo-badge--no  { color: var(--crm-text-faint); background: var(--crm-surface-hover); }

/* ── Summary bar ── */
.summary-bar {
  display: flex; align-items: center; gap: 0;
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 14px 24px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.summary-item  { display: flex; flex-direction: column; gap: 2px; }
.summary-item--link { cursor: pointer; border-radius: 8px; padding: 4px 8px; margin: -4px -8px; transition: background 0.15s; }
.summary-item--link:hover { background: rgba(59,130,246,0.08); }
.summary-item--link:hover .summary-label { color: #3B82F6; }
.summary-sep   { width: 1px; height: 32px; background: var(--crm-border-strong); flex-shrink: 0; }
.summary-label { font-size: 11px; color: var(--crm-text-faint); text-transform: uppercase; letter-spacing: 0.04em; transition: color 0.15s; }
.summary-value { font-size: 15px; font-weight: 700; color: var(--crm-text); }

/* ── Detail panel ── */
.detail-panel {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  padding: 20px 24px;
  margin-bottom: 20px;
}
.detail-header {
  display: flex; align-items: center;
  margin-bottom: 16px;
}
.detail-title {
  font-size: 15px; font-weight: 600; color: var(--crm-text-secondary);
}

/* Detail KPI mini-cards */
.detail-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.detail-kpis .kpi-card {
  /* 132px даёт запас под 2-строчное значение (самая длинная сумма в проде —
     «1 109 245 278,72 ₽», см. .kpi-value ниже) без клиппинга родительским overflow:hidden */
  min-height: 132px;
  height: 100%;
}

/* ── KPI Cards (copied from DashboardView) ── */
.kpi-card {
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: default;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              box-shadow 0.25s cubic-bezier(0.22, 1, 0.36, 1),
              border-color 0.25s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--crm-border);
  background: var(--crm-surface);
  box-shadow: 0 1px 4px var(--crm-shadow);
}
.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px var(--crm-shadow-hover);
  border-color: var(--crm-border-strong);
}
.kpi-card:active {
  transform: translateY(-1px) scale(0.985);
  transition-duration: 0.1s;
}
.kpi-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: -1;
}
.kpi-card:hover::before { opacity: 1; }
.kpi-budget::before            { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-plan_schedule::before     { box-shadow: 0 0 30px rgba(245,158,11,0.15); }
.kpi-work::before              { box-shadow: 0 0 30px rgba(99,102,241,0.15); }
.kpi-ordered::before           { box-shadow: 0 0 30px rgba(59,130,246,0.15); }
.kpi-contracts::before         { box-shadow: 0 0 30px rgba(2,132,199,0.15); }
.kpi-delivered::before         { box-shadow: 0 0 30px rgba(20,184,166,0.15); }
.kpi-delivered_unpaid::before  { box-shadow: 0 0 30px rgba(239,68,68,0.15); }
.kpi-paid::before              { box-shadow: 0 0 30px rgba(34,197,94,0.15); }
.kpi-free::before              { box-shadow: 0 0 30px rgba(148,163,184,0.15); }

.kpi-icon-box {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.kpi-card:hover .kpi-icon-box { transform: scale(1.12) rotate(-3deg); }

.kpi-budget .kpi-icon-box            { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-plan_schedule .kpi-icon-box     { background: rgba(245,158,11,0.12);  color: #F59E0B; }
.kpi-work .kpi-icon-box              { background: rgba(99,102,241,0.12);  color: #6366F1; }
.kpi-ordered .kpi-icon-box           { background: rgba(59,130,246,0.12);  color: #3B82F6; }
.kpi-contracts .kpi-icon-box         { background: rgba(2,132,199,0.12);   color: #0284C7; }
.kpi-delivered .kpi-icon-box         { background: rgba(20,184,166,0.12);  color: #14B8A6; }
.kpi-delivered_unpaid .kpi-icon-box  { background: rgba(239,68,68,0.12);   color: #EF4444; }
.kpi-paid .kpi-icon-box              { background: rgba(34,197,94,0.12);   color: #22C55E; }
.kpi-free .kpi-icon-box              { background: rgba(148,163,184,0.12); color: #94A3B8; }

.kpi-budget           { border-top: 3px solid #3B82F6; }
.kpi-plan_schedule    { border-top: 3px solid #F59E0B; }
.kpi-work             { border-top: 3px solid #6366F1; }
.kpi-ordered          { border-top: 3px solid #3B82F6; }
.kpi-contracts        { border-top: 3px solid #0284C7; }
.kpi-delivered        { border-top: 3px solid #14B8A6; }
.kpi-delivered_unpaid { border-top: 3px solid #EF4444; }
.kpi-paid             { border-top: 3px solid #22C55E; }
.kpi-free             { border-top: 3px solid #94A3B8; }
.kpi-card.kpi-over { border-top-color: #EF4444; }
.kpi-over .kpi-icon-box { background: rgba(239,68,68,0.12); color: #EF4444; }

.kpi-body  { flex: 1; min-width: 0; }
.kpi-value {
  /* Чуть меньше 20px + разрешённый перенос строк — гарантия, что даже самая длинная
     сумма в проде («1 109 245 278,72 ₽», 19 символов) не будет ни обрезана,
     ни съедена многоточием, независимо от ширины карточки (проверено Playwright,
     см. отчёт в задаче: scrollHeight/scrollWidth не превышают clientHeight/clientWidth) */
  font-size: 18px;
  font-weight: 700;
  color: var(--crm-text);
  white-space: normal;
  overflow-wrap: break-word;
  word-break: break-word;
  line-height: 1.25;
}
.kpi-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  margin-top: 2px;
}
@media (max-width: 599px) {
  .kpi-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 12px;
  }
  .kpi-icon-box {
    width: 34px;
    height: 34px;
    border-radius: 8px;
  }
  .kpi-icon-box :deep(.v-icon) { font-size: 18px !important; }
  .kpi-body  { width: 100%; }
  .kpi-value { font-size: 15px; white-space: normal; overflow-wrap: break-word; word-break: break-word; line-height: 1.25; }
  .kpi-label { font-size: 10px; line-height: 1.2; white-space: normal; margin-top: 1px; }
}

/* FEO section */
.detail-feo-header {
  display: flex; align-items: center;
  margin-bottom: 12px;
}
.chart-card-title {
  font-size: 14px; font-weight: 600; color: var(--crm-text-secondary);
}
.feo-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 32px 0; color: var(--crm-text-faint);
}
.feo-purchase-link {
  display: inline-flex; align-items: center;
  font-size: 11px; color: #0d9488;
  text-decoration: none; margin-top: 2px;
  cursor: pointer;
}
.feo-purchase-link:hover { text-decoration: underline; color: #0f766e; }

/* Владелец, 2026-08-13: «остановка закупки» — крупный (для контекста строки
   плотной таблицы) маркер в красной рамке, тот же приём, что и в WishesView/
   OrdersView. Сейчас всегда скрыт (v-if на stopped_at) — см. комментарии у
   FeoActualItem/FeoReqItem/FeoPurchaseFolder.stopped_at. */
.feo-stopped-marker {
  display: inline-flex;
  align-items: center;
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 0.02em;
  color: #b71c1c;
  background: #fdecea;
  border: 1.5px solid #d32f2f;
  border-radius: 4px;
  padding: 2px 8px;
}

/* FEO table */
.feo-table-wrap {
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  overflow-x: auto;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
}
.feo-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 1100px;
}
.feo-th {
  font-size: 11px; font-weight: 600; color: var(--crm-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  background: var(--crm-table-header); padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--crm-border-strong);
  position: sticky;
  top: 0;
  z-index: 3;
  box-shadow: inset 0 -1px 0 var(--crm-border-strong);
}
.feo-th-num { text-align: right; }
.feo-th-name { }
/* table-layout:fixed — ширину колонки задаёт th: ровно под 6 значков (100px контент + 12px паддинги) */
.feo-th-actions { width: 112px; position: sticky; right: 0; z-index: 5; }
.feo-td {
  padding: 8px 12px; border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
}
.feo-td-name { min-width: 0; }
.feo-name-inner { display: flex; align-items: center; min-width: 0; }
.feo-td-num { text-align: right; }
.feo-td-actions {
  text-align: right; white-space: nowrap; padding-left: 6px; padding-right: 6px;
  position: sticky; right: 0; z-index: 2;
  background: var(--crm-surface);
  box-shadow: inset 1px 0 0 var(--crm-border-strong);
}
/* Действия: [позиции][стрелки друг под другом][квадрат 2×2] — всегда влезает в вьюпорт */
.feo-actions-wrap { display: inline-flex; align-items: center; vertical-align: middle; }
.feo-actions-wrap .v-btn { width: 24px !important; height: 24px !important; }
.feo-actions-col { display: flex; flex-direction: column; align-items: center; }
.feo-actions-grid {
  display: inline-grid; grid-template-columns: repeat(2, 26px);
  justify-items: center; align-items: center;
}
.feo-td-actions .v-btn { background: transparent !important; }
/* sticky-колонку действий держим непрозрачной во всех состояниях строки,
   иначе при горизонтальном скролле сквозь неё видны другие колонки */
.feo-tr:hover .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td-actions { background: var(--crm-surface-hover); }
.feo-action-slot { display: inline-flex; width: 24px; justify-content: center; vertical-align: middle; }
.feo-tr:last-child .feo-td { border-bottom: none; }
.feo-tr:hover .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td { background: var(--crm-surface-hover); }
.feo-plan-note { font-size: 10px; line-height: 1.2; white-space: nowrap; }
/* Кликабельная заметка «в т.ч. на самом направлении N ₽» (жалоба владельца
   2026-08-13) — раскрывает панель направления, см. feoOwnDirectionPlanFor(). */
.feo-plan-note--link { cursor: pointer; text-decoration: none; }
.feo-plan-note--link:hover { text-decoration: underline; color: #0f766e; }
/* «Заметный сигнал превышения» (план zany-fluttering-mountain.md, возвращено из отката
   e0db76a) — сознательно КРУПНЕЕ и заметнее соседних .feo-plan-note (10px, тонкий текст):
   владелец жаловался, что превышение «теряется среди чисел» — эта плашка обязана читаться
   с первого взгляда, поэтому контрастный красный фон/рамка, а не просто цвет текста. */
.feo-excess-culprit {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  font-size: 12px; font-weight: 700; line-height: 1.4; white-space: normal;
  color: #7f1d1d; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 6px; padding: 4px 8px; margin-top: 4px; max-width: 100%;
}
.feo-residual-toggle { display: flex; gap: 2px; justify-content: flex-end; margin-top: 2px; }
.feo-residual-opt {
  font-size: 9px; font-weight: 500; text-transform: none; letter-spacing: 0;
  padding: 1px 6px; border-radius: 8px; cursor: pointer;
  color: #94a3b8; border: 1px solid transparent; user-select: none;
}
.feo-residual-opt:hover { color: #475569; }
.feo-residual-opt--active { color: #0f766e; background: rgba(20,184,166,0.12); border-color: rgba(20,184,166,0.35); }
.feo-name { font-size: 13px; font-weight: 500; color: var(--crm-text); white-space: normal; word-break: break-word; min-width: 0; flex: 1; }
.feo-name--l1 { font-weight: 700; font-size: 13px; }
.feo-name--l2 { font-weight: 600; }
.feo-name--l3 { font-weight: 400; color: var(--crm-text-secondary); }
.feo-code {
  font-size: 11px; color: var(--crm-text-muted); background: var(--crm-input-bg);
  border-radius: 4px; padding: 1px 5px; font-family: monospace; white-space: nowrap;
}
.feo-appendix { font-size: 11px; color: var(--crm-text-faint); white-space: nowrap; }
.feo-amount { font-size: 13px; font-weight: 500; color: var(--crm-text); }
.feo-amount--link { cursor: pointer; text-decoration: underline dotted; }
.feo-amount--link:hover { color: #1976d2; }
.feo-amount-empty { font-size: 13px; color: var(--crm-text-faint); }
.feo-set-hint {
  font-size: 12px; color: #3B82F6; cursor: pointer; text-decoration: underline dotted;
}
.feo-set-hint:hover { color: #2563EB; }
.feo-tree-chevron { display: inline-flex; align-items: center; }
.cursor-pointer { cursor: pointer; }

/* Inline budget edit */
.feo-amount-cell { cursor: pointer; padding: 2px 4px; border-radius: 4px; display: inline-flex; align-items: center; }
.feo-amount-cell:hover { background: rgba(59,130,246,0.07); }
.feo-amount-cell--readonly { cursor: default; }
.feo-amount-cell--readonly:hover { background: none; }
.inline-input {
  border: 1px solid rgba(59,130,246,0.7); border-radius: 4px;
  padding: 2px 6px; width: 120px; text-align: right;
  font-size: 0.875rem; outline: none; background: var(--crm-surface);
  color: var(--crm-text);
}

/* Drag & Drop */
.feo-tr[draggable="true"] { cursor: grab; }
.feo-tr[draggable="true"]:active { cursor: grabbing; }
.feo-dragging { opacity: 0.45; }
.feo-dragging .feo-td { background: var(--crm-surface-alt) !important; }
.feo-drop-target .feo-td {
  background: rgba(59, 130, 246, 0.12) !important;
  outline: 2px dashed rgba(59, 130, 246, 0.6);
  outline-offset: -2px;
}
.feo-drop-root { border-top: 2px dashed var(--crm-border); transition: background 0.15s; }
.feo-drop-root.feo-drop-target .feo-td { background: rgba(59, 130, 246, 0.08) !important; }

/* Total row */
.feo-tr--total .feo-td { background: var(--crm-surface-alt); border-top: 2px solid var(--crm-border-strong); }

/* ── Dialogs ── */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}

/* Column resize handle */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  z-index: 1;
}
.col-resize-handle::before {
  content: '';
  position: absolute;
  right: 3px;
  top: 20%;
  bottom: 20%;
  width: 2px;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 2px;
  transition: all 0.15s ease;
}
.v-theme--dark .col-resize-handle::before {
  background: rgba(255, 255, 255, 0.22);
}
.col-resize-handle:hover::before,
.col-resize-handle:active::before {
  right: 2px;
  top: 5%;
  bottom: 5%;
  width: 3px;
  background: rgb(59, 130, 246);
}

/* ── FEO Column Mapping ── */
.feo-imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.feo-imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.feo-imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.feo-imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.feo-imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.feo-imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.feo-imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.feo-imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.feo-imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.feo-imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.feo-imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.feo-imap-card-x:hover { color: #e53935; }
.feo-imap-card-x--grey { color: #bbb; }
.feo-imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.feo-imap-card--free {
  background: #fafafa;
}
.feo-imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
/* 12-05 F3: snapshot tree table */
.snapshot-tree-table { width: 100%; border-collapse: collapse; }
.snapshot-tree-table th, .snapshot-tree-table td { padding: 6px 8px; border-bottom: 1px solid rgba(0,0,0,0.08); font-size: 13px; }
.snapshot-tree-table .level-1 td { font-weight: 600; background: rgba(33,150,243,0.06); }
.snapshot-tree-table .level-2 td { background: rgba(33,150,243,0.03); }
.snapshot-tree-table tfoot td { background: rgba(0,0,0,0.05); padding: 8px; border-top: 2px solid rgba(0,0,0,0.15); }
.snapshot-tree-table .status-orphan td:first-child { color: rgb(180,120,0); }

/* ── KPI drill-down: подсветка дерева ФЭО по клику на карточку ── */
.kpi-card { cursor: pointer; }
.kpi-card--active {
  outline: 2px solid #fb923c; outline-offset: -2px;
  box-shadow: 0 0 0 4px rgba(251,146,60,.22);
}
.feo-kpi-hl > .feo-td, .feo-kpi-hl > td {
  background: rgba(251,146,60,.16) !important;
  animation: feo-kpi-glow 1.4s ease-in-out infinite;
}
.feo-kpi-hl > .feo-td:first-child, .feo-kpi-hl > td:first-child { border-left: 3px solid #fb923c; }
@keyframes feo-kpi-glow {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.14); }
}
.feo-kpi-path > .feo-td:first-child { border-left: 3px solid rgba(251,146,60,.35); }
.feo-kpi-dim  > .feo-td, .feo-kpi-dim > td { opacity: .32; filter: grayscale(.5); }
.feo-kpi-dim  > .feo-td-actions { opacity: 1; filter: none; }
.feo-kpi-banner {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--crm-text-secondary);
  background: rgba(251,146,60,.10); border: 1px solid rgba(251,146,60,.35);
  border-radius: 8px; padding: 6px 12px; margin: -8px 0 16px;
}
.feo-status-strip { display: inline-flex; align-items: center; }

/* Тёмная тема: .16/.32/.14 почти сливаются с тёмной подложкой — усиливаем контраст */
.v-theme--dark .feo-kpi-hl > .feo-td,
.v-theme--dark .feo-kpi-hl > td {
  background: rgba(251,146,60,.30) !important;
  animation-name: feo-kpi-glow-dark;
}
@keyframes feo-kpi-glow-dark {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.22); }
}
.v-theme--dark .feo-kpi-dim > .feo-td,
.v-theme--dark .feo-kpi-dim > td { opacity: .22; }
</style>
