<template>
  <div
    class="col-header-menu"
    :style="align === 'end' ? 'flex-direction: row-reverse' : ''"
  >
    <span class="col-header-menu__title">{{ title }}</span>

    <v-chip
      v-if="modelValue !== null"
      size="x-small"
      color="primary"
      variant="tonal"
      class="col-header-menu__chip"
    >
      ф
    </v-chip>

    <v-menu
      v-model="menuOpen"
      :close-on-content-click="false"
      location="bottom start"
      offset="4"
    >
      <template #activator="{ props: menuProps }">
        <v-btn
          v-bind="menuProps"
          icon
          size="x-small"
          variant="text"
          :style="modelValue === null ? 'opacity: 0.7' : ''"
          class="col-header-menu__btn"
          @click.stop
        >
          <v-icon size="14">
            {{ modelValue !== null ? 'mdi-filter' : 'mdi-filter-variant' }}
          </v-icon>
        </v-btn>
      </template>

      <v-card min-width="260" @click.stop>
        <!-- Сортировка -->
        <v-list-subheader class="text-uppercase text-caption font-weight-bold px-3 pt-2">
          Сортировка
        </v-list-subheader>
        <div class="d-flex gap-1 px-3 pb-1">
          <v-btn
            size="small"
            variant="tonal"
            :color="sortBy === 'asc' ? 'primary' : undefined"
            @click="onSort('asc')"
          >
            ↑ По возрастанию
          </v-btn>
          <v-btn
            size="small"
            variant="tonal"
            :color="sortBy === 'desc' ? 'primary' : undefined"
            @click="onSort('desc')"
          >
            ↓ По убыванию
          </v-btn>
        </div>
        <div v-if="sortBy" class="px-3 pb-2">
          <v-btn size="x-small" variant="text" @click="onSort(null)">
            Сбросить сортировку
          </v-btn>
        </div>

        <v-divider />

        <!-- Фильтр -->
        <v-list-subheader class="text-uppercase text-caption font-weight-bold px-3 pt-2">
          Фильтр
        </v-list-subheader>

        <!-- text -->
        <template v-if="colType === 'text'">
          <div class="px-3 pb-2">
            <v-text-field
              :model-value="textLocal"
              placeholder="Содержит…"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              @update:model-value="onTextInput"
            />
          </div>
        </template>

        <!-- enum -->
        <template v-else-if="colType === 'enum'">
          <div class="px-3 pb-1">
            <v-text-field
              v-model="enumSearch"
              placeholder="Поиск…"
              density="compact"
              variant="outlined"
              hide-details
              clearable
            />
          </div>
          <div class="d-flex gap-1 px-3 pb-1">
            <v-btn size="x-small" variant="text" @click="enumSelectAll">Выбрать все</v-btn>
            <v-btn size="x-small" variant="text" @click="enumClearAll">Снять все</v-btn>
          </div>
          <div style="max-height: 240px; overflow-y: auto">
            <v-checkbox
              v-for="item in filteredEnumItems"
              :key="String(item)"
              :model-value="enumSelected.includes(item)"
              :label="enumLabel(item)"
              density="compact"
              hide-details
              class="px-3"
              @update:model-value="(v) => onEnumToggle(item, v as boolean)"
            />
          </div>
        </template>

        <!-- number -->
        <template v-else-if="colType === 'number'">
          <div class="px-3 pb-2 d-flex gap-2">
            <v-text-field
              :model-value="numberMin"
              label="От"
              type="number"
              inputmode="decimal"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="(v) => onNumberChange('min', v as string)"
            />
            <v-text-field
              :model-value="numberMax"
              label="До"
              type="number"
              inputmode="decimal"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="(v) => onNumberChange('max', v as string)"
            />
          </div>
        </template>

        <!-- date -->
        <template v-else-if="colType === 'date'">
          <div class="px-3 pb-2 d-flex gap-2">
            <v-text-field
              :model-value="dateFrom"
              label="От"
              type="date"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="(v) => onDateChange('from', v as string)"
            />
            <v-text-field
              :model-value="dateTo"
              label="До"
              type="date"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="(v) => onDateChange('to', v as string)"
            />
          </div>
        </template>

        <!-- boolean -->
        <template v-else-if="colType === 'boolean'">
          <div class="px-3 pb-2 d-flex gap-1">
            <v-btn
              size="small"
              variant="tonal"
              :color="boolLocal === true ? 'primary' : undefined"
              @click="onBoolChange(true)"
            >
              Да
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :color="boolLocal === false ? 'primary' : undefined"
              @click="onBoolChange(false)"
            >
              Нет
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              :color="boolLocal === null ? 'primary' : undefined"
              @click="onBoolChange(null)"
            >
              Все
            </v-btn>
          </div>
        </template>

        <v-divider />

        <!-- Скрыть колонку + сбросить фильтр -->
        <div class="d-flex align-center justify-space-between px-3 py-2">
          <v-btn
            v-if="modelValue !== null"
            size="small"
            variant="text"
            color="error"
            @click="onClearFilter"
          >
            Сбросить фильтр
          </v-btn>
          <v-spacer />
          <v-btn
            size="small"
            variant="text"
            prepend-icon="mdi-eye-off"
            @click="onHide"
          >
            Скрыть колонку
          </v-btn>
        </div>
      </v-card>
    </v-menu>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { FilterValue } from '@/composables/useColumnConfig'

const props = defineProps<{
  colKey: string
  title: string
  colType: 'text' | 'enum' | 'number' | 'date' | 'boolean'
  items?: (string | number | null)[]
  itemLabels?: Record<string, string> | ((v: string | number | null) => string)
  modelValue: FilterValue | null
  sortBy?: 'asc' | 'desc' | null
  align?: 'start' | 'center' | 'end'
}>()

const emit = defineEmits<{
  'update:modelValue': [FilterValue | null]
  'sort': [direction: 'asc' | 'desc' | null]
  'hide': []
}>()

const menuOpen = ref(false)

// ---------- sort ----------
function onSort(direction: 'asc' | 'desc' | null) {
  emit('sort', direction)
}

// ---------- hide ----------
function onHide() {
  menuOpen.value = false
  emit('hide')
}

// ---------- clear filter ----------
function onClearFilter() {
  emit('update:modelValue', null)
}

// ---------- text ----------
const textLocal = computed(() =>
  props.modelValue?.type === 'text' ? props.modelValue.q : ''
)

let textDebounceTimer: ReturnType<typeof setTimeout> | null = null
function onTextInput(v: string) {
  if (textDebounceTimer) clearTimeout(textDebounceTimer)
  textDebounceTimer = setTimeout(() => {
    if (v) {
      emit('update:modelValue', { type: 'text', q: v })
    } else {
      emit('update:modelValue', null)
    }
  }, 200)
}

// ---------- enum ----------
const enumSearch = ref('')
const enumSelected = ref<(string | number | null)[]>(
  props.modelValue?.type === 'enum' ? [...props.modelValue.values] : []
)

watch(
  () => props.modelValue,
  (v) => {
    if (v?.type === 'enum') enumSelected.value = [...v.values]
    else if (v === null) enumSelected.value = []
  }
)

function enumLabel(item: string | number | null): string {
  if (item === null || item === '') return '(пусто)'
  const labels = props.itemLabels
  if (typeof labels === 'function') return labels(item) || String(item)
  if (labels && typeof labels === 'object') return labels[String(item)] || String(item)
  return String(item)
}

const filteredEnumItems = computed(() => {
  const all = props.items ?? []
  if (!enumSearch.value) return all
  const q = enumSearch.value.toLowerCase()
  return all.filter(item => enumLabel(item).toLowerCase().includes(q))
})

function onEnumToggle(item: string | number | null, checked: boolean) {
  const next = checked
    ? [...enumSelected.value, item]
    : enumSelected.value.filter(v => v !== item)
  enumSelected.value = next
  if (next.length === 0) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', { type: 'enum', values: next })
  }
}

function enumSelectAll() {
  const all = props.items ?? []
  enumSelected.value = [...all]
  if (all.length === 0) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', { type: 'enum', values: [...all] })
  }
}

function enumClearAll() {
  enumSelected.value = []
  emit('update:modelValue', null)
}

// ---------- number ----------
const numberMin = computed(() =>
  props.modelValue?.type === 'number' ? props.modelValue.min : null
)
const numberMax = computed(() =>
  props.modelValue?.type === 'number' ? props.modelValue.max : null
)

function onNumberChange(field: 'min' | 'max', raw: string) {
  const val = raw === '' || raw === null ? null : Number(raw)
  const current = props.modelValue?.type === 'number'
    ? { ...props.modelValue }
    : { type: 'number' as const, min: null, max: null }
  const next = { ...current, [field]: val }
  if (next.min === null && next.max === null) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', next)
  }
}

// ---------- date ----------
const dateFrom = computed(() =>
  props.modelValue?.type === 'date' ? props.modelValue.from : null
)
const dateTo = computed(() =>
  props.modelValue?.type === 'date' ? props.modelValue.to : null
)

function onDateChange(field: 'from' | 'to', raw: string) {
  const val = raw || null
  const current = props.modelValue?.type === 'date'
    ? { ...props.modelValue }
    : { type: 'date' as const, from: null, to: null }
  const next = { ...current, [field]: val }
  if (next.from === null && next.to === null) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', next)
  }
}

// ---------- boolean ----------
const boolLocal = computed(() =>
  props.modelValue?.type === 'boolean' ? props.modelValue.value : null
)

function onBoolChange(v: boolean | null) {
  if (v === null) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', { type: 'boolean', value: v })
  }
}
</script>

<style scoped>
.col-header-menu {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  overflow: hidden;
}

.col-header-menu__title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.col-header-menu__chip {
  flex-shrink: 0;
}

.col-header-menu__btn {
  flex-shrink: 0;
  min-width: 24px !important;
  width: 24px;
  height: 24px;
}
</style>
