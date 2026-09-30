// useFeoPlannedBulkMatch — кнопка «Привязать к плану» (владелец, 2026-09-16,
// дефект 2): «в закупке и заявке была возможность привязать ВСЕ позиции к
// имеющимся плановым одной кнопкой: предлагались подходящие, ты либо соглашался,
// либо нет; при 100% совпадении подставлялось автоматически».
//
// Отличие от уже существующей общей кнопки «Создать в плане закупок»
// (useItemsBulkFeo.ts::runCreatePlannedBulk) — та ВСЕГДА заводит НОВУЮ плановую
// позицию для каждой непривязанной строки; эта — сначала ищет среди УЖЕ
// существующих плановых позиций всей субсидии (тот же движок, что и остальной
// матчинг проекта — POST /feo-planned-items/match, Правило №6, второй матчер не
// заводим) и предлагает привязку с чекбоксами, а не создание.
//
// Общий для закупки и заявки (владелец, требование C): PurchaseItemsEditor.vue —
// ЕДИНЫЙ компонент для обеих форм (itemShape='purchase'|'wish', см. WishFormDialog.vue/
// CreateOrderView.vue) — вызывая этот композабл и FeoPlannedBulkMatchDialog.vue
// отсюда один раз, получаем одинаковое поведение в обеих формах без второй копии.
import { computed, ref, type Ref } from 'vue'
import { useFeoPlanMatching } from '@/composables/useFeoPlanMatching'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { ToastType } from '@/composables/useToast'
import { PLAN_MATCH_SCORE_EXACT, PLAN_MATCH_SCORE_SUGGEST } from '@/constants/planMatchThresholds'
import { checkPlanOccupancy } from '@/composables/items/feoPlanned/feoPlanOccupancy'

type EditorItem = any

export interface BulkMatchRow {
  idx: number
  uid: string | number
  name: string
  quantity: number | null
  unit: string
  amount: number | null
  /** Товар/услуга/работа позиции закупки/заявки (it.item_type). Тип плановой
   *  позиции — candidate.itemType (из GET /feo-categories/plan-positions). */
  itemType: string | null
  /** Лучший кандидат — id/kind плановой позиции (или конечной категории с планом,
   *  если своей FeoPlannedItem нет), путь, остаток; null — похожих не нашлось. */
  candidate: {
    kind: 'plan_position' | 'feo_article' | 'planned_item'
    id: number
    name: string
    path: string
    score: number
    residual: number | null
    plannedAmount: number | null
    /** Тип плановой позиции; null у категории-плана целиком (своего типа нет). */
    itemType: string | null
  } | null
  isExact: boolean
  /** Владелец (30.09.2026): «Доставка» из чека была отмечена «точное совпадение»
   *  и привязана к плановой позиции, которую уже израсходовала ДРУГАЯ закупка
   *  (остаток −113,60 ₽) — occupied=true запрещает АВТОМАТИЧЕСКУЮ галочку (см.
   *  checkPlanOccupancy), ручную галочку не блокирует. Пока candidate==null
   *  occupied всегда false (нечему быть занятым). */
  occupied: boolean
  /** Другая закупка/заявка уже занимает кандидата — см. FeoPlanPosition.linked_purchases/
   *  linked_wishes (уже исключают ТЕКУЩУЮ закупку/заявку, exclude_purchase_id/
   *  exclude_wish_id на бэке). Для показа FeoPlannedTakenBy в диалоге. */
  linkedPurchases: FeoPlanPosition['linked_purchases'] | null
  linkedWishes: FeoPlanPosition['linked_wishes'] | null
  /** Сумма позиции минус остаток кандидата (> 0 — не хватает); null — кандидата
   *  нет. Тот же знак, что и FeoPlannedTakenBy::shortfall в FeoPlannedMatchSuggestions.vue. */
  shortfall: number | null
  checked: boolean
}

export interface UseFeoPlannedBulkMatchDeps {
  localItems: Ref<EditorItem[]>
  subsidyId: Ref<number | null | undefined>
  plannedItems: Ref<FeoPlanPosition[]>
  emitUpdate: () => void
  showSnack: (text: string, color?: ToastType) => void
}

export function useFeoPlannedBulkMatch(deps: UseFeoPlannedBulkMatchDeps) {
  const { localItems, subsidyId, plannedItems, emitUpdate, showSnack } = deps
  const { matchQueries } = useFeoPlanMatching()

  const bulkMatchDialog = ref(false)
  const bulkMatchLoading = ref(false)
  const bulkMatchRows = ref<BulkMatchRow[]>([])

  // Кандидаты на привязку — непустое имя, ещё нет feo_planned_item_id. Тот же
  // критерий, что и needPlanRows/_unlinkedCandidates в useItemsBulkFeo.ts (общая
  // формулировка «позиция без плана»), намеренно НЕ импортируется оттуда как значение
  // (needPlanRows дополнительно требует известную категорию — здесь категория не
  // нужна ДО подбора: ищем по всей субсидии, категория придёт вместе с кандидатом).
  const unlinkedForMatch = computed(() =>
    localItems.value
      .map((it, idx) => ({ it, idx }))
      .filter(({ it }) => (it.item_name || '').trim() && it.feo_planned_item_id == null)
  )

  const canOpenBulkMatch = computed(() => unlinkedForMatch.value.length > 0 && !!subsidyId.value)

  function planRowOf(kind: string, id: number): FeoPlanPosition | null {
    return plannedItems.value.find(p => p.kind === kind && p.id === id) ?? null
  }

  function residualOf(row: FeoPlanPosition | null): { residual: number | null; plannedAmount: number | null; itemType: string | null } {
    return { residual: row?.residual ?? null, plannedAmount: row?.planned_amount ?? null, itemType: row?.item_type ?? null }
  }

  async function openBulkMatchDialog() {
    const targets = unlinkedForMatch.value
    if (!targets.length || !subsidyId.value) return
    bulkMatchLoading.value = true
    bulkMatchDialog.value = true
    try {
      const results = await matchQueries(
        targets.map(({ it }) => it.item_name),
        subsidyId.value,
        undefined, // ищем по ВСЕЙ субсидии — ровно жалоба владельца (дефект 1): категория
                   // позиции закупки/заявки может быть выставлена неверно/вообще не выставлена,
                   // сужать поиск ею означало бы повторить тот же тупик.
        5,
      )
      bulkMatchRows.value = targets.map(({ it, idx }, i) => {
        const top = results[i]?.candidates?.[0] || null
        const isExact = !!top && top.score >= PLAN_MATCH_SCORE_EXACT
        const topRow = top ? planRowOf(top.kind, top.id) : null
        const candidate = top && top.score >= PLAN_MATCH_SCORE_SUGGEST
          ? { kind: top.kind, id: top.id, name: top.name, path: top.path, score: top.score, ...residualOf(topRow) }
          : null
        const amount: number | null = it.total_price ?? null
        // Владелец (30.09.2026, «Доставка из чека должна быть создана отдельно,
        // она не должна объединяться ни с чем») — позиции из чека авансового
        // (receipt_id задан) по сути уникальные покупки: occupancy-проверка ниже
        // уже запрещает авто-галочку у ЛЮБОГО кандидата, занятого другой
        // закупкой/заявкой (checkPlanOccupancy::linkedByOther), receipt_id
        // отдельной веткой не нужен — правило одно (ПРАВИЛО №6).
        const occupancy = candidate ? checkPlanOccupancy(topRow, { amount, quantity: it.quantity ?? null }) : null
        return {
          idx,
          uid: it._uid ?? idx,
          name: (it.item_name || '').trim(),
          quantity: it.quantity ?? null,
          unit: it.unit || '',
          amount,
          itemType: it.item_type || null,
          candidate,
          isExact: !!candidate && isExact,
          occupied: !!occupancy?.occupied,
          linkedPurchases: topRow?.linked_purchases ?? null,
          linkedWishes: topRow?.linked_wishes ?? null,
          shortfall: candidate && amount != null && candidate.residual != null ? amount - candidate.residual : null,
          // Автоматическая галочка — только точное совпадение имени И кандидат
          // свободен (не занят другой закупкой/заявкой, остатка достаточно).
          // Занятый кандидат остаётся ВИДЕН (isExact/имя не меняются), но
          // требует осознанного ручного клика — см. toggleBulkMatchRow.
          checked: !!candidate && isExact && !occupancy?.occupied,
        } as BulkMatchRow
      })
    } catch (e: any) {
      bulkMatchDialog.value = false
      showSnack(e?.payload?.message || e?.message || 'Не удалось подобрать плановые позиции', 'error')
    } finally {
      bulkMatchLoading.value = false
    }
  }

  function closeBulkMatchDialog() {
    if (bulkMatchLoading.value) return
    bulkMatchDialog.value = false
  }

  function toggleBulkMatchRow(i: number) {
    const row = bulkMatchRows.value[i]
    if (row && row.candidate) row.checked = !row.checked
  }

  // Владелец, дословно: «либо соглашался, либо нет; при 100% совпадении подставлялось
  // автоматически» — применяем ТОЛЬКО отмеченные строки. Категория позиции переезжает
  // вслед за плановой позицией (тот же приём, что и в useItemsFeo.ts::onItemPlannedChange/
  // остальных трёх местах той же правки, ПРАВИЛО №6 — переносим позицию в категорию
  // найденного плана, а не молчим о несовпадении: список candidate.path в диалоге уже
  // и есть «предупреждение словами» перед привязкой).
  function runBulkMatchApply() {
    let applied = 0
    for (const row of bulkMatchRows.value) {
      if (!row.checked || !row.candidate) continue
      const item = localItems.value[row.idx]
      if (!item) continue
      const c = row.candidate
      if (c.kind === 'planned_item') {
        item.feo_planned_item_id = c.id
        const plannedCategoryId = plannedItems.value.find(p => p.kind === 'planned_item' && p.id === c.id)?.category_id
        if (plannedCategoryId != null) {
          item.feo_node_id = plannedCategoryId
          item.feo_category_id = plannedCategoryId
        }
      } else {
        item.feo_planned_item_id = null
        item.feo_category_id = c.id
        item.feo_node_id = c.id
      }
      item.over_plan = false
      applied++
    }
    bulkMatchDialog.value = false
    if (applied > 0) {
      emitUpdate()
      showSnack(`Привязано к плану: ${applied}`)
    } else {
      showSnack('Ничего не отмечено — привязка не выполнена', 'warning')
    }
  }

  return {
    bulkMatchDialog, bulkMatchLoading, bulkMatchRows, unlinkedForMatch, canOpenBulkMatch,
    openBulkMatchDialog, closeBulkMatchDialog, toggleBulkMatchRow, runBulkMatchApply,
  }
}

export type UseFeoPlannedBulkMatch = ReturnType<typeof useFeoPlannedBulkMatch>
