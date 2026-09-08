// useStaffDeleteUser.ts — удаление сотрудника (одиночное и массовое).
// Дословный перенос из StaffView.vue.
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { UserItem } from './staffTypes'

export function useStaffDeleteUser(options: {
  users: { value: UserItem[] }
  currentOrgId: number | null
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { users, currentOrgId, showSnack } = options

  const deleteDialog = reactive({ show: false, user: null as UserItem | null, deleting: false, warning: '' as string })
  const selectedUsers = ref<any[]>([])
  const bulkDeleteUsersDialog = ref(false)
  const bulkDeleteUsersLoading = ref(false)

  function confirmDelete(u: UserItem) {
    deleteDialog.user = u
    deleteDialog.warning = ''
    deleteDialog.show = true
  }

  async function doDelete() {
    if (!deleteDialog.user) return
    deleteDialog.deleting = true
    try {
      // org-контекст: удаление карточки = открепление от ЭТОЙ орг; глобальное
      // удаление аккаунта бэк делает только если это его последняя организация.
      const orgId = deleteDialog.user.org_id ?? currentOrgId
      const params = new URLSearchParams()
      if (orgId) params.set('org_id', String(orgId))
      // Второй этап (warning уже показан) — удаляем с confirm=true
      if (deleteDialog.warning) params.set('confirm', 'true')
      const qs = params.toString()
      const url = `/users/${deleteDialog.user.id}${qs ? `?${qs}` : ''}`
      const res = await apiFetch(url, { method: 'DELETE' })
      users.value = users.value.filter(u => u.id !== deleteDialog.user!.id)
      deleteDialog.show = false
      showSnack((res as any)?.detached ? 'Сотрудник убран из организации' : 'Пользователь удален')
    } catch (e: any) {
      if (e?.status === 409 && e?.payload?.code === 'CONFIRM_DELETE_USER') {
        // Показываем предупреждение о связанных записях, требуем повторного подтверждения
        deleteDialog.warning = e.payload.message || e.message
      } else {
        showSnack(e?.payload?.message || e.message || 'Ошибка', 'error')
      }
    } finally {
      deleteDialog.deleting = false
    }
  }

  function confirmBulkDeleteUsers() {
    bulkDeleteUsersDialog.value = true
  }

  function toggleUserSelection(u: UserItem) {
    const idx = selectedUsers.value.findIndex((s: any) => (s?.id ?? s) === u.id)
    if (idx >= 0) {
      selectedUsers.value = selectedUsers.value.filter((_: any, i: number) => i !== idx)
    } else {
      selectedUsers.value = [...selectedUsers.value, u]
    }
  }

  async function doBulkDeleteUsers() {
    bulkDeleteUsersLoading.value = true
    const toDelete = [...selectedUsers.value]
    let deleted = 0
    const errors: string[] = []
    for (const item of toDelete) {
      const id = typeof item === 'object' ? item.id : item
      const name = typeof item === 'object' ? (item.full_name || item.username || String(id)) : String(id)
      try {
        // Диалог bulk-удаления — уже явное подтверждение, поэтому confirm=true.
        // org_id — открепить от текущей орг, а не удалять аккаунт глобально.
        const orgId = (typeof item === 'object' ? item.org_id : null) ?? currentOrgId
        await apiFetch(`/users/${id}?confirm=true${orgId ? `&org_id=${orgId}` : ''}`, { method: 'DELETE' })
        users.value = users.value.filter(u => u.id !== id)
        deleted++
      } catch (e: any) {
        const msg = e?.payload?.message || e?.message || 'Ошибка'
        errors.push(`${name}: ${msg}`)
      }
    }
    selectedUsers.value = []
    bulkDeleteUsersDialog.value = false
    bulkDeleteUsersLoading.value = false
    if (errors.length) {
      showSnack(`Удалено: ${deleted}. Ошибки (${errors.length}): ${errors.slice(0, 3).join('; ')}`, 'error')
    } else {
      showSnack(`Удалено сотрудников: ${deleted}`, 'success')
    }
  }

  return {
    deleteDialog, selectedUsers, bulkDeleteUsersDialog, bulkDeleteUsersLoading,
    confirmDelete, doDelete, confirmBulkDeleteUsers, toggleUserSelection, doBulkDeleteUsers,
  }
}
