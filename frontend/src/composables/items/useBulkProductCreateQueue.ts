// useBulkProductCreateQueue.ts — массовое «Добавить в каталог» (владелец,
// 14.10): вместо одного POST /products/bulk-from-purchase-items (эндпоинт не
// удаляем, просто фронт больше не зовёт его — у него нет общей формы, товар
// заводился с одной категорией 'Прочее' без возможности правки) открывает
// ЕДИНОЕ окно товара (components/products/ProductEditorDialog.vue, ПРАВИЛО
// №6) ПО ОЧЕРЕДИ для каждой выбранной позиции без product_id, с
// предзаполнением name/unit/price из позиции. «Пропустить» — к следующей без
// создания; закрытие диалога — конец очереди.
//
// Привязка сохранённого товара к позиции — тот же путь, что и одиночное
// «Добавить товар» (PurchaseItemsEditor.vue::onProductEditorSaved):
// onItemProductSelect + POST /purchases/{id}/items/{itemId}/set-product,
// второй механизм линковки не заводим.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export interface BulkQueueItem {
  idx: number
  name: string
  unit?: string | null
  price?: number | null
  rowId?: number | null
}

export interface UseBulkProductCreateQueueDeps {
  purchaseId?: number | null
  onItemProductSelect: (idx: number, val: any) => void
  showSnack: (text: string, color?: ToastType) => void
}

export function useBulkProductCreateQueue(deps: UseBulkProductCreateQueueDeps) {
  const queue = ref<BulkQueueItem[]>([])
  const queuePos = ref(0)
  const queueTotal = ref(0)
  const queueDone = ref(0)
  const active = ref(false)

  const queueLabel = computed(() =>
    active.value ? `Позиция ${queuePos.value + 1} из ${queueTotal.value}` : '',
  )

  function current(): BulkQueueItem | null {
    return active.value ? (queue.value[queuePos.value] ?? null) : null
  }

  function start(items: BulkQueueItem[]): BulkQueueItem | null {
    if (!items.length) return null
    queue.value = items
    queuePos.value = 0
    queueTotal.value = items.length
    queueDone.value = 0
    active.value = true
    return current()
  }

  function finish() {
    if (active.value) {
      deps.showSnack(`Добавлено в каталог: ${queueDone.value} из ${queueTotal.value}`, 'success')
    }
    active.value = false
    queue.value = []
  }

  // К следующей позиции очереди; null — очередь закончена (finish() уже вызван).
  function advance(): BulkQueueItem | null {
    queuePos.value += 1
    const next = current()
    if (!next) finish()
    return next
  }

  // Товар сохранён (создан/выбран существующий дубликат) — привязать к
  // текущей позиции очереди и перейти к следующей.
  async function onSaved(saved: { id: number; name?: string }): Promise<BulkQueueItem | null> {
    const item = current()
    queueDone.value += 1
    if (item) {
      deps.onItemProductSelect(item.idx, saved)
      if (deps.purchaseId && item.rowId && saved.id) {
        try {
          await apiFetch(`/purchases/${deps.purchaseId}/items/${item.rowId}/set-product`,
            { method: 'POST', body: { product_id: saved.id } })
        } catch (e) { console.warn('Failed to persist product_id link', e) }
      }
    }
    return advance()
  }

  // «Пропустить» — без создания товара, к следующей позиции.
  function onSkip(): BulkQueueItem | null {
    return advance()
  }

  // Диалог закрыт без сохранения/пропуска — пользователь прервал очередь.
  function onClosed() {
    if (active.value) finish()
  }

  return {
    active, queueLabel,
    start, current, onSaved, onSkip, onClosed,
  }
}
