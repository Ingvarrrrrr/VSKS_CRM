// Типы внутреннего чата — вынесены 1:1 из ChatView.vue при разбиении (ПРАВИЛО №5).
// Единственный источник этих интерфейсов; components/chat и composables/chat импортируют отсюда.

export interface LastMessage {
  id: number
  content: string | null
  sender_name: string | null
  created_at: string
  has_file: boolean
}

export interface Participant {
  id: number
  full_name: string
  username: string
  avatar: string | null
  department: string | null
  position: string | null
}

export interface Room {
  id: number
  name: string | null
  is_group: boolean
  org_id: number
  created_at: string
  last_message: LastMessage | null
  unread_count: number
  participants: Participant[]
}

export interface Message {
  id: number
  room_id: number
  sender_id: number | null
  sender_name: string | null
  content: string | null
  file_name: string | null
  file_mime: string | null
  file_size: number | null
  has_file: boolean
  created_at: string
}

export interface StaffMember {
  id: number
  full_name: string
  username: string
  avatar: string | null
  department: string | null
  position: string | null
}

export interface DateSeparator {
  type: 'separator'
  date: string
}

export type MessageOrSeparator = (Message & { showAvatar?: boolean }) | DateSeparator
