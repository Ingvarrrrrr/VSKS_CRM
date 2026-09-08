// Диалоги сотрудника: карточка (оклад/должность по организациям), копировать в отдел, удалить.
// Вынесено из HierarchyView.vue без изменения логики.
import { computed, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import type { GraphData } from './hierarchyTypes'

export interface HierarchyUserDialogsOptions {
  lastGraphData: Ref<GraphData | null>
  showSnack: (text: string, color?: ToastType) => void
  loadGraph: () => Promise<void>
  onEditUser: (id: number) => void
}

export function useHierarchyUserDialogs(opts: HierarchyUserDialogsOptions) {
  // ── User info (должности/оклады по организациям) ────────────────────────────
  const userInfoDialog = ref({ show: false, userId: 0, userName: '', orgs: [] as any[], saving: false })

  async function saveUserOrgSalary(orgId: number) {
    const o = userInfoDialog.value.orgs.find((x: any) => x.org_id === orgId)
    if (!o) return
    userInfoDialog.value.saving = true
    try {
      await apiFetch(`/users/${userInfoDialog.value.userId}/organizations/${orgId}`, {
        method: 'PATCH',
        // salary_amount/employment_percent — v-model.number; при очистке Vue кладёт '',
        // OrgMembershipBody ждёт Optional[float]/Optional[int] → 422. numOrNull (2026-09-04).
        body: { position: o.position, salary_amount: numOrNull(o.salary_amount), employment_percent: numOrNull(o.employment_percent) },
      })
    } catch {}
    userInfoDialog.value.saving = false
  }

  // ── Copy user to dept ────────────────────────────────────────────────────────
  const copyUserDialog = ref({ show: false, userId: 0, userName: '' })
  const copyTargetDeptId = ref<number | null>(null)

  const copyDeptOptions = computed(() => (opts.lastGraphData.value?.departments || []).map(d => ({
    title: d.name + ' (' + ((opts.lastGraphData.value?.orgs || []).find(o => o.id === d.org_id)?.name || '') + ')',
    value: d.id,
  })))

  function startCopyUser(userId: number) {
    const user = opts.lastGraphData.value?.users.find(u => u.id === userId)
    if (!user) return
    copyUserDialog.value = { show: true, userId, userName: user.full_name || user.username }
    copyTargetDeptId.value = null
  }

  async function confirmCopyUser() {
    if (!copyTargetDeptId.value) return
    try {
      await apiFetch(`/departments/${copyTargetDeptId.value}/members`, { method: 'POST', body: { user_id: copyUserDialog.value.userId } })
      copyUserDialog.value.show = false
      opts.showSnack('Сотрудник добавлен в отдел')
      await opts.loadGraph()
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка', 'error')
    }
  }

  // ── Delete user ──────────────────────────────────────────────────────────────
  const deleteUserConfirm = ref<{ show: boolean; userId: number | null; orgId: number | null; name: string; loading: boolean; warning: string }>({ show: false, userId: null, orgId: null, name: '', loading: false, warning: '' })

  function deleteUserNode(userId: number, name: string, orgId: number | null = null) {
    deleteUserConfirm.value = { show: true, userId, orgId, name, loading: false, warning: '' }
  }

  async function confirmDeleteUser() {
    const { userId, orgId } = deleteUserConfirm.value
    if (!userId) return
    deleteUserConfirm.value.loading = true
    try {
      // org-контекст: удаление из иерархии = открепление от ЭТОЙ орг; глобальное
      // удаление аккаунта бэк выполняет только для последней организации.
      const params = new URLSearchParams()
      if (orgId) params.set('org_id', String(orgId))
      // Второй этап (warning уже показан) — удаляем с confirm=true
      if (deleteUserConfirm.value.warning) params.set('confirm', 'true')
      const qs = params.toString()
      const res = await apiFetch(`/users/${userId}${qs ? `?${qs}` : ''}`, { method: 'DELETE' })
      opts.showSnack((res as any)?.detached ? 'Сотрудник убран из организации' : 'Сотрудник удалён')
      deleteUserConfirm.value.show = false
      await opts.loadGraph()
    } catch (e: any) {
      if (e?.status === 409 && e?.payload?.code === 'CONFIRM_DELETE_USER') {
        deleteUserConfirm.value.warning = e.payload.message || e.message
      } else {
        opts.showSnack(e?.payload?.message || e?.message || 'Ошибка удаления сотрудника', 'error')
      }
    } finally {
      deleteUserConfirm.value.loading = false
    }
  }

  return {
    userInfoDialog, saveUserOrgSalary,
    copyUserDialog, copyTargetDeptId, copyDeptOptions, startCopyUser, confirmCopyUser,
    deleteUserConfirm, deleteUserNode, confirmDeleteUser,
  }
}
