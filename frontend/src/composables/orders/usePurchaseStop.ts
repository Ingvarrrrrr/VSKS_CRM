// Остановка/возобновление закупки (владелец, 2026-09-15) — единый механизм
// для вкладки «Закупки» (OrdersView.vue → useOrdersData.ts) и карточки
// закупки (CreateOrderView.vue): POST /api/purchases/{id}/stop и /resume
// (backend/app/routers/purchase_stop.py). ПРАВИЛО №6 — один composable,
// не отдельная копия кнопки+запроса в каждом view.
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Purchase } from './ordersTypes'

export type PurchaseStopMode = 'stop' | 'resume'

export interface PurchaseStopDialogState {
  show: boolean
  mode: PurchaseStopMode
  purchase: Purchase | null
  reason: string
}

export function usePurchaseStop(opts: { showSnack: (text: string, color?: ToastType) => void }) {
  const { showSnack } = opts

  const dialog = reactive<PurchaseStopDialogState>({
    show: false,
    mode: 'stop',
    purchase: null,
    reason: '',
  })
  const loading = ref(false)

  function openStop(item: Purchase) {
    dialog.purchase = item
    dialog.mode = 'stop'
    dialog.reason = ''
    dialog.show = true
  }

  function openResume(item: Purchase) {
    dialog.purchase = item
    dialog.mode = 'resume'
    dialog.reason = ''
    dialog.show = true
  }

  // onUpdated получает обновлённую закупку с сервера — вызывающий сам решает,
  // как её применить (заменить строку в списке / перезагрузить карточку).
  async function confirm(onUpdated: (updated: Purchase) => void) {
    if (!dialog.purchase) return
    loading.value = true
    const item = dialog.purchase
    const mode = dialog.mode
    try {
      const path = mode === 'stop' ? `/purchases/${item.id}/stop` : `/purchases/${item.id}/resume`
      const body: Record<string, string> = {}
      if (mode === 'stop' && dialog.reason.trim()) body.reason = dialog.reason.trim()
      const updated = await apiFetch<Purchase>(path, { method: 'POST', body: JSON.stringify(body) })
      showSnack(mode === 'stop' ? 'Закупка остановлена' : 'Закупка возобновлена')
      dialog.show = false
      onUpdated(updated)
    } catch (e: any) {
      const msg = e?.payload?.message || e?.detail || e?.message || 'неизвестная ошибка'
      showSnack(`Не удалось ${mode === 'stop' ? 'остановить' : 'возобновить'} закупку: ${msg}`, 'error')
    } finally {
      loading.value = false
    }
  }

  return { dialog, loading, openStop, openResume, confirm }
}
