// useProductsDelete.ts — удаление товара / массовое удаление / удаление всех /
// массовая активация-деактивация. Дословный перенос из ProductsView.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Product, ProductDeleteImpact } from './productsTypes'

// Форма 409 отданная backend/app/services/product_delete_impact.py — извлекаем
// message/impact из структурированного detail (api.ts сохраняет его целиком в
// err.payload.details, см. память проекта «Не глотать ошибки generic-снэкбаром»).
function extractBlockInfo(e: any): { message: string; impact: ProductDeleteImpact | null } {
  const details = e?.payload?.details
  if (details && typeof details === 'object' && details.code === 'PRODUCT_HAS_DEPENDENTS') {
    return { message: details.message || e?.detail || 'Товар нельзя удалить: есть связанные записи', impact: details.impact || null }
  }
  return { message: e?.detail || e?.payload?.message || 'Ошибка удаления', impact: null }
}

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
  // 409 «нельзя удалить»: сообщение + разбор по группам (закупки/заявки/
  // договоры/КП) со ссылками на карточки — не generic-снэкбар (Правило проекта).
  const deleteBlockMessage = ref('')
  const deleteBlockImpact = ref<ProductDeleteImpact | null>(null)

  function confirmDelete(p: Product) {
    deleteTarget.value = p
    deleteBlockMessage.value = ''
    deleteBlockImpact.value = null
    deleteDialog.value = true
  }

  async function doDelete() {
    if (!deleteTarget.value) return
    deleting.value = true
    deleteBlockMessage.value = ''
    deleteBlockImpact.value = null
    try {
      await apiFetch(`/products/${deleteTarget.value.id}`, { method: 'DELETE' })
      showSnack('Товар удалён')
      deleteDialog.value = false
      selectedIds.value = selectedIds.value.filter(id => id !== deleteTarget.value!.id)
      await load()
    } catch (e: any) {
      if (e?.status === 409) {
        // Диалог остаётся открытым — показываем причину и список ссылок,
        // не закрываем на generic-ошибку (владелец: «объяснять причину блокировки»).
        const { message, impact } = extractBlockInfo(e)
        deleteBlockMessage.value = message
        deleteBlockImpact.value = impact
      } else {
        showSnack(e?.detail || 'Ошибка удаления', 'error')
      }
    } finally {
      deleting.value = false
    }
  }

  const bulkDeleting = ref(false)
  const bulkDeleteDialog = ref(false)
  // Массовое удаление: часть товаров может быть заблокирована — каждому
  // отказу своя причина (не общий "ошибка при удалении" на всю пачку).
  const bulkDeleteBlocked = ref<{ id: number; name: string; message: string }[]>([])

  async function doBulkDelete() {
    bulkDeleting.value = true
    bulkDeleteBlocked.value = []
    const ids = [...selectedIds.value]
    const blocked: { id: number; name: string; message: string }[] = []
    let okCount = 0
    for (const id of ids) {
      try {
        await apiFetch(`/products/${id}`, { method: 'DELETE' })
        okCount += 1
      } catch (e: any) {
        const product = products.value.find(p => p.id === id)
        const { message } = e?.status === 409 ? extractBlockInfo(e) : { message: e?.detail || 'Ошибка удаления' }
        blocked.push({ id, name: product?.name || `#${id}`, message })
      }
    }
    bulkDeleteBlocked.value = blocked
    if (okCount > 0) {
      showSnack(blocked.length > 0 ? `Удалено ${okCount} из ${ids.length} товаров` : `Удалено ${okCount} товаров`, blocked.length > 0 ? 'warning' : 'success')
      selectedIds.value = selectedIds.value.filter(id => !ids.includes(id) || blocked.some(b => b.id === id))
      await load()
    } else if (blocked.length > 0) {
      showSnack('Ни один товар не удалён — все заблокированы связанными записями', 'error')
    }
    if (blocked.length === 0) {
      bulkDeleteDialog.value = false
    }
    bulkDeleting.value = false
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
    deleteBlockMessage, deleteBlockImpact,
    bulkDeleting, bulkDeleteDialog, doBulkDelete, bulkDeleteBlocked,
    deletingAll, deleteAllDialog, deleteAllConfirm, doDeleteAll,
    bulkToggleActive,
  }
}
