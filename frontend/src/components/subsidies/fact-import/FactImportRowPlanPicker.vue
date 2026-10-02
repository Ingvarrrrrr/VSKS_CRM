<template>
  <v-dialog v-model="model" max-width="900">
    <v-card>
      <v-card-title class="text-h6">Выбрать плановую позицию — строка {{ row?.row }}</v-card-title>
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-2">{{ row?.name }}</div>
        <FeoPlannedItemsSelect
          v-if="row"
          :model-value="selection"
          :category-id="null"
          :nodes="feoNodes"
          :items="plannedResiduals"
          :subsidy-id="subsidyId"
          @update:model-value="onSelect"
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
// Пикер плановой позиции для строк со статусом сопоставления
// ambiguous/not_found (Шаг 3 мастера «Импорт факта») — переиспользует
// FeoPlannedItemsSelect.vue целиком (ПРАВИЛО №6), а не копирует поиск по
// дереву ФЭО. nodes/items грузятся ОДИН раз на весь мастер (не на строку) —
// те же composables, что питают дерево ФЭО (useFeoLeaves/
// useFeoPlannedResiduals), subsidyId включает поиск по всей субсидии внутри
// компонента (см. его проп subsidyId).
//
// ⚠️ Замечание для бэкенда (не ломает контракт, но сужает то, что он может
// значить): FeoPlannedItemsSelect эмитит составной {kind,id} (id — то id
// FeoCategory, то id FeoPlannedItem, в разных пространствах — см. докстринг
// FeoPlanSelection). Контракт decisions.row_overrides.planned_item_id — один
// плоский id. Сюда уходит именно selection.id, без kind — предполагается,
// что бэкенд импорта факта резолвит его как id FeoPlannedItem (см.
// match.candidates[].planned_item_id в контракте предпросмотра, тоже плоский
// id). Если это не так — единственное место, которое нужно поправить.
import { computed, ref, watch } from 'vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoPlannedResiduals, type FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { useFactImport, type FactImportRow } from '@/composables/subsidies/useFactImport'

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
const { feoNodes } = useFeoLeaves({ subsidyId: subsidyIdRef })
const { plannedResiduals } = useFeoPlannedResiduals({ subsidyId: subsidyIdRef })

const { setRowPlannedItem, setRowSkip } = useFactImport()

const selection = ref<FeoPlanSelection | null>(null)
watch(() => props.row, (r) => {
  const id = r?.match?.planned_item_id ?? null
  selection.value = id != null ? { kind: 'planned_item', id } : null
})

function onSelect(sel: FeoPlanSelection | null) {
  selection.value = sel
  if (props.row) setRowPlannedItem(props.row.row, sel?.id ?? null, false)
}

function skipRow() {
  if (props.row) setRowSkip(props.row.row, true)
  model.value = false
}
</script>
