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
import { makeCtxSingleton } from './ctxSingleton'
import type { FeoCategory } from './types'
import { useToast } from '@/composables/useToast'
import { waitForFeoSearchElement } from './useFeoTreeSearchHighlight'
import { searchWords, matchesAllWords } from '@/utils/textSearch'

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

// Module-level singleton через makeCtxSingleton (ctxSingleton.ts, Правило №6) —
// единственный экземпляр состояния на всех потребителей (FeoTreeToolbar.vue —
// поле ввода и список результатов); пересобирается при новом ctx (повторный
// маунт SubsidiesView.vue, владелец 21.09 П2), не держит ctx первого маунта
// навсегда.
export const useFeoTreeSearch = makeCtxSingleton(
  buildFeoTreeSearch,
  'useFeoTreeSearch() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue',
)

function buildFeoTreeSearch(ctx: FeoTreeSearchCtx) {
  const feoSearchQuery = ref('')
  const plannedItemRows = ref<PlanPositionRow[]>([])
  const plannedItemsLoadedFor = ref<number | null>(null)
  const feoSearchLoading = ref(false)
  const toast = useToast()

  // Открытость выпадающего списка — ОТДЕЛЬНЫЙ флаг от «запрос не пуст» (владелец,
  // 2026-10-13): после выбора варианта запрос остаётся в поле, но список должен
  // закрыться; снова открывается при вводе (watch ниже) или фокусе поля
  // (onFeoSearchFocus). Раньше список был v-if="запрос не пуст" — тогда закрыть
  // его без очистки поля было нечем, второго способа закрытия не заводим.
  const feoSearchOpen = ref(false)
  // Ключ найденного узла/позиции, который держит подсветку в дереве до явного
  // сброса — тот же формат key, что у FeoSearchResult ('c-<id>' / 'p-<id>').
  // Реактивный ref, а не inline-стиль с setTimeout (как было в прежней
  // scrollAndHighlight) — дерево ФЭО перерисовывается (loadFeo), inline-стиль на
  // DOM-узле слетел бы при перерисовке, реактивный класс переживает её.
  const highlightedKey = ref<string | null>(null)
  function isFeoSearchHighlighted(key: string): boolean {
    return highlightedKey.value === key
  }
  // Категории на пути к найденному узлу (сама найденная категория/категория-
  // владелец плановой позиции + все её предки) — владелец, правка 2026-10-13:
  // переключатель «скрыть закупленные полностью» (useFeoHideFullyPurchased,
  // FeoTreeRow.vue::hiddenByFullyPurchasedFilter) иначе прятал бы найденный
  // узел, если он сам или путь к нему полностью закуплены, и поиск молча
  // показывал бы «не удалось показать». Живёт СТРОГО вместе с highlightedKey —
  // то же условие «пока подсветка держится», второй жизненный цикл не заводим.
  const searchPathCategoryIds = ref<Set<number>>(new Set())
  function isOnFeoSearchPath(categoryId: number): boolean {
    return searchPathCategoryIds.value.has(categoryId)
  }

  // Другая субсидия — сбросить и запрос, и кэш плановых позиций (иначе результаты
  // прошлой субсидии на миг показались бы для новой, пока не подгрузится её список).
  watch(ctx.selectedId, () => {
    feoSearchQuery.value = ''
    plannedItemRows.value = []
    plannedItemsLoadedFor.value = null
    feoSearchOpen.value = false
    highlightedKey.value = null
    searchPathCategoryIds.value = new Set()
  })

  // Открыть список при вводе; при полной очистке поля (крестик/Esc/Backspace до
  // пустой строки) — закрыть список И снять подсветку (владелец, п.4: «пока
  // человек не очистит поиск»). Срабатывает только на ИЗМЕНЕНИЕ запроса —
  // goToFeoSearchResult больше не трогает feoSearchQuery при выборе варианта,
  // поэтому сам выбор этот watch не переоткрывает.
  watch(feoSearchQuery, (v) => {
    const trimmed = (v || '').trim()
    feoSearchOpen.value = !!trimmed
    if (!trimmed) {
      highlightedKey.value = null
      searchPathCategoryIds.value = new Set()
    }
  })
  function onFeoSearchFocus() {
    if ((feoSearchQuery.value || '').trim()) feoSearchOpen.value = true
  }
  function clearFeoSearch() {
    feoSearchQuery.value = ''
    feoSearchOpen.value = false
    highlightedKey.value = null
    searchPathCategoryIds.value = new Set()
  }

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

  // searchWords/matchesAllWords — общий модуль frontend/src/utils/textSearch.ts
  // (Правило №6, вынесено 15.10.2026 вместе с FeoPlanTreePicker.vue/
  // ordersSearch.ts); поведение прежнее (слова в любом порядке, подстрокой),
  // плюс теперь ё/е не различаются — строго сверху прежнего, лишних
  // совпадений не отфильтровывает.

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

  // Прокрутка к найденному узлу — подсветка теперь реактивным классом
  // (highlightedKey выше), эта функция только ЖДЁТ появления элемента в DOM
  // (до 5 с, опрос каждые 100 мс — см. useFeoTreeSearchHighlight.ts) и
  // центрирует его. Раньше ждала ровно 2 nextTick и тихо выходила, если
  // элемент не успевал отрисоваться — пользователь не видел ни прокрутки,
  // ни сигнала об ошибке (жалоба владельца, п.2-3).
  async function scrollAndHighlight(r: FeoSearchResult) {
    await nextTick()
    const area = ctx.feoTableArea.value
    const selector = r.kind === 'planned_item'
      ? `[data-feo-planned-item-id="${r.id}"]`
      : `[data-feo-node-id="${r.id}"]`
    const el = area ? await waitForFeoSearchElement(area, selector) : null
    if (!el) {
      highlightedKey.value = null
      searchPathCategoryIds.value = new Set()
      toast.addToast(`Не удалось показать позицию «${r.name}» в дереве`, 'error')
      return
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function goToFeoSearchResult(r: FeoSearchResult) {
    // Раскрыть предков найденного узла (тот же приём, что и addFeoCategory в
    // FeoCategoryDialog.vue — push недостающих id в expandedIds); собственный id
    // тоже попадает в список — лишним не мешает (isNodeVisible смотрит только на
    // цепочку ПРЕДКОВ, не на сам узел), а если у найденной категории есть дети,
    // заодно раскрывает и их.
    const pathIds = new Set<number>()
    let cur: FeoCategory | undefined = catById.value[r.categoryId]
    while (cur) {
      const id = cur.id
      if (!ctx.expandedIds.value.includes(id)) ctx.expandedIds.value.push(id)
      pathIds.add(id)
      cur = cur.parent_id != null ? catById.value[cur.parent_id] : undefined
    }
    // «Скрыть закупленные полностью» не должен прятать найденный узел/путь к
    // нему, пока держится подсветка (см. докстринг searchPathCategoryIds выше).
    searchPathCategoryIds.value = pathIds
    if (r.kind === 'planned_item') {
      // Открыть панель «План vs факт» категории-владельца и подгрузить данные — тот
      // же приём, что и applyKpiExpansion в useKpiDrilldown.ts (панель раскрывается
      // прямым присваиванием, данные — отдельным refreshComparison, если их ещё нет).
      if (!ctx.expandedItemPanels.value.has(r.categoryId)) ctx.expandedItemPanels.value.add(r.categoryId)
      if (!ctx.comparisonData.value[r.categoryId] && !ctx.loadingComparison.value.has(r.categoryId)) {
        await ctx.refreshComparison(r.categoryId)
      }
    }
    // Запрос ОСТАЁТСЯ в поле (владелец, п.2) — выбор варианта только закрывает
    // список (feoSearchOpen), не трогая feoSearchQuery (watch на него не
    // переоткроет список, т.к. значение не меняется).
    feoSearchOpen.value = false
    // Подсветка выставляется ДО ожидания элемента — к моменту, когда дерево
    // дорисует найденную строку, класс уже забинден, и подсветка появляется
    // сразу вместе со строкой, без лишнего мигания.
    highlightedKey.value = r.key
    await scrollAndHighlight(r)
  }

  return {
    feoSearchQuery, feoSearchResults, feoSearchLoading, goToFeoSearchResult,
    feoSearchOpen, onFeoSearchFocus, clearFeoSearch, isFeoSearchHighlighted, isOnFeoSearchPath,
  }
}
