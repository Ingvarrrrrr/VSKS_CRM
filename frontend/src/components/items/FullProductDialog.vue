<template>
  <!-- Presentational full create/edit product dialog. The parent owns the
       reactive `form`, all computed suggestion/option lists, the avg-price,
       the saving flag and the save handler. This child renders the form
       (mutating the passed reactive `form` in place) and emits intents.
       Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="1600" width="95vw" scrollable :fullscreen="mobile"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card class="d-flex flex-column" style="height: calc(100vh - 48px)">
      <v-card-title class="text-h6 pt-4 px-4 px-sm-6 d-flex align-center justify-space-between">
        <span>{{ editingId ? 'Редактировать товар / услугу' : 'Добавить товар / услугу в каталог' }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="px-4 px-sm-6 flex-grow-1" style="overflow-y:auto">
        <v-row dense>
          <v-col cols="12">
            <v-combobox
              v-model="form.name"
              :search="nameSearch"
              :items="nameSuggestions"
              no-filter
              label="Наименование *"
              variant="outlined" density="compact"
              autofocus
              :rules="[(v: string) => !!v || 'Обязательное поле']"
              :hint="isDuplicate ? '⚠ Товар с таким названием уже есть в каталоге' : ''"
              :persistent-hint="isDuplicate"
              @update:search="(v: string) => emit('update:nameSearch', v ?? '')"
            >
              <template #item="{ item: listItem, props: itemProps }">
                <v-list-item v-bind="itemProps" :title="listItem.raw">
                  <template #append>
                    <v-chip size="x-small" color="warning" variant="tonal">уже есть</v-chip>
                  </template>
                </v-list-item>
              </template>
            </v-combobox>
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="form.item_kind"
              :items="[{ title: 'Товар', value: 'товар' }, { title: 'Услуга', value: 'услуга' }]"
              label="Товар / Услуга" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="4">
            <v-combobox v-model="form.product_type"
              :items="typeOptions"
              label="Тип товара" variant="outlined" density="compact" clearable
              hint="Напр.: Ноутбук, Тренажёр" persistent-hint />
          </v-col>
          <v-col cols="12" md="4">
            <v-combobox v-model="form.category"
              :items="categoryOptions"
              label="Категория *"
              :rules="[(v: any) => (!!v && String(v).trim().length > 0) || 'Категория обязательна']"
              required
              variant="outlined" density="compact"
              hint="Выберите или введите новую (обязательное поле)" persistent-hint />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model.number="form.price" label="Цена за ед., ₽" type="number"
              variant="outlined" density="compact"
              :readonly="avgPrice !== null"
              :hint="avgPrice !== null ? 'Среднее из ссылок — ' + avgPrice.toLocaleString('ru-RU') + ' ₽' : 'Можно задать вручную или через ссылки'"
              persistent-hint />
          </v-col>
          <v-col cols="12" md="6">
            <v-switch v-model="form.is_active" label="Активен" color="success" density="compact" hide-details class="mt-1" />
          </v-col>
          <v-col cols="12">
            <v-textarea v-model="form.description" label="Описание" variant="outlined"
              density="compact" rows="2" auto-grow />
          </v-col>
          <v-col v-if="supportsPhotoUpload" cols="12">
            <div class="text-subtitle-2 mb-2">Фото товара</div>
            <div v-if="photoPreview" class="mb-3">
              <img :src="photoPreview" style="max-width:100%;max-height:140px;object-fit:contain;display:block;border-radius:4px;border:1px solid #e0e0e0;background:#f5f5f5" />
            </div>
            <v-file-input
              :model-value="photoFileList"
              label="Загрузить фото с компьютера"
              accept="image/jpeg,image/jpg,image/png,image/webp,image/gif"
              variant="outlined" density="compact" prepend-icon="mdi-camera" show-size clearable
              @update:model-value="(v: any) => emit('photo-file-change', v)"
            />
            <v-text-field v-model="form.photo_link" label="Или ссылка на фото" variant="outlined"
              density="compact" prepend-inner-icon="mdi-image-outline" class="mt-2"
              :disabled="hasPhotoFile" />
          </v-col>
          <v-col cols="12">
            <div class="text-subtitle-2 mb-2">
              Ссылки для сравнения цен
              <span v-if="avgPrice !== null" class="text-caption font-weight-bold text-blue-darken-2 ml-2">
                ср. {{ avgPrice.toLocaleString('ru-RU') }} ₽
              </span>
            </div>
            <div v-for="(link, i) in form.priceLinks" :key="i" class="d-flex gap-2 mb-2 align-center">
              <v-text-field v-model="link.url" :label="'Ссылка ' + (i + 1)" variant="outlined" density="compact"
                hide-details prepend-inner-icon="mdi-link" class="flex-grow-1" />
              <v-text-field v-model.number="link.price" label="Цена, ₽" type="number"
                variant="outlined" density="compact" hide-details style="max-width:140px" />
              <v-btn v-if="link.url" icon="mdi-open-in-new" variant="text" size="x-small" color="primary"
                :href="link.url" target="_blank" />
              <v-btn icon="mdi-minus-circle" variant="text" size="x-small" color="error"
                @click="form.priceLinks.splice(i, 1)" />
            </div>
            <v-btn prepend-icon="mdi-plus" variant="tonal" size="small" color="primary"
              @click="form.priceLinks.push({ url: '', price: null })">
              Добавить ссылку
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-4 pb-4 d-flex flex-wrap" style="gap:8px">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="primary" :loading="saving"
          :disabled="!form.category || !String(form.category).trim()"
          @click="emit('save')">
          {{ editingId ? 'Сохранить' : 'Добавить в каталог' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { FullProductForm } from '@/components/items/types'
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()

defineProps<{
  modelValue: boolean
  /** Reactive form owned by the parent; mutated in place via v-model. */
  form: FullProductForm
  editingId: number | null
  saving?: boolean
  supportsPhotoUpload?: boolean
  nameSearch: string
  nameSuggestions: string[]
  isDuplicate: boolean
  typeOptions: string[]
  categoryOptions: string[]
  avgPrice: number | null
  photoPreview: string | null
  photoFileList: File[]
  hasPhotoFile: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  'update:nameSearch': [v: string]
  'photo-file-change': [files: File[] | File | null]
  save: []
}>()
</script>
