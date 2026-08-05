import { ref } from 'vue'
import { apiFetch } from '@/api'

// Единый счётчик «мои согласования» — закупки + заявки + превышения плана
// ФЭО (GET /api/approvals/my-pending/count). По образцу totalUnread из
// useChat.ts: module-level ref, общий на всё приложение, обновляется
// периодическим REST-поллингом (для трёх разнородных сущностей нет единого
// WebSocket-события, поэтому вместо push — poll + ручной refresh сразу после
// решения по любому согласованию).
export const myPendingApprovalsCount = ref(0)

let pollTimer: ReturnType<typeof setInterval> | null = null

export async function refreshMyPendingApprovals() {
  const token = localStorage.getItem('auth_token')
  if (!token) return
  try {
    const data = await apiFetch<{ total: number }>('/approvals/my-pending/count')
    myPendingApprovalsCount.value = data.total ?? 0
  } catch (e: any) {
    // Не роняем бейдж/поллинг из-за одной неудачной попытки — просто оставляем
    // прежнее значение. Ошибка при этом не глотается молча: видна в консоли.
    console.warn('[approvals-badge] refresh failed:', e?.payload?.message || e?.message)
  }
}

export function initApprovalsBadge() {
  refreshMyPendingApprovals()
  if (!pollTimer) {
    pollTimer = setInterval(refreshMyPendingApprovals, 60_000)
  }
}

export function destroyApprovalsBadge() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
