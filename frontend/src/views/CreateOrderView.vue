<template>
  <v-container fluid class="pa-6" style="max-width:1200px">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">
          {{ isEdit ? `Закупка #${form.purchase_number || route.params.id}` : 'Новая закупка' }}
        </h1>
        <div class="d-flex align-center gap-2 mt-1">
          <v-chip v-if="isEdit && form.status" :color="STATUS_COLOR[form.status]" size="small" variant="tonal">
            {{ STATUS_LABEL[form.status] }}
          </v-chip>
          <span v-if="isEdit && form.registry_number" class="text-caption text-medium-emphasis">
            Реестр: {{ form.registry_number }}
          </span>
        </div>
      </div>
      <v-btn variant="outlined" prepend-icon="mdi-arrow-left" to="/orders">К списку</v-btn>
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
            <v-col cols="12" md="3">
              <v-select v-model="form.purchase_method"
                :items="[{value:'single',title:'Единственный поставщик'},{value:'competitive',title:'Конкурсная процедура'},{value:'advance',title:'Авансовый отчёт'}]"
                item-title="title" item-value="value" label="Способ закупки" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="form.subsidy_id" :items="subsidies" item-title="name" item-value="id"
                label="Субсидия *" variant="outlined" density="compact"
                :rules="[r => !!r || 'Выберите субсидию']" @update:model-value="onSubsidyChange" />
            </v-col>
            <v-col cols="12" md="3">
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
                @update:model-value="onContractorSelect"
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template #subtitle>
                      <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
                    </template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model="contractorInn"
                label="ИНН"
                variant="outlined"
                density="compact"
                maxlength="12"
                @update:model-value="onInnInput"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model="form.subject"
                label="Предмет договора"
                variant="outlined"
                density="compact"
                placeholder="Поставка оборудования..."
              />
            </v-col>
            <!-- FEO level 1 — появляется после выбора субсидии -->
            <v-col v-if="form.subsidy_id && feoLevel1Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo1" :items="feoLevel1Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.1)" variant="outlined" density="compact" clearable
                @update:model-value="onFeo1Change" />
            </v-col>
            <!-- FEO level 2 — появляется после выбора ур.1 -->
            <v-col v-if="selectedFeo1 && feoLevel2Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo2" :items="feoLevel2Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.2)" variant="outlined" density="compact" clearable
                @update:model-value="onFeo2Change" />
            </v-col>
            <!-- FEO level 3 — появляется после выбора ур.2 -->
            <v-col v-if="selectedFeo2 && feoLevel3Options.length" cols="12" md="4">
              <v-select v-model="selectedFeo3" :items="feoLevel3Options" item-title="name" item-value="id"
                label="Категория ФЭО (ур.3)" variant="outlined" density="compact" clearable
                @update:model-value="onFeo3Change" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.registry_number" label="Реестровый номер"
                variant="outlined" density="compact" :readonly="!isEdit"
                :bg-color="!isEdit ? 'grey-lighten-4' : undefined"
                hint="Генерируется автоматически" persistent-hint />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 2. Позиции закупки -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center justify-space-between">
          <span>Позиции закупки</span>
          <v-chip color="primary" variant="tonal" size="small">
            НМЦК: {{ formatMoney(totalNmck) }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <div class="overflow-x-auto">
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="min-width:280px">Наименование</th>
                  <th style="min-width:130px">Тип</th>
                  <th style="min-width:80px">Кол-во</th>
                  <th style="min-width:70px">Ед.</th>
                  <th style="min-width:110px">Цена ед., ₽</th>
                  <th style="min-width:110px">Сумма, ₽</th>
                  <th style="width:48px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in items" :key="idx">
                  <td style="min-width:300px">
                    <div class="d-flex align-center gap-1">
                      <!-- Mini thumbnail in row -->
                      <v-tooltip v-if="item._photo_url" location="right">
                        <template #activator="{ props: tip }">
                          <v-avatar v-bind="tip" size="36" rounded="sm" class="flex-shrink-0" style="cursor:pointer">
                            <v-img :src="item._photo_url" cover />
                          </v-avatar>
                        </template>
                        <v-img :src="item._photo_url" width="200" height="200" cover style="border-radius:8px" />
                      </v-tooltip>
                      <v-icon v-else size="28" class="flex-shrink-0 text-medium-emphasis">mdi-package-variant</v-icon>

                      <v-text-field
                        v-model="item.item_name"
                        density="compact"
                        variant="outlined"
                        hide-details
                        clearable
                        readonly
                        class="my-1"
                        style="cursor:pointer"
                        placeholder="Нажмите для выбора..."
                        @click="openProductPicker(idx)"
                        @click:clear.stop="clearItem(idx)"
                      />
                      <v-tooltip text="Добавить новый товар в каталог" location="top">
                        <template #activator="{ props: tip }">
                          <v-btn v-bind="tip" icon="mdi-plus" size="x-small" variant="tonal"
                            color="primary" class="flex-shrink-0 ml-1"
                            @click.stop="openFullProduct(idx, item.item_name)" />
                        </template>
                      </v-tooltip>
                    </div>
                  </td>
                  <td>
                    <v-select v-model="item.item_type"
                      :items="[{value:'товар',title:'Товар'},{value:'услуга',title:'Услуга'},{value:'работа',title:'Работа'}]"
                      item-title="title" item-value="value" density="compact" variant="outlined"
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
                    <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                      @click="removeItem(idx)" />
                  </td>
                </tr>
                <tr v-if="!items.length">
                  <td colspan="7" class="text-center text-medium-emphasis py-4">
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
          <div class="d-flex gap-2">
            <v-btn
              v-if="isEdit"
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-file-word-outline"
              :loading="docLoading === 'contract_tz'"
              @click="downloadDoc('contract_tz')"
            >
              Скачать ТЗ (.docx)
            </v-btn>
            <v-chip v-else size="small" color="grey" variant="tonal">Сохраните закупку для скачивания</v-chip>
          </div>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-table density="comfortable" class="tz-table">
            <thead>
              <tr style="background:#F0F7FF">
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
                  <v-avatar v-if="item._photo_url" size="56" rounded="sm">
                    <v-img :src="item._photo_url" cover />
                  </v-avatar>
                  <v-icon v-else size="40" color="grey-lighten-2">mdi-image-off-outline</v-icon>
                </td>
                <td class="py-2">
                  <div class="font-weight-medium" style="font-size:13px">{{ item.item_name }}</div>
                  <div v-if="item._description" class="text-caption text-medium-emphasis mt-1" style="white-space:pre-line;max-width:420px">
                    {{ item._description }}
                  </div>
                </td>
                <td class="text-center">{{ item.quantity ?? '—' }}</td>
                <td class="text-center">{{ item.unit || '—' }}</td>
                <td class="text-right">{{ item.unit_price != null ? item.unit_price.toLocaleString('ru-RU', {minimumFractionDigits:2}) : '—' }}</td>
                <td class="text-right font-weight-medium">{{ item.total_price != null ? item.total_price.toLocaleString('ru-RU', {minimumFractionDigits:2}) : '—' }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr style="background:#F9FAFB">
                <td colspan="6" class="text-right font-weight-bold pa-3" style="font-size:13px">Итого НМЦК:</td>
                <td class="text-right font-weight-bold pa-3" style="font-size:13px;color:#3B82F6">{{ formatMoney(totalNmck) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </v-card-text>
      </v-card>

      <!-- 3. Финансы -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Финансовые показатели</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field :model-value="formatMoney(totalNmck)" label="НМЦК (итого)" variant="outlined"
                density="compact" readonly bg-color="grey-lighten-4" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="form.contract_price" label="Цена договора" variant="outlined"
                density="compact" type="number" suffix="₽" @update:model-value="calcEconomy" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field :model-value="form.economy ?? ''" label="Экономия (авто)" variant="outlined"
                density="compact" suffix="₽" readonly bg-color="grey-lighten-4" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="form.price_increase" label="Увеличение цены (доп. соглашения)"
                variant="outlined" density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
          <!-- Тип договора -->
          <v-row class="mt-0">
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
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 4. Договор -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Договор</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.contract_number" label="Номер договора" variant="outlined" density="compact"
                :hint="needsContract ? 'Обязательно для перехода в статус Договор' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.contract_date" label="Дата договора" variant="outlined"
                density="compact" type="date"
                :rules="contractDateRules" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
                density="compact" type="date"
                :rules="executionTermRules" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.execution_term_changed" label="Срок (с учётом изменений)"
                variant="outlined" density="compact" type="date" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 5. Акт приёмки -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Акт приёмки</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.acceptance_doc_name" label="Наименование документа" variant="outlined" density="compact"
                :hint="needsAcceptance ? 'Обязательно для перехода в статус Поставлено' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_number" label="Номер акта" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_date" label="Дата акта" variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.acceptance_doc_amount" label="Сумма акта" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 6. Платёж -->
      <v-card variant="outlined" class="mb-4">
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
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 7. Файлы (только в режиме редактирования) -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы к закупке</v-card-title>
        <v-card-text>
          <div class="d-flex align-center gap-3 mb-3">
            <v-btn prepend-icon="mdi-upload" variant="tonal" size="small"
              :loading="uploading" @click="fileInputEl?.click()">
              Загрузить файл
            </v-btn>
            <span class="text-caption text-medium-emphasis">PDF, Word, Excel, JPEG, PNG</span>
          </div>
          <input ref="fileInputEl" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
            style="display:none" @change="uploadFile" />

          <v-list v-if="uploadedFiles.length" density="compact" lines="one">
            <v-list-item v-for="f in uploadedFiles" :key="f.id"
              :prepend-icon="fileIcon(f.mime_type)"
              :title="f.filename"
              :subtitle="formatSize(f.size)"
            >
              <template #append>
                <v-btn icon="mdi-download" variant="text" size="small" @click="downloadFile(f.id, f.filename)" />
                <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                  @click="deleteFile(f.id)" />
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="text-caption text-medium-emphasis">Нет загруженных файлов</div>
        </v-card-text>
      </v-card>

      <!-- 8. Формирование документов (только в режиме редактирования) -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы</v-card-title>
        <v-card-text>
          <div class="d-flex gap-3 flex-wrap">
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'service_note'"
              @click="downloadDoc('service_note')"
            >
              Служебная записка
            </v-btn>
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'contract_tz'"
              @click="downloadDoc('contract_tz')"
            >
              Договор + ТЗ
            </v-btn>
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'approval_sheet'"
              @click="downloadDoc('approval_sheet')"
            >
              Лист согласования
            </v-btn>
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            Документы формируются по шаблонам из backend/templates/
          </div>
        </v-card-text>
      </v-card>

      <!-- 9. Публикация на площадках (только в режиме редактирования) -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4" style="border-color:#7C3AED">
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
            <tbody>
              <tr v-for="pub in publications" :key="pub.id">
                <td style="width:160px" class="font-weight-medium">{{ PLATFORM_LABELS[pub.platform] || pub.platform }}</td>
                <td style="width:140px">
                  <v-chip size="x-small" :color="PUB_STATUS_COLOR[pub.status]" variant="tonal">
                    {{ PUB_STATUS_LABEL[pub.status] || pub.status }}
                  </v-chip>
                </td>
                <td>
                  <a v-if="pub.external_url" :href="pub.external_url" target="_blank"
                    class="text-caption text-blue-darken-2 text-decoration-none">
                    {{ pub.external_id || 'Открыть на площадке' }}
                    <v-icon size="12">mdi-open-in-new</v-icon>
                  </a>
                  <span v-else-if="pub.external_id" class="text-caption">{{ pub.external_id }}</span>
                </td>
                <td class="text-caption text-medium-emphasis">
                  {{ pub.error_text || (pub.published_at ? new Date(pub.published_at).toLocaleDateString('ru-RU') : '') }}
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

      <!-- Кнопки -->
      <div class="d-flex gap-3 mt-4 flex-wrap">
        <v-btn type="submit" color="primary" size="large" :loading="saving" prepend-icon="mdi-content-save">
          {{ isEdit ? 'Сохранить' : 'Создать закупку' }}
        </v-btn>
        <v-btn v-if="isEdit && nextStatusTarget" :color="STATUS_COLOR[nextStatusTarget]" size="large"
          variant="tonal" :loading="transitioning" prepend-icon="mdi-arrow-right-circle" @click="doTransition">
          → {{ STATUS_LABEL[nextStatusTarget] }}
        </v-btn>
        <v-btn variant="outlined" to="/orders" size="large">Отмена</v-btn>
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
                  color="deep-purple" variant="tonal" size="small"
                  :loading="publishingPlatform === pl.value"
                  :disabled="isPlatformPublished(pl.value)"
                  @click="doPublish(pl.value)"
                >
                  {{ isPlatformPublished(pl.value) ? 'Опубликовано' : 'Опубликовать' }}
                </v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="publishDialog = false">Закрыть</v-btn>
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
                <v-img :src="fullProductPhotoPreview" max-height="140" contain class="rounded border bg-grey-lighten-4" />
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
                  <v-avatar size="36" rounded="sm" class="my-1">
                    <v-img v-if="p.photo_url || p.photo_link" :src="p.photo_url || p.photo_link" cover />
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
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => !!route.params.id)
const purchaseId = computed(() => Number(route.params.id) || null)

const STATUS_ORDER = ['planned', 'confirmed', 'in_progress', 'contracted', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  planned: 'orange', confirmed: 'blue',
  in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const COUNTRIES = ['Российская Федерация', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

interface FeoCategory { id: number; name: string; parent_id: number | null; level: number; subsidy_id: number }
interface Contractor { id: number; name: string; inn?: string }
interface Subsidy { id: number; name: string; year: number; budget: number }
interface Product { id: number; name: string; price?: number; product_type?: string; description?: string; photo_url?: string; photo_link?: string; category?: string }
interface FrameworkContract { id: number; number: string; date?: string; contract_type: string; contractor_id?: number; contractor_name?: string; contractor_inn?: string; subject?: string; max_amount?: number; remaining?: number; status?: string }
interface PriceLink { url: string; price: number | null }
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
}
interface UploadedFile { id: number; purchase_id: number; filename: string; mime_type?: string; size?: number }

const form = reactive({
  purchase_method: '',
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
  status: 'planned',
  purchase_number: null as number | null,
  purchase_contract_type: 'single' as string,
  contract_id: null as number | null,
})

const items = ref<OrderItem[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const products = ref<Product[]>([])
const allFeoCategories = ref<FeoCategory[]>([])
const formRef = ref()
const saving = ref(false)
const transitioning = ref(false)
const uploading = ref(false)
const docLoading = ref<string | null>(null)
const snack = reactive({ show: false, text: '', color: 'success' })
const budgetInfo = ref<{ remaining: number; exceeded: boolean; over: number } | null>(null)
const budgetOverrideDialog = ref(false)
const isAdmin = computed(() => localStorage.getItem('user_role') === 'admin')
const contractorInn = ref('')
const fileInputEl = ref<HTMLInputElement | null>(null)
const uploadedFiles = ref<UploadedFile[]>([])

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

const publications = ref<Publication[]>([])
const publishDialog = ref(false)
const publishingPlatform = ref<string | null>(null)

const isPlatformPublished = (platform: string) =>
  publications.value.some(p => p.platform === platform && p.status === 'published')

async function loadPublications() {
  if (!purchaseId.value) return
  try {
    publications.value = await apiFetch<Publication[]>(`/publications/purchases/${purchaseId.value}`)
  } catch {}
}

async function doPublish(platform: string) {
  publishingPlatform.value = platform
  try {
    const pub = await apiFetch<Publication>(`/publications/purchases/${purchaseId.value}`, {
      method: 'POST',
      body: { platform },
    })
    publications.value.unshift(pub)
    showSnack(`Отправлено на публикацию: ${PLATFORM_LABELS[platform]}`)
    publishDialog.value = false
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

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }
const formatMoney = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
const formatSize = (bytes?: number) => !bytes ? '' : bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' МБ' : (bytes / 1024).toFixed(0) + ' КБ'

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

const onSubsidyChange = () => {
  form.feo_category_id = null
  selectedFeo1.value = null
  selectedFeo2.value = null
  selectedFeo3.value = null
  calcBudget()
}

const calcEconomy = () => {
  form.economy = (totalNmck.value > 0 && form.contract_price != null)
    ? Math.round((totalNmck.value - form.contract_price) * 100) / 100
    : null
}

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

// Items
const addItem = () => {
  items.value.push({ product_id: null, item_name: '', item_type: 'товар', quantity: null, unit: 'шт.', unit_price: null, total_price: null, final_unit_price: null, final_total: null, _selectedProduct: null, _photo_url: undefined, _description: undefined })
}

const removeItem = (idx: number) => {
  items.value.splice(idx, 1)
}

const calcItemTotal = (idx: number) => {
  const item = items.value[idx]
  if (item.quantity != null && item.unit_price != null) {
    item.total_price = Math.round(item.quantity * item.unit_price * 100) / 100
  } else {
    item.total_price = null
  }
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
  } else if (typeof val === 'string') {
    item.item_name = val
    item.product_id = null
    item._selectedProduct = val
    item._photo_url = undefined
    item._description = undefined
  } else {
    // Full product object selected via return-object
    item.item_name = val.name || ''
    item.product_id = val.id
    item._selectedProduct = val
    item._photo_url = val.photo_url || val.photo_link || undefined
    item._description = val.description || undefined
    if (val.product_type && !item.item_type) item.item_type = val.product_type
    if (val.price && !item.unit_price) {
      item.unit_price = Number(val.price)
      calcItemTotal(idx)
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

const needsContract = computed(() => form.status === 'confirmed')
const needsAcceptance = computed(() => form.status === 'contracted')
const needsPayment = computed(() => form.status === 'delivered')

const loadRefs = async () => {
  const [subs, cons, feos, prods] = await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/'),
    apiFetch<Contractor[]>('/contractors/'),
    apiFetch<FeoCategory[]>('/feo-categories/'),
    apiFetch<Product[]>('/products/'),
  ])
  subsidies.value = subs
  contractors.value = cons
  allFeoCategories.value = feos
  products.value = prods
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
    status: data.status || 'planned',
    purchase_number: data.purchase_number ?? null,
    purchase_contract_type: data.purchase_contract_type || 'single',
    contract_id: data.contract_id ?? null,
  })

  // Restore selected framework contract
  if (data.contract_id && (form.purchase_contract_type === 'framework_cumulative' || form.purchase_contract_type === 'framework_with_amount')) {
    try {
      const contracts = await apiFetch<FrameworkContract[]>(`/contracts/?subsidy_id=${data.subsidy_id || ''}`)
      selectedFrameworkContract.value = contracts.find(c => c.id === data.contract_id) ?? null
    } catch {}
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
        _selectedProduct: prod ?? (i.item_name || null),
        _photo_url: prod?.photo_url || undefined,
        _description: prod?.description || undefined,
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
}

onMounted(async () => {
  await loadRefs()
  if (isEdit.value && purchaseId.value) {
    await loadPurchase()
    await loadPublications()
  }
})

const save = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return
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
      .map(({ _selectedProduct, _photo_url, _description, ...rest }) => rest)
    const payload = {
      ...form,
      planned_total_price: totalNmck.value || null,
      total_nmck: totalNmck.value || null,
      contract_date: form.contract_date || null,
      execution_term: form.execution_term || null,
      execution_term_changed: form.execution_term_changed || null,
      acceptance_doc_date: form.acceptance_doc_date || null,
      payment_doc_date: form.payment_doc_date || null,
      items: validItems,
    }
    const qs = adminOverride ? '?admin_override=true' : ''
    if (isEdit.value) {
      await apiFetch(`/purchases/${purchaseId.value}${qs}`, { method: 'PUT', body: payload })
      showSnack('Сохранено')
    } else {
      const created = await apiFetch<any>(`/purchases/${qs}`, { method: 'POST', body: payload })
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

// File upload
const uploadFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !purchaseId.value) return
  uploading.value = true
  try {
    const file = input.files[0]
    const fd = new FormData()
    fd.append('file', file)
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

const deleteFile = async (fid: number) => {
  try {
    await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
    uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
    showSnack('Файл удалён')
  } catch {
    showSnack('Ошибка удаления', 'error')
  }
}

const downloadDoc = async (docType: string) => {
  if (!purchaseId.value) return
  docLoading.value = docType
  try {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/documents/${docType}`, {
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
</script>
