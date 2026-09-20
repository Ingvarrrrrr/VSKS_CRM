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
import { useFeoLevel5Api } from './useFeoLevel5'

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

  function startSelectMode() {
    active.value = true
    feoLevel5.selectedPlannedItemIds.value = new Set()
  }

  function cancelSelectMode() {
    active.value = false
    feoLevel5.selectedPlannedItemIds.value = new Set()
    dialogOpen.value = false
    rows.value = []
  }

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

  async function openConfirmDialog(subsidyId: number) {
    if (selectedCount.value === 0) return
    currentSubsidyId.value = subsidyId
    title.value = ''
    globalPriceSource.value = 'catalog'
    loadingCandidates.value = true
    dialogOpen.value = true
    try {
      const resp = await apiFetch<{ items: PlanToWishCandidateItem[] }>('/feo-planned-items/plan-to-wish/candidates', {
        method: 'POST',
        body: JSON.stringify({ planned_item_ids: [...feoLevel5.selectedPlannedItemIds.value], limit: 6 }),
      })
      rows.value = (resp.items || []).map(emptyRowFrom)
      for (const row of rows.value) recomputeRowPrice(row)
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось загрузить кандидатов для заявки', prefix: 'Ошибка' }), 'error')
      dialogOpen.value = false
    } finally {
      loadingCandidates.value = false
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
  }
}
