// Общий хелпер сохранения/восстановления прокрутки дерева ФЭО на время
// обновления данных без полной перезагрузки (loadFeo уже умел это точечно —
// см. докстринг там; жалоба владельца 30.09, п.5: «удаление плановой позиции
// по-прежнему бросает наверх страницы», «изменил сумму в категории — опять
// перекинуло вверх» — у удаления/правки/добавления плановой позиции того же
// сохранения не было). Один механизм на все эти пути (Правило №6) — не
// дублируем save/restore в каждом месте отдельно.
//
// Прокрутка «прыгает» наверх по той же причине, что была разобрана в loadFeo:
// пока список под v-if/замена данных на миг меняет высоту документа, браузер
// подрезает window.scrollY, а внутренний контейнер .feo-table-wrap теряет
// свой scrollTop. captureScroll() запоминает оба значения ДО операции,
// restoreScroll() выставляет их обратно ПОСЛЕ применения новых данных и
// ближайшего nextTick (дождаться перерисовки v-for, как и у
// scrollToFirstKpiHighlight/scrollToNewFeoNode).
//
// НАСТОЯЩАЯ причина жалобы владельца (07.10, воспроизведено в браузере,
// e2e/zz-checklist-fixes-0710.spec.ts): сохранение/удаление/правка плановой
// позиции закрывает v-dialog (showXxxDialog.value = false) ПЕРЕД вызовом
// withPreservedScroll — а именно это закрытие запускает Vuetify
// blockScrollStrategy (VOverlay/scrollStrategies.js): пока диалог был открыт,
// на <html> стояли класс `v-overlay-scroll-blocked` и `position: fixed; top:
// var(--v-body-scroll-y)` (VOverlay.css) — визуальная позиция сохранена ЭТИМ
// отступом, а не настоящим скроллом, поэтому window.scrollY в этот момент
// врёт и читается как 0. Снятие блокировки (и собственное, уже ПРАВИЛЬНОЕ,
// восстановление scrollTop самим Vuetify через onScopeDispose) происходит не
// синхронно, а на следующем тике размонтирования оверлея — captureScroll(),
// вызванный сразу после `.value = false` в том же тике, успевает прочитать
// window.scrollY ДО снятия блокировки и запоминает лживый 0. Когда
// restoreScroll() позже вызывает window.scrollTo({top: 0}), он ЗАТИРАЕТ уже
// корректно восстановленную Vuetify позицию — ровно то, что видел владелец
// (scrollTop внутреннего .feo-table-wrap не ломается, т.к. он не входит в
// scrollElements оверлея — тот блокирует только html/реальных scroll-parent'ов
// диалога).
//
// Фикс — внутри этого единственного механизма (Правило №6, второй
// save/restore не заводим): если в момент захвата html ещё заблокирован,
// берём настоящее значение не из window.scrollY, а из той же CSS-переменной
// --v-body-scroll-y, которую сам Vuetify использует для позиционирования
// (realWindowScrollY). Перед восстановлением — ждём снятия блокировки (класс
// уйдёт после размонтирования оверлея), иначе наш window.scrollTo либо не
// подействует (html ещё position:fixed), либо случайно совпадёт по времени с
// restore самого Vuetify. waitForScrollUnblock ограничен ~1с (requestAnimationFrame-
// цикл), чтобы не зависнуть, если блокировку почему-то не сняли вовсе.
import { nextTick } from 'vue'

function isHtmlScrollBlocked(): boolean {
  return document.documentElement.classList.contains('v-overlay-scroll-blocked')
}

// Настоящая прокрутка страницы в момент, когда html уже залочен Vuetify
// (window.scrollY в этот момент всегда 0 — см. докстринг выше) — читаем её из
// той же переменной, которую сам Vuetify выставил при входе в блокировку
// (scrollStrategies.js: `el.style.setProperty('--v-body-scroll-y', -scrollTop)`).
function realWindowScrollY(): number {
  if (isHtmlScrollBlocked()) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--v-body-scroll-y')
    const val = parseFloat(raw)
    if (!Number.isNaN(val)) return -val
  }
  return window.scrollY
}

async function waitForScrollUnblock(timeoutMs = 1000): Promise<void> {
  const start = performance.now()
  while (isHtmlScrollBlocked() && performance.now() - start < timeoutMs) {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  }
}

export function captureScroll(scrollEl?: HTMLElement | null): () => Promise<void> {
  const savedScrollTop = scrollEl ? scrollEl.scrollTop : null
  const savedWindowScrollY = realWindowScrollY()
  return async function restoreScroll() {
    await nextTick()
    // Дожидаемся, пока Vuetify снимет свою блокировку (и сам восстановит
    // scrollTop) — иначе наш window.scrollTo либо не подействует, пока html
    // ещё position:fixed, либо гонка со снятием блокировки отменит эффект.
    await waitForScrollUnblock()
    if (scrollEl && savedScrollTop != null) scrollEl.scrollTop = savedScrollTop
    window.scrollTo({ top: savedWindowScrollY })
  }
}

// withPreservedScroll(scrollEl, fn) — то же самое одним вызовом для мест,
// где нет собственного try/finally вокруг обновления (удаление/правка/
// добавление плановой позиции, инлайн-правка типа). loadFeo() в
// SubsidiesView.vue использует captureScroll()/restoreScroll() отдельно —
// там уже есть свой finally с условием isRefresh, подменять его структуру
// ради единообразия не нужно (риск параллельной правки того файла).
export async function withPreservedScroll<T>(
  scrollEl: HTMLElement | null | undefined,
  fn: () => Promise<T>,
): Promise<T> {
  const restoreScroll = captureScroll(scrollEl)
  try {
    return await fn()
  } finally {
    await restoreScroll()
  }
}
