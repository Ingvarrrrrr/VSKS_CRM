import { ref, onMounted, onUnmounted } from 'vue'

// Global state — shared across components via module-level refs
export const totalUnread = ref(0)
export const wsConnected = ref(false)

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

function connect() {
  const token = localStorage.getItem('auth_token')
  if (!token) return

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${protocol}://${location.host}/api/ws/chat?token=${token}`)

  ws.onopen = () => {
    wsConnected.value = true
    // Ping every 30s to keep WS alive
    pingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30000)
  }

  ws.onmessage = (e) => {
    if (e.data === 'pong') return
    try {
      const event = JSON.parse(e.data)
      if (event.type === 'unread_count') totalUnread.value = event.total_unread ?? 0
      listeners.forEach(cb => cb(event))
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
}

export function destroyChat() {
  disconnect()
}
