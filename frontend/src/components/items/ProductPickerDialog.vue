<template>
  <!-- Presentational product picker. Parent owns search state, results list and
       all business logic; this child renders the dialog and emits user intents.
       Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="1600" width="95vw" scrollable :fullscreen="mobile"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card class="d-flex flex-column" style="height: calc(100vh - 48px)">
      <v-card-title class="text-h6 pt-4 px-4 px-sm-6 d-flex align-center justify-space-between">
        <span>{{ title || 'Выбрать товар из каталога' }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="px-4 pb-2 flex-grow-1" style="overflow-y:auto">
        <v-text-field
          :model-value="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск"
          :placeholder="SEARCH_PLACEHOLDER"
          :hint="remainingHint"
          :persistent-hint="!!remainingHint"
          variant="outlined" density="compact" clearable autofocus
          class="mb-3"
          @update:model-value="(v: string) => emit('update:search', v ?? '')"
        />
        <div v-if="!results.length" class="text-center text-medium-emphasis py-8">
          <v-icon icon="mdi-package-variant-closed" size="40" class="mb-2" />
          <div>Ничего не найдено</div>
          <!-- Баг 30.09 (авансовый РЕЕ-2026-00963): этот no-results блок раньше
               ВСЕГДА рисовал кнопку создания, даже когда вызывающий диалог явно
               says supportsFullProductDialog=false (PlanToRequestDialog.vue —
               там создание нового товара сознательно идёт только через
               «Добавить товар» в меню строки, второй экземпляр механизма не
               заводим, Правило №6). Кнопка была кликабельна, но обработчик
               вызывающей стороны просто отвечал тостом «здесь недоступно» —
               то есть кнопка обещала действие, которого не будет. Прячем её
               там, где create-new реально не поддерживается, вместо
               show-then-refuse. -->
          <v-btn v-if="supportsFullProductDialog" class="mt-3" variant="tonal" color="primary" prepend-icon="mdi-plus"
            @click="emit('create-new')">
            Добавить в каталог{{ search.length <= 30 ? ': «' + search + '»' : '' }}
          </v-btn>
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
            <tr v-for="p in results" :key="p.id"
              style="cursor:pointer" @click="emit('pick', p)">
              <td>
                <v-avatar size="36" rounded="sm" class="my-1" style="overflow:hidden">
                  <img v-if="photoSrc(p)" :src="photoSrc(p)!" style="width:36px;height:36px;object-fit:cover;display:block" @error="($event.target as HTMLImageElement).style.display='none'" />
                  <v-icon v-else icon="mdi-package-variant" color="grey" size="20" />
                </v-avatar>
              </td>
              <td>
                <div class="font-weight-medium">{{ p.name }}</div>
                <div v-if="p.unit" class="text-caption text-medium-emphasis">{{ formatUnitWithPack(p) }}</div>
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

        <!-- Живой поиск в магазинах (этап 1, владелец, 28.10.2026; правка QA
             29.10.2026 — кнопка видна ВСЕГДА под результатами нашей базы,
             когда введён текст поиска, не только когда наш каталог ничего
             не нашёл: владелец хочет дособрать предложения из магазинов и
             когда results.length>0. Авто-запуск остаётся прежним — только
             results.length===0 && querySpecific, см. ниже scheduleAutoStoreSearch). -->
        <div v-if="search.trim() && !isSearchTooShort(search)" class="mt-4">
          <v-btn v-if="!storeSearch.hasSearched.value" variant="text" size="small" prepend-icon="mdi-storefront-search-outline"
            @click="runStoreSearch">
            Искать в магазинах
          </v-btn>
          <StoreOffersPanel
            v-else
            :offers="storeSearch.offers.value"
            :stores="storeSearch.stores.value"
            :loading="storeSearch.loading.value"
            :error="storeSearch.error.value"
            :has-searched="storeSearch.hasSearched.value"
            class="mt-2 text-left"
          />
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-3 d-flex flex-wrap" style="gap:6px">
        <v-btn v-if="supportsFullProductDialog"
          variant="tonal" color="teal" size="small" prepend-icon="mdi-plus"
          class="flex-grow-0" @click="emit('create-new')">
          Новый товар
        </v-btn>
        <span class="text-caption text-medium-emphasis">{{ results.length }} позиций</span>
        <v-spacer />
        <v-btn variant="text" size="small" @click="emit('update:modelValue', false)">Отмена</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import type { ProductLike } from '@/components/items/types'
import { useDisplay } from 'vuetify'
import { formatUnitWithPack } from '@/utils/units'
// Подсказка минимума символов — ЕДИНЫЙ источник (ПРАВИЛО №6), см. docstring
// useProductSearch.ts/useItemsCatalog.ts::runPickerSearch.
import { SEARCH_PLACEHOLDER, searchRemainingHint, isSearchTooShort } from '@/composables/products/useProductSearch'
import { useStoreSearch } from '@/composables/products/useStoreSearch'
import StoreOffersPanel from '@/components/products/StoreOffersPanel.vue'

const { mobile } = useDisplay()

const props = defineProps<{
  modelValue: boolean
  search: string
  results: ProductLike[]
  supportsFullProductDialog?: boolean
  /** Заголовок окна — свой у режима «Изменить привязку к каталогу»
      (владелец 16.10.2026, PurchaseItemsEditor.vue::openRepickDialog). */
  title?: string
  /** Resolves the row photo src (parent's productPhotoSrc helper). */
  photoSrc: (p: ProductLike | null | undefined) => string | undefined
  /** query_specific ответа /products/page (useProductSearch.ts) — владелец,
      28.10.2026, правка «вторая волна»: авто-запуск живого поиска в магазинах
      ТОЛЬКО когда backend нашёл в разборе фразы бренд/модель/величину, не
      просто широкий вид товара. Родитель, который ищет НЕ через /page (нет
      такого поля — PlanToRequestDialog.vue), просто не передаёт пропс —
      тогда авто-запуска нет, остаётся только кнопка. */
  querySpecific?: boolean
}>()

const remainingHint = computed(() => searchRemainingHint(props.search))

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  'update:search': [v: string]
  pick: [product: ProductLike]
  'create-new': []
}>()

// Живой поиск в магазинах — свой экземпляр композабла (диалог сам по себе
// самодостаточный UI-блок, ПРАВИЛО №6: один и тот же useStoreSearch.ts, не
// второй механизм, просто без лишней прокладки через родителя). Сбрасывается
// при каждом новом открытии/смене текста поиска — старые результаты не
// должны остаться висеть при новом запросе.
const storeSearch = useStoreSearch()

function runStoreSearch(): void {
  void storeSearch.search(props.search)
}

watch(() => props.search, () => storeSearch.reset())
watch(() => props.modelValue, (open) => { if (!open) storeSearch.reset() })

// Наш каталог ничего не нашёл по осмысленному запросу (не короче
// MIN_SEARCH_CHARS) И querySpecific===true (бренд/модель/величина в
// разборе фразы, не просто широкий вид товара — владелец, 28.10.2026,
// правка «вторая волна») → запускаем поиск в магазинах сами. Иначе — только
// кнопка «Искать в магазинах» выше. Не чаще одного авто-запуска на один и
// тот же текст поиска (lastAutoStoreQuery) — props.results.length может
// остаться 0 при повторных срабатываниях реактивности без изменения текста.
let lastAutoStoreQuery: string | null = null
watch(
  () => props.results.length,
  (len) => {
    const text = props.search
    if (
      len === 0 && props.querySpecific && !isSearchTooShort(text)
      && lastAutoStoreQuery !== text
    ) {
      lastAutoStoreQuery = text
      runStoreSearch()
    }
  },
)
</script>
