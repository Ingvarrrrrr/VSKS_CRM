// «Создать закупку на основе плана» (владелец, лист 2, п.7) — режим выбора
// плановых позиций дерева ФЭО (кнопка в FeoTreeToolbar.vue) → полноэкранный
// диалог подбора товара → создаётся ЗАЯВКА (не закупка), см. докстринг
// PlanToRequestDialog.vue. Module-level singleton — тот же приём, что и в
// useFeoUndoStack.ts/useFeoLevel5.ts (Правило №6): один источник состояния
// режима выбора для FeoTreeToolbar.vue (кнопка) и FeoTreeTable.vue (подсветка).
//
// Выбор плановых позиций — НЕ отдельный Set: переиспользуем ТОТ ЖЕ
// selectedPlannedItemIds из useFeoLevel5Api() (уже существовал для массового
// переноса категорий), галочки в FeoLevel5Panel.vue уже на него завязаны —
// второй набор чекбоксов не заводим (Правило №6, факт из задания).
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'
import { useFeoPlannedResiduals, type FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import { useFeoLevel5Api } from './useFeoLevel5'
import { materializeManualPlanAsItem } from './useFeoManualPlanMaterialize'
import { collectSubtreeIds } from './feoCategoryUtils'
import type { FeoCategory, FeoNode } from './types'

export interface PlanToWishLinkedPurchase {
  purchase_id: number
  purchase_number: number | string | null
  registry_number: string | null
  status: string | null
  status_label: string | null
  quantity: number | null
  initiator_user_id: number | null
  initiator_name: string | null
}

export interface PriceFreshnessDto {
  is_stale: boolean
  age_days: number | null
  ttl_days: number | null
  reason: string | null
  label: string | null
}

export interface PlanToWishCandidate {
  product_id: number
  name: string
  price: number | null
  score: number
  photo_url: string | null
  item_type: string | null
  category: string | null
  product_type: string | null
  unit: string | null
  price_updated_at: string | null
  price_source: string | null
  price_freshness: PriceFreshnessDto | null
}

export interface PlanToWishCandidateItem {
  planned_item_id: number
  name: string
  unit: string | null
  feo_category_id: number
  feo_category_name: string | null
  plan_quantity: number | null
  plan_unit_price: number | null
  plan_amount: number | null
  used_quantity: number
  residual_quantity: number | null
  residual_amount: number | null
  linked_purchases: PlanToWishLinkedPurchase[]
  exact: PlanToWishCandidate | null
  by_name: PlanToWishCandidate[]
  by_type: PlanToWishCandidate[]
}

export type PriceSource = 'catalog' | 'plan'

// Строка диалога подбора — кандидат из бэкенда + редактируемое состояние
// (количество/выбранный товар/цена). reactive — удобнее точечных ref-ов, поля
// правятся напрямую из PlanToRequestRow.vue через v-model.
export interface PlanToRequestRow {
  plannedItemId: number
  name: string
  unit: string | null
  feoCategoryId: number
  feoCategoryName: string
  planQuantity: number | null
  planUnitPrice: number | null
  planAmount: number | null
  usedQuantity: number
  residualQuantity: number | null
  residualAmount: number | null
  linkedPurchases: PlanToWishLinkedPurchase[]
  exact: PlanToWishCandidate | null
  byName: PlanToWishCandidate[]
  byType: PlanToWishCandidate[]
  // ── редактируемое состояние строки ──
  quantity: number
  selectedCandidate: PlanToWishCandidate | null
  productChosen: boolean // false = «ещё не выбрано» (плейсхолдер), true = осознанный выбор (включая «без товара»)
  priceSourceOverride: PriceSource | null // null = берёт общий переключатель
  unitPrice: number
  creatingTask: boolean
}

function emptyRowFrom(c: PlanToWishCandidateItem): PlanToRequestRow {
  const qty = c.residual_quantity != null ? c.residual_quantity : (c.plan_quantity ?? 0)
  const row: PlanToRequestRow = {
    plannedItemId: c.planned_item_id,
    name: c.name,
    unit: c.unit,
    feoCategoryId: c.feo_category_id,
    feoCategoryName: c.feo_category_name || '—',
    planQuantity: c.plan_quantity,
    planUnitPrice: c.plan_unit_price,
    planAmount: c.plan_amount,
    usedQuantity: c.used_quantity,
    residualQuantity: c.residual_quantity,
    residualAmount: c.residual_amount,
    linkedPurchases: c.linked_purchases || [],
    exact: c.exact,
    byName: c.by_name || [],
    byType: c.by_type || [],
    quantity: qty > 0 ? qty : 1,
    selectedCandidate: c.exact || null,
    productChosen: !!c.exact,
    priceSourceOverride: null,
    unitPrice: 0,
    creatingTask: false,
  }
  return row
}

// ── Module-level singleton ────────────────────────────────────────────────
const active = ref(false)
const dialogOpen = ref(false)
const loadingCandidates = ref(false)
const submitting = ref(false)
const title = ref('')
const globalPriceSource = ref<PriceSource>('catalog')
const rows = ref<PlanToRequestRow[]>([])
const currentSubsidyId = ref<number | null>(null)
// Прогресс материализации ручных планов категорий (перед сбором planned_item_ids)
// и пачечной загрузки кандидатов (>50 строк) — читает PlanToRequestDialog.vue,
// см. openConfirmDialog ниже.
const materializingManualPlans = ref(false)
const candidatesProgress = ref<{ done: number; total: number } | null>(null)

// Остатки плановых позиций субсидии — единственный источник для «выбрать
// категорию/смету целиком» (владелец, задача 1): переиспользуем
// useFeoPlannedResiduals (composables/useFeoPlannedResiduals.ts, GET
// /feo-categories/plan-positions) — тот же композабл, что уже используют
// диалоги привязки позиций к заявке/закупке (Правило №6, второй источник
// остатков не заводим). Module-level singleton (как и остальное состояние
// этого файла) — watcher должен жить один раз, не пересоздаваться при каждом
// вызове usePlanToRequest() (он вызывается из нескольких компонентов —
// FeoTreeToolbar.vue, FeoTreeRow.vue на каждую строку дерева).
const residualsSubsidyId = ref<number | null>(null)
const feoResiduals = useFeoPlannedResiduals({ subsidyId: residualsSubsidyId })

// ⚠️ Поля запроса задания ссылались на устаревший эндпоинт
// /feo-planned-items/residuals (feo_item_id/quantity) — он заменён на
// /feo-categories/plan-positions (см. докстринг FeoPlanPosition), тут
// используются его актуальные поля: `id`+`kind` вместо `feo_item_id`,
// `planned_quantity` вместо `quantity`. Решение владельца — только остаток
// количества > 0, позиции без количества (planned_quantity == null) пропускаются.
//
// id-пространство совпадает с selectedPlannedItemIds (переиспользуем ТОТ ЖЕ
// Set, см. докстринг файла выше): для kind='planned_item' — это уже id
// настоящей FeoPlannedItem (то же число, что чекбоксы FeoLevel5Panel.vue); для
// kind='plan_position'/'feo_article' (ручной план задан прямо на категории,
// без отдельных FeoPlannedItem) — синтетический id = −category_id, тот же
// приём, что и displayPlannedRowsFor в useFeoLevel5.ts (задача 2 — такие id
// материализуются в настоящие FeoPlannedItem перед отправкой на сервер).
function eligibleResidualIds(rows: FeoPlanPosition[]): number[] {
  const ids: number[] = []
  for (const r of rows) {
    if (r.planned_quantity == null) continue
    if (!(Number(r.residual_quantity) > 0)) continue
    ids.push(r.kind === 'planned_item' ? r.id : -r.category_id)
  }
  return ids
}

function computeSelectionState(ids: number[], selected: Set<number>): { all: boolean; some: boolean } {
  if (!ids.length) return { all: false, some: false }
  const selectedCount = ids.filter(id => selected.has(id)).length
  return { all: selectedCount === ids.length, some: selectedCount > 0 }
}

export function usePlanToRequest() {
  const router = useRouter()
  const toast = useToast()
  const feoLevel5 = useFeoLevel5Api()

  function showSnack(text: string, color: 'success' | 'error' | 'info' | 'warning' = 'success') {
    // useToast.addToast по умолчанию duration=0 — тост не исчезает сам, пока
    // не закрыт (обязательно для ошибок, память feedback_no_generic_error_snackbar).
    toast.addToast(text, color)
  }

  const selectedCount = computed(() => feoLevel5.selectedPlannedItemIds.value.size)
  const residualsLoading = computed(() => feoResiduals.plannedLoading.value)

  // Остатки грузятся один раз при входе в режим (владелец, задача 1) — если
  // субсидия та же, что и в прошлый раз, watch внутри useFeoPlannedResiduals не
  // перезапустится сам (subsidyId не изменился), поэтому перезапрашиваем явно.
  function startSelectMode(subsidyId: number) {
    active.value = true
    feoLevel5.selectedPlannedItemIds.value = new Set()
    if (residualsSubsidyId.value === subsidyId) {
      void feoResiduals.reloadPlanned()
    } else {
      residualsSubsidyId.value = subsidyId
    }
  }

  function cancelSelectMode() {
    active.value = false
    feoLevel5.selectedPlannedItemIds.value = new Set()
    dialogOpen.value = false
    rows.value = []
    // «Обновлять после подтверждения/отмены» (задача 1) — submitCreate тоже
    // зовёт cancelSelectMode() на успехе, второй вызов reloadPlanned не заводим.
    void feoResiduals.reloadPlanned()
  }

  // ── Выбор категории/сметы целиком (владелец, задача 1) ──────────────────
  function applySelection(ids: number[], on: boolean) {
    if (!ids.length) return
    const s = new Set(feoLevel5.selectedPlannedItemIds.value)
    for (const id of ids) { if (on) s.add(id); else s.delete(id) }
    feoLevel5.selectedPlannedItemIds.value = s
  }

  // ids поддерева — collectSubtreeIds(feoCategories, node.id) (включает сам
  // node), как в остальных местах проекта (Правило №6) — второй обход дерева
  // не пишем. feoCategories передаётся вызывающим компонентом (FeoTreeRow.vue
  // уже читает ctx.feoCategories.value) — этот файл сознательно не завязан на
  // SubsidyDetailContext целиком (тот же стиль, что и остальные функции здесь).
  function selectCategorySubtree(node: FeoNode, feoCategories: FeoCategory[], on: boolean) {
    const subtreeIds = new Set(collectSubtreeIds(feoCategories, node.id))
    const rowsInSubtree = feoResiduals.plannedResiduals.value.filter(r => subtreeIds.has(r.category_id))
    applySelection(eligibleResidualIds(rowsInSubtree), on)
  }

  function selectWholeSmeta(on: boolean) {
    applySelection(eligibleResidualIds(feoResiduals.plannedResiduals.value), on)
  }

  // Состояние чекбокса категории (задача 1): выбраны ВСЕ плановые позиции
  // поддерева с остатком количества > 0 → отмечен; выбрана часть →
  // indeterminate; нет ни одной подходящей позиции в поддереве → снят и
  // некликабелен по сути (клик просто ничего не выберет).
  function subtreeSelectionState(node: FeoNode, feoCategories: FeoCategory[]): { all: boolean; some: boolean } {
    const subtreeIds = new Set(collectSubtreeIds(feoCategories, node.id))
    const rowsInSubtree = feoResiduals.plannedResiduals.value.filter(r => subtreeIds.has(r.category_id))
    return computeSelectionState(eligibleResidualIds(rowsInSubtree), feoLevel5.selectedPlannedItemIds.value)
  }

  const wholeSmetaSelection = computed(() =>
    computeSelectionState(eligibleResidualIds(feoResiduals.plannedResiduals.value), feoLevel5.selectedPlannedItemIds.value),
  )

  function effectiveSourceFor(row: PlanToRequestRow): PriceSource {
    if (!row.selectedCandidate) return 'plan'
    return row.priceSourceOverride ?? globalPriceSource.value
  }

  function recomputeRowPrice(row: PlanToRequestRow) {
    const src = effectiveSourceFor(row)
    if (src === 'catalog' && row.selectedCandidate?.price != null) {
      row.unitPrice = Number(row.selectedCandidate.price)
    } else {
      row.unitPrice = row.planUnitPrice != null ? Number(row.planUnitPrice) : 0
    }
  }

  function setGlobalPriceSource(src: PriceSource) {
    globalPriceSource.value = src
    for (const row of rows.value) {
      if (row.priceSourceOverride == null) recomputeRowPrice(row)
    }
  }

  function setRowPriceSourceOverride(row: PlanToRequestRow, src: PriceSource | null) {
    row.priceSourceOverride = src
    recomputeRowPrice(row)
  }

  function pickCandidateForRow(row: PlanToRequestRow, cand: PlanToWishCandidate | null) {
    row.selectedCandidate = cand
    row.productChosen = true
    if (!cand) row.priceSourceOverride = 'plan'
    recomputeRowPrice(row)
  }

  // Ручные планы категорий (id < 0, см. selectCategorySubtree/selectWholeSmeta)
  // не существуют как записи FeoPlannedItem — POST plan-to-wish/candidates
  // умеет работать только с настоящими planned_item_id. Материализуем их ЧЕРЕЗ
  // ТУ ЖЕ логику, что и диалог «Завести плановую позицию»
  // (materializeManualPlanAsItem, useFeoPlannedItemAddDialog.ts, Правило №6 —
  // второй POST/PUT не заводим), заменяем отрицательные id на новые
  // положительные прямо в общем Set выбора и обновляем панель категории.
  async function materializeSelectedManualPlans(feoCategories: FeoCategory[]) {
    const negativeIds = [...feoLevel5.selectedPlannedItemIds.value].filter(id => id < 0)
    if (!negativeIds.length) return
    materializingManualPlans.value = true
    const s = new Set(feoLevel5.selectedPlannedItemIds.value)
    const touchedCategoryIds = new Set<number>()
    try {
      for (const negId of negativeIds) {
        const categoryId = -negId
        const cat = feoCategories.find(c => c.id === categoryId)
        s.delete(negId)
        if (!cat) continue
        try {
          const newId = await materializeManualPlanAsItem(cat)
          s.add(newId)
          touchedCategoryIds.add(categoryId)
        } catch (e: any) {
          showSnack(describeApiError(e, { fallback: `Не удалось создать плановую позицию для «${cat.name}»`, prefix: 'Ошибка' }), 'error')
        }
      }
      feoLevel5.selectedPlannedItemIds.value = s
      if (touchedCategoryIds.size) {
        await Promise.all([...touchedCategoryIds].map(id => feoLevel5.refreshComparison(id)))
      }
    } finally {
      materializingManualPlans.value = false
    }
  }

  // Пачки по 50 (владелец, задача 1) — строки появляются по мере готовности,
  // candidatesProgress читает PlanToRequestDialog.vue для v-progress-linear.
  async function loadCandidatesBatched(ids: number[]) {
    const BATCH_SIZE = 50
    if (ids.length <= BATCH_SIZE) {
      loadingCandidates.value = true
      const resp = await apiFetch<{ items: PlanToWishCandidateItem[] }>('/feo-planned-items/plan-to-wish/candidates', {
        method: 'POST',
        body: JSON.stringify({ planned_item_ids: ids, limit: 6 }),
      })
      rows.value = (resp.items || []).map(emptyRowFrom)
      for (const row of rows.value) recomputeRowPrice(row)
      loadingCandidates.value = false
      return
    }
    candidatesProgress.value = { done: 0, total: ids.length }
    for (let i = 0; i < ids.length; i += BATCH_SIZE) {
      const chunk = ids.slice(i, i + BATCH_SIZE)
      try {
        const resp = await apiFetch<{ items: PlanToWishCandidateItem[] }>('/feo-planned-items/plan-to-wish/candidates', {
          method: 'POST',
          body: JSON.stringify({ planned_item_ids: chunk, limit: 6 }),
        })
        const newRows = (resp.items || []).map(emptyRowFrom)
        for (const row of newRows) recomputeRowPrice(row)
        rows.value = [...rows.value, ...newRows]
      } catch (e: any) {
        showSnack(describeApiError(e, {
          fallback: `Не удалось загрузить часть кандидатов (${i + 1}–${Math.min(i + BATCH_SIZE, ids.length)})`,
          prefix: 'Ошибка',
        }), 'error')
      }
      candidatesProgress.value = { done: Math.min(i + BATCH_SIZE, ids.length), total: ids.length }
    }
    candidatesProgress.value = null
  }

  async function openConfirmDialog(subsidyId: number, feoCategories: FeoCategory[], reloadTree?: () => Promise<void>) {
    if (selectedCount.value === 0) return
    currentSubsidyId.value = subsidyId
    title.value = ''
    globalPriceSource.value = 'catalog'
    rows.value = []
    candidatesProgress.value = null
    dialogOpen.value = true
    try {
      await materializeSelectedManualPlans(feoCategories)
      const ids = [...feoLevel5.selectedPlannedItemIds.value]
      if (!ids.length) {
        dialogOpen.value = false
        return
      }
      await loadCandidatesBatched(ids)
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось загрузить кандидатов для заявки', prefix: 'Ошибка' }), 'error')
      dialogOpen.value = false
    } finally {
      loadingCandidates.value = false
      materializingManualPlans.value = false
      candidatesProgress.value = null
      if (reloadTree) await reloadTree()
    }
  }

  function closeDialog() {
    // Диалог закрывается, но режим выбора и галочки остаются — пользователь
    // может доправить состав на дереве и открыть подбор снова (см. докстринг
    // задачи в usePlanToRequest.ts).
    dialogOpen.value = false
  }

  const totalRowsCount = computed(() => rows.value.length)
  const totalAmount = computed(() => rows.value.reduce((s, r) => s + (Number(r.unitPrice) || 0) * (Number(r.quantity) || 0), 0))

  async function writeToInitiator(row: PlanToRequestRow) {
    const target = row.linkedPurchases[0]
    if (!target || target.initiator_user_id == null) {
      showSnack('У связанных закупок не определён инициатор', 'error')
      return
    }
    row.creatingTask = true
    try {
      const usedTxt = `${row.usedQuantity}${row.unit ? ' ' + row.unit : ''}`
      const planTxt = row.planQuantity != null ? `${row.planQuantity}${row.unit ? ' ' + row.unit : ''}` : '—'
      const purchaseTxt = target.registry_number || (target.purchase_number != null ? `№ ${target.purchase_number}` : `#${target.purchase_id}`)
      const body = {
        title: `Уточнить потребность: ${row.name}`,
        description: `Запланировано: ${planTxt}. Уже в закупках: ${usedTxt} (${purchaseTxt}, инициатор ${target.initiator_name || '—'}). `
          + `Новая заявка запрашивает ${row.quantity}${row.unit ? ' ' + row.unit : ''} — сверх остатка плана. Свяжитесь с инициатором для уточнения потребности.`,
        priority: 'medium',
        assignee_ids: [target.initiator_user_id],
        purchase_id: target.purchase_id,
      }
      await apiFetch('/tasks/', { method: 'POST', body: JSON.stringify(body) })
      showSnack('Задача инициатору создана')
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось создать задачу', prefix: 'Ошибка' }), 'error')
    } finally {
      row.creatingTask = false
    }
  }

  async function submitCreate() {
    if (!currentSubsidyId.value || rows.value.length === 0) return
    submitting.value = true
    try {
      const payload = {
        subsidy_id: currentSubsidyId.value,
        title: title.value.trim() || null,
        items: rows.value.map(r => ({
          feo_planned_item_id: r.plannedItemId,
          quantity: r.quantity,
          product_id: r.selectedCandidate ? r.selectedCandidate.product_id : null,
          item_name: r.selectedCandidate ? null : r.name,
          unit_price: r.unitPrice,
          price_source: effectiveSourceFor(r),
        })),
      }
      const resp = await apiFetch<{ wish_id: number; title: string; items_count: number; warnings: string[] }>(
        '/feo-planned-items/plan-to-wish/create',
        { method: 'POST', body: JSON.stringify(payload) },
      )
      if (resp.warnings && resp.warnings.length) {
        showSnack(`Заявка «${resp.title}» создана (${resp.items_count} поз.). ${resp.warnings.join(' ')}`, 'warning')
      } else {
        showSnack(`Заявка «${resp.title}» создана (${resp.items_count} поз.)`)
      }
      cancelSelectMode()
      await router.push(`/wishes?open=${resp.wish_id}`)
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось создать заявку', prefix: 'Ошибка' }), 'error')
    } finally {
      submitting.value = false
    }
  }

  return {
    active, dialogOpen, loadingCandidates, submitting,
    title, globalPriceSource, rows, selectedCount,
    totalRowsCount, totalAmount,
    startSelectMode, cancelSelectMode, openConfirmDialog, closeDialog,
    setGlobalPriceSource, setRowPriceSourceOverride, pickCandidateForRow,
    effectiveSourceFor, recomputeRowPrice, writeToInitiator, submitCreate,
    // Выбор категории/сметы целиком + материализация ручных планов (задачи 1 и 2)
    residualsLoading, selectCategorySubtree, selectWholeSmeta,
    subtreeSelectionState, wholeSmetaSelection,
    materializingManualPlans, candidatesProgress,
  }
}
