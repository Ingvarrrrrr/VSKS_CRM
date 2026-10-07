<template>
  <v-dialog v-model="model" max-width="900">
    <v-card>
      <v-card-title class="text-h6">Выбрать плановую позицию — строка {{ row?.row }}</v-card-title>
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-2">{{ row?.name }}</div>

        <div v-if="currentName" class="text-body-2 mb-3">
          Сейчас: <strong>{{ currentName }}</strong>
          <span v-if="currentAmount != null" class="text-medium-emphasis"> ({{ formatMoney(currentAmount) }})</span>
        </div>

        <div v-if="row?.match.candidates?.length" class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Похожие по имени:</div>
          <div class="d-flex flex-column ga-1">
            <v-btn v-for="c in row.match.candidates.slice(0, 5)" :key="c.id" size="small" variant="outlined"
              @click="selectPlannedItem(c.id)">
              {{ c.name }} ({{ formatMoney(c.amount) }})
            </v-btn>
          </div>
        </div>

        <div class="text-caption text-medium-emphasis mb-1">Поиск по всей субсидии:</div>
        <FeoPlannedSearchBox
          v-if="subsidyId"
          v-model:search-text="search.searchText.value"
          :rows="selectableRows"
          :loading="search.searchLoading.value"
          :fmt="formatMoney"
          @select="onSearchSelect"
        />
        <div v-if="hiddenCount > 0" class="text-caption text-medium-emphasis mt-1">
          Скрыто ещё {{ hiddenCount }}: статья ФЭО без детализации до плановой позиции — выбрать нельзя.
        </div>
      </v-card-text>
      <v-card-actions>
        <v-btn variant="text" color="warning" @click="skipRow">Пропустить строку</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="model = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Пикер плановой позиции для шага 3 мастера «Импорт факта» — используется
// И на ambiguous/not_found, И (чек-лист 07.10.2026, п.3) на found/
// already_purchased через кнопку «Изменить…».
//
// Дефект (владелец, 2-я приёмка 07.10.2026, «ничего вводить не могу» —
// главная жалоба): раньше здесь стоял FeoPlannedItemsSelect целиком с
// :category-id="null" — но FeoPlannedItemsSelect.vue:13 рендерит ВСЁ своё
// содержимое (поиск, дерево, список) только при `v-if="categoryId != null"`.
// С null компонент был пуст с момента создания пикера — ни поля поиска, ни
// списка не было видно НИ РАЗУ. Строка импорта факта категорию не выбирает
// (ищет по всей субсидии сразу), поэтому весь FeoPlannedItemsSelect — не тот
// инструмент; переиспользован его внутренний блок поиска по субсидии
// напрямую: FeoPlannedSearchBox.vue + useFeoPlannedSearch.ts (ПРАВИЛО №6 —
// тот же движок/эндпоинт /feo-planned-items/match, второй поиск не пишем).
import { computed, watch } from 'vue'
import FeoPlannedSearchBox from '@/components/items/feo-planned/FeoPlannedSearchBox.vue'
import { useFeoPlannedSearch, type FeoPlannedSearchRow } from '@/composables/items/feoPlanned/useFeoPlannedSearch'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import { useFactImport, type FactImportRow } from '@/composables/subsidies/useFactImport'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{
  modelValue: boolean
  row: FactImportRow | null
  subsidyId: number | null
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const model = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const subsidyIdRef = computed(() => props.subsidyId)
const { plannedResiduals } = useFeoPlannedResiduals({ subsidyId: subsidyIdRef })

// Геттеры вместо обычных полей — useFeoPlannedSearch читает props.items/
// props.subsidyId ВНУТРИ computed/watch (та же схема, что и в
// FeoPlannedItemsSelect.vue, где туда передаётся реактивный defineProps()
// целиком); геттеры дают то же самое без второго компонента-обёртки.
const searchProps = {
  get items() { return plannedResiduals.value },
  get categoryId() { return null as number | null },
  get subsidyId() { return subsidyIdRef.value },
}
const search = useFeoPlannedSearch({ props: searchProps })

const { setRowPlannedItem, setRowSkip } = useFactImport()

// Бэкенд принимает в decisions.row_overrides.planned_item_id ТОЛЬКО id
// FeoPlannedItem (kind='planned_item'): matching.py::build_matching_context
// строит catalog/by_name/candidates ИСКЛЮЧИТЕЛЬНО из записей kind=
// 'planned_item' (остальные kind туда не попадают), а commit.py пишет id
// НАПРЯМУЮ в purchase_items.feo_planned_item_id (commit.py:295) без всякого
// резолва. Общий поиск по субсидии (/feo-planned-items/match, тот же, что
// питает это поле) умеет отдавать ещё 'plan_position'/'feo_article' —
// статью/категорию ФЭО с планом, но БЕЗ детализации до FeoPlannedItem, где
// id — это id FeoCategory, в ДРУГОМ пространстве идентификаторов. Отправить
// такой id как planned_item_id значило бы привязать закупку к чужой сущности
// под чужим числом — такие строки отфильтрованы из выдачи (не исключение
// бэкенда, который их примет как есть, а именно фронтовая защита от
// подмены id).
const selectableRows = computed(() => search.searchRows.value.filter(r => r.kind === 'planned_item'))
const hiddenCount = computed(() => search.searchRows.value.length - selectableRows.value.length)

const currentName = computed(() => props.row?.match?.planned_item_name ?? null)
const currentAmount = computed(() => props.row?.match?.planned_item_amount ?? null)

// Открытие диалога — поле поиска сразу предзаполнено именем строки файла
// (чек-лист 07.10.2026, п.1: «варианты должны появиться сразу»), человек
// может стереть и искать своё. Закрытие — очистка, чтобы следующее открытие
// на ДРУГОЙ строке не унаследовало чужой текст/результаты.
watch(() => props.modelValue, (open) => {
  if (open && props.row) {
    search.searchText.value = props.row.name
  } else {
    search.clearSearch()
  }
})

function selectPlannedItem(id: number) {
  if (!props.row) return
  setRowPlannedItem(props.row.row, id, false)
  model.value = false
}

function onSearchSelect(row: FeoPlannedSearchRow) {
  selectPlannedItem(row.id)
}

function skipRow() {
  if (props.row) setRowSkip(props.row.row, true)
  model.value = false
}
</script>
