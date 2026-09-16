/**
 * PWA service-worker lifecycle: регистрация, поллинг обновлений, уведомление
 * пользователя о новой версии + самолечение «белого экрана» при устаревшем
 * бандле.
 *
 * Вынесено из main.ts отдельным модулем (Правило №5 проекта — модульность,
 * main.ts не должен разрастаться в файл-помойку с несвязанными обязанностями).
 *
 * Два независимых, но родственных механизма живут здесь:
 *
 * 1. initSwUpdate() — обычный, «мягкий» путь. Workbox (registerType:
 *    'autoUpdate' + skipWaiting + clientsClaim) сам активирует новый SW, как
 *    только его увидит; чтобы увидел — нужен периодический reg.update().
 *    Когда контроллер реально сменился (не первая установка — см. hadController),
 *    показываем тост «Доступна новая версия — Обновить» через общий useToast()
 *    (Правило №6 — не плодить свой собственный toast-компонент, в проекте уже
 *    есть один источник истины для уведомлений, см. ToastContainer.vue).
 *    На скрытой вкладке перезагружаем сразу — пользователь ничего не потеряет.
 *
 * 2. initChunkLoadRecovery() — «жёсткий» путь для случая, когда мягкий не
 *    успел или не сработал: пользователь уже открыл вкладку СО СТАРЫМ бандлом
 *    в памяти, происходит новый деплой, и пользователь кликает на ещё не
 *    подгруженный ленивый роут (Vue Router `() => import(...)`) — файл этого
 *    чанка по старому хэшу на сервере уже исчез (новый деплой оставил только
 *    новые хэши). Браузер бросает событие 'vite:preloadError' (для нативного
 *    dynamic import()) — READ this is exactly the класс бага из прод-инцидента
 *    2026-09-16: пользователь видит только логотип из статической разметки
 *    index.html (см. #app:empty::after), потому что JS-роут так и не смонтировался,
 *    а никакого обработчика ошибки на этот путь раньше не было (index.html
 *    ловит только падения СТАТИЧЕСКИХ <script>/<link> тегов — см. его inline
 *    self-heal script — но НЕ падения динамического import()).
 *    Лечение: один раз за сессию снять регистрацию SW, вычистить
 *    CacheStorage и перезагрузить страницу — свежий index.html снова
 *    ссылается на актуальный, самосогласованный набор чанков.
 *
 * Guard от цикла общий (sessionStorage, отдельные ключи, оба — 30-60с окно) —
 * если оба механизма выстрелят почти одновременно, каждый просто увидит уже
 * идущую перезагрузку и не будет пытаться её продублировать (location.reload
 * безопасно вызывать более одного раза).
 */
import { useToast } from './useToast'

const RELOAD_TS_KEY = 'sw_auto_reload_ts'
const CHUNK_RELOAD_TS_KEY = 'gala_chunk_reload_ts'
const RELOAD_COOLDOWN_MS = 60_000
const CHUNK_RELOAD_COOLDOWN_MS = 30_000

function withinCooldown(key: string, cooldownMs: number): boolean {
  const last = Number(sessionStorage.getItem(key) || 0)
  return Date.now() - last < cooldownMs
}

function markReload(key: string) {
  try { sessionStorage.setItem(key, String(Date.now())) } catch { /* noop */ }
}

/** Обычный путь: поллинг обновлений SW + тост при появлении новой версии. */
export function initSwUpdate() {
  if (!('serviceWorker' in navigator)) return

  navigator.serviceWorker.register('/sw.js').catch(() => {})

  const tryUpdate = () => {
    navigator.serviceWorker.getRegistration().then(reg => reg?.update()).catch(() => {})
  }
  setInterval(tryUpdate, 60 * 1000)
  window.addEventListener('focus', tryUpdate)

  // controllerchange стреляет и при ПЕРВОЙ установке SW (clientsClaim берёт
  // страницу под контроль) — это НЕ обновление. Реагируем только если у
  // страницы уже был контроллер на старте (= реально сменилась версия SW).
  // Иначе на iOS WebClip (Safari периодически сбрасывает SW-хранилище) тост
  // «новая версия» выскакивал бы при каждом запуске — вечное моргание.
  let hadController = !!navigator.serviceWorker.controller
  let reloadScheduled = false
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController) {
      hadController = true
      return
    }
    if (reloadScheduled) return
    reloadScheduled = true
    if (withinCooldown(RELOAD_TS_KEY, RELOAD_COOLDOWN_MS)) return
    markReload(RELOAD_TS_KEY)

    // Тихий reload если вкладка не видна — пользователь ничего не заметит,
    // но при возврате во вкладку получит свежую версию.
    if (document.visibilityState === 'hidden') {
      window.location.reload()
      return
    }
    // Активная вкладка — ненавязчивый тост вместо блокирующего confirm().
    // Без auto-dismiss (duration не задан) — важное сообщение не должно
    // исчезнуть само, пока пользователь его не заметил.
    useToast().info('Доступна новая версия приложения', {
      actionText: 'Обновить',
      onAction: () => window.location.reload(),
    })
  })
}

function isStaleChunkFailure(reason: unknown): boolean {
  const msg = String((reason as { message?: string })?.message ?? reason ?? '')
  return /import|module|chunk|fetch dynamically imported/i.test(msg)
}

async function recoverFromStaleChunk() {
  if (withinCooldown(CHUNK_RELOAD_TS_KEY, CHUNK_RELOAD_COOLDOWN_MS)) return
  markReload(CHUNK_RELOAD_TS_KEY)

  useToast().info('Обновляем приложение…')

  try {
    const jobs: Promise<unknown>[] = []
    if ('serviceWorker' in navigator) {
      jobs.push(
        navigator.serviceWorker.getRegistrations()
          .then(regs => Promise.all(regs.map(r => r.unregister())))
      )
    }
    if ('caches' in window) {
      jobs.push(caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k)))))
    }
    await Promise.all(jobs)
  } catch {
    /* переходим к перезагрузке в любом случае — само наличие устаревшего
       чанка важнее того, успела ли вычиститься SW-регистрация */
  }
  // Небольшая пауза — даём тосту показаться перед уходом со страницы.
  setTimeout(() => window.location.reload(), 400)
}

/**
 * Жёсткий путь: ловим падения ленивых чанков (Vue Router `() => import(...)`,
 * динамический import() любого другого рода), которых не видит self-heal
 * script в index.html (тот реагирует только на 'error' от статических
 * <script>/<link> тегов, см. его комментарий).
 */
export function initChunkLoadRecovery() {
  // Vite сам генерирует и бросает это событие в каждом чанке, где есть
  // dynamic import() — ровно на случай "чанк по старому хэшу не найден".
  window.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    recoverFromStaleChunk()
  })

  // Подстраховка на случай, если конкретный сценарий падения не прошёл через
  // vite:preloadError (например, ошибка внутри уже загруженного модуля при
  // обращении к экспорту, которого больше нет в новой версии чанка) —
  // фильтруем по тексту, чтобы не перезагружать страницу на КАЖДОЙ
  // необработанной ошибке в бизнес-логике.
  window.addEventListener('unhandledrejection', (event) => {
    if (!isStaleChunkFailure(event.reason)) return
    event.preventDefault()
    recoverFromStaleChunk()
  })
}
