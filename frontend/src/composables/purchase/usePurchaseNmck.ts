// НМЦД/итоги закупки — вынесено из CreateOrderView.vue без изменения поведения.
// Содержит ТОЛЬКО чистые вычисления (computed) и переключатели режима (refs),
// которые зависят исключительно от form/items. Функции, которые ПИШУТ в form
// (syncContractPriceIfSingle, calcEconomy) и watcher'ы остаются во view — их
// результат читается в save()/шаблоне напрямую из form, поэтому перенос сюда
// сломал бы единственный источник истины (ПРАВИЛО №6).
import { ref, computed, type Ref, type ComputedRef } from 'vue'

export interface NmckFormSlice {
  purchase_contract_type: string
  status: string
  contract_price: number | null
}

export interface NmckItemLike {
  total_price: number | null
}

// Статусы, при которых НМЦД считается зафиксированной (не пересчитывается от позиций)
export const CONTRACTED_STATUSES = ['contracted', 'delivered', 'paid']

export function usePurchaseNmck(
  form: NmckFormSlice,
  items: Ref<NmckItemLike[]>,
  contractWordGen: ComputedRef<string>,
  isFramework: ComputedRef<boolean>,
) {
  // Режим ввода НМЦД: auto (сумма позиций) / manual (ручной ввод)
  const nmckMode = ref<'auto' | 'manual'>('auto')
  const nmckManualValue = ref<number | null>(null)
  // Режим ввода цены договора: auto (= НМЦД для разовой закупки) / manual
  const contractPriceMode = ref<'auto' | 'manual'>('auto')
  // Зафиксированная в БД НМЦД (заморожена при переходе в contracted+)
  const savedNmck = ref<number | null>(null)

  const totalNmck = computed(() =>
    items.value.reduce((s, i) => s + (i.total_price || 0), 0)
  )

  // Single purchase = contract_price auto-filled from items
  const isSinglePurchase = computed(() =>
    !form.purchase_contract_type || form.purchase_contract_type === 'single'
  )

  // Is purchase in contracted+ status (НМЦД frozen)
  const isContracted = computed(() => CONTRACTED_STATUSES.includes(form.status))

  // Display НМЦД: manual override → frozen contracted value → live from items
  const displayNmck = computed(() => {
    if (nmckMode.value === 'manual' && nmckManualValue.value != null) return nmckManualValue.value
    if (isContracted.value && savedNmck.value != null) return savedNmck.value
    return totalNmck.value
  })

  const nmckHint = computed(() => {
    if (isContracted.value && savedNmck.value != null) {
      return `Зафиксирована при заключении ${contractWordGen.value}. Не пересчитывается.`
    }
    return `Сумма всех позиций. Пересчитывается автоматически. Фиксируется при заключении ${contractWordGen.value}.`
  })

  const contractPriceHint = computed(() => {
    if (isSinglePurchase.value) {
      if (isContracted.value) {
        return 'Разовая закупка: = сумма текущих цен позиций (обновляется при изменении цен)'
      }
      return 'Разовая закупка: = сумма позиций (заполняется автоматически)'
    }
    return 'Рамочный договор: введите общую сумму договора вручную'
  })

  const nmckExcessPct = computed(() => {
    const nmck = displayNmck.value
    if (!nmck || !form.contract_price) return 0
    return Math.round(((form.contract_price - nmck) / nmck) * 100)
  })

  const nmckWarningLevel = computed((): 'error' | 'warning' | null => {
    // For framework contracts, don't compare contract_price vs NMCD (they're different things)
    if (isFramework.value) return null
    const pct = nmckExcessPct.value
    if (pct > 10) return 'error'
    if (pct > 0) return 'warning'
    return null
  })

  return {
    nmckMode, nmckManualValue, contractPriceMode, savedNmck,
    totalNmck, isSinglePurchase, isContracted, displayNmck,
    nmckHint, contractPriceHint, nmckExcessPct, nmckWarningLevel,
  }
}
