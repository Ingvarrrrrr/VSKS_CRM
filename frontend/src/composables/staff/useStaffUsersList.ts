// useStaffUsersList.ts — список сотрудников, фильтры вкладки «Сотрудники»,
// дубликаты по ИНН, «вне отделов», task-authority по строке. Дословный
// перенос из StaffView.vue.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { UserItem } from './staffTypes'

export function useStaffUsersList(currentRole: string) {
  const users = ref<UserItem[]>([])
  const usersLoading = ref(false)

  async function loadUsers() {
    usersLoading.value = true
    try {
      users.value = await apiFetch<UserItem[]>('/users/')
    } finally {
      usersLoading.value = false
    }
  }

  // Dropdown items for user select components
  const userDropdownItems = computed(() =>
    users.value.map(u => ({ text: u.full_name || u.username, value: u.id }))
  )

  const filterUserRole = ref<string | null>(null)
  const filterUserOrgId = ref<number | null>(null)
  const filterUserSearch = ref('')

  const filteredUsers = computed(() => {
    let list = users.value
    // D-09: non-superadmin viewers don't see superadmin rows (defence-in-depth; backend also filters)
    if (currentRole !== 'superadmin') list = list.filter(u => u.role !== 'superadmin')
    if (filterUserRole.value) list = list.filter(u => u.role === filterUserRole.value)
    if (filterUserOrgId.value) list = list.filter(u => (u as any).org_id === filterUserOrgId.value)
    const q = filterUserSearch.value.trim().toLowerCase()
    if (q) {
      list = list.filter(u => {
        const fields = [
          u.full_name,
          u.username,
          (u as any).position,
          (u as any).email,
          (u as any).phone,
          (u as any).inn != null ? String((u as any).inn) : '',
        ]
        return fields.some(f => (f || '').toLowerCase().includes(q))
      })
    }
    return list
  })

  // B6: дедуп пользователей по ИНН
  const duplicateInnGroups = computed(() => {
    const byInn: Record<string, UserItem[]> = {}
    for (const u of users.value) {
      const inn = (u as any).inn
      if (!inn || String(inn).trim().length < 10) continue
      const key = String(inn).trim()
      if (!byInn[key]) byInn[key] = []
      byInn[key].push(u)
    }
    return Object.entries(byInn)
      .filter(([, group]) => group.length >= 2)
      .map(([inn, group]) => ({ inn, group }))
  })

  // Users not in any department
  const unassignedUsers = computed(() => users.value.filter(u => !u.department))
  const unassignedExpanded = ref(true)

  /** Get avatar id for a department member by user_id */
  function getMemberAvatar(userId: number): string | undefined {
    const u = users.value.find(x => x.id === userId)
    return u?.avatar
  }

  function getMemberPhotoUrl(userId: number): string | null | undefined {
    const u = users.value.find(x => x.id === userId)
    return u?.photo_url
  }

  // Task authority expand
  const expandedUsers = ref<number[]>([])
  const taskAuthority = ref<Record<number, { can_assign_to: any[]; can_receive_from: any[] }>>({})
  const taskAuthorityLoading = ref<Record<number, boolean>>({})

  async function loadTaskAuthority(userId: number) {
    if (taskAuthority.value[userId]) return
    taskAuthorityLoading.value = { ...taskAuthorityLoading.value, [userId]: true }
    try {
      const data = await apiFetch<{ can_assign_to: any[]; can_receive_from: any[] }>(`/users/${userId}/task-authority`)
      taskAuthority.value = { ...taskAuthority.value, [userId]: data }
    } catch {
      taskAuthority.value = { ...taskAuthority.value, [userId]: { can_assign_to: [], can_receive_from: [] } }
    } finally {
      taskAuthorityLoading.value = { ...taskAuthorityLoading.value, [userId]: false }
    }
  }

  async function onUserExpanded(expanded: number[]) {
    for (const uid of expanded) {
      if (!taskAuthority.value[uid]) {
        loadTaskAuthority(uid)
      }
    }
  }

  return {
    users, usersLoading, loadUsers, userDropdownItems,
    filterUserRole, filterUserOrgId, filterUserSearch, filteredUsers,
    duplicateInnGroups, unassignedUsers, unassignedExpanded,
    getMemberAvatar, getMemberPhotoUrl,
    expandedUsers, taskAuthority, taskAuthorityLoading, loadTaskAuthority, onUserExpanded,
  }
}
