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
import { filterFundedNodes, type FeoLeaf as FeoPickerLeaf, type FeoNode as FeoPickerNode } from '@/composables/useFeoLeaves'
import { PURCHASE_STATUS_ORDER, purchaseStatusColor, purchaseStatusLabel } from '@/constants/purchaseStatus'
import { pushFeoUndo } from './useFeoUndoStack'
import { createPlannedItemRaw } from './useFeoPlannedItemAddDialog'
import { makeCtxSingleton } from './ctxSingleton'
import type {
  DiffActual, FeoActualItem, FeoCategory, FeoNode, FeoPlannedItem, FeoStage, FeoStageRow,
} from './types'

// ── Сырые операции с плановой позицией — без диалогов/confirm/тостов ────────
// Выделены из deletePlannedItem/moveOnePlannedItem ниже специально для стека
// отмены (useFeoUndoStack.ts, задача владельца п.4, 2026-09-13): «отмена
// выполняется ОБРАТНОЙ ОПЕРАЦИЕЙ через существующие эндпоинты» — эти функции и
// есть та единственная точка входа в POST/PUT/DELETE /feo-planned-items (Правило
// №6), обычный путь (deletePlannedItem) их тоже вызывает, второго набора
// запросов нет.
export async function deletePlannedItemRaw(itemId: number): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await apiFetch(`/feo-planned-items/${itemId}`, { method: 'DELETE' })
    return { ok: true }
  } catch (e: any) {
    return { ok: false, error: e?.payload?.message || e?.detail || e?.message || 'Не удалось удалить плановую позицию' }
  }
}

export async function putPlannedItemFull(itemId: number, payload: Record<string, unknown>): Promise<{ ok: true; item: FeoPlannedItem } | { ok: false; error: string }> {
  try {
    const item = await apiFetch<FeoPlannedItem>(`/feo-planned-items/${itemId}`, { method: 'PUT', body: JSON.stringify(payload) })
    return { ok: true, item }
  } catch (e: any) {
    return { ok: false, error: e?.payload?.message || e?.detail || e?.message || 'Ошибка сохранения' }
  }
}

// Полный payload FeoPlannedItemCreate по снимку позиции. POST и PUT на бэкенде
// используют РОВНО одну и ту же pydantic-схему (update_planned_item(data:
// FeoPlannedItemCreate) — см. app/routers/feo_planned_items.py), поэтому одна
// функция годится и для пересоздания при undo(удаление)/redo(создание), и для
// полной замены при undo/redo(правка). is_feo_breakdown/is_internal_plan
// включены ЯВНО — в отличие от PUT (там непереданное поле не трогается,
// model_fields_set-guard), POST такой поблажки не имеет: не пришло — станет
// False, и «восстановленная» позиция молча потеряла бы признак разбивки ФЭО.
export function buildPlannedItemFullPayload(
  item: FeoPlannedItem,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    feo_category_id: item.feo_category_id,
    name: item.name,
    quantity: item.quantity,
    unit: item.unit,
    amount: item.amount,
    unit_price: item.unit_price ?? null,
    // Раздельные числа по ФЭО (владелец, 2026-09-14) — та же логика полного
    // снимка, что и у unit_price выше: без явной отправки undo/redo (POST при
    // пересоздании, PUT при полной замене) молча обнулили бы уже введённые
    // feo_quantity/feo_unit_price/feo_amount. См. FeoPlannedItem.feo_quantity
    // в backend/app/models/feo_planned_item.py.
    feo_quantity: item.feo_quantity ?? null,
    feo_unit_price: item.feo_unit_price ?? null,
    feo_amount: item.feo_amount ?? null,
    notes: item.notes,
    is_active: item.is_active,
    payment_mode: item.payment_mode ?? 'one_time',
    planned_date: item.planned_date ?? null,
    monthly_start_date: item.monthly_start_date ?? null,
    monthly_end_date: item.monthly_end_date ?? null,
    months_count: item.months_count ?? null,
    monthly_amount: item.monthly_amount ?? null,
    sort_order: item.sort_order ?? null,
    item_type: item.item_type ?? null,
    is_feo_breakdown: item.is_feo_breakdown ?? false,
    is_internal_plan: item.is_internal_plan ?? false,
    allow_duplicate_name: true,
    ...overrides,
  }
}

// Единственное место, которое реально шлёт PUT для смены feo_category_id
// плановой позиции (Правило №6) — одиночный перенос (movePlannedItemToCategory),
// массовый (bulkMove*) и стек отмены (undo/redo переноса, registerMoveUndo ниже)
// вызывают РОВНО эту функцию.
async function moveOnePlannedItem(item: FeoPlannedItem, targetCategoryId: number): Promise<{ ok: true } | { ok: false; error: string }> {
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
        monthly_end_date: item.monthly_end_date ?? null,
        months_count: item.months_count ?? null,
        monthly_amount: item.monthly_amount ?? null,
        sort_order: item.sort_order ?? null,
        item_type: item.item_type ?? null,
      }),
    })
    return { ok: true }
  } catch (e: any) {
    return { ok: false, error: e?.payload?.message || e?.detail || e?.message || 'Ошибка переноса' }
  }
}

export interface StageBreakdownSegment { key: string; label: string; color: string; count: number; pct: number }

// Жалоба владельца, п.15 волны 4 (2026-09-13): «в позициях плана должно быть...
// на каком этапе находится данная закупка». У одной плановой позиции может
// висеть НЕСКОЛЬКО строк закупки (несколько PurchaseItem одной и той же
// закупки, привязанных к одной плановой позиции — например, позиция разбита
// на несколько строк) — стадия у них общая (это одна и та же Purchase), считаем
// и показываем ЗАКУПКУ, а не строку, иначе бар/список задваивает одну и ту же
// закупку.
export function dedupPurchasesByPurchaseId(facts: FeoActualItem[]): FeoActualItem[] {
  const seen = new Map<number, FeoActualItem>()
  for (const a of facts) {
    if (!seen.has(a.purchase_id)) seen.set(a.purchase_id, a)
  }
  return [...seen.values()]
}

// Полоска по стадиям (свёрнутый вид новой колонки «Стадия закупки»): мера —
// КОЛИЧЕСТВО закупок на стадии, не деньги и не количество товара. Деньги
// недоступны на ранних стадиях (plan_schedule ещё не имеет fact_amount, см.
// purchase_item_fact_amount) — полоска бы молчала там, где владелец как раз
// хочет видеть «в плане-графике». Количество товара несравнимо между
// позициями с разными единицами измерения. Количество закупок — единственная
// мера, всегда доступная и однородная. Тот же приём (PURCHASE_STATUS_ORDER,
// filter+map по счётчику статусов), что useFeoReqItems.groupStatuses — там
// считаются статусы товаров виртуальной группы позиций заявок, здесь —
// закупки одной плановой позиции; второй счётчик статусов НЕ заводится,
// переиспользуется тот же канонический порядок жизненного цикла закупки.
export function buildStageBreakdown(facts: FeoActualItem[]): StageBreakdownSegment[] {
  const purchases = dedupPurchasesByPurchaseId(facts)
  const total = purchases.length
  if (!total) return []
  const counts = new Map<string, number>()
  for (const p of purchases) {
    const st = p.purchase_status || ''
    counts.set(st, (counts.get(st) || 0) + 1)
  }
  return PURCHASE_STATUS_ORDER
    .filter(key => counts.get(key))
    .map(key => ({
      key,
      label: purchaseStatusLabel(key),
      color: purchaseStatusColor(key),
      count: counts.get(key)!,
      pct: (counts.get(key)! / total) * 100,
    }))
}

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

// makeCtxSingleton (ctxSingleton.ts, Правило №6) — пересобирает API при новом
// ctx (повторный маунт SubsidiesView.vue, владелец 21.09 П2), а не держит ctx
// первого маунта навсегда.
export const useFeoLevel5 = makeCtxSingleton(
  buildFeoLevel5,
  'useFeoLevel5() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue',
)

// Точечный доступ к уже построенному синглтону — для новой массовой
// выбор/перенос-функциональности (п.12 волны 3, 2026-09-13), которую
// FeoLevel5Panel.vue вызывает напрямую, а не через SubsidyDetailContext
// (тот объект целиком собирается в SubsidiesView.vue — файл параллельного
// исполнителя этой же волны, не трогаем). SubsidiesView.vue вызывает
// useFeoLevel5(realCtx) в своём <script setup> раньше, чем монтируется любой
// дочерний компонент, поэтому к моменту вызова здесь синглтон уже собран —
// эквивалент вызова useFeoLevel5() без ctx (makeCtxSingleton отдаёт уже
// построенный API и не трогает его).
export function useFeoLevel5Api() {
  return useFeoLevel5()
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

  // ── Колонка «Стадия закупки» (владелец, п.15 волны 4, 2026-09-13) ──────────
  // Источник — тот же factForPlanned, что уже рисует нижнюю панель «План vs
  // факт»: она у ЭТОЙ плановой позиции уже загружена (comparisonData
  // подтягивается при раскрытии панели категории, ДО того как рисуется эта
  // таблица) — второй запрос к бэкенду не заводится (Правило №6), полоска и
  // список закупок — только вид данных, уже лежащих в памяти.
  function purchasesForPlanned(catId: number, plannedId: number): FeoActualItem[] {
    return dedupPurchasesByPurchaseId(factForPlanned(catId, plannedId))
  }
  function stageBreakdownFor(catId: number, plannedId: number): StageBreakdownSegment[] {
    return buildStageBreakdown(factForPlanned(catId, plannedId))
  }
  function stageBreakdownTitle(catId: number, plannedId: number): string {
    return stageBreakdownFor(catId, plannedId).map(s => `${s.label}: ${s.count}`).join(' · ')
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
    // Жалоба владельца (п.6 волны 2, 2026-09-13): «хотел удалить плановую позицию
    // „Москва“ — удалились сразу все» — на деле владелец нажал на корзину у
    // КАТЕГОРИИ (тот же значок, каскад по всему поддереву), а не у позиции: у
    // удаления ПОЗИЦИИ подтверждения не было вовсе, разница между двумя кнопками
    // визуально не считывалась. confirm() — тот же приём, что и у соседних
    // удалений в композаблах без отдельного диалога (см. useStaffDepartments.ts,
    // usePurchaseReceipts.ts, useContractsMaintenance.ts) — с названием позиции,
    // чтобы было видно, что удаляется именно она, а не категория целиком.
    if (!confirm(`Удалить плановую позицию «${item.name}»?`)) return
    deletingPlannedItemId.value = item.id
    try {
      const res = await deletePlannedItemRaw(item.id)
      if (!res.ok) throw new Error(res.error)
      await Promise.all([refreshComparison(item.feo_category_id), refreshReqData()])
      registerDeleteUndo(item)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось удалить плановую позицию', 'error')
    } finally {
      deletingPlannedItemId.value = null
    }
  }

  // Стек отмены (владелец, п.4 волны 4, 2026-09-13): «удалили позицию — отмена
  // создаёт её заново с теми же полями». Снимок — ПОЛНЫЙ payload из
  // buildPlannedItemFullPayload(item) (все поля, включая is_feo_breakdown/
  // is_internal_plan — POST их не подставит сам, в отличие от PUT). currentId —
  // id ТЕКУЩЕГО воплощения строки: сразу после удаления воплощения нет (null),
  // после undo сервер выдаёт НОВЫЙ id (это уже другая строка БД с тем же
  // содержимым) — redo обязан удалить именно его, не исходный (уже удалённый) id.
  function registerDeleteUndo(item: FeoPlannedItem) {
    let currentId: number | null = null
    const snapshot = buildPlannedItemFullPayload(item)
    const categoryId = item.feo_category_id
    pushFeoUndo({
      label: `удаление позиции «${item.name}»`,
      undo: async () => {
        try {
          const created = await createPlannedItemRaw(snapshot)
          currentId = created.id
          await Promise.all([refreshComparison(categoryId), refreshReqData()])
          return { ok: true }
        } catch (e: any) {
          return {
            ok: false,
            error: e?.payload?.message || e?.detail || e?.message
              || 'Не удалось восстановить позицию — возможно, в категории уже есть позиция с таким именем, или сервер отказал',
          }
        }
      },
      redo: async () => {
        if (currentId == null) return { ok: false, error: 'Позиция ещё не была восстановлена' }
        const res = await deletePlannedItemRaw(currentId)
        if (res.ok) await Promise.all([refreshComparison(categoryId), refreshReqData()])
        return res
      },
    })
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
      const result = await moveOnePlannedItem(item, targetCategoryId)
      if (!result.ok) throw new Error(result.error)
      await Promise.all([refreshComparison(sourceCategoryId), refreshComparison(targetCategoryId)])
      await refreshReqData()
      showSnack('Позиция перенесена')
      registerMoveUndo(item, sourceCategoryId, targetCategoryId)
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка переноса', 'error')
    } finally {
      movingPlannedItemId.value = null
    }
  }

  // Стек отмены: «перенесли — отмена переносит обратно». Снимок — сам item ДО
  // переноса (feo_category_id ещё равен fromCategoryId в момент вызова) —
  // остальные поля перенос не меняет, moveOnePlannedItem шлёт их as-is в обе
  // стороны (тот же приём, что и в обычном пути выше — Правило №6, второй
  // запрос не заводим).
  function registerMoveUndo(item: FeoPlannedItem, fromCategoryId: number, toCategoryId: number) {
    const snapshot: FeoPlannedItem = { ...item, feo_category_id: fromCategoryId }
    const fromName = feoCategories.value.find(c => c.id === fromCategoryId)?.name || `#${fromCategoryId}`
    const toName = feoCategories.value.find(c => c.id === toCategoryId)?.name || `#${toCategoryId}`
    pushFeoUndo({
      label: `перенос позиции «${item.name}» из «${fromName}» в «${toName}»`,
      undo: async () => {
        const res = await moveOnePlannedItem(snapshot, fromCategoryId)
        if (res.ok) await Promise.all([refreshComparison(fromCategoryId), refreshComparison(toCategoryId), refreshReqData()])
        return res
      },
      redo: async () => {
        const res = await moveOnePlannedItem(snapshot, toCategoryId)
        if (res.ok) await Promise.all([refreshComparison(fromCategoryId), refreshComparison(toCategoryId), refreshReqData()])
        return res
      },
    })
  }

  // ── Массовый выбор и перенос плановых позиций (владелец, п.12 волны 3,
  // 2026-09-13): «Нужен массовый выбор „Плановых позиций“... массово переносить
  // в другую папку». Выбор — глобальный Set id (id плановых позиций уникальны
  // по всей базе), т.к. это не усложняет код, а даёт бонус: выбор переживает
  // сворачивание панели категории. selectedIdsForNode/allSelectedForNode и т.д.
  // проецируют этот общий Set на видимые строки конкретного узла — тулбар и
  // «выбрать всё» в каждой раскрытой панели работают только со своими строками.
  // Ручная псевдо-строка (isManual, id<0 — см. displayPlannedRowsFor) не является
  // настоящей записью FeoPlannedItem и не может переноситься массово — исключена.
  const selectedPlannedItemIds = ref<Set<number>>(new Set())
  function isPlannedItemSelected(id: number): boolean {
    return selectedPlannedItemIds.value.has(id)
  }
  function togglePlannedItemSelected(id: number) {
    const s = new Set(selectedPlannedItemIds.value)
    if (s.has(id)) s.delete(id); else s.add(id)
    selectedPlannedItemIds.value = s
  }
  function selectableRowsFor(node: FeoNode): (FeoPlannedItem & { isManual?: boolean })[] {
    return displayPlannedRowsFor(node).filter(p => !p.isManual)
  }
  function selectedIdsForNode(node: FeoNode): number[] {
    const ids = new Set(selectableRowsFor(node).map(p => p.id))
    return [...selectedPlannedItemIds.value].filter(id => ids.has(id))
  }
  function someSelectedForNode(node: FeoNode): boolean {
    return selectedIdsForNode(node).length > 0
  }
  function allSelectedForNode(node: FeoNode): boolean {
    const rows = selectableRowsFor(node)
    return rows.length > 0 && rows.every(p => selectedPlannedItemIds.value.has(p.id))
  }
  function toggleSelectAllForNode(node: FeoNode) {
    const rows = selectableRowsFor(node)
    const selectAll = !allSelectedForNode(node)
    const s = new Set(selectedPlannedItemIds.value)
    for (const p of rows) {
      if (selectAll) s.add(p.id); else s.delete(p.id)
    }
    selectedPlannedItemIds.value = s
  }
  function clearSelectionForNode(node: FeoNode) {
    const toRemove = selectedIdsForNode(node)
    if (!toRemove.length) return
    const s = new Set(selectedPlannedItemIds.value)
    for (const id of toRemove) s.delete(id)
    selectedPlannedItemIds.value = s
  }

  // Диалог переноса — состояние общее (singleton useFeoLevel5), но
  // bulkMoveActiveNodeId помечает, КАКАЯ панель его открыла: FeoLevel5Panel.vue
  // рисует сам <v-dialog> только когда node.id совпадает с этим полем — иначе
  // при одновременно раскрытых нескольких категориях каждая панель завела бы
  // свой экземпляр диалога на общий v-model и все открылись бы разом.
  const bulkMoveDialogOpen = ref(false)
  const bulkMoveActiveNodeId = ref<number | null>(null)
  const bulkMoveItemIds = ref<number[]>([])
  const bulkMoveTargetCategoryId = ref<number | null>(null)
  const bulkMoveNodes = ref<FeoPickerNode[]>([])
  const bulkMoveLeaves = ref<FeoPickerLeaf[]>([])
  const bulkMoveLoadingTree = ref(false)
  const bulkMoveSubmitting = ref(false)
  const bulkMoveFailures = ref<{ name: string; error: string }[]>([])

  async function openBulkMoveDialog(node: FeoNode) {
    const ids = selectedIdsForNode(node)
    if (!ids.length) return
    bulkMoveActiveNodeId.value = node.id
    bulkMoveItemIds.value = ids
    bulkMoveTargetCategoryId.value = null
    bulkMoveFailures.value = []
    bulkMoveDialogOpen.value = true
    const subsId = selectedId.value
    if (!subsId) return
    bulkMoveLoadingTree.value = true
    try {
      // Полное дерево категорий субсидии, как у обычного пикера ФЭО (FeoTreeSelect —
      // переиспользуем существующий компонент выбора, второй свой не пишем).
      const [nodes, leaves] = await Promise.all([
        apiFetch<FeoPickerNode[]>(`/feo-categories/flat?subsidy_id=${subsId}`),
        apiFetch<FeoPickerLeaf[]>(`/feo-categories/leaves?subsidy_id=${subsId}`),
      ])
      bulkMoveNodes.value = filterFundedNodes(nodes)
      bulkMoveLeaves.value = leaves
    } catch {
      bulkMoveNodes.value = []
      bulkMoveLeaves.value = []
    } finally {
      bulkMoveLoadingTree.value = false
    }
  }

  function closeBulkMoveDialog() {
    bulkMoveDialogOpen.value = false
  }

  async function submitBulkMove() {
    const targetId = bulkMoveTargetCategoryId.value
    const ids = bulkMoveItemIds.value
    if (!targetId || !ids.length) return
    bulkMoveSubmitting.value = true
    bulkMoveFailures.value = []
    // Сами объекты позиций — из уже загруженного comparisonData (единственный
    // источник, тот же, что рисует таблицу), а не повторный запрос по id.
    const itemsById = new Map<number, FeoPlannedItem>()
    for (const data of Object.values(comparisonData.value)) {
      for (const p of data.planned) itemsById.set(p.id, p)
    }
    let successCount = 0
    const movedIds: number[] = []
    const touchedCategoryIds = new Set<number>([targetId])
    for (const id of ids) {
      const item = itemsById.get(id)
      if (!item) {
        bulkMoveFailures.value.push({ name: `#${id}`, error: 'Позиция не найдена — обновите список' })
        continue
      }
      if (item.feo_category_id === targetId) {
        successCount++
        movedIds.push(id)
        continue
      }
      touchedCategoryIds.add(item.feo_category_id)
      const result = await moveOnePlannedItem(item, targetId)
      if (result.ok) {
        successCount++
        movedIds.push(id)
      } else {
        bulkMoveFailures.value.push({ name: item.name, error: result.error })
      }
    }
    if (movedIds.length) {
      const s = new Set(selectedPlannedItemIds.value)
      for (const id of movedIds) s.delete(id)
      selectedPlannedItemIds.value = s
      bulkMoveItemIds.value = bulkMoveItemIds.value.filter(id => !movedIds.includes(id))
    }
    await Promise.all([...touchedCategoryIds].map(cid => refreshComparison(cid)))
    await refreshReqData()
    bulkMoveSubmitting.value = false
    if (!bulkMoveFailures.value.length) {
      showSnack(`Перенесено ${successCount} из ${ids.length}`)
      bulkMoveDialogOpen.value = false
    } else {
      showSnack(
        `Перенесено ${successCount} из ${ids.length}. Не удалось: `
        + bulkMoveFailures.value.map(f => `«${f.name}» — ${f.error}`).join('; '),
        'error',
      )
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
        // Волна 3, п.3 (владелец, период "с даты по дату") — тот же приём, что и в
        // moveOnePlannedItem выше: PUT здесь ПОЛНАЯ замена, без явной передачи
        // уже сохранённый конец периода молча обнулился бы при каждой перестановке
        // сортировки (см. FeoPlannedItem.monthly_end_date).
        monthly_end_date: item.monthly_end_date ?? null,
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
    purchasesForPlanned, stageBreakdownFor, stageBreakdownTitle,
    purchaseLabelFor, factExcessReasonItems, factExcessReasonRemainder,
    stageHeaderLabelFor, stageChipLabelFor, stageChipTitleFor, stageChipColorFor, factStageHeaderFor,
    planBreakdownText, displayPlannedRowsFor, unplannedActualFor, isOrphanedActual,
    comparisonPlanTotal, comparisonFactTotal, plannedItemIndentPx,
    DIFF_COMMITTED_STATUSES, calcDiff, getDiffStyle, stagesWithDiff,
    deletingPlannedItemId, deletePlannedItem, descendantCategoriesFor,
    movingPlannedItemId, movePlannedItemToCategory,
    reorderingPlannedItemId, savePlannedItemSortOrder, reorderPlannedItem,
    // Массовый выбор/перенос (п.12 волны 3)
    selectedPlannedItemIds, isPlannedItemSelected, togglePlannedItemSelected, selectableRowsFor,
    selectedIdsForNode, someSelectedForNode, allSelectedForNode, toggleSelectAllForNode, clearSelectionForNode,
    bulkMoveDialogOpen, bulkMoveActiveNodeId, bulkMoveItemIds, bulkMoveTargetCategoryId,
    bulkMoveNodes, bulkMoveLeaves, bulkMoveLoadingTree, bulkMoveSubmitting, bulkMoveFailures,
    openBulkMoveDialog, closeBulkMoveDialog, submitBulkMove,
  }
}
