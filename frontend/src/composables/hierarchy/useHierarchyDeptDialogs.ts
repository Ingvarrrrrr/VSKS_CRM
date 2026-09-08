// Диалоги отдела: создать, добавить сотрудника, удалить.
// Вынесено из HierarchyView.vue без изменения логики.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { GraphData } from './hierarchyTypes'

export interface HierarchyDeptDialogsOptions {
  lastGraphData: Ref<GraphData | null>
  showSnack: (text: string, color?: ToastType) => void
  loadGraph: () => Promise<void>
  onCreateUser: (ctx?: { orgId?: number; departmentName?: string }) => void
}

export function useHierarchyDeptDialogs(opts: HierarchyDeptDialogsOptions) {
  // ── New dept ─────────────────────────────────────────────────────────────────
  const newDeptDialog = ref({ show: false, name: '', orgId: null as number | null })

  // Вызывается графом при загрузке, если в контуре ровно одна организация —
  // выбираем её отделом по умолчанию (идемпотентно: только если ещё не выбрано).
  function setDefaultDeptOrgId(orgId: number) {
    if (newDeptDialog.value.orgId === null) newDeptDialog.value.orgId = orgId
  }

  async function createNewDept() {
    const name = newDeptDialog.value.name.trim()
    if (!name) return
    try {
      const body: any = { name }
      if (newDeptDialog.value.orgId) body.org_id = newDeptDialog.value.orgId
      await apiFetch('/departments/', { method: 'POST', body })
      opts.showSnack(`Отдел "${name}" создан`)
      newDeptDialog.value = { show: false, name: '', orgId: newDeptDialog.value.orgId }
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка создания отдела', 'error')
    }
  }

  // ── Add member ───────────────────────────────────────────────────────────────
  const addMemberDialog = ref<{ show: boolean; deptId: number | null; available: { id: number; label: string }[] }>({
    show: false, deptId: null, available: [],
  })
  const addMemberSelectedId = ref<number | null>(null)
  const addMemberLoading = ref(false)

  function openAddMemberDialog(deptId: number, available: { id: number; label: string }[]) {
    addMemberDialog.value = { show: true, deptId, available }
    addMemberSelectedId.value = null
  }

  // Владелец, 2026-09-01: «Создать нового» из диалога «добавить в отдел» обязан
  // передать орг/отдел этого диалога дальше в форму создания сотрудника —
  // раньше уходил голый emit('create-user') без контекста, и оба поля
  // оставались пустыми, хотя отдел (и его орг) уже выбраны кликом по «+».
  function onCreateFromAddMember() {
    const deptId = addMemberDialog.value.deptId
    const dept = deptId != null
      ? opts.lastGraphData.value?.departments.find(d => d.id === deptId)
      : null
    addMemberDialog.value.show = false
    opts.onCreateUser(dept ? { orgId: dept.org_id, departmentName: dept.name } : undefined)
  }

  async function confirmAddMember() {
    const { deptId } = addMemberDialog.value
    const userId = addMemberSelectedId.value
    if (!deptId || !userId) return
    addMemberLoading.value = true
    try {
      await apiFetch(`/departments/${deptId}/members`, { method: 'POST', body: { user_id: userId } })
      opts.showSnack('Сотрудник добавлен в отдел')
      addMemberDialog.value.show = false
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка добавления', 'error')
    } finally {
      addMemberLoading.value = false
    }
  }

  // ── Delete dept ──────────────────────────────────────────────────────────────
  const deleteDeptConfirm = ref<{ show: boolean; deptId: number | null; name: string }>({ show: false, deptId: null, name: '' })

  function deleteDeptNode(deptId: number, name: string) {
    deleteDeptConfirm.value = { show: true, deptId, name }
  }

  async function confirmDeleteDept() {
    const { deptId } = deleteDeptConfirm.value
    if (!deptId) return
    try {
      await apiFetch(`/departments/${deptId}`, { method: 'DELETE' })
      opts.showSnack('Отдел удалён')
      deleteDeptConfirm.value.show = false
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка удаления отдела', 'error')
    }
  }

  return {
    newDeptDialog, setDefaultDeptOrgId, createNewDept,
    addMemberDialog, addMemberSelectedId, addMemberLoading,
    openAddMemberDialog, onCreateFromAddMember, confirmAddMember,
    deleteDeptConfirm, deleteDeptNode, confirmDeleteDept,
  }
}
