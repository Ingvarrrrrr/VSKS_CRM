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
  contract_form_row_choices: Record<string, ItemFormCode[]>
}

const DATA = itemFormsData as unknown as ItemFormsJson

const CONTRACT_FORM_TO_ITEM_FORM: Record<string, ItemFormCode> = DATA.contract_form_to_item_form || {}
const CONTRACT_FORM_ROW_CHOICES: Record<string, ItemFormCode[]> = DATA.contract_form_row_choices || {}
const ITEM_FORMS: Record<string, ItemFormDescriptor> = DATA.item_forms || {}

/** Purchase.contract_form → код формы позиций (null = обычная позиция). Не
 * годится для contract_form из CONTRACT_FORM_ROW_CHOICES («Проживание и
 * питание») — там форма не одна на весь договор, см. itemFormForRow ниже. */
export function itemFormForContractForm(contractForm: string | null | undefined): ItemFormCode | null {
  if (!contractForm) return null
  return CONTRACT_FORM_TO_ITEM_FORM[contractForm] ?? null
}

/** contract_form, допускающие ВЫБОР формы НА СТРОКЕ («Проживание и питание») —
 * список допустимых item_form строки (первый — дефолт для новой строки), или
 * null, если у этого contract_form форма одна на весь договор/её нет вовсе. */
export function contractFormRowChoices(contractForm: string | null | undefined): ItemFormCode[] | null {
  if (!contractForm) return null
  return CONTRACT_FORM_ROW_CHOICES[contractForm] ?? null
}

/** Эффективная форма ОДНОЙ строки — зеркало backend
 * item_forms.py::item_form_for_row (Правило №6, единственный источник на
 * фронте). rowItemForm — item.item_form строки, учитывается только когда
 * contractForm допускает выбор. */
export function itemFormForRow(
  contractForm: string | null | undefined,
  rowItemForm?: ItemFormCode | string | null,
): ItemFormCode | null {
  if (!contractForm) return null
  const choices = CONTRACT_FORM_ROW_CHOICES[contractForm]
  if (choices && choices.length) {
    return (rowItemForm && (choices as string[]).includes(rowItemForm)) ? (rowItemForm as ItemFormCode) : choices[0]
  }
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
  /** «Проживание и питание»: допустимые формы СТРОКИ для текущего contractForm
   * (null — форма одна на весь договор, как раньше). */
  rowChoices: ComputedRef<ItemFormCode[] | null>
  /** Эффективная форма ОДНОЙ строки — см. itemFormForRow выше. */
  itemFormForItem: (item: { item_form?: string | null } | null | undefined) => ItemFormCode | null
}

/** contractForm — реактивный источник: Purchase.contract_form закупки ИЛИ
 * Wish.contract_form заявки (владелец, 2026-09-15: «договора на перевозку и
 * питание могут быть не только рамочные, но и разовые» — заявка получила
 * собственный contract_form, спец-формы позиций работают до конвертации). */
export function useItemForm(contractForm: Ref<string | null | undefined> | ComputedRef<string | null | undefined>): UseItemFormResult {
  const itemForm = computed<ItemFormCode | null>(() => itemFormForContractForm(contractForm.value))
  const descriptor = computed<ItemFormDescriptor | null>(() => itemFormDescriptor(itemForm.value))
  const fields = computed<ItemFormField[]>(() => descriptor.value?.fields ?? [])
  const rowChoices = computed<ItemFormCode[] | null>(() => contractFormRowChoices(contractForm.value))
  const itemFormForItem = (item: { item_form?: string | null } | null | undefined) =>
    itemFormForRow(contractForm.value, item?.item_form)
  return { itemForm, descriptor, fields, rowChoices, itemFormForItem }
}
