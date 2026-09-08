// useStaffDepartments.ts — вкладка «Отделы»: дерево, фильтры, диалог
// создания/редактирования отдела. Дословный перенос из StaffView.vue.
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export function flatDepts(nodes: any[]): any[] {
  const out: any[] = []
  for (const n of nodes) {
    out.push(n)
    if (n.children) out.push(...flatDepts(n.children))
  }
  return out
}

export function useStaffDepartments(options: {
  showSnack: (text: string, color?: ToastType) => void
  dictsCache: { value: Record<number, any> }
  knownDepartments: { value: string[] }
  loadDicts: (orgId?: number | null) => Promise<void>
  refreshHierarchy: () => void
}) {
  const { showSnack, dictsCache, knownDepartments, loadDicts, refreshHierarchy } = options

  const deptLoading = ref(false)
  const deptTree = ref<any[]>([])
  const selectedDept = ref<any>(null)
  const deptMembers = ref<any[]>([])
  const delegates = ref<any[]>([])
  const filterSubsidyId = ref<number | null>(null)
  const filterDeptOrgId = ref<number | null>(null)
  const filterDeptUserId = ref<number | null>(null)

  const filteredDeptTree = computed(() => {
    if (!filterDeptUserId.value) return deptTree.value
    const uid = filterDeptUserId.value
    function hasMember(node: any): boolean {
      if ((node.members || []).some((m: any) => m.user_id === uid)) return true
      return (node.children || []).some((c: any) => hasMember(c))
    }
    return deptTree.value.filter(hasMember)
  })

  async function loadDeptTree() {
    deptLoading.value = true
    const qs = new URLSearchParams()
    if (filterSubsidyId.value) qs.set('subsidy_id', String(filterSubsidyId.value))
    if (filterDeptOrgId.value) qs.set('org_id', String(filterDeptOrgId.value))
    const params = qs.toString() ? `?${qs.toString()}` : ''
    try { deptTree.value = await apiFetch<any[]>(`/departments/tree${params}`) } catch { deptTree.value = [] }
    finally { deptLoading.value = false }
  }

  watch([filterSubsidyId, filterDeptOrgId], () => { loadDeptTree() })

  // Dept dialog
  const deptDialog = ref(false)
  const editingDept = ref<any>(null)
  const deptForm = ref({ name: '', subsidy_id: null as number | null, head_user_id: null as number | null, deputy_head_user_id: null as number | null, curator_user_id: null as number | null, parent_id: null as number | null })

  const otherDeptItems = computed(() =>
    flatDepts(deptTree.value)
      .filter(d => !editingDept.value || d.id !== editingDept.value.id)
      .map(d => ({ text: d.name, value: d.id }))
  )
  const deptMemberItems = computed(() => {
    if (!selectedDept.value) return []
    const ms = selectedDept.value.members || []
    return ms.map((m: any) => ({ text: m.name || '?', value: m.user_id }))
  })
  const memberUserItems = computed(() =>
    deptMembers.value.map(m => ({ text: m.user_name || '?', value: m.user_id }))
  )

  function openCreateDept() {
    editingDept.value = null
    deptForm.value = { name: '', subsidy_id: filterSubsidyId.value, head_user_id: null, deputy_head_user_id: null, curator_user_id: null, parent_id: null }
    deptDialog.value = true
  }

  async function openEditDept(node: any) {
    selectedDept.value = node
    await loadDeptMembers(node.id)
    editingDept.value = node
    deptForm.value = { name: node.name, subsidy_id: node.subsidy_id, head_user_id: node.head_user_id, deputy_head_user_id: node.deputy_head_user_id ?? null, curator_user_id: node.curator_user_id ?? null, parent_id: node.parent_id }
    deptDialog.value = true
  }

  async function openEditDeptById(deptId: number) {
    const dept = flatDepts(deptTree.value).find(d => d.id === deptId)
    if (dept) openEditDept(dept)
  }

  async function saveDept() {
    try {
      if (editingDept.value) {
        await apiFetch(`/departments/${editingDept.value.id}`, { method: 'PATCH', body: JSON.stringify(deptForm.value) })
      } else {
        await apiFetch('/departments/', { method: 'POST', body: JSON.stringify(deptForm.value) })
      }
      deptDialog.value = false
      showSnack(editingDept.value ? 'Отдел обновлен' : 'Отдел создан')
      dictsCache.value = {}
      knownDepartments.value = []
      await loadDicts()
      await loadDeptTree()
      refreshHierarchy()
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function deleteDept(node: any) {
    if (!confirm(`Удалить отдел "${node.name}"?`)) return
    try {
      await apiFetch(`/departments/${node.id}`, { method: 'DELETE' })
      if (selectedDept.value?.id === node.id) selectedDept.value = null
      showSnack('Отдел удален')
      dictsCache.value = {}
      knownDepartments.value = []
      await loadDicts()
      await loadDeptTree()
    } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
  }

  async function selectDept(node: any) {
    selectedDept.value = node
    await Promise.all([loadDeptMembers(node.id), loadDelegates()])
  }

  async function loadDeptMembers(deptId: number) {
    try { deptMembers.value = await apiFetch<any[]>(`/departments/${deptId}/members`) } catch { deptMembers.value = [] }
  }

  async function loadDelegates() {
    try { delegates.value = await apiFetch<any[]>('/departments/delegates') } catch { delegates.value = [] }
  }

  return {
    deptLoading, deptTree, filteredDeptTree, selectedDept, deptMembers, delegates,
    filterSubsidyId, filterDeptOrgId, filterDeptUserId,
    loadDeptTree, loadDeptMembers, loadDelegates,
    deptDialog, editingDept, deptForm, otherDeptItems, deptMemberItems, memberUserItems,
    openCreateDept, openEditDept, openEditDeptById, saveDept, deleteDept, selectDept,
  }
}
