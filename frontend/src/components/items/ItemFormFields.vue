<template>
  <!-- item-forms-accommodation-transport.md, шаг 3: рендерит спец-поля позиции
       («Проживание»/«Перевозки автобусом») по описанию из item_forms.json —
       ЕДИНСТВЕННЫЙ рендерер этих полей (Правило №6), таблицы (ItemsTableFlat/
       Stages/Wish/ItemsCardsView) сами колонки под спец-форму не рисуют, а
       вставляют этот компонент вместо quantity/unit/unit_price.

       food-menu-editor.md (владелец, 2026-09-15, «даже мне не читаемо»):
       «Питание» больше не идёт через generic-рендер полей ниже — это ЕДИНАЯ
       широкая панель (переключатель режима + Человек/Дней в одну строку,
       затем либо однострочная формула, либо таблица меню), собранная
       отдельным блоком template ниже. Панель встраивает вызывающая сторона
       (PurchaseItemsEditor.vue) на всю ширину, СКРЫВ соседние колонки
       Наименование/Тип/Страна/каталог — владелец: «поле Наименование явно
       лишнее» для формы питания, позиция всего одна и называется
       автоматически. -->
  <div class="item-form-fields d-flex flex-wrap ga-2">
    <!-- Проживание (владелец, п. С4, 30.09: «указывается количество номеров,
         количество человек — огромная цифра будет с маленькой, странно так
         разбито, непонятно») — одна ровная строка-формула одинаковой ширины
         полей, тот же приём, что и у food-panel__simple-line ниже (единый
         bespoke-блок на форму, generic-цикл для accommodation теперь пуст —
         см. visibleFields). Цена — НЕ поле extra_attrs (не в реестре
         item_forms.json), это тот же item.unit_price, что и у обычной позиции
         (backend/app/services/item_amounts.py: «unit_price — цена за номер/
         человека в сутки»), НЕ производная, в отличие от transport (unit_price
         из hourly_rate/trip_cost) и food/меню (unit_price = итог/quantity). -->
    <div v-if="itemForm === 'accommodation'" class="accommodation-panel">
      <div class="d-flex align-center flex-wrap ga-2 mb-2">
        <v-text-field
          :model-value="valueOf(roomCategoryField)"
          type="text" label="Категория номера" hide-details="auto"
          density="compact" variant="outlined" style="min-width:220px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue('room_category', v || null)"
        />
        <div>
          <div class="text-caption text-medium-emphasis mb-1">Цена указана за</div>
          <v-btn-toggle
            :model-value="priceBasis" density="compact" mandatory divided variant="outlined" color="primary"
            :disabled="disabled"
            @update:model-value="(v: string) => setValue('price_basis', v)"
          >
            <v-btn value="room" size="small">Номер</v-btn>
            <v-btn value="person" size="small">Человека</v-btn>
          </v-btn-toggle>
        </div>
      </div>
      <!-- Формула — одна ровная строка, поля одинаковой ширины, подпись каждого
           поля называет и смысл, и единицу (владелец: «непонятно, какая цифра
           что значит» — тот же урок, что уже применён к food-panel ниже). -->
      <div class="d-flex align-center flex-wrap ga-2 accommodation-panel__formula">
        <v-text-field
          :model-value="numDisplay(accommodationQtyField)" type="number"
          :label="accommodationQtyLabel" :placeholder="numPlaceholder(accommodationQtyField)"
          density="compact" variant="outlined" hide-details="auto" style="width:140px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(accommodationQtyField.key, numOrNull(v))"
        />
        <span class="text-body-1">×</span>
        <v-text-field
          :model-value="numDisplay(nightsField)" type="number"
          label="Суток" :placeholder="numPlaceholder(nightsField)"
          density="compact" variant="outlined" hide-details="auto" style="width:140px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue('nights', numOrNull(v))"
        />
        <span class="text-body-1">×</span>
        <v-text-field
          :model-value="unitPriceDisplay" type="number"
          :label="priceLabel" hide-details="auto"
          density="compact" variant="outlined" style="width:140px"
          :disabled="disabled"
          @update:model-value="(v: string) => emit('update:unitPrice', numOrNull(v))"
        />
        <span class="text-h6 ml-1">= {{ fmtMoney(accommodationTotal) }} ₽</span>
      </div>
    </div>

    <!-- food-menu-editor.md: широкая панель питания — переключатель режима,
         Человек/Дней в одну строку, тело по режиму. -->
    <div v-if="itemForm === 'food'" class="food-panel">
      <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-2">
        <v-btn-toggle
          :model-value="foodMode" density="compact" mandatory divided variant="outlined" color="primary"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue('mode', v)"
        >
          <v-btn value="simple" size="small">Просто</v-btn>
          <v-btn value="menu" size="small">Меню по дням</v-btn>
        </v-btn-toggle>
        <div class="d-flex ga-2">
          <v-text-field
            :model-value="numDisplay(personsField)" type="number" label="Человек" :placeholder="numPlaceholder(personsField)"
            density="compact" variant="outlined" hide-details style="max-width:110px"
            :disabled="disabled"
            @update:model-value="(v: string) => setValue('persons', numOrNull(v))"
          />
          <v-text-field
            :model-value="numDisplay(daysField)" type="number" label="Дней" :placeholder="numPlaceholder(daysField)"
            density="compact" variant="outlined" hide-details style="max-width:100px"
            :disabled="disabled"
            @update:model-value="(v: string) => setValue('days', numOrNull(v))"
          />
        </div>
      </div>

      <!-- Режим «Просто»: одна строка-формула, крупно. -->
      <div v-if="foodMode !== 'menu'" class="food-panel__simple-line d-flex align-center flex-wrap ga-2">
        <span class="text-body-1">{{ personsDisplay }} чел ×</span>
        <!-- Было безликое число с подсказкой только в title (её не видно без
             наведения) и абревиатурой «приём/дн ×» ПОСЛЕ поля — владелец читал
             формулу как «Человек × Приёмов в день × Дней» и не мог понять, какое
             из двух соседних чисел что значит (жалоба С3, 30.09). Явный label на
             самом поле — тот же приём, что и у «₽/приём» ниже, каждое поле
             называется тем, что реально хранит (quantity = persons × meals_per_day ×
             days, см. utils/itemAmounts.ts::foodQuantity — формула не менялась,
             менялась только подпись). -->
        <v-text-field
          :model-value="numDisplay(mealsField)" type="number" label="Приёмов в день" :placeholder="numPlaceholder(mealsField)"
          density="compact" variant="outlined" hide-details style="max-width:150px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue('meals_per_day', numOrNull(v))"
        />
        <!-- Дней — то же число, что в поле «Дней» наверху панели (daysField),
             здесь только показывается (правится там же, чтобы не завести два
             способа ввести одно и то же, Правило №6); слово не сокращаем —
             раньше «дн» рядом с «приём/дн» читалось как два варианта одного
             сокращения. -->
        <span class="text-body-1">× {{ daysDisplay }} дней ×</span>
        <v-text-field
          :model-value="unitPriceDisplay" type="number" label="₽/приём"
          density="compact" variant="outlined" hide-details style="max-width:130px"
          :disabled="disabled"
          @update:model-value="(v: string) => emit('update:unitPrice', numOrNull(v))"
        />
        <span class="text-h6 ml-1">= {{ fmtMoney(totalPrice) }} ₽</span>
      </div>

      <!-- Режим «Меню по дням»: таблица (см. food-menu-editor.md). -->
      <FoodMenuEditor
        v-else
        :model-value="extra.menu"
        :days="extra.days"
        :persons="extra.persons"
        :disabled="disabled"
        @update:model-value="(v) => setValue('menu', v)"
      />
    </div>

    <template v-for="f in visibleFields" :key="f.key">
      <div class="item-form-fields__field" :class="'item-form-fields__field--' + f.type">
        <!-- Перевозки/авиа/ж.д. (владелец, п. С4, 30.09: «дата отправления
             позже даты окончания — так быть не может») — стрелка-указатель к
             полю ВТОРОЙ даты (finish_at/date_back), тот же hv-pointer-приём,
             что и остальные валидационные стрелки в проекте (PointerArrow.vue,
             Lessons.md: «ошибки ведут стрелкой, не просто подсветкой»).
             Проверка — ОДНА функция validateItemFormDates (utils/itemAmounts.ts,
             зеркало backend services/item_form_dates.py), не дублируется здесь. -->
        <PointerArrow
          v-if="dateErrorFieldKey === f.key"
          direction="up" current :title="dateOrderError || ''"
          class="item-form-fields__date-arrow"
        />
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
          :error="dateErrorFieldKey === f.key" :error-messages="dateErrorFieldKey === f.key ? [dateOrderError || ''] : []"
          density="compact" variant="outlined" hide-details="auto" style="min-width:200px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, v || null)"
        />

        <!-- Авиа/ж.д. билеты: дата без времени (date_to/date_back). -->
        <v-text-field
          v-else-if="f.type === 'date'"
          :model-value="valueOf(f) ?? ''"
          type="date" :label="f.label" :hint="f.hint" persistent-hint
          :error="dateErrorFieldKey === f.key" :error-messages="dateErrorFieldKey === f.key ? [dateOrderError || ''] : []"
          density="compact" variant="outlined" hide-details="auto" style="min-width:160px"
          :disabled="disabled"
          @update:model-value="(v: string) => setValue(f.key, v || null)"
        />

        <v-text-field
          v-else-if="f.type !== 'custom'"
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
import { computeItemTotal, validateItemFormDates } from '@/utils/itemAmounts'
import { numOrNull } from '@/utils/numberFormat'
import FoodMenuEditor from './FoodMenuEditor.vue'
import PointerArrow from '@/components/common/PointerArrow.vue'

const props = defineProps<{
  itemForm: ItemFormCode | null
  fields: ItemFormField[]
  modelValue: ExtraAttrs | null | undefined
  // Только для accommodation/food-«просто» — см. комментарий у поля «Цена» выше.
  unitPrice?: number | null
  // food-menu-editor.md: итог позиции (item.total_price) — только для отображения
  // «= Итого» в однострочной формуле режима «Просто»; сам расчёт остаётся в
  // utils/itemAmounts.ts::applyItemAmounts (Правило №6), сюда просто прокидывается.
  totalPrice?: number | null
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

// Проживание (п. С4): bespoke-строка формулы — field-объекты описания берём
// из реестра (props.fields, тот же приём, что у food-панели ниже, Правило
// №6 — подписи/дефолты не дублируем).
const roomCategoryField = computed(() => fieldByKey('room_category'))
const nightsField = computed(() => fieldByKey('nights'))
const priceBasis = computed(() => extra.value.price_basis || 'room')
// Активная количественная колонка — номера ИЛИ люди, по переключателю
// price_basis (зеркало utils/itemAmounts.ts::accommodationQuantity).
const accommodationQtyField = computed(() => fieldByKey(priceBasis.value === 'person' ? 'persons' : 'rooms'))
const accommodationQtyLabel = computed(() => priceBasis.value === 'person' ? 'Человек, чел.' : 'Номеров, шт.')
// Итог строки — превью той же формулы, что считает бэк при сохранении
// (compute_item_total), единственная формула, вызываемая, не дублируется
// здесь (computeItemTotal — общий helper utils/itemAmounts.ts).
const accommodationTotal = computed(() => computeItemTotal(extra.value, 'accommodation', null, props.unitPrice))

// Перевозки/авиа/ж.д. (п. С4, 30.09): «отправление позже окончания — так
// быть не может» — ОДНА проверка на оба вида транспорта (validateItemFormDates,
// зеркало backend services/item_form_dates.py::validate_item_form_dates,
// см. её докстринг — вызывается там же на сохранении, здесь только
// превью-отображение). dateErrorFieldKey — какое поле подсвечивать стрелкой
// (вторая дата — finish_at у transport, date_back у flight/train).
const dateOrderError = computed(() => validateItemFormDates(extra.value, props.itemForm))
const dateErrorFieldKey = computed<string | null>(() => {
  if (!dateOrderError.value) return null
  if (props.itemForm === 'transport') return 'finish_at'
  if (props.itemForm === 'flight' || props.itemForm === 'train') return 'date_back'
  return null
})

const extra = computed<ExtraAttrs>(() => (props.modelValue && typeof props.modelValue === 'object') ? props.modelValue : {})
// Питание: режим ввода ('simple'|'menu') — переключает видимость полей и
// заодно решает, показывать ли общую цену за приём (см. блок «Цена» выше).
const foodMode = computed(() => extra.value.mode || 'simple')

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function fmtMoney(v: number | null | undefined): string {
  return toNum(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// food-панель: находим описания полей persons/meals_per_day/days из реестра
// (item_forms.json, тот же props.fields) — подписи/дефолты не дублируем
// (Правило №6), просто переиспользуем те же field-объекты в bespoke-разметке.
function fieldByKey(key: string): ItemFormField {
  return props.fields.find(f => f.key === key) ?? { key, label: key, type: 'number' }
}
const personsField = computed(() => fieldByKey('persons'))
const mealsField = computed(() => fieldByKey('meals_per_day'))
const daysField = computed(() => fieldByKey('days'))
const personsDisplay = computed(() => numDisplay(personsField.value) || '0')
const daysDisplay = computed(() => numDisplay(daysField.value) || '1')

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

// Проживание (п. С4, 30.09): bespoke-строка формулы выше рендерит ВСЕ поля
// формы (room_category/price_basis/rooms-или-persons/nights/цена) сама — тот
// же приём, что у food-панели (generic-цикл для accommodation теперь пуст,
// второго рендерера этих полей не заводим, Правило №6).
// Перевозки: показываем активные по cost_mode поля — «по часам» vs
// «стоимость рейса». Это чисто отображение (какие поля видны), сама формула
// не дублируется — она живёт только в utils/itemAmounts.ts.
// Питание: bespoke-панель выше рендерит ВСЕ поля формы (mode/persons/
// meals_per_day/days/menu) сама — generic-цикл ниже для food всегда пуст,
// второго рендерера тех же полей не заводим (Правило №6).
const visibleFields = computed<ItemFormField[]>(() => {
  if (props.itemForm === 'food' || props.itemForm === 'accommodation') return []
  const ex = extra.value
  return props.fields.filter(f => {
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
/* food-menu-editor.md: редактор меню по дням — на всю ширину контейнера
   (day-панели с несколькими полями на строку не помещаются в узкую колонку
   рядом с остальными полями формы). */
.item-form-fields__field--custom {
  flex-basis: 100%;
  width: 100%;
}
/* food-menu-editor.md: широкая панель питания — занимает всю ширину строки
   родительского flex-wrap контейнера (тот же приём, что и у
   .item-form-fields__field--custom выше), который ей выделяет вызывающая
   сторона (PurchaseItemsEditor.vue рендерит её вместо всего ряда таблицы для
   формы «Питание»). */
.food-panel {
  flex-basis: 100%;
  width: 100%;
}
.food-panel__simple-line {
  font-size: 15px;
}
/* Проживание (п. С4, 30.09): bespoke-строка формулы — та же ширина строки,
   что и у food-panel выше. */
.accommodation-panel {
  flex-basis: 100%;
  width: 100%;
}
.accommodation-panel__formula {
  font-size: 15px;
}
/* Валидационная стрелка у второй даты (finish_at/date_back) — рядом с полем,
   не абсолютным позиционированием (поле лежит в обычном flex-потоке формы,
   не на холсте графа, как у исходного .hv-pointer). */
.item-form-fields__date-arrow {
  margin-bottom: 20px;
}
</style>
