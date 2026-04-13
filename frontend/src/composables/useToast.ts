import { ref, readonly } from 'vue'

export interface Toast {
  id: number
  text: string
  type: 'success' | 'error' | 'info' | 'warning'
  duration: number
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  function addToast(text: string, type: Toast['type'] = 'info', duration = 4000) {
    const id = nextId++
    toasts.value.push({ id, text, type, duration })
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
  }

  function removeToast(id: number) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx !== -1) toasts.value.splice(idx, 1)
  }

  function success(text: string, duration?: number) { addToast(text, 'success', duration) }
  function error(text: string, duration?: number) { addToast(text, 'error', duration ?? 6000) }
  function info(text: string, duration?: number) { addToast(text, 'info', duration) }
  function warning(text: string, duration?: number) { addToast(text, 'warning', duration) }

  return { toasts: readonly(toasts), addToast, removeToast, success, error, info, warning }
}
