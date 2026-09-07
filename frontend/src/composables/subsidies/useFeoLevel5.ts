// Level 5 дерева ФЭО — панель «Плановые позиции vs Фактические» (comparisonData:
// FeoPlannedItem[]/FeoActualItem[] по категории), разбор «сколько уже разобрано»,
// стадии уточнения наименования и удаление/перенос/переупорядочивание плановых
// позиций. Вынесено из SubsidiesView.vue (волна 5c) — единственный источник
// (Правило №6); FeoLevel5Panel.vue, FeoTreeRow.vue (расшифровка «из-за» под
// «Плановой суммой») и usePlannedItems.ts читают/вызывают через ctx.
//
// Module-level singleton (как useKpiDrilldown.ts).
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { formatCurrency, formatCurrencyRound } from './format'
import { normName } from './feoCategoryUtils'
import type {
  DiffActual, FeoActualItem, FeoCategory, FeoNode, FeoPlannedItem, FeoStage, FeoStageRow,
} from './types'

interface ExcessReasonPurchase { id: number; label: string; amount: number; stopped: boolean }
interface ExcessReasonItem { key: string; name: string; amount: number; purchases: ExcessReasonPurchase[] }

interface FeoLevel5Ctx {
  selectedId: Ref<number | null>
  feoCategories: Ref<FeoCategory[]>
  feoTree: ComputedRef<FeoNode[]>
  flattenAll: (nodes: FeoNode[]) => FeoNode[]
  expandedItemPanels: Ref<Set<number>>
  expandedPlannedItems: Ref<Set<number>>
  collapsedPlannedItems: Ref<Set<number>>
  feoResidualNoteFor: (node: FeoNode) => { planned: number; consumed: number; residual: number } | null
  refreshReqData: (catId?: number) => Promise<void>
}

let _api: ReturnType<typeof buildFeoLevel5> | null = null

export function useFeoLevel5(ctx: FeoLevel5Ctx) {
  if (!_api) _api = buildFeoLevel5(ctx)
  return _api
}

function buildFeoLevel5(ctx: FeoLevel5Ctx) {
  const {
    selectedId, feoCategories, feoTree, flattenAll,
    expandedItemPanels, expandedPlannedItems, collapsedPlannedItems,
    feoResidualNoteFor, refreshReqData,
  } = ctx

  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }
  // ── comparisonData: единственный источник детализации листа (Ур.5) ──────────
  const comparisonData = ref<Record<number, { planned: FeoPlannedItem[]; actual: FeoActualItem[] }>>({})
  const loadingComparison = ref<Set<number>>(new Set())
  const photoPreview = ref<{ src: string; title: string } | null>(null)

  async function toggleItemPanel(node: FeoNode) {
    const id = node.id
    if (expandedItemPanels.value.has(id)) {
      expandedItemPanels.value.delete(id)
      return
    }
    expandedItemPanels.value.add(id)
    if (comparisonData.value[id]) return
    loadingComparison.value.add(id)
    try {
      const subsId = selectedId.value
      const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
        `/feo-planned-items/comparison?feo_category_id=${id}${subsId ? `&subsidy_id=${subsId}` : ''}`
      )
      comparisonData.value[id] = res
      applyDefaultPlannedExpansion(id)
    } catch {
      comparisonData.value[id] = { planned: [], actual: [] }
    } finally {
      loadingComparison.value.delete(id)
    }
  }

  async function refreshComparison(categoryId: number) {
    const subsId = selectedId.value
    const res = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
      `/feo-planned-items/comparison?feo_category_id=${categoryId}${subsId ? `&subsidy_id=${subsId}` : ''}`
    )
    comparisonData.value[categoryId] = res
    applyDefaultPlannedExpansion(categoryId)
  }

  async function ensureComparison(catId: number) {
    if (comparisonData.value[catId]) return
    loadingComparison.value.add(catId)
    try {
      const subsId = selectedId.value
      comparisonData.value[catId] = await apiFetch<{ planned: FeoPlannedItem[]; actual: FeoActualItem[] }>(
        `/feo-planned-items/comparison?feo_category_id=${catId}${subsId ? `&subsidy_id=${subsId}` : ''}`
      )
      applyDefaultPlannedExpansion(catId)
    } catch {
      comparisonData.value[catId] = { planned: [], actual: [] }
    } finally {
      loadingComparison.value.delete(catId)
    }
  }

  // Применяет правило «раскрыто по умолчанию, если под плановой позицией есть закупка».
  function applyDefaultPlannedExpansion(catId: number) {
    const data = comparisonData.value[catId]
    if (!data) return
    const cat = feoCategories.value.find(c => c.id === catId)
    const plannedIds: number[] = data.planned.length
      ? data.planned.map(p => p.id)
      : (cat && (cat.planned_quantity != null || cat.planned_amount != null)) ? [-catId] : []
    for (const pid of plannedIds) {
      if (collapsedPlannedItems.value.has(pid)) continue
      if (expandedPlannedItems.value.has(pid)) continue
      if (factForPlanned(catId, pid).length > 0) {
        expandedPlannedItems.value.add(pid)
      }
    }
  }

  function anyPlannedExpandedFor(node: FeoNode): boolean {
    return displayPlannedRowsFor(node).some(p => expandedPlannedItems.value.has(p.id))
  }
  function toggleAllPlannedItemsForCategory(node: FeoNode) {
    const ids = displayPlannedRowsFor(node).map(p => p.id)
    const collapse = ids.some(id => expandedPlannedItems.value.has(id))
    for (const id of ids) {
      if (collapse) {
        expandedPlannedItems.value.delete(id)
        collapsedPlannedItems.value.add(id)
      } else {
        expandedPlannedItems.value.add(id)
        collapsedPlannedItems.value.delete(id)
      }
    }
  }

  // ── Факт по требованию владельца (2026-08-05/2026-08-06) ────────────────────
  const FACT_STATUSES = ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
  function isFactActual(a: { purchase_status?: string | null }): boolean {
    return FACT_STATUSES.includes(a.purchase_status || '')
  }
  const WISH_PLAN_LOCKED_STATUSES = ['wishes', 'plan_schedule', 'work_in_progress']
  function isWishLocked(it: { wish_id?: number | null; purchase_status?: string | null }): boolean {
    return !!it.wish_id && WISH_PLAN_LOCKED_STATUSES.includes(it.purchase_status || '')
  }
  function actualFactFor(catId: number) {
    return (comparisonData.value[catId]?.actual || []).filter(a => isFactActual(a))
  }
  function allActualFor(catId: number) {
    return comparisonData.value[catId]?.actual || []
  }

  // Фолбэк «плановая позиция была создана из заявки — названия совпадают, значит должны
  // разворачиваться в план БЕЗ факта» (см. подробный комментарий в истории SubsidiesView.vue).
  const fallbackAbsorbedByCategory = computed((): Record<number, Map<number, number>> => {
    const result: Record<number, Map<number, number>> = {}
    for (const key of Object.keys(comparisonData.value)) {
      const catId = Number(key)
      const data = comparisonData.value[catId]!
      const map = new Map<number, number>()
      const usedIds = new Set<number>()
      for (const planned of data.planned || []) {
        const hasBound = (data.actual || []).some(a => a.feo_planned_item_id === planned.id)
        if (hasBound) continue
        const targetName = normName(planned.name)
        if (!targetName) continue
        for (const a of data.actual || []) {
          if (a.feo_planned_item_id) continue
          if (usedIds.has(a.purchase_item_id)) continue
          if (normName(a.item_name) !== targetName) continue
          map.set(a.purchase_item_id, planned.id)
          usedIds.add(a.purchase_item_id)
        }
      }
      result[catId] = map
    }
    return result
  })

  // plannedId < 0 — синтетическая «ручная плановая позиция» (см. displayPlannedRowsFor).
  function factForPlanned(catId: number, plannedId: number) {
    if (plannedId < 0) return allActualFor(catId).filter(a => !a.feo_planned_item_id)
    const bound = allActualFor(catId).filter(a => a.feo_planned_item_id === plannedId)
    if (bound.length) return bound
    const absorbed = fallbackAbsorbedByCategory.value[catId]
    if (!absorbed) return bound
    return allActualFor(catId).filter(a => absorbed.get(a.purchase_item_id) === plannedId)
  }

  function factForPlannedTotal(catId: number, plannedId: number): number {
    return factForPlanned(catId, plannedId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
  }

  function purchaseLabelFor(a: { registry_number?: string | null; purchase_number?: number | null; purchase_id: number }): string {
    return a.registry_number || (a.purchase_number != null ? `№ ${a.purchase_number}` : `#${a.purchase_id}`)
  }

  // Расшифровка «больше плана на X» у заметки «план … · в закупках … · больше плана на …» —
  // используется и FeoTreeRow.vue (заметка под «Плановой суммой»).
  function factExcessReasonItems(node: FeoNode): ExcessReasonItem[] {
    const catId = node.id
    const data = comparisonData.value[catId]
    if (!data) return []
    const items: ExcessReasonItem[] = []
    for (const p of data.planned || []) {
      const amount = factForPlannedTotal(catId, p.id) - Number(p.amount ?? 0)
      if (amount <= 0.005) continue
      const facts = factForPlanned(catId, p.id)
      items.push({
        key: `p-${p.id}`,
        name: p.name,
        amount,
        purchases: facts.map(a => ({
          id: a.purchase_id,
          label: purchaseLabelFor(a),
          amount: Number(a.fact_amount ?? a.total_price ?? 0),
          stopped: !!a.stopped_at,
        })),
      })
    }
    for (const a of unplannedActualFor(node)) {
      const amount = Number(a.fact_amount ?? a.total_price ?? 0)
      if (amount <= 0.005) continue
      items.push({
        key: `a-${a.purchase_item_id}`,
        name: a.item_name,
        amount,
        purchases: [{ id: a.purchase_id, label: purchaseLabelFor(a), amount, stopped: !!a.stopped_at }],
      })
    }
    return items.sort((a, b) => b.amount - a.amount)
  }
  function factExcessReasonRemainder(node: FeoNode): number {
    const note = feoResidualNoteFor(node)
    if (!note) return 0
    const total = -note.residual
    const shown = factExcessReasonItems(node).reduce((s, it) => s + it.amount, 0)
    return total - shown
  }

  // ── Шапка вложенной таблицы закупок плановой позиции — ровно одна стадия ────
  function stageHeaderLabelFor(status: string | null | undefined): string {
    if (status === 'wishes' || status === 'plan_schedule') return 'Как называется в заявке'
    if (status === 'work_in_progress') return 'Как называется в закупке'
    if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Как в договоре'
    return 'Позиция закупки'
  }
  function stageChipLabelFor(status: string | null | undefined): string {
    const full = stageHeaderLabelFor(status)
    if (full === 'Как называется в заявке') return 'как в заявке'
    if (full === 'Как называется в закупке') return 'как в закупке'
    if (full === 'Как в договоре') return 'как в договоре'
    return 'как выставили'
  }
  function stageChipTitleFor(status: string | null | undefined): string {
    if (status === 'wishes' || status === 'plan_schedule') return 'Наименование, количество и цена — как их завели в заявке; в закупку ещё не выставлено'
    if (status === 'work_in_progress') return 'Наименование, количество и цена — как выставлено в закупке'
    if (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') return 'Наименование, количество и цена — из договора с подрядчиком'
    return 'Как товар завели в заявке/ТЗ — до заключения договора'
  }
  function stageChipColorFor(status: string | null | undefined): string {
    return (status === 'contracted' || status === 'ordered' || status === 'delivered' || status === 'paid') ? 'indigo' : 'blue-grey'
  }
  function factStageHeaderFor(catId: number, plannedId: number): string {
    const facts = factForPlanned(catId, plannedId)
    if (!facts.length) return 'Позиция закупки'
    const labels = new Set(facts.map(a => stageHeaderLabelFor(a.purchase_status)))
    if (labels.size > 1) return 'Позиция закупки'
    return [...labels][0]!
  }

  // ── Разбор плана на строке плановой позиции («сколько уже разобрано») ───────
  function planBreakdownText(catId: number, planned: FeoPlannedItem & { isManual?: boolean }): string {
    const facts = factForPlanned(catId, planned.id)
    const amountTotal = Number(planned.amount ?? 0)
    const amountTaken = factForPlannedTotal(catId, planned.id)
    const amountRemaining = amountTotal - amountTaken
    const unit = planned.unit || 'шт'
    if (planned.quantity != null) {
      const qtyTotal = Math.round(Number(planned.quantity) * 10000) / 10000
      const qtyTaken = Math.round(facts.reduce((s, a) => s + Number(a.quantity ?? 0), 0) * 10000) / 10000
      const qtyRemaining = Math.round((qtyTotal - qtyTaken) * 10000) / 10000
      return `в закупках ${qtyTaken} из ${qtyTotal} ${unit} · на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${qtyRemaining} ${unit} и ${formatCurrency(amountRemaining)}`
    }
    return `в закупках на ${formatCurrency(amountTaken)} из ${formatCurrency(amountTotal)} · остаток ${formatCurrency(amountRemaining)}`
  }

  // Строки «Плановые позиции» листа: реальные FeoPlannedItem, ИЛИ — если их нет, а план
  // задан прямо на листе — одна псевдо-строка «ручной план ФЭО» (id = -node.id).
  function displayPlannedRowsFor(node: FeoNode): (FeoPlannedItem & { isManual?: boolean })[] {
    const real = comparisonData.value[node.id]?.planned || []
    if (real.length) return real
    if (node.planned_quantity == null && node.planned_amount == null) return []
    const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
    const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
    const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
    return [{
      id: -node.id,
      feo_category_id: node.id,
      name: node.name,
      quantity: qty,
      unit: node.unit || null,
      amount,
      unit_price: amount != null ? unitPrice : null,
      notes: null,
      is_active: true,
      isManual: true,
    }]
  }

  // «Не привязаны к плану — требуется действие».
  function unplannedActualFor(node: FeoNode) {
    const catId = node.id
    const hasManualPseudoRow = !(comparisonData.value[catId]?.planned || []).length
      && (node.planned_quantity != null || node.planned_amount != null)
    const absorbed = fallbackAbsorbedByCategory.value[catId]
    const plannedIds = new Set((comparisonData.value[catId]?.planned || []).map(p => p.id))
    return allActualFor(catId).filter(a => {
      if (a.feo_planned_item_id != null) {
        return !plannedIds.has(a.feo_planned_item_id)
      }
      if (hasManualPseudoRow) return false
      return !(absorbed && absorbed.has(a.purchase_item_id))
    })
  }

  function isOrphanedActual(actual: FeoActualItem): boolean {
    return actual.feo_planned_item_id != null
  }

  // Dev-ассерт: панель «план vs факт» листа обязана показывать каждую PurchaseItem
  // категории РОВНО один раз.
  function devCheckNoDuplicateItems(catId: number) {
    if (!import.meta.env.DEV) return
    const node = flattenAll(feoTree.value).find(n => n.id === catId)
    if (!node || node.hasChildren) return
    const ids: number[] = []
    for (const planned of displayPlannedRowsFor(node)) {
      for (const a of factForPlanned(catId, planned.id)) ids.push(a.purchase_item_id)
    }
    for (const a of unplannedActualFor(node)) ids.push(a.purchase_item_id)
    const seen = new Set<number>()
    const dups = new Set<number>()
    for (const id of ids) {
      if (seen.has(id)) dups.add(id)
      seen.add(id)
    }
    if (dups.size) {
      console.warn(`[ФЭО дерево] Дубли PurchaseItem.id в панели «${node.name}» (категория ${catId}):`, [...dups])
    }
    const missing = allActualFor(catId).filter(a => !seen.has(a.purchase_item_id))
    if (missing.length) {
      console.warn(`[ФЭО дерево] Позиции закупок пропали из панели «${node.name}» (категория ${catId}):`, missing.map(a => a.purchase_item_id))
    }
  }
  watch(comparisonData, (data) => {
    for (const catId of Object.keys(data).map(Number)) devCheckNoDuplicateItems(catId)
  }, { deep: true })

  function comparisonPlanTotal(node: FeoNode): number {
    return displayPlannedRowsFor(node).reduce((s, p) => s + Number(p.amount || 0), 0)
  }
  function comparisonFactTotal(catId: number): number {
    return actualFactFor(catId).reduce((s, a) => s + Number(a.fact_amount ?? a.total_price ?? 0), 0)
  }

  function plannedItemIndentPx(node: FeoNode): number {
    return node.depth * 20 + 53
  }

  // ── Diff helpers ─────────────────────────────────────────────────────────
  const DIFF_COMMITTED_STATUSES = ['work_in_progress', 'contracted', 'ordered']
  function calcDiff(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): number {
    const amountOf = (a: DiffActual) => Number(a.fact_amount ?? a.total_price ?? 0)
    const delivered = actuals.filter(a => ['delivered', 'paid'].includes(a.purchase_status || ''))
    const committed = actuals.filter(a => DIFF_COMMITTED_STATUSES.includes(a.purchase_status || ''))
    const factSum = delivered.length
      ? delivered.reduce((s, a) => s + amountOf(a), 0)
      : committed.reduce((s, a) => s + amountOf(a), 0)
    return Number(plannedAmount || 0) - factSum
  }
  function getDiffStyle(plannedAmount: number | string | null | undefined, actuals: DiffActual[]): string {
    const diff = calcDiff(plannedAmount, actuals)
    return diff >= 0 ? 'color:#166534;font-weight:600' : 'color:#DC2626;font-weight:600'
  }

  // ── Подстроки стадий уточнения ───────────────────────────────────────────
  function stagesWithDiff(stages: FeoStage[] | undefined): FeoStageRow[] {
    const list = stages || []
    return list.map((stage, i) => {
      const prev = i > 0 ? list[i - 1] : null
      let nameChanged = false
      let qtyDeltaLabel: string | null = null
      let qtyDeltaColor = ''
      let priceDeltaLabel: string | null = null
      let priceDeltaColor = ''
      if (prev) {
        nameChanged = normName(stage.name) !== normName(prev.name)
        const qtyDelta = Math.round((Number(stage.quantity || 0) - Number(prev.quantity || 0)) * 10000) / 10000
        if (Math.abs(qtyDelta) >= 0.0001) {
          qtyDeltaColor = qtyDelta < 0 ? '#DC2626' : '#EA580C'
          qtyDeltaLabel = `${qtyDelta > 0 ? '+' : '−'}${Math.abs(qtyDelta)}${stage.unit ? ' ' + stage.unit : ''}`
        }
        const priceDelta = Number(stage.unit_price || 0) - Number(prev.unit_price || 0)
        if (Math.abs(priceDelta) >= 0.005) {
          priceDeltaColor = priceDelta < 0 ? '#DC2626' : '#EA580C'
          priceDeltaLabel = `${priceDelta > 0 ? '+' : '−'}${formatCurrencyRound(Math.abs(priceDelta))}`
        }
      }
      return { stage, nameChanged, qtyDeltaLabel, qtyDeltaColor, priceDeltaLabel, priceDeltaColor }
    })
  }

  // ── Удаление / перенос / переупорядочивание плановых позиций ────────────
  const deletingPlannedItemId = ref<number | null>(null)
  async function deletePlannedItem(item: FeoPlannedItem) {
    deletingPlannedItemId.value = item.id
    try {
      await apiFetch(`/feo-planned-items/${item.id}`, { method: 'DELETE' })
      await Promise.all([refreshComparison(item.feo_category_id), refreshReqData()])
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось удалить плановую позицию', 'error')
    } finally {
      deletingPlannedItemId.value = null
    }
  }

  function descendantCategoriesFor(node: FeoNode): FeoNode[] {
    return flattenAll(node.children || [])
  }

  const movingPlannedItemId = ref<number | null>(null)
  async function movePlannedItemToCategory(item: FeoPlannedItem, targetCategoryId: number) {
    if (item.feo_category_id === targetCategoryId) return
    const sourceCategoryId = item.feo_category_id
    movingPlannedItemId.value = item.id
    try {
      await apiFetch(`/feo-planned-items/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          feo_category_id: targetCategoryId,
          name: item.name,
          quantity: item.quantity,
          unit: item.unit,
          amount: item.amount,
          unit_price: item.unit_price ?? null,
          notes: item.notes,
          is_active: item.is_active,
          payment_mode: item.payment_mode ?? 'one_time',
          planned_date: item.planned_date ?? null,
          monthly_start_date: item.monthly_start_date ?? null,
          months_count: item.months_count ?? null,
          monthly_amount: item.monthly_amount ?? null,
          sort_order: item.sort_order ?? null,
          item_type: item.item_type ?? null,
        }),
      })
      await Promise.all([refreshComparison(sourceCategoryId), refreshComparison(targetCategoryId)])
      await refreshReqData()
      showSnack('Позиция перенесена')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || 'Ошибка переноса', 'error')
    } finally {
      movingPlannedItemId.value = null
    }
  }

  const reorderingPlannedItemId = ref<number | null>(null)
  async function savePlannedItemSortOrder(item: FeoPlannedItem, newOrder: number) {
    await apiFetch(`/feo-planned-items/${item.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        feo_category_id: item.feo_category_id,
        name: item.name,
        quantity: item.quantity,
        unit: item.unit,
        amount: item.amount,
        unit_price: item.unit_price ?? null,
        notes: item.notes,
        is_active: item.is_active,
        payment_mode: item.payment_mode ?? 'one_time',
        planned_date: item.planned_date ?? null,
        monthly_start_date: item.monthly_start_date ?? null,
        months_count: item.months_count ?? null,
        monthly_amount: item.monthly_amount ?? null,
        sort_order: newOrder,
        item_type: item.item_type ?? null,
      }),
    })
  }

  async function reorderPlannedItem(node: FeoNode, pIdx: number, direction: 'up' | 'down') {
    const rows = displayPlannedRowsFor(node)
    const a = rows[pIdx]
    const targetIdx = direction === 'up' ? pIdx - 1 : pIdx + 1
    if (!a || a.isManual || targetIdx < 0 || targetIdx >= rows.length) return
    const b = rows[targetIdx]
    if (!b || b.isManual) return
    reorderingPlannedItemId.value = a.id
    try {
      const needsBaseline = rows.some(p => p.sort_order == null)
      const orders = needsBaseline ? rows.map((_, i) => i + 1) : rows.map(p => Number(p.sort_order))
      if (needsBaseline) {
        for (let i = 0; i < rows.length; i++) {
          if (i === pIdx || i === targetIdx) continue
          if (Number(rows[i]!.sort_order) === orders[i]) continue
          await savePlannedItemSortOrder(rows[i]!, orders[i]!)
        }
      }
      await savePlannedItemSortOrder(a, orders[targetIdx]!)
      await savePlannedItemSortOrder(b, orders[pIdx]!)
      await refreshComparison(node.id)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось изменить порядок плановых позиций', 'error')
    } finally {
      reorderingPlannedItemId.value = null
    }
  }

  return {
    comparisonData, loadingComparison, photoPreview,
    toggleItemPanel, refreshComparison, ensureComparison, applyDefaultPlannedExpansion,
    anyPlannedExpandedFor, toggleAllPlannedItemsForCategory,
    FACT_STATUSES, isFactActual, WISH_PLAN_LOCKED_STATUSES, isWishLocked,
    actualFactFor, allActualFor, fallbackAbsorbedByCategory, factForPlanned, factForPlannedTotal,
    purchaseLabelFor, factExcessReasonItems, factExcessReasonRemainder,
    stageHeaderLabelFor, stageChipLabelFor, stageChipTitleFor, stageChipColorFor, factStageHeaderFor,
    planBreakdownText, displayPlannedRowsFor, unplannedActualFor, isOrphanedActual,
    comparisonPlanTotal, comparisonFactTotal, plannedItemIndentPx,
    DIFF_COMMITTED_STATUSES, calcDiff, getDiffStyle, stagesWithDiff,
    deletingPlannedItemId, deletePlannedItem, descendantCategoriesFor,
    movingPlannedItemId, movePlannedItemToCategory,
    reorderingPlannedItemId, savePlannedItemSortOrder, reorderPlannedItem,
  }
}
