// Заявка-компаньон авансового отчёта (source='advance_report' на бэке,
// см. app/routers/purchases.py::create_purchase) — состояние карточки
// AdvanceReimbursementCard.vue.
//
// Решение владельца (опрос 2026-09-15): компаньон теперь создаётся
// status='draft' (раньше сразу 'submitted' — уходила ВСЕМ руководителям по
// иерархии, хотя никто не отправлял). Сотрудник сам жмёт «Отправить на
// согласование» — переиспользуем СУЩЕСТВУЮЩИЙ эндпоинт POST /api/wishes/{id}/submit
// (app/routers/wish_transitions.py::submit_wish), новый механизм отправки НЕ
// заводим (ПРАВИЛО №6).
//
// Владелец (прод-инцидент с заявкой №85, 2026-09-29): «Мы же говорили: цепочка
// автоматически не выстраивается, только если нажато кнопочкой». До этой
// правки в карточке компаньона не было раздела «Согласующие» вовсе — submit
// сам пытался построить восходящую цепочку (см. коммит, убравший это из
// app/routers/wish_transitions.py::submit_wish). Теперь здесь ЖИВЁТ тот же
// раздел «Согласующие», что и у обычной заявки (composables/wishes/
// useWishApprovers.ts, components/wishes/WishFormDialog.vue) — те же REST-пути
// (/wishes/{id}/approvers*), ПРАВИЛО №6: второй механизм подбора/решения
// согласующих не заводим, здесь просто самостоятельная (без тяжёлого
// WishesContext) обвязка НАД теми же эндпоинтами для страницы закупки.
//
// Детали заявки (статус/дата/причина отклонения/согласующие) — отдельный
// запрос GET /api/wishes/{id}: он неизбежно отличается от блока чеков
// (usePurchaseReceipts.ts, GET /purchases/{id}/receipts) — данные о самих
// чеках сюда НЕ дублируются, состояние «есть ли чеки» приходит пропом извне
// (receipts/receiptFiles — те же refs, что уже загружены в CreateOrderView).
import { ref, computed, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Receipt, ReceiptFile } from '@/composables/purchase/usePurchaseReceipts'

export interface AdvanceWishDetail {
  id: number
  status: string
  rejection_reason?: string | null
  updated_at?: string | null
  created_at?: string | null
  approver_names?: string[]
  approval_mode?: string | null
}

export interface AdvanceApprover {
  id: number
  wish_id: number
  user_id: number | null
  order_num: number
  role_name: string | null
  full_name: string | null
  is_auto: boolean
  status: string  // pending / approved / rejected / skipped
  comment: string | null
  decided_at: string | null
  decided_by_user_id: number | null
  decided_by_name?: string | null
  is_on_behalf?: boolean
}

export function useAdvanceReimbursement(
  wishId: Ref<number | null | undefined>,
  itemsCount: Ref<number>,
  receipts: Ref<Receipt[]>,
  receiptFiles: Ref<ReceiptFile[]>,
  showSnack: (text: string, color?: ToastType) => void,
  currentUserId: number,
  isAdmin: Ref<boolean>,
) {
  const wish = ref<AdvanceWishDetail | null>(null)
  const loading = ref(false)
  const submitting = ref(false)

  async function loadWish() {
    if (!wishId.value) {
      wish.value = null
      return
    }
    loading.value = true
    try {
      wish.value = await apiFetch<AdvanceWishDetail>(`/wishes/${wishId.value}`)
    } catch {
      // Заявка ещё недоступна (страница только открывается) — тихо, карточка
      // просто не покажет статус до следующей успешной загрузки.
    } finally {
      loading.value = false
    }
  }

  watch(wishId, () => { loadWish(); loadApprovers() }, { immediate: true })

  const statusLabel = computed(() => {
    const w = wish.value
    if (!w) return ''
    if (w.status === 'draft') return 'Черновик — не отправлена'
    if (w.status === 'submitted') {
      const d = w.updated_at ? new Date(w.updated_at).toLocaleDateString('ru-RU') : ''
      return `На согласовании${d ? ' с ' + d : ''}`
    }
    if (w.status === 'approved' || w.status === 'converted') return 'Одобрена'
    if (w.status === 'rejected') return `Отклонена: ${w.rejection_reason || 'причина не указана'}`
    return w.status
  })

  const statusColor = computed(() => {
    const s = wish.value?.status
    if (s === 'draft') return 'grey'
    if (s === 'submitted') return 'warning'
    if (s === 'approved' || s === 'converted') return 'success'
    if (s === 'rejected') return 'error'
    return 'default'
  })

  const hasReceipts = computed(() => receipts.value.length > 0 || receiptFiles.value.length > 0)

  const canSubmit = computed(() =>
    !!wishId.value
    && !submitting.value
    && itemsCount.value > 0
    && (wish.value?.status === 'draft' || wish.value?.status === 'rejected'),
  )

  async function submit() {
    if (!wishId.value || submitting.value) return
    submitting.value = true
    try {
      await apiFetch<AdvanceWishDetail>(`/wishes/${wishId.value}/submit`, { method: 'POST' })
      // POST /submit возвращает WishOut без approver_names (см. submit_wish —
      // он не делает доп. запрос за именами согласующих, в отличие от
      // GET /{wish_id}). Перечитываем через тот же GET, что и loadWish() —
      // без него, а не заводим второй способ узнать статус.
      await loadWish()
      showSnack('Заявка на возмещение отправлена на согласование', 'success')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось отправить заявку на согласование', 'error')
    } finally {
      submitting.value = false
    }
  }

  // ── Согласующие (ПРАВИЛО №6: те же эндпоинты /wishes/{id}/approvers*, что и
  // у обычной заявки — composables/wishes/useWishApprovers.ts) ──────────────
  const approvers = ref<AdvanceApprover[]>([])
  const approverTopUser = ref<number | null>(null)
  const approvalMode = ref<'sequential' | 'parallel'>('sequential')
  const cascadeLoading = ref(false)
  const approverToAdd = ref<number | null>(null)
  const decideComment = ref<Record<number, string>>({})
  const decideLoading = ref<number | null>(null)
  const reorderLoading = ref(false)

  const approvalStatusColor: Record<string, string> = {
    pending: 'orange', approved: 'green', rejected: 'red', skipped: 'grey',
  }
  const approvalStatusLabel: Record<string, string> = {
    pending: 'Ожидает', approved: 'Согласовано', rejected: 'Отклонил', skipped: 'Пропущено',
  }

  // Черновик/отклонена — цепочку/состав ещё можно менять (та же граница, что
  // и у обычной заявки: isWishEditable в useWishForm.ts).
  const isEditable = computed(() =>
    wish.value?.status === 'draft' || wish.value?.status === 'rejected',
  )

  async function loadApprovers() {
    if (!wishId.value) { approvers.value = []; return }
    try {
      approvers.value = await apiFetch<AdvanceApprover[]>(`/wishes/${wishId.value}/approvers`)
    } catch { approvers.value = [] }
  }

  async function runCascade() {
    if (!wishId.value) return
    if (!approverTopUser.value) { showSnack('Выберите верхнего согласующего', 'warning'); return }
    cascadeLoading.value = true
    try {
      const res = await apiFetch<{ approval_mode: string; approvers: AdvanceApprover[]; warning?: string | null }>(
        `/wishes/${wishId.value}/approvers/cascade`,
        { method: 'POST', body: JSON.stringify({ top_user_id: approverTopUser.value, mode: approvalMode.value }) },
      )
      approvers.value = res.approvers
      approverTopUser.value = null
      if (res.warning) showSnack(`Цепочка построена. Внимание: ${res.warning}`, 'warning')
      else showSnack('Цепочка построена. На согласование заявка уйдёт после кнопки «Отправить на согласование»')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось построить цепочку', 'error')
    } finally {
      cascadeLoading.value = false
    }
  }

  async function addApprover(userId: number | null) {
    approverToAdd.value = null
    if (!userId || !wishId.value) return
    if (approvers.value.some(a => a.user_id === userId)) return
    try {
      await apiFetch(`/wishes/${wishId.value}/approvers`, {
        method: 'POST', body: JSON.stringify({ user_id: userId }),
      })
      await loadApprovers()
      showSnack('Согласующий добавлен')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось добавить согласующего', 'error')
    }
  }

  async function removeApprover(approvalId: number) {
    if (!wishId.value) return
    try {
      await apiFetch(`/wishes/${wishId.value}/approvers/${approvalId}`, { method: 'DELETE' })
      await loadApprovers()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось удалить согласующего', 'error')
    }
  }

  async function decideApprover(approvalId: number, decision: 'approved' | 'rejected') {
    if (!wishId.value) return
    decideLoading.value = approvalId
    try {
      const res = await apiFetch<{
        status: string
        approvers: AdvanceApprover[]
        purchases?: { id: number; registry_number?: string | null }[]
        // Владелец (2026-09-29): «авансовый должен идти дальше сам» — закупка
        // пробует автоматом уйти из 'wishes' в план (см. wish_distribution.py).
        // Если гейт (обязательные поля/превышение) отказал — здесь причина,
        // кнопка «→ План закупок» остаётся для ручного повтора.
        advance_purchase_transition_warning?: string | null
      }>(
        `/wishes/${wishId.value}/approvers/${approvalId}/decide`,
        { method: 'POST', body: JSON.stringify({ decision, comment: decideComment.value[approvalId] || null }) },
      )
      approvers.value = res.approvers
      decideComment.value[approvalId] = ''
      if (wish.value) wish.value.status = res.status
      const convertedPurchase = res.status === 'converted' ? (res.purchases || [])[0] : null
      if (res.advance_purchase_transition_warning) {
        showSnack(res.advance_purchase_transition_warning, 'warning')
      } else if (convertedPurchase) {
        showSnack(
          `Возмещение согласовано. Закупка ${convertedPurchase.registry_number || `№${convertedPurchase.id}`} `
          + 'переведена в план закупок.',
        )
      } else {
        showSnack(decision === 'approved' ? 'Согласовано' : 'Отклонено')
      }
      await loadWish()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
    } finally {
      decideLoading.value = null
    }
  }

  const canDecideApprover = (a: AdvanceApprover): boolean => {
    if (a.status !== 'pending') return false
    if (wish.value?.status !== 'submitted') return false
    const mine = a.user_id === currentUserId || isAdmin.value
    if (!mine) return false
    if (approvalMode.value === 'sequential') {
      const lowerPending = approvers.value.some(x => x.order_num < a.order_num && x.status === 'pending')
      if (lowerPending) return false
    }
    return true
  }
  function isDecidingOnBehalf(a: AdvanceApprover): boolean {
    return a.user_id !== currentUserId
  }
  function approverDecisionLine(a: AdvanceApprover): string | null {
    if (!a.decided_at || (a.status !== 'approved' && a.status !== 'rejected')) return null
    const when = new Date(a.decided_at).toLocaleString('ru-RU')
    if (a.is_on_behalf) {
      const verb = a.status === 'rejected' ? 'Отклонил' : 'Согласовал'
      return `${verb}: ${a.decided_by_name || '—'} вместо ${a.full_name || '—'} · ${when}`
    }
    const verb = a.status === 'rejected' ? 'Отклонено' : 'Согласовано'
    return `${verb} ${when}`
  }

  watch(() => wish.value?.approval_mode, (m) => {
    if (m === 'parallel' || m === 'sequential') approvalMode.value = m
  })

  return {
    wish, loading, submitting, statusLabel, statusColor, hasReceipts, canSubmit, submit, loadWish,
    approvers, approverTopUser, approvalMode, cascadeLoading, approverToAdd,
    decideComment, decideLoading, reorderLoading, approvalStatusColor, approvalStatusLabel,
    isEditable, loadApprovers, runCascade, addApprover, removeApprover, decideApprover,
    canDecideApprover, isDecidingOnBehalf, approverDecisionLine,
  }
}
