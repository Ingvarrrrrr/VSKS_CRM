// useWishApprovers.ts — участники заявки (WishMember) + цепочка согласующих
// (WishApprover, мультисогласование с авто-каскадом) + решение по согласованию.
// Дословный перенос из WishesView.vue при разбиении файла на компоненты/композаблы.
import { computed, ref } from 'vue'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import type { WishesContext } from './useWishesContext'
import type { Wish, WishApprover, WishMember } from './wishTypes'
import type { UseWishFormReturn } from './useWishForm'

export function useWishApprovers(deps: {
  ctx: WishesContext
  apiFetch: typeof import('@/api').apiFetch
  form: UseWishFormReturn
  flushFeoAutosave: () => Promise<boolean>
  notifyLocalUpdate: () => void
  loadWishes: () => Promise<void>
}) {
  const { ctx, apiFetch, form, flushFeoAutosave, notifyLocalUpdate, loadWishes } = deps
  const { showSnack, currentUserId, isAdmin, requiresConsent, showExcessWarnings, showPurchaseSync } = ctx
  const { editingWishId, editingWish, wishForm, isWishEditable, wishPayloadSnapshotJson, wishFormSavedSnapshot, saveWish, handleMissingFeoCategoryError, orgUsers, setIsChainApprover } = form

  const wishMembers = ref<WishMember[]>([])
  const participantToAdd = ref<number | null>(null)

  async function loadWishMembers() {
    if (!editingWishId.value) { wishMembers.value = []; return }
    try {
      wishMembers.value = await apiFetch<WishMember[]>(`/wishes/${editingWishId.value}/members`)
    } catch { wishMembers.value = [] }
  }
  async function addWishMember(userId: number | null) {
    participantToAdd.value = null
    if (!userId) return
    if (wishMembers.value.some(m => m.user_id === userId)) return
    if (!editingWishId.value) {
      const u = orgUsers.value.find((x: any) => x.id === userId)
      wishMembers.value.push({
        id: -userId, wish_id: 0, user_id: userId, role: 'participant',
        added_by_id: null, consent_pending: false,
        username: (u as any)?.username ?? null, full_name: u?.full_name ?? null,
      } as WishMember)
      return
    }
    try {
      await apiFetch(`/wishes/${editingWishId.value}/members`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, role: 'participant' }),
      })
      await loadWishMembers()
      showSnack('Участник добавлен')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось добавить участника', 'error')
    }
  }
  async function removeWishMember(userId: number) {
    if (!editingWishId.value) {
      wishMembers.value = wishMembers.value.filter(m => m.user_id !== userId)
      return
    }
    try {
      await apiFetch(`/wishes/${editingWishId.value}/members/${userId}`, { method: 'DELETE' })
      await loadWishMembers()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось удалить участника', 'error')
    }
  }

  const wishApprovers = ref<WishApprover[]>([])
  const approverTopUser = ref<number | null>(null)
  const approverToAdd = ref<number | null>(null)
  const approvalMode = ref<'sequential' | 'parallel'>('sequential')
  const cascadeLoading = ref(false)
  const decideComment = ref<Record<number, string>>({})
  const decideLoading = ref<number | null>(null)

  const approvalStatusColor: Record<string, string> = {
    pending: 'orange',
    approved: 'green',
    rejected: 'red',
    skipped: 'grey',
  }
  const approvalStatusLabel: Record<string, string> = {
    pending: 'Ожидает',
    approved: 'Согласовано',
    rejected: 'Отклонил',
    skipped: 'Пропущено',
  }

  // Согласующий из цепочки может менять ФЭО у отправленной заявки — синхронизируем
  // с useWishForm.isChainApprover (см. setIsChainApprover), т.к. canEditWishFeo там.
  const isChainApprover = computed(() =>
    wishApprovers.value.some(a => a.user_id === currentUserId)
  )
  function syncIsChainApprover() { setIsChainApprover(isChainApprover.value) }

  async function loadWishApprovers() {
    if (!editingWishId.value) { wishApprovers.value = []; syncIsChainApprover(); return }
    try {
      wishApprovers.value = await apiFetch<WishApprover[]>(`/wishes/${editingWishId.value}/approvers`)
    } catch { wishApprovers.value = [] }
    syncIsChainApprover()
  }
  async function callCascadeApi(wishId: number, topUserId: number) {
    return apiFetch<{ approval_mode: string; approvers: WishApprover[]; warning?: string | null }>(
      `/wishes/${wishId}/approvers/cascade`,
      { method: 'POST', body: JSON.stringify({ top_user_id: topUserId, mode: approvalMode.value }) },
    )
  }
  async function runCascade() {
    if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'warning'); return }
    if (!approverTopUser.value) { showSnack('Выберите верхнего согласующего', 'warning'); return }
    cascadeLoading.value = true
    try {
      const res = await callCascadeApi(editingWishId.value, approverTopUser.value)
      wishApprovers.value = res.approvers
      syncIsChainApprover()
      approverTopUser.value = null
      if (res.warning) {
        showSnack(`Цепочка построена. Внимание: ${res.warning}`, 'warning')
      } else {
        showSnack('Цепочка построена. Заявка уйдёт на согласование после кнопки «Отправить на согласование»')
      }
      await loadWishOnce()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось построить цепочку', 'error')
    } finally {
      cascadeLoading.value = false
    }
  }
  // Владелец (2026-09-03): не нажал кнопку — цепочка НЕ строится вообще, согласующим
  // становится РОВНО тот человек, что выбран в поле «Верхний согласующий».
  async function ensureApprovers(wishId: number): Promise<boolean> {
    if (wishApprovers.value.length > 0) return true
    if (!approverTopUser.value) return false
    try {
      await apiFetch(`/wishes/${wishId}/approvers`, {
        method: 'POST', body: JSON.stringify({ user_id: approverTopUser.value }),
      })
      await loadWishApprovers()
      approverTopUser.value = null
      showSnack('Согласующий добавлен')
      return wishApprovers.value.length > 0
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось добавить согласующего', 'error')
      return false
    }
  }
  async function addApprover(userId: number | null) {
    approverToAdd.value = null
    if (!userId || !editingWishId.value) return
    if (wishApprovers.value.some(a => a.user_id === userId)) return
    try {
      await apiFetch(`/wishes/${editingWishId.value}/approvers`, {
        method: 'POST', body: JSON.stringify({ user_id: userId }),
      })
      await loadWishApprovers()
      showSnack('Согласующий добавлен')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось добавить согласующего', 'error')
    }
  }
  const reorderLoading = ref(false)
  async function moveApprover(idx: number, dir: number) {
    if (!editingWishId.value) return
    const j = idx + dir
    if (j < 0 || j >= wishApprovers.value.length) return
    const arr: WishApprover[] = [...wishApprovers.value]
    const tmp: WishApprover = arr[idx]!
    arr[idx] = arr[j]!
    arr[j] = tmp
    reorderLoading.value = true
    try {
      wishApprovers.value = await apiFetch<WishApprover[]>(
        `/wishes/${editingWishId.value}/approvers/reorder`,
        { method: 'POST', body: JSON.stringify({ ids: arr.map(a => a.id) }) },
      )
      syncIsChainApprover()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось изменить порядок согласующих', 'error')
    } finally {
      reorderLoading.value = false
    }
  }
  async function removeApprover(approvalId: number) {
    if (!editingWishId.value) return
    try {
      await apiFetch(`/wishes/${editingWishId.value}/approvers/${approvalId}`, { method: 'DELETE' })
      await loadWishApprovers()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось удалить согласующего', 'error')
    }
  }
  async function decideApprover(approvalId: number, decision: 'approved' | 'rejected') {
    if (!editingWishId.value) return
    const flushedFeo = await flushFeoAutosave()
    if (!flushedFeo) return
    if (decision === 'approved' && isWishEditable.value) {
      const currentSnapshot = wishPayloadSnapshotJson()
      if (currentSnapshot && currentSnapshot !== wishFormSavedSnapshot.value) {
        const saved = await saveWish(false)
        if (!saved) return
      }
    }
    decideLoading.value = approvalId
    try {
      const res = await apiFetch<{
        status: string
        convert_error?: string | null
        approvers: WishApprover[]
        excess_warnings?: import('./wishTypes').ExcessWarning[]
        purchases?: { id: number; registry_number?: string | null }[]
        purchase_sync?: import('./wishTypes').PurchaseSync | null
      }>(
        `/wishes/${editingWishId.value}/approvers/${approvalId}/decide`,
        { method: 'POST', body: JSON.stringify({ decision, comment: decideComment.value[approvalId] || null }) },
      )
      wishApprovers.value = res.approvers
      syncIsChainApprover()
      decideComment.value[approvalId] = ''
      if (wishForm.value) (wishForm.value as any).status = res.status
      notifyLocalUpdate()
      const _convertedPurchase = res.status === 'converted' ? (res.purchases || [])[0] : null
      if (res.convert_error) showSnack(res.convert_error, 'warning')
      else if (_convertedPurchase)
        showSnack(`Заявка согласована и перенесена в закупку ${_convertedPurchase.registry_number || `№${_convertedPurchase.id}`}`)
      else showSnack(decision === 'approved' ? 'Согласовано' : 'Отклонено')
      showExcessWarnings(res.excess_warnings, 'Заявка согласована, закупка создана.')
      showPurchaseSync(res.purchase_sync)
      await loadWishOnce()
      await loadWishes()
      refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
    } catch (e: any) {
      const handled = editingWish.value ? await handleMissingFeoCategoryError(e, editingWish.value) : false
      if (!handled) {
        showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось сохранить решение', 'error')
      }
    } finally {
      decideLoading.value = null
    }
  }
  async function loadWishOnce() {
    if (!editingWishId.value) return
    try {
      const fresh = await apiFetch<Wish>(`/wishes/${editingWishId.value}`)
      editingWish.value = fresh
      ;(wishForm.value as any).status = fresh.status
      if ((fresh as any).approval_mode) approvalMode.value = (fresh as any).approval_mode
    } catch { /* ignore */ }
  }
  const canDecideApprover = (a: WishApprover): boolean => {
    if (a.status !== 'pending') return false
    if ((wishForm.value as any).status !== 'submitted') return false
    if (editingWish.value && editingWish.value.status !== 'submitted') return false
    const mine = a.user_id === currentUserId || isAdmin.value
    if (!mine) return false
    if (approvalMode.value === 'sequential') {
      const lowerPending = wishApprovers.value.some(x => x.order_num < a.order_num && x.status === 'pending')
      if (lowerPending) return false
    }
    return true
  }
  function isDecidingOnBehalf(a: WishApprover): boolean {
    return a.user_id !== currentUserId
  }
  function approverDecisionLine(a: WishApprover): string | null {
    if (!a.decided_at || (a.status !== 'approved' && a.status !== 'rejected')) return null
    const when = ctx.formatDateTime(a.decided_at)
    if (a.is_on_behalf) {
      const verb = a.status === 'rejected' ? 'Отклонил' : 'Согласовал'
      const who = ctx.shortName(a.decided_by_name) || a.decided_by_name || '—'
      const whom = ctx.shortName(a.full_name) || a.full_name || '—'
      return `${verb}: ${who} вместо ${whom} · ${when}`
    }
    const verb = a.status === 'rejected' ? 'Отклонено' : 'Согласовано'
    return `${verb} ${when}`
  }

  return {
    wishMembers, participantToAdd, loadWishMembers, addWishMember, removeWishMember,
    wishApprovers, approverTopUser, approverToAdd, approvalMode, cascadeLoading,
    decideComment, decideLoading, approvalStatusColor, approvalStatusLabel,
    isChainApprover, loadWishApprovers, callCascadeApi, runCascade, ensureApprovers,
    addApprover, reorderLoading, moveApprover, removeApprover, decideApprover, loadWishOnce,
    canDecideApprover, isDecidingOnBehalf, approverDecisionLine, requiresConsent,
  }
}

export type UseWishApproversReturn = ReturnType<typeof useWishApprovers>
