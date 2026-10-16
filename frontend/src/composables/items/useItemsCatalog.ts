// useItemsCatalog — product catalogue: load/search/filter, per-row catalog
// matching (product picker, inline match), category/type grouping of the
// items list and the "add uncatalogued selected items to catalog" bulk
// action. Extracted from PurchaseItemsEditor.vue (monolith refactor, часть 2).
//
// Создание/правка товара — ЕДИНОЕ окно (components/products/
// ProductEditorDialog.vue, ПРАВИЛО №6, владелец 14.10): раньше здесь жила
// урезанная копия (fullProductForm/openFullProduct/saveFullProduct) — убрана,
// открытие окна теперь у владельца ref'а (PurchaseItemsEditor.vue) через
// deps.openProductEditor.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { ItemsDisplayRow } from '@/components/items/types'
import type { ToastType } from '@/composables/useToast'
import { productPhotoSrc } from '@/utils/productPhoto'
import { matchesAllWords, normalizeSearchText, searchWords } from '@/utils/textSearch'

// EditorItem/Product are structurally identical to the parent's; kept loose
// here (same convention as ItemsTableFlat.vue) since the parent owns the real
// shape and this composable only reads/writes the fields it uses.
type EditorItem = any
type Product = any

// productPhotoSrc — реэкспорт единого источника (utils/productPhoto.ts,
// ПРАВИЛО №6) ради обратной совместимости: PurchaseItemsEditor.vue и другие
// файлы уже импортируют его отсюда (`import { productPhotoSrc } from
// '@/composables/items/useItemsCatalog'`) — переносить все call-site'ы ради
// одной строки риска не стоит, логика теперь в одном месте.
export { productPhotoSrc }

export interface UseItemsCatalogDeps {
  props: { purchaseId?: number | null; isWishStage?: boolean }
  localItems: Ref<EditorItem[]>
  selectedItemIdxs: Ref<number[]>
  emitUpdate: () => void
  emit: {
    (event: 'reload-requested'): void
    (event: 'product-created', product: Product): void
  }
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
  applyMatchCandidate: (row: EditorItem, cand: MatchCandidate) => void
  clearMatchBinding: (row: EditorItem) => void
  clearItem: (idx: number) => void
  // Открыть ЕДИНОЕ окно товара (components/products/ProductEditorDialog.vue,
  // ПРАВИЛО №6) — владеет сама PurchaseItemsEditor.vue (там живёт ref на
  // диалог и привязка выбранного товара к строке/set-product). Композабл
  // только просит открыть его с предзаполнением, когда «Создать новый
  // товар» нажали из пикера/инлайн-подбора. `mode` — тот же режим, что у
  // пикера (openProductPicker), чтобы после сохранения нового товара
  // PurchaseItemsEditor.vue знал, привязывать ли его как обычно (имя+цена)
  // или только привязку (режим «repick», владелец 16.10.2026).
  openProductEditor: (idx: number, prefill?: string, productId?: number | null, prefillPrice?: number, mode?: 'normal' | 'repick') => void
}

export function useItemsCatalog(deps: UseItemsCatalogDeps) {
  const { props, localItems, selectedItemIdxs, emitUpdate, emit, showSnack, applyMatchCandidate, clearMatchBinding, clearItem, openProductEditor } = deps

  const products = ref<Product[]>([])
  // Перф (владелец, 27.09.2026, «закупка грузится 10 сек»): GET /api/products/
  // без ids отдаёт ВЕСЬ каталог (≈4,4 МБ JSON, ~800 КБ gzip) — на карточке
  // закупки открытие грузило его дважды (см. лог nginx). fullCatalogLoaded
  // гейтит ленивую ОДНОКРАТНУю догрузку полного каталога (ensureFullCatalog)
  // — только когда реально нужен (пикер товара / диалог «новый товар из
  // каталога»), не на каждое открытие карточки.
  const fullCatalogLoaded = ref(false)
  let _fullCatalogPromise: Promise<void> | null = null

  async function loadProducts() {
    try {
      // Перф (координатор, сессия 2026-09-20, находка «каталог грузится
      // ДВАЖДЫ при открытии заявки», расширено 27.09.2026 на закупку —
      // владелец: «закупки грузятся долго... GET /api/products/ ДВАЖДЫ подряд,
      // ≈4,4 МБ»): PurchaseItemsEditor.vue::onMounted зовёт loadProducts()
      // БЕЗУСЛОВНО при открытии ЛЮБОЙ карточки (заявка И закупка) — грузить
      // ВЕСЬ каталог тут незачем: подбор товара идёт через InlineProductMatch.vue
      // (свой POST /products/match, эту ref не читает), а строки уже несут
      // product_id. Грузим только уже привязанные товары — по id, тем же
      // контрактом (`/products/?ids=`), что и useWishActions.ts/
      // usePurchaseSplit.ts. Вторичные фичи каталога (группировка по
      // категории/типу для ещё НЕ привязанных строк, подсказки в диалоге
      // «Новый товар из каталога», productPickerDialog fallback-список) при
      // этом видят суженный products ДО первого обращения — см.
      // ensureFullCatalog(), которую они дозывают сами (openProductPicker/
      // openFullProduct) при реальной необходимости.
      const ids = [...new Set(
        (localItems.value as any[])
          .map((it) => it?.product_id)
          .filter((id): id is number => id != null)
      )]
      products.value = ids.length ? await apiFetch<Product[]>(`/products/?ids=${ids.join(',')}`) : []
    } catch (e) {
      console.warn('[PurchaseItemsEditor] Could not load products:', e)
    }
  }

  // Догружает ПОЛНЫЙ каталог ОДИН раз за время жизни компонента (не на каждый
  // вызов пикера/диалога) — общий промис не даёт двум одновременным вызовам
  // (например, клик по строке во время ещё не отрисованного диалога) уйти в
  // две параллельные загрузки одного и того же (тот же паттерн дедупа, что и
  // в api.ts для инфлайт-запросов, но здесь нужен персистентный флаг, а не
  // разовый).
  function ensureFullCatalog(): Promise<void> {
    if (fullCatalogLoaded.value) return Promise.resolve()
    if (_fullCatalogPromise) return _fullCatalogPromise
    _fullCatalogPromise = apiFetch<Product[]>('/products/')
      .then(list => {
        products.value = list
        fullCatalogLoaded.value = true
      })
      .catch(e => {
        console.warn('[PurchaseItemsEditor] Could not load full catalog:', e)
      })
      .finally(() => { _fullCatalogPromise = null })
    return _fullCatalogPromise
  }

  // ── Группировка/фильтр позиций по категории и виду товара из каталога ────────
  // Категория/вид берутся у сматченного товара (product_id → products); позиции
  // без товара попадают в «Без категории»/«Без вида». Строки данных ссылаются на
  // ОРИГИНАЛЬНЫЙ индекс в localItems, поэтому все idx-события работают как раньше.
  const NO_CATEGORY = 'Без категории'
  const NO_TYPE = 'Без вида'
  const itemsGroupBy = ref<'none' | 'category' | 'category_type'>('none')
  const itemsFilterCats = ref<string[]>([])
  const itemsFilterTypes = ref<string[]>([])

  const productById = computed(() => {
    const m = new Map<number, Product>()
    for (const p of products.value) m.set(p.id, p)
    return m
  })
  function itemCategoryOf(it: EditorItem): string {
    const p = it.product_id != null ? productById.value.get(it.product_id) : undefined
    return (p?.category || '').trim() || ((it as any)._category || '').trim() || NO_CATEGORY
  }
  function itemTypeOf(it: EditorItem): string {
    const p = it.product_id != null ? productById.value.get(it.product_id) : undefined
    return (p?.product_type || '').trim() || ((it as any)._product_type || '').trim() || NO_TYPE
  }
  const itemCategoryOptions = computed(() => {
    const s = new Set(localItems.value.map(itemCategoryOf))
    return [...s].sort((a, b) => a.localeCompare(b, 'ru'))
  })
  const itemTypeOptions = computed(() => {
    const cats = itemsFilterCats.value
    const s = new Set(
      localItems.value
        .filter(it => !cats.length || cats.includes(itemCategoryOf(it)))
        .map(itemTypeOf)
    )
    return [...s].sort((a, b) => a.localeCompare(b, 'ru'))
  })
  const itemsFilterActive = computed(() =>
    itemsFilterCats.value.length > 0 || itemsFilterTypes.value.length > 0
  )

  const itemsDisplayRows = computed<ItemsDisplayRow[] | null>(() => {
    // null → дети рендерят natural order без каких-либо изменений (быстрый путь)
    if (itemsGroupBy.value === 'none' && !itemsFilterActive.value) return null
    const rows = localItems.value
      .map((item, idx) => ({
        idx,
        cat: itemCategoryOf(item),
        type: itemTypeOf(item),
        sum: Number(item.total_price || 0),
      }))
      .filter(r =>
        (!itemsFilterCats.value.length || itemsFilterCats.value.includes(r.cat)) &&
        (!itemsFilterTypes.value.length || itemsFilterTypes.value.includes(r.type))
      )
    if (itemsGroupBy.value === 'none') return rows.map(r => ({ idx: r.idx }))
    rows.sort((a, b) =>
      a.cat.localeCompare(b.cat, 'ru') ||
      a.type.localeCompare(b.type, 'ru') ||
      a.idx - b.idx
    )
    const out: ItemsDisplayRow[] = []
    let curCat: string | null = null
    let curType: string | null = null
    for (const r of rows) {
      if (r.cat !== curCat) {
        curCat = r.cat
        curType = null
        const grp = rows.filter(x => x.cat === r.cat)
        out.push({ header: r.cat, level: 1, count: grp.length, sum: grp.reduce((s, x) => s + x.sum, 0) })
      }
      if (itemsGroupBy.value === 'category_type' && r.type !== curType) {
        curType = r.type
        const grp = rows.filter(x => x.cat === r.cat && x.type === r.type)
        out.push({ header: r.type, level: 2, count: grp.length, sum: grp.reduce((s, x) => s + x.sum, 0) })
      }
      out.push({ idx: r.idx })
    }
    return out
  })
  const visibleItemsCount = computed(() =>
    itemsDisplayRows.value == null
      ? localItems.value.length
      : itemsDisplayRows.value.filter(r => r.idx != null).length
  )

  // ── import-no-clutter: bulk-add несвязанных позиций в каталог ────────────────
  // Сам процесс (открытие ЕДИНОГО окна товара по очереди) — отдельный файл
  // composables/items/useBulkProductCreateQueue.ts (ПРАВИЛО №5/№6, владелец
  // 14.10) — раньше здесь был один POST /products/bulk-from-purchase-items
  // без общей формы (эндпоинт оставлен на бэкенде, фронт его больше не зовёт).
  const hasUncatalogedSelected = computed(() =>
    selectedItemIdxs.value.some(idx => !localItems.value[idx]?.product_id)
  )
  const uncatalogedSelectedCount = computed(() =>
    selectedItemIdxs.value.filter(idx => !localItems.value[idx]?.product_id).length
  )

  // ── Product selection ────────────────────────────────────────────────────────

  const productFilter = (_value: string, query: string, item?: any): boolean => {
    if (!query.trim()) return true
    const q = query.toLowerCase().trim()
    const name = (item?.raw?.name || '').toLowerCase()
    const desc = (item?.raw?.description || '').toLowerCase()
    const type = (item?.raw?.product_type || '').toLowerCase()
    return name.includes(q) || desc.includes(q) || type.includes(q)
  }
  // Keep productFilter available but it's not used directly in this component's template
  void productFilter

  // Слова в любом порядке (utils/textSearch.ts — один алгоритм на проект).
  // Владелец 16.10.2026: окно привязки открывается с полным названием позиции
  // («Бинт марлевый стерильный 7 м х 14 см.») и показывало «Ничего не найдено»,
  // пока не сотрёшь лишнее. Если все слова разом не нашлись — показываем
  // товары, где совпало больше всего значимых слов (от 3 букв), лучшие сверху.
  function productItemsFor(search?: string): Product[] {
    const words = searchWords(search)
    if (!words.length) return products.value
    const text = (p: Product) => `${p.name || ''} ${p.description || ''} ${p.product_type || ''}`
    const exact = products.value.filter(p => matchesAllWords(text(p), words))
    if (exact.length) return exact
    const significant = words.filter(w => w.length >= 3)
    if (significant.length < 2) return exact
    return products.value
      .map(p => {
        const t = normalizeSearchText(text(p))
        return { p, hits: significant.filter(w => t.includes(w)).length }
      })
      .filter(r => r.hits > 0)
      .sort((a, b) => b.hits - a.hits)
      .slice(0, 60)
      .map(r => r.p)
  }

  const hasProducts = computed(() => products.value.length > 0)
  void hasProducts

  function onItemProductSelect(idx: number, val: any) {
    const item = localItems.value[idx]
    if (!val) {
      clearMatchBinding(item)
      item._description_44fz = undefined
      ;(item as any).match_confirmed = true
      emitUpdate()
      return
    }
    if (typeof val === 'string') {
      item.item_name = val
      item.product_id = null
      item._selectedProduct = val
      item._photo_url = undefined
      item._description = undefined
      item._description_44fz = undefined
      item._price_meta = null
      ;(item as any).match_confirmed = true
      emitUpdate()
      return
    }
    // Catalog Product object → apply via shared matching logic.
    applyMatchCandidate(item as any, {
      product_id: val.id,
      name: val.name || '',
      price: val.price ?? null,
      score: 1,
      description: val.description ?? null,
      photo_url: productPhotoSrc(val) ?? null,
      // ПРАВИЛО №6 / баг 2026-10-01: тип позиции — ЕДИНСТВЕННО из Product.item_kind
      // (бэк — app.services.item_types), не из product_type («Вид» — свободный
      // текст, к типу товар/услуга/работа отношения не имеет).
      item_type: val.item_kind ?? null,
      contract_price: val.contract_price ?? null,
      price_updated_at: val.price_updated_at ?? null,
      price_source: val.price_source ?? null,
      price_source_ref: val.price_source_ref ?? null,
      price_freshness: val.price_freshness ?? null,
    })
    item._description_44fz = val.description_44fz || undefined
    emitUpdate()
  }

  // ── BUG #5: inline per-row catalog matching ──────────────────────────────────
  // InlineProductMatch emits a chosen candidate; apply it without opening a dialog.
  function onInlineMatchPick(idx: number, candidate: MatchCandidate) {
    const item = localItems.value[idx]
    if (!item) return
    applyMatchCandidate(item as any, candidate)
    emitUpdate()
  }

  function onInlineMatchClear(idx: number) {
    clearItem(idx)
  }

  // Fall back to the единое окно товара for "create new" from inline match.
  function onInlineMatchCreateNew(idx: number) {
    const row = idx >= 0 ? localItems.value[idx] : null
    const prefillName = row?.item_name || ''
    const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
    openProductEditor(idx, prefillName, undefined, price)
  }

  // ── Product picker dialog ────────────────────────────────────────────────────

  const productPickerDialog = ref(false)
  const productPickerSearch = ref('')
  const productPickerIdx = ref(-1)
  // Режим окна (владелец, 16.10.2026, «Изменить привязку к каталогу»):
  // 'normal' — обычный выбор товара в наименование (как раньше, через
  // onItemProductSelect — перезаписывает имя/цену строки); 'repick' —
  // кнопка-скрепка в позиции, меняет ТОЛЬКО product_id, имя/цена/количество
  // позиции не трогаются (см. bindProductToItem). Общее окно
  // components/items/ProductPickerDialog.vue теперь одно на оба режима
  // (ПРАВИЛО №6) — отдельный SingleProductPickerDialog.vue убран.
  const pickerMode = ref<'normal' | 'repick'>('normal')
  const pickerTitle = computed(() =>
    pickerMode.value === 'repick' ? 'Изменить привязку к каталогу' : 'Выбрать товар из каталога'
  )

  const productPickerResults = computed(() => productItemsFor(productPickerSearch.value))

  function openProductPicker(idx: number, mode: 'normal' | 'repick' = 'normal') {
    pickerMode.value = mode
    productPickerIdx.value = idx
    productPickerSearch.value = localItems.value[idx]?.item_name || ''
    productPickerDialog.value = true
    // Пикер ищет по ВСЕМУ каталогу (productItemsFor фильтрует products.value
    // целиком) — догружаем его тут, не на mount карточки.
    void ensureFullCatalog()
  }

  // Кнопка-скрепка «Изменить привязку к каталогу» у позиции — тот же пикер,
  // но в режиме repick (ItemsTableStages.vue::open-repick-dialog).
  function openRepickPicker(idx: number) {
    openProductPicker(idx, 'repick')
  }

  // Привязка СУЩЕСТВУЮЩЕГО товара каталога к позиции без перезаписи
  // наименования/цены/количества строки (владелец 16.10.2026: окно привязки
  // раньше молча ничего не предлагало, но даже при выборе трогать саму
  // позицию не нужно — только её product_id). В отличие от onItemProductSelect
  // (обычный выбор товара в колонке наименования), который через
  // applyMatchCandidate перезаписывает item_name/unit_price/total_price.
  function bindProductToItem(idx: number, prod: Product) {
    const item = localItems.value[idx]
    if (!item) return
    item.product_id = prod.id
    item._selectedProduct = prod
    item._photo_url = productPhotoSrc(prod) ?? undefined
    item._description = prod.description ?? undefined
    item._price_meta = {
      price_updated_at: prod.price_updated_at ?? null,
      price_source: prod.price_source ?? null,
      price_source_ref: prod.price_source_ref ?? null,
      price_freshness: prod.price_freshness ?? null,
    }
    item.match_confirmed = true
    emitUpdate()
  }

  function selectFromPicker(prod: Product) {
    productPickerDialog.value = false
    const idx = productPickerIdx.value
    if (pickerMode.value === 'repick') {
      bindProductToItem(idx, prod)
      showSnack(`Товар перепривязан: ${prod.name}`, 'success')
      return
    }
    onItemProductSelect(idx, prod)
  }

  function createProductFromPicker() {
    productPickerDialog.value = false
    const idx = productPickerIdx.value
    const row = idx >= 0 ? localItems.value[idx] : null
    const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
    openProductEditor(idx, productPickerSearch.value, undefined, price, pickerMode.value)
  }

  return {
    products, loadProducts, ensureFullCatalog, fullCatalogLoaded,
    itemsGroupBy, itemsFilterCats, itemsFilterTypes, productById, itemCategoryOf, itemTypeOf,
    itemCategoryOptions, itemTypeOptions, itemsFilterActive, itemsDisplayRows, visibleItemsCount,
    hasUncatalogedSelected, uncatalogedSelectedCount,
    productFilter, productItemsFor, hasProducts, onItemProductSelect,
    onInlineMatchPick, onInlineMatchClear, onInlineMatchCreateNew,
    productPickerDialog, productPickerSearch, productPickerIdx, productPickerResults,
    pickerMode, pickerTitle, bindProductToItem,
    openProductPicker, openRepickPicker, selectFromPicker, createProductFromPicker,
  }
}
