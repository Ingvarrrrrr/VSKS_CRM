// latestRequest.ts — ЕДИНЫЙ механизм «последний запрос побеждает» (ПРАВИЛО №6).
//
// Повод (владелец, 26.10.2026): в заявке при поиске товара по имени «Боевая»
// список сначала показывал правильный результат, а через секунду подменялся
// «болгаркой» — ответ на раннее «бо»/«боев» прилетал ПОСЛЕ ответа на
// «боевая» и перетирал уже правильный список. Причина — отмена устаревших
// ответов была реализована только в useProductSearch.ts, а
// InlineProductMatch.vue (поле «Наименование» позиции заявки) своего запроса
// вообще не отменял.
//
// Логика (без изменений — просто вынесена из useProductSearch.ts::run(), где
// жила инлайн) — ДВА механизма сразу, не один вместо другого:
//  - AbortController прерывает сетевой запрос физически;
//  - счётчик seq отбрасывает ответ, даже если он успел прилететь ДО того, как
//    abort долетел до браузера (гонка).
// Это теперь ЕДИНОЕ место (ПРАВИЛО №6) — useProductSearch.ts и
// InlineProductMatch.vue (и любой будущий потребитель с той же проблемой)
// берут его отсюда, а не копируют seq/controller у себя.
export interface LatestRequestGuardToken {
  /** Передать в apiFetch({ signal }) — физически прерывает сетевой запрос,
      если begin() вызовут снова раньше, чем этот запрос завершится. */
  signal: AbortSignal
  /** Проверить ПОСЛЕ await: true — этот ответ устарел (кто-то успел начать
      новый запрос), применять его результат нельзя, даже если сеть не
      успела прервать отправку (гонка). */
  isStale: () => boolean
}

export interface LatestRequestGuard {
  /** Начать новый запрос: отменяет предыдущий (если был) и возвращает токен
      этого запроса (signal + isStale). Звать один раз на каждый запрос,
      СРАЗУ перед вызовом apiFetch. */
  begin: () => LatestRequestGuardToken
}

export function createLatestRequestGuard(): LatestRequestGuard {
  let seq = 0
  let controller: AbortController | null = null

  function begin(): LatestRequestGuardToken {
    if (controller) controller.abort()
    controller = new AbortController()
    const mySeq = ++seq
    const signal = controller.signal
    return {
      signal,
      isStale: () => mySeq !== seq,
    }
  }

  return { begin }
}
