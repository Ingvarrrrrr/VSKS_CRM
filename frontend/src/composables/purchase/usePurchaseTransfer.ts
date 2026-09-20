// usePurchaseTransfer.ts — «Перенести позиции в другую закупку заявки»
// (владелец, замечание 2, правка 2026-09-21): полноэкранный канбан-перенос
// позиций МЕЖДУ уже существующими закупками одной заявки, открытый ПРЯМО ИЗ
// формы закупки (не только из карточки заявки «Распределить», как раньше).
// Переиспользует components/wishes/WishKanbanDialog.vue в ветке
// wish.status==='converted' (WishPurchasesKanban.vue) — второй канбан/диалог не
// заводим (Правило №6). WishKanbanDialog вызывает useWishesContext() внутри
// (ctx.showSnack для сетевых ошибок доски) — компонент рассчитан на предка,
// вызвавшего provideWishesContext(); CreateOrderView.vue не входит в дерево
// WishesView.vue, поэтому зовёт provideWishesContext() сам (см. вызов в файле).
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { Wish } from '@/composables/wishes/wishTypes'

export function usePurchaseTransfer(
  purchaseData: Ref<any>,
  isContracted: ComputedRef<boolean>,
  isEdit: ComputedRef<boolean>,
  reloadPurchase: () => Promise<void> | void,
) {
  const transferKanbanDialog = ref(false)

  // WishKanbanDialog/WishPurchasesKanban читают из wish ТОЛЬКО id (title/toolbar)
  // и status==='converted' (выбор ветки шаблона) — остальные поля Wish обязательны
  // по типу, но не используются этой веткой, заполняем пустыми безопасными
  // значениями (см. докстринг WishKanbanDialog.vue: 'converted' → WishPurchasesKanban,
  // единственный потребитель которой — сама доска по wishId).
  const transferWish = computed<Wish | null>(() => {
    const wishId = purchaseData.value?.wish_id
    if (wishId == null) return null
    return {
      id: wishId,
      org_id: 0,
      title: '',
      status: 'converted',
      created_by: 0,
      created_at: '',
      updated_at: '',
    }
  })

  // Доступно только у СОХРАНЁННОЙ закупки из заявки, до заключения договора —
  // тот же порог, что и у «Разбить на закупки» (usePurchaseSplit.ts,
  // LOCKED_SPLIT_STATUSES), единственное отличие — здесь без исключения для
  // ADMIN_ROLES (перенос между закупками ОДНОЙ заявки менее рискован, чем
  // разбиение, но после договора состав уже зафиксирован документом).
  const canTransferToSiblingPurchase = computed(() =>
    isEdit.value && transferWish.value != null && !isContracted.value,
  )

  // Закрытие диалога (после DnD-переноса позиций между закупками) — перезагружаем
  // ТЕКУЩУЮ закупку целиком (её собственный состав/суммы могли измениться), тот
  // же приём, что и onPurchaseSplit/saveSplit (reload-requested → loadPurchase).
  watch(transferKanbanDialog, (open, wasOpen) => {
    if (!open && wasOpen) void reloadPurchase()
  })

  return { transferKanbanDialog, transferWish, canTransferToSiblingPurchase }
}
