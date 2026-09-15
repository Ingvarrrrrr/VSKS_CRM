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
}

export function useAdvanceReimbursement(
  wishId: Ref<number | null | undefined>,
  itemsCount: Ref<number>,
  receipts: Ref<Receipt[]>,
  receiptFiles: Ref<ReceiptFile[]>,
  showSnack: (text: string, color?: ToastType) => void,
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

  watch(wishId, () => { loadWish() }, { immediate: true })

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

  return { wish, loading, submitting, statusLabel, statusColor, hasReceipts, canSubmit, submit, loadWish }
}
