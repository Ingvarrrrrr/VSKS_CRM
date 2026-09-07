// useItemsContractors — per-row contractor assignment: the merged
// props/local contractors list (Phase 26-JJ shared-state pattern), the
// quick-create picker dialog, INN lookup + live server-search on the
// contractor combobox, and onItemContractorSelect. Extracted from
// PurchaseItemsEditor.vue (monolith refactor, часть 3).
import { ref, computed, reactive, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { Contractor } from '@/components/items/types'
import type { ToastType } from '@/composables/useToast'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue) since the parent owns the real shape and
// this composable only reads/writes contractor_id/contractor_name/contractor_inn.
type EditorItem = any

export interface UseItemsContractorsDeps {
  props: { contractors?: Contractor[]; modelValue: EditorItem[] }
  localItems: Ref<EditorItem[]>
  emitUpdate: () => void
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
}

export function useItemsContractors(deps: UseItemsContractorsDeps) {
  const { props, localItems, emitUpdate, showSnack } = deps

  // Phase 26-JJ: localContractors holds hydrated-per-id + live-search results.
  // contractors computed merges props.contractors (parent shared state) with local — no duplicates.
  const localContractors = ref<Contractor[]>([])
  const contractors = computed<Contractor[]>(() => {
    if (!props.contractors) return localContractors.value
    const seen = new Set(props.contractors.map((c: Contractor) => c.id))
    return [...props.contractors, ...localContractors.value.filter((c: Contractor) => !seen.has(c.id))]
  })
  const contractorPickerDialog = ref(false)
  const contractorPickerSaving = ref(false)
  const contractorPickerForm = reactive({
    name: '',
    inn: '',
    kpp: '',
    address: '',
  })
  const contractorPickerIdx = ref(-1)
  const contractorPickerPrefillName = ref('')
  const contractorPickerPrefillInn = ref('')

  // Per-row loading state для INN lookup
  const contractorLookupLoading = ref<Record<number, boolean>>({})

  // Phase 26-JJ: NO bulk load. Hydrate only known contractor_id from current items.
  // If props.contractors is provided — parent already manages the list.
  async function loadContractors() {
    if (props.contractors) return  // shared state from parent — parent will hydrate
    const ids = Array.from(new Set(
      (props.modelValue || [])
        .map((it: any) => it.contractor_id)
        .filter((id: any) => typeof id === 'number' && id > 0)
    )) as number[]
    if (!ids.length) return
    const fetched = await Promise.all(
      ids.map((id: number) => apiFetch<Contractor>(`/contractors/${id}`).catch(() => null as any))
    )
    for (const c of fetched) {
      if (c && c.id && !localContractors.value.some((x: Contractor) => x.id === c.id)) {
        localContractors.value.push(c)
      }
    }
  }

  function contractorFilter(_value: string, query: string, item?: any): boolean {
    if (!query.trim()) return true
    const q = query.toLowerCase().trim()
    const name = (item?.raw?.name || '').toLowerCase()
    const inn = (item?.raw?.inn || '').toLowerCase()
    return name.includes(q) || inn.includes(q)
  }

  function onItemContractorSelect(idx: number, val: Contractor | null) {
    const item = localItems.value[idx]
    if (!item) return
    if (!val) {
      item.contractor_id = null
      item.contractor_name = null
      item.contractor_inn = null
    } else {
      item.contractor_id = val.id
      item.contractor_name = val.name
      item.contractor_inn = val.inn || null
    }
    emitUpdate()
  }

  function openContractorQuickCreate(idx: number, prefillName?: string, prefillInn?: string) {
    contractorPickerIdx.value = idx
    contractorPickerPrefillName.value = prefillName || ''
    contractorPickerPrefillInn.value = prefillInn || ''
    Object.assign(contractorPickerForm, {
      name: prefillName || '',
      inn: prefillInn || '',
      kpp: '',
      address: '',
    })
    contractorPickerDialog.value = true
  }

  async function saveContractorQuickCreate() {
    if (!contractorPickerForm.name.trim()) return
    contractorPickerSaving.value = true
    try {
      const saved = await apiFetch<Contractor>('/contractors/', {
        method: 'POST',
        body: {
          name: contractorPickerForm.name.trim(),
          inn: contractorPickerForm.inn.trim() || null,
          kpp: contractorPickerForm.kpp.trim() || null,
          address: contractorPickerForm.address.trim() || null,
        },
      })
      // Phase 26-JJ: loadContractors теперь не делает bulk load — добавляем нового контрагента напрямую
      if (saved && saved.id && !localContractors.value.some((c: Contractor) => c.id === saved.id)) {
        localContractors.value.push(saved)
      }
      if (contractorPickerIdx.value >= 0) {
        onItemContractorSelect(contractorPickerIdx.value, saved)
      }
      contractorPickerDialog.value = false
      showSnack(`Контрагент «${saved.name}» создан`)
    } catch (e: any) {
      const msg = e?.payload?.message || e?.detail || e?.message || 'Ошибка создания контрагента'
      showSnack(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error')
    } finally {
      contractorPickerSaving.value = false
    }
  }

  // Lookup contractor by INN from the local list
  async function tryLookupContractorByInn(inn: string): Promise<Contractor | null> {
    if (!inn || inn.length < 10) return null
    const found = contractors.value.find(c => c.inn === inn)
    if (found) return found
    try {
      const res = await apiFetch<Contractor>(`/contractors/lookup-inn/${inn}`)
      return res || null
    } catch {
      return null
    }
  }

  // Phase 26-JJ: live server-search + INN lookup
  let _innLookupTimer: ReturnType<typeof setTimeout> | null = null
  let _searchTimer: ReturnType<typeof setTimeout> | null = null
  async function onContractorSearchInput(idx: number, search: string) {
    if (_innLookupTimer) { clearTimeout(_innLookupTimer); _innLookupTimer = null }
    if (_searchTimer) { clearTimeout(_searchTimer); _searchTimer = null }

    const q = (search || '').trim()
    if (!q) return

    // Цифровой ИНН (10/12) — отдельный путь через lookup-inn
    if (/^\d{10}$|^\d{12}$/.test(q)) {
      if (contractors.value.some((c: Contractor) => c.inn === q)) return
      _innLookupTimer = window.setTimeout(async () => {
        contractorLookupLoading.value[idx] = true
        try {
          const found = await apiFetch<Contractor>(`/contractors/lookup-inn/${q}`)
          if (found && found.id) {
            if (!localContractors.value.some((c: Contractor) => c.id === found.id)) {
              localContractors.value.push(found)
            }
            const item = localItems.value[idx]
            if (item && !item.contractor_id) {
              onItemContractorSelect(idx, found)
            }
          }
        } catch {
          // ФНС не нашёл / network — молча игнорируем
        } finally {
          contractorLookupLoading.value[idx] = false
        }
      }, 600) as unknown as number
      return
    }

    // Текстовый поиск — server-side через /contractors/?search=...
    if (q.length < 2) return
    _searchTimer = window.setTimeout(async () => {
      contractorLookupLoading.value[idx] = true
      try {
        const results = await apiFetch<Contractor[]>(`/contractors/?search=${encodeURIComponent(q)}&limit=50`)
        if (Array.isArray(results)) {
          for (const c of results) {
            if (c.id && !localContractors.value.some((x: Contractor) => x.id === c.id)) {
              localContractors.value.push(c)
            }
          }
        }
      } catch {
        // network — молча игнорируем
      } finally {
        contractorLookupLoading.value[idx] = false
      }
    }, 300) as unknown as number
  }

  return {
    localContractors, contractors,
    contractorPickerDialog, contractorPickerSaving, contractorPickerForm,
    contractorPickerIdx, contractorPickerPrefillName, contractorPickerPrefillInn,
    contractorLookupLoading,
    loadContractors, contractorFilter, onItemContractorSelect,
    openContractorQuickCreate, saveContractorQuickCreate,
    tryLookupContractorByInn, onContractorSearchInput,
  }
}
