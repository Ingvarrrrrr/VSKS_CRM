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
import type { FeoCategory, FeoNode } from './types'

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
    try {
      const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
        method: 'PATCH', body: JSON.stringify({ parent_id: targetNode.id }),
      })
      showSnack('Категория перемещена')
      if (res?.warning) showSnack(res.warning, 'warning')
      if (selectedId.value) await loadFeo(selectedId.value)
      syncFeoFilled()
    } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
  }
  async function onDropToRoot(e: DragEvent) {
    e.preventDefault()
    if (!dragNodeId.value) return
    const srcId = dragNodeId.value
    const srcNode = visibleFeoNodes.value.find(n => n.id === srcId)
    dragOverId.value = null; dragNodeId.value = null
    if (!srcNode || !srcNode.parent_id) return
    try {
      const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
        method: 'PATCH', body: JSON.stringify({ parent_id: null }),
      })
      showSnack('Категория перемещена на верхний уровень')
      if (res?.warning) showSnack(res.warning, 'warning')
      if (selectedId.value) await loadFeo(selectedId.value)
      syncFeoFilled()
    } catch (e: any) { showSnack(e.detail || 'Ошибка перемещения', 'error') }
  }
  function onDragEnd() { dragNodeId.value = null; dragOverId.value = null }

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

  // ── Inline budget edit ───────────────────────────
  const inlineBudgetId = ref<number | null>(null)
  const inlineBudgetVal = ref('')
  const inlineInputEl = ref<HTMLInputElement | null>(null)
  let _pendingBudgetSave: { nodeId: number; node: FeoNode } | null = null

  async function startInlineBudget(node: FeoNode) {
    inlineBudgetId.value = node.id
    inlineBudgetVal.value = node.budget != null ? String(node.budget) : ''
    _pendingBudgetSave = { nodeId: node.id, node }
    await nextTick()
    const el = Array.isArray(inlineInputEl.value) ? (inlineInputEl.value as any)[0] : inlineInputEl.value
    el?.focus?.()
  }
  async function saveInlineBudget(node: FeoNode) {
    const nodeId = _pendingBudgetSave?.nodeId ?? inlineBudgetId.value
    if (!nodeId) return
    const savedNode = _pendingBudgetSave?.node ?? node
    _pendingBudgetSave = null
    inlineBudgetId.value = null
    const raw = String(inlineBudgetVal.value ?? '').trim()
    const val = raw === '' ? null : parseFloat(raw)
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

  async function startInlineQty(node: FeoNode) {
    inlineQtyId.value = node.id
    inlineQtyVal.value = node.planned_quantity != null ? String(node.planned_quantity) : ''
    _pendingQtySave = { nodeId: node.id, node }
    await nextTick()
    const elQ = Array.isArray(inlineQtyInputEl.value) ? (inlineQtyInputEl.value as any)[0] : inlineQtyInputEl.value
    elQ?.focus?.()
  }
  async function saveInlineQty(node: FeoNode) {
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
    reorderFeoNode,
    inlineBudgetId, inlineBudgetVal, inlineInputEl, startInlineBudget, saveInlineBudget,
    inlineQtyId, inlineQtyVal, inlineQtyInputEl, startInlineQty, saveInlineQty,
    inlineAmtId, inlineAmtVal, inlineAmtInputEl, startInlineAmt, saveInlineAmt,
  }
}
