<template>
  <!-- food-menu-editor.md: владелец не принял «просто» (единая цена за
       приём) — режим «меню по дням» разбивает каждый день на отдельные
       приёмы (по умолчанию завтрак/обед/ужин, список редактируемый: можно
       переименовать, добавить, убрать) с описанием состава и ценой ЗА
       ПРИЁМ НА ЧЕЛОВЕКА у каждого приёма отдельно. Число дней управляется
       общим полем «Дней» формы (props.days), а не кнопкой внутри этого
       компонента — Правило №6, один счётчик дней на форму.

       Оформление (владелец, 2026-09-15, «даже мне не читаемо»): ТАБЛИЦА
       (строки — дни, столбцы — приёмы), а не стопка карточек-дней — так
       видно всю раскладку сразу, без прокрутки вниз по каждому дню. -->
  <div class="food-menu-editor">
    <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-2">
      <v-btn size="small" variant="text" prepend-icon="mdi-plus" :disabled="disabled" @click="addMealColumn">
        Приём
      </v-btn>
      <v-btn
        v-if="days_.length > 1"
        size="small" variant="tonal" prepend-icon="mdi-content-copy"
        :disabled="disabled"
        @click="repeatFirstDayToAll"
      >
        Повторить День 1 на все дни
      </v-btn>
    </div>

    <div v-if="!days_.length" class="text-caption text-medium-emphasis">
      Укажите «Дней» — здесь появится меню по дням.
    </div>

    <div v-else class="food-menu-table__scroll">
      <table class="food-menu-table">
        <thead>
          <tr>
            <th class="food-menu-table__day-col">День</th>
            <th v-for="name in mealColumns" :key="name" class="food-menu-table__meal-col">
              <div class="d-flex align-center ga-1">
                <v-text-field
                  :model-value="name" density="compact" variant="plain" hide-details
                  class="food-menu-table__col-name" title="Название приёма — можно переименовать"
                  :disabled="disabled"
                  @update:model-value="(v: string) => renameMealColumn(name, v)"
                />
                <v-btn icon="mdi-close" size="x-small" variant="text" density="comfortable"
                  :disabled="disabled" title="Убрать приём" @click="removeMealColumn(name)" />
              </div>
            </th>
            <th class="food-menu-table__total-col">Итого за день</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(day, dayIdx) in days_" :key="dayIdx">
            <td class="food-menu-table__day-col text-body-2 font-weight-medium">День {{ day.day }}</td>
            <td v-for="name in mealColumns" :key="name" class="food-menu-table__meal-col">
              <v-textarea
                :model-value="cellOf(day, name)?.description ?? ''"
                placeholder="состав" rows="1" auto-grow density="compact" variant="outlined" hide-details
                class="mb-1" :disabled="disabled"
                @update:model-value="(v: string) => setCell(dayIdx, name, 'description', v)"
              />
              <v-text-field
                :model-value="cellOf(day, name)?.price ?? ''"
                type="number" placeholder="₽/чел" density="compact" variant="outlined" hide-details
                :disabled="disabled"
                @update:model-value="(v: string) => setCell(dayIdx, name, 'price', numOrNull(v))"
              />
            </td>
            <td class="food-menu-table__total-col text-body-2">{{ fmtMoney(dayTotal(day)) }} ₽</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="days_.length" class="text-body-2 mt-2">
      Всего на человека: {{ fmtMoney(perPersonTotal) }} ₽
      <template v-if="personsNum > 0">
        · Итого: <strong>{{ fmtMoney(grandTotal) }} ₽</strong>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// food-menu-editor.md: редактор структуры extra.menu ([{day, meals:[{name,
// description, price}]}]) — цена ВСЕГДА за приём на человека. Формула итога
// (человек × Σ price всех приёмов всех дней) не дублируется здесь — только
// живой предпросмотр, тот же расчёт см. utils/itemAmounts.ts::foodMenuAmounts
// (превью) и backend/app/services/item_amounts.py::_food_menu_amounts
// (источник истины при сохранении, Правило №6).
import { computed, watch } from 'vue'
import type { FoodMenuDay, FoodMenuMeal } from '@/utils/itemAmounts'
import { itemFormDescriptor } from '@/composables/items/useItemForm'
import { numOrNull } from '@/utils/numberFormat'

const props = defineProps<{
  modelValue: FoodMenuDay[] | null | undefined
  days?: number | string | null
  persons?: number | string | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: FoodMenuDay[]]
}>()

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function fmtMoney(v: number): string {
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Названия приёмов по умолчанию для нового дня — ЕДИНСТВЕННЫЙ источник
// item_forms.json (services/item_forms.py::ITEM_FORMS.food.default_meal_names),
// второй копии списка здесь не заводить (Правило №6).
const defaultMealNames = computed<string[]>(
  () => itemFormDescriptor('food')?.default_meal_names ?? ['Завтрак', 'Обед', 'Ужин'],
)

function makeDefaultMeals(): FoodMenuMeal[] {
  return defaultMealNames.value.map(name => ({ name, description: '', price: null }))
}

const days_ = computed<FoodMenuDay[]>(() => Array.isArray(props.modelValue) ? props.modelValue : [])
const personsNum = computed(() => toNum(props.persons))

// Столбцы таблицы — объединение названий приёмов по всем дням (владелец:
// «столбцы приёмов общие для всех дней»), порядок — первое появление, день 1
// первым. Если у дней разные наборы — просто объединение по именам, пустые
// ячейки допустимы (см. cellOf/setCell ниже) — колонки НЕ навязывают
// одинаковую длину массива meals на каждый день.
const mealColumns = computed<string[]>(() => {
  const seen: string[] = []
  const set = new Set<string>()
  for (const d of days_.value) {
    for (const m of (Array.isArray(d?.meals) ? d.meals : [])) {
      if (m?.name && !set.has(m.name)) { set.add(m.name); seen.push(m.name) }
    }
  }
  return seen.length ? seen : defaultMealNames.value
})

function cellOf(day: FoodMenuDay, name: string): FoodMenuMeal | undefined {
  return (Array.isArray(day?.meals) ? day.meals : []).find(m => m?.name === name)
}

function dayTotal(day: FoodMenuDay): number {
  const meals = Array.isArray(day?.meals) ? day.meals : []
  return meals.reduce((s, m) => s + toNum(m?.price), 0)
}

const perPersonTotal = computed(() => days_.value.reduce((sum, d) => {
  const meals = Array.isArray(d?.meals) ? d.meals : []
  return sum + meals.reduce((s, m) => s + toNum(m?.price), 0)
}, 0))
const grandTotal = computed(() => Math.round((perPersonTotal.value * personsNum.value + Number.EPSILON) * 100) / 100)

// Синхронизация числа дней (общее поле формы «Дней», props.days) с длиной
// массива menu — владелец: «в позициях закупки должен добавлять дни»; дни
// добавляются/убираются через это число, а не отдельную кнопку внутри
// редактора. Новый день получает набор приёмов по умолчанию (или копию
// приёмов последнего существующего дня, если он уже был — сохраняет
// пользовательские переименования приёмов при увеличении числа дней).
watch(
  () => [toNum(props.days), days_.value.length] as const,
  ([target, currentLen]) => {
    if (!target || target === currentLen) return
    const next = days_.value.slice(0, target).map(d => ({ ...d, meals: d.meals.map(m => ({ ...m })) }))
    const template = next.length ? next[next.length - 1].meals.map(m => ({ ...m, price: null })) : makeDefaultMeals()
    while (next.length < target) {
      next.push({ day: next.length + 1, meals: template.map(m => ({ ...m })) })
    }
    next.forEach((d, i) => { d.day = i + 1 })
    emit('update:modelValue', next)
  },
  { immediate: true },
)

// Столбец = приём с этим названием у ВСЕХ дней (владелец: «кнопка "+ приём"
// добавляет столбец, "×" у заголовка убирает»). Переименование меняет имя у
// всех дней, где приём с таким названием уже есть — дни, где его ещё нет,
// не трогаем (пустая ячейка сама создаст запись при вводе, см. setCell).
function addMealColumn() {
  const existing = new Set(mealColumns.value)
  let n = 1
  let name = `Приём ${n}`
  while (existing.has(name)) { n += 1; name = `Приём ${n}` }
  const next = days_.value.map(d => ({ ...d, meals: [...d.meals, { name, description: '', price: null }] }))
  emit('update:modelValue', next)
}

function removeMealColumn(name: string) {
  const next = days_.value.map(d => ({ ...d, meals: d.meals.filter(m => m?.name !== name) }))
  emit('update:modelValue', next)
}

function renameMealColumn(oldName: string, newName: string) {
  const trimmed = (newName || '').trim()
  if (!trimmed || trimmed === oldName) return
  const next = days_.value.map(d => ({
    ...d,
    meals: d.meals.map(m => (m?.name === oldName ? { ...m, name: trimmed } : m)),
  }))
  emit('update:modelValue', next)
}

function setCell(dayIdx: number, name: string, field: 'description' | 'price', value: any) {
  const next = days_.value.map((d, i) => {
    if (i !== dayIdx) return d
    const meals = Array.isArray(d.meals) ? d.meals : []
    const mealIdx = meals.findIndex(m => m?.name === name)
    if (mealIdx === -1) {
      // Пустая ячейка (у этого дня ещё нет такого приёма) — создаём запись при первом вводе.
      const created: FoodMenuMeal = { name, description: '', price: null, [field]: value }
      return { ...d, meals: [...meals, created] }
    }
    return { ...d, meals: meals.map((m, j) => (j === mealIdx ? { ...m, [field]: value } : m)) }
  })
  emit('update:modelValue', next)
}

function repeatFirstDayToAll() {
  const first = days_.value[0]
  if (!first) return
  const next = days_.value.map((d, i) => i === 0 ? d : { ...d, meals: first.meals.map(m => ({ ...m })) })
  emit('update:modelValue', next)
}
</script>

<style scoped>
.food-menu-table__scroll {
  overflow-x: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
}
.food-menu-table {
  border-collapse: collapse;
  width: 100%;
}
.food-menu-table th, .food-menu-table td {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 4px 6px;
  vertical-align: top;
}
.food-menu-table th {
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  background: rgba(var(--v-theme-surface-variant), 0.35);
}
/* Владелец: «на мобильном таблица меню — прокрутка внутри панели, шапка
   с днями закреплена слева» — первая колонка (День N) прилипает при
   горизонтальном скролле food-menu-table__scroll. */
.food-menu-table__day-col {
  position: sticky;
  left: 0;
  z-index: 1;
  min-width: 88px;
  background: rgb(var(--v-theme-surface));
  white-space: nowrap;
}
.food-menu-table__meal-col {
  min-width: 170px;
}
.food-menu-table__total-col {
  min-width: 110px;
  white-space: nowrap;
  text-align: right;
}
.food-menu-table__col-name {
  min-width: 80px;
}
.food-menu-table__col-name :deep(input) {
  font-size: 12px;
  font-weight: 600;
}
</style>
