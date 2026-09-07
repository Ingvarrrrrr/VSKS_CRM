// useContractsFilters.ts — мульти-фильтры реестра (клиентские), поиск по
// товару внутри позиций закупок, итоговая отфильтрованная/отсортированная
// выдача с нумерацией строк. Дословный перенос из ContractsView.vue.
import { computed, ref, watch } from 'vue'
import { contractTypeItems, purchaseMethodItems } from './contractsLabels'
import type { Contract, Contractor, Purchase, Subsidy } from './contractsTypes'

export function useContractsFilters(options: {
  contracts: { value: Contract[] }
  subsidies: { value: Subsidy[] }
  contractors: { value: Contractor[] }
  purchasesByContract: { value: Record<number, Purchase[]> }
  // Владелец: тип намеренно `any` — воспроизводит существующее поведение
  // ContractsView.vue (ref, не .value, мутируется напрямую в plain-script
  // watch ниже; в шаблоне ColumnsTable используется отдельно как .value).
  // Не унифицировать — см. ОТЧЁТ (старый дефект, не трогать).
  expandedPurchases: any
  expanded: { value: number[] }
  matchesColumnFilters: (row: any) => boolean
  localSort: { value: { key: string; order: 'asc' | 'desc' } | null }
  loadAllPurchases: () => Promise<void>
}) {
  const { contracts, subsidies, contractors, purchasesByContract, expandedPurchases, expanded, matchesColumnFilters, localSort, loadAllPurchases } = options

  // Локальный поиск по реестру договоров (независим от глобального поиска в шапке —
  // владелец отказался от режима «по странице» у глобального поиска 2026-09-03,
  // поэтому у страницы своё поле).
  const search = ref('')

  // ── Filters (all multi-select, client-side) ────────────────────────────────
  const fSubsidy    = ref<number[]>([])
  const fType       = ref<string[]>([])
  const fMethod     = ref<string[]>([])
  const fStatus     = ref<string[]>([])
  const fContractor = ref<number[]>([])
  const fProduct    = ref('')
  const fDateFrom   = ref('')
  const fDateTo     = ref('')

  const hasFilters = computed(() =>
    fSubsidy.value.length > 0 || fType.value.length > 0 || fMethod.value.length > 0 ||
    fStatus.value.length > 0 || fContractor.value.length > 0 || !!fProduct.value || !!fDateFrom.value || !!fDateTo.value
  )

  const clearFilters = () => {
    fSubsidy.value = []; fType.value = []; fMethod.value = []
    fStatus.value = []; fContractor.value = []; fProduct.value = ''; fDateFrom.value = ''; fDateTo.value = ''
  }

  // ── Dropdown items: only values present in contracts ──────────────────────
  const usedSubsidies = computed(() => {
    const ids = new Set(contracts.value.map(c => c.subsidy_id).filter(Boolean))
    return subsidies.value.filter(s => ids.has(s.id))
  })

  function matchesSearch(c: Contract, q: string): boolean {
    const lq = q.toLowerCase()
    return [c.number, c.contractor_name, c.contractor_inn, c.subsidy_name, c.subject, c.notes]
      .some(v => v?.toLowerCase().includes(lq))
  }

  // Дедуп по имени контрагента — для авансовых contractor_id часто пуст,
  // заполнено только contractor_name (через JOIN на бэке).
  const usedContractors = computed(() => {
    const byName = new Map<string, any>()
    for (const c of contracts.value as any[]) {
      const name = c.contractor_name
      if (!name || byName.has(name)) continue
      const real = contractors.value.find(x =>
        (c.contractor_id && x.id === c.contractor_id) ||
        (c.contractor_inn && x.inn === c.contractor_inn) ||
        x.name === name
      )
      byName.set(name, real || { id: -byName.size - 1, name, inn: c.contractor_inn || '' })
    }
    return Array.from(byName.values())
  })
  const usedContractTypes = computed(() => {
    const types = new Set(contracts.value.map(c => c.contract_type))
    return contractTypeItems.filter(i => types.has(i.value))
  })
  const usedPurchaseMethods = computed(() => {
    const methods = new Set(contracts.value.map(c => c.purchase_method).filter(Boolean))
    return purchaseMethodItems.filter(i => methods.has(i.value))
  })

  // Product search: contracts whose purchases contain matching items
  const productMatchContractIds = computed(() => {
    const q = fProduct.value.trim().toLowerCase()
    if (!q) return null
    const ids = new Set<number>()
    for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
      for (const p of purchases) {
        if (p.items?.some(i => i.item_name?.toLowerCase().includes(q)) ||
            p.subject?.toLowerCase().includes(q) ||
            p.item_name?.toLowerCase().includes(q)) {
          ids.add(Number(cid))
        }
      }
    }
    return ids
  })

  // Auto-expand contracts and purchases when product search is active
  watch(productMatchContractIds, (ids) => {
    if (!ids || ids.size === 0) return
    // Expand matching contracts
    const toExpand = [...ids].filter(id => !expanded.value.includes(id))
    if (toExpand.length) expanded.value = [...expanded.value, ...toExpand]
    // Expand matching purchases to show items
    const q = fProduct.value.trim().toLowerCase()
    if (!q) return
    for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
      if (!ids.has(Number(cid))) continue
      for (const p of purchases) {
        if (p.items?.some(i => i.item_name?.toLowerCase().includes(q))) {
          expandedPurchases[p.id] = true
        }
      }
    }
  })

  // When product filter starts being typed, load all purchases if not yet loaded
  watch(fProduct, (val) => {
    if (val && val.trim().length >= 2) {
      const missingIds = contracts.value.filter(c => !purchasesByContract.value[c.id]).map(c => c.id)
      if (missingIds.length) loadAllPurchases()
    }
  })

  const filtered = computed(() => {
    let list = contracts.value
    if (fSubsidy.value.length)    list = list.filter(c => c.subsidy_id != null && fSubsidy.value.includes(c.subsidy_id))
    if (fType.value.length)       list = list.filter(c => fType.value.includes(c.contract_type))
    if (fMethod.value.length)     list = list.filter(c => c.purchase_method != null && fMethod.value.includes(c.purchase_method))
    if (fStatus.value.length)     list = list.filter(c => c.status != null && fStatus.value.includes(c.status))
    if (fContractor.value.length) {
      const allowedNames = new Set(
        usedContractors.value
          .filter((x: any) => fContractor.value.includes(x.id))
          .map((x: any) => x.name)
      )
      list = list.filter(c => !!c.contractor_name && allowedNames.has(c.contractor_name))
    }
    if (fDateFrom.value)          list = list.filter(c => !c.date || c.date >= fDateFrom.value)
    if (fDateTo.value)            list = list.filter(c => !c.date || c.date <= fDateTo.value)
    // Product filter
    if (productMatchContractIds.value) list = list.filter(c => productMatchContractIds.value!.has(c.id))
    // Локальный поиск страницы
    const q = search.value.trim()
    if (q) list = list.filter(c => matchesSearch(c, q))
    return list
  })

  const filteredWithRowNum = computed(() => {
    // Применяем column-header фильтры поверх основного filtered
    let list = filtered.value.filter(matchesColumnFilters)
    // Применяем локальную сортировку из ColumnHeaderMenu
    if (localSort.value) {
      const { key, order } = localSort.value
      list = [...list].sort((a, b) => {
        const av = (a as any)[key] ?? ''
        const bv = (b as any)[key] ?? ''
        const cmp = String(av).localeCompare(String(bv), 'ru', { numeric: true })
        return order === 'asc' ? cmp : -cmp
      })
    }
    // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum
    const forNum = [...filtered.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
    const map = new Map<string, number>()
    forNum.forEach((c, idx) => map.set(String(c.id), idx + 1))
    return list.map(c => ({ ...c, _rownum: map.get(String(c.id)) ?? '' }))
  })

  const filteredSum = computed(() =>
    filtered.value.reduce((acc, c) => acc + (c.max_amount ? Number(c.max_amount) : 0), 0)
  )

  return {
    search,
    fSubsidy, fType, fMethod, fStatus, fContractor, fProduct, fDateFrom, fDateTo,
    hasFilters, clearFilters,
    usedSubsidies, usedContractors, usedContractTypes, usedPurchaseMethods,
    matchesSearch, productMatchContractIds,
    filtered, filteredWithRowNum, filteredSum,
  }
}
