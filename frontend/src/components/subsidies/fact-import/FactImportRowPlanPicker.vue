<template>
  <v-dialog v-model="model" max-width="900">
    <v-card>
      <v-card-title class="text-h6">Выбрать плановую позицию — строка {{ row?.row }}</v-card-title>
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-2">{{ row?.name }}</div>

        <div v-if="currentName" class="text-body-2 mb-3">
          Сейчас: <strong>{{ currentName }}</strong>
          <span v-if="currentAmount != null" class="text-medium-emphasis"> ({{ formatMoney(currentAmount) }})</span>
          <!-- Часть объединённой позиции (план merged-item-parts.md) -->
          <span v-if="row?.match.plan_parts?.length">
            <span v-if="currentPartRow" class="text-purple"> · часть: стр. {{ currentPartRow }}</span>
            <span v-else class="text-warning"> · часть не выбрана — выберите ниже</span>
          </span>
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

        <div class="text-caption text-medium-emphasis mb-1">План субсидии:</div>
        <FeoPlanTreePicker
          v-if="subsidyId && row"
          :subsidy-id="subsidyId"
          :planned-items="plannedItemRows"
          :row-path="row.path"
          :candidate-ids="candidateIds"
          :open="model"
          @select="onTreeSelect"
        />
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
// 🟡 Решение владельца (прод, субсидия «ДНР», строка 151 «Проезд, проживание,
// питание», скриншоты): плоский поиск FeoPlannedSearchBox (/feo-planned-items/
// match) путал — точное имя строки находило «бинты/перчатки» (серверный
// fuzzy-скоринг), а запрос без совпадений («преддрейсовых») тихо подменялся
// ВСЕМ планом без предупреждения. Заменено на FeoPlanTreePicker.vue — дерево
// Направление›Тип›Подкатегория (тот же источник узлов, что «План закупок»),
// с ДЕТЕРМИНИРОВАННЫМ клиентским поиском (все слова запроса — подстроки
// нормализованного имени, без фаззи-скоринга бэкенда) и явным «ничего не
// найдено» без подмены. FeoPlannedSearchBox.vue/useFeoPlannedSearch.ts НЕ
// тронуты — используются как раньше в FeoPlannedItemsSelect.vue (ПРАВИЛО №6:
// это не второй механизм ВМЕСТО старого, а замена инструмента ИМЕННО в этом
// диалоге, старый остаётся работать там, где работал).
//
// История (2-я приёмка 07.10.2026, «ничего вводить не могу»): раньше здесь
// стоял FeoPlannedItemsSelect целиком с :category-id="null" — но тот рендерит
// содержимое только при categoryId != null, был пуст с момента создания
// пикера.
import { computed } from 'vue'
import FeoPlanTreePicker from './FeoPlanTreePicker.vue'
import { useFeoPlannedResiduals, type FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import { useFactImport, type FactImportRow } from '@/composables/subsidies/useFactImport'
// Часть объединённой позиции (план merged-item-parts.md) — показана тут же,
// не отдельным диалогом (ПРАВИЛО №6: один пикер решает и позицию, и часть).
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

const { setRowPlannedItem, setRowSkip } = useFactImport()

// Бэкенд принимает в decisions.row_overrides.planned_item_id ТОЛЬКО id
// FeoPlannedItem (kind='planned_item'): matching.py::build_matching_context
// строит catalog/by_name/candidates ИСКЛЮЧИТЕЛЬНО из записей kind=
// 'planned_item' (остальные kind туда не попадают), а commit.py пишет id
// НАПРЯМУЮ в purchase_items.feo_planned_item_id (commit.py:295) без всякого
// резолва. У 'plan_position'/'feo_article' id — это id FeoCategory, в ДРУГОМ
// пространстве идентификаторов — отправить такой id как planned_item_id
// значило бы привязать закупку к чужой сущности под чужим числом. Дерево
// (FeoPlanTreePicker) и так показывает «plan_position»/«feo_article» только
// как категории-папки (не кликабельны для выбора), а кликабельные листья —
// только planned_item, но на входе фильтруем явно, belt-and-braces.
const plannedItemRows = computed<FeoPlanPosition[]>(() => plannedResiduals.value.filter(r => r.kind === 'planned_item'))

const candidateIds = computed<number[]>(() => props.row?.match.candidates?.map(c => c.id) ?? [])

const currentName = computed(() => props.row?.match?.planned_item_name ?? null)
const currentAmount = computed(() => props.row?.match?.planned_item_amount ?? null)
const currentPartRow = computed(() => {
  const key = props.row?.match?.plan_part_key
  if (!key) return null
  return props.row?.match?.plan_parts?.find(p => p.key === key)?.row ?? null
})

function selectPlannedItem(id: number, planPartKey: string | null = null) {
  if (!props.row) return
  setRowPlannedItem(props.row.row, id, false, planPartKey)
  model.value = false
}

function onTreeSelect(item: FeoPlanPosition, partKey: string | null) {
  selectPlannedItem(item.id, partKey)
}

function skipRow() {
  if (props.row) setRowSkip(props.row.row, true)
  model.value = false
}
</script>
