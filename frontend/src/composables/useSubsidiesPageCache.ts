// useSubsidiesPageCache.ts — поведение SubsidiesView.vue внутри App.vue's
// <keep-alive> (план «мгновенный возврат на главные страницы», 2026-10-13).
// Отдельно от общего usePageCache.ts (composables/usePageCache.ts), потому
// что у этой страницы есть то, чего нет у остальных четырёх кэшируемых:
// глобальный window keydown для Ctrl+Z/Ctrl+Y отката дерева ФЭО
// (handleFeoUndoKeydown, см. SubsidiesView.vue onMounted) — хоткей не должен
// срабатывать, пока человек смотрит Закупки/Сводную/т.д.
import { onActivated, onDeactivated } from 'vue'

export interface UseSubsidiesPageCacheOptions {
  // Тихое обновление списка субсидий + дерева ФЭО выбранной субсидии.
  // Вызывающий передаёт уже существующие «тихие» функции (silentRefreshSubsidies/
  // loadFeo) — здесь НЕ заводится вторая формула/механизм загрузки (Правило №6).
  refresh: () => void | Promise<void>
  keydownHandler: (e: KeyboardEvent) => void
}

export function useSubsidiesPageCache(options: UseSubsidiesPageCacheOptions) {
  // onMounted самой SubsidiesView.vue уже подписал handleFeoUndoKeydown на
  // первую (она же "mount") активацию — здесь ничего дополнительно не
  // делаем на ней, чтобы не навесить слушатель дважды.
  let firstActivation = true

  onActivated(() => {
    if (firstActivation) {
      firstActivation = false
      return
    }
    window.addEventListener('keydown', options.keydownHandler)
    void options.refresh()
  })

  onDeactivated(() => {
    window.removeEventListener('keydown', options.keydownHandler)
  })
}
