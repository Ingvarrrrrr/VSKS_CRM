// Общий хелпер «не писать ответ на устаревший запрос» (ПРАВИЛО №6 — один
// механизм, не три копии одной и той же проверки токена в разных местах).
//
// Повод: баннер сверки выписки (SubsidyPaymentControlBanner.vue) показал цифры
// ЧУЖОЙ субсидии — владелец переключил субсидию 7 → 89, запрос /subsidies/7/
// payment-control считался дольше и его ответ пришёл ПОСЛЕ ответа по 89,
// затерев правильные данные (race condition по времени ответа, не по порядку
// отправки запросов).
//
// Использование:
//   const guard = useLatestRequest()
//   const token = guard.next()
//   const res = await fetchSomething()
//   if (!guard.isCurrent(token)) return // пришёл ответ не на последний запрос — отбросить
//   data.value = res
export interface LatestRequestGuard {
  /** Пометить начало нового запроса, вернуть токен для последующей проверки. */
  next(): number
  /** true — токен соответствует последнему выданному next() (ответ ещё актуален). */
  isCurrent(token: number): boolean
}

export function useLatestRequest(): LatestRequestGuard {
  let current = 0
  return {
    next(): number {
      current += 1
      return current
    },
    isCurrent(token: number): boolean {
      return token === current
    },
  }
}
