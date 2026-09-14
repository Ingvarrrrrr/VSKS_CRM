// Drag & drop категорий ФЭО (перенос в поддерево/на верхний уровень,
// перестановка стрелками) + инлайн-редактирование финансирования/планового
// количества/плановой суммы узла — вынесено из SubsidiesView.vue (волна 5c).
// Единственный источник этой логики (Правило №6) — FeoTreeRow.vue/
// FeoTreeTable.vue вызывают через ctx.
//
// Module-level singleton (как useKpiDrilldown.ts).
import { nextTick, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { collectSubtreeIds } from './feoCategoryUtils'
import { pushFeoUndo } from './useFeoUndoStack'
import type { FeoCategory, FeoNode } from './types'

// Сырой перенос категории (смена родителя) — выделен из onDrop/onDropToRoot
// ниже для стека отмены (useFeoUndoStack.ts, «и перенос... категорий» из
// области задачи владельца, п.4 волны 4, 2026-09-13): undo/redo переноса
// категории зовут ЭТУ ЖЕ функцию в обратную/прямую сторону (Правило №6, второй
// PATCH не заводим). Экспортирована (доп. волна 2026-09-14, «отмена и для
// категорий по всем четырём действиям») — FeoCategoryDialog.vue переиспользует
// её же для смены родителя внутри диалога «Редактировать направление» вместо
// собственного PATCH (там раньше был третий похожий вызов того же PATCH).
export async function moveCategoryRaw(nodeId: number, parentId: number | null): Promise<{ ok: true; warning?: string } | { ok: false; error: string }> {
  try {
    const res = await apiFetch<any>(`/feo-categories/${nodeId}/move`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: parentId }),
    })
    return { ok: true, warning: res?.warning }
  } catch (e: any) {
    return { ok: false, error: e?.detail || e?.payload?.message || e?.message || 'Ошибка перемещения' }
  }
}

// ── Сырые create/put/delete категории — доп. волна 2026-09-14 ───────────────
// Владелец: «отмена для позиций И КАТЕГОРИЙ по всем четырём действиям» (создание/
// правка/удаление/перенос). Выделены сюда (не в FeoCategoryDialog.vue/
// FeoCategoryDeleteDialog.vue, которые их вызывают) — тот же приём, что и
// deletePlannedItemRaw/putPlannedItemFull/buildPlannedItemFullPayload в
// useFeoLevel5.ts: один источник запроса, используется и обычным путём
// (диалоги), и стеком отмены (Правило №6, второй набор запросов не заводим).
export async function createCategoryRaw(payload: Record<string, unknown>): Promise<FeoCategory> {
  return apiFetch<FeoCategory>('/feo-categories/', { method: 'POST', body: JSON.stringify(payload) })
}

export async function putCategoryFull(id: number, payload: Record<string, unknown>): Promise<{ ok: true; item: FeoCategory } | { ok: false; error: string }> {
  try {
    const item = await apiFetch<FeoCategory>(`/feo-categories/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
    return { ok: true, item }
  } catch (e: any) {
    return { ok: false, error: e?.payload?.message || e?.detail || e?.message || 'Ошибка сохранения' }
  }
}

// detail — сырой e.detail при 409 (объект {message, feo_category_ids} у
// закупок-держателей блокирующей стадии, см. delete_category в
// app/routers/feo_categories.py) — FeoCategoryDeleteDialog.vue строит из него
// кнопку «Перейти к закупкам этой категории», простой строки error для этого
// недостаточно.
export async function deleteCategoryRaw(id: number): Promise<{ ok: true } | { ok: false; error: string; detail?: any }> {
  try {
    await apiFetch(`/feo-categories/${id}`, { method: 'DELETE' })
    return { ok: true }
  } catch (e: any) {
    const detail = e?.detail
    const msg = (detail && typeof detail === 'object' && detail.message) ? detail.message
      : (typeof detail === 'string' ? detail : null)
    return { ok: false, error: e?.payload?.message || msg || e?.message || 'Не удалось удалить направление', detail }
  }
}

// Полный payload FeoCategoryCreate по снимку категории — POST и PUT на бэкенде
// используют ОДНУ схему (update_category(category_data: FeoCategoryCreate), см.
// app/routers/feo_categories.py). parent_id ЗДЕСЬ включён (в отличие от
// buildPlannedItemFullPayload) — категории меняют родителя и через этот же PUT
// в обычном updateFeoCategory (см. FeoCategoryDialog.vue), а не только через
// /move: важно для undo(create) — воссоздание должно попасть в ТУ ЖЕ позицию
// дерева, откуда её удалили.
export function buildCategoryFullPayload(cat: FeoCategory, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    parent_id: cat.parent_id ?? null,
    subsidy_id: cat.subsidy_id,
    name: cat.name,
    code: cat.code ?? null,
    appendix: cat.appendix ?? null,
    is_active: cat.is_active,
    description: cat.description ?? null,
    budget: cat.budget ?? null,
    feo_quantity: cat.feo_quantity ?? null,
    feo_unit: cat.feo_unit ?? null,
    feo_amount: cat.feo_amount ?? null,
    planned_quantity: cat.planned_quantity ?? null,
    planned_amount: cat.planned_amount ?? null,
    unit: cat.unit ?? null,
    plan_source: cat.plan_source || 'planned_items',
    manual_plan_amount: cat.manual_plan_amount ?? null,
    ...overrides,
  }
}

interface FeoTreeDndCtx {
  feoCategories: Ref<FeoCategory[]>
  visibleFeoNodes: import('vue').ComputedRef<FeoNode[]>
  selectedId: Ref<number | null>
  loadFeo: (subsidyId: number) => Promise<void>
  syncFeoFilled: () => void
}

let _api: ReturnType<typeof buildFeoTreeDnd> | null = null

export function useFeoTreeDnd(ctx: FeoTreeDndCtx) {
  if (!_api) _api = buildFeoTreeDnd(ctx)
  return _api
}

function buildFeoTreeDnd(ctx: FeoTreeDndCtx) {
  const { feoCategories, visibleFeoNodes, selectedId, loadFeo, syncFeoFilled } = ctx

  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  // ── Drag & Drop ──────────────────────────────────
  const dragNodeId = ref<number | null>(null)
  const dragOverId = ref<number | null>(null)

  function onDragStart(e: DragEvent, node: FeoNode) {
    dragNodeId.value = node.id
    e.dataTransfer!.effectAllowed = 'move'
    e.dataTransfer!.setData('text/plain', String(node.id))
  }
  function onDragOver(_e: DragEvent, node: FeoNode) {
    if (!dragNodeId.value || dragNodeId.value === node.id) return
    const subtree = collectSubtreeIds(feoCategories.value, dragNodeId.value)
    if (subtree.includes(node.id)) return
    dragOverId.value = node.id
  }
  function onDragLeave() { dragOverId.value = null }
  async function onDrop(e: DragEvent, targetNode: FeoNode) {
    e.preventDefault()
    if (!dragNodeId.value || dragNodeId.value === targetNode.id) return
    const srcId = dragNodeId.value
    const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
    dragOverId.value = null; dragNodeId.value = null
    if (!srcNode) return
    const subtree = collectSubtreeIds(feoCategories.value, srcId)
    if (subtree.includes(targetNode.id)) { showSnack('Нельзя переместить в собственное поддерево', 'error'); return }
    if (srcNode.parent_id === targetNode.id) return
    const fromParentId = srcNode.parent_id
    const res = await moveCategoryRaw(srcId, targetNode.id)
    if (!res.ok) { showSnack(res.error, 'error'); return }
    showSnack('Категория перемещена')
    if (res.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
    registerCategoryMoveUndo(srcId, srcNode.name, fromParentId, targetNode.id)
  }
  async function onDropToRoot(e: DragEvent) {
    e.preventDefault()
    if (!dragNodeId.value) return
    const srcId = dragNodeId.value
    const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
    dragOverId.value = null; dragNodeId.value = null
    if (!srcNode || !srcNode.parent_id) return
    const fromParentId = srcNode.parent_id
    const res = await moveCategoryRaw(srcId, null)
    if (!res.ok) { showSnack(res.error, 'error'); return }
    showSnack('Категория перемещена на верхний уровень')
    if (res.warning) showSnack(res.warning, 'warning')
    if (selectedId.value) await loadFeo(selectedId.value)
    syncFeoFilled()
    registerCategoryMoveUndo(srcId, srcNode.name, fromParentId, null)
  }
  function onDragEnd() { dragNodeId.value = null; dragOverId.value = null }

  // Стек отмены (владелец, «и перенос... категорий», п.4 волны 4, 2026-09-13):
  // undo/redo переноса категории — та же moveCategoryRaw в обратную/прямую
  // сторону, второго запроса не заводим.
  function registerCategoryMoveUndo(categoryId: number, name: string, fromParentId: number | null, toParentId: number | null) {
    pushFeoUndo({
      label: `перенос направления «${name}»`,
      undo: async () => {
        const res = await moveCategoryRaw(categoryId, fromParentId)
        if (res.ok && selectedId.value) { await loadFeo(selectedId.value); syncFeoFilled() }
        return res.ok ? { ok: true } : { ok: false, error: res.error }
      },
      redo: async () => {
        const res = await moveCategoryRaw(categoryId, toParentId)
        if (res.ok && selectedId.value) { await loadFeo(selectedId.value); syncFeoFilled() }
        return res.ok ? { ok: true } : { ok: false, error: res.error }
      },
    })
  }

  async function reorderFeoNode(node: FeoNode, direction: 'up' | 'down') {
    if (!selectedId.value) return
    try {
      const res = await apiFetch<any>(`/feo-categories/${node.id}/reorder`, {
        method: 'PATCH',
        body: JSON.stringify({ direction }),
      })
      if (res?.moved === false) {
        showSnack(direction === 'up' ? 'Уже первая в списке' : 'Уже последняя в списке', 'info')
        return
      }
      await loadFeo(selectedId.value)
      syncFeoFilled()
    } catch (e: any) {
      showSnack(e?.detail || e?.payload?.message || 'Не удалось переместить', 'error')
    }
  }

  // ── Отмена инлайн-редактирования по Escape ────────
  // Баг (найден на приёмке волны 5c, был и в исходнике 828f5b1:743-745/810-812
  // до разбиения на этот файл): @keydown.esc сбрасывал только inline*Id, но
  // снятие <input> с DOM после этого всё равно вызывает нативный blur → save*
  // берёт значение из _pending*Save (Escape его не трогал) и шлёт PUT —
  // Escape «сохранял» вместо отмены. Общий хелпер: флаг «это поле отменено»,
  // save* проверяет и гасит его ПЕРВЫМ действием, до единого запроса.
  function useCancellableFlag() {
    let cancelled = false
    return {
      cancel: () => { cancelled = true },
      consume: () => { const was = cancelled; cancelled = false; return was },
    }
  }

  // ── Inline budget edit ───────────────────────────
  const inlineBudgetId = ref<number | null>(null)
  const inlineBudgetVal = ref('')
  const inlineInputEl = ref<HTMLInputElement | null>(null)
  let _pendingBudgetSave: { nodeId: number; node: FeoNode } | null = null
  const budgetCancelFlag = useCancellableFlag()

  async function startInlineBudget(node: FeoNode) {
    inlineBudgetId.value = node.id
    inlineBudgetVal.value = node.budget != null ? String(node.budget) : ''
    _pendingBudgetSave = { nodeId: node.id, node }
    await nextTick()
    const el = Array.isArray(inlineInputEl.value) ? (inlineInputEl.value as any)[0] : inlineInputEl.value
    el?.focus?.()
  }
  function cancelInlineBudget() {
    _pendingBudgetSave = null
    inlineBudgetId.value = null
    budgetCancelFlag.cancel()
  }
  async function saveInlineBudget(node: FeoNode) {
    if (budgetCancelFlag.consume()) return
    const nodeId = _pendingBudgetSave?.nodeId ?? inlineBudgetId.value
    if (!nodeId) return
    const savedNode = _pendingBudgetSave?.node ?? node
    _pendingBudgetSave = null
    inlineBudgetId.value = null
    const raw = String(inlineBudgetVal.value ?? '').trim()
    const parsedBudget = raw === '' ? null : parseFloat(raw)
    // «0» в финансировании ФЭО = «не задано» наравне с пустым полем (владелец,
    // сессия 2026-09-05, п.8) — зеркалит backend/app/services/feo_plan_tree.py,
    // где узел с budget=0 тоже трактуется как отсутствие суммы. Единственное
    // место, где инлайн-ввод превращается в значение для PUT — держим правило
    // здесь, а не размазываем проверку по вызывающим местам.
    const val = (parsedBudget === null || Number.isNaN(parsedBudget) || parsedBudget === 0) ? null : parsedBudget
    try {
      await apiFetch(`/feo-categories/${nodeId}`, {
        method: 'PUT',
        body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
          is_active: savedNode.is_active, budget: val, planned_quantity: savedNode.planned_quantity ?? null,
          planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
      })
      const cat = feoCategories.value.find(c => c.id === nodeId)
      if (cat) cat.budget = val
      savedNode.budget = val
      feoCategories.value = [...feoCategories.value]
      syncFeoFilled()
    } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
  }

  // ── Inline planned_quantity edit ──────────────────
  const inlineQtyId = ref<number | null>(null)
  const inlineQtyVal = ref('')
  const inlineQtyInputEl = ref<HTMLInputElement | null>(null)
  let _pendingQtySave: { nodeId: number; node: FeoNode } | null = null
  const qtyCancelFlag = useCancellableFlag()

  async function startInlineQty(node: FeoNode) {
    inlineQtyId.value = node.id
    inlineQtyVal.value = node.planned_quantity != null ? String(node.planned_quantity) : ''
    _pendingQtySave = { nodeId: node.id, node }
    await nextTick()
    const elQ = Array.isArray(inlineQtyInputEl.value) ? (inlineQtyInputEl.value as any)[0] : inlineQtyInputEl.value
    elQ?.focus?.()
  }
  function cancelInlineQty() {
    _pendingQtySave = null
    inlineQtyId.value = null
    qtyCancelFlag.cancel()
  }
  async function saveInlineQty(node: FeoNode) {
    if (qtyCancelFlag.consume()) return
    const nodeId = _pendingQtySave?.nodeId ?? inlineQtyId.value
    if (!nodeId) return
    const savedNode = _pendingQtySave?.node ?? node
    _pendingQtySave = null
    inlineQtyId.value = null
    const raw = String(inlineQtyVal.value ?? '').trim()
    const val = raw === '' ? null : parseFloat(raw)
    try {
      await apiFetch(`/feo-categories/${nodeId}`, {
        method: 'PUT',
        body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
          is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: val,
          planned_amount: savedNode.planned_amount ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
      })
      const cat = feoCategories.value.find(c => c.id === nodeId)
      if (cat) cat.planned_quantity = val
      savedNode.planned_quantity = val
      feoCategories.value = [...feoCategories.value]
    } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
  }

  // ── Inline planned_amount edit ────────────────────
  const inlineAmtId = ref<number | null>(null)
  const inlineAmtVal = ref('')
  const inlineAmtInputEl = ref<HTMLInputElement | null>(null)
  let _pendingAmtSave: { nodeId: number; node: FeoNode } | null = null

  async function startInlineAmt(node: FeoNode) {
    inlineAmtId.value = node.id
    inlineAmtVal.value = node.planned_amount != null ? String(node.planned_amount) : ''
    _pendingAmtSave = { nodeId: node.id, node }
    await nextTick()
    const elA = Array.isArray(inlineAmtInputEl.value) ? (inlineAmtInputEl.value as any)[0] : inlineAmtInputEl.value
    elA?.focus?.()
  }
  async function saveInlineAmt(node: FeoNode) {
    const nodeId = _pendingAmtSave?.nodeId ?? inlineAmtId.value
    if (!nodeId) return
    const savedNode = _pendingAmtSave?.node ?? node
    _pendingAmtSave = null
    inlineAmtId.value = null
    const raw = String(inlineAmtVal.value ?? '').trim()
    const val = raw === '' ? null : parseFloat(raw)
    try {
      await apiFetch(`/feo-categories/${nodeId}`, {
        method: 'PUT',
        body: JSON.stringify({ name: savedNode.name, code: savedNode.code ?? null, appendix: savedNode.appendix ?? null,
          is_active: savedNode.is_active, budget: savedNode.budget ?? null, planned_quantity: savedNode.planned_quantity ?? null,
          planned_amount: val ?? null, unit: savedNode.unit ?? null, subsidy_id: savedNode.subsidy_id }),
      })
      const cat = feoCategories.value.find(c => c.id === nodeId)
      if (cat) cat.planned_amount = val ?? null
      savedNode.planned_amount = val ?? null
      feoCategories.value = [...feoCategories.value]
    } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
  }

  return {
    dragNodeId, dragOverId, onDragStart, onDragOver, onDragLeave, onDrop, onDropToRoot, onDragEnd,
    reorderFeoNode, registerCategoryMoveUndo,
    inlineBudgetId, inlineBudgetVal, inlineInputEl, startInlineBudget, saveInlineBudget, cancelInlineBudget,
    inlineQtyId, inlineQtyVal, inlineQtyInputEl, startInlineQty, saveInlineQty, cancelInlineQty,
    inlineAmtId, inlineAmtVal, inlineAmtInputEl, startInlineAmt, saveInlineAmt,
  }
}
