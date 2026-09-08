// useProductsDelete.ts — удаление товара / массовое удаление / удаление всех /
// массовая активация-деактивация. Дословный перенос из ProductsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Product } from './productsTypes'

export function useProductsDelete(options: {
  products: { value: Product[] }
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { products, load, showSnack } = options

  const selectedIds = ref<number[]>([])

  const deleting = ref(false)
  const deleteDialog = ref(false)
  const deleteTarget = ref<Product | null>(null)

  function confirmDelete(p: Product) {
    deleteTarget.value = p
    deleteDialog.value = true
  }

  async function doDelete() {
    if (!deleteTarget.value) return
    deleting.value = true
    try {
      await apiFetch(`/products/${deleteTarget.value.id}`, { method: 'DELETE' })
      showSnack('Товар удалён')
      deleteDialog.value = false
      selectedIds.value = selectedIds.value.filter(id => id !== deleteTarget.value!.id)
      await load()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка удаления', 'error')
    } finally {
      deleting.value = false
    }
  }

  const bulkDeleting = ref(false)
  const bulkDeleteDialog = ref(false)

  async function doBulkDelete() {
    bulkDeleting.value = true
    const ids = [...selectedIds.value]
    try {
      await Promise.all(ids.map(id => apiFetch(`/products/${id}`, { method: 'DELETE' })))
      showSnack(`Удалено ${ids.length} товаров`)
      bulkDeleteDialog.value = false
      selectedIds.value = []
      await load()
    } catch {
      showSnack('Ошибка при удалении', 'error')
    } finally {
      bulkDeleting.value = false
    }
  }

  const deletingAll = ref(false)
  const deleteAllDialog = ref(false)
  const deleteAllConfirm = ref('')

  async function doDeleteAll() {
    deletingAll.value = true
    try {
      const res = await apiFetch<{message: string}>('/products/bulk/all', { method: 'DELETE' })
      showSnack(res.message || 'Все товары удалены')
      deleteAllDialog.value = false
      deleteAllConfirm.value = ''
      selectedIds.value = []
      await load()
    } catch {
      showSnack('Ошибка при удалении', 'error')
    } finally {
      deletingAll.value = false
    }
  }

  async function bulkToggleActive(active: boolean) {
    const ids = [...selectedIds.value]
    try {
      await Promise.all(ids.map(id => {
        const p = products.value.find(p => p.id === id)
        if (!p) return Promise.resolve()
        return apiFetch(`/products/${id}`, {
          method: 'PUT',
          body: { name: p.name, is_active: active, price_links: p.price_links || [] },
        })
      }))
      showSnack(`${active ? 'Активировано' : 'Деактивировано'} ${ids.length} товаров`)
      selectedIds.value = []
      await load()
    } catch {
      showSnack('Ошибка обновления', 'error')
    }
  }

  return {
    selectedIds,
    deleting, deleteDialog, deleteTarget, confirmDelete, doDelete,
    bulkDeleting, bulkDeleteDialog, doBulkDelete,
    deletingAll, deleteAllDialog, deleteAllConfirm, doDeleteAll,
    bulkToggleActive,
  }
}
