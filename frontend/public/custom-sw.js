// Custom service worker for Web Push notifications + cache cleanup on activate
//
// importScripts('/custom-sw.js') выполняется ПЕРВОЙ строкой сгенерированного
// workbox sw.js (см. vite.config.ts importScripts), то есть этот файл
// исполняется до s.precacheAndRoute()/s.registerRoute() — наши addEventListener
// регистрируются раньше workbox-овских. Для 'activate' это не важно (все
// листенеры одного типа вызываются все), а для 'fetch' (ниже) это критично:
// наш листенер для navigate успевает вызвать event.respondWith() первым.

// 2026-09-16: раньше чистили только кэши с 'api' в имени (остаток от эпохи
// NetworkFirst /api/*). Это оставляло жить ЛЮБОЙ другой runtime-кэш вечно —
// конкретно 'html-cache' (NetworkFirst для navigate, Phase 26-FFF) ни разу не
// очищался activate-хендлером ни на одной версии SW. Теперь правило простое:
// оставляем только кеш(и) ТЕКУЩЕЙ версии workbox precache (единственный кэш,
// именем содержащий 'precache' — его наполнением и версионностью управляет
// сам workbox через cleanupOutdatedCaches), всё остальное — под нож.
function isCurrentWorkboxCache(cacheName) {
  return cacheName.indexOf('workbox-precache') !== -1
}

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys
          .filter(function(k) { return !isCurrentWorkboxCache(k) })
          .map(function(k) { return caches.delete(k) })
      )
    }).then(function() {
      // Страховка от бага прежних версий этого файла: до этого фикса SW
      // регистрировал navigateFallback:'index.html' по умолчанию (см.
      // vite.config.ts) — при промахе по precache он тихо докладывал ответ
      // сети внутрь ТОГО ЖЕ precache-кэша под ключом 'index.html'/'/' без
      // ревизии, и cleanupOutdatedCaches() о такой записи не знает (она не
      // из манифеста) — то есть протухший index.html со ссылками на давно
      // удалённые чанки мог годами лежать именно в precache-кэше пользователя,
      // не будучи задет фильтром выше. Выпиливаем такие записи явно.
      return caches.keys().then(function(precacheKeys) {
        var precacheKey = precacheKeys.filter(isCurrentWorkboxCache)[0]
        if (!precacheKey) return
        return caches.open(precacheKey).then(function(cache) {
          return cache.keys().then(function(reqs) {
            return Promise.all(
              reqs
                .filter(function(r) {
                  var path = new URL(r.url).pathname
                  return path === '/' || /\/index\.html$/.test(path)
                })
                .map(function(r) { return cache.delete(r) })
            )
          })
        })
      })
    }).then(function() {
      // Берём под контроль все открытые вкладки немедленно.
      return self.clients.claim()
    })
  )
})

// 2026-09-16: навигационные запросы (открытие/перезагрузка страницы) идут
// ТОЛЬКО в сеть — никакого кэша HTML в CacheStorage вообще не создаётся.
// Раньше здесь стояло NetworkFirst(networkTimeoutSeconds: 3, cacheName:
// 'html-cache') в runtimeCaching (vite.config.ts), но по факту оно никогда
// не срабатывало — vite-plugin-pwa по умолчанию регистрирует СВОЙ
// navigateFallback-роут раньше пользовательских runtimeCaching-правил, и он
// перехватывал navigate первым (см. комментарий в vite.config.ts). Теперь
// navigateFallback явно выключен, а этот листенер — единственный обработчик
// navigate: чистый NetworkOnly с инлайновым офлайн-фолбэком (без обращения к
// CacheStorage — фолбэк не зависит от того, что где-то успело закэшироваться).
// Это устраняет весь класс «протухший HTML» в принципе: раз HTML никогда не
// сохраняется в кэш, ему неоткуда быть протухшим при следующем деплое.
var OFFLINE_HTML = '<!doctype html><html lang="ru"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
  '<title>GALA — нет соединения</title>' +
  '<style>html,body{margin:0;height:100%;display:flex;align-items:center;' +
  'justify-content:center;background:#0f0e0c;color:#f5f1ea;' +
  'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;text-align:center}' +
  '.b{padding:24px}h1{font-size:18px;margin:0 0 8px}p{opacity:.7;font-size:14px;margin:0 0 16px}' +
  'button{background:#fb923c;color:#0f0e0c;border:none;border-radius:8px;' +
  'padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer}</style></head>' +
  '<body><div class="b"><h1>Нет соединения с сервером</h1>' +
  '<p>Проверьте интернет и попробуйте ещё раз</p>' +
  '<button onclick="location.reload()">Повторить</button></div></body></html>'

self.addEventListener('fetch', function(event) {
  if (event.request.mode !== 'navigate') return
  // /api/ и /deploy/ — не HTML-навигация в смысле этого приложения, но mode
  // всё равно может быть 'navigate' для прямых переходов по ссылке; явных
  // navigate-переходов на /api/ в приложении нет, так что фильтровать не
  // нужно — сервер сам ответит на них как обычно через сеть.
  event.respondWith(
    fetch(event.request).catch(function() {
      return new Response(OFFLINE_HTML, {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      })
    })
  )
})

self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'VSKS CRM'
  // 2026-09: url/tag теперь читаются из payload (см. app/services/push_sender.py),
  // а не жёстко зашиты — нужно разным событиям (чат, запрос местоположения,
  // в будущем — задачи/добавления в чаты) открывать разные экраны по клику.
  // Дефолты — СТАРОЕ поведение чата (чат url/tag явно не передаёт).
  const options = {
    body: data.body || 'Новое сообщение',
    icon: '/pwa-192x192.png',
    badge: '/pwa-192x192.png',
    tag: data.tag || 'vsks-chat',
    renotify: true,
    data: { url: data.url || '/chat' },
  }

  // phase26-bb: Set app badge with actual unread count from payload (iOS PWA 16.4+)
  const unread = typeof data.unread_count === 'number' ? data.unread_count : 0
  if ('setAppBadge' in self) {
    if (unread > 0) self.setAppBadge(unread).catch(() => {})
    else self.clearAppBadge && self.clearAppBadge().catch(() => {})
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', function(event) {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) return client.focus()
      }
      if (clients.openWindow) return clients.openWindow(url)
    })
  )
})
