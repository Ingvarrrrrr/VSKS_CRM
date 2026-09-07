// useItemsBulkFeo — «ISSUE-3 PART B» bulk-assign FEO level to selected items
// (bulkFeoDialog + applyBulkFeo/applyBulkUnallocated) and the «Владелец
// 2026-08-06: общая кнопка "Создать в плане закупок"» flow (создать плановые
// позиции разом для всех непривязанных позиций, needPlanRows/runCreatePlannedBulk).
// Держатся в ОДНОМ файле (не разрезаны на useItemsBulkFeo.ts/useItemsPlanCreate.ts,
// как допускал план рефакторинга), потому что create-planned-bulk читает
// effectivePlannedItems, объявленный в bulk-assign-FEO блоке (нужен и там для
// bulk-диалога, и здесь — для needPlanRows.duplicateOf); дробить значило бы либо
// дублировать `props.plannedItems || []` в двух файлах под одним именем (ПРАВИЛО
// №6 — один источник), либо тащить его как проп из одного файла в другой, что не
// проще прямого вызова из одного места. Extracted from PurchaseItemsEditor.vue
// (monolith refactor, часть 3).
import { computed, reactive, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import type { ToastType } from '@/composables/useToast'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue) since the parent owns the real shape.
type EditorItem = any

// «Если делаются разные категории ФЭО, то ... должна быть общая кнопка, которая
// "Создать в плане закупок" — при нажатии на неё все позиции, которые не привязались
// к плановым, надо создать будут в соответствующих категориях, как плановые, которые
// для них выбраны». Категория позиции — тот же эффективный узел, что используют
// per-item FeoPlannedItemsSelect в таблицах (item.feo_node_id ?? item.feo_category_id,
// см. ItemsTableFlat.vue/ItemsCardsView.vue/ItemsTableStages.vue).
export interface PlanCreateRow {
  idx: number
  uid: string | number
  name: string
  quantity: number | null
  unit: string
  amount: number | null
  categoryId: number
  categoryName: string
  // Дефект 2 (владелец, 2026-08-20): решение владельца — каждой строке своя ОТДЕЛЬНАЯ
  // плановая позиция, одноимённые НЕ объединяются (см. runCreatePlannedBulk). Это поле
  // чисто информационное — честно предупредить в предпросмотре, что в этой категории
  // уже есть плановая позиция с таким же именем, НЕ блокирует и НЕ меняет создание.
  duplicateOf: { id: number; name: string } | null
}

export interface UseItemsBulkFeoDeps {
  props: {
    plannedItems?: FeoPlanPosition[]
    subsidyId?: number | null
    feoPerItem?: boolean
    defaultFeoCategoryId?: number | null
    itemShape: 'purchase' | 'wish'
  }
  localItems: Ref<EditorItem[]>
  selectedItemIdxs: Ref<number[]>
  feoNodes: Ref<FeoNode[]>
  injectUnallocatedNode: (cat: { id: number; name: string; parent_id?: number | null }) => void
  emitUpdate: () => void
  emit: { (event: 'planned-item-created'): void }
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
}

export function useItemsBulkFeo(deps: UseItemsBulkFeoDeps) {
  const { props, localItems, selectedItemIdxs, feoNodes, injectUnallocatedNode, emitUpdate, emit, showSnack } = deps

  // ── ISSUE-3 PART B: bulk-assign FEO level to selected items ─────────────────
  const bulkFeoDialog = ref(false)
  const bulkFeoId = ref<number | null>(null)
  // F-PLAN: массово назначаемая плановая позиция (единый источник plan-positions) для bulk-диалога.
  const bulkPlannedSelection = ref<FeoPlanSelection | null>(null)
  const unallocatedLoading = ref(false)

  // F-PLAN: список плановых позиций для bulk-диалога — то же, что приходит в проп.
  const effectivePlannedItems = computed(() => props.plannedItems || [])

  // Предзаполнение диалога «Создать в плане закупок» для bulk-выбора — имя первой
  // выбранной позиции, сумма — Σ total_price ВСЕХ выбранных (агрегат по группе, не
  // одна позиция, как в построчных редакторах).
  const bulkPlannedPrefill = computed(() => {
    const rows = selectedItemIdxs.value.map(idx => localItems.value[idx]).filter((r): r is EditorItem => !!r)
    const first = rows.find(r => (r.item_name || '').trim())
    const amount = rows.reduce((sum, r) => sum + (Number(r.total_price) || 0), 0)
    return {
      name: first?.item_name ?? null,
      quantity: first?.quantity ?? null,
      unit: first?.unit ?? null,
      amount,
    }
  })

  function openBulkFeoDialog() {
    bulkFeoId.value = null
    bulkPlannedSelection.value = null
    bulkFeoDialog.value = true
  }

  function closeBulkFeoDialog() {
    bulkFeoDialog.value = false
    bulkFeoId.value = null
    bulkPlannedSelection.value = null
  }

  function applyBulkFeo() {
    if (bulkFeoId.value == null) return
    // Same rule as onItemFeoChange: feo_node_id всегда получает выбранный узел
    // (лист или промежуточная папка), feo_category_id — только когда узел лист.
    // Раньше здесь писался только feo_category_id, и поле позиции (которое
    // читает feo_node_id ?? feo_category_id) продолжало показывать старый путь.
    const isLeaf = feoNodes.value.find(n => n.id === bulkFeoId.value)?.is_leaf ?? false
    const planned = bulkPlannedSelection.value
    for (const idx of selectedItemIdxs.value) {
      const item = localItems.value[idx]
      if (item) {
        item.feo_node_id = bulkFeoId.value
        item.feo_category_id = isLeaf ? bulkFeoId.value : null
        // F-PLAN: массовое назначение плановой позиции — только когда выбрана явно в диалоге.
        if (planned) {
          if (planned.kind === 'planned_item') {
            item.feo_planned_item_id = planned.id
          } else {
            item.feo_planned_item_id = null
            item.feo_category_id = planned.id
          }
          item.over_plan = false
        }
      }
    }
    bulkFeoDialog.value = false
    bulkFeoId.value = null
    bulkPlannedSelection.value = null
    selectedItemIdxs.value = []
    emitUpdate()
  }

  async function applyBulkUnallocated(parentId: number | null) {
    if (!props.subsidyId) return
    unallocatedLoading.value = true
    try {
      const body: Record<string, unknown> = { subsidy_id: props.subsidyId }
      if (parentId != null) body.parent_id = parentId
      const cat = await apiFetch<{ id: number; name: string; parent_id: number | null }>('/feo-categories/unallocated', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      // Добавить в feoNodes если отсутствует, пометив родителя не-листом.
      injectUnallocatedNode(cat)
      for (const idx of selectedItemIdxs.value) {
        const item = localItems.value[idx]
        if (item) {
          item.feo_node_id = cat.id
          item.feo_category_id = cat.id
        }
      }
      bulkFeoDialog.value = false
      bulkFeoId.value = null
      selectedItemIdxs.value = []
      emitUpdate()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
    } finally {
      unallocatedLoading.value = false
    }
  }

  // ── Владелец 2026-08-06: общая кнопка «Создать в плане закупок» ─────────────
  // Этап 1 (владелец, 2026-09-02): «сейчас на закупке без per-item категорий
  // кнопка "Создать в плане закупок" гаснет, и расхождение нечем исправить» —
  // когда режим «разные категории ФЭО для каждого товара» (feoPerItem) ВЫКЛЮЧЕН,
  // эффективная категория позиции обязана быть категорией шапки (defaultFeoCategoryId),
  // а не собственным feo_category_id позиции (в этом режиме позиции вообще не
  // должны иметь свою категорию — см. backend _item_feo_mismatch reason="header",
  // который как раз и алярмит расхождение, если она вдруг есть). Когда feoPerItem
  // ВКЛЮЧЁН — прежнее поведение (своя категория позиции).
  function _effectiveFeoCategoryId(it: EditorItem): number | null {
    if (!props.feoPerItem) return props.defaultFeoCategoryId ?? null
    return it.feo_node_id ?? it.feo_category_id ?? null
  }

  // Кандидаты — непустое наименование, ещё нет привязки к плановой позиции (Ур.5).
  const _unlinkedCandidates = computed(() =>
    localItems.value
      .map((it, idx) => ({ it, idx }))
      .filter(({ it }) => (it.item_name || '').trim() && it.feo_planned_item_id == null)
  )

  // Владелец 2026-08-18: «У меня в закупке имеются позиции, не привязанные к
  // плановым. Это косяк, об этом надо сообщать!» — те же строки, что и
  // _unlinkedCandidates (непустое имя, feo_planned_item_id == null), НО без
  // over_plan=true: такие позиции сознательно заведены сверх плана (согласуется
  // отдельно, см. EditorItem.over_plan / F-PLAN2) и привязки к плановой позиции
  // не требуют — не считаем их «косяком». Гейт по subsidyId: без субсидии у
  // закупки нет плана вовсе, предупреждение всегда было бы включено — бесполезный шум.
  const itemsMissingPlan = computed(() => {
    if (props.itemShape !== 'purchase' || !props.subsidyId) return []
    return _unlinkedCandidates.value.filter(({ it }) => !it.over_plan).map(({ it }) => it)
  })

  function _pluralRu(n: number, [one, few, many]: [string, string, string]): string {
    const mod10 = n % 10
    const mod100 = n % 100
    if (mod10 === 1 && mod100 !== 11) return one
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
    return many
  }

  const itemsMissingPlanWord = computed(() => _pluralRu(itemsMissingPlan.value.length, ['позиция', 'позиции', 'позиций']))

  const itemsMissingPlanSummary = computed(() => {
    const names = itemsMissingPlan.value.map(it => (it.item_name || '').trim() || '—')
    const shown = names.slice(0, 3)
    const restCount = names.length - shown.length
    return shown.join(', ') + (restCount > 0 ? ` и ещё ${restCount}` : '')
  })

  const needPlanRows = computed((): PlanCreateRow[] =>
    _unlinkedCandidates.value
      .map(({ it, idx }) => {
        const categoryId = _effectiveFeoCategoryId(it)
        if (categoryId == null) return null
        const categoryName = feoNodes.value.find(n => n.id === categoryId)?.name ?? `#${categoryId}`
        const name = (it.item_name || '').trim()
        // Дефект 2 (владелец, 2026-08-20): ЧЕСТНОЕ предупреждение — в этой категории уже
        // есть плановая позиция с таким же именем. Информационное, НЕ дедуп: runCreatePlannedBulk
        // ниже больше не привязывает к ней и не пропускает создание — каждая строка получает
        // свою отдельную плановую позицию (allow_duplicate_name), одноимённые не объединяются.
        const dup = (effectivePlannedItems.value || []).find(p =>
          p.kind === 'planned_item'
          && p.category_id === categoryId
          && _normalizePlanName(p.name) === _normalizePlanName(name)
        )
        return {
          idx,
          uid: it._uid ?? idx,
          name,
          quantity: it.quantity ?? null,
          unit: it.unit || '',
          amount: it.total_price ?? null,
          categoryId,
          categoryName,
          duplicateOf: dup ? { id: dup.id, name: dup.name } : null,
        } as PlanCreateRow
      })
      .filter((r): r is PlanCreateRow => r != null)
  )

  const needPlanCount = computed(() => needPlanRows.value.length)

  const noCategoryCount = computed(() =>
    _unlinkedCandidates.value.filter(({ it }) => _effectiveFeoCategoryId(it) == null).length
  )

  // Дефект 2 (владелец, 2026-08-20): пункт 3 задачи — кнопка «Создать в плане закупок»
  // заблокирована, пока хоть у одной непривязанной позиции нет конечной категории ФЭО
  // (иначе клик по кнопке частично создаёт план и молча пропускает остальное — путаница).
  // Список нужен и для тултипа-объяснения, и для перехода/подсветки первой строки.
  const itemsMissingCategoryForPlan = computed(() =>
    _unlinkedCandidates.value
      .filter(({ it }) => _effectiveFeoCategoryId(it) == null)
      .map(({ it, idx }) => ({ idx, uid: it._uid ?? idx, name: (it.item_name || '').trim() || 'без названия' }))
  )

  const createPlannedBulkDialog = ref(false)
  const createPlannedBulkLoading = ref(false)
  const createPlannedBulkProgress = reactive({ done: 0, total: 0 })
  const createPlannedBulkFailures = ref<string[]>([])

  function openCreatePlannedBulkDialog() {
    createPlannedBulkFailures.value = []
    createPlannedBulkProgress.done = 0
    createPlannedBulkProgress.total = 0
    createPlannedBulkDialog.value = true
  }

  function closeCreatePlannedBulkDialog() {
    if (createPlannedBulkLoading.value) return
    createPlannedBulkDialog.value = false
  }

  // Дефект 2, п.3 (владелец, 2026-08-20): клик по заблокированной кнопке «Создать в плане
  // закупок» не молчит — прокручивает к первой позиции без категории ФЭО и подсвечивает её
  // строку (тот же приём, что highlightMissingFeoCategory/highlightMissingDateItems в
  // WishesView.vue: pulse-класс + scrollIntoView, только здесь без общего arrow-оверлея —
  // компонент переиспользуется вне WishesView, ссылаться на её рефы нельзя). item-row-*
  // id проставлен на строку/карточку каждой позиции в ItemsTableFlat/ItemsCardsView/
  // ItemsTableStages (см. соответствующие файлы).
  function highlightMissingCategoryForPlan() {
    const first = itemsMissingCategoryForPlan.value[0]
    if (!first) return
    const el = document.getElementById(`item-row-${first.uid}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('plan-bulk-row-pulse')
    setTimeout(() => el.classList.remove('plan-bulk-row-pulse'), 3000)
  }

  // Дедуп — строго точное совпадение имени после нормализации (trim + схлопывание
  // пробелов + lower), НИКАКОГО fuzzy (правило проекта — fuzzy ложно сливал разные
  // SKU, см. Lessons: feedback_dedup_exact_only).
  function _normalizePlanName(s: string | null | undefined): string {
    return (s || '').trim().replace(/\s+/g, ' ').toLowerCase()
  }

  // Дефект 2 (владелец, 2026-08-20): решение владельца — «каждой строке своя отдельная
  // плановая позиция, одноимённые НЕ объединять». Раньше здесь был дедуп (внутри прогона
  // И против props.plannedItems) — 2 позиции заявки с одинаковым названием («Футболка
  // поло», 10 шт и 15 шт с разной печатью) схлопывались в одну плановую и роняли остаток
  // плана. Теперь КАЖДАЯ строка — отдельный POST с allow_duplicate_name:true (backend
  // feo_planned_items.py::create_planned_item, тот же флаг, что снимает интерактивный
  // 409 planned_item_duplicate_name у одиночного создания) — дедуп по имени внутри
  // категории сознательно пропускается, needPlanRows.duplicateOf выше только предупреждает
  // об этом в предпросмотре, не меняя поведение.
  async function runCreatePlannedBulk() {
    const rows = needPlanRows.value
    if (!rows.length) return
    createPlannedBulkLoading.value = true
    createPlannedBulkFailures.value = []
    createPlannedBulkProgress.done = 0
    createPlannedBulkProgress.total = rows.length
    let anyChanged = false
    for (const row of rows) {
      const item = localItems.value[row.idx]
      if (!item) { createPlannedBulkProgress.done += 1; continue }
      try {
        const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
          method: 'POST',
          body: JSON.stringify({
            feo_category_id: row.categoryId,
            name: row.name,
            quantity: row.quantity,
            unit: row.unit || null,
            amount: row.amount,
            allow_duplicate_name: true,
          }),
        })
        item.feo_planned_item_id = created.id
        item.over_plan = false
        anyChanged = true
      } catch (e: any) {
        const status = e?.status
        const msg = e?.payload?.message || e?.message || 'неизвестная ошибка'
        createPlannedBulkFailures.value.push(`«${row.name}»${status ? ` (HTTP ${status})` : ''}: ${msg}`)
      } finally {
        createPlannedBulkProgress.done += 1
      }
    }
    if (anyChanged) {
      emitUpdate()
      emit('planned-item-created')
    }
    createPlannedBulkLoading.value = false
    const failCount = createPlannedBulkFailures.value.length
    // Дефект 2, п.4 (владелец): ОДИН тост на весь прогон, не по одному на позицию.
    if (failCount === 0) {
      createPlannedBulkDialog.value = false
      showSnack(`Плановые позиции созданы: ${rows.length}`)
    } else {
      showSnack(
        `Готово ${rows.length - failCount} из ${rows.length}. Не удалось: ${createPlannedBulkFailures.value.join('; ')}`,
        'error'
      )
      // Диалог не закрываем — пусть видно, что не получилось; успевшие позиции уже привязаны.
    }
  }

  return {
    bulkFeoDialog, bulkFeoId, bulkPlannedSelection, unallocatedLoading,
    effectivePlannedItems, bulkPlannedPrefill,
    openBulkFeoDialog, closeBulkFeoDialog, applyBulkFeo, applyBulkUnallocated,
    itemsMissingPlan, itemsMissingPlanWord, itemsMissingPlanSummary,
    needPlanRows, needPlanCount, noCategoryCount, itemsMissingCategoryForPlan,
    createPlannedBulkDialog, createPlannedBulkLoading, createPlannedBulkProgress, createPlannedBulkFailures,
    openCreatePlannedBulkDialog, closeCreatePlannedBulkDialog,
    highlightMissingCategoryForPlan, runCreatePlannedBulk,
  }
}
