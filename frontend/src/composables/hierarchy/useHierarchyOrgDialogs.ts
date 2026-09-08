// Диалоги организации: создать / редактировать / привязать к контрагенту / удалить.
// Вынесено из HierarchyView.vue без изменения логики.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useContractorsStore } from '@/stores/contractors'
import type { ToastType } from '@/composables/useToast'
import type { GraphData, OrgLite } from './hierarchyTypes'

export interface HierarchyOrgDialogsOptions {
  lastGraphData: Ref<GraphData | null>
  showSnack: (text: string, color?: ToastType) => void
  loadGraph: () => Promise<void>
  isSuperadmin: boolean
}

export function useHierarchyOrgDialogs(opts: HierarchyOrgDialogsOptions) {
  const contractorsStore = useContractorsStore()

  // ── New org ──────────────────────────────────────────────────────────────────
  const newOrgDialog = ref({ show: false, name: '', full_name: '', inn: '', kpp: '', ogrn: '', address: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', loading: false })
  // 2026-09-01: аккаунт (головная организация) для новой org — только superadmin,
  // см. app/services/org_account_resolution.py на бэкенде.
  const newOrgAccountId = ref<number | null>(null)
  const newOrgAccountOptions = ref<{ id: number; name: string }[]>([])
  async function openNewOrgDialog() {
    newOrgDialog.value.show = true
    if (!opts.isSuperadmin) return
    try {
      newOrgAccountOptions.value = await apiFetch<{ id: number; name: string }[]>('/organizations/accounts')
    } catch {
      newOrgAccountOptions.value = []
    }
  }
  const newOrgEgrulLoading = ref(false)
  const newOrgEgrulMessage = ref('')
  const newOrgEgrulMessageType = ref<'success' | 'info' | 'error'>('info')
  const newOrgContractors = ref<any[]>([])
  const newOrgContractorId = ref<number | null>(null)
  let _newOrgContractorSearchTimeout: any = null

  const orgContractorFilter = (_value: string, query: string, item?: any): boolean => {
    const q = query.toLowerCase()
    const name = (item?.raw?.name || '').toLowerCase()
    const inn = (item?.raw?.inn || '').toLowerCase()
    return name.includes(q) || inn.includes(q)
  }
  function onNewOrgContractorSearch(query: string) {
    clearTimeout(_newOrgContractorSearchTimeout)
    if (!query || query.length < 2) return
    _newOrgContractorSearchTimeout = setTimeout(async () => {
      const list = await contractorsStore.search(query, 50)
      const existing = new Set(newOrgContractors.value.map((c: any) => c.id))
      for (const c of list) {
        if (!existing.has(c.id)) newOrgContractors.value.push(c)
      }
    }, 300)
  }
  function onNewOrgContractorSelect(id: number | null) {
    if (!id) return
    const c = newOrgContractors.value.find((x: any) => x.id === id)
    if (!c) return
    const d = newOrgDialog.value
    if (c.name && !d.name.trim()) d.name = c.name
    if (c.full_name && !d.full_name.trim()) d.full_name = c.full_name
    if (c.inn && !d.inn.trim()) d.inn = c.inn
    if (c.kpp && !d.kpp.trim()) d.kpp = c.kpp
    if (c.ogrn && !d.ogrn.trim()) d.ogrn = c.ogrn
    if (c.address && !d.address.trim()) d.address = c.address
    if (c.signatory && !(d as any).signatory.trim()) (d as any).signatory = c.signatory
    // ↑ поле signatory не объявлено в форме — сохранённая особенность исходника (не чиним).
  }

  async function createNewOrg() {
    const name = newOrgDialog.value.name.trim()
    if (!name) return
    newOrgDialog.value.loading = true
    try {
      const d = newOrgDialog.value
      const body: any = {
        name,
        full_name: d.full_name.trim() || null,
        inn: d.inn.trim() || null,
        kpp: d.kpp.trim() || null,
        ogrn: d.ogrn.trim() || null,
        address: d.address.trim() || null,
        signatory_last_name: d.signatory_last_name.trim() || null,
        signatory_first_name: d.signatory_first_name.trim() || null,
        signatory_middle_name: d.signatory_middle_name.trim() || null,
        signatory_position: d.signatory_position.trim() || null,
        contractor_id: newOrgContractorId.value || null,
        root_org_id: opts.isSuperadmin ? (newOrgAccountId.value || null) : null,
      }
      await apiFetch('/organizations/', { method: 'POST', body })
      opts.showSnack(`Организация "${name}" создана`)
      newOrgDialog.value = { show: false, name: '', full_name: '', inn: '', kpp: '', ogrn: '', address: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', loading: false }
      newOrgContractorId.value = null
      newOrgContractors.value = []
      newOrgEgrulMessage.value = ''
      newOrgAccountId.value = null
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка создания организации', 'error')
    } finally {
      newOrgDialog.value.loading = false
    }
  }

  async function enrichNewOrgFromEgrul() {
    const inn = newOrgDialog.value.inn.trim()
    if (!inn || inn.length < 10) return
    newOrgEgrulLoading.value = true
    newOrgEgrulMessage.value = ''
    try {
      const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
      if (data._source === 'npd') {
        newOrgEgrulMessage.value = data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`
        newOrgEgrulMessageType.value = 'warning' as any
        return
      }
      const d = newOrgDialog.value
      if (data.name && !d.name.trim()) d.name = data.name
      if (data.full_name) d.full_name = data.full_name
      if (data.kpp) d.kpp = data.kpp
      if (data.ogrn) d.ogrn = data.ogrn
      if (data.address) d.address = data.address
      if (data.signatory_last_name) d.signatory_last_name = data.signatory_last_name
      if (data.signatory_first_name) d.signatory_first_name = data.signatory_first_name
      if (data.signatory_middle_name) d.signatory_middle_name = data.signatory_middle_name
      if (data.signatory_position) d.signatory_position = data.signatory_position
      newOrgEgrulMessage.value = 'Данные заполнены из ЕГРЮЛ'
      newOrgEgrulMessageType.value = 'success'
    } catch (e: any) {
      if (e?.payload?.code === 'INN_NOT_FOUND') {
        newOrgEgrulMessage.value = e.payload.message
        newOrgEgrulMessageType.value = 'warning' as any
      } else {
        newOrgEgrulMessage.value = e?.message || 'Ошибка запроса к ФНС'
        newOrgEgrulMessageType.value = 'error'
      }
    } finally {
      newOrgEgrulLoading.value = false
    }
  }

  // ── Edit org ─────────────────────────────────────────────────────────────────
  const editOrgDialog = ref({ show: false, id: 0, name: '', full_name: '', inn: '', kpp: '', ogrn: '', address: '', signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '', contractor_id: null as number | null })
  const editOrgContractors = ref<any[]>([])
  const editOrgContractorId = ref<number | null>(null)
  let _editOrgContractorSearchTimeout: any = null
  const editOrgEgrulLoading = ref(false)
  const editOrgEgrulMessage = ref('')
  const editOrgEgrulMessageType = ref<'success' | 'info' | 'error'>('info')

  function onEditOrgContractorSearch(query: string) {
    clearTimeout(_editOrgContractorSearchTimeout)
    if (!query || query.length < 2) return
    _editOrgContractorSearchTimeout = setTimeout(async () => {
      const list = await contractorsStore.search(query, 50)
      const existing = new Set(editOrgContractors.value.map((c: any) => c.id))
      for (const c of list) {
        if (!existing.has(c.id)) editOrgContractors.value.push(c)
      }
    }, 300)
  }
  function onEditOrgContractorSelect(id: number | null) {
    if (!id) return
    const c = editOrgContractors.value.find((x: any) => x.id === id)
    if (!c) return
    const d = editOrgDialog.value
    d.contractor_id = id
    if (c.name) d.name = c.name
    if (c.full_name) d.full_name = c.full_name
    if (c.inn) d.inn = c.inn
    if (c.kpp) d.kpp = c.kpp
    if (c.ogrn) d.ogrn = c.ogrn
    if (c.address) d.address = c.address
    if (c.signatory) (d as any).signatory = c.signatory
  }

  async function saveOrg() {
    try {
      const d = editOrgDialog.value
      await apiFetch(`/organizations/${d.id}`, {
        method: 'PUT',
        body: {
          name: d.name,
          full_name: d.full_name || null,
          inn: d.inn || null,
          kpp: d.kpp || null,
          ogrn: d.ogrn || null,
          address: d.address || null,
          signatory_last_name: d.signatory_last_name || null,
          signatory_first_name: d.signatory_first_name || null,
          signatory_middle_name: d.signatory_middle_name || null,
          signatory_position: d.signatory_position || null,
          contractor_id: d.contractor_id ?? null,
        },
      })
      editOrgDialog.value.show = false
      opts.showSnack('Организация обновлена')
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка сохранения', 'error')
    }
  }

  async function enrichEditOrgFromEgrul() {
    const inn = editOrgDialog.value.inn.trim()
    if (!inn || inn.length < 10) return
    editOrgEgrulLoading.value = true
    editOrgEgrulMessage.value = ''
    try {
      const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
      if (data._source === 'npd') {
        editOrgEgrulMessage.value = data._notice || `ИНН ${inn} — самозанятый, данных в ЕГРЮЛ нет`
        editOrgEgrulMessageType.value = 'warning'
        return
      }
      const d = editOrgDialog.value
      if (data.full_name) d.full_name = data.full_name
      if (data.kpp) d.kpp = data.kpp
      if (data.ogrn) d.ogrn = data.ogrn
      if (data.address) d.address = data.address
      if (data.signatory_last_name) d.signatory_last_name = data.signatory_last_name
      if (data.signatory_first_name) d.signatory_first_name = data.signatory_first_name
      if (data.signatory_middle_name) d.signatory_middle_name = data.signatory_middle_name
      if (data.signatory_position) d.signatory_position = data.signatory_position
      editOrgEgrulMessage.value = 'Данные обновлены из ЕГРЮЛ'
      editOrgEgrulMessageType.value = 'success'
    } catch (e: any) {
      if (e?.payload?.code === 'INN_NOT_FOUND') {
        editOrgEgrulMessage.value = e.payload.message
        editOrgEgrulMessageType.value = 'warning'
      } else {
        editOrgEgrulMessage.value = e?.message || 'Ошибка запроса к ФНС'
        editOrgEgrulMessageType.value = 'error'
      }
    } finally {
      editOrgEgrulLoading.value = false
    }
  }

  // Единая карточка контрагента (для организаций, привязанных к контрагенту)
  const contractorDialog = ref({ show: false, contractorId: null as number | null })
  async function onContractorSaved() {
    contractorDialog.value.show = false
    await opts.loadGraph()
  }

  // Двойной клик по орг-узлу графа → либо карточка контрагента, либо fallback-редактор.
  function openOrgDetail(org: OrgLite) {
    const o = org as any
    // Если организация привязана к контрагенту — открываем единую богатую карточку
    // контрагента (то же хранилище, что и на странице «Контрагенты»).
    if (o.contractor_id) {
      contractorDialog.value = { show: true, contractorId: o.contractor_id }
      return
    }
    // Иначе — fallback: урезанный диалог редактирования организации
    editOrgDialog.value = {
      show: true, id: o.id,
      name: o.name || '', full_name: o.full_name || '',
      inn: o.inn || '', kpp: o.kpp || '', ogrn: o.ogrn || '',
      address: o.address || '',
      signatory_last_name: o.signatory_last_name || '',
      signatory_first_name: o.signatory_first_name || '',
      signatory_middle_name: o.signatory_middle_name || '',
      signatory_position: o.signatory_position || '',
      contractor_id: o.contractor_id ?? null,
    }
    editOrgEgrulMessage.value = ''
    // Best-effort prefill empty fields via lookup-inn (no force_egrul)
    if (!o.contractor_id && o.inn) {
      apiFetch<Record<string, any>>(`/contractors/lookup-inn/${o.inn.trim()}`).then(data => {
        const fill = (key: keyof typeof editOrgDialog.value, value: any) => {
          if (!((editOrgDialog.value as any)[key] || '').toString().trim() && value) {
            ;(editOrgDialog.value as any)[key] = value
          }
        }
        fill('full_name', data.full_name)
        fill('kpp', data.kpp)
        fill('ogrn', data.ogrn)
        fill('address', data.address)
        fill('signatory_last_name', data.signatory_last_name)
        fill('signatory_first_name', data.signatory_first_name)
        fill('signatory_middle_name', data.signatory_middle_name)
        fill('signatory_position', data.signatory_position)
      }).catch(() => { /* silent best-effort */ })
    }
  }

  // ── Delete org ───────────────────────────────────────────────────────────────
  const deleteOrgConfirm = ref<{ show: boolean; orgId: number | null; name: string; loading: boolean; impact: any | null; loadingImpact: boolean; forceAck: boolean }>({ show: false, orgId: null, name: '', loading: false, impact: null, loadingImpact: false, forceAck: false })

  async function deleteOrgNode(orgId: number, name: string) {
    deleteOrgConfirm.value = { show: true, orgId, name, loading: false, impact: null, loadingImpact: true, forceAck: false }
    try {
      const imp = await apiFetch(`/organizations/${orgId}/delete-impact`)
      deleteOrgConfirm.value.impact = imp
    } catch {
      deleteOrgConfirm.value.impact = null
    } finally {
      deleteOrgConfirm.value.loadingImpact = false
    }
  }
  async function confirmDeleteOrg() {
    const { orgId } = deleteOrgConfirm.value
    if (!orgId) return
    deleteOrgConfirm.value.loading = true
    try {
      const needsForce = !!deleteOrgConfirm.value.impact?.has_dependencies
      await apiFetch(`/organizations/${orgId}${needsForce ? '?force=true' : ''}`, { method: 'DELETE' })
      opts.showSnack('Организация удалена')
      deleteOrgConfirm.value.show = false
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка удаления организации', 'error')
    } finally {
      deleteOrgConfirm.value.loading = false
    }
  }

  return {
    contractorsStore,
    newOrgDialog, newOrgAccountId, newOrgAccountOptions, openNewOrgDialog,
    newOrgEgrulLoading, newOrgEgrulMessage, newOrgEgrulMessageType,
    newOrgContractors, newOrgContractorId, orgContractorFilter,
    onNewOrgContractorSearch, onNewOrgContractorSelect, createNewOrg, enrichNewOrgFromEgrul,
    editOrgDialog, editOrgContractors, editOrgContractorId,
    editOrgEgrulLoading, editOrgEgrulMessage, editOrgEgrulMessageType,
    onEditOrgContractorSearch, onEditOrgContractorSelect, saveOrg, enrichEditOrgFromEgrul,
    contractorDialog, onContractorSaved, openOrgDetail,
    deleteOrgConfirm, deleteOrgNode, confirmDeleteOrg,
  }
}
