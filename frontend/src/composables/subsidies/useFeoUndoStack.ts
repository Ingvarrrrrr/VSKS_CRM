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
// «busy» теперь отражает очередь (см. _feoUndoRedoChain ниже), а не блокирует
// повторное нажатие — см. докстринг у неё.
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

// Очередь записи в стек (владелец, п.4, 13.10.2026): «удалил "Аренда офиса",
// потом "Канцтовары" — Ctrl+Z вернул "Аренда офиса"» вместо последней
// удалённой. Причина — гонка: у каждой позиции СВОЙ ряд (deletingPlannedItemId
// держит id именно этой строки), поэтому можно нажать удаление второй позиции,
// не дождавшись ответа сервера на первую, и если второй запрос (вместе с
// refreshComparison/refreshReqData) ответит раньше — pushFeoUndo для него
// отработает раньше, и порядок в стеке окажется противоположным порядку
// кликов. runFeoWriteSerialized — ЕДИНЫЙ механизм (Правило №6), которым
// оборачивается промежуток «запрос на сервер → pushFeoUndo» у удаления/
// переноса/создания позиции и переноса категории: каждое следующее действие
// ждёт, пока предыдущее не положит (или не откажется положить) свою запись,
// так что порядок в стеке = порядку, в котором человек нажимал кнопки,
// а не порядку ответов сети.
let _feoWriteChain: Promise<unknown> = Promise.resolve()
export function runFeoWriteSerialized<T>(fn: () => Promise<T>): Promise<T> {
  const run = _feoWriteChain.then(fn, fn)
  _feoWriteChain = run.then(() => undefined, () => undefined)
  return run
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

// Очередь отмены/повтора (найдено QA, 13.10.2026 — волна 2): «удалил позицию из
// плановой, Ctrl+Z, Ctrl+Z ещё раз — второе нажатие не делает НИЧЕГО: ни тоста,
// ни запроса». Причина — busy-флаг СТАРОЙ реализации: пока первый undo() ждёт
// сервер (а при большом дереве/категории с подкатегориями ctx.loadFeo() после
// undo может занять больше времени, чем пауза между двумя нажатиями), второе
// нажатие видело busy=true и тихо возвращалось — ни тоста об этом, ни попытки
// повторить, вопреки «любая неудача отката — не молча» из докстринга выше.
// Теперь оба действия (undo и redo) идут через ОДНУ очередь: второе нажатие не
// теряется, а исполняется СРАЗУ ПОСЛЕ первого — то, что человек ожидает от
// «быстро нажал Ctrl+Z дважды». Undo и redo нарочно делят одну очередь (а не
// две раздельных), иначе быстрое чередование Ctrl+Z/Ctrl+Y могло бы исполниться
// не по порядку и испортить оба стека одновременно.
let _feoUndoRedoChain: Promise<unknown> = Promise.resolve()
function queueFeoUndoRedo(fn: () => Promise<void>): Promise<void> {
  busy.value = true
  const run = _feoUndoRedoChain.then(fn, fn)
  const settled = run.then(() => undefined, () => undefined)
  _feoUndoRedoChain = settled
  // Снимаем busy только когда ЭТА операция была последней поставленной в
  // очередь — если за время её выполнения встали ещё нажатия, индикатор
  // должен остаться «занято» до конца всей цепочки, а не мигать между ними.
  settled.finally(() => {
    if (_feoUndoRedoChain === settled) busy.value = false
  })
  return run as Promise<void>
}

async function doPerformFeoUndo() {
  const entry = undoStack.value[undoStack.value.length - 1]
  if (!entry) return
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
}

async function doPerformFeoRedo() {
  const entry = redoStack.value[redoStack.value.length - 1]
  if (!entry) return
  const res = await entry.redo()
  if (res.ok) {
    redoStack.value = redoStack.value.slice(0, -1)
    undoStack.value = [...undoStack.value, entry].slice(-MAX_DEPTH)
    toast().addToast(`Повторено: ${entry.label}`, 'success')
  } else {
    toast().addToast(`Не удалось повторить «${entry.label}»: ${res.error}`, 'error')
  }
}

export function performFeoUndo(): Promise<void> {
  return queueFeoUndoRedo(doPerformFeoUndo)
}

export function performFeoRedo(): Promise<void> {
  return queueFeoUndoRedo(doPerformFeoRedo)
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
  // Владелец (п.4, 13.10.2026): «сочетание клавиш не работают». Причина —
  // e.key на русской раскладке для физических клавиш Z/Y отдаёт «я»/«н»
  // (раскладка меняет СИМВОЛ, который сравнивали с 'z'/'y' — сравнение
  // никогда не совпадало). e.code — код физической клавиши, не зависит от
  // раскладки: 'KeyZ'/'KeyY' одинаковы и на латинице, и на кириллице.
  const code = e.code
  const isUndo = code === 'KeyZ' && !e.shiftKey
  const isRedo = code === 'KeyY' || (code === 'KeyZ' && e.shiftKey)
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
