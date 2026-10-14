// Диалоги перед скачиванием документов: выбор закрывающих документов для СЗ на
// оплату/аванс (Phase 27.2-02) и выбор согласующих/инициатора перед скачиванием
// листа согласования или служебной записки. Вынесено из CreateOrderView.vue без
// изменения поведения — те же apiFetch-пути. downloadDoc() остаётся в
// CreateOrderView.vue и передаётся сюда колбэком.
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface DocApprover {
  id: number; role_name: string; full_name: string; order_num: number; is_default: boolean; can_initiate: boolean
}

interface OrgUserLike { id: number; full_name: string; short_name: string; position?: string | null; name?: string }

type DocType = 'service_note_procurement' | 'service_note_delivery' | 'service_note_payment' | 'service_note_advance' | 'approval_sheet'
type AcceptanceDocType = 'service_note_payment' | 'service_note_advance'

export function useDocPickerDialogs(
  form: Record<string, any>,
  purchaseId: ComputedRef<number | null>,
  acceptanceDocs: Ref<{ name: string; number: string; date: string; amount: number | null; file_id?: number | null }[]>,
  orgUsersList: Ref<OrgUserLike[]>,
  loadOrgUsers: () => Promise<void>,
  currentUserId: number,
  pickerResponsibleName: Ref<string>,
  loadResponsiblePersonsList: () => Promise<void>,
  downloadDoc: (docType: string, extraParams?: string, loadingKey?: string) => Promise<void>,
  toShortName: (fullName: string) => string,
) {
  // ── Phase 27.2-02: Acceptance doc picker (select closing docs before СЗ download) ──
  const acceptanceDocPickerDialog   = ref(false)
  const acceptanceDocPickerDocType  = ref<AcceptanceDocType>('service_note_payment')
  const acceptanceDocPickerSelected = ref<number[]>([])
  // pending initiator_id to append after acceptance doc selection
  const acceptanceDocPickerInitiatorId = ref<number | null>(null)

  async function openAcceptanceDocPicker(type: AcceptanceDocType, initiatorId: number | null) {
    if (acceptanceDocs.value.length > 1) {
      acceptanceDocPickerDocType.value = type
      acceptanceDocPickerInitiatorId.value = initiatorId
      // Default: all selected
      acceptanceDocPickerSelected.value = acceptanceDocs.value.map((_, i) => i)
      acceptanceDocPickerDialog.value = true
    } else {
      // Single or zero docs — skip picker, download directly
      const params = initiatorId ? `?initiator_id=${initiatorId}` : ''
      await downloadDoc(type, params)
    }
  }

  async function confirmAcceptanceDocDownload() {
    acceptanceDocPickerDialog.value = false
    const type = acceptanceDocPickerDocType.value
    const initiatorId = acceptanceDocPickerInitiatorId.value
    const indices = [...acceptanceDocPickerSelected.value].sort((a, b) => a - b)
    const parts: string[] = []
    if (initiatorId) parts.push(`initiator_id=${initiatorId}`)
    if (indices.length && indices.length < acceptanceDocs.value.length) {
      parts.push(`doc_indices=${indices.join(',')}`)
    }
    await downloadDoc(type, parts.length ? `?${parts.join('&')}` : '')
  }

  // ── Doc picker (approver selection before download) ──
  const docPickerDialog      = ref(false)
  const docPickerType        = ref<DocType>('approval_sheet')
  const loadingDocApprovers  = ref(false)
  const docApprovers         = ref<DocApprover[]>([])
  const pickerApproverIds    = ref<number[]>([])
  const pickerInitiatorId    = ref<number | null>(null)
  const docApproversInitiators = computed(() => docApprovers.value.filter(a => a.can_initiate))

  // Список «кого можно указать инициатором служебной записки» — «штат»
  // организации субсидии, сокращённый по роли выбирающего (backend
  // app/services/service_note_initiators.py::initiator_candidate_ids,
  // правило владельца 14.10.2026). Без subsidyId — старое поведение
  // (себя + видимых через _get_visible_user_ids), для мест, где субсидия
  // ещё не выбрана.
  const actAsList = ref<OrgUserLike[]>([])
  async function loadActAsUsers(subsidyId?: number | string | null) {
    try {
      const qs = subsidyId ? `?subsidy_id=${subsidyId}` : ''
      const users = await apiFetch<any[]>(`/users/i-can-act-for${qs}`)
      actAsList.value = users
        .filter(u => u.full_name)
        .map(u => ({ id: u.id, full_name: u.full_name, short_name: toShortName(u.full_name), position: u.position }))
    } catch { actAsList.value = [] }
  }

  async function openDocPicker(type: DocType) {
    if (!purchaseId.value || !form.subsidy_id) {
      downloadDoc(type)
      return
    }
    docPickerType.value = type
    docPickerDialog.value = true
    loadingDocApprovers.value = true
    // Pre-fill responsible person from the purchase form.
    // Приоритет: form.responsible_person (legacy строковое поле) → ФИО юзера из form.assigned_user_id.
    let prefillName = (form.responsible_person || '').trim()
    if (!prefillName && form.assigned_user_id) {
      const u = orgUsersList.value.find((x: any) => x.id === form.assigned_user_id)
      prefillName = (u?.full_name || u?.name || '').trim()
    }
    pickerResponsibleName.value = prefillName
    try {
      if (type.startsWith('service_note')) {
        // service_note: согласующие субсидии инициатору не нужны (служебка —
        // до согласования) — approvers не запрашиваем/не ждём, только пул
        // инициаторов (правило владельца, 14.10.2026, см. loadActAsUsers).
        docApprovers.value = []
        await Promise.all([
          loadActAsUsers(form.subsidy_id),
          orgUsersList.value.length ? Promise.resolve() : loadOrgUsers(),
        ])
        if (form.service_note_by && actAsList.value.find(u => u.id === form.service_note_by)) {
          pickerInitiatorId.value = form.service_note_by
        } else if (currentUserId && actAsList.value.find(u => u.id === currentUserId)) {
          pickerInitiatorId.value = currentUserId
        } else {
          pickerInitiatorId.value = null
        }
      } else {
        const [list] = await Promise.all([
          apiFetch<DocApprover[]>(`/subsidies/${form.subsidy_id}/approvers`),
          loadResponsiblePersonsList(),
          orgUsersList.value.length ? Promise.resolve() : loadOrgUsers(),
        ])
        docApprovers.value = list
        pickerApproverIds.value = list.filter(a => a.is_default).map(a => a.id)
      }
    } catch {
      docApprovers.value = []
    } finally {
      loadingDocApprovers.value = false
    }
  }

  async function confirmDocDownload() {
    // Capture values BEFORE closing dialog
    const type = docPickerType.value
    const approverIds = [...pickerApproverIds.value]
    const responsibleName = pickerResponsibleName.value
    const initiatorId = pickerInitiatorId.value
    docPickerDialog.value = false

    if (type === 'service_note_payment' || type === 'service_note_advance') {
      // Phase 27.2-02: если несколько закр.документов — показать picker
      await openAcceptanceDocPicker(type, initiatorId)
    } else if (type.startsWith('service_note')) {
      const params = initiatorId ? `?initiator_id=${initiatorId}` : ''
      await downloadDoc(type, params)
    } else {
      const parts: string[] = []
      if (approverIds.length) parts.push(`approver_ids=${approverIds.join(',')}`)
      if (responsibleName) parts.push(`responsible_name=${encodeURIComponent(responsibleName)}`)
      console.log('[DOC] approval_sheet params:', parts, 'approverIds:', approverIds)
      await downloadDoc('approval_sheet', parts.length ? `?${parts.join('&')}` : '')
    }
  }

  return {
    acceptanceDocPickerDialog, acceptanceDocPickerDocType, acceptanceDocPickerSelected, acceptanceDocPickerInitiatorId,
    openAcceptanceDocPicker, confirmAcceptanceDocDownload,
    docPickerDialog, docPickerType, loadingDocApprovers, docApprovers, pickerApproverIds, pickerInitiatorId,
    docApproversInitiators, actAsList, loadActAsUsers, openDocPicker, confirmDocDownload,
  }
}
