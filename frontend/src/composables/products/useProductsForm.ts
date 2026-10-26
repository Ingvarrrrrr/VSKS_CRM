// useProductsForm.ts — диалог добавления/редактирования товара: форма, фото,
// ссылки для сравнения цен, автоподсказки по названию. Дословный перенос из
// ProductsView.vue.
import { ref, computed, reactive, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import { describeApiError } from '@/utils/apiErrorMessage'
import { isPackUnit } from '@/utils/units'
import { postPriceHistoryEntry } from './useProductPriceHistory'
import type { DraftPriceEntry } from './useProductPriceHistory'
import type { Product, PriceLink } from './productsTypes'
import { useProductSearch, isSearchTooShort } from './useProductSearch'

export function useProductsForm(options: {
  products: { value: Product[] }
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
  // Опциональный колбэк — товар только что создан/обновлён и сохранён в общий
  // каталог (POST/PUT /products/, как обычно). Единственный текущий
  // потребитель композабла — ProductsView.vue — колбэк не передаёт, поведение
  // не меняется. Добавлен для «Добавить товар» в PlanToRequestRow.vue: после
  // сохранения строка заявки подставляет товар как выбранного кандидата, не
  // заводя второй механизм создания (Правило №6).
  onSaved?: (product: Product) => void
}) {
  const { products, load, showSnack, onSaved } = options

  const saving = ref(false)
  const dialog = ref(false)
  const editingId = ref<number | null>(null)

  // Дубликат по имени при создании (409 duplicate_product, backend —
  // threshold=0.7) — раньше это решалось window.confirm() в двух разных
  // местах (useItemsCatalog.ts::saveFullProduct, PlannedItemAddDialog.vue).
  // Единственный источник теперь здесь (ПРАВИЛО №6) — все вызовы save()
  // (каталог, ProductEditorDialog, PlanToRequestRow и т.д.) получают один и
  // тот же выбор «Использовать существующий / Создать новый», отрисованный
  // диалогом внутри ProductFormDialog.vue (без window.confirm).
  const duplicateDialog = ref(false)
  const duplicateExisting = ref<Product | null>(null)
  let pendingPayload: any = null

  // Пункт 8 (владелец, 14.10, баг «добавил цену в блоке "Цены" — она не
  // сохранилась»): блок «Цены» (PurchasePriceHistory.vue::addEntry/
  // removeEntry) меняет Product.price на сервере СВОИМ путём. Если «Сохранить»
  // всё равно шлёт PUT со старым form.price, backend::update_product видит
  // price != old_price и actualize_product_price перетирает цену обратно
  // (и теряет только что добавленную ссылку/источник). origPrice — цена,
  // загруженная с сервера (openEdit) либо подтверждённая блоком «Цены»
  // (price-synced) — save() шлёт price в PUT ТОЛЬКО если form.price от неё
  // отличается, т.е. пользователь реально поправил поле вручную.
  const origPrice = ref<number | null>(null)
  function syncPriceFromHistory(price: number | null) {
    form.price = price
    origPrice.value = price
  }

  // Часть 1 плана clever-bouncing-lantern.md (владелец 14.10.2026): без
  // products.edit_catalog можно заполнить ПУСТОЕ поле существующего товара
  // (описание/описание 44-ФЗ/фото/цена), но не заменить уже заполненное —
  // «пусто» фиксируется В МОМЕНТ ОТКРЫТИЯ карточки (openEdit), а не текущим
  // значением формы (иначе пользователь мог бы стереть поле локально и
  // получить право его «заполнить» заново). ProductFormDialog.vue читает
  // этот снэпшот, backend — единственный источник правды (PUT/PATCH всё
  // равно пере-проверит, см. product_catalog_guard.py, ПРАВИЛО №6).
  const emptyAtOpen = reactive({
    description: true,
    description_44fz: true,
    price: true,
    photo: true,
  })

  // Photo upload state
  const photoFile     = ref<File | null>(null)
  const photoFileList = ref<File[]>([])
  const photoPreview  = ref<string | null>(null)

  const emptyForm = () => ({
    name: '', category: '', product_type: '', unit: '' as string, item_kind: 'товар' as string, price: null as number | null,
    // Упаковка (владелец, 14.10) — поля показываются в форме только при
    // isPackUnit(unit) (см. ProductFormDialog.vue), очищаются при save()
    // ниже, если unit перестал быть упаковочным.
    pack_quantity: null as number | null,
    pack_unit: '' as string,
    // Пункт 2 (владелец, 14.10) — черновые цены, введённые ДО первого
    // сохранения товара (PurchasePriceHistory.vue::addEntry при productId=null).
    // Отправляются после создания товара, см. flushPendingPrices ниже.
    pendingPrices: [] as DraftPriceEntry[],
    description: '', description_44fz: '', photo_url: '', photo_link: '', clarification_link: '',
    is_active: true, is_reusable: true, feo_category_id: null as number | null,
    priceLinks: [] as PriceLink[],
    // Категории закупки (справочник, решение владельца 2026-09-16, п.1) —
    // отдельно от свободнотекстового category выше.
    purchase_category_ids: [] as number[],
    country_origin: 'РФ' as string,
    has_photo: false as boolean,
    price_ttl_days: null as number | null,
    // Характеристики каталога (владелец, 26.10) — список GET /products/ их не
    // отдаёт (тяжёлый JSONB, карточка догружает отдельным запросом, см.
    // openEdit ниже), поэтому в пустой форме — пустое значение по умолчанию.
    characteristics: null as Product['characteristics'],
    manufacturer: '' as string,
    article: '' as string,
  })
  const form = reactive(emptyForm())
  // Bumped when we re-download / re-upload so the <img> bypasses browser cache.
  const photoCacheBuster = ref(0)
  const editMeta = reactive({ updated_at: null as string | null, updated_by: null as string | null, import_note: null as string | null })

  // Name autocomplete + duplicate detection — серверный поиск по ИМЕНИ
  // (ПРАВИЛО №6, тот же механизм useProductSearch.ts, что у страницы «Товары»/
  // пикера товара), не products.value: каталог 54 тыс. строк, вырастет до
  // 250+ тыс. — products.value теперь ТЕКУЩАЯ СТРАНИЦА списка (≤200 строк),
  // искать по ней подстроку означало бы почти всегда «ничего не найдено»
  // (владелец, 26.10.2026). Финальная защита от дублей всё равно на backend
  // (409 duplicate_product при save(), см. ниже) — это только живая подсказка.
  const nameSearch = ref('')
  const nameSearchApi = useProductSearch({ debounceMs: 250 })
  watch(nameSearch, (q) => {
    if (isSearchTooShort(q)) { nameSearchApi.items.value = []; return }
    nameSearchApi.loadDebounced({ search: (q || '').trim(), limit: 15 })
  })
  const nameSuggestions = computed(() => {
    if (isSearchTooShort(nameSearch.value)) return []
    return nameSearchApi.items.value
      .filter(p => p.id !== editingId.value)
      .map(p => p.name)
      .slice(0, 15)
  })
  const isDuplicateName = computed(() => {
    if (!form.name) return false
    const q = (typeof form.name === 'string' ? form.name : '').toLowerCase().trim()
    if (!q) return false
    return nameSearchApi.items.value.some(p => p.name.toLowerCase().trim() === q && p.id !== editingId.value)
  })

  // Auto-calculate average price from links
  const avgPrice = computed<number | null>(() => {
    const prices = form.priceLinks
      .map(l => l.price)
      .filter((p): p is number => p !== null && p !== undefined && !isNaN(Number(p)) && Number(p) > 0)
    if (prices.length === 0) return null
    return Math.round(prices.reduce((s, p) => s + p, 0) / prices.length * 100) / 100
  })

  watch(avgPrice, (v) => { if (v !== null) form.price = v })

  function onPhotoFileChange(val: File | File[] | null) {
    const f = Array.isArray(val) ? (val[0] ?? null) : val
    photoFile.value = f
    photoPreview.value = f ? URL.createObjectURL(f) : null
    if (f) form.photo_url = ''
  }

  function addPriceLink() {
    form.priceLinks.push({ url: '', price: null })
  }
  function removePriceLink(i: number) {
    form.priceLinks.splice(i, 1)
  }

  function resetPhotoState() {
    photoFile.value = null
    photoFileList.value = []
    photoPreview.value = null
  }

  function openCreate() {
    Object.assign(form, emptyForm())
    resetPhotoState()
    editingId.value = null
    origPrice.value = null
    // Создание нового товара не ограничено (см. докстринг ProductFormDialog.vue) —
    // значения здесь не влияют на readonly, но держим снэпшот честным.
    emptyAtOpen.description = true
    emptyAtOpen.description_44fz = true
    emptyAtOpen.price = true
    emptyAtOpen.photo = true
    dialog.value = true
  }

  function onProductRowClick(_: any, { item }: { item: Product }) {
    openEdit(item)
  }

  function openEdit(p: Product) {
    Object.assign(form, {
      name: p.name, category: p.category || '', product_type: p.product_type || '', unit: p.unit || '', item_kind: p.item_kind || 'товар',
      pack_quantity: p.pack_quantity != null ? Number(p.pack_quantity) : null,
      pack_unit: p.pack_unit || '',
      pendingPrices: [] as DraftPriceEntry[],  // товар уже сохранён — черновики не используются
      price: p.price ?? null, description: p.description || '', description_44fz: p.description_44fz || '',
      photo_url: p.photo_url || '', photo_link: p.photo_link || '',
      clarification_link: p.clarification_link || '',
      is_active: p.is_active, is_reusable: p.is_reusable ?? true,
      feo_category_id: p.feo_category_id ?? null,
      priceLinks: (p.price_links || []).map(l => ({ url: l.url, price: l.price ?? null })),
      // Один источник — purchase_categories (relationship), backend теперь
      // всегда синхронизирует purchase_category_ids с ним (ПРАВИЛО №6); раньше
      // опасный `??`-фолбэк маскировал то, что backend отдавал [] (баг
      // владельца "категория закупки не сохраняется", товар 5461).
      purchase_category_ids: (p.purchase_categories || []).map(c => c.id),
      country_origin: p.country_origin || 'РФ',
      has_photo: !!p.has_photo,
      price_ttl_days: p.price_ttl_days ?? null,
      // Список товаров (GET /products/) больше не отдаёт characteristics
      // (владелец, 26.10 — тяжёлый JSONB не нужен в списке), поэтому из p
      // здесь почти всегда null/undefined — реальные значения подгружает
      // _loadCharacteristics ниже отдельным запросом GET /products/{id}.
      characteristics: p.characteristics ?? null,
      manufacturer: p.manufacturer || '',
      article: p.article || '',
    })
    photoCacheBuster.value = Date.now()
    resetPhotoState()
    editingId.value = p.id
    origPrice.value = p.price ?? null
    // Снэпшот «пусто/заполнено» на момент открытия (Часть 1 плана, 14.10.2026).
    emptyAtOpen.description = !p.description?.trim()
    emptyAtOpen.description_44fz = !p.description_44fz?.trim()
    emptyAtOpen.price = p.price == null
    emptyAtOpen.photo = !p.has_photo
    editMeta.updated_at = (p as any).updated_at || null
    editMeta.updated_by = (p as any).updated_by || null
    editMeta.import_note = (p as any).import_note || null
    dialog.value = true
    void _loadCharacteristics(p.id)
  }

  // Владелец, 26.10.2026: список товаров больше не отдаёт characteristics/
  // manufacturer/article (см. backend/app/routers/products.py::list_products —
  // defer(Product.characteristics), ответ был слишком тяжёлым на каталоге
  // 53 797 товаров). Карточка товара при открытии существующего товара
  // догружает их отдельным GET /products/{id}. Остальные поля формы НЕ
  // трогаем (пользователь мог начать печатать до ответа) — применяем ответ
  // ТОЛЬКО если editingId не сменился (пользователь быстро открыл другой
  // товар/создал новый, пока запрос letел).
  async function _loadCharacteristics(productId: number) {
    try {
      const full = await apiFetch<Product>(`/products/${productId}`)
      if (editingId.value !== productId) return
      form.characteristics = full.characteristics ?? null
      form.manufacturer = full.manufacturer || ''
      form.article = full.article || ''
    } catch {
      // Молча — characteristics не критичны для остальной работы формы,
      // save() их не требует; showSnack здесь только отвлекал бы внимание
      // от основной задачи редактирования товара.
    }
  }

  // Пункт 2 (владелец, 14.10): после первого сохранения товара отправляет
  // накопленные черновые цены ТЕМ ЖЕ postPriceHistoryEntry, что и обычное
  // «Добавить цену» в PurchasePriceHistory.vue (ПРАВИЛО №6 — один механизм
  // записи истории, не второй). Товару цену проставит последняя отправленная
  // запись (actualize_product_price на бэкенде, backend/app/routers/products.py).
  async function flushPendingPrices(productId: number) {
    for (const entry of form.pendingPrices) {
      await postPriceHistoryEntry(productId, entry)
    }
    form.pendingPrices = []
  }

  async function save() {
    if (!form.name.trim()) { showSnack('Укажите наименование', 'error'); return }
    if (!form.country_origin?.trim()) { showSnack('Укажите страну производства', 'error'); return }
    saving.value = true
    try {
      // price/link.price — v-model.number. `form.price || null` попутно ловит '',
      // но и валидный 0 тоже схлопывает в null; `l.price ?? null` вообще не ловит ''
      // (не null/undefined) — та самая ловушка, найденная владельцем 2026-09-04.
      // numOrNull: '' → null, 0 сохраняется как число.
      // Упаковка (владелец, 14.10): поля валидны только при упаковочной
      // unit — при любом другом unit (или если количество не задано)
      // отправляем явный null, а не оставляем висящее старое значение
      // (backend/app/services/units.py::normalize_pack_fields делает то же
      // самое повторно на сервере — защита от рассинхрона, не единственный
      // барьер).
      const packActive = isPackUnit(form.unit)
      const payload: Record<string, any> = {
        ...form,
        price: numOrNull(form.price),
        price_links: form.priceLinks.filter(l => l.url.trim()).map(l => ({ url: l.url, price: numOrNull(l.price) })),
        pack_quantity: packActive ? numOrNull(form.pack_quantity) : null,
        pack_unit: packActive ? (form.pack_unit?.trim() || null) : null,
      }
      // Пункт 8а (владелец, 14.10): PUT шлёт price только если ПОЛЕ формы
      // реально отличается от origPrice (загруженной/подтверждённой блоком
      // «Цены» цены) — иначе не трогаем его вовсе (backend::update_product
      // не актуализирует цену, когда ключ price не пришёл). Для НОВОГО товара
      // (editingId нет) origPrice всегда null — price шлём как раньше.
      if (editingId.value && payload.price === origPrice.value) {
        delete payload.price
      }
      if (editingId.value) {
        await apiFetch(`/products/${editingId.value}`, { method: 'PUT', body: payload })
        await finishSave(editingId.value, 'Товар обновлён')
      } else {
        try {
          const created = await apiFetch<Product>('/products/', { method: 'POST', body: payload })
          await flushPendingPrices(created.id)
          await finishSave(created.id, 'Товар добавлен')
        } catch (err: any) {
          // FastAPI HTTPException(detail={...}) → apiFetch кладёт исходный
          // dict в err.payload.message (см. api.ts). Тот же разбор, что был
          // раньше в useItemsCatalog.ts::saveFullProduct() и
          // PlannedItemAddDialog.vue — сведено в одно место (ПРАВИЛО №6).
          const detail = err?.payload?.message
          const existing = (err?.status === 409 && typeof detail === 'object' && detail?.code === 'duplicate_product')
            ? detail.existing : null
          if (!existing) throw err
          duplicateExisting.value = existing
          pendingPayload = payload
          duplicateDialog.value = true
          return
        }
      }
    } catch (e: any) {
      // Не глотать причину generic-текстом (память проекта
      // feedback_no_generic_error_snackbar) — общий хелпер, см. также
      // useItemsCatalog.ts::saveFullProduct().
      showSnack(
        describeApiError(e, { fallback: 'Не удалось сохранить товар', prefix: 'Ошибка сохранения' }),
        'error',
      )
    } finally {
      saving.value = false
    }
  }

  // Общий хвост сохранения (фото + закрытие диалога + перезагрузка списка +
  // колбэк onSaved) — одно место для обычного сохранения, выбора
  // существующего дубликата и принудительного создания нового (ниже).
  async function finishSave(savedId: number, successMsg: string) {
    if (photoFile.value) {
      const fd = new FormData()
      fd.append('file', photoFile.value)
      const res = await fetch(`/api/products/${savedId}/photo`, {
        method: 'POST',
        headers: {},
        body: fd,
      })
      if (!res.ok) showSnack('Товар сохранён, но фото не загрузилось', 'warning')
    }
    showSnack(successMsg)
    dialog.value = false
    resetPhotoState()
    await load()
    if (onSaved) {
      // Всегда прямым запросом, а не поиском по products — у части
      // потребителей (usePlanToRequestProductCreate.ts) список не полный
      // каталог, а узкая подсказка по search-запросу, только что созданного
      // товара там может не быть.
      const fresh = await apiFetch<Product>(`/products/${savedId}`).catch(() => null)
      if (fresh) onSaved(fresh)
    }
  }

  // Выбор в диалоге дубликата: «Использовать существующий».
  async function confirmUseExisting() {
    const existing = duplicateExisting.value
    duplicateDialog.value = false
    if (!existing) return
    saving.value = true
    try {
      await flushPendingPrices(existing.id)
      await finishSave(existing.id, `Использован существующий товар «${existing.name}»`)
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось сохранить товар', prefix: 'Ошибка сохранения' }), 'error')
    } finally {
      saving.value = false
      duplicateExisting.value = null
      pendingPayload = null
    }
  }

  // Выбор в диалоге дубликата: «Всё равно создать новый» (POST ?force=true).
  async function confirmCreateNew() {
    const payload = pendingPayload
    duplicateDialog.value = false
    if (!payload) return
    saving.value = true
    try {
      const created = await apiFetch<Product>('/products/?force=true', { method: 'POST', body: payload })
      await flushPendingPrices(created.id)
      await finishSave(created.id, 'Товар добавлен')
    } catch (e: any) {
      showSnack(describeApiError(e, { fallback: 'Не удалось сохранить товар', prefix: 'Ошибка сохранения' }), 'error')
    } finally {
      saving.value = false
      duplicateExisting.value = null
      pendingPayload = null
    }
  }

  function cancelDuplicate() {
    duplicateDialog.value = false
    duplicateExisting.value = null
    pendingPayload = null
  }

  async function toggleSharing(p: any) {
    try {
      const res = await apiFetch<any>(`/products/${p.id}/share-price`, {
        method: 'PATCH',
        body: JSON.stringify({ shared: !p.price_shared }),
      })
      p.price_shared = res.price_shared
      showSnack(p.price_shared ? 'Цена доступна другим организациям' : 'Цена скрыта')
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка', 'error')
    }
  }

  // Single-photo download/delete (внутри диалога редактирования)
  const downloadingPhoto = ref(false)
  const deletingPhoto = ref(false)

  async function clearUploadedPhoto() {
    if (!editingId.value) return
    deletingPhoto.value = true
    try {
      await apiFetch(`/products/${editingId.value}/photo`, { method: 'DELETE' })
      form.photo_url = ''
      form.has_photo = false
      form.photo_size = undefined
      form.photo_mime = undefined
      photoPreview.value = null
      photoFile.value = null
      photoFileList.value = []
      photoCacheBuster.value = Date.now()
      showSnack('Фото удалено', 'success')
    } catch (e: any) {
      showSnack(e?.detail || 'Не удалось удалить фото', 'error')
    } finally {
      deletingPhoto.value = false
    }
  }

  async function downloadSinglePhoto() {
    if (!editingId.value) return
    downloadingPhoto.value = true
    try {
      const updated = await apiFetch<Product>(`/products/${editingId.value}/download-photo`, { method: 'POST' })
      form.photo_url = updated.photo_url || form.photo_url
      form.has_photo = !!updated.has_photo
      photoCacheBuster.value = Date.now()
      showSnack('Фото скачано и сохранено')
      await load()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка скачивания фото', 'error')
    } finally {
      downloadingPhoto.value = false
    }
  }

  return {
    saving, dialog, editingId,
    photoFile, photoFileList, photoPreview,
    form, photoCacheBuster, editMeta, emptyAtOpen,
    nameSearch, nameSuggestions, isDuplicateName,
    avgPrice,
    onPhotoFileChange, addPriceLink, removePriceLink, resetPhotoState,
    openCreate, openEdit, onProductRowClick, save, toggleSharing,
    downloadingPhoto, deletingPhoto, clearUploadedPhoto, downloadSinglePhoto,
    duplicateDialog, duplicateExisting, confirmUseExisting, confirmCreateNew, cancelDuplicate,
    syncPriceFromHistory,
  }
}
