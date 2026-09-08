// useFeoPlannedCreate — диалог «Новая плановая позиция» (POST /feo-planned-items/)
// и связанный с ним диалог дубликата (409 planned_item_duplicate_name). Вынесено
// дословно из FeoPlannedItemsSelect.vue (рефакторинг монолита, 2026-09-08) —
// оба диалога живут в одной паре, т.к. дубликат появляется ПРЯМО из создания
// (saveCreateDialog перехватывает 409 и открывает duplicateDialog поверх).
import { computed, reactive, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { numOrNull } from '@/utils/numberFormat'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import type { ToastType } from '@/composables/useToast'

export { UNIT_PRICE_NOT_FIXED_HINT }

// Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/работа —
// нижний регистр, как хранится в БД (см. normalize_item_type в
// backend/app/routers/feo_planned_items.py).
export const ITEM_TYPE_OPTIONS = [
  { title: 'Товар', value: 'товар' },
  { title: 'Услуга', value: 'услуга' },
  { title: 'Работа', value: 'работа' },
]

// Жалоба владельца (сессия 2026-08-19): 409 planned_item_duplicate_name — бэкенд
// (backend/app/routers/feo_planned_items.py, create_planned_item) отдаёт данные
// обеих позиций вместо тихого слияния. duplicateInfo хранит и то, чем отвечать
// при «Создать отдельную» (allow_duplicate_name: true, тот же payload).
export interface DuplicateInfo {
  message: string
  existingItemId: number
  existingQuantity: number | null
  existingUnit: string | null
  existingAmount: number | null
  newQuantity: number | null
  newUnit: string | null
  newAmount: number | null
}

export interface UseFeoPlannedCreateDeps {
  props: {
    categoryId: number | null
    items: FeoPlanPosition[]
    readonly?: boolean
    prefill?: { name?: string | null; quantity?: number | null; unit?: string | null; amount?: number | null }
  }
  emit: {
    (event: 'update:modelValue', val: FeoPlanSelection | null): void
    (event: 'planned-item-created'): void
  }
  showSnack: (text: string, color?: ToastType) => void
  fmt: (v: number | null | undefined) => string
  fmtNum: (v: number | null | undefined) => string
}

export function useFeoPlannedCreate(deps: UseFeoPlannedCreateDeps) {
  const { props, emit, showSnack, fmt, fmtNum } = deps

  // БАГ 3 (сессия 2026-08-05): раньше кнопка «Создать в плане закупок» делала
  // router.push('/subsidies') — уводила пользователя со страницы, теряя введённые данные
  // формы, и ничего не создавала. Теперь — диалог тут же, POST /feo-planned-items/
  // (контракт см. backend/app/routers/feo_planned_items.py), затем родитель
  // перезагружает список ('planned-item-created') и созданная позиция выбирается сразу.
  const createDialog = ref(false)
  const createForm = reactive<{ name: string; quantity: number | null; unit: string; unitPrice: number | null; amount: number | null; item_type: string | null }>({
    name: '', quantity: null, unit: '', unitPrice: null, amount: null, item_type: null,
  })
  // Цена за единицу (владелец, 2026-09-02, дословно): «Я на самом деле не хочу
  // здесь указывать количество услуг, я её знаю примерно. Я знаю сумму, которая
  // у меня на это есть, это 200 000, я хочу ввести, что это примерно 20 услуг.
  // При этом тогда не надо автоматически делить сумму на количество и
  // препятствовать дальнейшему продвижению... Должно быть поле с ценой за
  // ед. — если её вводят, тогда сумма считается путём умножения; если не
  // ввели, то сумма и есть сумма, не надо делить и блокировать.»
  // Пока цена задана (и не равна 0) — «Сумма плана» считается сама (кол-во ×
  // цена) и недоступна для ручного ввода; иначе сумма — обычное ручное поле, как
  // раньше. См. backend/app/models/feo_planned_item.py::unit_price и
  // assert_tz_not_over_plan (backend/app/services/feo_plan.py) — контроль
  // превышения плана следует ровно этой же семантике.
  const createAmountIsComputed = computed(() => createForm.unitPrice != null && Number(createForm.unitPrice) !== 0)
  function recalcCreateAmountFromUnitPrice() {
    if (!createAmountIsComputed.value) return
    const price = Number(createForm.unitPrice)
    const qty = createForm.quantity != null && Number(createForm.quantity) > 0 ? Number(createForm.quantity) : 1
    createForm.amount = Math.round(qty * price * 100) / 100
  }
  watch([() => createForm.quantity, () => createForm.unitPrice], () => recalcCreateAmountFromUnitPrice())
  // Пояснение прямо в диалоге (владелец просил объяснить оба режима и
  // последствия — «должен быть комментарий, чтобы человек понял, что он
  // вводит и к чему это приведёт»), без терминов из кода.
  const createPriceCaption = computed((): string =>
    createAmountIsComputed.value
      ? 'С ценой за единицу закупка по этой позиции проверяется и по цене, и по количеству, и по сумме — превысить нельзя ничего из трёх.'
      : 'Без цены за единицу количество считается ориентировочным и не ограничивает закупку — под контролем только общая сумма плана.'
  )
  const createSaving = ref(false)

  function openCreateDialog() {
    if (props.readonly || props.categoryId == null) return
    // Предзаполнение из уже введённой позиции закупки (см. prefill в defineProps),
    // с фолбэком на пустые значения — как было раньше без пропа.
    createForm.name = props.prefill?.name ?? ''
    createForm.quantity = props.prefill?.quantity ?? null
    createForm.unit = props.prefill?.unit ?? ''
    createForm.unitPrice = null
    createForm.amount = props.prefill?.amount ?? null
    createForm.item_type = null
    createDialog.value = true
  }

  // Жалоба владельца (добор сессии 2026-08-19): диалог показывал только «план»
  // существующей позиции, без «выбрано»/«остаток» — «Привязать к существующей»
  // оставалась активной, даже когда там уже выбрано 14 из 14 и человек садил новые
  // 10 шт поверх. duplicateInfo (из тела 409) содержит только собственный план
  // позиции (existing_item.quantity/amount), НЕ её выбранность — это есть только
  // в props.items (единый источник consumed/residual, см. useFeoPlannedResiduals),
  // поэтому строку ищем там по existingItemId (kind всегда 'planned_item' — дедуп
  // на бэке идёт по FeoPlannedItem, см. create_planned_item).
  const duplicateDialog = ref(false)
  const duplicateInfo = ref<DuplicateInfo | null>(null)

  const duplicateExistingRow = computed((): FeoPlanPosition | null => {
    const id = duplicateInfo.value?.existingItemId
    if (id == null) return null
    return props.items.find(r => r.kind === 'planned_item' && r.id === id) ?? null
  })

  // Допуск как у соседних сравнений остатков в проекте (PurchaseItemsEditor.vue,
  // SubsidiesView.vue) — количество в БД Numeric(15,4), точное сравнение ловило бы
  // ложные «не влезает» на округлении с плавающей точкой.
  const RESIDUAL_EPS = 0.0001

  // Не найдена строка в props.items — ведём себя как раньше (кнопка активна,
  // сравнивать остаток не с чем).
  const attachBlockedReason = computed((): string | null => {
    const row = duplicateExistingRow.value
    const info = duplicateInfo.value
    if (!row || !info) return null
    const amountShort = info.newAmount != null && info.newAmount > row.residual + RESIDUAL_EPS
    const qtyShort = info.newQuantity != null && row.residual_quantity != null
      && info.newQuantity > row.residual_quantity + RESIDUAL_EPS
    if (!amountShort && !qtyShort) return null
    const qtyPart = row.planned_quantity != null
      ? `выбрано ${fmtNum(row.consumed_quantity)} из ${fmtNum(row.planned_quantity)} ${row.unit || ''}`.trim() + ' '
      : 'выбрано '
    return `в этой плановой позиции не осталось места: ${qtyPart}(${fmt(row.consumed)} из ${fmt(row.planned_amount)}), остаток ${fmt(row.residual)}`
  })

  const attachDisabled = computed((): boolean => attachBlockedReason.value != null)

  // Владелец (жалоба 2026-09-04, скриншот): «Цена за единицу, ₽ (необязательно)»
  // оставляли пустой → 422 «ожидается число». createForm.* типизирован number|null,
  // но v-model.number на очищенном поле реально кладёт туда '' (Vue's looseToNumber,
  // не NaN/null) — quantity/unitPrice/amount без явного приведения уходили на сервер
  // как есть. numOrNull — общий хелпер (см. @/utils/numberFormat.ts): '' → null,
  // 0 сохраняется как число.
  function buildCreatePayload(allowDuplicate: boolean) {
    return {
      feo_category_id: props.categoryId,
      name: createForm.name.trim(),
      quantity: numOrNull(createForm.quantity),
      unit: createForm.unit.trim() || null,
      unit_price: numOrNull(createForm.unitPrice),
      amount: numOrNull(createForm.amount),
      item_type: createForm.item_type,
      allow_duplicate_name: allowDuplicate,
    }
  }

  async function saveCreateDialog() {
    if (props.categoryId == null) return
    if (!createForm.name.trim()) {
      showSnack('Укажите наименование', 'error')
      return
    }
    createSaving.value = true
    try {
      const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
        method: 'POST',
        body: JSON.stringify(buildCreatePayload(false)),
      })
      createDialog.value = false
      emit('planned-item-created')
      emit('update:modelValue', { kind: 'planned_item', id: created.id })
      showSnack('Плановая позиция создана')
    } catch (e: any) {
      const det = e?.payload?.details
      if (e?.status === 409 && det?.error_code === 'planned_item_duplicate_name') {
        duplicateInfo.value = {
          message: det.message || e.message,
          existingItemId: det.existing_item_id,
          existingQuantity: det.existing_item_quantity != null ? Number(det.existing_item_quantity) : null,
          existingUnit: det.existing_item_unit ?? null,
          existingAmount: det.existing_item_amount != null ? Number(det.existing_item_amount) : null,
          newQuantity: det.new_quantity != null ? Number(det.new_quantity) : null,
          newUnit: det.new_unit ?? null,
          newAmount: det.new_amount != null ? Number(det.new_amount) : null,
        }
        duplicateDialog.value = true
      } else {
        showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
      }
    } finally {
      createSaving.value = false
    }
  }

  // «Привязать к существующей» — тот же путь выбора, что и клик по строке списка
  // (selectItem): просто выбираем уже существующую плановую позицию, ничего не создаём.
  function confirmAttachDuplicate() {
    if (!duplicateInfo.value || attachDisabled.value) return
    emit('update:modelValue', { kind: 'planned_item', id: duplicateInfo.value.existingItemId })
    duplicateDialog.value = false
    createDialog.value = false
  }

  // «Создать отдельную» — повторный POST с allow_duplicate_name: true (тот же payload
  // формы, дедуп на бэке осознанно пропущен), затем выбираем созданную позицию.
  async function confirmCreateDuplicate() {
    if (props.categoryId == null) return
    createSaving.value = true
    try {
      const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
        method: 'POST',
        body: JSON.stringify(buildCreatePayload(true)),
      })
      duplicateDialog.value = false
      createDialog.value = false
      emit('planned-item-created')
      emit('update:modelValue', { kind: 'planned_item', id: created.id })
      showSnack('Плановая позиция создана')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
    } finally {
      createSaving.value = false
    }
  }

  return {
    createDialog, createForm, createAmountIsComputed, createPriceCaption, createSaving,
    openCreateDialog, saveCreateDialog,
    duplicateDialog, duplicateInfo, duplicateExistingRow, attachBlockedReason, attachDisabled,
    confirmAttachDuplicate, confirmCreateDuplicate,
  }
}
