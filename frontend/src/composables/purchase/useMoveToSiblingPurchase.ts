// useMoveToSiblingPurchase.ts — «Перенести позиции в другую закупку заявки»
// (владелец, правка 2026-09-21, замечание 2): построчный перенос позиции ТЗ
// между закупками ОДНОЙ заявки, до формирования договора. Единственный источник
// (Правило №6) — и построчное меню действий (ItemsTableFlat/ItemsTableStages/
// ItemsCardsView через PurchaseItemsEditor.vue), и полноэкранный канбан-диалог
// «Перенести позиции в другую закупку заявки» в шапке CreateOrderView.vue читают
// один и тот же эндпоинт: GET /wishes/{wish_id}/purchases-board (тот же список
// закупок, что и WishPurchasesKanban.vue) + POST /purchases/{pid}/items/{iid}/move
// (тот же путь, что использует CategoryKanbanBoard-обвязка WishPurchasesKanban.vue).
// Второго источника списка «сестринских» закупок или второго POST не заводим.
import { ref, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import type { ToastType } from '@/composables/useToast'

export interface SiblingPurchaseOption {
  id: number
  label: string
  disabled: boolean
  disabledReason: string | null
}

interface SiblingBoardPurchase {
  id: number
  purchase_number?: string | number | null
  registry_number?: string | null
  status?: string | null
  status_label?: string | null
  frozen?: boolean
}

export function useMoveToSiblingPurchase(deps: {
  purchaseId: ComputedRef<number | null | undefined>
  wishId: ComputedRef<number | null | undefined>
  emitReload: () => void
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { purchaseId, wishId, emitReload, showSnack } = deps

  const siblingPurchases = ref<SiblingPurchaseOption[]>([])
  const siblingPurchasesLoading = ref(false)
  const moving = ref(false)
  // Кэш «на какую заявку уже загружали» — повторное открытие меню в той же
  // закупке не бьёт по сети заново; сбрасывается после каждого успешного
  // переноса (состав/заморозка соседних закупок могли поменяться).
  let loadedForWishId: number | null = null

  function labelOf(p: SiblingBoardPurchase): string {
    if (p.purchase_number != null) return `№${p.purchase_number}`
    if (p.registry_number) return p.registry_number
    return `#${p.id}`
  }

  async function ensureSiblingPurchasesLoaded(force = false) {
    const wid = wishId.value
    if (wid == null) {
      siblingPurchases.value = []
      return
    }
    if (!force && loadedForWishId === wid) return
    siblingPurchasesLoading.value = true
    try {
      const board = await apiFetch<{ wish_id: number; purchases: SiblingBoardPurchase[] }>(
        `/wishes/${wid}/purchases-board`,
      )
      siblingPurchases.value = (board.purchases || [])
        .filter(p => p.id !== purchaseId.value)
        .map(p => ({
          id: p.id,
          label: labelOf(p),
          disabled: !!p.frozen,
          disabledReason: p.frozen ? `заморожена — ${p.status_label || p.status || 'этап договора'}` : null,
        }))
      loadedForWishId = wid
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось загрузить закупки заявки', prefix: 'Ошибка' }), 'error')
      siblingPurchases.value = []
    } finally {
      siblingPurchasesLoading.value = false
    }
  }

  async function moveItemToPurchase(itemId: number | null | undefined, targetPurchaseId: number) {
    if (purchaseId.value == null || itemId == null) return
    moving.value = true
    try {
      await apiFetch(`/purchases/${purchaseId.value}/items/${itemId}/move`, {
        method: 'POST',
        body: JSON.stringify({ target_purchase_id: targetPurchaseId }),
      })
      // Состав/суммы ОБЕИХ закупок могли измениться (та же осторожность, что и в
      // WishPurchasesKanban.vue::onColumnChange) — родитель перезагружает закупку
      // целиком, второй точечный клиентский пересчёт не пишем.
      loadedForWishId = null
      emitReload()
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось перенести позицию в другую закупку', prefix: 'Ошибка' }), 'error')
    } finally {
      moving.value = false
    }
  }

  return { siblingPurchases, siblingPurchasesLoading, moving, ensureSiblingPurchasesLoaded, moveItemToPurchase }
}
