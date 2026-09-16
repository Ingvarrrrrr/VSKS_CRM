<template>
  <v-dialog v-model="dialog" max-width="700" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        {{ editingId ? 'Редактировать товар' : 'Добавить товар' }}
        <div v-if="editingId && editMeta.updated_by" class="text-caption text-medium-emphasis mt-1">
          Изменено: {{ editMeta.updated_by }} — {{ formatDate(editMeta.updated_at) }}
        </div>
        <div v-if="editingId && editMeta.import_note" class="text-caption text-medium-emphasis mt-1">
          {{ editMeta.import_note }}
        </div>
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

          <!-- Товар / Услуга -->
          <v-col cols="12" md="3">
            <v-select v-model="form.item_kind"
              :items="[{ title: 'Товар', value: 'товар' }, { title: 'Услуга', value: 'услуга' }]"
              label="Товар / Услуга" variant="outlined" density="compact" />
          </v-col>

          <!-- Тип — свободный текст с подсказками -->
          <v-col cols="12" md="4">
            <v-combobox v-model="form.product_type"
              :items="typeOptions"
              label="Тип товара"
              variant="outlined" density="compact" clearable
              hint="Напр.: Ноутбук, Тренажёр, Ткань" persistent-hint />
          </v-col>

          <!-- Категория — свободный текст с подсказками -->
          <v-col cols="12" md="5">
            <v-combobox v-model="form.category"
              :items="categoryOptions"
              label="Категория" variant="outlined" density="compact" clearable
              hint="Выберите или введите новую" persistent-hint />
          </v-col>

          <!-- Категории закупки — справочник, решение владельца 2026-09-16, п.1:
               отдельный мультивыбор от свободнотекстовой «Категории» выше — по
               этим категориям товар выставляется в закупку. -->
          <v-col cols="12">
            <div class="d-flex align-center mb-1" style="gap:8px">
              <v-select
                v-model="form.purchase_category_ids"
                :items="categoryChoices"
                item-title="name" item-value="id"
                label="Категории закупки" multiple chips closable-chips
                variant="outlined" density="compact" hide-details
                class="flex-grow-1"
              />
              <v-btn size="small" variant="text" color="teal" prepend-icon="mdi-cog-outline" @click="catalogDialog = true">
                Справочник…
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">По этим категориям товар выставляется в закупку.</div>
          </v-col>

          <!-- Единица измерения (владелец, 2026-09-01) -->
          <v-col cols="12" md="3">
            <v-text-field v-model="form.unit"
              label="Ед. изм." variant="outlined" density="compact" clearable
              hint="шт, компл., кг…" persistent-hint />
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

          <!-- Владелец, сессия 2026-08-29: срок актуальности не константа —
               по умолчанию считается по категории (+ поправка на курс доллара),
               но можно переопределить персонально для этого товара. -->
          <v-col cols="12" md="6">
            <v-text-field v-model.number="form.price_ttl_days" label="Свой срок актуальности, дней" type="number"
              variant="outlined" density="compact" clearable
              hint="Пусто — берётся из настроек по категории" persistent-hint />
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
            <div v-if="photoPreview || (editingId && form.has_photo) || isLikelyImageUrl(form.photo_url) || isLikelyImageUrl(form.photo_link)" class="mb-3">
              <img
                :src="photoPreview || ((editingId && form.has_photo) ? `/api/products/${editingId}/photo?v=${photoCacheBuster}` : (isLikelyImageUrl(form.photo_url) ? form.photo_url : form.photo_link))"
                style="max-width:100%;max-height:180px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5"
              />
              <div class="d-flex gap-2 mt-1">
                <v-btn
                  v-if="editingId && form.has_photo"
                  size="x-small" variant="text" color="error"
                  :loading="deletingPhoto"
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
              @update:model-value="$emit('photo-file-change', $event)"
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
                @click="$emit('download-photo')"
              >Скачать</v-btn>
            </div>
            <v-text-field v-model="form.photo_link" label="Запасная ссылка" variant="outlined"
              density="compact" prepend-inner-icon="mdi-link" class="mt-2" />
          </v-col>

          <!-- Цены: история + средняя — решение владельца 2026-09-16, п.2/п.3,
               заменяет собой редактируемые «Ссылки для сравнения цен». -->
          <v-col cols="12">
            <PurchasePriceHistory :product-id="editingId" :legacy-price-links="form.priceLinks" />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
        <v-btn color="primary" :loading="saving" @click="$emit('save')">
          {{ editingId ? 'Сохранить' : 'Добавить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Справочник категорий закупки — управление списком (добавить/переименовать/
       выключить/удалить), решение владельца 2026-09-16, п.1. -->
  <PurchaseCategoriesDialog v-model="catalogDialog" :mobile="mobile" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatDate } from '@/composables/products/productsTypes'
import { isLikelyImageUrl } from '@/utils/productPhoto'
import { usePurchaseCategories } from '@/composables/products/usePurchaseCategories'
import PurchaseCategoriesDialog from '@/components/settings/PurchaseCategoriesDialog.vue'
import PurchasePriceHistory from '@/components/products/PurchasePriceHistory.vue'

const props = defineProps<{
  mobile: boolean
  editingId: number | null
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
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'clear-photo'): void
  (e: 'download-photo'): void
  (e: 'photo-file-change', value: File | File[] | null): void
}>()

const dialog = defineModel<boolean>('modelValue', { required: true })
const nameSearch = defineModel<string>('nameSearch', { required: true })

// Категории закупки (справочник) — решение владельца 2026-09-16, п.1. Диалог
// самодостаточен (тот же приём, что и ContractorPicker.vue со своим
// ContractorEditDialog): не требует прокидывать список категорий через
// ProductsView.vue отдельным пропом.
const { categories, activeCategories, load: loadPurchaseCategories } = usePurchaseCategories()
loadPurchaseCategories()

const catalogDialog = ref(false)

// Активные + уже выбранные неактивные (иначе выбор молча пропадает из списка,
// если категорию потом выключили в справочнике).
const categoryChoices = computed(() => {
  const selected = new Set<number>(props.form.purchase_category_ids || [])
  const extra = categories.value.filter(c => !c.is_active && selected.has(c.id))
  return [...activeCategories.value, ...extra]
})
</script>
