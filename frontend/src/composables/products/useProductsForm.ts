// useProductsForm.ts — диалог добавления/редактирования товара: форма, фото,
// ссылки для сравнения цен, автоподсказки по названию. Дословный перенос из
// ProductsView.vue.
import { ref, computed, reactive, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import type { Product, PriceLink } from './productsTypes'

export function useProductsForm(options: {
  products: { value: Product[] }
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { products, load, showSnack } = options

  const saving = ref(false)
  const dialog = ref(false)
  const editingId = ref<number | null>(null)

  // Photo upload state
  const photoFile     = ref<File | null>(null)
  const photoFileList = ref<File[]>([])
  const photoPreview  = ref<string | null>(null)

  const emptyForm = () => ({
    name: '', category: '', product_type: '', unit: '' as string, item_kind: 'товар' as string, price: null as number | null,
    description: '', description_44fz: '', photo_url: '', photo_link: '', clarification_link: '',
    is_active: true, is_reusable: true, feo_category_id: null as number | null,
    priceLinks: [] as PriceLink[],
    country_origin: 'РФ' as string,
    has_photo: false as boolean,
    price_ttl_days: null as number | null,
  })
  const form = reactive(emptyForm())
  // Bumped when we re-download / re-upload so the <img> bypasses browser cache.
  const photoCacheBuster = ref(0)
  const editMeta = reactive({ updated_at: null as string | null, updated_by: null as string | null, import_note: null as string | null })

  // Name autocomplete + duplicate detection
  const nameSearch = ref('')
  const nameSuggestions = computed(() => {
    const q = (nameSearch.value || '').toLowerCase().trim()
    if (q.length < 2) return []
    return products.value
      .filter(p => p.name.toLowerCase().includes(q) && p.id !== editingId.value)
      .map(p => p.name)
      .slice(0, 15)
  })
  const isDuplicateName = computed(() => {
    if (!form.name) return false
    const q = (typeof form.name === 'string' ? form.name : '').toLowerCase().trim()
    if (!q) return false
    return products.value.some(p => p.name.toLowerCase().trim() === q && p.id !== editingId.value)
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
    dialog.value = true
  }

  function onProductRowClick(_: any, { item }: { item: Product }) {
    openEdit(item)
  }

  function openEdit(p: Product) {
    Object.assign(form, {
      name: p.name, category: p.category || '', product_type: p.product_type || '', unit: p.unit || '', item_kind: p.item_kind || 'товар',
      price: p.price ?? null, description: p.description || '', description_44fz: p.description_44fz || '',
      photo_url: p.photo_url || '', photo_link: p.photo_link || '',
      clarification_link: p.clarification_link || '',
      is_active: p.is_active, is_reusable: p.is_reusable ?? true,
      feo_category_id: p.feo_category_id ?? null,
      priceLinks: (p.price_links || []).map(l => ({ url: l.url, price: l.price ?? null })),
      country_origin: p.country_origin || 'РФ',
      has_photo: !!p.has_photo,
      price_ttl_days: p.price_ttl_days ?? null,
    })
    photoCacheBuster.value = Date.now()
    resetPhotoState()
    editingId.value = p.id
    editMeta.updated_at = (p as any).updated_at || null
    editMeta.updated_by = (p as any).updated_by || null
    editMeta.import_note = (p as any).import_note || null
    dialog.value = true
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
      const payload = {
        ...form,
        price: numOrNull(form.price),
        price_links: form.priceLinks.filter(l => l.url.trim()).map(l => ({ url: l.url, price: numOrNull(l.price) })),
      }
      let savedId: number
      if (editingId.value) {
        await apiFetch(`/products/${editingId.value}`, { method: 'PUT', body: payload })
        savedId = editingId.value
        showSnack('Товар обновлён')
      } else {
        const created = await apiFetch<Product>('/products/', { method: 'POST', body: payload })
        savedId = created.id
        showSnack('Товар добавлен')
      }

      if (photoFile.value) {
        const fd = new FormData()
        fd.append('file', photoFile.value)
        const token = localStorage.getItem('auth_token')
        const res = await fetch(`/api/products/${savedId}/photo`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: fd,
        })
        if (!res.ok) showSnack('Товар сохранён, но фото не загрузилось', 'warning')
      }

      dialog.value = false
      resetPhotoState()
      await load()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка сохранения', 'error')
    } finally {
      saving.value = false
    }
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
    form, photoCacheBuster, editMeta,
    nameSearch, nameSuggestions, isDuplicateName,
    avgPrice,
    onPhotoFileChange, addPriceLink, removePriceLink, resetPhotoState,
    openCreate, openEdit, onProductRowClick, save, toggleSharing,
    downloadingPhoto, deletingPhoto, clearUploadedPhoto, downloadSinglePhoto,
  }
}
