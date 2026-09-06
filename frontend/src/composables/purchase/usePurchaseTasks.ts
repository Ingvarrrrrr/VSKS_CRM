// Задачи, связанные с закупкой: создание новой + привязка существующей.
// Вынесено из CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, reactive, type ComputedRef } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export const TASK_STATUS_LABEL: Record<string, string> = {
  todo: 'К выполнению', in_progress: 'В работе', done: 'Выполнена', cancelled: 'Отменена',
}
export const TASK_PRIORITIES = [
  { value: 'low', title: 'Низкий' }, { value: 'medium', title: 'Средний' },
  { value: 'high', title: 'Высокий' }, { value: 'urgent', title: 'Срочный' },
]
export function taskStatusColor(s: string) {
  return s === 'done' ? 'success' : s === 'in_progress' ? 'info' : s === 'cancelled' ? 'grey' : 'default'
}
export function taskPriorityColor(p: string) {
  return p === 'urgent' ? 'error' : p === 'high' ? 'warning' : p === 'medium' ? 'info' : 'default'
}

export function usePurchaseTasks(
  purchaseId: ComputedRef<number | null>,
  loadAllUsers: () => Promise<void>,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const linkedTasks = ref<any[]>([])
  const linkedTaskDialog = ref(false)
  const linkedTaskSaving = ref(false)
  const linkedTaskForm = reactive({
    title: '', description: '', priority: 'medium',
    due_date: '', assignee_ids: [] as number[],
  })

  async function loadLinkedTasks() {
    if (!purchaseId.value) return
    try {
      linkedTasks.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/tasks/`)
    } catch { linkedTasks.value = [] }
  }

  function openCreateLinkedTask() {
    Object.assign(linkedTaskForm, {
      title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [],
    })
    loadAllUsers()
    linkedTaskDialog.value = true
  }

  async function saveLinkedTask() {
    if (!linkedTaskForm.title || !purchaseId.value) return
    linkedTaskSaving.value = true
    try {
      const body: Record<string, any> = {
        title: linkedTaskForm.title,
        description: linkedTaskForm.description || undefined,
        priority: linkedTaskForm.priority,
        purchase_id: purchaseId.value,
        assignee_ids: linkedTaskForm.assignee_ids,
      }
      if (linkedTaskForm.due_date) body.due_date = linkedTaskForm.due_date + 'T23:59:59'
      await apiFetch('/tasks/', { method: 'POST', body: JSON.stringify(body) })
      linkedTaskDialog.value = false
      showSnack('Задача создана')
      await loadLinkedTasks()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка при создании задачи', 'error')
    } finally {
      linkedTaskSaving.value = false
    }
  }

  // ── Link existing task ───────────────────────────────────────────────────
  const linkTaskDialog = ref(false)
  const linkTaskSearch = ref('')
  const linkTaskResults = ref<any[]>([])
  const linkTaskSearching = ref(false)
  let _linkSearchTimer: ReturnType<typeof setTimeout> | null = null

  function openLinkExistingTask() {
    linkTaskSearch.value = ''
    linkTaskResults.value = []
    linkTaskDialog.value = true
  }

  function searchUnlinkedTasks(q: string | null) {
    if (_linkSearchTimer) clearTimeout(_linkSearchTimer)
    if (!q || q.length < 2) { linkTaskResults.value = []; return }
    _linkSearchTimer = setTimeout(async () => {
      linkTaskSearching.value = true
      try {
        linkTaskResults.value = await apiFetch<any[]>(`/tasks/?search=${encodeURIComponent(q)}`)
      } catch { linkTaskResults.value = [] }
      finally { linkTaskSearching.value = false }
    }, 300)
  }

  async function linkExistingTask(taskId: number) {
    try {
      await apiFetch(`/tasks/${taskId}`, {
        method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId.value }),
      })
      linkTaskDialog.value = false
      showSnack('Задача привязана к закупке')
      await loadLinkedTasks()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка привязки', 'error')
    }
  }

  async function unlinkTask(taskId: number) {
    try {
      await apiFetch(`/tasks/${taskId}`, {
        method: 'PATCH', body: JSON.stringify({ purchase_id: null }),
      })
      showSnack('Задача отвязана')
      await loadLinkedTasks()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка', 'error')
    }
  }

  return {
    linkedTasks, linkedTaskDialog, linkedTaskSaving, linkedTaskForm,
    loadLinkedTasks, openCreateLinkedTask, saveLinkedTask,
    linkTaskDialog, linkTaskSearch, linkTaskResults, linkTaskSearching,
    openLinkExistingTask, searchUnlinkedTasks, linkExistingTask, unlinkTask,
  }
}
