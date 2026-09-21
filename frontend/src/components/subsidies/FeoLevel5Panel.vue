<template>
  <!-- ── Level 5 панель: Плановые vs Фактические ──
       Условие расширено (!node.hasChildren || hasOwnPlannedAmountFor(node)) — у
       направления панель раскрывается, только если есть чем её наполнить. -->
  <!-- Владелец 21.09.2026: панель открывается у ЛЮБОГО узла (в т.ч. у направления
       без собственных позиций — пустая, с кнопкой «Добавить плановую»), иначе
       первую позицию на направление добавить неоткуда. -->
  <tr v-if="ctx.expandedItemPanels.value.has(node.id)" :data-feo-panel-for="node.id">
    <td colspan="7" style="padding:0">
      <div style="padding:10px 0 12px 0">
        <div class="d-flex align-center mb-2" style="gap:8px">
          <v-btn v-if="ctx.displayPlannedRowsFor(node).length > 1" size="x-small" variant="text" color="teal"
            :prepend-icon="ctx.anyPlannedExpandedFor(node) ? 'mdi-arrow-collapse-vertical' : 'mdi-arrow-expand-vertical'"
            @click="ctx.toggleAllPlannedItemsForCategory(node)"
          >{{ ctx.anyPlannedExpandedFor(node) ? 'Свернуть всё' : 'Развернуть всё' }}</v-btn>
          <!-- Задача владельца, п.12 волны 3 (2026-09-13): массовый выбор плановых
               позиций + перенос выбранных в другую категорию ФЭО. Тулбар виден,
               только когда в ЭТОЙ категории что-то отмечено (feoLevel5.selectedIdsForNode
               проецирует общий Set выбора на строки узла). -->
          <template v-if="feoLevel5.someSelectedForNode(node)">
            <v-chip size="small" color="orange" variant="tonal">
              Выбрано: {{ feoLevel5.selectedIdsForNode(node).length }}
            </v-chip>
            <v-btn size="x-small" variant="tonal" color="orange-darken-1" prepend-icon="mdi-folder-move-outline"
              @click="feoLevel5.openBulkMoveDialog(node)">
              Перенести в категорию
            </v-btn>
            <v-btn size="x-small" variant="text" color="grey-darken-1"
              @click="feoLevel5.clearSelectionForNode(node)">
              Снять выбор
            </v-btn>
          </template>
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
              <th :style="[nameColStyle, { paddingLeft: `${ctx.plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;text-align:left;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE" title="Плановая позиция. Закупки, привязанные к ней (как выставили в закупку / как в договоре — по стадии), — в раскрывающемся блоке под строкой плана.">
                <div class="d-flex align-center" style="gap:2px">
                  <v-checkbox-btn
                    v-if="feoLevel5.selectableRowsFor(node).length > 0"
                    density="compact" color="orange-darken-1"
                    :model-value="feoLevel5.allSelectedForNode(node)"
                    :indeterminate="!feoLevel5.allSelectedForNode(node) && feoLevel5.someSelectedForNode(node)"
                    title="Выбрать все плановые позиции категории"
                    style="flex:0 0 auto"
                    @click.stop
                    @update:model-value="feoLevel5.toggleSelectAllForNode(node)"
                  />
                  <span>Позиция плана</span>
                </div>
              </th>
              <th :style="feoResize.resizeStyle('budget')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Плановая цена за единицу</th>
              <th :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Кол-во плана</th>
              <th :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Сумма плана</th>
              <th style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE">Тип</th>
              <!-- Задача владельца, п.15 волны 4 (2026-09-13): «на каком этапе находится
                   данная закупка» — свободное место сразу после «Тип». Переиспользуем
                   колонку 'spent' — в этой конкретной (Ур.5) таблице она и так всегда
                   пустая (её обычный смысл «В плане-графике» — метрика КАТЕГОРИИ, см.
                   FeoTreeTable.vue, у отдельной плановой позиции её нет и не может быть),
                   новую колонку не заводим — не сдвигает ширины остальных (feoResize
                   общий на всё дерево ФЭО, см. докстринг ниже про singleton). -->
              <th :style="feoResize.resizeStyle('spent')" style="padding:4px 8px;text-align:center;color:#1e40af;font-weight:600;border-bottom:1px solid #BFDBFE" title="Стадии закупок, привязанных к этой плановой позиции. Свёрнуто — полоска долей (сколько закупок на какой стадии), развёрнуто (кнопка «План vs факт» ниже) — список закупок с их текущим статусом.">Стадия закупки</th>
              <th :style="feoResize.resizeStyle('residual')" style="border-bottom:1px solid #BFDBFE"></th>
              <th style="width:112px;min-width:112px;max-width:112px;padding:4px 2px;border-bottom:1px solid #BFDBFE"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(planned, pIdx) in ctx.displayPlannedRowsFor(node)" :key="`p-${planned.id}`">
              <!-- data-feo-planned-item-id — цель прокрутки+подсветки поиска по субсидии
                   (useFeoTreeSearch.ts::scrollAndHighlight), тот же приём, что и
                   data-feo-node-id у строки категории (FeoTreeRow.vue). -->
              <tr style="border-bottom:1px solid #E5E7EB" :data-feo-planned-item-id="planned.id">
                <td :style="[nameColStyle, { paddingLeft: `${ctx.plannedItemIndentPx(node)}px` }]" style="padding-top:4px;padding-right:8px;padding-bottom:4px;color:#0c4a6e">
                  <div class="d-flex align-center" style="gap:2px">
                    <!-- Задача владельца, п.12 волны 3: чекбокс массового выбора — только у
                         настоящих записей (ручная псевдо-строка isManual не может переноситься
                         пачкой, у неё нет отдельной FeoPlannedItem-записи в базе). -->
                    <v-checkbox-btn
                      v-if="!planned.isManual"
                      density="compact" color="orange-darken-1"
                      :model-value="feoLevel5.isPlannedItemSelected(planned.id)"
                      style="flex:0 0 auto"
                      @click.stop
                      @update:model-value="feoLevel5.togglePlannedItemSelected(planned.id)"
                    />
                    <!-- Задача 2 (владелец, «Создать закупку на основе плана»): ручной план
                         категории (isManual, id = −node.id — уже уникален в общем Set выбора,
                         Правило №6) выбирается ТОЙ ЖЕ галочкой/функцией, что и настоящие записи
                         выше — второй механизм выбора не заводим, разница только в id. Видна
                         ТОЛЬКО в режиме «Создать закупку на основе плана» (usePlanToRequest.ts):
                         вне этого режима у ручного плана нет операции, для которой имел бы смысл
                         этот чекбокс (массовый перенос категорий его не поддерживает — см. условие
                         выше, selectableRowsFor тоже исключает isManual). При подтверждении выбора
                         usePlanToRequest.ts::materializeSelectedManualPlans заменяет −node.id на id
                         только что созданной настоящей FeoPlannedItem (задача 2). -->
                    <v-checkbox-btn
                      v-else-if="planToRequest.active.value"
                      density="compact" color="orange-darken-1"
                      :model-value="feoLevel5.isPlannedItemSelected(planned.id)"
                      style="flex:0 0 auto"
                      title="Выбрать ручной план категории — при подтверждении выбора он станет настоящей плановой позицией"
                      @click.stop
                      @update:model-value="feoLevel5.togglePlannedItemSelected(planned.id)"
                    />
                    <!-- Задача владельца, п.11 волны 3 (2026-09-13): «нужна нумерация, иначе
                         неудобно искать, где что находится и после чего, когда запланировано
                         несколько сотен позиций». Номер — позиция в ТЕКУЩЕМ видимом порядке
                         (тот же sort_order.nulls_last(), id, что и в списке — см.
                         displayPlannedRowsFor/pIdx), не id из базы. Префикс перед названием, а
                         не отдельная колонка — таблица и так плотно упакована (7+ управляющих
                         кнопок в последней колонке, узкие ширины из feoResize), новая колонка
                         сдвинула бы все border/colspan расчёты по всему файлу без выигрыша:
                         номер и так стоит прямо перед именем, там же, где его ищут глазами. -->
                    <span class="feo-plan-num text-medium-emphasis" title="Порядковый номер в текущем порядке списка">{{ pIdx + 1 }}.</span>
                    <v-btn
                      :icon="ctx.expandedPlannedItems.value.has(planned.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                      variant="text" density="compact" size="x-small" color="teal"
                      title="Показать/скрыть закупки, привязанные к этой плановой позиции"
                      @click="ctx.togglePlannedItemFolder(planned.id)"
                    />
                    <span>{{ planned.name }}</span>
                  </div>
                  <!-- Шильдики происхождения (владелец, Волна 5, 2026-09-14): «от
                       статусов остались только обрезанные слова» — в узкой (плотной,
                       resizable) колонке 'name' v-chip внутри d-flex БЕЗ переноса
                       сжимался наравне с остальными flex-элементами строки заголовка,
                       текст обрезался («пла», «по (», «внутр»). Вынесены в отдельную
                       строку с flex-wrap (feo-plan-origin-row, см. <style> ниже) —
                       чипы не участвуют в сжатии однострочного заголовка и переносятся
                       на следующую строку целиком, не обрезаясь. -->
                  <div class="feo-plan-origin-row">
                    <v-chip size="x-small" color="blue-grey" variant="tonal" style="font-size:9px;height:16px"
                      title="Это плановая позиция — она запланирована, а не выставлена в закупку и не приехала по факту"
                    >план</v-chip>
                    <v-chip v-if="node.hasChildren" size="x-small" color="grey" variant="tonal" style="font-size:9px;height:16px"
                      title="Позиция привязана к направлению, а не к конечной категории. Её можно перенести вниз, в подходящую категорию — суммы при этом не изменятся."
                    >на направлении целиком</v-chip>
                    <v-chip v-if="!planned.isManual && planned.is_feo_breakdown" size="x-small" color="green" variant="tonal" style="font-size:9px;height:16px"
                      title="По ФЭО — жёсткая построчная разбивка ФЭО, покупать будут именно это, отчётность строгая"
                    >по ФЭО</v-chip>
                    <v-chip v-if="!planned.isManual && planned.is_internal_plan" size="x-small" color="amber-darken-3" variant="tonal" style="font-size:9px;height:16px"
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
                  <!-- Задача владельца, п.15б/Волна 5 (2026-09-14): позиция с ОБЕИМИ
                       галочками (по ФЭО + внутренний план) показывала одну и ту же
                       цифру под двумя подписями — цифры теперь РАЗНЫЕ (feo_unit_price
                       у строки «по ФЭО», unit_price — «внутренний план», см.
                       feoUnitPriceFor ниже), подсвечено цветом каждого происхождения.
                       Непроставленная галочка — строка не рисуется вовсе. Для ручного
                       плана (isManual) деления «по ФЭО/внутренний план» не существует
                       — там прежнее поведение без подписи. -->
                  <template v-if="!planned.isManual && (planned.is_feo_breakdown || planned.is_internal_plan)">
                    <div v-if="planned.is_feo_breakdown" class="feo-origin-split feo-origin-split--feo">
                      <span v-if="feoUnitPriceFor(planned) != null">{{ formatCurrency(Number(feoUnitPriceFor(planned))) }}</span>
                      <span v-else class="text-medium-emphasis" style="font-size:10px;line-height:1.3">{{ UNIT_PRICE_NOT_FIXED_HINT }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--feo">по ФЭО</div>
                    </div>
                    <div v-if="planned.is_internal_plan" class="feo-origin-split feo-origin-split--internal" :class="planned.is_feo_breakdown ? 'mt-1' : ''">
                      <span v-if="planned.unit_price != null">{{ formatCurrency(Number(planned.unit_price)) }}</span>
                      <span v-else class="text-medium-emphasis" style="font-size:10px;line-height:1.3">{{ UNIT_PRICE_NOT_FIXED_HINT }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--internal">внутренний план</div>
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="planned.unit_price != null">{{ formatCurrency(Number(planned.unit_price)) }}</span>
                    <span v-else-if="planned.amount != null" class="text-medium-emphasis" style="font-size:10px;line-height:1.3">{{ UNIT_PRICE_NOT_FIXED_HINT }}</span>
                  </template>
                </td>
                <td :style="feoResize.resizeStyle('qty')" style="padding:4px 8px;text-align:right;color:#64748b">
                  <!-- Тот же принцип разбивки, что и у «Плановой цены за единицу»
                       выше (задача владельца, Волна 5, 2026-09-14: «то же самое
                       нужно в Кол-во плана и Сумма плана») — единообразно во всех
                       трёх колонках, строка только для реально стоящей галочки. -->
                  <template v-if="!planned.isManual && (planned.is_feo_breakdown || planned.is_internal_plan)">
                    <div v-if="planned.is_feo_breakdown" class="feo-origin-split feo-origin-split--feo">
                      <span v-if="feoQuantityFor(planned) != null">{{ parseFloat(String(feoQuantityFor(planned))) }} {{ planned.unit || '' }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--feo">по ФЭО</div>
                    </div>
                    <div v-if="planned.is_internal_plan" class="feo-origin-split feo-origin-split--internal" :class="planned.is_feo_breakdown ? 'mt-1' : ''">
                      <span v-if="planned.quantity">{{ parseFloat(String(planned.quantity)) }} {{ planned.unit || '' }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--internal">внутренний план</div>
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="planned.quantity">{{ parseFloat(String(planned.quantity)) }} {{ planned.unit || '' }}</span>
                  </template>
                </td>
                <td :style="feoResize.resizeStyle('planned')" style="padding:4px 8px;text-align:right;color:#64748b">
                  <template v-if="!planned.isManual && (planned.is_feo_breakdown || planned.is_internal_plan)">
                    <div v-if="planned.is_feo_breakdown" class="feo-origin-split feo-origin-split--feo">
                      <span v-if="feoAmountFor(planned) != null">{{ formatCurrency(Number(feoAmountFor(planned))) }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--feo">по ФЭО</div>
                    </div>
                    <div v-if="planned.is_internal_plan" class="feo-origin-split feo-origin-split--internal" :class="planned.is_feo_breakdown ? 'mt-1' : ''">
                      <span v-if="planned.amount">{{ formatCurrency(planned.amount) }}</span>
                      <div class="feo-origin-split__label feo-origin-split__label--internal">внутренний план</div>
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="planned.amount">{{ formatCurrency(planned.amount) }}</span>
                  </template>
                </td>
                <td style="width:74px;min-width:74px;padding:4px 8px;text-align:center;color:#64748b">
                  <span
                    v-if="planned.item_type_inherited"
                    class="text-medium-emphasis"
                    title="Тип взят из позиций закупок — у самой плановой позиции он не задан"
                  >{{ planned.item_type_effective }}</span>
                  <span v-else>{{ planned.item_type_effective || '—' }}</span>
                  <!-- Раздел C0 (план ancient-prancing-music.md, 2026-09-21): позиция
                       без типа не участвует в контролях превышения по типу
                       (useFeoTreeExcess.ts::typeExcessFor/backend kind_of) — явная
                       подсказка вместо молчаливого выпадения из подсчёта. -->
                  <v-icon v-if="!planned.item_type_effective" icon="mdi-alert-circle-outline" size="12" color="amber-darken-3"
                    class="ml-1" title="укажите тип — иначе не участвует в контроле по типам"
                  />
                  <!-- Комментарии к плановой позиции (владелец, Волна 4, п.16, правка
                       2026-09-14) — «отображается после поля Тип»: сразу под значением
                       типа, в этой же ячейке (новую колонку не заводим — таблица
                       плотная, см. докстринг задачи). Жалоба владельца: «переключатель
                       просто показывает или выключает иконку... она должна быть видна
                       постоянно» — иконка теперь видна ВСЕГДА для настоящих записей
                       (!isManual — у ручной псевдо-строки нет id FeoPlannedItem);
                       общий переключатель субсидии (FeoTreeRow.vue) больше не прячет
                       иконку, а массово разворачивает/сворачивает ветки — см. watch на
                       feoComments.expandAllSignal ниже. -->
                  <div v-if="!planned.isManual" class="mt-1">
                    <!-- Счётчик комментариев (владелец, 2026-09-15) — виден ДО
                         раскрытия, тот же принцип, что и у категории в
                         FeoTreeRow.vue (см. её докстринг): по нему сразу видно,
                         есть ли комментарии и сколько, не открывая ветку. Клик
                         по иконке по-прежнему просто переключает раскрытие —
                         работает и при count = 0 (иначе некуда писать первый
                         комментарий). НЕ v-badge — см. докстринг классов
                         .feo-comment-icon-wrap/.feo-comment-count-badge в
                         styles/subsidies.css (живой QA нашёл: v-badge
                         перекрывает x-small-иконку и перехватывает клик мимо
                         кнопки). Классы общие с FeoTreeRow.vue — второй способ
                         рисовать тот же бейдж не заводим. -->
                    <span class="feo-comment-icon-wrap">
                      <v-btn
                        :icon="commentCountFor(planned.id) > 0 ? 'mdi-comment-text' : 'mdi-comment-text-outline'"
                        variant="text" density="compact" size="x-small"
                        :color="commentsExpandedIds.has(planned.id) ? 'teal' : 'grey-darken-1'"
                        title="Комментарии к этой плановой позиции"
                        @click.stop="toggleCommentsForItem(planned.id)"
                      />
                      <span v-if="commentCountFor(planned.id) > 0" class="feo-comment-count-badge">{{ commentCountFor(planned.id) }}</span>
                    </span>
                  </div>
                </td>
                <td :style="feoResize.resizeStyle('spent')" style="padding:4px 8px;vertical-align:top">
                  <!-- Свёрнуто (нет ни одной раскрытой строки закупок под позицией) — полоска
                       долей по стадиям; развёрнуто — список закупок с текущим статусом каждой
                       (владелец, п.15 волны 4). Нет закупок вовсе — колонка честно молчит
                       (внешний v-if), не рисует пустую полоску. -->
                  <template v-if="feoLevel5.purchasesForPlanned(node.id, planned.id).length">
                    <template v-if="!ctx.expandedPlannedItems.value.has(planned.id)">
                      <div class="feo-stage-bar" :title="feoLevel5.stageBreakdownTitle(node.id, planned.id)">
                        <span
                          v-for="seg in feoLevel5.stageBreakdownFor(node.id, planned.id)"
                          :key="seg.key"
                          class="feo-stage-bar__seg"
                          :style="{ width: seg.pct + '%', background: seg.color }"
                        />
                      </div>
                      <div class="feo-stage-bar__caption">Закупок: {{ feoLevel5.purchasesForPlanned(node.id, planned.id).length }}</div>
                    </template>
                    <template v-else>
                      <div
                        v-for="p in feoLevel5.purchasesForPlanned(node.id, planned.id)"
                        :key="`stage-${p.purchase_id}`"
                        class="feo-stage-list-row"
                      >
                        <a
                          href="javascript:void(0)"
                          class="feo-purchase-link"
                          :title="`Перейти в закупку ${p.registry_number || ('#' + p.purchase_id)}`"
                          @click.stop="ctx.router.push(`/orders/${p.purchase_id}`)"
                        >{{ p.registry_number || (p.purchase_number != null ? `№ ${p.purchase_number}` : `#${p.purchase_id}`) }}</a>
                        <span class="feo-stage-list-row__status" :style="{ color: purchaseStatusColor(p.purchase_status) }">{{ purchaseStatusLabel(p.purchase_status) }}</span>
                      </div>
                    </template>
                  </template>
                </td>
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
              <!-- Ветка комментариев плановой позиции (владелец, Волна 4, п.16) —
                   раскрывающийся блок под строкой, не колонка (см. докстринг задачи
                   про плотную таблицу). Тот же переиспользуемый FeoCommentThread.vue,
                   что и у категории в FeoTreeRow.vue (Правило №6 — второй копии нет). -->
              <tr v-if="!planned.isManual && commentsExpandedIds.has(planned.id)">
                <td colspan="8" style="padding:0">
                  <div style="margin:6px 8px 10px 32px;padding:8px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px">
                    <FeoCommentThread :feo-planned-item-id="planned.id" :subsidy-id="subsidyId" />
                  </div>
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
                        <!-- Задача владельца, п.15б: заголовок «ФАКТ (из закупок)» стоял
                             прямо перед денежной колонкой «Сумма (факт)» и читался как
                             задвоенная сумма. Это заголовок ГРУППЫ колонок факта (имя
                             позиции/ссылка на закупку), а не число — переименован так,
                             чтобы не выглядеть суммой; данные строки не менялись. -->
                        <th style="padding:4px 8px;text-align:left;color:#0f766e;font-weight:600;border-bottom:1px solid #99F6E4" title="Реальные закупки, привязанные к этой плановой позиции — что действительно куплено или заказано">Фактическая позиция</th>
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

        <!-- Раздел C0 (план ancient-prancing-music.md, 2026-09-21): подытоги
             товары/услуги/без типа по СТРОКАМ ЭТОЙ панели — считаются на клиенте
             (kindOf, единственный источник правила на фронте — utils/
             itemTypeKind.ts, та же формула, что и на бэкенде kind_of) из уже
             отображаемых displayPlannedRowsFor(node), второй запрос не шлём. -->
        <div v-if="ctx.displayPlannedRowsFor(node).length" class="feo-level5-type-subtotals">
          товары: {{ formatCurrency(typeSubtotals.goods.sum) }} ({{ typeSubtotals.goods.count }} поз.)
          · услуги: {{ formatCurrency(typeSubtotals.services.sum) }} ({{ typeSubtotals.services.count }} поз.)
          <span v-if="typeSubtotals.unspecified.count > 0">
            · без типа: {{ formatCurrency(typeSubtotals.unspecified.sum) }} ({{ typeSubtotals.unspecified.count }} поз.)
          </span>
        </div>

        <!-- Диалог массового переноса (п.12 волны 3) — рендерится ТОЛЬКО в панели,
             которая его открыла (bulkMoveActiveNodeId === node.id): состояние
             диалога общее на все панели (синглтон useFeoLevel5), а не привязано к
             конкретному узлу — без этой проверки при нескольких одновременно
             раскрытых категориях каждая нарисовала бы свой <v-dialog> на общий
             v-model, и все открылись бы разом. Категория-приёмник выбирается тем
             же деревом, что и везде в проекте (FeoTreeSelect) — второй свой пикер
             не заводим. -->
        <v-dialog v-if="feoLevel5.bulkMoveActiveNodeId.value === node.id" v-model="feoLevel5.bulkMoveDialogOpen.value" max-width="640" persistent>
          <v-card>
            <v-card-title class="text-subtitle-1">
              Перенести {{ feoLevel5.bulkMoveItemIds.value.length }} плановых позиций в другую категорию
            </v-card-title>
            <v-card-text>
              <div v-if="feoLevel5.bulkMoveLoadingTree.value" class="d-flex align-center" style="gap:8px;padding:8px 0">
                <v-progress-circular indeterminate size="16" color="orange-darken-1" />
                <span class="text-caption">Загрузка дерева категорий...</span>
              </div>
              <FeoTreeSelect
                v-else
                v-model="feoLevel5.bulkMoveTargetCategoryId.value"
                :nodes="feoLevel5.bulkMoveNodes.value"
                :leaves="feoLevel5.bulkMoveLeaves.value"
                label="Категория-приёмник"
                required
              />
              <div v-if="feoLevel5.bulkMoveFailures.value.length" class="mt-3 text-caption text-error">
                <div class="font-weight-medium mb-1">Не удалось перенести ({{ feoLevel5.bulkMoveFailures.value.length }}):</div>
                <div v-for="f in feoLevel5.bulkMoveFailures.value" :key="f.name">«{{ f.name }}» — {{ f.error }}</div>
              </div>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" :disabled="feoLevel5.bulkMoveSubmitting.value" @click="feoLevel5.closeBulkMoveDialog()">Отмена</v-btn>
              <v-btn color="orange-darken-1" variant="tonal"
                :loading="feoLevel5.bulkMoveSubmitting.value"
                :disabled="!feoLevel5.bulkMoveTargetCategoryId.value"
                @click="feoLevel5.submitBulkMove()"
              >Перенести</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

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
import { useFeoLevel5Api } from '@/composables/subsidies/useFeoLevel5'
import { usePlanToRequest } from '@/composables/subsidies/usePlanToRequest'
import { formatCurrency } from '@/composables/subsidies/format'
import { leftGroupInfo, withNameColumnFloor } from '@/composables/subsidies/feoCategoryUtils'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { purchaseStatusLabel, purchaseStatusColor } from '@/constants/purchaseStatus'
import type { FeoNode, FeoPlannedItem } from '@/composables/subsidies/types'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { computed, reactive, watch } from 'vue'
import { useFeoComments } from '@/composables/subsidies/useFeoComments'
import FeoCommentThread from './FeoCommentThread.vue'
// Раздел C0 (план ancient-prancing-music.md, 2026-09-21) — единственный
// источник правила «тип позиции → товары/услуги» на фронте (зеркалит
// backend/app/services/item_type_split.py::kind_of, ПРАВИЛО №6, второй
// разбор item_type здесь не пишем). ⚠️ Файл пишет параллельный агент —
// на момент написания этого компонента ещё не существовал, импорт по
// согласованному пути; npx vue-tsc --noEmit перепроверить, когда появится.
import { kindOf } from '@/utils/itemTypeKind'

const props = defineProps<{ node: FeoNode }>()
const node = props.node

const ctx = useSubsidyDetailCtx()
// useResizableColumns() НЕ singleton — создаёт новый colWidths при каждом вызове
// (см. её докстринг). Единственный экземпляр 'feo-table' живёт в SubsidiesView.vue
// и приходит через ctx.feoResize — иначе у каждого узла была бы своя, не связанная
// с основной таблицей ширина колонок (см. комментарий в FeoTreeTable.vue).
const feoResize = ctx.feoResize
// Нижний порог ширины «Наименование» (координатор, регресс приёмки 2026-09-20
// №2) — эта панель рисует СВОЮ <table> (table-layout:fixed внутри неё считает
// ширины независимо от внешнего дерева), поэтому оборачивает feoResize.resizeStyle
// тем же порогом отдельно (feoCategoryUtils.ts, Правило №6 — общая формула).
// Чекбокс массового выбора здесь виден при bulk-move ИЛИ режиме «Создать
// закупку на основе плана» независимо от их состояния — всегда берём порог
// «с чекбоксом» (true), а не гоняемся за тем, показан ли он в конкретный момент.
const nameColStyle = computed(() => withNameColumnFloor(feoResize.resizeStyle('name'), true))
// Массовый выбор/перенос плановых позиций (п.12 волны 3, 2026-09-13) — берём
// напрямую из синглтона useFeoLevel5, а не через ctx: SubsidyDetailContext
// (SubsidiesView.vue) собирается параллельным исполнителем этой же волны в
// файле, который трогать нельзя. useFeoLevel5Api() возвращает уже построенный
// SubsidiesView.vue синглтон (см. её докстринг) — второй экземпляр состояния
// не заводится, это тот же объект, что и ctx.movePlannedItemToCategory и т.п.
const feoLevel5 = useFeoLevel5Api()
// «Создать закупку на основе плана» (задача 2) — только для видимости чекбокса
// у ручных планов (isManual), см. докстринг в шаблоне выше.
const planToRequest = usePlanToRequest()

// Комментарии к плановым позициям (владелец, Волна 4, п.16) — переиспользуем
// ОДИН FeoCommentThread.vue (та же копия, что и у категории в FeoTreeRow.vue,
// см. её докстринг про Правило №6) + общий флаг видимости субсидии из
// useFeoComments.ts (загружается в FeoTreeRow.vue при монтировании дерева —
// здесь читаем уже закэшированное значение, второй сетевой запрос не шлём).
const feoComments = useFeoComments()
const subsidyId = computed(() => ctx.selectedId.value)
// Раскрытые ветки — локальный набор ЭТОЙ панели (per-node UI-состояние, не
// разделяемые данные), reactive(Set) даёт корректную реактивность на add/delete.
const commentsExpandedIds = reactive(new Set<number>())
function toggleCommentsForItem(plannedId: number) {
  if (commentsExpandedIds.has(plannedId)) commentsExpandedIds.delete(plannedId)
  else commentsExpandedIds.add(plannedId)
}

// Счётчик комментариев плановой позиции (владелец, 2026-09-15) — тот же
// общесубсидийный кэш, что и у категории в FeoTreeRow.vue (см. её докстринг
// про loadCounts/ПРАВИЛО №6). Панель раскрывается позже строки дерева — на
// момент монтирования кэш обычно уже загружен FeoTreeRow.vue (та же
// субсидия), но вызов здесь всё равно безопасен: loadCounts дедуплицирует
// параллельные запросы и просто вернёт уже закэшированное значение, второй
// сетевой запрос не уйдёт.
if (subsidyId.value != null) void feoComments.loadCounts(subsidyId.value)
function commentCountFor(plannedId: number): number {
  return feoComments.plannedItemCommentCount(subsidyId.value, plannedId)
}

// Общий переключатель субсидии (FeoTreeRow.vue) — жалоба владельца (2026-09-14):
// «при включении видимости комментариев должны все комментарии разворачиваться»
// (индивидуальный клик по иконке ветки продолжает работать как раньше и не
// переопределяется этим сигналом навсегда — см. докстринг expandAllSignal в
// useFeoComments.ts). Второй механизм не заводим — подписываемся на ТОТ ЖЕ
// синглтон-сигнал, что уже слушает FeoTreeRow.vue для своих категорий.
watch(
  () => feoComments.expandAllSignal.version,
  () => {
    const sig = feoComments.expandAllSignal
    if (sig.version === 0) return // начальное значение — сигнала ещё не было
    if (sig.subsidyId !== subsidyId.value) return
    if (sig.expanded) {
      // Жалоба владельца 2026-09-15: массовое раскрытие открывает ТОЛЬКО
      // позиции, где комментарии реально есть — пустые «Комментариев пока
      // нет — будьте первым» больше не разворачиваются сами по себе.
      for (const pl of ctx.displayPlannedRowsFor(node)) {
        if (!pl.isManual && commentCountFor(pl.id) > 0) commentsExpandedIds.add(pl.id)
      }
    } else {
      commentsExpandedIds.clear()
    }
  },
)

// Раздельные числа по ФЭО (владелец, Волна 5, 2026-09-14) — см. докстринг
// FeoPlannedItem.feo_quantity/feo_unit_price/feo_amount (backend/app/models/
// feo_planned_item.py). Второй, независимый комплект чисел заполняется ТОЛЬКО
// когда обе галочки происхождения стояли разом и человек явно ввёл число «по
// ФЭО» отдельно от «внутреннего плана» (диалоги добавления/правки). Если он
// NULL (не задан — единственная галочка «по ФЭО», либо обе галочки, но числа
// совпадают и второй ввод не понадобился) — строка «по ФЭО» честно показывает
// ТО ЖЕ число, что и «план» (quantity/unit_price/amount), а не пустоту: это
// единственное число, которое вообще есть у позиции, и по определению это и
// есть «число по ФЭО» для этого случая (см. отчёт задачи, п.1).
function feoUnitPriceFor(p: FeoPlannedItem): number | null {
  return p.feo_unit_price != null ? Number(p.feo_unit_price) : (p.unit_price != null ? Number(p.unit_price) : null)
}
function feoQuantityFor(p: FeoPlannedItem): number | null {
  return p.feo_quantity != null ? Number(p.feo_quantity) : (p.quantity != null ? Number(p.quantity) : null)
}
function feoAmountFor(p: FeoPlannedItem): number | null {
  return p.feo_amount != null ? Number(p.feo_amount) : (p.amount != null ? Number(p.amount) : null)
}

// Раздел C0 — подытоги товары/услуги/без типа по строкам панели (см. докстринг
// в шаблоне выше). kindOf принимает item_type_effective строки (уже с учётом
// наследования от позиций закупок, см. resolve_effective_item_types на
// бэкенде) — псевдо-строка ручного плана (isManual) не имеет этого поля и
// честно попадает в «без типа».
const typeSubtotals = computed(() => {
  const acc = {
    goods: { sum: 0, count: 0 },
    services: { sum: 0, count: 0 },
    unspecified: { sum: 0, count: 0 },
  }
  for (const row of ctx.displayPlannedRowsFor(node)) {
    const kind = kindOf((row as any).item_type_effective)
    const bucket = acc[kind as 'goods' | 'services' | 'unspecified'] || acc.unspecified
    bucket.sum += Number(row.amount || 0)
    bucket.count += 1
  }
  return acc
})
</script>

<style scoped>
/* Номер позиции в текущем видимом порядке списка (п.11 волны 3) — префикс
   перед названием, не отдельная колонка (см. комментарий у v-for в шаблоне). */
.feo-plan-num {
  flex: 0 0 auto;
  min-width: 16px;
  font-size: 10px;
  text-align: right;
}

/* Шильдики происхождения/статуса позиции (владелец, Волна 5, 2026-09-14):
   ДЕФЕКТ — на скриншоте владельца текст обрезан до огрызков («пла», «по (»,
   «внутр»). Причина: раньше чипы жили ВНУТРИ строки заголовка (d-flex
   align-center БЕЗ переноса) вперемешку с чекбоксом/номером/кнопкой-стрелкой —
   в узкой (плотной, resizable) колонке 'name' flex сжимал все элементы строки
   разом, а v-chip обрезает свой текст ellipsis при недостатке места. Вынесены
   в отдельную строку ПОД заголовком с flex-wrap: каждый чип — flex:0 0 auto
   (не сжимается никогда), при нехватке ширины переносится на новую строку
   ЦЕЛИКОМ, а не обрезается посимвольно. */
.feo-plan-origin-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  row-gap: 3px;
  margin-top: 2px;
}
.feo-plan-origin-row :deep(.v-chip) {
  flex: 0 0 auto;
  white-space: nowrap;
  /* Vuetify задаёт чипу max-width:100% относительно flex-контейнера — в узкой
     фиксированной колонке 'name' (resizeStyle задаёт px-ширину) это ровно то,
     что резало текст («внутренний» без «план»), даже с flex:0 0 auto (та
     правка не даёт чипу СЖИМАТЬСЯ, но не мешает Vuetify ограничить его
     максимальную ширину контейнером). none — чип всегда по размеру своего
     текста, обрезание больше невозможно. */
  max-width: none;
}
.feo-plan-origin-row :deep(.v-chip__content) {
  white-space: nowrap;
  overflow: visible;
  text-overflow: unset;
}

/* Раздельные числа по ФЭО/внутреннему плану (задача владельца, Волна 5) —
   единообразная подсветка происхождения во всех трёх колонках («Плановая цена
   за единицу», «Кол-во плана», «Сумма плана»), а не только в первой. */
.feo-origin-split__label {
  font-size: 10px;
  line-height: 1.2;
}
.feo-origin-split--feo .feo-origin-split__label {
  color: #15803d; /* тот же зелёный, что и у чипа «по ФЭО» (color="green") */
}
.feo-origin-split--internal .feo-origin-split__label {
  color: #b45309; /* тот же янтарный, что и у чипа «внутренний план» (amber-darken-3) */
}

/* Колонка «Стадия закупки» (п.15 волны 4): свёрнутая полоска долей по стадиям
   + подпись, развёрнутый список закупок со статусом. Элементы — прямые дети
   шаблона ЭТОГО компонента (не дочернего SFC), scoped CSS их достаёт. */
.feo-stage-bar {
  display: flex;
  align-items: stretch;
  width: 100%;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: #E5E7EB;
}
.feo-stage-bar__seg {
  display: block;
  height: 100%;
}
.feo-stage-bar__caption {
  margin-top: 3px;
  font-size: 10px;
  color: #94A3B8;
  white-space: nowrap;
}
.feo-stage-list-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  font-size: 10px;
  line-height: 1.6;
  white-space: nowrap;
  overflow: hidden;
}
.feo-stage-list-row .feo-purchase-link {
  overflow: hidden;
  text-overflow: ellipsis;
}
.feo-stage-list-row__status {
  font-weight: 600;
  flex-shrink: 0;
}

/* Раздел C0 (план ancient-prancing-music.md, 2026-09-21): подытоги товары/
   услуги/без типа под таблицей плановых позиций панели. */
.feo-level5-type-subtotals {
  margin-top: 6px;
  padding: 4px 8px;
  font-size: 11px;
  color: #64748b;
}
</style>
