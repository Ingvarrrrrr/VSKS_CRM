// useProductsData.ts — список товаров страницы «Товары»: серверный поиск/
// фильтры/пагинация/сортировка через GET /api/products/page (владелец,
// 26.10.2026 — каталог 54 тыс. строк, вырастет до 250+ тыс., полный список
// грузить нельзя). Серверный механизм — ОДИН на проект (ПРАВИЛО №6), см.
// useProductSearch.ts; useProductsForm.ts (подсказки по имени) и
// useItemsCatalog.ts (пикер товара в закупке) заводят свой экземпляр того же
// композабла, не второй механизм.
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { productPhotoSrc } from '@/utils/productPhoto'
import { useProductSearch, isSearchTooShort } from './useProductSearch'
import { useProductOptions } from './useProductOptions'
import { useStoreSearch } from './useStoreSearch'

// Белый список сортируемых колонок — зеркало SORTABLE_COLUMNS backend'а
// (app/services/product_search.py). Сортировка вне списка тут не нужна,
// т.к. все ключи ставит сама ProductsTable.vue по headers.key, но держим
// явную защиту, если @update:options придёт с незнакомым key.
const SORTABLE_KEYS = new Set(['name', 'category', 'product_type', 'price', 'price_updated_at', 'updated_at', 'id'])
const CARDS_PAGE_SIZE = 24

export function useProductsData(showSnack: (text: string, color?: ToastType) => void) {
  const { mobile } = useDisplay()

  const viewMode = ref<'table' | 'cards'>(
    (localStorage.getItem('products_view_mode') as 'table' | 'cards') || 'table',
  )
  watch(viewMode, v => localStorage.setItem('products_view_mode', v))
  const effectiveView = computed<'table' | 'cards'>(() => mobile.value ? 'cards' : viewMode.value)

  const searchApi = useProductSearch()
  const { items: products, total, totalCapped, loading } = searchApi

  // Счётчик «требует актуализации» — ОТДЕЛЬНЫЙ запрос GET
  // /api/products/stale-count (владелец, 26.10.2026, см. docstring
  // backend/app/services/product_stale_count_cache.py): раньше ехал внутри
  // КАЖДОГО /page и считался на каждое нажатие клавиши при поиске; теперь
  // грузится на открытии страницы и после актуализации цены (loadStaleCount()
  // ниже), не на каждый load().
  const staleTotal = ref(0)
  async function loadStaleCount() {
    try {
      const data = await apiFetch<{ stale_total: number }>('/products/stale-count')
      staleTotal.value = data.stale_total
    } catch {
      // Бейдж необязателен для работы страницы — молча оставляем прежнее значение.
    }
  }

  const search         = ref('')
  const filterType     = ref<string[]>([])
  const filterCategory = ref<string[]>([])
  const filterActive   = ref<boolean | null>(null)
  const filterPriceMin = ref<number | null>(null)
  const filterPriceMax = ref<number | null>(null)
  // Владелец, сессия 2026-08-29: «подсвечивать требующие актуализации» — быстрый
  // фильтр + счётчик, сколько таких товаров в каталоге прямо сейчас.
  const filterStaleOnly = ref(false)

  function resetFilters() {
    filterType.value = []
    filterCategory.value = []
    filterActive.value = null
    filterPriceMin.value = null
    filterPriceMax.value = null
    filterStaleOnly.value = false
  }

  // Опции фильтров «Категория»/«Тип» — по ВСЕМУ каталогу (GET /products/options),
  // НЕ из текущей страницы результатов (страница — выборка ≤200 строк, не
  // источник списка значений).
  const productOptions = useProductOptions()
  const typeOptions = computed(() => productOptions.types.value)
  const categoryOptions = computed(() => productOptions.categories.value)

  // ── Таблица: серверная пагинация/сортировка (v-data-table-server) ──────────
  const tablePage = ref(1)
  const tableItemsPerPage = ref(100)
  const tableSortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>([])

  // ── Карточки: пагинация по 24 тем же запросом ───────────────────────────────
  const cardsPage = ref(1)
  const cardsTotalPages = computed(() => Math.max(1, Math.ceil(total.value / CARDS_PAGE_SIZE)))

  // Эффективный поиск — короче MIN_SEARCH_CHARS (useProductSearch.ts, решение
  // владельца 26.10.2026) считается отсутствующим: список как при пустом поле
  // поиска, с фильтрами. Именно от ЭТОГО значения (не от search.value
  // напрямую) зависит перезагрузка списка ниже — иначе каждый символ в
  // диапазоне 1-2 (эффективно всё ещё «пусто») дёргал бы повторный запрос.
  const effectiveSearch = computed(() => isSearchTooShort(search.value) ? '' : search.value.trim())

  // v-model.number на <v-text-field type="number"> (ProductsFilterBar.vue)
  // после стирания значения отдаёт '' (не null) — ".number" не приводит
  // пустую строку к числу. Без нормализации '' шло на сервер буквально
  // (price_min=) → 422 «Ошибка загрузки» (владелец, 29.10.2026, QA на
  // проде). ОДНО место (Правило №6) — здесь и в useProductSearch.ts::
  // buildQuery (двойная защита: здесь на входе в фильтры, там — на сборке
  // query, на случай другого вызывающего той же ручки).
  function normalizePriceFilter(v: unknown): number | null {
    if (v === '' || v === null || v === undefined) return null
    const n = typeof v === 'number' ? v : Number(v)
    return Number.isFinite(n) ? n : null
  }

  function filterParams() {
    return {
      search: effectiveSearch.value,
      category: filterCategory.value,
      productType: filterType.value,
      isActive: filterActive.value,
      priceMin: normalizePriceFilter(filterPriceMin.value),
      priceMax: normalizePriceFilter(filterPriceMax.value),
      staleOnly: filterStaleOnly.value,
    }
  }

  // sort/order НЕ возвращаются (undefined), если пользователь НЕ выбрал
  // колонку сортировки явно (тогда tableSortBy пуст — так и приходит из
  // v-data-table-server::update:options, пока по заголовку не кликнули) —
  // backend (ProductSearchFilters.sort=None) отличает «умолчание» от
  // «выбрано name asc» (владелец, 29.10.2026, QA на проде: раньше default
  // всегда был {sort:'name',order:'asc'}, из-за чего при search сортировка
  // по релевантности ВСЕГДА перезаписывалась бы, если бы backend её
  // применял буквально — теперь явный выбор отличим).
  function activeSort(): { sort?: string; order?: 'asc' | 'desc' } {
    const s = tableSortBy.value[0]
    if (s && SORTABLE_KEYS.has(s.key)) return { sort: s.key, order: s.order }
    return {}
  }

  async function loadTable() {
    const { sort, order } = activeSort()
    const limit = tableItemsPerPage.value === -1 ? 200 : tableItemsPerPage.value
    const offset = tableItemsPerPage.value === -1 ? 0 : (tablePage.value - 1) * tableItemsPerPage.value
    const res = await searchApi.load({ ...filterParams(), sort, order, limit, offset })
    if (res === null) return // отменён более новым запросом — не показываем ошибку
  }

  async function loadCards() {
    // Без sort (владелец, 29.10.2026, задание п.B: «карточки — без sort») —
    // карточки не дают пользователю выбрать колонку, умолчание backend'а
    // (name asc без search / релевантность с search) — то же самое,
    // чего карточки раньше добивались явным {sort:'name',order:'asc'},
    // но без ослепления сортировкой лестницы поиска при непустом search.
    await searchApi.load({
      ...filterParams(),
      limit: CARDS_PAGE_SIZE,
      offset: (cardsPage.value - 1) * CARDS_PAGE_SIZE,
    })
  }

  async function load() {
    try {
      if (effectiveView.value === 'table') await loadTable()
      else await loadCards()
    } catch {
      showSnack('Ошибка загрузки', 'error')
    }
  }

  // Живой поиск в магазинах (этап 1, владелец, 28.10.2026; правка владельца
  // 28.10.2026 «вторая волна»: авто-запуск только когда total===0 И
  // querySpecific===true — т.е. в разборе фразы backend'ом нашёлся бренд/
  // модель/величина, не только широкий вид товара типа «огнетушитель»; иначе
  // — только кнопка, см. ProductsView.vue). Тот же useStoreSearch.ts, что и у
  // ProductPickerDialog.vue (ПРАВИЛО №6, второй механизм не заводим). В
  // каталог НИЧЕГО не пишем (этап 2).
  const storeSearch = useStoreSearch()
  function runStoreSearch() {
    void storeSearch.search(effectiveSearch.value)
  }

  // Не чаще одного авто-запуска на один и тот же текст (не на каждый
  // ререндер/каждое совпадение total===0 при неизменном запросе) — текст,
  // для которого авто-запуск уже случился.
  let lastAutoStoreQuery: string | null = null
  function maybeAutoTriggerStoreSearch(resultTotal: number, querySpecific: boolean) {
    const text = effectiveSearch.value
    if (resultTotal === 0 && querySpecific && text && lastAutoStoreQuery !== text) {
      lastAutoStoreQuery = text
      runStoreSearch()
    }
  }

  // Текстовый поиск — debounce 300 мс (внутри useProductSearch.loadDebounced,
  // теперь возвращает промис результата, см. docstring там) — авто-запуск в
  // магазины решается ИМЕННО по результату этого ответа базы (после паузы
  // ввода и реального ответа, не раньше), второй дебаунс не заводим.
  // Остальные фильтры/сортировка/страница — сразу: владелец ждёт отклика на
  // клик по чекбоксу/селекту, не только на ввод в текстовое поле (и там
  // авто-запуск в магазины НЕ нужен — только по изменению самого текста).
  async function loadSearchDebounced() {
    const { sort, order } = activeSort()
    const result = effectiveView.value === 'table'
      ? await searchApi.loadDebounced({
          ...filterParams(), sort, order,
          limit: tableItemsPerPage.value === -1 ? 200 : tableItemsPerPage.value, offset: 0,
        })
      : await searchApi.loadDebounced({
          ...filterParams(), limit: CARDS_PAGE_SIZE, offset: 0,
        })
    if (!result) return // отменено более новым запросом (гонка/новый ввод) — не решаем по устаревшему ответу
    maybeAutoTriggerStoreSearch(result.total, result.querySpecific)
  }

  watch(effectiveSearch, () => {
    tablePage.value = 1
    cardsPage.value = 1
    storeSearch.reset()
    void loadSearchDebounced()
  })
  watch([filterType, filterCategory, filterActive, filterPriceMin, filterPriceMax, filterStaleOnly], () => {
    tablePage.value = 1
    cardsPage.value = 1
    void load()
  })
  watch(effectiveView, () => { void load() })

  // v-data-table-server::update:options — один объединённый обработчик
  // страницы/размера страницы/сортировки (стандартный паттерн проекта, см.
  // useVehicleListData.ts::onTableOptions).
  function onTableOptions(opts: { page: number; itemsPerPage: number; sortBy: { key: string; order: string }[] }) {
    tablePage.value = opts.page
    tableItemsPerPage.value = opts.itemsPerPage
    tableSortBy.value = (opts.sortBy || []).map(s => ({ key: s.key, order: s.order === 'desc' ? 'desc' : 'asc' }))
    void loadTable().catch(() => showSnack('Ошибка загрузки', 'error'))
  }

  function onCardsPage(p: number) {
    cardsPage.value = p
    void loadCards().catch(() => showSnack('Ошибка загрузки', 'error'))
  }

  const staleProductsCount = computed(() => staleTotal.value)

  // Единый источник — utils/productPhoto.ts (ПРАВИЛО №6): отсекает мусорные
  // значения photo_link вроде «НЕ смог найти», оставшиеся от Excel-импорта.
  const cardPhotoSrc = productPhotoSrc

  return {
    products, loading, total, totalCapped,
    search, filterType, filterCategory, filterActive, filterPriceMin, filterPriceMax, filterStaleOnly,
    resetFilters, load,
    typeOptions, categoryOptions, staleProductsCount, loadStaleCount,
    loadProductOptions: productOptions.load,
    mobile, viewMode, effectiveView,
    tablePage, tableItemsPerPage, tableSortBy, onTableOptions,
    cardsPage, cardsTotalPages, onCardsPage,
    cardPhotoSrc,
    storeSearch, runStoreSearch,
  }
}
