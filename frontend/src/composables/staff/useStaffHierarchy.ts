// useStaffHierarchy.ts — вкладка «Иерархия»: дерево подчинённости и диалог
// «Подчинённые». Дословный перенос из StaffView.vue.
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '@/api'
import type { UserItem, SubordinateItem, TreeNode } from './staffTypes'

export function useStaffHierarchy(options: {
  users: { value: UserItem[] }
  showSnack: (text: string, color?: 'success' | 'error' | 'info' | 'warning') => void
}) {
  const { users, showSnack } = options

  const treeLoading = ref(false)
  const hierarchyTree = ref<TreeNode[]>([])

  const hierarchyDialog = reactive({
    show: false,
    user: null as UserItem | null,
    subordinates: [] as SubordinateItem[],
    allSubordinates: [] as SubordinateItem[],
    newSubId: null as number | null,
    adding: false,
    availableUsers: [] as { id: number; display: string }[],
  })

  const allSubsNotDirect = computed(() =>
    hierarchyDialog.allSubordinates.filter(a => !hierarchyDialog.subordinates.some(s => s.id === a.id))
  )

  async function loadHierarchyTree() {
    treeLoading.value = true
    try {
      const allUsers = await apiFetch<UserItem[]>('/users/')
      const tree: TreeNode[] = []
      for (const u of allUsers) {
        const subs = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates`).catch(() => [])
        if (subs.length > 0) {
          tree.push({ ...u, subordinates: subs })
        }
      }
      hierarchyTree.value = tree
    } finally {
      treeLoading.value = false
    }
  }

  async function openHierarchyDialog(u: UserItem) {
    hierarchyDialog.user = u
    hierarchyDialog.newSubId = null
    hierarchyDialog.show = true
    hierarchyDialog.subordinates = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates`).catch(() => [])
    hierarchyDialog.allSubordinates = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates/all`).catch(() => [])
    const allSubIds = new Set(hierarchyDialog.allSubordinates.map(s => s.id))
    hierarchyDialog.availableUsers = users.value
      .filter(x => x.id !== u.id && !allSubIds.has(x.id))
      .map(x => ({ id: x.id, display: x.full_name ? `${x.full_name} (${x.username})` : x.username }))
  }

  async function addSubordinate() {
    if (!hierarchyDialog.user || !hierarchyDialog.newSubId) return
    hierarchyDialog.adding = true
    try {
      const s = await apiFetch<SubordinateItem>(`/users/${hierarchyDialog.user.id}/subordinates`, {
        method: 'POST',
        body: { subordinate_id: hierarchyDialog.newSubId },
      })
      hierarchyDialog.subordinates = [...hierarchyDialog.subordinates, s]
      hierarchyDialog.allSubordinates = [...hierarchyDialog.allSubordinates, s]
      hierarchyDialog.availableUsers = hierarchyDialog.availableUsers.filter(x => x.id !== hierarchyDialog.newSubId)
      hierarchyDialog.newSubId = null
      loadHierarchyTree()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка', 'error')
    } finally {
      hierarchyDialog.adding = false
    }
  }

  async function removeSubordinate(subId: number) {
    if (!hierarchyDialog.user) return
    try {
      await apiFetch(`/users/${hierarchyDialog.user.id}/subordinates/${subId}`, { method: 'DELETE' })
      hierarchyDialog.subordinates = hierarchyDialog.subordinates.filter(s => s.id !== subId)
      hierarchyDialog.allSubordinates = hierarchyDialog.allSubordinates.filter(s => s.id !== subId)
      loadHierarchyTree()
    } catch (e: any) {
      showSnack(e.message || 'Ошибка', 'error')
    }
  }

  return {
    treeLoading, hierarchyTree, hierarchyDialog, allSubsNotDirect,
    loadHierarchyTree, openHierarchyDialog, addSubordinate, removeSubordinate,
  }
}
