// useFeoPlannedConsumers — «Кто расходует план» (владелец, 2026-08-20):
// расшифровка GET /feo-planned-items/{id}/consumers, три группы (позиции ЭТОЙ
// формы / другие закупки / другие заявки), обязаны в сумме дать ровно то же
// «выбрано»/«остаток», что строка списка. Вынесено дословно из
// FeoPlannedItemsSelect.vue (рефакторинг монолита, 2026-09-08).
import { computed, reactive } from 'vue'
import { apiFetch } from '@/api'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { PendingItemEntry } from './useFeoPlannedRows'

export interface FeoPlannedConsumer {
  type: 'purchase' | 'wish'
  counts_towards_consumed: boolean
  item_name: string
  quantity: number | null
  unit: string | null
  amount: number
  purchase_id?: number
  purchase_number?: number | null
  registry_number?: string | null
  purchase_subject?: string | null
  wish_id?: number | null
  wish_title?: string | null
  author_name?: string | null
  status: string
  status_label: string
}

export interface FeoPlannedConsumersResponse {
  planned_item_id: number
  planned_item_name: string
  planned_amount: number
  consumed: number
  residual: number
  consumers: FeoPlannedConsumer[]
}

export interface UseFeoPlannedConsumersDeps {
  props: {
    purchaseId?: number | null
    wishId?: number | null
    excludeWishId?: number | null
    excludePurchaseId?: number | null
  }
  pendingItemsFor: (row: FeoPlanPosition) => PendingItemEntry[]
}

// ───────────────────────────────────────────────────────────────────────────
// «Кто расходует план» (владелец, 2026-08-20): «Откуда у 14 футболок... остаток
// 4512? Я ничего к ним не привязывал. Я не могу это найти. Нигде этого не
// видно» — строка показывает «план X · выбрано Y · остаток Z», но КТО съел Y
// нигде не видно. Клик по «выбрано» (только у kind==='planned_item' — только
// у него есть отдельная запись FeoPlannedItem, к которой можно обратиться;
// у plan_position/feo_article «выбрано» — это сумма по всему поддереву
// категории, для неё такой расшифровки бэкенд не считает) открывает диалог
// с расшифровкой GET /feo-planned-items/{id}/consumers.
export function useFeoPlannedConsumers(deps: UseFeoPlannedConsumersDeps) {
  const { props, pendingItemsFor } = deps

  const consumersDialog = reactive<{
    open: boolean
    loading: boolean
    error: string | null
    row: FeoPlanPosition | null
    data: FeoPlannedConsumersResponse | null
  }>({ open: false, loading: false, error: null, row: null, data: null })

  async function openConsumers(row: FeoPlanPosition) {
    if (row.kind !== 'planned_item') return
    consumersDialog.row = row
    consumersDialog.open = true
    consumersDialog.loading = true
    consumersDialog.error = null
    consumersDialog.data = null
    try {
      const parts: string[] = []
      if (props.excludePurchaseId != null) parts.push(`exclude_purchase_id=${props.excludePurchaseId}`)
      if (props.excludeWishId != null) parts.push(`exclude_wish_id=${props.excludeWishId}`)
      const qs = parts.length ? `?${parts.join('&')}` : ''
      consumersDialog.data = await apiFetch<FeoPlannedConsumersResponse>(
        `/feo-planned-items/${row.id}/consumers${qs}`,
      )
    } catch (e: any) {
      consumersDialog.error = e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось загрузить расшифровку расхода плана'
    } finally {
      consumersDialog.loading = false
    }
  }

  // Три группы расшифровки — обязаны в сумме дать ровно то же Y/Z, что строка списка
  // (см. итоговую строку диалога в шаблоне, которая берёт числа через consumedFor/
  // residualFor(consumersDialog.row), а не пересчитывает их сама, чтобы гарантированно
  // совпасть):
  //   1) pendingItemsFor(row) — позиции ЭТОЙ ЖЕ открытой формы (WishesView/PurchaseItemsEditor
  //      localItems), ещё не обязательно сохранённые на сервер — источник pendingFor(row);
  //   2) серверные consumers типа 'purchase' из ДРУГИХ закупок (не той, что сейчас
  //      редактируется — props.purchaseId, её собственные строки уже показаны группой 1);
  //   3) серверные consumers типа 'wish' из ДРУГИХ заявок (не той, что сейчас редактируется —
  //      props.wishId, по той же причине) — план не резервируют, показаны для полноты.
  const dialogPendingItems = computed((): PendingItemEntry[] =>
    consumersDialog.row ? pendingItemsFor(consumersDialog.row) : []
  )
  const dialogOtherPurchases = computed((): FeoPlannedConsumer[] =>
    (consumersDialog.data?.consumers || []).filter(c => c.type === 'purchase' && c.purchase_id !== props.purchaseId)
  )
  const dialogOtherWishes = computed((): FeoPlannedConsumer[] =>
    (consumersDialog.data?.consumers || []).filter(c => c.type === 'wish' && c.wish_id !== props.wishId)
  )
  const dialogIsEmpty = computed((): boolean =>
    dialogPendingItems.value.length === 0 && dialogOtherPurchases.value.length === 0 && dialogOtherWishes.value.length === 0
  )
  const dialogFormLabel = computed((): string => {
    if (props.purchaseId != null) return 'в этой закупке (сейчас на экране)'
    if (props.wishId != null) return 'в этой заявке (сейчас на экране)'
    return 'в этой форме (сейчас на экране)'
  })

  function goToPurchase(id: number | undefined) {
    if (id == null) return
    // Открываем в новой вкладке, а не router.push — этот диалог обычно висит
    // поверх ЕЩЁ НЕ сохранённой формы заявки/закупки (та самая, из которой его
    // открыли), уводить с неё нельзя.
    window.open(`/orders/${id}`, '_blank')
  }

  return {
    consumersDialog, openConsumers, dialogPendingItems, dialogOtherPurchases,
    dialogOtherWishes, dialogIsEmpty, dialogFormLabel, goToPurchase,
  }
}
