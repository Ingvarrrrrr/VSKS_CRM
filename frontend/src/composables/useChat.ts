import { ref, onMounted, onUnmounted } from 'vue'

// Global state — shared across components via module-level refs
export const totalUnread = ref(0)
export const wsConnected = ref(false)

// Cache of room participant counts (populated by ChatView/ChatEmbed on room load)
export const roomParticipantCounts = ref<Record<number, number>>({})

// Callbacks registered by ChatView to receive events
type MessageCallback = (event: {
  type: string
  room_id?: number
  message?: any
  user_id?: number
  last_read_message_id?: number
  total_unread?: number
}) => void

const listeners: MessageCallback[] = []

export function onChatEvent(cb: MessageCallback) {
  listeners.push(cb)
  return () => {
    const i = listeners.indexOf(cb)
    if (i >= 0) listeners.splice(i, 1)
  }
}

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
let badgePollTimer: ReturnType<typeof setInterval> | null = null

function updateAppBadge(count: number) {
  try {
    if ('setAppBadge' in navigator) {
      if (count > 0) (navigator as any).setAppBadge(count)
      else (navigator as any).clearAppBadge()
    }
  } catch {}
}

async function pollBadgeCount() {
  // Fallback: fetch unread count via REST when WS is down
  if (wsConnected.value) return
  const token = localStorage.getItem('auth_token')
  if (!token) return
  try {
    const res = await fetch('/api/tasks/badges', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      const count = data.chat_unread ?? 0
      totalUnread.value = count
      updateAppBadge(count)
    }
  } catch {}
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)))
}

async function sendSubToBackend(sub: globalThis.PushSubscription) {
  const token = localStorage.getItem('auth_token') ?? ''
  const json = sub.toJSON()
  await fetch('/api/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  }).catch(() => {})
}

async function subscribeToPush() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return
    const reg = await navigator.serviceWorker.ready
    // Check if already subscribed
    let sub = await reg.pushManager.getSubscription()
    if (sub) {
      // Already subscribed — send to backend in case token changed
      await sendSubToBackend(sub)
      return
    }
    // Request notification permission first
    if (typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
      const perm = await Notification.requestPermission()
      if (perm !== 'granted') return
    }
    // Get VAPID public key from backend
    const token = localStorage.getItem('auth_token') ?? ''
    const res = await fetch('/api/push/vapid-key', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const { key } = await res.json()
    if (!key) return
    // Convert VAPID key and subscribe
    const vapidKey = urlBase64ToUint8Array(key)
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKey,
    })
    await sendSubToBackend(sub)
  } catch (e) {
    console.warn('Push subscription failed:', e)
  }
}

function playNotificationSound() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.25, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.35)
  } catch {
    // AudioContext may be blocked if no user gesture yet — silently ignore
  }
}

function connect() {
  // Don't create duplicate connections
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return

  const token = localStorage.getItem('auth_token')
  if (!token) {
    // Token not yet available — retry in 2s (login may be in progress)
    reconnectTimer = setTimeout(connect, 2000)
    return
  }

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${protocol}://${location.host}/api/ws/chat?token=${token}`)

  ws.onopen = () => {
    wsConnected.value = true
    listeners.forEach(cb => cb({ type: 'connected' }))
    // Ping every 30s to keep WS alive
    pingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30000)
    // Subscribe to Web Push for offline notifications (handles permission internally)
    subscribeToPush()
  }

  ws.onmessage = (e) => {
    if (e.data === 'pong') return
    try {
      const event = JSON.parse(e.data)
      if (event.type === 'unread_count') {
        totalUnread.value = event.total_unread ?? 0
        updateAppBadge(totalUnread.value)
      }

      // D-19/D-20: Handle system notifications (assignment, consent requests)
      if (event.type === 'system_notification') {
        // Log to console for debugging
        console.log('[СИСТЕМА]', event.message)

        // Browser notification if permitted
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && event.message) {
          new Notification('GALA', { body: event.message })
        }

        // Play notification sound
        playNotificationSound()

        // Forward to listeners (ChatView can refresh room list and highlight new room)
        listeners.forEach(cb => cb({
          type: 'new_room',
          room_id: event.room_id,
          message: event.message,
          link: event.link,
        }))

        return
      }

      listeners.forEach(cb => cb(event))

      // Sound notification for mentions or 2-person rooms
      if (event.type === 'message') {
        const myId = Number(localStorage.getItem('user_id') ?? '0')
        const senderId = event.message?.sender_id
        if (senderId && senderId !== myId) {
          const mentionIds: number[] = event.message?.mention_ids ?? []
          const participantCount: number = event.message?.participant_count ??
            (roomParticipantCounts.value[event.room_id] ?? 3)
          const shouldNotify = participantCount <= 2 || mentionIds.includes(myId)
          if (shouldNotify) {
            playNotificationSound()
          }
        }
      }
    } catch {
      // ignore malformed messages
    }
  }

  ws.onclose = (e) => {
    wsConnected.value = false
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
    // Close code 4001 = auth error, don't reconnect
    if (e.code !== 4001) {
      reconnectTimer = setTimeout(connect, 3000)
    }
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (pingTimer) {
    clearInterval(pingTimer)
    pingTimer = null
  }
  ws?.close()
  ws = null
}

// useChat composable — call in App.vue or a persistent component to keep WS alive
export function useChat() {
  onMounted(connect)
  onUnmounted(disconnect)
  return { totalUnread, wsConnected }
}

// initChat — call once at app startup (from App.vue) without lifecycle binding
export function initChat() {
  connect()
  // Polling fallback: check badge count every 60s when WS is down
  if (!badgePollTimer) {
    badgePollTimer = setInterval(pollBadgeCount, 60000)
    // Also fetch immediately on init
    pollBadgeCount()
  }

  // phase26-cc: на iOS Safari WS закрывается когда приложение в фоне.
  // При возврате (visibilitychange/focus) — немедленный reconnect и refresh unread.
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        if (!wsConnected.value) connect()
        pollBadgeCount()
      }
    })
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', () => {
      if (!wsConnected.value) connect()
      pollBadgeCount()
    })
  }
}

export function destroyChat() {
  disconnect()
  if (badgePollTimer) {
    clearInterval(badgePollTimer)
    badgePollTimer = null
  }
}

export { connect }
