// useDrillSearch.ts — поле динамического поиска во всплывающих окнах-
// расшифровках карточек субсидии (владелец, 15.10.2026: «во всплывающих
// окнах сделать поле для динамического поиска по этому окну»; «почему
// поиска по позициям не идёт? ведь уже реализовано, просто скопировать
// логику»). Общая фильтрация списка строк — Правило №6, не копируем цикл
// filter/matchesAllWords в каждом диалоге (FeoCardDrillDialog.vue,
// StageFeoDrillDialog.vue, RedistributableDrillDialog.vue,
// ContractsDrillDialog.vue, PaidOverDeliveredDrillDialog.vue,
// OrderSubstitutionDialog.vue). Фильтрация мгновенная (computed, без
// debounce) — так же, как и в уже существующих полях поиска проекта
// (FeoPlanTreePicker.vue, FeoTreeToolbar.vue/useFeoTreeSearch.ts).
import { computed, ref, type Ref } from 'vue'
import { searchWords, matchesAllWords } from '@/utils/textSearch'

export interface DrillSearch<T> {
  /** Текст в поле поиска — v-model для DrillSearchField.vue. */
  query: Ref<string>
  /** Строки rows, прошедшие фильтр (или все rows, если запрос пуст). */
  filtered: Ref<T[]>
  /** Сколько строк показано после фильтра. */
  foundCount: Ref<number>
  /** Сколько строк всего (до фильтра). */
  totalCount: Ref<number>
  /** Σ amountOf(r) по отфильтрованным строкам — 0, если amountOf не передан. */
  foundAmount: Ref<number>
  /** Запрос не пуст — показывать строку «Найдено… / ничего не найдено». */
  isActive: Ref<boolean>
  /** Сбросить поле (вызывать при открытии окна — владелец: «при открытии
   *  окна query сбрасывается»). */
  reset: () => void
}

/**
 * rows — реактивный список строк окна (уже загруженных с сервера — этот
 * композабл ничего не грузит и не пересчитывает бизнес-показатели, только
 * текстовый фильтр уже готовых данных).
 * textOf — собирает ОДНУ строку для поиска из нужных полей строки (см.
 * frontend/src/components/drill/drillRowText.ts — там textOf для каждого
 * вида строк всех окон, Правило №6: одна функция на вид строки).
 * amountOf — опционально, для подписи «найдено … на сумму X».
 */
export function useDrillSearch<T>(
  rows: Ref<T[]>,
  textOf: (r: T) => string,
  amountOf?: (r: T) => number,
): DrillSearch<T> {
  const query = ref('')
  const words = computed(() => searchWords(query.value))
  const isActive = computed(() => words.value.length > 0)
  const filtered = computed<T[]>(() => {
    if (!words.value.length) return rows.value
    return rows.value.filter(r => matchesAllWords(textOf(r), words.value))
  })
  const totalCount = computed(() => rows.value.length)
  const foundCount = computed(() => filtered.value.length)
  const foundAmount = computed(() => amountOf ? filtered.value.reduce((s, r) => s + (amountOf(r) || 0), 0) : 0)
  function reset() { query.value = '' }
  return { query, filtered, foundCount, totalCount, foundAmount, isActive, reset }
}

/** Отфильтрованное дерево — узел FilteredTreeNode несёт только детей,
 *  прошедших фильтр (оставляет узлы с совпадением текста И их предков), плюс
 *  множество id узлов-предков для авто-раскрытия (владелец: «ветки
 *  раскрыты»). Используется там, где дерево строится обходом getChildren
 *  (а не группировкой готового плоского списка, как card='planned' в
 *  FeoCardDrillDialog.vue — там проще переиспользовать её же groupByDepth по
 *  уже отфильтрованному плоскому списку, см. докстринг этого файла сверху).
 */
export interface FilteredTreeNode<N> {
  node: N
  children: FilteredTreeNode<N>[]
}

export function filterTree<N>(
  nodes: N[],
  getChildren: (n: N) => N[] | undefined,
  getId: (n: N) => number | string,
  textOfNode: (n: N) => string,
  query: string,
): { nodes: FilteredTreeNode<N>[]; expandIds: Set<number | string> } {
  const words = searchWords(query)
  const expandIds = new Set<number | string>()
  if (!words.length) {
    // Без запроса — дерево целиком, раскрытие не навязываем (вызывающая
    // сторона решает сама, как и раньше).
    function wrapAll(list: N[]): FilteredTreeNode<N>[] {
      return list.map(n => ({ node: n, children: wrapAll(getChildren(n) ?? []) }))
    }
    return { nodes: wrapAll(nodes), expandIds }
  }

  function walk(list: N[]): FilteredTreeNode<N>[] {
    const out: FilteredTreeNode<N>[] = []
    for (const n of list) {
      const children = getChildren(n) ?? []
      const filteredChildren = children.length ? walk(children) : []
      const selfMatches = matchesAllWords(textOfNode(n), words)
      if (selfMatches || filteredChildren.length) {
        out.push({ node: n, children: filteredChildren })
        if (filteredChildren.length) expandIds.add(getId(n))
      }
    }
    return out
  }
  return { nodes: walk(nodes), expandIds }
}
