// Стек отмены/повтора (Ctrl+Z / Ctrl+Y + кнопки в тулбаре) — владелец: «Я просил,
// чтобы внутри приложения работали кнопки Ctrl+Z и Ctrl+Y для того, чтобы отменять
// действия или возвращать... хотя бы шагов на 5». Область — СТРОГО дерево плана
// субсидии: создание/правка/удаление/перенос ПЛАНОВЫХ ПОЗИЦИЙ (пуш из
// useFeoPlannedItemAddDialog.ts/useFeoPlannedItemEditDialog.ts/useFeoLevel5.ts) и
// перенос КАТЕГОРИЙ ФЭО (пуш из useFeoTreeDnd.ts). Создание/правка/удаление самих
// категорий в эту волну НЕ вошли (см. отчёт) — только их перенос.
//
// Command pattern: запись стека — это готовая пара замыканий `{ label, undo, redo }`,
// СОБРАННАЯ ТАМ, где произошло исходное действие — тем самым обратный шаг ЗОВЁТ
// уже существующие функции (moveOnePlannedItem/deletePlannedItemRaw/
// createPlannedItemRaw/putPlannedItemFull/moveCategoryRaw), а не второй набор
// запросов (Правило №6). Этот файл ничего не знает о ФЭО-специфике — только
// держит сам стек, хоткеи и порядок исполнения. Что именно кладётся в замыкание
// каждого типа действия — см. комментарии у registerCreateUndo/registerDeleteUndo/
// registerEditUndo/registerMoveUndo (useFeoLevel5.ts/useFeoPlannedItemAddDialog.ts/
// useFeoPlannedItemEditDialog.ts) и registerCategoryMoveUndo (useFeoTreeDnd.ts).
//
// ЧЕСТНОСТЬ: entry.undo()/entry.redo() обязаны вернуть { ok:false, error } вместо
// исключения — если обратный шаг не удался (позицию уже привязали к закупке, кто-то
// её поменял, сервер отказал), запись НЕ переезжает в другой стек и тост показывает
// причину — молчаливого «как будто отменили» быть не должно.
//
// Глубина — 5 (MAX_DEPTH), стек живёт в рамках ОДНОЙ субсидии: clear() при смене
// selectedId (иначе Ctrl+Z уехал бы в чужую субсидию). Module-level singleton —
// тот же приём, что и в useFeoLevel5.ts/useKpiDrilldown.ts.
import { computed, ref, watch, type Ref } from 'vue'
import { useToast } from '@/composables/useToast'

export type FeoUndoOutcome = { ok: true } | { ok: false; error: string }

export interface FeoUndoEntry {
  label: string
  undo: () => Promise<FeoUndoOutcome>
  redo: () => Promise<FeoUndoOutcome>
}

const MAX_DEPTH = 5
const undoStack = ref<FeoUndoEntry[]>([])
const redoStack = ref<FeoUndoEntry[]>([])
const busy = ref(false)

// Вызывается из мест, где произошло исходное действие (см. докстринг выше) —
// ЕДИНСТВЕННЫЙ способ положить запись на стек (Правило №6 — не заводим второй).
// Новое действие всегда обнуляет «будущее» (redoStack) — стандартное поведение
// любого undo/redo-стека: сделал что-то новое после отмены — повторить старое
// «вперёд» уже нельзя, история разошлась.
export function pushFeoUndo(entry: FeoUndoEntry) {
  undoStack.value = [...undoStack.value, entry].slice(-MAX_DEPTH)
  redoStack.value = []
}

export function clearFeoUndoStack() {
  undoStack.value = []
  redoStack.value = []
}

export const canUndoFeo = computed(() => undoStack.value.length > 0)
export const canRedoFeo = computed(() => redoStack.value.length > 0)
// Подпись под кнопкой/хоткеем — «Отменить: удаление позиции «Чайник»» (владелец:
// «человек должен понимать, ЧТО именно отменится»).
export const feoUndoLabel = computed(() => undoStack.value.length ? undoStack.value[undoStack.value.length - 1]!.label : '')
export const feoRedoLabel = computed(() => redoStack.value.length ? redoStack.value[redoStack.value.length - 1]!.label : '')

let _toast: ReturnType<typeof useToast> | null = null
function toast() {
  if (!_toast) _toast = useToast()
  return _toast
}

export async function performFeoUndo() {
  if (busy.value) return
  const entry = undoStack.value[undoStack.value.length - 1]
  if (!entry) return
  busy.value = true
  try {
    const res = await entry.undo()
    if (res.ok) {
      undoStack.value = undoStack.value.slice(0, -1)
      redoStack.value = [...redoStack.value, entry].slice(-MAX_DEPTH)
      toast().addToast(`Отменено: ${entry.label}`, 'success')
    } else {
      // Честно показываем причину и НЕ трогаем стек — запись остаётся на месте
      // (ещё не отменена), повторный Ctrl+Z/клик может сработать, если причина
      // была временной (сеть), либо человек увидит, что отменить нельзя вовсе.
      toast().addToast(`Не удалось отменить «${entry.label}»: ${res.error}`, 'error')
    }
  } finally {
    busy.value = false
  }
}

export async function performFeoRedo() {
  if (busy.value) return
  const entry = redoStack.value[redoStack.value.length - 1]
  if (!entry) return
  busy.value = true
  try {
    const res = await entry.redo()
    if (res.ok) {
      redoStack.value = redoStack.value.slice(0, -1)
      undoStack.value = [...undoStack.value, entry].slice(-MAX_DEPTH)
      toast().addToast(`Повторено: ${entry.label}`, 'success')
    } else {
      toast().addToast(`Не удалось повторить «${entry.label}»: ${res.error}`, 'error')
    }
  } finally {
    busy.value = false
  }
}

// ── Хоткеи ───────────────────────────────────────────────────────────────────
// Владелец явно потребовал ОТДЕЛЬНО проверить: «Ctrl+Z во время набора текста в
// поле НЕ должен трогать дерево» — иначе человек теряет введённый текст (браузер/
// поле обрабатывает Ctrl+Z как отмену ввода САМ, наш обработчик не должен ему
// мешать и тем более не должен параллельно дёргать дерево). Два независимых
// признака «сейчас печатают/открыт диалог»:
//  1) фокус на реальном поле ввода (input/textarea/select либо contenteditable) —
//     закрывает как обычные текстовые поля, так и v-select/v-autocomplete
//     Vuetify (у них тоже реальный <input> в DOM);
//  2) открыт МОДАЛЬНЫЙ диалог (.v-dialog.v-overlay--active — подтверждено по
//     исходникам vuetify/VDialog.js + VOverlay.js: активный v-dialog несёт ОБА
//     класса на одном узле) — блокирует хоткей, даже если фокус ещё не попал в
//     конкретное поле (человек только что открыл диалог и ещё не кликнул в
//     поле), чтобы Ctrl+Z не улетел в дерево ПОД диалогом.
function isEditableTarget(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  return (el as HTMLElement).isContentEditable === true
}

function anyFeoDialogOpen(): boolean {
  return !!document.querySelector('.v-dialog.v-overlay--active')
}

export function feoUndoHotkeyBlocked(): boolean {
  return isEditableTarget(document.activeElement) || anyFeoDialogOpen()
}

// Слушатель вешает/снимает SubsidiesView.vue (единственное место с деревом плана
// на экране) — здесь только чистая функция-обработчик, без побочного
// addEventListener, чтобы её было легко подключать/отключать и тестировать.
export function handleFeoUndoKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return
  const key = e.key.toLowerCase()
  const isUndo = key === 'z' && !e.shiftKey
  const isRedo = key === 'y' || (key === 'z' && e.shiftKey)
  if (!isUndo && !isRedo) return
  if (feoUndoHotkeyBlocked()) return
  if (isUndo) {
    if (!canUndoFeo.value) return
    e.preventDefault()
    void performFeoUndo()
  } else {
    if (!canRedoFeo.value) return
    e.preventDefault()
    void performFeoRedo()
  }
}

interface FeoUndoStackCtx {
  selectedId: Ref<number | null>
}

let _wired = false
export function useFeoUndoStack(ctx: FeoUndoStackCtx) {
  // Смена открытой субсидии обязана обнулить стек — иначе «отменить» на другой
  // субсидии попытается дёргать чужие плановые позиции/категории. watch стоит
  // один раз (module-level singleton, как и остальные composables этого модуля).
  if (!_wired) {
    _wired = true
    watch(ctx.selectedId, () => clearFeoUndoStack())
  }
  return {
    canUndoFeo, canRedoFeo, feoUndoLabel, feoRedoLabel,
    performFeoUndo, performFeoRedo,
  }
}
