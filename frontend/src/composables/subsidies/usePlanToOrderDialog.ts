// «Что ещё заказать» (владелец, 04.10.2026, план .planning/quick/2026-10-04-
// sheet-ideas/PLAN.md, Волна B) — окно со списком плановых позиций субсидии,
// которые ещё не выбраны ни одной закупкой (ordered_residual > 0.5 ₽),
// сгруппированных по статусу «нужности» (need_level) и внутри — по товарам/
// услугам. Кнопка открытия — FeoTreeToolbar.vue, сам диалог —
// PlanToOrderDialog.vue. Module-level singleton — тот же приём, что у
// usePlanToRequest.ts/useFeoUndoStack.ts (Правило №6, одна точка состояния).
//
// Источник данных — GET /api/feo-categories/plan-positions (Правило №6, тот же
// эндпоинт, что и useFeoPlannedResiduals.ts/FeoTreeSelect.vue) — запрошен
// здесь напрямую (а не через useFeoPlannedResiduals), потому что та обёртка
// намеренно ГЛОТАЕТ ошибку сети (пустой список — приемлемо для пикера, но не
// для этого окна: владелец явно просил не глотать ошибку, показывать текст с
// HTTP-статусом).
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { kindOf, KIND_LABELS, KIND_GOODS, KIND_SERVICES, KIND_UNSPECIFIED, type ItemTypeKind } from '@/utils/itemTypeKind'
import { needLevelOf, NEED_LEVEL_LABELS, NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE, type NeedLevel } from '@/utils/planNeedLevel'
import type { FeoPlanKind } from '@/composables/useFeoPlannedResiduals'
// (import type — эрейзится на компиляции, никакого реального импорта модуля)

interface RawPlanPositionRow {
  id: number
  name: string
  path: string
  category_id: number
  kind: FeoPlanKind
  item_type?: string | null
  need_level?: string | null
  planned_quantity: number | null
  unit: string | null
  planned_amount: number | null
  residual: number
  residual_quantity: number
  ordered_qty?: number
  ordered_residual?: number
  // «Без договоров» (владелец, 04.10.2026) — см. докстринг не поля not_committed
  // (которое клэмпится в null у закрытой позиции, используется FeoLevel5Panel.vue
  // и сюда не годится), а not_committed_raw в backend/app/routers/feo_plan_reads_tree.py
  // (kind='planned_item' только) и not_committed (kind='plan_position'/'feo_article',
  // та же формула «план − законтрактовано» без привязки к quantity-замещению —
  // этим строкам оно не нужно отдельно, см. ту же ручку).
  not_committed?: number | null
  not_committed_raw?: number
}

export interface PlanToOrderRow {
  key: string
  id: number
  kind: FeoPlanKind
  name: string
  path: string
  categoryId: number
  itemKind: ItemTypeKind
  needLevel: NeedLevel
  unit: string | null
  /** «Без договоров» — остаток количества (план − заказано; старый остаток
   *  (residual_quantity), если формула v2 недоступна для этой строки — см.
   *  docstring модуля/GET /feo-categories/plan-positions). */
  residualQuantity: number
  /** «Без договоров» в деньгах — ИСПРАВЛЕНО 04.10.2026 (приёмка субсидии «ХО»
   *  id 75, владелец): раньше брали ordered_residual ?? residual (план минус
   *  ПОТРЕБЛЕНО закупками, любого статуса) — расходилось с карточкой «Можно
   *  перераспределить» (план минус ЗАКОНТРАКТОВАНО). Теперь: kind='planned_item'
   *  → not_committed_raw (contribution − committed, без клэмпа, см. тип
   *  RawPlanPositionRow); иначе → not_committed (null у закрытой позиции
   *  трактуется как 0 — план полностью занят договором). */
  residualAmount: number
}

export interface PlanToOrderGroup {
  needLevel: NeedLevel
  label: string
  kinds: { kind: ItemTypeKind; label: string; rows: PlanToOrderRow[]; totalAmount: number; totalQuantity: number }[]
  totalAmount: number
}

const show = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const subsidyId = ref<number | null>(null)
const subsidyName = ref<string>('')
const rawRows = ref<RawPlanPositionRow[]>([])
// «Можно перераспределить» карточки (not_committed_likely + not_committed_nice
// этой субсидии, SubsidyRow) — владелец 04.10.2026: итог окна обязан совпасть с
// карточкой (ПРАВИЛО №6, тот же источник), а не со своей Σ по строкам (строки —
// только позиции С ФЭО-категорией; заявки без плановой позиции и т.п. в них не
// попадают — разница закрывается строкой сверки, см. unlinkedAmount ниже).
const cardTotal = ref<number | null>(null)

async function load() {
  if (!subsidyId.value) return
  loading.value = true
  error.value = null
  try {
    rawRows.value = await apiFetch<RawPlanPositionRow[]>(
      `/feo-categories/plan-positions?subsidy_id=${subsidyId.value}`
    )
  } catch (e: any) {
    rawRows.value = []
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить плановые позиции', prefix: 'Ошибка загрузки' })
  } finally {
    loading.value = false
  }
}

function openPlanToOrderDialog(sId: number, sName?: string | null, cardTotalValue?: number | null) {
  subsidyId.value = sId
  subsidyName.value = sName || ''
  cardTotal.value = cardTotalValue ?? null
  show.value = true
  void load()
}

function closePlanToOrderDialog() {
  show.value = false
}

// «Без договоров» (владелец, 04.10.2026, приёмка субсидии «ХО» id 75) — ИСПРАВЛЕНО:
// раньше было ordered_residual ?? residual (план минус ПОТРЕБЛЕНО, см. формулу v2
// у FeoTreeSelect.vue) — расходилось с карточкой «Можно перераспределить» (план
// минус ЗАКОНТРАКТОВАНО). Теперь читаем ИМЕННО not_committed/not_committed_raw
// (ПРАВИЛО №6 — тот же источник, что и карточка, см. типы выше). kind='planned_item'
// → not_committed_raw (без клэмпа); иначе → not_committed (null у закрытой позиции
// = план полностью занят договором = 0 «без договоров»).
const rows = computed<PlanToOrderRow[]>(() => {
  const out: PlanToOrderRow[] = []
  for (const r of rawRows.value) {
    const residualAmount = r.kind === 'planned_item' ? (r.not_committed_raw ?? 0) : (r.not_committed ?? 0)
    if (!(residualAmount > 0.5)) continue
    const residualQuantity = r.ordered_qty != null && r.planned_quantity != null
      ? Math.max(r.planned_quantity - r.ordered_qty, 0)
      : (r.residual_quantity ?? 0)
    out.push({
      key: `${r.kind}:${r.id}`,
      id: r.id,
      kind: r.kind,
      name: r.name,
      path: r.path,
      categoryId: r.category_id,
      itemKind: kindOf(r.item_type),
      needLevel: needLevelOf(r.need_level),
      unit: r.unit,
      residualQuantity,
      residualAmount,
    })
  }
  return out
})

const KIND_ORDER: ItemTypeKind[] = [KIND_GOODS, KIND_SERVICES, KIND_UNSPECIFIED]
const NEED_LEVEL_ORDER: NeedLevel[] = [NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE]

// Группировка «нужность» → «товары/услуги/без типа» (владелец: позиции без
// need_level — в группу «Скорее всего понадобится», см. needLevelOf выше;
// KIND_LABELS — единственный источник подписи типа, @/utils/itemTypeKind.ts,
// Правило №6, тот же словарь, что и везде в проекте).
const groups = computed<PlanToOrderGroup[]>(() => {
  const byNeed = new Map<NeedLevel, PlanToOrderRow[]>()
  for (const r of rows.value) {
    const arr = byNeed.get(r.needLevel) ?? []
    arr.push(r)
    byNeed.set(r.needLevel, arr)
  }
  const out: PlanToOrderGroup[] = []
  for (const nl of NEED_LEVEL_ORDER) {
    const needRows = byNeed.get(nl)
    if (!needRows || !needRows.length) continue
    const byKind = new Map<ItemTypeKind, PlanToOrderRow[]>()
    for (const r of needRows) {
      const arr = byKind.get(r.itemKind) ?? []
      arr.push(r)
      byKind.set(r.itemKind, arr)
    }
    const kinds = KIND_ORDER
      .filter(k => byKind.has(k))
      .map(k => {
        const kRows = byKind.get(k)!
        return {
          kind: k,
          label: KIND_LABELS[k],
          rows: kRows,
          totalAmount: kRows.reduce((s, r) => s + r.residualAmount, 0),
          totalQuantity: kRows.reduce((s, r) => s + r.residualQuantity, 0),
        }
      })
    out.push({
      needLevel: nl,
      label: NEED_LEVEL_LABELS[nl],
      kinds,
      totalAmount: needRows.reduce((s, r) => s + r.residualAmount, 0),
    })
  }
  return out
})

// Σ по строкам — только позициям с собственной ФЭО-категорией/FeoPlannedItem;
// заявки без плановой позиции и прочие непривязанные суммы в них не попадают
// (см. docstring not_committed_raw/not_committed выше), поэтому это НЕ итог
// окна, а слагаемое для строки сверки ниже.
const rowsTotalAmount = computed(() => rows.value.reduce((s, r) => s + r.residualAmount, 0))

// Итог окна = итог карточки «Можно перераспределить» (not_committed_likely +
// not_committed_nice ВЫБРАННОЙ субсидии, передаётся в openPlanToOrderDialog) —
// владелец 04.10.2026: два окна одного вопроса не должны показывать разные
// числа (ПРАВИЛО №6). Если карточка недоступна (cardTotal не передан) — фолбэк
// на Σ по строкам, как было раньше.
const grandTotalAmount = computed(() => cardTotal.value ?? rowsTotalAmount.value)

// Строка сверки «не привязано к позициям» — остаток разницы между итогом
// карточки и Σ строк (заявки без плановой позиции и т.п., см. docstring
// unlinked_actual_amount в backend/app/routers/feo_plan_reads_tree.py) — это НЕ
// новая формула, а остаток сверки: сколько из итога карточки не объяснено
// списком строк окна. Показывается только когда разница заметна (>1 ₽).
const unlinkedAmount = computed(() => {
  if (cardTotal.value == null) return null
  const diff = cardTotal.value - rowsTotalAmount.value
  return Math.abs(diff) > 1 ? diff : null
})

export function usePlanToOrderDialog() {
  return {
    show, loading, error, subsidyName, rows, groups, grandTotalAmount, unlinkedAmount,
    openPlanToOrderDialog, closePlanToOrderDialog, reload: load,
  }
}
