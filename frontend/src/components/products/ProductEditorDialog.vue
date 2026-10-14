<!-- ProductEditorDialog.vue — единое окно создания/правки товара ВНЕ страницы
     «Товары» (ПРАВИЛО №6, задание владельца 14.10: «везде, где заводится/
     правится товар, открывается ОДНО окно с одинаковыми полями»). Тонкая
     обёртка над каталожным useProductsForm.ts + ProductFormDialog.vue — тем
     же, чем раньше была урезанная копия components/items/FullProductDialog.vue
     и 20 пропсов ProductFormDialog напрямую в PlanToRequestRow.vue. Второй
     формы/валидации/эндпоинта не заводит.

     Открывается программно через defineExpose({ open }) — у вызывающего кода
     (PurchaseItemsEditor.vue, PlanToRequestRow.vue, PlanToRequestDialog.vue,
     PlannedItemAddDialog.vue) нет повода знать о внутренностях формы, только
     предзаполнение и результат (emit('saved', product)). -->
<template>
  <ProductFormDialog
    v-model="form.dialog.value"
    v-model:name-search="form.nameSearch.value"
    :mobile="mobile"
    :editing-id="form.editingId.value"
    :can-edit-catalog="canEditCatalog"
    :empty-at-open="form.emptyAtOpen"
    :edit-meta="form.editMeta"
    :form="form.form"
    :name-suggestions="form.nameSuggestions.value"
    :is-duplicate-name="form.isDuplicateName.value"
    :type-options="typeOptions"
    :category-options="categoryOptions"
    :avg-price="form.avgPrice.value"
    :photo-preview="form.photoPreview.value"
    :photo-file="form.photoFile.value"
    :photo-file-list="form.photoFileList.value"
    :photo-cache-buster="form.photoCacheBuster.value"
    :downloading-photo="form.downloadingPhoto.value"
    :deleting-photo="form.deletingPhoto.value"
    :saving="form.saving.value"
    :duplicate-dialog="form.duplicateDialog.value"
    :duplicate-existing="form.duplicateExisting.value"
    :queue-label="queueLabel"
    :show-skip="showSkip"
    @save="form.save"
    @clear-photo="form.clearUploadedPhoto"
    @download-photo="form.downloadSinglePhoto"
    @confirm-use-existing="form.confirmUseExisting"
    @confirm-create-new="form.confirmCreateNew"
    @cancel-duplicate="form.cancelDuplicate"
    @photo-file-change="form.onPhotoFileChange"
    @price-synced="form.syncPriceFromHistory($event.price)"
    @skip="$emit('skip')"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import ProductFormDialog from '@/components/products/ProductFormDialog.vue'
import { useProductsForm } from '@/composables/products/useProductsForm'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { ACTIONS } from '@/constants/permissionActions'
import type { Product } from '@/composables/products/productsTypes'

const { mobile } = useDisplay()
const toast = useToast()
// Защита каталога (Этап В, план item-tz-description.md, владелец 14.10.2026) —
// тот же механизм проверки права, что и в ProductsView.vue (ПРАВИЛО №6),
// не вторая проверка.
const authStore = useAuthStore()
const canEditCatalog = computed(() => authStore.hasAction(ACTIONS.PRODUCTS_EDIT_CATALOG!))
const showSnack = (text: string, color: 'success' | 'error' | 'info' | 'warning' = 'success') =>
  toast.addToast(text, color)

defineProps<{
  // Массовое «Добавить в каталог» (composables/items/useBulkProductCreateQueue.ts,
  // владелец 14.10) — «Позиция N из M» в заголовке и кнопка «Пропустить».
  // Остальные вызывающие (одна позиция, PlanToRequestRow и т.д.) их не передают.
  queueLabel?: string
  showSkip?: boolean
}>()

const emit = defineEmits<{
  (e: 'saved', product: Product): void
  (e: 'skip'): void
  // Диалог закрыт БЕЗ сохранения (Отмена/крестик/клик вовне) — отличается от
  // 'saved': массовая очередь (useBulkProductCreateQueue.ts) считает это
  // концом очереди, а не переходом к следующей позиции.
  (e: 'closed'): void
}>()

// Узкая подсказка по названию (search + limit=20 + is_active=true) — НЕ весь
// каталог (те самые ≈4.4 МБ, источник тормозов владельца). Тот же контракт,
// что usePlanToRequestProductCreate.ts/PlanToRequestDialog.vue::runSearch.
const products = ref<Product[]>([])
let searchedFor = ''
async function loadFor(q: string) {
  searchedFor = q
  try {
    const params = new URLSearchParams()
    if (q.trim()) params.set('search', q.trim())
    params.set('limit', '20')
    params.set('is_active', 'true')
    products.value = await apiFetch<Product[]>(`/products/?${params.toString()}`)
  } catch {
    // Подсказки необязательны — форма создания/правки работает и без них.
  }
}
// useProductsForm.load() вызывается без параметров (напр. после сохранения) —
// перечитываем тем же последним поисковым запросом.
async function load() {
  await loadFor(searchedFor)
}

const typeOptions = computed(() =>
  [...new Set(products.value.map(p => p.product_type).filter(Boolean) as string[])].sort(),
)
const categoryOptions = computed(() =>
  [...new Set(products.value.map(p => p.category).filter(Boolean) as string[])].sort(),
)

const form = useProductsForm({
  products,
  load,
  showSnack,
  onSaved: (p) => emit('saved', p),
})

interface ProductEditorOpenOptions {
  productId?: number | null
  name?: string
  unit?: string | null
  price?: number | null
}

async function open(opts: ProductEditorOpenOptions = {}) {
  if (opts.productId) {
    // Узкая подсказка по имени товара, затем полноценная карточка — тем же
    // путём, что openQuickProductEdit() раньше делал в useItemsCatalog.ts.
    const fresh = await apiFetch<Product>(`/products/${opts.productId}`).catch(() => null)
    if (fresh) {
      await loadFor(fresh.name || '')
      form.openEdit(fresh)
      return
    }
  }
  form.openCreate()
  if (opts.name) form.form.name = opts.name
  if (opts.unit) form.form.unit = opts.unit
  if (opts.price != null && Number.isFinite(opts.price) && opts.price > 0) form.form.price = opts.price
  await loadFor(opts.name || '')
}

// Диалог закрыт БЕЗ сохранения (Отмена/крестик/клик вовне) — отличаем от
// закрытия ПОСЛЕ успешного сохранения (useProductsForm.ts::finishSave тоже
// ставит dialog=false, но делает это пока saving.value ещё true — флаг снят
// только в finally самого save()). Массовая очередь
// (useBulkProductCreateQueue.ts) слушает 'closed' как сигнал «пользователь
// прервал очередь», а не «перейти к следующей позиции».
watch(() => form.dialog.value, (v) => {
  if (!v && !form.saving.value) emit('closed')
})

defineExpose({ open })
</script>
