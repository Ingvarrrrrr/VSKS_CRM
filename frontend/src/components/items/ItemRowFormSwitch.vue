<template>
  <!-- «Проживание и питание» (решение владельца) — ПРАВИЛО №5/№6: единственное
       место, рендерящее переключатель формы СТРОКИ + поля формы по эффективной
       форме этой строки. Используется во ВСЕХ 4 таблицах позиций (Flat/Stages/
       Wish/ItemsCardsView) вместо четырёх копий одной и той же разметки.
       rowItemFormChoices пуст/не передан — ведёт себя как раньше: просто
       ItemFormFields по единому itemForm (переключатель не рендерится). -->
  <div class="item-row-form-switch">
    <v-btn-toggle
      v-if="rowItemFormChoices && rowItemFormChoices.length"
      :model-value="effectiveForm"
      density="compact" variant="outlined" mandatory class="mb-1"
      :disabled="disabled"
      @update:model-value="(v: string) => emit('update:row-form', v as ItemFormCode)"
    >
      <v-btn v-for="choice in rowItemFormChoices" :key="choice" :value="choice" size="x-small">
        {{ labelFor(choice) }}
      </v-btn>
    </v-btn-toggle>
    <ItemFormFields
      :item-form="effectiveForm"
      :fields="effectiveFields"
      :model-value="modelValue"
      :unit-price="unitPrice"
      :total-price="totalPrice"
      :disabled="disabled"
      @update:model-value="(v) => emit('update:model-value', v)"
      @update:unit-price="(v) => emit('update:unit-price', v)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ItemFormFields from '@/components/items/ItemFormFields.vue'
import { itemFormDescriptor } from '@/composables/items/useItemForm'
import type { ItemFormCode, ItemFormField, ExtraAttrs } from '@/utils/itemAmounts'

const props = defineProps<{
  // «Проживание и питание»: допустимые формы СТРОКИ — непусто только для
  // contract_form из CONTRACT_FORM_ROW_CHOICES (item_forms.py). Пусто/не
  // передан — старое поведение, единый itemForm на всю закупку/заявку.
  rowItemFormChoices?: ItemFormCode[] | null
  // Единый itemForm (когда rowItemFormChoices пуст) — как раньше.
  itemForm?: ItemFormCode | null
  // item.item_form строки (raw, может быть null/не входить в choices — тогда
  // эффективная форма — первая из rowItemFormChoices, см. item_forms.py::
  // item_form_for_row, зеркало здесь).
  rowForm?: string | null
  // Поля формы для единого itemForm-случая (rowItemFormChoices пуст) — при
  // row-choices фронт сам берёт fields по effectiveForm из item_forms.json.
  fields?: ItemFormField[]
  modelValue?: ExtraAttrs | null
  unitPrice?: number | string | null
  totalPrice?: number | string | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:row-form': [value: ItemFormCode]
  'update:model-value': [value: ExtraAttrs]
  'update:unit-price': [value: number | null]
}>()

const effectiveForm = computed<ItemFormCode | null>(() => {
  const choices = props.rowItemFormChoices
  if (choices && choices.length) {
    return (props.rowForm && (choices as string[]).includes(props.rowForm)) ? (props.rowForm as ItemFormCode) : choices[0]
  }
  return props.itemForm ?? null
})

const effectiveFields = computed<ItemFormField[]>(() => {
  if (props.rowItemFormChoices && props.rowItemFormChoices.length) {
    return itemFormDescriptor(effectiveForm.value)?.fields ?? []
  }
  return props.fields ?? []
})

function labelFor(form: ItemFormCode): string {
  return itemFormDescriptor(form)?.label ?? form
}
</script>
