// useContractsData.ts — загрузка договоров/субсидий/контрагентов и закупок
// по договору (для expand-row и поиска по товару). Дословный перенос из
// ContractsView.vue.
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Contract, Subsidy, Contractor, Purchase } from './contractsTypes'

export function useContractsData(options: { showSnack: (text: string, color?: ToastType) => void }) {
  const { showSnack } = options

  const contracts = ref<Contract[]>([])
  const subsidies = ref<Subsidy[]>([])
  const contractors = ref<Contractor[]>([])
  const loading = ref(false)
  const expanded = ref<number[]>([])

  const purchasesByContract = ref<Record<number, Purchase[]>>({})
  const expandedPurchases = ref<Record<number, boolean>>({})

  // ── Load data (all contracts, no server-side filter) ──────────────────────
  const loadContracts = async () => {
    loading.value = true
    try {
      const [contractsData, advanceReports] = await Promise.all([
        apiFetch<Contract[]>('/contracts/'),
        apiFetch<any[]>('/purchases/?purchase_method=advance').catch(() => [])
      ])
      const arAsContracts = advanceReports.map((p: any) => ({
        id: p.id,
        number: p.registry_number || `АО-${p.id}`,
        date: p.created_at,
        contract_type: 'advance_report',
        contractor_name: p.contractor_name,
        contractor_inn: p.contractor_inn,
        subsidy_name: p.subsidy_name,
        subject: p.subject || p.item_name,
        max_amount: p.planned_total_price,
        total_ordered: p.planned_total_price,
        total_paid: null,
        status: p.status,
        _is_advance_report: true,
        _purchase_id: p.id,
        reimbursement_user_id: p.reimbursement_user_id,
        reimbursement_user_name: p.reimbursement_user_name,
        multi_contractor_label: p.multi_contractor_label,
      }))
      contracts.value = [...contractsData, ...arAsContracts]
    } catch {
      showSnack('Ошибка загрузки', 'error')
    } finally {
      loading.value = false
    }
  }

  const loadSubsidies = async () => { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') }

  // Phase 26-ZZ: bulk-load контрагентов убран. Фильтр контрагентов
  // dedupe-by-name из contracts, edit-dialog подгружает одного контрагента
  // ad-hoc по id (см. useContractsDialog::openEdit).
  const loadContractors = async () => {
    try {
      contractors.value = await apiFetch<Contractor[]>('/contractors/?limit=50')
    } catch (_) {
      // тихо игнорируем — список наполнится по мере поиска
    }
  }

  const loadPurchasesForContract = async (contractId: number) => {
    const c = contracts.value.find(x => x.id === contractId) as any
    if (c?._is_advance_report) {
      // Авансовый отчёт = одна Purchase. Грузим её items напрямую.
      const p = await apiFetch<Purchase>(`/purchases/${c._purchase_id}`)
      purchasesByContract.value = { ...purchasesByContract.value, [contractId]: [p] }
      return
    }
    const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contractId}`)
    purchasesByContract.value = { ...purchasesByContract.value, [contractId]: items }
  }

  const loadAllPurchases = async () => {
    // Load purchases for all contracts (needed for product search)
    const ids = contracts.value.map(c => c.id)
    const batchSize = 10
    for (let i = 0; i < ids.length; i += batchSize) {
      const batch = ids.slice(i, i + batchSize)
      await Promise.all(batch.filter(id => !purchasesByContract.value[id]).map(id => loadPurchasesForContract(id)))
    }
  }

  watch(expanded, (newVal) => {
    for (const id of newVal) {
      if (!purchasesByContract.value[id]) loadPurchasesForContract(id)
    }
  })

  return {
    contracts, subsidies, contractors, loading, expanded,
    purchasesByContract, expandedPurchases,
    loadContracts, loadSubsidies, loadContractors,
    loadPurchasesForContract, loadAllPurchases,
  }
}
