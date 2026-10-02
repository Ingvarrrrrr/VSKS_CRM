// useItemsTotals — VAT-per-row helpers (uniform/per_item modes), item/stage
// totals recalculation and the contract-vs-plan sum comparison (savings %).
// Extracted from PurchaseItemsEditor.vue (monolith refactor, часть 2).
import { computed, type ComputedRef, type Ref } from 'vue'
import { parseVatRatePercent, normalizeVatRate, effectiveVatOnTop, lineTotalWithVat, effectiveVatRateForItem } from '@/composables/useVatCalc'
// item-forms-accommodation-transport.md: ЕДИНСТВЕННОЕ место на фронте, вызывающее
// applyItemAmounts — таблицы (ItemsTableFlat/Stages/Wish/ItemsCardsView) сами
// формулу не считают, только эмитят 'calc-item-total' сюда (Правило №6).
import { applyItemAmounts, type ItemFormCode } from '@/utils/itemAmounts'

// EditorItem/ContractItem are structurally identical to the parent's; kept
// loose here (same convention as ItemsTableFlat.vue) since the parent owns
// the real shape and this composable only reads/writes the fields it uses.
type EditorItem = any
type ContractItem = any

export interface UseItemsTotalsDeps {
  localItems: Ref<EditorItem[]>
  localContractItems: Ref<ContractItem[]>
  getContractItemFor: (rowIdx: number) => ContractItem | undefined
  isAdvance: ComputedRef<boolean>
  emitUpdate: () => void
  // item-forms-accommodation-transport.md: форма позиций текущей закупки
  // (выводится из Purchase.contract_form, см. composables/items/useItemForm.ts) —
  // null для обычных закупок/заявок, тогда calcItemTotal считает как раньше.
  itemForm?: ComputedRef<ItemFormCode | null>
  // «Проживание и питание»: форма ПО СТРОКЕ (item.item_form), когда
  // contract_form допускает выбор — зеркало backend item_form_for_row. Если
  // передан, побеждает itemForm выше для этой позиции (useItemForm.ts::
  // itemFormForItem уже учитывает обычный случай «форма одна на весь
  // договор» сам, так что при наличии resolveItemForm itemForm можно не
  // передавать вовсе).
  resolveItemForm?: (item: EditorItem) => ItemFormCode | null
  // 2026-10-02 (НДС «в цене»/«сверху»): флаг закупки «цена ТЗ без НДС, сверху»
  // (tz_vat_on_top) и текущий режим НДС (uniform/per_item) — для разрешения
  // эффективного флага строки через effectiveVatOnTop (ПРАВИЛО №6, один
  // источник формулы — useVatCalc.ts). Опциональны — без них calcItemTotal
  // ведёт себя как раньше (как при onTop=false).
  tzVatOnTop?: ComputedRef<boolean>
  vatMode?: ComputedRef<string | null | undefined>
  // 2026-10-02 (дефект приёмки): ставка «как в шапке», уже в строковом формате
  // VAT_RATE_OPTIONS (headerVatRateString(vatApplicable, vatRate) — считает
  // вызывающий, PurchaseItemsEditor.vue). В uniform-режиме строка своей ставки
  // не вводит (UI ставки появляется только при per_item) — без фолбэка на
  // шапку item.vat_rate всегда null, и «НДС сверху» резолвился бы в 0%.
  headerVatRate?: ComputedRef<string | null>
}

export function useItemsTotals(deps: UseItemsTotalsDeps) {
  const { localItems, localContractItems, getContractItemFor, isAdvance, emitUpdate, itemForm, resolveItemForm, tzVatOnTop, vatMode, headerVatRate } = deps

  // ЕДИНСТВЕННОЕ место разрешения «эффективной» ставки строки (ПРАВИЛО №6) —
  // своя (item/ci.vat_rate), а в uniform — фолбэк на шапку. Используют
  // calcItemTotal, effectiveVatRate, vatAmountForStage И
  // PurchaseItemsEditor.vue::recalcContractTotal/recalc-хендлеры шапки для
  // Договора (экспортируется ниже, второй копии в компоненте не заводим).
  function resolvedVatRate(itemRate: string | null | undefined): string | null {
    return effectiveVatRateForItem(itemRate, vatMode?.value, headerVatRate?.value ?? null)
  }

  // Phase 27.1.17: per-stage helpers с fallback vat_rate на PurchaseItem, а
  // дальше — на шапку (resolvedVatRate, 2026-10-02).
  function effectiveVatRate(idx: number, stage: 'contract' | 'delivery'): string | null {
    void stage
    const ci = getContractItemFor(idx)
    return resolvedVatRate(ci?.vat_rate ?? localItems.value[idx]?.vat_rate ?? null)
  }

  function vatAmountForStage(idx: number, stage: 'tz' | 'contract' | 'delivery'): number {
    let rate: string | null = null
    let total = 0
    if (stage === 'tz') {
      const pi = localItems.value[idx]
      rate = resolvedVatRate(pi?.vat_rate ?? null)
      total = Number((pi as any)?.total_price ?? 0)
    } else if (stage === 'contract') {
      rate = effectiveVatRate(idx, 'contract')
      total = Number(getContractItemFor(idx)?.total ?? 0)
    } else {
      rate = effectiveVatRate(idx, 'delivery')
      total = Number(getContractItemFor(idx)?.total ?? 0)
    }
    if (!rate) return 0
    const pct = parseVatRatePercent(rate)
    if (pct <= 0) return 0
    return Number((total * pct / (100 + pct)).toFixed(2))
  }

  function totalWithVatForStage(idx: number, stage: 'contract' | 'delivery'): number {
    void stage
    return Number(getContractItemFor(idx)?.total ?? 0)
  }

  function onVatRateChange(idx: number, v: any) {
    const item = localItems.value[idx]
    if (!item) return
    item.vat_rate = normalizeVatRate(v)
    calcItemTotal(idx)
  }

  // 2026-10-02: построчный переключатель «НДС сверху» для строки ТЗ (per_item-режим).
  function onVatOnTopChange(idx: number, v: boolean | null) {
    const item = localItems.value[idx]
    if (!item) return
    item.vat_on_top = v
    calcItemTotal(idx)
  }

  // 2026-10-02 (защита ручных/файловых сумм — владелец, правка после приёмки):
  // пересчёт строк ТОЛЬКО по ЯВНОМУ клику переключателя «НДС сверху» В ШАПКЕ
  // (вызывает PurchaseItemsEditor.vue::onTzVatOnTopToggle), с НОВЫМ значением
  // переданным напрямую — НЕ через watch на props (эхо прежнего значения
  // пришло бы ПОЗЖЕ при: открытии старой карточки из GET, автосейве, смене
  // ставки/режима без участия «сверху» — именно эти случаи были дырой: строка,
  // чья сумма не равна qty×price (ручной ввод/«оставить как в файле»), молча
  // переписывалась бы при каждой такой загрузке). Строку с СОБСТВЕННЫМ флагом
  // (per_item, vat_on_top !== null) эта функция не трогает НИКОГДА — заголовок
  // на неё не действует (effectiveVatOnTop). Спец-формы (item_form) тоже не
  // трогает — total_price там считает applyItemAmounts, не lineTotalWithVat.
  function recalcItemsForHeaderVatOnTop(newHeaderOnTop: boolean) {
    const mode = vatMode?.value || 'uniform'
    localItems.value.forEach((item: any) => {
      if (mode === 'per_item' && item.vat_on_top != null) return
      const form = resolveItemForm ? resolveItemForm(item) : (itemForm?.value ?? null)
      if (form) return
      if (item.quantity == null || item.unit_price == null) return
      item.total_price = lineTotalWithVat(item.quantity, item.unit_price, resolvedVatRate(item.vat_rate), newHeaderOnTop)
    })
    emitUpdate()
  }

  function calcItemTotal(idx: number) {
    const item = localItems.value[idx]
    const form = resolveItemForm ? resolveItemForm(item) : (itemForm?.value ?? null)
    if (form) {
      // Спец-форма позиции («Проживание»/«Перевозки автобусом»): quantity/unit_price
      // (для transport) — производные от extra_attrs, total_price — по формуле формы.
      // Единственный писатель — utils/itemAmounts.ts (превью того же расчёта, что на бэке).
      applyItemAmounts(item, form)
    } else if (item.quantity != null && item.unit_price != null) {
      // «НДС сверху» (2026-10-02): цена ТЗ может быть введена без НДС — сумма
      // строки всегда с НДС (lineTotalWithVat — единственная формула, Правило №6).
      const onTop = effectiveVatOnTop(item.vat_on_top, tzVatOnTop?.value ?? false, vatMode?.value)
      item.total_price = lineTotalWithVat(item.quantity, item.unit_price, resolvedVatRate(item.vat_rate), onTop)
    } else {
      item.total_price = null
    }
    emitUpdate()
  }

  // ── Totals ───────────────────────────────────────────────────────────────────

  const internalTotalNmck = computed(() =>
    localItems.value.reduce((s, i) => s + (i.total_price || 0), 0)
  )

  const contractItemsTotal = computed(() =>
    localContractItems.value.reduce((s, ci) => s + Number(ci.total || 0), 0),
  )

  const purchasePlannedTotal = computed(() =>
    localItems.value.reduce((s, it) => s + Number(it.total_price || 0), 0),
  )

  const contractSavings = computed(() => {
    const tz = purchasePlannedTotal.value
    const ci = contractItemsTotal.value
    if (!tz || !ci) return null
    return tz - ci
  })

  const contractSavingsPercent = computed(() => {
    const tz = purchasePlannedTotal.value
    const sv = contractSavings.value
    if (!tz || sv == null) return null
    return ((sv / tz) * 100).toFixed(1)
  })

  const showVatColumnsInExpandRow = computed(() => {
    if (!isAdvance.value) return true
    return (localItems.value || []).some((it: any) =>
      it?.vat_rate && String(it.vat_rate).trim() !== ''
    )
  })

  return {
    effectiveVatRate, vatAmountForStage, totalWithVatForStage, onVatRateChange, onVatOnTopChange, calcItemTotal,
    recalcItemsForHeaderVatOnTop, resolvedVatRate,
    internalTotalNmck, contractItemsTotal, purchasePlannedTotal, contractSavings, contractSavingsPercent,
    showVatColumnsInExpandRow,
  }
}
