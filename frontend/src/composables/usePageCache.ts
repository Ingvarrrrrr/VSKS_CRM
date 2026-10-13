// usePageCache.ts — поведение страницы внутри App.vue's <keep-alive> (план
// «мгновенный возврат на главные страницы», 2026-10-13). Переиспользуется
// DashboardView/OrdersView/WishesView/MyTasksView (у SubsidiesView — своя
// версия, useSubsidiesPageCache.ts, из-за доп. window-listener'а и диалога).
//
// onActivated вызывается Vue'ом ДВА раза за жизненный цикл инстанса: сразу
// после обычного монтирования (когда страница открыта первый раз) и затем
// при каждом возврате из кэша. Первый вызов дублировал бы то, что страница
// уже сделала в своём onMounted — пропускаем его явно.
import { onActivated, onDeactivated } from 'vue'

export interface UsePageCacheOptions {
  // Фоновое "тихое" обновление данных при возврате на страницу. Страница
  // сама отвечает за то, чтобы не показывать спиннер/скелетон поверх уже
  // видимого контента (переиспользовать существующий «тихий» путь загрузки,
  // если он уже есть — см. комментарии в местах вызова).
  refresh: () => void | Promise<void>
  // Что-то, что нужно остановить, пока страница спрятана в кэше (таймер,
  // подписка) — симметрично restart() ниже.
  onLeave?: () => void
  // Что-то, что нужно возобновить ДО refresh() при возврате (например,
  // перезапустить setInterval).
  onReturn?: () => void
}

export function usePageCache(options: UsePageCacheOptions) {
  let firstActivation = true

  onActivated(() => {
    if (firstActivation) {
      firstActivation = false
      return
    }
    options.onReturn?.()
    void options.refresh()
  })

  onDeactivated(() => {
    options.onLeave?.()
  })
}
