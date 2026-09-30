// useWishPurchaseNav.ts — «Перейти в закупку» в карточке заявки (владелец, 30.09).
// Заявка распределяется на одну или несколько закупок (см. app/services/
// wish_distribution.py); эта кнопка должна открыть закупку/закупки заявки
// прямо из карточки, рядом со «Скачать Excel»/«Скопировать заявку». Данные —
// ТОТ ЖЕ эндпоинт GET /wishes/{id}/purchases-board, что уже использует
// useWishDistributionReset.ts (checkHiddenPurchases) — второй запрос не заводим
// (ПРАВИЛО №6). Компаньон авансового отчёта (Wish.source === 'advance_report')
// открывается маршрутом /advance-reports/{id}/edit (см. AdvanceReportsView.vue),
// обычная закупка — /orders/{id}/edit (тот же путь, что и везде в проекте, см.
// useWishesContext.ts::goToWishPurchases). Одна закупка — сразу переход,
// несколько — меню со списком «РЕЕ-… — статус» (шаблон в WishFormDialog.vue).
// Отдельный файл — Правило №5 (WishFormDialog.vue и так один из самых больших).
import { ref } from 'vue'
import type { Wish } from './wishTypes'

export interface WishPurchaseNavItem {
  id: number
  registry_number: string | null
  purchase_number: string | null
  subject?: string | null
  status: string
  status_label: string
}

export function useWishPurchaseNav(deps: {
  apiFetch: typeof import('@/api').apiFetch
  router: { push: (to: any) => any }
}) {
  const { apiFetch, router } = deps

  const relatedPurchases = ref<WishPurchaseNavItem[]>([])
  const loadedForWishId = ref<number | null>(null)
  const loading = ref(false)

  // Ленивая загрузка с кэшем по wishId (тот же приём, что checkHiddenPurchases в
  // useWishDistributionReset.ts) — повторные открытия/автосейвы той же заявки
  // не долбят сервер заново; forgetRelatedPurchases() перед новым openEdit().
  async function loadRelatedPurchases(wish: Pick<Wish, 'id'> | null | undefined) {
    if (!wish?.id) {
      relatedPurchases.value = []
      loadedForWishId.value = null
      return
    }
    if (loadedForWishId.value === wish.id) return
    loading.value = true
    loadedForWishId.value = wish.id
    try {
      const board = await apiFetch<{ purchases: WishPurchaseNavItem[] }>(`/wishes/${wish.id}/purchases-board`)
      // status='wishes' — скрытая старая разбивка (заявку откатили с 'converted',
      // см. useWishDistributionReset.ts) — не редактируется как обычная закупка,
      // переходить в неё нечего.
      relatedPurchases.value = (board.purchases || []).filter(p => p.status !== 'wishes')
    } catch {
      // Тихо — вспомогательная кнопка, не роняем карточку заявки из-за неё.
      relatedPurchases.value = []
    } finally {
      loading.value = false
    }
  }

  function forgetRelatedPurchases() {
    loadedForWishId.value = null
    relatedPurchases.value = []
  }

  function routeForPurchase(purchaseId: number, wish: Pick<Wish, 'source'> | null | undefined): string {
    return wish?.source === 'advance_report'
      ? `/advance-reports/${purchaseId}/edit`
      : `/orders/${purchaseId}/edit`
  }

  function goToPurchase(purchaseId: number, wish: Pick<Wish, 'source'> | null | undefined) {
    router.push(routeForPurchase(purchaseId, wish))
  }

  // Один результат — сразу переход (кнопка сама решает, вызывать меню или это).
  function goToSinglePurchase(wish: Pick<Wish, 'source'> | null | undefined) {
    const p = relatedPurchases.value[0]
    if (p) goToPurchase(p.id, wish)
  }

  return {
    relatedPurchases, loading, loadRelatedPurchases, forgetRelatedPurchases,
    routeForPurchase, goToPurchase, goToSinglePurchase,
  }
}

export type UseWishPurchaseNavReturn = ReturnType<typeof useWishPurchaseNav>
