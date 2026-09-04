<template>
  <!-- Выбор ПЛАНОВОЙ ПОЗИЦИИ (единый источник /feo-categories/plan-positions —
       конечный элемент дерева ФЭО с планом, статья ФЭО с планом, или детализация
       Ур.5 FeoPlannedItem) — визуально продолжение дерева ФЭО (FeoTreeSelect): те же
       рельсы/локти (feoTreeRails.css), корневая строка — выбранная категория, ниже —
       её плановые позиции (сама категория + дочерние конечные элементы). Строка —
       <div role="switch">, обработчик клика висит на самом div (НЕ на <label>, чтобы
       браузер не удваивал клик синтетическим событием на вложенном контроле — см. баг
       в onItemRadioClick); <v-switch> внутри — чисто визуальный индикатор,
       pointer-events:none. Клик по всей строке = выбор, повторный клик
       по уже выбранной строке снимает выбор (см. onItemRadioClick).
       Псевдо-вариант «Вне плана (новая позиция)» убран (сессия 2026-08-05) — владелец:
       позицию, которой нет в плане, заводят кнопкой «Создать в плане закупок» ниже. -->
  <div v-if="categoryId != null" class="feo-planned-select" :class="{ 'feo-planned-select--dense': dense }">
    <!-- skipLast: заявка привязана к промежуточному уровню — плановые позиции недоступны -->
    <template v-if="skipLast">
      <div class="feo-tree-row feo-tree-row--pseudo feo-planned-disabled">
        <v-icon size="16" icon="mdi-clipboard-list-outline" class="mr-1" />
        <span class="feo-tree-name">Заявка привязана к промежуточному уровню ФЭО — плановые позиции недоступны</span>
      </div>
    </template>

    <template v-else>
      <div class="feo-planned-title text-caption font-weight-medium d-flex align-center ga-1 mb-1">
        <v-icon size="16" icon="mdi-clipboard-list-outline" />
        <span>Плановые позиции плана закупок</span>
      </div>

      <template v-if="loading">
        <v-skeleton-loader type="list-item-two-line@2" />
      </template>

      <template v-else>
        <!-- Корневая строка — выбранная категория, не кликается -->
        <div class="feo-tree-row feo-tree-row--root">
          <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-folder" color="#3B82F6" />
          <span class="feo-tree-name feo-tree-name--root">{{ categoryName }}</span>
        </div>

        <!-- Шаг 4 плана zany-fluttering-mountain.md: похожие по имени плановые позиции
             (POST /feo-planned-items/match) — новый блок поверх старого одиночного чипа
             suggestKey/suggestReason (тот НЕ убран — PurchaseItemsEditor.vue его тоже
             использует и не передаёт candidates, значит блок ниже там просто не рендерится,
             v-if="candidates.length"). Каждый кандидат — % совпадения + «Привязать»;
             кандидаты из чужой категории — отдельной подгруппой с пометкой (не молча). -->
        <div v-if="!readonly && candidates && candidates.length" class="feo-match-suggestions mb-2">
          <div class="text-caption text-medium-emphasis d-flex align-center ga-1 mb-1">
            <v-icon size="14" icon="mdi-auto-fix" />
            <span>Похожие плановые позиции — подтвердите выбор или выберите свою ниже</span>
          </div>
          <div
            v-for="c in sameCategoryCandidates"
            :key="'cand-' + c.key"
            class="feo-match-candidate-row"
          >
            <v-chip size="small" :color="scoreColor(c.score)" variant="tonal" class="feo-match-score">
              {{ Math.round(c.score * 100) }}%
            </v-chip>
            <span class="feo-match-name">{{ c.name }}</span>
            <v-btn size="x-small" color="primary" variant="tonal" @click="bindCandidate(c)">Привязать</v-btn>
          </div>
          <div v-if="otherCategoryCandidates.length" class="mt-1">
            <div class="text-caption text-medium-emphasis">Похожие есть и в других категориях — привязка перенесёт позицию в категорию плановой позиции:</div>
            <div
              v-for="c in otherCategoryCandidates"
              :key="'cand-other-' + c.key"
              class="feo-match-candidate-row feo-match-candidate-row--other"
            >
              <v-chip size="small" color="grey" variant="tonal" class="feo-match-score">
                {{ Math.round(c.score * 100) }}%
              </v-chip>
              <span class="feo-match-name">{{ c.name }} <span class="text-caption text-medium-emphasis">— {{ c.path }}</span></span>
              <v-btn
                size="x-small"
                color="warning"
                variant="tonal"
                :title="`Привязать и перенести позицию в категорию: ${c.path}`"
                @click="bindCandidate(c)"
              >Привязать</v-btn>
            </div>
          </div>
          <v-btn size="x-small" variant="text" color="primary" class="mt-1" @click="rejectSuggestions">
            Ни одна не подходит — выбрать вручную
          </v-btn>
        </div>

        <!-- Компактный (dense) режим — свёрнутая строка с разворотом по клику -->
        <template v-if="dense">
          <v-menu v-model="denseMenuOpen" :close-on-content-click="false" location="bottom start">
            <template #activator="{ props: menuActivatorProps }">
              <div v-bind="menuActivatorProps" class="feo-tree-row feo-planned-dense-row">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow" />
                <span class="feo-tree-name">
                  <template v-if="denseSummaryRow">{{ denseSummaryRow.name }} — план {{ fmt(denseSummaryRow.planned_amount) }} ·
                    <span :class="denseResidualDisplay!.cssClass">{{ denseResidualDisplay!.text }}</span>
                  </template>
                  <template v-else>Выбрать плановую позицию</template>
                </span>
                <v-icon size="16" icon="mdi-chevron-down" class="flex-shrink-0" />
              </div>
            </template>
            <v-card class="feo-planned-dense-menu pa-1">
              <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
                <v-btn size="x-small" variant="text" color="error" @click.stop="detachGhost">Отвязать</v-btn>
              </div>
              <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
                <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">В этой категории нет плановых позиций</span>
              </div>
              <div
                v-for="row in filteredItems"
                :key="row.key"
                class="feo-tree-row"
                :class="{ 'feo-tree-row--selected': selectedKey === row.key, 'feo-tree-row--clickable': !readonly }"
                :title="selectedKey === row.key ? 'Нажмите ещё раз, чтобы снять выбор' : undefined"
                role="switch"
                :aria-checked="selectedKey === row.key"
                :tabindex="readonly ? -1 : 0"
                @click="onItemRadioClick(row, $event)"
                @keydown.enter.prevent="onItemRadioClick(row, $event)"
                @keydown.space.prevent="onItemRadioClick(row, $event)"
              >
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <v-switch
                  :model-value="selectedKey === row.key"
                  :disabled="readonly"
                  density="compact"
                  hide-details
                  color="primary"
                  class="feo-planned-switch"
                />
                <span class="feo-tree-name">
                  {{ row.name }}
                  <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
                  <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
                  <v-chip
                    v-if="suggestKey === row.key"
                    size="x-small"
                    color="teal"
                    variant="tonal"
                    prepend-icon="mdi-auto-fix"
                    class="ml-1"
                    @click.stop="selectItem(row)"
                  >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
                </span>
                <span class="feo-tree-residual">
                  план {{ fmt(row.planned_amount) }} ·
                  <span
                    v-if="row.kind === 'planned_item'"
                    class="feo-planned-consumed-link"
                    role="button"
                    tabindex="0"
                    title="Кто расходует план — показать построчно"
                    @click.stop="openConsumers(row)"
                    @keydown.enter.stop.prevent="openConsumers(row)"
                  >выбрано {{ fmt(consumedFor(row)) }}<v-icon size="12" icon="mdi-magnify" class="ml-1" /></span>
                  <span v-else>выбрано {{ fmt(consumedFor(row)) }}</span> ·
                  <span :class="planResidualDisplay(row).cssClass">{{ planResidualDisplay(row).text }}</span>
                  <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
                </span>
                <!-- Владелец (сессия 2026-08-19): «где эта корзиночка?» — удаление плановой
                     позиции прямо из строки списка, только у kind='planned_item' (см.
                     deletePlannedItem). @click.stop — клик по кнопке НЕ должен сработать как
                     выбор строки (обработчик клика висит на самом .feo-tree-row). -->
                <v-btn
                  v-if="row.kind === 'planned_item' && !readonly"
                  icon="mdi-delete-outline"
                  variant="text"
                  size="x-small"
                  color="error"
                  class="feo-planned-delete-btn"
                  title="Удалить плановую позицию"
                  @click.stop="deletePlannedItem(row)"
                />
              </div>
              <!-- Владелец 2026-08-06: кнопка «Создать в плане закупок» доступна ВСЕГДА в
                   dense-режиме (не только когда список пуст) — если ни одна из существующих
                   плановых позиций категории не подходит для конкретного товара, должна быть
                   возможность завести новую, не переключаясь в развёрнутый режим. -->
              <div class="mt-1 px-1">
                <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" :disabled="readonly" @click.stop="openCreateEntry">
                  Создать в плане закупок
                </v-btn>
              </div>
            </v-card>
          </v-menu>
        </template>

        <!-- Обычный (развёрнутый) режим -->
        <template v-else>
          <!-- «Призрак»: modelValue указывает на позицию, которой нет в items -->
          <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
            <v-btn size="x-small" variant="text" color="error" @click="detachGhost">Отвязать</v-btn>
          </div>

          <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
            <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">В этой категории нет плановых позиций</span>
            <v-btn size="x-small" variant="text" color="primary" :disabled="readonly" @click="openCreateEntry">Создать в плане закупок</v-btn>
          </div>

          <div
            v-for="row in filteredItems"
            :key="row.key"
            class="feo-tree-row"
            :class="{ 'feo-tree-row--selected': selectedKey === row.key, 'feo-tree-row--clickable': !readonly }"
            :title="selectedKey === row.key ? 'Нажмите ещё раз, чтобы снять выбор' : undefined"
            role="switch"
            :aria-checked="selectedKey === row.key"
            :tabindex="readonly ? -1 : 0"
            @click="onItemRadioClick(row, $event)"
            @keydown.enter.prevent="onItemRadioClick(row, $event)"
            @keydown.space.prevent="onItemRadioClick(row, $event)"
          >
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <v-switch
              :model-value="selectedKey === row.key"
              :disabled="readonly"
              density="compact"
              hide-details
              color="primary"
              class="feo-planned-switch"
            />
            <span class="feo-tree-name">
              {{ row.name }}
              <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
              <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
              <v-chip
                v-if="suggestKey === row.key"
                size="x-small"
                color="teal"
                variant="tonal"
                prepend-icon="mdi-auto-fix"
                class="ml-1"
                @click.stop="selectItem(row)"
              >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
            </span>
            <span class="feo-tree-residual">
              план {{ fmt(row.planned_amount) }} ·
              <span
                v-if="row.kind === 'planned_item'"
                class="feo-planned-consumed-link"
                role="button"
                tabindex="0"
                title="Кто расходует план — показать построчно"
                @click.stop="openConsumers(row)"
                @keydown.enter.stop.prevent="openConsumers(row)"
              >выбрано {{ fmt(consumedFor(row)) }}<v-icon size="12" icon="mdi-magnify" class="ml-1" /></span>
              <span v-else>выбрано {{ fmt(consumedFor(row)) }}</span> ·
              <span :class="planResidualDisplay(row).cssClass">{{ planResidualDisplay(row).text }}</span>
              <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
            </span>
            <!-- Владелец (сессия 2026-08-19): «где эта корзиночка?» — удаление плановой
                 позиции прямо из строки списка, только у kind='planned_item' (см.
                 deletePlannedItem). @click.stop — клик по кнопке НЕ должен сработать как
                 выбор строки (обработчик клика висит на самом .feo-tree-row). -->
            <v-btn
              v-if="row.kind === 'planned_item' && !readonly"
              icon="mdi-delete-outline"
              variant="text"
              size="x-small"
              color="error"
              class="feo-planned-delete-btn"
              title="Удалить плановую позицию"
              @click.stop="deletePlannedItem(row)"
            />
          </div>

          <div class="mt-1">
            <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" :disabled="readonly" @click="openCreateEntry">
              Создать в плане закупок
            </v-btn>
          </div>
        </template>
      </template>
    </template>

    <!-- Диалог создания плановой позиции (Ур.5 FeoPlannedItem) прямо в текущей категории —
         POST /feo-planned-items/, без перехода на другую страницу и потери введённых данных
         формы (см. баг «кнопка ничего не делает», сессия 2026-08-05). -->
    <v-dialog v-model="createDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1">Новая плановая позиция</v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-2">Категория: {{ categoryName }}</div>
          <v-text-field
            v-model="createForm.name"
            label="Наименование *"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
            autofocus
          />
          <v-text-field
            v-model.number="createForm.quantity"
            type="number"
            label="Количество"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
          />
          <v-text-field
            v-model="createForm.unit"
            label="Ед. изм."
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
          />
          <!-- Цена за единицу (владелец, 2026-09-02) — необязательное поле, см. коммент
               у createForm.unitPrice выше. Задана — «Сумма плана» ниже считается сама
               (кол-во × цена) и недоступна для ручного ввода; не задана — обычное поле. -->
          <v-text-field
            v-model.number="createForm.unitPrice"
            type="number"
            label="Цена за единицу, ₽ (необязательно)"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-1"
            :hint="createForm.unitPrice == null ? UNIT_PRICE_NOT_FIXED_HINT : ''"
            :persistent-hint="createForm.unitPrice == null"
          />
          <v-text-field
            v-model.number="createForm.amount"
            type="number"
            label="Сумма плана, ₽"
            variant="outlined"
            density="compact"
            hide-details="auto"
            :readonly="createAmountIsComputed"
            :bg-color="createAmountIsComputed ? 'grey-lighten-4' : undefined"
            class="mb-1"
          />
          <div class="text-caption text-medium-emphasis mb-2" style="line-height:1.35">
            <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ createPriceCaption }}
          </div>
          <!-- Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/работа —
               необязательно, как и у остальных полей этого диалога. -->
          <v-select
            v-model="createForm.item_type"
            :items="ITEM_TYPE_OPTIONS"
            label="Тип"
            variant="outlined"
            density="compact"
            hide-details="auto"
            clearable
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="createSaving" @click="createDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="createSaving" @click="saveCreateDialog">Создать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Жалоба владельца (сессия 2026-08-19): «создаю новую позицию 10 шт — она молча
         привязывается к существующей 14 шт». POST /feo-planned-items/ теперь отдаёт 409
         planned_item_duplicate_name вместо тихого return existing_item — этот диалог
         показывает ОБА набора чисел (что уже есть / что вводит человек) и даёт выбор:
         привязаться к существующей плановой позиции или создать отдельную (allow_duplicate_name). -->
    <v-dialog v-model="duplicateDialog" max-width="460" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1">Такая позиция уже есть в плане</v-card-title>
        <v-card-text>
          <div class="mb-3">{{ duplicateInfo?.message }}</div>
          <v-table density="compact" class="mb-2">
            <thead>
              <tr><th></th><th>Кол-во</th><th class="text-right">Сумма</th></tr>
            </thead>
            <tbody>
              <tr>
                <td class="text-medium-emphasis">Уже в плане</td>
                <td>{{ duplicateInfo?.existingQuantity ?? '—' }} {{ duplicateInfo?.existingUnit || '' }}</td>
                <td class="text-right">{{ fmt(duplicateInfo?.existingAmount ?? null) }}</td>
              </tr>
              <tr>
                <td class="text-medium-emphasis">Вы вводите</td>
                <td>{{ duplicateInfo?.newQuantity ?? '—' }} {{ duplicateInfo?.newUnit || '' }}</td>
                <td class="text-right">{{ fmt(duplicateInfo?.newAmount ?? null) }}</td>
              </tr>
            </tbody>
          </v-table>
          <!-- Жалоба владельца (добор 2026-08-19): «Привязать к существующей» была
               активна, даже когда в найденной позиции остатка не было — новые числа
               молча садились поверх уже выбранных. -->
          <div v-if="attachBlockedReason" class="feo-planned-shortfall-note">{{ attachBlockedReason }}</div>
        </v-card-text>
        <v-card-actions class="flex-wrap">
          <v-spacer />
          <v-btn variant="text" :disabled="createSaving" @click="duplicateDialog = false">Отмена</v-btn>
          <v-btn
            variant="outlined"
            color="primary"
            :disabled="createSaving || attachDisabled"
            :title="attachBlockedReason || undefined"
            @click="confirmAttachDuplicate"
          >Привязать к существующей</v-btn>
          <v-btn color="primary" variant="flat" :loading="createSaving" @click="confirmCreateDuplicate">Создать отдельную</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог выбора СПОСОБА создания (владелец, сессия 2026-08-17): «Создать в плане
         закупок» на «шапочном» экземпляре (см. проп bulkItems) больше не создаёт молча
         одну позицию на имя первого товара и всю НМЦД — сначала спрашивает, как именно.
         POST /feo-planned-items/bulk — одна атомарная транзакция на все выбранные строки. -->
    <v-dialog v-model="bulkChooserDialog" max-width="640" :persistent="bulkCreating">
      <v-card>
        <v-card-title class="text-subtitle-1">Создать в плане закупок</v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-3">Категория: {{ categoryName }}</div>
          <v-radio-group v-model="bulkMode" hide-details density="compact" class="mb-3">
            <v-radio value="per_item">
              <template #label>
                <span>По плановой позиции на <b>каждый товар</b> — {{ bulkPerItemCandidates.length }}
                  {{ bulkPerItemCandidates.length === 1 ? 'позиция' : 'позиций' }}, каждая на свою сумму</span>
              </template>
            </v-radio>
            <v-radio value="single">
              <template #label>
                <span>Одна <b>общая</b> позиция на всю закупку — сумма {{ fmt(bulkTotalAmount) }}</span>
              </template>
            </v-radio>
            <v-radio value="manual">
              <template #label>
                <span>Выбрать позиции <b>вручную</b></span>
              </template>
            </v-radio>
          </v-radio-group>

          <v-text-field
            v-if="bulkMode === 'single'"
            v-model="bulkSingleName"
            label="Наименование *"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-3"
            autofocus
          />

          <div v-if="bulkMode === 'manual'" class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Отметьте позиции для создания:</div>
            <div v-for="row in props.bulkItems" :key="'manual-' + row.idx" class="d-flex align-center ga-1">
              <v-checkbox
                :model-value="manualChecked.includes(row.idx)"
                density="compact"
                hide-details
                class="flex-shrink-0"
                @update:model-value="(v: boolean | null) => toggleManualChecked(row.idx, !!v)"
              />
              <span class="text-body-2">
                {{ row.name }}
                <span class="text-caption text-medium-emphasis">— {{ fmt(row.amount) }}</span>
                <span v-if="row.linked" class="text-caption text-medium-emphasis"> (уже привязана к плановой позиции — по умолчанию не отмечена)</span>
              </span>
            </div>
          </div>

          <div class="text-caption text-medium-emphasis mb-1">Будет создано:</div>
          <v-table density="compact">
            <thead>
              <tr><th>Наименование</th><th>Кол-во</th><th class="text-right">Сумма</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in bulkPreviewRows" :key="'prev-' + (row.idx ?? 'single') + '-' + i">
                <td>{{ row.name || '—' }}</td>
                <td>{{ row.quantity ?? '—' }} {{ row.unit || '' }}</td>
                <td class="text-right">{{ fmt(row.amount) }}</td>
              </tr>
              <tr v-if="bulkPreviewRows.length === 0">
                <td colspan="3" class="text-medium-emphasis">Нечего создавать — отметьте хотя бы одну позицию</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td class="font-weight-bold">ИТОГО</td>
                <td></td>
                <td class="text-right font-weight-bold">{{ fmt(bulkPreviewTotal) }}</td>
              </tr>
            </tfoot>
          </v-table>
          <div v-if="bulkMode === 'per_item' && bulkSkippedLinkedCount > 0" class="text-caption text-medium-emphasis mt-1">
            {{ bulkSkippedLinkedCount }} {{ bulkSkippedLinkedCount === 1 ? 'позиция уже привязана' : 'позиций уже привязаны' }} к плановой позиции — пропущены.
          </div>
          <div v-if="bulkCreating" class="mt-2 d-flex align-center ga-2">
            <v-progress-circular indeterminate size="18" width="2" color="primary" />
            <span class="text-caption">Создание…</span>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="bulkCreating" @click="bulkChooserDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="bulkCreating"
            :disabled="bulkPreviewRows.length === 0 || (bulkMode === 'single' && !bulkSingleName.trim())"
            @click="runBulkCreate"
          >
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- «Кто расходует план» (владелец, 2026-08-20) — расшифровка GET
         /feo-planned-items/{id}/consumers, см. openConsumers выше. -->
    <v-dialog v-model="consumersDialog.open" max-width="760">
      <v-card>
        <v-card-title class="text-subtitle-1">
          Кто расходует план{{ consumersDialog.row ? ' — «' + consumersDialog.row.name + '»' : '' }}
        </v-card-title>
        <v-card-text>
          <div v-if="consumersDialog.loading" class="d-flex justify-center align-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="consumersDialog.error" type="error" variant="tonal" density="compact">
            {{ consumersDialog.error }}
          </v-alert>
          <template v-else-if="consumersDialog.data && consumersDialog.row">
            <!-- Итог — ТЕ ЖЕ слагаемые, что строка списка (consumedFor/residualFor
                 consumersDialog.row), НЕ пересчитаны заново: серверные
                 consumersDialog.data.consumed/residual не знают о позициях ЭТОЙ формы,
                 ещё не сохранённых на сервер (см. pendingItemsFor/группа 1 ниже) — если
                 взять их напрямую, число в диалоге разойдётся с числом в строке (жалоба
                 владельца, боевой случай: строка «выбрано 11 281», диалог «съедено 0 ₽»). -->
            <div class="text-body-2 mb-3">
              план {{ fmt(consumersDialog.row.planned_amount) }} ·
              выбрано {{ fmt(consumedFor(consumersDialog.row)) }} ·
              <span :class="planResidualDisplay(consumersDialog.row).cssClass">
                {{ planResidualDisplay(consumersDialog.row).text }}
              </span>
            </div>
            <div v-if="dialogIsEmpty" class="text-body-2 text-medium-emphasis">
              На эту плановую позицию ничего не привязано — план ещё свободен целиком.
            </div>
            <template v-else>
              <!-- Группа 1: позиции ЭТОЙ ЖЕ открытой формы — причина, по которой «выбрано»
                   в строке больше нуля даже когда сервер ещё ничего не видит (форма не
                   сохранена). -->
              <div v-if="dialogPendingItems.length" class="feo-consumers-group mb-3">
                <div class="text-caption font-weight-medium text-medium-emphasis mb-1">{{ dialogFormLabel }}</div>
                <v-table density="compact" class="feo-consumers-table">
                  <thead>
                    <tr><th>Что</th><th class="text-right">Кол-во</th><th class="text-right">Сумма</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(p, i) in dialogPendingItems" :key="'pend-' + i">
                      <td>{{ p.name }}</td>
                      <td class="text-right">{{ fmtNum(p.quantity) }} {{ p.unit || '' }}</td>
                      <td class="text-right">{{ fmt(p.amount) }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>

              <!-- Группа 2: позиции ДРУГИХ закупок, реально расходующие план (то, что
                   сервер считает в consumed) — своя (props.purchaseId) отфильтрована,
                   она уже показана группой 1. -->
              <div v-if="dialogOtherPurchases.length" class="feo-consumers-group mb-3">
                <div class="text-caption font-weight-medium text-medium-emphasis mb-1">Другие закупки, расходующие план</div>
                <v-table density="compact" class="feo-consumers-table">
                  <thead>
                    <tr>
                      <th>Что</th><th>Где</th><th>Статус</th>
                      <th class="text-right">Кол-во</th><th class="text-right">Сумма</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(c, i) in dialogOtherPurchases"
                      :key="'pur-' + i"
                      :class="{ 'feo-consumer-row--excluded': !c.counts_towards_consumed }"
                    >
                      <td>{{ c.item_name }}</td>
                      <td>
                        <a href="#" class="feo-consumer-link" @click.prevent="goToPurchase(c.purchase_id)">
                          Закупка {{ c.registry_number || ('№' + (c.purchase_number ?? c.purchase_id)) }}
                        </a>
                        <div class="text-caption text-medium-emphasis">{{ c.purchase_subject }}</div>
                        <div v-if="c.wish_id" class="text-caption text-medium-emphasis">из заявки №{{ c.wish_id }}</div>
                      </td>
                      <td>
                        {{ c.status_label }}
                        <div v-if="!c.counts_towards_consumed" class="text-caption text-medium-emphasis">
                          не входит в остаток
                        </div>
                      </td>
                      <td class="text-right">{{ fmtNum(c.quantity) }} {{ c.unit || '' }}</td>
                      <td class="text-right">{{ fmt(c.amount) }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>

              <!-- Группа 3: позиции ДРУГИХ заявок — план НЕ резервируют (резервируют
                   только после переноса в план закупок), на остаток не влияют. Своя
                   заявка (props.wishId) отфильтрована — она уже показана группой 1. -->
              <div v-if="dialogOtherWishes.length" class="feo-consumers-group">
                <div class="text-caption font-weight-medium text-medium-emphasis mb-1">
                  Другие заявки — план не резервируют, на остаток не влияют (заявка резервирует
                  план только после переноса в план закупок)
                </div>
                <v-table density="compact" class="feo-consumers-table">
                  <thead>
                    <tr>
                      <th>Что</th><th>Заявка</th><th>Статус</th>
                      <th class="text-right">Кол-во</th><th class="text-right">Сумма</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(c, i) in dialogOtherWishes" :key="'wish-' + i" class="feo-consumer-row--excluded">
                      <td>{{ c.item_name }}</td>
                      <td>
                        <div>Заявка №{{ c.wish_id }} «{{ c.wish_title }}»</div>
                        <div class="text-caption text-medium-emphasis">автор: {{ c.author_name || '—' }}</div>
                      </td>
                      <td>
                        {{ c.status_label }}
                        <div class="text-caption text-medium-emphasis">не входит в остаток</div>
                      </td>
                      <td class="text-right">{{ fmtNum(c.quantity) }} {{ c.unit || '' }}</td>
                      <td class="text-right">{{ fmt(c.amount) }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </template>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="consumersDialog.open = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import { useToast, type ToastType } from '@/composables/useToast'
import { formatPlanResidual, numOrNull } from '@/utils/numberFormat'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'

const props = defineProps<{
  modelValue: FeoPlanSelection | null
  categoryId: number | null
  nodes: FeoNode[]
  items: FeoPlanPosition[]
  /** Сумма позиций заявки — чтобы показать нехватку остатка при выборе строки. */
  amount?: number | null
  /** Составной ключ (`${kind}:${id}`) авто-подсказанной строки — см. FeoPlanPosition.key. */
  suggestKey?: string | null
  suggestReason?: string | null
  /** Шаг 4 плана zany-fluttering-mountain.md: кандидаты POST /feo-planned-items/match
   *  (похожие по имени плановые позиции, со score) — опционально; без пропа блок
   *  ниже НЕ рендерится (PurchaseItemsEditor.vue его не передаёт, back-compat). */
  candidates?: FeoMatchCandidate[]
  loading?: boolean
  readonly?: boolean
  skipLast?: boolean
  dense?: boolean
  /** Данные уже введённой позиции закупки — кнопка «Создать в плане закупок»
   *  заполняет ими форму диалога вместо пустых полей (владелец: «пусть берёт
   *  данные уже введённой позиции»). Опционально — без пропа диалог открывается
   *  пустым, как раньше. */
  prefill?: { name?: string | null; quantity?: number | null; unit?: string | null; amount?: number | null }
  /** Позиции заявки/закупки — доступны ТОЛЬКО у «шапочного» экземпляра компонента
   *  (CreateOrderView.vue/WishesView.vue, один на всю заявку/закупку), НЕ у построчных
   *  (dense-режим внутри PurchaseItemsEditor — там prefill уже про ОДНУ строку и старый
   *  однопозиционный диалог остаётся как есть). Наличие и непустота этого пропа — сигнал
   *  открывать диалог ВЫБОРА СПОСОБА вместо старого прямого диалога создания (жалоба
   *  владельца, сессия 2026-08-17: кнопка создавала ровно одну плановую позицию на имя
   *  первого товара и на всю НМЦД закупки/заявки — 6 из 7 товаров заявки теряли план). */
  bulkItems?: { idx: number; name: string; quantity: number | null; unit: string | null; amount: number | null; linked: boolean }[]
  /** Заголовок заявки/закупки — дефолт имени для варианта «одна общая позиция» (вариант б):
   *  задаётся пользователем, но предзаполняется НЕ именем первого товара (как было раньше),
   *  а названием самой заявки/закупки. */
  bulkTitle?: string | null
  /** Жалоба владельца (сессия 2026-08-19): «включаю переключатель — должно стать выбрано
   *  1500, остаток 0... а сейчас включаю-выключаю, там по-прежнему выбрано 0». row.consumed/
   *  row.residual приходят С СЕРВЕРА (/feo-categories/plan-positions, exclude_purchase_id —
   *  своя закупка НЕ учтена, это верно и не трогается), но выбор, сделанный ПРЯМО СЕЙЧАС в
   *  этой форме, в них не отражён. Карта feo_planned_item_id → сумма позиций ЭТОЙ формы
   *  (PurchaseItemsEditor.vue::pendingByPlannedItem) добавляется поверх серверных чисел —
   *  см. pendingFor/consumedFor/residualFor ниже. Только для kind==='planned_item' (id —
   *  это id FeoPlannedItem; у plan_position/feo_article своей плановой позиции нет). */
  pendingByPlannedItem?: Record<number, number> | null
  /** Расшифровка «Кто расходует план» (владелец, 2026-08-20): та же выборка, что дала
   *  pendingByPlannedItem, но самими позициями (имя/кол-во/ед./сумма) — построена в
   *  PurchaseItemsEditor.vue::pendingItemsByPlannedItem той же фильтрацией (pid != null,
   *  !over_plan). Диалог «Кто расходует план» (см. openConsumers/pendingItemsFor ниже)
   *  показывает их отдельным блоком «в этой заявке/закупке (сейчас на экране)» — это
   *  и есть причина, по которой consumedFor(row) > row.consumed с сервера, и без этого
   *  блока расшифровка молча не сходится со строкой (жалоба владельца: «съедено 0 ₽»
   *  в диалоге при «выбрано 11 281» в строке). */
  pendingItemsByPlannedItem?: Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> | null
  /** Жалоба владельца (сессия 2026-08-19): «Хочу удалить плановую позицию... где эта
   *  корзиночка?» — корзинка уже была в ШАПКЕ карточки закупки (CreateOrderView.vue::
   *  deleteHeadPlannedItem, коммит 5901986), но не в этом компоненте, через который
   *  реально идёт построчный/dense выбор. purchaseId — «откуда удаляют» (см.
   *  deletePlannedItem ниже и backend/app/routers/feo_planned_items.py::
   *  delete_planned_item) — необязателен: PurchaseItemsEditor.vue его знает и
   *  прокидывает, форма заявки (ещё не закупка) — нет, и это нормально. */
  purchaseId?: number | null
  /** Дефект 2 (владелец, 2026-08-20): «При создании заявки случайно создали плановую
   *  позицию неправильно, надо удалить» — та же роль, что purchaseId выше, но для
   *  формы ЗАЯВКИ (WishesView.vue), у которой закупки ещё нет и purchase_id взять
   *  неоткуда. wish_id уходит в DELETE (см. deletePlannedItem) — бэкенд считает
   *  ссылки wish_items ЭТОЙ заявки «своими» и снимает их молча, как purchase_id
   *  снимает ссылки своей закупки. Отдельный проп от excludeWishId ниже: тот только
   *  влияет на СЧЁТ «съедено» в GET consumers, этот — на право удалить. */
  wishId?: number | null
  /** Та же заявка/закупка, что родитель передал useFeoPlannedResiduals как
   *  excludeWishId/excludePurchaseId при загрузке props.items (WishesView.vue —
   *  editingWishId, CreateOrderView.vue/PurchaseItemsEditor.vue — purchaseId) —
   *  чтобы GET /feo-planned-items/{id}/consumers (см. openConsumers ниже) считал
   *  «съедено» ТЕМИ ЖЕ исключениями, что и уже показанное row.consumed, иначе два
   *  числа на экране разойдутся между собой. */
  excludeWishId?: number | null
  excludePurchaseId?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: FeoPlanSelection | null]
  /** Пользователь нажал «Привязать» на предложенном кандидате (Шаг 4) — родитель
   *  фиксирует, что привязку выбрал человек (флаг подтверждения, см.
   *  POST /feo-planned-items/confirm-wish-plan-match). update:modelValue тоже
   *  эмитится (сама привязка), это отдельное событие — только про подтверждение. */
  'candidate-confirmed': [candidate: FeoMatchCandidate]
  /** Плановая позиция создана диалогом «Создать в плане закупок» (POST /feo-planned-items/) —
   *  родитель должен перезагрузить список плановых позиций (напр. useFeoPlannedResiduals.reloadPlanned). */
  'planned-item-created': []
  /** Плановая позиция удалена корзинкой прямо из строки списка (см. deletePlannedItem) —
   *  родитель должен перезагрузить список плановых позиций, тем же обработчиком, что
   *  и на 'planned-item-created' (owner: «оставить перечень плановых, для возможности
   *  их удаления и высвобождения денег»). */
  'planned-item-deleted': []
  /** Диалог выбора способа (bulkItems) создал 1+ плановых позиций через
   *  POST /feo-planned-items/bulk — родитель обязан привязать каждую созданную
   *  позицию к её товару заявки/закупки по idx (results[i].idx — индекс в том же
   *  массиве, что был передан через bulkItems; null у режима «одна общая позиция»,
   *  там привязка приходит через update:modelValue как обычно). */
  'bulk-items-created': [payload: { mode: 'per_item' | 'single' | 'manual'; results: { idx: number | null; id: number }[] }]
}>()

const denseMenuOpen = ref(false)

const selectedNode = computed((): FeoNode | undefined =>
  props.categoryId != null ? props.nodes.find(n => n.id === props.categoryId) : undefined
)

const categoryName = computed((): string => selectedNode.value?.name?.trim() ?? '—')

const selectedKey = computed((): string | null =>
  props.modelValue ? `${props.modelValue.kind}:${props.modelValue.id}` : null
)

// БАГ 1 (сессия 2026-08-05): раньше фильтрация шла обходом props.nodes
// (collectDescendantIds), а nodes приходит из useFeoLeaves → filterFundedNodes,
// который ВЫРЕЗАЕТ конечные категории без собственного budget — даже если у них
// заполнены planned_quantity/planned_amount (плановая позиция). Из-за этого
// «В этой категории нет плановых позиций» показывалось для категорий, у которых
// план ЕСТЬ, просто их лист не прошёл фильтр finansирования. Бэкенд
// GET /feo-categories/plan-positions теперь отдаёт на каждой строке ancestor_ids
// (id всех предков ДО корня) — матчим напрямую по нему, без обхода дерева.
const filteredItems = computed((): FeoPlanPosition[] => {
  if (props.categoryId == null) return []
  const cid = props.categoryId
  return props.items.filter(r => r.category_id === cid || (r.ancestor_ids || []).includes(cid))
})

// modelValue ссылается на строку, которой больше нет среди актуальных (отфильтрованных
// по категории/потомкам) items — либо позицию удалили из плана закупок, либо она
// принадлежит категории вне текущей ветки дерева.
const ghostRow = computed((): boolean => {
  if (!props.modelValue) return false
  return !filteredItems.value.some(r => r.key === selectedKey.value)
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

function fmtQty(row: FeoPlanPosition): string {
  const qty = row.planned_quantity != null ? row.planned_quantity.toLocaleString('ru-RU') : '—'
  return `${qty} ${row.unit || ''}`.trim()
}

// «Занято прямо сейчас в этой форме» поверх серверных consumed/residual — см. проп
// pendingByPlannedItem выше. Только planned_item (row.id живёт в пространстве id
// FeoPlannedItem у этого kind; у plan_position/feo_article своей плановой позиции нет,
// поэтому pendingFor для них всегда 0 и consumedFor/residualFor равны серверным числам).
function pendingFor(row: FeoPlanPosition): number {
  if (row.kind !== 'planned_item') return 0
  return props.pendingByPlannedItem?.[row.id] || 0
}

function consumedFor(row: FeoPlanPosition): number {
  return row.consumed + pendingFor(row)
}

// Расшифровка «Кто расходует план» — сами позиции ЭТОЙ формы, дающие pendingFor(row)
// (см. проп pendingItemsByPlannedItem). Тот же guard kind!=='planned_item' → [].
function pendingItemsFor(row: FeoPlanPosition): { name: string; quantity: number | null; unit: string | null; amount: number }[] {
  if (row.kind !== 'planned_item') return []
  return props.pendingItemsByPlannedItem?.[row.id] || []
}

function residualFor(row: FeoPlanPosition): number {
  // row.residual с сервера уже = planned_amount − consumed (backend/app/routers/
  // feo_categories.py::spendable_remaining, без клампинга) — вычитаем pendingFor
  // отдельно, а не пересчитываем через planned_amount (может быть null у legacy строк).
  return row.residual - pendingFor(row)
}

// Единый источник числа И цвета для «остаток/превышение» строки (владелец,
// сессия 2026-08-21: «Подсвечено должно быть везде такое несоответствие» —
// раньше класс .feo-planned-shortfall вешался по isShort()/props.amount (другому
// условию — «войдёт ли ЭТА сумма»), а число печаталось из residualFor(row)
// (или вовсе сырого row.residual в развёрнутом списке) — при отрицательном
// остатке цвет мог не загореться. formatPlanResidual берёт residualFor(row)
// ОДИН раз и производит из него и текст, и класс — расхождение больше невозможно.
function planResidualDisplay(row: FeoPlanPosition) {
  return formatPlanResidual(residualFor(row))
}

function shortfall(row: FeoPlanPosition): number {
  if (props.amount == null) return 0
  // Строка row уже выбрана (selectedKey === row.key) — её собственная сумма (props.amount,
  // сумма ЭТОЙ редактируемой позиции) уже учтена в consumedFor(row) через
  // pendingByPlannedItem (карта считается по ВСЕЙ форме, включая текущую строку). Добавлять
  // props.amount поверх ещё раз значило бы посчитать одну и ту же сумму дважды. Для остальных
  // (пока не выбранных) строк props.amount — гипотетическая проверка «войдёт ли эта сумма,
  // если переключить сюда».
  const alreadySelected = selectedKey.value === row.key
  return residualFor(row) - (alreadySelected ? 0 : props.amount)
}

function isShort(row: FeoPlanPosition): boolean {
  return props.amount != null && shortfall(row) < 0
}

const KIND_CHIP_COLOR: Record<FeoPlanKind, string> = {
  plan_position: 'teal',
  feo_article: 'grey',
  planned_item: 'indigo',
}
const KIND_CHIP_LABEL: Record<FeoPlanKind, string> = {
  plan_position: 'плановая позиция',
  feo_article: 'статья ФЭО с планом',
  planned_item: 'детализация',
}
function kindChipColor(kind: FeoPlanKind): string { return KIND_CHIP_COLOR[kind] }
function kindChipLabel(kind: FeoPlanKind): string { return KIND_CHIP_LABEL[kind] }

// Разбито на структурированный computed (было — готовая строка denseSummaryLabel)
// специально ради подсветки: шаблону нужен отдельный элемент для «остаток/
// превышение», чтобы повесить на него planResidualDisplay(row).cssClass.
const denseSummaryRow = computed((): FeoPlanPosition | undefined =>
  selectedKey.value != null ? filteredItems.value.find(r => r.key === selectedKey.value) : undefined
)
const denseResidualDisplay = computed(() =>
  denseSummaryRow.value ? planResidualDisplay(denseSummaryRow.value) : null
)

function selectItem(row: FeoPlanPosition) {
  if (props.readonly) return
  emit('update:modelValue', { kind: row.kind, id: row.id })
}

// Шаг 4 плана zany-fluttering-mountain.md — кандидаты POST /feo-planned-items/match,
// разделённые на «своей категории/ветки» (можно привязать сразу) и «из другой
// категории» (показываем отдельной группой как визуальную подсказку). С 2026-09-02
// выбор кандидата из ДРУГОЙ категории (bindCandidate/selectItem ниже — оба идут через
// v-model в PATCH позиции закупки) обычному пользователю сервер отклонит 409-кой
// (PLANNED_ITEM_CATEGORY_MISMATCH, распаковывается вызывающей стороной), суперадмину
// разрешит с уведомлением — same_category тут по-прежнему только группировка в UI,
// действие не блокируется на фронте намеренно (пусть сервер даст понятную причину).
const sameCategoryCandidates = computed(() => (props.candidates || []).filter(c => c.same_category))
const otherCategoryCandidates = computed(() => (props.candidates || []).filter(c => !c.same_category))

function scoreColor(score: number): string {
  if (score >= 0.9) return 'success'
  if (score >= 0.6) return 'amber'
  return 'grey'
}

function bindCandidate(c: FeoMatchCandidate) {
  if (props.readonly) return
  emit('update:modelValue', { kind: c.kind, id: c.id })
  emit('candidate-confirmed', c)
}

function rejectSuggestions() {
  if (props.readonly) return
  // «Выбрать другую» — открыть полный список: в dense-режиме список скрыт в меню,
  // в развёрнутом он уже отображён ниже (filteredItems), просто фокус не требуется.
  if (props.dense) denseMenuOpen.value = true
}

// БАГ 2 (сессия 2026-08-05, добор 2026-08-05): изначально <input type="radio"> лежал
// ВНУТРИ <label class="feo-tree-row">, а обработчик висел на самом <input>. Клик по
// <label> браузер сам транслирует во ВТОРОЙ синтетический клик по вложенному <input> —
// onItemRadioClick срабатывал дважды за один клик пользователя: первый раз выбирал
// строку, второй тут же видел selectedKey === row.key и снимал выбор. Внешне — «клик
// ничего не делает». Исправлено: обёртка теперь <div role="switch">, обработчик висит
// на самом div (ровно один клик = ровно один вызов). Индикатор выбора (сессия
// 2026-08-06, владелец: «точка выбора не садится на позицию — сделай переключатель»)
// заменён с input[type=radio] на <v-switch> — чисто визуальный, pointer-events:none
// в CSS, своих событий не порождает. Источник правды — Vue-состояние (props.modelValue),
// а не DOM-состояние переключателя. Доступность: role="switch" + aria-checked + tabindex
// + Enter/Space.
function onItemRadioClick(row: FeoPlanPosition, event?: Event) {
  if (props.readonly) return
  event?.preventDefault()
  if (selectedKey.value === row.key) {
    emit('update:modelValue', null)
  } else {
    selectItem(row)
  }
}

function detachGhost() {
  if (props.readonly) return
  emit('update:modelValue', null)
}

// Жалоба владельца (сессия 2026-08-19): «Я не увидел здесь возможности удалять ненужные
// плановые позиции... где эта корзиночка?» — DELETE /feo-planned-items/{id}, с
// purchase_id ТЕКУЩЕЙ закупки (props.purchaseId) и/или wish_id ТЕКУЩЕЙ заявки
// (props.wishId, дефект 2, владелец 2026-08-20 — «случайно создали плановую позицию
// неправильно, надо удалить» ПРЯМО ИЗ ФОРМЫ ЗАЯВКИ, ещё до появления закупки), если они
// известны: бэкенд снимает «свои» ссылки (эта закупка + заявка, которая её породила,
// и/или сама эта заявка) молча, а если позицию держит ЧУЖАЯ закупка/заявка — отвечает
// 409 со списком держателей и ничего не меняет (см.
// backend/app/routers/feo_planned_items.py::delete_planned_item). Формулировка
// подтверждения — по образцу deleteHeadPlannedItem в CreateOrderView.vue (та же
// корзинка, но в ШАПКЕ карточки, коммит 5901986), дополнена количеством (дефект 2, п.в:
// называть позицию по имени/кол-ву/сумме, не по id). Кнопка есть только у
// kind==='planned_item' — строки уровня категории (plan_position/feo_article) это сама
// категория ФЭО дерева, их «удаление» другое, куда более опасное действие.
async function deletePlannedItem(row: FeoPlanPosition) {
  if (props.readonly || row.kind !== 'planned_item') return
  const msg = `Удалить плановую позицию «${row.name}»? Кол-во ${fmtQty(row)}, ` +
    `план ${fmt(row.planned_amount)}, сейчас выбрано ${fmt(consumedFor(row))}.`
  if (!confirm(msg)) return
  try {
    const qsParts: string[] = []
    if (props.purchaseId != null) qsParts.push(`purchase_id=${props.purchaseId}`)
    if (props.wishId != null) qsParts.push(`wish_id=${props.wishId}`)
    const qs = qsParts.length ? `?${qsParts.join('&')}` : ''
    await apiFetch(`/feo-planned-items/${row.id}${qs}`, { method: 'DELETE', suppressErrorDialog: true })
    // Удалённая позиция была выбрана в этой строке — снять выбор, чтобы не остался
    // «призрак» (см. ghostRow computed выше — он и без этого поймал бы несоответствие,
    // но снимаем явно, не дожидаясь перезагрузки родителем).
    if (selectedKey.value === row.key) {
      emit('update:modelValue', null)
    }
    emit('planned-item-deleted')
    showSnack('Плановая позиция удалена')
  } catch (e: any) {
    showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось удалить плановую позицию', 'error')
  }
}

// ───────────────────────────────────────────────────────────────────────────
// «Кто расходует план» (владелец, 2026-08-20): «Откуда у 14 футболок... остаток
// 4512? Я ничего к ним не привязывал. Я не могу это найти. Нигде этого не
// видно» — строка показывает «план X · выбрано Y · остаток Z», но КТО съел Y
// нигде не видно. Клик по «выбрано» (только у kind==='planned_item' — только
// у него есть отдельная запись FeoPlannedItem, к которой можно обратиться;
// у plan_position/feo_article «выбрано» — это сумма по всему поддереву
// категории, для неё такой расшифровки бэкенд не считает) открывает диалог
// с расшифровкой GET /feo-planned-items/{id}/consumers.
interface FeoPlannedConsumer {
  type: 'purchase' | 'wish'
  counts_towards_consumed: boolean
  item_name: string
  quantity: number | null
  unit: string | null
  amount: number
  purchase_id?: number
  purchase_number?: number | null
  registry_number?: string | null
  purchase_subject?: string | null
  wish_id?: number | null
  wish_title?: string | null
  author_name?: string | null
  status: string
  status_label: string
}
interface FeoPlannedConsumersResponse {
  planned_item_id: number
  planned_item_name: string
  planned_amount: number
  consumed: number
  residual: number
  consumers: FeoPlannedConsumer[]
}
const consumersDialog = reactive<{
  open: boolean
  loading: boolean
  error: string | null
  row: FeoPlanPosition | null
  data: FeoPlannedConsumersResponse | null
}>({ open: false, loading: false, error: null, row: null, data: null })

async function openConsumers(row: FeoPlanPosition) {
  if (row.kind !== 'planned_item') return
  consumersDialog.row = row
  consumersDialog.open = true
  consumersDialog.loading = true
  consumersDialog.error = null
  consumersDialog.data = null
  try {
    const parts: string[] = []
    if (props.excludePurchaseId != null) parts.push(`exclude_purchase_id=${props.excludePurchaseId}`)
    if (props.excludeWishId != null) parts.push(`exclude_wish_id=${props.excludeWishId}`)
    const qs = parts.length ? `?${parts.join('&')}` : ''
    consumersDialog.data = await apiFetch<FeoPlannedConsumersResponse>(
      `/feo-planned-items/${row.id}/consumers${qs}`,
    )
  } catch (e: any) {
    consumersDialog.error = e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось загрузить расшифровку расхода плана'
  } finally {
    consumersDialog.loading = false
  }
}

// Три группы расшифровки — обязаны в сумме дать ровно то же Y/Z, что строка списка
// (см. итоговую строку диалога ниже, которая берёт числа через consumedFor/residualFor(
// consumersDialog.row), а не пересчитывает их сама, чтобы гарантированно совпасть):
//   1) pendingItemsFor(row) — позиции ЭТОЙ ЖЕ открытой формы (WishesView/PurchaseItemsEditor
//      localItems), ещё не обязательно сохранённые на сервер — источник pendingFor(row);
//   2) серверные consumers типа 'purchase' из ДРУГИХ закупок (не той, что сейчас
//      редактируется — props.purchaseId, её собственные строки уже показаны группой 1);
//   3) серверные consumers типа 'wish' из ДРУГИХ заявок (не той, что сейчас редактируется —
//      props.wishId, по той же причине) — план не резервируют, показаны для полноты.
const dialogPendingItems = computed((): { name: string; quantity: number | null; unit: string | null; amount: number }[] =>
  consumersDialog.row ? pendingItemsFor(consumersDialog.row) : []
)
const dialogOtherPurchases = computed((): FeoPlannedConsumer[] =>
  (consumersDialog.data?.consumers || []).filter(c => c.type === 'purchase' && c.purchase_id !== props.purchaseId)
)
const dialogOtherWishes = computed((): FeoPlannedConsumer[] =>
  (consumersDialog.data?.consumers || []).filter(c => c.type === 'wish' && c.wish_id !== props.wishId)
)
const dialogIsEmpty = computed((): boolean =>
  dialogPendingItems.value.length === 0 && dialogOtherPurchases.value.length === 0 && dialogOtherWishes.value.length === 0
)
const dialogFormLabel = computed((): string => {
  if (props.purchaseId != null) return 'в этой закупке (сейчас на экране)'
  if (props.wishId != null) return 'в этой заявке (сейчас на экране)'
  return 'в этой форме (сейчас на экране)'
})

function goToPurchase(id: number | undefined) {
  if (id == null) return
  // Открываем в новой вкладке, а не router.push — этот диалог обычно висит
  // поверх ЕЩЁ НЕ сохранённой формы заявки/закупки (та самая, из которой его
  // открыли), уводить с неё нельзя.
  window.open(`/orders/${id}`, '_blank')
}

// БАГ 3 (сессия 2026-08-05): раньше кнопка «Создать в плане закупок» делала
// router.push('/subsidies') — уводила пользователя со страницы, теряя введённые данные
// формы, и ничего не создавала. Теперь — диалог тут же, POST /feo-planned-items/
// (контракт см. backend/app/routers/feo_planned_items.py), затем родитель
// перезагружает список ('planned-item-created') и созданная позиция выбирается сразу.
const createDialog = ref(false)
// Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/работа —
// нижний регистр, как хранится в БД (см. normalize_item_type в
// backend/app/routers/feo_planned_items.py).
const ITEM_TYPE_OPTIONS = [
  { title: 'Товар', value: 'товар' },
  { title: 'Услуга', value: 'услуга' },
  { title: 'Работа', value: 'работа' },
]
const createForm = reactive<{ name: string; quantity: number | null; unit: string; unitPrice: number | null; amount: number | null; item_type: string | null }>({
  name: '', quantity: null, unit: '', unitPrice: null, amount: null, item_type: null,
})
// Цена за единицу (владелец, 2026-09-02, дословно): «Я на самом деле не хочу
// здесь указывать количество услуг, я её знаю примерно. Я знаю сумму, которая
// у меня на это есть, это 200 000, я хочу ввести, что это примерно 20 услуг.
// При этом тогда не надо автоматически делить сумму на количество и
// препятствовать дальнейшему продвижению... Должно быть поле с ценой за
// ед. — если её вводят, тогда сумма считается путём умножения; если не
// ввели, то сумма и есть сумма, не надо делить и блокировать.»
// Пока цена задана (и не равна 0) — «Сумма плана» считается сама (кол-во ×
// цена) и недоступна для ручного ввода; иначе сумма — обычное ручное поле, как
// раньше. См. backend/app/models/feo_planned_item.py::unit_price и
// assert_tz_not_over_plan (backend/app/services/feo_plan.py) — контроль
// превышения плана следует ровно этой же семантике.
const createAmountIsComputed = computed(() => createForm.unitPrice != null && Number(createForm.unitPrice) !== 0)
function recalcCreateAmountFromUnitPrice() {
  if (!createAmountIsComputed.value) return
  const price = Number(createForm.unitPrice)
  const qty = createForm.quantity != null && Number(createForm.quantity) > 0 ? Number(createForm.quantity) : 1
  createForm.amount = Math.round(qty * price * 100) / 100
}
watch([() => createForm.quantity, () => createForm.unitPrice], () => recalcCreateAmountFromUnitPrice())
// Пояснение прямо в диалоге (владелец просил объяснить оба режима и
// последствия — «должен быть комментарий, чтобы человек понял, что он
// вводит и к чему это приведёт»), без терминов из кода.
const createPriceCaption = computed((): string =>
  createAmountIsComputed.value
    ? 'С ценой за единицу закупка по этой позиции проверяется и по цене, и по количеству, и по сумме — превысить нельзя ничего из трёх.'
    : 'Без цены за единицу количество считается ориентировочным и не ограничивает закупку — под контролем только общая сумма плана.'
)
const createSaving = ref(false)
// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

function openCreateDialog() {
  if (props.readonly || props.categoryId == null) return
  // Предзаполнение из уже введённой позиции закупки (см. prefill в defineProps),
  // с фолбэком на пустые значения — как было раньше без пропа.
  createForm.name = props.prefill?.name ?? ''
  createForm.quantity = props.prefill?.quantity ?? null
  createForm.unit = props.prefill?.unit ?? ''
  createForm.unitPrice = null
  createForm.amount = props.prefill?.amount ?? null
  createForm.item_type = null
  createDialog.value = true
}

// Владелец (сессия 2026-08-17): «должна сразу предлагать, как сделать» — на
// «шапочном» экземпляре (bulkItems передан и непуст) кнопка открывает диалог выбора
// способа вместо старого прямого диалога на одну позицию. Построчные (dense/prefill
// одной позиции внутри PurchaseItemsEditor) bulkItems не получают и продолжают
// пользоваться старым простым openCreateDialog — там кнопка и так «про эту позицию».
function openCreateEntry() {
  if (props.readonly || props.categoryId == null) return
  if (props.bulkItems && props.bulkItems.length > 0) {
    openBulkChooserDialog()
  } else {
    openCreateDialog()
  }
}

// ── Диалог выбора способа массового создания (владелец, сессия 2026-08-17) ────
const bulkChooserDialog = ref(false)
const bulkMode = ref<'per_item' | 'single' | 'manual'>('per_item')
const bulkSingleName = ref('')
const manualChecked = ref<number[]>([])
const bulkCreating = ref(false)

function toggleManualChecked(idx: number, checked: boolean) {
  if (checked) {
    if (!manualChecked.value.includes(idx)) manualChecked.value = [...manualChecked.value, idx]
  } else {
    manualChecked.value = manualChecked.value.filter(i => i !== idx)
  }
}

function openBulkChooserDialog() {
  bulkMode.value = 'per_item'
  bulkSingleName.value = props.bulkTitle?.trim() || ''
  // По умолчанию отмечены позиции БЕЗ существующей привязки к плановой позиции —
  // владелец: «уже привязанные по умолчанию не отмечать и пояснить почему».
  manualChecked.value = (props.bulkItems || []).filter(r => !r.linked).map(r => r.idx)
  bulkChooserDialog.value = true
}

const bulkTotalAmount = computed((): number =>
  (props.bulkItems || []).reduce((s, r) => s + (Number(r.amount) || 0), 0)
)

// Вариант (а) «по позиции на каждый товар» — пропускает уже привязанные к плановой
// позиции строки (иначе плодили бы вторую плановую позицию поверх уже существующей).
const bulkPerItemCandidates = computed(() => (props.bulkItems || []).filter(r => !r.linked))
const bulkSkippedLinkedCount = computed(() => (props.bulkItems || []).filter(r => r.linked).length)

interface BulkPreviewRow {
  idx: number | null
  name: string
  quantity: number | null
  unit: string | null
  amount: number | null
}

const bulkPreviewRows = computed((): BulkPreviewRow[] => {
  if (bulkMode.value === 'single') {
    const name = bulkSingleName.value.trim()
    if (!name) return []
    return [{ idx: null, name, quantity: null, unit: null, amount: bulkTotalAmount.value }]
  }
  if (bulkMode.value === 'manual') {
    return (props.bulkItems || [])
      .filter(r => manualChecked.value.includes(r.idx))
      .map(r => ({ idx: r.idx, name: r.name, quantity: r.quantity, unit: r.unit, amount: r.amount }))
  }
  // per_item
  return bulkPerItemCandidates.value.map(r => ({ idx: r.idx, name: r.name, quantity: r.quantity, unit: r.unit, amount: r.amount }))
})

const bulkPreviewTotal = computed((): number =>
  bulkPreviewRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0)
)

async function runBulkCreate() {
  if (props.categoryId == null) return
  const rows = bulkPreviewRows.value
  if (!rows.length) return
  bulkCreating.value = true
  try {
    const resp = await apiFetch<{ items: { id: number }[] }>('/feo-planned-items/bulk', {
      method: 'POST',
      body: JSON.stringify({
        items: rows.map(r => ({
          feo_category_id: props.categoryId,
          name: r.name,
          quantity: r.quantity,
          unit: r.unit || null,
          amount: r.amount,
        })),
      }),
    })
    const results = resp.items.map((it, i) => ({ idx: rows[i].idx, id: it.id }))
    bulkChooserDialog.value = false
    emit('planned-item-created')
    emit('bulk-items-created', { mode: bulkMode.value, results })
    if (bulkMode.value === 'single' && results[0]) {
      emit('update:modelValue', { kind: 'planned_item', id: results[0].id })
    }
    showSnack(`Плановых позиций создано/привязано: ${results.length}`)
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось создать плановые позиции', 'error')
  } finally {
    bulkCreating.value = false
  }
}

// Жалоба владельца (сессия 2026-08-19): 409 planned_item_duplicate_name — бэкенд
// (backend/app/routers/feo_planned_items.py, create_planned_item) отдаёт данные
// обеих позиций вместо тихого слияния. duplicateInfo хранит и то, чем отвечать
// при «Создать отдельную» (allow_duplicate_name: true, тот же payload).
interface DuplicateInfo {
  message: string
  existingItemId: number
  existingQuantity: number | null
  existingUnit: string | null
  existingAmount: number | null
  newQuantity: number | null
  newUnit: string | null
  newAmount: number | null
}
const duplicateDialog = ref(false)
const duplicateInfo = ref<DuplicateInfo | null>(null)

// Жалоба владельца (добор сессии 2026-08-19): диалог показывал только «план»
// существующей позиции, без «выбрано»/«остаток» — «Привязать к существующей»
// оставалась активной, даже когда там уже выбрано 14 из 14 и человек садил новые
// 10 шт поверх. duplicateInfo (из тела 409) содержит только собственный план
// позиции (existing_item.quantity/amount), НЕ её выбранность — это есть только
// в props.items (единый источник consumed/residual, см. useFeoPlannedResiduals),
// поэтому строку ищем там по existingItemId (kind всегда 'planned_item' — дедуп
// на бэке идёт по FeoPlannedItem, см. create_planned_item).
const duplicateExistingRow = computed((): FeoPlanPosition | null => {
  const id = duplicateInfo.value?.existingItemId
  if (id == null) return null
  return props.items.find(r => r.kind === 'planned_item' && r.id === id) ?? null
})

// Допуск как у соседних сравнений остатков в проекте (PurchaseItemsEditor.vue,
// SubsidiesView.vue) — количество в БД Numeric(15,4), точное сравнение ловило бы
// ложные «не влезает» на округлении с плавающей точкой.
const RESIDUAL_EPS = 0.0001

function fmtNum(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU')
}

// Не найдена строка в props.items — ведём себя как раньше (кнопка активна,
// сравнивать остаток не с чем).
const attachBlockedReason = computed((): string | null => {
  const row = duplicateExistingRow.value
  const info = duplicateInfo.value
  if (!row || !info) return null
  const amountShort = info.newAmount != null && info.newAmount > row.residual + RESIDUAL_EPS
  const qtyShort = info.newQuantity != null && row.residual_quantity != null
    && info.newQuantity > row.residual_quantity + RESIDUAL_EPS
  if (!amountShort && !qtyShort) return null
  const qtyPart = row.planned_quantity != null
    ? `выбрано ${fmtNum(row.consumed_quantity)} из ${fmtNum(row.planned_quantity)} ${row.unit || ''}`.trim() + ' '
    : 'выбрано '
  return `в этой плановой позиции не осталось места: ${qtyPart}(${fmt(row.consumed)} из ${fmt(row.planned_amount)}), остаток ${fmt(row.residual)}`
})

const attachDisabled = computed((): boolean => attachBlockedReason.value != null)

// Владелец (жалоба 2026-09-04, скриншот): «Цена за единицу, ₽ (необязательно)»
// оставляли пустой → 422 «ожидается число». createForm.* типизирован number|null,
// но v-model.number на очищенном поле реально кладёт туда '' (Vue's looseToNumber,
// не NaN/null) — quantity/unitPrice/amount без явного приведения уходили на сервер
// как есть. numOrNull — общий хелпер (см. @/utils/numberFormat.ts, тот же, что и
// в SubsidiesView.vue::savePlannedItem/saveEditPlannedItem) — '' → null, 0 остаётся 0.
function buildCreatePayload(allowDuplicate: boolean) {
  return {
    feo_category_id: props.categoryId,
    name: createForm.name.trim(),
    quantity: numOrNull(createForm.quantity),
    unit: createForm.unit.trim() || null,
    unit_price: numOrNull(createForm.unitPrice),
    amount: numOrNull(createForm.amount),
    item_type: createForm.item_type,
    allow_duplicate_name: allowDuplicate,
  }
}

async function saveCreateDialog() {
  if (props.categoryId == null) return
  if (!createForm.name.trim()) {
    showSnack('Укажите наименование', 'error')
    return
  }
  createSaving.value = true
  try {
    const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
      method: 'POST',
      body: JSON.stringify(buildCreatePayload(false)),
    })
    createDialog.value = false
    emit('planned-item-created')
    emit('update:modelValue', { kind: 'planned_item', id: created.id })
    showSnack('Плановая позиция создана')
  } catch (e: any) {
    const det = e?.payload?.details
    if (e?.status === 409 && det?.error_code === 'planned_item_duplicate_name') {
      duplicateInfo.value = {
        message: det.message || e.message,
        existingItemId: det.existing_item_id,
        existingQuantity: det.existing_item_quantity != null ? Number(det.existing_item_quantity) : null,
        existingUnit: det.existing_item_unit ?? null,
        existingAmount: det.existing_item_amount != null ? Number(det.existing_item_amount) : null,
        newQuantity: det.new_quantity != null ? Number(det.new_quantity) : null,
        newUnit: det.new_unit ?? null,
        newAmount: det.new_amount != null ? Number(det.new_amount) : null,
      }
      duplicateDialog.value = true
    } else {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
    }
  } finally {
    createSaving.value = false
  }
}

// «Привязать к существующей» — тот же путь выбора, что и клик по строке списка
// (selectItem): просто выбираем уже существующую плановую позицию, ничего не создаём.
function confirmAttachDuplicate() {
  if (!duplicateInfo.value || attachDisabled.value) return
  emit('update:modelValue', { kind: 'planned_item', id: duplicateInfo.value.existingItemId })
  duplicateDialog.value = false
  createDialog.value = false
}

// «Создать отдельную» — повторный POST с allow_duplicate_name: true (тот же payload
// формы, дедуп на бэке осознанно пропущен), затем выбираем созданную позицию.
async function confirmCreateDuplicate() {
  if (props.categoryId == null) return
  createSaving.value = true
  try {
    const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
      method: 'POST',
      body: JSON.stringify(buildCreatePayload(true)),
    })
    duplicateDialog.value = false
    createDialog.value = false
    emit('planned-item-created')
    emit('update:modelValue', { kind: 'planned_item', id: created.id })
    showSnack('Плановая позиция создана')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
  } finally {
    createSaving.value = false
  }
}
</script>

<style scoped src="./feoTreeRails.css"></style>
<style scoped>
.feo-planned-select {
  margin-top: 4px;
}
.feo-planned-title {
  color: var(--crm-text-secondary);
}
.feo-planned-disabled {
  cursor: default;
  opacity: 0.85;
}
.feo-planned-switch {
  flex-shrink: 0;
  margin-top: -4px;
  margin-bottom: -4px;
  /* Отступ до подписи (владелец 2026-08-06: текст «прилипал» к переключателю без
     зазора) — 10px, как padding-left стандартного <v-switch><label> в форме (см.
     «Не указывать последний уровень ФЭО» в WishesView.vue: там label получает его
     из Vuetify по умолчанию, а тут подпись — соседний <span class="feo-tree-name">
     без своего label/padding, поэтому зазор нужно задать явно). */
  margin-right: 8px;
  /* Чисто визуальный индикатор — клик обрабатывается на обёртке .feo-tree-row (div
     role="switch"), не на самом переключателе (иначе браузер генерит второй
     синтетический клик по клику на обёртке — двойное срабатывание onItemRadioClick,
     см. комментарий в <script setup>). */
  pointer-events: none;
}
.feo-planned-switch :deep(.v-selection-control) {
  min-height: unset;
}
.feo-planned-select .feo-tree-row--clickable {
  cursor: pointer;
}
.feo-planned-select .feo-tree-row:not(.feo-tree-row--clickable) {
  cursor: default;
}
.feo-planned-select .feo-tree-row--clickable:focus-visible {
  outline: 2px solid #3B82F6;
  outline-offset: -2px;
}
.feo-planned-qty {
  margin-left: 6px;
}
.feo-planned-shortfall {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-shortfall-note {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-consumed-link {
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 2px;
}
.feo-planned-consumed-link:hover,
.feo-planned-consumed-link:focus-visible {
  color: #3B82F6;
  outline: none;
}
.feo-consumers-table :deep(td) {
  vertical-align: top;
}
.feo-consumer-row--excluded {
  opacity: 0.6;
}
.feo-consumer-link {
  color: #3B82F6;
  text-decoration: none;
}
.feo-consumer-link:hover {
  text-decoration: underline;
}
.feo-planned-delete-btn {
  flex-shrink: 0;
  margin-left: 2px;
  /* Оптический центр по первой строке текста — тот же приём, что у
     .feo-tree-chevron/.feo-tree-row-icon выше (row теперь align-items:flex-start). */
  margin-top: calc((var(--feo-row-line) - 24px) / 2);
}
.feo-planned-ghost {
  color: #EF4444;
}
.feo-planned-ghost .feo-tree-name {
  color: #EF4444;
}
.feo-planned-dense-row {
  cursor: pointer;
}
.feo-planned-dense-menu {
  max-height: 360px;
  overflow-y: auto;
  min-width: 320px;
}
.feo-match-suggestions {
  border: 1px dashed #14B8A6;
  border-radius: 8px;
  padding: 8px;
  background: rgba(20, 184, 166, 0.06);
}
.feo-match-candidate-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}
.feo-match-candidate-row--other {
  opacity: 0.75;
}
.feo-match-score {
  flex-shrink: 0;
  min-width: 44px;
  justify-content: center;
}
.feo-match-name {
  flex: 1 1 auto;
  font-size: 13px;
}
</style>
