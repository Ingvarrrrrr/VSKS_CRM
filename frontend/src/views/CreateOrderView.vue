<template>
  <v-container fluid class="pa-6" style="max-width:1600px">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold" v-if="!isEdit || purchaseLoaded">
          {{ pageTitle }}
        </h1>
        <div v-else class="text-h5 font-weight-bold text-medium-emphasis">…</div>
        <div class="d-flex align-center gap-2 mt-1">
          <v-chip v-if="isEdit && form.status" :color="STATUS_COLOR[form.status]" size="small" variant="tonal">
            {{ STATUS_LABEL[form.status] }}
          </v-chip>
          <!-- Владелец (2026-09-02, закупка РЕЕ-2026-00904): «раньше суперадмин мог
               двигать закупки по статусам самостоятельно, куда делось это поле» —
               в карточке закупки такого управления не было вообще (было только в
               списке, OrdersView.vue). Минует workflow-проверки, доступно только
               SaaS-роли. -->
          <v-menu v-if="isSaas && isEdit && purchaseId">
            <template #activator="{ props: menuProps }">
              <v-btn v-bind="menuProps" icon="mdi-shield-crown" size="x-small" variant="text" color="red-darken-2"
                :loading="forcingOrderStatus" title="Принудительно сменить статус (SaaS-admin)" />
            </template>
            <v-list density="compact">
              <v-list-item v-for="s in STATUS_ORDER" :key="s" :disabled="s === form.status" @click="forceOrderStatus(s)">
                <template #prepend><v-icon :color="STATUS_COLOR[s]" icon="mdi-circle-medium" /></template>
                <v-list-item-title>{{ STATUS_LABEL[s] }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
          <v-chip v-if="form.substatus" size="x-small" variant="outlined" color="teal">
            {{ SUBSTATUS_OPTIONS.find(o => o.value === form.substatus)?.title || form.substatus }}
          </v-chip>
          <v-icon v-if="form.is_monthly_payment" size="small" color="blue" title="Ежемесячный платёж">mdi-calendar-sync</v-icon>
          <span v-if="isEdit && form.registry_number" class="text-caption text-medium-emphasis">
            Реестр: {{ form.registry_number }}
          </span>
          <v-fade-transition>
            <span v-if="draftSaved" class="text-caption text-success">
              <v-icon size="12" icon="mdi-cloud-check" /> Черновик сохранён
            </span>
          </v-fade-transition>
          <v-btn v-if="!isEdit && hasDraft" size="x-small" variant="outlined" color="warning"
            prepend-icon="mdi-delete-sweep" @click="clearDraft(); showSnack('Черновик удалён')">
            Очистить черновик
          </v-btn>
        </div>
      </div>
      <v-btn variant="outlined" prepend-icon="mdi-arrow-left" :to="backRoute">К списку</v-btn>
    </div>

    <!-- Задача владельца (сессия 2026-08-21): плашка превышения ФЭО + строка «Создана
         из заявки №N». См. computed-и purchaseExcess*/purchaseData выше — оба блока
         тихо не рендерятся, пока backend-агент не досчитал соответствующие поля в
         GET /api/purchases/{id} (v-if по наличию полей, не заглушки). -->
    <div v-if="isEdit && purchaseData?.feo_excess" class="feo-excess-culprit mb-3">
      <v-icon size="16" icon="mdi-alert-decagram" class="mr-1" />
      <span>{{ purchaseExcessText }}</span>
      <v-chip size="x-small" :color="purchaseExcessStateColor" variant="flat" class="ml-1">
        {{ purchaseExcessStateText }}
      </v-chip>
    </div>

    <!-- Владелец (2026-09-02): «уведомление глобально, если позиция категории
         ФЭО вверху и в каждом товаре не соответствует друг другу — об этом
         должен быть алярм прям стоять». По образцу .purchase-stopped-banner
         (OrdersView.vue) — крупная рамка на всю ширину, держится, пока
         расхождение есть (не таймаут-снэкбар). Красный занят остановкой
         закупки — здесь предупреждающий (амбер) цвет. См. GET /api/purchases/{id}
         → feo_mismatch/feo_mismatch_items (app.routers.purchases._compute_purchase_feo_mismatch). -->
    <div v-if="isEdit && purchaseData?.feo_mismatch" class="feo-mismatch-banner mb-3">
      <div class="feo-mismatch-banner__head">
        <v-icon icon="mdi-alert" size="18" class="mr-1" />
        <span class="feo-mismatch-banner__title">РАСХОЖДЕНИЕ КАТЕГОРИИ ФЭО</span>
      </div>
      <div class="feo-mismatch-banner__hint">
        Категория ФЭО у закупки и у товаров не совпадает. Выберите плановую позицию
        из нужной категории либо исправьте категорию — иначе лист согласования и
        план ФЭО разъедутся.
      </div>
      <ul class="feo-mismatch-banner__list">
        <li v-for="mi in (purchaseData?.feo_mismatch_items || [])" :key="mi.item_id">
          {{ mi.message }}
        </li>
      </ul>
      <!-- Владелец (2026-09-02): чинит ровно то, что описывает reason='header'/'both' —
           видна только пока «разные категории для каждого товара» выключены и есть
           хоть одна позиция со своей (протухшей) категорией. См. fixFeoMismatchOwnCategories. -->
      <v-btn v-if="feoMismatchFixableItems.length" size="small" variant="tonal" color="warning"
        prepend-icon="mdi-broom" :loading="fixingFeoMismatch" class="mt-2"
        @click="fixFeoMismatchOwnCategories">
        Убрать свои категории у позиций ({{ feoMismatchFixableItems.length }})
      </v-btn>
    </div>
    <div v-if="isEdit && purchaseData?.wish_id" class="text-caption text-medium-emphasis mb-3 d-flex align-center ga-1 flex-wrap">
      <v-icon size="14" icon="mdi-file-document-outline" />
      <span>Создана из заявки №{{ purchaseData.wish_id }}{{ purchaseData.wish_title ? ` «${purchaseData.wish_title}»` : '' }}</span>
      <v-btn size="x-small" variant="text" color="primary"
        @click="router.push({ path: '/wishes', query: { open: String(purchaseData.wish_id) } })">
        Открыть заявку
      </v-btn>
    </div>
    <!-- Владелец (2026-08-21, дефект «отцеплённая закупка»): status='wishes' —
         закупка скрыта из реестра (см. backend list_purchases). Чип «Желания
         сотрудников» сам по себе ничего не объясняет — прямо говорим, что
         происходит: ждёт одобрения заявки (ещё не в плане) или отцеплена
         обратно в черновик (force_wish_status/принудительный откат). -->
    <v-alert v-if="isEdit && purchaseData?.status === 'wishes' && purchaseData?.wish_id"
      type="warning" variant="tonal" density="compact" class="mb-3">
      {{ wishWithdrawnBannerText }}
    </v-alert>

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
      <v-card
        v-if="showReceiptsOnTop"
        variant="outlined"
        class="mb-4"
        style="border: 2px solid var(--gala-accent, #fb923c); background: rgba(251,146,60,0.04);"
      >
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex flex-wrap align-center ga-2">
          <v-icon color="#fb923c" size="24" class="mr-2">mdi-receipt-text</v-icon>
          <span class="d-flex align-center" style="color: #fb923c;">
            <span>Загрузите чеки&nbsp;</span>
            <v-chip size="x-small" color="#fb923c" variant="tonal" class="ml-1">{{ receipts.length }}</v-chip>
          </span>
          <v-spacer />
          <v-btn size="small" variant="flat" color="#fb923c" @click="onScanQrClick">
            <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
          </v-btn>
          <v-btn size="small" variant="tonal" color="#fb923c" @click="onJsonBtnClick">
            <v-icon start>mdi-file-upload</v-icon>Загрузить чек
          </v-btn>
          <input ref="advJsonReceiptInput" type="file" accept="image/*,.json" multiple
            style="display:none" @change="onJsonReceiptUpload" />
          <v-btn size="small" variant="tonal" @click="onManualBtnClick">
            <v-icon start>mdi-plus</v-icon>Вручную
          </v-btn>
          <v-btn
            v-if="isEdit && purchaseId"
            size="small"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-refresh"
            :loading="recomputeLoading"
            @click="recomputeFromReceipts"
          >
            Пересчитать из чеков
          </v-btn>
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3 text-caption" color="#fb923c">
            Сначала загрузите все чеки — сканируйте QR или загрузите фото/JSON. После загрузки позиции и суммы подтянутся автоматически.
          </v-alert>

          <!-- Empty-state: нет чеков — крупный призыв -->
          <div v-if="receipts.length === 0" class="text-center py-6">
            <v-icon size="48" style="color: #ccc; margin-bottom: 8px;" class="d-block mx-auto">mdi-receipt-text-plus</v-icon>
            <div class="text-subtitle-2 text-medium-emphasis mb-1">Пока нет чеков</div>
            <div class="text-caption text-medium-emphasis mb-4">Нажмите «Сканировать QR» или «Загрузить чек» выше</div>
            <div class="d-flex justify-center ga-2 flex-wrap">
              <v-btn variant="flat" color="#fb923c" @click="onScanQrClick">
                <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
              </v-btn>
              <v-btn variant="tonal" color="#fb923c" @click="onJsonBtnClick">
                <v-icon start>mdi-file-upload</v-icon>Загрузить чек
              </v-btn>
            </div>
          </div>

          <!-- Список загруженных чеков -->
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Продавец</th>
                <th>ИНН</th>
                <th class="text-right">Сумма ₽</th>
                <th>Источник</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in receipts" :key="r.id">
                <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
                <td>{{ r.seller_name || '—' }}</td>
                <td>{{ r.seller_inn || '—' }}</td>
                <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
                <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
                <td>
                  <v-btn size="x-small" variant="text" color="primary"
                    icon="mdi-file-pdf-box"
                    :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
                    target="_blank" rel="noopener" />
                  <v-btn size="x-small" variant="text" color="primary"
                    icon="mdi-file-image"
                    :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
                    target="_blank" rel="noopener" />
                  <v-btn size="x-small" variant="text" color="error"
                    icon="mdi-delete" @click="deleteReceipt(r.id)" />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>

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
                  hint="Поставщик/исполнитель. Поиск по названию или ИНН" persistent-hint
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
                    <td><v-chip :color="statusColor(s.status)" size="x-small" variant="tonal">{{ statusLabel(s.status) }}</v-chip></td>
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
      <v-card v-if="!showReceiptsOnTop && showReceiptsBlock" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex flex-wrap align-center ga-2">
          <span class="d-flex align-center">
            <v-icon start>mdi-receipt-text-outline</v-icon>
            <span>Чеки ({{ receipts.length }})</span>
          </span>
          <v-spacer />
          <v-btn size="small" variant="tonal" color="primary" @click="onScanQrClick">
            <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
          </v-btn>
          <v-btn size="small" variant="tonal" @click="onJsonBtnClick">
            <v-icon start>mdi-file-upload</v-icon>Загрузить чек
          </v-btn>
          <input ref="advJsonReceiptInput" type="file" accept="image/*,.json" multiple
            style="display:none" @change="onJsonReceiptUpload" />
          <v-btn size="small" variant="tonal" @click="onManualBtnClick">
            <v-icon start>mdi-plus</v-icon>Вручную
          </v-btn>
        </v-card-title>
        <v-card-text>
          <v-alert v-if="!isEdit || !purchaseId" type="info" variant="tonal" density="compact" class="mb-0 text-caption">
            При сканировании QR или загрузке фото/JSON чека запись сохранится автоматически, позиции из чеков подтянутся в «Позиции закупки».
          </v-alert>
          <template v-else>
            <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
              Сканируйте QR с чека или загрузите его фото / JSON — данные подтянутся из ФНС, позиции попадут в «Позиции закупки» ниже. Для каждой позиции укажите товар из каталога (или создайте новый).
            </v-alert>
            <div v-if="receipts.length === 0" class="text-center text-medium-emphasis py-4 text-caption">
              Чеков нет — отсканируйте QR, загрузите фото чека (PNG/JPG) или JSON
            </div>
            <v-table v-else density="compact">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Продавец</th>
                  <th>ИНН</th>
                  <th class="text-right">Сумма ₽</th>
                  <th>Источник</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in receipts" :key="r.id">
                  <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
                  <td>{{ r.seller_name || '—' }}</td>
                  <td>{{ r.seller_inn || '—' }}</td>
                  <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
                  <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
                  <td>
                    <v-btn size="x-small" variant="text" color="primary"
                      icon="mdi-file-pdf-box"
                      :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
                      target="_blank" rel="noopener" />
                    <v-btn size="x-small" variant="text" color="primary"
                      icon="mdi-file-image"
                      :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
                      target="_blank" rel="noopener" />
                    <v-btn size="x-small" variant="text" color="error"
                      icon="mdi-delete" @click="deleteReceipt(r.id)" />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </template>
        </v-card-text>
      </v-card>

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

      <!-- 3. Финансы (скрыто для employee и manager) -->
      <v-card v-if="isSectionVisible('financial_indicators') || isSectionVisible('contract_type')" variant="outlined" class="mb-4">
        <v-card-title v-if="isSectionVisible('financial_indicators')" class="text-subtitle-1 font-weight-bold px-4 pt-4">Финансовые показатели</v-card-title>
        <v-card-text>
          <v-row v-if="isSectionVisible('financial_indicators')">
            <v-col cols="12" md="3">
              <div id="pub-target-nmck" style="position:relative">
              <div v-if="pointerTarget === 'nmck'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
              <div :class="pointerTarget === 'nmck' ? 'pub-glow' : ''">
              <div class="text-caption text-medium-emphasis mb-1">НМЦД (итого)</div>
              <v-btn-toggle v-model="nmckMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
                <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
                <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
              </v-btn-toggle>
              <v-text-field v-if="nmckMode === 'auto'"
                :model-value="formatMoney(displayNmck)"
                label="НМЦД (итого)" variant="outlined" density="compact"
                readonly bg-color="grey-lighten-4"
                :hint="nmckHint" persistent-hint />
              <v-text-field v-else
                v-model.number="nmckManualValue"
                label="НМЦД (итого, вручную)" variant="outlined" density="compact"
                type="number" suffix="₽"
                hint="Введено вручную. Цена за единицу в ТЗ скрыта." persistent-hint
                @update:model-value="calcEconomy" />
              </div><!-- /pub-glow -->
              </div><!-- /pub-target-nmck -->
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-caption text-medium-emphasis mb-1">Цена договора</div>
              <v-btn-toggle v-if="!isFrameworkCumulative" v-model="contractPriceMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
                <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
                <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
              </v-btn-toggle>
              <!-- Рамочный накопительный: показываем сумму заказов -->
              <v-text-field v-if="isFrameworkCumulative && selectedFrameworkContract"
                :model-value="selectedFrameworkContract.total_ordered ? formatMoney(Number(selectedFrameworkContract.total_ordered)) : ''"
                label="Сумма заказов по договору" variant="outlined"
                density="compact" suffix="₽" readonly bg-color="grey-lighten-4"
                :placeholder="!selectedFrameworkContract.total_ordered ? 'Ещё ничего не заказывали' : ''"
                :hint="selectedFrameworkContract.total_ordered ? 'Сумма всех заказов по рамочному договору' : ''"
                persistent-hint persistent-placeholder />
              <!-- Остальные типы: стандартное поле цены -->
              <v-text-field v-else v-model.number="form.contract_price"
                :label="isFramework ? 'Предельная сумма договора' : 'Цена договора'" variant="outlined"
                density="compact" type="number" suffix="₽"
                :readonly="contractPriceMode === 'auto' || (isFramework && !!selectedFrameworkContract)"
                :bg-color="(contractPriceMode === 'auto' || (isFramework && !!selectedFrameworkContract)) ? 'grey-lighten-4' : undefined"
                :hint="isFramework && selectedFrameworkContract ? 'Подтянуто из рамочного договора' : contractPriceMode === 'manual' ? 'Введено вручную' : contractPriceHint"
                persistent-hint
                :color="nmckWarningLevel === 'error' ? 'error' : nmckWarningLevel === 'warning' ? 'warning' : undefined"
                @update:model-value="calcEconomy">
                <template v-slot:append-inner>
                  <v-icon v-if="nmckWarningLevel === 'error'" icon="mdi-alert" color="error" size="18" :title="`Превышение НМЦД на ${nmckExcessPct}%`" />
                  <v-icon v-else-if="nmckWarningLevel === 'warning'" icon="mdi-alert-outline" color="warning" size="18" :title="`Близко к НМЦД (+${nmckExcessPct}%)`" />
                </template>
              </v-text-field>
              <div v-if="nmckWarningLevel" class="text-caption mt-n2 mb-1"
                :class="nmckWarningLevel === 'error' ? 'text-error' : 'text-warning'">
                {{ nmckWarningLevel === 'error' ? `Превышение НМЦД на ${nmckExcessPct}%` : `Близко к НМЦД (+${nmckExcessPct}%)` }}
              </div>
            </v-col>
            <v-col cols="12" md="3" class="pt-8">
              <!-- framework_cumulative без лимита: нет отрицательного остатка, только счётчик -->
              <template v-if="isFrameworkCumulative && selectedFrameworkContract && selectedFrameworkContract.remaining_ordered == null">
                <div class="text-caption text-medium-emphasis mb-1">Накопленная сумма заказов</div>
                <div class="text-body-2 font-weight-bold">{{ formatMoney(Number(selectedFrameworkContract.total_ordered ?? 0)) }} ₽</div>
                <div class="text-caption text-medium-emphasis">Накопительный договор без предельной суммы</div>
                <!-- TODO(phase26): кнопка «Согласовать у руководителя» если сумма выходит за разумный предел -->
              </template>
              <!-- framework_with_amount или cumulative с лимитом: показываем остаток -->
              <v-text-field v-else-if="isFramework && selectedFrameworkContract"
                :model-value="selectedFrameworkContract.remaining_ordered != null ? formatMoney(selectedFrameworkContract.remaining_ordered) : '—'"
                :label="isFrameworkCumulative ? 'Остаток (лимит − накоплено)' : 'Остаток средств на договоре'" variant="outlined"
                density="compact" suffix="₽" readonly
                :bg-color="(selectedFrameworkContract.remaining_ordered ?? 0) < 0 ? 'red-lighten-5' : 'grey-lighten-4'"
                :hint="(selectedFrameworkContract.remaining_ordered ?? 0) < 0 ? 'Превышен лимит договора' : 'Предельная сумма минус сумма заказанного'" persistent-hint />
              <v-text-field v-else :model-value="form.economy ?? ''" label="Экономия (авто)" variant="outlined"
                density="compact" suffix="₽" readonly bg-color="grey-lighten-4"
                hint="НМЦД минус Цена договора. Считается автоматически." persistent-hint />
            </v-col>
            <v-col cols="12" md="3" class="pt-8">
              <v-text-field v-model.number="form.price_increase" label="Удорожание (доп. соглашения)"
                variant="outlined" density="compact" type="number" suffix="₽"
                hint="Указывается при увеличении цены по доп. соглашению к договору" persistent-hint />
            </v-col>
          </v-row>
          <!-- Тип договора перенесён в Основную информацию -->
          <v-row v-if="false" class="mt-0">
            <v-col><!-- placeholder --></v-col>
            <v-col v-if="false" cols="12">
              <v-table density="compact" class="framework-siblings-table mt-1">
                <thead>
                  <tr>
                    <th style="width:50px">№</th>
                    <th>Наименование</th>
                    <th>Статус</th>
                    <th class="text-right">НМЦД</th>
                    <th class="text-right">Цена договора</th>
                    <th class="text-right">Оплачено</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="s in frameworkSiblings" :key="s.id"
                    :class="s.id === purchaseId ? 'framework-sibling-current' : ''"
                    style="cursor:pointer"
                    @click="s.id !== purchaseId && $router.push(`/orders/${s.id}`)"
                  >
                    <td>
                      <v-chip :color="s.id === purchaseId ? 'primary' : 'default'" size="x-small" variant="tonal">
                        {{ s.framework_seq ?? '—' }}
                      </v-chip>
                    </td>
                    <td class="text-caption">{{ s.item_name || s.subject || '—' }}</td>
                    <td><v-chip :color="statusColor(s.status)" size="x-small" variant="tonal">{{ statusLabel(s.status) }}</v-chip></td>
                    <td class="text-right text-caption">{{ s.total_nmck ? formatMoney(Number(s.total_nmck)) : '—' }}</td>
                    <td class="text-right text-caption">{{ s.contract_price ? formatMoney(Number(s.contract_price)) : '—' }}</td>
                    <td class="text-right text-caption">{{ s.payment_amount ? formatMoney(Number(s.payment_amount)) : '—' }}</td>
                  </tr>
                  <!-- Итоговая строка -->
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
        </v-card-text>
      </v-card>

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
                  :hint="needsContract ? `Обязательно для перехода в статус ${contractWord}` : isNew ? 'Будет присвоен автоматически или введите вручную' : 'Можно изменить вручную'"
                  persistent-hint
                  :readonly="!isNew && !contractNumberEditEnabled"
                  data-field="contract_number"
                  @click="!isNew && !contractNumberEditEnabled && enableContractNumberEdit()" />
              </div>
            </v-col>
            <v-col cols="12" md="3" data-field-name="contract_date">
              <div :class="entityChanges.isFieldUnseen('contract_date') ? 'field-changed' : ''"
                @click="entityChanges.dismissField('contract_date')">
                <v-text-field v-model="form.contract_date" :label="`Дата ${contractWordGen}`" variant="outlined"
                  density="compact" type="date" :rules="contractDateRules" data-field="contract_date" />
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
            <v-card variant="outlined" class="mb-3">
              <v-card-title class="d-flex align-center pa-3 text-subtitle-2">
                <v-icon start>mdi-receipt-text-outline</v-icon>
                <span>Чеки ({{ receipts.length }})</span>
                <v-spacer />
                <v-btn size="small" variant="tonal" @click="$refs.jsonReceiptInput.click()">
                  <v-icon start>mdi-file-upload</v-icon>JSON чека
                </v-btn>
                <input ref="jsonReceiptInput" type="file" accept=".json" multiple
                  style="display:none" @change="onJsonReceiptUpload" />
                <v-btn size="small" variant="tonal" class="ml-2" @click="openManualReceiptDialog">
                  <v-icon start>mdi-plus</v-icon>Вручную
                </v-btn>
              </v-card-title>
              <v-card-text v-if="receipts.length === 0" class="text-center text-medium-emphasis py-4">
                Чеков нет — загрузите JSON из приложения «Проверка чека» (ФНС) или введите данные вручную
              </v-card-text>
              <v-table v-else density="compact">
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Продавец</th>
                    <th>ИНН</th>
                    <th class="text-right">Сумма ₽</th>
                    <th>Источник</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in receipts" :key="r.id">
                    <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
                    <td>{{ r.seller_name || '—' }}</td>
                    <td>{{ r.seller_inn || '—' }}</td>
                    <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
                    <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
                    <td>
                      <v-btn size="x-small" variant="text" color="primary"
                        icon="mdi-file-pdf-box"
                        :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
                        target="_blank" rel="noopener" />
                      <v-btn size="x-small" variant="text" color="primary"
                        icon="mdi-file-image"
                        :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
                        target="_blank" rel="noopener" />
                      <v-btn size="x-small" variant="text" color="error"
                        icon="mdi-delete" @click="deleteReceipt(r.id)" />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
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

      <!-- 4а. Параметры для генерации договора (admin+) -->
      <v-card v-if="isSectionVisible('contract_params')" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Параметры {{ contractWordGen }} (для документа)</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <v-select
                v-model="form.service_period_type"
                :items="[{title: 'Период (с... по...)', value: 'period'}, {title: 'Разовая дата', value: 'date'}]"
                item-title="title" item-value="value"
                label="Тип срока оказания услуг" variant="outlined" density="compact" clearable
              />
            </v-col>
            <!-- Даты редактируются только в блоке «Сроки и даты» ниже -->
            <v-col cols="12" md="5">
              <div class="d-flex align-center gap-2 mt-1">
                <v-icon size="16" color="blue-grey-lighten-2">mdi-calendar-range</v-icon>
                <span class="text-body-2 text-medium-emphasis">
                  <template v-if="form.service_period_type === 'period'">
                    Период:
                    <strong>{{ form.service_start_date || '—' }}</strong>
                    &nbsp;—&nbsp;
                    <strong>{{ form.service_end_date || '—' }}</strong>
                  </template>
                  <template v-else-if="form.service_period_type === 'date'">
                    Дата оказания услуг:
                    <strong>{{ form.service_start_date || '—' }}</strong>
                  </template>
                  <template v-else>Тип срока не выбран</template>
                </span>
                <v-btn
                  size="x-small" variant="text" color="primary" class="ml-1"
                  @click="document.getElementById('section-dates')?.scrollIntoView({ behavior: 'smooth', block: 'start' })"
                >Изменить ↓</v-btn>
              </div>
              <div class="text-caption text-medium-emphasis">Изменить даты — в блоке «Сроки и даты»</div>
            </v-col>
            <v-col cols="12" md="3">
              <v-checkbox
                v-model="form.third_party_involved"
                label="Привлечение третьих лиц"
                density="compact" hide-details class="mt-2"
              />
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12" md="3">
              <v-checkbox
                v-model="form.vat_applicable"
                label="НДС применяется"
                density="compact" hide-details
              />
            </v-col>
            <v-col v-if="form.vat_applicable" cols="12" md="2">
              <v-text-field
                v-model.number="form.vat_rate"
                label="Ставка НДС (%)" variant="outlined" density="compact" type="number"
                suffix="%" placeholder="20"
              />
            </v-col>
            <v-col v-if="!form.vat_applicable" cols="12" md="6">
              <v-text-field
                v-model="form.vat_exemption_article"
                label="Основание освобождения от НДС (статья НК РФ)"
                variant="outlined" density="compact"
                placeholder="напр. п.2 ст.346.11 НК РФ (УСН)"
              />
            </v-col>
            <!-- U-3: НДС режим toggle -->
            <v-col cols="12" md="4" class="d-flex align-center">
              <v-btn-toggle
                v-model="form.vat_mode"
                density="compact"
                rounded="lg"
                color="primary"
                border
                mandatory
                @update:model-value="onVatModeChange"
              >
                <v-btn value="uniform" size="small">НДС одинаковый</v-btn>
                <v-btn value="per_item" size="small">НДС для каждого товара</v-btn>
              </v-btn-toggle>
            </v-col>
          </v-row>

          <!-- Phase 23: customer requisites preview -->
          <v-card variant="outlined" class="mb-3" style="border-color:#9c6ade; background:transparent">
            <v-card-text class="pa-3">
              <div class="d-flex align-center mb-2">
                <v-icon icon="mdi-domain" size="18" color="purple-darken-2" class="mr-2" />
                <span class="text-body-1 font-weight-bold">Реквизиты Заказчика (подставятся в шаблон)</span>
                <v-spacer />
                <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-information-outline" @click="showPlaceholdersDialog = true">
                  Доступные переменные
                </v-btn>
              </div>
              <div v-if="customerPreview" class="text-body-2 text-high-emphasis" style="line-height:1.7">
                <div><strong>{{ customerPreview.full_name || customerPreview.name }}</strong></div>
                <div>ИНН/КПП: {{ customerPreview.inn || '—' }} / {{ customerPreview.kpp || '—' }}</div>
                <div v-if="customerPreview.address">Адрес: {{ customerPreview.address }}</div>
                <div v-if="customerPreview.signatory">Подписант: {{ customerPreview.signatory }}</div>
              </div>
              <div v-else class="text-body-2 text-medium-emphasis">
                Сначала выберите субсидию — реквизиты возьмутся из её организации.
              </div>
              <div class="text-caption text-high-emphasis mt-2">
                Изменить реквизиты можно в карточке организации (Иерархия → клик на организацию).
              </div>
            </v-card-text>
          </v-card>

          <!-- Phase 19: template-specific fields (submission deadline, delivery location, service term) -->
          <v-divider class="my-3" />
          <div class="text-subtitle-2 font-weight-bold mb-1">Для формирования договора</div>
          <div class="text-caption text-high-emphasis mb-2">
            Переменные, которые не были определены ранее (форма договора, приём заявок, место и срок оказания услуг)
          </div>
          <!-- Форма договора (текст договора) + методичка (приложение к договору, выбирается отдельно) -->
          <v-row v-if="formMode !== 'service_note_delivery' && formMode !== 'advance_report' && form.purchase_method !== 'advance'">
            <v-col cols="12" md="6">
              <v-select
                v-model="form.contract_form"
                :items="contractFormOptions"
                item-title="title"
                item-value="value"
                label="Форма договора (текст договора)"
                variant="outlined"
                density="compact"
                clearable
                hint="Определяет какой шаблон используется при скачивании «Договор» и «Договор+ТЗ»"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-select
                v-model="form.methodology"
                :items="methodologyOptions"
                item-title="title"
                item-value="value"
                label="Методические рекомендации"
                variant="outlined"
                density="compact"
                clearable
                hint="Приложение к договору — приклеивается к готовому документу отдельно от формы договора. Не выбирается автоматически."
                persistent-hint
              />
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12">
              <div id="pub-target-address" style="position:relative">
                <div v-if="pointerTarget === 'address'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                <div :class="pointerTarget === 'address' ? 'pub-glow' : ''">
                  <div class="mb-1">
                    <v-btn-toggle
                      v-model="form.delivery_location_kind"
                      density="compact" mandatory color="primary" variant="outlined"
                    >
                      <v-btn value="delivery" size="small">Адрес доставки</v-btn>
                      <v-btn value="service" size="small">Место оказания услуг</v-btn>
                    </v-btn-toggle>
                  </div>
                  <AddressAutocomplete
                    v-model="form.delivery_location"
                    :label="deliveryLabel"
                    :customer-address="customerPreview?.address"
                    hint="Подставится в шаблон документа"
                    persistent-hint
                  />
                </div>
              </div>
            </v-col>
          </v-row>
          <!-- Регион поставки и Регион проведения мероприятия — рядом в одной строке -->
          <v-row>
            <v-col cols="12" md="6">
              <div id="pub-target-region" style="position:relative">
                <div v-if="pointerTarget === 'region'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                <div :class="pointerTarget === 'region' ? 'pub-glow' : ''">
                  <v-autocomplete
                    v-model="form.delivery_region"
                    :items="DELIVERY_REGIONS"
                    label="Регион поставки (субъект РФ)"
                    density="compact"
                    variant="outlined"
                    clearable
                    hide-details
                    hint="Используется для ОКАТО/федерального округа места поставки Фабриканта"
                    persistent-hint
                    @update:model-value="pointerTarget = null; clearGuideArrow()"
                  />
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="6">
              <v-autocomplete
                v-model="form.region"
                :items="RUSSIAN_REGIONS"
                label="Регион проведения мероприятия"
                density="compact"
                variant="outlined"
                clearable
                hide-details
                hint='Включая вариант "Федеральное мероприятие"'
                persistent-hint
              />
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.delivery_postcode"
                label="Индекс"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.delivery_city"
                label="Город / населённый пункт"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.delivery_street"
                label="Улица"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model="form.delivery_house"
                label="Дом"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="1">
              <v-text-field
                v-model="form.delivery_building"
                label="Корпус"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
          </v-row>
          <!-- Новые поля: скорее всего понадобится, предоплата перенесена в «Сроки и даты», подпись этапа -->
          <v-row class="mt-2">
            <v-col cols="12" md="4">
              <v-checkbox
                v-model="form.is_likely_needed"
                label="Скорее всего понадобится"
                density="compact" hide-details
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-checkbox
                v-model="form.is_prepayment"
                label="Предоплата"
                density="compact" hide-details
              />
            </v-col>
            <v-col v-if="form.is_prepayment" cols="12" md="4">
              <!-- дата предоплаты перенесена в блок «Сроки и даты» -->
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.stage_label"
                label="Подпись этапа"
                variant="outlined" density="compact"
                hint="Например: Февраль 2026"
                persistent-hint
              />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 4б. Сроки и даты закупки — единый блок -->
      <v-card id="section-dates" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
          <v-icon start color="blue-grey">mdi-calendar-clock</v-icon>
          Сроки и даты
        </v-card-title>
        <v-card-text>

          <!-- Планирование -->
          <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Планирование</div>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.procurement_planned_date"
                label="Планируемая дата закупки"
                variant="outlined" density="compact" type="date"
                hint="Когда планируем провести закупку — используется в плане закупок"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.delivery_date"
                label="Нужна к дате"
                variant="outlined" density="compact" type="date"
                hint="Срок, к которому товар/услуга должны быть получены"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.submission_deadline"
                label="Приём заявок до"
                variant="outlined" density="compact"
                type="datetime-local"
                hint="Дедлайн подачи предложений поставщиками (уходит на Фабрикант как {{submission_deadline_datetime}})"
                persistent-hint
              />
            </v-col>
          </v-row>

          <v-divider class="my-3" />

          <!-- Исполнение -->
          <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Исполнение</div>
          <v-row>
            <v-col cols="12">
              <div class="text-body-2 mb-1">Срок оказания услуг</div>
              <v-radio-group
                v-model="form.service_term_mode"
                inline density="compact" hide-details class="mt-0"
              >
                <v-radio label="Не указано" value="" />
                <v-radio label="Конкретные даты (с… по…)" value="range" />
                <v-radio label="В течение N дней" value="duration" />
                <v-radio label="До даты" value="deadline" />
              </v-radio-group>
              <div class="text-caption text-medium-emphasis mt-1">Как считается срок исполнения: период, длительность или конкретная дата</div>
            </v-col>
          </v-row>
          <v-row v-if="form.service_term_mode === 'range'">
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.service_start_date"
                label="Начало периода" type="date"
                variant="outlined" density="compact"
                hint="Дата начала оказания услуг/поставки" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.service_end_date"
                label="Конец периода" type="date"
                variant="outlined" density="compact"
                hint="Дата завершения оказания услуг/поставки" persistent-hint
              />
            </v-col>
          </v-row>
          <v-row v-if="form.service_term_mode === 'duration'">
            <v-col cols="12" md="3">
              <v-text-field
                v-model.number="form.service_term_days"
                label="Количество дней" type="number" min="1"
                variant="outlined" density="compact"
                hint="Срок исполнения в днях от даты подписания" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="form.service_term_type"
                :items="[{title: 'Календарных', value: 'calendar'}, {title: 'Рабочих', value: 'working'}]"
                item-title="title" item-value="value"
                label="Тип дней" variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <v-row v-if="form.service_term_mode === 'deadline'">
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.service_deadline_date"
                label="До какой даты" type="date"
                variant="outlined" density="compact"
                hint="Услуга/поставка должна быть исполнена не позднее этой даты" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4" class="d-flex align-center gap-2">
              <!-- Конец месяца quick-fill -->
              <v-menu v-model="endOfMonthMenu" :close-on-content-click="false" location="bottom">
                <template #activator="{ props: menuProps }">
                  <v-btn v-bind="menuProps" size="small" variant="tonal" color="teal" prepend-icon="mdi-calendar-end">
                    Конец месяца
                  </v-btn>
                </template>
                <v-card min-width="260" class="pa-3">
                  <div class="text-body-2 font-weight-medium mb-2">Выберите период</div>
                  <v-row dense>
                    <v-col cols="6">
                      <v-text-field
                        v-model.number="endOfMonthYear"
                        label="Год" type="number" min="2020" max="2040"
                        variant="outlined" density="compact"
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-select
                        v-model="endOfMonthMonth"
                        :items="endOfMonthMonthItems"
                        item-title="label" item-value="value"
                        label="Месяц"
                        variant="outlined" density="compact"
                      />
                    </v-col>
                  </v-row>
                  <v-btn color="primary" size="small" block @click="applyEndOfMonth">Применить</v-btn>
                </v-card>
              </v-menu>
            </v-col>
          </v-row>

          <v-divider class="my-3" />

          <!-- Договор и оплата -->
          <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Договор и оплата</div>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.contract_end_date"
                label="Срок действия договора"
                variant="outlined" density="compact" type="date"
                :readonly="isFramework && !!selectedFrameworkContract?.end_date"
                :bg-color="isFramework && selectedFrameworkContract?.end_date ? 'grey-lighten-4' : undefined"
                hint="До какой даты действует договор" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="form.commitment_quarter"
                :items="[1,2,3,4]"
                label="Квартал принятия обязательств"
                variant="outlined" density="compact" clearable
                hint="Квартал, в котором приняты обязательства" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.planned_payment_month"
                label="Планируемый месяц платежа"
                variant="outlined" density="compact" type="date"
                hint="Месяц, в котором планируется платёж" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.agreement_date"
                label="Дата доп.соглашения"
                variant="outlined" density="compact" type="date"
                hint="Дата подписания дополнительного соглашения (при наличии)" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="form.order_date"
                label="Дата заказа"
                variant="outlined" density="compact" type="date"
                hint="Когда сделан заказ поставщику" persistent-hint
              />
            </v-col>
            <v-col v-if="form.is_prepayment" cols="12" md="3">
              <v-text-field
                v-model="form.prepayment_date"
                label="Дата предоплаты" type="date"
                variant="outlined" density="compact"
                hint="Когда возникло обязательство по предоплате" persistent-hint
              />
            </v-col>
          </v-row>

        </v-card-text>
      </v-card>

      <!-- 5. Закрывающие документы (admin+) -->
      <v-card v-if="isSectionVisible('acceptance')" variant="outlined" class="mb-4">
        <!-- Мобильный фикс (владелец, 2026-09-04, «прокручиваемых вбок таблиц быть не должно»):
             заголовок + кнопка без flex-wrap уезжали за правый край на узком экране, кнопка
             «Добавить закрывающий документ» обрезалась. flex-wrap ga-2 — тот же приём, что уже
             применён у заголовков «Загрузите чеки»/«Чеки» выше в этом файле: на десктопе места
             хватает и перенос не срабатывает, на мобильном кнопка уходит на вторую строку. -->
        <v-card-title class="d-flex flex-wrap align-center ga-2 text-subtitle-1 font-weight-bold px-4 pt-4">
          Закрывающие документы
          <v-spacer />
          <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="addAcceptanceDoc">Добавить закрывающий документ</v-btn>
        </v-card-title>
        <v-card-text>
          <!-- Phase 26-ppp: кнопки «Загрузить» для типов документов (Договор/Акт/УПД/...)
               перенесены в секцию «Документы к закупке» (один блок upload вместо
               двух мест). Здесь оставляем ТОЛЬКО реквизиты (тип/№/дата/сумма) —
               связь с файлом по-прежнему есть через doc.file_id paperclip-кнопку. -->

          <!-- Реквизиты закрывающих документов -->
          <div v-for="(doc, idx) in acceptanceDocs" :key="idx" class="mb-3">
            <div class="d-flex align-center gap-2 mb-1">
              <span class="text-caption font-weight-medium">Документ {{ idx + 1 }}</span>
              <v-spacer />
              <v-btn
                v-if="doc.file_id"
                icon="mdi-paperclip"
                variant="text"
                size="x-small"
                color="primary"
                title="Скачать прикреплённый файл (чек)"
                @click="downloadAcceptanceFile(doc.file_id!)"
              />
              <v-btn icon="mdi-close" variant="text" size="x-small" color="error" @click="acceptanceDocs.splice(idx, 1)" />
            </div>
            <v-row dense>
              <v-col cols="12" md="5">
                <v-combobox
                  v-model="doc.name"
                  :items="acceptanceDocTypes"
                  label="Тип документа"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  @update:model-value="onAcceptanceDocTypeAdd($event)"
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps" :title="item.raw">
                      <template #append>
                        <v-btn
                          v-if="!BUILTIN_ACCEPTANCE_DOC_TYPES.includes(item.raw)"
                          icon="mdi-close"
                          size="x-small"
                          variant="text"
                          color="error"
                          @click.stop="deleteCustomDocType(item.raw)"
                        />
                      </template>
                    </v-list-item>
                  </template>
                </v-combobox>
              </v-col>
              <v-col cols="12" md="2">
                <v-text-field v-model="doc.number" label="Номер" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="12" md="2">
                <v-text-field v-model="doc.date" label="Дата" variant="outlined" density="compact" type="date" hide-details />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field v-model.number="doc.amount" label="Сумма" variant="outlined" density="compact" type="number" suffix="₽" hide-details />
              </v-col>
            </v-row>
            <v-divider v-if="idx < acceptanceDocs.length - 1" class="mt-3" />
          </div>

          <!-- Кнопка загрузки чека для авансового отчёта -->
          <div v-if="isEdit && purchaseId && (formMode === 'advance_report' || form.purchase_method === 'advance')" class="mt-3 mb-1">
            <v-btn size="small" variant="tonal" color="#fb923c" prepend-icon="mdi-receipt-text" @click="onJsonBtnClick">
              Загрузить чек
            </v-btn>
          </div>

          <!-- DnD-загрузка закрывающих документов (Phase 31-03) -->
          <FileDropZone
            v-if="isEdit && purchaseId"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
            :multiple="true"
            hint="Перетащите закрывающий документ (Акт/УПД/Прочее)"
            @files="onAcceptanceDocFilesDropped"
            class="mt-3"
          >
            <template #default="{ dragging, open }">
              <div
                class="d-flex align-center justify-center gap-2 pa-3"
                style="min-height:120px; border:1px dashed var(--gala-accent, #fb923c); border-radius:6px"
                :style="{ background: dragging ? 'rgba(251,146,60,0.08)' : 'transparent' }"
              >
                <v-icon :color="dragging ? '#fb923c' : 'grey'" size="20">mdi-file-upload-outline</v-icon>
                <span class="text-body-2 text-medium-emphasis">Перетащите закрывающий документ или</span>
                <v-btn variant="text" size="small" color="#fb923c" @click.stop="open()">выберите</v-btn>
              </div>
            </template>
          </FileDropZone>
        </v-card-text>
      </v-card>

      <!-- 6. Платёж (admin+) -->
      <v-card v-if="isSectionVisible('payment')" variant="outlined" class="mb-4">
        <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
          Платёж
        </v-card-title>
        <v-card-text>
          <!-- Загрузка платёжных документов -->
          <div v-if="isEdit && purchaseId" class="mb-4">
            <div class="d-flex align-center gap-2 py-2 border-b">
              <v-icon size="18" color="orange">mdi-cash-check</v-icon>
              <span class="text-body-2 font-weight-medium" style="min-width:120px">Платёжка</span>
              <v-btn size="x-small" variant="tonal" color="orange" prepend-icon="mdi-upload"
                :loading="uploading && pendingSectionUpload === 'invoice'" @click="uploadForSection('invoice')">
                Загрузить
              </v-btn>
              <v-spacer />
              <div class="d-flex flex-wrap gap-1">
                <template v-for="f in paymentFiles" :key="f.id">
                  <v-chip size="small" :color="f.is_active ? 'orange' : 'grey'" :variant="f.is_active ? 'tonal' : 'outlined'"
                    closable @click:close="deleteFile(f.id)" @click="downloadFile(f.id, f.filename)">
                    <v-icon start size="14">mdi-file</v-icon>
                    {{ f.filename.length > 25 ? f.filename.slice(0, 22) + '...' : f.filename }}
                    <template #append>
                      <v-tooltip :text="f.is_active ? 'Актуальный' : 'Не актуальный'" location="top">
                        <template #activator="{ props: tp }">
                          <v-icon v-bind="tp" size="14" class="ml-1" :color="f.is_active ? 'success' : 'grey'"
                            @click.stop="toggleFileActive(f)">{{ f.is_active ? 'mdi-check-circle' : 'mdi-close-circle-outline' }}</v-icon>
                        </template>
                      </v-tooltip>
                    </template>
                  </v-chip>
                </template>
              </div>
            </div>
          </div>
          <v-row>
            <v-col cols="12" md="4" data-field-name="payment_doc_number">
              <v-text-field v-model="form.payment_doc_number" label="Номер платёжного поручения" variant="outlined" density="compact"
                readonly hint="Заполняется автоматически из платежей. См. раздел Платежи ниже" persistent-hint />
            </v-col>
            <v-col cols="12" md="4" data-field-name="payment_doc_date">
              <v-text-field v-model="form.payment_doc_date" label="Дата ПП" variant="outlined" density="compact" type="date"
                readonly hint="Заполняется автоматически из платежей" persistent-hint />
            </v-col>
            <v-col cols="12" md="4" data-field-name="payment_amount">
              <v-text-field v-model.number="form.payment_amount" label="Сумма платежа" variant="outlined"
                density="compact" type="number" suffix="₽" readonly hint="Заполняется автоматически из платежей" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.payment_federal" label="в т.ч. федеральный бюджет" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.treasury_code" label="Казначейский код" variant="outlined" density="compact"
                hint="Код для Приложения №3, колонка S" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-checkbox v-model="form.has_pretension" label="Претензионная работа" density="compact"
                hint="Колонка U в Приложении №3" persistent-hint />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

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
      <v-dialog v-model="pBroadcastDialog" max-width="480" persistent :fullscreen="mobile">
        <v-card>
          <v-card-title class="d-flex align-center gap-2 pt-4">
            <v-icon color="orange">mdi-bullhorn</v-icon>
            Рассылка из закупки
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-3">
              Сообщение будет отправлено каждому сотруднику индивидуально в Telegram
            </div>
            <v-radio-group v-model="pBroadcastScope" class="mb-3">
              <v-radio value="department" label="Отдел" />
              <v-radio value="organization" label="Организация" />
              <v-radio v-if="pBroadcastOrgs.length > 1" value="all" label="Все организации" />
            </v-radio-group>
            <v-select v-if="pBroadcastScope === 'department'" v-model="pBroadcastScopeId"
              :items="pBroadcastDepts" item-title="name" item-value="id"
              label="Выберите отдел" variant="outlined" density="compact" class="mb-3" />
            <v-select v-if="pBroadcastScope === 'organization'" v-model="pBroadcastScopeId"
              :items="pBroadcastOrgs" item-title="name" item-value="id"
              label="Выберите организацию" variant="outlined" density="compact" class="mb-3" />
            <v-textarea v-model="pBroadcastText" label="Текст сообщения" variant="outlined"
              density="compact" rows="3" autofocus />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="pBroadcastDialog = false">Отмена</v-btn>
            <v-btn color="orange" variant="tonal" :loading="pBroadcastSending"
              :disabled="!pBroadcastText.trim() || (pBroadcastScope !== 'all' && !pBroadcastScopeId)"
              @click="sendPurchaseBroadcast">
              Отправить
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 7. Файлы (скрыто для employee, если нет права purchase_files.upload и не участник/согласующий) -->
      <v-card v-if="canSeePurchaseDocs" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы к закупке</v-card-title>
        <v-card-text>
          <!-- Phase 26-ppp: typed-upload секции перенесены сюда из «Закрывающие
               документы» — единая точка загрузки всех файлов закупки.
               Каждая кнопка «Загрузить» назначает file_type (contract/act/upd/
               invoice/order/etc) при upload. Файлы списком ниже. -->
          <div class="doc-upload-grid mb-4">
            <FileDropZone v-for="sec in DOC_UPLOAD_SECTIONS" :key="sec.type"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" :multiple="true" :disabled="!purchaseId"
              class="doc-upload-tile" style="min-height:140px; align-items:flex-start; padding:12px"
              @files="(files: File[]) => uploadFilesForType(files, sec.type)">
              <template #default="{ dragging }">
                <div class="doc-upload-tile-inner" :class="{ 'doc-upload-tile-inner--dragging': dragging && purchaseId }">
                  <div class="d-flex align-center gap-2 mb-1">
                    <v-icon size="20" :color="sec.color">{{ sec.icon }}</v-icon>
                    <span class="text-body-2 font-weight-medium">{{ sec.label }}</span>
                    <v-spacer />
                    <v-progress-circular v-if="uploading && pendingSectionUpload === sec.type"
                      indeterminate size="16" width="2" :color="sec.color" />
                  </div>
                  <div class="text-caption text-medium-emphasis mb-2">
                    {{ purchaseId ? 'Перетащите файл сюда или нажмите' : 'Сначала сохраните закупку' }}
                  </div>
                  <div v-if="filesByType(sec.type).length" class="d-flex flex-wrap gap-1" @click.stop>
                    <template v-for="f in filesByType(sec.type)" :key="f.id">
                      <v-chip size="small" :color="f.is_active ? sec.color : 'grey'" :variant="f.is_active ? 'tonal' : 'outlined'"
                        closable @click:close="deleteFile(f.id)" @click="downloadFile(f.id, f.filename)">
                        <v-icon start size="14">mdi-file</v-icon>
                        {{ f.filename.length > 20 ? f.filename.slice(0, 17) + '...' : f.filename }}
                        <template #append>
                          <v-tooltip :text="f.is_active ? 'Актуальный — нажмите чтобы деактивировать' : 'Не актуальный — нажмите чтобы активировать'" location="top">
                            <template #activator="{ props: tp }">
                              <v-icon v-bind="tp" size="14" class="ml-1" :color="f.is_active ? 'success' : 'grey'"
                                @click.stop="toggleFileActive(f)">{{ f.is_active ? 'mdi-check-circle' : 'mdi-close-circle-outline' }}</v-icon>
                            </template>
                          </v-tooltip>
                        </template>
                      </v-chip>
                    </template>
                  </div>
                </div>
              </template>
            </FileDropZone>
          </div>
          <input ref="sectionFileInputEl" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
            style="display:none" @change="uploadSectionFile" />
          <input ref="fileInputEl" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
            style="display:none" @change="uploadFile" />

          <v-list v-if="uploadedFiles.length" density="compact">
            <v-list-item v-for="f in uploadedFiles" :key="f.id"
              :prepend-icon="fileIcon(f.mime_type)"
            >
              <template #title>
                <span class="text-body-2">{{ f.filename }}</span>
                <v-chip size="x-small" class="ml-2" :color="fileTypeColor(f.file_type)" variant="tonal"
                  style="cursor:pointer" @click="openFileTypeEdit(f)">
                  {{ FILE_TYPE_LABELS[f.file_type || 'other'] || 'Прочее' }}
                  <v-icon size="10" class="ml-1">mdi-pencil</v-icon>
                </v-chip>
                <v-chip size="x-small" class="ml-1"
                  :color="f.doc_format === 'editable' ? 'blue' : 'grey'"
                  :prepend-icon="f.doc_format === 'editable' ? 'mdi-file-edit-outline' : 'mdi-scanner'"
                  variant="tonal" style="cursor:pointer" @click="toggleDocFormat(f)">
                  {{ f.doc_format === 'editable' ? 'Ред.' : 'Скан' }}
                </v-chip>
              </template>
              <template #subtitle>
                {{ formatSize(f.size) }}
                <span v-if="f.uploaded_by_name || f.created_at" class="text-medium-emphasis ml-2">
                  · {{ f.uploaded_by_name || '' }}{{ f.created_at ? ' · ' + formatDate(f.created_at) : '' }}
                </span>
              </template>
              <template #append>
                <v-btn v-if="isPreviewable(f.mime_type)" icon="mdi-eye-outline" variant="text" size="small" color="primary"
                  @click="openPreview(f)" />
                <v-btn icon="mdi-download" variant="text" size="small" @click="downloadFile(f.id, f.filename)" />
                <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                  @click="deleteFile(f.id)" />
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="text-caption text-medium-emphasis">Нет загруженных файлов</div>
        </v-card-text>
      </v-card>

      <!-- Диалог загрузки файла -->
      <v-dialog v-model="uploadDialog" max-width="420" persistent :fullscreen="mobile">
        <v-card>
          <v-card-title class="text-subtitle-1 pt-4 px-4">Загрузить файл</v-card-title>
          <v-card-text class="pb-0">
            <v-select v-model="uploadFileType"
              :items="FILE_TYPE_OPTIONS" item-title="title" item-value="value"
              label="Тип документа" variant="outlined" density="compact" class="mb-3" />
            <div class="text-body-2 mb-2">Формат файла</div>
            <v-btn-toggle v-model="uploadDocFormat" mandatory density="compact" color="primary" class="mb-1">
              <v-btn value="scan" prepend-icon="mdi-scanner">Скан</v-btn>
              <v-btn value="editable" prepend-icon="mdi-file-edit-outline">Редактируемый</v-btn>
            </v-btn-toggle>
            <div class="text-caption text-medium-emphasis mb-2">
              Редактируемый — только Word и Excel. PDF и изображения всегда скан.
            </div>
            <div class="text-caption text-medium-emphasis">PDF, Word, Excel, JPEG, PNG</div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="uploadDialog = false">Отмена</v-btn>
            <v-btn color="primary" variant="tonal" @click="fileInputEl?.click()">
              Выбрать файл
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Диалог смены типа файла -->
      <v-dialog v-model="fileTypeEditDialog" max-width="380">
        <v-card>
          <v-card-title class="text-subtitle-1 pt-4 px-4">Тип документа</v-card-title>
          <v-card-text>
            <v-select v-model="fileTypeEditValue"
              :items="FILE_TYPE_OPTIONS" item-title="title" item-value="value"
              label="Тип" variant="outlined" density="compact" class="mb-3" />
            <div class="text-body-2 mb-2">Формат файла</div>
            <v-btn-toggle v-model="fileDocFormatEditValue" mandatory density="compact" color="primary">
              <v-btn value="scan" prepend-icon="mdi-scanner">Скан</v-btn>
              <v-btn value="editable" prepend-icon="mdi-file-edit-outline"
                :disabled="fileTypeEditTarget ? !EDITABLE_MIME.has(fileTypeEditTarget.mime_type || '') : false">
                Редактируемый
              </v-btn>
            </v-btn-toggle>
            <div v-if="fileTypeEditTarget && !EDITABLE_MIME.has(fileTypeEditTarget.mime_type || '')"
              class="text-caption text-orange mt-1">
              Только Word/Excel могут быть редактируемыми
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="fileTypeEditDialog = false">Отмена</v-btn>
            <v-btn color="primary" variant="tonal" :loading="savingFileType" @click="saveFileType">Сохранить</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

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
            @click="openKpDialog">
            Разослать КП
          </v-btn>
        </v-card-title>
        <v-card-text class="px-4 pb-3 text-caption text-medium-emphasis">
          Отправьте запрос КП поставщикам с описанием закупки. Письма формируются через почтовый клиент.
        </v-card-text>
      </v-card>

      <!-- 10. Публикация на площадках (can_publish permission) -->
      <v-card v-if="isEdit && isSectionVisible('platform_publication') && canPublish" variant="outlined" class="mb-4" style="border-color:#7C3AED">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
          <span class="d-flex align-center gap-2">
            <v-icon icon="mdi-broadcast" color="deep-purple" size="20" />
            Публикация на площадках
          </span>
          <div class="d-flex gap-2">
            <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-folder-zip"
              :loading="docLoading === 'fabrikant_package'"
              @click="downloadFabrikantPackage">
              Скачать пакет (ZIP)
            </v-btn>
            <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-upload-network"
              @click="publishErrors = checkPublishReady(); publishDialog = true; pendingPlatform = null; fabrikantNoNmcd = !(publishNmck > 0)">
              Опубликовать
            </v-btn>
          </div>
        </v-card-title>
        <v-card-text class="px-4 pb-3">
          <div v-if="!publications.length" class="text-medium-emphasis text-caption">
            Закупка ещё не публиковалась ни на одной площадке
          </div>
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th class="text-caption text-medium-emphasis" style="width:140px">Площадка</th>
                <th class="text-caption text-medium-emphasis" style="width:130px">Статус</th>
                <th class="text-caption text-medium-emphasis" style="width:160px">Номер закупки</th>
                <th class="text-caption text-medium-emphasis">Ссылка на закупку</th>
                <th class="text-caption text-medium-emphasis"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pub in publications" :key="pub.id">
                <td class="font-weight-medium text-caption">{{ PLATFORM_LABELS[pub.platform] || pub.platform }}</td>
                <td>
                  <v-chip size="x-small" :color="PUB_STATUS_COLOR[pub.status]" variant="tonal">
                    {{ PUB_STATUS_LABEL[pub.status] || pub.status }}
                  </v-chip>
                </td>
                <td class="text-caption">
                  <template v-if="pub.status === 'draft'">
                    <span v-if="pub.platform_number" class="font-weight-medium">{{ pub.platform_number }}</span>
                    <span v-else-if="pub.external_id" class="text-medium-emphasis">{{ pub.external_id }}</span>
                    <span v-else class="text-medium-emphasis">—</span>
                  </template>
                  <span v-else-if="pub.status === 'error'" class="text-error" style="white-space: normal; word-break: break-word">{{ pub.error_text || 'Ошибка публикации' }}</span>
                  <span v-else-if="pub.external_id">{{ pub.external_id }}</span>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
                <td class="text-caption">
                  <!-- Черновик: ссылка недоступна до размещения — показываем пояснение -->
                  <template v-if="pub.status === 'draft'">
                    <span class="text-orange-darken-2">
                      Черновик №{{ pub.platform_number || '—' }} создан на Фабриканте.
                      Разместите его в личном кабинете площадки — до размещения ссылка недоступна.
                    </span>
                  </template>
                  <template v-else>
                    <a v-if="pub.external_url" :href="pub.external_url" target="_blank"
                      class="text-blue-darken-2 text-decoration-none">
                      {{ pub.external_url }}
                      <v-icon size="11">mdi-open-in-new</v-icon>
                    </a>
                    <span v-else class="text-medium-emphasis">—</span>
                  </template>
                </td>
                <td style="width:72px" class="text-right">
                  <!-- Обновить статус: для черновика и опубликованного (состояние может меняться) -->
                  <v-btn
                    v-if="pub.platform === 'fabrikant' && (pub.status === 'draft' || pub.status === 'published')"
                    icon="mdi-refresh"
                    size="x-small"
                    variant="text"
                    color="orange-darken-2"
                    :loading="refreshingPubId === pub.id"
                    title="Обновить статус с площадки"
                    @click="refreshPubStatus(pub)"
                  />
                  <!-- Ретрай при ошибке -->
                  <v-btn v-if="pub.status === 'error'" icon="mdi-send" size="x-small" variant="text"
                    color="deep-purple" @click="pub.platform === 'fabrikant' ? openFabrikantRetry(pub.platform) : retryPublish(pub.platform)" />
                </td>
              </tr>
            </tbody>
          </v-table>

          <!-- Документы пакета Фабрикант -->
          <v-divider class="my-3" />
          <div class="text-caption font-weight-medium text-deep-purple mb-2">Документы пакета Фабрикант</div>
          <input ref="fabrikantFileInputEl" type="file" accept=".docx,.pdf" style="display:none"
            @change="uploadFabrikantOverride" />
          <v-list density="compact" class="pa-0">
            <v-list-item v-for="doc in FABRIKANT_PKG_DOCS" :key="doc.ft" class="px-0 py-1" min-height="36">
              <template #prepend>
                <span class="text-caption" style="min-width:160px">{{ doc.label }}</span>
              </template>
              <template #default>
                <v-chip v-if="fabrikantOverride(doc.ft)" size="x-small" color="deep-purple" variant="tonal" class="mr-1">
                  своя версия
                </v-chip>
                <v-chip v-else size="x-small" color="grey" variant="tonal" class="mr-1">авто</v-chip>
                <span v-if="fabrikantOverride(doc.ft)" class="text-caption text-medium-emphasis mr-2">
                  {{ fabrikantOverride(doc.ft)!.filename }}
                </span>
              </template>
              <template #append>
                <v-btn icon="mdi-upload" size="x-small" variant="text" density="compact"
                  @click="triggerFabrikantUpload(doc.ft)" title="Загрузить свою версию" />
                <template v-if="fabrikantOverride(doc.ft)">
                  <v-btn icon="mdi-download" size="x-small" variant="text" density="compact"
                    @click="downloadFile(fabrikantOverride(doc.ft)!.id, fabrikantOverride(doc.ft)!.filename)" />
                  <v-btn icon="mdi-delete-outline" size="x-small" variant="text" density="compact" color="error"
                    @click="deleteFabrikantOverride(fabrikantOverride(doc.ft)!.id)" />
                </template>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>

      <!-- Связанные задачи -->
      <v-card v-if="isEdit && purchaseId" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 d-flex align-center gap-2">
          <v-icon size="20">mdi-clipboard-check-outline</v-icon>
          Связанные задачи
          <v-chip size="x-small" variant="tonal" color="primary">{{ linkedTasks.length }}</v-chip>
          <v-spacer />
          <v-btn size="small" variant="tonal" color="secondary" prepend-icon="mdi-link-variant"
            :to="`/my-tasks?link_purchase=${purchaseId}`" class="mr-2">
            Привязать
          </v-btn>
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus"
            @click="openCreateLinkedTask">
            Создать
          </v-btn>
        </v-card-title>
        <v-card-text v-if="linkedTasks.length" class="pt-0">
          <v-list density="compact" class="pa-0">
            <v-list-item v-for="lt in linkedTasks" :key="lt.id" class="px-2"
              @click="$router.push(`/my-tasks?task=${lt.id}`)">
              <template #prepend>
                <v-icon :color="taskStatusColor(lt.status)" size="18">
                  {{ lt.status === 'done' ? 'mdi-check-circle' : lt.status === 'in_progress' ? 'mdi-progress-clock' : 'mdi-circle-outline' }}
                </v-icon>
              </template>
              <v-list-item-title class="text-body-2">{{ lt.title }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                <v-chip size="x-small" variant="flat" :color="taskPriorityColor(lt.priority)" class="mr-1">
                  {{ lt.priority }}
                </v-chip>
                <span v-if="lt.assignees?.length">
                  {{ lt.assignees.map((a: any) => a.user_name || `#${a.user_id}`).join(', ') }}
                </span>
                <span v-if="lt.due_date" class="ml-2">
                  · до {{ new Date(lt.due_date).toLocaleDateString('ru') }}
                </span>
              </v-list-item-subtitle>
              <template #append>
                <v-chip size="x-small" variant="tonal" :color="taskStatusColor(lt.status)" class="mr-1">
                  {{ TASK_STATUS_LABEL[lt.status] || lt.status }}
                </v-chip>
                <v-btn icon="mdi-link-variant-off" size="x-small" variant="text" color="grey"
                  title="Отвязать задачу" @click.stop="unlinkTask(lt.id)" />
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-text v-else class="text-caption text-medium-emphasis pt-0">
          Нет связанных задач. Нажмите «Создать задачу» чтобы делегировать работу по этой закупке.
        </v-card-text>
      </v-card>

      <!-- Диалог создания связанной задачи -->
      <v-dialog v-model="linkedTaskDialog" max-width="560" persistent :fullscreen="mobile">
        <v-card>
          <v-card-title class="text-subtitle-1 pt-4 px-4">
            <v-icon class="mr-1" size="20">mdi-clipboard-plus-outline</v-icon>
            Задача по закупке
          </v-card-title>
          <v-card-text>
            <v-text-field v-model="linkedTaskForm.title" label="Заголовок задачи" variant="outlined"
              density="compact" class="mb-3" :rules="[v => !!v || 'Обязательно']" />
            <v-textarea v-model="linkedTaskForm.description" label="Описание" variant="outlined"
              density="compact" rows="2" class="mb-3" />
            <div class="d-flex gap-3 mb-3">
              <v-select v-model="linkedTaskForm.priority" :items="TASK_PRIORITIES"
                item-title="title" item-value="value"
                label="Приоритет" variant="outlined" density="compact" style="max-width:180px" />
              <v-text-field v-model="linkedTaskForm.due_date" label="Срок" type="date"
                variant="outlined" density="compact" />
            </div>
            <v-autocomplete v-model="linkedTaskForm.assignee_ids" :items="allUsers"
              item-title="text" item-value="value" label="Исполнители" variant="outlined"
              density="compact" multiple chips closable-chips />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="linkedTaskDialog = false">Отмена</v-btn>
            <v-btn color="primary" variant="tonal" :loading="linkedTaskSaving"
              :disabled="!linkedTaskForm.title" @click="saveLinkedTask">
              Создать
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Диалог привязки существующей задачи -->
      <v-dialog v-model="linkTaskDialog" max-width="520" :fullscreen="mobile">
        <v-card>
          <v-card-title class="text-subtitle-1 pt-4 px-4">
            <v-icon class="mr-1" size="20">mdi-link-variant</v-icon>
            Привязать задачу к закупке
          </v-card-title>
          <v-card-text>
            <v-text-field v-model="linkTaskSearch" label="Поиск по названию задачи" variant="outlined"
              density="compact" prepend-inner-icon="mdi-magnify" clearable autofocus
              @update:model-value="searchUnlinkedTasks" />
            <div v-if="linkTaskSearching" class="d-flex justify-center py-4"><v-progress-circular indeterminate size="24" /></div>
            <v-list v-else-if="linkTaskResults.length" density="compact" class="border rounded" style="max-height:300px;overflow-y:auto">
              <v-list-item v-for="t in linkTaskResults" :key="t.id" @click="linkExistingTask(t.id)">
                <template #prepend>
                  <v-icon :color="taskStatusColor(t.status)" size="18">
                    {{ t.status === 'done' ? 'mdi-check-circle' : t.status === 'in_progress' ? 'mdi-progress-clock' : 'mdi-circle-outline' }}
                  </v-icon>
                </template>
                <v-list-item-title class="text-body-2">{{ t.title }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ t.assignees?.map((a: any) => a.user_name).join(', ') || 'Без исполнителя' }}
                  <span v-if="t.purchase_id" class="text-warning ml-1">(уже привязана)</span>
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <div v-else-if="linkTaskSearch" class="text-caption text-medium-emphasis text-center py-4">
              Задачи не найдены
            </div>
            <div v-else class="text-caption text-medium-emphasis text-center py-4">
              Введите текст для поиска задач
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="linkTaskDialog = false">Закрыть</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

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

    <!-- Publish dialog -->
    <v-dialog v-model="publishDialog" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon color="deep-purple">mdi-broadcast</v-icon>
          Опубликовать закупку
        </v-card-title>
        <v-card-text class="px-6">

          <!-- Ошибки валидации -->
          <v-alert v-if="publishErrors.length" type="error" variant="tonal" density="compact" class="mb-4">
            <div class="text-subtitle-2 mb-1">Заполните обязательные поля:</div>
            <ul class="pl-4 mb-0">
              <li v-for="e in publishErrors" :key="e.target" class="text-body-2"
                style="cursor:pointer" @click="revealField(e.target)">
                <v-icon size="14" class="mr-1">mdi-arrow-right-circle</v-icon>{{ e.text }}
              </li>
            </ul>
          </v-alert>

            <p class="text-body-2 text-medium-emphasis mb-4">
              Выберите площадку. Данные закупки будут отправлены автоматически.
            </p>
            <v-list density="compact" class="border rounded">
              <v-list-item
                v-for="pl in AVAILABLE_PLATFORMS" :key="pl.value"
                :title="pl.title"
                :subtitle="pl.subtitle"
                class="py-3"
              >
                <template #prepend>
                  <v-avatar :color="pl.color" size="36" class="mr-3">
                    <v-icon size="18" color="white">{{ pl.icon }}</v-icon>
                  </v-avatar>
                </template>
                <template #append>
                  <v-btn
                    color="deep-purple" variant="tonal" size="small"
                    :loading="publishingPlatform === pl.value"
                    :disabled="isPlatformPublished(pl.value)"
                    @click="pendingPlatform = pl.value; if (pl.value === 'fabrikant') { initFabrikantDates(); fabrikantNoNmcd = !(publishNmck > 0) }"
                  >
                    {{ publications.some(p => p.platform === pl.value && p.status === 'draft') ? 'Черновик на ЭТП' : isPlatformPublished(pl.value) ? 'Опубликовано' : 'Опубликовать' }}
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>

            <!-- Настройки Фабрикант: даты -->
            <v-expand-transition>
              <div v-if="pendingPlatform === 'fabrikant'" class="mt-3 px-1">
                <v-divider class="mb-3" />
                <div class="text-subtitle-2 mb-3">Параметры публикации на Фабрикант</div>
                <v-alert v-if="!currentSubsidyOrgInn" type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
                  Не заполнен ИНН организации-заказчика. Перейдите в раздел <strong>Организации</strong> → нажмите карандаш → укажите ИНН.
                </v-alert>

                <!-- Тип процедуры -->
                <v-select
                  v-model="fabrikantProcedureType"
                  :items="FABRIKANT_PROCEDURE_TYPES"
                  item-title="title"
                  item-value="value"
                  label="Тип процедуры"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="mb-3"
                />

                <!-- Подсказка для Мониторинга цен -->
                <v-alert v-if="fabrikantProcedureType === 'price_monitoring'" type="info" variant="tonal" density="compact" class="mb-3 text-caption">
                  Сбор ценовых предложений без объявления цены и позиций. НМЦД не требуется.
                </v-alert>

                <div id="pub-target-okpd2" style="position:relative">
                  <v-autocomplete
                    v-model="fabrikantOkpd2"
                    :items="okpd2Items"
                    :item-value="(i: {code: string}) => i.code"
                    :item-title="(i: {code: string; name: string}) => okpd2ItemTitle(i)"
                    :no-filter="true"
                    :loading="okpd2Loading"
                    clearable
                    label="Код ОКПД2 (обязательно)"
                    variant="outlined"
                    density="compact"
                    class="mb-3"
                    :error="okpd2Pointer && !fabrikantOkpd2"
                    @update:search="searchOkpd2"
                    @update:model-value="okpd2Pointer = false; clearGuideArrow()"
                  >
                    <template #no-data>
                      <v-list-item>
                        <v-list-item-title class="text-caption" :class="okpd2Error ? 'text-error' : 'text-medium-emphasis'">
                          {{ okpd2Error || 'Ничего не найдено' }}
                        </v-list-item-title>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                  <div v-if="okpd2Pointer" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                </div>

                <!-- НМЦД — скрыт для Мониторинга цен -->
                <div v-if="fabrikantProcedureType !== 'price_monitoring'" class="mb-3">
                  <div v-if="publishNmck > 0" class="text-body-2 mb-1">
                    НМЦД: <strong>{{ formatMoney(publishNmck) }}</strong>
                  </div>
                  <v-checkbox
                    v-model="fabrikantNoNmcd"
                    label="Опубликовать без НМЦД"
                    density="compact"
                    hide-details
                    color="orange-darken-2"
                  />
                  <div v-if="publishNmck === 0" class="text-caption text-medium-emphasis mt-1">
                    НМЦД не найдена в закупке — будет опубликовано без НМЦД. Чтобы указать цену, заполните НМЦД в карточке.
                    <v-btn variant="text" size="x-small" class="ml-1" @click="revealField('nmck')">Показать поле НМЦД</v-btn>
                  </div>
                </div>

                <v-row dense>
                  <v-col cols="12" sm="6">
                    <v-text-field
                      v-model="fabrikantDates.proposal_start"
                      type="datetime-local"
                      label="Начало приёма предложений"
                      variant="outlined" density="compact"
                    />
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field
                      v-model="fabrikantDates.proposal_end"
                      type="datetime-local"
                      label="Конец приёма предложений"
                      variant="outlined" density="compact"
                    />
                  </v-col>
                  <!-- Определение победителя — только для ЗП -->
                  <v-col v-if="fabrikantProcedureType === 'zp'" cols="12" sm="6">
                    <v-text-field
                      v-model="fabrikantDates.determination_date"
                      type="datetime-local"
                      label="Определение победителя"
                      variant="outlined" density="compact"
                    />
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field
                      v-model="fabrikantDates.summing_up_date"
                      type="datetime-local"
                      label="Подведение итогов"
                      variant="outlined" density="compact"
                    />
                  </v-col>
                </v-row>

                <!-- Поля редукциона -->
                <template v-if="fabrikantProcedureType === 'reduction'">
                  <v-divider class="my-2" />
                  <div class="text-caption text-medium-emphasis mb-2">Параметры редукциона</div>
                  <v-row dense>
                    <v-col cols="12">
                      <div id="pub-target-auction-date" style="position:relative">
                        <div v-if="auctionPointerTarget === 'auction-date'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                        <div :class="auctionPointerTarget === 'auction-date' ? 'pub-glow' : ''">
                          <v-text-field
                            v-model="fabrikantAuctionDateStart"
                            type="datetime-local"
                            label="Дата и время начала редукциона *"
                            variant="outlined" density="compact"
                            :error="!fabrikantAuctionDateStart"
                            @update:model-value="auctionPointerTarget = null; clearGuideArrow()"
                          />
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6">
                      <div id="pub-target-auction-bet" style="position:relative">
                        <div v-if="auctionPointerTarget === 'auction-bet'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                        <div :class="auctionPointerTarget === 'auction-bet' ? 'pub-glow' : ''">
                          <v-text-field
                            v-model.number="fabrikantAuctionBetFrom"
                            type="number"
                            label="Граница ставки от *"
                            variant="outlined" density="compact"
                            :error="numOrNull(fabrikantAuctionBetFrom) === null"
                            @update:model-value="auctionPointerTarget = null; clearGuideArrow()"
                          />
                        </div>
                      </div>
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="fabrikantAuctionBetTo"
                        type="number"
                        label="Граница ставки до *"
                        variant="outlined" density="compact"
                        :error="numOrNull(fabrikantAuctionBetTo) === null"
                        @update:model-value="auctionPointerTarget = null"
                      />
                    </v-col>
                  </v-row>
                </template>

                <v-checkbox
                  v-model="fabrikantAttachDocs"
                  label="Прикрепить пакет документов (5 файлов)"
                  density="compact"
                  hide-details
                  color="orange-darken-2"
                  class="mb-2"
                />
                <div class="d-flex gap-2 mt-1">
                  <v-btn variant="text" @click="pendingPlatform = null">Назад</v-btn>
                  <v-btn color="orange-darken-2"
                    :loading="publishingPlatform === 'fabrikant'"
                    :disabled="!fabrikantOkpd2 || !fabrikantDates.proposal_start || !fabrikantDates.proposal_end || !currentSubsidyOrgInn"
                    @click="() => { publishErrors = checkPublishReady(); if (!publishErrors.length) doPublish('fabrikant'); else revealField(publishErrors[0].target) }"
                  >Опубликовать на Фабрикант</v-btn>
                </div>
              </div>
            </v-expand-transition>

            <!-- Выбор типа процедуры для Росэлторг -->
            <v-expand-transition>
              <div v-if="pendingPlatform === 'roseltorg_rb'" class="mt-3 px-1">
                <v-divider class="mb-3" />
                <div class="text-subtitle-2 mb-2">Тип процедуры Росэлторг.Бизнес</div>
                <v-select
                  v-model="roseltorgProcedureType"
                  :items="ROSELTORG_PROCEDURE_TYPES"
                  item-title="title"
                  item-value="value"
                  label="Выберите тип процедуры"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
                <div class="d-flex gap-2 mt-3">
                  <v-btn variant="text" @click="pendingPlatform = null; roseltorgProcedureType = null">Назад</v-btn>
                  <v-btn
                    color="deep-purple"
                    :disabled="!roseltorgProcedureType"
                    :loading="publishingPlatform === 'roseltorg_rb'"
                    @click="doPublish('roseltorg_rb', roseltorgProcedureType)"
                  >Опубликовать на Росэлторг</v-btn>
                </div>
              </div>
            </v-expand-transition>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="publishDialog = false; pendingPlatform = null; roseltorgProcedureType = null; publishErrors = []">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог подтверждения превышения бюджета -->
    <v-dialog v-model="budgetOverrideDialog" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 d-flex align-center ga-2">
          <v-icon color="warning">mdi-alert</v-icon>
          Превышение бюджета субсидии
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-3">
            Сумма закупки превышает остаток бюджета субсидии на
            <strong>{{ budgetInfo ? formatMoney(budgetInfo.over) : '' }}</strong>.
          </v-alert>
          Как администратор вы можете сохранить закупку с превышением бюджета.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="outlined" @click="budgetOverrideDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="flat" :loading="saving" @click="doSave(true)">
            Сохранить с превышением
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="feoPerItemDisableDialog" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 d-flex align-center ga-2">
          <v-icon color="warning">mdi-alert</v-icon>
          Отключить разные ФЭО по позициям?
        </v-card-title>
        <v-card-text>
          У {{ feoPerItemDisableCount }} {{ feoPerItemDisableCount === 1 ? 'позиции' : 'позиций' }} указана своя категория ФЭО — при отключении режима она будет очищена.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="outlined" @click="cancelFeoPerItemDisable">Отмена</v-btn>
          <v-btn color="warning" variant="flat" @click="confirmFeoPerItemDisable">Отключить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="duplicateDialog" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-warning">Возможный повтор закупки</v-card-title>
        <v-card-text>
          <div class="mb-3">Уже есть разовые закупки с этим контрагентом и совпадающей суммой (НМЦК, цена договора или платёж). Возможно, это повтор:</div>
          <v-list density="compact">
            <v-list-item v-for="m in duplicateMatches" :key="m.id"
              @click="$router.push(`/orders/${m.id}/edit`)" style="cursor:pointer;">
              <v-list-item-title>№{{ m.purchase_number ?? m.id }} — {{ m.name || 'без названия' }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ m.total_nmck != null ? Number(m.total_nmck).toLocaleString('ru-RU') + ' ₽' : '' }}
                <span v-if="(m as any).match_reason"> · совпало по: {{ (m as any).match_reason }}</span>
                <span v-if="m.contract_date"> · {{ m.contract_date }}</span>
                · {{ m.status }}
              </v-list-item-subtitle>
              <template #append><v-icon size="small">mdi-open-in-new</v-icon></template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer/>
          <v-btn variant="text" @click="duplicateDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="flat" @click="confirmDuplicateSave">Всё равно сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Владелец (2026-08-21, дефект «Цена договора пустая»): переход в «Договор»
         молча подставлял сумму позиций (backend Phase 27.1 D-07) без единого
         подтверждения — предлагаем проверить цену и перечень позиций (обычно
         переносятся из ТЗ) перед заключением договора. -->
    <v-dialog v-model="showContractedConfirm" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center ga-2">
          <v-icon color="indigo">mdi-file-sign</v-icon>
          Проверьте перед переходом в «Договор»
        </v-card-title>
        <v-card-text>
          <div class="mb-3">
            Цена договора = сумма позиций
            <strong>{{ formatMoney(displayNmck) }}</strong>.
            Проверьте перед заключением договора — при необходимости измените ниже.
          </div>
          <v-text-field
            v-model.number="form.contract_price"
            label="Цена договора" type="number" variant="outlined" density="compact"
            suffix="₽" hide-details class="mb-3"
            @update:model-value="contractPriceMode = 'manual'"
          />
          <div class="text-caption text-medium-emphasis mb-1">
            В договор уйдут позиции ниже. Названия обычно переносятся из ТЗ — если что-то
            нужно поправить, откройте редактор позиций.
          </div>
          <v-list density="compact" class="mb-2" style="max-height:260px;overflow-y:auto">
            <v-list-item v-for="(it, idx) in contractedConfirmItems" :key="idx">
              <v-list-item-title>{{ it.name }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ it.qty ?? '—' }} {{ it.unit || '' }} × {{ it.price != null ? formatMoney(it.price) : '—' }}
              </v-list-item-subtitle>
            </v-list-item>
            <v-list-item v-if="!contractedConfirmItems.length">
              <v-list-item-title class="text-medium-emphasis">Позиции не заполнены</v-list-item-title>
            </v-list-item>
          </v-list>
          <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-pencil"
            @click="editItemsBeforeContract">
            Изменить позиции
          </v-btn>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showContractedConfirm = false">Отмена</v-btn>
          <v-btn color="indigo" variant="flat" :loading="transitioning" @click="confirmContractedTransition">
            Всё верно, перейти в «Договор»
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
    <v-dialog v-model="splitKanbanDialog" max-width="1200" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 pb-2">
          <v-icon class="mr-2" color="primary">mdi-call-split</v-icon>
          Разбить закупку на несколько
          <span class="text-caption text-medium-emphasis ml-3">
            · Перетащите позиции по колонкам, затем «Разбить на N закупок»
          </span>
        </v-card-title>
        <v-card-text class="pa-4">
          <PurchaseSplitKanban
            v-if="splitKanbanDialog && splitKanbanItems.length && purchaseId"
            :purchase-id="purchaseId"
            :items="splitKanbanItems"
            @split="onPurchaseSplit"
            @cancel="splitKanbanDialog = false"
            @error="(m: string) => showSnack(m, 'error')"
          />
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- File preview dialog -->
    <v-dialog v-model="previewDialog" max-width="900" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon :icon="fileIcon(previewFile?.mime_type)" class="mr-2" />
          {{ previewFile?.filename }}
          <v-spacer />
          <v-btn icon="mdi-download" variant="text" size="small" @click="previewFile && downloadFile(previewFile.id, previewFile.filename)" />
          <v-btn icon="mdi-close" variant="text" size="small" @click="previewDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0" style="min-height:500px">
          <iframe v-if="previewFile?.mime_type === 'application/pdf'"
            :src="previewUrl" style="width:100%;height:600px;border:none" />
          <div v-else-if="previewFile?.mime_type?.startsWith('image/')" class="d-flex justify-center pa-4">
            <img :src="previewUrl" style="max-width:100%;max-height:600px;object-fit:contain" />
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Add contractor inline dialog -->
    <v-dialog v-model="addContractorDialog" max-width="700" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-account-plus" class="mr-2" />Новый контрагент
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <!-- Import from file -->
          <div class="mb-4 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Данные:</strong> система автоматически извлечёт реквизиты из карточки контрагента
              </div>
            </v-alert>
            <FileDropZone v-model="addContractorFile" accept=".xlsx,.xls,.pdf,.docx,.doc"
              hint="Excel, Word, PDF — перетащите или нажмите" class="mb-2" />
            <v-btn v-if="addContractorFile" variant="tonal" color="primary" size="small" :loading="addContractorImporting"
              @click="importContractorFromFile">Заполнить поля из файла</v-btn>
          </div>
          <v-select v-model="addContractorForm.org_type" :items="['Юридическое лицо', 'ИП', 'Самозанятый', 'Физическое лицо']"
            label="Тип организации" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="addContractorForm.name" label="Наименование организации *" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Обязательное поле']" />
          <v-row dense>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.inn" label="ИНН" variant="outlined" density="compact" hide-details
                @update:model-value="onAddContractorInnChange">
                <template #append-inner>
                  <v-btn icon="mdi-database-search" size="x-small" variant="text" color="blue" :disabled="!addContractorForm.inn || addContractorForm.inn.length < 10" @click="lookupContractorInn" title="Заполнить из ЕГРЮЛ (nalog.ru)" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.kpp" label="КПП" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-textarea v-model="addContractorForm.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
          <div class="text-caption text-medium-emphasis mt-4 mb-1">Подписант</div>
          <v-text-field v-model="addContractorForm.signatory_position" label="Должность подписанта" variant="outlined" density="compact" class="mb-2" hide-details />
          <v-row dense class="mb-3">
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="addContractorForm.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis mt-3 mb-1">Контакты</div>
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-text-field v-model="addContractorForm.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mt-3" hide-details />
          <div class="text-caption text-medium-emphasis mt-4 mb-1">Банковские реквизиты</div>
          <v-text-field v-model="addContractorForm.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-text-field v-model="addContractorForm.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details />
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.bik" label="БИК" variant="outlined" density="compact" hide-details />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="addContractorForm.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addContractorDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="addContractorSaving" :disabled="!addContractorForm.name.trim()" @click="saveNewContractor">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ЕГРЮЛ diff dialog -->
    <v-dialog v-model="egrulDiffDialog" max-width="640" persistent :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
          Данные из ЕГРЮЛ отличаются
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <p class="text-body-2 text-medium-emphasis mb-3">
            По каждому полю выберите — обновить значение или оставить текущее.
          </p>
          <v-table density="compact">
            <thead>
              <tr><th>Поле</th><th>Сейчас</th><th>Из ЕГРЮЛ</th><th style="width:90px">Обновить</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in egrulDiffItems" :key="d.key">
                <td class="text-caption font-weight-medium">{{ d.label }}</td>
                <td class="text-caption text-medium-emphasis" style="max-width:200px;word-break:break-word">{{ d.old }}</td>
                <td class="text-caption" style="color:#4caf50;max-width:200px;word-break:break-word">{{ d.new }}</td>
                <td>
                  <v-checkbox
                    :model-value="egrulDiffPending[d.key] !== undefined"
                    density="compact" hide-details
                    @update:model-value="(v) => v ? (egrulDiffPending[d.key] = d.new) : (delete egrulDiffPending[d.key])"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="egrulDiffDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" @click="applyEgrulDiff" :disabled="Object.keys(egrulDiffPending).length === 0">
            Применить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Framework contracts dialog -->
    <v-dialog v-model="frameworkDialog" max-width="860" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center justify-space-between">
          <span>Рамочные договоры</span>
          <v-btn color="primary" prepend-icon="mdi-plus" size="small"
            @click="newFrameworkDialog = true">
            Создать новый
          </v-btn>
        </v-card-title>
        <v-card-text class="px-6">
          <v-text-field v-model="frameworkSearch" prepend-inner-icon="mdi-magnify"
            label="Поиск по номеру, контрагенту, ИНН, предмету"
            variant="outlined" density="compact" clearable hide-details class="mb-4" />
          <v-progress-linear v-if="frameworkLoading" indeterminate color="primary" class="mb-3" />
          <div v-if="!frameworkLoading && !filteredFrameworkContracts.length" class="text-center text-medium-emphasis py-6">
            Рамочных договоров по данной субсидии не найдено
          </div>
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Номер</th>
                <th>Дата</th>
                <th>Контрагент</th>
                <th>ИНН</th>
                <th>Предмет договора</th>
                <th>Макс. сумма</th>
                <th>Остаток</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in filteredFrameworkContracts" :key="c.id"
                :class="{ 'bg-blue-lighten-5': selectedFrameworkContract?.id === c.id }"
                style="cursor:pointer" @click="selectFrameworkContract(c)">
                <td class="font-weight-medium">{{ c.number }}</td>
                <td>{{ c.date || '—' }}</td>
                <td>{{ c.contractor_name || '—' }}</td>
                <td class="text-caption">{{ c.contractor_inn || '—' }}</td>
                <td style="max-width:220px;white-space:normal;font-size:12px">{{ c.subject || '—' }}</td>
                <td class="text-right">{{ c.max_amount ? Number(c.max_amount).toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
                <td class="text-right" :class="c.remaining_ordered != null && c.remaining_ordered < 0 ? 'text-error' : 'text-success'">
                  {{ c.remaining_ordered != null ? Number(c.remaining_ordered).toLocaleString('ru-RU') + ' ₽' : '—' }}
                </td>
                <td>
                  <v-btn variant="tonal" color="primary" size="x-small"
                    @click.stop="selectFrameworkContract(c)">Выбрать</v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="frameworkDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- КП dialog -->
    <v-dialog v-model="kpDialog" max-width="780" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon color="cyan-darken-2">mdi-email-multiple-outline</v-icon>
          Запрос коммерческих предложений
          <v-progress-circular v-if="kpItemsLoading" size="18" indeterminate color="cyan-darken-2" class="ml-2" />
        </v-card-title>
        <v-card-text class="px-6 pb-2">

          <!-- Intro text + delivery date -->
          <v-row dense class="mb-1">
            <v-col cols="8">
              <div class="text-subtitle-2 mb-1">Вводный текст письма</div>
              <v-textarea
                v-model="kpIntroText"
                variant="outlined" density="compact" rows="3" auto-grow hide-details
                placeholder="Уважаемые коллеги, просим предоставить коммерческое предложение..."
              />
            </v-col>
            <v-col cols="4">
              <div class="text-subtitle-2 mb-1">Срок поставки</div>
              <v-text-field
                v-model="kpDeliveryDate"
                variant="outlined" density="compact" hide-details
                placeholder="до 31.12.2026"
              />
            </v-col>
          </v-row>

          <!-- Contractor selector -->
          <div class="text-subtitle-2 mb-1 mt-3">Получатели</div>
          <div class="d-flex align-center gap-2 mb-2">
            <v-autocomplete
              v-model="kpSelected"
              :items="kpContractorOptions"
              item-title="label"
              item-value="id"
              label="Найти контрагента"
              variant="outlined" density="compact"
              multiple hide-selected hide-details
              class="flex-grow-1"
              no-data-text="Не найдено"
            />
          </div>

          <!-- Selected contractors list -->
          <div v-if="kpSelected.length" class="mb-3">
            <div
              v-for="cid in kpSelected" :key="cid"
              class="d-flex align-center gap-2 pa-2 rounded mb-1"
              style="border: 1px solid rgba(0,0,0,0.12);"
            >
              <v-icon icon="mdi-domain" size="small" color="cyan-darken-2" />
              <span class="text-body-2 font-weight-medium" style="min-width:140px">
                {{ kpContractorList.find(c=>c.id===cid)?.name }}
              </span>

              <template v-if="kpEditEmailId !== cid">
                <span v-if="kpContractorList.find(c=>c.id===cid)?.email" class="text-body-2 text-medium-emphasis flex-grow-1">
                  {{ kpContractorList.find(c=>c.id===cid)?.email }}
                </span>
                <v-chip v-else color="warning" size="x-small" variant="tonal" class="flex-grow-1">
                  <v-icon start icon="mdi-alert-circle-outline" />
                  нет email
                </v-chip>
                <v-btn
                  :icon="kpContractorList.find(c=>c.id===cid)?.email ? 'mdi-pencil-outline' : 'mdi-email-plus-outline'"
                  size="x-small" variant="text"
                  :color="kpContractorList.find(c=>c.id===cid)?.email ? 'grey' : 'warning'"
                  title="Добавить/изменить email контрагента"
                  @click="kpStartEditEmail(cid)"
                />
              </template>
              <template v-else>
                <v-text-field
                  v-model="kpEditEmailValue"
                  label="Email"
                  type="email"
                  variant="outlined" density="compact" hide-details
                  class="flex-grow-1"
                  autofocus
                  @keyup.enter="kpSaveEmail(cid)"
                  @keyup.esc="kpEditEmailId = null"
                />
                <v-btn icon="mdi-check" size="x-small" variant="tonal" color="success"
                  :loading="kpSavingEmail" @click="kpSaveEmail(cid)" />
                <v-btn icon="mdi-close" size="x-small" variant="text" @click="kpEditEmailId = null" />
              </template>

              <v-btn
                icon="mdi-close" size="x-small" variant="text" color="error"
                title="Убрать из списка"
                @click="kpSelected = kpSelected.filter(id => id !== cid)"
              />
            </div>
          </div>

          <!-- Free email recipients -->
          <div v-if="kpFreeRecipients.length" class="mb-2">
            <div v-for="(fr, i) in kpFreeRecipients" :key="i"
              class="d-flex align-center gap-2 pa-2 rounded mb-1"
              style="border: 1px solid rgba(0,0,0,0.12);"
            >
              <v-icon icon="mdi-email-outline" size="small" color="cyan-darken-2" />
              <v-text-field
                v-model="fr.name"
                label="Название / имя"
                variant="outlined" density="compact" hide-details
                style="max-width:170px"
              />
              <v-text-field
                v-model="fr.email"
                label="Email *"
                type="email"
                variant="outlined" density="compact" hide-details
                class="flex-grow-1"
              />
              <v-btn
                icon="mdi-email-outline" size="x-small" variant="tonal" color="cyan-darken-2"
                :disabled="!fr.email"
                title="Открыть в почтовом клиенте"
                @click="openMailtoFree(fr)"
              />
              <v-btn
                icon="mdi-content-copy" size="x-small" variant="text"
                title="Скопировать текст письма"
                @click="copyFreeEmail(fr)"
              />
              <v-btn icon="mdi-close" size="x-small" variant="text" color="error"
                @click="kpFreeRecipients.splice(i, 1)" />
            </div>
          </div>
          <v-btn
            prepend-icon="mdi-email-plus-outline" size="small" variant="text" color="cyan-darken-2"
            class="mb-3"
            @click="kpFreeRecipients.push({ name: '', email: '' })"
          >
            Добавить email вручную
          </v-btn>

          <!-- Per-contractor preview -->
          <template v-if="kpSelected.length > 0">
            <v-divider class="mb-3" />
            <div class="text-subtitle-2 mb-2">Индивидуальные запросы ({{ kpSelected.length }} конт.):</div>
            <v-expansion-panels variant="accordion" class="mb-2">
              <v-expansion-panel
                v-for="cid in kpSelected"
                :key="cid"
              >
                <v-expansion-panel-title>
                  <div class="d-flex align-center gap-2 w-100">
                    <v-icon size="16" :color="kpContractorList.find(c=>c.id===cid)?.email ? 'success' : 'warning'">
                      {{ kpContractorList.find(c=>c.id===cid)?.email ? 'mdi-email-check' : 'mdi-email-off' }}
                    </v-icon>
                    <span class="font-weight-medium">{{ kpContractorList.find(c=>c.id===cid)?.name }}</span>
                    <v-chip size="x-small" color="teal" variant="tonal" class="ml-1">
                      {{ kpItemsForContractor(cid).length }} тов.
                    </v-chip>
                    <v-chip
                      v-for="cat in kpContractorList.find(c=>c.id===cid)?.product_categories?.slice(0,2) ?? []"
                      :key="cat" size="x-small" color="grey" variant="tonal" class="ml-1"
                    >{{ cat }}</v-chip>
                    <v-spacer />
                    <v-btn
                      size="x-small" color="cyan-darken-2" variant="tonal"
                      prepend-icon="mdi-email-outline"
                      :disabled="!kpContractorList.find(c=>c.id===cid)?.email"
                      @click.stop="openMailtoForContractor(cid)"
                    >В почту</v-btn>
                    <v-btn size="x-small" variant="text" class="ml-1" @click.stop="copyContractorEmail(cid)">
                      Копировать
                    </v-btn>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <div v-if="kpItemsForContractor(cid).length === 0" class="text-caption text-medium-emphasis py-2">
                    Нет товаров с подходящими категориями — будут отправлены все позиции
                  </div>
                  <v-table v-else density="compact">
                    <thead>
                      <tr>
                        <th>Наименование</th>
                        <th>Категория</th>
                        <th class="text-right">Кол-во</th>
                        <th class="text-right">Ед.</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in kpItemsForContractor(cid)" :key="item.id">
                        <td class="text-sm">{{ item.item_name }}</td>
                        <td><v-chip size="x-small" color="teal" variant="tonal">{{ item.category || '—' }}</v-chip></td>
                        <td class="text-right text-sm">{{ item.quantity }}</td>
                        <td class="text-right text-caption">{{ item.unit }}</td>
                      </tr>
                    </tbody>
                  </v-table>
                  <!-- Email preview -->
                  <v-textarea
                    :model-value="buildContractorEmail(cid)"
                    variant="outlined" density="compact" rows="6" readonly
                    class="mt-3" hide-details
                    label="Предпросмотр письма"
                  />
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4 gap-2">
          <v-btn variant="text" @click="kpDialog = false">Закрыть</v-btn>
          <v-spacer />
          <v-btn
            variant="outlined"
            prepend-icon="mdi-file-excel-outline"
            color="green-darken-1"
            size="small"
            :disabled="!purchaseId"
            @click="downloadKpXlsx"
          >
            Скачать xlsx
          </v-btn>
          <v-btn
            color="teal" variant="flat"
            prepend-icon="mdi-send-outline"
            :loading="kpSendingAll"
            :disabled="kpAllEmails.length === 0"
            @click="sendAllKpViaApi"
          >
            Отправить письма ({{ kpAllEmails.length }})
          </v-btn>
          <v-btn
            variant="text" size="small"
            prepend-icon="mdi-email-multiple-outline"
            :disabled="kpAllEmails.length === 0"
            @click="sendAllKp"
          >
            Открыть в почтовом клиенте
          </v-btn>
          <v-btn
            color="primary" variant="flat"
            prepend-icon="mdi-content-save-outline"
            :loading="kpSaving"
            :disabled="kpAllEmails.length === 0"
            @click="saveKpRequest"
          >
            Сохранить запрос
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- New framework contract dialog -->
    <v-dialog v-model="newFrameworkDialog" max-width="520" @after-enter="focusNewContractNumber" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Новый рамочный договор</v-card-title>
        <v-card-text class="px-6 pb-2">
          <v-text-field ref="newContractNumberRef" v-model="newFrameworkForm.number" label="Номер договора *" variant="outlined"
            density="compact" class="mb-3" />
          <v-text-field v-model="newFrameworkForm.date" label="Дата договора" variant="outlined"
            density="compact" type="date" class="mb-3" />
          <v-autocomplete v-model="newFrameworkForm.contractor_id"
            :items="contractors" item-title="name" item-value="id"
            label="Контрагент" variant="outlined" density="compact" clearable
            :custom-filter="contractorFilter" :no-data-text="contractorsNoDataText" class="mb-3">
            <template #item="{ item, props }">
              <v-list-item v-bind="props">
                <template #subtitle>
                  <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
          <v-textarea v-model="newFrameworkForm.subject" label="Предмет договора" variant="outlined"
            density="compact" rows="2" auto-grow class="mb-3" />
          <v-text-field v-model.number="newFrameworkForm.max_amount" label="Максимальная сумма, ₽"
            variant="outlined" density="compact" type="number" />
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="newFrameworkDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="newFrameworkSaving" @click="saveNewFrameworkContract">Создать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Approver Picker Dialog ── -->
    <v-dialog v-model="docPickerDialog" max-width="560" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-account-check-outline" color="teal" class="mr-2" />
          {{ docPickerType.startsWith('service_note') ? 'Служебная записка — выбор инициатора' : 'Лист согласования — выбор согласующих' }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="docPickerDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <div v-if="loadingDocApprovers" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate color="teal" />
          </div>
          <div v-else-if="!docApprovers.length" class="text-center text-medium-emphasis py-4">
            Для этой субсидии не настроены согласующие.<br>
            Откройте страницу Субсидии → кнопка «Согласующие».
          </div>
          <!-- service_note: autocomplete только из подчинённых + сам пользователь
               (бизнес-правило: за другого может делать только его руководитель) -->
          <div v-else-if="docPickerType.startsWith('service_note')" class="mt-1">
            <v-autocomplete
              v-model="pickerInitiatorId"
              :items="actAsList"
              item-title="full_name"
              item-value="id"
              label="Специалист (инициатор)"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              :hint="'Доступны: вы и сотрудники, кому вы можете ставить задачи'"
              persistent-hint
              :no-data-text="loadingDocApprovers ? 'Загрузка...' : 'Нет сотрудников'"
            >
              <template #item="{ item, props }">
                <v-list-item v-bind="props">
                  <template #subtitle>
                    <span v-if="item.raw.position" class="text-caption text-medium-emphasis">{{ item.raw.position }}</span>
                  </template>
                </v-list-item>
              </template>
            </v-autocomplete>
          </div>
          <!-- approval_sheet: responsible person + checkboxes -->
          <div v-else>
            <!-- Ответственный исполнитель -->
            <div class="d-flex align-start gap-2 mb-4">
              <v-autocomplete
                v-model="pickerResponsibleName"
                :items="responsibleOptions"
                item-title="display"
                item-value="full_name"
                label="Ответственный исполнитель"
                variant="outlined"
                density="compact"
                clearable
                class="flex-grow-1"
                :return-object="false"
                autocomplete="off"
                hint="По умолчанию — ответственный исполнитель этой закупки. Можно выбрать другого сотрудника или запись справочника."
                persistent-hint
              />
              <v-tooltip text="Добавить в справочник" location="top">
                <template #activator="{ props: tip }">
                  <v-btn v-bind="tip" icon="mdi-account-plus-outline" size="small"
                    variant="tonal" color="teal" class="mt-1" @click="addResponsibleDialog = true" />
                </template>
              </v-tooltip>
            </div>
            <v-divider class="mb-3" />
            <div class="text-body-2 font-weight-medium mb-2">Согласующие</div>
            <v-checkbox
              v-for="a in docApprovers"
              :key="a.id"
              v-model="pickerApproverIds"
              :value="a.id"
              :label="`${a.order_num}. ${a.role_name} — ${a.full_name}`"
              density="compact"
              hide-details
            />
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="docPickerDialog = false">Отмена</v-btn>
          <v-btn
            color="teal"
            variant="tonal"
            prepend-icon="mdi-download"
            :loading="docLoading === docPickerType"
            :disabled="docPickerType.startsWith('service_note') ? !pickerInitiatorId : !pickerApproverIds.length"
            @click="confirmDocDownload"
          >
            Скачать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Phase 27.2-02: Диалог выбора закрывающих документов перед скачиванием СЗ -->
    <v-dialog v-model="acceptanceDocPickerDialog" max-width="520" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-file-check-outline" color="teal" class="mr-2" />
          Выберите закрывающие документы
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="acceptanceDocPickerDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Отметьте документы, по которым формируется служебная записка на оплату.
            Сумма будет сложена автоматически.
          </p>
          <v-list density="compact">
            <v-list-item v-for="(doc, idx) in acceptanceDocs" :key="idx">
              <template #prepend>
                <v-checkbox-btn v-model="acceptanceDocPickerSelected" :value="idx" />
              </template>
              <v-list-item-title class="text-body-2">
                {{ doc.name }} {{ doc.number }} от {{ doc.date || '—' }}
              </v-list-item-title>
              <v-list-item-subtitle v-if="doc.amount != null">
                {{ Number(doc.amount).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="acceptanceDocPickerDialog = false">Отмена</v-btn>
          <v-btn
            color="teal"
            variant="tonal"
            prepend-icon="mdi-download"
            :disabled="!acceptanceDocPickerSelected.length"
            @click="confirmAcceptanceDocDownload"
          >
            Скачать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог добавления ответственного исполнителя -->
    <v-dialog v-model="addResponsibleDialog" max-width="400" :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-subtitle-1 pt-4 px-4">Добавить в справочник</v-card-title>
        <v-card-text class="pb-0">
          <v-text-field v-model="newResponsibleName" label="ФИО *" variant="outlined"
            density="compact" class="mb-2" autofocus />
          <v-text-field v-model="newResponsiblePosition" label="Должность (необязательно)"
            variant="outlined" density="compact" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addResponsibleDialog = false">Отмена</v-btn>
          <v-btn color="teal" variant="tonal" :loading="savingResponsible"
            :disabled="!newResponsibleName.trim()" @click="saveNewResponsible">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Phase 21: Manual receipt dialog -->
    <v-dialog v-model="manualReceiptDialog.show" max-width="700" :fullscreen="mobile">
      <v-card>
        <v-card-title>Чек — ручной ввод</v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="manualReceiptDialog.form.fiscal_drive_number"
                label="ФН (fiscal_drive_number)" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="manualReceiptDialog.form.fiscal_document_number"
                label="ФД" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="manualReceiptDialog.form.fiscal_sign"
                label="ФП" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="manualReceiptDialog.form.receipt_datetime"
                label="Дата/время" type="datetime-local" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="manualReceiptDialog.form.total_sum"
                label="Сумма, ₽" type="number" variant="outlined" density="compact" suffix="₽" />
            </v-col>
            <v-col cols="12" md="8">
              <v-text-field v-model="manualReceiptDialog.form.seller_name"
                label="Продавец" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="manualReceiptDialog.form.seller_inn"
                label="ИНН продавца" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-text-field v-model="manualReceiptDialog.form.retail_place"
                label="Место расчётов" variant="outlined" density="compact" />
            </v-col>
          </v-row>
          <div v-if="manualReceiptDialog.error" class="text-error text-caption mt-2">
            {{ manualReceiptDialog.error }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="manualReceiptDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="manualReceiptDialog.saving"
            @click="saveManualReceipt">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <QrScannerDialog v-model="qrScanShow" @detected="onQrDetected" />

    <!-- Phase 23: диалог «Доступные переменные шаблонов» -->
    <v-dialog v-model="showPlaceholdersDialog" max-width="960" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-code-braces" class="mr-2" />Доступные переменные шаблонов
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showPlaceholdersDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height:70vh">
          <div v-for="grp in placeholderGroups" :key="grp.title" class="mb-5">
            <div class="text-subtitle-2 font-weight-bold mb-2" style="color:#6200ea">{{ grp.title }}</div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="width:260px">Переменная</th>
                  <th>Описание</th>
                  <th style="width:200px">Пример</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in grp.items" :key="item.var">
                  <td><code style="font-size:11px">{{ formatPlaceholder(item.var) }}</code></td>
                  <td class="text-body-2">{{ item.desc }}</td>
                  <td class="text-caption text-medium-emphasis">{{ item.ex }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
          <v-alert type="info" variant="tonal" density="compact" class="mt-3">
            Полный справочник с примерами и условными блоками: <code>backend/templates/PLACEHOLDERS.md</code>
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn @click="showPlaceholdersDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Phase 23.2: диалог ошибки генерации документа -->
    <v-dialog v-model="docErrorDialog" max-width="640">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 bg-error-lighten-5">
          <v-icon icon="mdi-alert-circle" color="error" class="mr-2" />
          <span class="text-error">Ошибка генерации документа</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="docErrorDialog = false" />
        </v-card-title>
        <v-card-text class="pt-4" v-if="docErrorInfo">
          <div class="text-body-1 font-weight-medium mb-2">{{ docErrorInfo.message }}</div>
          <div v-if="docErrorInfo.template" class="text-caption text-medium-emphasis mb-3">
            <v-icon size="14" class="mr-1">mdi-file-document-outline</v-icon>
            {{ docErrorInfo.template_source }}: <code>{{ docErrorInfo.template }}</code>
          </div>
          <div class="text-caption text-medium-emphasis mb-3">
            <span v-if="docErrorInfo.code">Код: <code>{{ docErrorInfo.code }}</code></span>
            <span v-if="docErrorInfo.code && docErrorInfo.correlation_id"> · </span>
            <span v-if="docErrorInfo.correlation_id">ID: <code>{{ docErrorInfo.correlation_id }}</code></span>
          </div>
          <v-alert v-if="docErrorInfo.hint" type="info" variant="tonal" density="compact" class="mb-3">
            <div class="text-body-2" style="white-space: pre-line">{{ docErrorInfo.hint }}</div>
          </v-alert>
          <v-expansion-panels v-if="docErrorInfo.error_raw || docErrorInfo.error_class" variant="accordion" :model-value="[]" class="mt-2">
            <v-expansion-panel>
              <v-expansion-panel-title class="text-caption">
                Технические детали ({{ docErrorInfo.error_class }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <pre class="text-caption" style="white-space: pre-wrap; max-height: 200px; overflow: auto">{{ docErrorInfo.error_raw }}</pre>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>
        <v-card-actions class="pa-4 flex-wrap">
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-content-copy"
            @click="copyDocError">
            Скопировать ошибку
          </v-btn>
          <v-btn variant="text" prepend-icon="mdi-file-document-edit-outline"
            :href="form.subsidy_id ? `/subsidies?openTemplates=${form.subsidy_id}` : '/subsidies'"
            target="_self" @click="docErrorDialog = false"
            v-if="docErrorInfo?.template_source?.includes('субсидии') || docErrorInfo?.code === 'TEMPLATE_RENDER_ERROR'">
            Редактор шаблонов субсидии
          </v-btn>
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-format-list-bulleted"
            @click="docErrorDialog = false; revealField('items')"
            v-if="docErrorInfo?.code === 'CONTRACT_ITEMS_REQUIRED'">
            Показать позиции
          </v-btn>
          <v-spacer />
          <v-btn @click="docErrorDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
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
import { useContractorsStore } from '@/stores/contractors'
import { useToast, type ToastType } from '@/composables/useToast'
import { listContractItems, replaceAllContractItems } from '@/api/contractItems'
import type { ContractItem } from '@/types/contractItem'
import { useOrgConfig } from '@/composables/useOrgConfig'
import PurchaseEventFeed from '@/components/PurchaseEventFeed.vue'
import ApprovalPanel from '@/components/purchase/ApprovalPanel.vue'
import FileDropZone from '@/components/FileDropZone.vue'
import ChatEmbed from '@/components/ChatEmbed.vue'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import PurchaseSplitKanban from '@/components/PurchaseSplitKanban.vue'
import QrScannerDialog from '@/components/QrScannerDialog.vue'
import ValidationArrows from '@/components/ValidationArrows.vue'
import MonthlyStagesDialog from '@/components/MonthlyStagesDialog.vue'
import PaymentsBlock from '@/components/PaymentsBlock.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { useFeoTreeNodes } from '@/composables/useFeoTreeNodes'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import { decodeQrFromImageFile } from '@/utils/qrDecode'
import { numOrNull, numOrNullZeroEmpty } from '@/utils/numberFormat'
import { PURCHASE_STATUS_ORDER, purchaseStatusColor } from '@/constants/purchaseStatus'

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
import { useDisplay } from 'vuetify'
import { useEntityChanges } from '@/composables/useEntityChanges'
import { useUndoRedo } from '@/composables/useUndoRedo'

const { mobile } = useDisplay()

const route = useRoute()
const router = useRouter()

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

// НМЦД mode: auto (from items) or manual (user enters directly)
const nmckMode = ref<'auto' | 'manual'>('auto')
const nmckManualValue = ref<number | null>(null)
// Цена договора mode
const contractPriceMode = ref<'auto' | 'manual'>('auto')

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
// Подписи здесь намеренно длиннее/другие по смыслу, чем в общем словаре
// (заголовок формы закупки: «Желания сотрудников», «Заключён договор/заказ») — оставлены как есть.
const STATUS_LABEL_BASE: Record<string, string> = {
  wishes: 'Желания сотрудников', plan_schedule: 'План закупок',
  work_in_progress: 'Ведётся работа',
  contracted: 'Заключён договор', ordered: 'Заказано', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_LABEL = computed<Record<string, string>>(() => ({
  ...STATUS_LABEL_BASE,
  contracted: isFramework.value ? 'Заключён заказ' : 'Заключён договор',
}))
// Единый источник цвета статуса закупки: frontend/src/constants/purchaseStatus.ts
const STATUS_COLOR: Record<string, string> = Object.fromEntries(
  PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusColor(s)])
)
const SUBSTATUS_OPTIONS = [
  { value: 'tz_forming', title: 'Формирование ТЗ' },
  { value: 'kp_collecting', title: 'Сбор КП' },
  { value: 'on_platform', title: 'На площадке' },
  { value: 'contractor_negotiations', title: 'Переговоры с подрядчиком' },
  { value: 'contract_signing', title: 'Договор на подписании' },
]
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
interface UploadedFile { id: number; purchase_id: number; filename: string; mime_type?: string; size?: number; file_type?: string; doc_format?: string; is_active?: boolean; uploaded_by_name?: string | null; created_at?: string | null }

const FILE_TYPE_LABELS_BASE: Record<string, string> = {
  kp:                         'КП',
  service_note:               'Служебная записка',
  protocol:                   'Протокол закупки',
  invoice:                    'Счёт',
  order:                      'Приказ',
  upd:                        'УПД',
  contract:                   'Договор',
  act:                        'Закрывающий документ',
  other:                      'Прочее',
  fabrikant_instruction:      'Фабрикант: Инструкция',
  fabrikant_application_form: 'Фабрикант: Форма заявки',
  fabrikant_documentation:    'Фабрикант: Документация',
  fabrikant_contract_project: 'Фабрикант: Проект договора',
  fabrikant_tech_spec:        'Фабрикант: ТЗ',
}

const FABRIKANT_PKG_DOCS = [
  { ft: 'fabrikant_instruction',      label: 'Инструкция' },
  { ft: 'fabrikant_application_form', label: 'Форма заявки' },
  { ft: 'fabrikant_documentation',    label: 'Документация' },
  { ft: 'fabrikant_contract_project', label: 'Проект договора' },
  { ft: 'fabrikant_tech_spec',        label: 'ТЗ' },
] as const
const FILE_TYPE_LABELS = computed<Record<string, string>>(() => ({
  ...FILE_TYPE_LABELS_BASE,
  contract: contractWord.value,
}))
const FILE_TYPE_OPTIONS = computed(() => Object.entries(FILE_TYPE_LABELS.value).map(([value, title]) => ({ value, title })))

function fileTypeColor(t?: string): string {
  const map: Record<string, string> = {
    kp: 'teal', service_note: 'blue', protocol: 'deep-purple',
    invoice: 'orange', order: 'brown', upd: 'green',
    contract: 'indigo', act: 'cyan', other: 'grey',
  }
  return map[t || 'other'] || 'grey'
}

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
    // автосохранение валило 422 прямо на blur. numOrNull — единый хелпер (2026-09-04);
    // деньги/суммы (contract_price/nmck/planned_total_price/payment_amount) переведены
    // на numOrNullZeroEmpty — там 0 бессмыслен (владелец, 2026-09-04, «0 тоже значит,
    // что ничего нет»); сроки в днях и ставка НДС ниже остаются numOrNull — там 0 реален.
    contract_price: numOrNullZeroEmpty(f.contract_price),
    nmck: numOrNullZeroEmpty(f.nmck),
    planned_total_price: numOrNullZeroEmpty(f.planned_total_price),
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
    payment_amount: numOrNullZeroEmpty(f.payment_amount),
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
// Vue parser ломается на inline-выражении { '{{' + x + '}}' } (видит '}}' как конец интерполяции),
// поэтому формирование плейсхолдер-строки вынесено в функцию.
function formatPlaceholder(name: string): string {
  return '{' + '{' + name + '}' + '}'
}
const placeholderGroups = [
  {
    title: '🎯 Универсальный договор (auto-switch)',
    items: [
      { var: 'subject_kind', desc: 'Тип договора: services (если все позиции услуги) | goods (если есть товары или нет позиций)', ex: 'goods' },
      { var: '{% if subject_kind == \'goods\' %}', desc: 'Условный блок для договора поставки (Покупатель/Поставщик, Спецификация)', ex: 'Покупатель/Поставщик/Спецификация' },
      { var: '{% else %}', desc: 'Альтернативная ветка — договор услуг (Заказчик/Исполнитель, ТЗ)', ex: 'Заказчик/Исполнитель/ТЗ' },
    ],
  },
  {
    title: '📑 Договор (общее)',
    items: [
      { var: 'contract_number', desc: 'Номер договора', ex: '2026/15' },
      { var: 'contract_date', desc: 'Дата договора', ex: '28.04.2026' },
      { var: 'contract_date_day', desc: 'День', ex: '28' },
      { var: 'contract_date_month', desc: 'Месяц прописью', ex: 'апреля' },
      { var: 'contract_date_year', desc: 'Год', ex: '2026' },
      { var: 'contract_city', desc: 'Город заключения', ex: 'Москва' },
      { var: 'contract_price_num', desc: 'Цена (без символа ₽)', ex: '130 000,00' },
      { var: 'contract_price_words', desc: 'Цена прописью', ex: 'сто тридцать тысяч рублей 00 копеек' },
    ],
  },
  {
    title: '🏛 Заказчик (customer_*) — Phase 23',
    items: [
      { var: 'customer_full_name', desc: 'Полное наименование организации', ex: 'АНО «ВСКС»' },
      { var: 'customer_short_name', desc: 'Краткое (из кавычек)', ex: 'ВСКС' },
      { var: 'customer_inn', desc: 'ИНН', ex: '7700000001' },
      { var: 'customer_kpp', desc: 'КПП', ex: '770001001' },
      { var: 'customer_ogrn', desc: 'ОГРН', ex: '1027700000001' },
      { var: 'customer_address', desc: 'Юридический адрес', ex: 'г. Москва, ул. Ленина, д. 1' },
      { var: 'customer_bank_name', desc: 'Банк', ex: 'ПАО Сбербанк' },
      { var: 'customer_bik', desc: 'БИК', ex: '044525225' },
      { var: 'customer_settlement_account', desc: 'Расчётный счёт', ex: '40701810...' },
      { var: 'customer_correspondent_account', desc: 'Корр. счёт', ex: '30101810...' },
      { var: 'customer_signatory_position', desc: 'Должность подписанта', ex: 'Президент' },
      { var: 'customer_signatory_name_genitive', desc: 'ФИО в родительном падеже', ex: 'Козеева Евгения Викторовича' },
      { var: 'customer_signatory_initials', desc: 'Фамилия + инициалы', ex: 'Козеев Е.В.' },
      { var: 'customer_signatory_basis', desc: 'Основание полномочий', ex: 'Устава' },
    ],
  },
  {
    title: '🏢 Исполнитель (contractor_*)',
    items: [
      { var: 'contractor_full_name', desc: 'Полное наименование', ex: 'ООО «Ромашка»' },
      { var: 'contractor_short_name', desc: 'Краткое', ex: 'Ромашка' },
      { var: 'contractor_org_type', desc: 'Тип организации', ex: 'Юр.лицо / ИП' },
      { var: 'contractor_inn', desc: 'ИНН', ex: '7700000002' },
      { var: 'contractor_ogrn', desc: 'ОГРН', ex: '1027700000002' },
      { var: 'contractor_ogrnip', desc: 'ОГРНИП (только для ИП)', ex: '304770000000001' },
      { var: 'contractor_address', desc: 'Адрес', ex: 'г. Москва, ул. Садовая, д. 5' },
      { var: 'contractor_signatory_position', desc: 'Должность', ex: 'Директор' },
      { var: 'contractor_signatory_name_genitive', desc: 'ФИО в родительном', ex: 'Сидорова Петра Павловича' },
      { var: 'contractor_signatory_initials', desc: 'Инициалы', ex: 'Сидоров П.П.' },
      { var: 'contractor_bank_name', desc: 'Банк', ex: 'ПАО Сбербанк' },
      { var: 'contractor_settlement_account', desc: 'р/с', ex: '40702810...' },
      { var: 'contractor_bik', desc: 'БИК', ex: '044525225' },
    ],
  },
  {
    title: '💰 Цена и НДС',
    items: [
      { var: 'vat_applicable', desc: 'НДС применяется?', ex: 'true / false' },
      { var: 'vat_rate', desc: 'Ставка НДС, %', ex: '20' },
      { var: 'vat_amount_num', desc: 'Сумма НДС цифрами', ex: '21 666,67' },
      { var: 'vat_amount_words', desc: 'Сумма НДС прописью', ex: 'двадцать одна тысяча...' },
      { var: 'vat_exemption_article', desc: 'Статья освобождения', ex: 'п.2 ст.346.11 НК РФ' },
      { var: 'vat_info_line', desc: 'Готовая строка НДС', ex: 'В том числе НДС 20%: ...' },
    ],
  },
  {
    title: '📅 Сроки',
    items: [
      { var: 'service_term', desc: 'Готовая строка срока', ex: 'с 01.05.2026 по 31.05.2026' },
      { var: 'service_term_mode', desc: 'Режим', ex: 'range / duration / deadline' },
      { var: 'service_start_date', desc: 'Начало', ex: '01.05.2026' },
      { var: 'service_end_date', desc: 'Окончание', ex: '31.05.2026' },
      { var: 'service_deadline_date', desc: 'Крайняя дата', ex: '30.06.2026' },
      { var: 'service_term_days', desc: 'Количество дней', ex: '30' },
      { var: 'submission_deadline_datetime', desc: 'Дата+время завершения приёма заявок', ex: '25.04.2026 18:00' },
      { var: 'delivery_location', desc: 'Место оказания услуг', ex: 'г. Москва, ул. Ленина, д. 1' },
    ],
  },
  {
    title: '✅ Условия',
    items: [
      { var: 'third_party_involved', desc: 'Привлечение третьих лиц', ex: 'true / false' },
      { var: 'subsidy_agreement_text', desc: 'Текст соглашения Минтруда', ex: 'Соглашения № 149-2023...' },
      { var: 'service_subject', desc: 'Предмет услуг (синоним subject)', ex: 'оказание полиграфических услуг' },
    ],
  },
  {
    title: '📦 Позиции (таблица)',
    items: [
      { var: 'item.num', desc: 'Номер строки', ex: '1' },
      { var: 'item.name', desc: 'Наименование', ex: 'Ежедневник А5' },
      { var: 'item.quantity', desc: 'Количество', ex: '50' },
      { var: 'item.unit', desc: 'Единица измерения', ex: 'шт.' },
      { var: 'item.unit_price', desc: 'Цена за единицу', ex: '500,00 ₽' },
      { var: 'item.total_price', desc: 'Сумма строки', ex: '25 000,00 ₽' },
      { var: 'items_count', desc: 'Общее количество позиций', ex: '3' },
    ],
  },
  {
    title: '⚙️ Технические',
    items: [
      { var: 'today', desc: 'Сегодняшняя дата', ex: '04.05.2026' },
      { var: 'today_iso', desc: 'ISO-дата', ex: '2026-05-04' },
      { var: 'purchase_number', desc: 'Номер закупки', ex: '42' },
      { var: 'registry_number', desc: 'Реестровый номер', ex: 'РЕЕ-2026-00042' },
      { var: 'subject', desc: 'Предмет закупки', ex: 'Поставка оборудования' },
      { var: 'subsidy_name', desc: 'Субсидия', ex: 'ФАДМ_2026' },
    ],
  },
]
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

// ── Конец месяца quick-fill ───────────────────────────────────────────────
const endOfMonthMenu = ref(false)
const _now = new Date()
const endOfMonthYear = ref(_now.getFullYear())
const endOfMonthMonth = ref(_now.getMonth() + 1)
const endOfMonthMonthItems = [
  { value: 1, label: 'Январь' },
  { value: 2, label: 'Февраль' },
  { value: 3, label: 'Март' },
  { value: 4, label: 'Апрель' },
  { value: 5, label: 'Май' },
  { value: 6, label: 'Июнь' },
  { value: 7, label: 'Июль' },
  { value: 8, label: 'Август' },
  { value: 9, label: 'Сентябрь' },
  { value: 10, label: 'Октябрь' },
  { value: 11, label: 'Ноябрь' },
  { value: 12, label: 'Декабрь' },
]
function applyEndOfMonth() {
  // endOfMonthYear — v-model.number; при очистке поля Vue кладёт '', что уронило бы
  // service_deadline_date в 'NaN-MM-DD'/'-MM-DD' (Optional[date] на бэке). numOrNull
  // с фолбэком на текущий год — поле год всегда нужно, пустым смысла нет (2026-09-04).
  const year = numOrNull(endOfMonthYear.value) ?? new Date().getFullYear()
  const lastDay = new Date(year, endOfMonthMonth.value, 0).getDate()
  const mm = String(endOfMonthMonth.value).padStart(2, '0')
  const dd = String(lastDay).padStart(2, '0')
  form.service_deadline_date = `${year}-${mm}-${dd}`
  endOfMonthMenu.value = false
}
const transitioning = ref(false)
const converting = ref(false)
const uploading = ref(false)
const docLoading = ref<string | null>(null)

// ── Phase 27.2-02: Acceptance doc picker (select closing docs before СЗ download) ──
const acceptanceDocPickerDialog   = ref(false)
const acceptanceDocPickerDocType  = ref<'service_note_payment' | 'service_note_advance'>('service_note_payment')
const acceptanceDocPickerSelected = ref<number[]>([])
// pending initiator_id to append after acceptance doc selection
const acceptanceDocPickerInitiatorId = ref<number | null>(null)

async function openAcceptanceDocPicker(
  type: 'service_note_payment' | 'service_note_advance',
  initiatorId: number | null,
) {
  if (acceptanceDocs.value.length > 1) {
    acceptanceDocPickerDocType.value = type
    acceptanceDocPickerInitiatorId.value = initiatorId
    // Default: all selected
    acceptanceDocPickerSelected.value = acceptanceDocs.value.map((_, i) => i)
    acceptanceDocPickerDialog.value = true
  } else {
    // Single or zero docs — skip picker, download directly
    const params = initiatorId ? `?initiator_id=${initiatorId}` : ''
    await downloadDoc(type, params)
  }
}

async function confirmAcceptanceDocDownload() {
  acceptanceDocPickerDialog.value = false
  const type = acceptanceDocPickerDocType.value
  const initiatorId = acceptanceDocPickerInitiatorId.value
  const indices = [...acceptanceDocPickerSelected.value].sort((a, b) => a - b)
  const parts: string[] = []
  if (initiatorId) parts.push(`initiator_id=${initiatorId}`)
  if (indices.length && indices.length < acceptanceDocs.value.length) {
    parts.push(`doc_indices=${indices.join(',')}`)
  }
  await downloadDoc(type, parts.length ? `?${parts.join('&')}` : '')
}

// ── Doc picker (approver selection before download) ──
interface DocApprover { id: number; role_name: string; full_name: string; order_num: number; is_default: boolean; can_initiate: boolean }
const docPickerDialog      = ref(false)
const docPickerType        = ref<'service_note_procurement' | 'service_note_delivery' | 'service_note_payment' | 'service_note_advance' | 'approval_sheet'>('approval_sheet')
const loadingDocApprovers  = ref(false)
const docApprovers         = ref<DocApprover[]>([])
const pickerApproverIds    = ref<number[]>([])
const pickerInitiatorId    = ref<number | null>(null)
const docApproversInitiators = computed(() => docApprovers.value.filter(a => a.can_initiate))

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

// Список «за кого можно делать служебку»: сам + подчинённые (видимые через
// _get_visible_user_ids на бэке). Бизнес-правило: за другого человека делать
// СЗ может только его руководитель/тот кому он подчинён.
const actAsList = ref<OrgUser[]>([])
async function loadActAsUsers() {
  try {
    const users = await apiFetch<any[]>('/users/i-can-act-for')
    actAsList.value = users
      .filter(u => u.full_name)
      .map(u => ({ id: u.id, full_name: u.full_name, short_name: toShortName(u.full_name), position: u.position }))
  } catch { actAsList.value = [] }
}

// Кому возмещать — список сотрудников из orgUsersList
const reimbursementUserOptions = computed(() => orgUsersList.value)

// ── Delivery address autocomplete ──
const deliveryAddressSuggestions = ref<string[]>([])
let _deliverySearchTimer: ReturnType<typeof setTimeout> | null = null
async function loadDeliveryAddressHistory() {
  try {
    const orgId = currentSubsidyOrgId.value
    if (!orgId) return
    const results = await apiFetch<{ id: number; address: string }[]>(
      `/delivery-addresses/?org_id=${orgId}&q=`
    )
    const addresses = results.map(r => r.address)
    // Добавим адрес организации первым если его нет в истории
    const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
    if (subsidy?.org_id) {
      try {
        const orgs = await apiFetch<any[]>('/auth/my-orgs')
        const org = orgs.find((o: any) => o.id === subsidy.org_id)
        if (org?.address && !addresses.includes(org.address)) {
          addresses.unshift(org.address)
        }
      } catch { /* silent */ }
    }
    deliveryAddressSuggestions.value = [...new Set(addresses)]
  } catch { deliveryAddressSuggestions.value = [] }
}
async function onDeliveryAddressSearch(q: string) {
  if (!q || q.length < 2) {
    // При пустом поле показать историю
    if (!deliveryAddressSuggestions.value.length) loadDeliveryAddressHistory()
    return
  }
  if (_deliverySearchTimer) clearTimeout(_deliverySearchTimer)
  _deliverySearchTimer = setTimeout(async () => {
    try {
      const orgId = currentSubsidyOrgId.value
      if (!orgId) return
      const results = await apiFetch<{ id: number; address: string }[]>(
        `/delivery-addresses/?org_id=${orgId}&q=${encodeURIComponent(q)}`
      )
      deliveryAddressSuggestions.value = results.map(r => r.address)
    } catch { deliveryAddressSuggestions.value = [] }
  }, 300)
}
async function onDeliveryAddressSelect(val: string | null) {
  // val is already a string (full_name), just set it
  if (val) form.delivery_address = val
}
async function saveDeliveryAddressIfNew(address: string) {
  if (!address?.trim()) return
  try {
    const orgId = currentSubsidyOrgId.value
    if (!orgId) return
    await apiFetch('/delivery-addresses/', { method: 'POST', body: { org_id: orgId, address: address.trim() } })
  } catch { /* silent */ }
}

// ── Responsible persons suggestions (order form combobox) ──
const responsiblePersonSuggestions = ref<string[]>([])
async function loadResponsiblePersons() {
  if (!form.subsidy_id) { responsiblePersonSuggestions.value = []; return }
  try {
    responsiblePersonSuggestions.value = await apiFetch<string[]>(`/purchases/responsible-persons?subsidy_id=${form.subsidy_id}`)
  } catch { responsiblePersonSuggestions.value = [] }
}

// ── Responsible persons directory (for approval sheet dialog) ──
interface ResponsiblePerson { id: number; full_name: string; position?: string; display?: string }
const responsiblePersonsList = ref<ResponsiblePerson[]>([])
const pickerResponsibleName = ref<string>('')
const addResponsibleDialog = ref(false)
const newResponsibleName = ref('')
const newResponsiblePosition = ref('')
const savingResponsible = ref(false)

async function loadResponsiblePersonsList() {
  if (!form.subsidy_id) { responsiblePersonsList.value = []; return }
  try {
    const list = await apiFetch<ResponsiblePerson[]>(`/subsidies/${form.subsidy_id}/responsible-persons`)
    responsiblePersonsList.value = list.map(p => ({
      ...p,
      display: p.position ? `${p.full_name} (${p.position})` : p.full_name,
    }))
  } catch { responsiblePersonsList.value = [] }
}

// Список для выбора «Ответственный исполнитель» в диалоге листа согласования:
// сотрудники организации (orgUsersList) + справочник ответственных
// (responsiblePersonsList), объединённые и дедуплицированные по ФИО.
// При совпадении приоритет у записи справочника (там указана должность).
// Плюс: текущее предзаполненное значение (pickerResponsibleName) добавляется
// принудительно, если его нет ни в одном из наборов — иначе оно "исчезает"
// из списка при открытии автокомплита (v-autocomplete показывает пусто для
// значения, отсутствующего в items).
const responsibleOptions = computed(() => {
  const norm = (s: string) => s.trim().toLowerCase()
  const byName = new Map<string, { full_name: string; position?: string | null; display: string; source: 'user' | 'directory' }>()

  for (const u of orgUsersList.value) {
    if (!u.full_name) continue
    byName.set(norm(u.full_name), {
      full_name: u.full_name,
      position: u.position,
      display: u.position ? `${u.full_name} (${u.position})` : u.full_name,
      source: 'user',
    })
  }
  // Справочник имеет приоритет — перезаписывает запись сотрудника с тем же ФИО.
  for (const p of responsiblePersonsList.value) {
    if (!p.full_name) continue
    byName.set(norm(p.full_name), {
      full_name: p.full_name,
      position: p.position,
      display: p.display || (p.position ? `${p.full_name} (${p.position})` : p.full_name),
      source: 'directory',
    })
  }
  const current = pickerResponsibleName.value?.trim()
  if (current && !byName.has(norm(current))) {
    byName.set(norm(current), { full_name: current, display: current, source: 'directory' })
  }
  return [...byName.values()].sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'))
})

async function saveNewResponsible() {
  if (!newResponsibleName.value.trim() || !form.subsidy_id) return
  savingResponsible.value = true
  try {
    const created = await apiFetch<ResponsiblePerson>(`/subsidies/${form.subsidy_id}/responsible-persons`, {
      method: 'POST',
      body: { full_name: newResponsibleName.value.trim(), position: newResponsiblePosition.value.trim() || null },
    })
    const entry = { ...created, display: created.position ? `${created.full_name} (${created.position})` : created.full_name }
    responsiblePersonsList.value.push(entry)
    responsiblePersonsList.value.sort((a, b) => a.full_name.localeCompare(b.full_name))
    pickerResponsibleName.value = created.full_name
    addResponsibleDialog.value = false
    newResponsibleName.value = ''
    newResponsiblePosition.value = ''
  } catch { showSnack('Ошибка сохранения', 'error') }
  finally { savingResponsible.value = false }
}

async function openDocPicker(type: 'service_note_procurement' | 'service_note_delivery' | 'service_note_payment' | 'service_note_advance' | 'approval_sheet') {
  if (!purchaseId.value || !form.subsidy_id) {
    downloadDoc(type)
    return
  }
  docPickerType.value = type
  docPickerDialog.value = true
  loadingDocApprovers.value = true
  // Pre-fill responsible person from the purchase form.
  // Приоритет: form.responsible_person (legacy строковое поле) → ФИО юзера из form.assigned_user_id.
  let prefillName = (form.responsible_person || '').trim()
  if (!prefillName && form.assigned_user_id) {
    const u = orgUsersList.value.find((x: any) => x.id === form.assigned_user_id)
    prefillName = (u?.full_name || u?.name || '').trim()
  }
  pickerResponsibleName.value = prefillName
  try {
    const [list] = await Promise.all([
      apiFetch<DocApprover[]>(`/subsidies/${form.subsidy_id}/approvers`),
      loadResponsiblePersonsList(),
      orgUsersList.value.length ? Promise.resolve() : loadOrgUsers(),
    ])
    docApprovers.value = list
    if (type === 'approval_sheet') {
      pickerApproverIds.value = list.filter(a => a.is_default).map(a => a.id)
    } else {
      // Бизнес-правило: за другого человека делать СЗ может только тот, кому
      // подчинён этот человек. Грузим scope «я + мои подчинённые».
      await loadActAsUsers()
      // Default: current logged-in user
      if (currentUserId && actAsList.value.find(u => u.id === currentUserId)) {
        pickerInitiatorId.value = currentUserId
      } else {
        const def = list.find(a => a.can_initiate && a.is_default) || list.find(a => a.can_initiate)
        pickerInitiatorId.value = def?.id ?? null
      }
    }
  } catch {
    docApprovers.value = []
  } finally {
    loadingDocApprovers.value = false
  }
}

async function confirmDocDownload() {
  // Capture values BEFORE closing dialog
  const type = docPickerType.value
  const approverIds = [...pickerApproverIds.value]
  const responsibleName = pickerResponsibleName.value
  const initiatorId = pickerInitiatorId.value
  docPickerDialog.value = false

  if (type === 'service_note_payment' || type === 'service_note_advance') {
    // Phase 27.2-02: если несколько закр.документов — показать picker
    await openAcceptanceDocPicker(type, initiatorId)
  } else if (type.startsWith('service_note')) {
    const params = initiatorId ? `?initiator_id=${initiatorId}` : ''
    await downloadDoc(type, params)
  } else {
    const parts: string[] = []
    if (approverIds.length) parts.push(`approver_ids=${approverIds.join(',')}`)
    if (responsibleName) parts.push(`responsible_name=${encodeURIComponent(responsibleName)}`)
    console.log('[DOC] approval_sheet params:', parts, 'approverIds:', approverIds)
    await downloadDoc('approval_sheet', parts.length ? `?${parts.join('&')}` : '')
  }
}
// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// duration=0 по умолчанию: результат действия (смена статуса, сохранение,
// ошибка) не должен исчезать сам, пока пользователь не прочитал и не закрыл.
const toast = useToast()
const itemsEditorRef = ref<any>(null)
const budgetInfo = ref<{ remaining: number; exceeded: boolean; over: number; limit?: number; spent?: number } | null>(null)
// Остатки бюджета по ФЭО (по правам: лист всем с view_leaf, уровни выше — view_all_levels)
const authStore = useAuthStore()
const canViewLeafBudget = computed(() => authStore.hasAction('feo_budget.view_leaf'))
const canViewAllLevelsBudget = computed(() => authStore.hasAction('feo_budget.view_all_levels'))
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
const fileInputEl = ref<HTMLInputElement | null>(null)
const sectionFileInputEl = ref<HTMLInputElement | null>(null)
const pendingSectionUpload = ref<string | null>(null)
const uploadedFiles = ref<UploadedFile[]>([])
const uploadDialog = ref(false)
const uploadFileType = ref('other')
const uploadDocFormat = ref('scan')
const closingFiles = computed(() => uploadedFiles.value.filter(f => ['act', 'upd', 'contract'].includes(f.file_type || '')))
const paymentFiles = computed(() => uploadedFiles.value.filter(f => f.file_type === 'invoice'))

const DOC_UPLOAD_SECTIONS = computed(() => [
  { type: 'contract' as const, label: contractWord.value, icon: 'mdi-file-sign', color: 'indigo' },
  { type: 'act' as const, label: 'Акт', icon: 'mdi-file-check', color: 'cyan' },
  { type: 'upd' as const, label: 'УПД', icon: 'mdi-file-document-check', color: 'green' },
  { type: 'invoice' as const, label: 'Счёт', icon: 'mdi-receipt-text', color: 'orange' },
  { type: 'kp' as const, label: 'КП', icon: 'mdi-file-compare', color: 'teal' },
  { type: 'service_note' as const, label: 'Служебная записка', icon: 'mdi-file-document-edit', color: 'blue' },
  { type: 'protocol' as const, label: 'Протокол закупки', icon: 'mdi-file-certificate', color: 'deep-purple' },
  { type: 'order' as const, label: 'Приказ', icon: 'mdi-file-star', color: 'brown' },
  { type: 'other' as const, label: 'Прочее', icon: 'mdi-file-outline', color: 'grey' },
])

function filesByType(type: string) {
  return uploadedFiles.value.filter(f => f.file_type === type)
}
const fileTypeEditDialog = ref(false)
const fileTypeEditValue = ref('other')
const fileDocFormatEditValue = ref('scan')
const fileTypeEditTarget = ref<UploadedFile | null>(null)
const savingFileType = ref(false)

function openUploadDialog() {
  uploadFileType.value = 'other'
  uploadDocFormat.value = 'scan'
  uploadDialog.value = true
}

function openFileTypeEdit(f: UploadedFile) {
  fileTypeEditTarget.value = f
  fileTypeEditValue.value = f.file_type || 'other'
  fileDocFormatEditValue.value = f.doc_format || 'scan'
  fileTypeEditDialog.value = true
}

async function toggleDocFormat(f: UploadedFile) {
  if (!purchaseId.value) return
  const newFormat = f.doc_format === 'editable' ? 'scan' : 'editable'
  const token = localStorage.getItem('auth_token')
  const fd = new FormData()
  fd.append('doc_format', newFormat)
  const res = await fetch(`/api/purchases/${purchaseId.value}/files/${f.id}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  })
  if (res.ok) {
    const updated = await res.json()
    const idx = uploadedFiles.value.findIndex(x => x.id === updated.id)
    if (idx !== -1) uploadedFiles.value[idx] = updated
  }
}

async function saveFileType() {
  if (!fileTypeEditTarget.value || !purchaseId.value) return
  savingFileType.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file_type', fileTypeEditValue.value)
    fd.append('doc_format', fileDocFormatEditValue.value)
    const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fileTypeEditTarget.value.id}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (res.ok) {
      const updated = await res.json()
      const idx = uploadedFiles.value.findIndex(f => f.id === updated.id)
      if (idx !== -1) uploadedFiles.value[idx] = updated
      fileTypeEditDialog.value = false
    }
  } finally {
    savingFileType.value = false
  }
}

// ── Publications ──────────────────────────────────────────────────
interface Publication {
  id: number; purchase_id: number; platform: string; status: string
  external_id?: string; external_url?: string; error_text?: string
  published_at?: string; created_at?: string
  platform_number?: string; platform_state?: string
}

const AVAILABLE_PLATFORMS = [
  { value: 'fabrikant',    title: 'Фабрикант',          subtitle: 'fabrikant.ru — коммерческие и 223-ФЗ', color: 'orange-darken-2', icon: 'mdi-factory' },
  { value: 'roseltorg_rb', title: 'Росэлторг.Бизнес',   subtitle: 'rb.roseltorg.ru — коммерческие закупки', color: 'blue-darken-2',   icon: 'mdi-domain' },
]

const PLATFORM_LABELS: Record<string, string> = {
  fabrikant:    'Фабрикант',
  roseltorg_rb: 'Росэлторг.Бизнес',
}

const PUB_STATUS_COLOR: Record<string, string> = {
  pending:    'grey',
  publishing: 'blue',
  published:  'success',
  draft:      'orange',
  error:      'error',
}

const PUB_STATUS_LABEL: Record<string, string> = {
  pending:    'Ожидает',
  publishing: 'Публикуется...',
  published:  'Опубликовано',
  draft:      'Черновик на ЭТП',
  error:      'Ошибка',
}

const ROSELTORG_PROCEDURE_TYPES = [
  { value: 'request_quotations', title: 'Запрос котировок' },
  { value: 'request_proposals',  title: 'Запрос предложений' },
  { value: 'competition',        title: 'Конкурс' },
  { value: 'auction',            title: 'Аукцион' },
]

const publications = ref<Publication[]>([])
const publishDialog = ref(false)
const publishingPlatform = ref<string | null>(null)
const pendingPlatform = ref<string | null>(null)
const roseltorgProcedureType = ref<string | null>(null)
type PublishTarget = 'subject' | 'items' | 'nmck' | 'auction-date' | 'auction-bet' | 'region' | 'address'
const publishErrors = ref<{text: string; target: PublishTarget}[]>([])

const fabrikantDates = ref({ proposal_start: '', proposal_end: '', determination_date: '', summing_up_date: '' })
const fabrikantOkpd2 = ref('')
// ОКПД2 autocomplete state
const okpd2Items = ref<{code: string; name: string; section: string | null}[]>([])
const okpd2Loading = ref(false)
const okpd2Error = ref('')
let _okpd2SearchTimer: ReturnType<typeof setTimeout> | null = null

function okpd2ItemTitle(item: {code: string; name: string}): string {
  return `${item.code} — ${item.name}`
}

async function searchOkpd2(q: string | undefined) {
  if (_okpd2SearchTimer) clearTimeout(_okpd2SearchTimer)
  if (!q || q.length < 2) {
    okpd2Items.value = []
    okpd2Error.value = ''
    return
  }
  _okpd2SearchTimer = setTimeout(async () => {
    okpd2Loading.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/okpd2?q=${encodeURIComponent(q)}&limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        okpd2Error.value = ''
        const data = await res.json()
        // Ensure current value stays in the list if it was previously selected
        if (fabrikantOkpd2.value && !data.find((d: {code: string}) => d.code === fabrikantOkpd2.value)) {
          // keep existing items that include the current selection
          const existing = okpd2Items.value.filter(i => i.code === fabrikantOkpd2.value)
          okpd2Items.value = [...existing, ...data]
        } else {
          okpd2Items.value = data
        }
      } else {
        okpd2Error.value = `Ошибка загрузки справочника (${res.status})`
      }
    } catch (_e) {
      okpd2Error.value = 'Не удалось загрузить справочник ОКПД2'
    } finally {
      okpd2Loading.value = false
    }
  }, 300)
}

const fabrikantAttachDocs = ref(true)
const fabrikantNoNmcd = ref(false)
const fabrikantProcedureType = ref<'zp' | 'reduction' | 'price_monitoring'>('zp')
const fabrikantAuctionDateStart = ref('')
const fabrikantAuctionBetFrom = ref<number | null>(null)
const fabrikantAuctionBetTo = ref<number | null>(null)

const FABRIKANT_PROCEDURE_TYPES = [
  { value: 'zp',               title: 'Запрос предложений' },
  { value: 'reduction',        title: 'Редукцион (аукцион на понижение)' },
  { value: 'price_monitoring', title: 'Мониторинг цен' },
]

// pointer / glow state
const pointerTarget = ref<string | null>(null)
const okpd2Pointer = ref(false)
const auctionPointerTarget = ref<string | null>(null)
let _pointerTimer: ReturnType<typeof setTimeout> | null = null
let _okpd2Timer: ReturnType<typeof setTimeout> | null = null
let _auctionPointerTimer: ReturnType<typeof setTimeout> | null = null

const AUCTION_TARGETS = new Set(['auction-date', 'auction-bet'])

// ── Guide arrow (летящая стрелка с пунктирным следом) ────────────────────────
const guideArrowVisible = ref(false)
const guideArrowPos = ref({ x: 0, y: 0 })
const guideArrowAngle = ref(0)
const guideArrowArrived = ref(false)
const guideTrail = ref<{ x: number; y: number }[]>([])

let _guideRafId: number | null = null
let _guideSafetyTimer: ReturnType<typeof setTimeout> | null = null

function _getDestCenter(el: HTMLElement): { x: number; y: number } {
  const r = el.getBoundingClientRect()
  return { x: r.left + r.width / 2, y: r.top - 30 }
}

function clearGuideArrow() {
  guideArrowVisible.value = false
  guideArrowArrived.value = false
  guideTrail.value = []
  if (_guideRafId !== null) { cancelAnimationFrame(_guideRafId); _guideRafId = null }
  if (_guideSafetyTimer !== null) { clearTimeout(_guideSafetyTimer); _guideSafetyTimer = null }
}

async function guideArrowTo(target: string) {
  // Отменить предыдущий
  clearGuideArrow()

  const IN_DIALOG_TARGETS = new Set(['auction-date', 'auction-bet', 'okpd2'])
  // Наведение на КОНКРЕТНУЮ строку позиций: target вида 'item:<uid>'. id='item-row-<uid>'
  // уже проставлен на карточку/строку во всех трёх видах (ItemsCardsView/ItemsTableFlat/
  // ItemsTableStages, см. эти файлы) — тот же приём, что highlightMissingCategoryForPlan
  // в PurchaseItemsEditor.vue. Работает и на мобильных карточках, и в десктоп-таблице.
  const itemUid = target.startsWith('item:') ? target.slice(5) : null

  // Для out-of-dialog полей: закрыть диалог сначала
  if (!IN_DIALOG_TARGETS.has(target)) {
    publishDialog.value = false
    pendingPlatform.value = null
  }

  await nextTick()

  const el = itemUid != null
    ? document.getElementById('item-row-' + itemUid)
    : document.getElementById('pub-target-' + target)
  if (!el) return

  // Старт: правый верхний угол вьюпорта (где снэкбар)
  const startX = window.innerWidth - 100
  const startY = 90
  guideArrowPos.value = { x: startX, y: startY }
  guideTrail.value = [{ x: startX, y: startY }]
  guideArrowVisible.value = true
  guideArrowArrived.value = false

  // Инициировать плавный скролл к полю
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })

  // Также выставить glow
  if (itemUid != null) {
    // Строка позиций не обёрнута pub-glow div'ом (живёт в дочернем компоненте) —
    // подсвечиваем напрямую тем же глобальным pulse-классом, что и
    // highlightMissingCategoryForPlan в PurchaseItemsEditor.vue (.plan-bulk-row-pulse,
    // стиль объявлен там же, global, не scoped).
    el.classList.add('plan-bulk-row-pulse')
    setTimeout(() => el.classList.remove('plan-bulk-row-pulse'), 3000)
  } else if (AUCTION_TARGETS.has(target)) {
    if (_auctionPointerTimer) clearTimeout(_auctionPointerTimer)
    auctionPointerTarget.value = target
  } else if (target === 'okpd2') {
    if (_okpd2Timer) clearTimeout(_okpd2Timer)
    okpd2Pointer.value = true
  } else {
    if (_pointerTimer) clearTimeout(_pointerTimer)
    pointerTarget.value = target
  }

  const LERP = 0.07
  const ARRIVE_DIST = 12
  const TRAIL_MIN_DIST = 6
  let arrived = false

  function tick() {
    const dest = _getDestCenter(el)
    const cx = guideArrowPos.value.x
    const cy = guideArrowPos.value.y

    if (!arrived) {
      const dx = dest.x - cx
      const dy = dest.y - cy
      const dist = Math.sqrt(dx * dx + dy * dy)
      guideArrowAngle.value = (Math.atan2(dy, dx) * 180) / Math.PI + 90 // +90 т.к. стрелка вниз по умолчанию

      const nx = cx + dx * LERP
      const ny = cy + dy * LERP
      guideArrowPos.value = { x: nx, y: ny }

      // Добавить точку следа если сдвинулись достаточно
      const last = guideTrail.value[guideTrail.value.length - 1]
      const ldx = nx - (last?.x ?? nx)
      const ldy = ny - (last?.y ?? ny)
      if (Math.sqrt(ldx * ldx + ldy * ldy) > TRAIL_MIN_DIST) {
        guideTrail.value.push({ x: nx, y: ny })
        // Ограничим длину следа для производительности
        if (guideTrail.value.length > 500) guideTrail.value.shift()
      }

      if (dist < ARRIVE_DIST) {
        arrived = true
        guideArrowArrived.value = true
      }
    } else {
      // Прилипаем к полю (поле могло сдвинуться)
      guideArrowPos.value = _getDestCenter(el)
    }

    _guideRafId = requestAnimationFrame(tick)
  }

  _guideRafId = requestAnimationFrame(tick)

  // Safety: убираем через 3 минуты
  _guideSafetyTimer = setTimeout(() => clearGuideArrow(), 3 * 60 * 1000)
}
// ── end guide arrow ────────────────────────────────────────────────────────────

function revealField(target: string) {
  guideArrowTo(target)
}

const publishNmck = computed(() => displayNmck.value || savedNmck.value || 0)

function initFabrikantDates() {
  const pad = (n: number) => String(n).padStart(2, '0')
  const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  const now = new Date()
  const end = new Date(now.getTime() + 7*24*60*60*1000)
  fabrikantDates.value = {
    proposal_start: fmt(new Date(now.getTime() + 60*60*1000)),
    proposal_end: fmt(end),
    determination_date: fmt(new Date(end.getTime() + 24*60*60*1000)),
    summing_up_date: fmt(new Date(end.getTime() + 2*24*60*60*1000)),
  }
  // Preload current ОКПД2 selection so v-autocomplete can display the label
  if (fabrikantOkpd2.value && !okpd2Items.value.find(i => i.code === fabrikantOkpd2.value)) {
    void searchOkpd2(fabrikantOkpd2.value)
  }
}

function checkPublishReady(): {text: string; target: PublishTarget}[] {
  const errors: {text: string; target: PublishTarget}[] = []
  if (!form.subject?.trim()) errors.push({ text: 'Не заполнено наименование закупки', target: 'subject' })
  // Мониторинг цен не требует позиций (и deliveryPlace там опционален)
  if (fabrikantProcedureType.value !== 'price_monitoring') {
    if (!items.value.some(i => i.item_name?.trim())) errors.push({ text: 'Нет позиций в закупке (добавьте хотя бы одну)', target: 'items' })
    // Фабрикант требует lot_delivery_place.state/region/okato — нужен реальный субъект РФ (поле доставки, не мероприятия)
    if (!form.delivery_region || !resolveRegionOkato(form.delivery_region)) {
      errors.push({ text: 'Укажите субъект РФ (для места поставки)', target: 'region' })
    }
    // Адрес поставки: структурный → свободная строка → место оказания услуг → адрес организации субсидии
    const hasAddress = !!String(form.delivery_city || form.delivery_street || form.delivery_address || '').trim()
      || !!String(form.delivery_location || '').trim()
      || !!String(customerPreview.value?.address || '').trim()
    if (!hasAddress) errors.push({ text: 'Укажите адрес доставки', target: 'address' })
  }
  // Поля редукциона
  if (fabrikantProcedureType.value === 'reduction') {
    if (!fabrikantAuctionDateStart.value) errors.push({ text: 'Укажите дату и время начала редукциона', target: 'auction-date' })
    // numOrNull ловит и null, и '' (Vue кладёт '' при очистке v-model.number-поля,
    // голое === null это пропускало — редукцион на Фабрикант ушёл бы с auction_bet_limit_from: '').
    // ПРАВКА 2026-09-04 «0=пусто для денег/количеств»: auction_bet_limit_from/to (границы
    // ставки редукциона) НЕ переведены на numOrNullZeroEmpty — не входят в явный список
    // владельца (цена/сумма/кол-во/НМЦК/...), не однозначно деньги или ставка/шаг в
    // процентах, поле обязательное (см. error-check ниже). Оставлено на numOrNull —
    // требует отдельного решения владельца.
    if (numOrNull(fabrikantAuctionBetFrom.value) === null || numOrNull(fabrikantAuctionBetTo.value) === null) errors.push({ text: 'Укажите границы ставки редукциона (от / до)', target: 'auction-bet' })
  }
  return errors
}

const currentSubsidyOrgInn = computed(() =>
  subsidies.value.find(s => s.id === form.subsidy_id)?.org_inn ?? null
)

const isPlatformPublished = (platform: string) =>
  publications.value.some(p => p.platform === platform && (p.status === 'published' || p.status === 'draft'))

const refreshingPubId = ref<number | null>(null)

async function loadPublications() {
  if (!purchaseId.value) return
  try {
    publications.value = await apiFetch<Publication[]>(`/publications/purchases/${purchaseId.value}`)
  } catch {}
}

async function refreshPubStatus(pub: Publication) {
  refreshingPubId.value = pub.id
  try {
    const updated = await apiFetch<Publication>(`/publications/${pub.id}/refresh`, { method: 'POST' })
    const idx = publications.value.findIndex(p => p.id === pub.id)
    if (idx !== -1) publications.value[idx] = updated
    if (updated.status === 'published') {
      showSnack(`Процедура размещена на ${PLATFORM_LABELS[updated.platform] || updated.platform}`, 'success')
    } else if (updated.status === 'draft') {
      showSnack(`Статус обновлён: черновик${updated.platform_number ? ' №' + updated.platform_number : ''} на Фабриканте`)
    }
  } catch (e: any) {
    const msg = e?.payload?.message || e?.detail || e?.message || 'Не удалось обновить статус'
    showSnack(msg, 'error')
  } finally {
    refreshingPubId.value = null
  }
}

async function doPublish(platform: string, procedureType?: string | null) {
  publishingPlatform.value = platform
  // Сначала сбрасываем несохранённые изменения в БД, иначе бэкенд читает устаревший delivery_region
  if (isEdit.value && purchaseId.value) {
    await performAutosave()
    if (autosaveState.value === 'error') {
      showSnack('Не удалось сохранить изменения карточки — публикация отменена', 'error')
      publishingPlatform.value = null
      return
    }
  }
  try {
    const body: Record<string, any> = { platform }
    if (procedureType) body.procedure_type = procedureType
    if (platform === 'fabrikant') {
      body.procedure_type = fabrikantProcedureType.value
      body.okpd2_code = fabrikantOkpd2.value
      body.proposal_start = fabrikantDates.value.proposal_start
      body.proposal_end = fabrikantDates.value.proposal_end
      body.summing_up_date = fabrikantDates.value.summing_up_date
      body.attach_documents = fabrikantAttachDocs.value
      if (fabrikantProcedureType.value === 'zp') {
        body.determination_date = fabrikantDates.value.determination_date
        body.no_nmcd = fabrikantNoNmcd.value
      } else if (fabrikantProcedureType.value === 'reduction') {
        body.no_nmcd = fabrikantNoNmcd.value
        body.auction_date_start = fabrikantAuctionDateStart.value
        body.auction_bet_limit_from = numOrNull(fabrikantAuctionBetFrom.value)
        body.auction_bet_limit_to = numOrNull(fabrikantAuctionBetTo.value)
      }
      // price_monitoring: no no_nmcd, no determination_date, no auction fields
    }
    const pub = await apiFetch<Publication>(`/publications/purchases/${purchaseId.value}`, {
      method: 'POST',
      body,
    })
    publications.value.unshift(pub)
    showSnack(`Отправлено на публикацию: ${PLATFORM_LABELS[platform]}`)
    publishDialog.value = false
    pendingPlatform.value = null
    roseltorgProcedureType.value = null
    // Poll status for 30s
    pollPublication(pub.id)
  } catch (e: any) {
    const errText = e?.detail || e?.payload?.message || e?.message || 'Ошибка при отправке на публикацию'
    if (platform === 'fabrikant') {
      const errTarget = fabrikantErrorTarget(errText)
      if (errTarget === 'okpd2') {
        showSnack(errText, 'error', {
          actionText: 'Показать поле',
          onAction: () => guideArrowTo(errTarget),
        })
        guideArrowTo(errTarget)
      } else if (errTarget === 'region' || errTarget === 'address') {
        showSnack(errText, 'error', {
          actionText: 'Показать поле',
          onAction: () => guideArrowTo(errTarget),
        })
        guideArrowTo(errTarget)
      } else {
        showSnack(errText, 'error')
      }
    } else {
      showSnack(errText, 'error')
    }
  } finally {
    publishingPlatform.value = null
  }
}

async function retryPublish(platform: string) {
  if (platform === 'fabrikant') {
    openFabrikantRetry(platform)
  } else {
    await doPublish(platform)
  }
}

// Маппинг бизнес-ошибок Фабриканта → поле карточки (одна точка правды:
// используется и в openFabrikantRetry, и в снэкбаре поллинга)
function fabrikantErrorTarget(errorText?: string | null): 'okpd2' | 'region' | 'address' | null {
  const t = (errorText || '').toLowerCase()
  if (!t) return null
  if (t.includes('окпд') || t.includes('okpd')) return 'okpd2'
  const isDeliveryPlace = /delivery_place|deliveryplace|место поставки/.test(t)
  // lot_delivery_place.okato / .state / .region → поле «Субъект РФ»
  if (/okato|окато|\bregion\b|\bstate\b|субъект/.test(t)) return 'region'
  // адрес внутри места поставки → поле адреса
  if (isDeliveryPlace && /adress|address|адрес/.test(t)) return 'address'
  if (isDeliveryPlace) return 'region'
  return null
}

function openFabrikantRetry(platform: string) {
  const lastPub = publications.value.find(p => p.platform === platform && p.status === 'error')
  publishErrors.value = checkPublishReady()
  publishDialog.value = true
  pendingPlatform.value = 'fabrikant'
  initFabrikantDates()
  // Сохраняем выбранный тип процедуры при повторе (fabrikantProcedureType не сбрасываем)
  if (fabrikantProcedureType.value !== 'price_monitoring') {
    fabrikantNoNmcd.value = !(publishNmck.value > 0)
  }
  const errTarget = fabrikantErrorTarget(lastPub?.error_text)
  if (errTarget === 'okpd2') {
    nextTick(() => guideArrowTo('okpd2'))
  } else if (errTarget === 'region' || errTarget === 'address') {
    // Показать блокер в списке ошибок диалога; клик → закрыть диалог → стрелка к полю
    if (!publishErrors.value.some(e => e.target === errTarget)) {
      publishErrors.value.push({
        text: errTarget === 'region' ? 'Укажите субъект РФ (для места поставки)' : 'Укажите адрес доставки',
        target: errTarget,
      })
    }
  }
}

function pollPublication(pubId: number, attempts = 0) {
  if (attempts > 60) return
  // Первые 15 попыток — каждые 2с (быстрый отклик), дальше — каждые 5с (не долбим сервер)
  const delay = attempts < 15 ? 2000 : 5000
  setTimeout(async () => {
    await loadPublications()
    const pub = publications.value.find(p => p.id === pubId)
    if (pub && pub.status === 'error') {
      const errTarget = pub.platform === 'fabrikant' ? fabrikantErrorTarget(pub.error_text) : null
      if (errTarget === 'region' || errTarget === 'address') {
        // АВТОМАТИЧЕСКИ запускаем стрелку без ожидания клика
        guideArrowTo(errTarget)
        showSnack(pub.error_text || 'Ошибка публикации', 'error', {
          actionText: 'Показать поле',
          onAction: () => guideArrowTo(errTarget),
        })
      } else if (errTarget === 'okpd2') {
        // Поле ОКПД2 находится в диалоге публикации — открываем диалог со стрелкой
        openFabrikantRetry('fabrikant')
        showSnack(pub.error_text || 'Ошибка публикации', 'error', {
          actionText: 'Показать поле',
          onAction: () => openFabrikantRetry('fabrikant'),
        })
      } else {
        showSnack(pub.error_text || 'Ошибка публикации', 'error')
      }
    } else if (pub && pub.status === 'published') {
      showSnack(`Закупка опубликована на ${PLATFORM_LABELS[pub.platform] || pub.platform}`, 'success')
    } else if (pub && pub.status === 'draft') {
      showSnack(
        `Черновик процедуры${pub.platform_number ? ' №' + pub.platform_number : ''} создан на Фабриканте. Разместите его в личном кабинете площадки.`,
        'warning',
      )
    } else if (pub && (pub.status === 'publishing' || pub.status === 'pending')) {
      pollPublication(pubId, attempts + 1)
    }
  }, delay)
}

// ── Linked tasks ─────────────────────────────────────────────────────────────
const TASK_STATUS_LABEL: Record<string, string> = {
  todo: 'К выполнению', in_progress: 'В работе', done: 'Выполнена', cancelled: 'Отменена',
}
const TASK_PRIORITIES = [
  { value: 'low', title: 'Низкий' }, { value: 'medium', title: 'Средний' },
  { value: 'high', title: 'Высокий' }, { value: 'urgent', title: 'Срочный' },
]
function taskStatusColor(s: string) {
  return s === 'done' ? 'success' : s === 'in_progress' ? 'info' : s === 'cancelled' ? 'grey' : 'default'
}
function taskPriorityColor(p: string) {
  return p === 'urgent' ? 'error' : p === 'high' ? 'warning' : p === 'medium' ? 'info' : 'default'
}

const linkedTasks = ref<any[]>([])
const linkedTaskDialog = ref(false)
const linkedTaskSaving = ref(false)
const allUsers = ref<{ value: number; text: string }[]>([])
const linkedTaskForm = reactive({
  title: '', description: '', priority: 'medium',
  due_date: '', assignee_ids: [] as number[],
})

async function loadLinkedTasks() {
  if (!purchaseId.value) return
  try {
    linkedTasks.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/tasks/`)
  } catch { linkedTasks.value = [] }
}

async function loadAllUsers() {
  if (allUsers.value.length) return
  try {
    const users = await apiFetch<any[]>('/users/')
    allUsers.value = users.map(u => ({ value: u.id, text: u.full_name || u.username }))
  } catch {}
}

function openCreateLinkedTask() {
  Object.assign(linkedTaskForm, {
    title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [],
  })
  loadAllUsers()
  linkedTaskDialog.value = true
}

async function saveLinkedTask() {
  if (!linkedTaskForm.title || !purchaseId.value) return
  linkedTaskSaving.value = true
  try {
    const body: Record<string, any> = {
      title: linkedTaskForm.title,
      description: linkedTaskForm.description || undefined,
      priority: linkedTaskForm.priority,
      purchase_id: purchaseId.value,
      assignee_ids: linkedTaskForm.assignee_ids,
    }
    if (linkedTaskForm.due_date) body.due_date = linkedTaskForm.due_date + 'T23:59:59'
    await apiFetch('/tasks/', { method: 'POST', body })
    linkedTaskDialog.value = false
    showSnack('Задача создана')
    await loadLinkedTasks()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка при создании задачи', 'error')
  } finally {
    linkedTaskSaving.value = false
  }
}

// ── Link existing task ───────────────────────────────────────────────────────
const linkTaskDialog = ref(false)
const linkTaskSearch = ref('')
const linkTaskResults = ref<any[]>([])
const linkTaskSearching = ref(false)
let _linkSearchTimer: ReturnType<typeof setTimeout> | null = null

function openLinkExistingTask() {
  linkTaskSearch.value = ''
  linkTaskResults.value = []
  linkTaskDialog.value = true
}

function searchUnlinkedTasks(q: string | null) {
  if (_linkSearchTimer) clearTimeout(_linkSearchTimer)
  if (!q || q.length < 2) { linkTaskResults.value = []; return }
  _linkSearchTimer = setTimeout(async () => {
    linkTaskSearching.value = true
    try {
      linkTaskResults.value = await apiFetch<any[]>(`/tasks/?search=${encodeURIComponent(q)}`)
    } catch { linkTaskResults.value = [] }
    finally { linkTaskSearching.value = false }
  }, 300)
}

async function linkExistingTask(taskId: number) {
  try {
    await apiFetch(`/tasks/${taskId}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId.value }),
    })
    linkTaskDialog.value = false
    showSnack('Задача привязана к закупке')
    await loadLinkedTasks()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка привязки', 'error')
  }
}

async function unlinkTask(taskId: number) {
  try {
    await apiFetch(`/tasks/${taskId}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: null }),
    })
    showSnack('Задача отвязана')
    await loadLinkedTasks()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка', 'error')
  }
}

// ── Purchase members ─────────────────────────────────────────────────────────
const purchaseMembers = ref<any[]>([])
const newMemberUserId = ref<number | null>(null)
const memberMenuOpen = ref(false)
const memberAdding = ref(false)

const memberSubordinateIds = ref<Set<number>>(new Set())

async function loadMemberSubordinates() {
  try {
    const subs = await apiFetch<any[]>(`/users/${currentUserId}/subordinates`)
    memberSubordinateIds.value = new Set(subs.map((u: any) => u.id))
  } catch {}
}

function memberNeedsConsent(userId: number): boolean {
  // Discussion group: always show consent notice when adding someone else
  if (userId === currentUserId) return false
  return true
}

watch(memberMenuOpen, async (open) => {
  if (open) {
    await Promise.all([loadAllUsers(), loadPurchaseMembers(), loadMemberSubordinates()])
    newMemberUserId.value = null
  }
})

const memberSortedUsers = computed(() => {
  const memberIds = new Set(purchaseMembers.value.map((m: any) => m.user_id))
  const inGroup = allUsers.value
    .filter(u => memberIds.has(u.value))
    .sort((a, b) => a.text.localeCompare(b.text, 'ru'))
  const others = allUsers.value
    .filter(u => !memberIds.has(u.value))
    .sort((a, b) => a.text.localeCompare(b.text, 'ru'))
  return [...inGroup, ...others]
})

function isMemberOfGroup(userId: number): boolean {
  return purchaseMembers.value.some((m: any) => m.user_id === userId)
}

async function loadPurchaseMembers() {
  if (!purchaseId.value) return
  try {
    purchaseMembers.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/members`)
  } catch { purchaseMembers.value = [] }
}

// Список user_id согласующих по текущей закупке (для canSeePurchaseDocs)
const purchaseApprovalUserIds = ref<Set<number>>(new Set())

async function loadPurchaseApprovals() {
  if (!purchaseId.value) return
  try {
    const list = await apiFetch<any[]>(`/purchases/${purchaseId.value}/approvals`)
    purchaseApprovalUserIds.value = new Set(list.map((a: any) => a.user_id).filter(Boolean))
  } catch { purchaseApprovalUserIds.value = new Set() }
}

const isPurchaseApprover = computed(() =>
  !!currentUserId && purchaseApprovalUserIds.value.has(currentUserId)
)

const canSeePurchaseDocs = computed(() =>
  isEdit.value && (
    isManagerLevel.value ||
    authStore.hasAction('purchase_files.upload') ||
    purchaseMembers.value.some((m: any) => m.user_id === currentUserId) ||
    isPurchaseApprover.value
  )
)

async function addPurchaseMember(userId: number | null) {
  if (!userId || !purchaseId.value) return
  try {
    await apiFetch(`/purchases/${purchaseId.value}/members`, {
      method: 'POST', body: { user_id: userId },
    })
    await loadPurchaseMembers()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка', 'error')
  }
  newMemberUserId.value = null
}

async function addPurchaseMemberAndClose() {
  memberAdding.value = true
  await addPurchaseMember(newMemberUserId.value)
  memberAdding.value = false
  memberMenuOpen.value = false
}

async function removePurchaseMember(userId: number) {
  if (!purchaseId.value) return
  try {
    await apiFetch(`/purchases/${purchaseId.value}/members/${userId}`, { method: 'DELETE' })
    await loadPurchaseMembers()
  } catch {}
}

// ── Split purchase feature ───────────────────────────────────────────────────
const splitKanbanDialog = ref(false)
const splitKanbanItems = ref<any[]>([])

const ADMIN_ROLES_FE = ['superadmin', 'account_owner', 'org_admin', 'admin']
const LOCKED_SPLIT_STATUSES = ['contracted', 'delivered', 'paid']

const canSplitPurchase = computed(() => {
  if (!isEdit.value) return false
  const st = (form.status || '').toString()
  if (st === 'split') return false
  if ((items.value?.length || 0) < 2) return false
  if (LOCKED_SPLIT_STATUSES.includes(st)) {
    const role = localStorage.getItem('user_role') || ''
    return ADMIN_ROLES_FE.includes(role)
  }
  return true
})

async function openSplitKanban() {
  // items.value в CreateOrderView НЕ содержит item.id (см. mapping @4025),
  // а канбану нужны настоящие pk для DnD и payload. Фетчим closedly.
  const pid = Number(route.params.id)
  let fresh: any = null
  try { fresh = await apiFetch<any>(`/purchases/${pid}`) } catch {}
  const rawItems: any[] = (fresh?.items || []).filter((it: any) => it && it.id != null)

  let productsList: any[] = []
  try { productsList = await apiFetch<any[]>('/products/?limit=10000') } catch {}
  const byId = new Map<number, any>(productsList.map((p: any) => [p.id, p]))
  const byName = new Map<string, any>(productsList.map((p: any) => [(p.name || '').trim().toLowerCase(), p]))

  splitKanbanItems.value = rawItems.map((it: any) => {
    let prod = it.product_id ? byId.get(it.product_id) : null
    if (!prod && it.item_name) prod = byName.get(it.item_name.trim().toLowerCase()) || null
    const category = (prod?.category || '').trim()
    return {
      id: it.id,
      product_id: it.product_id ?? prod?.id ?? null,
      item_name: it.item_name,
      quantity: Number(it.quantity) || 0,
      unit: it.unit || 'шт',
      total_price: Number(it.total_price) || 0,
      _photo_url: productPhotoSrc(prod) ?? null,
      _product_category: category,
      _column: category || '__uncategorized__',
    }
  })
  splitKanbanDialog.value = true
}

async function onPurchaseSplit(result: { purchase_ids: number[]; count: number; source_purchase_id: number }) {
  splitKanbanDialog.value = false
  showSnack(`Создано ${result.count} закупок. Исходная разбита.`, 'success')
  if (result.purchase_ids?.[0]) {
    router.push(`/orders/${result.purchase_ids[0]}/edit`)
  }
}

// ── Purchase chat ────────────────────────────────────────────────────────────
const currentUserId = parseInt(localStorage.getItem('user_id') || '0')
const purchaseChatContainer = ref<HTMLElement | null>(null)
const purchaseCommentInput = ref<any>(null)
const purchaseComments = ref<any[]>([])
const pCommentText = ref('')
const pCommentSaving = ref(false)
const pEnterToSend = ref(localStorage.getItem('pchat_enter_to_send') !== 'false')
const pMentionOpen = ref(false)
const pMentionQuery = ref('')

const pFilteredMentionUsers = computed(() => {
  const q = pMentionQuery.value.toLowerCase()
  if (!q) return allUsers.value.slice(0, 8)
  return allUsers.value.filter(u => u.text.toLowerCase().includes(q)).slice(0, 6)
})

async function loadPurchaseComments() {
  if (!purchaseId.value) return
  try {
    purchaseComments.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/comments`)
    nextTick(() => {
      if (purchaseChatContainer.value) purchaseChatContainer.value.scrollTop = purchaseChatContainer.value.scrollHeight
    })
  } catch { purchaseComments.value = [] }
}

async function addPurchaseComment() {
  if (!purchaseId.value || !pCommentText.value.trim()) return
  pCommentSaving.value = true
  pMentionOpen.value = false
  try {
    await apiFetch(`/purchases/${purchaseId.value}/comments`, {
      method: 'POST', body: JSON.stringify({ text: pCommentText.value.trim() }),
    })
    pCommentText.value = ''
    await loadPurchaseComments()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка', 'error')
  } finally { pCommentSaving.value = false }
}

async function deletePurchaseComment(commentId: number) {
  if (!purchaseId.value) return
  try {
    await apiFetch(`/purchases/${purchaseId.value}/comments/${commentId}`, { method: 'DELETE' })
    await loadPurchaseComments()
  } catch {}
}

function onPurchaseCommentInput() {
  const text = pCommentText.value
  const atIdx = text.lastIndexOf('@')
  if (atIdx >= 0) {
    const afterAt = text.slice(atIdx + 1)
    if (!afterAt.includes('\n') && afterAt.length <= 30) {
      pMentionQuery.value = afterAt
      pMentionOpen.value = true
      return
    }
  }
  pMentionOpen.value = false
}

function onPurchaseCommentKeydown(e: KeyboardEvent) {
  if (pMentionOpen.value) {
    if (e.key === 'Escape') { pMentionOpen.value = false; e.preventDefault(); return }
    if ((e.key === 'Tab' || e.key === 'Enter') && pFilteredMentionUsers.value.length > 0) {
      e.preventDefault(); pInsertMention(pFilteredMentionUsers.value[0]); return
    }
  }
  if (e.key === 'Enter') {
    const ctrl = e.ctrlKey || e.metaKey
    if (pEnterToSend.value) {
      if (ctrl) {
        e.preventDefault()
        const ta = (purchaseCommentInput.value as any)?.$el?.querySelector('textarea')
        if (ta) { const s = ta.selectionStart; pCommentText.value = pCommentText.value.slice(0, s) + '\n' + pCommentText.value.slice(ta.selectionEnd); nextTick(() => { ta.selectionStart = ta.selectionEnd = s + 1 }) }
        return
      }
      if (!e.shiftKey) { e.preventDefault(); addPurchaseComment() }
    } else {
      if (ctrl) { e.preventDefault(); addPurchaseComment() }
    }
  }
}

function pOpenMentionPicker() {
  pMentionQuery.value = ''
  const text = pCommentText.value
  if (!text.endsWith('@')) pCommentText.value = text + (text && !text.endsWith(' ') ? ' @' : '@')
  pMentionOpen.value = true
  loadAllUsers()
}

function pInsertMention(user: { text: string; value: number }) {
  const text = pCommentText.value
  const atIdx = text.lastIndexOf('@')
  if (atIdx >= 0) pCommentText.value = text.slice(0, atIdx) + `@${user.text} `
  pMentionOpen.value = false
  nextTick(() => {
    const el = (purchaseCommentInput.value as any)?.$el?.querySelector('textarea')
    if (el) el.focus()
  })
}

function renderPurchaseMentions(text: string): string {
  if (!text) return ''
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return escaped.replace(/@([A-Za-zА-Яа-яёЁ\s]+?)(\s|$)/g, '<span style="color:#1976d2;font-weight:500">@$1</span>$2')
}

// ── Purchase broadcast ──
const pBroadcastDialog = ref(false)
const pBroadcastScope = ref<string>('organization')
const pBroadcastScopeId = ref<number | null>(null)
const pBroadcastText = ref('')
const pBroadcastSending = ref(false)
const pBroadcastOrgs = ref<{ id: number; name: string }[]>([])
const pBroadcastDepts = ref<{ id: number; name: string }[]>([])

async function openPurchaseBroadcast() {
  pBroadcastText.value = pCommentText.value || ''
  pBroadcastScopeId.value = null
  pBroadcastDialog.value = true
  try {
    const data = await apiFetch<any>('/tasks/broadcast/scopes')
    pBroadcastOrgs.value = data.organizations || []
    pBroadcastDepts.value = data.departments || []
    if (pBroadcastOrgs.value.length === 1) pBroadcastScopeId.value = pBroadcastOrgs.value[0].id
  } catch {}
}

async function sendPurchaseBroadcast() {
  if (!purchaseId.value || !pBroadcastText.value.trim()) return
  pBroadcastSending.value = true
  try {
    const res = await apiFetch<any>(`/purchases/${purchaseId.value}/broadcast`, {
      method: 'POST',
      body: JSON.stringify({
        text: pBroadcastText.value.trim(),
        scope: pBroadcastScope.value,
        scope_id: pBroadcastScope.value !== 'all' ? pBroadcastScopeId.value : undefined,
      }),
    })
    pBroadcastDialog.value = false
    pCommentText.value = ''
    showSnack(`Отправлено: ${res.sent} из ${res.total_users} сотрудников`)
    await loadPurchaseComments()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка рассылки', 'error')
  } finally { pBroadcastSending.value = false }
}

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
const frameworkContracts = ref<FrameworkContract[]>([])
const frameworkDialog = ref(false)
const frameworkLoading = ref(false)
const frameworkSearch = ref('')
const selectedFrameworkContract = ref<FrameworkContract | null>(null)
const newFrameworkDialog = ref(false)
const newFrameworkSaving = ref(false)
const newContractNumberRef = ref<any>(null)
function focusNewContractNumber() {
  nextTick(() => newContractNumberRef.value?.focus())
}
const newFrameworkForm = reactive({
  number: '', date: '', contractor_id: null as number | null, subject: '', max_amount: null as number | null,
})

const isFramework = computed(() => form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')
const isFrameworkCumulative = computed(() => form.purchase_contract_type === 'framework_cumulative')
const contractWord = computed(() => isFramework.value ? 'Заказ' : 'Договор')
const contractWordLower = computed(() => isFramework.value ? 'заказ' : 'договор')
const contractWordGen = computed(() => isFramework.value ? 'заказа' : 'договора')

// ── Framework sibling purchases ───────────────────────────────────────────────
interface FrameworkSibling {
  id: number; item_name?: string; subject?: string; status: string
  framework_seq?: number; total_nmck?: number; contract_price?: number; payment_amount?: number
}
const frameworkSiblings = ref<FrameworkSibling[]>([])

const frameworkTotals = computed(() => ({
  nmck:  frameworkSiblings.value.reduce((s, x) => s + (Number(x.total_nmck) || 0), 0),
  price: frameworkSiblings.value.reduce((s, x) => s + (Number(x.contract_price) || 0), 0),
  paid:  frameworkSiblings.value.reduce((s, x) => s + (Number(x.payment_amount) || 0), 0),
}))

async function loadFrameworkSiblings(contractId: number) {
  try {
    frameworkSiblings.value = await apiFetch<FrameworkSibling[]>(`/purchases/by-contract/${contractId}`)
  } catch {
    frameworkSiblings.value = []
  }
}

watch(() => form.contract_id, (cid) => {
  if (cid && isFramework.value) loadFrameworkSiblings(cid)
  else frameworkSiblings.value = []
})

const filteredFrameworkContracts = computed(() => {
  const q = frameworkSearch.value.toLowerCase().trim()
  if (!q) return frameworkContracts.value
  return frameworkContracts.value.filter(c =>
    (c.number || '').toLowerCase().includes(q) ||
    (c.contractor_name || '').toLowerCase().includes(q) ||
    (c.contractor_inn || '').toLowerCase().includes(q) ||
    (c.subject || '').toLowerCase().includes(q)
  )
})

// ── Счёт по РД (framework_invoice) ──────────────────────────────────────────
const selectedFrameworkInvoiceContract = ref<FrameworkContract | null>(null)

const frameworkContractsForInvoice = computed(() => {
  if (!form.contractor_id) return frameworkContracts.value
  return frameworkContracts.value.filter(c => c.contractor_id === form.contractor_id)
})

async function loadFrameworkContractsForInvoice() {
  if (form.payment_basis_type !== 'framework_invoice') return
  try {
    const params = new URLSearchParams()
    if (form.subsidy_id) params.set('subsidy_id', String(form.subsidy_id))
    if (form.contractor_id) params.set('contractor_id', String(form.contractor_id))
    params.append('contract_type', 'framework_cumulative')
    params.append('contract_type', 'framework_with_amount')
    frameworkContracts.value = await apiFetch<FrameworkContract[]>(`/contracts/?${params}`)
  } catch { /* silent */ }
}

function onFrameworkInvoiceSelect(c: FrameworkContract | null) {
  if (c) {
    form.contract_id = c.id
    // phase26-j-3: autofill denormalized fields from selected contract
    if (c.number) form.contract_number = c.number
    if (c.date) form.contract_date = c.date
    if (c.contract_type) form.purchase_contract_type = c.contract_type
  } else {
    form.contract_id = null
  }
}

watch(() => form.payment_basis_type, (newType) => {
  if (newType === 'framework_invoice') {
    loadFrameworkContractsForInvoice()
  }
})

watch(() => form.contractor_id, () => {
  if (form.payment_basis_type === 'framework_invoice') {
    loadFrameworkContractsForInvoice()
  }
})

// ── Со-финансирование (cofinancing subsidies) ────────────────────────────────
const cofinancingSubsidies = computed(() => {
  if (!form.subsidy_id) return []
  const primary = subsidies.value.find(s => s.id === form.subsidy_id)
  if (!primary) return []
  return subsidies.value.filter(s => s.id !== form.subsidy_id && s.org_id === primary.org_id)
})

async function openFrameworkDialog() {
  frameworkDialog.value = true
  frameworkSearch.value = ''
  frameworkLoading.value = true
  try {
    const types = [form.purchase_contract_type]
    const params = new URLSearchParams()
    if (form.subsidy_id) params.set('subsidy_id', String(form.subsidy_id))
    types.forEach(t => params.append('contract_type', t))
    frameworkContracts.value = await apiFetch<FrameworkContract[]>(`/contracts/?${params}`)
  } catch {
    showSnack('Ошибка загрузки договоров', 'error')
  } finally {
    frameworkLoading.value = false
  }
}

function selectFrameworkContract(c: FrameworkContract) {
  selectedFrameworkContract.value = c
  form.contract_id = c.id
  frameworkDialog.value = false
}

function clearFrameworkContract() {
  selectedFrameworkContract.value = null
  form.contract_id = null
}

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

async function saveNewFrameworkContract() {
  if (!newFrameworkForm.number.trim()) return
  newFrameworkSaving.value = true
  try {
    const created = await apiFetch<FrameworkContract>('/contracts/', {
      method: 'POST',
      body: {
        number: newFrameworkForm.number,
        date: newFrameworkForm.date || null,
        contract_type: form.purchase_contract_type,
        contractor_id: newFrameworkForm.contractor_id || null,
        subsidy_id: form.subsidy_id || null,
        subject: newFrameworkForm.subject || null,
        // `|| null` уже ловил '' (не было 422), но заменено на numOrNullZeroEmpty ради
        // единого источника истины (ПРАВИЛО №6) — предельная сумма рамочного договора
        // в группе «ноль бессмыслен» (владелец, 2026-09-04): '' и 0 обе → null.
        max_amount: numOrNullZeroEmpty(newFrameworkForm.max_amount),
        status: 'active',
      },
    })
    // Add contractor display info
    const ctrs = contractors.value.find(c => c.id === created.contractor_id)
    if (ctrs) { created.contractor_name = ctrs.name; created.contractor_inn = ctrs.inn }
    newFrameworkDialog.value = false
    selectFrameworkContract(created)
    newFrameworkForm.number = ''
    newFrameworkForm.date = ''
    newFrameworkForm.contractor_id = null
    newFrameworkForm.subject = ''
    newFrameworkForm.max_amount = null
  } catch (err: any) {
    const msg = err?.body?.message || err?.message || ''
    if (msg.includes('уже существует') || err?.status === 409) {
      showSnack(`${contractWord.value} с таким номером, контрагентом и датой уже существует`, 'warning')
    } else {
      showSnack('Ошибка создания договора', 'error')
    }
  } finally {
    newFrameworkSaving.value = false
  }
}

const totalNmck = computed(() =>
  items.value.reduce((s, i) => s + (i.total_price || 0), 0)
)

// Single purchase = contract_price auto-filled from items
const isSinglePurchase = computed(() =>
  !form.purchase_contract_type || form.purchase_contract_type === 'single'
)

// Is purchase in contracted+ status (НМЦД frozen)
const CONTRACTED_STATUSES = ['contracted', 'delivered', 'paid']
const isContracted = computed(() => CONTRACTED_STATUSES.includes(form.status))

// Saved НМЦД from DB (frozen value)
const savedNmck = ref<number | null>(null)

// Предупреждение о возможном повторе разовой закупки
const duplicateDialog = ref(false)
const duplicateMatches = ref<any[]>([])
let duplicateConfirmed = false
let duplicatePendingOverride = false

// Display НМЦД: manual override → frozen contracted value → live from items
const displayNmck = computed(() => {
  if (nmckMode.value === 'manual' && nmckManualValue.value != null) return nmckManualValue.value
  if (isContracted.value && savedNmck.value != null) return savedNmck.value
  return totalNmck.value
})

const nmckHint = computed(() => {
  if (isContracted.value && savedNmck.value != null) {
    return `Зафиксирована при заключении ${contractWordGen.value}. Не пересчитывается.`
  }
  return `Сумма всех позиций. Пересчитывается автоматически. Фиксируется при заключении ${contractWordGen.value}.`
})

const contractPriceHint = computed(() => {
  if (isSinglePurchase.value) {
    if (isContracted.value) {
      return 'Разовая закупка: = сумма текущих цен позиций (обновляется при изменении цен)'
    }
    return 'Разовая закупка: = сумма позиций (заполняется автоматически)'
  }
  return 'Рамочный договор: введите общую сумму договора вручную'
})

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

const monthlyTotal = computed(() => {
  if (form.monthly_payment_count && form.monthly_payment_amount) {
    return form.monthly_payment_count * form.monthly_payment_amount
  }
  return null
})

const calcMonthlyTotal = () => { /* reactivity trigger — monthlyTotal is computed */ }

const showSnack = (
  text: string,
  color: ToastType = 'success',
  opts?: { actionText?: string; onAction?: () => void; duration?: number },
) => {
  toast.addToast(text, color, opts)
}
const formatMoney = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
const formatSize = (bytes?: number) => !bytes ? '' : bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' МБ' : (bytes / 1024).toFixed(0) + ' КБ'
const formatDate = (dt?: string | null) => dt ? new Date(dt).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''

const fileIcon = (mime?: string) => {
  if (!mime) return 'mdi-file'
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime.startsWith('image/')) return 'mdi-file-image'
  if (mime.includes('word')) return 'mdi-file-word'
  return 'mdi-file'
}

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

const nmckExcessPct = computed(() => {
  const nmck = displayNmck.value
  if (!nmck || !form.contract_price) return 0
  return Math.round(((form.contract_price - nmck) / nmck) * 100)
})

const nmckWarningLevel = computed((): 'error' | 'warning' | null => {
  // For framework contracts, don't compare contract_price vs NMCD (they're different things)
  if (isFramework.value) return null
  const pct = nmckExcessPct.value
  if (pct > 10) return 'error'
  if (pct > 0) return 'warning'
  return null
})

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

const addContractorDialog = ref(false)
const addContractorForm = reactive({
  name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '',
  contact_person: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', org_type: '' as string,
  bank_name: '', bik: '', settlement_account: '', correspondent_account: '',
})
const addContractorSaving = ref(false)
const addContractorFile = ref<File | null>(null)
const addContractorImporting = ref(false)
const egrulDiffDialog = ref(false)
const egrulDiffItems = ref<{ key: string; label: string; old: string; new: string }[]>([])
const egrulDiffPending = ref<Record<string, string>>({})

function openAddContractor() {
  Object.assign(addContractorForm, { name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '', contact_person: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', org_type: 'Юридическое лицо', bank_name: '', bik: '', settlement_account: '', correspondent_account: '' })
  addContractorFile.value = null
  addContractorDialog.value = true
}

async function saveNewContractor() {
  if (!addContractorForm.name.trim()) return
  addContractorSaving.value = true
  try {
    const created = await apiFetch<Contractor>('/contractors/', { method: 'POST', body: { ...addContractorForm } })
    contractors.value.push(created)
    contractorsStore.putToCache(created)  // Phase 26-ZZ: и в Pinia cache для глобального resolve
    form.contractor_id = created.id
    contractorInn.value = created.inn || ''
    addContractorDialog.value = false
    showSnack('Контрагент добавлен')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    addContractorSaving.value = false
  }
}

async function importContractorFromFile() {
  if (!addContractorFile.value) return
  addContractorImporting.value = true
  try {
    const fd = new FormData()
    fd.append('file', addContractorFile.value)
    const res = await fetch('/api/contractors/import/preview', { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` }, body: fd })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    // Take first data row and try to fill form
    const headers = data.headers || []
    const sample = data.sample?.[0] || []
    const hints: Record<string, string[]> = {
      name: ['назван', 'наимен', 'name', 'органи'], inn: ['инн', 'inn'], kpp: ['кпп', 'kpp'],
      ogrn: ['огрн', 'ogrn'], address: ['адрес', 'address'], phone: ['телефон', 'phone'],
      email: ['email', 'mail'], contact_person: ['контакт', 'лицо'], signatory: ['подписант', 'директор'],
      bank_name: ['банк', 'bank'], bik: ['бик', 'bik'], settlement_account: ['расч', 'р/с'],
      correspondent_account: ['корр', 'к/с'],
    }
    for (const [field, kws] of Object.entries(hints)) {
      for (let i = 0; i < headers.length; i++) {
        const h = (headers[i] || '').toLowerCase()
        if (kws.some(k => h.includes(k)) && sample[i]) {
          (addContractorForm as any)[field] = String(sample[i]).trim()
          break
        }
      }
    }
    showSnack('Данные подтянуты из файла', 'info')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка чтения файла', 'error')
  } finally {
    addContractorImporting.value = false
  }
}

async function lookupContractorInn() {
  const inn = addContractorForm.inn?.trim()
  if (!inn || inn.length < 10) return
  try {
    const data = await apiFetch<any>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
    // Самозанятый: в ЕГРЮЛ/ЕГРИП его нет, реестр НПД отдаёт только статус
    if (data?._source === 'npd') {
      if (!addContractorForm.org_type) addContractorForm.org_type = 'Самозанятый'
      showSnack(data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`, 'warning')
      return
    }
    const FIELDS = [
      { key: 'name', label: 'Наименование' },
      { key: 'full_name', label: 'Полное наименование' },
      { key: 'kpp', label: 'КПП' },
      { key: 'ogrn', label: 'ОГРН' },
      { key: 'address', label: 'Адрес' },
      { key: 'signatory_last_name', label: 'Фамилия подписанта' },
      { key: 'signatory_first_name', label: 'Имя подписанта' },
      { key: 'signatory_middle_name', label: 'Отчество подписанта' },
      { key: 'signatory_position', label: 'Должность подписанта' },
      { key: 'phone', label: 'Телефон' },
      { key: 'email', label: 'Email' },
      { key: 'bank_name', label: 'Банк' },
      { key: 'bik', label: 'БИК' },
      { key: 'settlement_account', label: 'Расчётный счёт' },
      { key: 'correspondent_account', label: 'Корр. счёт' },
    ]
    const diffs: { key: string; label: string; old: string; new: string }[] = []
    const pending: Record<string, string> = {}
    for (const f of FIELDS) {
      const newVal = (data?.[f.key] || '').toString().trim()
      const curVal = ((addContractorForm as any)[f.key] || '').toString().trim()
      if (newVal && newVal !== curVal) {
        diffs.push({ key: f.key, label: f.label, old: curVal || '—', new: newVal })
        pending[f.key] = newVal
      }
    }
    if (diffs.length === 0) {
      showSnack('Данные ЕГРЮЛ совпадают с текущими', 'info')
      return
    }
    egrulDiffItems.value = diffs
    egrulDiffPending.value = pending
    egrulDiffDialog.value = true
  } catch (e: any) {
    if (e?.payload?.code === 'INN_NOT_FOUND') {
      showSnack(e.payload.message, 'warning')
    } else {
      showSnack(e?.message || 'Ошибка запроса к ФНС', 'error')
    }
  }
}

function applyEgrulDiff() {
  for (const k of Object.keys(egrulDiffPending.value)) {
    (addContractorForm as any)[k] = egrulDiffPending.value[k]
  }
  egrulDiffDialog.value = false
  showSnack('Данные обновлены из ЕГРЮЛ', 'success')
}

let _addContractorInnTimeout: any = null
function onAddContractorInnChange(val: string) {
  clearTimeout(_addContractorInnTimeout)
  const inn = (val || '').replace(/\D/g, '')
  if (inn.length === 10 || inn.length === 12) {
    _addContractorInnTimeout = setTimeout(() => lookupContractorInn(), 400)
  }
}

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
// Phase 21: multi-receipts on advance report
// ---------------------------------------------------------------------------
interface Receipt {
  id: number
  purchase_id: number
  fiscal_drive_number?: string | null
  fiscal_document_number?: number | null
  fiscal_sign?: string | null
  receipt_datetime?: string | null
  total_sum?: number | string | null
  seller_name?: string | null
  seller_inn?: string | null
  retail_place?: string | null
  operator?: string | null
  source?: string | null
  created_at?: string | null
}

const receipts = ref<Receipt[]>([])
const jsonReceiptInput = ref<HTMLInputElement | null>(null)

const manualReceiptDialog = reactive({
  show: false,
  saving: false,
  error: '',
  form: {
    fiscal_drive_number: '',
    fiscal_document_number: null as number | null,
    fiscal_sign: '',
    receipt_datetime: '',
    total_sum: null as number | null,
    seller_name: '',
    seller_inn: '',
    retail_place: '',
  },
})

function sourceLabel(s?: string | null) {
  if (!s) return '—'
  return ({ json_import: 'JSON', qr_scan: 'QR', manual: 'Вручную' } as Record<string, string>)[s] || s
}

async function loadReceipts() {
  if (!purchaseId.value) return
  try {
    receipts.value = await apiFetch<Receipt[]>(`/purchases/${purchaseId.value}/receipts`)
  } catch {
    /* silent — no receipts is fine */
  }
}

const qrScanShow = ref(false)
const POST_SAVE_ACTION_KEY = 'advance_report_post_save_action'

async function ensureSavedThen(action: 'scan_qr' | 'upload_json' | 'manual_receipt') {
  if (purchaseId.value) return true
  if (!form.subsidy_id && formMode.value !== 'advance_report') {
    showSnack('Сначала выберите субсидию (вверху страницы)', 'warning', {
      actionText: 'Показать поле',
      onAction: () => guideArrowTo('subsidy'),
    })
    guideArrowTo('subsidy')
    return false
  }
  sessionStorage.setItem(POST_SAVE_ACTION_KEY, action)
  await save()
  // save() либо успешно перенаправит (тогда после loadPurchase сработает action),
  // либо покажет snack с ошибкой валидации (FEO/etc) — флаг останется до следующей попытки.
  return false
}

async function onScanQrClick() {
  if (!(await ensureSavedThen('scan_qr'))) return
  qrScanShow.value = true
}

async function onJsonBtnClick() {
  if (!(await ensureSavedThen('upload_json'))) return
  document.querySelector<HTMLInputElement>('input[type=file][accept="image/*,.json"]')?.click()
}

async function onManualBtnClick() {
  if (!(await ensureSavedThen('manual_receipt'))) return
  openManualReceiptDialog()
}

const recomputeLoading = ref(false)
async function recomputeFromReceipts() {
  if (!purchaseId.value) return
  recomputeLoading.value = true
  try {
    const result = await apiFetch<any>(
      `/purchases/${purchaseId.value}/recompute-from-receipts`,
      { method: 'POST' }
    )
    const msg = `Обновлено позиций: ${result.items_updated}, прикреплено файлов чеков: ${result.files_attached}, добавлено записей закр.документов: ${result.acceptance_docs_added}`
    showSnack(msg, 'success')
    await loadPurchase()
  } catch (e: any) {
    showSnack(e?.message || 'Не удалось пересчитать', 'error')
  } finally {
    recomputeLoading.value = false
  }
}

function consumePostSaveAction() {
  if (!purchaseId.value) return
  if (formMode.value !== 'advance_report' && formMode.value !== 'order') return
  const pending = sessionStorage.getItem(POST_SAVE_ACTION_KEY)
  if (!pending) return
  sessionStorage.removeItem(POST_SAVE_ACTION_KEY)
  if (pending === 'scan_qr') qrScanShow.value = true
  else if (pending === 'upload_json') {
    document.querySelector<HTMLInputElement>('input[type=file][accept="image/*,.json"]')?.click()
  }
  else if (pending === 'manual_receipt') openManualReceiptDialog()
}

async function onQrDetected(qr: string) {
  qrScanShow.value = false
  if (!purchaseId.value) {
    showSnack('Сначала сохраните закупку', 'error')
    return
  }
  try {
    const existingIds = new Set(receipts.value.map(r => r.id))
    const created = await apiFetch<{ id: number }>(
      `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
      { method: 'POST', body: { qr } as any },
    )
    await loadReceipts()
    if (isEdit.value) {
      await new Promise(r => setTimeout(r, 50))
      await loadPurchase()
      console.log(`[advance] items refetched: ${items.value.length}, acceptance_docs: ${acceptanceDocs.value.length}`)
    }
    if (created?.id && existingIds.has(created.id)) {
      showSnack('Этот чек уже был загружен ранее', 'warning')
    } else {
      showSnack('Чек получен из ФНС, позиции добавлены')
    }
  } catch (e: any) {
    const p = e?.payload
    const code = p?.code
    const det = (p?.details && typeof p.details === 'object') ? p.details : null
    if (code === 'RECEIPT_DUPLICATE' && det?.purchase_id) {
      const ref = det.purchase_ref || `#${det.purchase_id}`
      const pid = det.purchase_id
      showSnack(
        p.message || `Чек был загружен ранее в закупку № ${ref}.`,
        'warning',
        { actionText: `Открыть закупку № ${ref}`, onAction: () => window.open(`/orders/${pid}`, '_blank') },
      )
    } else if (code === 'FNS_RATE_LIMIT') {
      showSnack(p?.message || 'ФНС временно ограничила запросы', 'warning')
    } else {
      showSnack(e?.message || 'Не удалось получить чек из ФНС', 'error')
    }
  }
}

async function onJsonReceiptUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length || !purchaseId.value) {
    if (input) input.value = ''
    return
  }
  const existingIds = new Set(receipts.value.map(r => r.id))
  let added = 0
  let dups = 0
  let qrFails = 0
  for (const f of files) {
    const isImage = (f.type || '').startsWith('image/') || /\.(png|jpe?g|webp|heic|heif)$/i.test(f.name)
    try {
      if (isImage) {
        const qr = await decodeQrFromImageFile(f)
        if (!qr) { qrFails++; continue }
        const r = await apiFetch<Receipt>(
          `/purchases/${purchaseId.value}/receipts/from-qr-fetch`,
          { method: 'POST', body: { qr } as any },
        )
        if (r?.id != null) {
          if (existingIds.has(r.id)) dups++
          else { added++; existingIds.add(r.id) }
        }
      } else {
        const fd = new FormData()
        fd.append('file', f)
        const res = await apiFetch<Receipt[]>(
          `/purchases/${purchaseId.value}/receipts/import-json`,
          { method: 'POST', body: fd as any }
        )
        for (const r of (res || [])) {
          if (existingIds.has(r.id)) dups++
          else { added++; existingIds.add(r.id) }
        }
      }
    } catch (err: any) {
      const p2 = err?.payload
      const code2 = p2?.code
      const det2 = (p2?.details && typeof p2.details === 'object') ? p2.details : null
      if (code2 === 'RECEIPT_DUPLICATE' && det2?.purchase_id) {
        const ref2 = det2.purchase_ref || `#${det2.purchase_id}`
        const pid2 = det2.purchase_id
        showSnack(
          p2.message || `Чек был загружен ранее в закупку № ${ref2}.`,
          'warning',
          { actionText: `Открыть закупку № ${ref2}`, onAction: () => window.open(`/orders/${pid2}`, '_blank') },
        )
      } else if (code2 === 'FNS_RATE_LIMIT') {
        showSnack(p2?.message || 'ФНС временно ограничила запросы', 'warning')
      } else {
        showSnack(err?.message || `Ошибка обработки ${f.name}`, 'error')
      }
    }
  }
  input.value = ''
  await loadReceipts()
  if (isEdit.value && purchaseId.value) {
    await new Promise(r => setTimeout(r, 50))
    await loadPurchase()
    console.log(`[advance] items refetched: ${items.value.length}, acceptance_docs: ${acceptanceDocs.value.length}`)
  }
  const parts: string[] = []
  if (added) parts.push(`добавлено: ${added}`)
  if (dups) parts.push(`уже было: ${dups}`)
  if (qrFails) parts.push(`QR не распознан: ${qrFails}`)
  if (parts.length) showSnack(parts.join(', '), qrFails && !added ? 'warning' : 'success')
}

function openManualReceiptDialog() {
  manualReceiptDialog.error = ''
  manualReceiptDialog.form = {
    fiscal_drive_number: '',
    fiscal_document_number: null,
    fiscal_sign: '',
    receipt_datetime: '',
    total_sum: null,
    seller_name: '',
    seller_inn: '',
    retail_place: '',
  }
  manualReceiptDialog.show = true
}

async function saveManualReceipt() {
  if (!purchaseId.value) return
  manualReceiptDialog.saving = true
  manualReceiptDialog.error = ''
  try {
    const payload: any = { source: 'manual' }
    const f = manualReceiptDialog.form
    if (f.fiscal_drive_number) payload.fiscal_drive_number = f.fiscal_drive_number
    // fiscal_document_number/total_sum — v-model.number; `!= null` не ловит '' после
    // очистки поля. При null поле в payload не попадает вовсе (как и раньше для
    // остальных необязательных полей формы). fiscal_document_number — номер документа
    // чека, не сумма/количество (0 в номере документа не встречается на практике, но
    // это не из явного списка «ноль бессмыслен» владельца) — оставлен на numOrNull.
    // total_sum — итоговая сумма чека (деньги) → numOrNullZeroEmpty (2026-09-04,
    // владелец: «0 тоже значит, что ничего нет»).
    const fiscalDocNumber = numOrNull(f.fiscal_document_number)
    if (fiscalDocNumber != null) payload.fiscal_document_number = fiscalDocNumber
    if (f.fiscal_sign) payload.fiscal_sign = f.fiscal_sign
    if (f.receipt_datetime) payload.receipt_datetime = f.receipt_datetime
    const totalSum = numOrNullZeroEmpty(f.total_sum)
    if (totalSum != null) payload.total_sum = totalSum
    if (f.seller_name) payload.seller_name = f.seller_name
    if (f.seller_inn) payload.seller_inn = f.seller_inn
    if (f.retail_place) payload.retail_place = f.retail_place
    await apiFetch(`/purchases/${purchaseId.value}/receipts`, {
      method: 'POST',
      body: JSON.stringify(payload) as any,
    })
    manualReceiptDialog.show = false
    await loadReceipts()
    showSnack('Чек добавлен')
  } catch (e: any) {
    manualReceiptDialog.error = e?.message || 'Ошибка сохранения'
  } finally {
    manualReceiptDialog.saving = false
  }
}

async function deleteReceipt(id: number) {
  if (!purchaseId.value) return
  if (!confirm('Удалить чек? Связанные позиции в закупке останутся.')) return
  try {
    await apiFetch(`/purchases/${purchaseId.value}/receipts/${id}`, { method: 'DELETE' })
    await loadReceipts()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка удаления', 'error')
  }
}

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
        // numOrNullZeroEmpty (2026-09-04, владелец: «0 тоже значит, что ничего нет» —
        // цена за единицу и количество в группе «ноль бессмыслен»), заменил локальную
        // проверку `!== '' && != null ? v : null` (ПРАВИЛО №6, один источник истины).
        unit_price: numOrNullZeroEmpty(rest.unit_price),
        quantity: numOrNullZeroEmpty(rest.quantity),
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
      // numOrNull — единый хелпер (2026-09-04); деньги/суммы (contract_price/
      // payment_amount/payment_federal/monthly_payment_amount) переведены на
      // numOrNullZeroEmpty — 0 там бессмыслен (владелец, 2026-09-04, «0 тоже значит,
      // что ничего нет»). vat_rate/price_increase/сроки в днях/пеня/аванс/monthly_
      // payment_count остаются numOrNull — там 0 реальное значение.
      contract_price: numOrNullZeroEmpty(form.contract_price),
      vat_rate: numOrNull(form.vat_rate),
      payment_amount: numOrNullZeroEmpty(form.payment_amount),
      payment_federal: numOrNullZeroEmpty(form.payment_federal),
      price_increase: numOrNull(form.price_increase),
      acceptance_term_days: numOrNull(form.acceptance_term_days),
      penalty_rate: numOrNull(form.penalty_rate),
      advance_amount: numOrNull(form.advance_amount),
      warranty_period_days: numOrNull(form.warranty_period_days),
      monthly_payment_count: numOrNull(form.monthly_payment_count),
      monthly_payment_amount: numOrNullZeroEmpty(form.monthly_payment_amount),
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
      // арифметика по amount ловит NaN/'0'). Сумма документа приёмки — деньги, группа
      // «ноль бессмыслен» (владелец, 2026-09-04) → numOrNullZeroEmpty приводит перед отправкой.
      acceptance_docs: acceptanceDocs.value
        .filter(d => d.name?.trim() || d.number?.trim() || d.date?.trim() || (d.amount !== null && d.amount !== undefined))
        .map(d => ({ ...d, amount: numOrNullZeroEmpty(d.amount) })),
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

const EDITABLE_MIME = new Set([
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
])

// File upload
const uploadFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !purchaseId.value) return
  uploadDialog.value = false
  uploading.value = true
  try {
    const file = input.files[0]
    // Auto-detect doc_format: only Word/Excel can be editable
    const resolvedFormat = EDITABLE_MIME.has(file.type) ? uploadDocFormat.value : 'scan'
    const fd = new FormData()
    fd.append('file', file)
    fd.append('file_type', uploadFileType.value)
    fd.append('doc_format', resolvedFormat)
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      let detail = `Ошибка загрузки (${res.status})`
      try { const err = await res.json(); detail = err.detail || err.message || detail } catch {}
      showSnack(detail, 'error')
      return
    }
    const uploaded = await res.json()
    uploadedFiles.value.push(uploaded)
    showSnack('Файл загружен')
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки файла', 'error')
  } finally {
    uploading.value = false
    if (fileInputEl.value) fileInputEl.value.value = ''
  }
}

// Единая точка загрузки файлов закупки с заданным file_type — используется и
// плитками drag-n-drop (Документы к закупке), и кнопкой «Загрузить» в разделе
// «Платёж», и кликом по плитке (открывает системный выбор файла с тем же типом).
async function uploadFilesForType(files: File[], fileType: string) {
  if (!purchaseId.value || !files.length) return
  uploading.value = true
  pendingSectionUpload.value = fileType
  try {
    for (const file of files) {
      const resolvedFormat = EDITABLE_MIME.has(file.type) ? 'editable' : 'scan'
      const fd = new FormData()
      fd.append('file', file)
      fd.append('file_type', fileType)
      fd.append('doc_format', resolvedFormat)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!res.ok) {
        let detail = `Ошибка загрузки (${res.status})`
        try { const err = await res.json(); detail = err.detail || err.message || detail } catch {}
        showSnack(`${file.name}: ${detail}`, 'error')
        continue
      }
      const uploaded = await res.json()
      // Backend деактивирует прежние файлы того же типа при загрузке — синхронизируем оптимистично
      const ft = uploaded.file_type
      uploadedFiles.value.forEach(f => { if (f.file_type === ft) f.is_active = false })
      uploadedFiles.value.push(uploaded)
    }
    showSnack(files.length > 1 ? `Загружено файлов: ${files.length}` : 'Файл загружен')
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки файлов', 'error')
  } finally {
    uploading.value = false
    pendingSectionUpload.value = null
  }
}

async function onAcceptanceDocFilesDropped(files: File[]) {
  if (!isEdit.value) return
  await uploadFilesForType(files, 'other')
}

function uploadForSection(section: string) {
  pendingSectionUpload.value = section as any
  sectionFileInputEl.value?.click()
}

async function toggleFileActive(f: UploadedFile) {
  const newActive = !(f.is_active ?? true)
  const token = localStorage.getItem('auth_token')
  const fd = new FormData()
  fd.append('is_active', String(newActive))
  try {
    const res = await fetch(`/api/purchases/${f.purchase_id}/files/${f.id}`, {
      method: 'PATCH', headers: { Authorization: `Bearer ${token}` }, body: fd,
    })
    if (res.ok) {
      f.is_active = newActive
    }
  } catch { /* skip */ }
}

const uploadSectionFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !purchaseId.value) return
  const file = input.files[0]
  const fileType = pendingSectionUpload.value || 'other'
  input.value = ''
  await uploadFilesForType([file], fileType)
}

const downloadFile = async (fid: number, filename: string) => {
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fid}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// File preview
const previewDialog = ref(false)
const previewFile = ref<UploadedFile | null>(null)
const previewUrl = ref('')

const isPreviewable = (mime?: string) => mime === 'application/pdf' || !!mime?.startsWith('image/')

const openPreview = async (f: UploadedFile) => {
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/purchases/${purchaseId.value}/files/${f.id}/view`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Ошибка открытия файла', 'error'); return }
  const blob = await res.blob()
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(blob)
  previewFile.value = f
  previewDialog.value = true
}

const deleteFile = async (fid: number) => {
  try {
    await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
    uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
    showSnack('Файл удалён')
  } catch {
    showSnack('Ошибка удаления', 'error')
  }
}

const copyDocError = async () => {
  if (!docErrorInfo.value) return
  const i = docErrorInfo.value as any
  const lines = [
    'Ошибка генерации документа',
    `Покупка: #${purchaseId.value} (субсидия id=${form.subsidy_id ?? '—'})`,
    `Шаблон: ${i.template ?? ''} (${i.template_source ?? ''})`,
    `Код: ${i.code ?? ''}${i.correlation_id ? ` · correlation_id=${i.correlation_id}` : ''}`,
    `Класс: ${i.error_class ?? ''}`,
    '',
    'Сообщение:',
    i.message ?? '',
    '',
    'Сырой текст:',
    i.error_raw ?? '',
  ]
  if (i.hint) {
    lines.push('', 'Подсказка:', i.hint)
  }
  if (i.traceback) {
    lines.push('', 'Traceback:', String(i.traceback).slice(0, 4000))
  }
  const txt = lines.join('\n')
  try {
    await navigator.clipboard.writeText(txt)
    showSnack('Текст ошибки скопирован в буфер обмена', 'success', { duration: 2500 })
  } catch {
    // Fallback для http-контекста или ограничений permission
    try {
      const ta = document.createElement('textarea')
      ta.value = txt
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      showSnack('Текст ошибки скопирован', 'success', { duration: 2500 })
    } catch {
      showSnack('Не удалось скопировать. Выделите текст в блоке «Технические детали» и Ctrl+C', 'error')
    }
  }
}

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

// ── Фабрикант: пакет документов (ZIP) ────────────────────────────────────────
async function downloadFabrikantPackage() {
  if (!purchaseId.value) return
  docLoading.value = 'fabrikant_package'
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/fabrikant-package`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      const d = err?.details || err?.detail
      if (err?.code) {
        const info: any = {
          code: err.code,
          message: err.message || 'Ошибка формирования пакета документов',
          correlation_id: err.correlation_id,
        }
        if (d && typeof d === 'object') Object.assign(info, d)
        else if (typeof d === 'string') info.error_raw = d
        docErrorInfo.value = info
        docErrorDialog.value = true
      } else {
        showSnack(err?.message || 'Ошибка формирования пакета документов', 'error')
      }
      return
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    let filename = `Фабрикант_закупка_${purchaseId.value}.zip`
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
    showSnack('Ошибка скачивания пакета документов', 'error')
  } finally {
    docLoading.value = null
  }
}

// ── Фабрикант: override-файлы пакета ────────────────────────────────────────
const fabrikantFileInputEl = ref<HTMLInputElement | null>(null)
const fabrikantPendingFt = ref<string>('')

function fabrikantOverride(ft: string): UploadedFile | undefined {
  return uploadedFiles.value.find(f => f.file_type === ft && f.is_active !== false)
}

function triggerFabrikantUpload(ft: string) {
  fabrikantPendingFt.value = ft
  fabrikantFileInputEl.value?.click()
}

const uploadFabrikantOverride = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !purchaseId.value) return
  uploading.value = true
  try {
    const file = input.files[0]
    const docFormat = EDITABLE_MIME.has(file.type) ? 'editable' : 'scan'
    const fd = new FormData()
    fd.append('file', file)
    fd.append('file_type', fabrikantPendingFt.value)
    fd.append('doc_format', docFormat)
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      let detail = `Ошибка загрузки (${res.status})`
      try { const err = await res.json(); detail = err.detail || err.message || detail } catch {}
      showSnack(detail, 'error')
      return
    }
    const uploaded: UploadedFile = await res.json()
    const ft = uploaded.file_type
    uploadedFiles.value.forEach(f => { if (f.file_type === ft) f.is_active = false })
    uploadedFiles.value.push(uploaded)
    showSnack('Файл загружен — будет использован вместо шаблона')
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки файла', 'error')
  } finally {
    uploading.value = false
    fabrikantPendingFt.value = ''
    if (input) input.value = ''
  }
}

const deleteFabrikantOverride = async (fid: number) => {
  try {
    await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
    uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
    showSnack('Override удалён — будет использоваться шаблон')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка удаления', 'error')
  }
}

// ── КП (Запрос коммерческих предложений) ─────────────────────────────────────
const kpDialog      = ref(false)
const kpSelected    = ref<number[]>([])
const kpIntroText   = ref('')
const kpDeliveryDate = ref('')
const kpItemsLoading = ref(false)
const kpFreeRecipients = ref<{ name: string; email: string }[]>([])
const kpEditEmailId  = ref<number | null>(null)
const kpEditEmailValue = ref('')
const kpSavingEmail  = ref(false)
const kpSaving       = ref(false)
const kpSendingAll   = ref(false)

const kpAllEmails = computed(() => {
  const emails: string[] = []
  for (const cid of kpSelected.value) {
    const c = kpContractorList.value.find(c => c.id === cid)
    if (c?.email) emails.push(c.email)
  }
  for (const fr of kpFreeRecipients.value) {
    if (fr.email.trim()) emails.push(fr.email.trim())
  }
  return emails
})

interface ContractorKp {
  id: number; name: string; email?: string
  product_categories: string[]
}
interface KpItem {
  id: number; item_name: string; quantity: number; unit: string
  unit_price: number; category: string | null
}

const kpContractorList = ref<ContractorKp[]>([])
const kpItems = ref<KpItem[]>([])

const kpContractorOptions = computed(() =>
  kpContractorList.value.map(c => ({
    id: c.id,
    label: c.email ? `${c.name} <${c.email}>` : `${c.name} (нет email)`,
  }))
)

/** Items matching a contractor's categories. If contractor has no categories → all items. */
function kpItemsForContractor(cid: number): KpItem[] {
  const contractor = kpContractorList.value.find(c => c.id === cid)
  if (!contractor) return kpItems.value
  const cats = contractor.product_categories
  if (!cats.length) return kpItems.value  // no categories known → send all
  return kpItems.value.filter(item => item.category && cats.includes(item.category))
}

function buildContractorEmail(cid: number): string {
  const contractor = kpContractorList.value.find(c => c.id === cid)
  if (!contractor) return ''
  const items = kpItemsForContractor(cid)
  const subject = form.subject || form.item_name || '—'
  const delivery = kpDeliveryDate.value || form.execution_term || '—'
  const intro = kpIntroText.value || 'Просим Вас направить коммерческое предложение на поставку товаров.'

  const itemLines = items.map((it, i) =>
    `${i + 1}. ${it.item_name}${it.category ? ` [${it.category}]` : ''} — ${it.quantity} ${it.unit}`
  ).join('\n')

  return `Уважаемые коллеги,

${intro}

Закупка: ${subject}
Срок поставки: ${delivery}

Перечень товаров (${items.length} поз.):
${itemLines || '— (товары не указаны)'}

Просим указать в КП:
— наименование и характеристики товара;
— стоимость за единицу и общую стоимость;
— срок поставки;
— гарантийные обязательства.

С уважением`
}

function kpStartEditEmail(cid: number) {
  kpEditEmailId.value = cid
  kpEditEmailValue.value = kpContractorList.value.find(c => c.id === cid)?.email || ''
}

async function kpSaveEmail(cid: number) {
  if (!kpEditEmailValue.value.trim()) return
  kpSavingEmail.value = true
  try {
    await apiFetch(`/contractors/${cid}/email`, {
      method: 'PATCH',
      body: { email: kpEditEmailValue.value.trim() },
    })
    const c = kpContractorList.value.find(c => c.id === cid)
    if (c) c.email = kpEditEmailValue.value.trim()
    kpEditEmailId.value = null
    showSnack('Email контрагента сохранён')
  } catch (e: any) {
    showSnack('Ошибка сохранения email', 'error')
  } finally {
    kpSavingEmail.value = false
  }
}

function openMailtoFree(fr: { name: string; email: string }) {
  if (!fr.email) return
  const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
  const body = encodeURIComponent(buildGenericEmail())
  window.open(`mailto:${fr.email}?subject=${subject}&body=${body}`, '_blank')
}

function copyFreeEmail(fr: { name: string; email: string }) {
  navigator.clipboard.writeText(buildGenericEmail()).then(
    () => showSnack('Текст письма скопирован', 'success', { duration: 2500 }),
    () => showSnack('Не удалось скопировать', 'error')
  )
}

function buildGenericEmail(): string {
  const subject = form.subject || form.item_name || '—'
  const delivery = kpDeliveryDate.value || form.execution_term || '—'
  const intro = kpIntroText.value || 'Просим Вас направить коммерческое предложение на поставку товаров.'
  const itemLines = kpItems.value.map((it, i) =>
    `${i + 1}. ${it.item_name} — ${it.quantity} ${it.unit}`
  ).join('\n')
  return `Уважаемые коллеги,\n\n${intro}\n\nЗакупка: ${subject}\nСрок поставки: ${delivery}\n\nПеречень товаров (${kpItems.value.length} поз.):\n${itemLines || '— (товары не указаны)'}\n\nС уважением`
}

async function openKpDialog() {
  kpDialog.value = true
  kpIntroText.value = ''
  kpDeliveryDate.value = form.execution_term || ''
  kpFreeRecipients.value = []
  kpEditEmailId.value = null

  // Load contractors with product categories
  if (!kpContractorList.value.length) {
    try {
      const list = await apiFetch<any[]>('/contractors/with-stats')
      kpContractorList.value = list.map((c: any) => ({
        id: c.id, name: c.name, email: c.email || '',
        product_categories: c.product_categories || [],
      }))
      if (form.contractor_id) kpSelected.value = [form.contractor_id]
    } catch { showSnack('Ошибка загрузки контрагентов', 'error') }
  }

  // Load purchase items with categories
  if (purchaseId.value && !kpItems.value.length) {
    kpItemsLoading.value = true
    try {
      kpItems.value = await apiFetch<KpItem[]>(`/purchases/${purchaseId.value}/kp-items`)
    } catch { showSnack('Ошибка загрузки позиций', 'error') }
    finally { kpItemsLoading.value = false }
  }
}

function openMailtoForContractor(cid: number) {
  const contractor = kpContractorList.value.find(c => c.id === cid)
  if (!contractor?.email) return
  const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
  const body = encodeURIComponent(buildContractorEmail(cid))
  window.open(`mailto:${contractor.email}?subject=${subject}&body=${body}`, '_blank')
}

function copyContractorEmail(cid: number) {
  navigator.clipboard.writeText(buildContractorEmail(cid)).then(
    () => showSnack('Текст письма скопирован', 'success', { duration: 2500 }),
    () => showSnack('Не удалось скопировать', 'error')
  )
}

function sendAllKp() {
  // Opens mailto: as fallback
  const emails = kpAllEmails.value
  if (!emails.length) return
  const subject = encodeURIComponent(`Запрос КП: ${form.subject || form.item_name || 'закупка'}`)
  const body = encodeURIComponent(buildGenericEmail())
  const [first, ...rest] = emails
  const bcc = rest.length ? `&bcc=${encodeURIComponent(rest.join(','))}` : ''
  window.open(`mailto:${first}?subject=${subject}${bcc}&body=${body}`, '_blank')
}

async function sendAllKpViaApi() {
  kpSendingAll.value = true
  try {
    // Auto-save КП request before sending if purchase exists
    if (purchaseId.value) {
      const validFree = kpFreeRecipients.value.filter(r => r.email.trim())
      try {
        await apiFetch('/commercial-requests/', {
          method: 'POST',
          body: {
            purchase_id: purchaseId.value,
            subject: `Запрос КП: ${form.subject || form.item_name || ''}`.trim(),
            intro_text: kpIntroText.value || null,
            delivery_date: kpDeliveryDate.value || null,
            recipient_ids: kpSelected.value,
            free_recipients: validFree.length ? validFree.map(r => ({ name: r.name || null, email: r.email })) : null,
          },
        })
      } catch { /* silent — save failure shouldn't block send */ }
    }

    // Build recipients list
    const recipients: { name: string | null; email: string }[] = []
    for (const cid of kpSelected.value) {
      const c = kpContractorList.value.find(c => c.id === cid)
      if (c?.email) recipients.push({ name: c.name, email: c.email })
    }
    for (const fr of kpFreeRecipients.value) {
      if (fr.email.trim()) recipients.push({ name: fr.name || null, email: fr.email.trim() })
    }
    if (!recipients.length) {
      showSnack('Нет получателей с email', 'warning')
      return
    }

    const result = await apiFetch<{ sent: number; failed: { email: string; error: string }[] }>(
      '/commercial-requests/send',
      {
        method: 'POST',
        body: {
          recipients,
          subject: `Запрос КП: ${form.subject || form.item_name || 'закупка'}`,
          body: buildGenericEmail(),
        },
      }
    )

    if (result.failed.length) {
      showSnack(`Отправлено: ${result.sent}, ошибки: ${result.failed.length}`, 'warning')
    } else {
      showSnack(`Отправлено ${result.sent} письмо(а)`)
      kpDialog.value = false
    }
  } catch (e: any) {
    const msg = e.message || 'Ошибка отправки'
    if (msg.includes('SMTP не настроен')) {
      showSnack('SMTP не настроен. Перейдите в Настройки организации → Email.', 'error')
    } else {
      showSnack(msg, 'error')
    }
  } finally {
    kpSendingAll.value = false
  }
}

async function saveKpRequest() {
  if (!purchaseId.value) return
  kpSaving.value = true
  try {
    const validFree = kpFreeRecipients.value.filter(r => r.email.trim())
    await apiFetch('/commercial-requests/', {
      method: 'POST',
      body: {
        purchase_id: purchaseId.value,
        subject: `Запрос КП: ${form.subject || form.item_name || ''}`.trim(),
        intro_text: kpIntroText.value || null,
        delivery_date: kpDeliveryDate.value || null,
        recipient_ids: kpSelected.value,
        free_recipients: validFree.length ? validFree.map(r => ({ name: r.name || null, email: r.email })) : null,
      },
    })
    showSnack('Запрос КП сохранён в реестре')
    kpDialog.value = false
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    kpSaving.value = false
  }
}

async function downloadKpXlsx() {
  if (!purchaseId.value) return
  try {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
    const resp = await fetch(`/api/documents/purchases/${purchaseId.value}/kp-xlsx`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!resp.ok) throw new Error('error')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Сравнение_КП_закупка_${purchaseId.value}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    showSnack('Ошибка загрузки xlsx', 'error')
  }
}
</script>

<style scoped>
/* «Заметный сигнал превышения» — по образцу .feo-excess-culprit в SubsidiesView.vue
   (сознательно крупнее и контрастнее .feo-plan-note — задача владельца, сессия
   2026-08-21: «в карточке закупки видно превышение»). Scoped-стиль, дублируется
   как и остальные per-view карточки в этом проекте (не вынесен в общий CSS, т.к.
   применяется только к заголовку карточки закупки). */
.feo-excess-culprit {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  font-size: 13px; font-weight: 700; line-height: 1.4; white-space: normal;
  color: #7f1d1d; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 6px; padding: 6px 10px; max-width: 100%;
}

/* Владелец (2026-09-02): «алярм» расхождения категории ФЭО шапка/товар/план —
   по образцу .purchase-stopped-banner (OrdersView.vue), но предупреждающий
   (амбер), т.к. красный там занят остановкой закупки. Держится, пока
   purchaseData.feo_mismatch=true — не самозакрывающийся снэкбар. */
.feo-mismatch-banner {
  width: 100%;
  border: 2px solid #b45309;
  background: #fffbeb;
  color: #7c2d12;
  border-radius: 6px;
  padding: 10px 14px;
}
.feo-mismatch-banner__head {
  display: flex;
  align-items: center;
}
.feo-mismatch-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.feo-mismatch-banner__hint {
  font-size: 0.8rem;
  font-weight: 500;
  margin-top: 2px;
  opacity: 0.92;
}
.feo-mismatch-banner__list {
  margin: 6px 0 0;
  padding-left: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.feo-mismatch-banner__list li {
  margin-bottom: 2px;
}
.doc-upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .doc-upload-grid {
    grid-template-columns: 1fr;
  }
}
.doc-upload-tile-inner {
  width: 100%;
  display: flex;
  flex-direction: column;
}
.doc-upload-tile-inner--dragging {
  transform: scale(1.01);
}
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

/* pub-pointer / pub-glow — указатель на целевые поля из диалога публикации */
.pub-pointer {
  position: absolute;
  top: -42px;
  left: 50%;
  margin-left: -16px;
  width: 32px;
  height: 36px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  pointer-events: none;
  z-index: 30;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.35));
  animation: pub-pointer-wiggle 0.9s ease-in-out infinite;
}
.pub-pointer .mdi {
  font-size: 30px;
  color: #fb923c;
  line-height: 1;
}
@keyframes pub-pointer-wiggle {
  0%   { transform: translateY(0)    rotate(-10deg); }
  25%  { transform: translateY(-6px) rotate(10deg); }
  50%  { transform: translateY(0)    rotate(-8deg); }
  75%  { transform: translateY(-4px) rotate(8deg); }
  100% { transform: translateY(0)    rotate(-10deg); }
}
.pub-glow {
  border-radius: 6px;
  animation: pub-match-glow 1.2s ease-in-out infinite;
}
@keyframes pub-match-glow {
  0%, 100% { box-shadow: 0 0 0 4px rgba(251,146,60,0.20), 0 0 16px 2px rgba(251,146,60,0.45); }
  50%      { box-shadow: 0 0 0 6px rgba(251,146,60,0.35), 0 0 30px 8px rgba(251,146,60,0.75); }
}
</style>
