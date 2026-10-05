// useWishApprovers.ts — участники заявки (WishMember) + цепочка согласующих
// (WishApprover, мультисогласование с авто-каскадом) + решение по согласованию.
// Дословный перенос из WishesView.vue при разбиении файла на компоненты/композаблы.
import { computed, ref } from 'vue'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { callApproverCascade, ensureApproversBeforeSubmit, moveApprover as moveApproverShared } from './useApproverCascade'
import type { WishesContext } from './useWishesContext'
import type { Wish, WishApprover, WishMember } from './wishTypes'
import type { UseWishFormReturn } from './useWishForm'

export type EnsureApproversOutcome = { ok: true } | { ok: false; reason: 'no-top' | 'error' }

export function useWishApprovers(deps: {
  ctx: WishesContext
  apiFetch: typeof import('@/api').apiFetch
  form: UseWishFormReturn
  flushFeoAutosave: () => Promise<boolean>
  notifyLocalUpdate: () => void
  loadWishes: () => Promise<void>
  // Прод 05.10, заявка №113: loadWishes() ниже обновляет только вкладку «Мои»,
  // а решение по согласованию чаще принимают со вкладки «На согласование мне»
  // (incoming) или «Заявки сотрудников» (all) — используем тот же механизм,
  // что и остальные composable'ы заявок (WishFormDialog.vue передаёт
  // props.reloadActiveTab), не заводим второй способ обновления списка.
  reloadActiveTab: () => Promise<void>
}) {
  const { ctx, apiFetch, form, flushFeoAutosave, notifyLocalUpdate, loadWishes, reloadActiveTab } = deps
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
  // Владелец (30.09): «Без ТЗ (мелкие закупки)» — галочка согласующего рядом
  // с решением по конкретному шагу цепочки (WishFormDialog.vue), передаётся
  // в decideApprover как tzNotRequired. Ключ — id согласующего (WishApproval.id),
  // тот же приём, что decideComment выше.
  const tzNotRequiredChecked = ref<Record<number, boolean>>({})

  // Владелец: верхним согласующим можно ставить только сотрудника с правом
  // корректировать субсидию заявки — список кандидатов приходит с бэка
  // (GET /wishes/{id}/approvers/candidates), не весь orgUsers (иначе каждый
  // сам себя ставил бы согласующим).
  const topApproverCandidates = ref<{ id: number; full_name: string | null; role: string }[]>([])
  const topApproverCandidatesLoading = ref(false)
  // Баг (прод, заявка №96): catch {} глотал ошибку загрузки — пустой список
  // при реальной ошибке сети/бэка выглядел как «нет сотрудников с правом»,
  // хотя причина была в упавшем запросе. Текст ошибки — в no-data-text
  // автокомплита (WishFormDialog.vue), не прячем (правило проекта).
  const topApproverCandidatesError = ref<string | null>(null)
  async function loadTopApproverCandidates() {
    if (!editingWishId.value) { topApproverCandidates.value = []; topApproverCandidatesError.value = null; return }
    topApproverCandidatesLoading.value = true
    topApproverCandidatesError.value = null
    try {
      topApproverCandidates.value = await apiFetch<{ id: number; full_name: string | null; role: string }[]>(
        `/wishes/${editingWishId.value}/approvers/candidates`,
      )
    } catch (e: any) {
      topApproverCandidates.value = []
      topApproverCandidatesError.value = e?.payload?.message || e?.message || `Не удалось загрузить список (${e?.status ?? 'ошибка сети'})`
    } finally {
      topApproverCandidatesLoading.value = false
    }
  }

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
    await loadTopApproverCandidates()
  }
  async function callCascadeApi(wishId: number, topUserId: number) {
    return callApproverCascade<WishApprover>(apiFetch, wishId, topUserId, approvalMode.value)
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
  // Владелец (прод, заявка №85, 2026-09-29, окончательно): цепочка строится
  // ТОЛЬКО по кнопке «Построить цепочку». Если кнопку не нажали, а верхнего
  // согласующего выбрали — «Отправить» добавляет ЕГО ОДНОГО единственным
  // согласующим (тот же POST, что и кнопка «Добавить согласующего», НЕ
  // cascade) — общий код в useApproverCascade.ts (ПРАВИЛО №6, второй механизм
  // подбора не заводим; то же самое зовёт useAdvanceReimbursement.ts для
  // карточки компаньона авансового отчёта).
  async function ensureApprovers(wishId: number): Promise<EnsureApproversOutcome> {
    const hadApproversAlready = wishApprovers.value.length > 0
    const res = await ensureApproversBeforeSubmit<WishApprover>({
      apiFetch,
      wishId,
      currentApproversCount: wishApprovers.value.length,
      topUserId: approverTopUser.value,
      onApprovers: (approvers) => { wishApprovers.value = approvers },
    })
    if (res.ok) {
      if (!hadApproversAlready) {
        // Согласующий только что добавлен этим вызовом (approverTopUser был
        // выбран, но кнопку «Добавить согласующего»/«Построить цепочку» не
        // нажимали).
        syncIsChainApprover()
        approverTopUser.value = null
        showSnack('Согласующий добавлен')
      }
      return { ok: true }
    }
    if (res.reason === 'error') { showSnack(res.message, 'error'); return { ok: false, reason: 'error' } }
    return { ok: false, reason: 'no-top' }
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
    reorderLoading.value = true
    try {
      await moveApproverShared<WishApprover>({
        apiFetch, wishId: editingWishId.value, approvers: wishApprovers.value, idx, dir,
        onApprovers: (list) => { wishApprovers.value = list; syncIsChainApprover() },
        onError: (msg) => showSnack(msg, 'error'),
      })
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
  async function decideApprover(approvalId: number, decision: 'approved' | 'rejected', tzNotRequired = false) {
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
        {
          method: 'POST',
          body: JSON.stringify({
            decision,
            comment: decideComment.value[approvalId] || null,
            ...(decision === 'approved' && tzNotRequired ? { tz_not_required: true } : {}),
          }),
        },
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
      // Прод 05.10, заявка №113: обновить именно активную вкладку (incoming/all),
      // не только «Мои» — иначе список продолжает показывать старый статус до
      // ручного «Обновить», и повторное открытие заявки из него откатывает окно.
      await reloadActiveTab()
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
    decideComment, decideLoading, tzNotRequiredChecked, approvalStatusColor, approvalStatusLabel,
    topApproverCandidates, loadTopApproverCandidates, topApproverCandidatesLoading, topApproverCandidatesError,
    isChainApprover, loadWishApprovers, callCascadeApi, runCascade, ensureApprovers,
    addApprover, reorderLoading, moveApprover, removeApprover, decideApprover, loadWishOnce,
    canDecideApprover, isDecidingOnBehalf, approverDecisionLine, requiresConsent,
  }
}

export type UseWishApproversReturn = ReturnType<typeof useWishApprovers>
