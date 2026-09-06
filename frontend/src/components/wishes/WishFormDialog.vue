<template>
  <!-- ── CREATE/EDIT DIALOG ── -->
  <v-dialog v-model="wishDialog" max-width="1600" width="95vw" scrollable persistent :fullscreen="mobile">
    <v-card class="wish-dialog">
      <v-overlay v-model="wishDialogLoading" contained class="align-center justify-center" persistent>
        <div class="d-flex flex-column align-center ga-3">
          <v-progress-circular indeterminate size="56" width="5" color="primary" />
          <div class="text-body-2 text-medium-emphasis">Загрузка позиций…</div>
        </div>
      </v-overlay>
      <v-card-title class="pa-4 pb-2 d-flex align-center justify-space-between">
        <span>{{ editingWishId ? `Заявка №${editingWishId} — редактирование` : 'Новая заявка' }}</span>
        <!-- Phase 31-07: Undo/Redo кнопки -->
        <div class="d-flex ga-1 align-center">
          <v-btn
            :disabled="!undoRedoWish.canUndo.value"
            icon="mdi-undo"
            size="x-small"
            variant="text"
            :color="undoRedoWish.canUndo.value ? '#fb923c' : undefined"
            title="Отменить (Ctrl+Z)"
            @click="undoRedoWish.undo()"
          />
          <v-btn
            :disabled="!undoRedoWish.canRedo.value"
            icon="mdi-redo"
            size="x-small"
            variant="text"
            :color="undoRedoWish.canRedo.value ? '#fb923c' : undefined"
            title="Повторить (Ctrl+Y)"
            @click="undoRedoWish.redo()"
          />
        </div>
      </v-card-title>
      <!-- B6 — от кого/кому/дата/статус -->
      <v-card-subtitle v-if="editingWish" class="pa-4 pt-0 d-flex flex-wrap" style="gap:16px">
        <div><b>От кого:</b> <span class="font-weight-medium">{{ ctx.shortName(editingWish.creator_name) || '—' }}</span><span
          v-if="ctx.wishCoAuthors(editingWish).length" class="text-medium-emphasis">, {{ ctx.wishCoAuthors(editingWish).join(', ') }}</span></div>
        <div><b>Кому:</b> {{ ctx.wishRecipients(editingWish) || '—' }}</div>
        <div><b>Создано:</b> {{ ctx.formatDate(editingWish.created_at) }}</div>
        <div v-if="editingWish.status"><b>Статус:</b> {{ statusLabel[editingWish.status] || editingWish.status }}</div>
        <div v-if="editingWish.executor_name"><b>Исполнитель:</b> {{ editingWish.executor_name }}</div>
        <div v-if="editingWish.execution_deadline"><b>Срок исполнения:</b> {{ ctx.formatDate(editingWish.execution_deadline) }}</div>
      </v-card-subtitle>
      <!-- Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил» -->
      <div v-if="editingWish && editingWish.status === 'rejected'" class="px-4 pb-3">
        <v-alert type="error" variant="tonal" density="compact" icon="mdi-close-circle-outline">
          {{ ctx.rejectedByLine(editingWish) }}
        </v-alert>
      </div>
      <v-card-text class="pa-4">
        <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт в красной рамке на всю ширину -->
        <div v-if="editingWish?.stopped_at" class="wish-stopped-banner wish-stopped-banner--large mb-3">
          <v-icon icon="mdi-alert-octagon" size="26" class="mr-2" />
          <div>
            <div class="wish-stopped-banner__title">{{ editingWish.stopped_partial ? 'ЗАЯВКА ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</div>
            <div class="wish-stopped-banner__meta">{{ ctx.stoppedByLine(editingWish) }}</div>
            <div v-if="editingWish.stopped_partial" class="wish-stopped-banner__meta mt-1">
              Часть закупок этой заявки уже прошла договор (и не останавливается) — точный список пока не отдаётся с сервера построчно. Проверьте статус позиций в разделе «Закупки».
            </div>
          </div>
        </div>
        <!-- T3: v-alert для ошибки «нет даты потребности» -->
        <v-alert
          v-if="wishConvertError"
          type="error"
          variant="tonal"
          class="mb-3"
          closable
          @click:close="wishConvertError = null"
        >
          <div class="font-weight-medium mb-1">Не удалось передать в план закупок</div>
          <div style="white-space:pre-wrap">{{ wishConvertError.message }}</div>
          <div v-if="wishConvertError.missingItemNames.length" class="mt-2">
            <span class="font-weight-medium">Позиции без даты:</span>
            <ul class="ml-4 mt-1">
              <li v-for="name in wishConvertError.missingItemNames" :key="name">{{ name }}</li>
            </ul>
          </div>
        </v-alert>
        <v-alert
          v-if="!isWishEditable && canAssigneeAct"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          Вы согласующий. Проверьте позиции и используйте кнопки ниже — «Распределить и одобрить», «Быстрое одобрение» или «Отклонить».
        </v-alert>
        <v-alert
          v-else-if="!isWishEditable && isDialogCreator && wishForm.status === 'submitted'"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          Заявка отправлена на согласование — редактирование недоступно. Вернуть можно, только если согласующий отклонит её.
        </v-alert>
        <v-alert
          v-else-if="!isWishEditable"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          Заявка в статусе «{{ statusLabel[wishForm.status] || wishForm.status }}» — редактирование недоступно. Редактировать можно только черновик или отклонённую заявку.
        </v-alert>
        <v-form ref="wishFormRef" @submit.prevent>

          <!-- Баннер: редактирование одобренной/конвертированной заявки -->
          <v-alert
            v-if="editingWish && ['approved', 'converted'].includes(editingWish.status) && !editingWish.contracted_locked"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-4"
            icon="mdi-alert-outline"
          >
            После изменения заявка уйдёт на повторное согласование
          </v-alert>

          <!-- Баннер: заявка заблокирована договором -->
          <v-alert
            v-if="editingWish && editingWish.contracted_locked"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-4"
            icon="mdi-lock-outline"
          >
            Редактирование запрещено: заявка привязана к закупке — {{ editingWish.contracted_locked_reason || 'на этапе договора или позже' }}
          </v-alert>

          <!-- Section 1: Основная информация -->
          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2">mdi-information-outline</v-icon>Основная информация
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-row dense>
                <v-col cols="12">
                  <v-text-field
                    v-model="wishForm.title"
                    label="Предмет заявки"
                    variant="outlined"
                    density="compact"
                    clearable
                    :readonly="!isWishEditable"
                    hint="Краткое название заявки. Если оставить пустым — сформируется из позиций"
                    persistent-hint
                    data-field="title"
                  />
                </v-col>
                <v-col cols="12">
                  <v-select
                    v-model="wishForm.subsidy_id"
                    :items="ctx.subsidies.value"
                    item-title="name"
                    item-value="id"
                    label="Субсидия *"
                    variant="outlined"
                    density="compact"
                    :rules="[v => !!v || 'Выберите субсидию']"
                    clearable
                    :readonly="!isWishEditable"
                    data-field="subsidy_id"
                    @update:model-value="onSubsidyChange"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="wishForm.desired_date"
                    :label="wishDateMode === 'per_item' ? 'Общая дата поставки (по умолчанию)' : 'Желаемая дата поставки/исполнения'"
                    type="date"
                    variant="outlined"
                    density="compact"
                    prepend-inner-icon="mdi-truck-delivery-outline"
                    :readonly="!isWishEditable"
                    persistent-hint
                    :hint="wishForm.execution_deadline ? 'Задан «Срок исполнения» — он перебивает эту дату при переносе в план закупок' : 'К этой дате нужна поставка/исполнение. Нужна для переноса в план закупок'"
                    :error-messages="serverFieldErrors.desired_date"
                    @update:model-value="serverFieldErrors.desired_date = ''"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <div class="text-caption font-weight-medium mb-1">Дата поставки</div>
                  <!-- Мобильный фикс (владелец, 2026-09-04): .mobile-toggle-wrap тянет тумблер
                       на всю ширину и переносит текст внутри кнопки на вторую строку. -->
                  <v-btn-toggle
                    v-model="wishDateMode"
                    color="primary"
                    density="compact"
                    variant="outlined"
                    divided
                    mandatory
                    :disabled="!isWishEditable"
                    :class="{ 'mobile-toggle-wrap': mobile }"
                  >
                    <v-btn value="common" size="small" prepend-icon="mdi-calendar">Одна на заявку</v-btn>
                    <v-btn value="per_item" size="small" prepend-icon="mdi-calendar-multiple">На каждую позицию</v-btn>
                  </v-btn-toggle>
                  <v-btn
                    v-if="wishDateMode === 'per_item' && isWishEditable"
                    size="small"
                    variant="text"
                    color="primary"
                    class="mt-1"
                    prepend-icon="mdi-calendar-sync-outline"
                    :disabled="!wishForm.desired_date"
                    @click="applyCommonDateToAllItems"
                  >
                    Проставить эту дату всем позициям
                  </v-btn>
                </v-col>
                <!-- Task 2 (сессия 2026-08-17): контрагент заявки — необязательное поле. -->
                <v-col cols="12" data-field="contractor">
                  <div class="text-caption font-weight-medium mb-1">Контрагент <span class="text-medium-emphasis">(необязательно)</span></div>
                  <v-row v-if="isWishEditable || canAssigneeAct" dense>
                    <v-col cols="12" md="6">
                      <ContractorPicker
                        v-model="wishForm.contractor_id"
                        :initial-contractor="wishContractorInitial"
                        label="Из справочника"
                        hint="Необязательно. Поиск по названию или ИНН"
                        @select="onWishContractorSelect"
                      />
                    </v-col>
                    <v-col cols="12" md="6">
                      <v-text-field
                        v-model="wishForm.contractor_name"
                        label="Или впишите имя вручную"
                        variant="outlined"
                        density="compact"
                        clearable
                        hint="Если контрагента ещё нет в справочнике"
                        persistent-hint
                      />
                    </v-col>
                  </v-row>
                  <div v-else class="text-body-2">
                    {{ editingWish?.contractor_display_name || wishForm.contractor_name || '—' }}
                  </div>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- Section 2: Позиции -->
          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2">mdi-format-list-numbered</v-icon>Позиции
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-switch
                v-if="wishForm.subsidy_id"
                v-model="wishForm.feo_per_item"
                label="Разные категории ФЭО для каждого товара"
                density="compact"
                color="primary"
                hide-details
                class="mb-3"
                :disabled="!isWishEditable"
                @update:model-value="onWishFeoPerItemChange"
              />
              <!-- data-field="feo_category" — цель для highlightMissingFeoCategory. -->
              <div data-field="feo_category">
                <template v-if="!wishForm.feo_per_item">
                  <v-alert v-if="wishFeoStale" type="warning" density="compact" variant="tonal" class="mb-2">
                    Категория ФЭО, выбранная в заявке, была удалена из справочника (структуру ФЭО субсидии
                    пересоздавали). Выберите актуальную категорию и сохраните. Если согласовать как есть —
                    закупка будет создана без категории ФЭО, её можно задать в «Плане закупок».
                  </v-alert>
                  <v-alert
                    v-if="wishFeoCategoryMissing"
                    type="error"
                    density="compact"
                    variant="tonal"
                    class="mb-2"
                    icon="mdi-alert-octagon-outline"
                  >
                    <div class="font-weight-medium">Конечная категория ФЭО не выбрана — отправить заявку на согласование нельзя</div>
                    <div class="mt-1">
                      Без конечной категории закупка не попадёт ни в один план ФЭО и её сумма потеряется.
                      Выберите категорию ниже, углубившись до самого конечного уровня дерева, а если
                      категория неизвестна — нажмите «Не определена».
                    </div>
                  </v-alert>
                  <template v-if="wishForm.subsidy_id && !(canEditWishFeo && !isWishEditable)">
                    <FeoTreeSelect
                      v-model="wishFeoSelected"
                      :nodes="wishFeoTreeNodes"
                      :leaves="wishFeoLeaves"
                      :plan-positions="wishPlannedResiduals"
                      :node-amounts="wishNodeAmounts"
                      horizontal
                      :readonly="!isWishEditable && !canEditWishFeo"
                      :allow-unallocated="!!(wishForm.subsidy_id && (isWishEditable || canEditWishFeo))"
                      :root-label="selectedSubsidyName"
                      @pick-unallocated="(parentId: number | null) => pickWishUnallocated(parentId)"
                    />
                  </template>
                </template>
                <template v-else>
                  <v-alert v-if="wishItemsWithStaleFeoCategory.length" type="warning" density="compact" variant="tonal" class="mb-2">
                    У части позиций категория ФЭО была удалена из справочника (структуру ФЭО субсидии
                    пересоздавали). Выберите актуальную категорию у этих позиций и сохраните — иначе
                    закупка будет создана без категории ФЭО.
                    <ul class="ml-4 mt-1">
                      <li v-for="(it, idx) in wishItemsWithStaleFeoCategory" :key="'stale-' + idx">{{ it.item_name || 'без названия' }}</li>
                    </ul>
                  </v-alert>
                  <v-alert
                    v-if="wishFeoCategoryMissing"
                    type="error"
                    density="compact"
                    variant="tonal"
                    class="mb-2"
                    icon="mdi-alert-octagon-outline"
                  >
                    <div class="font-weight-medium">Конечная категория ФЭО не выбрана — отправить заявку на согласование нельзя</div>
                    <div class="mt-1">
                      Без конечной категории закупка не попадёт ни в один план ФЭО и её сумма потеряется.
                      Выберите категорию у каждой позиции в таблице ниже, углубившись до самого конечного
                      уровня дерева, а если категория неизвестна — нажмите «Не определена» у нужной строки.
                    </div>
                    <div v-if="wishItemsMissingFeoCategory.length" class="mt-2">
                      <span class="font-weight-medium">Позиции без конечной категории:</span>
                      <ul class="ml-4 mt-1">
                        <li v-for="(it, idx) in wishItemsMissingFeoCategory" :key="idx">{{ it.item_name || 'без названия' }}</li>
                      </ul>
                    </div>
                  </v-alert>
                </template>
                <!-- Дефект 1 (владелец, 2026-08-20): видимый индикатор автосейва построчных
                     ФЭО-правок. -->
                <div
                  v-if="!isWishEditable && canEditWishFeo && (feoAutosaveSaving || feoAutosavePending)"
                  class="d-flex align-center ga-2 mb-2 text-caption text-medium-emphasis"
                >
                  <v-progress-circular v-if="feoAutosaveSaving" size="14" width="2" indeterminate color="primary" />
                  <v-icon v-else size="14" icon="mdi-clock-outline" />
                  {{ feoAutosaveSaving ? 'Сохранение ФЭО…' : 'Есть несохранённые изменения ФЭО — сохранятся автоматически' }}
                </div>
                <PurchaseItemsEditor
                  v-model="wishForm.items"
                  item-shape="purchase"
                  :purchase-id="null"
                  :wish-id="editingWishId"
                  :default-unit="'шт.'"
                  :default-country="'РФ'"
                  :allowed-item-types="['товар','услуга','работа']"
                  :supports-excel-import="true"
                  :supports-smart-import="true"
                  :supports-full-product-dialog="true"
                  :supports-photo-upload="true"
                  :readonly="!isWishEditable"
                  :feo-attrs-editable="!isWishEditable && canEditWishFeo"
                  :feo-per-item="wishForm.feo_per_item"
                  :subsidy-id="wishForm.subsidy_id"
                  :subsidy-name="selectedSubsidyName"
                  :default-feo-category-id="wishFeoSelected"
                  :feo-planned-per-item="false"
                  :allow-per-item-plan="true"
                  :planned-items="wishPlannedResiduals"
                  :show-needed-date="wishDateMode === 'per_item'"
                  :vat-mode="(wishForm.vat_mode as any)"
                  @update:vat-mode="(v: string) => { wishForm.vat_mode = v }"
                  @planned-item-created="onWishPlannedItemCreated"
                  @planned-item-deleted="onWishPlannedItemCreated"
                />
              </div>
              <!-- Владелец, 2026-08-13: построчные пометки — что остановлено, что разошлось с
                   закупкой, что не удалось сопоставить однозначно. -->
              <div v-if="wishForm.items.some((i: any) => wishItemStatus(i))" class="mt-2 d-flex flex-column" style="gap:4px">
                <template v-for="(it, idx) in wishForm.items" :key="'pmstatus-' + idx">
                  <div v-if="wishItemStatus(it)" class="d-flex align-center flex-wrap" style="gap:6px">
                    <span class="text-caption" :class="it.purchase_match?.purchase_stopped_at ? 'text-medium-emphasis text-decoration-line-through' : 'text-medium-emphasis'">
                      {{ it.item_name || 'без названия' }}:
                    </span>
                    <v-chip
                      v-if="it.purchase_match?.purchase_stopped_at"
                      size="x-small" color="error" variant="tonal" prepend-icon="mdi-stop-circle-outline"
                      :style="it.purchase_match?.purchase_id ? 'cursor:pointer' : ''"
                      :title="`Закупка №${it.purchase_match?.purchase_number || it.purchase_match?.purchase_id} остановлена ${ctx.formatDate(it.purchase_match!.purchase_stopped_at!)}`"
                      @click="ctx.goToMatchedPurchase(it)"
                    >остановлена</v-chip>
                    <v-tooltip v-if="itemDiscrepancy(it)" location="top">
                      <template #activator="{ props: dTip }">
                        <v-chip
                          v-bind="dTip"
                          size="x-small" color="orange" variant="tonal" prepend-icon="mdi-alert-outline"
                          :style="it.purchase_match?.purchase_id ? 'cursor:pointer' : ''"
                          @click="ctx.goToMatchedPurchase(it)"
                        >в закупке иначе</v-chip>
                      </template>
                      <div style="white-space:pre-line">{{ itemDiscrepancy(it)!.lines.join('\n') }}</div>
                    </v-tooltip>
                    <v-tooltip v-else-if="it.purchase_match?.match_method === 'item_name_ambiguous'" location="top">
                      <template #activator="{ props: aTip }">
                        <v-chip v-bind="aTip" size="x-small" color="grey" variant="tonal" prepend-icon="mdi-help-circle-outline">
                          двойник в закупке не определён
                        </v-chip>
                      </template>
                      Под этим наименованием в закупке несколько строк ({{ it.purchase_match?.ambiguous_candidates_count }}) — различить их автоматически нельзя.
                    </v-tooltip>
                  </div>
                </template>
              </div>
              <div class="d-flex justify-end mt-3">
                <div class="text-subtitle-1 font-weight-bold">Сумма заявки: {{ ctx.formatMoney(totalNmck) }}</div>
              </div>
            </v-card-text>
          </v-card>

          <!-- Section: Категория ФЭО — согласующий -->
          <v-card v-if="wishForm.subsidy_id && !isWishEditable && canEditWishFeo" variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2">mdi-sitemap</v-icon>Категория ФЭО (согласующий)
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <template v-if="!wishForm.feo_per_item">
                <v-alert v-if="wishFeoStale" type="warning" density="compact" variant="tonal" class="mb-2">
                  Категория ФЭО, выбранная в заявке, была удалена из справочника (структуру ФЭО субсидии
                  пересоздавали). Выберите актуальную категорию и сохраните. Если согласовать как есть —
                  закупка будет создана без категории ФЭО, её можно задать в «Плане закупок».
                </v-alert>
                <FeoTreeSelect
                  v-model="wishFeoSelected"
                  :nodes="wishFeoTreeNodes"
                  :leaves="wishFeoLeaves"
                  :plan-positions="wishPlannedResiduals"
                  :node-amounts="wishNodeAmounts"
                  horizontal
                  :readonly="!isWishEditable && !canEditWishFeo"
                  :allow-unallocated="!!(wishForm.subsidy_id && (isWishEditable || canEditWishFeo))"
                  :root-label="selectedSubsidyName"
                  @pick-unallocated="(parentId: number | null) => pickWishUnallocated(parentId)"
                />
              </template>
              <div v-else class="text-caption text-medium-emphasis mb-2">
                Включён режим «Разные категории ФЭО для каждого товара» — категория выбирается по каждой
                позиции в таблице «Позиции» выше.
              </div>
              <div v-if="!canAssigneeAct || wishItemsFeoDirty" class="mt-2">
                <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-content-save"
                       :loading="savingExecution" @click="saveExecution">
                  Сохранить ФЭО
                </v-btn>
                <span class="text-caption text-medium-emphasis ml-2">
                  Вы согласующий — можете изменить категорию ФЭО, если не согласны с выбором автора.
                </span>
              </div>
            </v-card-text>
          </v-card>

          <!-- Section: Дополнительно -->
          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2">mdi-information-outline</v-icon>Дополнительно
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-row dense>
                <v-col cols="12">
                  <v-autocomplete
                    v-model="wishForm.event_id"
                    :items="eventsForSubsidy"
                    item-title="name"
                    item-value="id"
                    label="Мероприятие"
                    variant="outlined"
                    density="compact"
                    clearable
                    :disabled="!wishForm.subsidy_id"
                    :readonly="!isWishEditable && !canAssigneeAct"
                    hint="Связать заявку с конкретным мероприятием субсидии"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12">
                  <v-autocomplete
                    v-model="wishForm.assigned_to"
                    :items="orgUsers"
                    item-title="full_name"
                    item-value="id"
                    label="На чьё имя будет заявка"
                    variant="outlined"
                    density="compact"
                    clearable
                    :disabled="!wishForm.subsidy_id"
                    :readonly="!isWishEditable && !canEditAssignee"
                    hint="Сотрудник, на имя которого составляется заявка"
                    persistent-hint
                    @update:model-value="(val: number | null) => { if (!isWishEditable && canEditAssignee) saveAssignedTo(val) }"
                  >
                    <template #item="{ item, props: itemProps }">
                      <v-list-item v-bind="itemProps">
                        <template #title>{{ item.raw.full_name }}</template>
                        <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                      </v-list-item>
                    </template>
                    <template #selection="{ item }">
                      {{ item.raw.full_name }}<span v-if="resolveUserPosition(item.raw)" class="text-caption text-medium-emphasis ml-2">— {{ resolveUserPosition(item.raw) }}</span>
                    </template>
                  </v-autocomplete>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- Section: Участники заявки -->
          <v-card v-if="isWishEditable || editingWishId" variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2" color="primary">mdi-account-multiple-plus</v-icon>
              Участники заявки
              <v-chip class="ml-2" size="x-small" variant="tonal">{{ wishMembers.length }}</v-chip>
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-autocomplete
                v-model="participantToAdd"
                :items="orgUsers"
                item-title="full_name"
                item-value="id"
                label="Добавить участника"
                variant="outlined"
                density="compact"
                clearable
                :disabled="!isWishEditable"
                hide-details
                @update:model-value="(val: number | null) => { if (val) { addWishMember(val); } }"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-item v-bind="itemProps">
                    <template #title>
                      {{ item.raw.full_name }}
                      <v-chip
                        size="x-small"
                        :color="ctx.requiresConsent(item.raw.id) ? 'orange' : 'green'"
                        variant="tonal"
                        class="ml-2"
                      >{{ ctx.requiresConsent(item.raw.id) ? 'нужно согласование' : 'без согласования' }}</v-chip>
                    </template>
                    <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                  </v-list-item>
                </template>
              </v-autocomplete>
              <div class="text-caption text-medium-emphasis mt-1 mb-3">
                Если у вас нет права ставить задачи участнику — потребуется его согласие.
              </div>
              <div class="d-flex flex-wrap" style="gap:8px">
                <v-chip
                  v-for="m in wishMembers"
                  :key="m.user_id"
                  :closable="isWishEditable"
                  @click:close="removeWishMember(m.user_id)"
                >
                  {{ m.full_name || m.username || '—' }}
                  <v-chip
                    v-if="m.consent_pending"
                    size="x-small"
                    color="orange"
                    variant="tonal"
                    class="ml-1"
                  >ждёт согласия</v-chip>
                  <v-chip
                    v-else-if="!editingWishId && ctx.requiresConsent(m.user_id)"
                    size="x-small"
                    color="orange"
                    variant="tonal"
                    class="ml-1"
                  >потребует согласования</v-chip>
                </v-chip>
              </div>
            </v-card-text>
          </v-card>

          <!-- Section: Согласующие необходимости закупки -->
          <v-card v-if="isWishEditable || editingWishId" variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2 d-flex flex-wrap align-center ga-1">
              <v-icon class="mr-2" color="primary">mdi-account-check</v-icon>
              Согласующие необходимости закупки
              <v-chip class="ml-2" size="x-small" variant="tonal">{{ wishApprovers.length }}</v-chip>
              <v-spacer />
              <v-chip size="x-small" :color="approvalMode === 'sequential' ? 'blue' : 'teal'" variant="tonal">
                {{ approvalMode === 'sequential' ? 'Последовательно' : 'Параллельно' }}
              </v-chip>
            </v-card-title>
            <div class="text-caption text-medium-emphasis px-4 pb-2">
              Здесь подтверждают, что закупка вообще нужна. Согласование превышения плана ФЭО — отдельно, в разделе субсидии, и доступно только уполномоченным.
            </div>
            <v-card-text class="pa-4 pt-2">
              <v-alert
                v-if="!editingWishId"
                type="info"
                variant="tonal"
                density="compact"
                class="mb-0"
              >
                <v-btn
                  size="small"
                  color="primary"
                  variant="flat"
                  :loading="saving"
                  prepend-icon="mdi-account-plus"
                  @click="onAddApproversClick"
                >Добавить согласующих</v-btn>
                <div class="mt-2 text-caption">
                  Черновик заявки сохранится автоматически, и появится возможность выбрать согласующих.
                </div>
              </v-alert>
              <!-- Построение цепочки (только для черновика/отклонённой) -->
              <template v-if="isWishEditable && editingWishId">
                <div class="text-caption text-medium-emphasis mb-2">
                  Выберите верхнего согласующего — система автоматически подтянет всю восходящую цепочку начальников снизу вверх.
                  Построение цепочки НЕ отправляет заявку: цепочку можно менять и дополнять людьми вручную,
                  а на согласование заявка уйдёт только по кнопке «Отправить на согласование».
                </div>
                <v-row dense align="center">
                  <v-col cols="12" md="6" data-field="approvers">
                    <v-autocomplete
                      v-model="approverTopUser"
                      :items="orgUsers"
                      item-title="full_name"
                      item-value="id"
                      label="Верхний согласующий"
                      variant="outlined"
                      density="compact"
                      clearable
                      hide-details
                    >
                      <template #item="{ item, props: itemProps }">
                        <v-list-item v-bind="itemProps">
                          <template #title>{{ item.raw.full_name }}</template>
                          <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                        </v-list-item>
                      </template>
                    </v-autocomplete>
                  </v-col>
                  <v-col cols="12" md="3">
                    <v-select
                      v-model="approvalMode"
                      :items="[
                        { value: 'sequential', title: 'Последовательно' },
                        { value: 'parallel', title: 'Параллельно' },
                      ]"
                      label="Режим"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </v-col>
                  <v-col cols="12" md="3">
                    <v-btn
                      color="primary"
                      variant="flat"
                      block
                      :loading="cascadeLoading"
                      :disabled="!approverTopUser"
                      prepend-icon="mdi-sitemap"
                      @click="runCascade"
                    >Построить цепочку</v-btn>
                  </v-col>
                </v-row>
                <v-divider class="my-3" />
              </template>

              <!-- Список согласующих -->
              <div v-if="wishApprovers.length === 0" class="text-caption text-medium-emphasis">
                Согласующие ещё не назначены.
                <div v-if="approverTopUser">Нажмите «Построить цепочку» — или просто отправьте заявку, цепочка построится автоматически.</div>
              </div>
              <div v-else class="d-flex flex-column" style="gap:10px">
                <v-sheet
                  v-for="(a, ai) in wishApprovers"
                  :key="a.id"
                  rounded="lg"
                  border
                  class="pa-3"
                >
                  <div class="d-flex align-center flex-wrap" style="gap:8px">
                    <v-chip size="x-small" variant="tonal" color="grey">#{{ a.order_num + 1 }}</v-chip>
                    <span class="font-weight-medium">{{ a.full_name || '—' }}</span>
                    <span v-if="a.role_name" class="text-caption text-medium-emphasis">{{ a.role_name }}</span>
                    <v-chip
                      v-if="!a.is_auto"
                      size="x-small"
                      variant="tonal"
                      color="purple"
                    >вручную</v-chip>
                    <v-spacer />
                    <v-chip size="small" :color="approvalStatusColor[a.status]" variant="tonal">
                      {{ approvalStatusLabel[a.status] || a.status }}
                    </v-chip>
                    <template v-if="isWishEditable && wishApprovers.length > 1">
                      <v-btn
                        icon="mdi-arrow-up"
                        size="x-small"
                        variant="text"
                        :disabled="ai === 0 || reorderLoading"
                        title="Поднять в очереди согласования"
                        @click="moveApprover(ai, -1)"
                      />
                      <v-btn
                        icon="mdi-arrow-down"
                        size="x-small"
                        variant="text"
                        :disabled="ai === wishApprovers.length - 1 || reorderLoading"
                        title="Опустить в очереди согласования"
                        @click="moveApprover(ai, 1)"
                      />
                    </template>
                    <v-btn
                      v-if="a.status === 'pending' && isWishEditable"
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      @click="removeApprover(a.id)"
                    />
                  </div>
                  <div v-if="approverDecisionLine(a)" class="text-caption text-medium-emphasis mt-1">
                    {{ approverDecisionLine(a) }}
                  </div>
                  <div v-if="a.comment" class="text-caption text-medium-emphasis mt-1">
                    Комментарий: {{ a.comment }}
                  </div>
                  <!-- Действия текущего пользователя-согласующего -->
                  <div v-if="canDecideApprover(a)" class="mt-2">
                    <div v-if="isDecidingOnBehalf(a)" class="text-caption text-orange-darken-3 mb-1 d-flex align-center" style="gap:4px">
                      <v-icon size="14">mdi-account-arrow-right</v-icon>
                      Вы решаете за {{ ctx.shortName(a.full_name) || a.full_name || 'назначенного согласующего' }}
                    </div>
                    <v-textarea
                      v-model="decideComment[a.id]"
                      :label="isDecidingOnBehalf(a) ? 'Причина решения за другого (обязательно)' : 'Комментарий (необязательно при согласовании, обязателен при отказе)'"
                      variant="outlined"
                      density="compact"
                      rows="2"
                      auto-grow
                      hide-details
                      class="mb-1"
                    />
                    <div v-if="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()" class="text-caption text-red mb-2">
                      Укажите причину — например, что согласующий в отпуске или поручил вам решение.
                    </div>
                    <div v-else class="mb-2" />
                    <div class="d-flex" style="gap:8px">
                      <v-btn
                        color="green"
                        variant="flat"
                        size="small"
                        :loading="decideLoading === a.id"
                        :disabled="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()"
                        prepend-icon="mdi-check"
                        @click="decideApprover(a.id, 'approved')"
                      >Согласовать</v-btn>
                      <v-btn
                        color="red"
                        variant="tonal"
                        size="small"
                        :loading="decideLoading === a.id"
                        :disabled="!decideComment[a.id]"
                        prepend-icon="mdi-close"
                        @click="decideApprover(a.id, 'rejected')"
                      >Отклонить</v-btn>
                    </div>
                  </div>
                  <!-- Задача 2: строка стала неактуальна из-за живого обновления -->
                  <div
                    v-else-if="a.status === 'pending' && (a.user_id === ctx.currentUserId || ctx.isAdmin.value) && editingWish && editingWish.status !== 'submitted'"
                    class="text-caption text-medium-emphasis mt-2"
                  >
                    Действие недоступно — статус заявки изменился на «{{ statusLabel[editingWish.status] || editingWish.status }}».
                  </div>
                </v-sheet>
              </div>

              <!-- Ручное добавление -->
              <template v-if="editingWishId && (isWishEditable || (editingWish && editingWish.status === 'submitted' && (isChainApprover || ctx.isManagerOrAdmin.value)))">
                <v-divider class="my-3" />
                <v-autocomplete
                  v-model="approverToAdd"
                  :items="orgUsers"
                  item-title="full_name"
                  item-value="id"
                  label="Добавить согласующего"
                  variant="outlined"
                  density="compact"
                  clearable
                  hide-details
                  @update:model-value="(val: number | null) => { if (val) addApprover(val) }"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps">
                      <template #title>{{ item.raw.full_name }}</template>
                      <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </template>
            </v-card-text>
          </v-card>

          <!-- Section: Принудительная смена статуса (только superadmin/account_owner) -->
          <v-card v-if="ctx.isSaas.value && editingWishId" variant="outlined" class="mb-4 bg-red-lighten-5">
            <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
              <v-icon class="mr-2" color="red-darken-2">mdi-shield-crown</v-icon>Принудительная смена статуса (SaaS-admin)
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-row dense align="center">
                <v-col cols="12" md="8">
                  <v-select
                    v-model="forceStatusValue"
                    :items="WISH_FORCE_STATUS_OPTIONS"
                    label="Новый статус"
                    variant="outlined"
                    density="compact"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-btn color="red-darken-2" variant="flat" block prepend-icon="mdi-flash" :loading="forcingStatus"
                    @click="async () => { if (await forceStatus()) wishDialog = false }">
                    Применить
                  </v-btn>
                </v-col>
              </v-row>
              <div class="text-body-2 text-medium-emphasis mt-2">
                Минуя все workflow-проверки. Доступно только SaaS-роли.
              </div>
            </v-card-text>
          </v-card>

          <!-- Section: На исполнение (видна согласующему) -->
          <v-card v-if="canAssigneeAct || (editingWish && editingWish.status === 'approved' && (editingWish.assigned_to === ctx.currentUserId || ctx.isAdmin.value))" variant="outlined" class="mb-4 bg-amber-lighten-5">
            <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
              <v-icon class="mr-2" color="orange-darken-4">mdi-account-clock</v-icon>На исполнение
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-row dense>
                <v-col cols="12" md="6">
                  <v-autocomplete
                    v-model="wishForm.executor_id"
                    :items="orgUsers"
                    item-title="full_name"
                    item-value="id"
                    label="Исполнитель"
                    variant="outlined"
                    density="compact"
                    clearable
                    hint="Кому назначено фактическое исполнение"
                    persistent-hint
                  >
                    <template #item="{ item, props: itemProps }">
                      <v-list-item v-bind="itemProps">
                        <template #title>{{ item.raw.full_name }}</template>
                        <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                      </v-list-item>
                    </template>
                    <template #selection="{ item }">
                      {{ item.raw.full_name }}<span v-if="resolveUserPosition(item.raw)" class="text-caption text-medium-emphasis ml-2">— {{ resolveUserPosition(item.raw) }}</span>
                    </template>
                  </v-autocomplete>
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="wishForm.execution_deadline"
                    label="Срок исполнения"
                    type="date"
                    variant="outlined"
                    density="compact"
                    clearable
                    hint="К какому числу должно быть исполнено"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12">
                  <v-autocomplete
                    v-model="wishForm.event_id"
                    :items="eventsForSubsidy"
                    item-title="name"
                    item-value="id"
                    label="Мероприятие"
                    variant="outlined"
                    density="compact"
                    clearable
                    hint="Связать с конкретным мероприятием (можно изменить тут даже после одобрения)"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12">
                  <v-autocomplete
                    v-model="wishForm.assigned_to"
                    :items="orgUsers"
                    item-title="full_name"
                    item-value="id"
                    label="На чьё имя заявка"
                    variant="outlined"
                    density="compact"
                    clearable
                    hint="Сотрудник, на имя которого составляется заявка (без сброса цепочки согласования)"
                    persistent-hint
                  >
                    <template #item="{ item, props: itemProps }">
                      <v-list-item v-bind="itemProps">
                        <template #title>{{ item.raw.full_name }}</template>
                        <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                      </v-list-item>
                    </template>
                    <template #selection="{ item }">
                      {{ item.raw.full_name }}<span v-if="resolveUserPosition(item.raw)" class="text-caption text-medium-emphasis ml-2">— {{ resolveUserPosition(item.raw) }}</span>
                    </template>
                  </v-autocomplete>
                </v-col>
                <v-col cols="12">
                  <v-btn color="orange-darken-4" variant="flat" prepend-icon="mdi-content-save" :loading="savingExecution" @click="saveExecution">
                    Сохранить исполнителя / срок / мероприятие / получателя
                  </v-btn>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- Section 3: Обоснование и сроки -->
          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pa-4 pb-2">
              <v-icon class="mr-2">mdi-text-box-check-outline</v-icon>Обоснование и сроки
            </v-card-title>
            <v-card-text class="pa-4 pt-2">
              <v-row dense>
                <v-col cols="12">
                  <v-textarea
                    v-model="wishForm.justification"
                    label="Обоснование *"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    :rules="[v => !!v || 'Обязательное поле']"
                    hint="Почему это необходимо для работы"
                    persistent-hint
                    :readonly="!isWishEditable"
                    data-field="justification"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-select
                    v-model="wishForm.priority"
                    :items="priorityOptions"
                    label="Приоритет"
                    variant="outlined"
                    density="compact"
                    :readonly="!isWishEditable"
                    data-field="priority"
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

        </v-form>
      </v-card-text>

      <v-card-actions class="px-4 pb-4 flex-wrap">
        <v-btn variant="text" @click="wishDialog = false">Закрыть</v-btn>
        <v-menu v-if="editingWishId && editingWish">
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" variant="tonal" color="green-darken-1" prepend-icon="mdi-microsoft-excel" :loading="actions.downloadingExcelId.value === editingWishId">Скачать Excel</v-btn>
          </template>
          <v-list density="compact">
            <v-list-item prepend-icon="mdi-image" title="С фото" @click="actions.downloadWishExcel(editingWish as any, true)" />
            <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="actions.downloadWishExcel(editingWish as any, false)" />
          </v-list>
        </v-menu>
        <!-- Владелец, 2026-08-13: копирование — доступно всегда, кто видит заявку -->
        <v-tooltip v-if="editingWishId && editingWish" location="top" text="Скопируются позиции и количества, остальное заполните заново">
          <template #activator="{ props: tipProps }">
            <v-btn v-bind="tipProps" variant="tonal" color="secondary" prepend-icon="mdi-content-copy"
                   :loading="actions.copyingId.value === editingWishId" @click="actions.copyWish(editingWish)">
              Скопировать заявку
            </v-btn>
          </template>
        </v-tooltip>
        <!-- Владелец, 2026-08-13: «останавливать могут все» -->
        <v-btn v-if="editingWishId && editingWish && !editingWish.stopped_at" variant="tonal" color="error"
               prepend-icon="mdi-stop-circle-outline" @click="actions.openStopDialog(editingWish)">
          Остановить заявку
        </v-btn>
        <!-- Владелец, 2026-09-04: возможность завести заявку как авансовый отчёт -->
        <v-tooltip v-if="editingWishId && editingWish && editingWish.source !== 'advance_report' && editingWish.contracted_locked"
                   location="top" :text="`Нельзя: ${editingWish.contracted_locked_reason || 'заявка уже на этапе договора или позже'}`">
          <template #activator="{ props: tipProps }">
            <span v-bind="tipProps">
              <v-btn variant="tonal" color="orange-darken-2" prepend-icon="mdi-cash-refund" disabled>
                Оформить как авансовый отчёт
              </v-btn>
            </span>
          </template>
        </v-tooltip>
        <v-btn v-else-if="editingWishId && editingWish && editingWish.source !== 'advance_report'"
               variant="tonal" color="orange-darken-2" prepend-icon="mdi-cash-refund"
               @click="actions.openConvertToAdvanceDialog(editingWish)">
          Оформить как авансовый отчёт
        </v-btn>
        <v-spacer />
        <!-- draft/rejected или новая заявка: черновик + отправить -->
        <template v-if="isWishEditable && (!editingWishId || ['draft', 'rejected'].includes((wishForm as any).status))">
          <v-btn color="grey" variant="tonal" :loading="saving" @click="saveWish(false)">
            Сохранить черновик
          </v-btn>
          <v-tooltip :disabled="!wishFeoCategoryMissing" location="top">
            <template #activator="{ props: tipProps }">
              <span v-bind="tipProps">
                <v-btn ref="wishSubmitBtnRef" color="primary" variant="flat" :loading="saving"
                       :class="{ 'wish-btn-blocked': wishFeoCategoryMissing }"
                       @click="wishFeoCategoryMissing ? highlightMissingFeoCategory() : saveWish(true)">
                  Отправить на согласование
                </v-btn>
              </span>
            </template>
            {{ wishFeoCategoryMissingTooltip }}
          </v-tooltip>
        </template>
        <!-- approved/converted и editable (не contracted_locked): сохранить изменения -->
        <template v-else-if="isWishEditable && editingWish && ['approved', 'converted'].includes(editingWish.status)">
          <v-btn color="primary" variant="tonal" :loading="saving" @click="saveWish(false)">
            Сохранить изменения
          </v-btn>
          <v-btn v-if="ctx.isManagerOrAdmin.value && editingWish.status === 'approved'" color="primary" variant="flat" prepend-icon="mdi-cart-arrow-right"
                 @click="actions.openConvertDialog(editingWish); wishDialog = false">
            Передать в План закупок
          </v-btn>
          <v-btn v-else-if="editingWish.status === 'converted' && editingWish.purchase_id" color="primary" variant="flat" prepend-icon="mdi-cart-arrow-right"
                 @click="ctx.goToWishPurchases(editingWish); wishDialog = false">
            Перейти в {{ (editingWish.purchases?.length || editingWish.purchase_ids?.length || 1) > 1 ? 'закупки' : 'закупку' }}
          </v-btn>
        </template>
        <template v-else-if="canAssigneeAct && editingWish">
          <v-btn color="error" variant="tonal" prepend-icon="mdi-close" @click="actions.openRejectDialog(editingWish); wishDialog = false">
            Отклонить
          </v-btn>
          <v-tooltip :disabled="!wishFeoCategoryMissing" location="top">
            <template #activator="{ props: tipProps }">
              <span v-bind="tipProps">
                <v-btn color="success" variant="tonal" prepend-icon="mdi-check" :loading="actions.approvingId.value === editingWish.id"
                       :class="{ 'wish-btn-blocked': wishFeoCategoryMissing }"
                       @click="wishFeoCategoryMissing ? highlightMissingFeoCategory() : actions.approveWish(editingWish).then(() => wishDialog = false)">
                  Одобрить без согласования остальных
                </v-btn>
              </span>
            </template>
            {{ wishFeoCategoryMissingTooltip }}
          </v-tooltip>
          <v-btn color="primary" variant="flat" prepend-icon="mdi-view-column-outline"
                 @click="actions.openKanbanDialog(editingWish); wishDialog = false">
            Распределить и одобрить
          </v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Стрелочки от кнопки отправки к незаполненным полям (как в Закупке) -->
  <ValidationArrows
    :active="validationArrowsActive"
    :from-el="validationArrowFrom"
    :to-els="validationArrowTargets"
    @dismiss="dismissValidationArrows"
  />

  <WishKanbanDialog
    v-model="actions.kanbanDialog.value"
    :wish="actions.kanbanWish.value"
    :items="actions.kanbanItems.value"
    :mobile="mobile"
    @approved="actions.onKanbanApproved"
  />

  <WishActionDialogs
    v-model:reject-dialog="actions.rejectDialog.value"
    v-model:rejection-reason="actions.rejectionReason.value"
    v-model:row-force-status-wish="rowForceStatusWish"
    v-model:force-status-value="forceStatusValue"
    v-model:feo-per-item-disable-dialog="wishFeoPerItemDisableDialog"
    v-model:stop-dialog="actions.stopDialog.value"
    v-model:stop-reason="actions.stopReason.value"
    v-model:convert-to-advance-dialog="actions.convertToAdvanceDialog.value"
    v-model:convert-dialog="actions.convertDialog.value"
    v-model:convert-form="actions.convertForm.value"
    :mobile="mobile"
    :rejecting-wish="actions.rejectingWish.value"
    :WISH_FORCE_STATUS_OPTIONS="WISH_FORCE_STATUS_OPTIONS"
    :forcing-status="forcingStatus"
    :feo-per-item-disable-count="wishFeoPerItemDisableCount"
    :stopping-wish="actions.stoppingWish.value"
    :converting-to-advance-wish="actions.convertingToAdvanceWish.value"
    :converting-to-advance-loading="actions.convertingToAdvanceLoading.value"
    :converting-wish="actions.convertingWish.value"
    :converting-wish-loading="actions.convertingWishLoading.value"
    @reject-confirm="actions.rejectWish"
    @apply-row-force-status="applyRowForceStatus"
    @confirm-feo-per-item-disable="confirmWishFeoPerItemDisable"
    @cancel-feo-per-item-disable="cancelWishFeoPerItemDisable"
    @stop-confirm="actions.confirmStopWish"
    @convert-to-advance-confirm="actions.confirmConvertToAdvance"
    @convert-confirm="actions.convertWish"
  />
</template>

<script setup lang="ts">
// WishFormDialog.vue — карточка создания/редактирования заявки (самый большой
// компонент модуля «Заявки», см. задание сессии). Владеет ВСЕМ состоянием одной
// открытой заявки: формой (useWishForm.ts), участниками/согласующими
// (useWishApprovers.ts), автосейвом построчного ФЭО (useWishItemsFeoAutosave.ts)
// и действиями над заявкой — отправка/одобрение/отклонение/остановка/копирование/
// convert (useWishActions.ts). Рендерит также вспомогательные диалоги как дочерние
// компоненты (WishKanbanDialog/WishActionDialogs) — Vuetify телепортирует их
// содержимое в <body>, поэтому вложенность в дереве компонентов не влияет на DOM/
// e2e-селекторы.
//
// useWishLive живёт ЗДЕСЬ (не в WishesView.vue, вопреки первоначальному разбиению
// по заданию): composable мутирует переданные approvers/wish refs НАПРЯМУЮ
// (`approvers.value = freshApprovers`), а onUnmounted должен жить, пока эта
// заявка вообще может быть открыта. Раз это состояние и так принадлежит
// WishFormDialog (owns wishForm/editingWishId/wishApprovers), вызывать
// useWishLive из WishesView.vue означало бы либо тащить наверх все эти refs
// (раздувая View обратно), либо городить псевдо-writable computed через
// defineExpose — тот же результат ценой куда большего риска регресса. Родитель
// получает то немногое, что ему НУЖНО (editingWishId/wishDialog/editingWish/
// wishApprovers/feoAutosaveSaving/feoAutosavePending и функции открытия/действий)
// через defineExpose — единственное официально разрешённое место для него по
// заданию, здесь расширенное на этот один непреодолимый случай.
import { useWishLive } from '@/composables/useWishLive'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import ContractorPicker from '@/components/ContractorPicker.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import ValidationArrows from '@/components/ValidationArrows.vue'
import WishKanbanDialog from './WishKanbanDialog.vue'
import WishActionDialogs from './WishActionDialogs.vue'
import { apiFetch } from '@/api'
import {
  useWishesContext, statusLabel, priorityOptions,
} from '@/composables/wishes/useWishesContext'
import { useWishForm } from '@/composables/wishes/useWishForm'
import { useWishApprovers } from '@/composables/wishes/useWishApprovers'
import { useWishItemsFeoAutosave } from '@/composables/wishes/useWishItemsFeoAutosave'
import { useWishActions } from '@/composables/wishes/useWishActions'
import type { Wish } from '@/composables/wishes/wishTypes'

const props = defineProps<{
  mobile: boolean
  reloadActiveTab: () => Promise<void>
  loadWishes: () => Promise<void>
  loadAllWishes: () => Promise<void>
}>()

const ctx = useWishesContext()

const form = useWishForm({
  ctx,
  apiFetch,
  reloadActiveTab: props.reloadActiveTab,
  ensureApprovers: (id: number) => approvers.ensureApprovers(id),
  getStagedMemberUserIds: () => approvers.wishMembers.value.map(m => m.user_id),
  reloadStagedMembers: () => approvers.loadWishMembers(),
  reloadApprovers: () => approvers.loadWishApprovers(),
})

const autosave = useWishItemsFeoAutosave({
  ctx,
  apiFetch,
  form,
  reloadActiveTab: props.reloadActiveTab,
})

// Владелец: forward-reference на wishLive (объявлен ниже approvers, approvers
// нужен ему как источник approvers.value) — лямбда не читает переменную до
// первого реального решения по согласованию, к тому моменту wishLive уже создан.
const approvers = useWishApprovers({
  ctx,
  apiFetch,
  form,
  flushFeoAutosave: () => autosave.flushFeoAutosave(),
  notifyLocalUpdate: () => wishLive.markLocalUpdate(),
  loadWishes: props.loadWishes,
})

const wishLive = useWishLive({
  wishId: form.editingWishId,
  isOpen: form.wishDialog,
  approvers: approvers.wishApprovers,
  wish: form.editingWish as any,
  currentUserId: ctx.currentUserId,
  isAutosaveBusy: () => autosave.feoAutosaveSaving.value || autosave.feoAutosavePending.value,
  showSnack: ctx.showSnack,
  shortName: ctx.shortName,
  onExternalChange: () => {
    props.loadWishes()
    props.loadAllWishes()
    refreshMyPendingApprovals()
  },
})

// Полностью оркестрованное открытие карточки — форма + участники + согласующие +
// снимки автосейва ФЭО, ровно как единая функция openEditDialog в исходном файле.
async function openEdit(wish: Wish) {
  await form.openEditDialog(wish, {
    afterItemsFilled: async () => {
      await approvers.loadWishMembers()
      await approvers.loadWishApprovers()
      approvers.approvalMode.value = ((wish as any).approval_mode === 'parallel') ? 'parallel' : 'sequential'
      form.wishFormSavedSnapshot.value = form.wishPayloadSnapshotJson()
      autosave.snapshotWishItemsFeo()
    },
  })
}
function openCreate() {
  approvers.wishMembers.value = []
  approvers.wishApprovers.value = []
  approvers.approverTopUser.value = null
  approvers.approverToAdd.value = null
  approvers.approvalMode.value = 'sequential'
  form.openCreateDialog()
}

const actions = useWishActions({
  ctx,
  apiFetch,
  form,
  flushFeoAutosave: () => autosave.flushFeoAutosave(),
  reloadActiveTab: props.reloadActiveTab,
  loadAllWishes: props.loadAllWishes,
  openEditDialog: openEdit,
})

async function applyRowForceStatus() { await form.applyRowForceStatus() }

// ── Разворачиваем поля form/approvers/autosave в top-level имена — ТОЧНО как в
// исходном WishesView.vue — чтобы шаблон (дословно перенесённый) резолвил их
// через авто-unwrap top-level setup-ref'ов, а не через ручной .value на каждый
// доступ (что и в оригинале работало именно так). ──
const {
  wishDialog, wishDialogLoading, editingWishId, editingWish, wishDateMode, wishConvertError,
  applyCommonDateToAllItems, wishFormRef, wishSubmitBtnRef,
  validationArrowsActive, validationArrowFrom, validationArrowTargets, dismissValidationArrows,
  highlightMissingFeoCategory, saving, serverFieldErrors, wishForm, selectedSubsidyName, eventsForSubsidy,
  wishFeoSelected, wishFeoPerItemDisableDialog, wishFeoPerItemDisableCount,
  onWishFeoPerItemChange, cancelWishFeoPerItemDisable, confirmWishFeoPerItemDisable,
  orgUsers, resolveUserPosition, wishContractorInitial, onWishContractorSelect,
  wishFeoLeaves, wishFeoTreeNodes, wishNodeAmounts, pickWishUnallocated,
  wishPlannedResiduals, onWishPlannedItemCreated,
  wishFeoStale, wishItemsMissingFeoCategory, wishFeoCategoryMissing, wishFeoCategoryMissingTooltip,
  wishItemsWithStaleFeoCategory, itemDiscrepancy, wishItemStatus,
  onAddApproversClick, totalNmck, onSubsidyChange,
  isWishEditable, isDialogCreator, canAssigneeAct, isChainApprover, canEditWishFeo, canEditAssignee,
  saveWish, WISH_FORCE_STATUS_OPTIONS, forceStatusValue, forcingStatus, forceStatus,
  rowForceStatusWish,
  undoRedoWish,
} = form
// wishFormRef/wishSubmitBtnRef подключены к DOM только через `ref="..."` в шаблоне
// (v-form/кнопка отправки) — vue-tsc не видит эту связь при noUnusedLocals, хотя
// внутри useWishForm.ts (showValidationArrows/pointArrowsTo) они читаются постоянно.
void wishFormRef
void wishSubmitBtnRef

const {
  wishMembers, participantToAdd, addWishMember, removeWishMember,
  wishApprovers, approverTopUser, approverToAdd, approvalMode, cascadeLoading,
  decideComment, decideLoading, approvalStatusColor, approvalStatusLabel,
  runCascade, addApprover, reorderLoading, moveApprover, removeApprover, decideApprover,
  canDecideApprover, isDecidingOnBehalf, approverDecisionLine,
} = approvers

const { feoAutosavePending, feoAutosaveSaving, wishItemsFeoDirty, savingExecution, saveExecution, saveAssignedTo } = autosave

// useWishLive нужен родителю (WishesView.vue) для бейджа/подгрузки списков после
// внешних изменений — здесь достаточно, что composable сам запускается/
// останавливается по watch(isOpen) внутри себя.
void wishLive

defineExpose({
  openCreate,
  openEdit,
  submitWish: actions.submitWish,
  deleteWish: actions.deleteWish,
  approveWish: actions.approveWish,
  openRejectDialog: actions.openRejectDialog,
  openKanbanDialog: actions.openKanbanDialog,
  openConvertDialog: actions.openConvertDialog,
  openConvertToAdvanceDialog: actions.openConvertToAdvanceDialog,
  openStopDialog: actions.openStopDialog,
  openRowForceStatus: form.openRowForceStatus,
  downloadWishExcel: actions.downloadWishExcel,
  // Индикаторы загрузки для кнопок в строках таблиц (Wish*Tab.vue) — read-only,
  // родитель (WishesView.vue) читает их реактивно через computed поверх ref
  // компонента (см. WishesView.vue::submittingId и соседние).
  submittingId: actions.submittingId,
  deletingId: actions.deletingId,
  approvingId: actions.approvingId,
  downloadingExcelId: actions.downloadingExcelId,
})
</script>

<style scoped>
.wish-dialog.v-theme--light :deep(.text-medium-emphasis) {
  color: rgba(0, 0, 0, 0.72) !important;
}
</style>
