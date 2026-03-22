<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Каталог товаров</h1>
        <span class="text-body-2 text-medium-emphasis">{{ products.length }} позиций</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="outlined" prepend-icon="mdi-download-outline" @click="downloadTemplate">Шаблон</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-upload-outline" color="secondary" @click="importDialog.show = true">Импорт Excel</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-image-sync" color="teal" @click="openDownloadPhotosDialog">Скачать фото</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-content-duplicate" color="warning" :loading="deduplicating" @click="deduplicateProducts">Удалить дубликаты</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Добавить товар</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-table-column" @click="colConfigDialog = true">Столбцы</v-btn>
      </div>
    </div>

    <!-- Search + filter -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex gap-3 flex-wrap align-center">
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по наименованию / описанию"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:240px"
          />
          <v-combobox
            v-model="filterType"
            :items="typeOptions"
            label="Тип" variant="outlined" density="compact"
            clearable hide-details style="min-width:160px"
          />
          <v-combobox
            v-model="filterCategory"
            :items="categoryOptions"
            label="Категория" variant="outlined" density="compact"
            clearable hide-details style="min-width:160px"
          />
          <v-select
            v-model="filterActive"
            :items="[{title:'Активные',value:true},{title:'Неактивные',value:false}]"
            label="Статус" variant="outlined" density="compact"
            clearable hide-details style="min-width:140px"
          />
          <v-text-field
            v-model.number="filterPriceMin"
            label="Цена от, ₽" type="number"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:120px;max-width:140px"
          />
          <v-text-field
            v-model.number="filterPriceMax"
            label="Цена до, ₽" type="number"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:120px;max-width:140px"
          />
          <v-btn
            v-if="filterType || filterCategory || filterActive !== null || filterPriceMin || filterPriceMax"
            variant="text" size="small" prepend-icon="mdi-filter-off" color="grey-darken-1"
            @click="filterType = null; filterCategory = null; filterActive = null; filterPriceMin = null; filterPriceMax = null"
          >Сбросить</v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <v-card variant="outlined">
      <!-- Bulk action bar -->
      <v-toolbar v-if="selectedIds.length" color="primary" density="compact" class="px-2 rounded-t">
        <span class="text-body-2 ml-2 font-weight-medium">Выбрано: {{ selectedIds.length }}</span>
        <v-btn variant="text" size="small" prepend-icon="mdi-close-circle" color="white" class="ml-2"
          @click="selectedIds = []">Снять</v-btn>
        <v-btn v-if="selectedIds.length < filteredProducts.length" variant="text" size="small" prepend-icon="mdi-select-all" color="white" class="ml-1"
          @click="selectedIds = filteredProducts.map(p => p.id)">Выбрать все ({{ filteredProducts.length }})</v-btn>
        <v-spacer />
        <v-btn variant="tonal" size="small" prepend-icon="mdi-eye-check" color="white" class="mr-2"
          @click="bulkToggleActive(true)">Активировать</v-btn>
        <v-btn variant="tonal" size="small" prepend-icon="mdi-eye-off" color="white" class="mr-2"
          @click="bulkToggleActive(false)">Деактивировать</v-btn>
        <v-btn variant="flat" size="small" prepend-icon="mdi-delete" color="error"
          @click="bulkDeleteDialog = true">Удалить выбранные</v-btn>
        <v-btn v-if="isSuperadmin" variant="flat" size="small" prepend-icon="mdi-delete-sweep" color="error" class="ml-2"
          @click="deleteAllDialog = true">Удалить ВСЕ</v-btn>
      </v-toolbar>

      <v-data-table
        v-resizable-columns="'products'"
        v-model="selectedIds"
        show-select
        item-value="id"
        :headers="headers"
        :items="filteredProducts"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        items-per-page="25"
        class="products-clickable"
        @click:row="onProductRowClick"
        :items-per-page-options="[25, 50, 100, -1]"
      >
        <!-- Photo -->
        <template #item.photo="{ item }">
          <v-avatar size="40" rounded="sm" class="my-1" style="overflow:hidden">
            <img v-if="item.photo_url || item.photo_link" :src="item.photo_url || item.photo_link" style="width:40px;height:40px;object-fit:cover;display:block" />
            <v-icon v-else icon="mdi-package-variant" color="grey" />
          </v-avatar>
        </template>

        <!-- Name + description -->
        <template #item.name="{ item }">
          <div class="font-weight-medium">{{ item.name }}</div>
          <div v-if="item.description" class="text-caption text-medium-emphasis" style="max-width:280px;white-space:normal;line-height:1.3">
            {{ item.description.slice(0, 100) }}{{ item.description.length > 100 ? '…' : '' }}
          </div>
          <v-chip v-if="item.description_44fz" size="x-small" variant="tonal" color="blue" class="mt-1">44-ФЗ</v-chip>
        </template>

        <!-- Type chip -->
        <template #item.product_type="{ item }">
          <v-chip v-if="item.product_type" size="x-small" variant="tonal" :color="typeColor(item.product_type)">
            {{ item.product_type }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Price -->
        <template #item.price="{ item }">
          <div v-if="item.price" class="font-weight-medium text-blue-darken-2">
            {{ Number(item.price).toLocaleString('ru-RU') }} ₽
          </div>
          <div v-if="item.price_links?.length" class="text-caption text-medium-emphasis">
            {{ item.price_links.length }} ист.
          </div>
          <span v-if="!item.price" class="text-medium-emphasis">—</span>
        </template>

        <!-- Contract Price -->
        <template #item.contract_price="{ item }">
          <template v-if="item.contract_price">
            <div class="font-weight-medium text-green-darken-2">
              {{ Number(item.contract_price).toLocaleString('ru-RU') }} ₽
            </div>
            <div v-if="item.contract_number" class="text-caption text-medium-emphasis">
              № {{ item.contract_number }}
              <span v-if="item.contract_date"> от {{ item.contract_date }}</span>
            </div>
            <v-tooltip :text="item.price_shared ? 'Цена видна другим организациям' : 'Цена скрыта от других организаций'" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" :icon="item.price_shared ? 'mdi-eye' : 'mdi-eye-off'" variant="text"
                  size="x-small" :color="item.price_shared ? 'success' : 'grey'"
                  @click="toggleSharing(item)" />
              </template>
            </v-tooltip>
          </template>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Country origin -->
        <template #item.country_origin="{ item }">
          <v-chip v-if="item.country_origin" size="x-small" variant="tonal"
            :color="item.country_origin === 'Россия' ? 'primary' : 'orange'">
            {{ item.country_origin }}
          </v-chip>
          <v-chip v-else size="x-small" variant="tonal" color="error">не указана</v-chip>
        </template>

        <!-- Active -->
        <template #item.is_active="{ item }">
          <v-chip size="x-small" :color="item.is_active ? 'success' : 'grey'" variant="tonal">
            {{ item.is_active ? 'Активен' : 'Неактивен' }}
          </v-chip>
        </template>

        <!-- TZ verified -->
        <template #item.tz_verified_at="{ item }">
          <v-tooltip
            :text="item.tz_verified_at
              ? `${new Date(item.tz_verified_at).toLocaleDateString('ru-RU')} · ${item.tz_verified_by}`
              : 'Нажмите чтобы подтвердить'"
            location="top"
          >
            <template #activator="{ props }">
              <v-progress-circular v-if="tzVerifying === item.id + '_standard'" indeterminate size="18" width="2" color="primary" />
              <v-icon
                v-else
                v-bind="props"
                :icon="item.tz_verified_at ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline'"
                :color="item.tz_verified_at ? 'success' : 'grey-lighten-1'"
                style="cursor: pointer"
                @click="!item.tz_verified_at && verifyTz(item, 'standard')"
              />
            </template>
          </v-tooltip>
        </template>

        <!-- TZ 44fz verified -->
        <template #item.tz_44fz_verified_at="{ item }">
          <v-tooltip
            :text="item.tz_44fz_verified_at
              ? `${new Date(item.tz_44fz_verified_at).toLocaleDateString('ru-RU')} · ${item.tz_44fz_verified_by}`
              : 'Нажмите чтобы подтвердить (44-ФЗ)'"
            location="top"
          >
            <template #activator="{ props }">
              <v-progress-circular v-if="tzVerifying === item.id + '_44fz'" indeterminate size="18" width="2" color="blue" />
              <v-icon
                v-else
                v-bind="props"
                :icon="item.tz_44fz_verified_at ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline'"
                :color="item.tz_44fz_verified_at ? 'blue-darken-2' : 'grey-lighten-1'"
                style="cursor: pointer"
                @click="!item.tz_44fz_verified_at && verifyTz(item, '44fz')"
              />
            </template>
          </v-tooltip>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <div class="d-flex gap-1" @click.stop>
            <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
              @click.stop="confirmDelete(item)" />
          </div>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-package-variant-closed" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Товары не найдены</div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Add / Edit dialog -->
    <v-dialog v-model="dialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">
          {{ editingId ? 'Редактировать товар' : 'Добавить товар' }}
        </v-card-title>
        <v-card-text class="px-6">
          <v-row dense>
            <!-- Наименование -->
            <v-col cols="12">
              <v-combobox
                v-model="form.name"
                v-model:search="nameSearch"
                :items="nameSuggestions"
                no-filter
                label="Наименование *"
                variant="outlined" density="compact"
                :rules="[v => !!v || 'Обязательное поле']"
                :hint="isDuplicateName ? '⚠ Товар с таким названием уже есть в каталоге' : ''"
                :persistent-hint="isDuplicateName"
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

            <!-- Тип — свободный текст с подсказками -->
            <v-col cols="12" md="6">
              <v-combobox v-model="form.product_type"
                :items="typeOptions"
                label="Тип товара"
                variant="outlined" density="compact" clearable
                hint="Напр.: Ноутбук, Тренажёр, Ткань" persistent-hint />
            </v-col>

            <!-- Категория — свободный текст с подсказками -->
            <v-col cols="12" md="6">
              <v-combobox v-model="form.category"
                :items="categoryOptions"
                label="Категория" variant="outlined" density="compact" clearable
                hint="Выберите или введите новую" persistent-hint />
            </v-col>

            <!-- Страна производства -->
            <v-col cols="12" md="6">
              <v-text-field v-model="form.country_origin"
                label="Страна производства *"
                variant="outlined" density="compact"
                hint="Обязательно для Приложения №3 (колонка P)"
                persistent-hint
                :rules="[v => !!v?.trim() || 'Укажите страну производства']"
              />
            </v-col>

            <!-- Цена (авто из ссылок или ручная) -->
            <v-col cols="12" md="6">
              <v-text-field v-model.number="form.price" label="Цена за ед., ₽" type="number"
                variant="outlined" density="compact"
                :readonly="avgPrice !== null"
                :hint="avgPrice !== null ? 'Среднее из ссылок — ' + avgPrice.toLocaleString('ru-RU') + ' ₽' : 'Можно задать вручную или через ссылки ниже'"
                persistent-hint />
            </v-col>

            <v-col cols="12" md="6">
              <v-switch v-model="form.is_active" label="Активен" color="success" density="compact" hide-details class="mt-1" />
            </v-col>

            <v-col cols="12">
              <v-textarea v-model="form.description" label="Точное описание"
                hint="Конкретные характеристики товара"
                variant="outlined" density="compact" rows="3" auto-grow persistent-hint />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="form.description_44fz" label="Описание для 44-ФЗ"
                hint="Допустимые интервалы характеристик для публикации закупки"
                variant="outlined" density="compact" rows="3" auto-grow persistent-hint />
            </v-col>

            <!-- Фото -->
            <v-col cols="12">
              <div class="text-subtitle-2 mb-2">Фото товара</div>
              <div v-if="photoPreview || form.photo_url || form.photo_link" class="mb-3">
                <img
                  :src="photoPreview || form.photo_url || form.photo_link"
                  style="max-width:100%;max-height:180px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5"
                />
                <v-btn
                  v-if="form.photo_url?.startsWith('/api/products/photos/')"
                  size="x-small" variant="text" color="error" class="mt-1"
                  @click="form.photo_url = ''"
                >Удалить загруженное фото</v-btn>
              </div>
              <v-file-input
                v-model="photoFileList"
                label="Загрузить фото с компьютера"
                accept="image/jpeg,image/jpg,image/png,image/webp,image/gif"
                variant="outlined" density="compact"
                prepend-icon="mdi-camera" show-size clearable
                @update:model-value="onPhotoFileChange"
              />
              <div class="d-flex gap-2 align-center mt-2">
                <v-text-field v-model="form.photo_url"
                  label="Или внешняя ссылка на фото"
                  variant="outlined" density="compact"
                  prepend-inner-icon="mdi-image-outline"
                  hide-details
                  :disabled="!!photoFile"
                  class="flex-grow-1"
                />
                <v-btn
                  v-if="editingId && form.photo_url && (form.photo_url.startsWith('http://') || form.photo_url.startsWith('https://'))"
                  variant="tonal" color="teal" size="small" :loading="downloadingPhoto"
                  prepend-icon="mdi-image-sync"
                  @click="downloadSinglePhoto"
                >Скачать</v-btn>
              </div>
              <v-text-field v-model="form.photo_link" label="Запасная ссылка" variant="outlined"
                density="compact" prepend-inner-icon="mdi-link" class="mt-2" />
            </v-col>

            <!-- Ссылки для сравнения цен -->
            <v-col cols="12">
              <div class="text-subtitle-2 mb-2">
                Ссылки для сравнения цен
                <span v-if="avgPrice !== null" class="text-caption font-weight-bold text-blue-darken-2 ml-2">
                  ср. {{ avgPrice.toLocaleString('ru-RU') }} ₽
                </span>
              </div>
              <div v-for="(link, i) in form.priceLinks" :key="i" class="d-flex gap-2 mb-2 align-center">
                <v-text-field
                  v-model="link.url"
                  :label="'Ссылка ' + (i + 1)"
                  variant="outlined" density="compact" hide-details
                  prepend-inner-icon="mdi-link"
                  class="flex-grow-1"
                />
                <v-text-field
                  v-model.number="link.price"
                  label="Цена, ₽"
                  type="number" variant="outlined" density="compact" hide-details
                  style="max-width: 140px"
                />
                <div class="d-flex flex-column gap-1">
                  <v-btn
                    v-if="link.url"
                    icon="mdi-open-in-new" variant="text" size="x-small"
                    color="primary"
                    :href="link.url" target="_blank"
                  />
                  <v-btn
                    icon="mdi-minus-circle" variant="text" size="x-small"
                    color="error"
                    @click="removePriceLink(i)"
                  />
                </div>
              </div>
              <v-btn prepend-icon="mdi-plus" variant="tonal" size="small" color="primary" @click="addPriceLink">
                Добавить ссылку
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">
            {{ editingId ? 'Сохранить' : 'Добавить' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Удалить товар?</v-card-title>
        <v-card-text class="px-6">
          <strong>{{ deleteTarget?.name }}</strong> будет удалён из каталога.
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Bulk delete confirm -->
    <v-dialog v-model="bulkDeleteDialog" max-width="420">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Удалить товары?</v-card-title>
        <v-card-text class="px-6">
          Будет удалено <strong>{{ selectedIds.length }}</strong> товаров из каталога.
          Позиции в закупках, где эти товары были выбраны, сохранятся, но ссылка на карточку товара будет очищена.
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="bulkDeleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="bulkDeleting" @click="doBulkDelete">Удалить {{ selectedIds.length }} товаров</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete ALL confirm (superadmin only) -->
    <v-dialog v-model="deleteAllDialog" max-width="480">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 text-error">Удалить ВСЕ товары?</v-card-title>
        <v-card-text class="px-6">
          Будут удалены <strong>все {{ products.length }}</strong> товаров из каталога.
          Это действие необратимо. Для подтверждения введите слово <strong>УДАЛИТЬ</strong>.
        </v-card-text>
        <v-text-field v-model="deleteAllConfirm" label="Введите УДАЛИТЬ" variant="outlined" density="compact" class="mx-6" hide-details />
        <v-card-actions class="px-6 pb-4 pt-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteAllDialog = false; deleteAllConfirm = ''">Отмена</v-btn>
          <v-btn color="error" :loading="deletingAll" :disabled="deleteAllConfirm !== 'УДАЛИТЬ'" @click="doDeleteAll">Удалить все</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import dialog -->
    <v-dialog v-model="importDialog.show" max-width="540" persistent>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Импорт товаров из Excel</v-card-title>
        <v-card-text class="px-6">
          <!-- Step 1: upload -->
          <template v-if="importDialog.step === 1">
            <p class="text-body-2 text-medium-emphasis mb-4">
              Загрузите файл .xlsx. Обязательная колонка:<br>
              <strong>Наименование</strong> (или «Название», «Товар»).<br>
              Необязательные: Описание, Категория, Вид, Цена (или «Стоимость»),
              Ссылка 1…3, Цена ссылки 1…3,
              Фото (URL), Многоразовое, Активен, Категория ФЭО.
            </p>
            <v-file-input
              v-model="importDialog.fileList"
              label="Файл Excel (.xlsx)"
              accept=".xlsx,.xls"
              variant="outlined" density="compact"
              prepend-icon="mdi-file-excel"
              show-size
              @update:model-value="importDialog.file = Array.isArray($event) ? ($event[0] ?? null) : ($event ?? null)"
            />
          </template>

          <!-- Step 2: results -->
          <template v-else>
            <v-alert v-if="importDialog.result && !importDialog.result.headers_found?.name" type="error" variant="tonal" class="mb-3">
              Колонка <strong>«Наименование»</strong> не найдена в файле!<br>
              Все строки пропущены. Проверьте заголовки в первой строке Excel.
              <div v-if="importDialog.result.headers_raw?.length" class="mt-2 text-caption">
                Найденные заголовки: <strong>{{ importDialog.result.headers_raw.filter((h: any) => h).join(', ') }}</strong>
              </div>
            </v-alert>
            <v-alert v-else-if="importDialog.result" :type="importDialog.result.created > 0 ? 'success' : 'warning'" variant="tonal" class="mb-3">
              Создано: <strong>{{ importDialog.result.created }}</strong> &nbsp;
              Пропущено: <strong>{{ importDialog.result.skipped }}</strong>
            </v-alert>
            <div v-if="importDialog.result?.headers_found && Object.keys(importDialog.result.headers_found).length" class="mb-3">
              <div class="text-caption text-medium-emphasis">Распознанные колонки:
                <span v-for="(header, field) in importDialog.result.headers_found" :key="field" class="mr-2">
                  <v-chip size="x-small" color="primary" variant="tonal">{{ header }}</v-chip>
                </span>
              </div>
            </div>
            <div v-if="importDialog.result?.errors?.length" class="mt-2">
              <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ importDialog.result.errors.length }}):</div>
              <v-list density="compact" class="bg-error-lighten-5 rounded">
                <v-list-item v-for="e in importDialog.result.errors" :key="e.row"
                  :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
              </v-list>
            </div>
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="closeImportDialog">{{ importDialog.step === 2 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="importDialog.step === 1" color="primary" :loading="importDialog.loading"
            :disabled="!importDialog.file" @click="doImport">Загрузить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Download photos dialog -->
    <v-dialog v-model="dlPhotoDialog.show" max-width="480" persistent>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">
          <v-icon icon="mdi-image-sync" class="mr-2" />Скачать фото по ссылкам
        </v-card-title>
        <v-card-text class="px-6">
          <template v-if="!dlPhotoDialog.result">
            <p class="text-body-2 text-medium-emphasis">
              Для всех товаров, у которых есть ссылка на фото (но нет локальной копии),
              будет скачана фотография и сохранена в базе данных.
            </p>
            <v-alert v-if="dlPhotoDialog.loading" type="info" variant="tonal" class="mt-3">
              <v-progress-circular indeterminate size="16" width="2" class="mr-2" />
              Скачивание... может занять несколько минут
            </v-alert>
          </template>
          <template v-else>
            <v-alert type="success" variant="tonal" class="mb-3">
              Обновлено: <strong>{{ dlPhotoDialog.result.updated }}</strong> &nbsp;
              Пропущено: <strong>{{ dlPhotoDialog.result.skipped }}</strong>
            </v-alert>
            <div v-if="dlPhotoDialog.result.errors?.length" class="mt-2">
              <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ dlPhotoDialog.result.errors.length }}):</div>
              <v-list density="compact" class="rounded" style="max-height:160px;overflow-y:auto">
                <v-list-item v-for="e in dlPhotoDialog.result.errors" :key="e.id"
                  :subtitle="`#${e.id} ${e.name}: ${e.error}`" />
              </v-list>
            </div>
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dlPhotoDialog.show = false; dlPhotoDialog.result = null">Закрыть</v-btn>
          <v-btn v-if="!dlPhotoDialog.result" color="teal" :loading="dlPhotoDialog.loading"
            prepend-icon="mdi-download" @click="doDownloadAllPhotos">Скачать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Column configurator dialog -->
    <v-dialog v-model="colConfigDialog" max-width="360" scrollable>
      <v-card>
        <v-card-title class="text-h6 pt-4 px-5 d-flex align-center justify-space-between">
          Порядок столбцов
          <v-btn variant="text" size="small" prepend-icon="mdi-restore" @click="resetColOrder">Сбросить</v-btn>
        </v-card-title>
        <v-card-subtitle class="px-5 pb-2 text-caption text-medium-emphasis">
          Перетащите строки, чтобы изменить порядок
        </v-card-subtitle>
        <v-card-text class="px-3 py-0">
          <v-list density="compact">
            <v-list-item
              v-for="(key, idx) in colOrder"
              :key="key"
              :draggable="true"
              @dragstart="onDragStart(idx)"
              @dragover="onDragOver($event, idx)"
              @dragend="onDragEnd"
              :style="dragSrcIdx === idx ? 'opacity:0.4' : ''"
              class="col-drag-item px-2"
              rounded="sm"
            >
              <template #prepend>
                <v-icon icon="mdi-drag-vertical" color="grey" size="20" class="mr-1" style="cursor:grab" />
              </template>
              <v-list-item-title class="text-body-2">
                {{ ALL_COLUMNS.find(c => c.key === key)?.title || key }}
              </v-list-item-title>
              <template #append>
                <v-btn icon="mdi-chevron-up" variant="text" size="x-small" :disabled="idx === 0" @click="moveCol(idx, -1)" />
                <v-btn icon="mdi-chevron-down" variant="text" size="x-small" :disabled="idx === colOrder.length - 1" @click="moveCol(idx, 1)" />
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-spacer />
          <v-btn color="primary" @click="colConfigDialog = false">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { apiFetch } from '@/api'

interface PriceLink { url: string; price: number | null }
interface Product {
  id: number; name: string; category?: string; product_type?: string
  price?: number; description?: string; description_44fz?: string; photo_url?: string
  photo_link?: string; clarification_link?: string
  is_active: boolean; is_reusable?: boolean; feo_category_id?: number
  price_links?: PriceLink[]
  contract_price?: number; contract_number?: string; contract_date?: string; contract_org_id?: number; price_shared?: boolean
  tz_verified_at?: string; tz_verified_by?: string
  tz_44fz_verified_at?: string; tz_44fz_verified_by?: string
}

const userRole = localStorage.getItem('user_role') || ''
const isSuperadmin = userRole === 'superadmin'

const products = ref<Product[]>([])
const loading  = ref(false)
const saving   = ref(false)
const deleting = ref(false)
const bulkDeleting = ref(false)
const deletingAll = ref(false)
const dialog      = ref(false)
const deleteDialog = ref(false)
const bulkDeleteDialog = ref(false)
const deleteAllDialog = ref(false)
const deleteAllConfirm = ref('')
const deleteTarget = ref<Product | null>(null)
const editingId    = ref<number | null>(null)
const selectedIds  = ref<number[]>([])
const search         = ref('')
const filterType     = ref<string | null>(null)
const filterCategory = ref<string | null>(null)
const filterActive   = ref<boolean | null>(null)
const filterPriceMin = ref<number | null>(null)
const filterPriceMax = ref<number | null>(null)

// Photo upload state
const photoFile     = ref<File | null>(null)
const photoFileList = ref<File[]>([])
const photoPreview  = ref<string | null>(null)

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const deduplicating = ref(false)
async function deduplicateProducts() {
  if (!confirm('Удалить дублирующиеся товары? (совпадение по Наименованию + ТЗ)')) return
  deduplicating.value = true
  try {
    const result = await apiFetch<{ deleted: number; kept: number }>('/products/deduplicate', { method: 'POST' })
    showSnack(`Удалено дублей: ${result.deleted}, оставлено: ${result.kept}`)
    if (result.deleted > 0) await load()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка дедупликации', 'error')
  } finally {
    deduplicating.value = false
  }
}

const tzVerifying = ref<string | null>(null)
async function verifyTz(item: Product, tzType: 'standard' | '44fz') {
  tzVerifying.value = `${item.id}_${tzType}`
  try {
    const updated = await apiFetch<Product>(`/products/${item.id}/verify-tz?tz_type=${tzType}`, { method: 'PATCH' })
    const idx = products.value.findIndex(p => p.id === item.id)
    if (idx !== -1) products.value[idx] = { ...products.value[idx], ...updated }
    showSnack('ТЗ подтверждено')
  } catch {
    showSnack('Ошибка подтверждения ТЗ', 'error')
  } finally {
    tzVerifying.value = null
  }
}

const emptyForm = () => ({
  name: '', category: '', product_type: '', price: null as number | null,
  description: '', description_44fz: '', photo_url: '', photo_link: '', clarification_link: '',
  is_active: true, is_reusable: true, feo_category_id: null as number | null,
  priceLinks: [] as PriceLink[],
  country_origin: 'Россия' as string,
})
const form = reactive(emptyForm())

// Name autocomplete + duplicate detection
const nameSearch = ref('')
const nameSuggestions = computed(() => {
  const q = (nameSearch.value || '').toLowerCase().trim()
  if (q.length < 2) return []
  return products.value
    .filter(p => p.name.toLowerCase().includes(q) && p.id !== editingId.value)
    .map(p => p.name)
    .slice(0, 15)
})
const isDuplicateName = computed(() => {
  if (!form.name) return false
  const q = (typeof form.name === 'string' ? form.name : '').toLowerCase().trim()
  if (!q) return false
  return products.value.some(p => p.name.toLowerCase().trim() === q && p.id !== editingId.value)
})

// Computed options from existing data
const typeOptions = computed(() => {
  const types = products.value.map(p => p.product_type).filter(Boolean) as string[]
  return [...new Set(types)].sort()
})

const categoryOptions = computed(() => {
  const cats = products.value.map(p => p.category).filter(Boolean) as string[]
  return [...new Set(cats)].sort()
})

// Auto-calculate average price from links
const avgPrice = computed<number | null>(() => {
  const prices = form.priceLinks
    .map(l => l.price)
    .filter((p): p is number => p !== null && p !== undefined && !isNaN(Number(p)) && Number(p) > 0)
  if (prices.length === 0) return null
  return Math.round(prices.reduce((s, p) => s + p, 0) / prices.length * 100) / 100
})

watch(avgPrice, (v) => { if (v !== null) form.price = v })

// All available columns — порядок по умолчанию
const ALL_COLUMNS = [
  { title: '',          key: 'photo',              width: 56,  sortable: false, fixed: true },
  { title: 'Наименование', key: 'name',            minWidth: 240, fixed: true },
  { title: 'Тип',       key: 'product_type',       width: 140 },
  { title: 'Категория', key: 'category',           minWidth: 140 },
  { title: 'Цена',      key: 'price',              width: 130, align: 'end' as const },
  { title: 'Цена по договору', key: 'contract_price', width: 180, align: 'end' as const },
  { title: 'Страна',    key: 'country_origin',     width: 120 },
  { title: 'Статус',    key: 'is_active',          width: 110 },
  { title: 'Действия',  key: 'actions',            width: 100, sortable: false },
  { title: 'ТЗ проверено',     key: 'tz_verified_at',      width: 160, sortable: false },
  { title: 'ТЗ 44-ФЗ',        key: 'tz_44fz_verified_at', width: 150, sortable: false },
]

function loadColOrder(): string[] {
  try {
    const saved = localStorage.getItem('products_col_order')
    if (saved) {
      const arr = JSON.parse(saved) as string[]
      const allKeys = ALL_COLUMNS.map(c => c.key)
      // merge: saved + any new columns not yet in saved
      const merged = arr.filter(k => allKeys.includes(k))
      allKeys.forEach(k => { if (!merged.includes(k)) merged.push(k) })
      return merged
    }
  } catch {}
  return ALL_COLUMNS.map(c => c.key)
}

const colOrder = ref<string[]>(loadColOrder())

const headers = computed(() => {
  const map = Object.fromEntries(ALL_COLUMNS.map(c => [c.key, c]))
  return colOrder.value.map(k => map[k]).filter(Boolean)
})

function saveColOrder() {
  localStorage.setItem('products_col_order', JSON.stringify(colOrder.value))
}

// Column configurator dialog
const colConfigDialog = ref(false)
const dragSrcIdx = ref<number | null>(null)

function onDragStart(idx: number) { dragSrcIdx.value = idx }
function onDragOver(e: DragEvent, idx: number) {
  e.preventDefault()
  if (dragSrcIdx.value === null || dragSrcIdx.value === idx) return
  const newOrder = [...colOrder.value]
  const [moved] = newOrder.splice(dragSrcIdx.value, 1)
  newOrder.splice(idx, 0, moved)
  colOrder.value = newOrder
  dragSrcIdx.value = idx
}
function onDragEnd() { dragSrcIdx.value = null; saveColOrder() }
function moveCol(idx: number, dir: -1 | 1) {
  const to = idx + dir
  if (to < 0 || to >= colOrder.value.length) return
  const newOrder = [...colOrder.value]
  ;[newOrder[idx], newOrder[to]] = [newOrder[to], newOrder[idx]]
  colOrder.value = newOrder
  saveColOrder()
}
function resetColOrder() {
  colOrder.value = ALL_COLUMNS.map(c => c.key)
  saveColOrder()
}

const filteredProducts = computed(() => {
  let r = products.value
  if (filterType.value)     r = r.filter(p => p.product_type === filterType.value)
  if (filterCategory.value) r = r.filter(p => p.category === filterCategory.value)
  if (filterActive.value !== null) r = r.filter(p => p.is_active === filterActive.value)
  if (filterPriceMin.value !== null) r = r.filter(p => p.price != null && Number(p.price) >= filterPriceMin.value!)
  if (filterPriceMax.value !== null) r = r.filter(p => p.price != null && Number(p.price) <= filterPriceMax.value!)
  return r
})

// Hash-based color for any free-text type
const PALETTE = ['blue', 'teal', 'orange', 'purple', 'pink', 'green', 'indigo', 'cyan', 'deep-orange']
function typeColor(t: string): string {
  const h = Math.abs([...t].reduce((acc, c) => acc * 31 + c.charCodeAt(0), 0))
  return PALETTE[h % PALETTE.length]
}

function onPhotoFileChange(val: File | File[] | null) {
  const f = Array.isArray(val) ? (val[0] ?? null) : val
  photoFile.value = f
  photoPreview.value = f ? URL.createObjectURL(f) : null
  if (f) form.photo_url = ''
}

function addPriceLink() {
  form.priceLinks.push({ url: '', price: null })
}
function removePriceLink(i: number) {
  form.priceLinks.splice(i, 1)
}

async function load() {
  loading.value = true
  try { products.value = await apiFetch<Product[]>('/products/') }
  catch { showSnack('Ошибка загрузки', 'error') }
  finally { loading.value = false }
}

function resetPhotoState() {
  photoFile.value = null
  photoFileList.value = []
  photoPreview.value = null
}

function openCreate() {
  Object.assign(form, emptyForm())
  resetPhotoState()
  editingId.value = null
  dialog.value = true
}

function onProductRowClick(_: any, { item }: { item: Product }) {
  openEdit(item)
}

function openEdit(p: Product) {
  Object.assign(form, {
    name: p.name, category: p.category || '', product_type: p.product_type || '',
    price: p.price ?? null, description: p.description || '', description_44fz: p.description_44fz || '',
    photo_url: p.photo_url || '', photo_link: p.photo_link || '',
    clarification_link: p.clarification_link || '',
    is_active: p.is_active, is_reusable: p.is_reusable ?? true,
    feo_category_id: p.feo_category_id ?? null,
    priceLinks: (p.price_links || []).map(l => ({ url: l.url, price: l.price ?? null })),
    country_origin: p.country_origin || 'Россия',
  })
  resetPhotoState()
  editingId.value = p.id
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) { showSnack('Укажите наименование', 'error'); return }
  if (!form.country_origin?.trim()) { showSnack('Укажите страну производства', 'error'); return }
  saving.value = true
  try {
    const payload = {
      ...form,
      price: form.price || null,
      price_links: form.priceLinks.filter(l => l.url.trim()).map(l => ({ url: l.url, price: l.price ?? null })),
    }
    let savedId: number
    if (editingId.value) {
      await apiFetch(`/products/${editingId.value}`, { method: 'PUT', body: payload })
      savedId = editingId.value
      showSnack('Товар обновлён')
    } else {
      const created = await apiFetch<Product>('/products/', { method: 'POST', body: payload })
      savedId = created.id
      showSnack('Товар добавлен')
    }

    if (photoFile.value) {
      const fd = new FormData()
      fd.append('file', photoFile.value)
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/products/${savedId}/photo`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) showSnack('Товар сохранён, но фото не загрузилось', 'warning')
    }

    dialog.value = false
    resetPhotoState()
    await load()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

async function toggleSharing(p: any) {
  try {
    const res = await apiFetch<any>(`/products/${p.id}/share-price`, {
      method: 'PATCH',
      body: JSON.stringify({ shared: !p.price_shared }),
    })
    p.price_shared = res.price_shared
    showSnack(p.price_shared ? 'Цена доступна другим организациям' : 'Цена скрыта')
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка', 'error')
  }
}

function confirmDelete(p: Product) {
  deleteTarget.value = p
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await apiFetch(`/products/${deleteTarget.value.id}`, { method: 'DELETE' })
    showSnack('Товар удалён')
    deleteDialog.value = false
    selectedIds.value = selectedIds.value.filter(id => id !== deleteTarget.value!.id)
    await load()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleting.value = false
  }
}

async function doBulkDelete() {
  bulkDeleting.value = true
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map(id => apiFetch(`/products/${id}`, { method: 'DELETE' })))
    showSnack(`Удалено ${ids.length} товаров`)
    bulkDeleteDialog.value = false
    selectedIds.value = []
    await load()
  } catch {
    showSnack('Ошибка при удалении', 'error')
  } finally {
    bulkDeleting.value = false
  }
}

async function doDeleteAll() {
  deletingAll.value = true
  try {
    const res = await apiFetch<{message: string}>('/products/bulk/all', { method: 'DELETE' })
    showSnack(res.message || 'Все товары удалены')
    deleteAllDialog.value = false
    deleteAllConfirm.value = ''
    selectedIds.value = []
    await load()
  } catch {
    showSnack('Ошибка при удалении', 'error')
  } finally {
    deletingAll.value = false
  }
}

async function bulkToggleActive(active: boolean) {
  const ids = [...selectedIds.value]
  try {
    await Promise.all(ids.map(id => {
      const p = products.value.find(p => p.id === id)
      if (!p) return Promise.resolve()
      return apiFetch(`/products/${id}`, {
        method: 'PUT',
        body: { name: p.name, is_active: active, price_links: p.price_links || [] },
      })
    }))
    showSnack(`${active ? 'Активировано' : 'Деактивировано'} ${ids.length} товаров`)
    selectedIds.value = []
    await load()
  } catch {
    showSnack('Ошибка обновления', 'error')
  }
}

// Download photos
const downloadingPhoto = ref(false)
const dlPhotoDialog = reactive({
  show: false,
  loading: false,
  result: null as { updated: number; skipped: number; errors: { id: number; name: string; error: string }[] } | null,
})

function openDownloadPhotosDialog() {
  dlPhotoDialog.result = null
  dlPhotoDialog.show = true
}

async function doDownloadAllPhotos() {
  dlPhotoDialog.loading = true
  try {
    dlPhotoDialog.result = await apiFetch<typeof dlPhotoDialog.result>('/products/download-photos', { method: 'POST' })
    if (dlPhotoDialog.result?.updated) await load()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка скачивания фото', 'error')
  } finally {
    dlPhotoDialog.loading = false
  }
}

async function downloadSinglePhoto() {
  if (!editingId.value) return
  downloadingPhoto.value = true
  try {
    const updated = await apiFetch<{ photo_url: string }>(`/products/${editingId.value}/download-photo`, { method: 'POST' })
    form.photo_url = updated.photo_url
    showSnack('Фото скачано и сохранено')
    await load()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка скачивания фото', 'error')
  } finally {
    downloadingPhoto.value = false
  }
}

// Import
const importDialog = reactive({
  show: false, step: 1, file: null as File | null, fileList: [] as File[],
  loading: false, result: null as { created: number; skipped: number; errors: { row: number; name: string; message: string }[] } | null,
})

function closeImportDialog() {
  importDialog.show = false
  importDialog.step = 1
  importDialog.file = null
  importDialog.fileList = []
  importDialog.result = null
  if (importDialog.result?.created) load()
}

async function downloadTemplate() {
  const token = localStorage.getItem('auth_token')
  const res = await fetch('/api/products/import/template', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'products_template.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function doImport() {
  if (!importDialog.file) return
  importDialog.loading = true
  try {
    const fd = new FormData()
    fd.append('file', importDialog.file)
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/products/import', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      showSnack(err.detail || 'Ошибка импорта', 'error')
      return
    }
    importDialog.result = await res.json()
    importDialog.step = 2
    showSnack(`Импорт завершён: создано ${importDialog.result!.created}`)
    await load()
  } catch {
    showSnack('Ошибка импорта', 'error')
  } finally {
    importDialog.loading = false
  }
}

onMounted(load)
</script>

<style scoped>
.products-clickable :deep(tbody tr) { cursor: pointer; }
.col-drag-item { cursor: default; user-select: none; }
.col-drag-item:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
</style>
