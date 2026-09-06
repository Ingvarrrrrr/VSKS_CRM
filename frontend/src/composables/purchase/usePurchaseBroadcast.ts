// Рассылка сообщения из закупки (кнопка «Рассылка» рядом с обсуждением).
// Вынесено из CreateOrderView.vue без изменения поведения — те же apiFetch-пути,
// тот же текст сообщений. commentText — тот же ref, что использует поле ввода
// комментария в чате (usePurchaseChat) — рассылка предзаполняется его текстом и
// очищает его после отправки, как раньше.
import { ref, type Ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export function usePurchaseBroadcast(
  purchaseId: ComputedRef<number | null>,
  commentText: Ref<string>,
  reloadComments: () => Promise<void>,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const pBroadcastDialog = ref(false)
  const pBroadcastScope = ref<string>('organization')
  const pBroadcastScopeId = ref<number | null>(null)
  const pBroadcastText = ref('')
  const pBroadcastSending = ref(false)
  const pBroadcastOrgs = ref<{ id: number; name: string }[]>([])
  const pBroadcastDepts = ref<{ id: number; name: string }[]>([])

  async function openPurchaseBroadcast() {
    pBroadcastText.value = commentText.value || ''
    pBroadcastScopeId.value = null
    pBroadcastDialog.value = true
    try {
      const data = await apiFetch<any>('/tasks/broadcast/scopes')
      pBroadcastOrgs.value = data.organizations || []
      pBroadcastDepts.value = data.departments || []
      if (pBroadcastOrgs.value.length === 1) pBroadcastScopeId.value = pBroadcastOrgs.value[0]!.id
    } catch {}
  }

  async function sendPurchaseBroadcast() {
    if (!purchaseId.value || !pBroadcastText.value.trim()) return
    pBroadcastSending.value = true
    try {
      const res = await apiFetch<any>(`/purchases/${purchaseId.value}/broadcast`, {
        method: 'POST',
        body: JSON.stringify({
          text: pBroadcastText.value.trim(),
          scope: pBroadcastScope.value,
          scope_id: pBroadcastScope.value !== 'all' ? pBroadcastScopeId.value : undefined,
        }),
      })
      pBroadcastDialog.value = false
      commentText.value = ''
      showSnack(`Отправлено: ${res.sent} из ${res.total_users} сотрудников`)
      await reloadComments()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка рассылки', 'error')
    } finally { pBroadcastSending.value = false }
  }

  return {
    pBroadcastDialog, pBroadcastScope, pBroadcastScopeId, pBroadcastText,
    pBroadcastSending, pBroadcastOrgs, pBroadcastDepts,
    openPurchaseBroadcast, sendPurchaseBroadcast,
  }
}
