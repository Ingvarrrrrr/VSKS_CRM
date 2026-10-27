// Создание организации — ЕДИНЫЙ механизм для «Иерархия → Организация» и
// «Организации → Добавить организацию» (задание владельца 27.10: раньше
// существовало ДВА разных диалога создания с разной логикой — страница
// «Организации» не искала контрагента в нашей базе по ИНН и не слала
// poruchenie_accepted, из-за чего создание account_owner'ом падало 400.
// ПРАВИЛО №6: один источник — этот композабл, оба входа его переиспользуют
// (useHierarchyOrgDialogs.ts зовёт его внутри себя для Иерархии).
//
// Поиск контрагента по ИНН — ТОЛЬКО через нашу базу: useContractorsStore().search
// (тот же стор, что у автокомплита) и GET /contractors/lookup-inn/{inn} БЕЗ
// force_egrul (этот эндпоинт сам проверяет локальную БД первым и возвращает
// id при совпадении). Второго механизма поиска/обогащения не заводим — ЕГРЮЛ
// остаётся ручным по кнопке (force_egrul=1), как и раньше.
import { reactive, ref } from 'vue'
import { watch } from 'vue'
import { apiFetch } from '@/api'
import { useContractorsStore } from '@/stores/contractors'
import type { ToastType } from '@/composables/useToast'

export interface OrgCreateForm {
  loading: boolean
  name: string
  full_name: string
  inn: string
  kpp: string
  ogrn: string
  address: string
  signatory_last_name: string
  signatory_first_name: string
  signatory_middle_name: string
  signatory_position: string
}

function emptyForm(): OrgCreateForm {
  return {
    loading: false,
    name: '', full_name: '', inn: '', kpp: '', ogrn: '', address: '',
    signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '',
  }
}

export interface UseOrgCreateOptions {
  isSuperadmin: boolean
  showSnack: (text: string, color?: ToastType) => void
  onCreated?: () => void | Promise<void>
}

// Единственное место, где запись контрагента превращается в поля формы
// организации — используется и авто-поиском по ИНН, и ручным выбором из
// автокомплита (Правило №6: раньше было 2 похожие копии этой логики в
// useHierarchyOrgDialogs.ts, одна из них писала в несуществующее поле
// `d.signatory` и ничего реально не заполняла).
function fillFormFromContractor(form: OrgCreateForm, c: Record<string, any>) {
  if (c.name) form.name = c.name
  if (c.full_name) form.full_name = c.full_name
  if (c.inn) form.inn = c.inn
  if (c.kpp) form.kpp = c.kpp
  if (c.ogrn) form.ogrn = c.ogrn
  if (c.address) form.address = c.address
  if (c.signatory_last_name) form.signatory_last_name = c.signatory_last_name
  if (c.signatory_first_name) form.signatory_first_name = c.signatory_first_name
  if (c.signatory_middle_name) form.signatory_middle_name = c.signatory_middle_name
  if (c.signatory_position) form.signatory_position = c.signatory_position
}

export function useOrgCreate(opts: UseOrgCreateOptions) {
  const contractorsStore = useContractorsStore()

  const show = ref(false)
  const form = reactive<OrgCreateForm>(emptyForm())

  // 2026-09-01: аккаунт (головная организация) для новой org — выбирает
  // только superadmin, см. app/services/org_account_resolution.py.
  const accountId = ref<number | null>(null)
  const accountOptions = ref<{ id: number; name: string }[]>([])

  // 152-ФЗ (2026-10-14): account_owner, создающий организацию, становится
  // её owner_user_id — backend требует явного согласия (poruchenie_accepted),
  // снимается на каждое открытие диалога.
  const poruchenieAccepted = ref(false)

  const contractorId = ref<number | null>(null)
  const contractors = ref<any[]>([])
  // ИНН, с которым контрагент был привязан — отличить «мы сами подставили» от
  // «пользователь поменял ИНН руками» (тогда отвязываем контрагента).
  let linkedInn: string | null = null
  let contractorSearchTimeout: ReturnType<typeof setTimeout> | null = null
  let innLookupTimeout: ReturnType<typeof setTimeout> | null = null

  const egrulLoading = ref(false)
  const egrulMessage = ref('')
  const egrulMessageType = ref<'success' | 'info' | 'error' | 'warning'>('info')

  const contractorFilter = (_value: string, query: string, item?: any): boolean => {
    const q = query.toLowerCase()
    const name = (item?.raw?.name || '').toLowerCase()
    const inn = (item?.raw?.inn || '').toLowerCase()
    return name.includes(q) || inn.includes(q)
  }

  function resetForm() {
    Object.assign(form, emptyForm())
    contractorId.value = null
    contractors.value = []
    linkedInn = null
    egrulMessage.value = ''
    accountId.value = null
    poruchenieAccepted.value = false
  }

  async function open() {
    resetForm()
    show.value = true
    if (!opts.isSuperadmin) return
    try {
      accountOptions.value = await apiFetch<{ id: number; name: string }[]>('/organizations/accounts')
    } catch {
      accountOptions.value = []
    }
  }

  function onContractorSearch(query: string) {
    if (contractorSearchTimeout) clearTimeout(contractorSearchTimeout)
    if (!query || query.length < 2) return
    contractorSearchTimeout = setTimeout(async () => {
      const list = await contractorsStore.search(query, 50)
      const existing = new Set(contractors.value.map((c: any) => c.id))
      for (const c of list) {
        if (!existing.has(c.id)) contractors.value.push(c)
      }
    }, 300)
  }

  // Ручной выбор из автокомплита. Фикс дефекта: раньше писал в несуществующее
  // поле `d.signatory` — теперь заполняет ВСЕ поля через общий helper, как и
  // авто-поиск по ИНН ниже (Правило №6, один источник этой логики).
  function onContractorSelect(id: number | null) {
    if (!id) {
      // autocomplete очищен (clearable) — поля снова редактируемые.
      contractorId.value = null
      linkedInn = null
      return
    }
    const c = contractors.value.find((x: any) => x.id === id)
    if (!c) return
    contractorId.value = id
    fillFormFromContractor(form, c)
    linkedInn = (form.inn || '').trim()
  }

  // Авто-поиск контрагента в НАШЕЙ базе по ИНН, когда поле достигает 10/12
  // цифр и контрагент ещё не выбран руками. ЕГРЮЛ сюда НЕ зовём — только
  // useContractorsStore().search + /contractors/lookup-inn/{inn} (без
  // force_egrul, т.е. тоже только локальная БД).
  watch(() => form.inn, (val) => {
    if (innLookupTimeout) clearTimeout(innLookupTimeout)
    const digits = (val || '').trim()

    // ИНН разошёлся с привязанным контрагентом — отвязываем, поля снова
    // редактируемые.
    if (contractorId.value != null && linkedInn != null && digits !== linkedInn) {
      contractorId.value = null
      linkedInn = null
    }
    if (contractorId.value != null) return // уже привязан вручную/автоматически
    if (digits.length !== 10 && digits.length !== 12) return

    innLookupTimeout = setTimeout(async () => {
      if (contractorId.value != null) return
      if ((form.inn || '').trim() !== digits) return // ИНН успел измениться за время debounce
      try {
        const list = await contractorsStore.search(digits, 10)
        const match = list.find((c: any) => (c.inn || '').trim() === digits)
        if (!match) return
        if ((form.inn || '').trim() !== digits || contractorId.value != null) return

        const existing = contractors.value.some((c: any) => c.id === match.id)
        if (!existing) contractors.value.push(match)

        let full: Record<string, any> = match
        if (!match.kpp || !match.address || !match.signatory_last_name) {
          try {
            const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${digits}`)
            if (data._source === 'local') full = { ...match, ...data }
          } catch { /* best-effort — локальных данных автокомплита достаточно */ }
        }
        if ((form.inn || '').trim() !== digits || contractorId.value != null) return

        contractorId.value = match.id
        fillFormFromContractor(form, full)
        linkedInn = digits
        egrulMessage.value = `Найден в базе контрагентов: «${full.name || match.name}» (ИНН ${digits}) — реквизиты взяты из его карточки`
        egrulMessageType.value = 'info'
      } catch { /* silent — автопоиск best-effort, ЕГРЮЛ остаётся кнопкой */ }
    }, 300)
  })

  async function enrichFromEgrul() {
    const inn = form.inn.trim()
    if (!inn || inn.length < 10) return
    egrulLoading.value = true
    egrulMessage.value = ''
    try {
      const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
      if (data._source === 'npd') {
        egrulMessage.value = data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`
        egrulMessageType.value = 'warning'
        return
      }
      if (data.name && !form.name.trim()) form.name = data.name
      if (data.full_name) form.full_name = data.full_name
      if (data.kpp) form.kpp = data.kpp
      if (data.ogrn) form.ogrn = data.ogrn
      if (data.address) form.address = data.address
      if (data.signatory_last_name) form.signatory_last_name = data.signatory_last_name
      if (data.signatory_first_name) form.signatory_first_name = data.signatory_first_name
      if (data.signatory_middle_name) form.signatory_middle_name = data.signatory_middle_name
      if (data.signatory_position) form.signatory_position = data.signatory_position
      egrulMessage.value = 'Данные заполнены из ЕГРЮЛ'
      egrulMessageType.value = 'success'
    } catch (e: any) {
      if (e?.payload?.code === 'INN_NOT_FOUND') {
        egrulMessage.value = e.payload.message
        egrulMessageType.value = 'warning'
      } else {
        egrulMessage.value = e?.message || 'Ошибка запроса к ФНС'
        egrulMessageType.value = 'error'
      }
    } finally {
      egrulLoading.value = false
    }
  }

  async function createOrg() {
    const name = form.name.trim()
    if (!name) return
    form.loading = true
    try {
      const body: Record<string, unknown> = {
        name,
        full_name: form.full_name.trim() || null,
        inn: form.inn.trim() || null,
        kpp: form.kpp.trim() || null,
        ogrn: form.ogrn.trim() || null,
        address: form.address.trim() || null,
        signatory_last_name: form.signatory_last_name.trim() || null,
        signatory_first_name: form.signatory_first_name.trim() || null,
        signatory_middle_name: form.signatory_middle_name.trim() || null,
        signatory_position: form.signatory_position.trim() || null,
        contractor_id: contractorId.value || null,
        root_org_id: opts.isSuperadmin ? (accountId.value || null) : null,
        // Требуется backend'ом только когда создающий становится владельцем
        // (account_owner) — для superadmin игнорируется, но передаём как есть.
        poruchenie_accepted: poruchenieAccepted.value,
      }
      await apiFetch('/organizations/', { method: 'POST', body })
      opts.showSnack(`Организация "${name}" создана`)
      show.value = false
      resetForm()
      await opts.onCreated?.()
    } catch (e: any) {
      opts.showSnack(e?.payload?.message || e?.message || 'Ошибка создания организации', 'error')
    } finally {
      form.loading = false
    }
  }

  return {
    contractorsStore,
    show, form, accountId, accountOptions, poruchenieAccepted,
    contractorId, contractors, contractorFilter,
    egrulLoading, egrulMessage, egrulMessageType,
    open, onContractorSearch, onContractorSelect, enrichFromEgrul, createOrg,
    clearEgrulMessage: () => { egrulMessage.value = '' },
  }
}
