<template>
  <!-- Мультивыбор категорий закупки с инлайн-созданием — единый виджет для
       ВСЕХ экранов, где заводится/правится товар (ПРАВИЛО №6: одна точка
       выбора категорий закупки, не копия v-select на каждый диалог).
       Источник данных и мутации — composables/products/usePurchaseCategories.ts
       (модульный ref, общий со справочником PurchaseCategoriesDialog). -->
  <div class="d-flex align-center flex-wrap" style="gap:8px">
    <v-autocomplete
      v-model="model"
      v-model:search="search"
      :items="categoryChoices"
      item-title="name" item-value="id"
      label="Категории закупки" multiple chips closable-chips clearable
      variant="outlined" density="compact" hide-details
      :loading="loading || creating"
      class="flex-grow-1" style="min-width:220px"
      no-filter
      :custom-filter="filterCategories"
    >
      <template #append-item>
        <!-- #append-item у Vuetify рисуется ВСЕГДА (безусловно, независимо от
             того, пуст ли список) — см. VAutocomplete.js: `slots['append-item']?.()`
             без охранного условия. А вот #no-data из-за `no-filter` (нужен для
             своего filterCategories, иначе no-filter+custom-filter конфликтуют —
             custom-filter тогда вовсе не вызывается, composables/filter.js:
             `!options?.noFilter`) у Vuetify практически никогда не срабатывает:
             internal displayItems не пустеет, т.к. фильтрация отключена. Поэтому
             «Создать» живёт ТОЛЬКО тут, единственным местом, независимо от
             filteredCount — иначе при filteredCount===0 пункт «Создать» пропадал
             бы совсем (ни #append-item, ни #no-data его не показывали — поймано
             живым прогоном e2e 14.10, не только статикой). #no-data ниже оставлен
             только для текста «Нет категорий» и для вырожденного случая, когда
             categoryChoices в принципе пуст. -->
        <v-list-item
          v-if="trimmedSearch && !exactMatch"
          :disabled="creating" @click="handleCreate"
        >
          <v-list-item-title>Создать категорию «{{ trimmedSearch }}»</v-list-item-title>
        </v-list-item>
        <v-list-item v-else-if="trimmedSearch && filteredCount === 0">
          <v-list-item-title class="text-medium-emphasis">Нет категорий</v-list-item-title>
        </v-list-item>
      </template>
      <template #no-data>
        <v-list-item v-if="trimmedSearch">
          <v-list-item-title class="text-medium-emphasis">Нет категорий</v-list-item-title>
        </v-list-item>
      </template>
    </v-autocomplete>
    <v-btn v-if="showManage" size="small" variant="text" color="teal" prepend-icon="mdi-cog-outline"
      @click="manageDialog = true">
      Справочник…
    </v-btn>
    <PurchaseCategoriesDialog v-if="showManage" v-model="manageDialog" :mobile="mobile" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePurchaseCategories } from '@/composables/products/usePurchaseCategories'
import PurchaseCategoriesDialog from '@/components/settings/PurchaseCategoriesDialog.vue'

const props = withDefaults(defineProps<{
  modelValue: number[]
  mobile?: boolean
  /** Кнопка «Справочник…» — скрыть там, где она избыточна (не сейчас, но на будущее). */
  showManage?: boolean
}>(), {
  mobile: false,
  showManage: true,
})

const emit = defineEmits<{ 'update:modelValue': [v: number[]] }>()

const { categories, activeCategories, loading, load, createCategory } = usePurchaseCategories()
load()

const model = computed<number[]>({
  get: () => props.modelValue || [],
  set: v => emit('update:modelValue', v),
})

// Активные + уже выбранные неактивные (иначе выбор молча пропадает из списка,
// если категорию потом выключили в справочнике) — перенесено из
// ProductFormDialog.vue, теперь единственная версия этого правила (ПРАВИЛО №6).
const baseChoices = computed(() => {
  const selected = new Set<number>(props.modelValue || [])
  const extra = categories.value.filter(c => !c.is_active && selected.has(c.id))
  return [...activeCategories.value, ...extra]
})

const search = ref('')
const trimmedSearch = computed(() => (search.value || '').trim())
const exactMatch = computed(() => {
  const q = trimmedSearch.value.toLowerCase()
  if (!q) return true
  return activeCategories.value.some(c => c.name.trim().toLowerCase() === q)
})

// Фильтр по подстроке в названии (без учёта регистра) — набранный текст
// остаётся виден в поле (no-filter + свой фильтр, т.к. стандартный фильтр
// v-autocomplete по умолчанию сверяет с item-title строго, что ломает кейс
// "мебель" ищет "Мебель").
function filterCategories(_itemTitle: string, queryText: string, item: any): boolean {
  if (!queryText) return true
  return (item?.raw?.name || '').toLowerCase().includes(queryText.toLowerCase())
}

// Сколько категорий реально совпало с trimmedSearch (без учёта уже выбранных) —
// определяет, в какой слот (#append-item / #no-data) попадает пункт «Создать»
// (см. комментарий выше про #append-item/#no-data).
const filteredCount = computed(() => {
  const q = trimmedSearch.value
  if (!q) return baseChoices.value.length
  return baseChoices.value.filter(c => filterCategories('', q, { raw: c })).length
})

// no-filter у v-autocomplete означает, что Vuetify сам список НЕ сужает —
// custom-filter с no-filter вместе не работают (Vuetify просто игнорирует
// custom-filter, если no-filter стоит), поэтому фильтруем сами и отдаём в
// :items уже готовый список (приёмка 14.10: «пож» не сужал список).
// Уже выбранные категории оставляем в items независимо от совпадения —
// иначе их чипы пропадают из поля при наборе текста, не совпадающего с ними.
const categoryChoices = computed(() => {
  const q = trimmedSearch.value
  if (!q) return baseChoices.value
  const selected = new Set<number>(props.modelValue || [])
  return baseChoices.value.filter(c => selected.has(c.id) || filterCategories('', q, { raw: c }))
})

const creating = ref(false)
async function handleCreate() {
  const name = trimmedSearch.value
  if (!name || creating.value) return
  creating.value = true
  try {
    const res = await createCategory(name)
    if (res.ok) {
      model.value = [...model.value, res.item.id]
      search.value = ''
    }
  } finally {
    creating.value = false
  }
}

const manageDialog = ref(false)
</script>
