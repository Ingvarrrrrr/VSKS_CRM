<template>
  <!-- item-forms-accommodation-transport.md, шаг 3: рендерит спец-поля позиции
       («Проживание»/«Перевозки автобусом») по описанию из item_forms.json —
       ЕДИНСТВЕННЫЙ рендерер этих полей (Правило №6), таблицы (ItemsTableFlat/
       Stages/Wish/ItemsCardsView) сами колонки под спец-форму не рисуют, а
       вставляют этот компонент вместо quantity/unit/unit_price. -->
  <div class="item-form-fields d-flex flex-wrap ga-2">
    <!-- Проживание: цена — НЕ поле extra_attrs (не в реестре item_forms.json), это
         тот же item.unit_price, что и у обычной позиции (backend/app/services/
         item_amounts.py: «unit_price — цена за номер/человека в сутки, вводится
         пользователем напрямую», НЕ производная, в отличие от transport, где
         unit_price выводится из hourly_rate/trip_cost и своего поля ввода не
         требует). Показываем его тут же, рядом со спец-полями, с формулировкой
         подписи по price_basis — единственное место, где решается эта подпись. -->
    <div v-if="itemForm === 'accommodation'" class="item-form-fields__field">
      <v-text-field
        :model-value="unitPriceDisplay"
        type="number" :label="priceLabel" hide-details="auto"
        density="compact" variant="outlined" style="min-width:150px"
        :disabled="disabled"
        @update:model-value="(v: string) => emit('update:unitPrice', numOrNull(v))"
      />
    </div>
    <template v-for="f in visibleFields" :key="f.key">
      <div class="item-form-fields__field" :class="'item-form-fields__field--' + f.type">
        <!-- switch/select с ровно 2 вариантами — переключатель (владелец: «за номер/
             за человека», «по часам/стоимость рейса»), с пояснением под ним. -->
        <template v-if="(f.type === 'switch' || f.type === 'select') && f.options && f.options.length <= 3">
          <div class="text-caption text-medium-emphasis mb-1">{{ f.label }}</div>
          <v-btn-toggle
            :model-value="valueOf(f)"
            density="compact" mandatory divided variant="outlined" color="primary"
            :disabled="disabled"
            @update:model-value="(v: string) => setValue(f.key, v)"
          >
            <v-btn v-for="opt in f.options" :key="opt.value" :value="opt.value" size="small">{{ opt.label }}</v-btn>
          </v-btn-toggle>
          <div v-if="f.hint" class="text-caption text-medium-emphasis item-form-fields__hint">{{ f.hint }}</div>
        </template>

        <!-- select с произвольным числом вариантов (сейчас не встречается, но реестр
             это допускает — не хардкодить под ровно 2). -->
        <v-select
          v-else-if="f.type === 'select'"
          :model-value="valueOf(f)"
          :items="f.options || []" item-title="label" item-value="value"
          :label="f.label" :hint="f.hint" persistent-hint
          density="compact" variant="outlined" hide-details="auto" style="min-width:180px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, v)"
        />

        <v-text-field
          v-else-if="f.type === 'number'"
          :model-value="numDisplay(f)"
          type="number" :label="f.label" :placeholder="numPlaceholder(f)"
          :hint="f.hint" persistent-hint
          density="compact" variant="outlined" hide-details="auto" style="min-width:130px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, numOrNull(v))"
        />

        <v-text-field
          v-else-if="f.type === 'datetime'"
          :model-value="valueOf(f) ?? ''"
          type="datetime-local" :label="f.label" :hint="f.hint" persistent-hint
          density="compact" variant="outlined" hide-details="auto" style="min-width:200px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, v || null)"
        />

        <v-text-field
          v-else
          :model-value="valueOf(f) ?? ''"
          type="text" :label="f.label" :hint="f.hint" persistent-hint
          density="compact" variant="outlined" hide-details="auto" style="min-width:180px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, v || null)"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ItemFormCode, ItemFormField, ExtraAttrs } from '@/utils/itemAmounts'
import { numOrNull } from '@/utils/numberFormat'

const props = defineProps<{
  itemForm: ItemFormCode | null
  fields: ItemFormField[]
  modelValue: ExtraAttrs | null | undefined
  // Только для accommodation — см. комментарий у поля «Цена» в template выше.
  unitPrice?: number | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ExtraAttrs]
  'update:unitPrice': [value: number | null]
}>()

const unitPriceDisplay = computed(() => props.unitPrice === undefined || props.unitPrice === null ? '' : String(props.unitPrice))
const priceLabel = computed(() => {
  const basis = extra.value.price_basis || 'room'
  return basis === 'person' ? 'Цена за человека, ₽/сутки' : 'Цена за номер, ₽/сутки'
})

const extra = computed<ExtraAttrs>(() => (props.modelValue && typeof props.modelValue === 'object') ? props.modelValue : {})

function valueOf(f: ItemFormField): any {
  const v = extra.value[f.key]
  if (v !== undefined && v !== null && v !== '') return v
  // Переключатели — всегда показывают активный вариант (нужен для mandatory
  // v-btn-toggle), берём default из реестра (item_forms.json).
  if (f.type === 'switch' || f.type === 'select') return f.default ?? f.options?.[0]?.value ?? null
  return null
}

// Числовые поля: пустое значение — ПУСТО, не 0 (владелец: «ноль — тоже значение»).
// Осмысленный ненулевой default (сутки=1, часы подачи=2) показываем ПОДСКАЗКОЙ
// (placeholder), а не подставляем в extra_attrs — формула (utils/itemAmounts.ts,
// зеркало backend/app/services/item_amounts.py) применяет тот же default сама,
// когда поле не заполнено, так что сумма верна и без явной записи в модель.
function numDisplay(f: ItemFormField): string {
  const v = extra.value[f.key]
  return v === undefined || v === null || v === '' ? '' : String(v)
}
function numPlaceholder(f: ItemFormField): string | undefined {
  if (f.default === undefined || f.default === null) return undefined
  return f.default === 0 ? undefined : String(f.default)
}

function setValue(key: string, value: any) {
  emit('update:modelValue', { ...extra.value, [key]: value })
}

// Проживание: показываем ТОЛЬКО активную по price_basis количественную колонку
// (номера ИЛИ люди) — вторую прятать, чтобы не путать, какая из двух считается
// (см. formula в item_forms.json / utils/itemAmounts.ts::accommodationQuantity).
// Перевозки: аналогично по cost_mode — «по часам» vs «стоимость рейса». Это
// чисто отображение (какие поля видны), сама формула не дублируется — она
// живёт только в utils/itemAmounts.ts.
const visibleFields = computed<ItemFormField[]>(() => {
  const ex = extra.value
  return props.fields.filter(f => {
    if (props.itemForm === 'accommodation') {
      if (f.key === 'rooms') return (ex.price_basis || 'room') !== 'person'
      if (f.key === 'persons') return (ex.price_basis || 'room') === 'person'
    }
    if (props.itemForm === 'transport') {
      if (f.key === 'work_hours' || f.key === 'supply_hours' || f.key === 'hourly_rate') {
        return (ex.cost_mode || 'hours') !== 'trip'
      }
      if (f.key === 'trip_cost') return (ex.cost_mode || 'hours') === 'trip'
    }
    return true
  })
})
</script>

<style scoped>
.item-form-fields__field {
  display: flex;
  flex-direction: column;
}
.item-form-fields__hint {
  max-width: 220px;
  line-height: 1.3;
}
</style>
