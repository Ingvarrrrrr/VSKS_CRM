// Участники обсуждения закупки (группа чата) + список согласующих (для
// canSeePurchaseDocs). Вынесено из CreateOrderView.vue без изменения поведения.
import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export function usePurchaseMembers(
  purchaseId: ComputedRef<number | null>,
  currentUserId: number,
  isEdit: ComputedRef<boolean>,
  isManagerLevel: ComputedRef<boolean>,
  authStore: { hasAction: (a: string) => boolean },
  allUsers: Ref<{ value: number; text: string }[]>,
  loadAllUsers: () => Promise<void>,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const purchaseMembers = ref<any[]>([])
  const newMemberUserId = ref<number | null>(null)
  const memberMenuOpen = ref(false)
  const memberAdding = ref(false)

  const memberSubordinateIds = ref<Set<number>>(new Set())

  async function loadMemberSubordinates() {
    try {
      const subs = await apiFetch<any[]>(`/users/${currentUserId}/subordinates`)
      memberSubordinateIds.value = new Set(subs.map((u: any) => u.id))
    } catch {}
  }

  function memberNeedsConsent(userId: number): boolean {
    // Discussion group: always show consent notice when adding someone else
    if (userId === currentUserId) return false
    return true
  }

  watch(memberMenuOpen, async (open) => {
    if (open) {
      await Promise.all([loadAllUsers(), loadPurchaseMembers(), loadMemberSubordinates()])
      newMemberUserId.value = null
    }
  })

  const memberSortedUsers = computed(() => {
    const memberIds = new Set(purchaseMembers.value.map((m: any) => m.user_id))
    const inGroup = allUsers.value
      .filter(u => memberIds.has(u.value))
      .sort((a, b) => a.text.localeCompare(b.text, 'ru'))
    const others = allUsers.value
      .filter(u => !memberIds.has(u.value))
      .sort((a, b) => a.text.localeCompare(b.text, 'ru'))
    return [...inGroup, ...others]
  })

  function isMemberOfGroup(userId: number): boolean {
    return purchaseMembers.value.some((m: any) => m.user_id === userId)
  }

  async function loadPurchaseMembers() {
    if (!purchaseId.value) return
    try {
      purchaseMembers.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/members`)
    } catch { purchaseMembers.value = [] }
  }

  // Список user_id согласующих по текущей закупке (для canSeePurchaseDocs)
  const purchaseApprovalUserIds = ref<Set<number>>(new Set())

  async function loadPurchaseApprovals() {
    if (!purchaseId.value) return
    try {
      const list = await apiFetch<any[]>(`/purchases/${purchaseId.value}/approvals`)
      purchaseApprovalUserIds.value = new Set(list.map((a: any) => a.user_id).filter(Boolean))
    } catch { purchaseApprovalUserIds.value = new Set() }
  }

  const isPurchaseApprover = computed(() =>
    !!currentUserId && purchaseApprovalUserIds.value.has(currentUserId)
  )

  const canSeePurchaseDocs = computed(() =>
    isEdit.value && (
      isManagerLevel.value ||
      authStore.hasAction('purchase_files.upload') ||
      purchaseMembers.value.some((m: any) => m.user_id === currentUserId) ||
      isPurchaseApprover.value
    )
  )

  async function addPurchaseMember(userId: number | null) {
    if (!userId || !purchaseId.value) return
    try {
      await apiFetch(`/purchases/${purchaseId.value}/members`, {
        method: 'POST', body: JSON.stringify({ user_id: userId }),
      })
      await loadPurchaseMembers()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка', 'error')
    }
    newMemberUserId.value = null
  }

  async function addPurchaseMemberAndClose() {
    memberAdding.value = true
    await addPurchaseMember(newMemberUserId.value)
    memberAdding.value = false
    memberMenuOpen.value = false
  }

  async function removePurchaseMember(userId: number) {
    if (!purchaseId.value) return
    try {
      await apiFetch(`/purchases/${purchaseId.value}/members/${userId}`, { method: 'DELETE' })
      await loadPurchaseMembers()
    } catch {}
  }

  return {
    purchaseMembers, newMemberUserId, memberMenuOpen, memberAdding, memberSubordinateIds,
    loadMemberSubordinates, memberNeedsConsent, memberSortedUsers, isMemberOfGroup,
    loadPurchaseMembers, purchaseApprovalUserIds, loadPurchaseApprovals, isPurchaseApprover,
    canSeePurchaseDocs, addPurchaseMember, addPurchaseMemberAndClose, removePurchaseMember,
  }
}
