// Custom service worker for Web Push notifications
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

  // Set app badge
  if ('setAppBadge' in self) {
    self.setAppBadge().catch(() => {})
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
