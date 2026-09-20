// useWishDistributionReset.ts — «Сбросить разбивку» (владелец, лист 2 №3,
// 2026-09-20). Заявку откатили с 'converted' обратно (реджект/повторное
// согласование после правки сенситивных полей — см. update_wish в
// backend/app/routers/wishes.py) — закупки, которые из неё уже были созданы,
// НЕ удаляются: _withdraw_wish_from_plan (backend/app/services/wish_distribution.py)
// прячет их в скрытый статус 'wishes', чтобы сохранить историю/файлы/чаты, и при
// следующем approve-distribution гейт вернёт их в план С ТОЙ ЖЕ разбивкой по
// колонкам. Если пользователю эта старая разбивка больше не нужна — эта кнопка
// удаляет скрытые закупки насовсем (DELETE /wishes/{id}/distribution), и при
// следующем согласовании канбан соберётся заново с нуля. Отдельный файл (не
// внутри useWishActions.ts/useWishForm.ts — оба уже большие) — Правило №5.
import { ref } from 'vue'
import type { WishesContext } from './useWishesContext'
import type { Wish } from './wishTypes'
import { describeApiError } from '@/utils/apiErrorMessage'

export function useWishDistributionReset(deps: {
  ctx: Pick<WishesContext, 'showSnack'>
  apiFetch: typeof import('@/api').apiFetch
  reloadActiveTab: () => Promise<void>
}) {
  const { ctx, apiFetch, reloadActiveTab } = deps

  const hiddenPurchasesCount = ref(0)
  const checkedForWishId = ref<number | null>(null)
  const checkingHiddenPurchases = ref(false)

  // Ленивая проверка — только когда карточка открыта (не в списках, дорогой
  // запрос отдаёт позиции всех закупок заявки). Кэш по wishId в этом же
  // открытии карточки: повторные вызовы (например, после каждого автосейва)
  // не долбят сервер заново.
  async function checkHiddenPurchases(wish: Pick<Wish, 'id' | 'status'>) {
    if (!wish?.id || wish.status === 'converted') {
      hiddenPurchasesCount.value = 0
      checkedForWishId.value = wish?.id ?? null
      return
    }
    if (checkedForWishId.value === wish.id) return
    checkingHiddenPurchases.value = true
    checkedForWishId.value = wish.id
    try {
      const board = await apiFetch<{ purchases: { status: string }[] }>(`/wishes/${wish.id}/purchases-board`)
      hiddenPurchasesCount.value = (board.purchases || []).filter(p => p.status === 'wishes').length
    } catch {
      // Тихо — это фоновая проверка для необязательной кнопки, не роняем карточку.
      hiddenPurchasesCount.value = 0
    } finally {
      checkingHiddenPurchases.value = false
    }
  }

  function forgetHiddenPurchasesCheck() {
    checkedForWishId.value = null
    hiddenPurchasesCount.value = 0
  }

  const resetDialog = ref(false)
  const resetting = ref(false)
  function openResetDialog() {
    resetDialog.value = true
  }

  async function confirmResetDistribution(wish: Pick<Wish, 'id'>) {
    if (!wish?.id || resetting.value) return
    resetting.value = true
    try {
      const res = await apiFetch<{ deleted_purchase_ids: number[] }>(`/wishes/${wish.id}/distribution`, { method: 'DELETE' })
      const n = res?.deleted_purchase_ids?.length ?? 0
      ctx.showSnack(`Разбивка сброшена — удалено скрытых закупок: ${n}`)
      resetDialog.value = false
      hiddenPurchasesCount.value = 0
      await reloadActiveTab()
    } catch (e: any) {
      ctx.showSnack(describeApiError(e, { fallback: 'Не удалось сбросить разбивку' }), 'error')
    } finally {
      resetting.value = false
    }
  }

  return {
    hiddenPurchasesCount, checkingHiddenPurchases, checkHiddenPurchases, forgetHiddenPurchasesCheck,
    resetDialog, resetting, openResetDialog, confirmResetDistribution,
  }
}

export type UseWishDistributionResetReturn = ReturnType<typeof useWishDistributionReset>
