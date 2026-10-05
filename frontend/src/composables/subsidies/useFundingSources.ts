// «Где взять деньги» (план .planning/quick/2026-10-05-funding-sources/PLAN.md,
// владелец 05.10.2026) — окно подсказывает, с какой плановой позиции/категории
// без договоров можно перенести деньги, чтобы закрыть превышение плана по
// категории ФЭО или по плановой позиции. Контракт целиком на бэкенде (список
// источников, суммы, порядок групп по «нужности») — фронт только отображает и
// шлёт выбранную сумму в reduce (ПРАВИЛО №6, вторую сортировку/формулу не
// заводим).
//
// Module-level singleton (как usePlanToOrderDialog.ts/useFeoUndoStack.ts) —
// окно открывается из НЕСКОЛЬКИХ несвязанных деревьев компонентов (дерево ФЭО
// на вкладке «Субсидии», панель подтверждений оплаты, форма закупки при 409,
// карточка «Можно перераспределить»), поэтому состояние не может жить в ctx
// одной страницы. Сам диалог смонтирован один раз глобально в App.vue (как
// <toast-container/>), как и у ApiErrorDialog.
import { computed, reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { useToast } from '@/composables/useToast'

export type FundingTargetKind = 'category' | 'planned_item' | 'subsidy'
export type FundingScopeKind = 'branch' | 'subsidy'
export type FundingNeedLevel = 'nice_to_have' | 'likely'

export interface FundingSourceItem {
  planned_item_id: number
  name: string
  category_id: number
  category_path: string
  need_level: FundingNeedLevel
  residual: number
  suggested_take: number
  cumulative_after: number
  same_branch: boolean
}

export interface FundingSourceGroup {
  need_level: FundingNeedLevel
  label: string
  items: FundingSourceItem[]
}

export interface FundingSourcesResponse {
  target: { kind: FundingTargetKind; id: number; name: string; path: string; excess_amount: number }
  scope: { kind: FundingScopeKind; category_id: number | null; name: string }
  need_amount: number
  covered_amount: number
  groups: FundingSourceGroup[]
}

export interface FundingHint {
  planned_item_id: number | null
  category_id: number | null
  amount: number
}

interface OpenParams {
  subsidyId: number
  categoryId?: number | null
  plannedItemId?: number | null
  amount?: number | null
}

const show = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const data = ref<FundingSourcesResponse | null>(null)
const params = ref<OpenParams | null>(null)
// Сумма, которую пользователь задал для переноса по каждой строке (по
// planned_item_id) — по умолчанию suggested_take, редактируется в диалоге,
// не больше residual (clamp в диалоге, не здесь — Правило №6 про одно место
// валидации избыточно для простого min()).
const rowAmounts = reactive<Record<number, number>>({})
// id строки (planned_item_id), для которой сейчас идёт POST reduce.
const actingId = ref<number | null>(null)

const toast = useToast()

function buildQuery(p: OpenParams): string {
  const qs = new URLSearchParams()
  if (p.categoryId != null) qs.set('category_id', String(p.categoryId))
  if (p.plannedItemId != null) qs.set('planned_item_id', String(p.plannedItemId))
  if (p.amount != null) qs.set('amount', String(p.amount))
  return qs.toString()
}

async function load() {
  if (!params.value) return
  loading.value = true
  error.value = null
  try {
    const qs = buildQuery(params.value)
    data.value = await apiFetch<FundingSourcesResponse>(
      `/subsidies/${params.value.subsidyId}/funding-sources${qs ? `?${qs}` : ''}`
    )
    for (const g of data.value.groups) {
      for (const it of g.items) {
        if (!(it.planned_item_id in rowAmounts)) {
          rowAmounts[it.planned_item_id] = Math.min(it.suggested_take, it.residual)
        }
      }
    }
  } catch (e: any) {
    data.value = null
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить источники финансирования' })
  } finally {
    loading.value = false
  }
}

/** Открыть окно «Где взять деньги» — либо по категории (branch-уровень), либо
 *  по конкретной плановой позиции (planned_item). amount — сумма превышения,
 *  которую нужно закрыть, если вызывающий код её уже знает (чип дерева); если
 *  нет — backend сам возьмёт own excess_amount цели. */
function openFundingSources(p: OpenParams) {
  params.value = p
  data.value = null
  error.value = null
  for (const k of Object.keys(rowAmounts)) delete rowAmounts[Number(k)]
  show.value = true
  void load()
}

function closeFundingSources() {
  show.value = false
}

function setRowAmount(plannedItemId: number, value: number) {
  rowAmounts[plannedItemId] = value
}

/** POST /feo-planned-items/{id}/reduce — перенести сумму со строки-источника в
 *  цель окна (target.kind определяет, какой из target_category_id/
 *  target_planned_item_id передать — Правило №6, один вызов на оба случая). */
async function reduceFrom(item: FundingSourceItem) {
  if (!data.value || !params.value) return
  const amount = Number(rowAmounts[item.planned_item_id] ?? 0)
  if (!(amount > 0)) {
    toast.addToast('Укажите сумму больше нуля', 'warning')
    return
  }
  if (amount - item.residual > 0.5) {
    toast.addToast('Сумма больше, чем не законтрактовано по этой позиции', 'warning')
    return
  }
  actingId.value = item.planned_item_id
  try {
    const target = data.value.target
    const body: Record<string, unknown> = { amount, comment: null }
    if (target.kind === 'planned_item') body.target_planned_item_id = target.id
    else if (target.kind === 'category') body.target_category_id = target.id
    // target.kind === 'subsidy' — превышение уровня субсидии целиком: бэкенд
    // различает «цель — субсидия» и «без цели» только по этому флагу.
    else if (target.kind === 'subsidy') body.target_subsidy = true
    const res = await apiFetch<{
      ok: boolean; reduced_by: number
      item: { id: number; amount: number; residual: number }
      target_remaining_excess: number
      warnings: string[]
    }>(`/feo-planned-items/${item.planned_item_id}/reduce`, { method: 'POST', body })
    for (const w of res.warnings || []) toast.addToast(w, 'warning')
    if (res.target_remaining_excess > 0.5) {
      toast.addToast(`Перенесено ${formatMoney(res.reduced_by)} ₽. Осталось закрыть ${formatMoney(res.target_remaining_excess)} ₽`, 'success')
    } else {
      toast.addToast('Превышение закрыто', 'success')
    }
    await load()
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось перенести сумму' }), 'error')
  } finally {
    actingId.value = null
  }
}

function formatMoney(n: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n)
}

/** GET /purchases/{id}/funding-hint — используется местами, где нет готового
 *  category_id/planned_item_id под рукой (банковский подтверждение оплаты,
 *  отказ 409 «ТЗ/договор над плановой позицией» при сохранении закупки). */
async function fetchFundingHint(purchaseId: number): Promise<FundingHint | null> {
  try {
    return await apiFetch<FundingHint | null>(`/purchases/${purchaseId}/funding-hint`)
  } catch {
    return null
  }
}

/** Открыть окно по уже известной подсказке (hint) — не делает сетевой запрос,
 *  используется там, где planned_item_id/category_id/amount уже под рукой:
 *  заголовок ответа X-Funding-Hint на 409 «ТЗ/договор над плановой позицией»
 *  (api.ts::err.fundingHint, доступен и для ещё НЕ сохранённой закупки при
 *  создании — обычный GET /purchases/{id}/funding-hint ей недоступен, id ещё
 *  нет) и результат fetchFundingHint ниже (Правило №6, одна точка открытия). */
function openFundingSourcesFromHint(subsidyId: number, hint: FundingHint) {
  if (hint.planned_item_id == null && hint.category_id == null) {
    toast.addToast('Не удалось определить плановую позицию закупки для подбора источников', 'warning')
    return
  }
  openFundingSources({
    subsidyId,
    categoryId: hint.planned_item_id == null ? hint.category_id : null,
    plannedItemId: hint.planned_item_id,
    amount: hint.amount,
  })
}

/** Открыть окно по закупке: сперва funding-hint, потом сам диалог — общий
 *  путь для PaidConfirmationsPanel.vue и обработчика 409 в CreateOrderView.vue
 *  (Правило №6, вторую последовательность запросов не заводим). */
async function openFundingSourcesForPurchase(subsidyId: number, purchaseId: number) {
  const hint = await fetchFundingHint(purchaseId)
  if (!hint) {
    toast.addToast('Не удалось определить плановую позицию закупки для подбора источников', 'warning')
    return
  }
  openFundingSourcesFromHint(subsidyId, hint)
}

const progressPct = computed(() => {
  if (!data.value || !data.value.need_amount) return 0
  return Math.min(100, Math.round((data.value.covered_amount / data.value.need_amount) * 100))
})

export function useFundingSources() {
  return {
    show, loading, error, data, rowAmounts, actingId, progressPct,
    openFundingSources, openFundingSourcesForPurchase, openFundingSourcesFromHint, closeFundingSources,
    setRowAmount, reduceFrom, fetchFundingHint,
  }
}
