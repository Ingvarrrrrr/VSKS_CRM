<template>
  <!-- food-menu-editor.md: владелец не принял «просто» (единая цена за
       приём) — режим «меню по дням» разбивает каждый день на отдельные
       приёмы (по умолчанию завтрак/обед/ужин, список редактируемый: можно
       переименовать, добавить, убрать) с описанием состава и ценой ЗА
       ПРИЁМ НА ЧЕЛОВЕКА у каждого приёма отдельно. Число дней управляется
       общим полем «Дней» формы (props.days), а не кнопкой внутри этого
       компонента — Правило №6, один счётчик дней на форму. -->
  <div class="food-menu-editor">
    <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-2">
      <div class="text-caption text-medium-emphasis">{{ hint }}</div>
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

    <v-sheet
      v-for="(day, dayIdx) in days_" :key="dayIdx"
      class="food-menu-editor__day mb-3 pa-2" variant="outlined" rounded
    >
      <div class="text-subtitle-2 mb-2">День {{ day.day }}</div>

      <div
        v-for="(meal, mealIdx) in day.meals" :key="mealIdx"
        class="food-menu-editor__meal d-flex flex-wrap align-start ga-2 mb-2"
      >
        <v-text-field
          :model-value="meal.name" label="Приём" placeholder="Завтрак"
          density="compact" variant="outlined" hide-details style="min-width:140px"
          :disabled="disabled"
          @update:model-value="(v: string) => setMealField(dayIdx, mealIdx, 'name', v)"
        />
        <v-text-field
          :model-value="meal.description" label="Состав" placeholder="каша, чай"
          density="compact" variant="outlined" hide-details style="min-width:260px;flex-grow:1"
          :disabled="disabled"
          @update:model-value="(v: string) => setMealField(dayIdx, mealIdx, 'description', v)"
        />
        <v-text-field
          :model-value="meal.price ?? ''" type="number" label="Цена/чел, ₽"
          density="compact" variant="outlined" hide-details style="min-width:130px"
          :disabled="disabled"
          @update:model-value="(v: string) => setMealField(dayIdx, mealIdx, 'price', numOrNull(v))"
        />
        <v-btn
          icon="mdi-close" size="small" variant="text" density="comfortable"
          :disabled="disabled" title="Убрать приём"
          @click="removeMeal(dayIdx, mealIdx)"
        />
      </div>

      <v-btn size="small" variant="text" prepend-icon="mdi-plus" :disabled="disabled" @click="addMeal(dayIdx)">
        Добавить приём
      </v-btn>
    </v-sheet>

    <div v-if="days_.length" class="text-body-2 mt-1">
      Итого: {{ fmtMoney(perPersonTotal) }} ₽ на человека
      <template v-if="personsNum > 0">
        × {{ personsNum }} чел. = <strong>{{ fmtMoney(grandTotal) }} ₽</strong>
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

const hint = computed(() => 'Цена — за приём на одного человека')

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

function setMealField(dayIdx: number, mealIdx: number, key: keyof FoodMenuMeal, value: any) {
  const next = days_.value.map((d, i) => i === dayIdx
    ? { ...d, meals: d.meals.map((m, j) => j === mealIdx ? { ...m, [key]: value } : m) }
    : d)
  emit('update:modelValue', next)
}

function addMeal(dayIdx: number) {
  const next = days_.value.map((d, i) => i === dayIdx
    ? { ...d, meals: [...d.meals, { name: '', description: '', price: null }] }
    : d)
  emit('update:modelValue', next)
}

function removeMeal(dayIdx: number, mealIdx: number) {
  const next = days_.value.map((d, i) => i === dayIdx
    ? { ...d, meals: d.meals.filter((_, j) => j !== mealIdx) }
    : d)
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
.food-menu-editor__day {
  border-color: rgba(var(--v-border-color), var(--v-border-opacity)) !important;
}
</style>
