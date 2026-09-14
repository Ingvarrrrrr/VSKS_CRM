// Поиск ПО СУБСИДИИ внутри развёрнутого дерева ФЭО (владелец, 2026-09-15):
// «Нужен поиск по субсидии, чтобы при развёрнутой субсидии искал товары/категории,
// просто вхождение слов. ОУ-2 огнетушитель не помню где находится в субсидии
// минпроса, задолбался искать. Общий поиск по БД для этого неудобен.»
//
// Простое вхождение слов, порядок и регистр не важны: «ОУ-2 огнетушитель» находит
// «Огнетушитель ОУ-2» — каждое слово запроса ищется независимо подстрокой внутри
// названия, никакого fuzzy (см. feedback_dedup_exact_only.md — тот же принцип:
// нечёткое сравнение здесь не нужно и не просили).
//
// ДВА источника данных — не два механизма поиска, а два места, где физически лежат
// совпадающие данные (Правило №6 — не второй источник истины, а честный выбор между
// уже существующими):
//  - категории/направления (любого уровня, не только листья) — ctx.feoCategories уже
//    загружены ЦЕЛИКОМ на клиенте при открытии субсидии (loadFeo() в SubsidiesView.vue,
//    GET /feo-categories/?subsidy_id=), поэтому поиск по названию/коду направления —
//    чисто клиентский, без сетевого запроса;
//  - плановые позиции (FeoPlannedItem, «Огнетушитель ОУ-2» внутри категории) — НЕ все
//    на клиенте: comparisonData (см. useFeoLevel5.ts) подгружается ЛЕНИВО, по одной
//    категории, только когда открыта её панель «План vs факт». Обходить клиентские
//    данные бессмысленно — их там ещё может не быть ни для одной категории субсидии.
//    Вместо нового бэкенд-роутера переиспользуется УЖЕ существующий
//    GET /api/feo-categories/plan-positions?subsidy_id= (feo_plan_reads_tree.py) —
//    он и так одним списком отдаёт ВСЕ FeoPlannedItem субсидии (kind='planned_item')
//    с готовым полем `path` (app.services.feo_plan_totals.build_category_path,
//    "Направление › Подраздел"), которым уже пользуются FeoPlannedItemsSelect.vue/
//    PurchaseItemsEditor.vue для показа пути плановой позиции при выборе. Второй
//    роутер под то же самое не заводим.
import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoCategory } from './types'

export interface FeoSearchResult {
  key: string
  kind: 'category' | 'planned_item'
  id: number
  name: string
  /** Путь ПРЕДКОВ (без самого узла/позиции), "Направление › Подраздел" — пусто для корня. */
  path: string
  categoryId: number
}

interface PlanPositionRow {
  id: number
  name: string
  path: string
  category_id: number
  kind: 'plan_position' | 'feo_article' | 'planned_item'
}

let _api: ReturnType<typeof buildFeoTreeSearch> | null = null

interface FeoTreeSearchCtx {
  selectedId: Ref<number | null>
  feoCategories: Ref<FeoCategory[]>
  expandedIds: Ref<number[]>
  expandedItemPanels: Ref<Set<number>>
  comparisonData: Ref<Record<number, unknown>>
  loadingComparison: Ref<Set<number>>
  refreshComparison: (categoryId: number) => Promise<void>
  feoTableArea: Ref<HTMLElement | null>
}

// Module-level singleton — тот же паттерн, что и useKpiDrilldown.ts/useFeoTreeState.ts
// в этом же проекте: единственный экземпляр состояния на всех потребителей
// (FeoTreeToolbar.vue — поле ввода и список результатов).
export function useFeoTreeSearch(ctx: FeoTreeSearchCtx) {
  if (!_api) _api = buildFeoTreeSearch(ctx)
  return _api
}

function buildFeoTreeSearch(ctx: FeoTreeSearchCtx) {
  const feoSearchQuery = ref('')
  const plannedItemRows = ref<PlanPositionRow[]>([])
  const plannedItemsLoadedFor = ref<number | null>(null)
  const feoSearchLoading = ref(false)

  // Другая субсидия — сбросить и запрос, и кэш плановых позиций (иначе результаты
  // прошлой субсидии на миг показались бы для новой, пока не подгрузится её список).
  watch(ctx.selectedId, () => {
    feoSearchQuery.value = ''
    plannedItemRows.value = []
    plannedItemsLoadedFor.value = null
  })

  async function ensurePlannedItemsLoaded() {
    const sid = ctx.selectedId.value
    if (!sid || plannedItemsLoadedFor.value === sid || feoSearchLoading.value) return
    feoSearchLoading.value = true
    try {
      const rows = await apiFetch<PlanPositionRow[]>(`/feo-categories/plan-positions?subsidy_id=${sid}`)
      plannedItemRows.value = rows.filter(r => r.kind === 'planned_item')
      plannedItemsLoadedFor.value = sid
    } catch {
      plannedItemRows.value = []
    } finally {
      feoSearchLoading.value = false
    }
  }

  // Подгружаем список плановых позиций один раз на субсидию, лениво — на первый
  // непустой ввод, а не сразу при открытии субсидии (поиском пользуются не всегда).
  watch(feoSearchQuery, (v) => { if ((v || '').trim()) ensurePlannedItemsLoaded() })

  function searchWords(q: string): string[] {
    // Vuetify clearable (кнопка «×» в поле ввода) отдаёт null, а не '' — модель
    // типизирована как string, но рантайм не проверяет это за нас.
    return (q || '').trim().toLowerCase().split(/\s+/).filter(Boolean)
  }
  function matchesAllWords(text: string, words: string[]): boolean {
    const t = text.toLowerCase()
    return words.every(w => t.includes(w))
  }

  const catById = computed<Record<number, FeoCategory>>(() => {
    const map: Record<number, FeoCategory> = {}
    for (const c of ctx.feoCategories.value) map[c.id] = c
    return map
  })

  // Тот же вид пути, что и бэкендовый build_category_path ("Направление › Подраздел"),
  // но БЕЗ самого узла (см. докстринг FeoSearchResult.path) — единообразно с path,
  // который для plan-positions уже приходит в этом формате.
  function ancestorPath(catId: number): string {
    const names: string[] = []
    let cur: FeoCategory | undefined = catById.value[catId]
    while (cur && cur.parent_id != null) {
      const parent: FeoCategory | undefined = catById.value[cur.parent_id]
      if (!parent) break
      names.push(parent.name)
      cur = parent
    }
    return names.reverse().join(' › ')
  }

  const feoSearchResults = computed<FeoSearchResult[]>(() => {
    const words = searchWords(feoSearchQuery.value)
    if (!words.length) return []
    const out: FeoSearchResult[] = []
    for (const c of ctx.feoCategories.value) {
      if (matchesAllWords(c.name, words) || (c.code && matchesAllWords(c.code, words))) {
        out.push({ key: `c-${c.id}`, kind: 'category', id: c.id, name: c.name, path: ancestorPath(c.id), categoryId: c.id })
      }
    }
    for (const it of plannedItemRows.value) {
      if (matchesAllWords(it.name, words)) {
        out.push({ key: `p-${it.id}`, kind: 'planned_item', id: it.id, name: it.name, path: it.path, categoryId: it.category_id })
      }
    }
    // Ограничение — то же самое разумное «не тысячу строк на экран», что и у похожих
    // списков дерева (см. find_excess_culprit — «обычно единицы, не весь тред»).
    return out.slice(0, 50)
  })

  // Прокрутка+подсветка узла — тот же приём, что и scrollToNewFeoNode в
  // FeoCategoryDialog.vue (querySelector по data-атрибуту строки + scrollIntoView +
  // временный inline-фон вместо своего CSS-класса), второй механизм не заводим.
  async function scrollAndHighlight(r: FeoSearchResult) {
    await nextTick()
    await nextTick() // панель/дерево перерисовываются после смены expandedIds/comparisonData
    const selector = r.kind === 'planned_item'
      ? `[data-feo-planned-item-id="${r.id}"]`
      : `[data-feo-node-id="${r.id}"]`
    const el = ctx.feoTableArea.value?.querySelector<HTMLElement>(selector)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const prevBg = el.style.backgroundColor
    const prevTransition = el.style.transition
    el.style.transition = 'background-color 1.6s ease'
    el.style.backgroundColor = '#FEF3C7'
    setTimeout(() => {
      el.style.backgroundColor = prevBg
      setTimeout(() => { el.style.transition = prevTransition }, 1700)
    }, 400)
  }

  async function goToFeoSearchResult(r: FeoSearchResult) {
    // Раскрыть предков найденного узла (тот же приём, что и addFeoCategory в
    // FeoCategoryDialog.vue — push недостающих id в expandedIds); собственный id
    // тоже попадает в список — лишним не мешает (isNodeVisible смотрит только на
    // цепочку ПРЕДКОВ, не на сам узел), а если у найденной категории есть дети,
    // заодно раскрывает и их.
    let cur: FeoCategory | undefined = catById.value[r.categoryId]
    while (cur) {
      const id = cur.id
      if (!ctx.expandedIds.value.includes(id)) ctx.expandedIds.value.push(id)
      cur = cur.parent_id != null ? catById.value[cur.parent_id] : undefined
    }
    if (r.kind === 'planned_item') {
      // Открыть панель «План vs факт» категории-владельца и подгрузить данные — тот
      // же приём, что и applyKpiExpansion в useKpiDrilldown.ts (панель раскрывается
      // прямым присваиванием, данные — отдельным refreshComparison, если их ещё нет).
      if (!ctx.expandedItemPanels.value.has(r.categoryId)) ctx.expandedItemPanels.value.add(r.categoryId)
      if (!ctx.comparisonData.value[r.categoryId] && !ctx.loadingComparison.value.has(r.categoryId)) {
        await ctx.refreshComparison(r.categoryId)
      }
    }
    feoSearchQuery.value = ''
    await scrollAndHighlight(r)
  }

  return { feoSearchQuery, feoSearchResults, feoSearchLoading, goToFeoSearchResult }
}
