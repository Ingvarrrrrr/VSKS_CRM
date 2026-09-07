// useContractsDialog.ts — диалог создания/редактирования договора, вложенные
// «Создать ежемесячные этапы» и «Согласование и документы» (переход на
// закупку-голову рамочного договора). Дословный перенос из ContractsView.vue.
import { computed, reactive, ref } from 'vue'
import type { Router } from 'vue-router'
import { apiFetch } from '@/api'
import { numOrNull } from '@/utils/numberFormat'
import type { ToastType } from '@/composables/useToast'
import type { Contract, Contractor } from './contractsTypes'

export function useContractsDialog(options: {
  contracts: { value: Contract[] }
  contractors: { value: Contractor[] }
  loadContracts: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
  router: Router
  confirmDelete: (c: Contract) => void
}) {
  const { contracts, contractors, loadContracts, showSnack, router, confirmDelete } = options

  // ── Dialog ─────────────────────────────────────────────────────────────────
  const emptyForm = () => ({
    number: '', date: '', contract_type: 'single', purchase_method: null as string | null, item_type: null as string | null,
    contractor_id: null as number | null, contractor_name: '' as string, contractor_inn: '' as string,
    subsidy_id: null as number | null,
    extra_subsidy_ids: [] as number[],
    subject: '', max_amount: null as number | null, planned_monthly: null as number | null,
    start_date: '', end_date: '', status: 'active', notes: '',
  })
  const dialog = reactive({ show: false, saving: false, id: 0, form: emptyForm() })

  const dialogInitialContractor = computed(() => {
    if (!dialog.form.contractor_id) return null
    return {
      id: dialog.form.contractor_id,
      name: dialog.form.contractor_name || `Контрагент #${dialog.form.contractor_id}`,
      inn: dialog.form.contractor_inn || undefined,
    }
  })

  function onContractorPicked(c: { id: number; name: string; inn?: string } | null) {
    dialog.form.contractor_name = c?.name || ''
    dialog.form.contractor_inn = c?.inn || ''
  }

  const openCreate = () => { dialog.id = 0; Object.assign(dialog.form, emptyForm()); dialog.show = true }

  const openEdit = async (c: Contract) => {
    if ((c as any)._is_advance_report) {
      router.push(`/advance-reports/${(c as any)._purchase_id}/edit`)
      return
    }
    dialog.id = c.id
    // Ensure contractor is loaded before showing
    if (c.contractor_id && !contractors.value.find(x => x.id === c.contractor_id)) {
      try {
        const fetched = await apiFetch<Contractor>(`/contractors/${c.contractor_id}`)
        contractors.value.push(fetched)
      } catch {}
    }
    Object.assign(dialog.form, {
      number: c.number || '', date: c.date || '', contract_type: c.contract_type || 'single',
      purchase_method: c.purchase_method || null, item_type: (c as any).item_type || null,
      contractor_id: c.contractor_id || null, contractor_name: c.contractor_name || '', contractor_inn: c.contractor_inn || '',
      subsidy_id: c.subsidy_id || null,
      extra_subsidy_ids: (c.extra_subsidies || []).map(es => es.subsidy_id),
      subject: c.subject || '',
      max_amount: c.max_amount || null, planned_monthly: c.planned_monthly || null,
      start_date: c.start_date || '', end_date: c.end_date || '',
      status: c.status || 'active', notes: c.notes || '',
    })
    dialog.show = true
  }

  const saveContract = async () => {
    dialog.saving = true
    try {
      // max_amount/planned_monthly — v-model.number; при очистке Vue кладёт '' (не null),
      // `...dialog.form` слал бы её как есть на Optional[Decimal] → 422. numOrNull
      // (2026-09-04): '' → null, 0 сохраняется как число.
      const body = {
        ...dialog.form,
        date: dialog.form.date || null,
        start_date: dialog.form.start_date || null,
        end_date: dialog.form.end_date || null,
        max_amount: numOrNull(dialog.form.max_amount),
        planned_monthly: numOrNull(dialog.form.planned_monthly),
      }
      if (dialog.id) {
        const res = await apiFetch<any>(`/contracts/${dialog.id}`, { method: 'PUT', body: JSON.stringify(body) })
        // Phase 31-04: response is now ContractUpdateResponse {contract, n_updated_purchases, warnings}
        const n = res?.n_updated_purchases ?? 0
        const warnMsg = n > 0 ? `Договор сохранён. Обновлено ${n} закупок` : 'Договор сохранён. Связанных закупок нет'
        showSnack(warnMsg)
        // Phase 31-04: sync warnings — persistent (no auto-dismiss), stack as separate toasts
        if (res?.warnings?.amount_over_max) {
          showSnack('Сумма закупок превышает max_amount договора', 'warning')
        }
        const dateWarnCount = res?.warnings?.date_out_of_validity?.length ?? 0
        if (dateWarnCount > 0) {
          showSnack(`${dateWarnCount} закупок за пределами срока действия договора`, 'warning')
        }
      } else {
        await apiFetch('/contracts/', { method: 'POST', body: JSON.stringify(body) })
        showSnack('Создано')
      }
      dialog.show = false
      await loadContracts()
    } catch (e: any) {
      const msg = (e?.response?.data?.detail) || e?.detail || 'Ошибка сохранения'
      showSnack(msg, 'error')
    } finally {
      dialog.saving = false
    }
  }

  function startDeleteFromDialog() {
    dialog.show = false
    confirmDelete(contracts.value.find(c => c.id === dialog.id)!)
  }

  // ── Monthly Stages ─────────────────────────────────────────────────────────
  const monthlyStagesDialog = reactive({
    show: false,
    contractId: 0,
    contractName: '',
    contractType: '',
    subsidyId: null as number | null,
    defaultAmount: null as number | null,
  })

  function openMonthlyStagesFromDialog() {
    const c = contracts.value.find(x => x.id === dialog.id)
    monthlyStagesDialog.contractId = dialog.id
    monthlyStagesDialog.contractName = c?.number || ''
    monthlyStagesDialog.contractType = dialog.form.contract_type
    monthlyStagesDialog.subsidyId = dialog.form.subsidy_id
    monthlyStagesDialog.defaultAmount = dialog.form.planned_monthly
    dialog.show = false
    monthlyStagesDialog.show = true
  }

  function onMonthlyStagesCreated(res: any) {
    const created = res.created?.length ?? 0
    showSnack(`Создано ${created} этапов`)
    loadContracts()
  }

  // ── Согласование и документы (T-ContractApprovalPurchase) ──────────────────
  // Реестр «Договоры» не имеет своего согласования/печати — эта машинерия
  // живёт на закупке (Purchase). Для рамочного договора без «головной» закупки
  // эндпоинт /contracts/{id}/approval-purchase заводит её (или находит уже
  // существующую) и мы переходим в её карточку — там уже есть согласование
  // необходимости, печать договора и листа согласования.
  const approvalPurchaseLoading = ref(false)
  async function openApprovalPurchase() {
    if (!dialog.id) return
    approvalPurchaseLoading.value = true
    try {
      const res = await apiFetch<{ purchase_id: number; created: boolean }>(
        `/contracts/${dialog.id}/approval-purchase`,
        { method: 'POST' }
      )
      dialog.show = false
      router.push(`/orders/${res.purchase_id}/edit`)
    } catch (e: any) {
      showSnack(e?.message || e?.detail || 'Не удалось открыть согласование и документы', 'error')
    } finally {
      approvalPurchaseLoading.value = false
    }
  }

  return {
    dialog, dialogInitialContractor, onContractorPicked,
    openCreate, openEdit, saveContract, startDeleteFromDialog,
    monthlyStagesDialog, openMonthlyStagesFromDialog, onMonthlyStagesCreated,
    approvalPurchaseLoading, openApprovalPurchase,
  }
}
