// Состояние и CRUD согласующих субсидии, общее для трёх диалогов
// (SubsidyApproversDialog/SubsidyApproverFormDialog/SubsidyCopyApproversDialog) —
// вынесено из SubsidiesView.vue. Module-level singleton state, как
// useApprovalsBadge.ts/useToast.ts в этом же проекте: все три компонента,
// вызывая useSubsidyApprovers(), получают ОДНО и то же реактивное состояние,
// без прокидывания через props/emit между диалогом списка и формой.
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { SubsidyApprover, SubsidyRow } from './types'

export const ROLE_SUGGESTIONS = [
  'Первый заместитель руководителя',
  'Куратор проекта',
  'Ответственный исполнитель',
  'Юрист',
  'Главный бухгалтер',
  'Начальник отдела МТО',
  'Заместитель руководителя по ФХД',
]

export const approversHeaders = [
  { title: '#', key: 'order_num', width: '60px', sortable: false },
  { title: 'Роль / Должность', key: 'role_name', sortable: false },
  { title: 'ФИО', key: 'full_name', sortable: false },
  { title: '', key: 'is_default', width: '120px', sortable: false },
  { title: '', key: 'can_initiate', width: '100px', sortable: false },
  { title: '', key: 'actions', width: '110px', sortable: false },
]

const RESPONSIBLE_PLACEHOLDER = '_________________'

// ── Approvers state ──
const showApproversDialog    = ref(false)
const showApproverFormDialog = ref(false)
const loadingApprovers       = ref(false)
const savingApprover         = ref(false)
const approversSubsidy       = ref<SubsidyRow | null>(null)
const approversList          = ref<SubsidyApprover[]>([])
const approverEditTarget     = ref<SubsidyApprover | null>(null)
const approverForm = ref<{
  role_name: string
  full_name: string
  order_num: number
  is_default: boolean
  can_initiate: boolean
  show_feo_path: boolean
  user_id: number | null
  selectedUser: { id: number; full_name: string } | null
}>({ role_name: '', full_name: '', order_num: 0, is_default: true, can_initiate: false, show_feo_path: false, user_id: null, selectedUser: null })

const approverUsersList = ref<Array<{ id: number; full_name: string }>>([])

// ── Copy Approvers state ──
const showCopyApproversDialog = ref(false)
const copyApprovers = ref<{ sourceId: number | null; replace: boolean; loading: boolean; error: string }>({
  sourceId: null, replace: false, loading: false, error: '',
})

let _approverUsersSubsidyId: number | null = null

// ctx — опциональный: провайдится через provideSubsidyDetail() в SubsidiesView.vue
// (родителе), а inject() не резолвит собственный provide() того же компонента —
// поэтому САМ SubsidiesView.vue вызывает useSubsidyApprovers() без аргумента
// (нужны только openApproversDialog/contractTemplates-подобные части, ctx не нужен),
// а SubsidyCopyApproversDialog.vue — настоящий потомок, вызывает
// useSubsidyApprovers(useSubsidyDetailCtx()), передавая свой корректно
// заинжекченный контекст для copySourceSubsidies.
export function useSubsidyApprovers(ctx?: SubsidyDetailContext) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
    toast.addToast(text, color, opts)
  }

  const copySourceSubsidies = computed(() =>
    (ctx?.allSubsidies.value || []).filter(s => s.id !== approversSubsidy.value?.id)
  )

  function openCopyApproversDialog() {
    copyApprovers.value = { sourceId: null, replace: false, loading: false, error: '' }
    showCopyApproversDialog.value = true
  }

  async function confirmCopyApprovers() {
    if (!approversSubsidy.value?.id || !copyApprovers.value.sourceId) return
    copyApprovers.value.loading = true
    copyApprovers.value.error = ''
    try {
      const result = await apiFetch<{ copied: number; replaced: boolean }>(
        `/subsidies/${approversSubsidy.value.id}/approvers/copy-from/${copyApprovers.value.sourceId}?replace=${copyApprovers.value.replace}`,
        { method: 'POST' }
      )
      showCopyApproversDialog.value = false
      showSnack(`Скопировано: ${result.copied} согласующих${result.replaced ? ' (с заменой)' : ''}`, 'success')
      const list = await apiFetch<SubsidyApprover[]>(`/subsidies/${approversSubsidy.value.id}/approvers`)
      approversList.value = list
    } catch (e: any) {
      copyApprovers.value.error = e?.payload?.message || e?.message || 'Ошибка копирования'
    } finally {
      copyApprovers.value.loading = false
    }
  }

  async function loadApproverUsers() {
    // Согласующим может быть только сотрудник орг(а) субсидии или человек
    // с персональным доступом к ней — не весь контур.
    const sid = approversSubsidy.value?.id ?? null
    if (approverUsersList.value.length && _approverUsersSubsidyId === sid) return
    try {
      const data = await apiFetch<any[]>(`/users/${sid ? `?subsidy_id=${sid}` : ''}`)
      approverUsersList.value = data
      _approverUsersSubsidyId = sid
    } catch { approverUsersList.value = [] }
  }

  async function openApproversDialog(s: SubsidyRow) {
    approversSubsidy.value = s
    showApproversDialog.value = true
    loadingApprovers.value = true
    try {
      const list = await apiFetch<SubsidyApprover[]>(`/subsidies/${s.id}/approvers`)
      approversList.value = list
      // Fix any duplicate order_nums silently
      const hasDuplicates = list.some((a: SubsidyApprover, i: number) => a.order_num !== i + 1)
      if (hasDuplicates) await _renumberApprovers()
    } catch {
      showSnack('Ошибка загрузки согласующих', 'error')
    } finally {
      loadingApprovers.value = false
    }
  }

  function onApproverRoleChange(role: string) {
    if (role === 'Ответственный исполнитель') {
      approverForm.value.full_name = RESPONSIBLE_PLACEHOLDER
      approverForm.value.selectedUser = null
      approverForm.value.user_id = null
    }
  }

  function onApproverUserSelect(user: { id: number; full_name: string } | null) {
    if (user) {
      approverForm.value.full_name = user.full_name
      approverForm.value.user_id = user.id
    } else {
      approverForm.value.full_name = ''
      approverForm.value.user_id = null
    }
  }

  function startAddApprover() {
    approverEditTarget.value = null
    approverForm.value = { role_name: '', full_name: '', order_num: approversList.value.length + 1, is_default: true, can_initiate: false, show_feo_path: false, user_id: null, selectedUser: null }
    loadApproverUsers()
    showApproverFormDialog.value = true
  }

  function startEditApprover(a: SubsidyApprover) {
    approverEditTarget.value = a
    // «Ответственный исполнитель» — роль-слот: ФИО определяется по каждой
    // закупке, а не хранится фиксированным в настройках субсидии. Даже если
    // в БД у старой записи оказалось живое ФИО (баг, почищен миграцией
    // g8h9i0j1k2l3), форма редактирования не должна его снова показывать и
    // молча сохранять обратно — иначе правка любого другого поля этой строки
    // (например order_num) вернула бы фиксированное ФИО.
    const isResponsibleRole = a.role_name === 'Ответственный исполнитель'
    const foundUser = (!isResponsibleRole && a.user_id)
      ? (approverUsersList.value.find(u => u.id === a.user_id) ?? null)
      : null
    approverForm.value = {
      role_name: a.role_name,
      full_name: isResponsibleRole ? RESPONSIBLE_PLACEHOLDER : a.full_name,
      order_num: a.order_num,
      is_default: a.is_default,
      can_initiate: a.can_initiate,
      show_feo_path: a.show_feo_path ?? false,
      user_id: isResponsibleRole ? null : (a.user_id ?? null),
      selectedUser: foundUser,
    }
    loadApproverUsers().then(() => {
      // re-resolve after load in case list was empty when dialog opened
      if (!isResponsibleRole && a.user_id && !approverForm.value.selectedUser) {
        approverForm.value.selectedUser = approverUsersList.value.find(u => u.id === a.user_id) ?? null
      }
    })
    showApproverFormDialog.value = true
  }

  async function saveApprover() {
    if (!approversSubsidy.value) return
    savingApprover.value = true
    const sid = approversSubsidy.value.id
    const { selectedUser: _su, ...formData } = approverForm.value
    try {
      if (approverEditTarget.value) {
        const updated = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers/${approverEditTarget.value.id}`, {
          method: 'PUT',
          body: JSON.stringify(formData),
        })
        const idx = approversList.value.findIndex(a => a.id === updated.id)
        if (idx >= 0) approversList.value[idx] = updated
      } else {
        const created = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers`, {
          method: 'POST',
          body: JSON.stringify(formData),
        })
        approversList.value.push(created)
      }
      showApproverFormDialog.value = false
      showSnack(approverEditTarget.value ? 'Обновлено' : 'Добавлено')
    } catch (e: any) {
      console.error('saveApprover failed:', e)
      showSnack('Ошибка сохранения', 'error')
    } finally {
      savingApprover.value = false
    }
  }

  async function deleteApprover(a: SubsidyApprover) {
    if (!approversSubsidy.value) return
    try {
      await apiFetch(`/subsidies/${approversSubsidy.value.id}/approvers/${a.id}`, { method: 'DELETE' })
      approversList.value = approversList.value.filter(x => x.id !== a.id)
      await _renumberApprovers()
      showSnack('Удалено', 'warning')
    } catch {
      showSnack('Ошибка удаления', 'error')
    }
  }

  async function moveApprover(index: number, direction: -1 | 1) {
    const list = approversList.value
    const swapIdx = index + direction
    if (swapIdx < 0 || swapIdx >= list.length) return
    // Swap in local list
    const tmp = list[index]!
    list[index] = list[swapIdx]!
    list[swapIdx] = tmp
    approversList.value = [...list]
    await _renumberApprovers()
  }

  async function _renumberApprovers() {
    if (!approversSubsidy.value) return
    const sid = approversSubsidy.value.id
    for (let i = 0; i < approversList.value.length; i++) {
      const a = approversList.value[i]!
      if (a.order_num !== i + 1) {
        try {
          const updated = await apiFetch<SubsidyApprover>(`/subsidies/${sid}/approvers/${a.id}`, {
            method: 'PUT',
            body: JSON.stringify({ ...a, order_num: i + 1 }),
          })
          approversList.value[i] = updated
        } catch {}
      }
    }
  }

  return {
    showApproversDialog, showApproverFormDialog, loadingApprovers, savingApprover,
    approversSubsidy, approversList, approverEditTarget, approverForm, approverUsersList,
    showCopyApproversDialog, copyApprovers, copySourceSubsidies,
    openCopyApproversDialog, confirmCopyApprovers, loadApproverUsers, openApproversDialog,
    onApproverRoleChange, onApproverUserSelect, startAddApprover, startEditApprover,
    saveApprover, deleteApprover, moveApprover,
  }
}
