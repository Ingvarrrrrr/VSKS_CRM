<template>
  <v-container fluid class="pa-6" style="max-width:1600px">
    <PurchaseHeader
      :form="form"
      :is-edit="isEdit"
      :purchase-loaded="purchaseLoaded"
      :page-title="pageTitle"
      :is-saas="isSaas"
      :purchase-id="purchaseId"
      :status-order="STATUS_ORDER"
      :status-label="STATUS_LABEL"
      :status-color="STATUS_COLOR"
      :forcing-order-status="forcingOrderStatus"
      :substatus-options="SUBSTATUS_OPTIONS"
      :has-draft="hasDraft"
      :draft-saved="draftSaved"
      :back-route="backRoute"
      :purchase-data="purchaseData"
      :purchase-excess-text="purchaseExcessText"
      :purchase-excess-state-color="purchaseExcessStateColor"
      :purchase-excess-state-text="purchaseExcessStateText"
      :feo-mismatch-fixable-items="feoMismatchFixableItems"
      :fixing-feo-mismatch="fixingFeoMismatch"
      :wish-withdrawn-banner-text="wishWithdrawnBannerText"
      :force-order-status="forceOrderStatus"
      :clear-draft="clearDraft"
      :show-snack="showSnack"
      :fix-feo-mismatch-own-categories="fixFeoMismatchOwnCategories"
      :go-to-wish="(wishId: number) => router.push({ path: '/wishes', query: { open: String(wishId) } })"
    />

    <div v-if="form.subsidy_id && (feoDirections.length || feoResiduals.length)" class="mb-4">
      <!-- Заголовок с переключателем свёртки -->
      <div class="d-flex align-center text-subtitle-2 font-weight-medium mb-2"
           style="cursor:pointer;user-select:none" @click="toggleFeoRemains">
        <v-icon icon="mdi-chart-donut" size="18" color="grey" class="mr-2" />
        <span>Остатки по категориям ФЭО</span>
        <v-icon :icon="feoRemainsCollapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'" size="18" color="grey" class="ml-1" />
      </div>
      <div v-show="!feoRemainsCollapsed">
        <!-- Остатки по направлениям ФЭО (ур.1) — видны при формировании, контроль бюджета -->
        <template v-if="canViewAllLevelsBudget && feoDirections.length">
          <v-alert
            v-for="d in feoDirections" :key="d.id"
            :type="d.spendable_remaining < 0 ? 'error' : 'info'"
            variant="tonal" density="compact" class="mb-2">
            <div class="text-subtitle-2 mb-1">{{ d.name }}</div>
            <div class="d-flex flex-wrap gap-x-4 text-body-2">
              <span>
                Незаконтрактовано:
                <strong :class="d.uncontracted_remaining < 0 ? 'text-error' : ''">{{ formatMoney(d.uncontracted_remaining) }}</strong>
              </span>
              <span>
                На траты:
                <strong :class="d.spendable_remaining < 0 ? 'text-error font-weight-bold' : ''">{{ formatMoney(d.spendable_remaining) }}</strong>
                <span class="text-caption text-medium-emphasis"> из {{ formatMoney(d.budget) }}</span>
              </span>
            </div>
          </v-alert>
        </template>
        <!-- Остатки по выбранным листовым ФЭО (после выбора пункта) -->
        <template v-if="canViewLeafBudget">
          <v-alert
            v-for="r in feoResiduals" :key="r.id"
            :type="(basketForNode(r.id) > r.spendable_remaining) ? 'warning' : r.spendable_remaining < 0 ? 'error' : 'info'"
            variant="tonal" density="compact" class="mb-2">
            <div class="text-subtitle-2 mb-1">Остаток по «{{ r.name }}»</div>
            <div class="text-body-2">
              <div>Бюджет: <strong>{{ formatMoney(r.budget) }}</strong></div>
              <div>Осталось незаконтрактованным: <strong :class="r.uncontracted_remaining < 0 ? 'text-error' : ''">{{ formatMoney(r.uncontracted_remaining) }}</strong></div>
              <div>Осталось на траты: <strong :class="r.spendable_remaining < 0 ? 'text-error font-weight-bold' : ''">{{ formatMoney(r.spendable_remaining) }}</strong></div>
              <div :class="(r.spendable_remaining - basketForNode(r.id)) < 0 ? 'text-error font-weight-bold' : ''">
                Осталось потратить (с учётом этой заявки): <strong>{{ formatMoney(r.spendable_remaining - basketForNode(r.id)) }}</strong>
              </div>
              <div v-if="(r.spendable_remaining - basketForNode(r.id)) < 0" class="text-error text-caption mt-1">
                Превышение на {{ formatMoney(Math.abs(r.spendable_remaining - basketForNode(r.id))) }} — потребуется согласование руководителя
              </div>
            </div>
            <div v-if="canViewAllLevelsBudget && r.ancestors && r.ancestors.length" class="mt-2 text-caption">
              <div v-for="a in r.ancestors" :key="a.id">
                ур.{{ a.level }} «{{ a.name }}»: незаконтрактовано <strong>{{ formatMoney(a.uncontracted_remaining) }}</strong> / на траты <strong>{{ formatMoney(a.spendable_remaining) }}</strong>
              </div>
            </div>
          </v-alert>
        </template>
      </div>
    </div>

    <v-form ref="formRef" :class="{ 'compact-mobile': formMode === 'advance_report' }" @submit.prevent="save">

      <!-- Чеки вверху — только при создании авансового отчёта -->
      <PurchaseReceiptsBlock
        v-if="showReceiptsOnTop"
        variant="top"
        :receipts="receipts"
        :purchase-id="purchaseId"
        :is-edit="isEdit"
        :source-label="sourceLabel"
        :recompute-loading="recomputeLoading"
        :on-scan-qr-click="onScanQrClick"
        :on-json-btn-click="onJsonBtnClick"
        :on-manual-click="onManualBtnClick"
        :on-recompute="recomputeFromReceipts"
        :on-json-receipt-upload="onJsonReceiptUpload"
        :on-delete-receipt="deleteReceipt"
      />

      <!-- U-2: Подсказка про мульти-чеки (только для авансового, закрываемая) -->
      <v-alert
        v-if="formMode === 'advance_report' && !advanceInfoAlertClosed"
        type="info"
        variant="tonal"
        density="compact"
        closable
        class="mb-4"
        @click:close="closeAdvanceInfoAlert"
      >
        В одном авансовом отчёте можно загрузить <strong>несколько чеков от разных контрагентов</strong>. Каждый чек сохранит свой ИНН продавца и список товаров. Для добавления чека используйте кнопки «Загрузить чек», «Сканировать QR» или «Внести вручную».
      </v-alert>

      <!-- Инфо про авто-заявку при создании авансового -->
      <v-alert
        v-if="formMode === 'advance_report' && !isEdit"
        type="warning"
        variant="tonal"
        density="compact"
        class="mb-3"
        icon="mdi-file-document-check-outline"
      >
        При сохранении будет автоматически создана <strong>заявка на возмещение</strong> (статус «На согласовании»). После одобрения руководителем вам вернут средства.
      </v-alert>

      <!-- 1. Основная информация -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Основная информация</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <div id="pub-target-subsidy" :class="entityChanges.isFieldUnseen('subsidy_id') ? 'field-changed' : ''"
                @click="entityChanges.dismissField('subsidy_id')">
                <v-select v-model="form.subsidy_id" :items="subsidies" item-title="name" item-value="id"
                  :label="formMode === 'advance_report' ? 'Субсидия' : 'Субсидия *'" variant="outlined" density="compact"
                  hint="По какой субсидии финансируется закупка" persistent-hint
                  :rules="formMode === 'advance_report' ? [] : [r => !!r || 'Выберите субсидию']" data-field="subsidy_id" @update:model-value="onSubsidyChange" />
              </div>
            </v-col>
            <!-- Авансовый без субсидии: плейсхолдер ФЭО «Не определена» -->
            <v-col v-if="formMode === 'advance_report' && !form.feo_category_id && !form.subsidy_id" cols="12" md="4">
              <v-chip size="small" color="grey" variant="tonal">Категория ФЭО: Не определена</v-chip>
              <div class="text-caption text-medium-emphasis mt-1">Укажите субсидию, чтобы выбрать категорию ФЭО</div>
            </v-col>
            <v-col v-if="isSectionVisible('contractor')" cols="12" md="3">
              <div :class="entityChanges.isFieldUnseen('contractor_id') ? 'field-changed' : ''"
                @click="entityChanges.dismissField('contractor_id')">
                <v-autocomplete
                  v-model="form.contractor_id"
                  :items="contractors"
                  item-title="name"
                  item-value="id"
                  label="Контрагент"
                  variant="outlined"
                  density="compact"
                  clearable
                  auto-select-first
                  :custom-filter="contractorFilter"
                  :loading="contractorSearchLoading || contractorsInitialLoading"
                  :no-data-text="contractorsNoDataText"
                  :menu-props="{ maxWidth: 500 }"
                  :readonly="contractHeaderLocked"
                  :bg-color="contractHeaderLocked ? 'grey-lighten-4' : undefined"
                  :hint="contractHeaderLocked ? contractHeaderLockedHint : 'Поставщик/исполнитель. Поиск по названию или ИНН'"
                  persistent-hint
                  data-field="contractor_id"
                  @update:search="onContractorSearch"
                  @update:model-value="onContractorSelect"
                  @click:clear="onContractorClear"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps" :title="undefined">
                      <template #title>
                        <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
                      </template>
                      <template #subtitle>
                        <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
                      </template>
                    </v-list-item>
                  </template>
                  <template #append-inner>
                    <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
                      title="Добавить контрагента" @click.stop="openAddContractor" />
                  </template>
                </v-autocomplete>
              </div>
            </v-col>
            <!-- Contract type choice after selecting contractor -->
            <v-col v-if="showContractTypeChoice" cols="12">
              <v-alert type="info" variant="tonal" density="compact" class="mb-0">
                <div class="text-body-2 font-weight-medium mb-2">У контрагента есть рамочные договоры. Выберите тип:</div>
                <div class="d-flex flex-wrap gap-2">
                  <v-btn size="small" variant="tonal" color="grey" prepend-icon="mdi-file-document-outline" @click="selectContractType('single')">
                    Разовый договор
                  </v-btn>
                  <v-btn v-for="fc in contractorFrameworkContracts" :key="fc.id"
                    size="small" variant="tonal" color="primary" prepend-icon="mdi-file-document-multiple-outline"
                    @click="selectContractType('framework', fc)">
                    Рамочный {{ fc.number }} {{ fc.max_amount ? '(' + Number(fc.max_amount).toLocaleString('ru-RU') + ' ₽)' : '' }}
                  </v-btn>
                </div>
              </v-alert>
            </v-col>
            <v-col v-if="isSectionVisible('contractor')" cols="12" md="2">
              <v-text-field
                v-model="contractorInn"
                label="ИНН"
                variant="outlined"
                density="compact"
                maxlength="12"
                hint="Введите ИНН — если контрагент найден, он подставится. Если нет — добавьте нового." persistent-hint
                @update:model-value="onInnInput"
              >
                <template #prepend-inner>
                  <v-icon size="18" color="grey">mdi-domain</v-icon>
                </template>
              </v-text-field>
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery' && formMode !== 'advance_report'" cols="12" md="2">
              <v-select v-model="form.purchase_method"
                :items="[{value:'single',title:'Единственный поставщик'},{value:'competitive',title:'Конкурсная процедура'},{value:'advance',title:'Авансовый отчёт'}]"
                item-title="title" item-value="value" label="Способ закупки" variant="outlined" density="compact"
                hint="Как выбирается поставщик" persistent-hint />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery' && formMode !== 'advance_report' && form.purchase_method === 'competitive'" cols="12" md="2">
              <v-select v-model="form.competitive_form"
                :items="[{value:'price_request',title:'Запрос цен'},{value:'auction',title:'Аукцион (редукцион)'},{value:'tender',title:'Конкурс'}]"
                item-title="title" item-value="value" label="Форма процедуры" variant="outlined" density="compact"
                hint="Конкретная форма конкурентной процедуры — попадёт в приказ о закупке" persistent-hint />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="2">
              <v-select v-model="form.item_type"
                :items="[{value:'товар',title:'Поставка товара'},{value:'услуга',title:'Оказание услуг'},{value:'mixed',title:'Поставка товаров и услуг'}]"
                item-title="title" item-value="value" label="Тип закупки" variant="outlined" density="compact"
                hint="Выберите тип закупки" persistent-hint />
            </v-col>
            <!-- ЭТП: ссылка на конкурсную процедуру — скрыто для единственного поставщика -->
            <v-col v-if="formMode !== 'service_note_delivery' && formMode !== 'advance_report' && form.purchase_method !== 'single'" cols="12" md="4">
              <v-text-field
                v-model="form.etp_url"
                label="Ссылка на процедуру ЭТП"
                variant="outlined"
                density="compact"
                clearable
                placeholder="https://zakupki.gov.ru/..."
                hint="Если закупка проводилась через электронную торговую площадку"
                persistent-hint
                @blur="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="4">
              <div id="pub-target-subject" style="position:relative">
              <div v-if="pointerTarget === 'subject'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
              <div :class="[entityChanges.isFieldUnseen('subject') ? 'field-changed' : '', pointerTarget === 'subject' ? 'pub-glow' : '']"
                @click="entityChanges.dismissField('subject')">
                <v-text-field
                  v-model="form.subject"
                  :label="formMode === 'advance_report' ? 'Предмет авансового' : `Предмет ${contractWordGen}`"
                  variant="outlined"
                  density="compact"
                  placeholder="Поставка оборудования..."
                  hint="Краткое описание: что закупается" persistent-hint
                  data-field="subject"
                />
                <div v-if="entityChanges.isFieldUnseen('subject')" class="field-changed-info" @click.stop="openFieldHistory('subject')">
                  <v-icon size="14" color="#fb923c">mdi-history</v-icon>
                  <span class="text-caption" style="color:#fb923c;margin-left:2px">изменено — нажмите чтобы увидеть</span>
                  <v-card v-if="fieldHistoryMenu['subject']" class="field-history-card elevation-4 pa-2" @click.stop>
                    <div v-if="fieldHistoryData['subject']?.length">
                      <div v-for="(h, idx) in fieldHistoryData['subject']" :key="idx" class="text-caption mb-1">
                        <span class="text-medium-emphasis">было: </span><b>{{ h.old_value ?? '—' }}</b>
                        <span v-if="h.changed_by_name" class="text-medium-emphasis">, {{ h.changed_by_name }}</span>
                        <span class="text-medium-emphasis">, {{ formatHistoryDate(h.changed_at) }}</span>
                      </div>
                    </div>
                    <div v-else class="text-caption text-medium-emphasis">Загрузка...</div>
                    <v-btn size="x-small" variant="text" @click="fieldHistoryMenu['subject'] = false">Закрыть</v-btn>
                  </v-card>
                </div>
              </div>
              <v-expand-transition>
                <v-autocomplete
                  v-if="showVehicleSelect"
                  v-model="form.vehicle_id"
                  :items="vehicleOptions"
                  item-title="label"
                  item-value="id"
                  label="Автомобиль"
                  prepend-inner-icon="mdi-car"
                  clearable
                  variant="outlined"
                  density="compact"
                  :loading="vehiclesLoading"
                  class="mt-2"
                  hint="Связать закупку с ТС"
                  persistent-hint
                  @update:search="onVehicleSearch"
                />
              </v-expand-transition>
              </div><!-- /pub-target-subject -->
            </v-col>
            <!-- B-dedup: «Исполнитель (для документов)» удалён как дубль «Ответственного исполнителя».
                 В шаблоне СЗ {{responsible_person}} = ФИО → инициалы автоматически (форматирование на backend). -->

            <!-- SN-UX: Кому служебная записка (адресат) — только для service_note_delivery -->
            <v-col v-if="formMode === 'service_note_delivery'" cols="12" md="4">
              <v-autocomplete
                v-model="form.service_note_to_user_id"
                :items="orgUsersList"
                item-title="full_name"
                item-value="id"
                label="Кому служебная записка"
                variant="outlined"
                density="compact"
                clearable
                hide-no-data
                hint="Адресат служебной записки"
                persistent-hint
                autocomplete="off"
                @update:model-value="onServiceNoteToUserChange"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-item v-bind="itemProps">
                    <template #title>{{ item.raw.full_name }}</template>
                    <template #subtitle>{{ item.raw.position || '' }}</template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <!-- SN-UX: От кого (автор СЗ, авто = текущий пользователь, редактируемо) -->
            <v-col v-if="formMode === 'service_note_delivery'" cols="12" md="4">
              <v-autocomplete
                v-model="form.service_note_by"
                :items="orgUsersList"
                item-title="full_name"
                item-value="id"
                label="От кого"
                variant="outlined"
                density="compact"
                clearable
                hide-no-data
                hint="Автор служебной записки (по умолчанию — вы)"
                persistent-hint
                autocomplete="off"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-item v-bind="itemProps">
                    <template #title>{{ item.raw.full_name }}</template>
                    <template #subtitle>{{ item.raw.position || '' }}</template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <!-- SN-UX: Дата СЗ (авто = сегодня, редактируемо) -->
            <v-col v-if="formMode === 'service_note_delivery'" cols="12" md="2">
              <v-text-field
                v-model="form.service_note_at"
                type="date"
                label="Дата СЗ"
                variant="outlined"
                density="compact"
                hint="По умолчанию — сегодня"
                persistent-hint
              />
            </v-col>
            <!-- SN-UX: Обоснование (для каких целей требуется) -->
            <v-col v-if="formMode === 'service_note_delivery'" cols="12">
              <v-textarea
                v-model="form.service_note_text"
                label="Обоснование *"
                variant="outlined"
                density="compact"
                rows="3"
                auto-grow
                hint="Для каких целей необходимо это оборудование / материалы"
                persistent-hint
                :rules="[v => !!(v && String(v).trim()) || 'Обязательное поле']"
              />
            </v-col>
            <!-- Phase 28 B4: Ответственный исполнитель (user FK, обязательное) -->
            <v-col cols="12" md="4">
              <v-autocomplete
                v-model="form.assigned_user_id"
                :items="orgUsersList"
                item-title="full_name"
                item-value="id"
                :label="formMode === 'service_note_delivery' ? 'Ответственный исполнитель' : 'Ответственный исполнитель *'"
                variant="outlined"
                density="compact"
                hide-no-data
                :rules="formMode === 'service_note_delivery' ? [] : [v => !!v || 'Обязательное поле']"
                :hint="formMode === 'service_note_delivery' ? 'На кого расписана СЗ (автоматически = адресат)' : 'Кто ведёт закупку в системе'"
                persistent-hint
                autocomplete="off"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-item v-bind="itemProps">
                    <template #title>{{ item.raw.full_name }}</template>
                    <template #subtitle>{{ item.raw.position || '' }}</template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <!-- Fallback: категория ФЭО записана, но не найдена в справочнике (удалена/недоступна) -->
            <v-col v-if="feoCategoryMissing" cols="12" md="4">
              <v-text-field
                :model-value="'Категория ФЭО недоступна (была удалена)'"
                label="Категория ФЭО"
                variant="outlined"
                density="compact"
                readonly
                :hint="`ID категории: ${form.feo_category_id}`"
                persistent-hint
                error
                error-messages="Категория удалена из справочника — выберите другую"
              />
            </v-col>
            <!-- Дерево категорий ФЭО (замена трёхуровневого каскада) — один узел любой глубины,
                 промежуточные уровни заполняются автоматически при клике на лист. -->
            <v-col v-if="form.subsidy_id && feoTreeNodes.length" cols="12" md="4">
              <FeoTreeSelect
                v-model="form.feo_category_id"
                :nodes="feoTreeNodes"
                :leaves="feoTreeLeavesForNote"
                :error="feoSaveAttempted && !!feoValidationError"
                :allow-unallocated="!!form.subsidy_id"
                :required="formMode !== 'service_note_delivery' && formMode !== 'advance_report'"
                :root-label="selectedSubsidyName"
                @pick-unallocated="onFeoPickUnallocated"
              />
            </v-col>
            <!-- Владелец (сессия 2026-08-21): шапочный read-only перечень плановых позиций
                 категории (просмотр + удаление) убран — дублирует то же самое, что уже
                 показывает построчный FeoPlannedItemsSelect в таблице позиций ниже, когда
                 открываешь его выпадающий список (тот же fmt/остаток/кнопка «удалить»,
                 см. filteredItems в FeoPlannedItemsSelect.vue). Единственное отличие
                 (видно даже без открытия строки) не перевешивает дублирование — обоснование
                 в отчёте задачи. Просмотр/удаление доступны через построчный выбор
                 (allow-per-item-plan, см. PurchaseItemsEditor ниже), даже в режиме «одна
                 категория на всю закупку». -->
            <!-- Переключатель «не указывать последний уровень ФЭО»: виден, когда выбран
                 промежуточный (не листовой) узел — раньше это было «выбран ур.1 с детьми». -->
            <v-col v-if="form.feo_category_id && !feoSelectedIsLeaf && formMode !== 'service_note_delivery' && formMode !== 'advance_report'" cols="12">
              <v-switch
                v-model="feoSkipLast"
                label="Не указывать последний уровень ФЭО"
                density="compact"
                color="primary"
                hide-details
                class="mb-2"
              />
              <div v-if="feoSkipLast" class="text-caption text-medium-emphasis mt-n2 mb-2">
                Закупка будет привязана к выбранному уровню без детализации до конечной категории.
              </div>
            </v-col>
            <!-- F-PIF1: тогл «Разные ФЭО позиции для каждого товара» -->
            <v-col v-if="(feoSelectedLevel && feoSelectedLevel >= 2) || form.feo_per_item" cols="12">
              <v-switch
                v-model="form.feo_per_item"
                label="Разные категории ФЭО для каждого товара"
                density="compact"
                color="primary"
                hide-details
                class="mb-2"
                @update:model-value="onFeoPerItemChange"
              />
            </v-col>
            <v-col v-if="formMode === 'advance_report'" cols="12" md="4">
              <v-text-field
                v-model="form.advance_report_number"
                label="Номер авансового отчёта"
                variant="outlined"
                density="compact"
                placeholder="Введите номер вручную"
                prepend-inner-icon="mdi-file-document-outline"
              />
            </v-col>
            <v-col v-if="formMode === 'advance_report' || form.purchase_method === 'advance'" cols="12" md="4">
              <v-autocomplete
                v-model="form.reimbursement_user_id"
                :items="reimbursementUserOptions"
                item-title="full_name"
                item-value="id"
                label="Кому возмещать"
                variant="outlined" density="compact" clearable hide-details
              />
            </v-col>
            <v-col v-if="!(formMode === 'advance_report' && isNew)" cols="12" md="4">
              <v-text-field :model-value="form.registry_number || (isNew ? '—' : '')" label="Реестровый номер"
                variant="outlined" density="compact"
                :readonly="!isSuperadmin || isNew"
                bg-color="grey-lighten-4"
                :hint="isNew ? 'Присвоится после сохранения' : 'Генерируется автоматически'" persistent-hint
                @update:model-value="onAutoFieldChange('registry_number', 'Реестровый номер', $event)" />
            </v-col>
            <!-- Мероприятие (после выбора субсидии, или всегда для служебных записок) -->
            <v-col v-if="(form.subsidy_id && filteredEvents.length) || formMode === 'service_note_delivery'" cols="12" md="4">
              <div class="d-flex align-center gap-2">
                <v-select
                  v-model="form.event_id"
                  :items="filteredEvents"
                  item-title="name" item-value="id"
                  label="Мероприятие *"
                  variant="outlined" density="compact"
                  :rules="[v => !!v || 'Обязательное поле']"
                  hint="К какому мероприятию относится закупка" persistent-hint
                  class="flex-grow-1"
                />
                <v-tooltip v-if="!isNew && !form.event_id" location="top" text="Мероприятие не привязано">
                  <template #activator="{ props: tooltipProps }">
                    <v-icon v-bind="tooltipProps" icon="mdi-calendar-alert" color="warning" class="mb-5" />
                  </template>
                </v-tooltip>
              </div>
            </v-col>
            <!-- Мероприятие не привязано, а у субсидии их вообще нет — значок вместо поля -->
            <v-col v-else-if="!isNew && form.subsidy_id && !form.event_id" cols="12" md="4">
              <div class="d-flex align-center gap-2" style="height: 40px;">
                <v-icon icon="mdi-calendar-alert" color="warning" />
                <span class="text-body-2 text-medium-emphasis">Мероприятие не привязано</span>
              </div>
            </v-col>
            <!-- delivery_date перенесена в блок «Сроки и даты» ниже -->
          </v-row>
          <!-- Тип договора: определяет предельную сумму (Разовый/Рамочный) -->
          <v-row v-if="isSectionVisible('contract_type')" class="mt-2">
            <v-col cols="12" md="3">
              <v-select v-model="form.purchase_contract_type" :items="CONTRACT_TYPES"
                item-title="title" item-value="value" label="Тип договора" variant="outlined" density="compact"
                :readonly="contractHeaderLocked"
                :bg-color="contractHeaderLocked ? 'grey-lighten-4' : undefined"
                :hint="contractHeaderLocked ? contractHeaderLockedHint : undefined"
                :persistent-hint="contractHeaderLocked"
                @update:model-value="onContractTypeChange" />
            </v-col>
            <v-col v-if="isFramework" cols="12" md="9">
              <div class="d-flex align-center gap-3 pt-1">
                <div class="flex-grow-1">
                  <template v-if="selectedFrameworkContract">
                    <div class="d-flex align-center gap-2 flex-wrap">
                      <v-chip color="primary" size="small" variant="tonal">{{ selectedFrameworkContract.number }}</v-chip>
                      <span class="text-body-2 font-weight-medium">{{ selectedFrameworkContract.contractor_name }}</span>
                      <span v-if="selectedFrameworkContract.contractor_inn" class="text-caption text-medium-emphasis">ИНН: {{ selectedFrameworkContract.contractor_inn }}</span>
                    </div>
                    <div v-if="selectedFrameworkContract.subject" class="text-caption text-medium-emphasis mt-1">{{ selectedFrameworkContract.subject }}</div>
                    <div v-if="selectedFrameworkContract.max_amount" class="text-caption font-weight-medium text-blue-darken-2 mt-1">
                      Макс. сумма: {{ Number(selectedFrameworkContract.max_amount).toLocaleString('ru-RU') }} ₽
                      <span v-if="selectedFrameworkContract.remaining_ordered != null"> · Остаток: {{ Number(selectedFrameworkContract.remaining_ordered).toLocaleString('ru-RU') }} ₽</span>
                    </div>
                  </template>
                  <span v-else class="text-medium-emphasis text-body-2">Рамочный договор не выбран</span>
                </div>
                <v-btn variant="outlined" size="small" prepend-icon="mdi-file-document-outline" @click="openFrameworkDialog">{{ selectedFrameworkContract ? 'Изменить' : 'Выбрать договор' }}</v-btn>
                <v-btn v-if="selectedFrameworkContract" icon="mdi-close" variant="text" size="small" color="error" @click="clearFrameworkContract" />
              </div>
            </v-col>
            <!-- Alert для накопительного договора -->
            <v-col v-if="isFrameworkCumulative && form.contract_id" cols="12">
              <v-alert type="info" density="compact" variant="tonal" icon="mdi-information" class="mb-0">
                Договор накопительный — сумма за поставку согласуйте с руководителем.
              </v-alert>
            </v-col>

            <v-col v-if="isFramework && form.contract_id" cols="12" md="auto">
              <v-btn
                color="primary" variant="tonal"
                prepend-icon="mdi-calendar-multiple"
                @click="monthlyStagesDialogShow = true"
                style="margin-top:6px"
              >
                Создать ежемесячные этапы
              </v-btn>
              <div class="text-caption text-medium-emphasis mt-1" style="max-width:260px">
                Сгенерировать N закупок-этапов с одинаковой суммой и разными сроками исполнения
              </div>
            </v-col>
            <v-col v-if="isFramework && form.contract_id" cols="12" md="2">
              <v-text-field :model-value="form.framework_seq" label="Порядковый № в рамочном договоре"
                variant="outlined" density="compact" type="number" min="1"
                readonly bg-color="grey-lighten-4"
                :hint="isNew ? 'Присвоится автоматически после сохранения' : 'Номер закупки внутри рамочного договора'"
                persistent-hint>
                <template v-if="isAdminLevel && !isNew" #append-inner>
                  <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editFrameworkSeq" title="Изменить вручную" />
                </template>
              </v-text-field>
            </v-col>
            <v-col v-if="isFramework && frameworkSiblings.length" cols="12">
              <div class="framework-siblings-label">
                <v-icon icon="mdi-link-variant" size="14" class="mr-1" />Закупки в рамках этого договора ({{ frameworkSiblings.length }})
              </div>
              <v-table density="compact" class="framework-siblings-table mt-1">
                <thead><tr><th style="width:50px">№</th><th>Наименование</th><th>Статус</th><th class="text-right">НМЦД</th><th class="text-right">Цена договора</th><th class="text-right">Оплачено</th></tr></thead>
                <tbody>
                  <tr v-for="s in frameworkSiblings" :key="s.id" :class="s.id === purchaseId ? 'bg-primary-lighten-5' : ''">
                    <td><v-chip :color="s.id === purchaseId ? 'primary' : 'default'" size="x-small" variant="tonal">{{ s.framework_seq ?? '—' }}</v-chip></td>
                    <td class="text-caption">{{ s.item_name || s.subject || '—' }}</td>
                    <td><v-chip :color="purchaseStatusColor(s.status)" size="x-small" variant="tonal">{{ purchaseStatusLabel(s.status) }}</v-chip></td>
                    <td class="text-right text-caption">{{ s.total_nmck ? formatMoney(Number(s.total_nmck)) : '—' }}</td>
                    <td class="text-right text-caption">{{ s.contract_price ? formatMoney(Number(s.contract_price)) : '—' }}</td>
                    <td class="text-right text-caption">{{ s.payment_amount ? formatMoney(Number(s.payment_amount)) : '—' }}</td>
                  </tr>
                  <tr class="framework-total-row">
                    <td colspan="3" class="text-caption font-weight-bold">Итого по договору</td>
                    <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.nmck) }}</td>
                    <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.price) }}</td>
                    <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.paid) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-col>
          </v-row>
          <!-- Phase 28: Условия конкретного договора — видно только если выбрана форма договора -->
          <template v-if="form.contract_form">
            <!-- Срок приёмки + неустойка — для поставки и услуг -->
            <v-row v-if="['goods_single', 'services', 'services_food'].includes(form.contract_form)" class="mt-1">
              <v-col cols="12" class="pb-0">
                <div class="text-subtitle-2 text-medium-emphasis">Условия договора</div>
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.acceptance_term_days" type="number" label="Срок приёмки (раб. дней)" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.penalty_rate" type="number" step="0.01" label="Неустойка, %/день" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field
                  v-model.number="form.warranty_period_days"
                  type="number"
                  label="Срок гарантии (раб.дней)"
                  hint="{{warranty_period_days}} в шаблонах. По умолчанию 15."
                  persistent-hint
                  density="compact"
                  variant="outlined"
                  @blur="flushAutosaveOnBlur"
                />
              </v-col>
            </v-row>
            <!-- Договор задним числом — для всех форм договора -->
            <v-row v-if="form.contract_form" class="mt-1">
              <v-col cols="12" md="6">
                <v-checkbox
                  v-model="form.is_retroactive"
                  label="Договор задним числом (ст. 425 ГК РФ)"
                  hint="Если включено, в шаблон добавляется пункт о применении условий с даты начала услуг до подписания договора. {{is_retroactive}}"
                  persistent-hint
                  density="compact"
                />
              </v-col>
              <!-- Phase 28 T8: delivery_by_supplier — для договоров поставки -->
              <v-col v-if="form.contract_form === 'goods_single'" cols="12" md="6">
                <v-checkbox
                  v-model="form.delivery_by_supplier"
                  label="Доставка силами поставщика"
                  hint="В договоре поставки: включено — поставщик доставляет сам; выключено — самовывоз со склада поставщика."
                  persistent-hint
                  density="compact"
                />
              </v-col>
              <!-- Phase 28 T8: has_stages — для договоров ГПХ (услуги) -->
              <v-col v-if="['gph_individual', 'gph_individual_rid'].includes(form.contract_form)" cols="12" md="6">
                <v-checkbox
                  v-model="form.has_stages"
                  label="Этапы оказания услуг (Приложение №1)"
                  hint="В Приложении №1 (ТЗ) есть этапы — в договор войдёт пункт о поэтапной оплате (п. 4.5.1) и упоминания «этапа оказания Услуг»."
                  persistent-hint
                  density="compact"
                />
              </v-col>
            </v-row>
            <!-- Ремонт ТС: дата ОГРНИП + номер заявки -->
            <v-row v-if="['repair_vehicle', 'repair_framework'].includes(form.contract_form)" class="mt-1">
              <v-col cols="12" class="pb-0">
                <div class="text-subtitle-2 text-medium-emphasis">Условия договора</div>
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model="form.contractor_ogrnip_date" type="date" label="Дата ОГРНИП подрядчика" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <v-col v-if="form.contract_form === 'repair_framework'" cols="6" md="3">
                <v-text-field v-model="form.repair_request_number" label="Номер заявки на ремонт" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
            </v-row>
            <!-- Сумма аванса — только для большой отчётности (теперь это ось методички, не формы) -->
            <v-row v-if="form.methodology === 'large'" class="mt-1">
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.advance_amount" type="number" label="Сумма аванса, ₽" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
            </v-row>
            <!-- Закупочная комиссия — для всех форм (нужна в Протоколе) -->
            <v-row class="mt-1">
              <v-col cols="12" class="pb-0">
                <div class="text-subtitle-2 text-medium-emphasis">Закупочная комиссия (для протокола)</div>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field v-model="form.commission_member_1_name" label="ФИО члена комиссии 1" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field v-model="form.commission_member_2_name" label="ФИО члена комиссии 2" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field v-model="form.commission_member_3_name" label="ФИО члена комиссии 3" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
              </v-col>
              <!-- Phase 28 T8: номера документов закупочной комиссии -->
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="form.procurement_protocol_number"
                  label="Номер протокола закупочной комиссии"
                  density="compact"
                  variant="outlined"
                  hint="Заполняется в шаблоне протокола. {{procurement_protocol_number}}"
                  persistent-hint
                  @blur="flushAutosaveOnBlur"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="form.procurement_order_number"
                  label="Номер приказа о закупке"
                  density="compact"
                  variant="outlined"
                  hint="Номер внутреннего приказа, подтверждающего проведение закупки. {{procurement_order_number}}"
                  persistent-hint
                  @blur="flushAutosaveOnBlur"
                />
              </v-col>
            </v-row>
          </template>
        </v-card-text>
      </v-card>

      <!-- 1.5. Основание закупки -->
      <v-card v-if="formMode !== 'service_note_delivery'" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Основание закупки</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-select v-model="form.purchase_basis" clearable
                :items="[{value:'plan_schedule',title:'План закупок'},{value:'service_note',title:'Служебная записка'}]"
                item-title="title" item-value="value" label="Основание закупки" variant="outlined" density="compact"
                hint="Документ-основание для закупки" persistent-hint />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 1.7. Чеки (для авансовых отчётов и обычных закупок — позиции из чека добавляются в закупку) -->
      <PurchaseReceiptsBlock
        v-if="!showReceiptsOnTop && showReceiptsBlock"
        variant="block"
        :receipts="receipts"
        :purchase-id="purchaseId"
        :is-edit="isEdit"
        :source-label="sourceLabel"
        :on-scan-qr-click="onScanQrClick"
        :on-json-btn-click="onJsonBtnClick"
        :on-manual-click="onManualBtnClick"
        :on-json-receipt-upload="onJsonReceiptUpload"
        :on-delete-receipt="deleteReceipt"
      />

      <!-- 2. Позиции закупки -->
      <v-card id="pub-target-items" variant="outlined" class="mb-4" style="position:relative">
        <div v-if="pointerTarget === 'items'" class="pub-pointer" style="top:-42px;left:50%;"><span class="mdi mdi-arrow-down-bold" /></div>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center justify-end">
          <div class="d-flex align-center ga-2">
            <v-btn
              v-if="canSplitPurchase"
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-call-split"
              @click="openSplitKanban"
            >
              Разбить на закупки
            </v-btn>
            <v-chip v-if="isContracted && savedNmck" color="orange" variant="tonal" size="small" :title="`Зафиксирована при заключении ${contractWordGen}`">
              НМЦД (фикс.): {{ formatMoney(savedNmck) }}
            </v-chip>
            <v-chip color="primary" variant="tonal" size="small">
              {{ isContracted ? 'Текущая сумма' : 'НМЦД' }}: {{ formatMoney(displayNmck) }}
            </v-chip>
          </div>
        </v-card-title>
        <v-card-text>
          <PurchaseItemsEditor
            ref="itemsEditorRef"
            v-model="items"
            v-model:contract-items="contractItemsState"
            :items-title="formMode === 'service_note_delivery' ? 'Что надо выдать' : undefined"
            :show-contract-columns="canShowContractColumns"
            :unified-stages-view="canShowContractColumns"
            :purchase-status="form.status"
            item-shape="purchase"
            :purchase-id="purchaseId"
            :default-unit="'шт.'"
            :default-country="'РФ'"
            :allowed-item-types="['товар','услуга','работа']"
            :supports-excel-import="true"
            :supports-smart-import="true"
            :supports-full-product-dialog="true"
            :supports-photo-upload="true"
            :vat-mode="form.vat_mode"
            :uniform-vat-rate="form.vat_applicable ? String(form.vat_rate ?? '') : null"
            :form-mode="formMode"
            :contractors="contractors"
            :feo-per-item="form.feo_per_item"
            :level2-id="itemsFeoLevel2"
            :subsidy-id="form.subsidy_id"
            :subsidy-name="selectedSubsidyName"
            :purchase-id-feo="purchaseId"
            :default-feo-category-id="form.feo_category_id"
            :feo-planned-per-item="form.feo_per_item"
            :allow-per-item-plan="!!form.feo_category_id"
            :planned-items="purchasePlannedResiduals"
            :feo-excess-amount="purchaseData?.feo_excess_amount ?? null"
            :feo-excess-category-id="purchaseData?.feo_excess_category_id ?? null"
            @update:vat-mode="(v: string) => { form.vat_mode = v; onVatModeChange(v) }"
            @items-changed="syncContractPriceIfSingle"
            @reload-requested="loadPurchase"
            @product-created="onProductCreatedFromEditor"
            @planned-item-created="reloadPurchasePlanned"
            @planned-item-deleted="reloadPurchasePlanned"
          />
          <!-- 12-02: FEO auto-match suggestion chips -->
          <div v-if="feoMatchSuggestions.length" class="px-4 pb-2">
            <div class="text-caption text-medium-emphasis mb-1">Похожие позиции ФЭО плана:</div>
            <v-chip
              v-for="match in feoMatchSuggestions"
              :key="match.suggested_item_id"
              size="x-small"
              color="teal"
              variant="tonal"
              prepend-icon="mdi-link-variant"
              closable
              class="mr-1 mb-1"
              @click:close="feoMatchSuggestions = feoMatchSuggestions.filter(m => m.suggested_item_id !== match.suggested_item_id)"
              @click="applyFeoMatch(match.item_index, match.suggested_item_id)"
            >
              {{ match.item_name }} → {{ match.suggested_name }} ({{ Math.round(match.confidence * 100) }}%). Привязать?
            </v-chip>
          </div>
        </v-card-text>
      </v-card>

      <!-- 2.5 Техническое задание (показывается когда есть позиции) -->
      <v-card v-if="hasProducts" variant="outlined" class="mb-4" style="border-color:#3B82F6">
        <v-card-title
          class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between"
          style="cursor:pointer;user-select:none"
          @click.self="toggleTz"
        >
          <span class="d-flex align-center gap-2" style="cursor:pointer" @click="toggleTz">
            <v-icon icon="mdi-clipboard-text-outline" color="primary" size="20" />
            Техническое задание
            <v-icon
              :icon="tzCollapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
              size="18"
              color="grey"
              class="ml-1"
            />
          </span>
          <div class="d-flex align-center gap-2" @click.stop>
            <v-btn-toggle v-model="form.description_mode" mandatory density="compact" color="primary" class="mr-2">
              <v-btn value="exact" size="small" style="text-transform:none;letter-spacing:0">Точное</v-btn>
              <v-btn value="44fz" size="small" style="text-transform:none;letter-spacing:0">44-ФЗ</v-btn>
            </v-btn-toggle>
            <v-menu v-if="isEdit">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  size="small"
                  variant="tonal"
                  color="primary"
                  prepend-icon="mdi-file-word-outline"
                  append-icon="mdi-chevron-down"
                  :loading="!!docLoading && docLoading.startsWith('tech_spec')"
                >
                  Скачать ТЗ (.docx)
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-file-search-outline" @click="downloadDoc('tech_spec_request')">
                  <v-list-item-title>ТЗ для запроса цен</v-list-item-title>
                </v-list-item>
                <v-list-item prepend-icon="mdi-file-sign" @click="downloadDoc('tech_spec_contract')">
                  <v-list-item-title>ТЗ для договора</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <v-chip v-else size="small" color="grey" variant="tonal">Сохраните закупку для скачивания</v-chip>
          </div>
        </v-card-title>
        <v-card-text v-show="!tzCollapsed" class="pa-0">
          <v-table density="comfortable" class="tz-table">
            <thead>
              <tr class="tz-table-header">
                <th style="width:36px;text-align:center">№</th>
                <th style="width:72px;text-align:center">Фото</th>
                <th>Наименование и описание</th>
                <th style="width:70px;text-align:center">Кол-во</th>
                <th style="width:56px;text-align:center">Ед.</th>
                <th style="width:120px;text-align:right">Цена ед., ₽</th>
                <th style="width:130px;text-align:right">Сумма, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, i) in items.filter(x => x.item_name?.trim())" :key="i" style="vertical-align:middle">
                <td class="text-center text-medium-emphasis">{{ i + 1 }}</td>
                <td class="text-center py-2">
                  <v-avatar v-if="item._photo_url" size="56" rounded="sm" style="overflow:hidden">
                    <img :src="item._photo_url" style="width:56px;height:56px;object-fit:cover;display:block" />
                  </v-avatar>
                  <v-icon v-else size="40" color="grey-lighten-2">mdi-image-off-outline</v-icon>
                </td>
                <td class="py-2">
                  <div class="font-weight-medium" style="font-size:13px">{{ item.item_name }}</div>
                  <div v-if="activeDescription(item)" class="text-caption text-medium-emphasis mt-1" style="white-space:pre-line;max-width:420px">
                    {{ activeDescription(item) }}
                  </div>
                  <v-chip v-if="form.description_mode === '44fz' && !item._description_44fz && item._description" size="x-small" variant="tonal" color="warning" class="mt-1">нет описания 44-ФЗ</v-chip>
                </td>
                <td class="text-center">{{ item.quantity ?? '—' }}</td>
                <td class="text-center">{{ item.unit || '—' }}</td>
                <td class="text-right">{{ nmckMode === 'manual' ? '—' : (item.unit_price != null ? item.unit_price.toLocaleString('ru-RU', {minimumFractionDigits:2}) : '—') }}</td>
                <td class="text-right font-weight-medium">{{ nmckMode === 'manual' ? '—' : (item.total_price != null ? item.total_price.toLocaleString('ru-RU', {minimumFractionDigits:2}) : '—') }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="tz-table-footer">
                <td colspan="6" class="text-right font-weight-bold pa-3" style="font-size:13px">Итого НМЦД:</td>
                <td class="text-right font-weight-bold pa-3 text-primary" style="font-size:13px">{{ formatMoney(displayNmck) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </v-card-text>
      </v-card>

      <PurchaseFinanceSection
        :form="form"
        :is-framework="isFramework"
        :is-framework-cumulative="isFrameworkCumulative"
        :selected-framework-contract="selectedFrameworkContract"
        :display-nmck="displayNmck"
        :nmck-hint="nmckHint"
        :contract-price-hint="contractPriceHint"
        :nmck-warning-level="nmckWarningLevel"
        :nmck-excess-pct="nmckExcessPct"
        :format-money="formatMoney"
        :calc-economy="calcEconomy"
        :pointer-target="pointerTarget"
        :is-section-visible="isSectionVisible"
        :framework-siblings="frameworkSiblings"
        :framework-totals="frameworkTotals"
        :purchase-id="purchaseId"
        v-model:nmck-mode="nmckMode"
        v-model:nmck-manual-value="nmckManualValue"
        v-model:contract-price-mode="contractPriceMode"
      />

      <!-- 4. Договор / Счёт / Счёт-договор -->
      <v-card v-if="isSectionVisible('contract')" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 pb-0">Основание для закупки</v-card-title>
        <v-tabs v-model="form.payment_basis_type" density="compact" color="primary" class="px-2 pt-1">
          <v-tab value="contract">Разовый договор</v-tab>
          <v-tab value="invoice">Счёт</v-tab>
          <v-tab value="invoice_contract">Счёт-договор</v-tab>
          <v-tab value="framework_invoice">Счёт по рамочному договору</v-tab>
          <v-tab value="work_order">Заказ-наряд</v-tab>
          <v-tab value="receipt">Чек</v-tab>
        </v-tabs>
        <v-divider />
        <v-card-text>
          <v-window v-model="form.payment_basis_type">

          <!-- ── Договор ── -->
          <v-window-item value="contract">
          <v-row class="mt-1">
            <v-col cols="12" md="3" data-field-name="contract_number">
              <div :class="entityChanges.isFieldUnseen('contract_number') ? 'field-changed' : ''"
                @click="entityChanges.dismissField('contract_number')">
                <v-text-field v-model="form.contract_number" :label="`Номер ${contractWordGen}`" variant="outlined" density="compact"
                  :placeholder="isNew ? 'Присвоится после сохранения (можно ввести вручную)' : ''"
                  :hint="contractHeaderLocked ? contractHeaderLockedHint : needsContract ? `Обязательно для перехода в статус ${contractWord}` : isNew ? 'Будет присвоен автоматически или введите вручную' : 'Можно изменить вручную'"
                  persistent-hint
                  :readonly="contractHeaderLocked || (!isNew && !contractNumberEditEnabled)"
                  :bg-color="contractHeaderLocked ? 'grey-lighten-4' : undefined"
                  data-field="contract_number"
                  @click="!contractHeaderLocked && !isNew && !contractNumberEditEnabled && enableContractNumberEdit()" />
              </div>
            </v-col>
            <v-col cols="12" md="3" data-field-name="contract_date">
              <div :class="entityChanges.isFieldUnseen('contract_date') ? 'field-changed' : ''"
                @click="entityChanges.dismissField('contract_date')">
                <v-text-field v-model="form.contract_date" :label="`Дата ${contractWordGen}`" variant="outlined"
                  density="compact" type="date" :rules="contractDateRules" data-field="contract_date"
                  :readonly="contractHeaderLocked"
                  :bg-color="contractHeaderLocked ? 'grey-lighten-4' : undefined"
                  :hint="contractHeaderLocked ? 'Берётся из договора — изменить в карточке договора' : undefined"
                  :persistent-hint="contractHeaderLocked" />
              </div>
            </v-col>
            <!-- Phase 31-04: contract_conflict chip + «Взять из договора» button -->
            <v-col v-if="!isNew && purchaseData?.contract_conflict && form.contract_id" cols="12" class="d-flex align-center gap-2 pb-0">
              <v-chip
                color="warning"
                size="small"
                prepend-icon="mdi-alert"
                :title="linkedContractTooltip"
              >Расхождение с договором</v-chip>
              <v-btn
                variant="tonal"
                size="small"
                color="#fb923c"
                :loading="takingFromContract"
                @click="takeFromContract"
              >Взять из договора</v-btn>
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.agreement_number" label="№ доп.соглашения" variant="outlined"
                density="compact" placeholder="При наличии" />
            </v-col>
            <!-- agreement_date, order_date, contract_end_date, procurement_planned_date перенесены в «Сроки и даты» -->
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
            <v-col cols="12" md="2" class="d-flex align-center">
              <v-checkbox v-model="form.is_monthly_payment" label="Ежемесячный платёж"
                density="compact" hide-details color="blue" />
            </v-col>
            <template v-if="form.is_monthly_payment">
              <v-col cols="12" md="2">
                <v-text-field v-model.number="form.monthly_payment_count" label="Кол-во платежей"
                  variant="outlined" density="compact" type="number" min="1" @update:model-value="calcMonthlyTotal" />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field v-model.number="form.monthly_payment_amount" label="Сумма платежа, ₽"
                  variant="outlined" density="compact" type="number" suffix="₽" @update:model-value="calcMonthlyTotal" />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field :model-value="monthlyTotal != null ? monthlyTotal.toLocaleString('ru-RU') + ' ₽' : '—'"
                  label="Итого обязательств" variant="outlined" density="compact" readonly bg-color="grey-lighten-4"
                  hint="Не обязана совпадать с суммой договора" persistent-hint />
              </v-col>
            </template>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" hint="Необязательно" persistent-hint variant="outlined"
                density="compact" type="date" :rules="executionTermRules" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term_changed" label="Срок (с учётом изменений)"
                variant="outlined" density="compact" type="date" />
            </v-col>
          </v-row>
          </v-window-item>

          <!-- ── Счёт ── -->
          <v-window-item value="invoice">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 mt-2 text-caption">
            Счёт на оплату — выставляется поставщиком, является основанием для оплаты без заключения договора.
          </v-alert>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер счёта" variant="outlined" density="compact"
                hint="Номер счёта от поставщика" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата счёта" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <!-- procurement_planned_date перенесена в «Сроки и даты» -->
            <v-col cols="12" md="6">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" hint="Необязательно" persistent-hint variant="outlined"
                density="compact" type="date" />
            </v-col>
          </v-row>
          </v-window-item>

          <!-- ── Счёт-договор ── -->
          <v-window-item value="invoice_contract">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 mt-2 text-caption">
            Счёт-договор — упрощённая форма договора, объединяющая счёт и договорные условия. Применяется при сумме до 600 тыс. ₽.
          </v-alert>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер счёт-договора" variant="outlined" density="compact"
                hint="Номер документа от поставщика" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата счёт-договора" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <!-- contract_end_date и procurement_planned_date перенесены в «Сроки и даты» -->
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
            <v-col cols="12" md="2" class="d-flex align-center">
              <v-checkbox v-model="form.is_monthly_payment" label="Ежемесячный платёж"
                density="compact" hide-details color="blue" />
            </v-col>
            <template v-if="form.is_monthly_payment">
              <v-col cols="12" md="2">
                <v-text-field v-model.number="form.monthly_payment_count" label="Кол-во платежей"
                  variant="outlined" density="compact" type="number" min="1" @update:model-value="calcMonthlyTotal" />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field v-model.number="form.monthly_payment_amount" label="Сумма платежа, ₽"
                  variant="outlined" density="compact" type="number" suffix="₽" @update:model-value="calcMonthlyTotal" />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field :model-value="monthlyTotal != null ? monthlyTotal.toLocaleString('ru-RU') + ' ₽' : '—'"
                  label="Итого обязательств" variant="outlined" density="compact" readonly bg-color="grey-lighten-4"
                  hint="Не обязана совпадать с суммой договора" persistent-hint />
              </v-col>
            </template>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" hint="Необязательно" persistent-hint variant="outlined"
                density="compact" type="date" />
            </v-col>
          </v-row>
          </v-window-item>

          <!-- ── Счёт по РД ── -->
          <v-window-item value="framework_invoice">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 mt-2 text-caption">
            Счёт в рамках рамочного договора (РД). Выберите РД контрагента, затем укажите номер и дату счёта.
          </v-alert>
          <v-row>
            <v-col cols="12" md="6">
              <v-autocomplete
                v-model="selectedFrameworkInvoiceContract"
                :items="frameworkContractsForInvoice"
                item-title="number"
                item-value="id"
                label="Рамочный договор"
                variant="outlined"
                density="compact"
                clearable
                return-object
                hint="При выборе контрагента выше — показываются только его договора по данной субсидии"
                persistent-hint
                @update:model-value="onFrameworkInvoiceSelect"
              >
                <template #item="{ item, props: itemProps }">
                  <v-list-item v-bind="itemProps" :title="undefined">
                    <template #title>
                      <span class="font-weight-medium">{{ item.raw.number }}</span>
                      <span v-if="item.raw.contractor_name" class="text-caption text-medium-emphasis ml-2">{{ item.raw.contractor_name }}</span>
                    </template>
                    <template #subtitle>
                      <span v-if="item.raw.max_amount" class="text-caption">
                        Макс: {{ Number(item.raw.max_amount).toLocaleString('ru-RU') }} ₽
                        <span v-if="item.raw.remaining_ordered != null"> · Остаток: {{ Number(item.raw.remaining_ordered).toLocaleString('ru-RU') }} ₽</span>
                      </span>
                    </template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер счёта" variant="outlined" density="compact"
                hint="Номер счёта от поставщика" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата счёта" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" hint="Необязательно" persistent-hint variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
          </v-row>
          </v-window-item>

          <!-- ── Заказ-наряд ── -->
          <v-window-item value="work_order">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 mt-2 text-caption">
            Заказ-наряд — документ на выполнение работ/услуг. Используется для ремонтных, сервисных и подрядных работ.
          </v-alert>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер заказ-наряда" variant="outlined" density="compact"
                hint="Номер документа" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата заказ-наряда" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" hint="Необязательно" persistent-hint variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
          </v-row>
          </v-window-item>

          <!-- ── Чек ── -->
          <v-window-item value="receipt">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 mt-2 text-caption">
            Чек — кассовый или товарный чек. Используется для мелких закупок за наличный расчёт или по карте.
          </v-alert>

          <!-- Multi-receipts list (Phase 21) — shown only when purchase already saved -->
          <template v-if="(formMode === 'advance_report' || form.purchase_method === 'advance') && isEdit && purchaseId">
            <PurchaseReceiptsBlock
              variant="tab"
              :receipts="receipts"
              :purchase-id="purchaseId"
              :is-edit="isEdit"
              :source-label="sourceLabel"
              :on-manual-click="openManualReceiptDialog"
              :on-json-receipt-upload="onJsonReceiptUpload"
              :on-delete-receipt="deleteReceipt"
            />
          </template>
          <v-alert
            v-else-if="(formMode === 'advance_report' || form.purchase_method === 'advance') && !isEdit"
            type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
            Сохраните закупку, чтобы добавить чеки.
          </v-alert>

          <v-row>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер чека" variant="outlined" density="compact"
                hint="Можно оставить пустым при использовании списка чеков выше" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата чека" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                :label="addressLabel" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
          </v-row>
          </v-window-item>

          </v-window>
        </v-card-text>
      </v-card>

      <PurchaseContractParamsSection
        v-if="isSectionVisible('contract_params')"
        :form="form"
        :contract-word-gen="contractWordGen"
        :form-mode="formMode"
        :vat-exemption-auto-basis="vatExemptionAutoBasis"
        :on-vat-mode-change="onVatModeChange"
        :customer-preview="customerPreview"
        :contract-form-options="contractFormOptions"
        :methodology-options="methodologyOptions"
        :clear-guide-arrow="clearGuideArrow"
        :delivery-label="deliveryLabel"
        :scroll-to-dates-section="scrollToDatesSection"
        v-model:show-placeholders-dialog="showPlaceholdersDialog"
        v-model:pointer-target="pointerTarget"
      />

      <PurchaseDatesSection
        :form="form"
        :is-framework="isFramework"
        :selected-framework-contract="selectedFrameworkContract"
      />

      <PurchaseAcceptanceSection
        v-if="isSectionVisible('acceptance')"
        :form="form"
        :is-edit="isEdit"
        :purchase-id="purchaseId"
        :form-mode="formMode"
        :acceptance-docs="acceptanceDocs"
        :acceptance-doc-types="acceptanceDocTypes"
        :builtin-acceptance-doc-types="BUILTIN_ACCEPTANCE_DOC_TYPES"
        :add-acceptance-doc="addAcceptanceDoc"
        :download-acceptance-file="downloadAcceptanceFile"
        :on-acceptance-doc-type-add="onAcceptanceDocTypeAdd"
        :delete-custom-doc-type="deleteCustomDocType"
        :on-json-btn-click="onJsonBtnClick"
        :on-acceptance-doc-files-dropped="onAcceptanceDocFilesDropped"
      />

      <PurchasePaymentSection
        v-if="isSectionVisible('payment')"
        :form="form"
        :is-edit="isEdit"
        :purchase-id="purchaseId"
        :uploading="uploading"
        :pending-section-upload="pendingSectionUpload"
        :payment-files="paymentFiles"
        :upload-for-section="uploadForSection"
        :delete-file="deleteFile"
        :download-file="downloadFile"
        :toggle-file-active="toggleFileActive"
      />

      <!-- Платежи — только для обычных закупок (не advance_report, не service_note) -->
      <PaymentsBlock
        v-if="formMode === 'order' || formMode === 'default'"
        :purchase-id="isEdit ? purchaseId : null"
        :contract-price="form.contract_price"
        :planned-total-price="null"
        :status="form.status"
        @changed="loadPurchase"
      />

      <!-- Обсуждение — linked chat room -->
      <v-card v-if="isEdit && purchaseId" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
          <v-icon icon="mdi-chat-outline" class="mr-2" color="blue" />
          Обсуждение
        </v-card-title>
        <v-card-text class="pa-2">
          <ChatEmbed
            :entity-type="'purchase'"
            :entity-id="purchaseId"
            :title="form.subject ? `Закупка: ${form.subject}` : `Закупка #${purchaseId}`"
          />
        </v-card-text>
      </v-card>

      <!-- Purchase broadcast dialog -->
      <PurchaseBroadcastDialog
        v-model="pBroadcastDialog"
        v-model:scope="pBroadcastScope"
        v-model:scope-id="pBroadcastScopeId"
        v-model:text="pBroadcastText"
        :sending="pBroadcastSending"
        :orgs="pBroadcastOrgs"
        :depts="pBroadcastDepts"
        @send="sendPurchaseBroadcast"
      />

      <PurchaseDocumentsCard
        v-if="canSeePurchaseDocs"
        :purchase-id="purchaseId"
        :uploading="uploading"
        :pending-section-upload="pendingSectionUpload"
        :doc-upload-sections="DOC_UPLOAD_SECTIONS"
        :uploaded-files="uploadedFiles"
        :file-type-labels="FILE_TYPE_LABELS"
        :upload-files-for-type="uploadFilesForType"
        :files-by-type="filesByType"
        :delete-file="deleteFile"
        :download-file="downloadFile"
        :toggle-file-active="toggleFileActive"
        :file-icon="fileIcon"
        :open-file-type-edit="openFileTypeEdit"
        :file-type-color="fileTypeColor"
        :toggle-doc-format="toggleDocFormat"
        :format-size="formatSize"
        :format-date="formatDate"
        :is-previewable="isPreviewable"
        :open-preview="openPreview"
      />
      <!-- Скрытые file-input'ы читаемых секций (см. PurchaseDocumentsCard.vue —
           ref-биндинг не переносится в дочерний компонент без forwarding'а). -->
      <input v-if="canSeePurchaseDocs" ref="sectionFileInputEl" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
        style="display:none" @change="uploadSectionFile" />
      <input v-if="canSeePurchaseDocs" ref="fileInputEl" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
        style="display:none" @change="uploadFile" />

      <!-- Диалоги файлов (загрузка / смена типа / предпросмотр) -->
      <PurchaseFileDialogs
        v-model:upload-open="uploadDialog"
        v-model:file-type-edit-open="fileTypeEditDialog"
        v-model:preview-open="previewDialog"
        v-model:upload-file-type="uploadFileType"
        v-model:upload-doc-format="uploadDocFormat"
        v-model:file-type-edit-value="fileTypeEditValue"
        v-model:file-doc-format-edit-value="fileDocFormatEditValue"
        :file-type-options="FILE_TYPE_OPTIONS"
        :file-type-edit-target="fileTypeEditTarget"
        :editable-mime="EDITABLE_MIME"
        :saving-file-type="savingFileType"
        :preview-file="previewFile"
        :preview-url="previewUrl"
        :file-icon="fileIcon"
        @choose-file="fileInputEl?.click()"
        @save-file-type="saveFileType"
        @download="(id, filename) => downloadFile(id, filename)"
      />

      <!-- 8. Формирование документов -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы</v-card-title>
        <v-card-text>
          <div class="d-flex gap-3 flex-wrap">
            <v-menu>
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  prepend-icon="mdi-file-word-outline"
                  append-icon="mdi-chevron-down"
                  variant="tonal"
                  color="blue-darken-2"
                  size="small"
                  :loading="!!docLoading && docLoading.startsWith('service_note')"
                >
                  Служебная записка
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item
                  prepend-icon="mdi-file-document-outline"
                  @click="openDocPicker('service_note_procurement')"
                >
                  <v-list-item-title>На закупку</v-list-item-title>
                </v-list-item>
                <v-list-item
                  prepend-icon="mdi-truck-delivery-outline"
                  @click="openDocPicker('service_note_delivery')"
                >
                  <v-list-item-title>На выдачу</v-list-item-title>
                </v-list-item>
                <v-list-item
                  prepend-icon="mdi-cash-check"
                  @click="openDocPicker('service_note_payment')"
                >
                  <v-list-item-title>На оплату поставленного</v-list-item-title>
                </v-list-item>
                <v-list-item
                  prepend-icon="mdi-cash-fast"
                  @click="openDocPicker('service_note_advance')"
                >
                  <v-list-item-title>На аванс</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <v-menu>
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  prepend-icon="mdi-file-word-outline"
                  append-icon="mdi-chevron-down"
                  variant="tonal"
                  color="blue-darken-2"
                  size="small"
                  :loading="!!docLoading && docLoading.startsWith('tech_spec')"
                >
                  ТЗ
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-file-search-outline" @click="downloadDoc('tech_spec_request')">
                  <v-list-item-title>ТЗ для запроса цен</v-list-item-title>
                </v-list-item>
                <v-list-item prepend-icon="mdi-file-sign" @click="downloadDoc('tech_spec_contract')">
                  <v-list-item-title>ТЗ для договора</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <!-- Phase 28: «Договор» — doc_type определяется по form.contract_form, fallback → 'contract' -->
            <v-btn v-if="isSectionVisible('contractor')"
              prepend-icon="mdi-file-document-outline"
              variant="tonal"
              color="indigo"
              size="small"
              :loading="docLoading === (form.contract_form ? contractDocTypeMap[form.contract_form] || 'contract' : 'contract')"
              @click="downloadDoc(form.contract_form ? contractDocTypeMap[form.contract_form] || 'contract' : 'contract')"
              :title="form.contract_form ? 'Форма: ' + (contractFormOptions.find(o => o.value === form.contract_form)?.title || form.contract_form) : 'Договор (универсальный) — тип определяется автоматически по позициям закупки'"
            >
              {{ contractWord }}
            </v-btn>
            <div v-if="isSectionVisible('contractor')" class="text-caption text-medium-emphasis ml-2 d-flex align-center">
              <template v-if="form.contract_form">
                {{ contractFormOptions.find(o => o.value === form.contract_form)?.title || form.contract_form }}
              </template>
              <template v-else>
                Тип определяется автоматически по типу позиций
              </template>
              <v-tooltip :text="form.contract_form ? 'Форма договора выбрана явно. Изменить можно в поле «Форма договора» выше.' : 'Все позиции \'услуга\' → договор оказания услуг. Иначе → договор поставки.'" location="top">
                <template #activator="{ props: tip }">
                  <v-icon v-bind="tip" icon="mdi-information-outline" size="14" class="ml-1" />
                </template>
              </v-tooltip>
            </div>
            <v-btn v-if="isSectionVisible('contractor')"
              prepend-icon="mdi-file-multiple-outline"
              variant="tonal"
              color="indigo-darken-2"
              size="small"
              :loading="docLoading === 'contract_merge'"
              @click="downloadDoc(form.contract_form ? contractDocTypeMap[form.contract_form] || 'contract' : 'contract', '?merge=tech_spec_contract', 'contract_merge')"
              title="Скачать Договор и ТЗ одним файлом"
            >
              {{ contractWord }} + ТЗ
            </v-btn>
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'approval_sheet'"
              @click="openDocPicker('approval_sheet')"
            >
              Лист согласования
            </v-btn>
            <v-divider vertical class="mx-1" />
            <v-btn
              prepend-icon="mdi-folder-zip-outline"
              variant="tonal"
              color="orange-darken-2"
              size="small"
              :loading="docLoading === 'fabrikant_package'"
              @click="downloadFabrikantPackage"
              title="Пакет документов для публикации на Фабрикант (5 файлов)"
            >
              Пакет для Фабриканта (ZIP)
            </v-btn>
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            Документы формируются по шаблонам из backend/templates/
          </div>
        </v-card-text>
      </v-card>

      <!-- 8.5 Согласование (approval chain) -->
      <ApprovalPanel
        ref="approvalPanelRef"
        :purchase-id="purchaseId!"
        :approval-status="form.approval_status"
        :approval-mode="form.approval_mode"
        :is-manager="isManagerLevel"
        :is-admin="isAdminLevel"
        :visible="isEdit && showApprovalSection"
        :subsidy-id="form.subsidy_id"
        :is-framework-head="isFrameworkHeadPurchase"
        @update:approval-status="form.approval_status = $event"
        @update:approval-mode="form.approval_mode = $event"
        @snack="showSnack($event, arguments[1])"
      />

      <!-- 9. Запрос КП (manager+) -->
      <v-card v-if="isEdit && isSectionVisible('commercial_requests')" variant="outlined" class="mb-4" style="border-color:#0891B2">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
          <span class="d-flex align-center gap-2">
            <v-icon icon="mdi-email-send-outline" color="cyan-darken-2" size="20" />
            Запрос коммерческих предложений
          </span>
          <v-btn color="cyan-darken-2" variant="tonal" size="small" prepend-icon="mdi-email-multiple-outline"
            @click="kpDialogRef?.openKpDialog()">
            Разослать КП
          </v-btn>
        </v-card-title>
        <v-card-text class="px-4 pb-3 text-caption text-medium-emphasis">
          Отправьте запрос КП поставщикам с описанием закупки. Письма формируются через почтовый клиент.
        </v-card-text>
      </v-card>

      <PurchasePlatformCard
        v-if="isEdit && isSectionVisible('platform_publication') && canPublish"
        :doc-loading="docLoading"
        :download-fabrikant-package="downloadFabrikantPackage"
        :open-publish-dialog="openPublishDialog"
        :publications="publications"
        :PLATFORM_LABELS="PLATFORM_LABELS"
        :PUB_STATUS_COLOR="PUB_STATUS_COLOR"
        :PUB_STATUS_LABEL="PUB_STATUS_LABEL"
        :refreshing-pub-id="refreshingPubId"
        :refresh-pub-status="refreshPubStatus"
        :open-fabrikant-retry="openFabrikantRetry"
        :retry-publish="retryPublish"
        :FABRIKANT_PKG_DOCS="FABRIKANT_PKG_DOCS"
        :fabrikant-override="fabrikantOverride"
        :download-file="downloadFile"
        :delete-fabrikant-override="deleteFabrikantOverride"
        :trigger-fabrikant-upload="triggerFabrikantUpload"
      />
      <!-- Скрытый file-input оверрайда пакета Фабрикант (см. PurchasePlatformCard.vue
           — ref-биндинг не переносится в дочерний компонент без forwarding'а). -->
      <input v-if="isEdit && isSectionVisible('platform_publication') && canPublish"
        ref="fabrikantFileInputEl" type="file" accept=".docx,.pdf" style="display:none"
        @change="uploadFabrikantOverride" />

      <PurchaseLinkedTasksCard
        v-if="isEdit && purchaseId"
        :purchase-id="purchaseId"
        :linked-tasks="linkedTasks"
        :open-create-linked-task="openCreateLinkedTask"
        :task-status-color="taskStatusColor"
        :task-priority-color="taskPriorityColor"
        :TASK_STATUS_LABEL="TASK_STATUS_LABEL"
        :unlink-task="unlinkTask"
      />

      <!-- Диалоги задач закупки -->
      <LinkedTaskDialogs
        v-model:linked-task-open="linkedTaskDialog"
        v-model:link-open="linkTaskDialog"
        v-model:search-text="linkTaskSearch"
        :form="linkedTaskForm"
        :saving="linkedTaskSaving"
        :all-users="allUsers"
        :results="linkTaskResults"
        :searching="linkTaskSearching"
        @save="saveLinkedTask"
        @search="searchUnlinkedTasks"
        @link="linkExistingTask"
      />

      <!-- Кнопки -->
      <div class="d-flex gap-3 mt-4 flex-wrap align-center">
        <v-btn ref="saveBtnRef" type="submit" color="primary" size="large" :loading="saving" prepend-icon="mdi-content-save">
          {{ isEdit ? 'Сохранить' : formMode === 'advance_report' ? 'Сформировать авансовый' : formMode === 'service_note_delivery' ? 'Создать служебную записку' : 'Создать закупку' }}
        </v-btn>
        <!-- Phase 26: индикатор автосохранения -->
        <v-chip
          v-if="isEdit && autosaveState !== 'idle'"
          size="small"
          :color="autosaveState === 'saving' ? 'grey' : autosaveState === 'saved' ? 'success' : 'error'"
          variant="tonal"
        >
          <v-icon
            :icon="autosaveState === 'saving' ? 'mdi-cloud-upload-outline' : autosaveState === 'saved' ? 'mdi-cloud-check' : 'mdi-cloud-alert'"
            size="14" class="mr-1"
          />
          {{ autosaveState === 'saving' ? 'Сохраняется…' : autosaveState === 'saved' ? 'Сохранено' : 'Не сохранилось' }}
        </v-chip>
        <!-- Phase 31-07: Undo/Redo кнопки -->
        <v-btn
          :disabled="!_undoRedo?.canUndo.value"
          icon="mdi-undo"
          size="small"
          variant="text"
          :color="_undoRedo?.canUndo.value ? '#fb923c' : undefined"
          title="Отменить (Ctrl+Z)"
          @click="_undoRedo?.undo()"
        />
        <v-btn
          :disabled="!_undoRedo?.canRedo.value"
          icon="mdi-redo"
          size="small"
          variant="text"
          :color="_undoRedo?.canRedo.value ? '#fb923c' : undefined"
          title="Повторить (Ctrl+Y)"
          @click="_undoRedo?.redo()"
        />
        <v-btn v-if="isEdit && nextStatusTarget" :color="STATUS_COLOR[nextStatusTarget]" size="large"
          variant="tonal" :loading="transitioning" prepend-icon="mdi-arrow-right-circle" @click="onTransitionClick">
          → {{ nextStatusTarget === 'work_in_progress' ? 'Направлено в закупку' : STATUS_LABEL[nextStatusTarget] }}
        </v-btn>
        <v-select v-if="isEdit && form.status === 'work_in_progress'" v-model="form.substatus"
          :items="SUBSTATUS_OPTIONS" item-title="title" item-value="value"
          label="Подстатус" variant="outlined" density="compact" clearable
          style="max-width:220px" hide-details class="ml-2" @update:model-value="saveSubstatus" />
        <v-btn v-if="isEdit && formMode === 'service_note_delivery'" variant="tonal" color="orange" size="large"
          prepend-icon="mdi-swap-horizontal" :loading="converting" @click="convertToOrder">
          Переоформить в закупку
        </v-btn>
        <v-btn variant="outlined" :to="backRoute" size="large">Отмена</v-btn>
      </div>
    </v-form>

    <!-- Диалог публикации на площадках -->
    <PurchasePublishDialog
      v-model:open="publishDialog"
      v-model:pending-platform="pendingPlatform"
      v-model:roseltorg-procedure-type="roseltorgProcedureType"
      v-model:fabrikant-procedure-type="fabrikantProcedureType"
      v-model:fabrikant-okpd2="fabrikantOkpd2"
      v-model:fabrikant-no-nmcd="fabrikantNoNmcd"
      v-model:fabrikant-attach-docs="fabrikantAttachDocs"
      v-model:fabrikant-auction-date-start="fabrikantAuctionDateStart"
      v-model:fabrikant-auction-bet-from="fabrikantAuctionBetFrom"
      v-model:fabrikant-auction-bet-to="fabrikantAuctionBetTo"
      v-model:publish-errors="publishErrors"
      v-model:okpd2-pointer="okpd2Pointer"
      v-model:auction-pointer-target="auctionPointerTarget"
      :publishing-platform="publishingPlatform"
      :publications="publications"
      :current-subsidy-org-inn="currentSubsidyOrgInn"
      :publish-nmck="publishNmck"
      :okpd2-items="okpd2Items"
      :okpd2-loading="okpd2Loading"
      :okpd2-error="okpd2Error"
      :fabrikant-dates="fabrikantDates"
      :format-money="formatMoney"
      :is-platform-published="isPlatformPublished"
      :check-publish-ready="checkPublishReady"
      :okpd2-item-title="okpd2ItemTitle"
      :search-okpd2="searchOkpd2"
      :do-publish="doPublish"
      :reveal-field="revealField"
      :clear-guide-arrow="clearGuideArrow"
      :init-fabrikant-dates="initFabrikantDates"
    />

    <!-- Диалог подтверждения превышения бюджета -->
    <!-- Диалоги подтверждения (превышение бюджета / отключение per-item ФЭО /
         повтор закупки / переход в «Договор») — сама логика (doSave, save/
         transition) остаётся в этом файле, компонент только показывает и
         эмитит намерение пользователя. -->
    <PurchaseConfirmDialogs
      v-model:budget-override-open="budgetOverrideDialog"
      v-model:feo-per-item-disable-open="feoPerItemDisableDialog"
      v-model:duplicate-open="duplicateDialog"
      v-model:contracted-confirm-open="showContractedConfirm"
      v-model:contract-price="form.contract_price"
      :budget-info="budgetInfo"
      :saving="saving"
      :feo-per-item-disable-count="feoPerItemDisableCount"
      :duplicate-matches="duplicateMatches"
      :contracted-confirm-items="contractedConfirmItems"
      :transitioning="transitioning"
      :display-nmck="displayNmck"
      :format-money="formatMoney"
      @save-with-override="doSave(true)"
      @cancel-feo-disable="cancelFeoPerItemDisable"
      @confirm-feo-disable="confirmFeoPerItemDisable"
      @confirm-duplicate-save="confirmDuplicateSave"
      @edit-items-before-contract="editItemsBeforeContract"
      @confirm-contracted-transition="confirmContractedTransition"
      @contract-price-edited="contractPriceMode = 'manual'"
    />

    <!-- Генератор ежемесячных этапов рамочного договора -->
    <MonthlyStagesDialog
      v-if="isFramework && form.contract_id && selectedFrameworkContract"
      v-model="monthlyStagesDialogShow"
      :contract-id="form.contract_id"
      :contract-name="(selectedFrameworkContract as any).number || (selectedFrameworkContract as any).name || ''"
      :contract-type="(selectedFrameworkContract as any).contract_type || ''"
      :default-subsidy-id="form.subsidy_id ?? null"
      :default-amount="(selectedFrameworkContract as any).planned_monthly ?? null"
      @created="onMonthlyStagesCreated"
    />

    <!-- Split purchase kanban dialog -->
    <SplitKanbanDialog
      v-model="splitKanbanDialog"
      :purchase-id="purchaseId"
      :items="splitKanbanItems"
      @split="onPurchaseSplit"
      @error="(m: string) => showSnack(m, 'error')"
    />

    <!-- Add contractor inline dialog -->
    <AddContractorDialog
      v-model="addContractorDialog"
      v-model:file="addContractorFile"
      :form="addContractorForm"
      :saving="addContractorSaving"
      :importing="addContractorImporting"
      @save="saveNewContractor"
      @import-from-file="importContractorFromFile"
      @lookup-inn="lookupContractorInn"
      @inn-change="onAddContractorInnChange"
    />

    <!-- ЕГРЮЛ diff dialog -->
    <EgrulDiffDialog
      v-model="egrulDiffDialog"
      :items="egrulDiffItems"
      :pending="egrulDiffPending"
      @apply="applyEgrulDiff"
    />

    <!-- Диалоги рамочного договора (выбор существующего / создание нового) -->
    <FrameworkDialogs
      v-model:framework-open="frameworkDialog"
      v-model:new-framework-open="newFrameworkDialog"
      v-model:framework-search="frameworkSearch"
      :framework-loading="frameworkLoading"
      :filtered-framework-contracts="filteredFrameworkContracts"
      :selected-framework-contract="selectedFrameworkContract"
      :new-framework-form="newFrameworkForm"
      :new-framework-saving="newFrameworkSaving"
      :contractors="contractors"
      :contractor-filter="contractorFilter"
      :contractors-no-data-text="contractorsNoDataText"
      @select="selectFrameworkContract"
      @save-new="saveNewFrameworkContract"
    />

    <!-- КП dialog -->
    <KpDialog ref="kpDialogRef" :purchase-id="purchaseId" :form="form" />

    <!-- Диалоги перед скачиванием документов (согласующие/закрывающие) -->
    <DocPickerDialogs
      v-model:doc-picker-open="docPickerDialog"
      v-model:acceptance-open="acceptanceDocPickerDialog"
      v-model:picker-initiator-id="pickerInitiatorId"
      v-model:picker-responsible-name="pickerResponsibleName"
      v-model:picker-approver-ids="pickerApproverIds"
      v-model:acceptance-selected="acceptanceDocPickerSelected"
      :doc-picker-type="docPickerType"
      :loading-doc-approvers="loadingDocApprovers"
      :doc-approvers="docApprovers"
      :act-as-list="actAsList"
      :responsible-options="responsibleOptions"
      :doc-loading="docLoading"
      :acceptance-docs="acceptanceDocs"
      @download="confirmDocDownload"
      @confirm-acceptance="confirmAcceptanceDocDownload"
      @add-responsible="addResponsibleDialog = true"
    />

    <!-- Диалог добавления ответственного исполнителя -->
    <AddResponsibleDialog
      v-model="addResponsibleDialog"
      v-model:name="newResponsibleName"
      v-model:position="newResponsiblePosition"
      :saving="savingResponsible"
      @save="saveNewResponsible"
    />

    <!-- Phase 21: Manual receipt dialog -->
    <ManualReceiptDialog :dialog="manualReceiptDialog" @save="saveManualReceipt" />

    <QrScannerDialog v-model="qrScanShow" @detected="onQrDetected" />

    <!-- Phase 23: диалог «Доступные переменные шаблонов» -->
    <PlaceholdersDialog v-model="showPlaceholdersDialog" />

    <!-- Phase 23.2: диалог ошибки генерации документа -->
    <DocErrorDialog
      v-model="docErrorDialog"
      :info="docErrorInfo"
      :purchase-id="purchaseId"
      :subsidy-id="form.subsidy_id"
      @reveal-field="revealField"
    />
    <ValidationArrows
      :active="validationArrowsActive"
      :from-el="validationArrowFrom"
      :to-els="validationArrowTargets"
      @dismiss="dismissValidationArrows"
    />
  </v-container>

  <!-- Guide arrow overlay — летящая стрелка с пунктирным следом -->
  <Teleport to="body">
    <div
      v-if="guideArrowVisible"
      class="guide-arrow-overlay"
      style="position:fixed;inset:0;pointer-events:none;z-index:9999"
    >
      <!-- Пунктирный след -->
      <svg
        v-if="guideTrail.length > 1"
        style="position:absolute;inset:0;width:100%;height:100%;overflow:visible"
      >
        <polyline
          :points="guideTrail.map(p => `${p.x},${p.y}`).join(' ')"
          fill="none"
          stroke="#e53935"
          stroke-width="3"
          stroke-dasharray="7 7"
          stroke-linecap="round"
          opacity="0.85"
        />
      </svg>
      <!-- Div-стрелка (pointer-events auto для клика "скрыть") -->
      <div
        class="guide-arrow-icon"
        :class="{ 'guide-arrow-arrived': guideArrowArrived }"
        :style="{
          position: 'absolute',
          left: guideArrowPos.x + 'px',
          top: guideArrowPos.y + 'px',
          transform: `translate(-50%,-50%) rotate(${guideArrowArrived ? 0 : guideArrowAngle}deg)`,
          pointerEvents: 'auto',
          cursor: 'pointer',
        }"
        title="Скрыть"
        @click="clearGuideArrow"
      >
        <span class="mdi mdi-arrow-down-bold guide-arrow-mdi" />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, nextTick, shallowRef } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import { useContractorsStore } from '@/stores/contractors'
import { useToast, type ToastType } from '@/composables/useToast'
import { listContractItems, replaceAllContractItems } from '@/api/contractItems'
import type { ContractItem } from '@/types/contractItem'
import { useOrgConfig } from '@/composables/useOrgConfig'
import PurchaseEventFeed from '@/components/PurchaseEventFeed.vue'
import ApprovalPanel from '@/components/purchase/ApprovalPanel.vue'
import PurchaseHeader from '@/components/purchase/PurchaseHeader.vue'
import PurchaseDatesSection from '@/components/purchase/PurchaseDatesSection.vue'
import PurchaseAcceptanceSection from '@/components/purchase/PurchaseAcceptanceSection.vue'
import PurchasePaymentSection from '@/components/purchase/PurchasePaymentSection.vue'
import PurchaseFinanceSection from '@/components/purchase/PurchaseFinanceSection.vue'
import PurchaseContractParamsSection from '@/components/purchase/PurchaseContractParamsSection.vue'
import PurchaseDocumentsCard from '@/components/purchase/PurchaseDocumentsCard.vue'
import PurchasePlatformCard from '@/components/purchase/PurchasePlatformCard.vue'
import PurchaseLinkedTasksCard from '@/components/purchase/PurchaseLinkedTasksCard.vue'
import PurchaseBroadcastDialog from '@/components/purchase/PurchaseBroadcastDialog.vue'
import { usePurchaseBroadcast } from '@/composables/purchase/usePurchaseBroadcast'
import { useDeliveryAddress } from '@/composables/purchase/useDeliveryAddress'
import { useResponsiblePersons } from '@/composables/purchase/useResponsiblePersons'
import AddResponsibleDialog from '@/components/purchase/AddResponsibleDialog.vue'
import { useGuideArrow } from '@/composables/purchase/useGuideArrow'
import { usePurchaseMembers } from '@/composables/purchase/usePurchaseMembers'
import { usePurchaseTasks, TASK_STATUS_LABEL, taskStatusColor, taskPriorityColor } from '@/composables/purchase/usePurchaseTasks'
import LinkedTaskDialogs from '@/components/purchase/LinkedTaskDialogs.vue'
import { usePurchaseSplit } from '@/composables/purchase/usePurchaseSplit'
import SplitKanbanDialog from '@/components/purchase/SplitKanbanDialog.vue'
import { usePurchaseChat } from '@/composables/purchase/usePurchaseChat'
import { useFrameworkSiblings } from '@/composables/purchase/useFrameworkSiblings'
import { useFrameworkContracts } from '@/composables/purchase/useFrameworkContracts'
import FrameworkDialogs from '@/components/purchase/FrameworkDialogs.vue'
import PlaceholdersDialog from '@/components/purchase/PlaceholdersDialog.vue'
import DocErrorDialog from '@/components/purchase/DocErrorDialog.vue'
import { useManualReceipt } from '@/composables/purchase/useManualReceipt'
import ManualReceiptDialog from '@/components/purchase/ManualReceiptDialog.vue'
import { usePurchaseReceipts, POST_SAVE_ACTION_KEY } from '@/composables/purchase/usePurchaseReceipts'
import { useMonthlyPayments } from '@/composables/purchase/useMonthlyPayments'
import PurchaseReceiptsBlock from '@/components/purchase/PurchaseReceiptsBlock.vue'
import { useFabrikantPackage } from '@/composables/purchase/useFabrikantPackage'
import PurchaseConfirmDialogs from '@/components/purchase/PurchaseConfirmDialogs.vue'
import KpDialog from '@/components/purchase/KpDialog.vue'
import { useContractorLookup } from '@/composables/purchase/useContractorLookup'
import AddContractorDialog from '@/components/purchase/AddContractorDialog.vue'
import EgrulDiffDialog from '@/components/purchase/EgrulDiffDialog.vue'
import { useDocPickerDialogs } from '@/composables/purchase/useDocPickerDialogs'
import DocPickerDialogs from '@/components/purchase/DocPickerDialogs.vue'
import { usePurchaseFiles } from '@/composables/purchase/usePurchaseFiles'
import { usePurchaseNmck } from '@/composables/purchase/usePurchaseNmck'
import PurchaseFileDialogs from '@/components/purchase/PurchaseFileDialogs.vue'
import {
  usePurchasePublications, PLATFORM_LABELS, PUB_STATUS_COLOR, PUB_STATUS_LABEL,
} from '@/composables/purchase/usePurchasePublications'
import PurchasePublishDialog from '@/components/purchase/PurchasePublishDialog.vue'
import ChatEmbed from '@/components/ChatEmbed.vue'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import QrScannerDialog from '@/components/QrScannerDialog.vue'
import ValidationArrows from '@/components/ValidationArrows.vue'
import MonthlyStagesDialog from '@/components/MonthlyStagesDialog.vue'
import PaymentsBlock from '@/components/PaymentsBlock.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { useFeoTreeNodes } from '@/composables/useFeoTreeNodes'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import { numOrNull } from '@/utils/numberFormat'
import { PURCHASE_STATUS_ORDER, purchaseStatusColor, purchaseStatusLabel, purchaseSubstatusLabel } from '@/constants/purchaseStatus'

const monthlyStagesDialogShow = ref(false)
function onMonthlyStagesCreated(res: any) {
  monthlyStagesDialogShow.value = false
  const n = res?.created?.length ?? 0
  showSnack(`Создано этапов: ${n}`, 'success')
  if (form.contract_id) loadFrameworkSiblings(form.contract_id)
}
import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import { RUSSIAN_REGIONS, DELIVERY_REGIONS } from '@/constants/russian_regions'
import { RU_REGION_OKATO, resolveRegionOkato } from '@/constants/ru_region_okato'
import { useEntityChanges } from '@/composables/useEntityChanges'
import { useUndoRedo } from '@/composables/useUndoRedo'
import '@/styles/purchase-form.css'

const route = useRoute()
const router = useRouter()
// Phase 27/31: id текущего пользователя — читается один раз при инициализации формы,
// используется как в этом файле (дефолты для reimbursement/assigned_user_id/service_note_by),
// так и в composables/purchase/* (usePurchaseMembers, useResponsiblePersons/docPicker) —
// объявлено здесь (а не рядом с первым использованием), чтобы не ловить TDZ на композаблах,
// которые вызываются раньше, чем эта константа объявлялась исторически.
const currentUserId = parseInt(localStorage.getItem('user_id') || '0')

const isEdit = computed(() => !!route.params.id)
const isNew = computed(() => !isEdit.value)
const purchaseId = computed(() => Number(route.params.id) || null)
// Phase 23.5: флаг загрузки данных закупки — скрывает заголовок до получения данных с сервера
const purchaseLoaded = ref(false)
// Phase 31-04: raw purchase data from last loadPurchase (for contract_conflict)
const purchaseData = ref<any>(null)

// Phase 31-06: diff-tracking composable for purchase fields
const _purchaseUnseenFields = computed<string[]>(() => purchaseData.value?.unseen_fields ?? [])
const entityChanges = useEntityChanges('purchase', purchaseId, _purchaseUnseenFields)

// Задача владельца (сессия 2026-08-21): «в закупке видно превышение и родительская
// заявка» — GET /api/purchases/{id} отдаёт (контракт backend-агента, работающего
// параллельно в эту же сессию): feo_excess, feo_excess_hint, feo_excess_amount,
// feo_excess_category, feo_excess_state ('none'|'not_requested'|'pending'|'approved'),
// feo_excess_approved_by, feo_excess_approved_at, wish_id, wish_title. Поля опциональны
// (purchaseData — any) — пока бэкенд их не отдаёт, computed-и ниже тихо не показывают
// блок (v-if), никаких заглушек. Плашка — по образцу .feo-excess-culprit
// (SubsidiesView.vue:956-962 + CSS :11219-11224, задача 3): согласованное превышение
// раньше просто гасило индикатор (purchases.py:959-961) — теперь состояние называется
// прямо и НЕ прячет сам факт превышения.
const purchaseExcessAmount = computed((): number | null => {
  const v = purchaseData.value?.feo_excess_amount
  return v == null ? null : Number(v)
})
const purchaseExcessText = computed((): string => {
  const d = purchaseData.value
  if (!d) return ''
  const cat = d.feo_excess_category ? ` по категории «${d.feo_excess_category}»` : ''
  const amt = purchaseExcessAmount.value != null ? `: превышение ${fmtHeadPlannedMoney(Math.abs(purchaseExcessAmount.value))}` : ''
  return d.feo_excess_hint || `Превышение плана ФЭО${cat}${amt}`
})
// Три состояния согласования превышения (задача 3, владелец: «превышение могут
// согласовывать только определённые люди, это разные уровни» — не путать с
// согласованием самой заявки). Источник — feo_excess_state с бэка, тот же контур
// PlanExcessApproval, что и в SubsidiesView.
const purchaseExcessStateColor = computed((): string => {
  const st = purchaseData.value?.feo_excess_state
  if (st === 'approved') return 'grey'
  if (st === 'pending') return 'orange'
  return 'red' // not_requested (и любое иное непустое значение) — по умолчанию тревожный цвет
})
const purchaseExcessStateText = computed((): string => {
  const d = purchaseData.value
  const st = d?.feo_excess_state
  if (st === 'approved') {
    const who = d.feo_excess_approved_by || '—'
    const when = d.feo_excess_approved_at ? new Date(d.feo_excess_approved_at).toLocaleDateString('ru-RU') : ''
    return `превышение согласовано: ${who}${when ? ', ' + when : ''}`
  }
  if (st === 'pending') return 'превышение на согласовании'
  // not_requested / отсутствует состояние, но feo_excess=true — согласование ещё не запрашивалось
  return 'превышение не согласовано'
})
// Владелец (2026-08-21, дефект «отцеплённая закупка»): закупка со status='wishes'
// либо ещё ждёт одобрения (свежесозданная), либо была отцеплена обратно —
// wish.status с бэка (draft/rejected → отцеплена; submitted/approved → ждёт
// решения) различает эти два случая. См. GET /api/purchases/{id}: wish_status.
const wishWithdrawnBannerText = computed((): string => {
  const d = purchaseData.value
  if (!d) return ''
  const num = d.wish_id
  const title = d.wish_title ? ` «${d.wish_title}»` : ''
  const ws = d.wish_status
  if (ws === 'draft' || ws === 'rejected') {
    return `Возвращена в заявку №${num}${title} — не в работе, план не расходует. `
      + `Чтобы закупка вернулась в реестр и План закупок, согласуйте заявку заново.`
  }
  // submitted / approved / неизвестно — заявка ещё идёт по цепочке согласования,
  // закупка создана заранее, но гейт одобрения ещё не пройден.
  return `Ожидает одобрения заявки №${num}${title} — пока не в Плане закупок, в реестре закупок не отображается.`
})
// Tooltip state for "было: X" on highlighted fields
const fieldHistoryMenu = ref<Record<string, boolean>>({})
const fieldHistoryData = ref<Record<string, Array<{ old_value: string | null; changed_by_name: string | null; changed_at: string }>>>({})
async function openFieldHistory(field: string) {
  if (!entityChanges.isFieldUnseen(field)) return
  fieldHistoryMenu.value[field] = true
  if (!fieldHistoryData.value[field]) {
    const history = await entityChanges.getFieldHistory(field)
    fieldHistoryData.value[field] = history
  }
}
function formatHistoryDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// 12-02: FEO auto-match suggestions
const feoMatchSuggestions = ref<Array<{
  item_index: number
  purchase_item_id: number
  item_name: string
  suggested_item_id: number
  suggested_name: string
  confidence: number
}>>([])

async function applyFeoMatch(itemIndex: number, feoItemId: number) {
  const match = feoMatchSuggestions.value.find(m => m.item_index === itemIndex)
  if (!match) return
  try {
    await apiFetch(`/feo-planned-items/map?purchase_item_id=${match.purchase_item_id}&planned_item_id=${feoItemId}`, {
      method: 'POST',
    })
    feoMatchSuggestions.value = feoMatchSuggestions.value.filter(m => m.item_index !== itemIndex)
    showSnack('Позиция привязана к плану ФЭО')
  } catch (e: any) {
    // Этап 3 (владелец, 2026-09-02): POST /feo-planned-items/map теперь может
    // отклонить привязку 409-кой PLANNED_ITEM_CATEGORY_MISMATCH с понятным
    // detail.message (см. app/services/plan_autoassign.py) — распаковываем его,
    // а не глотаем generic-текстом (правило проекта, не общий снэкбар).
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка привязки', 'error')
  }
}

// Phase 26: Автосохранение — refs declared early, watch+activation moved BELOW form reactive (~line 3033) to avoid TDZ
const autosaveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const autosaveError = ref<string | null>(null)
let serverAutosaveTimer: any = null
let autosaveBaseline = ''

// Phase 31-07: Undo/Redo — shallowRef wraps reactive form so composable can mutate fields via .value[field]
// Wiring happens here (after form reactive is declared at line ~3724) — composable is safe to use from any point below.
// Note: formRef.value IS the same reactive object as form — mutations flow through Vue reactivity normally.
let _undoRedo: ReturnType<typeof useUndoRedo> | null = null
// pendingUndoBlur tracks the value of a field at focusin so we can push on focusout
let _pendingUndoBlur: { field: string; before: unknown } | null = null

// Role-based visibility
const userRole = localStorage.getItem('user_role') || 'employee'
const isEmployee = computed(() => userRole === 'employee')
const isManager = computed(() => userRole === 'manager')
const isAdminLevel = computed(() => ['superadmin', 'org_admin', 'admin'].includes(userRole))
const isSuperadmin = computed(() => userRole === 'superadmin')
// Владелец (2026-09-02): «раньше суперадмин мог двигать закупки по статусам
// самостоятельно, куда делось это поле» — то же правило, что isSaas в WishesView.vue.
const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRole))
const isManagerLevel = computed(() => ['superadmin', 'org_admin', 'admin', 'manager'].includes(userRole))
const canPublish = computed(() =>
  isAdminLevel.value ||
  authStore.hasAction('publication.create') ||
  localStorage.getItem('can_publish') === 'true'
)

// ТЗ (Техническое задание) collapse state — persisted in localStorage
const TZ_COLLAPSE_KEY = 'purchase_tz_collapsed'
const tzCollapsed = ref(localStorage.getItem(TZ_COLLAPSE_KEY) === '1' ? true : false)
function toggleTz() {
  tzCollapsed.value = !tzCollapsed.value
  try { localStorage.setItem(TZ_COLLAPSE_KEY, tzCollapsed.value ? '1' : '0') } catch {}
}

// Блок «Остатки по категориям ФЭО» — свёрнут по умолчанию
const FEO_REMAINS_COLLAPSE_KEY = 'purchase_feo_remains_collapsed'
const feoRemainsCollapsed = ref(localStorage.getItem(FEO_REMAINS_COLLAPSE_KEY) !== '0')
function toggleFeoRemains() {
  feoRemainsCollapsed.value = !feoRemainsCollapsed.value
  try { localStorage.setItem(FEO_REMAINS_COLLAPSE_KEY, feoRemainsCollapsed.value ? '1' : '0') } catch {}
}

// НМЦД mode/итоги — вынесено в composables/purchase/usePurchaseNmck.ts, вызов
// ниже по файлу (после form/items/contractWordGen/isFramework, от которых зависит).

// U-2: Alert о мульти-чеках для авансового
const ADVANCE_ALERT_KEY = 'advance_multi_receipt_alert_closed'
const advanceInfoAlertClosed = ref(localStorage.getItem(ADVANCE_ALERT_KEY) === '1')
function closeAdvanceInfoAlert() {
  advanceInfoAlertClosed.value = true
  localStorage.setItem(ADVANCE_ALERT_KEY, '1')
}

// U-3: НДС режим toggle
function onVatModeChange(newMode: string) {
  if (newMode === 'per_item') {
    // При переключении на per_item — сбрасываем vat_rate у всех items на null (без НДС)
    items.value = items.value.map((it: any) => ({ ...it, vat_rate: null }))
  } else if (newMode === 'uniform') {
    // При переключении на uniform — убираем per-item ставки (они игнорируются при сохранении)
    items.value = items.value.map((it: any) => ({ ...it, vat_rate: null }))
  }
}

// --- formMode: drives simplified views for service notes / advance reports ---
const formMode = computed(() => (route.meta?.formMode as string) || 'default')

// При создании И редактировании авансового — блок чеков показывается первым (выше основной формы)
const showReceiptsOnTop = computed(() => formMode.value === 'advance_report')

const formModeHidden = computed((): Set<string> => {
  if (formMode.value === 'service_note_delivery')
    return new Set(['contractor', 'financial_indicators', 'contract_type',
                    'contract', 'contract_params', 'acceptance', 'payment',
                    'platform_publication', 'commercial_requests'])
  if (formMode.value === 'advance_report')
    return new Set(['contractor', 'contract_type', 'contract', 'contract_params',
                    'platform_publication', 'commercial_requests'])
  // Авансовая закупка (редактирование существующей через /orders/:id/edit)
  if ((form as any).purchase_method === 'advance')
    return new Set(['contract_type'])
  return new Set()
})

const { isSectionHidden: isOrgHidden, loadConfig: loadOrgConfig } = useOrgConfig()

function isSectionVisible(key: string): boolean {
  return !formModeHidden.value.has(key) && !isOrgHidden(key)
}

// Phase 26-ggg: показывать registry_number (РЕЕ-2026-00806) вместо
// purchase_number (582) в заголовке когда оба есть. Fallback на #purchase_number
// для legacy/draft записей без registry_number.
const purchaseTitleLabel = computed(() => {
  return (form as any).registry_number
    || `#${form.purchase_number || route.params.id}`
})

const pageTitle = computed(() => {
  if (formMode.value === 'service_note_delivery')
    return isEdit.value ? `Служебная записка ${purchaseTitleLabel.value}` : 'Новая служебная записка на выдачу'
  if (formMode.value === 'advance_report')
    return isEdit.value ? `Авансовый отчёт ${purchaseTitleLabel.value}` : 'Новый авансовый отчёт'
  return isEdit.value ? `Закупка ${purchaseTitleLabel.value}` : 'Новая закупка'
})

const backRoute = computed(() => {
  if (formMode.value === 'service_note_delivery') return '/service-notes'
  if (formMode.value === 'advance_report') return '/advance-reports'
  return '/orders'
})

const STATUS_ORDER = PURCHASE_STATUS_ORDER
// Единый источник подписи/цвета статуса закупки: frontend/src/constants/purchaseStatus.ts
// (Правило №6; раньше здесь был отдельный STATUS_LABEL_BASE со своими текстами —
// сведён к единому словарю, framework-переопределение 'contracted' оставлено).
const STATUS_LABEL = computed<Record<string, string>>(() => ({
  ...Object.fromEntries(PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusLabel(s)])),
  contracted: isFramework.value ? 'Заключён заказ' : purchaseStatusLabel('contracted'),
}))
const STATUS_COLOR: Record<string, string> = Object.fromEntries(
  PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusColor(s)])
)
const SUBSTATUS_OPTIONS = ['tz_forming', 'kp_collecting', 'on_platform', 'contractor_negotiations', 'contract_signing']
  .map(value => ({ value, title: purchaseSubstatusLabel(value) }))
interface FeoCategory { id: number; name: string; parent_id: number | null; level: number; subsidy_id: number; budget?: number | null }
interface Contractor { id: number; name: string; inn?: string }
interface Subsidy { id: number; name: string; year: number; budget: number; org_id?: number | null; org_inn?: string | null }
interface Product {
  id: number; name: string; price?: number; product_type?: string; description?: string; description_44fz?: string
  photo_url?: string; photo_link?: string; category?: string; has_photo?: boolean
  price_updated_at?: string | null; price_source?: string | null; price_source_ref?: string | null
  price_freshness?: import('@/composables/usePriceFreshness').PriceFreshness | null
}

// Phase 17.1-08: prefer bytea endpoint when DB has a cached copy.
function productPhotoSrc(p: Pick<Product, 'id' | 'has_photo' | 'photo_url' | 'photo_link'> | null | undefined): string | undefined {
  if (!p) return undefined
  if (p.has_photo) return `/api/products/${p.id}/photo`
  return p.photo_url || p.photo_link || undefined
}
interface FrameworkContract { id: number; number: string; date?: string; contract_type: string; contractor_id?: number; contractor_name?: string; contractor_inn?: string; subject?: string; max_amount?: number; remaining?: number; remaining_ordered?: number; remaining_delivered?: number; remaining_paid?: number; total_ordered?: number; status?: string; purchase_method?: string; end_date?: string }
interface OrderItem {
  product_id: number | null
  item_name: string
  item_type: string
  quantity: number | null
  unit: string
  unit_price: number | null
  total_price: number | null
  final_unit_price: number | null
  final_total: number | null
  match_confirmed?: boolean
  // UI-only: not sent to backend
  _selectedProduct?: Product | null
  _photo_url?: string
  // Стабильный id строки, проставляется PurchaseItemsEditor (см. EditorItem._uid) —
  // используется guideArrowTo('item:'+uid) чтобы стрелка вела к КОНКРЕТНОЙ позиции,
  // а не к блоку позиций целиком (владелец, 2026-09-04: «я не понимаю, что надо сделать»).
  _uid?: string | number
  _description?: string
  _description_44fz?: string
  // Владелец, 2026-08-29: штамп даты/источника актуализации цены — см. usePriceFreshness.ts.
  _price_meta?: {
    price_updated_at?: string | null
    price_source?: string | null
    price_source_ref?: string | null
    price_freshness?: import('@/composables/usePriceFreshness').PriceFreshness | null
  } | null
}
// UploadedFile, FILE_TYPE_LABELS(_BASE)/FILE_TYPE_OPTIONS/fileTypeColor — вынесены в
// composables/purchase/usePurchaseFiles.ts (см. вызов usePurchaseFiles() ниже по файлу).
const FABRIKANT_PKG_DOCS = [
  { ft: 'fabrikant_instruction',      label: 'Инструкция' },
  { ft: 'fabrikant_application_form', label: 'Форма заявки' },
  { ft: 'fabrikant_documentation',    label: 'Документация' },
  { ft: 'fabrikant_contract_project', label: 'Проект договора' },
  { ft: 'fabrikant_tech_spec',        label: 'ТЗ' },
] as const

const form = reactive({
  purchase_method: '',
  competitive_form: '',
  purchase_basis: 'service_note' as string,
  item_type: 'товар' as string,
  subsidy_id: null as number | null,
  contractor_id: null as number | null,
  registry_number: '',
  advance_report_number: '',
  feo_category_id: null as number | null,
  subject: '',
  contract_price: null as number | null,
  economy: null as number | null,
  price_increase: null as number | null,
  contract_number: '',
  contract_date: '',
  agreement_number: '' as string,   // Phase 26-K: № доп. соглашения
  agreement_date: '' as string,     // Phase 26-K: Дата доп. соглашения
  order_date: '' as string,         // Phase 26-K: Дата заказа
  contract_end_date: '' as string,
  commitment_quarter: null as number | null,
  planned_payment_month: '' as string,
  delivery_date: '',
  delivery_address: '',
  procurement_planned_date: '',
  execution_term: '',
  execution_term_changed: '',
  acceptance_doc_name: '',
  acceptance_doc_number: '',
  acceptance_doc_date: '',
  acceptance_doc_amount: null as number | null,
  acceptance_docs: [] as { name: string; number: string; date: string; amount: number | null; file_id?: number | null }[],
  payment_doc_number: '',
  payment_doc_date: '',
  payment_amount: null as number | null,
  payment_federal: null as number | null,
  status: 'wishes',
  substatus: null as string | null,
  is_monthly_payment: false as boolean,
  monthly_payment_count: null as number | null,
  monthly_payment_amount: null as number | null,
  purchase_number: null as number | null,
  purchase_contract_type: 'single' as string,
  contract_id: null as number | null,
  framework_seq: null as number | null,
  responsible_person: '' as string,
  // Поля для генерации договора
  vat_applicable: true as boolean,
  vat_rate: 22 as number | null,
  vat_exemption_article: '' as string,
  third_party_involved: false as boolean,
  service_period_type: 'date' as string,
  service_start_date: '' as string,
  service_end_date: '' as string,
  // Phase 19: template-specific fields
  submission_deadline: '' as string,              // ISO datetime-local (YYYY-MM-DDTHH:mm)
  delivery_location: '' as string,
  delivery_location_kind: '' as string,        // '' | 'delivery' | 'service' (ручной тогл лейбла)
  region: '' as string,                          // Регион проведения мероприятия (Phase 25)
  service_term_mode: '' as string,                // '' | 'range' | 'duration' | 'deadline'
  service_term_days: null as number | null,       // mode='duration'
  service_term_type: 'calendar' as string,        // 'calendar' | 'working' (mode='duration')
  service_deadline_date: '' as string,            // mode='deadline'
  description_mode: 'exact' as string,
  event_id: null as number | null,
  approval_status: null as string | null,
  approval_mode: null as string | null,
  country_origin: '' as string,
  treasury_code: '' as string,
  has_pretension: false as boolean,
  payment_basis_type: 'contract' as string,
  subsidy_allocations: [] as Array<{subsidy_id: number, amount: number | null}>,
  // Phase 25: monthly stages fields
  is_likely_needed: true as boolean,
  is_prepayment: false as boolean,
  prepayment_date: '' as string,
  stage_label: '' as string,
  // Авансовый отчёт: кому возмещать
  reimbursement_user_id: null as number | null,
  // Phase 28 B4: ответственный исполнитель (user FK)
  assigned_user_id: null as number | null,
  // SN-UX: адресат служебной записки
  service_note_to_user_id: null as number | null,
  // SN-UX: автор СЗ + дата СЗ (auto-fill при создании, редактируемы)
  service_note_by: null as number | null,
  service_note_at: null as string | null,
  // SN-UX: текст обоснования служебной записки
  service_note_text: '' as string,
  // Phase 26-U-3: режим НДС
  vat_mode: 'uniform' as string,
  // Phase 28: форма договора (определяет шаблон при скачивании)
  contract_form: null as string | null,
  // Методичка, приклеиваемая к договору (large / small / none) — отдельно от формы
  methodology: null as string | null,
  // Phase 28: contract-specific поля (условия конкретного договора)
  acceptance_term_days: null as number | null,
  penalty_rate: null as number | null,
  contractor_ogrnip_date: null as string | null,
  repair_request_number: null as string | null,
  commission_member_1_name: null as string | null,
  commission_member_2_name: null as string | null,
  commission_member_3_name: null as string | null,
  advance_amount: null as number | null,
  warranty_period_days: null as number | null,
  is_retroactive: false as boolean,
  // Phase 28 T8: доставка и этапы (управляют ветвлениями в шаблонах договоров)
  delivery_by_supplier: true as boolean,
  has_stages: false as boolean,
  // Phase 28 T8: документы закупочной комиссии
  procurement_protocol_number: null as string | null,
  procurement_order_number: null as string | null,
  // Phase 29: связь с ТС
  vehicle_id: null as number | null,
  // ЭТП: ссылка на конкурсную процедуру
  etp_url: null as string | null,
  // Структурированный адрес доставки (Фабрикант: место поставки)
  delivery_region: '' as string,
  delivery_city: '' as string,
  delivery_street: '' as string,
  delivery_house: '' as string,
  delivery_building: '' as string,
  delivery_postcode: '' as string,
  // B-PIF1/F-PIF1: per-item FEO (UI-only, not persisted)
  feo_per_item: false as boolean,
})

// Шаг 5 «ТЗ не дороже и не больше плана» (владелец, 2026-08-07, план
// zany-fluttering-mountain.md): плановые позиции субсидии — тот же источник и
// composable, что WishesView.vue уже использует (useFeoPlannedResiduals) —
// нужны PurchaseItemsEditor'у, чтобы planForItem/planExcessFor могли найти
// плановую строку позиции (по feo_planned_item_id либо по feo_category_id) и
// подсветить превышение ДО отправки (см. её planExcessFor/planForItem).
// Раньше эта страница вообще не подгружала плановые позиции — подсказка/
// подсветка были показывать нечем.
// ⚠️ excludeWishId здесь НЕ передаём: он исключает ВСЕ закупки одной заявки, а у
// заявки их может быть несколько (_distribute_wish_to_purchases) — остаток завысился бы.
const {
  plannedResiduals: purchasePlannedResiduals,
  plannedLoading: purchasePlannedLoading,
  reloadPlanned: reloadPurchasePlanned,
} = useFeoPlannedResiduals({
  subsidyId: computed(() => form.subsidy_id),
  // Своя закупка не занимает свой же план — иначе двойное вычитание и ложное
  // «не хватает»; при создании purchaseId=null, исключать нечего.
  excludePurchaseId: computed(() => purchaseId.value),
})

// Phase 29: Vehicle selector — ключевые слова для автопоказа селекта ТС
const VEHICLE_KEYWORDS = [
  'ремонт тс', 'ремонт автомобил', 'заправк', 'техобслуж', 'тех. обслуж',
  'страхован', 'запчаст', 'шиномонтаж', 'диагностик', 'мойка', 'эвакуатор',
  'осаго', 'каско', 'технический осмотр',
]
const showVehicleSelect = computed(() => {
  const s = (form.subject || '').toLowerCase()
  const keywordMatch = VEHICLE_KEYWORDS.some(kw => s.includes(kw))
  return keywordMatch || !!form.vehicle_id
})
const vehicleOptions = ref<Array<{ id: number; label: string }>>([])
const vehiclesLoading = ref(false)
let vehicleSearchDebounce: ReturnType<typeof setTimeout> | null = null
async function loadVehicles(q: string = '') {
  vehiclesLoading.value = true
  try {
    const r = await apiFetch(`/vehicles?q=${encodeURIComponent(q)}&limit=30`)
    const items = r?.items ?? r ?? []
    vehicleOptions.value = items.map((v: any) => ({
      id: v.id,
      label: `${v.plate ?? ''} — ${v.brand ?? ''} ${v.model ?? ''}`.trim(),
    }))
  } catch (e: any) {
    console.error('loadVehicles error', e)
  } finally {
    vehiclesLoading.value = false
  }
}
function onVehicleSearch(q: string) {
  if (vehicleSearchDebounce) clearTimeout(vehicleSearchDebounce)
  vehicleSearchDebounce = setTimeout(() => loadVehicles(q), 300)
}
watch(showVehicleSelect, (v) => {
  if (v && vehicleOptions.value.length === 0) loadVehicles()
})

// Phase 26: Автосохранение — функции и watcher'ы (form объявлен выше, безопасно)
function serializeFormForAutosave() {
  const f: any = form
  return JSON.stringify({
    subject: f.subject,
    description: f.description,
    contractor_id: f.contractor_id,
    feo_category_id: f.feo_category_id,
    purchase_method: f.purchase_method,
    competitive_form: f.competitive_form,
    purchase_contract_type: f.purchase_contract_type,
    contract_number: f.contract_number,
    contract_date: f.contract_date,
    // contract_price/vat_rate/payment_amount/service_term_days/acceptance_term_days/
    // penalty_rate/advance_amount/warranty_period_days — v-model.number; при очистке
    // Vue кладёт '' (не null), PurchaseUpdate ждёт Optional[Decimal]/Optional[int] →
    // автосохранение валило 422 прямо на blur. numOrNull — единый хелпер (2026-09-04):
    // '' → null, 0 сохраняется как число во всех полях без исключения.
    contract_price: numOrNull(f.contract_price),
    nmck: numOrNull(f.nmck),
    planned_total_price: numOrNull(f.planned_total_price),
    delivery_date: f.delivery_date,
    delivery_location: f.delivery_location,
    delivery_location_kind: f.delivery_location_kind,
    submission_deadline: f.submission_deadline,
    service_term_mode: f.service_term_mode,
    service_start_date: f.service_start_date,
    service_end_date: f.service_end_date,
    service_term_days: numOrNull(f.service_term_days),
    service_term_type: f.service_term_type,
    service_deadline_date: f.service_deadline_date,
    third_party_involved: f.third_party_involved,
    vat_applicable: f.vat_applicable,
    vat_rate: numOrNull(f.vat_rate),
    vat_mode: f.vat_mode,
    vat_exemption_article: f.vat_exemption_article,
    acceptance_doc_name: f.acceptance_doc_name,
    acceptance_doc_date: f.acceptance_doc_date,
    acceptance_doc_number: f.acceptance_doc_number,
    acceptance_doc_amount: f.acceptance_doc_amount,
    payment_doc_number: f.payment_doc_number,
    payment_doc_date: f.payment_doc_date,
    payment_amount: numOrNull(f.payment_amount),
    country_origin: f.country_origin,
    purchase_basis: f.purchase_basis,
    responsible_person: f.responsible_person,
    initiator_id: f.initiator_id,
    subject_kind: f.subject_kind,
    delivery_address: f.delivery_address,
    delivery_region: f.delivery_region || null,
    delivery_city: f.delivery_city || null,
    delivery_street: f.delivery_street || null,
    delivery_house: f.delivery_house || null,
    delivery_building: f.delivery_building || null,
    delivery_postcode: f.delivery_postcode || null,
    execution_term: f.execution_term,
    contract_end_date: f.contract_end_date,
    event_id: f.event_id,
    // Phase 25: monthly stages fields
    is_likely_needed: f.is_likely_needed,
    is_prepayment: f.is_prepayment,
    prepayment_date: f.prepayment_date || null,
    stage_label: f.stage_label || null,
    // Phase 28 B4: ответственный исполнитель — не шлём null, только валидное id
    ...(f.assigned_user_id ? { assigned_user_id: f.assigned_user_id } : {}),
    // Phase 28: форма договора
    contract_form: f.contract_form || null,
    // Методичка, приклеиваемая к договору — отдельно от формы
    methodology: f.methodology || null,
    // Phase 28: contract-specific поля
    acceptance_term_days: numOrNull(f.acceptance_term_days),
    penalty_rate: numOrNull(f.penalty_rate),
    contractor_ogrnip_date: f.contractor_ogrnip_date || null,
    repair_request_number: f.repair_request_number || null,
    commission_member_1_name: f.commission_member_1_name || null,
    commission_member_2_name: f.commission_member_2_name || null,
    commission_member_3_name: f.commission_member_3_name || null,
    advance_amount: numOrNull(f.advance_amount),
    warranty_period_days: numOrNull(f.warranty_period_days),
    is_retroactive: f.is_retroactive ?? false,
    // Phase 28 T8: доставка и этапы
    delivery_by_supplier: f.delivery_by_supplier ?? true,
    has_stages: f.has_stages ?? false,
    // Phase 28 T8: документы закупочной комиссии
    procurement_protocol_number: f.procurement_protocol_number || null,
    procurement_order_number: f.procurement_order_number || null,
    // ЭТП
    etp_url: f.etp_url || null,
  })
}

// Владелец (2026-09-02), прод-баг: суперадмин поменял категорию ФЭО в шапке
// закупки, но плановая позиция товара (feo_planned_item_id) осталась от
// старой категории — лист согласования печатал путь ФЭО от плановой позиции,
// показывая ветку, противоречащую шапке. Бэкенд теперь сам сбрасывает такие
// привязки при смене категории (см. _reset_incompatible_item_feo_links) и
// сообщает, сколько штук сброшено — здесь заметно предупреждаем пользователя
// и перезагружаем позиции с сервера, чтобы локальный UI не «воскресил»
// сброшенную привязку следующим же автосохранением (items.feo_planned_item_id
// в форме иначе остался бы старым и снова уехал бы на сервер как есть).
async function handleFeoLinksReset(count: number | undefined | null) {
  if (!count) return
  showSnack(
    `Категория ФЭО изменена: ${count} ${count === 1 ? 'позиция отвязана' : 'позиций отвязано'} от плановых позиций старой категории. Выберите плановую позицию заново для каждой отмеченной позиции.`,
    'warning',
    { actionText: 'Показать позиции', onAction: () => guideArrowTo('items') },
  )
  guideArrowTo('items')
  if (isEdit.value) await loadPurchase()
}

// Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
// app.services.feo_plan.assert_no_unapproved_excess больше не бросает 409 за
// перекос ОТДЕЛЬНОЙ категории ФЭО (план узла > его финансирования), а
// возвращает список предупреждений — бэкенд отдаёт его ключом excess_warnings
// в ответе POST/PUT /api/purchases и PATCH .../items/{id} (тот же паттерн, что
// excess_warnings у заявок в WishesView.vue). Пусто/undefined — превышения нет,
// уведомление не показываем (тихая деградация).
interface PurchaseExcessWarning { message: string; feo_category_id?: number; feo_category_name?: string }
function showExcessWarnings(warnings: PurchaseExcessWarning[] | null | undefined) {
  if (!warnings || !warnings.length) return
  showSnack(warnings.map(w => w.message).join(' '), 'warning')
}

async function performAutosave() {
  if (!isEdit.value || !purchaseId.value) return
  const current = serializeFormForAutosave()
  if (current === autosaveBaseline) return
  autosaveState.value = 'saving'
  try {
    const body = JSON.parse(current)
    const resp = await apiFetch<any>(`/purchases/${purchaseId.value}`, { method: 'PATCH', body })
    autosaveBaseline = current
    autosaveState.value = 'saved'
    setTimeout(() => {
      if (autosaveState.value === 'saved') autosaveState.value = 'idle'
    }, 2000)
    if (resp?.feo_links_reset) await handleFeoLinksReset(resp.feo_links_reset)
  } catch (e: any) {
    autosaveState.value = 'error'
    autosaveError.value = e?.message || 'Не удалось сохранить'
  }
}

watch(form, () => {
  if (!isEdit.value || !purchaseId.value) return
  if (serverAutosaveTimer) clearTimeout(serverAutosaveTimer)
  serverAutosaveTimer = setTimeout(performAutosave, 1500)
}, { deep: true })

watch(purchaseLoaded, (v) => {
  if (v) {
    setTimeout(() => { autosaveBaseline = serializeFormForAutosave() }, 100)
  }
})

onBeforeRouteLeave((_to, _from, next) => {
  if (autosaveState.value === 'saving' || autosaveState.value === 'error') {
    if (confirm('Есть несохранённые изменения. Уйти со страницы?')) next()
    else next(false)
  } else {
    next()
  }
})

// Доработка 5 мая: помимо debounce 1500ms нужен немедленный flush при blur поля.
// Если пользователь переключился на другое поле — сохраняем не дожидаясь таймера.
function flushAutosaveOnBlur() {
  if (!isEdit.value || !purchaseId.value) return
  if (serverAutosaveTimer) {
    clearTimeout(serverAutosaveTimer)
    serverAutosaveTimer = null
  }
  // Запускаем немедленно (микро-задержка чтобы Vue успел обновить reactive)
  setTimeout(performAutosave, 50)
}
// Глобальный capture-blur на форме (один раз на mount).
// onUnmounted на верхнем уровне setup — нельзя вкладывать в onMounted (Vue требование).
const _focusoutHandler = (e: FocusEvent) => {
  const t = e.target as HTMLElement | null
  if (!t) return
  const tag = t.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') {
    flushAutosaveOnBlur()
  }
}
onMounted(() => document.addEventListener('focusout', _focusoutHandler, true))
onUnmounted(() => {
  document.removeEventListener('focusout', _focusoutHandler, true)
  clearGuideArrow()
})
onMounted(() => { if (!authStore.loaded) authStore.loadPermissions() })

// Phase 31-07: Undo/Redo init — form is reactive, wrap in shallowRef so composable can mutate via .value[field]
const _formRef = shallowRef(form as Record<string, any>)
_undoRedo = useUndoRedo(_formRef, {
  onAfterUndoRedo: async () => {
    // D-12: clear pending debounce and immediately persist rolled-back state
    if (serverAutosaveTimer) { clearTimeout(serverAutosaveTimer); serverAutosaveTimer = null }
    await performAutosave()
  },
})

// Field-level blur tracking for undo push (data-field attribute on inputs)
const _undoFocusinHandler = (e: FocusEvent) => {
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (!field) return
  _pendingUndoBlur = { field, before: (form as any)[field] }
}
const _undoFocusoutHandler = (e: FocusEvent) => {
  if (!_pendingUndoBlur) return
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (field && field === _pendingUndoBlur.field) {
    const after = (form as any)[field]
    _undoRedo?.push(field, _pendingUndoBlur.before, after)
  }
  _pendingUndoBlur = null
}
onMounted(() => {
  document.addEventListener('focusin', _undoFocusinHandler, true)
  document.addEventListener('focusout', _undoFocusoutHandler, true)
})
onUnmounted(() => {
  document.removeEventListener('focusin', _undoFocusinHandler, true)
  document.removeEventListener('focusout', _undoFocusoutHandler, true)
})

function activeDescription(item: OrderItem): string | undefined {
  if (form.description_mode === '44fz') return item._description_44fz || item._description
  return item._description
}

interface EventItem { id: number; subsidy_id: number; name: string; is_active: boolean }

const items = ref<OrderItem[]>([])

// Phase 27.1 D-04: contract_items side-by-side
const contractItemsState = ref<ContractItem[]>([])
// Phase 27.1.2: expand-row для любой существующей закупки независимо от статуса (planned/wishes тоже).
// Для новой (несохранённой) закупки контракт-стадия неприменима — contract_items нельзя POST'ить без purchase_id.
const canShowContractColumns = computed(() => isEdit.value)

const subsidies = ref<Subsidy[]>([])
// Название субсидии для «ствола» дерева ФЭО (FeoTreeSelect rootLabel) — то же,
// что показывается в v-select «Субсидия» через item-title="name".
const selectedSubsidyName = computed((): string | null =>
  subsidies.value.find(s => s.id === form.subsidy_id)?.name ?? null
)
const contractors = ref<Contractor[]>([])
const acceptanceDocs = ref<{ name: string; number: string; date: string; amount: number | null; file_id?: number | null }[]>([])
function addAcceptanceDoc() {
  acceptanceDocs.value.push({ name: '', number: '', date: '', amount: null })
}
async function downloadAcceptanceFile(fileId: number) {
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fileId}/view`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Не удалось скачать файл', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
function ensurePlaceholderDoc() {
  if (!acceptanceDocs.value || acceptanceDocs.value.length === 0) {
    acceptanceDocs.value = [{ name: '', number: '', date: '', amount: null }]
  }
}

// 26-F4b: combobox с inline-add для типа документа
// Phase 26-ooo: добавлен «Чек» (fiscal receipt) — auto-add'ится из импорта чеков
// авансовых отчётов, должен быть в списке системных
const BUILTIN_ACCEPTANCE_DOC_TYPES = ['АКТ', 'УПД', 'СЧФ', 'ТТН', 'Счёт', 'Накладная', 'Платежное поручение', 'Чек']
const customDocTypes = ref<string[]>(JSON.parse(localStorage.getItem('acceptance_doc_types_custom') || '[]'))
const acceptanceDocTypes = computed(() => [
  ...BUILTIN_ACCEPTANCE_DOC_TYPES,
  ...customDocTypes.value.filter(t => !BUILTIN_ACCEPTANCE_DOC_TYPES.includes(t))
])
function onAcceptanceDocTypeAdd(val: string | null) {
  if (!val) return
  const v = String(val).trim()
  if (!v) return
  if (acceptanceDocTypes.value.includes(v)) return
  customDocTypes.value = [...customDocTypes.value, v]
  try { localStorage.setItem('acceptance_doc_types_custom', JSON.stringify(customDocTypes.value)) } catch {}
}
function deleteCustomDocType(val: string) {
  if (BUILTIN_ACCEPTANCE_DOC_TYPES.includes(val)) return  // системные нельзя удалять
  customDocTypes.value = customDocTypes.value.filter(t => t !== val)
  try { localStorage.setItem('acceptance_doc_types_custom', JSON.stringify(customDocTypes.value)) } catch {}
  // если этот тип был выбран в каком-то документе — оставляем значение (не чистим форму)
}

// 26-F2: показывать блок чеков и в обычной закупке
const showReceiptsBlock = computed(() => {
  return formMode.value === 'advance_report' || formMode.value === 'order' || (form as any).purchase_method === 'advance'
})

const addressLabel = computed(() => form.item_type === 'услуга' ? 'Адрес оказания услуг' : 'Адрес доставки')

// Phase 23.4: динамический label для delivery_location по типу позиций.
// Доработка 5 мая: ручной тогл (form.delivery_location_kind) перекрывает автодетект.
// Если пользователь выбрал явно — используем выбор; если нет — fallback на item_kind.
const deliveryLabel = computed(() => {
  const manual = form.delivery_location_kind
  if (manual === 'service') return 'Место оказания услуг'
  if (manual === 'delivery') return 'Адрес доставки'
  const its = items.value || []
  if (its.length === 0) return 'Адрес доставки / место оказания услуг'
  const kinds = new Set(its.map((it: any) => {
    const k = (it.item_kind || it._selectedProduct?.item_kind || 'товар') as string
    return k.toLowerCase()
  }))
  if (kinds.size === 1 && kinds.has('услуга')) return 'Место оказания услуг'
  return 'Адрес доставки'
})

const allEvents = ref<EventItem[]>([])
const filteredEvents = computed(() =>
  allEvents.value.filter(e => e.subsidy_id === form.subsidy_id && e.is_active)
)
const currentSubsidyOrgId = computed(() =>
  subsidies.value.find(s => s.id === form.subsidy_id)?.org_id ?? null
)

// Phase 23: Customer requisites preview (via list endpoint since no GET by ID)
const customerPreview = ref<any>(null)
watch(() => form.subsidy_id, async (sid) => {
  if (!sid) { customerPreview.value = null; return }
  try {
    const subsidy = subsidies.value.find(s => s.id === sid)
    if (!subsidy?.org_id) { customerPreview.value = null; return }
    // 27.4-03: GET одной org по id (раньше дёргали list — 403 для employee)
    customerPreview.value = await apiFetch<any>(`/organizations/${subsidy.org_id}`)
  } catch { customerPreview.value = null }
}, { immediate: true })

// Дефолт адреса доставки из организации субсидии при смене субсидии
watch(() => form.subsidy_id, async (sid) => {
  if (!sid) return
  try {
    const subsidy = subsidies.value.find(s => s.id === sid)
    if (!subsidy?.org_id) return
    const org = await apiFetch<any>(`/organizations/${subsidy.org_id}`)
    if (!form.delivery_address && org?.address) form.delivery_address = org.address
    if (!form.delivery_region && org?.region) form.delivery_region = org.region
    if (!form.delivery_city && org?.contract_city) form.delivery_city = org.contract_city
  } catch { /* silent */ }
})

// Смена субсидии меняет допустимый круг исполнителей/адресатов СЗ
watch(() => form.subsidy_id, () => { loadOrgUsers() })

// Phase 23: диалог «Доступные переменные»
const showPlaceholdersDialog = ref(false)
// Phase 23.2: диалог ошибки генерации документа
const docErrorDialog = ref(false)
const docErrorInfo = ref<any>(null)
// formatPlaceholder/placeholderGroups — вынесены в components/purchase/PlaceholdersDialog.vue
// (использовались только в этом диалоге).
const products = ref<Product[]>([])
const allFeoCategories = ref<FeoCategory[]>([])
const formRef = ref()
const saving = ref(false)
// Validation arrows: подсветка обязательных полей при провальной валидации
const saveBtnRef = ref<any>(null)
const validationArrowsActive = ref(false)
const validationArrowFrom = ref<HTMLElement | null>(null)
const validationArrowTargets = ref<HTMLElement[]>([])
let validationArrowsTimer: number | null = null
function dismissValidationArrows() {
  validationArrowsActive.value = false
  validationArrowFrom.value = null
  validationArrowTargets.value = []
  if (validationArrowsTimer) { window.clearTimeout(validationArrowsTimer); validationArrowsTimer = null }
}
function showValidationArrows() {
  // querySelector внутри формы — все ошибочные v-input
  const formEl = formRef.value?.$el as HTMLElement | undefined
  if (!formEl) return
  const errors = Array.from(formEl.querySelectorAll('.v-input.v-input--error')) as HTMLElement[]
  if (!errors.length) return
  // Кнопка-источник
  const btn = (saveBtnRef.value?.$el ?? saveBtnRef.value) as HTMLElement | null
  if (!btn) return
  // Скроллим к первому ошибочному, чтобы он был в области видимости
  errors[0].scrollIntoView({ behavior: 'smooth', block: 'center' })
  validationArrowFrom.value = btn
  validationArrowTargets.value = errors.slice(0, 8) // не больше 8 чтобы не засорять экран
  validationArrowsActive.value = true
  if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
  validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
}

// ── Конец месяца quick-fill — вынесено в composables/purchase/useEndOfMonthFill.ts,
// вызывается теперь внутри components/purchase/PurchaseDatesSection.vue (см. шаблон,
// секция #section-dates) — не используется больше нигде в этом файле.
const transitioning = ref(false)
const converting = ref(false)
// uploading — владеет composables/purchase/usePurchaseFiles.ts (вызов ниже по файлу)
const docLoading = ref<string | null>(null)

// ── Org users list for executor dropdown ──
function toShortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  if (parts.length >= 3) return `${parts[0]} ${parts[1][0]}.${parts[2][0]}.`
  if (parts.length === 2) return `${parts[0]} ${parts[1][0]}.`
  return fullName
}
interface OrgUser { id: number; full_name: string; short_name: string; position?: string | null }
const orgUsersList = ref<OrgUser[]>([])
async function loadOrgUsers() {
  try {
    // При выбранной субсидии — только сотрудники её орг(а) и люди с персональным
    // доступом к субсидии (иначе по документам не закрыться), не весь контур.
    const qs = form.subsidy_id ? `?subsidy_id=${form.subsidy_id}` : ''
    const users = await apiFetch<any[]>(`/users/${qs}`)
    orgUsersList.value = users
      .filter(u => u.full_name)
      .map(u => ({ id: u.id, full_name: u.full_name, short_name: toShortName(u.full_name), position: u.position }))
  } catch { orgUsersList.value = [] }
}

// Кому возмещать — список сотрудников из orgUsersList
const reimbursementUserOptions = computed(() => orgUsersList.value)

// ── Delivery address autocomplete — вынесено в composables/purchase/useDeliveryAddress.ts ──
const {
  deliveryAddressSuggestions,
  loadDeliveryAddressHistory, onDeliveryAddressSearch, onDeliveryAddressSelect, saveDeliveryAddressIfNew,
} = useDeliveryAddress(form, currentSubsidyOrgId, subsidies)

// ── Responsible persons suggestions (order form combobox) ──
const responsiblePersonSuggestions = ref<string[]>([])
async function loadResponsiblePersons() {
  if (!form.subsidy_id) { responsiblePersonSuggestions.value = []; return }
  try {
    responsiblePersonSuggestions.value = await apiFetch<string[]>(`/purchases/responsible-persons?subsidy_id=${form.subsidy_id}`)
  } catch { responsiblePersonSuggestions.value = [] }
}

// ── Responsible persons directory (for approval sheet dialog) — вынесено в
// composables/purchase/useResponsiblePersons.ts + components/purchase/AddResponsibleDialog.vue ──
const {
  pickerResponsibleName, addResponsibleDialog,
  newResponsibleName, newResponsiblePosition, savingResponsible,
  loadResponsiblePersonsList, responsibleOptions, saveNewResponsible,
} = useResponsiblePersons(form, orgUsersList)

// ── Диалоги перед скачиванием документов (закрывающие/согласующие) — вынесено
// в composables/purchase/useDocPickerDialogs.ts + components/purchase/DocPickerDialogs.vue.
// downloadDoc определена ниже по файлу — передаём лениво вызывающей обёрткой,
// чтобы не читать идентификатор до его объявления (TDZ). ──
const {
  acceptanceDocPickerDialog, acceptanceDocPickerSelected,
  // openAcceptanceDocPicker не деструктурируется — вызывается только изнутри
  // confirmDocDownload (тот же composable), view её напрямую не дёргает.
  confirmAcceptanceDocDownload,
  docPickerDialog, docPickerType, loadingDocApprovers, docApprovers, pickerApproverIds, pickerInitiatorId,
  actAsList, openDocPicker, confirmDocDownload,
} = useDocPickerDialogs(
  form, purchaseId, acceptanceDocs, orgUsersList, loadOrgUsers, currentUserId,
  pickerResponsibleName, loadResponsiblePersonsList,
  (docType, extraParams, loadingKey) => downloadDoc(docType, extraParams, loadingKey),
  toShortName,
)
// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// duration=0 по умолчанию: результат действия (смена статуса, сохранение,
// ошибка) не должен исчезать сам, пока пользователь не прочитал и не закрыл.
const toast = useToast()
// showSnack объявлен здесь (а не рядом с formatMoney ниже, как было исторически) —
// несколько composables/purchase/* вызываются раньше по файлу и получают showSnack
// напрямую аргументом (не через собственный useToast()), поэтому объявление обязано
// стоять до первого такого вызова, иначе — TDZ ReferenceError при монтировании.
const showSnack = (
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) => {
  toast.addToast(text, color, opts)
}
const itemsEditorRef = ref<any>(null)
const budgetInfo = ref<{ remaining: number; exceeded: boolean; over: number; limit?: number; spent?: number } | null>(null)
// Остатки бюджета по ФЭО (по правам: лист всем с view_leaf, уровни выше — view_all_levels)
const authStore = useAuthStore()
const canViewLeafBudget = computed(() => authStore.hasAction(ACTIONS.FEO_BUDGET_VIEW_LEAF!))
const canViewAllLevelsBudget = computed(() => authStore.hasAction(ACTIONS.FEO_BUDGET_VIEW_ALL_LEVELS!))
type FeoNode = { id: number; name: string; level: number; path: string; budget: number; used: number; residual: number; contracted_used: number; planned_used: number; uncontracted_remaining: number; spendable_remaining: number }
type FeoLeaf = FeoNode & { ancestors: FeoNode[] }
const feoDirections = ref<FeoNode[]>([])
const feoResiduals = ref<FeoLeaf[]>([])
const leafCatIds = computed<number[]>(() => {
  if (form.feo_per_item) {
    const s = new Set<number>()
    for (const it of items.value) {
      const cid = (it as any).feo_category_id
      if (cid) s.add(Number(cid))
    }
    return [...s]
  }
  return form.feo_category_id ? [Number(form.feo_category_id)] : []
})
const loadFeoResiduals = async () => {
  if (!form.subsidy_id || (!canViewLeafBudget.value && !canViewAllLevelsBudget.value)) {
    feoDirections.value = []
    feoResiduals.value = []
    return
  }
  try {
    const qs = new URLSearchParams({ subsidy_id: String(form.subsidy_id) })
    if (leafCatIds.value.length) qs.set('category_ids', leafCatIds.value.join(','))
    if (purchaseId.value) qs.set('exclude_purchase_id', String(purchaseId.value))
    const data = await apiFetch<{ directions: FeoNode[]; leaves: FeoLeaf[] }>(`/feo-categories/budget-residuals?${qs.toString()}`)
    feoDirections.value = data.directions || []
    feoResiduals.value = data.leaves || []
  } catch { feoDirections.value = []; feoResiduals.value = [] }
}
watch([() => form.subsidy_id, leafCatIds, canViewLeafBudget, canViewAllLevelsBudget], loadFeoResiduals, { immediate: true })

// Личная корзина по узлу ФЭО: сумма позиций текущей формы, привязанных к данному узлу
const basketForNode = (nodeId: number, leafIds?: Set<number>): number => {
  if (form.feo_per_item) {
    // per-item режим: смотрим feo_category_id каждой позиции
    const allowed = leafIds ?? new Set([nodeId])
    return items.value.reduce((s, i) => {
      const cid = (i as any).feo_category_id
      return s + (cid && allowed.has(Number(cid)) ? (i.total_price || 0) : 0)
    }, 0)
  } else {
    // одиночный режим: если выбранная категория совпадает с узлом — берём planned_total_price
    const selId = form.feo_category_id ? Number(form.feo_category_id) : null
    if (selId === nodeId) return Number((form as any).planned_total_price) || 0
    return 0
  }
}

const budgetOverrideDialog = ref(false)
const isAdmin = computed(() => ['superadmin', 'org_admin', 'admin'].includes(userRole))

// ── Approval (Согласование) — extracted to ApprovalPanel.vue ─────────────────
const approvalPanelRef = ref<InstanceType<typeof ApprovalPanel> | null>(null)

// Владелец (2026-09-03): рамочная ГОЛОВА договора (Purchase.is_framework_head,
// см. purchases.py::is_framework_head) видит блок согласования ВСЕГДА, независимо
// от статуса закупки (у свежесозданной головы Purchase.status='wishes') — автор
// должен иметь возможность добавить согласующих необходимости сразу, до того как
// approval_status вообще выставлен (до 2026-09-03 согласование строилось само при
// создании; теперь строит его человек — см. contracts.py::get_or_create_approval_purchase).
const isFrameworkHeadPurchase = computed(() => !!purchaseData.value?.is_framework_head)

const showApprovalSection = computed(() => {
  if (!isEdit.value) return false
  if (isFrameworkHeadPurchase.value) return true
  if (form.approval_status) return true
  const idx = STATUS_ORDER.indexOf(form.status)
  return idx >= STATUS_ORDER.indexOf('work_in_progress')
})

const contractorInn = ref('')
// Файлы к закупке (uploadedFiles, диалоги загрузки/типа/предпросмотра) — вынесены
// в composables/purchase/usePurchaseFiles.ts, вызов ниже по файлу (после contractWord).

// ── Publications (список публикаций, диалог настроек, поллинг статуса) —
// вынесено в composables/purchase/usePurchasePublications.ts + components/purchase/
// PurchasePublishDialog.vue. Вызов usePurchasePublications() ниже по файлу — после
// displayNmck/savedNmck (publishNmck от них зависит), иначе TDZ. ──

// ── Guide arrow (летящая стрелка с пунктирным следом) — вынесено в
// composables/purchase/useGuideArrow.ts. onBeforeNavigate закрывает диалог
// публикации при наведении на цель вне диалога — то же поведение, что раньше
// было зашито прямо в guideArrowTo. ──
const {
  guideArrowVisible, guideArrowPos, guideArrowAngle, guideArrowArrived, guideTrail,
  pointerTarget, okpd2Pointer, auctionPointerTarget,
  clearGuideArrow, guideArrowTo,
} = useGuideArrow(() => {
  publishDialog.value = false
  pendingPlatform.value = null
})
// ── end guide arrow ────────────────────────────────────────────────────────────

function revealField(target: string) {
  guideArrowTo(target)
}

// ── Linked tasks / Link existing task — вынесено в
// composables/purchase/usePurchaseTasks.ts + components/purchase/LinkedTaskDialogs.vue ──
const allUsers = ref<{ value: number; text: string }[]>([])
async function loadAllUsers() {
  if (allUsers.value.length) return
  try {
    const users = await apiFetch<any[]>('/users/')
    allUsers.value = users.map(u => ({ value: u.id, text: u.full_name || u.username }))
  } catch {}
}
const {
  linkedTasks, linkedTaskDialog, linkedTaskSaving, linkedTaskForm,
  loadLinkedTasks, openCreateLinkedTask, saveLinkedTask,
  linkTaskDialog, linkTaskSearch, linkTaskResults, linkTaskSearching,
  searchUnlinkedTasks, linkExistingTask, unlinkTask,
} = usePurchaseTasks(purchaseId, loadAllUsers)

// ── Purchase members — вынесено в composables/purchase/usePurchaseMembers.ts.
// Фича добавления/удаления участников обсуждения (menu/buttons) в текущем шаблоне
// не подключена (не было UI-триггера и до выноса — canSeePurchaseDocs единственное,
// что реально используется видом); остальной API композабла сохранён на случай,
// если UI появится, но здесь не деструктурируется, чтобы не тащить мёртвый код.
const { canSeePurchaseDocs, loadPurchaseMembers, loadPurchaseApprovals } =
  usePurchaseMembers(purchaseId, currentUserId, isEdit, isManagerLevel, authStore, allUsers, loadAllUsers)

// ── Split purchase feature — вынесено в composables/purchase/usePurchaseSplit.ts +
// components/purchase/SplitKanbanDialog.vue ──
const {
  splitKanbanDialog, splitKanbanItems, canSplitPurchase, onPurchaseSplit,
  openSplitKanban: _openSplitKanban,
} = usePurchaseSplit(router, isEdit, form, items, productPhotoSrc, showSnack)
function openSplitKanban() { return _openSplitKanban(route.params.id) }

// ── Purchase chat — вынесено в composables/purchase/usePurchaseChat.ts. Собственный
// UI этой реализации в шаблоне сейчас не подключён (заменён общим ChatEmbed.vue
// в карточке «Обсуждение»), но loadPurchaseComments/pCommentText остаются нужны:
// используются loadPurchase() и usePurchaseBroadcast — поэтому деструктурируем
// только их, а не весь дохлый API (иначе TS ловит их как unused в этом файле). ──
const { pCommentText, loadPurchaseComments } = usePurchaseChat(purchaseId, allUsers, loadAllUsers)

// ── Purchase broadcast — вынесено в composables/purchase/usePurchaseBroadcast.ts + components/purchase/PurchaseBroadcastDialog.vue ──
const {
  pBroadcastDialog, pBroadcastScope, pBroadcastScopeId, pBroadcastText,
  pBroadcastSending, pBroadcastOrgs, pBroadcastDepts,
  openPurchaseBroadcast, sendPurchaseBroadcast,
} = usePurchaseBroadcast(purchaseId, pCommentText, loadPurchaseComments)

// Framework contracts
const CONTRACT_TYPES = [
  { value: 'single', title: 'Разовый' },
  { value: 'framework_cumulative', title: 'Рамочный накопительный' },
  { value: 'framework_with_amount', title: 'Рамочный с суммой' },
]

// Phase 28: варианты формы договора — определяют какой шаблон используется при скачивании.
// Семь форм (большая/малая отчётность объединены в «Услуги» — различие теперь
// не в тексте договора, а в приклеиваемой методичке, см. methodologyOptions ниже).
const contractFormOptions = [
  { value: 'services',           title: 'Услуги' },
  { value: 'services_food',      title: 'Услуги — питание' },
  { value: 'goods_single',       title: 'Поставка — разовый договор' },
  { value: 'gph_individual',     title: 'ГПХ с физ.лицом' },
  { value: 'gph_individual_rid', title: 'ГПХ с физ.лицом, передача прав на РИД' },
  { value: 'repair_vehicle',     title: 'Договор на ремонт ТС' },
  { value: 'repair_framework',   title: 'Рамочный договор на ремонт ТС' },
]

// Phase 28: маппинг contract_form → doc_type для кнопки «Договор»
const contractDocTypeMap: Record<string, string> = {
  services:           'contract_services',
  services_food:      'contract_services_food',
  goods_single:       'contract_goods_single',
  gph_individual:     'contract_gph_individual',
  gph_individual_rid: 'contract_gph_individual_rid',
  repair_vehicle:     'contract_repair_vehicle',
  repair_framework:   'contract_repair_framework',
}

// Методичка, приклеиваемая к договору при генерации (docxcompose) — выбирается
// ОТДЕЛЬНО от формы договора, владелец запретил автовыбор. 'none' — не приклеивать.
const methodologyOptions = [
  { value: 'large', title: 'Большие' },
  { value: 'small', title: 'Малые' },
  { value: 'none',  title: 'Без методички' },
]

// Форма конкурентной процедуры релевантна только при purchase_method === 'competitive' —
// при смене способа закупки на другой сбрасываем, чтобы в базе не оставалась неактуальная форма
watch(() => form.purchase_method, (newMethod) => {
  if (newMethod !== 'competitive') form.competitive_form = ''
})

// Phase 28: авто-предложение contract_form при первом выборе item_type
watch(() => form.item_type, (newType) => {
  if (form.contract_form) return  // не перезаписываем если уже выбрано
  if (newType === 'услуга') {
    form.contract_form = 'services'
  } else if (newType === 'товар' || newType === 'mixed') {
    form.contract_form = 'goods_single'
  }
})
const isFramework = computed(() => form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')
const isFrameworkCumulative = computed(() => form.purchase_contract_type === 'framework_cumulative')
const contractWord = computed(() => isFramework.value ? 'Заказ' : 'Договор')
const contractWordLower = computed(() => isFramework.value ? 'заказ' : 'договор')
const contractWordGen = computed(() => isFramework.value ? 'заказа' : 'договора')
// ПРАВИЛО №6 (2026-09-07, группа D7): при заданном form.contract_id шапка
// договора (номер/дата/тип/контрагент) — источник Contract на бэкенде
// (см. app.services.purchase_contract_header, PUT/PATCH /api/purchases
// молча игнорируют эти поля из payload'а при contract_id — contract_fields_ignored
// в ответе). Фронт больше не даёт их редактировать здесь — правка только в
// карточке договора (реестр «Договоры»).
const contractHeaderLocked = computed(() => !!form.contract_id)
const contractHeaderLockedHint = computed(() =>
  `Берётся из договора №${form.contract_number || '—'} — изменить в карточке договора`
)

// ── Диалоги выбора/создания рамочного договора — вынесено в
// composables/purchase/useFrameworkContracts.ts + components/purchase/FrameworkDialogs.vue ──
const {
  frameworkContracts, frameworkDialog, frameworkLoading, frameworkSearch, selectedFrameworkContract,
  newFrameworkDialog, newFrameworkSaving, newFrameworkForm,
  openFrameworkDialog, selectFrameworkContract, clearFrameworkContract, saveNewFrameworkContract,
} = useFrameworkContracts(form, contractWord, contractors, showSnack)

// ── Framework sibling purchases / Счёт по РД — вынесено в
// composables/purchase/useFrameworkSiblings.ts ──
const {
  frameworkSiblings, frameworkTotals, loadFrameworkSiblings, filteredFrameworkContracts,
  selectedFrameworkInvoiceContract, frameworkContractsForInvoice,
  loadFrameworkContractsForInvoice, onFrameworkInvoiceSelect,
} = useFrameworkSiblings(form, isFramework, frameworkContracts, frameworkSearch)

// ── Со-финансирование (cofinancing subsidies) ────────────────────────────────
// Найдено при рефакторинге 2026-09: computed нигде не используется (мёртвый
// код, ни в template, ни в других composables) — оставлено без изменений
// (не в скоупе этого рефакторинга, поведение не трогаем), см. отчёт.
const cofinancingSubsidies = computed(() => {
  if (!form.subsidy_id) return []
  const primary = subsidies.value.find(s => s.id === form.subsidy_id)
  if (!primary) return []
  return subsidies.value.filter(s => s.id !== form.subsidy_id && s.org_id === primary.org_id)
})

// ── Файлы к закупке — вынесено в composables/purchase/usePurchaseFiles.ts.
// Требует contractWord (DOC_UPLOAD_SECTIONS/FILE_TYPE_LABELS используют подпись
// «Договор»/«Заказ») — вызывается здесь, после её объявления выше, иначе TDZ. ──
const {
  EDITABLE_MIME, FILE_TYPE_LABELS, FILE_TYPE_OPTIONS, fileTypeColor,
  fileInputEl, sectionFileInputEl, pendingSectionUpload,
  uploadedFiles, uploadDialog, uploadFileType, uploadDocFormat, paymentFiles,
  DOC_UPLOAD_SECTIONS, filesByType,
  fileTypeEditDialog, fileTypeEditValue, fileDocFormatEditValue, fileTypeEditTarget, savingFileType,
  // openUploadDialog не деструктурируется — как и в оригинале, ни одна кнопка её не
  // вызывает (мёртвый код ещё до рефакторинга, см. отчёт), не тащим её в view.
  openFileTypeEdit, toggleDocFormat, saveFileType,
  uploading, uploadFile, uploadFilesForType, onAcceptanceDocFilesDropped, uploadForSection, toggleFileActive, uploadSectionFile,
  downloadFile, deleteFile,
  previewDialog, previewFile, previewUrl, isPreviewable, openPreview,
  fileIcon, formatSize, formatDate,
} = usePurchaseFiles(purchaseId, showSnack, contractWord, isEdit)

const contractNumberEditEnabled = ref(false)

function onAutoFieldChange(field: string, label: string, value: any) {
  if (!isAdminLevel.value) return
  ;(form as any)[field] = value
}

function enableContractNumberEdit() {
  if (!contractNumberEditEnabled.value) {
    if (!confirm(`Вы уверены, что хотите изменить это поле? Оно генерируется автоматически.`)) return
    contractNumberEditEnabled.value = true
  }
}

async function editFrameworkSeq() {
  const current = form.framework_seq
  const input = prompt(`Изменить порядковый номер в рамочном договоре?\nТекущий: ${current ?? '—'}\n\nВведите новый номер (или оставьте пустым для автоназначения):`)
  if (input === null) return // отмена
  if (input.trim() === '') {
    if (confirm('Номер будет назначен автоматически при сохранении. Продолжить?')) {
      form.framework_seq = null
    }
    return
  }

  const num = parseInt(input, 10)
  if (isNaN(num) || num < 1) {
    showSnack('Номер должен быть целым числом больше 0', 'warning')
    return
  }

  // Phase 27.1.4: проверить дубль на сервере перед принятием нового номера
  if (form.contract_id && num !== current) {
    try {
      const check = await apiFetch<any>(
        `/purchases/?contract_id=${form.contract_id}&framework_seq=${num}`
      )
      const existing = (Array.isArray(check) ? check : check.items || [])
        .find((p: any) => p.id !== purchaseId.value)
      if (existing) {
        const confirmed = window.confirm(
          `Номер ${num} уже занят закупкой ${existing.registry_number || `#${existing.id}`}.\n\n` +
          `Если продолжить — после сохранения сервер может вернуть ошибку.\n\n` +
          `Точно установить этот номер?`
        )
        if (!confirmed) return
      }
    } catch {}
  }

  form.framework_seq = num
}

function onContractTypeChange() {
  if (!isFramework.value) {
    clearFrameworkContract()
  }
}

// ── НМЦД/итоги закупки — вынесено в composables/purchase/usePurchaseNmck.ts
// (только чистые computed/refs, зависящие от form/items). syncContractPriceIfSingle/
// calcEconomy и их watcher'ы остаются во view — они пишут в form, а form читается
// напрямую в save() (ПРАВИЛО №6, один источник истины). ──
const {
  nmckMode, nmckManualValue, contractPriceMode, savedNmck,
  totalNmck, isSinglePurchase, isContracted, displayNmck,
  nmckHint, contractPriceHint, nmckExcessPct, nmckWarningLevel,
} = usePurchaseNmck(form, items, contractWordGen, isFramework)

// Предупреждение о возможном повторе разовой закупки
const duplicateDialog = ref(false)
const duplicateMatches = ref<any[]>([])
let duplicateConfirmed = false
let duplicatePendingOverride = false

// ── Публикация на площадках — вынесено в composables/purchase/usePurchasePublications.ts +
// components/purchase/PurchasePublishDialog.vue. Вызывается здесь (после displayNmck/
// savedNmck, от которых зависит publishNmck) — раньше по файлу словил бы TDZ. ──
const {
  publications, publishDialog, publishingPlatform, pendingPlatform, roseltorgProcedureType, publishErrors,
  fabrikantDates, fabrikantOkpd2, okpd2Items, okpd2Loading, okpd2Error, okpd2ItemTitle, searchOkpd2,
  fabrikantAttachDocs, fabrikantNoNmcd, fabrikantProcedureType,
  fabrikantAuctionDateStart, fabrikantAuctionBetFrom, fabrikantAuctionBetTo,
  publishNmck, initFabrikantDates, checkPublishReady, currentSubsidyOrgInn, isPlatformPublished,
  refreshingPubId, loadPublications, refreshPubStatus, doPublish, retryPublish,
  // fabrikantErrorTarget/pollPublication не деструктурируются — используются только
  // внутри самого composable (doPublish/openFabrikantRetry/поллинг), view их не вызывает.
  openFabrikantRetry,
} = usePurchasePublications(
  purchaseId, showSnack, form, items, subsidies, isEdit, performAutosave, autosaveState,
  resolveRegionOkato, customerPreview, displayNmck, savedNmck, guideArrowTo,
)
// Кнопка «Опубликовать» в components/purchase/PurchasePlatformCard.vue — тот же
// инлайн, что раньше стоял прямо в @click, вынесен в функцию, т.к. дочерний
// компонент не может писать в чужие refs напрямую (передаём функцию пропом).
function openPublishDialog() {
  publishErrors.value = checkPublishReady()
  publishDialog.value = true
  pendingPlatform.value = null
  fabrikantNoNmcd.value = !(publishNmck.value > 0)
}

// Auto-sync contract_price when mode is auto
function syncContractPriceIfSingle() {
  if (contractPriceMode.value === 'manual') return
  if (isSinglePurchase.value && displayNmck.value > 0) {
    form.contract_price = displayNmck.value
    calcEconomy()
  }
}

// Владелец (2026-08-21): подпись «Цена договора» обещает автозаполнение суммой
// позиций, но раньше syncContractPriceIfSingle() вызывался только из watcher'ов
// nmckMode/nmckManualValue/contractPriceMode — НЕ при изменении самих позиций
// (totalNmck) и не при первой загрузке закупки. Итог: у закупки, приехавшей из
// заявки с уже готовыми позициями, поле оставалось пустым. displayNmck уже
// учитывает и авто-сумму позиций, и ручной оверрайд НМЦД, и замороженное
// (isContracted) значение — тот же источник, которым пользуется сама функция
// выше, поэтому один watcher покрывает все случаи «состав/цены позиций
// изменились».
watch(displayNmck, () => { syncContractPriceIfSingle() })

function onProductCreatedFromEditor(product: Product) {
  // Mirror the existing behaviour: push into local products list so any
  // parent-side product selects stay up-to-date.
  if (product && !products.value.some(p => p.id === product.id)) {
    products.value.push(product)
  }
}

const { monthlyTotal, calcMonthlyTotal } = useMonthlyPayments(form)

const formatMoney = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
// fileIcon/formatSize/formatDate — вынесены в composables/purchase/usePurchaseFiles.ts

// FEO — дерево категорий (заменяет трёхуровневый каскад selectedFeo1/2/3; form.feo_category_id
// теперь ЕДИНСТВЕННЫЙ источник истины и хранит id любого выбранного узла, лист или папку).
const feoSaveAttempted = ref(false)
// Переключатель «не указывать последний уровень»: обязателен хоть какой-то узел,
// более глубокие уровни ФЭО можно не выбирать (закупка привяжется к промежуточной категории).
const feoSkipLast = ref(false)

// Узлы дерева ФЭО для шапки — теперь через GET /feo-categories/flat (тот же эндпоинт,
// что и построчный выбор в PurchaseItemsEditor/useFeoLeaves), а не через allFeoCategories
// (GET /feo-categories/, не отдающий has_budget/has_plan). Раньше шапка считала «есть план»
// только по числовым planned_quantity/planned_amount самой категории и не видела план,
// заданный плановыми позициями или ручной суммой (plan_source='manual_sum') — категория
// пропадала из дерева выбора в шапке, хотя оставалась выбираемой построчно. См.
// composables/useFeoTreeNodes.ts (переиспользует filterFundedNodes + цепочку-фолбэк,
// перенесённую отсюда без изменения поведения).
const { feoTreeNodes, rawNodes: feoTreeRawNodes } = useFeoTreeNodes(
  computed(() => form.subsidy_id),
  computed(() => form.feo_category_id),
)
const feoNodeById = computed(() => new Map(feoTreeNodes.value.map(n => [n.id, n])))
const feoSelectedIsLeaf = computed(() => (form.feo_category_id != null ? (feoNodeById.value.get(form.feo_category_id)?.is_leaf ?? false) : false))
const feoSelectedLevel = computed(() => (form.feo_category_id != null ? (feoNodeById.value.get(form.feo_category_id)?.level ?? null) : null))

// Категория есть в form.feo_category_id, но полностью отсутствует в справочнике (удалена) —
// раньше это определялось как «resolveFeeLevels не нашёл цепочку», теперь — прямой поиск.
const feoCategoryMissing = computed(() =>
  form.feo_category_id != null && !!form.subsidy_id && allFeoCategories.value.length > 0
  && !allFeoCategories.value.some(c => c.id === form.feo_category_id)
)

// «Остатки» по узлу для подписи под деревом — переиспользуем уже загруженные feoResiduals
// (см. loadFeoResiduals выше), а не отдельный composable: они и так грузятся под текущий
// выбор ФЭО и содержат budget/residual, только под другими именами полей.
const feoTreeLeavesForNote = computed(() =>
  feoResiduals.value.map(r => ({
    id: r.id,
    name: r.name,
    parent_id: feoNodeById.value.get(r.id)?.parent_id ?? null,
    level: r.level,
    budget: r.budget,
    used_amount: r.used,
    residual: r.residual,
    path: r.path,
  }))
)

// Ошибка выбора ФЭО: нужно выбрать самый глубокий доступный уровень
const feoValidationError = computed((): string | null => {
  // SN-UX: в режиме служебной записки ФЭО необязательны
  if (formMode.value === 'service_note_delivery') return null
  // Авансовый отчёт: ФЭО необязательна — чеки грузятся сразу, категория назначается позже
  if (formMode.value === 'advance_report') return null
  if (!form.subsidy_id || !feoTreeNodes.value.length) return null
  if (!form.feo_category_id) return 'Выберите категорию ФЭО'
  if (feoSkipLast.value) return null
  // В режиме per-item конечный уровень выбирается per-row — не требуем общий
  if (!form.feo_per_item && !feoSelectedIsLeaf.value) return 'Выберите конечную категорию ФЭО (самый глубокий уровень)'
  return null
})

// Владелец (сессия 2026-08-21): шапочная плановая позиция «на всю закупку»
// (headFeoPlannedItemId) и read-only перечень для её просмотра/удаления
// (headPlannedListItems/deleteHeadPlannedItem) убраны целиком — «каждому товару надо
// присваивать свою плановую» (то же требование, что и в WishesView.vue). Привязка
// feo_planned_item_id теперь ВСЕГДА построчная (см. allow-per-item-plan ниже и
// feo_planned_item_id в validItems/doSave), просмотр/удаление доступны через
// построчный FeoPlannedItemsSelect (тот же список filteredItems, что показывал
// убранный шапочный перечень). fmtHeadPlannedMoney используется и ниже (excess badge).
function fmtHeadPlannedMoney(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

// Псевдо-«Не определена»: для авансового отчёта (см. allow-unallocated на FeoTreeSelect).
// parentId — id узла, под которым кликнули строку «❓ Не определена» (null = корень).
const onFeoPickUnallocated = async (parentId: number | null) => {
  const sid = form.subsidy_id
  if (!sid) return
  try {
    const cat = await apiFetch<{ id: number; name: string; parent_id?: number | null }>(
      '/feo-categories/unallocated',
      { method: 'POST', body: JSON.stringify({ subsidy_id: sid, parent_id: parentId }) }
    )
    if (!allFeoCategories.value.find(c => c.id === cat.id)) {
      const parent = parentId != null ? allFeoCategories.value.find(c => c.id === parentId) : undefined
      allFeoCategories.value = [
        ...allFeoCategories.value,
        { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? parentId ?? null, level: parent ? parent.level + 1 : 1, subsidy_id: sid },
      ]
    }
    // Тот же псевдо-узел — в rawNodes composable'а useFeoTreeNodes (источник дерева шапки,
    // :nodes="feoTreeNodes"): без этого дерево не знает о только что созданной категории
    // «Не определена» и не может отрисовать её как выбранную (поле окажется пустым, см.
    // useFeoTreeNodes.ts).
    if (!feoTreeRawNodes.value.find(n => n.id === cat.id)) {
      const parentRawNode = parentId != null ? feoTreeRawNodes.value.find(n => n.id === parentId) : undefined
      const newRawNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? parentId ?? null, level: parentRawNode ? parentRawNode.level + 1 : 1, is_leaf: true } as any
      const updatedRaw = [...feoTreeRawNodes.value, newRawNode]
      if (parentId != null) {
        const pi = updatedRaw.findIndex(n => n.id === parentId)
        if (pi !== -1) updatedRaw[pi] = { ...updatedRaw[pi], is_leaf: false }
      }
      feoTreeRawNodes.value = updatedRaw
    }
    form.feo_category_id = cat.id
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось получить категорию «Не определена»', 'error')
  }
}
const feoPerItemDisableDialog = ref(false)
const feoPerItemDisableCount = ref(0)
const onFeoPerItemChange = (val: boolean | null) => {
  // С деревом form.feo_category_id уже актуален в любой момент (нет отдельных
  // selectedFeo2/3 для «схлопывания») — при включении режима просто ничего не делаем.
  if (val) return
  // Ручное выключение — предупреждаем, если есть позиции с уже выбранной категорией
  const count = items.value.filter(i => i.feo_category_id != null).length
  if (count > 0) {
    feoPerItemDisableCount.value = count
    feoPerItemDisableDialog.value = true
  }
  // Заполнение пустых позиций дефолтом выполняется внутри PurchaseItemsEditor
  // (watch на feoPerItem + defaultFeoCategoryId). При выключении ничего не делаем.
}
const cancelFeoPerItemDisable = () => {
  form.feo_per_item = true
  feoPerItemDisableDialog.value = false
}
// Подтверждение «Отключить» — очищаем per-item ФЭО СРАЗУ, а не только при сохранении
// (см. аналогичный фикс в WishesView.vue): иначе до следующего save() позиции
// продолжают нести свои feo_category_id/feo_planned_item_id.
const confirmFeoPerItemDisable = () => {
  for (const it of items.value as any[]) {
    it.feo_category_id = null
    it.feo_planned_item_id = null
  }
  feoPerItemDisableDialog.value = false
}

// SN-UX: при выборе адресата СЗ — автоматически ставим его как ответственного, если пуст
const onServiceNoteToUserChange = (userId: number | null) => {
  if (userId && !form.assigned_user_id) {
    form.assigned_user_id = userId
  }
}

// Цепочка id от корня до узла по allFeoCategories (используется только для itemsFeoLevel2 ниже).
function feoAncestorChain(id: number | null | undefined): number[] {
  const path: number[] = []
  let cur = id != null ? allFeoCategories.value.find(c => c.id === id) : undefined
  while (cur) {
    path.unshift(cur.id)
    cur = cur.parent_id ? allFeoCategories.value.find(c => c.id === cur!.parent_id) : undefined
  }
  return path
}

// FCAT-F1: в per-item режиме шапка ФЭО обычно пуста — скоуп для пер-позиционного пикера
// категорий берём от категории первой позиции с заполненным feo_category_id.
// form.feo_category_id НЕ трогаем, чтобы не дописать в БД шапочную категорию,
// которую пользователь не выбирал.
const itemsFeoLevel2 = computed<number | null>(() => {
  const headChain = feoAncestorChain(form.feo_category_id)
  if (headChain[1]) return headChain[1]
  if (!form.feo_per_item) return null
  const withCat = items.value.find(i => (i as any).feo_category_id != null)
  if (!withCat) return null
  return feoAncestorChain((withCat as any).feo_category_id)[1] ?? null
})

const onSubsidyChange = async () => {
  form.feo_category_id = null
  form.event_id = null
  feoSaveAttempted.value = false
  feoSkipLast.value = false
  fetchRemaining()
  loadResponsiblePersons()
  // Pre-fill delivery address from org if empty & load address history
  loadDeliveryAddressHistory()
  if ((!form.delivery_address || !form.delivery_region) && form.subsidy_id) {
    try {
      const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
      if (subsidy?.org_id) {
        // GET /organizations/{id} — merge-паттерн: address организации с фолбэком
        // на адрес привязанного контрагента (доступен любому authenticated)
        const org = await apiFetch<any>(`/organizations/${subsidy.org_id}`)
        // не перетираем введённое, если пользователь успел заполнить пока грузили
        if (!form.delivery_address && org?.address) form.delivery_address = org.address
        if (!form.delivery_region && org?.region) form.delivery_region = org.region
        if (!form.delivery_city && org?.contract_city) form.delivery_city = org.contract_city
      }
    } catch { /* silent */ }
  }
}

const calcEconomy = () => {
  // Экономия = НМЦД (зафиксированная) - Цена договора
  const nmck = displayNmck.value
  form.economy = (nmck > 0 && form.contract_price != null)
    ? Math.round((nmck - form.contract_price) * 100) / 100
    : null
}

// Phase 31-05: server-side remaining (D-17); replaces client-side calcBudget.
// exclude_purchase_id excludes current purchase from spent on UPDATE (D-16 correct remaining).
const fetchRemaining = async () => {
  if (!form.subsidy_id) { budgetInfo.value = null; return }
  try {
    const params = new URLSearchParams()
    if (purchaseId.value) params.set('exclude_purchase_id', String(purchaseId.value))
    const data = await apiFetch<{ limit: number; spent: number; remaining: number; planned_amount: number; discrepancy: number }>(
      `/subsidies/${form.subsidy_id}/budget-check?${params.toString()}`
    )
    const remaining = data.remaining - totalNmck.value
    budgetInfo.value = {
      remaining,
      exceeded: remaining < 0,
      over: remaining < 0 ? -remaining : 0,
      limit: data.limit,
      spent: data.spent,
    }
  } catch {}
}

watch(totalNmck, () => { calcEconomy(); fetchRemaining() })
watch(nmckMode, () => { syncContractPriceIfSingle(); calcEconomy(); fetchRemaining() })
watch(nmckManualValue, () => { syncContractPriceIfSingle(); calcEconomy() })
watch(contractPriceMode, () => { syncContractPriceIfSingle() })

const hasProducts = computed(() => items.value.some(i => i.item_name?.trim()))

// Date validation rules
const contractDateRules = computed(() => [
  (v: string) => !v || !form.execution_term || v <= form.execution_term
    || `Дата ${contractWordGen.value} не может быть позже срока исполнения`,
])
const executionTermRules = computed(() => [
  (v: string) => !v || !form.execution_term_changed || v <= form.execution_term_changed
    || 'Срок исполнения не может быть позже изменённого срока',
])

const nextStatusTarget = computed(() => {
  if (!isEdit.value || !form.status) return null
  // Рамочные закупки: из work_in_progress сразу в delivered (contracted недоступен)
  if (form.status === 'work_in_progress' && isFramework.value) return 'delivered'
  const idx = STATUS_ORDER.indexOf(form.status)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
})

const needsContract = computed(() => form.status === 'work_in_progress')
const needsAcceptance = computed(() => form.status === 'contracted')
const needsPayment = computed(() => form.status === 'delivered')

const contractorsStore = useContractorsStore()

// НДС «не облагается»: основание освобождения система определяет сама для
// двух случаев — самозанятый исполнитель и договор ГПХ с физлицом (владелец,
// 2026-09-04: «самозанятые не облагаются НДС и ГПХ, у остальных должно
// быть [указано]»). Тексты и сама логика — на бэкенде, единственный источник
// истины: backend/app/routers/documents.py::_resolve_vat_exemption_basis.
// Здесь только читаем контекст (контрагент/форма договора), чтобы решить,
// требовать ли поле «Статья НК РФ» от пользователя.
const GPH_INDIVIDUAL_CONTRACT_FORMS = ['gph_individual', 'gph_individual_rid']
const vatExemptionAutoBasis = computed<string | null>(() => {
  if (form.vat_applicable) return null
  const contractor = form.contractor_id ? contractorsStore.getById(form.contractor_id) : null
  if (contractor?.org_type === 'Самозанятый') {
    return 'исполнитель — самозанятый, ч. 9 ст. 2 Федерального закона от 27.11.2018 № 422-ФЗ'
  }
  if (form.contract_form && GPH_INDIVIDUAL_CONTRACT_FORMS.includes(form.contract_form)) {
    return 'договор ГПХ с физическим лицом, ст. 143 НК РФ'
  }
  return null
})

const loadRefs = async () => {
  // Phase 26-ZZ: контрагенты через server-search (см. onContractorSearch).
  // Локальный contractors.value наполняется по мере поиска и ad-hoc fetch'ей.
  const [subs, feos, prods, evts] = await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/'),
    apiFetch<FeoCategory[]>('/feo-categories/'),
    apiFetch<Product[]>('/products/'),
    apiFetch<EventItem[]>('/events/'),
  ])
  subsidies.value = subs
  allFeoCategories.value = feos
  products.value = prods
  allEvents.value = evts
  loadOrgUsers()
  loadInitialContractors()
}

const contractorFilter = (value: string, query: string, item?: any): boolean => {
  const q = query.toLowerCase()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}

// Жалоба владельца (2026-08-21): пустое поле «Контрагент» показывало
// английскую заглушку Vuetify "No data available" при открытии без ввода.
// Подгружаем первую страницу контрагентов заранее; серверный поиск при
// вводе (onContractorSearch) не трогаем.
const contractorsInitialLoading = ref(false)
const contractorsInitialLoaded = ref(false)
async function loadInitialContractors() {
  if (contractorsInitialLoaded.value || contractorsInitialLoading.value) return
  contractorsInitialLoading.value = true
  try {
    const list = await contractorsStore.search('', 50)
    const existing = new Set(contractors.value.map(c => c.id))
    for (const c of list) if (!existing.has(c.id)) contractors.value.push(c as Contractor)
  } finally {
    contractorsInitialLoading.value = false
    contractorsInitialLoaded.value = true
  }
}
const contractorsNoDataText = computed(() => {
  if (contractorSearchLoading.value || contractorsInitialLoading.value) return 'Загрузка…'
  if (contractors.value.length === 0) {
    return 'В справочнике пока нет контрагентов — начните вводить название или ИНН, либо добавьте нового'
  }
  return 'Ничего не найдено'
})

// ── Новый контрагент (диалог) + ЕГРЮЛ lookup — вынесено в
// composables/purchase/useContractorLookup.ts + components/purchase/AddContractorDialog.vue,
// EgrulDiffDialog.vue ──
const {
  addContractorDialog, addContractorForm, addContractorSaving, addContractorFile, addContractorImporting,
  egrulDiffDialog, egrulDiffItems, egrulDiffPending,
  openAddContractor, saveNewContractor, importContractorFromFile, lookupContractorInn, applyEgrulDiff, onAddContractorInnChange,
} = useContractorLookup(form, contractors, contractorInn, contractorsStore, showSnack)

const contractorSearchLoading = computed(() => contractorsStore.searching)
let _contractorSearchTimeout: any = null
function onContractorSearch(query: string) {
  clearTimeout(_contractorSearchTimeout)
  if (!query || query.length < 2) return
  // Phase 26-ZZ: server-search через store с отменой in-flight + cache
  _contractorSearchTimeout = setTimeout(async () => {
    const list = await contractorsStore.search(query, 50)
    // Merge with existing local array (хранит selected + per-item lookups)
    const existing = new Set(contractors.value.map(c => c.id))
    for (const c of list) {
      if (!existing.has(c.id)) contractors.value.push(c as Contractor)
    }
  }, 300)
}

// Phase 23.5: предупреждение при удалении контрагента через X
function onContractorClear() {
  if (isEdit.value) {
    showSnack('Контрагент удалён. Не забудьте нажать «Сохранить» чтобы изменение применилось.', 'warning')
  }
}

const contractorFrameworkContracts = ref<FrameworkContract[]>([])
const showContractTypeChoice = ref(false)

const onContractorSelect = async (id: number | null) => {
  const c = contractors.value.find(c => c.id === id)
  contractorInn.value = c?.inn || ''
  contractorFrameworkContracts.value = []
  showContractTypeChoice.value = false
  if (!id) return
  // Check if contractor has framework contracts
  try {
    const allContracts = await apiFetch<FrameworkContract[]>('/contracts/')
    const cFramework = allContracts.filter(ct =>
      ct.contractor_id === id && (ct.contract_type === 'framework_cumulative' || ct.contract_type === 'framework_with_amount')
    )
    if (cFramework.length > 0) {
      contractorFrameworkContracts.value = cFramework
      showContractTypeChoice.value = true
    }
  } catch {}
}

function selectContractType(type: 'single' | 'framework', contract?: FrameworkContract) {
  showContractTypeChoice.value = false
  if (type === 'single') {
    form.purchase_contract_type = 'single'
    form.contract_id = null
    form.payment_basis_type = 'contract'
  } else if (contract) {
    form.purchase_contract_type = contract.contract_type as string || 'framework_cumulative'
    form.contract_id = contract.id
    // phase26-j-3: autofill denormalized fields from selected contract
    if (contract.number) form.contract_number = contract.number
    if (contract.date) form.contract_date = contract.date
    if (contract.contract_type) form.purchase_contract_type = contract.contract_type
    if (contract.max_amount) form.contract_price = contract.max_amount
    if (contract.subject) form.subject = contract.subject
    if ((contract as any).purchase_method) form.purchase_method = (contract as any).purchase_method
    if ((contract as any).item_type) form.item_type = (contract as any).item_type
    // Switch to "Счёт по рамочному договору" tab
    form.payment_basis_type = 'framework_invoice'
    selectedFrameworkContract.value = contract
  }
}

const onInnInput = (val: string) => {
  const c = contractors.value.find(c => c.inn === val.trim())
  if (c) form.contractor_id = c.id
}

const loadPurchase = async () => {
  const data = await apiFetch<any>(`/purchases/${purchaseId.value}`)
  // Phase 31-04: store raw response for contract_conflict detection
  purchaseData.value = data

  // Phase 27.1.4: prefetch contractor СИНХРОННО до Object.assign
  // чтобы избежать race с editFrameworkSeq save (форма шлёт PUT до завершения fetch)
  if (data.contractor_id) {
    let c = contractors.value.find(c => c.id === data.contractor_id)
    if (!c) {
      try {
        const fetched = await apiFetch<Contractor>(`/contractors/${data.contractor_id}`)
        contractors.value.push(fetched)
      } catch {}
    }
  }

  Object.assign(form, {
    purchase_method: data.purchase_method || '',
    competitive_form: data.competitive_form || '',
    purchase_basis: data.purchase_basis || '',
    item_type: data.item_type || 'товар',
    subsidy_id: data.subsidy_id ?? null,
    contractor_id: data.contractor_id ?? null, // Phase 27.1.4: set directly (prefetched above)
    registry_number: data.registry_number || '',
    feo_category_id: data.feo_category_id ?? null,
    subject: data.subject || '',
    contract_price: data.contract_price ? Number(data.contract_price) : null,
    economy: data.economy ? Number(data.economy) : null,
    price_increase: data.price_increase ? Number(data.price_increase) : null,
    contract_number: data.contract_number || '',
    contract_date: data.contract_date || '',
    agreement_number: data.agreement_number || '',
    agreement_date: data.agreement_date || '',
    order_date: data.order_date || '',
    contract_end_date: data.contract_end_date || '',
    commitment_quarter: data.commitment_quarter ?? null,
    planned_payment_month: data.planned_payment_month || '',
    delivery_date: data.delivery_date || '',
    delivery_address: data.delivery_address || '',
    procurement_planned_date: data.procurement_planned_date || '',
    execution_term: data.execution_term || '',
    execution_term_changed: data.execution_term_changed || '',
    acceptance_doc_name: data.acceptance_doc_name || '',
    acceptance_doc_number: data.acceptance_doc_number || '',
    acceptance_doc_date: data.acceptance_doc_date || '',
    acceptance_doc_amount: data.acceptance_doc_amount ? Number(data.acceptance_doc_amount) : null,
    acceptance_docs: data.acceptance_docs || [],
    payment_doc_number: data.payment_doc_number || '',
    payment_doc_date: data.payment_doc_date || '',
    payment_amount: data.payment_amount ? Number(data.payment_amount) : null,
    payment_federal: data.payment_federal ? Number(data.payment_federal) : null,
    status: data.status || 'wishes',
    substatus: data.substatus || null,
    is_monthly_payment: !!data.is_monthly_payment,
    monthly_payment_count: data.monthly_payment_count ?? null,
    monthly_payment_amount: data.monthly_payment_amount ? Number(data.monthly_payment_amount) : null,
    purchase_number: data.purchase_number ?? null,
    purchase_contract_type: data.purchase_method === 'advance' ? (data.purchase_contract_type || null) : (data.purchase_contract_type || 'single'),
    contract_id: data.contract_id ?? null,
    framework_seq: data.framework_seq ?? null,
    responsible_person: data.responsible_person || '',
    vat_applicable: !!data.vat_applicable,
    vat_rate: data.vat_rate ?? null,
    vat_exemption_article: data.vat_exemption_article || '',
    third_party_involved: !!data.third_party_involved,
    service_period_type: data.service_period_type || 'date',
    service_start_date: data.service_start_date || '',
    service_end_date: data.service_end_date || '',
    // Phase 19: template-specific fields
    submission_deadline: data.submission_deadline
      ? String(data.submission_deadline).slice(0, 16)  // ISO → datetime-local input value
      : '',
    delivery_location: data.delivery_location || '',
    region: data.region || '',
    service_term_mode: data.service_term_mode || '',
    service_term_days: data.service_term_days ?? null,
    service_term_type: data.service_term_type || 'calendar',
    service_deadline_date: data.service_deadline_date || '',
    description_mode: data.description_mode || 'exact',
    // Phase 25: monthly stages fields
    is_likely_needed: data.is_likely_needed !== false,  // default true
    is_prepayment: !!data.is_prepayment,
    prepayment_date: data.prepayment_date || '',
    stage_label: data.stage_label || '',
    event_id: data.event_id ?? null,
    reimbursement_user_id: data.reimbursement_user_id ?? null,
    approval_status: data.approval_status ?? null,
    approval_mode: data.approval_mode ?? null,
    country_origin: data.country_origin || '',
    treasury_code: data.treasury_code || '',
    has_pretension: !!data.has_pretension,
    payment_basis_type: data.payment_basis_type || 'contract',
    subsidy_allocations: (data.subsidy_allocations || []).map((a: any) => ({
      subsidy_id: a.subsidy_id,
      amount: a.amount != null ? Number(a.amount) : null,
    })),
    // Phase 28 B4: ответственный исполнитель
    assigned_user_id: data.assigned_user_id ?? null,
    // SN-UX: адресат служебной записки
    service_note_to_user_id: data.service_note_to_user_id ?? null,
    // SN-UX: автор СЗ + дата СЗ
    service_note_by: data.service_note_by ?? null,
    service_note_at: data.service_note_at ? String(data.service_note_at).slice(0, 10) : null,
    service_note_text: data.service_note_text ?? '',
    // Phase 26-U-3: НДС режим
    vat_mode: data.vat_mode || 'uniform',
    // Phase 28: форма договора
    contract_form: data.contract_form || null,
    // Методичка, приклеиваемая к договору — отдельно от формы
    methodology: data.methodology || null,
    // Phase 28: contract-specific поля
    acceptance_term_days: data.acceptance_term_days ?? null,
    penalty_rate: data.penalty_rate != null ? Number(data.penalty_rate) : null,
    contractor_ogrnip_date: data.contractor_ogrnip_date || null,
    repair_request_number: data.repair_request_number || null,
    commission_member_1_name: data.commission_member_1_name || null,
    commission_member_2_name: data.commission_member_2_name || null,
    commission_member_3_name: data.commission_member_3_name || null,
    advance_amount: data.advance_amount != null ? Number(data.advance_amount) : null,
    warranty_period_days: data.warranty_period_days ?? null,
    is_retroactive: data.is_retroactive ?? false,
    // Phase 28 T8: доставка и этапы
    delivery_by_supplier: data.delivery_by_supplier ?? true,
    has_stages: data.has_stages ?? false,
    // Phase 28 T8: документы закупочной комиссии
    procurement_protocol_number: data.procurement_protocol_number ?? null,
    procurement_order_number: data.procurement_order_number ?? null,
    // Phase 29: связь с ТС
    vehicle_id: data.vehicle_id ?? null,
    // ЭТП
    etp_url: data.etp_url ?? null,
    // Структурированный адрес доставки (Фабрикант: место поставки)
    delivery_region: data.delivery_region || '',
    delivery_city: data.delivery_city || '',
    delivery_street: data.delivery_street || '',
    delivery_house: data.delivery_house || '',
    delivery_building: data.delivery_building || '',
    delivery_postcode: data.delivery_postcode || '',
  })

  // Save frozen НМЦД from DB
  savedNmck.value = data.total_nmck ? Number(data.total_nmck) : null

  loadResponsiblePersons()

  // Restore selected framework contract
  if (data.contract_id && (form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')) {
    try {
      // First try filtered by subsidy (fast), then fallback to unfiltered (safe)
      const params = new URLSearchParams()
      if (data.subsidy_id) params.set('subsidy_id', String(data.subsidy_id))
      let contracts = await apiFetch<FrameworkContract[]>(`/contracts/?${params}`)
      let found = contracts.find(c => c.id === data.contract_id) ?? null
      if (!found) {
        // contract may belong to a different subsidy — fetch all and locate by id
        const all = await apiFetch<FrameworkContract[]>('/contracts/')
        found = all.find(c => c.id === data.contract_id) ?? null
      }
      selectedFrameworkContract.value = found
    } catch {}
    await loadFrameworkSiblings(data.contract_id)
  }

  // Restore selected framework invoice contract
  if (data.contract_id && data.payment_basis_type === 'framework_invoice') {
    await loadFrameworkContractsForInvoice()
    selectedFrameworkInvoiceContract.value = frameworkContracts.value.find(c => c.id === data.contract_id) ?? null
  }

  // Load items
  if (data.items && data.items.length) {
    items.value = data.items.map((i: any) => {
      const prod = i.product_id ? products.value.find(p => p.id === i.product_id) : null
      return {
        id: i.id,  // Phase 27.1.13: КРИТИЧЕСКИЙ FIX — без id orphan resolution не работает (rematch dropdown показывал "№1281 связь не найдена" даже когда PI существовал)
        product_id: i.product_id ?? null,
        item_name: i.item_name || '',
        item_type: i.item_type || 'товар',
        quantity: i.quantity ? Number(i.quantity) : null,
        unit: i.unit || '',
        unit_price: i.unit_price ? Number(i.unit_price) : null,
        total_price: i.total_price ? Number(i.total_price) : null,
        final_unit_price: i.final_unit_price ? Number(i.final_unit_price) : null,
        final_total: i.final_total ? Number(i.final_total) : null,
        country_origin: i.country_origin || '',
        match_confirmed: i.match_confirmed !== false,
        // Phase 26-V: contractor fields from receipt autofill
        contractor_id: i.contractor_id ?? null,
        contractor_inn: i.contractor_inn || null,
        contractor_name: i.contractor_name || null,
        vat_rate: i.vat_rate ?? null,  // Phase 27.1.15: НДС % per-item из чека ФФД 1.2 (Phase 26-AAA парсил → не подтягивался во фронт)
        feo_planned_item_id: i.feo_planned_item_id ?? null,  // F-PIF1: per-item FEO (legacy)
        feo_category_id: i.feo_category_id ?? null,  // FCAT-F1: per-item leaf FeoCategory
        _selectedProduct: prod ?? (i.item_name || null),
        _photo_url: productPhotoSrc(prod),
        _description: i.product_description || prod?.description || undefined,
        _description_44fz: i.product_description_44fz || prod?.description_44fz || undefined,
        // Владелец, 2026-08-29: штамп актуализации цены — из привязанного товара
        // каталога (позиция закупки сама по себе цену не «актуализирует»).
        _price_meta: prod ? {
          price_updated_at: prod.price_updated_at ?? null,
          price_source: prod.price_source ?? null,
          price_source_ref: prod.price_source_ref ?? null,
          price_freshness: prod.price_freshness ?? null,
        } : null,
      }
    })
    // Режим читаем из БД; фолбэк — только для записей, созданных до появления колонки.
    form.feo_per_item = data.feo_per_item ?? data.items.some((i: any) => i.feo_category_id != null)
    // Владелец (сессия 2026-08-21): «каждому товару надо присваивать свою плановую» —
    // шапочного значения feo_planned_item_id больше нет ни в одном режиме, построчные
    // значения читаются как есть выше (feo_planned_item_id: i.feo_planned_item_id).
  } else if (data.item_name) {
    // Migrate old single-item purchase
    items.value = [{
      product_id: null,
      item_name: data.item_name,
      item_type: data.item_type || 'товар',
      quantity: data.planned_quantity ? Number(data.planned_quantity) : null,
      unit: data.unit || '',
      unit_price: data.planned_unit_price ? Number(data.planned_unit_price) : null,
      total_price: data.planned_total_price ? Number(data.planned_total_price) : null,
      final_unit_price: data.final_unit_price ? Number(data.final_unit_price) : null,
      final_total: data.final_total_amount ? Number(data.final_total_amount) : null,
    }]
  }

  // Phase 27.1 D-04: load contract_items for side-by-side
  if (purchaseId.value) {
    try {
      contractItemsState.value = await listContractItems(purchaseId.value)
    } catch {
      contractItemsState.value = []
    }
  }

  // FEO: form.feo_category_id уже выставлен выше (Object.assign) — дереву больше ничего
  // резолвить не нужно, путь строится напрямую из allFeoCategories по этому id.
  if (data.feo_category_id) {
    // Закупка сохранена на промежуточном уровне (у категории есть дети, глубже не выбрано) —
    // включаем «Не указывать последний уровень», чтобы редактирование не требовало довыбора.
    const hasChildren = allFeoCategories.value.some(c => c.parent_id === data.feo_category_id)
    if (hasChildren && !form.feo_per_item) feoSkipLast.value = true
  }

  // Load acceptance docs
  acceptanceDocs.value = (data.acceptance_docs || []).map((d: any) => ({
    name: d.name || d.type || '', number: d.number || '', date: d.date || '', amount: d.amount ? Number(d.amount) : null,
    file_id: d.file_id || null,
  }))
  // Migrate legacy single fields if no acceptance_docs
  if (!acceptanceDocs.value.length && data.acceptance_doc_name) {
    acceptanceDocs.value = [{ name: data.acceptance_doc_name, number: data.acceptance_doc_number || '', date: data.acceptance_doc_date || '', amount: data.acceptance_doc_amount ? Number(data.acceptance_doc_amount) : null }]
  }
  // 26-F4a: гарантировать хотя бы одну пустую строку в режиме редактирования
  ensurePlaceholderDoc()

  // Load uploaded files
  uploadedFiles.value = data.files || []

  // Auto-fill INN — contractor was prefetched above (Phase 27.1.4), just set INN
  if (data.contractor_id) {
    const c = contractors.value.find(c => c.id === data.contractor_id)
    contractorInn.value = c?.inn || ''
    // form.contractor_id already set in Object.assign above (race-safe)
  }

  // Phase 26-EE: hydrate per-item contractors. Если у позиций stoit contractor_id,
  // которого нет в локальном contractors массиве — frontend autocomplete показывает пустоту.
  // Это критический баг для employee, у которых /contractors отдаёт фильтрованный список.
  try {
    const itemContractorIds = Array.from(new Set(
      (data.items || [])
        .map((it: any) => it.contractor_id)
        .filter((cid: any) => cid && !contractors.value.some(c => c.id === cid))
    )) as number[]
    if (itemContractorIds.length) {
      const fetched = await Promise.all(
        itemContractorIds.map(cid =>
          apiFetch<Contractor>(`/contractors/${cid}`).catch(() => null as any)
        )
      )
      for (const f of fetched) {
        if (f && f.id && !contractors.value.some(c => c.id === f.id)) {
          contractors.value.push(f)
        }
      }
    }
  } catch {}

  // Phase 26-AA: дозагрузить ответственного и возмещателя, если их нет в orgUsersList.
  // Сценарий: employee не имеет прав видеть пользователя, который назначен другим
  // (например, Цыганов id=8 у employee Лягина). Без этого v-autocomplete с item-value=id
  // показывает raw ID цифру вместо ФИО.
  {
    const _toHydrate: number[] = []
    if (data.assigned_user_id && !orgUsersList.value.some((u: any) => u.id === data.assigned_user_id)) {
      _toHydrate.push(data.assigned_user_id)
    }
    if (data.reimbursement_user_id && !orgUsersList.value.some((u: any) => u.id === data.reimbursement_user_id)) {
      if (!_toHydrate.includes(data.reimbursement_user_id)) _toHydrate.push(data.reimbursement_user_id)
    }
    await Promise.all(_toHydrate.map(async (uid) => {
      try {
        // suppressErrorDialog: бек прячет суперадминов за 404 «Пользователь не найден» (D-09),
        // ниже есть fallback-заглушка — глобальный диалог ошибки тут только пугает.
        const u = await apiFetch<any>(`/users/${uid}`, { suppressErrorDialog: true })
        if (u && u.full_name) {
          orgUsersList.value.push({
            id: u.id,
            full_name: u.full_name,
            short_name: toShortName(u.full_name),
            position: u.position || null,
          })
        }
      } catch {
        // Endpoint /users/{id} закрыт — fallback: заглушка с минимальными данными
        orgUsersList.value.push({
          id: uid,
          full_name: `Сотрудник #${uid}`,
          short_name: `#${uid}`,
          position: null,
        })
      }
    }))
  }

  fetchRemaining()

  // Restore manual НМЦД if saved value differs from items total
  if (savedNmck.value != null && !isContracted.value) {
    const itemsTotal = items.value.reduce((s, i) => s + (i.total_price || 0), 0)
    if (Math.abs(savedNmck.value - itemsTotal) > 0.01) {
      nmckMode.value = 'manual'
      nmckManualValue.value = savedNmck.value
    }
  }

  // Владелец (2026-08-21): «Цена договора = сумма позиций, заполняется
  // автоматически» — но раньше синхронизация запускалась только по
  // watcher'ам режимов, не при самой загрузке закупки (см. syncContractPriceIfSingle
  // выше). Тот же приём, что и для НМЦД строкой выше: сохранённая цена,
  // отличающаяся от текущей суммы позиций, считается осознанно введённой
  // вручную (contractPriceMode='manual', не перебиваем) — иначе (пусто или
  // совпадает) остаёмся в «Авто» и подтягиваем/держим её равной сумме.
  if (isSinglePurchase.value && !isContracted.value) {
    const itemsTotal = items.value.reduce((s, i) => s + (i.total_price || 0), 0)
    if (form.contract_price != null && Math.abs(Number(form.contract_price) - itemsTotal) > 0.01) {
      contractPriceMode.value = 'manual'
    } else {
      syncContractPriceIfSingle()
    }
  }

  // Phase 23.5: данные загружены — теперь заголовок показывает актуальный номер
  purchaseLoaded.value = true
  // Phase 31-06: sync unseen_fields from freshly loaded purchase
  entityChanges.syncFromEntity(data.unseen_fields ?? [])
  // Phase 31-07: clear undo stack when a new purchase record is loaded
  _undoRedo?.clear()
}

// ---------------------------------------------------------------------------
// Владелец (2026-09-02, закупка РЕЕ-2026-00904): «это неверное утверждение, я
// выбрал категорию ФЭО шапки верно, а у "Нашивки на спину" осталась протухшая
// своя категория — надо это менять» — кнопка чинит ровно то, что баннер
// описывает при reason='header'/'both': режим «разные категории для каждого
// товара» выключен (form.feo_per_item === false), но у части позиций всё ещё
// висит собственная feo_category_id. См. backend app.routers.purchases.
// _item_feo_mismatch (эффективная категория при выключенном тумблере теперь
// ВСЕГДА категория шапки) — здесь просто убираем источник расхождения.
// ---------------------------------------------------------------------------
const fixingFeoMismatch = ref(false)
const feoMismatchFixableItems = computed(() => {
  if (form.feo_per_item) return []
  return (purchaseData.value?.feo_mismatch_items || []).filter(
    (mi: any) => mi.reason === 'header' || mi.reason === 'both',
  )
})

async function fixFeoMismatchOwnCategories() {
  const targets = feoMismatchFixableItems.value
  if (!targets.length || !purchaseId.value) return
  if (!confirm(
    `Убрать свою категорию ФЭО у ${targets.length} ` +
    `${targets.length === 1 ? 'позиции' : 'позиций'}? Они станут следовать за категорией шапки закупки.`,
  )) return
  fixingFeoMismatch.value = true
  let fixed = 0
  try {
    for (const mi of targets) {
      try {
        await apiFetch(`/purchases/${purchaseId.value}/items/${mi.item_id}`, {
          method: 'PATCH',
          body: { clear_feo_category: true },
          suppressErrorDialog: true,
        })
        fixed += 1
      } catch (e: any) {
        showSnack(
          `«${mi.item_name || mi.item_id}»: ${e?.detail || e?.payload?.message || e?.message || 'не удалось убрать категорию'}`,
          'error',
        )
      }
    }
    if (fixed) {
      await loadPurchase()
      showSnack(`Категория убрана у позиций: ${fixed} из ${targets.length}`)
    }
  } finally {
    fixingFeoMismatch.value = false
  }
}

// ---------------------------------------------------------------------------
// Phase 21: multi-receipts on advance report — состояние и логика (QR/JSON,
// удаление, пересчёт) вынесены в composables/purchase/usePurchaseReceipts.ts,
// разметка (3 места использования) — в components/purchase/PurchaseReceiptsBlock.vue.
// Ручной ввод чека остаётся в composables/purchase/useManualReceipt.ts (не дублируется).
// ---------------------------------------------------------------------------
const { manualReceiptDialog, openManualReceiptDialog, saveManualReceipt } =
  useManualReceipt(purchaseId, showSnack, () => loadReceipts())

const {
  receipts, sourceLabel, loadReceipts,
  qrScanShow, onScanQrClick, onJsonBtnClick, onManualBtnClick,
  recomputeLoading, recomputeFromReceipts,
  consumePostSaveAction, onQrDetected, onJsonReceiptUpload, deleteReceipt,
} = usePurchaseReceipts(
  purchaseId, formMode, isEdit, form, showSnack, guideArrowTo,
  () => save(), () => loadPurchase(), openManualReceiptDialog,
  () => console.log(`[advance] items refetched: ${items.value.length}, acceptance_docs: ${acceptanceDocs.value.length}`),
)

// ---------------------------------------------------------------------------
// Autosave draft for new purchases
// ---------------------------------------------------------------------------
// 27.4-04: ключ scoped per-user — иначе чужой черновик виден после смены логина в том же браузере.
const draftKey = () => `purchase_form_draft_u${localStorage.getItem('user_id') || '0'}`
const draftSaved = ref(false)
const hasDraft = computed(() => !!localStorage.getItem(draftKey()))
let autosaveTimer: ReturnType<typeof setTimeout> | null = null

function saveDraft() {
  if (isEdit.value) return
  localStorage.setItem(draftKey(), JSON.stringify({ form: { ...form }, items: items.value, contractorInn: contractorInn.value }))
  draftSaved.value = true
  setTimeout(() => { draftSaved.value = false }, 2000)
}

async function loadDraft() {
  if (isEdit.value) return
  try {
    // 27.4-04: чистим легаси ключ без user_id (мог содержать чужой черновик)
    try { localStorage.removeItem('purchase_form_draft') } catch {}
    const raw = localStorage.getItem(draftKey())
    if (!raw) return
    const draft = JSON.parse(raw)
    const formData = draft.form || draft
    const savedContractorId = formData.contractor_id
    formData.contractor_id = null // Don't set until loaded
    Object.assign(form, formData)
    if (draft.items?.length) items.value = draft.items
    if (draft.contractorInn) contractorInn.value = draft.contractorInn
    // Load contractor by ID if needed
    if (savedContractorId) {
      let c = contractors.value.find(c => c.id === savedContractorId)
      if (!c) {
        try {
          const fetched = await apiFetch<Contractor>(`/contractors/${savedContractorId}`)
          contractors.value.push(fetched)
          c = fetched
        } catch {}
      }
      form.contractor_id = savedContractorId
      if (c) contractorInn.value = c.inn || ''
    }
    showSnack('Черновик восстановлен', 'info')
  } catch {}
}

function clearDraft() {
  localStorage.removeItem(draftKey())
  // 27.4-04: чистим легаси ключ (без user_id) тоже
  try { localStorage.removeItem('purchase_form_draft') } catch {}
}

watch(form, () => {
  if (isEdit.value) return
  if (autosaveTimer) clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(saveDraft, 3000)
}, { deep: true })

watch([items, contractorInn], () => {
  if (isEdit.value) return
  if (autosaveTimer) clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(saveDraft, 3000)
}, { deep: true })

onMounted(async () => {
  await loadOrgConfig()
  await loadRefs()
  if (isEdit.value && purchaseId.value) {
    await loadPurchase()
    await loadPublications()
    await loadLinkedTasks()
    await loadPurchaseComments()
    await loadPurchaseMembers()
    await loadPurchaseApprovals()
    loadAllUsers()
    approvalPanelRef.value?.loadApprovals()
    // Чеки/импорт чека: для авансовых, для обычной закупки c purchase_method='advance',
    // и для любых обычных закупок (позиции добавляются по QR).
    if (formMode.value === 'advance_report' || formMode.value === 'order' || form.purchase_method === 'advance') {
      await loadReceipts()
      consumePostSaveAction()
    }
  } else {
    // Страховка: прямой /create-order без formMode → редирект на создание заявки
    if (!formMode.value || formMode.value === 'default' || formMode.value === 'order') {
      router.replace('/wishes?create=1')
      return
    }
    await loadDraft()
    // formMode overrides — these are always enforced regardless of draft
    if (formMode.value === 'service_note_delivery') {
      form.purchase_basis = 'service_note'
      form.purchase_method = 'single'
    } else if (formMode.value === 'advance_report') {
      form.purchase_method = 'advance'
    }
    // По умолчанию «Кому возмещать» = текущий пользователь (для новых авансовых).
    // Можно поменять вручную в форме.
    if (
      !form.reimbursement_user_id &&
      (formMode.value === 'advance_report' || form.purchase_method === 'advance') &&
      currentUserId
    ) {
      form.reimbursement_user_id = currentUserId
    }
    // Phase 28 B4: default ответственный исполнитель = текущий пользователь
    // SN-UX: для режима СЗ не подставляем текущего пользователя — ответственный = адресат СЗ
    if (!form.assigned_user_id && currentUserId && formMode.value !== 'service_note_delivery') {
      form.assigned_user_id = currentUserId
    }
    // SN-UX: для новой СЗ — автор = текущий пользователь, дата = сегодня (оба редактируемы)
    if (formMode.value === 'service_note_delivery') {
      if (!form.service_note_by && currentUserId) form.service_note_by = currentUserId
      if (!form.service_note_at) form.service_note_at = new Date().toISOString().slice(0, 10)
    }
    // 26-F4a: пустой плейсхолдер для закрывающего документа при создании
    ensurePlaceholderDoc()
  }
})

const save = async () => {
  const { valid } = await formRef.value.validate()
  feoSaveAttempted.value = true
  const feoErr = feoValidationError.value
  if (!valid || feoErr) {
    showSnack(feoErr || 'Необходимо заполнить выделенные поля', 'error')
    await nextTick()
    showValidationArrows()
    return
  }
  dismissValidationArrows()
  if (form.item_type === 'mixed') {
    const missingType = items.value.filter(i => i.item_name?.trim() && !i.item_type)
    if (missingType.length) {
      // Владелец (2026-09-04): «стрелка должна идти к полям» — ведём к КОНКРЕТНОЙ
      // первой незаполненной позиции (item-row-<uid>), не к блоку целиком.
      const firstUid = missingType[0]._uid
      showSnack(`Укажите тип для ${missingType.length} позиции(й) перед сохранением`, 'error', {
        actionText: 'Показать позицию',
        onAction: () => guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items'),
      })
      await nextTick()
      guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items')
      return
    }
  }
  if (formMode.value === 'advance_report') {
    // Привязка к каталогу для авансовых НЕобязательна: названия позиций в чеках
    // каждый раз чуть отличаются, форсировать каталог нельзя (решение 2026-07-06).
    const unconfirmed = items.value.filter(i => i.item_name?.trim() && i.match_confirmed === false)
    if (unconfirmed.length) {
      // Владелец (2026-09-04): именно эта проверка молчала «куда смотреть» — ведём
      // к первой неподтверждённой позиции из чека.
      const firstUid = unconfirmed[0]._uid
      showSnack(
        `Подтвердите ${unconfirmed.length} позицию(й) из чека: товар, тип и категория должны быть проверены вручную.`,
        'error',
        {
          actionText: 'Показать позицию',
          onAction: () => guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items'),
        },
      )
      await nextTick()
      guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items')
      return
    }
  }
  if (budgetInfo.value?.exceeded) {
    if (!isAdmin.value) {
      showSnack('Превышение бюджета субсидии. Сохранение недоступно.', 'error')
      return
    }
    budgetOverrideDialog.value = true
    return
  }
  await doSave(false)
}

const doSave = async (adminOverride: boolean) => {
  budgetOverrideDialog.value = false
  // F-PIF2: Hard validation — в режиме feo_per_item каждая позиция должна иметь feo_planned_item_id
  if (form.feo_per_item) {
    const missingCount = itemsEditorRef.value?.missingFeoRowsCount?.() ?? 0
    if (missingCount > 0) {
      const firstUid = itemsEditorRef.value?.firstMissingFeoRowUid?.() ?? null
      showSnack(
        `Не сохранено: у ${missingCount} ${missingCount === 1 ? 'позиции' : 'позиций'} не указана ФЭО позиция. Включите режим «Одинаковый на всю закупку» или укажите ФЭО для каждой.`,
        'error',
        {
          actionText: 'Показать позицию',
          onAction: () => guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items'),
        },
      )
      await nextTick()
      guideArrowTo(firstUid != null ? 'item:' + firstUid : 'items')
      return
    }
  }
  // Предупреждение о возможном повторе: разовая закупка (НЕ ежемесячный платёж)
  // с той же суммой и контрагентом в пределах субсидии. См. фидбек пользователя.
  if (!isEdit.value && !form.is_monthly_payment && !duplicateConfirmed
      && form.subsidy_id && form.contractor_id && displayNmck.value > 0) {
    try {
      const matches = await apiFetch<any[]>(
        `/purchases/duplicate-check?subsidy_id=${form.subsidy_id}&contractor_id=${form.contractor_id}&amount=${displayNmck.value}`
      )
      if (matches.length > 0) {
        duplicateMatches.value = matches
        duplicatePendingOverride = adminOverride
        duplicateDialog.value = true
        return
      }
    } catch { /* проверка опциональна — не блокируем сохранение */ }
  }
  duplicateConfirmed = false
  saving.value = true
  try {
    const validItems = items.value
      .filter(i => i.item_name?.trim())
      .map(({ _selectedProduct, _photo_url, _description, _description_44fz, _price_meta, feo_node_id: _feoNodeId, ...rest }) => ({
        ...rest,
        // numOrNull (2026-09-04) заменил локальную проверку `!== '' && != null ? v : null`
        // (ПРАВИЛО №6, один источник истины): '' → null, 0 сохраняется как число.
        unit_price: numOrNull(rest.unit_price),
        quantity: numOrNull(rest.quantity),
        // Возвращено из отката e0db76a (КОРЕНЬ ПРОБЛЕМЫ): раньше здесь ОБА поля
        // принудительно писались как null в режиме single — позиция пересоздавалась
        // и ЛЮБАЯ привязка стиралась первым же сохранением (id 2871 → 2872 на проде,
        // привязка «Great Wall POER» потеряна). Владелец (сессия 2026-08-21): «каждому
        // товару надо присваивать свою плановую» — feo_planned_item_id ВСЕГДА построчный,
        // в ОБОИХ режимах (никакого шапочного фолбэка больше нет, см. allow-per-item-plan
        // в шаблоне и headFeoPlannedItemId — убран целиком). feo_category_id ниже остаётся
        // режимо-зависимым — категория в single-режиме по-прежнему общая на всю закупку.
        feo_planned_item_id: rest.feo_planned_item_id ?? null,
        // FCAT-F1: per-item leaf FeoCategory
        feo_category_id: form.feo_per_item
          ? (rest.feo_category_id ?? null)
          : (rest.feo_category_id ?? form.feo_category_id ?? null),
      }))
    const payload = {
      ...form,
      // contract_price/vat_rate/payment_amount/payment_federal/price_increase/
      // acceptance_term_days/penalty_rate/advance_amount/warranty_period_days/
      // monthly_payment_count/monthly_payment_amount — v-model.number-поля формы,
      // ...form выше протаскивает их СЫРЫМИ: при очистке поля Vue кладёт '', а
      // PurchaseUpdate ждёт Optional[Decimal]/Optional[int] → 422 прямо на «Сохранить».
      // numOrNull — единый хелпер (2026-09-04): '' → null, 0 сохраняется как число
      // во всех полях без исключения.
      contract_price: numOrNull(form.contract_price),
      vat_rate: numOrNull(form.vat_rate),
      payment_amount: numOrNull(form.payment_amount),
      payment_federal: numOrNull(form.payment_federal),
      price_increase: numOrNull(form.price_increase),
      acceptance_term_days: numOrNull(form.acceptance_term_days),
      penalty_rate: numOrNull(form.penalty_rate),
      advance_amount: numOrNull(form.advance_amount),
      warranty_period_days: numOrNull(form.warranty_period_days),
      monthly_payment_count: numOrNull(form.monthly_payment_count),
      monthly_payment_amount: numOrNull(form.monthly_payment_amount),
      planned_total_price: displayNmck.value || null,
      total_nmck: displayNmck.value || null,
      framework_seq: form.framework_seq || null,
      contract_date: form.contract_date || null,
      agreement_number: form.agreement_number || null,
      agreement_date: form.agreement_date || null,
      order_date: form.order_date || null,
      contract_end_date: form.contract_end_date || null,
      commitment_quarter: form.commitment_quarter ?? null,
      planned_payment_month: form.planned_payment_month || null,
      delivery_date: form.delivery_date || null,
      delivery_address: form.delivery_address || null,
      // Структурированный адрес доставки
      delivery_region: form.delivery_region || null,
      delivery_city: form.delivery_city || null,
      delivery_street: form.delivery_street || null,
      delivery_house: form.delivery_house || null,
      delivery_building: form.delivery_building || null,
      delivery_postcode: form.delivery_postcode || null,
      procurement_planned_date: form.procurement_planned_date || null,
      execution_term: form.execution_term || null,
      execution_term_changed: form.execution_term_changed || null,
      service_start_date: form.service_start_date || null,
      service_end_date: form.service_end_date || null,
      // Phase 19: template-specific fields
      submission_deadline: form.submission_deadline || null,
      delivery_location: form.delivery_location || null,
      region: form.region || null,
      service_term_mode: form.service_term_mode || null,
      service_term_days: numOrNull(form.service_term_days),
      service_term_type: form.service_term_mode === 'duration' ? (form.service_term_type || 'calendar') : null,
      service_deadline_date: form.service_deadline_date || null,
      // Phase 25: monthly stages fields
      is_likely_needed: form.is_likely_needed,
      is_prepayment: form.is_prepayment,
      prepayment_date: form.prepayment_date || null,
      stage_label: form.stage_label || null,
      acceptance_doc_date: form.acceptance_doc_date || null,
      // doc.amount — v-model.number (2181): при очистке даёт '', уходит в JSONB-колонку
      // acceptance_docs как есть (не 422 — JSONB грязных строк не валит, но дальше
      // арифметика по amount ловит NaN/'0'). numOrNull приводит перед отправкой:
      // '' → null, 0 сохраняется как число.
      acceptance_docs: acceptanceDocs.value
        .filter(d => d.name?.trim() || d.number?.trim() || d.date?.trim() || (d.amount !== null && d.amount !== undefined))
        .map(d => ({ ...d, amount: numOrNull(d.amount) })),
      payment_doc_date: form.payment_doc_date || null,
      // SN-UX: бэкенд ждёт datetime (YYYY-MM-DDTHH:MM:SS), фронт хранит YYYY-MM-DD → дополним
      service_note_at: form.service_note_at ? (String(form.service_note_at).length === 10 ? `${form.service_note_at}T00:00:00` : form.service_note_at) : null,
      items: validItems,
      subsidy_allocations: form.subsidy_allocations.filter(a => a.subsidy_id > 0),
    }
    // Save new delivery address to history
    if (form.delivery_address) saveDeliveryAddressIfNew(form.delivery_address)

    const _qsParams = new URLSearchParams()
    if (adminOverride) _qsParams.set('admin_override', 'true')
    if (formMode.value === 'service_note_delivery') _qsParams.set('context', 'service_note_delivery')
    const qs = _qsParams.toString() ? `?${_qsParams.toString()}` : ''
    if (isEdit.value) {
      const updated = await apiFetch<any>(`/purchases/${purchaseId.value}${qs}`, { method: 'PUT', body: payload })
      // 12-02: capture FEO match suggestions
      if (updated.suggested_feo_matches?.length) {
        feoMatchSuggestions.value = updated.suggested_feo_matches
      }
      // Владелец (2026-09-02): смена категории ФЭО шапки сбросила привязки
      // позиций к плановым позициям старой категории — см. handleFeoLinksReset.
      if (updated.feo_links_reset) await handleFeoLinksReset(updated.feo_links_reset)
      showExcessWarnings(updated.excess_warnings)
      if (updated.registry_number) form.registry_number = updated.registry_number
      if (updated.contract_number) form.contract_number = updated.contract_number
      if (updated.purchase_number) form.purchase_number = updated.purchase_number
      if (updated.framework_seq != null) form.framework_seq = updated.framework_seq
      // Phase 27.1 W-2: unconditionally save contract_items when status >= contracted
      // Passing empty array correctly clears contract_items on backend
      if (purchaseId.value && canShowContractColumns.value) {
        const drafts = contractItemsState.value.map(ci => ({
          source_item_id: ci.source_item_id ?? null,
          contract_id: ci.contract_id ?? null,
          product_id: ci.product_id ?? null,
          name: ci.name,
          quantity: ci.quantity ?? null,
          unit: ci.unit ?? null,
          unit_price: ci.unit_price ?? null,
          total: ci.total ?? null,
          match_confirmed: ci.match_confirmed,
        }))
        try {
          const savedCi = await replaceAllContractItems(purchaseId.value, drafts)
          contractItemsState.value = savedCi
        } catch (ciErr: any) {
          // Non-fatal: log but don't block purchase save
          console.warn('[contract_items save]', ciErr)
        }
      }
      if (form.vehicle_id) {
        const vOpt = vehicleOptions.value.find(v => v.id === form.vehicle_id)
        showSnack(vOpt ? `Сохранено. Закупка связана с ${vOpt.label}` : 'Сохранено')
      } else {
        showSnack('Сохранено')
      }
    } else {
      const created = await apiFetch<any>(`/purchases/${qs}`, { method: 'POST', body: payload, suppressErrorDialog: true })
      clearDraft()
      showExcessWarnings(created.excess_warnings)
      const hasPostSaveAction = !!sessionStorage.getItem(POST_SAVE_ACTION_KEY)
      if (!hasPostSaveAction) {
        if (form.vehicle_id) {
          const vOpt = vehicleOptions.value.find(v => v.id === form.vehicle_id)
          showSnack(vOpt ? `Закупка создана. Связана с ${vOpt.label}` : 'Закупка создана')
        } else {
          showSnack('Закупка создана')
        }
      }
      const editPath = formMode.value === 'advance_report'
        ? `/advance-reports/${created.id}/edit`
        : formMode.value === 'service_note_delivery'
          ? `/service-notes/${created.id}/edit`
          : `/orders/${created.id}/edit`
      router.push(editPath)
    }
  } catch (e: any) {
    // Phase 27.1.4: handle 409 FRAMEWORK_SEQ_DUPLICATE
    const errCode = e?.code || e?.body?.code || e?.detail?.code
    if (errCode === 'FRAMEWORK_SEQ_DUPLICATE') {
      const msg = e?.message || e?.body?.message || 'Порядковый номер уже занят другой закупкой.'
      const existingId = e?.existing_purchase_id || e?.body?.existing_purchase_id
      const autoFix = window.confirm(
        `${msg}\n\nНажмите OK чтобы сохранить с автоматическим номером, или Отмена чтобы изменить вручную.`
      )
      if (autoFix) {
        form.framework_seq = null
        saving.value = false
        await doSave(adminOverride)
        return
      }
    } else if (e?.status === 403) {
      // Показываем полный detail из бэка (не generic «ошибка»)
      showSnack(e?.payload?.message || e?.detail || 'Нет доступа', 'error')
    } else {
      showSnack(e?.message || e?.detail || 'Ошибка сохранения', 'error')
    }
  } finally {
    saving.value = false
  }
}

function confirmDuplicateSave() {
  duplicateDialog.value = false
  duplicateConfirmed = true
  doSave(duplicatePendingOverride)
}

// Дефект: bare `document.getElementById(...)` в шаблоне (@click) резолвился
// в _ctx.document (undefined) — компилятор Vue 3 в module-режиме (SFC/script
// setup) не проставляет глобалы вроде document/window через `with`, только
// через явный whitelist (GLOBALS_ALLOWED), куда DOM-глобалы не входят.
// В <script setup> тот же идентификатор — обычный JS-global, поэтому вызов
// вынесен в функцию и используется из шаблона по имени.
function scrollToDatesSection() {
  document.getElementById('section-dates')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// Доработка 5 мая: подсветка незаполненных полей при отказе перехода статуса.
// Бэк возвращает detail.missing_fields = ['contract_date', ...]; ищем элементы с
// data-field-name=<имя> и подсвечиваем красным border на 6 секунд + scrollIntoView
// первого. Чистим всё через 6с или при следующей попытке transition.
const highlightedFields = ref<Set<string>>(new Set())
function highlightMissingFields(fields: string[]) {
  highlightedFields.value = new Set(fields)
  nextTick(() => {
    let firstEl: HTMLElement | null = null
    for (const f of fields) {
      const el = document.querySelector<HTMLElement>(`[data-field-name="${f}"]`)
      if (el) {
        el.classList.add('field-missing-highlight')
        if (!firstEl) firstEl = el
      }
    }
    firstEl?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  setTimeout(() => {
    for (const f of fields) {
      document.querySelector<HTMLElement>(`[data-field-name="${f}"]`)?.classList.remove('field-missing-highlight')
    }
    highlightedFields.value = new Set()
  }, 6000)
}

// Владелец (2026-08-21, дефект «Цена договора пустая»): «предлагать ПРОВЕРИТЬ,
// а не молча подставлять» + «названия позиций обычно переносятся из ТЗ — дать
// увидеть перечень, чтобы поправить». Разовая закупка (не рамочная) при переходе
// в «Договор» — лёгкое подтверждение вместо тяжёлого мастера: показываем цену
// (= сумма позиций) и список позиций, которые уйдут в договор; «Изменить
// позиции» уводит к существующему редактору (переиспользуем guideArrowTo,
// он же используется для наведения на поля публикации).
const showContractedConfirm = ref(false)
const contractedConfirmItems = computed(() =>
  items.value
    .filter(i => (i.item_name || '').trim())
    .map(i => ({ name: i.item_name, qty: i.quantity, unit: i.unit, price: i.unit_price }))
)

function onTransitionClick() {
  if (nextStatusTarget.value === 'contracted' && isSinglePurchase.value && !isFramework.value) {
    showContractedConfirm.value = true
    return
  }
  doTransition()
}

function confirmContractedTransition() {
  showContractedConfirm.value = false
  doTransition()
}

function editItemsBeforeContract() {
  showContractedConfirm.value = false
  nextTick(() => guideArrowTo('items'))
}

const doTransition = async () => {
  if (!nextStatusTarget.value || !purchaseId.value) return
  transitioning.value = true
  try {
    const updated = await apiFetch<any>(
      `/purchases/${purchaseId.value}/transition?status=${nextStatusTarget.value}`,
      { method: 'POST' }
    )
    form.status = updated.status
    // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» — см. OrdersView.vue::doTransition.
    if (updated.excess_warnings?.length) {
      showSnack(`Статус → ${STATUS_LABEL.value[updated.status]}. ` + updated.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack(`Статус → ${STATUS_LABEL.value[updated.status]}`)
    }
  } catch (e: any) {
    const missing = e?.payload?.details?.missing_fields
    if (Array.isArray(missing) && missing.length) {
      highlightMissingFields(missing)
    }
    showSnack(e?.detail || 'Ошибка смены статуса', 'error')
  } finally {
    transitioning.value = false
  }
}

// Владелец (2026-09-02, закупка РЕЕ-2026-00904): «раньше суперадмин мог двигать
// закупки по статусам самостоятельно, куда делось это поле» — в списке (OrdersView)
// такое меню есть, в карточке закупки не было вообще. Список статусов и подписи те
// же, что и в шапке этой формы (STATUS_ORDER/STATUS_LABEL/STATUS_COLOR выше) —
// именно они, в свою очередь, единый источник из constants/purchaseStatus.ts,
// которым пользуется и OrdersView.vue (statusItems/statusLabelFor/STATUS_COLOR).
// В отличие от обычного doTransition — минует все workflow-проверки, на любой
// статус, в обе стороны.
const forcingOrderStatus = ref(false)
async function forceOrderStatus(status: string) {
  if (!purchaseId.value || status === form.status) return
  if (!confirm(`Принудительно установить статус «${STATUS_LABEL.value[status]}»? Workflow-проверки будут пропущены.`)) return
  forcingOrderStatus.value = true
  try {
    const updated = await apiFetch<any>(`/purchases/${purchaseId.value}/transition?status=${status}`, { method: 'POST' })
    form.status = updated.status
    if (updated.excess_warnings?.length) {
      showSnack(`Статус принудительно изменён → ${STATUS_LABEL.value[updated.status]}. ` + updated.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack(`Статус принудительно изменён → ${STATUS_LABEL.value[updated.status]}`)
    }
    await loadPurchase()
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || e?.message || 'Ошибка изменения статуса', 'error')
  } finally {
    forcingOrderStatus.value = false
  }
}

const convertToOrder = async () => {
  if (!purchaseId.value) return
  if (!confirm('Переоформить служебную записку в закупку по плану-графику?')) return
  converting.value = true
  try {
    await apiFetch(`/purchases/${purchaseId.value}/convert-to-order`, { method: 'POST' })
    showSnack('Переоформлено в закупку. Перенаправление...')
    setTimeout(() => router.push(`/orders/${purchaseId.value}`), 1000)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка конвертации', 'error')
  } finally {
    converting.value = false
  }
}

const saveSubstatus = async (val: string | null) => {
  if (!purchaseId.value) return
  try {
    const qs = val ? `substatus=${val}` : 'substatus='
    await apiFetch(`/purchases/${purchaseId.value}/substatus?${qs}`, { method: 'PATCH' })
    showSnack(val ? `Подстатус → ${SUBSTATUS_OPTIONS.find(o => o.value === val)?.title}` : 'Подстатус сброшен')
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка обновления подстатуса', 'error')
  }
}

// EDITABLE_MIME, uploadFile/uploadFilesForType/onAcceptanceDocFilesDropped/uploadForSection/
// uploadSectionFile/toggleFileActive/downloadFile/deleteFile, previewDialog/openPreview —
// вынесены в composables/purchase/usePurchaseFiles.ts (вызов usePurchaseFiles() выше по файлу).

// copyDocError — вынесена в components/purchase/DocErrorDialog.vue (использовалась только там).

const downloadDoc = async (docType: string, extraParams = '', loadingKey?: string) => {
  if (!purchaseId.value) return
  docLoading.value = loadingKey || docType
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/documents/${docType}${extraParams}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      // Phase 26-U: ВСЕГДА показываем подробный диалог, если backend вернул structured payload
      // (любой code, не только TEMPLATE_RENDER_ERROR). Generic snackbar — только если JSON не распарсился.
      // Backend exception handler возвращает: {code, message, details, correlation_id}
      // где details = оригинальный dict-detail из HTTPException(detail={...})
      const d = err?.details || err?.detail
      if (err?.code) {
        const info: any = {
          code: err.code,
          message: err.message || 'Ошибка генерации документа',
          correlation_id: err.correlation_id,
        }
        if (d && typeof d === 'object') Object.assign(info, d)
        else if (typeof d === 'string') info.error_raw = d
        docErrorInfo.value = info
        docErrorDialog.value = true
      } else {
        showSnack(err?.message || 'Ошибка генерации документа (нет подробностей от сервера)', 'error')
      }
      return
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    // RFC 5987 filename*=UTF-8''... or plain filename="..."
    let filename = `${docType}.docx`
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match) {
      try { filename = decodeURIComponent(utf8Match[1]) } catch { filename = utf8Match[1] }
    } else {
      const plain = disposition.match(/filename="?([^";]+)"?/)
      if (plain) filename = plain[1]
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch {
    showSnack('Ошибка скачивания документа', 'error')
  } finally {
    docLoading.value = null
  }
}

// ── Фабрикант: пакет документов (ZIP) + override-файлы — вынесено в
// composables/purchase/useFabrikantPackage.ts ──
const {
  downloadFabrikantPackage,
  fabrikantFileInputEl, fabrikantPendingFt, fabrikantOverride,
  triggerFabrikantUpload, uploadFabrikantOverride, deleteFabrikantOverride,
} = useFabrikantPackage(purchaseId, showSnack, docErrorInfo, docErrorDialog, docLoading, uploadedFiles, EDITABLE_MIME, uploading)

// КП (Запрос коммерческих предложений) — вынесен в composables/purchase/usePurchaseKp.ts +
// components/purchase/KpDialog.vue (самодостаточный, состояние внутри компонента).
const kpDialogRef = ref<InstanceType<typeof KpDialog> | null>(null)
</script>

<style scoped>
.framework-siblings-label {
  font-size: 12px;
  color: var(--crm-text-muted);
  display: flex;
  align-items: center;
  font-weight: 500;
}
.framework-siblings-table {
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  overflow: hidden;
}
.framework-siblings-table thead tr th {
  background: var(--crm-table-header);
  font-size: 11px;
  color: var(--crm-text-secondary);
  font-weight: 600;
  padding: 6px 10px !important;
}
.framework-siblings-table tbody tr td {
  padding: 5px 10px !important;
  font-size: 12px;
}
.framework-sibling-current {
  background: var(--crm-surface-hover) !important;
}
.framework-total-row td {
  background: var(--crm-table-stripe);
  border-top: 2px solid var(--crm-border-strong);
}
.tz-table-header { background: var(--crm-table-header); }
.tz-table-footer { background: var(--crm-table-stripe); }
.purchase-chat-container {
  max-height: 350px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  background: var(--crm-table-stripe);
}
.pchat-msg { margin-bottom: 8px; padding: 6px 10px; border-radius: 12px; max-width: 85%; position: relative; }
.pchat-msg--mine { background: #1976d2; color: white; margin-left: auto; border-bottom-right-radius: 4px; }
.pchat-msg--other { background: var(--crm-surface-hover); border: 1px solid var(--crm-border-strong); border-bottom-left-radius: 4px; }
.pchat-msg-header { display: flex; align-items: center; gap: 4px; font-size: 11px; margin-bottom: 2px; }
.pchat-msg-author { font-weight: 600; }
.pchat-msg-time { opacity: 0.6; margin-left: auto; }
.pchat-msg-text { font-size: 13px; white-space: pre-wrap; word-break: break-word; }
.pchat-msg-delete { opacity: 0; transition: opacity .15s; position: absolute; top: 2px; right: 2px; }
.pchat-msg:hover .pchat-msg-delete { opacity: 1; }
.purchase-mention-dropdown {
  background: var(--crm-surface-hover);
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,.12);
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 4px;
}
.purchase-mention-dropdown .mention-item {
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
}
.purchase-mention-dropdown .mention-item:hover { background: var(--crm-table-stripe); }

/* Mobile compact mode for advance reports — drops hint rows + reduces gaps */
@media (max-width: 768px) {
  .compact-mobile :deep(.v-messages) { display: none; }
  .compact-mobile :deep(.v-input__details) { padding-top: 0; min-height: 0; }
  .compact-mobile :deep(.v-row) { row-gap: 0; }
  .compact-mobile :deep(.v-col) { padding-top: 4px; padding-bottom: 4px; }
  .compact-mobile :deep(.v-card-title) { font-size: 0.95rem; padding: 12px 16px 8px; }
  .compact-mobile :deep(.v-card-text) { padding: 8px 12px; }
}

/* Phase 31-06: diff-tracking highlight for unseen changes (GALA-orange) */
.field-changed {
  border-radius: 6px;
  outline: 2px solid #fb923c;
  outline-offset: 2px;
  cursor: pointer;
  transition: outline-color 0.2s;
}
.field-changed:hover {
  outline-color: #ea7a1a;
}
.field-changed-info {
  display: flex;
  align-items: center;
  margin-top: 2px;
  cursor: pointer;
  position: relative;
}
.field-history-card {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 100;
  min-width: 240px;
  max-width: 360px;
  background: white;
}

/* Подсветка обязательных полей, не заполненных на момент перехода статуса.
   Backend возвращает missing_fields → highlightMissingFields() добавляет этот класс. */
.field-missing-highlight {
  position: relative;
  animation: missingFieldPulse 0.6s ease-in-out 0s 4 alternate;
}
.field-missing-highlight :deep(.v-field) {
  outline: 2px solid #DC2626 !important;
  outline-offset: 2px;
  border-radius: 4px;
  background: rgba(220, 38, 38, 0.05);
}
.field-missing-highlight :deep(.v-field__outline) { color: #DC2626 !important; }
@keyframes missingFieldPulse {
  from { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }
  to   { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
}

/* guide-arrow — летящая стрелка с пунктирным следом */
.guide-arrow-overlay { pointer-events: none; }
.guide-arrow-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  filter: drop-shadow(0 2px 6px rgba(229,57,53,0.6));
  transition: transform 0.05s linear;
}
.guide-arrow-icon.guide-arrow-arrived {
  animation: pub-pointer-wiggle 0.9s ease-in-out infinite;
}
.guide-arrow-mdi {
  font-size: 34px;
  color: #e53935;
  line-height: 1;
}

/* pub-pointer / pub-glow вынесены в @/styles/purchase-form.css (используются также
   в components/purchase/*); .guide-arrow-icon.guide-arrow-arrived выше опирается
   на keyframes pub-pointer-wiggle оттуда. */
</style>
