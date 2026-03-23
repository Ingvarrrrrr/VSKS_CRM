<template>
  <v-container fluid class="pa-6" style="max-width:1600px">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">
          {{ pageTitle }}
        </h1>
        <div class="d-flex align-center gap-2 mt-1">
          <v-chip v-if="isEdit && form.status" :color="STATUS_COLOR[form.status]" size="small" variant="tonal">
            {{ STATUS_LABEL[form.status] }}
          </v-chip>
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

    <v-alert v-if="budgetInfo" :type="budgetInfo.exceeded ? 'error' : 'info'" variant="tonal" class="mb-4" density="compact">
      <template v-if="budgetInfo.exceeded">
        Превышение бюджета субсидии на <strong>{{ formatMoney(budgetInfo.over) }}</strong>
      </template>
      <template v-else>
        Остаток бюджета субсидии: <strong>{{ formatMoney(budgetInfo.remaining) }}</strong>
      </template>
    </v-alert>

    <v-form ref="formRef" @submit.prevent="save">

      <!-- 1. Основная информация -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Основная информация</v-card-title>
        <v-card-text>
          <v-row>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="2">
              <v-select v-model="form.purchase_method"
                :items="[{value:'single',title:'Единственный поставщик'},{value:'competitive',title:'Конкурсная процедура'},{value:'advance',title:'Авансовый отчёт'}]"
                item-title="title" item-value="value" label="Способ закупки" variant="outlined" density="compact"
                hint="Как выбирается поставщик" persistent-hint />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="2">
              <v-select v-model="form.item_type"
                :items="[{value:'товар',title:'Поставка товара'},{value:'услуга',title:'Оказание услуг'},{value:'mixed',title:'Поставка товаров и услуг'}]"
                item-title="title" item-value="value" label="Тип закупки" variant="outlined" density="compact"
                hint="Выберите тип закупки" persistent-hint />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="2">
              <v-select v-model="form.purchase_basis" clearable
                :items="[{value:'plan_schedule',title:'План-график'},{value:'service_note',title:'Служебная записка'}]"
                item-title="title" item-value="value" label="Основание закупки" variant="outlined" density="compact"
                hint="Документ-основание для закупки" persistent-hint />
            </v-col>

            <v-col cols="12" md="3">
              <v-select v-model="form.subsidy_id" :items="subsidies" item-title="name" item-value="id"
                label="Субсидия *" variant="outlined" density="compact"
                hint="По какой субсидии финансируется закупка" persistent-hint
                :rules="[r => !!r || 'Выберите субсидию']" @update:model-value="onSubsidyChange" />
            </v-col>
            <v-col v-if="isSectionVisible('contractor')" cols="12" md="3">
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
                :menu-props="{ maxWidth: 500 }"
                hint="Поставщик/исполнитель. Поиск по названию или ИНН" persistent-hint
                @update:model-value="onContractorSelect"
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
              </v-autocomplete>
            </v-col>
            <v-col v-if="isSectionVisible('contractor')" cols="12" md="2">
              <v-text-field
                v-model="contractorInn"
                label="ИНН"
                variant="outlined"
                density="compact"
                maxlength="12"
                hint="Введите ИНН — контрагент подставится автоматически" persistent-hint
                @update:model-value="onInnInput"
              />
            </v-col>
            <v-col v-if="formMode !== 'service_note_delivery'" cols="12" md="4">
              <v-text-field
                v-model="form.subject"
                :label="formMode === 'advance_report' ? 'Предмет авансового' : 'Предмет договора'"
                variant="outlined"
                density="compact"
                placeholder="Поставка оборудования..."
                hint="Краткое описание: что закупается" persistent-hint
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-autocomplete
                v-model="form.responsible_person"
                :items="orgUsersList"
                item-title="full_name"
                item-value="full_name"
                label="Ответственный исполнитель"
                variant="outlined"
                density="compact"
                clearable
                hide-no-data
                hint="Необязательное поле"
                persistent-hint
                autocomplete="off"
              />
            </v-col>
            <!-- FEO level 1 — появляется после выбора субсидии -->
            <v-col v-if="form.subsidy_id && feoLevel1Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo1" :items="feoLevel1Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.1) *" variant="outlined" density="compact" clearable
                hint="Направление расходования средств" persistent-hint
                :error-messages="feoSaveAttempted && !selectedFeo1 ? 'Обязательное поле' : ''"
                @update:model-value="onFeo1Change" />
            </v-col>
            <!-- FEO level 2 — появляется после выбора ур.1 -->
            <v-col v-if="selectedFeo1 && feoLevel2Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo2" :items="feoLevel2Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.2) *" variant="outlined" density="compact" clearable
                :error-messages="feoSaveAttempted && !selectedFeo2 ? 'Выберите уточняющую категорию' : ''"
                @update:model-value="onFeo2Change" />
            </v-col>
            <!-- FEO level 3 — появляется после выбора ур.2 -->
            <v-col v-if="selectedFeo2 && feoLevel3Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo3" :items="feoLevel3Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.3) *" variant="outlined" density="compact" clearable
                :error-messages="feoSaveAttempted && !selectedFeo3 ? 'Выберите уточняющую категорию' : ''"
                @update:model-value="onFeo3Change" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.registry_number" label="Реестровый номер"
                variant="outlined" density="compact" :readonly="!isEdit"
                :bg-color="!isEdit ? 'grey-lighten-4' : undefined"
                hint="Генерируется автоматически" persistent-hint />
            </v-col>
            <!-- Мероприятие (после выбора субсидии, или всегда для служебных записок) -->
            <v-col v-if="(form.subsidy_id && filteredEvents.length) || formMode === 'service_note_delivery'" cols="12" md="4">
              <v-select
                v-model="form.event_id"
                :items="filteredEvents"
                item-title="name" item-value="id"
                label="Мероприятие"
                variant="outlined" density="compact"
                clearable
                hint="К какому мероприятию относится закупка" persistent-hint
              />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 2. Позиции закупки -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center justify-space-between">
          <span>{{ formMode === 'service_note_delivery' ? 'Оборудование для выдачи' : 'Позиции закупки' }}</span>
          <div class="d-flex align-center ga-2">
            <v-chip v-if="isContracted && savedNmck" color="orange" variant="tonal" size="small" title="Зафиксирована при заключении договора">
              НМЦК (фикс.): {{ formatMoney(savedNmck) }}
            </v-chip>
            <v-chip color="primary" variant="tonal" size="small">
              {{ isContracted ? 'Текущая сумма' : 'НМЦК' }}: {{ formatMoney(displayNmck) }}
            </v-chip>
          </div>
        </v-card-title>
        <v-card-text>
          <div class="overflow-x-auto">
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="min-width:420px">Наименование</th>
                  <th style="min-width:180px">Тип</th>
                  <th style="min-width:140px">Кол-во</th>
                  <th style="min-width:140px">Ед. изм.</th>
                  <th style="min-width:150px">Цена ед., ₽</th>
                  <th style="min-width:150px">Сумма, ₽</th>
                  <th style="min-width:150px">Страна происхождения</th>
                  <th style="width:48px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in items" :key="idx">
                  <td style="min-width:420px">
                    <div class="d-flex align-center gap-1">
                      <!-- Mini thumbnail in row -->
                      <v-tooltip v-if="item._photo_url" location="right">
                        <template #activator="{ props: tip }">
                          <v-avatar v-bind="tip" size="36" rounded="sm" class="flex-shrink-0" style="cursor:pointer;overflow:hidden">
                            <img :src="item._photo_url" style="width:36px;height:36px;object-fit:cover;display:block" />
                          </v-avatar>
                        </template>
                        <img :src="item._photo_url" style="width:200px;height:200px;object-fit:cover;border-radius:8px;display:block" />
                      </v-tooltip>
                      <v-icon v-else size="28" class="flex-shrink-0 text-medium-emphasis">mdi-package-variant</v-icon>

                      <v-tooltip v-if="item.item_name && !item.product_id && form.purchase_method !== 'advance'"
                        text="Позиция не привязана к каталогу" location="top">
                        <template #activator="{ props: tip }">
                          <v-icon v-bind="tip" size="18" color="warning" class="flex-shrink-0">mdi-alert</v-icon>
                        </template>
                      </v-tooltip>

                      <v-textarea
                        v-model="item.item_name"
                        density="compact"
                        variant="outlined"
                        hide-details
                        clearable
                        readonly
                        rows="1"
                        auto-grow
                        class="my-1"
                        style="cursor:pointer;min-width:280px"
                        placeholder="Нажмите для выбора..."
                        @click="openProductPicker(idx)"
                        @click:clear.stop="clearItem(idx)"
                      />
                      <v-tooltip v-if="item.item_name" :text="item.product_id ? 'Обновить цену / ссылки в каталоге' : 'Обновить цену'" location="top">
                        <template #activator="{ props: tip }">
                          <v-btn v-bind="tip" icon="mdi-pencil-outline" size="x-small" variant="tonal"
                            color="teal" class="flex-shrink-0 ml-1"
                            @click.stop="openQuickProductEdit(item)" />
                        </template>
                      </v-tooltip>
                    </div>
                  </td>
                  <td>
                    <v-select v-model="item.item_type"
                      :items="[{value:'товар',title:'Товар'},{value:'услуга',title:'Услуга'},{value:'работа',title:'Работа'}]"
                      item-title="title" item-value="value" density="compact" variant="outlined"
                      :error="form.item_type === 'mixed' && !!item.item_name?.trim() && !item.item_type"
                      hide-details class="my-1" />
                  </td>
                  <td>
                    <v-text-field v-model.number="item.quantity" type="number" density="compact"
                      variant="outlined" hide-details class="my-1"
                      @update:model-value="calcItemTotal(idx)" />
                  </td>
                  <td>
                    <v-text-field v-model="item.unit" density="compact" variant="outlined"
                      hide-details class="my-1" />
                  </td>
                  <td>
                    <v-text-field v-model.number="item.unit_price" type="number" density="compact"
                      variant="outlined" hide-details class="my-1"
                      @update:model-value="calcItemTotal(idx)" />
                  </td>
                  <td>
                    <v-text-field :model-value="item.total_price ?? ''" readonly density="compact"
                      variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1" />
                  </td>
                  <td>
                    <v-text-field v-model="item.country_origin" density="compact"
                      variant="outlined" hide-details class="my-1" placeholder="Россия" />
                  </td>
                  <td>
                    <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                      @click="removeItem(idx)" />
                  </td>
                </tr>
                <tr v-if="!items.length">
                  <td colspan="8" class="text-center text-medium-emphasis py-4">
                    Нет позиций. Нажмите «Добавить позицию».
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
          <div class="d-flex gap-2 mt-3">
            <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addItem">
              Добавить позицию
            </v-btn>
            <v-btn variant="outlined" prepend-icon="mdi-package-variant-plus" size="small" color="primary"
              @click="openFullProduct(-1)">
              Добавить товар в каталог
            </v-btn>
            <v-btn variant="outlined" prepend-icon="mdi-file-excel-outline" size="small" color="success"
              @click="itemsImportDialog = true">
              Импорт из файла
            </v-btn>
          </div>
        </v-card-text>
      </v-card>

      <!-- 2.5 Техническое задание (показывается когда есть позиции) -->
      <v-card v-if="hasProducts" variant="outlined" class="mb-4" style="border-color:#3B82F6">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
          <span class="d-flex align-center gap-2">
            <v-icon icon="mdi-clipboard-text-outline" color="primary" size="20" />
            Техническое задание
          </span>
          <div class="d-flex align-center gap-2">
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
                  :loading="docLoading === 'contract_tz'"
                >
                  Скачать ТЗ (.docx)
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-file-word-outline" @click="downloadDoc('contract_tz', '?tz_override_mode=exact')">
                  <v-list-item-title>Точное ТЗ</v-list-item-title>
                </v-list-item>
                <v-list-item prepend-icon="mdi-file-word-outline" @click="downloadDoc('contract_tz', '?tz_override_mode=44fz')">
                  <v-list-item-title>ТЗ для 44-ФЗ</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <v-chip v-else size="small" color="grey" variant="tonal">Сохраните закупку для скачивания</v-chip>
          </div>
        </v-card-title>
        <v-card-text class="pa-0">
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
                <td class="text-right font-weight-medium">{{ item.total_price != null ? item.total_price.toLocaleString('ru-RU', {minimumFractionDigits:2}) : '—' }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="tz-table-footer">
                <td colspan="6" class="text-right font-weight-bold pa-3" style="font-size:13px">Итого НМЦК:</td>
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
              <div class="text-caption text-medium-emphasis mb-1">НМЦК (итого)</div>
              <v-btn-toggle v-model="nmckMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
                <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
                <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
              </v-btn-toggle>
              <v-text-field v-if="nmckMode === 'auto'"
                :model-value="formatMoney(displayNmck)"
                label="НМЦК (итого)" variant="outlined" density="compact"
                readonly bg-color="grey-lighten-4"
                :hint="nmckHint" persistent-hint />
              <v-text-field v-else
                v-model.number="nmckManualValue"
                label="НМЦК (итого, вручную)" variant="outlined" density="compact"
                type="number" suffix="₽"
                hint="Введено вручную. Цена за единицу в ТЗ скрыта." persistent-hint
                @update:model-value="calcEconomy" />
            </v-col>
            <v-col cols="12" md="3">
              <div class="text-caption text-medium-emphasis mb-1">Цена договора</div>
              <v-btn-toggle v-model="contractPriceMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
                <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
                <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
              </v-btn-toggle>
              <v-text-field v-model.number="form.contract_price" label="Цена договора" variant="outlined"
                density="compact" type="number" suffix="₽"
                :readonly="contractPriceMode === 'auto'"
                :bg-color="contractPriceMode === 'auto' ? 'grey-lighten-4' : undefined"
                :hint="contractPriceMode === 'manual' ? 'Введено вручную' : contractPriceHint"
                persistent-hint
                :color="nmckWarningLevel === 'error' ? 'error' : nmckWarningLevel === 'warning' ? 'warning' : undefined"
                @update:model-value="calcEconomy">
                <template v-slot:append-inner>
                  <v-icon v-if="nmckWarningLevel === 'error'" icon="mdi-alert" color="error" size="18" :title="`Превышение НМЦК на ${nmckExcessPct}%`" />
                  <v-icon v-else-if="nmckWarningLevel === 'warning'" icon="mdi-alert-outline" color="warning" size="18" :title="`Близко к НМЦК (+${nmckExcessPct}%)`" />
                </template>
              </v-text-field>
              <div v-if="nmckWarningLevel" class="text-caption mt-n2 mb-1"
                :class="nmckWarningLevel === 'error' ? 'text-error' : 'text-warning'">
                {{ nmckWarningLevel === 'error' ? `Превышение НМЦК на ${nmckExcessPct}%` : `Близко к НМЦК (+${nmckExcessPct}%)` }}
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field :model-value="form.economy ?? ''" label="Экономия (авто)" variant="outlined"
                density="compact" suffix="₽" readonly bg-color="grey-lighten-4"
                hint="НМЦК минус Цена договора. Считается автоматически." persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="form.price_increase" label="Удорожание (доп. соглашения)"
                variant="outlined" density="compact" type="number" suffix="₽"
                hint="Указывается при увеличении цены по доп. соглашению к договору" persistent-hint />
            </v-col>
          </v-row>
          <!-- Тип договора -->
          <v-row v-if="isSectionVisible('contract_type')" class="mt-0">
            <v-col cols="12" md="3">
              <v-select
                v-model="form.purchase_contract_type"
                :items="CONTRACT_TYPES"
                item-title="title" item-value="value"
                label="Тип договора" variant="outlined" density="compact"
                @update:model-value="onContractTypeChange"
              />
            </v-col>
            <v-col v-if="isFramework" cols="12" md="9">
              <div class="d-flex align-center gap-3 pt-1">
                <div class="flex-grow-1">
                  <template v-if="selectedFrameworkContract">
                    <div class="d-flex align-center gap-2 flex-wrap">
                      <v-chip color="primary" size="small" variant="tonal">{{ selectedFrameworkContract.number }}</v-chip>
                      <span class="text-body-2 font-weight-medium">{{ selectedFrameworkContract.contractor_name }}</span>
                      <span v-if="selectedFrameworkContract.contractor_inn" class="text-caption text-medium-emphasis">
                        ИНН: {{ selectedFrameworkContract.contractor_inn }}
                      </span>
                    </div>
                    <div v-if="selectedFrameworkContract.subject" class="text-caption text-medium-emphasis mt-1">
                      {{ selectedFrameworkContract.subject }}
                    </div>
                    <div v-if="selectedFrameworkContract.max_amount" class="text-caption font-weight-medium text-blue-darken-2 mt-1">
                      Макс. сумма: {{ Number(selectedFrameworkContract.max_amount).toLocaleString('ru-RU') }} ₽
                      <span v-if="selectedFrameworkContract.remaining != null">
                        · Остаток: {{ Number(selectedFrameworkContract.remaining).toLocaleString('ru-RU') }} ₽
                      </span>
                    </div>
                  </template>
                  <span v-else class="text-medium-emphasis text-body-2">Рамочный договор не выбран</span>
                </div>
                <v-btn variant="outlined" size="small" prepend-icon="mdi-file-document-outline"
                  @click="openFrameworkDialog">
                  {{ selectedFrameworkContract ? 'Изменить' : 'Выбрать договор' }}
                </v-btn>
                <v-btn v-if="selectedFrameworkContract" icon="mdi-close" variant="text" size="small"
                  color="error" @click="clearFrameworkContract" />
              </div>
            </v-col>
            <!-- Порядковый номер в РД -->
            <v-col v-if="isFramework && form.contract_id" cols="12" md="2">
              <v-text-field
                v-model.number="form.framework_seq"
                label="№ в рамках РД"
                variant="outlined" density="compact" type="number" min="1"
                hint="Авто, можно изменить" persistent-hint
              />
            </v-col>
            <!-- Таблица других закупок в том же РД -->
            <v-col v-if="isFramework && frameworkSiblings.length" cols="12">
              <div class="framework-siblings-label">
                <v-icon icon="mdi-link-variant" size="14" class="mr-1" />
                Закупки в рамках этого договора ({{ frameworkSiblings.length }})
              </div>
              <v-table density="compact" class="framework-siblings-table mt-1">
                <thead>
                  <tr>
                    <th style="width:50px">№</th>
                    <th>Наименование</th>
                    <th>Статус</th>
                    <th class="text-right">НМЦК</th>
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
        <v-tabs v-model="form.payment_basis_type" density="compact" color="primary" class="px-2 pt-2">
          <v-tab value="contract">Договор</v-tab>
          <v-tab value="invoice">Счёт</v-tab>
          <v-tab value="invoice_contract">Счёт-договор</v-tab>
          <v-tab value="framework_invoice">Счёт по РД</v-tab>
        </v-tabs>
        <v-divider />
        <v-card-text>
          <v-window v-model="form.payment_basis_type">

          <!-- ── Договор ── -->
          <v-window-item value="contract">
          <v-row class="mt-1">
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_number" label="Номер договора" variant="outlined" density="compact"
                :placeholder="isNew ? 'Назначается автоматически' : ''"
                :hint="needsContract ? 'Обязательно для перехода в статус Договор' : isNew ? 'Будет присвоен после сохранения' : ''"
                persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_date" label="Дата договора" variant="outlined"
                density="compact" type="date" :rules="contractDateRules" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_end_date" label="Срок действия договора" variant="outlined"
                density="compact" type="date"
                :readonly="isFramework && !!selectedFrameworkContract?.end_date"
                :bg-color="isFramework && selectedFrameworkContract?.end_date ? 'grey-lighten-4' : undefined"
                hint="Дата окончания действия договора" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.delivery_date" label="Нужна к дате" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.procurement_planned_date" label="Планируемая дата закупки"
                variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                label="Адрес доставки" variant="outlined" density="compact" clearable hide-no-data no-filter
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
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
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
            <v-col cols="12" md="3">
              <v-text-field v-model="form.delivery_date" label="Нужна к дате" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.procurement_planned_date" label="Планируемая дата закупки"
                variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                label="Адрес доставки" variant="outlined" density="compact" clearable hide-no-data no-filter
                :custom-filter="() => true" @update:search="onDeliveryAddressSearch"
                placeholder="Начните вводить адрес..." />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
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
            <v-col cols="12" md="3">
              <v-text-field v-model="form.contract_end_date" label="Срок действия" variant="outlined"
                density="compact" type="date" hint="Дата окончания действия" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.delivery_date" label="Нужна к дате" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.procurement_planned_date" label="Планируемая дата закупки"
                variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                label="Адрес доставки" variant="outlined" density="compact" clearable hide-no-data no-filter
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
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
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
                        <span v-if="item.raw.remaining != null"> · Остаток: {{ Number(item.raw.remaining).toLocaleString('ru-RU') }} ₽</span>
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
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.delivery_date" label="Нужна к дате" variant="outlined"
                density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="5">
              <v-combobox v-model="form.delivery_address" :items="deliveryAddressSuggestions"
                label="Адрес доставки" variant="outlined" density="compact" clearable hide-no-data no-filter
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
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Параметры договора (для документа)</v-card-title>
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
            <v-col v-if="form.service_period_type === 'period'" cols="12" md="2">
              <v-text-field v-model="form.service_start_date" label="Начало периода"
                variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col v-if="form.service_period_type === 'period'" cols="12" md="2">
              <v-text-field v-model="form.service_end_date" label="Конец периода"
                variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col v-if="form.service_period_type === 'date'" cols="12" md="3">
              <v-text-field v-model="form.service_start_date" label="Дата оказания услуг"
                variant="outlined" density="compact" type="date" />
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
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 5. Закрывающие документы (admin+) -->
      <v-card v-if="isSectionVisible('acceptance')" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Закрывающие документы</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.acceptance_doc_name" label="Наименование документа" variant="outlined" density="compact"
                :hint="needsAcceptance ? 'Обязательно для перехода в статус Поставлено' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_number" label="Номер закрывающего документа" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_date" label="Дата закрывающего документа" variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.acceptance_doc_amount" label="Сумма закрывающего документа" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 6. Платёж (admin+) -->
      <v-card v-if="isSectionVisible('payment')" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Платёж</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.payment_doc_number" label="Номер платёжного поручения" variant="outlined" density="compact"
                :hint="needsPayment ? 'Обязательно для перехода в статус Оплачено' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.payment_doc_date" label="Дата ПП" variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.payment_amount" label="Сумма платежа" variant="outlined"
                density="compact" type="number" suffix="₽" />
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

      <!-- 7b. Участники и лента событий (только в режиме редактирования) -->
      <!-- Чат по закупке -->
      <v-card v-if="isEdit && purchaseId" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
          <v-icon icon="mdi-chat-outline" class="mr-2" color="blue" />
          Обсуждение
          <v-chip v-if="purchaseComments.length" size="x-small" color="blue-grey" class="ml-2" variant="tonal">{{ purchaseComments.length }}</v-chip>
        </v-card-title>
        <v-card-text>
          <!-- Участники -->
          <div class="d-flex align-center flex-wrap ga-1 mb-3">
            <span class="text-caption text-medium-emphasis mr-1">Участники:</span>
            <v-chip v-for="m in purchaseMembers" :key="m.user_id" size="small" variant="tonal" color="primary"
              closable @click:close="removePurchaseMember(m.user_id)">
              {{ m.user_name || `#${m.user_id}` }}
            </v-chip>
            <v-menu :close-on-content-click="false">
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" icon="mdi-account-plus" size="x-small" variant="tonal" color="primary" title="Добавить участника" />
              </template>
              <v-card min-width="250">
                <v-card-text class="pa-2">
                  <v-autocomplete v-model="newMemberUserId" :items="allUsers" item-title="text" item-value="value"
                    label="Добавить" variant="outlined" density="compact" hide-details
                    @update:model-value="addPurchaseMember" />
                </v-card-text>
              </v-card>
            </v-menu>
          </div>
          <div ref="purchaseChatContainer" class="purchase-chat-container mb-2">
            <div v-for="c in purchaseComments" :key="c.id"
              class="pchat-msg" :class="c.user_id === currentUserId ? 'pchat-msg--mine' : 'pchat-msg--other'">
              <div class="pchat-msg-header">
                <v-icon icon="mdi-account-circle" size="14" :color="c.user_id === currentUserId ? 'white' : 'primary'" class="mr-1" />
                <span class="pchat-msg-author">{{ c.user_name }}</span>
                <span class="pchat-msg-time">{{ c.created_at ? new Date(c.created_at).toLocaleString('ru') : '' }}</span>
                <v-btn v-if="c.user_id === currentUserId" icon="mdi-delete-outline" size="x-small" variant="text" density="compact"
                  :color="c.user_id === currentUserId ? 'white' : 'grey'" class="pchat-msg-delete"
                  @click.stop="deletePurchaseComment(c.id)" />
              </div>
              <div class="pchat-msg-text" v-html="renderPurchaseMentions(c.text)"></div>
            </div>
            <div v-if="purchaseComments.length === 0" class="text-caption text-medium-emphasis text-center pa-4">Начните обсуждение</div>
          </div>
          <!-- Mention dropdown -->
          <div v-if="pMentionOpen" class="purchase-mention-dropdown">
            <div v-for="u in pFilteredMentionUsers" :key="u.value"
              class="mention-item" @mousedown.prevent="pInsertMention(u)">
              <v-icon icon="mdi-account" size="14" class="mr-1" />{{ u.text }}
            </div>
            <div v-if="pFilteredMentionUsers.length === 0" class="mention-item text-medium-emphasis">Нет совпадений</div>
          </div>
          <div class="d-flex ga-2 align-end">
            <v-textarea
              ref="purchaseCommentInput"
              v-model="pCommentText"
              :placeholder="pEnterToSend ? 'Сообщение... (Enter — отправить)' : 'Сообщение... (Ctrl+Enter — отправить)'"
              variant="outlined" density="compact" rows="5" hide-details auto-grow
              style="flex:1"
              @keydown="onPurchaseCommentKeydown"
              @input="onPurchaseCommentInput"
            />
            <div class="d-flex flex-column ga-1" style="min-width:36px">
              <v-btn color="primary" icon size="small" :disabled="!pCommentText.trim()" :loading="pCommentSaving" @click="addPurchaseComment" title="Отправить">
                <v-icon icon="mdi-send" size="18" />
              </v-btn>
              <v-btn icon size="small" variant="tonal" color="deep-purple" @click="pOpenMentionPicker" title="Упомянуть">
                <v-icon icon="mdi-at" size="18" />
              </v-btn>
              <v-btn v-if="isManagerLevel" icon size="small" variant="tonal" color="orange" @click="openPurchaseBroadcast" title="Рассылка">
                <v-icon icon="mdi-bullhorn" size="18" />
              </v-btn>
            </div>
          </div>
          <div class="d-flex align-center mt-1" style="font-size:11px;color:#888;user-select:none">
            <span style="white-space:nowrap">{{ pEnterToSend ? 'Enter — отправка' : 'Enter — новая строка' }}</span>
            <v-switch v-model="pEnterToSend" density="compact" hide-details color="primary"
              style="flex:0 0 auto; margin: 0 16px"
              @update:model-value="(v: any) => localStorage.setItem('pchat_enter_to_send', String(v))" />
            <span style="white-space:nowrap">{{ pEnterToSend ? 'Ctrl+Enter — новая строка' : 'Ctrl+Enter — отправка' }}</span>
          </div>
        </v-card-text>
      </v-card>

      <!-- Purchase broadcast dialog -->
      <v-dialog v-model="pBroadcastDialog" max-width="480" persistent>
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

      <!-- 7. Файлы (скрыто для employee) -->
      <v-card v-if="isEdit && isManagerLevel" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы к закупке</v-card-title>
        <v-card-text>
          <div class="d-flex align-center gap-3 mb-3">
            <v-btn prepend-icon="mdi-upload" variant="tonal" size="small"
              :loading="uploading" @click="openUploadDialog">
              Загрузить файл
            </v-btn>
            <span class="text-caption text-medium-emphasis">PDF, Word, Excel, JPEG, PNG</span>
          </div>
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
      <v-dialog v-model="uploadDialog" max-width="420" persistent>
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

      <!-- Диалог быстрого редактирования товара (цена + ссылки) -->
      <v-dialog v-model="quickProductEditDialog" max-width="520">
        <v-card>
          <v-card-title class="text-subtitle-1 pt-4 px-4">
            Обновить товар
            <div class="text-caption text-medium-emphasis font-weight-regular">{{ quickProductEditName }}</div>
          </v-card-title>
          <v-card-text>
            <div class="d-flex gap-2 align-center mb-3">
              <v-text-field v-model.number="quickProductEditPrice" label="Цена, ₽" type="number"
                variant="outlined" density="compact" prefix="₽" hide-details class="flex-grow-1" />
              <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-calculator"
                @click="recalcQuickProductPrice">Пересчитать</v-btn>
            </div>
            <template v-if="quickProductEditProductId">
              <div class="text-body-2 mb-2 font-weight-medium">Ссылки на товар</div>
              <div v-for="(link, i) in quickProductEditLinks" :key="i" class="d-flex gap-2 mb-2 align-center">
                <v-text-field v-model="link.url" label="URL" variant="outlined" density="compact"
                  hide-details class="flex-grow-1" />
                <v-text-field v-model.number="link.price" label="Цена" type="number" variant="outlined"
                  density="compact" hide-details style="max-width:90px" />
                <v-text-field v-model="link.collected_at" label="Дата" type="date" variant="outlined"
                  density="compact" hide-details style="max-width:130px" />
                <v-btn icon="mdi-close" size="x-small" variant="text" color="error"
                  @click="quickProductEditLinks.splice(i, 1)" />
              </div>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" class="mt-1"
                @click="quickProductEditLinks.push({ url: '', price: null, collected_at: new Date().toISOString().slice(0,10) })">
                Добавить ссылку
              </v-btn>
              <div class="text-caption text-medium-emphasis mt-3">
                Цена и ссылки сохранятся в каталоге. Для полного редактирования — вкладка «Товары»
              </div>
            </template>
            <div v-else class="text-caption text-medium-emphasis mt-1">
              Товар не привязан к каталогу — обновится только цена в этой закупке
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="quickProductEditDialog = false">Отмена</v-btn>
            <v-btn color="primary" variant="tonal" :loading="savingQuickProduct" @click="saveQuickProduct">
              Сохранить
            </v-btn>
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
                  @click="openDocPicker('service_note')"
                >
                  <v-list-item-title>На организацию закупки</v-list-item-title>
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
              </v-list>
            </v-menu>
            <v-menu v-if="isManagerLevel">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  prepend-icon="mdi-file-word-outline"
                  append-icon="mdi-chevron-down"
                  variant="tonal"
                  color="blue-darken-2"
                  size="small"
                  :loading="docLoading === 'contract_tz'"
                >
                  ТЗ
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-file-word-outline" @click="downloadDoc('contract_tz', '?tz_override_mode=exact')">
                  <v-list-item-title>Точное ТЗ</v-list-item-title>
                </v-list-item>
                <v-list-item prepend-icon="mdi-file-word-outline" @click="downloadDoc('contract_tz', '?tz_override_mode=44fz')">
                  <v-list-item-title>ТЗ для 44-ФЗ</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <v-btn v-if="isManagerLevel && isSectionVisible('contractor')"
              prepend-icon="mdi-file-document-outline"
              variant="tonal"
              color="indigo"
              size="small"
              :loading="docLoading === 'contract'"
              @click="downloadDoc('contract')"
            >
              Договор
            </v-btn>
            <v-btn v-if="isManagerLevel && isSectionVisible('contractor')"
              prepend-icon="mdi-file-document-edit-outline"
              variant="tonal"
              color="deep-purple"
              size="small"
              :loading="docLoading === 'contract_fadm'"
              @click="downloadDoc('contract_fadm')"
            >
              Договор ФАДМ
            </v-btn>
            <v-btn v-if="isManagerLevel"
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'approval_sheet'"
              @click="openDocPicker('approval_sheet')"
            >
              Лист согласования
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
        @update:approval-status="form.approval_status = $event"
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

      <!-- 10. Публикация на площадках (admin+) -->
      <v-card v-if="isEdit && isSectionVisible('platform_publication')" variant="outlined" class="mb-4" style="border-color:#7C3AED">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
          <span class="d-flex align-center gap-2">
            <v-icon icon="mdi-broadcast" color="deep-purple" size="20" />
            Публикация на площадках
          </span>
          <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-upload-network"
            @click="publishDialog = true">
            Опубликовать
          </v-btn>
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
                  <span v-if="pub.external_id">{{ pub.external_id }}</span>
                  <span v-else-if="pub.error_text" class="text-error">{{ pub.error_text }}</span>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
                <td class="text-caption">
                  <a v-if="pub.external_url" :href="pub.external_url" target="_blank"
                    class="text-blue-darken-2 text-decoration-none">
                    {{ pub.external_url }}
                    <v-icon size="11">mdi-open-in-new</v-icon>
                  </a>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
                <td style="width:36px">
                  <v-btn v-if="pub.status === 'error'" icon="mdi-refresh" size="x-small" variant="text"
                    color="deep-purple" @click="retryPublish(pub.platform)" />
                </td>
              </tr>
            </tbody>
          </v-table>
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
      <v-dialog v-model="linkedTaskDialog" max-width="560" persistent>
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
      <v-dialog v-model="linkTaskDialog" max-width="520">
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
      <div class="d-flex gap-3 mt-4 flex-wrap">
        <v-btn type="submit" color="primary" size="large" :loading="saving" prepend-icon="mdi-content-save">
          {{ isEdit ? 'Сохранить' : formMode === 'advance_report' ? 'Сформировать авансовый' : 'Создать закупку' }}
        </v-btn>
        <v-btn v-if="isEdit && nextStatusTarget" :color="STATUS_COLOR[nextStatusTarget]" size="large"
          variant="tonal" :loading="transitioning" prepend-icon="mdi-arrow-right-circle" @click="doTransition">
          → {{ STATUS_LABEL[nextStatusTarget] }}
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
    <v-dialog v-model="publishDialog" max-width="440">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon color="deep-purple">mdi-broadcast</v-icon>
          Опубликовать закупку
        </v-card-title>
        <v-card-text class="px-6">
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
                  v-if="pl.value !== 'roseltorg_rb'"
                  color="deep-purple" variant="tonal" size="small"
                  :loading="publishingPlatform === pl.value"
                  :disabled="isPlatformPublished(pl.value)"
                  @click="doPublish(pl.value)"
                >
                  {{ isPlatformPublished(pl.value) ? 'Опубликовано' : 'Опубликовать' }}
                </v-btn>
                <v-btn
                  v-else
                  color="deep-purple" variant="tonal" size="small"
                  :loading="publishingPlatform === 'roseltorg_rb'"
                  :disabled="isPlatformPublished('roseltorg_rb')"
                  @click="pendingPlatform = 'roseltorg_rb'"
                >
                  {{ isPlatformPublished('roseltorg_rb') ? 'Опубликовано' : 'Опубликовать' }}
                </v-btn>
              </template>
            </v-list-item>
          </v-list>

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
                <v-btn
                  variant="text"
                  @click="pendingPlatform = null; roseltorgProcedureType = null"
                >Назад</v-btn>
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
          <v-btn variant="text" @click="publishDialog = false; pendingPlatform = null; roseltorgProcedureType = null">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог подтверждения превышения бюджета -->
    <v-dialog v-model="budgetOverrideDialog" max-width="480">
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

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3500" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <!-- File preview dialog -->
    <v-dialog v-model="previewDialog" max-width="900" scrollable>
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

    <!-- Full product add dialog -->
    <v-dialog v-model="fullProductDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Добавить товар в каталог</v-card-title>
        <v-card-text class="px-6">
          <v-row dense>
            <v-col cols="12">
              <v-combobox
                v-model="fullProductForm.name"
                v-model:search="fullProductNameSearch"
                :items="fullProductNameSuggestions"
                no-filter
                label="Наименование *"
                variant="outlined" density="compact"
                autofocus
                :rules="[v => !!v || 'Обязательное поле']"
                :hint="isFullProductDuplicate ? '⚠ Товар с таким названием уже есть в каталоге' : ''"
                :persistent-hint="isFullProductDuplicate"
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props" :title="item.raw">
                    <template #append>
                      <v-chip size="x-small" color="warning" variant="tonal">уже есть</v-chip>
                    </template>
                  </v-list-item>
                </template>
              </v-combobox>
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox v-model="fullProductForm.product_type"
                :items="fullProductTypeOptions"
                label="Тип товара" variant="outlined" density="compact" clearable
                hint="Напр.: Ноутбук, Тренажёр, Ткань" persistent-hint />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox v-model="fullProductForm.category"
                :items="fullProductCategoryOptions"
                label="Категория" variant="outlined" density="compact" clearable
                hint="Выберите или введите новую" persistent-hint />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="fullProductForm.price" label="Цена за ед., ₽" type="number"
                variant="outlined" density="compact"
                :readonly="fullAvgPrice !== null"
                :hint="fullAvgPrice !== null ? 'Среднее из ссылок — ' + fullAvgPrice.toLocaleString('ru-RU') + ' ₽' : 'Можно задать вручную или через ссылки'"
                persistent-hint />
            </v-col>
            <v-col cols="12" md="6">
              <v-switch v-model="fullProductForm.is_active" label="Активен" color="success" density="compact" hide-details class="mt-1" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="fullProductForm.description" label="Описание" variant="outlined"
                density="compact" rows="2" auto-grow />
            </v-col>
            <v-col cols="12">
              <div class="text-subtitle-2 mb-2">Фото товара</div>
              <div v-if="fullProductPhotoPreview" class="mb-3">
                <img :src="fullProductPhotoPreview" style="max-width:100%;max-height:140px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5" />
              </div>
              <v-file-input
                v-model="fullProductPhotoFileList"
                label="Загрузить фото с компьютера"
                accept="image/jpeg,image/jpg,image/png,image/webp,image/gif"
                variant="outlined" density="compact" prepend-icon="mdi-camera" show-size clearable
                @update:model-value="onFullPhotoFileChange"
              />
              <v-text-field v-model="fullProductForm.photo_link" label="Или ссылка на фото" variant="outlined"
                density="compact" prepend-inner-icon="mdi-image-outline" class="mt-2"
                :disabled="!!fullProductPhotoFile" />
            </v-col>
            <v-col cols="12">
              <div class="text-subtitle-2 mb-2">
                Ссылки для сравнения цен
                <span v-if="fullAvgPrice !== null" class="text-caption font-weight-bold text-blue-darken-2 ml-2">
                  ср. {{ fullAvgPrice.toLocaleString('ru-RU') }} ₽
                </span>
              </div>
              <div v-for="(link, i) in fullProductForm.priceLinks" :key="i" class="d-flex gap-2 mb-2 align-center">
                <v-text-field v-model="link.url" :label="'Ссылка ' + (i + 1)" variant="outlined" density="compact"
                  hide-details prepend-inner-icon="mdi-link" class="flex-grow-1" />
                <v-text-field v-model.number="link.price" label="Цена, ₽" type="number"
                  variant="outlined" density="compact" hide-details style="max-width:140px" />
                <v-btn v-if="link.url" icon="mdi-open-in-new" variant="text" size="x-small" color="primary"
                  :href="link.url" target="_blank" />
                <v-btn icon="mdi-minus-circle" variant="text" size="x-small" color="error"
                  @click="fullProductForm.priceLinks.splice(i, 1)" />
              </div>
              <v-btn prepend-icon="mdi-plus" variant="tonal" size="small" color="primary"
                @click="fullProductForm.priceLinks.push({ url: '', price: null })">
                Добавить ссылку
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="fullProductDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="fullProductSaving" @click="saveFullProduct">Добавить в каталог</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Product picker dialog -->
    <v-dialog v-model="productPickerDialog" max-width="720" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center justify-space-between">
          <span>Выбрать товар из каталога</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="productPickerDialog = false" />
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-text-field
            v-model="productPickerSearch"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по наименованию / описанию / типу"
            variant="outlined" density="compact" clearable hide-details autofocus
            class="mb-3"
          />
          <div v-if="!productPickerResults.length" class="text-center text-medium-emphasis py-8">
            <v-icon icon="mdi-package-variant-closed" size="40" class="mb-2" />
            <div>Ничего не найдено</div>
          </div>
          <v-table v-else density="compact" hover>
            <thead>
              <tr>
                <th style="width:48px"></th>
                <th>Наименование</th>
                <th style="width:110px">Тип</th>
                <th style="width:130px;text-align:right">Цена, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in productPickerResults" :key="p.id"
                style="cursor:pointer" class="hover-row" @click="selectFromPicker(p)">
                <td>
                  <v-avatar size="36" rounded="sm" class="my-1" style="overflow:hidden">
                    <img v-if="p.photo_url || p.photo_link" :src="p.photo_url || p.photo_link" style="width:36px;height:36px;object-fit:cover;display:block" />
                    <v-icon v-else icon="mdi-package-variant" color="grey" size="20" />
                  </v-avatar>
                </td>
                <td>
                  <div class="font-weight-medium">{{ p.name }}</div>
                  <div v-if="p.description" class="text-caption text-medium-emphasis"
                    style="max-width:340px;white-space:normal;line-height:1.3">
                    {{ p.description.slice(0, 90) }}{{ p.description.length > 90 ? '…' : '' }}
                  </div>
                </td>
                <td>
                  <v-chip v-if="p.product_type" size="x-small" variant="tonal">{{ p.product_type }}</v-chip>
                </td>
                <td style="text-align:right" class="font-weight-medium text-blue-darken-2">
                  {{ p.price ? Number(p.price).toLocaleString('ru-RU') + ' ₽' : '—' }}
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="px-6 pb-3">
          <span class="text-caption text-medium-emphasis">{{ productPickerResults.length }} позиций</span>
          <v-spacer />
          <v-btn variant="text" @click="productPickerDialog = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Items import dialog -->
    <v-dialog v-model="itemsImportDialog" max-width="600">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-package-variant-plus" class="mr-2" />
          Загрузка товаров в каталог
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-alert v-if="!purchaseId" type="warning" class="mb-3" density="compact" icon="mdi-information-outline">
            Для добавления в закупку сначала сохраните заказ
          </v-alert>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Загрузите Excel-файл по шаблону — товары попадут в каталог и сразу будут добавлены в закупку.
          </p>
          <div class="d-flex gap-2 mb-3 flex-wrap">
            <v-btn variant="text" color="teal" size="small" prepend-icon="mdi-download"
              @click="downloadProductsTemplate">
              Скачать шаблон
            </v-btn>
          </div>
          <v-file-input
            v-model="itemsImportFile"
            label="Выберите Excel файл (.xlsx / .xls)"
            accept=".xlsx,.xls"
            variant="outlined" density="compact"
            prepend-icon="mdi-file-upload-outline"
            :disabled="itemsImportLoading"
          />
          <v-alert v-if="itemsImportResult" type="success" class="mt-3" density="compact">
            Создано товаров: {{ itemsImportResult.added }}
          </v-alert>

        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="itemsImportDialog = false">Закрыть</v-btn>
          <v-btn color="success" variant="flat"
            :loading="itemsImportLoading"
            :disabled="!itemsImportFile"
            @click="doItemsImport">
            Загрузить в каталог
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Framework contracts dialog -->
    <v-dialog v-model="frameworkDialog" max-width="860" scrollable>
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
                <td class="text-right" :class="c.remaining != null && c.remaining < 0 ? 'text-error' : 'text-success'">
                  {{ c.remaining != null ? Number(c.remaining).toLocaleString('ru-RU') + ' ₽' : '—' }}
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
    <v-dialog v-model="kpDialog" max-width="780" scrollable>
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
            variant="tonal"
            prepend-icon="mdi-email-multiple-outline"
            :disabled="kpAllEmails.length === 0"
            @click="sendAllKp"
          >
            Открыть в почте
          </v-btn>
          <v-btn
            color="teal" variant="flat"
            prepend-icon="mdi-send-outline"
            :loading="kpSendingAll"
            :disabled="kpAllEmails.length === 0"
            @click="sendAllKpViaApi"
          >
            Отправить ({{ kpAllEmails.length }})
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
    <v-dialog v-model="newFrameworkDialog" max-width="520">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Новый рамочный договор</v-card-title>
        <v-card-text class="px-6 pb-2">
          <v-text-field v-model="newFrameworkForm.number" label="Номер договора *" variant="outlined"
            density="compact" class="mb-3" autofocus />
          <v-text-field v-model="newFrameworkForm.date" label="Дата договора" variant="outlined"
            density="compact" type="date" class="mb-3" />
          <v-autocomplete v-model="newFrameworkForm.contractor_id"
            :items="contractors" item-title="name" item-value="id"
            label="Контрагент" variant="outlined" density="compact" clearable
            :custom-filter="contractorFilter" class="mb-3">
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
    <v-dialog v-model="docPickerDialog" max-width="560" scrollable>
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
          <!-- service_note: radio (один инициатор) -->
          <v-radio-group v-else-if="docPickerType.startsWith('service_note')" v-model="pickerInitiatorId" class="mt-0">
            <v-radio
              v-for="a in docApproversInitiators"
              :key="a.id"
              :value="a.id"
              :label="`${a.role_name} — ${a.full_name}`"
            />
            <div v-if="!docApproversInitiators.length" class="text-medium-emphasis text-caption">
              Нет людей с пометкой «Может быть инициатором». Отредактируйте согласующих.
            </div>
          </v-radio-group>
          <!-- approval_sheet: responsible person + checkboxes -->
          <div v-else>
            <!-- Ответственный исполнитель -->
            <div class="d-flex align-center gap-2 mb-4">
              <v-autocomplete
                v-model="pickerResponsibleName"
                :items="responsiblePersonsList"
                item-title="display"
                item-value="full_name"
                label="Ответственный исполнитель"
                variant="outlined"
                density="compact"
                clearable
                hide-details
                class="flex-grow-1"
                :return-object="false"
                autocomplete="off"
              />
              <v-tooltip text="Добавить в справочник" location="top">
                <template #activator="{ props: tip }">
                  <v-btn v-bind="tip" icon="mdi-account-plus-outline" size="small"
                    variant="tonal" color="teal" @click="addResponsibleDialog = true" />
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

    <!-- Диалог добавления ответственного исполнителя -->
    <v-dialog v-model="addResponsibleDialog" max-width="400">
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
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useOrgConfig } from '@/composables/useOrgConfig'
import PurchaseEventFeed from '@/components/PurchaseEventFeed.vue'
import ApprovalPanel from '@/components/purchase/ApprovalPanel.vue'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => !!route.params.id)
const purchaseId = computed(() => Number(route.params.id) || null)

// Role-based visibility
const userRole = localStorage.getItem('user_role') || 'employee'
const isEmployee = computed(() => userRole === 'employee')
const isManager = computed(() => userRole === 'manager')
const isAdminLevel = computed(() => ['superadmin', 'org_admin', 'admin'].includes(userRole))
const isManagerLevel = computed(() => ['superadmin', 'org_admin', 'admin', 'manager'].includes(userRole))

// НМЦК mode: auto (from items) or manual (user enters directly)
const nmckMode = ref<'auto' | 'manual'>('auto')
const nmckManualValue = ref<number | null>(null)
// Цена договора mode
const contractPriceMode = ref<'auto' | 'manual'>('auto')

// --- formMode: drives simplified views for service notes / advance reports ---
const formMode = computed(() => (route.meta?.formMode as string) || 'default')

const formModeHidden = computed((): Set<string> => {
  if (formMode.value === 'service_note_delivery')
    return new Set(['contractor', 'financial_indicators', 'contract_type',
                    'contract', 'contract_params', 'acceptance', 'payment',
                    'platform_publication', 'commercial_requests'])
  if (formMode.value === 'advance_report')
    return new Set(['contractor', 'contract_type', 'contract_params',
                    'platform_publication', 'commercial_requests'])
  return new Set()
})

const { isSectionHidden: isOrgHidden, loadConfig: loadOrgConfig } = useOrgConfig()

function isSectionVisible(key: string): boolean {
  return !formModeHidden.value.has(key) && !isOrgHidden(key)
}

const pageTitle = computed(() => {
  if (formMode.value === 'service_note_delivery')
    return isEdit.value ? `Служебная записка #${form.purchase_number || route.params.id}` : 'Новая служебная записка на выдачу'
  if (formMode.value === 'advance_report')
    return isEdit.value ? `Авансовый отчёт #${form.purchase_number || route.params.id}` : 'Новый авансовый отчёт'
  return isEdit.value ? `Закупка #${form.purchase_number || route.params.id}` : 'Новая закупка'
})

const backRoute = computed(() => {
  if (formMode.value === 'service_note_delivery') return '/service-notes'
  if (formMode.value === 'advance_report') return '/advance-reports'
  return '/orders'
})

const STATUS_ORDER = ['wishes', 'plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания сотрудников', plan_schedule: 'План-график',
  confirmed: 'Подтверждено руководством', work_in_progress: 'Ведётся работа',
  contracted: 'Заключён договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  wishes: 'amber', plan_schedule: 'orange',
  confirmed: 'blue', work_in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const SUBSTATUS_OPTIONS = [
  { value: 'tz_forming', title: 'Формируется ТЗ' },
  { value: 'kp_collecting', title: 'Идёт сбор КП' },
  { value: 'on_platform', title: 'Выставлено на площадку' },
]
const COUNTRIES = ['Российская Федерация', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

interface FeoCategory { id: number; name: string; parent_id: number | null; level: number; subsidy_id: number }
interface Contractor { id: number; name: string; inn?: string }
interface Subsidy { id: number; name: string; year: number; budget: number; org_id?: number | null }
interface Product { id: number; name: string; price?: number; product_type?: string; description?: string; description_44fz?: string; photo_url?: string; photo_link?: string; category?: string }
interface FrameworkContract { id: number; number: string; date?: string; contract_type: string; contractor_id?: number; contractor_name?: string; contractor_inn?: string; subject?: string; max_amount?: number; remaining?: number; status?: string }
interface PriceLink { url: string; price: number | null; collected_at?: string }
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
  // UI-only: not sent to backend
  _selectedProduct?: Product | null
  _photo_url?: string
  _description?: string
  _description_44fz?: string
}
interface UploadedFile { id: number; purchase_id: number; filename: string; mime_type?: string; size?: number; file_type?: string; doc_format?: string; uploaded_by_name?: string | null; created_at?: string | null }

const FILE_TYPE_LABELS: Record<string, string> = {
  kp:           'КП',
  service_note: 'Служебная записка',
  protocol:     'Протокол закупки',
  invoice:      'Счёт',
  order:        'Приказ',
  upd:          'УПД',
  contract:     'Договор',
  act:          'Закрывающий документ',
  other:        'Прочее',
}
const FILE_TYPE_OPTIONS = Object.entries(FILE_TYPE_LABELS).map(([value, title]) => ({ value, title }))

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
  purchase_basis: '' as string,
  item_type: 'товар' as string,
  subsidy_id: null as number | null,
  contractor_id: null as number | null,
  registry_number: '',
  feo_category_id: null as number | null,
  subject: '',
  contract_price: null as number | null,
  economy: null as number | null,
  price_increase: null as number | null,
  contract_number: '',
  contract_date: '',
  contract_end_date: '' as string,
  delivery_date: '',
  delivery_address: '',
  procurement_planned_date: '',
  execution_term: '',
  execution_term_changed: '',
  acceptance_doc_name: '',
  acceptance_doc_number: '',
  acceptance_doc_date: '',
  acceptance_doc_amount: null as number | null,
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
  vat_applicable: false as boolean,
  vat_rate: null as number | null,
  vat_exemption_article: '' as string,
  third_party_involved: false as boolean,
  service_period_type: 'period' as string,
  service_start_date: '' as string,
  service_end_date: '' as string,
  description_mode: 'exact' as string,
  event_id: null as number | null,
  approval_status: null as string | null,
  approval_mode: null as string | null,
  country_origin: '' as string,
  treasury_code: '' as string,
  has_pretension: false as boolean,
  payment_basis_type: 'contract' as string,
  subsidy_allocations: [] as Array<{subsidy_id: number, amount: number | null}>,
})

function activeDescription(item: OrderItem): string | undefined {
  if (form.description_mode === '44fz') return item._description_44fz || item._description
  return item._description
}

interface EventItem { id: number; subsidy_id: number; name: string; is_active: boolean }

const items = ref<OrderItem[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const allEvents = ref<EventItem[]>([])
const filteredEvents = computed(() =>
  allEvents.value.filter(e => e.subsidy_id === form.subsidy_id && e.is_active)
)
const currentSubsidyOrgId = computed(() =>
  subsidies.value.find(s => s.id === form.subsidy_id)?.org_id ?? null
)
const products = ref<Product[]>([])
const allFeoCategories = ref<FeoCategory[]>([])
const formRef = ref()
const saving = ref(false)
const transitioning = ref(false)
const converting = ref(false)
const uploading = ref(false)
const docLoading = ref<string | null>(null)

// ── Doc picker (approver selection before download) ──
interface DocApprover { id: number; role_name: string; full_name: string; order_num: number; is_default: boolean; can_initiate: boolean }
const docPickerDialog      = ref(false)
const docPickerType        = ref<'service_note' | 'service_note_delivery' | 'service_note_payment' | 'approval_sheet'>('approval_sheet')
const loadingDocApprovers  = ref(false)
const docApprovers         = ref<DocApprover[]>([])
const pickerApproverIds    = ref<number[]>([])
const pickerInitiatorId    = ref<number | null>(null)
const docApproversInitiators = computed(() => docApprovers.value.filter(a => a.can_initiate))

// ── Org users list for executor dropdown ──
interface OrgUser { id: number; full_name: string; position?: string | null }
const orgUsersList = ref<OrgUser[]>([])
async function loadOrgUsers() {
  try {
    const users = await apiFetch<any[]>('/users/')
    orgUsersList.value = users
      .filter(u => u.full_name)
      .map(u => ({ id: u.id, full_name: u.full_name, position: u.position }))
  } catch { orgUsersList.value = [] }
}

// ── Delivery address autocomplete ──
const deliveryAddressSuggestions = ref<string[]>([])
let _deliverySearchTimer: ReturnType<typeof setTimeout> | null = null
async function onDeliveryAddressSearch(q: string) {
  if (!q || q.length < 2) { deliveryAddressSuggestions.value = []; return }
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

async function openDocPicker(type: 'service_note' | 'service_note_delivery' | 'service_note_payment' | 'approval_sheet') {
  if (!purchaseId.value || !form.subsidy_id) {
    downloadDoc(type)
    return
  }
  docPickerType.value = type
  docPickerDialog.value = true
  loadingDocApprovers.value = true
  // Pre-fill responsible person from the purchase form
  pickerResponsibleName.value = form.responsible_person || ''
  try {
    const [list] = await Promise.all([
      apiFetch<DocApprover[]>(`/subsidies/${form.subsidy_id}/approvers`),
      loadResponsiblePersonsList(),
    ])
    docApprovers.value = list
    if (type === 'approval_sheet') {
      pickerApproverIds.value = list.filter(a => a.is_default).map(a => a.id)
    } else {
      const def = list.find(a => a.can_initiate && a.is_default) || list.find(a => a.can_initiate)
      pickerInitiatorId.value = def?.id ?? null
    }
  } catch {
    docApprovers.value = []
  } finally {
    loadingDocApprovers.value = false
  }
}

async function confirmDocDownload() {
  docPickerDialog.value = false
  if (docPickerType.value.startsWith('service_note')) {
    const params = pickerInitiatorId.value ? `?initiator_id=${pickerInitiatorId.value}` : ''
    await downloadDoc(docPickerType.value, params)
  } else {
    const parts: string[] = []
    if (pickerApproverIds.value.length) parts.push(`approver_ids=${pickerApproverIds.value.join(',')}`)
    if (pickerResponsibleName.value) parts.push(`responsible_name=${encodeURIComponent(pickerResponsibleName.value)}`)
    await downloadDoc('approval_sheet', parts.length ? `?${parts.join('&')}` : '')
  }
}
const snack = reactive({ show: false, text: '', color: 'success' })
const budgetInfo = ref<{ remaining: number; exceeded: boolean; over: number } | null>(null)
const budgetOverrideDialog = ref(false)
const isAdmin = computed(() => ['superadmin', 'org_admin', 'admin'].includes(userRole))

// ── Approval (Согласование) — extracted to ApprovalPanel.vue ─────────────────
const approvalPanelRef = ref<InstanceType<typeof ApprovalPanel> | null>(null)

const showApprovalSection = computed(() => {
  if (!isEdit.value) return false
  const idx = STATUS_ORDER.indexOf(form.status)
  return idx >= STATUS_ORDER.indexOf('confirmed')
})

const contractorInn = ref('')
const fileInputEl = ref<HTMLInputElement | null>(null)
const uploadedFiles = ref<UploadedFile[]>([])
const uploadDialog = ref(false)
const uploadFileType = ref('other')
const uploadDocFormat = ref('scan')
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

// ── Quick product edit (price + links) ────────────────────────────
const quickProductEditDialog = ref(false)
const quickProductEditProductId = ref<number | null>(null)
const quickProductEditItemIdx = ref<number>(-1)
const quickProductEditName = ref('')
const quickProductEditPrice = ref<number | null>(null)
const quickProductEditLinks = ref<PriceLink[]>([])
const savingQuickProduct = ref(false)

async function openQuickProductEdit(item: OrderItem) {
  quickProductEditItemIdx.value = items.value.indexOf(item)
  quickProductEditName.value = item.item_name
  quickProductEditPrice.value = item.unit_price ?? null
  quickProductEditLinks.value = []

  // Resolve product_id: use existing or find by name in catalog
  let productId = item.product_id
  if (!productId && item.item_name) {
    const match = products.value.find(p => p.name.trim().toLowerCase() === item.item_name.trim().toLowerCase())
    if (match) {
      productId = match.id
      item.product_id = match.id  // backfill for future saves
    }
  }
  quickProductEditProductId.value = productId

  if (productId) {
    try {
      const prod = await apiFetch<any>(`/products/${productId}`)
      quickProductEditPrice.value = prod.price ?? item.unit_price ?? null
      quickProductEditLinks.value = (prod.price_links || []).map((l: any) => ({ url: l.url, price: l.price ?? null, collected_at: l.collected_at ?? null }))
    } catch {}
  }
  quickProductEditDialog.value = true
}

function recalcQuickProductPrice() {
  const links = quickProductEditLinks.value.filter(l => l.url && l.price != null && l.collected_at)
  if (!links.length) return
  // Find top 3 distinct dates
  const dates = [...new Set(links.map(l => l.collected_at!).filter(Boolean))].sort().reverse().slice(0, 3)
  const relevant = links.filter(l => dates.includes(l.collected_at!))
  const avg = relevant.reduce((s, l) => s + (l.price ?? 0), 0) / relevant.length
  quickProductEditPrice.value = Math.round(avg * 100) / 100
}

async function saveQuickProduct() {
  savingQuickProduct.value = true
  try {
    let finalPrice = quickProductEditPrice.value
    if (quickProductEditProductId.value) {
      // Save to catalog, use returned price (recalculated from links)
      const updated = await apiFetch<any>(`/products/${quickProductEditProductId.value}`, {
        method: 'PATCH',
        body: {
          price: quickProductEditPrice.value,
          price_links: quickProductEditLinks.value.filter(l => l.url),
        },
      })
      finalPrice = updated?.price ?? quickProductEditPrice.value
    }
    // Always update the order row price
    if (quickProductEditItemIdx.value >= 0 && finalPrice != null) {
      const item = items.value[quickProductEditItemIdx.value]
      if (item) {
        item.unit_price = finalPrice
        calcItemTotal(quickProductEditItemIdx.value)
      }
    }
    quickProductEditDialog.value = false
    showSnack(quickProductEditProductId.value ? 'Товар обновлён в каталоге' : 'Цена обновлена')
  } catch {
    showSnack('Ошибка сохранения', 'error')
  } finally {
    savingQuickProduct.value = false
  }
}

// ── Publications ──────────────────────────────────────────────────
interface Publication {
  id: number; purchase_id: number; platform: string; status: string
  external_id?: string; external_url?: string; error_text?: string
  published_at?: string; created_at?: string
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
  error:      'error',
}

const PUB_STATUS_LABEL: Record<string, string> = {
  pending:    'Ожидает',
  publishing: 'Публикуется...',
  published:  'Опубликовано',
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

const isPlatformPublished = (platform: string) =>
  publications.value.some(p => p.platform === platform && p.status === 'published')

async function loadPublications() {
  if (!purchaseId.value) return
  try {
    publications.value = await apiFetch<Publication[]>(`/publications/purchases/${purchaseId.value}`)
  } catch {}
}

async function doPublish(platform: string, procedureType?: string | null) {
  publishingPlatform.value = platform
  try {
    const body: Record<string, any> = { platform }
    if (procedureType) body.procedure_type = procedureType
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
    showSnack(e?.detail || 'Ошибка при отправке на публикацию', 'error')
  } finally {
    publishingPlatform.value = null
  }
}

async function retryPublish(platform: string) {
  await doPublish(platform)
}

function pollPublication(pubId: number, attempts = 0) {
  if (attempts > 15) return
  setTimeout(async () => {
    await loadPublications()
    const pub = publications.value.find(p => p.id === pubId)
    if (pub && pub.status === 'publishing') pollPublication(pubId, attempts + 1)
  }, 2000)
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

async function loadPurchaseMembers() {
  if (!purchaseId.value) return
  try {
    purchaseMembers.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/members`)
  } catch { purchaseMembers.value = [] }
}

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

async function removePurchaseMember(userId: number) {
  if (!purchaseId.value) return
  try {
    await apiFetch(`/purchases/${purchaseId.value}/members/${userId}`, { method: 'DELETE' })
    await loadPurchaseMembers()
  } catch {}
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
const frameworkContracts = ref<FrameworkContract[]>([])
const frameworkDialog = ref(false)
const frameworkLoading = ref(false)
const frameworkSearch = ref('')
const selectedFrameworkContract = ref<FrameworkContract | null>(null)
const newFrameworkDialog = ref(false)
const newFrameworkSaving = ref(false)
const newFrameworkForm = reactive({
  number: '', date: '', contractor_id: null as number | null, subject: '', max_amount: null as number | null,
})

const isFramework = computed(() => form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')

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
        max_amount: newFrameworkForm.max_amount || null,
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
  } catch {
    showSnack('Ошибка создания договора', 'error')
  } finally {
    newFrameworkSaving.value = false
  }
}

// Full product add dialog
const fullProductDialog = ref(false)
const fullProductSaving = ref(false)
const fullProductIdx = ref(-1)
const fullProductPhotoFile = ref<File | null>(null)
const fullProductPhotoFileList = ref<File[]>([])
const fullProductPhotoPreview = ref<string | null>(null)
const fullProductForm = reactive({
  name: '', category: '', product_type: '', price: null as number | null,
  description: '', photo_url: '', photo_link: '', is_active: true,
  priceLinks: [] as PriceLink[],
})

const fullProductNameSearch = ref('')
const fullProductNameSuggestions = computed(() => {
  const q = (fullProductNameSearch.value || '').toLowerCase().trim()
  if (q.length < 2) return []
  return products.value
    .filter(p => p.name.toLowerCase().includes(q))
    .map(p => p.name)
    .slice(0, 15)
})
const isFullProductDuplicate = computed(() => {
  const q = (typeof fullProductForm.name === 'string' ? fullProductForm.name : '').toLowerCase().trim()
  if (!q) return false
  return products.value.some(p => p.name.toLowerCase().trim() === q)
})

const fullProductTypeOptions = computed(() => {
  const types = products.value.map(p => p.product_type).filter(Boolean) as string[]
  return [...new Set(types)].sort()
})
const fullProductCategoryOptions = computed(() => {
  const cats = products.value.map(p => p.category).filter(Boolean) as string[]
  return [...new Set(cats)].sort()
})
const fullAvgPrice = computed<number | null>(() => {
  const prices = fullProductForm.priceLinks
    .map(l => l.price)
    .filter((p): p is number => p !== null && !isNaN(Number(p)) && Number(p) > 0)
  if (!prices.length) return null
  return Math.round(prices.reduce((s, p) => s + p, 0) / prices.length * 100) / 100
})
watch(fullAvgPrice, v => { if (v !== null) fullProductForm.price = v })

function onFullPhotoFileChange(files: File[]) {
  const f = files?.[0] ?? null
  fullProductPhotoFile.value = f
  fullProductPhotoPreview.value = f ? URL.createObjectURL(f) : null
}

function openFullProduct(idx: number, prefill?: string) {
  fullProductIdx.value = idx
  Object.assign(fullProductForm, { name: prefill || '', category: '', product_type: '', price: null, description: '', photo_url: '', photo_link: '', is_active: true, priceLinks: [] })
  fullProductPhotoFile.value = null
  fullProductPhotoFileList.value = []
  fullProductPhotoPreview.value = null
  fullProductDialog.value = true
}

async function saveFullProduct() {
  if (!fullProductForm.name.trim()) return
  fullProductSaving.value = true
  try {
    const body: any = {
      name: fullProductForm.name, category: fullProductForm.category || null,
      product_type: fullProductForm.product_type || null, price: fullAvgPrice.value ?? fullProductForm.price ?? null,
      description: fullProductForm.description || null, photo_link: fullProductForm.photo_link || null,
      is_active: fullProductForm.is_active,
      price_links: fullProductForm.priceLinks.filter(l => l.url),
    }
    const created = await apiFetch<Product>('/products/', { method: 'POST', body })
    // Upload photo if selected
    if (fullProductPhotoFile.value) {
      const fd = new FormData()
      fd.append('file', fullProductPhotoFile.value)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/products/${created.id}/photo`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd,
      })
      if (res.ok) Object.assign(created, await res.json())
    }
    products.value = await apiFetch<Product[]>('/products/')
    if (fullProductIdx.value >= 0) onItemProductSelect(fullProductIdx.value, created)
    showSnack(`Товар "${created.name}" добавлен в каталог`)
    fullProductDialog.value = false
  } catch {
    showSnack('Ошибка при добавлении товара', 'error')
  } finally {
    fullProductSaving.value = false
  }
}


const totalNmck = computed(() =>
  items.value.reduce((s, i) => s + (i.total_price || 0), 0)
)

// Single purchase = contract_price auto-filled from items
const isSinglePurchase = computed(() =>
  !form.purchase_contract_type || form.purchase_contract_type === 'single'
)

// Is purchase in contracted+ status (НМЦК frozen)
const CONTRACTED_STATUSES = ['contracted', 'delivered', 'paid']
const isContracted = computed(() => CONTRACTED_STATUSES.includes(form.status))

// Saved НМЦК from DB (frozen value)
const savedNmck = ref<number | null>(null)

// Display НМЦК: manual override → frozen contracted value → live from items
const displayNmck = computed(() => {
  if (nmckMode.value === 'manual' && nmckManualValue.value != null) return nmckManualValue.value
  if (isContracted.value && savedNmck.value != null) return savedNmck.value
  return totalNmck.value
})

const nmckHint = computed(() => {
  if (isContracted.value && savedNmck.value != null) {
    return 'Зафиксирована при заключении договора. Не пересчитывается.'
  }
  return 'Сумма всех позиций. Пересчитывается автоматически. Фиксируется при заключении договора.'
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

const monthlyTotal = computed(() => {
  if (form.monthly_payment_count && form.monthly_payment_amount) {
    return form.monthly_payment_count * form.monthly_payment_amount
  }
  return null
})

const calcMonthlyTotal = () => { /* reactivity trigger — monthlyTotal is computed */ }

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }
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

// FEO — cascading selects
const selectedFeo1 = ref<number | null>(null)
const selectedFeo2 = ref<number | null>(null)
const selectedFeo3 = ref<number | null>(null)
const feoSaveAttempted = ref(false)

// Ошибка выбора ФЭО: нужно выбрать самый глубокий доступный уровень
const feoValidationError = computed((): string | null => {
  if (!form.subsidy_id || !feoLevel1Options.value.length) return null
  if (!selectedFeo1.value) return 'Выберите категорию ФЭО'
  if (feoLevel2Options.value.length > 0 && !selectedFeo2.value) return 'Выберите категорию ФЭО уровня 2'
  if (feoLevel3Options.value.length > 0 && !selectedFeo3.value) return 'Выберите категорию ФЭО уровня 3'
  return null
})

const feoLevel1Options = computed(() =>
  form.subsidy_id
    ? allFeoCategories.value.filter(c => c.subsidy_id === form.subsidy_id && !c.parent_id)
    : []
)
const feoLevel2Options = computed(() =>
  selectedFeo1.value
    ? allFeoCategories.value.filter(c => c.parent_id === selectedFeo1.value)
    : []
)
const feoLevel3Options = computed(() =>
  selectedFeo2.value
    ? allFeoCategories.value.filter(c => c.parent_id === selectedFeo2.value)
    : []
)

const updateFeoId = () => {
  form.feo_category_id = selectedFeo3.value ?? selectedFeo2.value ?? selectedFeo1.value ?? null
}

const onFeo1Change = () => { selectedFeo2.value = null; selectedFeo3.value = null; updateFeoId() }
const onFeo2Change = () => { selectedFeo3.value = null; updateFeoId() }
const onFeo3Change = () => { updateFeoId() }

// Resolve feo_category_id → path of ancestors for cascade
const resolveFeeLevels = (id: number) => {
  const path: number[] = []
  let cur = allFeoCategories.value.find(c => c.id === id)
  while (cur) {
    path.unshift(cur.id)
    cur = cur.parent_id ? allFeoCategories.value.find(c => c.id === cur!.parent_id) : undefined
  }
  selectedFeo1.value = path[0] ?? null
  selectedFeo2.value = path[1] ?? null
  selectedFeo3.value = path[2] ?? null
}

const onSubsidyChange = async () => {
  form.feo_category_id = null
  form.event_id = null
  selectedFeo1.value = null
  selectedFeo2.value = null
  selectedFeo3.value = null
  feoSaveAttempted.value = false
  calcBudget()
  loadResponsiblePersons()
  // Pre-fill delivery address from org if empty
  if (!form.delivery_address && form.subsidy_id) {
    try {
      const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
      if (subsidy?.org_id) {
        const orgs = await apiFetch<any[]>('/auth/my-orgs')
        const org = orgs.find((o: any) => o.id === subsidy.org_id)
        if (org?.address) form.delivery_address = org.address
      }
    } catch { /* silent */ }
  }
}

const calcEconomy = () => {
  // Экономия = НМЦК (зафиксированная) - Цена договора
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
  const pct = nmckExcessPct.value
  if (pct > 10) return 'error'
  if (pct > 0) return 'warning'
  return null
})

const calcBudget = async () => {
  if (!form.subsidy_id) { budgetInfo.value = null; return }
  try {
    const all = await apiFetch<any[]>(`/purchases/?subsidy_id=${form.subsidy_id}`)
    const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
    if (!subsidy) return
    const total = all
      .filter(p => !purchaseId.value || p.id !== purchaseId.value)
      .reduce((s, p) => s + (Number(p.planned_total_price) || 0), 0)
    const mine = totalNmck.value
    const remaining = subsidy.budget - total - mine
    budgetInfo.value = { remaining, exceeded: remaining < 0, over: remaining < 0 ? -remaining : 0 }
  } catch {}
}

watch(totalNmck, () => { calcEconomy(); calcBudget() })
watch(nmckMode, () => { syncContractPriceIfSingle(); calcEconomy(); calcBudget() })
watch(nmckManualValue, () => { syncContractPriceIfSingle(); calcEconomy() })
watch(contractPriceMode, () => { syncContractPriceIfSingle() })

// Items
const addItem = () => {
  const defaultType = form.item_type === 'mixed' ? '' : (form.item_type === 'услуга' ? 'услуга' : 'товар')
  items.value.push({ product_id: null, item_name: '', item_type: defaultType, quantity: null, unit: 'шт.', unit_price: null, total_price: null, final_unit_price: null, final_total: null, country_origin: '', _selectedProduct: null, _photo_url: undefined, _description: undefined })
}

const removeItem = (idx: number) => {
  items.value.splice(idx, 1)
}

// Items import from Excel
const itemsImportDialog = ref(false)
const itemsImportFile = ref<File | null>(null)
const itemsImportLoading = ref(false)
const itemsImportResult = ref<{ added: number; matched_catalog: number; unmatched: number } | null>(null)
const importTab = ref<'excel' | 'smart'>('excel')

// Smart import
const smartImportFile = ref<File | null>(null)
const smartImportLoading = ref(false)
const smartImportPreview = ref<any[] | null>(null)
const smartImportColumns = ref<string[] | null>(null)
const smartImportResult = ref<{ added: number; matched_catalog: number; unmatched: number } | null>(null)

// Column mapping
const CRM_MAPPING_FIELDS: Record<string, string> = {
  item_name: 'Наименование',
  quantity: 'Кол-во',
  unit: 'Ед. изм.',
  unit_price: 'Цена за ед.',
  total_price: 'Сумма',
}
const crmFieldSelectItems = [
  { title: 'Наименование', value: 'item_name' },
  { title: 'Кол-во', value: 'quantity' },
  { title: 'Ед. изм.', value: 'unit' },
  { title: 'Цена за ед.', value: 'unit_price' },
  { title: 'Сумма', value: 'total_price' },
  { title: '— игнорировать', value: '_ignore' },
]
const showMappingPanel = ref(false)
const columnFieldMapping = ref<Record<string, string>>({})
const columnMappingApplied = ref(false)

watch(smartImportPreview, (v) => {
  if (v) {
    columnFieldMapping.value = Object.fromEntries(Object.keys(CRM_MAPPING_FIELDS).map(f => [f, f]))
    columnMappingApplied.value = false
    showMappingPanel.value = false
  }
})

function applyColumnMapping() {
  if (!smartImportPreview.value) return
  const mapping = columnFieldMapping.value
  smartImportPreview.value = smartImportPreview.value.map(row => {
    const newRow: any = { ...row }
    for (const [field, src] of Object.entries(mapping)) {
      newRow[field] = src === '_ignore' ? null : (row[src as keyof typeof row] ?? null)
    }
    return newRow
  })
  columnMappingApplied.value = true
  showMappingPanel.value = false
}

async function downloadItemsTemplate() {
  const token = localStorage.getItem('auth_token')
  const resp = await fetch('/api/purchases/items/import/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'items_template.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadProductsTemplate() {
  const token = localStorage.getItem('auth_token')
  const resp = await fetch('/api/products/import/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'products_template.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

async function doItemsImport() {
  if (!itemsImportFile.value) return
  if (!purchaseId.value) {
    showSnack('Сначала сохраните заказ, затем импортируйте позиции', 'warning')
    return
  }
  itemsImportLoading.value = true
  itemsImportResult.value = null
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', itemsImportFile.value)
    const resp = await fetch(`/api/products/import?purchase_id=${purchaseId.value}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.message || err.detail || `Ошибка ${resp.status}`)
    }
    const data = await resp.json()
    itemsImportResult.value = { added: data.created || 0, matched_catalog: data.created || 0, unmatched: 0 }
    if (data.created > 0) {
      showSnack(`Создано ${data.created} товаров в каталоге и добавлено в закупку`)
      await loadPurchase()
    } else {
      showSnack(`Нет новых товаров (${data.skipped || 0} уже в каталоге)`, 'info')
    }
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    itemsImportLoading.value = false
  }
}

async function doSmartPreview() {
  if (!smartImportFile.value) return
  if (!purchaseId.value) {
    showSnack('Сначала сохраните закупку, затем нажмите «Распознать»', 'warning')
    return
  }
  smartImportLoading.value = true
  smartImportPreview.value = null
  smartImportResult.value = null
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', smartImportFile.value)
    const resp = await fetch(`/api/purchases/${purchaseId.value}/items/import-smart?confirm=false`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
    }
    const data = await resp.json()
    smartImportPreview.value = data.preview || []
    smartImportColumns.value = data.columns_found || []
    if (!smartImportPreview.value.length) showSnack('Позиции не распознаны', 'warning')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка распознавания', 'error')
  } finally {
    smartImportLoading.value = false
  }
}

async function doSmartImport() {
  if (!purchaseId.value || !smartImportPreview.value?.length) return

  // If user applied custom column mapping, add items directly from re-mapped preview
  if (columnMappingApplied.value) {
    const newItems = smartImportPreview.value.map(row => ({
      product_id: null,
      item_name: row.item_name || '',
      item_type: row.item_type || 'товар',
      quantity: row.quantity ?? null,
      unit: row.unit || 'шт.',
      unit_price: row.unit_price ?? null,
      total_price: row.total_price ?? null,
      final_unit_price: null,
      final_total: null,
      country_origin: '',
      _selectedProduct: null,
      _photo_url: undefined,
      _description: undefined,
    }))
    items.value.push(...newItems)
    smartImportResult.value = { added: newItems.length, matched_catalog: 0, unmatched: newItems.length }
    showSnack(`${newItems.length} позиций добавлены в список. Сохраните закупку.`, 'info')
    itemsImportDialog.value = false
    return
  }

  if (!smartImportFile.value) return
  smartImportLoading.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', smartImportFile.value)
    const resp = await fetch(`/api/purchases/${purchaseId.value}/items/import-smart?confirm=true`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || err.message || `Ошибка ${resp.status}`)
    }
    smartImportResult.value = await resp.json()
    if (smartImportResult.value!.added > 0) {
      showSnack(`Импортировано ${smartImportResult.value!.added} позиций`)
      await loadPurchase()
    }
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    smartImportLoading.value = false
  }
}

const calcItemTotal = (idx: number) => {
  const item = items.value[idx]
  if (item.quantity != null && item.unit_price != null) {
    item.total_price = Math.round(item.quantity * item.unit_price * 100) / 100
  } else {
    item.total_price = null
  }
  // Auto-sync contract_price for single purchases
  nextTick(() => syncContractPriceIfSingle())
}

const onItemProductSelect = (idx: number, val: any) => {
  const item = items.value[idx]
  if (!val) {
    // Cleared
    item.item_name = ''
    item.product_id = null
    item._selectedProduct = null
    item._photo_url = undefined
    item._description = undefined
    item._description_44fz = undefined
  } else if (typeof val === 'string') {
    item.item_name = val
    item.product_id = null
    item._selectedProduct = val
    item._photo_url = undefined
    item._description = undefined
    item._description_44fz = undefined
  } else {
    // Full product object selected via return-object
    item.item_name = val.name || ''
    item.product_id = val.id
    item._selectedProduct = val
    item._photo_url = val.photo_url || val.photo_link || undefined
    item._description = val.description || undefined
    item._description_44fz = val.description_44fz || undefined
    if (val.product_type && !item.item_type) item.item_type = val.product_type
    if (!item.unit_price) {
      // Приоритет: контрактная цена (из договора) → каталожная цена
      const bestPrice = val.contract_price ?? val.price
      if (bestPrice) {
        item.unit_price = Number(bestPrice)
        calcItemTotal(idx)
      }
    }
  }
}

// Custom filter for combobox — Vuetify calls this with the full products array (stable ref),
// so items never "change" while typing → no Vuetify search-reset bug
const productFilter = (_value: string, query: string, item?: any): boolean => {
  if (!query.trim()) return true
  const q = query.toLowerCase().trim()
  const name = (item?.raw?.name || '').toLowerCase()
  const desc = (item?.raw?.description || '').toLowerCase()
  const type = (item?.raw?.product_type || '').toLowerCase()
  return name.includes(q) || desc.includes(q) || type.includes(q)
}

function productItemsFor(search?: string): Product[] {
  const q = (search || '').toLowerCase().trim()
  if (!q) return products.value
  return products.value.filter(p => {
    const name = (p.name || '').toLowerCase()
    const desc = (p.description || '').toLowerCase()
    const type = (p.product_type || '').toLowerCase()
    return name.includes(q) || desc.includes(q) || type.includes(q)
  })
}

// Product picker dialog
const productPickerDialog = ref(false)
const productPickerSearch = ref('')
const productPickerIdx = ref(-1)

const productPickerResults = computed(() => productItemsFor(productPickerSearch.value))

function openProductPicker(idx: number) {
  productPickerIdx.value = idx
  productPickerSearch.value = items.value[idx].item_name || ''
  productPickerDialog.value = true
}

function selectFromPicker(prod: Product) {
  productPickerDialog.value = false
  onItemProductSelect(productPickerIdx.value, prod)
}

function clearItem(idx: number) {
  items.value[idx].item_name = ''
  items.value[idx].product_id = null
  items.value[idx]._selectedProduct = null
  items.value[idx]._photo_url = undefined
  items.value[idx]._description = undefined
}

const hasProducts = computed(() => items.value.some(i => i.item_name?.trim()))

// Date validation rules
const contractDateRules = computed(() => [
  (v: string) => !v || !form.execution_term || v <= form.execution_term
    || 'Дата договора не может быть позже срока исполнения',
])
const executionTermRules = computed(() => [
  (v: string) => !v || !form.execution_term_changed || v <= form.execution_term_changed
    || 'Срок исполнения не может быть позже изменённого срока',
])

const nextStatusTarget = computed(() => {
  if (!isEdit.value || !form.status) return null
  const idx = STATUS_ORDER.indexOf(form.status)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
})

const needsContract = computed(() => form.status === 'work_in_progress')
const needsAcceptance = computed(() => form.status === 'contracted')
const needsPayment = computed(() => form.status === 'delivered')

const loadRefs = async () => {
  const [subs, cons, feos, prods, evts] = await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/'),
    apiFetch<Contractor[]>('/contractors/'),
    apiFetch<FeoCategory[]>('/feo-categories/'),
    apiFetch<Product[]>('/products/'),
    apiFetch<EventItem[]>('/events/'),
  ])
  subsidies.value = subs
  contractors.value = cons
  allFeoCategories.value = feos
  products.value = prods
  allEvents.value = evts
  loadOrgUsers()
}

const contractorFilter = (value: string, query: string, item?: any): boolean => {
  const q = query.toLowerCase()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}

const onContractorSelect = (id: number | null) => {
  const c = contractors.value.find(c => c.id === id)
  contractorInn.value = c?.inn || ''
}

const onInnInput = (val: string) => {
  const c = contractors.value.find(c => c.inn === val.trim())
  if (c) form.contractor_id = c.id
}

const loadPurchase = async () => {
  const data = await apiFetch<any>(`/purchases/${purchaseId.value}`)
  Object.assign(form, {
    purchase_method: data.purchase_method || '',
    purchase_basis: data.purchase_basis || '',
    item_type: data.item_type || 'товар',
    subsidy_id: data.subsidy_id ?? null,
    contractor_id: data.contractor_id ?? null,
    registry_number: data.registry_number || '',
    feo_category_id: data.feo_category_id ?? null,
    subject: data.subject || '',
    contract_price: data.contract_price ? Number(data.contract_price) : null,
    economy: data.economy ? Number(data.economy) : null,
    price_increase: data.price_increase ? Number(data.price_increase) : null,
    contract_number: data.contract_number || '',
    contract_date: data.contract_date || '',
    contract_end_date: data.contract_end_date || '',
    delivery_date: data.delivery_date || '',
    delivery_address: data.delivery_address || '',
    procurement_planned_date: data.procurement_planned_date || '',
    execution_term: data.execution_term || '',
    execution_term_changed: data.execution_term_changed || '',
    acceptance_doc_name: data.acceptance_doc_name || '',
    acceptance_doc_number: data.acceptance_doc_number || '',
    acceptance_doc_date: data.acceptance_doc_date || '',
    acceptance_doc_amount: data.acceptance_doc_amount ? Number(data.acceptance_doc_amount) : null,
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
    purchase_contract_type: data.purchase_contract_type || 'single',
    contract_id: data.contract_id ?? null,
    framework_seq: data.framework_seq ?? null,
    responsible_person: data.responsible_person || '',
    vat_applicable: !!data.vat_applicable,
    vat_rate: data.vat_rate ?? null,
    vat_exemption_article: data.vat_exemption_article || '',
    third_party_involved: !!data.third_party_involved,
    service_period_type: data.service_period_type || 'period',
    service_start_date: data.service_start_date || '',
    service_end_date: data.service_end_date || '',
    description_mode: data.description_mode || 'exact',
    event_id: data.event_id ?? null,
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
  })

  // Save frozen НМЦК from DB
  savedNmck.value = data.total_nmck ? Number(data.total_nmck) : null

  loadResponsiblePersons()

  // Restore selected framework contract
  if (data.contract_id && (form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')) {
    try {
      const contracts = await apiFetch<FrameworkContract[]>(`/contracts/?subsidy_id=${data.subsidy_id || ''}`)
      selectedFrameworkContract.value = contracts.find(c => c.id === data.contract_id) ?? null
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
        _selectedProduct: prod ?? (i.item_name || null),
        _photo_url: prod?.photo_url || undefined,
        _description: i.product_description || prod?.description || undefined,
        _description_44fz: i.product_description_44fz || prod?.description_44fz || undefined,
      }
    })
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

  // Resolve FEO cascade
  if (data.feo_category_id) resolveFeeLevels(data.feo_category_id)

  // Load uploaded files
  uploadedFiles.value = data.files || []

  // Auto-fill INN
  if (data.contractor_id) {
    const c = contractors.value.find(c => c.id === data.contractor_id)
    contractorInn.value = c?.inn || ''
  }

  calcBudget()

  // Restore manual НМЦК if saved value differs from items total
  if (savedNmck.value != null && !isContracted.value) {
    const itemsTotal = items.value.reduce((s, i) => s + (i.total_price || 0), 0)
    if (Math.abs(savedNmck.value - itemsTotal) > 0.01) {
      nmckMode.value = 'manual'
      nmckManualValue.value = savedNmck.value
    }
  }
}

// ---------------------------------------------------------------------------
// Autosave draft for new purchases
// ---------------------------------------------------------------------------
const DRAFT_KEY = 'purchase_form_draft'
const draftSaved = ref(false)
const hasDraft = computed(() => !!localStorage.getItem(DRAFT_KEY))
let autosaveTimer: ReturnType<typeof setTimeout> | null = null

function saveDraft() {
  if (isEdit.value) return
  localStorage.setItem(DRAFT_KEY, JSON.stringify({ form: { ...form }, items: items.value, contractorInn: contractorInn.value }))
  draftSaved.value = true
  setTimeout(() => { draftSaved.value = false }, 2000)
}

function loadDraft() {
  if (isEdit.value) return
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const draft = JSON.parse(raw)
    // Support both old format (plain form fields) and new format ({form, items, contractorInn})
    const formData = draft.form || draft
    Object.assign(form, formData)
    if (draft.items?.length) items.value = draft.items
    if (draft.contractorInn) contractorInn.value = draft.contractorInn
    showSnack('Черновик восстановлен', 'info')
  } catch {}
}

function clearDraft() {
  localStorage.removeItem(DRAFT_KEY)
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
    loadAllUsers()
    approvalPanelRef.value?.loadApprovals()
  } else {
    loadDraft()
    // Auto-fill based on route formMode
    if (formMode.value === 'service_note_delivery') {
      form.purchase_basis = 'service_note'
      form.purchase_method = 'single'
    } else if (formMode.value === 'advance_report') {
      form.purchase_method = 'advance'
    }
  }
})

const save = async () => {
  const { valid } = await formRef.value.validate()
  feoSaveAttempted.value = true
  const feoErr = feoValidationError.value
  if (!valid || feoErr) {
    if (feoErr) showSnack(feoErr, 'error')
    return
  }
  if (form.item_type === 'mixed') {
    const missingType = items.value.filter(i => i.item_name?.trim() && !i.item_type)
    if (missingType.length) {
      showSnack(`Укажите тип для ${missingType.length} позиции(й) перед сохранением`, 'error')
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
  saving.value = true
  try {
    const validItems = items.value
      .filter(i => i.item_name?.trim())
      .map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => ({
        ...rest,
        unit_price: (rest.unit_price !== '' && rest.unit_price != null) ? rest.unit_price : null,
        quantity: (rest.quantity !== '' && rest.quantity != null) ? rest.quantity : null,
      }))
    const payload = {
      ...form,
      planned_total_price: displayNmck.value || null,
      total_nmck: displayNmck.value || null,
      contract_date: form.contract_date || null,
      contract_end_date: form.contract_end_date || null,
      delivery_date: form.delivery_date || null,
      delivery_address: form.delivery_address || null,
      procurement_planned_date: form.procurement_planned_date || null,
      execution_term: form.execution_term || null,
      execution_term_changed: form.execution_term_changed || null,
      service_start_date: form.service_start_date || null,
      service_end_date: form.service_end_date || null,
      acceptance_doc_date: form.acceptance_doc_date || null,
      payment_doc_date: form.payment_doc_date || null,
      items: validItems,
      subsidy_allocations: form.subsidy_allocations.filter(a => a.subsidy_id > 0),
    }
    // Save new delivery address to history
    if (form.delivery_address) saveDeliveryAddressIfNew(form.delivery_address)

    const qs = adminOverride ? '?admin_override=true' : ''
    if (isEdit.value) {
      await apiFetch(`/purchases/${purchaseId.value}${qs}`, { method: 'PUT', body: payload })
      showSnack('Сохранено')
    } else {
      const created = await apiFetch<any>(`/purchases/${qs}`, { method: 'POST', body: payload })
      clearDraft()
      showSnack('Закупка создана')
      router.push(`/orders/${created.id}/edit`)
    }
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
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
    showSnack(`Статус → ${STATUS_LABEL[updated.status]}`)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка смены статуса', 'error')
  } finally {
    transitioning.value = false
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
      let detail = 'Ошибка загрузки'
      try { const err = await res.json(); detail = err.detail || detail } catch {}
      showSnack(detail, 'error')
      return
    }
    const uploaded = await res.json()
    uploadedFiles.value.push(uploaded)
    showSnack('Файл загружен')
  } catch {
    showSnack('Ошибка загрузки файла', 'error')
  } finally {
    uploading.value = false
    if (fileInputEl.value) fileInputEl.value.value = ''
  }
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

const downloadDoc = async (docType: string, extraParams = '') => {
  if (!purchaseId.value) return
  docLoading.value = docType
  try {
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/documents/${docType}${extraParams}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ошибка генерации документа' }))
      showSnack(err.detail || 'Ошибка генерации документа', 'error')
      return
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : `${docType}.docx`
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
    () => showSnack('Текст письма скопирован'),
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
    () => showSnack('Текст письма скопирован'),
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
    a.download = `KP_items_${purchaseId.value}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    showSnack('Ошибка загрузки xlsx', 'error')
  }
}
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
</style>
