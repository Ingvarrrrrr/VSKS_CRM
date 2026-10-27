<template>
  <v-dialog v-model="dialog" max-width="700" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        {{ editingId ? 'Редактировать товар' : 'Добавить товар' }}
        <!-- Массовое «Добавить в каталог» (владелец, 14.10) — окно открывается
             по очереди на каждую позицию без товара, подпись показывает где
             мы в очереди (useBulkProductCreateQueue.ts). -->
        <div v-if="queueLabel" class="text-caption text-medium-emphasis mt-1">{{ queueLabel }}</div>
        <div v-if="editingId && editMeta.updated_by" class="text-caption text-medium-emphasis mt-1">
          Изменено: {{ editMeta.updated_by }} — {{ formatDate(editMeta.updated_at) }}
        </div>
        <div v-if="editingId && editMeta.import_note" class="text-caption text-medium-emphasis mt-1">
          {{ editMeta.import_note }}
        </div>
      </v-card-title>
      <v-card-text class="px-6">
        <!-- Защита каталога (план clever-bouncing-lantern.md, Часть 1,
             владелец 14.10.2026): без права products.edit_catalog у
             СУЩЕСТВУЮЩЕГО товара редактируемы только поля, которые были
             ПУСТЫ на момент открытия карточки (описание/описание 44-ФЗ/
             фото/цена, props.emptyAtOpen из useProductsForm.ts::openEdit) —
             заполнить их можно, заменить уже заполненные или поменять любое
             другое поле — нет, PUT/PATCH всё равно вернёт 403 тем же
             текстом (backend/app/services/product_catalog_guard.py::
             CATALOG_EDIT_DENIED_MESSAGE). Создание нового товара (editingId
             нет) этим не ограничено ни на бэкенде, ни здесь. -->
        <v-alert v-if="readonlyCatalog" type="info" variant="tonal" density="comfortable" class="mb-4">
          Без права «Редактировать каталог товаров» можно заполнить пустые поля (описание, фото, цену).
          Изменить заполненное — через «Предложить правку».
        </v-alert>
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
              :disabled="readonlyCatalog"
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

          <!-- Товар / Услуга / Работа — ITEM_TYPE_OPTIONS, единственный источник
               (Правило №6, владелец 21.09, раздел W2 плана corrections-21-09.md). -->
          <v-col cols="12" md="3">
            <v-select v-model="form.item_kind"
              :items="ITEM_TYPE_OPTIONS" :disabled="readonlyCatalog"
              label="Товар / Услуга / Работа" variant="outlined" density="compact" />
          </v-col>

          <!-- Тип — свободный текст с подсказками -->
          <v-col cols="12" md="4">
            <v-combobox v-model="form.product_type"
              :items="typeOptions" :disabled="readonlyCatalog"
              label="Тип товара"
              variant="outlined" density="compact" clearable
              hint="Напр.: Ноутбук, Тренажёр, Ткань" persistent-hint />
          </v-col>

          <!-- Категория — свободный текст с подсказками -->
          <v-col cols="12" md="5">
            <v-combobox v-model="form.category"
              :items="categoryOptions" :disabled="readonlyCatalog"
              label="Категория" variant="outlined" density="compact" clearable
              hint="Выберите или введите новую" persistent-hint />
          </v-col>

          <!-- Категории закупки — справочник, решение владельца 2026-09-16, п.1:
               отдельный мультивыбор от свободнотекстовой «Категории» выше — по
               этим категориям товар выставляется в закупку. -->
          <v-col cols="12">
            <PurchaseCategoriesPicker v-model="form.purchase_category_ids" :mobile="mobile" />
            <div class="text-caption text-medium-emphasis mt-1">По этим категориям товар выставляется в закупку.</div>
          </v-col>

          <!-- Единица измерения (владелец, 2026-09-01; комбобокс со
               справочником — 14.10) -->
          <v-col cols="12" md="3">
            <v-combobox v-model="form.unit"
              :items="UNIT_OPTIONS" :disabled="readonlyCatalog"
              label="Ед. изм." variant="outlined" density="compact" clearable
              hint="Выберите или введите свою" persistent-hint />
          </v-col>

          <!-- Упаковка (владелец, 14.10): «когда товар меряется упаковками,
               должно быть количество в упаковке» — показывается только при
               упаковочной unit (utils/units.ts::isPackUnit). -->
          <template v-if="isPackUnit(form.unit)">
            <v-col cols="6" md="3">
              <v-text-field v-model.number="form.pack_quantity" label="Кол-во в упаковке" type="number"
                variant="outlined" density="compact" min="0" :disabled="readonlyCatalog"
                hint="Сколько штук/единиц внутри одной упаковки" persistent-hint />
            </v-col>
            <v-col cols="6" md="3">
              <v-combobox v-model="form.pack_unit"
                :items="INNER_UNIT_OPTIONS" :disabled="readonlyCatalog"
                label="Единица внутри упаковки" variant="outlined" density="compact" />
            </v-col>
          </template>

          <!-- Страна производства -->
          <v-col cols="12" md="6">
            <v-text-field v-model="form.country_origin"
              label="Страна производства *"
              variant="outlined" density="compact" :disabled="readonlyCatalog"
              hint="Обязательно для Приложения №3 (колонка P)"
              persistent-hint
              :rules="[v => !!v?.trim() || 'Укажите страну производства']"
            />
          </v-col>

          <!-- Цена (авто из ссылок или ручная) -->
          <v-col cols="12" md="6">
            <v-text-field v-model.number="form.price" label="Цена за ед., ₽" type="number"
              variant="outlined" density="compact"
              :readonly="avgPrice !== null" :disabled="priceReadonly"
              :hint="avgPrice !== null ? 'Среднее из ссылок — ' + avgPrice.toLocaleString('ru-RU') + ' ₽' : 'Можно задать вручную или через ссылки ниже'"
              persistent-hint />
          </v-col>

          <!-- Владелец, сессия 2026-08-29: срок актуальности не константа —
               по умолчанию считается по категории (+ поправка на курс доллара),
               но можно переопределить персонально для этого товара. -->
          <v-col cols="12" md="6">
            <v-text-field v-model.number="form.price_ttl_days" label="Свой срок актуальности, дней" type="number"
              variant="outlined" density="compact" clearable :disabled="readonlyCatalog"
              hint="Пусто — берётся из настроек по категории" persistent-hint />
          </v-col>

          <v-col cols="12" md="6">
            <v-switch v-model="form.is_active" label="Активен" color="success" density="compact" hide-details class="mt-1" :disabled="readonlyCatalog" />
          </v-col>

          <v-col cols="12">
            <v-textarea v-model="form.description" label="Точное описание"
              hint="Конкретные характеристики товара"
              variant="outlined" density="compact" rows="3" auto-grow persistent-hint
              :readonly="descriptionReadonly" />
            <v-btn
              v-if="descriptionReadonly"
              size="small" variant="tonal" color="primary" class="mt-1"
              prepend-icon="mdi-pencil-outline"
              @click="proposeDialog.field = 'description'; proposeDialog.show = true"
            >
              Предложить правку описания
            </v-btn>
          </v-col>
          <v-col cols="12">
            <v-textarea v-model="form.description_44fz" label="Описание для 44-ФЗ"
              hint="Допустимые интервалы характеристик для публикации закупки"
              variant="outlined" density="compact" rows="3" auto-grow persistent-hint
              :readonly="description44Readonly" />
            <v-btn
              v-if="description44Readonly"
              size="small" variant="tonal" color="primary" class="mt-1"
              prepend-icon="mdi-pencil-outline"
              @click="proposeDialog.field = 'description_44fz'; proposeDialog.show = true"
            >
              Предложить правку описания для 44-ФЗ
            </v-btn>
            <!-- Сборка ТЗ 44-ФЗ из характеристик каталога (владелец,
                 26.10.2026) — только для существующего товара (нужен id для
                 preview) и только когда поле реально редактируемо; ничего
                 не сохраняет сама, кладёт текст в form.description_44fz —
                 реальное сохранение делает общая кнопка «Сохранить» тем же
                 PUT/PATCH, что и раньше (ПРАВИЛО №6, второй механизм записи
                 не заводим). -->
            <v-btn
              v-if="editingId && !description44Readonly"
              size="small" variant="tonal" color="secondary" class="mt-1 ml-2"
              prepend-icon="mdi-file-document-check-outline"
              :loading="generatingTz44"
              @click="onGenerateTz44Click"
            >
              Сформировать по характеристикам
            </v-btn>
            <div v-if="tz44NeedsReview" class="text-caption text-warning mt-1">
              Проверьте наименование — не удалось однозначно очистить от бренда/модели.
            </div>
            <!-- Подтверждение замены непустого поля — внутри диалога, не
                 confirm() (см. CLAUDE.md: системные confirm-диалоги в этом
                 проекте не используются). -->
            <v-alert v-if="tz44Pending" type="warning" variant="tonal" density="comfortable" class="mt-2">
              Поле «Описание для 44-ФЗ» не пустое. Заменить его сформированным текстом?
              <div class="d-flex gap-2 mt-2">
                <v-btn size="small" color="warning" variant="flat" @click="applyGeneratedTz44">Заменить</v-btn>
                <v-btn size="small" variant="text" @click="tz44Pending = null">Отмена</v-btn>
              </div>
            </v-alert>
            <!-- Владелец: «нажимаю "Сформировать по характеристикам", если их
                 нет — ничего не происходит, продолжаешь тыкать, не понимая»
                 (26.10.2026) — явное сообщение вместо молчания + скролл к
                 редактору характеристик ниже (characteristicsSectionRef). -->
            <v-alert
              v-if="tz44EmptyWarning"
              type="warning" variant="tonal" density="comfortable" class="mt-2" closable
              @click:close="tz44EmptyWarning = false"
            >
              Сформировать ТЗ 44-ФЗ нельзя: у товара нет характеристик и описания.
              Заполните характеристики ниже или вставьте описание с сайта товара.
            </v-alert>
            <v-alert
              v-if="tz44Error"
              type="error" variant="tonal" density="comfortable" class="mt-2" closable
              @click:close="tz44Error = null"
            >
              {{ tz44Error }}
            </v-alert>
          </v-col>

          <!-- Характеристики каталога (владелец, 26.10; редактирование —
               задача «ручное заполнение характеристик», 26.10.2026): поля
               наполняет либо загрузчик из прайсов поставщиков
               (app/services/catalog_gala/), либо сотрудник вручную здесь —
               тот же JSONB Product.characteristics, та же общая кнопка
               «Сохранить» (ПРАВИЛО №6, второй механизм записи не заводим). -->
          <v-col cols="12" ref="characteristicsSectionRef">
            <div v-if="form.manufacturer">Производитель: {{ form.manufacturer }}</div>
            <div v-if="form.article">Артикул производителя: {{ form.article }}</div>
            <!-- QA (26.10.2026, товар 50014): пока характеристики не
                 загрузились — явная ошибка, а не молчание (память проекта
                 feedback_no_generic_error_snackbar), редактор readonly
                 (characteristicsReadonly выше). -->
            <v-alert
              v-if="characteristicsLoadError"
              type="warning" variant="tonal" density="comfortable" class="mt-2"
            >
              {{ characteristicsLoadError }}
            </v-alert>
            <ProductCharacteristicsEditor
              class="mt-2"
              :model-value="form.characteristics"
              :readonly="characteristicsReadonly"
              :mobile="mobile"
              @update:model-value="onCharacteristicsUpdate"
              @description-generated="onCharacteristicsDescription"
              @error="onCharacteristicsError"
            />
          </v-col>

          <!-- Фото -->
          <v-col cols="12">
            <div class="text-subtitle-2 mb-2">Фото товара</div>
            <div v-if="photoPreview || (editingId && form.has_photo) || isLikelyImageUrl(form.photo_url) || isLikelyImageUrl(form.photo_link)" class="mb-3">
              <img
                :src="photoPreview || ((editingId && form.has_photo) ? `/api/products/${editingId}/photo?v=${photoCacheBuster}` : (isLikelyImageUrl(form.photo_url) ? form.photo_url : form.photo_link))"
                style="max-width:100%;max-height:180px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5"
              />
              <div class="d-flex gap-2 mt-1">
                <v-btn
                  v-if="editingId && form.has_photo"
                  size="x-small" variant="text" color="error"
                  :loading="deletingPhoto" :disabled="readonlyCatalog"
                  @click="$emit('clear-photo')"
                >Удалить загруженное фото</v-btn>
                <v-btn
                  v-if="form.photo_url?.startsWith('/api/products/photos/')"
                  size="x-small" variant="text" color="error"
                  @click="form.photo_url = ''"
                >Удалить устаревшую ссылку</v-btn>
              </div>
            </div>
            <v-file-input
              :model-value="photoFileList"
              label="Загрузить фото с компьютера"
              accept="image/jpeg,image/jpg,image/png,image/webp,image/gif"
              variant="outlined" density="compact"
              prepend-icon="mdi-camera" show-size clearable
              :disabled="photoReadonly"
              @update:model-value="$emit('photo-file-change', $event)"
            />
            <div class="d-flex gap-2 align-center mt-2">
              <v-text-field v-model="form.photo_url"
                label="Или внешняя ссылка на фото"
                variant="outlined" density="compact"
                prepend-inner-icon="mdi-image-outline"
                hide-details
                :disabled="!!photoFile || photoReadonly"
                class="flex-grow-1"
              />
              <v-btn
                v-if="editingId && form.photo_url && (form.photo_url.startsWith('http://') || form.photo_url.startsWith('https://'))"
                variant="tonal" color="teal" size="small" :loading="downloadingPhoto" :disabled="photoReadonly"
                prepend-icon="mdi-image-sync"
                @click="$emit('download-photo')"
              >Скачать</v-btn>
            </div>
            <v-text-field v-model="form.photo_link" label="Запасная ссылка" variant="outlined"
              density="compact" prepend-inner-icon="mdi-link" class="mt-2" />
          </v-col>

          <!-- Цены: история + средняя — решение владельца 2026-09-16, п.2/п.3,
               заменяет собой редактируемые «Ссылки для сравнения цен». -->
          <v-col cols="12">
            <PurchasePriceHistory
              ref="priceHistoryRef"
              :product-id="editingId"
              :legacy-price-links="form.priceLinks"
              v-model:pending-prices="form.pendingPrices"
              @product-refreshed="$emit('price-synced', $event)"
            />
          </v-col>
        </v-row>

        <!-- История описаний — только для уже существующего товара (у нового
             товара её по определению нет). -->
        <ProductDescriptionHistory
          v-if="editingId"
          :product-id="editingId"
          :can-edit-catalog="!readonlyCatalog"
          @reverted="onHistoryReverted"
        />
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-btn v-if="showSkip" variant="text" color="grey" @click="$emit('skip')">Пропустить</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn v-if="canSaveSomething" color="primary" :loading="saving" @click="onSaveClick">
          {{ editingId ? 'Сохранить' : 'Добавить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Предложить правку описания (readonlyCatalog) — своя карточка, не вторая
       отправка (ПРАВИЛО №6): переиспользует ProposeToCatalogDialog.vue, тот
       же, что и у позиций заявки/закупки (WishTzSection.vue/ItemsTableStages.vue). -->
  <ProposeToCatalogDialog
    v-if="editingId"
    v-model="proposeDialog.show"
    :product-id="editingId"
    :product-name="form.name"
    :field="proposeDialog.field"
    :catalog-value="proposeDialog.field === 'description' ? form.description : form.description_44fz"
    :own-value="proposeDialog.field === 'description' ? form.description : form.description_44fz"
    editable-own
  />

  <!-- Дубликат по имени (409 duplicate_product) при создании — один диалог на
       всех потребителей useProductsForm.ts (ПРАВИЛО №6), без window.confirm:
       раньше одно и то же решал window.confirm() в useItemsCatalog.ts и
       отдельно PlannedItemAddDialog.vue. -->
  <v-dialog :model-value="duplicateDialog" max-width="420" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1">Похожий товар уже есть в каталоге</v-card-title>
      <v-card-text>
        «{{ duplicateExisting?.name }}» — использовать его или всё равно создать новый?
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel-duplicate')">Отмена</v-btn>
        <v-btn variant="outlined" @click="$emit('confirm-create-new')">Создать новый</v-btn>
        <v-btn color="primary" @click="$emit('confirm-use-existing')">Использовать существующий</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { formatDate } from '@/composables/products/productsTypes'
import type { Product } from '@/composables/products/productsTypes'
import { isLikelyImageUrl } from '@/utils/productPhoto'
import { ITEM_TYPE_OPTIONS } from '@/utils/itemTypeKind'
import { UNIT_OPTIONS, INNER_UNIT_OPTIONS, isPackUnit } from '@/utils/units'
import PurchaseCategoriesPicker from '@/components/products/PurchaseCategoriesPicker.vue'
import PurchasePriceHistory from '@/components/products/PurchasePriceHistory.vue'
import ProductDescriptionHistory from '@/components/products/ProductDescriptionHistory.vue'
import ProposeToCatalogDialog from '@/components/products/ProposeToCatalogDialog.vue'
import ProductCharacteristicsEditor from '@/components/products/ProductCharacteristicsEditor.vue'

const props = defineProps<{
  mobile: boolean
  editingId: number | null
  // Этап В (владелец, 14.10.2026, п.1): права.edit_catalog — считает вызывающая
  // сторона (ProductsView.vue/ProductEditorDialog.vue) ОДНИМ механизмом
  // (authStore.hasAction(ACTIONS.PRODUCTS_EDIT_CATALOG), ПРАВИЛО №6), сюда
  // приходит готовым булевым значением. При создании нового товара
  // (editingId==null) ограничение не действует — см. readonlyCatalog ниже.
  canEditCatalog: boolean
  // Часть 1 плана clever-bouncing-lantern.md (владелец 14.10.2026): снэпшот
  // «поле было пусто в момент открытия» — считает useProductsForm.ts::openEdit
  // ОДИН раз (ПРАВИЛО №6), сюда приходит готовым. Без него нельзя отличить
  // «поле изначально пусто» от «пользователь только что стёр значение
  // локально» — это разные права.
  emptyAtOpen: { description: boolean; description_44fz: boolean; price: boolean; photo: boolean; characteristics: boolean }
  // QA (26.10.2026, товар 50014): характеристики грузятся отдельным запросом
  // ПОСЛЕ открытия карточки (useProductsForm.ts::_loadCharacteristics) — пока
  // characteristicsLoaded===false, редактор доступен, но save() у родителя
  // не отправляет ключ characteristics вовсе (защита от перезаписи null).
  // characteristicsLoadError — запрос упал: редактор становится readonly
  // (characteristicsReadonly ниже), текст ошибки показан отдельным alert.
  characteristicsLoaded: boolean
  characteristicsLoadError: string | null
  editMeta: { updated_at: string | null; updated_by: string | null; import_note: string | null }
  form: Record<string, any>
  nameSuggestions: string[]
  isDuplicateName: boolean
  typeOptions: string[]
  categoryOptions: string[]
  avgPrice: number | null
  photoPreview: string | null
  photoFile: File | null
  photoFileList: File[]
  photoCacheBuster: number
  downloadingPhoto: boolean
  deletingPhoto: boolean
  saving: boolean
  duplicateDialog?: boolean
  duplicateExisting?: { name: string } | null
  // Массовое «Добавить в каталог» (useBulkProductCreateQueue.ts) — подпись
  // «Позиция N из M» в заголовке и кнопка «Пропустить» в действиях.
  queueLabel?: string
  showSkip?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'clear-photo'): void
  (e: 'download-photo'): void
  (e: 'photo-file-change', value: File | File[] | null): void
  (e: 'confirm-use-existing'): void
  (e: 'confirm-create-new'): void
  (e: 'cancel-duplicate'): void
  (e: 'skip'): void
  // Пункт 8 (владелец, 14.10) — блок «Цены» поменял Product.price своим путём
  // (addEntry/removeEntry) — родитель (useProductsForm.ts) обязан подхватить
  // новое значение, иначе следующее «Сохранить» перетрёт его назад.
  (e: 'price-synced', p: { price: number | null }): void
  // QA (26.10.2026): характеристики менялись — родитель (useProductsForm.ts::
  // markCharacteristicsDirty) взводит флаг, который save() читает, чтобы
  // решить, слать ли ключ characteristics вообще (см. emptyAtOpen prop выше).
  (e: 'characteristics-dirty'): void
}>()

const dialog = defineModel<boolean>('modelValue', { required: true })
const nameSearch = defineModel<string>('nameSearch', { required: true })

// Этап В, п.1: правка СУЩЕСТВУЮЩЕГО товара без права — поля, не входящие в
// "заполнение пустого" (название/категория/единица/тип и т.д.), только
// чтение. Создание нового (editingId==null) не ограничено (см. докстринг
// prop выше).
const readonlyCatalog = computed(() => !!props.editingId && props.canEditCatalog === false)

// Часть 1 плана (14.10.2026): по полю — без галочки редактируемо, только
// если оно было ПУСТО на момент открытия (props.emptyAtOpen); с галочкой —
// как обычно, readonlyCatalog всегда false. Backend — та же проверка
// (product_catalog_guard.py::is_fill_empty_change, ПРАВИЛО №6), эти computed
// только управляют UI заранее, не подменяют проверку сервера.
const descriptionReadonly = computed(() => readonlyCatalog.value && !props.emptyAtOpen.description)
const description44Readonly = computed(() => readonlyCatalog.value && !props.emptyAtOpen.description_44fz)
const priceReadonly = computed(() => readonlyCatalog.value && !props.emptyAtOpen.price)
const photoReadonly = computed(() => readonlyCatalog.value && !props.emptyAtOpen.photo)
// QA (26.10.2026): запрос характеристик упал (characteristicsLoadError) —
// редактор readonly независимо от прав/эмптинесса, правка «вслепую» (без
// реальных текущих данных) рискует молча потерять их при следующем save().
const characteristicsReadonly = computed(() =>
  (readonlyCatalog.value && !props.emptyAtOpen.characteristics) || !!props.characteristicsLoadError)

function onCharacteristicsUpdate(value: any) {
  props.form.characteristics = value
  emit('characteristics-dirty')
}

// Кнопка «Сохранить» видна, если есть что сохранить: с галочкой — всегда;
// без галочки у существующего товара — только если хотя бы одно из
// заполняемых-пустых полей действительно пусто.
const canSaveSomething = computed(() => {
  if (!readonlyCatalog.value) return true
  const e = props.emptyAtOpen
  return e.description || e.description_44fz || e.price || e.photo || e.characteristics
})

const proposeDialog = ref<{ show: boolean; field: 'description' | 'description_44fz' }>({
  show: false,
  field: 'description',
})

// Пункт 1 (владелец, 14.10): переключили на упаковочную unit — подставить
// дефолт «шт.» для внутренней единицы, если она ещё не задана.
watch(() => props.form.unit, (u) => {
  if (isPackUnit(u) && !props.form.pack_unit) props.form.pack_unit = 'шт.'
})

// Пункт 8в: если в форме «Добавить цену» введена цена, но кнопка «Добавить
// цену» не нажата — досохранить её тем же addEntry() ПЕРЕД основным
// «Сохранить»/«Добавить», иначе введённое потеряется молча.
const priceHistoryRef = ref<InstanceType<typeof PurchasePriceHistory> | null>(null)
async function onSaveClick() {
  await priceHistoryRef.value?.commitPendingEntry?.()
  emit('save')
}

// Этап В, п.2: «Вернуть прежнее» применило старое значение описания на
// сервере — форма обязана перечитать товар оттуда (ПРАВИЛО №6, сервер —
// единственный источник), а не угадывать поле локально. props.form —
// тот же мутируемый reactive-объект, что и у всех v-model полей выше.
async function onHistoryReverted() {
  if (!props.editingId) return
  const fresh = await apiFetch<Product>(`/products/${props.editingId}`).catch(() => null)
  if (!fresh) return
  props.form.description = fresh.description || ''
  props.form.description_44fz = fresh.description_44fz || ''
}

// Сборка ТЗ 44-ФЗ из характеристик (владелец, 26.10.2026) — вызывает ТОЛЬКО
// preview-роутер (app/routers/products_tz44.py), ничего не сохраняет сама.
// Единственный генератор текста — backend/app/services/product_tz_44fz.py
// (ПРАВИЛО №6); фронт просто показывает результат и кладёт его в форму.
const generatingTz44 = ref(false)
const tz44NeedsReview = ref(false)
const tz44Pending = ref<string | null>(null)
// Владелец: «если характеристик нет — ничего не происходит, продолжаешь
// тыкать, не понимая» (26.10.2026) — явные состояния вместо молчаливого
// return на пустом результате, плюс явная ошибка сервера (catch), не глотаем
// (память проекта feedback_no_generic_error_snackbar).
const tz44EmptyWarning = ref(false)
const tz44Error = ref<string | null>(null)
const characteristicsSectionRef = ref<any>(null)

function scrollToCharacteristics() {
  const el = characteristicsSectionRef.value?.$el ?? characteristicsSectionRef.value
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

async function onGenerateTz44Click() {
  if (!props.editingId) return
  generatingTz44.value = true
  tz44NeedsReview.value = false
  tz44EmptyWarning.value = false
  tz44Error.value = null
  try {
    const result = await apiFetch<{ text: string | null; needs_review: boolean }>(
      `/products/${props.editingId}/tz-44fz/preview`,
      { method: 'POST' },
    )
    if (!result.text) {
      tz44EmptyWarning.value = true
      scrollToCharacteristics()
      return
    }
    tz44NeedsReview.value = result.needs_review
    if ((props.form.description_44fz || '').trim()) {
      // Поле не пустое — подтверждение внутри диалога (см. v-alert ниже),
      // не браузерный confirm().
      tz44Pending.value = result.text
    } else {
      props.form.description_44fz = result.text
    }
  } catch (e: any) {
    tz44Error.value = describeApiError(e, { fallback: 'Не удалось сформировать ТЗ 44-ФЗ', prefix: 'Ошибка' })
  } finally {
    generatingTz44.value = false
  }
}

function applyGeneratedTz44() {
  if (tz44Pending.value) {
    props.form.description_44fz = tz44Pending.value
  }
  tz44Pending.value = null
}

// Характеристики (владелец, задача «ручное заполнение характеристик»,
// 26.10.2026): ProductCharacteristicsEditor.vue сам зовёт preview-роутер
// /characteristics/describe — результат только кладём в форму/показываем
// ошибку, сохраняет общая кнопка «Сохранить» (ПРАВИЛО №6).
function onCharacteristicsDescription(text: string) {
  props.form.description = text
}
function onCharacteristicsError(message: string) {
  tz44Error.value = message
}
</script>
