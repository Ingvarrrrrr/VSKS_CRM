// useItemsCatalog — product catalogue: load/search/filter, per-row catalog
// matching (product picker, inline match, full product create/edit dialog),
// category/type grouping of the items list and the "add uncatalogued selected
// items to catalog" bulk action. Extracted from PurchaseItemsEditor.vue
// (monolith refactor, часть 2).
import { ref, computed, reactive, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { MatchCandidate } from '@/composables/useItemMatching'
import type { PriceLink, ItemsDisplayRow } from '@/components/items/types'

// EditorItem/Product are structurally identical to the parent's; kept loose
// here (same convention as ItemsTableFlat.vue) since the parent owns the real
// shape and this composable only reads/writes the fields it uses.
type EditorItem = any
type Product = any

// Phase 17.1-08: prefer the bytea-backed /api/products/{id}/photo endpoint
// when the backend has a cached copy; fall back to external photo_url/link.
export function productPhotoSrc(p: Pick<Product, 'id' | 'has_photo' | 'photo_url' | 'photo_link'> | null | undefined): string | undefined {
  if (!p) return undefined
  if (p.has_photo) return `/api/products/${p.id}/photo`
  return p.photo_url || p.photo_link || undefined
}

export interface UseItemsCatalogDeps {
  props: { purchaseId?: number | null }
  localItems: Ref<EditorItem[]>
  selectedItemIdxs: Ref<number[]>
  emitUpdate: () => void
  emit: {
    (event: 'reload-requested'): void
    (event: 'product-created', product: Product): void
  }
  showSnack: (text: string, color?: string, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
  applyMatchCandidate: (row: EditorItem, cand: MatchCandidate) => void
  clearMatchBinding: (row: EditorItem) => void
  clearItem: (idx: number) => void
}

export function useItemsCatalog(deps: UseItemsCatalogDeps) {
  const { props, localItems, selectedItemIdxs, emitUpdate, emit, showSnack, applyMatchCandidate, clearMatchBinding, clearItem } = deps

  const products = ref<Product[]>([])

  async function loadProducts() {
    try {
      products.value = await apiFetch<Product[]>('/products/')
    } catch (e) {
      console.warn('[PurchaseItemsEditor] Could not load products:', e)
    }
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
  const hasUncatalogedSelected = computed(() =>
    selectedItemIdxs.value.some(idx => !localItems.value[idx]?.product_id)
  )
  const uncatalogedSelectedCount = computed(() =>
    selectedItemIdxs.value.filter(idx => !localItems.value[idx]?.product_id).length
  )

  const bulkAddCatalogLoading = ref(false)

  async function bulkAddToCatalog() {
    const uncatItems = selectedItemIdxs.value
      .map(idx => localItems.value[idx])
      .filter(it => it && !it.product_id && it.id)  // только сохранённые в БД (имеют id)
    if (!uncatItems.length) {
      showSnack('Выберите сохранённые позиции без привязки к каталогу', 'warning')
      return
    }
    bulkAddCatalogLoading.value = true
    try {
      const res = await apiFetch<{ created: number; linked: number; errors: string[] }>(
        '/products/bulk-from-purchase-items',
        { method: 'POST', body: JSON.stringify({ purchase_item_ids: uncatItems.map(it => it.id) }) }
      )
      showSnack(`Добавлено в каталог: ${res.created + res.linked}`, 'success')
      emit('reload-requested')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка добавления в каталог', 'error')
    } finally {
      bulkAddCatalogLoading.value = false
    }
  }

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

  function productItemsFor(search?: string): Product[] {
    const q = (search || '').toLowerCase().trim()
    if (!q) return products.value
    return products.value.filter(p => {
      const name = (p.name || '').toLowerCase()
      const desc = (p.description || '').toLowerCase()
      const type = (p.product_type || '').toLowerCase()
      return name.includes(q) || desc.includes(q) || type.includes(q)
    })
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
      item_type: val.product_type ?? null,
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

  // Fall back to the full product dialog for "create new" from inline match.
  function onInlineMatchCreateNew(idx: number) {
    const row = idx >= 0 ? localItems.value[idx] : null
    const prefillName = row?.item_name || ''
    const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
    openFullProduct(idx, prefillName, undefined, price)
  }

  // ── Product picker dialog ────────────────────────────────────────────────────

  const productPickerDialog = ref(false)
  const productPickerSearch = ref('')
  const productPickerIdx = ref(-1)

  const productPickerResults = computed(() => productItemsFor(productPickerSearch.value))

  function openProductPicker(idx: number) {
    productPickerIdx.value = idx
    productPickerSearch.value = localItems.value[idx]?.item_name || ''
    productPickerDialog.value = true
  }

  function selectFromPicker(prod: Product) {
    productPickerDialog.value = false
    onItemProductSelect(productPickerIdx.value, prod)
  }

  function createProductFromPicker() {
    productPickerDialog.value = false
    const idx = productPickerIdx.value
    const row = idx >= 0 ? localItems.value[idx] : null
    const price = row && row.unit_price != null && Number(row.unit_price) > 0 ? Number(row.unit_price) : undefined
    openFullProduct(idx, productPickerSearch.value, undefined, price)
  }

  // ── Full product dialog ───────────────────────────────────────────────────────

  const fullProductDialog = ref(false)
  const fullProductSaving = ref(false)
  const fullProductIdx = ref(-1)
  const fullProductEditingId = ref<number | null>(null)
  const fullProductPhotoFile = ref<File | null>(null)
  const fullProductPhotoFileList = ref<File[]>([])
  const fullProductPhotoPreview = ref<string | null>(null)
  const fullProductForm = reactive({
    name: '' as string,
    category: '',
    product_type: '',
    item_kind: 'товар' as string,
    price: null as number | null,
    description: '',
    photo_url: '',
    photo_link: '',
    is_active: true,
    priceLinks: [] as PriceLink[],
  })

  const fullProductNameSearch = ref('')
  const fullProductNameSuggestions = computed(() => {
    const q = (fullProductNameSearch.value || '').toLowerCase().trim()
    if (q.length < 2) return []
    return products.value
      .filter(p => p.name.toLowerCase().includes(q))
      .map(p => p.name)
      .slice(0, 15)
  })

  const isFullProductDuplicate = computed(() => {
    const q = (typeof fullProductForm.name === 'string' ? fullProductForm.name : '').toLowerCase().trim()
    if (!q) return false
    return products.value.some(p => p.name.toLowerCase().trim() === q)
  })

  const fullProductTypeOptions = computed(() => {
    const types = products.value.map(p => p.product_type).filter(Boolean) as string[]
    return [...new Set(types)].sort()
  })

  const fullProductCategoryOptions = computed(() => {
    const cats = products.value.map(p => p.category).filter(Boolean) as string[]
    return [...new Set(cats)].sort()
  })

  const fullAvgPrice = computed<number | null>(() => {
    const prices = fullProductForm.priceLinks
      .map(l => l.price)
      .filter((p): p is number => p !== null && !isNaN(Number(p)) && Number(p) > 0)
    if (!prices.length) return null
    return Math.round(prices.reduce((s, p) => s + p, 0) / prices.length * 100) / 100
  })

  watch(fullAvgPrice, v => { if (v !== null) fullProductForm.price = v })

  function onFullPhotoFileChange(files: File[] | File | null) {
    const fileArr = Array.isArray(files) ? files : (files ? [files] : [])
    const f = fileArr[0] ?? null
    fullProductPhotoFile.value = f
    fullProductPhotoPreview.value = f ? URL.createObjectURL(f) : null
  }

  function resetFullProductForm(prefill?: string) {
    Object.assign(fullProductForm, {
      name: prefill || '',
      category: '',
      product_type: '',
      item_kind: 'товар',
      price: null,
      description: '',
      photo_url: '',
      photo_link: '',
      is_active: true,
      priceLinks: [],
    })
    fullProductPhotoFile.value = null
    fullProductPhotoFileList.value = []
    fullProductPhotoPreview.value = null
  }

  function openFullProduct(idx: number, prefill?: string, productId?: number | null, prefillPrice?: number) {
    fullProductIdx.value = idx
    fullProductEditingId.value = null
    resetFullProductForm(prefill)
    if (!productId && prefillPrice != null && Number.isFinite(prefillPrice) && prefillPrice > 0) {
      fullProductForm.price = prefillPrice
    }
    fullProductDialog.value = true

    if (productId) {
      // Try cache first, then refetch fresh data so any backend-only fields are loaded
      const cached = products.value.find(p => p.id === productId)
      if (cached) populateFullProductFromProduct(cached)
      apiFetch<Product>(`/products/${productId}`)
        .then(p => populateFullProductFromProduct(p))
        .catch(() => { /* keep cached/prefill values */ })
    }
  }

  function populateFullProductFromProduct(p: Product) {
    fullProductEditingId.value = p.id
    Object.assign(fullProductForm, {
      name: p.name || '',
      category: p.category || '',
      product_type: p.product_type || '',
      item_kind: (p as any).item_kind || 'товар',
      price: p.price != null ? Number(p.price) : null,
      description: p.description || '',
      photo_url: p.photo_url || '',
      photo_link: p.photo_link || '',
      is_active: (p as any).is_active !== false,
      priceLinks: Array.isArray((p as any).price_links)
        ? (p as any).price_links.map((l: any) => ({ url: l.url || '', price: l.price ?? null }))
        : [],
    })
    fullProductPhotoPreview.value = productPhotoSrc(p) || null
  }

  function openQuickProductEdit(item: EditorItem) {
    const idx = localItems.value.indexOf(item)
    const price = !item.product_id && item.unit_price != null && Number(item.unit_price) > 0 ? Number(item.unit_price) : undefined
    openFullProduct(idx, item.item_name, item.product_id || undefined, price)
  }

  async function saveFullProduct() {
    const nameStr = typeof fullProductForm.name === 'string' ? fullProductForm.name : (fullProductForm.name as any)?.name || ''
    if (!nameStr.trim()) return
    fullProductSaving.value = true
    try {
      const body: any = {
        name: nameStr,
        category: (fullProductForm.category || '').trim(),
        product_type: fullProductForm.product_type || null,
        item_kind: fullProductForm.item_kind || 'товар',
        price: fullAvgPrice.value ?? fullProductForm.price ?? null,
        description: fullProductForm.description || null,
        photo_link: fullProductForm.photo_link || null,
        is_active: fullProductForm.is_active,
        price_links: fullProductForm.priceLinks.filter(l => l.url),
      }
      const isEdit = fullProductEditingId.value != null
      let saved: Product
      if (isEdit) {
        saved = await apiFetch<Product>(`/products/${fullProductEditingId.value}`, { method: 'PUT', body })
      } else {
        try {
          saved = await apiFetch<Product>('/products/', { method: 'POST', body })
        } catch (err: any) {
          // Backend detected a near-duplicate name → ask the user.
          // FastAPI's HTTPException(detail={...}) is wrapped by api.ts: the original
          // dict ends up at err.payload.message (apiFetch puts parsed.detail there).
          const detail = err?.payload?.message
          const existing = (err?.status === 409 && typeof detail === 'object' && detail?.code === 'duplicate_product')
            ? detail.existing : null
          if (existing) {
            const msg = `Похожий товар уже есть в каталоге:\n«${existing.name}»\n\nИспользовать его (ОК) или всё равно создать новый (Отмена)?`
            if (confirm(msg)) {
              saved = existing
            } else {
              saved = await apiFetch<Product>('/products/?force=true', { method: 'POST', body })
            }
          } else {
            throw err
          }
        }
      }
      // Upload photo if selected (works for both create and edit)
      if (fullProductPhotoFile.value) {
        const fd = new FormData()
        fd.append('file', fullProductPhotoFile.value)
        const token = localStorage.getItem('auth_token')
        const res = await fetch(`/api/products/${saved.id}/photo`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: fd,
        })
        if (res.ok) Object.assign(saved, await res.json())
      }
      products.value = await apiFetch<Product[]>('/products/')
      if (fullProductIdx.value >= 0) {
        onItemProductSelect(fullProductIdx.value, saved)
        // 27.4-14: моментальная запись привязки в БД (без ожидания общего «Сохранить»),
        // иначе после F5 product_id вернётся в null.
        const linkItem = localItems.value[fullProductIdx.value]
        if (props.purchaseId && (linkItem as any)?.id && saved.id) {
          try {
            await apiFetch(`/purchases/${props.purchaseId}/items/${(linkItem as any).id}/set-product`,
              { method: 'POST', body: { product_id: saved.id } })
          } catch (e) { console.warn('Failed to persist product_id link', e) }
        }
      }
      emit('product-created', saved)
      showSnack(isEdit ? `Товар "${saved.name}" обновлён` : `Товар "${saved.name}" добавлен в каталог`)
      fullProductDialog.value = false
      fullProductPhotoFile.value = null
      fullProductPhotoFileList.value = []
      fullProductPhotoPreview.value = null
    } catch {
      showSnack('Ошибка при добавлении товара', 'error')
    } finally {
      fullProductSaving.value = false
    }
  }

  return {
    products, loadProducts,
    itemsGroupBy, itemsFilterCats, itemsFilterTypes, productById, itemCategoryOf, itemTypeOf,
    itemCategoryOptions, itemTypeOptions, itemsFilterActive, itemsDisplayRows, visibleItemsCount,
    hasUncatalogedSelected, uncatalogedSelectedCount, bulkAddCatalogLoading, bulkAddToCatalog,
    productFilter, productItemsFor, hasProducts, onItemProductSelect,
    onInlineMatchPick, onInlineMatchClear, onInlineMatchCreateNew,
    productPickerDialog, productPickerSearch, productPickerIdx, productPickerResults,
    openProductPicker, selectFromPicker, createProductFromPicker,
    fullProductDialog, fullProductSaving, fullProductIdx, fullProductEditingId,
    fullProductPhotoFile, fullProductPhotoFileList, fullProductPhotoPreview, fullProductForm,
    fullProductNameSearch, fullProductNameSuggestions, isFullProductDuplicate,
    fullProductTypeOptions, fullProductCategoryOptions, fullAvgPrice,
    onFullPhotoFileChange, resetFullProductForm, openFullProduct, populateFullProductFromProduct,
    openQuickProductEdit, saveFullProduct,
  }
}
