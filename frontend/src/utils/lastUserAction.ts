// Единый трекер «что пользователь делал последним» перед JS-ошибкой — чтобы
// окно ApiErrorDialog могло сказать «Произошло после: нажатие «…»», а не
// только показать стек минифицированной библиотеки (который владельцу ни о
// чём не говорит). Один источник на всё приложение (ПРАВИЛО №6): слушает
// click/keydown на document в фазе ЗАХВАТА (capture) — так запись успевает
// обновиться ДО того, как сам обработчик клика что-то уронит и попадёт в
// window 'error'/'unhandledrejection' (ApiErrorDialog.vue), а не после.
//
// init() вызывается один раз из main.ts.

export interface LastUserAction {
  label: string       // человеческое имя элемента, обрезано до 80 символов
  path: string         // location.pathname на момент действия
  pageTitle: string     // document.title (или раздел, см. resolvePageTitle)
  time: number          // Date.now()
}

let lastAction: LastUserAction | null = null
let initialized = false

const MAX_LABEL_LENGTH = 80

function collapseWhitespace(s: string): string {
  return s.replace(/\s+/g, ' ').trim()
}

function truncateLabel(s: string): string {
  const collapsed = collapseWhitespace(s)
  return collapsed.length > MAX_LABEL_LENGTH
    ? collapsed.slice(0, MAX_LABEL_LENGTH - 1) + '…'
    : collapsed
}

// Селекторы «именующих» предков, в порядке убывания приоритета — первый же
// найденный предок (или сам элемент) с непустым человеческим именем решает.
const NAMED_ANCESTOR_SELECTOR = [
  'button',
  'a',
  '[role="button"]',
  '.v-btn',
  '.v-list-item',
  '.v-chip',
  '.v-tab',
  'tr',
  'li',
  '[aria-label]',
  '[title]',
].join(',')

function elementHumanName(el: Element): string | null {
  const ariaLabel = el.getAttribute?.('aria-label')
  if (ariaLabel && collapseWhitespace(ariaLabel)) return truncateLabel(ariaLabel)

  const title = el.getAttribute?.('title')
  if (title && collapseWhitespace(title)) return truncateLabel(title)

  const text = (el as HTMLElement).innerText ?? el.textContent ?? ''
  if (collapseWhitespace(text)) return truncateLabel(text)

  return null
}

function describeTarget(target: EventTarget | null): string | null {
  if (!(target instanceof Element)) return null

  // Сам элемент сначала, потом ближайший «именующий» предок (кнопка/ссылка/
  // пункт меню/строка таблицы/chip и т.п.) — клик обычно приходится на
  // вложенную иконку или span внутри настоящей интерактивной обёртки.
  const direct = elementHumanName(target)
  if (direct) return direct

  const ancestor = target.closest(NAMED_ANCESTOR_SELECTOR)
  if (ancestor) {
    const name = elementHumanName(ancestor)
    if (name) return name
  }

  return null
}

function resolvePageTitle(): string {
  // document.title — единственный простой и всегда доступный источник имени
  // раздела (отдельного реестра «название раздела по маршруту» в проекте нет —
  // заводить его ради этой строки было бы вторым источником истины).
  return document.title || location.pathname
}

function recordAction(target: EventTarget | null) {
  const label = describeTarget(target)
  if (!label) return
  lastAction = {
    label,
    path: location.pathname,
    pageTitle: resolvePageTitle(),
    time: Date.now(),
  }
}

function onClick(e: MouseEvent) {
  recordAction(e.target)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter') return
  recordAction(e.target)
}

export function initLastUserAction(): void {
  if (initialized) return
  initialized = true
  document.addEventListener('click', onClick, { capture: true })
  document.addEventListener('keydown', onKeydown, { capture: true })
}

export function getLastUserAction(): LastUserAction | null {
  return lastAction
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

/**
 * Строка «Произошло после: нажатие «X» на странице «Y» (путь), ЧЧ:ММ:СС» —
 * или «Произошло при загрузке страницы «Y»», если действия не было.
 * Без действия берём ТЕКУЩУЮ страницу (document.title/location.pathname) —
 * на момент вызова ошибка уже произошла на ней, SPA ещё не успела уйти
 * дальше (и handleJsError/handleUnhandledRejection в ApiErrorDialog вызывают
 * это сразу при получении события).
 */
export function describeLastAction(): string {
  const a = lastAction
  if (!a) {
    return `Произошло при загрузке страницы «${resolvePageTitle()}»`
  }
  return `Произошло после: нажатие «${a.label}» на странице «${a.pageTitle}» (${a.path}), ${formatTime(a.time)}`
}
