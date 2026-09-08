// useProductsBulkEdit.ts — массовое изменение категории/вида для выбранных
// товаров. Дословный перенос из ProductsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export function useProductsBulkEdit(options: {
  selectedIds: { value: number[] }
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { selectedIds, load, showSnack } = options

  const bulkEditDialog = ref(false)
  const bulkEditCategory = ref<string | null>(null)
  const bulkEditType = ref<string | null>(null)
  const bulkEditing = ref(false)

  function openBulkEdit() {
    bulkEditCategory.value = null
    bulkEditType.value = null
    bulkEditDialog.value = true
  }

  async function doBulkEdit() {
    const body: Record<string, string> = {}
    const cat = (bulkEditCategory.value || '').trim()
    const pt = (bulkEditType.value || '').trim()
    if (cat) body.category = cat
    if (pt) body.product_type = pt
    if (!Object.keys(body).length) {
      showSnack('Укажите новую категорию и/или вид', 'warning')
      return
    }
    const ids = [...selectedIds.value]
    bulkEditing.value = true
    try {
      await Promise.all(ids.map(id => apiFetch(`/products/${id}`, { method: 'PATCH', body })))
      showSnack(`Обновлено ${ids.length} товаров`)
      bulkEditDialog.value = false
      selectedIds.value = []
      await load()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка массового обновления', 'error')
    } finally {
      bulkEditing.value = false
    }
  }

  return { bulkEditDialog, bulkEditCategory, bulkEditType, bulkEditing, openBulkEdit, doBulkEdit }
}
