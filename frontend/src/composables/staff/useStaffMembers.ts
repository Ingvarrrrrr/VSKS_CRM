// useStaffMembers.ts — добавление/редактирование/удаление участников отдела,
// делегирование прав на задачи. Дословный перенос из StaffView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { unformatPhone } from '@/utils/phoneFormat'
import type { ToastType } from '@/composables/useToast'

export function useStaffMembers(options: {
  showSnack: (text: string, color?: ToastType) => void
  selectedDept: { value: any }
  loadDeptMembers: (deptId: number) => Promise<void>
  loadDeptTree: () => Promise<void>
  loadDelegates: () => Promise<void>
  loadUsers: () => Promise<void>
  openEditUserById: (userId: number) => Promise<void> | void
}) {
  const { showSnack, selectedDept, loadDeptMembers, loadDeptTree, loadDelegates, loadUsers, openEditUserById } = options

  // Member dialog
  const addMemberDialog = ref(false)
  const addMemberMode = ref<'existing' | 'new'>('existing')
  const memberForm = ref({ user_id: null as number | null, position: '' })
  const newMemberForm = ref({ email: '', last_name: '', first_name: '', middle_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' })
  const newMemberSaving = ref(false)

  // Edit member position dialog
  const editMemberDialog = ref(false)
  const editMemberTarget = ref<any>(null)
  const editMemberForm = ref({ position: '' })

  // Delegate dialog
  const delegateDialog = ref(false)
  const delegateForm = ref({ target_user_id: null as number | null, delegate_user_id: null as number | null })

  async function addMember() {
    if (!selectedDept.value || !memberForm.value.user_id) return
    try {
      await apiFetch(`/departments/${selectedDept.value.id}/members`, {
        method: 'POST', body: JSON.stringify(memberForm.value),
      })
      addMemberDialog.value = false
      memberForm.value = { user_id: null, position: '' }
      await loadDeptMembers(selectedDept.value.id)
      await loadDeptTree()
      showSnack('Сотрудник добавлен в отдел')
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function createAndAddMember() {
    if (!selectedDept.value) return
    newMemberSaving.value = true
    try {
      // 1. Create user
      const user = await apiFetch<any>('/users/', {
        method: 'POST',
        body: JSON.stringify({
          email: newMemberForm.value.email,
          password: newMemberForm.value.password,
          last_name: newMemberForm.value.last_name,
          first_name: newMemberForm.value.first_name,
          middle_name: newMemberForm.value.middle_name || null,
          role: newMemberForm.value.role,
          city: newMemberForm.value.city || null,
          phone: unformatPhone(newMemberForm.value.phone) || null,
          department: selectedDept.value.name,
          position: newMemberForm.value.position || null,
          // Орг сотрудника = орг отдела, куда добавляем (напр. Донецкое), а не своя
          // орг вызывающего. Иначе backend ставил org_id = current_user.org_id (ВСКС).
          org_id: selectedDept.value.org_id ?? null,
        }),
      })
      // 2. Add to department
      await apiFetch(`/departments/${selectedDept.value.id}/members`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user.id, position: newMemberForm.value.position || null }),
      })
      addMemberDialog.value = false
      newMemberForm.value = { email: '', last_name: '', first_name: '', middle_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' }
      // Refresh all
      await Promise.all([loadUsers(), loadDeptMembers(selectedDept.value.id), loadDeptTree()])
      showSnack(`Сотрудник ${user.full_name || user.username} создан и добавлен в отдел`)
    } catch (e: any) {
      showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка при создании сотрудника', 'error')
    } finally {
      newMemberSaving.value = false
    }
  }

  async function removeMember(userId: number) {
    if (!selectedDept.value) return
    try {
      await apiFetch(`/departments/${selectedDept.value.id}/members/${userId}`, { method: 'DELETE' })
      await loadDeptMembers(selectedDept.value.id)
      await loadDeptTree()
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  // Inline handlers for tree buttons
  function onAddMemberInline(dept: any) {
    selectedDept.value = dept
    memberForm.value = { user_id: null, position: '' }
    newMemberForm.value = { email: '', last_name: '', first_name: '', middle_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' }
    addMemberMode.value = 'existing'
    addMemberDialog.value = true
  }

  function onEditMemberInline(payload: { dept: any; member: any; fullEdit?: boolean }) {
    if (payload.fullEdit) {
      // Open full user edit dialog instead of position-only dialog
      openEditUserById(payload.member.user_id)
      return
    }
    selectedDept.value = payload.dept
    editMemberTarget.value = payload.member
    editMemberForm.value = { position: payload.member.position || '' }
    editMemberDialog.value = true
  }

  async function onRemoveMemberInline(payload: { deptId: number; userId: number }) {
    try {
      await apiFetch(`/departments/${payload.deptId}/members/${payload.userId}`, { method: 'DELETE' })
      await loadDeptTree()
      if (selectedDept.value?.id === payload.deptId) {
        await loadDeptMembers(payload.deptId)
      }
      showSnack('Сотрудник убран из отдела')
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function saveEditMember() {
    if (!selectedDept.value || !editMemberTarget.value) return
    try {
      await apiFetch(`/departments/${selectedDept.value.id}/members/${editMemberTarget.value.user_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ position: editMemberForm.value.position }),
      })
      editMemberDialog.value = false
      await loadDeptTree()
      if (selectedDept.value) await loadDeptMembers(selectedDept.value.id)
      showSnack('Должность обновлена')
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function addDelegate() {
    try {
      await apiFetch('/departments/delegates', { method: 'POST', body: JSON.stringify(delegateForm.value) })
      delegateDialog.value = false
      delegateForm.value = { target_user_id: null, delegate_user_id: null }
      await loadDelegates()
      showSnack('Делегирование добавлено')
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function removeDelegate(id: number) {
    try {
      await apiFetch(`/departments/delegates/${id}`, { method: 'DELETE' })
      await loadDelegates()
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  return {
    addMemberDialog, addMemberMode, memberForm, newMemberForm, newMemberSaving,
    editMemberDialog, editMemberTarget, editMemberForm,
    delegateDialog, delegateForm,
    addMember, createAndAddMember, removeMember,
    onAddMemberInline, onEditMemberInline, onRemoveMemberInline, saveEditMember,
    addDelegate, removeDelegate,
  }
}
