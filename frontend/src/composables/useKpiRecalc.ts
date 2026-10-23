// Общий флаг «карточки пересчитываются» + токен последнего запроса — задача
// владельца (23.10.2026, доп. к payroll_view): после переключения «ФОТ: Всё /
// Только закупки / Только ФОТ» (useKpiPrefs.ts::payrollView) или «Целиком /
// Товары и услуги» (kpiTypeSplit) карточки денег какое-то время показывают
// СТАРЫЕ числа, пока не придёт новый ответ /dashboard/charts — люди не
// понимают, что происходит.
//
// Module-level singleton (тот же приём, что useKpiPrefs.ts) — ОБЩИЙ для
// дашборда (KpiCardsWidget.vue/useDashboardData.ts) и карточки субсидии
// (SubsidyKpiCards.vue/SubsidiesView.vue): один и тот же индикатор над
// карточками и в переключателе, не две копии состояния (Правило №6).
//
// Токен — защита от устаревшего ответа при быстрых повторных кликах по
// переключателю: вызывающий код получает номер своего запроса из
// startRecalc(), и ПЕРЕД применением полученных данных обязан проверить
// isCurrent(token) — если за время запроса стартовал более новый вызов,
// данные устарели и должны быть отброшены молча (не перезаписывать числа
// актуального режима числами предыдущего). finishRecalc(token) гасит флаг
// «пересчитывается» только если токен ещё самый свежий — иначе более новый
// запрос всё ещё летит, и индикатор должен остаться включённым.
import { ref } from 'vue'

let _api: ReturnType<typeof buildKpiRecalc> | null = null

export function useKpiRecalc() {
  if (!_api) _api = buildKpiRecalc()
  return _api
}

function buildKpiRecalc() {
  const recalculating = ref(false)
  let token = 0

  /** Начать новый пересчитывающий запрос. Включает флаг и возвращает номер
   * этого запроса — передать его в isCurrent()/finishRecalc(). */
  function startRecalc(): number {
    recalculating.value = true
    return ++token
  }

  /** true — myToken ещё самый свежий из начатых (ответ можно применять).
   * false — за это время стартовал более новый вызов, ответ устарел. */
  function isCurrent(myToken: number): boolean {
    return myToken === token
  }

  /** Вызывать из finally ПОСЛЕ применения (или отбрасывания) данных запроса
   * myToken. Гасит индикатор только если myToken — ещё самый свежий; если
   * за это время стартовал новый запрос, индикатор остаётся включённым
   * (его погасит finishRecalc того, нового, вызова). */
  function finishRecalc(myToken: number) {
    if (isCurrent(myToken)) recalculating.value = false
  }

  return { recalculating, startRecalc, isCurrent, finishRecalc }
}
