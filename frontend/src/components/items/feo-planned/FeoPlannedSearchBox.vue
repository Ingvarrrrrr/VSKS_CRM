<template>
  <!-- Поиск по ВСЕМ плановым позициям субсидии (владелец, 2026-09-16, дефект 1/3):
       v-autocomplete — и поле ввода, и выпадающий список одновременно (жалоба:
       «тыкаю в поле — список, но НЕТ поля для ввода»), без v-model на постоянное
       значение (это поиск-действие, не хранимый выбор — после клика по варианту
       поле очищается, см. onSelect). -->
  <v-autocomplete
    :model-value="null"
    :search="searchText"
    @update:search="onUpdateSearch"
    @update:focused="onFocusedUpdate"
    v-model:menu="menuOpen"
    :items="rows"
    item-title="name"
    item-value="key"
    :loading="loading"
    :disabled="readonly"
    density="compact"
    variant="outlined"
    clearable
    hide-no-data
    hide-details
    no-filter
    placeholder="Поиск по всем плановым позициям субсидии…"
    prepend-inner-icon="mdi-magnify"
    class="feo-planned-search-box mb-2"
    :menu-props="{ maxHeight: 360 }"
    @update:model-value="onSelectKey"
  >
    <template #item="{ item, props: itemProps }">
      <v-list-item v-bind="itemProps" :title="undefined">
        <div class="d-flex align-center ga-2 flex-wrap">
          <span class="text-body-2">{{ item.raw.name }}</span>
          <v-chip v-if="item.raw.score >= 0.999" size="x-small" color="success" variant="tonal">точное совпадение</v-chip>
          <v-chip v-else-if="item.raw.score >= 0.6" size="x-small" color="amber" variant="tonal">похоже, {{ Math.round(item.raw.score * 100) }}%</v-chip>
          <v-chip v-if="item.raw.crossCategory" size="x-small" color="warning" variant="tonal">другая категория</v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">
          <template v-if="item.raw.crossCategory">{{ item.raw.path }} — выбор перенесёт позицию в эту категорию · </template>
          остаток {{ fmt(item.raw.residual) }}
        </div>
      </v-list-item>
    </template>
  </v-autocomplete>
</template>

<script setup lang="ts">
// Дефект (владелец, прод, скриншот — «меню 1 раз мелькает, навигацию не
// даёт, на следующих строках даже не пытается появиться»): причина — ДВЕ
// внутренние особенности Vuetify VAutocomplete (подтверждено чтением
// node_modules/vuetify/lib/components/VAutocomplete/VAutocomplete.js и живым
// Playwright-прогоном с перехватом /feo-planned-items/match):
// 1) watch(isFocused) в VAutocomplete на КАЖДОМ focus-in сбрасывает `search`
//    в '' (т.к. `model-value` у нас намеренно всегда null — это поиск-
//    действие, см. комментарий выше у шаблона, — а компонент считает «нет
//    выбранного значения» и стирает поле, как для чистого combobox). Это
//    стирает заранее подставленный текст (имя строки импорта факта) ДО того,
//    как пользователь успевает что-то увидеть/нажать — сам стёртый '' уходит
//    через @update:search в searchText (это ОДИН и тот же ref, что кормит
//    запрос), запрос с пустым текстом ничего не находит → список пуст.
// 2) watch(items) открывает меню САМ только если список был пуст и ПОЯВИЛСЯ
//    НОВЫЙ непустой — при открытии на второй и далее строке `rows` уже был
//    непустым с прошлого раза (тот же компонент, не пересоздаётся), так что
//    меню не открывается вовсе, даже когда результаты есть.
// Фикс — не бороться с внутренней логикой, а: (а) сразу после focus-in
// восстанавливать то, что было в searchText ДО сброса (nextTick — после
// внутреннего watcher, который отрабатывает в 'pre'-фазе до рендера);
// (б) открывать меню явно по приходу непустого списка `rows`, не дожидаясь
// фокуса — ПРАВИЛО №6 не нарушено: второй механизм поиска не завели, тут
// только управление открытием/восстановлением текста вокруг существующего.
import { nextTick, ref, watch } from 'vue'
import type { FeoPlannedSearchRow } from '@/composables/items/feoPlanned/useFeoPlannedSearch'

const searchText = defineModel<string>('searchText', { default: '' })

const props = defineProps<{
  rows: FeoPlannedSearchRow[]
  loading?: boolean
  readonly?: boolean
  fmt: (v: number | null | undefined) => string
}>()

const emit = defineEmits<{
  select: [row: FeoPlannedSearchRow]
}>()

const menuOpen = ref(false)

function onUpdateSearch(v: string) {
  searchText.value = v
}

function onFocusedUpdate(focused: boolean) {
  if (!focused) return
  const before = searchText.value
  if (!before) return
  // VAutocomplete может синхронно стереть search в '' в этом же тике
  // (watch(isFocused) внутри компонента) — восстанавливаем ПОСЛЕ, иначе
  // наша же запись будет перезатёрта следующим тиком.
  void nextTick(() => {
    if (!searchText.value && before) {
      searchText.value = before
      if (props.rows.length > 0) menuOpen.value = true
    }
  })
}

// Меню открываем по самому факту «есть что показать», а не по фокусу — это
// и чинит «не пытается появиться на следующих строках», и даёт требуемое
// «при открытии диалога сразу видны варианты» (родитель, FactImportRowPlan
// Picker.vue, передаёт либо похожие по имени, либо весь план на просмотр).
watch(() => props.rows, rows => {
  if (rows.length > 0) menuOpen.value = true
})

function onSelectKey(key: string | null) {
  if (!key) return
  const row = props.rows.find(r => r.key === key)
  if (row) emit('select', row)
}
</script>

<style scoped>
.feo-planned-search-box :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 4px;
  padding-bottom: 4px;
}
</style>
