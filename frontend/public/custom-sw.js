// Custom service worker for Web Push notifications + cache cleanup on activate

// При активации нового SW удаляем старые API-кэши которые остались от
// предыдущей версии (раньше /api/* был NetworkFirst с cacheName='api-cache').
// Без этого пользователи продолжают видеть stale GET-ответы пока браузер
// сам не очистит storage.
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys
          .filter(function(k) { return k.includes('api-cache') || k.includes('api') })
          .map(function(k) { return caches.delete(k) })
      )
    }).then(function() {
      // Берём под контроль все открытые вкладки немедленно.
      return self.clients.claim()
    })
  )
})

self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'VSKS CRM'
  const options = {
    body: data.body || 'Новое сообщение',
    icon: '/pwa-192x192.png',
    badge: '/pwa-192x192.png',
    tag: 'vsks-chat',
    renotify: true,
    data: { url: '/chat' },
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
