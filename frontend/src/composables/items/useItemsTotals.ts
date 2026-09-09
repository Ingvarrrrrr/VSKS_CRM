// useItemsTotals — VAT-per-row helpers (uniform/per_item modes), item/stage
// totals recalculation and the contract-vs-plan sum comparison (savings %).
// Extracted from PurchaseItemsEditor.vue (monolith refactor, часть 2).
import { computed, type ComputedRef, type Ref } from 'vue'
import { parseVatRatePercent, normalizeVatRate } from '@/composables/useVatCalc'
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
}

export function useItemsTotals(deps: UseItemsTotalsDeps) {
  const { localItems, localContractItems, getContractItemFor, isAdvance, emitUpdate, itemForm } = deps

  // Phase 27.1.17: per-stage helpers с fallback vat_rate на PurchaseItem
  function effectiveVatRate(idx: number, stage: 'contract' | 'delivery'): string | null {
    void stage
    const ci = getContractItemFor(idx)
    return ci?.vat_rate ?? localItems.value[idx]?.vat_rate ?? null
  }

  function vatAmountForStage(idx: number, stage: 'tz' | 'contract' | 'delivery'): number {
    let rate: string | null = null
    let total = 0
    if (stage === 'tz') {
      const pi = localItems.value[idx]
      rate = pi?.vat_rate ?? null
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

  function calcItemTotal(idx: number) {
    const item = localItems.value[idx]
    const form = itemForm?.value ?? null
    if (form) {
      // Спец-форма позиции («Проживание»/«Перевозки автобусом»): quantity/unit_price
      // (для transport) — производные от extra_attrs, total_price — по формуле формы.
      // Единственный писатель — utils/itemAmounts.ts (превью того же расчёта, что на бэке).
      applyItemAmounts(item, form)
    } else if (item.quantity != null && item.unit_price != null) {
      item.total_price = Math.round(item.quantity * item.unit_price * 100) / 100
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
    effectiveVatRate, vatAmountForStage, totalWithVatForStage, onVatRateChange, calcItemTotal,
    internalTotalNmck, contractItemsTotal, purchasePlannedTotal, contractSavings, contractSavingsPercent,
    showVatColumnsInExpandRow,
  }
}
