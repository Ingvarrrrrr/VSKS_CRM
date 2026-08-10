import { ref, readonly } from 'vue'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastOptions {
  /**
   * Milliseconds until auto-dismiss. Omit (or 0) = the toast stays on screen
   * until the user closes it — this is the DEFAULT and MUST be used for any
   * message reporting the result of a user action (save, delete, approve,
   * status change, etc.), per the "уведомления не должны исчезать сами" rule.
   * Pass an explicit small value only for low-stakes background routine
   * (autosave ticks, "скопировано в буфер") that must not get in the way.
   */
  duration?: number
  actionText?: string
  onAction?: () => void
}

export interface Toast {
  id: number
  text: string
  type: ToastType
  duration: number
  actionText?: string
  onAction?: () => void
}

// Module-level state → one shared stack for the whole app (mounted once via
// <ToastContainer /> in App.vue). New toasts are pushed, never overwrite an
// existing unread one, so several results in a row simply stack.
const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  function addToast(text: string, type: ToastType = 'info', opts: ToastOptions = {}) {
    const id = nextId++
    const duration = opts.duration ?? 0
    toasts.value.push({
      id,
      text,
      type,
      duration,
      actionText: opts.actionText,
      onAction: opts.onAction,
    })
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
    return id
  }

  function removeToast(id: number) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx !== -1) toasts.value.splice(idx, 1)
  }

  function success(text: string, opts?: ToastOptions) { return addToast(text, 'success', opts) }
  function error(text: string, opts?: ToastOptions) { return addToast(text, 'error', opts) }
  function info(text: string, opts?: ToastOptions) { return addToast(text, 'info', opts) }
  function warning(text: string, opts?: ToastOptions) { return addToast(text, 'warning', opts) }

  return { toasts: readonly(toasts), addToast, removeToast, success, error, info, warning }
}
