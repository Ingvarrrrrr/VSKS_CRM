// Диалог выбора рамочного договора («Рамочные договоры» + «Новый рамочный
// договор») — отдельно от useFrameworkSiblings.ts (сводка сумм закупок-«братьев»
// и выбор для «Счёт по РД»). Вынесено из CreateOrderView.vue без изменения
// поведения — те же apiFetch-пути.
import { reactive, ref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { numOrNull } from '@/utils/numberFormat'
import type { ToastType } from '@/composables/useToast'

export interface FrameworkContractLike {
  id: number; number: string; date?: string; contract_type: string
  contractor_id?: number; contractor_name?: string; contractor_inn?: string
  subject?: string; max_amount?: number
  [key: string]: any
}

export function useFrameworkContracts<FrameworkContract extends FrameworkContractLike>(
  form: Record<string, any>,
  contractWord: ComputedRef<string>,
  contractors: Ref<{ id: number; name: string; inn?: string }[]>,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
) {
  const frameworkContracts = ref<FrameworkContract[]>([])
  const frameworkDialog = ref(false)
  const frameworkLoading = ref(false)
  const frameworkSearch = ref('')
  const selectedFrameworkContract = ref<FrameworkContract | null>(null)
  const newFrameworkDialog = ref(false)
  const newFrameworkSaving = ref(false)
  const newFrameworkForm = reactive({
    number: '', date: '', contractor_id: null as number | null, subject: '', max_amount: null as number | null,
  })

  async function openFrameworkDialog() {
    frameworkDialog.value = true
    frameworkSearch.value = ''
    frameworkLoading.value = true
    try {
      const types = [form.purchase_contract_type]
      const params = new URLSearchParams()
      if (form.subsidy_id) params.set('subsidy_id', String(form.subsidy_id))
      types.forEach(t => params.append('contract_type', t))
      frameworkContracts.value = await apiFetch<FrameworkContract[]>(`/contracts/?${params}`)
    } catch {
      showSnack('Ошибка загрузки договоров', 'error')
    } finally {
      frameworkLoading.value = false
    }
  }

  function selectFrameworkContract(c: FrameworkContract) {
    selectedFrameworkContract.value = c
    form.contract_id = c.id
    frameworkDialog.value = false
  }

  function clearFrameworkContract() {
    selectedFrameworkContract.value = null
    form.contract_id = null
  }

  async function saveNewFrameworkContract() {
    if (!newFrameworkForm.number.trim()) return
    newFrameworkSaving.value = true
    try {
      const created = await apiFetch<FrameworkContract>('/contracts/', {
        method: 'POST',
        body: JSON.stringify({
          number: newFrameworkForm.number,
          date: newFrameworkForm.date || null,
          contract_type: form.purchase_contract_type,
          contractor_id: newFrameworkForm.contractor_id || null,
          subsidy_id: form.subsidy_id || null,
          subject: newFrameworkForm.subject || null,
          // `|| null` уже ловил '' (не было 422), но заменено на numOrNull ради
          // единого источника истины (ПРАВИЛО №6): '' → null, 0 сохраняется как число.
          max_amount: numOrNull(newFrameworkForm.max_amount),
          status: 'active',
        }),
      })
      // Add contractor display info
      const ctrs = contractors.value.find(c => c.id === created.contractor_id)
      if (ctrs) { created.contractor_name = ctrs.name; created.contractor_inn = ctrs.inn }
      newFrameworkDialog.value = false
      selectFrameworkContract(created)
      newFrameworkForm.number = ''
      newFrameworkForm.date = ''
      newFrameworkForm.contractor_id = null
      newFrameworkForm.subject = ''
      newFrameworkForm.max_amount = null
    } catch (err: any) {
      const msg = err?.body?.message || err?.message || ''
      if (msg.includes('уже существует') || err?.status === 409) {
        showSnack(`${contractWord.value} с таким номером, контрагентом и датой уже существует`, 'warning')
      } else {
        showSnack('Ошибка создания договора', 'error')
      }
    } finally {
      newFrameworkSaving.value = false
    }
  }

  return {
    frameworkContracts, frameworkDialog, frameworkLoading, frameworkSearch, selectedFrameworkContract,
    newFrameworkDialog, newFrameworkSaving, newFrameworkForm,
    openFrameworkDialog, selectFrameworkContract, clearFrameworkContract, saveNewFrameworkContract,
  }
}
