// Рамочные договоры: закупки-«братья» по тому же договору (сводка сумм) +
// выбор рамочного договора для «Счёт по РД» (payment_basis_type=framework_invoice).
// Вынесено из CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface FrameworkSibling {
  id: number; item_name?: string; subject?: string; status: string
  framework_seq?: number; total_nmck?: number; contract_price?: number; payment_amount?: number
}

export function useFrameworkSiblings<FrameworkContract extends { id: number; number?: string; date?: string; contract_type?: string; contractor_id?: number; contractor_name?: string; contractor_inn?: string; subject?: string }>(
  form: Record<string, any>,
  isFramework: ComputedRef<boolean>,
  frameworkContracts: Ref<FrameworkContract[]>,
  frameworkSearch: Ref<string>,
) {
  const frameworkSiblings = ref<FrameworkSibling[]>([])

  const frameworkTotals = computed(() => ({
    nmck:  frameworkSiblings.value.reduce((s, x) => s + (Number(x.total_nmck) || 0), 0),
    price: frameworkSiblings.value.reduce((s, x) => s + (Number(x.contract_price) || 0), 0),
    paid:  frameworkSiblings.value.reduce((s, x) => s + (Number(x.payment_amount) || 0), 0),
  }))

  async function loadFrameworkSiblings(contractId: number) {
    try {
      frameworkSiblings.value = await apiFetch<FrameworkSibling[]>(`/purchases/by-contract/${contractId}`)
    } catch {
      frameworkSiblings.value = []
    }
  }

  watch(() => form.contract_id, (cid) => {
    if (cid && isFramework.value) loadFrameworkSiblings(cid)
    else frameworkSiblings.value = []
  })

  const filteredFrameworkContracts = computed(() => {
    const q = frameworkSearch.value.toLowerCase().trim()
    if (!q) return frameworkContracts.value
    return frameworkContracts.value.filter(c =>
      (c.number || '').toLowerCase().includes(q) ||
      (c.contractor_name || '').toLowerCase().includes(q) ||
      (c.contractor_inn || '').toLowerCase().includes(q) ||
      (c.subject || '').toLowerCase().includes(q)
    )
  })

  // ── Счёт по РД (framework_invoice) ──────────────────────────────────────
  const selectedFrameworkInvoiceContract = ref<FrameworkContract | null>(null)

  const frameworkContractsForInvoice = computed(() => {
    if (!form.contractor_id) return frameworkContracts.value
    return frameworkContracts.value.filter(c => c.contractor_id === form.contractor_id)
  })

  async function loadFrameworkContractsForInvoice() {
    if (form.payment_basis_type !== 'framework_invoice') return
    try {
      const params = new URLSearchParams()
      if (form.subsidy_id) params.set('subsidy_id', String(form.subsidy_id))
      if (form.contractor_id) params.set('contractor_id', String(form.contractor_id))
      params.append('contract_type', 'framework_cumulative')
      params.append('contract_type', 'framework_with_amount')
      frameworkContracts.value = await apiFetch<FrameworkContract[]>(`/contracts/?${params}`)
    } catch { /* silent */ }
  }

  function onFrameworkInvoiceSelect(c: FrameworkContract | null) {
    if (c) {
      form.contract_id = c.id
      // phase26-j-3: autofill denormalized fields from selected contract
      if (c.number) form.contract_number = c.number
      if (c.date) form.contract_date = c.date
      if (c.contract_type) form.purchase_contract_type = c.contract_type
    } else {
      form.contract_id = null
    }
  }

  watch(() => form.payment_basis_type, (newType) => {
    if (newType === 'framework_invoice') {
      loadFrameworkContractsForInvoice()
    }
  })

  watch(() => form.contractor_id, () => {
    if (form.payment_basis_type === 'framework_invoice') {
      loadFrameworkContractsForInvoice()
    }
  })

  return {
    frameworkSiblings, frameworkTotals, loadFrameworkSiblings, filteredFrameworkContracts,
    selectedFrameworkInvoiceContract, frameworkContractsForInvoice,
    loadFrameworkContractsForInvoice, onFrameworkInvoiceSelect,
  }
}
