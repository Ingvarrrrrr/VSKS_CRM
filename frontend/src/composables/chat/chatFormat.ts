// Чистые форматтеры и хелперы отображения чата — вынесены 1:1 из ChatView.vue
// (ПРАВИЛО №5). Без реактивного состояния: всё нужное передаётся аргументами,
// чтобы функции переиспользовались из любого components/chat без привязки
// к конкретному композаблу.

import type { Message, MessageOrSeparator, Room } from './chatTypes'

const COLORS = ['blue', 'teal', 'deep-purple', 'indigo', 'cyan', 'green', 'orange', 'pink']

export function colorFromId(id: number): string {
  return COLORS[id % COLORS.length]
}

export function roomColor(room: Room): string {
  return colorFromId(room.id)
}

export function senderColor(senderId: number | null): string {
  return colorFromId(senderId ?? 0)
}

export function stringToColor(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  const colors = ['#E57373', '#81C784', '#64B5F6', '#FFD54F', '#BA68C8', '#4DB6AC', '#FF8A65', '#A1887F']
  return colors[Math.abs(hash) % colors.length]
}

export function roomDisplayName(room: Room, currentUserId: number | null): string {
  if (room.is_group) return room.name || 'Группа'
  // For direct chat: show the other participant's name
  const other = room.participants.find(p => p.id !== currentUserId)
  return other?.full_name || room.name || 'Чат'
}

export function roomInitial(room: Room, currentUserId: number | null): string {
  return roomDisplayName(room, currentUserId).charAt(0).toUpperCase()
}

export function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
}

export function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

export function isImage(msg: Message): boolean {
  if (!msg.file_mime) return false
  return msg.file_mime.startsWith('image/')
}

export function fileUrl(roomId: number | undefined, msgId: number): string {
  const token = localStorage.getItem('auth_token') ?? ''
  return `/api/chat/rooms/${roomId}/files/${msgId}?token=${encodeURIComponent(token)}`
}

export function highlightSearch(text: string, query: string): string {
  const q = query.trim()
  if (!q) return text
  const regex = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}

/** Строит ленту сообщений с разделителями дат и признаком показа аватара —
 * чистая трансформация без побочных эффектов (Telegram-style группировка). */
export function groupMessagesWithSeparators(source: Message[]): MessageOrSeparator[] {
  const result: MessageOrSeparator[] = []
  let lastDate = ''
  let lastSenderId: number | null = null
  let lastTime: number | null = null

  for (const msg of source) {
    const d = new Date(msg.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
    if (d !== lastDate) {
      result.push({ type: 'separator', date: d })
      lastDate = d
      lastSenderId = null
      lastTime = null
    }

    const msgTime = new Date(msg.created_at).getTime()
    const showAvatar = msg.sender_id !== lastSenderId ||
      (lastTime !== null && msgTime - lastTime > 2 * 60 * 1000)

    result.push({ ...msg, showAvatar })
    lastSenderId = msg.sender_id
    lastTime = msgTime
  }
  return result
}
