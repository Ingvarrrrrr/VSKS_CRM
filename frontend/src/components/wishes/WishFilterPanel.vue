<template>
  <!-- ── FILTER PANEL (общий для всех табов) ──
       Владелец (мобильные карточки, 2026-10-05): на телефоне панель по умолчанию
       свёрнута в одну горизонтальную прокручиваемую строку — «Фильтры · N» + чипы
       активных фильтров с крестиком (сброс конкретного фильтра). На десктопе
       вид и поведение НЕ меняются (та же v-card всегда развёрнута). -->
  <div v-if="mobile && !expanded" class="mb-4">
    <!-- Владелец (поиск на телефоне, 2026-10-05): «одно поле — ввожу буквы, остаются
         только подходящие заявки» — над строкой «Фильтры · N». font-size 16px НЕ
         косметика: iOS Safari зумит страницу при фокусе на поле мельче 16px (PWA). -->
    <v-text-field
      v-model="searchText"
      placeholder="Поиск: номер, предмет, автор, субсидия…"
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      density="compact"
      clearable
      hide-details
      class="wish-search-field mb-2"
      @click:clear="searchText = ''"
    />
    <div class="d-flex ga-2" style="overflow-x:auto; padding-bottom:2px">
      <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-filter-variant" style="flex:none" @click="expanded = true">
        Фильтры<template v-if="activeFilterChips.length"> · {{ activeFilterChips.length }}</template>
      </v-btn>
      <v-chip
        v-for="c in activeFilterChips"
        :key="c.key"
        size="small"
        variant="tonal"
        closable
        style="flex:none"
        @click="expanded = true"
        @click:close="clearOne(c.key)"
      >
        {{ c.label }}
      </v-chip>
    </div>
  </div>

  <v-card v-else variant="outlined" class="mb-4">
    <v-card-text v-if="mobile" class="pb-0 pt-2 d-flex justify-end">
      <v-btn size="small" variant="text" prepend-icon="mdi-chevron-up" @click="expanded = false">Свернуть</v-btn>
    </v-card-text>
    <v-card-text class="py-3">
      <div class="d-flex flex-wrap align-center" style="gap:12px">
        <!-- Владелец (поиск на десктопе, 2026-10-07): то же поле поиска, тот же
             searchText — на телефоне (свёрнутый вид выше) оно уже есть, здесь
             первым элементом развёрнутой панели, видимой на компьютере. -->
        <v-text-field
          v-model="searchText"
          placeholder="Поиск: номер, предмет, автор, субсидия…"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          class="wish-search-field"
          style="min-width:280px;flex:1 1 280px;max-width:420px"
          @click:clear="searchText = ''"
        />
        <v-select
          v-model="filters.wishTypes"
          :items="WISH_TYPE_OPTIONS"
          item-title="title"
          item-value="value"
          label="Тип заявки"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:190px;max-width:240px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:130px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.wishTypes.length - 1 }}</span>
          </template>
        </v-select>
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.accountIds"
          :items="accountOptions"
          item-title="name"
          item-value="id"
          label="Аккаунт"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:130px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.accountIds.length - 1 }}</span>
          </template>
        </v-autocomplete>
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.orgIds"
          :items="orgOptionsFiltered"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:130px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.orgIds.length - 1 }}</span>
          </template>
        </v-autocomplete>
        <v-autocomplete
          v-model="filters.subsidyIds"
          :items="ctx.subsidies.value"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:220px;max-width:280px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:140px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.subsidyIds.length - 1 }}</span>
          </template>
        </v-autocomplete>
        <v-autocomplete
          v-model="filters.creatorIds"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="От кого"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:200px;max-width:250px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:130px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.creatorIds.length - 1 }}</span>
          </template>
        </v-autocomplete>
        <v-autocomplete
          v-model="filters.assignedToIds"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="Кому"
          variant="outlined"
          density="compact"
          multiple
          clearable
          hide-details
          style="min-width:200px;max-width:250px"
        >
          <template #selection="{ item, index }">
            <span v-if="index === 0" class="text-truncate" style="max-width:130px">{{ item.title }}</span>
            <span v-else-if="index === 1" class="text-caption text-medium-emphasis ml-1">+{{ filters.assignedToIds.length - 1 }}</span>
          </template>
        </v-autocomplete>
        <v-text-field
          v-model="filters.createdFrom"
          type="date"
          label="Создано с"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.createdTo"
          type="date"
          label="Создано по"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.deadlineFrom"
          type="date"
          label="Срок с"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-text-field
          v-model="filters.deadlineTo"
          type="date"
          label="Срок по"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:150px;max-width:180px"
        />
        <v-btn variant="tonal" size="small" prepend-icon="mdi-filter-off" @click="resetAll">
          Очистить фильтры
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// WishFilterPanel.vue — общая панель фильтров для трёх вкладок заявок («Мои» /
// «На согласование мне» / «Заявки сотрудников»). Дословный перенос шаблона из
// WishesView.vue (см. useWishFilters.ts для состояния/buildFilterParams).
import { computed, ref } from 'vue'
import { useWishesContext } from '@/composables/wishes/useWishesContext'
import { WISH_TYPE_OPTIONS, type WishFiltersState } from '@/composables/wishes/useWishFilters'

const props = defineProps<{
  filters: WishFiltersState
  accountOptions: { id: number; name: string }[]
  orgOptionsFiltered: { id: number; name: string }[]
  resetFilters: () => void
  mobile: boolean
}>()

const ctx = useWishesContext()

// Владелец (поиск на телефоне, 2026-10-05): v-model:search-text из WishesView.vue —
// searchText хранится в useWishColumnMenu.ts (ПРАВИЛО №6, applyColFilters — общий
// конвейер фильтрации для всех трёх вкладок), здесь только поле ввода.
const searchText = defineModel<string>('searchText', { default: '' })

// Владелец (мобильные карточки, 2026-10-05): свёрнутое состояние панели на
// телефоне — по умолчанию свёрнута (первый экран не съедают фильтры), тап по
// кнопке/чипу разворачивает полную панель выше, «Свернуть» возвращает обратно.
const expanded = ref(false)

function namesOf(list: { id: number; name?: string; full_name?: string }[] | undefined, ids: number[]): string {
  if (ids.length === 1) {
    const found = list?.find(o => o.id === ids[0])
    return found ? (found.name ?? found.full_name ?? `#${ids[0]}`) : `#${ids[0]}`
  }
  return `выбрано ${ids.length}`
}

// Чипы активных фильтров — одно место для подсчёта N у кнопки «Фильтры · N» и
// для списка чипов со сбросом (ПРАВИЛО №6: не плодить второй способ посчитать
// «сколько фильтров задано» — один computed, читает то же filters, что и форма
// выше/buildFilterParams в useWishFilters.ts).
const activeFilterChips = computed(() => {
  const f = props.filters
  const chips: { key: keyof WishFiltersState; label: string }[] = []
  if (f.wishTypes.length) {
    const label = f.wishTypes.length === 1
      ? (WISH_TYPE_OPTIONS.find(o => o.value === f.wishTypes[0])?.title ?? f.wishTypes[0])
      : `выбрано ${f.wishTypes.length}`
    chips.push({ key: 'wishTypes', label: `Тип: ${label}` })
  }
  if (f.accountIds.length) chips.push({ key: 'accountIds', label: `Аккаунт: ${namesOf(props.accountOptions, f.accountIds)}` })
  if (f.orgIds.length) chips.push({ key: 'orgIds', label: `Организация: ${namesOf(props.orgOptionsFiltered, f.orgIds)}` })
  if (f.subsidyIds.length) chips.push({ key: 'subsidyIds', label: `Субсидия: ${namesOf(ctx.subsidies.value, f.subsidyIds)}` })
  if (f.creatorIds.length) chips.push({ key: 'creatorIds', label: `От: ${namesOf(ctx.users.value, f.creatorIds)}` })
  if (f.assignedToIds.length) chips.push({ key: 'assignedToIds', label: `Кому: ${namesOf(ctx.users.value, f.assignedToIds)}` })
  if (f.createdFrom) chips.push({ key: 'createdFrom', label: `Создано с ${f.createdFrom}` })
  if (f.createdTo) chips.push({ key: 'createdTo', label: `Создано по ${f.createdTo}` })
  if (f.deadlineFrom) chips.push({ key: 'deadlineFrom', label: `Срок с ${f.deadlineFrom}` })
  if (f.deadlineTo) chips.push({ key: 'deadlineTo', label: `Срок по ${f.deadlineTo}` })
  return chips
})

function clearOne(key: keyof WishFiltersState) {
  const isArr = Array.isArray((props.filters as any)[key])
  ;(props.filters as any)[key] = isArr ? [] : ''
}

// Владелец (поиск на десктопе, 2026-10-07): «Очистить фильтры» сбрасывал только
// props.filters (useWishFilters.ts) — поиск (searchText, отдельный composable
// useWishColumnMenu.ts, ПРАВИЛО №6: второй механизм не завожу) оставался
// заполненным. Здесь же, в единственном месте с доступом к обоим, сбрасываю оба.
function resetAll() {
  props.resetFilters()
  searchText.value = ''
}
</script>

<style scoped>
/* iOS Safari зумит страницу при фокусе на поле с font-size < 16px (PWA) — поле
   поиска обязано держать реальный 16px на <input>, не только на обёртке. */
.wish-search-field :deep(input) {
  font-size: 16px;
}
</style>
