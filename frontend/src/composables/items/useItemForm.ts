// item-forms-accommodation-transport.md, шаг 3: из формы договора закупки
// (Purchase.contract_form) выводит itemForm ('accommodation'|'transport'|null)
// и описание спец-полей — ЕДИНСТВЕННЫЙ источник: сгенерированный
// frontend/src/data/item_forms.json (тот же файл, что и bэкенд-реестр
// backend/app/services/item_forms.py, экспортируется export_dictionaries.py,
// см. README в data/, Правило №6). Без второго источника подписей: рантайм-
// фолбэк на GET /api/dictionaries/item-forms сознательно НЕ заведён — json
// генерируется и проверяется в CI (`export_dictionaries.py --check`), тем же
// способом, что dictionaries.json уже используется в constants/purchaseStatus.ts
// и constants/permissionActions.ts (там тоже нет рантайм-фетча).
import { computed, type ComputedRef, type Ref } from 'vue'
import itemFormsData from '@/data/item_forms.json'
import type { ItemFormCode, ItemFormDescriptor, ItemFormField } from '@/utils/itemAmounts'

interface ItemFormsJson {
  item_forms: Record<string, ItemFormDescriptor>
  contract_forms: { key: string; label: string; order: number }[]
  contract_form_to_item_form: Record<string, ItemFormCode>
}

const DATA = itemFormsData as unknown as ItemFormsJson

const CONTRACT_FORM_TO_ITEM_FORM: Record<string, ItemFormCode> = DATA.contract_form_to_item_form || {}
const ITEM_FORMS: Record<string, ItemFormDescriptor> = DATA.item_forms || {}

/** Purchase.contract_form → код формы позиций (null = обычная позиция). */
export function itemFormForContractForm(contractForm: string | null | undefined): ItemFormCode | null {
  if (!contractForm) return null
  return CONTRACT_FORM_TO_ITEM_FORM[contractForm] ?? null
}

export function itemFormDescriptor(itemForm: ItemFormCode | null | undefined): ItemFormDescriptor | null {
  if (!itemForm) return null
  return ITEM_FORMS[itemForm] ?? null
}

/** Варианты формы договора для CreateOrderView.vue::contractFormOptions — та же
 * генерируемая таблица (contract_forms), что описывает соответствие форме
 * позиций. Единый источник подписей — CONTRACT_FORM_LABELS на бэке
 * (services/dictionaries.py), сюда попадает через item_forms.json. */
export function contractFormOptions(): { value: string; title: string }[] {
  const list = DATA.contract_forms || []
  return [...list].sort((a, b) => a.order - b.order).map(c => ({ value: c.key, title: c.label }))
}

export interface UseItemFormResult {
  itemForm: ComputedRef<ItemFormCode | null>
  descriptor: ComputedRef<ItemFormDescriptor | null>
  fields: ComputedRef<ItemFormField[]>
}

/** contractForm — реактивный источник (Purchase.contract_form закупки; для
 * заявок/wish — всегда null, у Wish нет contract_form, см. план «Модель»). */
export function useItemForm(contractForm: Ref<string | null | undefined> | ComputedRef<string | null | undefined>): UseItemFormResult {
  const itemForm = computed<ItemFormCode | null>(() => itemFormForContractForm(contractForm.value))
  const descriptor = computed<ItemFormDescriptor | null>(() => itemFormDescriptor(itemForm.value))
  const fields = computed<ItemFormField[]>(() => descriptor.value?.fields ?? [])
  return { itemForm, descriptor, fields }
}
