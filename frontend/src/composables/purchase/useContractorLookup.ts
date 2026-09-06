// Новый контрагент (диалог + импорт из файла) + автозаполнение из ЕГРЮЛ по ИНН
// (lookup-inn/force_egrul=1) с diff-подтверждением перед применением. Вынесено
// из CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { reactive, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

interface ContractorLike { id: number; name: string; inn?: string }

interface ContractorsStoreLike {
  putToCache: (c: any) => void
}

export function useContractorLookup(
  form: Record<string, any>,
  contractors: Ref<ContractorLike[]>,
  contractorInn: Ref<string>,
  contractorsStore: ContractorsStoreLike,
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void,
) {
  const addContractorDialog = ref(false)
  const addContractorForm = reactive({
    name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '',
    contact_person: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', org_type: '' as string,
    bank_name: '', bik: '', settlement_account: '', correspondent_account: '',
  })
  const addContractorSaving = ref(false)
  const addContractorFile = ref<File | null>(null)
  const addContractorImporting = ref(false)
  const egrulDiffDialog = ref(false)
  const egrulDiffItems = ref<{ key: string; label: string; old: string; new: string }[]>([])
  const egrulDiffPending = ref<Record<string, string>>({})

  function openAddContractor() {
    Object.assign(addContractorForm, { name: '', inn: '', kpp: '', ogrn: '', address: '', phone: '', email: '', contact_person: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', org_type: 'Юридическое лицо', bank_name: '', bik: '', settlement_account: '', correspondent_account: '' })
    addContractorFile.value = null
    addContractorDialog.value = true
  }

  async function saveNewContractor() {
    if (!addContractorForm.name.trim()) return
    addContractorSaving.value = true
    try {
      const created = await apiFetch<ContractorLike>('/contractors/', { method: 'POST', body: JSON.stringify({ ...addContractorForm }) })
      contractors.value.push(created)
      contractorsStore.putToCache(created)  // Phase 26-ZZ: и в Pinia cache для глобального resolve
      form.contractor_id = created.id
      contractorInn.value = created.inn || ''
      addContractorDialog.value = false
      showSnack('Контрагент добавлен')
    } catch (e: any) {
      showSnack(e.message || 'Ошибка', 'error')
    } finally {
      addContractorSaving.value = false
    }
  }

  async function importContractorFromFile() {
    if (!addContractorFile.value) return
    addContractorImporting.value = true
    try {
      const fd = new FormData()
      fd.append('file', addContractorFile.value)
      const res = await fetch('/api/contractors/import/preview', { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('auth_token')}` }, body: fd })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      // Take first data row and try to fill form
      const headers = data.headers || []
      const sample = data.sample?.[0] || []
      const hints: Record<string, string[]> = {
        name: ['назван', 'наимен', 'name', 'органи'], inn: ['инн', 'inn'], kpp: ['кпп', 'kpp'],
        ogrn: ['огрн', 'ogrn'], address: ['адрес', 'address'], phone: ['телефон', 'phone'],
        email: ['email', 'mail'], contact_person: ['контакт', 'лицо'], signatory: ['подписант', 'директор'],
        bank_name: ['банк', 'bank'], bik: ['бик', 'bik'], settlement_account: ['расч', 'р/с'],
        correspondent_account: ['корр', 'к/с'],
      }
      for (const [field, kws] of Object.entries(hints)) {
        for (let i = 0; i < headers.length; i++) {
          const h = (headers[i] || '').toLowerCase()
          if (kws.some(k => h.includes(k)) && sample[i]) {
            (addContractorForm as any)[field] = String(sample[i]).trim()
            break
          }
        }
      }
      showSnack('Данные подтянуты из файла', 'info')
    } catch (e: any) {
      showSnack(e.message || 'Ошибка чтения файла', 'error')
    } finally {
      addContractorImporting.value = false
    }
  }

  async function lookupContractorInn() {
    const inn = addContractorForm.inn?.trim()
    if (!inn || inn.length < 10) return
    try {
      const data = await apiFetch<any>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
      // Самозанятый: в ЕГРЮЛ/ЕГРИП его нет, реестр НПД отдаёт только статус
      if (data?._source === 'npd') {
        if (!addContractorForm.org_type) addContractorForm.org_type = 'Самозанятый'
        showSnack(data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`, 'warning')
        return
      }
      const FIELDS = [
        { key: 'name', label: 'Наименование' },
        { key: 'full_name', label: 'Полное наименование' },
        { key: 'kpp', label: 'КПП' },
        { key: 'ogrn', label: 'ОГРН' },
        { key: 'address', label: 'Адрес' },
        { key: 'signatory_last_name', label: 'Фамилия подписанта' },
        { key: 'signatory_first_name', label: 'Имя подписанта' },
        { key: 'signatory_middle_name', label: 'Отчество подписанта' },
        { key: 'signatory_position', label: 'Должность подписанта' },
        { key: 'phone', label: 'Телефон' },
        { key: 'email', label: 'Email' },
        { key: 'bank_name', label: 'Банк' },
        { key: 'bik', label: 'БИК' },
        { key: 'settlement_account', label: 'Расчётный счёт' },
        { key: 'correspondent_account', label: 'Корр. счёт' },
      ]
      const diffs: { key: string; label: string; old: string; new: string }[] = []
      const pending: Record<string, string> = {}
      for (const f of FIELDS) {
        const newVal = (data?.[f.key] || '').toString().trim()
        const curVal = ((addContractorForm as any)[f.key] || '').toString().trim()
        if (newVal && newVal !== curVal) {
          diffs.push({ key: f.key, label: f.label, old: curVal || '—', new: newVal })
          pending[f.key] = newVal
        }
      }
      if (diffs.length === 0) {
        showSnack('Данные ЕГРЮЛ совпадают с текущими', 'info')
        return
      }
      egrulDiffItems.value = diffs
      egrulDiffPending.value = pending
      egrulDiffDialog.value = true
    } catch (e: any) {
      if (e?.payload?.code === 'INN_NOT_FOUND') {
        showSnack(e.payload.message, 'warning')
      } else {
        showSnack(e?.message || 'Ошибка запроса к ФНС', 'error')
      }
    }
  }

  function applyEgrulDiff() {
    for (const k of Object.keys(egrulDiffPending.value)) {
      (addContractorForm as any)[k] = egrulDiffPending.value[k]
    }
    egrulDiffDialog.value = false
    showSnack('Данные обновлены из ЕГРЮЛ', 'success')
  }

  let _addContractorInnTimeout: any = null
  function onAddContractorInnChange(val: string) {
    clearTimeout(_addContractorInnTimeout)
    const inn = (val || '').replace(/\D/g, '')
    if (inn.length === 10 || inn.length === 12) {
      _addContractorInnTimeout = setTimeout(() => lookupContractorInn(), 400)
    }
  }

  return {
    addContractorDialog, addContractorForm, addContractorSaving, addContractorFile, addContractorImporting,
    egrulDiffDialog, egrulDiffItems, egrulDiffPending,
    openAddContractor, saveNewContractor, importContractorFromFile, lookupContractorInn, applyEgrulDiff, onAddContractorInnChange,
  }
}
