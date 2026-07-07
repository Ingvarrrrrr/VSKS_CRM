import { ref, computed, onMounted, onBeforeUnmount, type Ref } from 'vue'

export interface UndoRedoStep { field: string; before: unknown; after: unknown }
export interface UseUndoRedoOptions {
  maxSteps?: number                    // default 50
  onAfterUndoRedo?: (step: UndoRedoStep, direction: 'undo' | 'redo') => void | Promise<void>
  attachGlobalListener?: boolean       // default true — вешает keydown на document
}

export function useUndoRedo(form: Ref<Record<string, any>>, opts: UseUndoRedoOptions = {}) {
  const max = opts.maxSteps ?? 50
  const undoStack = ref<UndoRedoStep[]>([])
  const redoStack = ref<UndoRedoStep[]>([])

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function push(field: string, before: unknown, after: unknown) {
    try { if (JSON.stringify(before) === JSON.stringify(after)) return } catch {}
    undoStack.value.push({ field, before, after })
    if (undoStack.value.length > max) undoStack.value.shift()
    redoStack.value = []
  }

  async function undo() {
    const step = undoStack.value.pop()
    if (!step) return
    redoStack.value.push(step)
    form.value[step.field] = deepClone(step.before)
    await opts.onAfterUndoRedo?.(step, 'undo')
  }

  async function redo() {
    const step = redoStack.value.pop()
    if (!step) return
    undoStack.value.push(step)
    form.value[step.field] = deepClone(step.after)
    await opts.onAfterUndoRedo?.(step, 'redo')
  }

  function isTextInput(target: EventTarget | null): boolean {
    if (!target || !(target instanceof Element)) return false
    if (target instanceof HTMLInputElement) {
      const t = (target.type || '').toLowerCase()
      // Не считаем чекбоксы/радио text-input — там нативного undo нет
      return ['text', 'email', 'password', 'search', 'url', 'tel', 'number', 'date', 'datetime-local', 'time', 'month'].includes(t) || t === ''
    }
    if (target instanceof HTMLTextAreaElement) return true
    if ((target as HTMLElement).isContentEditable) return true
    return false
  }

  function onKeyDown(e: KeyboardEvent) {
    if (isTextInput(e.target)) return   // не перехватываем — нативный undo браузера
    if (!(e.ctrlKey || e.metaKey)) return
    const key = e.key.toLowerCase()
    if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
    else if (key === 'y' || (key === 'z' && e.shiftKey)) { e.preventDefault(); redo() }
  }

  function clear() { undoStack.value = []; redoStack.value = [] }

  function deepClone<T>(v: T): T { try { return JSON.parse(JSON.stringify(v)) } catch { return v } }

  if (opts.attachGlobalListener !== false) {
    onMounted(() => document.addEventListener('keydown', onKeyDown))
    onBeforeUnmount(() => document.removeEventListener('keydown', onKeyDown))
  }

  return { push, undo, redo, onKeyDown, canUndo, canRedo, clear, undoStack, redoStack }
}
