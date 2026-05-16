// Phase 26-QQQ: sticky horizontal scrollbar для всех v-data-table.
//
// Проблема: естественный горизонтальный скролл в .v-table__wrapper находится
// в самом низу обёртки. На длинных таблицах низ за viewport → пользователю
// нужно прокрутить страницу вниз чтобы добраться до скроллбара. CSS max-height
// не помогает (Vuetify добавляет промежуточные wrapper'ы, sticky внутри
// карточек ломается).
//
// Решение: создаём fake-скроллбар position:fixed bottom:0, который синхронно
// двигается с реальным scrollLeft таблицы. Виден всегда пока таблица в viewport
// и имеет горизонтальный overflow.

const ATTACHED = new WeakSet<HTMLElement>()
const STATES = new WeakMap<HTMLElement, { fake: HTMLDivElement; cleanup: () => void }>()
let globalListenersAttached = false
const updateCallbacks: Array<() => void> = []

function attach(el: HTMLElement) {
  if (ATTACHED.has(el)) return
  ATTACHED.add(el)

  const fake = document.createElement('div')
  fake.className = '__sticky-hscroll-fake'
  fake.style.cssText = [
    'position:fixed',
    'bottom:0',
    'height:14px',
    'overflow-x:scroll',
    'overflow-y:hidden',
    'background:rgba(255,255,255,0.92)',
    'border-top:1px solid rgba(0,0,0,0.12)',
    'box-shadow:0 -1px 4px rgba(0,0,0,0.06)',
    'z-index:1000',
    'display:none',
    'scrollbar-width:auto',
  ].join(';')

  const inner = document.createElement('div')
  inner.style.cssText = 'height:1px;'
  fake.appendChild(inner)
  document.body.appendChild(fake)

  let syncing = false
  const onElScroll = () => {
    if (syncing) return
    syncing = true
    fake.scrollLeft = el.scrollLeft
    syncing = false
  }
  const onFakeScroll = () => {
    if (syncing) return
    syncing = true
    el.scrollLeft = fake.scrollLeft
    syncing = false
  }
  el.addEventListener('scroll', onElScroll, { passive: true })
  fake.addEventListener('scroll', onFakeScroll, { passive: true })

  const update = () => {
    // Если элемент удалён из DOM — чистим
    if (!document.body.contains(el)) {
      cleanup()
      return
    }
    const rect = el.getBoundingClientRect()
    const hasOverflow = el.scrollWidth > el.clientWidth + 1
    const inViewport = rect.top < window.innerHeight && rect.bottom > 0
    // Естественный скроллбар уже в viewport → fake не нужен
    const naturalScrollbarVisible = rect.bottom >= 0 && rect.bottom <= window.innerHeight

    if (hasOverflow && inViewport && !naturalScrollbarVisible) {
      fake.style.display = 'block'
      fake.style.left = rect.left + 'px'
      fake.style.width = rect.width + 'px'
      inner.style.width = el.scrollWidth + 'px'
      fake.scrollLeft = el.scrollLeft
    } else {
      fake.style.display = 'none'
    }
  }

  const ro = new ResizeObserver(update)
  ro.observe(el)
  // Также реагируем на изменение размеров table внутри
  const innerTable = el.querySelector('table')
  if (innerTable) ro.observe(innerTable)

  updateCallbacks.push(update)
  update()

  const cleanup = () => {
    ro.disconnect()
    fake.remove()
    el.removeEventListener('scroll', onElScroll)
    const idx = updateCallbacks.indexOf(update)
    if (idx >= 0) updateCallbacks.splice(idx, 1)
    ATTACHED.delete(el)
    STATES.delete(el)
  }
  STATES.set(el, { fake, cleanup })
}

function scanAndAttach() {
  document.querySelectorAll<HTMLElement>('.v-table__wrapper').forEach(attach)
}

function updateAll() {
  for (const cb of updateCallbacks) cb()
}

export function initStickyHscroll() {
  if (globalListenersAttached) return
  globalListenersAttached = true

  // Первичное сканирование
  scanAndAttach()

  // MutationObserver: подцепляем новые таблицы при навигации между view
  const mo = new MutationObserver(() => {
    scanAndAttach()
    // updateAll вызывается через ResizeObserver автоматически
  })
  mo.observe(document.body, { childList: true, subtree: true })

  // Глобальные события
  window.addEventListener('scroll', updateAll, { passive: true, capture: true })
  window.addEventListener('resize', updateAll, { passive: true })
}
