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
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.accountId"
          :items="accountOptions"
          item-title="name"
          item-value="id"
          label="Аккаунт"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        />
        <v-autocomplete
          v-if="ctx.isSaas.value"
          v-model="filters.orgId"
          :items="orgOptionsFiltered"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:260px"
        />
        <v-autocomplete
          v-model="filters.subsidyId"
          :items="ctx.subsidies.value"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:220px;max-width:280px"
        />
        <v-autocomplete
          v-model="filters.creatorId"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="От кого"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:240px"
        />
        <v-autocomplete
          v-model="filters.assignedToId"
          :items="ctx.users.value"
          item-title="full_name"
          item-value="id"
          label="Кому"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          style="min-width:200px;max-width:240px"
        />
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
        <v-btn variant="tonal" size="small" prepend-icon="mdi-filter-off" @click="resetFilters">
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
import type { WishFiltersState } from '@/composables/wishes/useWishFilters'

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

function nameOf(list: { id: number; name?: string; full_name?: string }[] | undefined, id: number | null): string {
  const found = list?.find(o => o.id === id)
  return found ? (found.name ?? found.full_name ?? `#${id}`) : `#${id}`
}

// Чипы активных фильтров — одно место для подсчёта N у кнопки «Фильтры · N» и
// для списка чипов со сбросом (ПРАВИЛО №6: не плодить второй способ посчитать
// «сколько фильтров задано» — один computed, читает то же filters, что и форма
// выше/buildFilterParams в useWishFilters.ts).
const activeFilterChips = computed(() => {
  const f = props.filters
  const chips: { key: keyof WishFiltersState; label: string }[] = []
  if (f.accountId) chips.push({ key: 'accountId', label: `Аккаунт: ${nameOf(props.accountOptions, f.accountId)}` })
  if (f.orgId) chips.push({ key: 'orgId', label: `Организация: ${nameOf(props.orgOptionsFiltered, f.orgId)}` })
  if (f.subsidyId) chips.push({ key: 'subsidyId', label: `Субсидия: ${nameOf(ctx.subsidies.value, f.subsidyId)}` })
  if (f.creatorId) chips.push({ key: 'creatorId', label: `От: ${nameOf(ctx.users.value, f.creatorId)}` })
  if (f.assignedToId) chips.push({ key: 'assignedToId', label: `Кому: ${nameOf(ctx.users.value, f.assignedToId)}` })
  if (f.createdFrom) chips.push({ key: 'createdFrom', label: `Создано с ${f.createdFrom}` })
  if (f.createdTo) chips.push({ key: 'createdTo', label: `Создано по ${f.createdTo}` })
  if (f.deadlineFrom) chips.push({ key: 'deadlineFrom', label: `Срок с ${f.deadlineFrom}` })
  if (f.deadlineTo) chips.push({ key: 'deadlineTo', label: `Срок по ${f.deadlineTo}` })
  return chips
})

function clearOne(key: keyof WishFiltersState) {
  const isId = key.endsWith('Id')
  ;(props.filters as any)[key] = isId ? null : ''
}
</script>

<style scoped>
/* iOS Safari зумит страницу при фокусе на поле с font-size < 16px (PWA) — поле
   поиска обязано держать реальный 16px на <input>, не только на обёртке. */
.wish-search-field :deep(input) {
  font-size: 16px;
}
</style>
